# Operational Runbook

**Document ID:** RB-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Overview](#1-overview)
2. [Alert: ServiceDown](#2-alert-servicedown)
3. [Alert: HighErrorRate](#3-alert-higherrorrate)
4. [Alert: HighLatency](#4-alert-highlatency)
5. [Alert: HighCPU](#5-alert-highcpu)
6. [Routine Procedures](#6-routine-procedures)

---

## 1. Overview

This runbook provides step-by-step procedures for responding to each
Prometheus alert defined in `prometheus/alerts.yml`. Each section maps an
alert to triage, diagnosis, resolution, and post-incident actions.

**Prerequisite access:**
- SSH access to the droplet (`ssh root@<DROPLET_IP>`)
- HTTP access to the application (`http://<DROPLET_IP>`)
- `CHAOS_TOKEN` value (for chaos testing only)

**Notation:**
- `$HOST` refers to the application URL (e.g., `http://161.35.198.232`)
- All `curl` commands can be run from any machine with network access

---

## 2. Alert: ServiceDown

**Rule:** `up{job="flask_app"} == 0` for 10 seconds
**Severity:** critical
**Meaning:** Prometheus cannot reach the application's `/metrics` endpoint.
The application container is either crashed, restarting, or unreachable.

### Step 1: Confirm the alert

```bash
curl -sf $HOST/health
# If no response or connection refused: confirmed down
# If {"status":"ok"}: false alarm, check Prometheus → app connectivity
```

### Step 2: Check container status

```bash
ssh root@<DROPLET_IP>
docker ps -a --filter name=app
# Look for: STATUS column (Up, Restarting, Exited)
# Look for: RESTARTS count (high count = crash loop)
```

### Step 3: Read container logs

```bash
docker logs app --tail 50 --timestamps
# Look for: Python tracebacks, OOMKilled, segfaults
# Look for: Gunicorn worker timeout messages
```

### Step 4: Resolve

**If container is in a crash loop:**
```bash
docker compose logs app --tail 100
# Identify root cause (bad config, missing env var, DB failure)
# Fix the issue, then:
docker compose up -d --build
```

**If container exited and did not restart:**
```bash
docker compose up -d
```

**If container is running but /metrics unreachable:**
```bash
# Check if Gunicorn is listening
docker exec app curl -sf http://localhost:5000/health
# If this works: network issue between Prometheus and app
docker compose restart prometheus
```

### Step 5: Verify recovery

```bash
curl -sf $HOST/health
# Expected: {"status":"ok"}

curl -sf $HOST/metrics | head -5
# Expected: Prometheus text metrics
```

### Step 6: Post-incident

1. Check `/logs?level=ERROR&limit=50` for related errors.
2. Review container restart count: `docker inspect app | grep RestartCount`.
3. If a code change caused the crash, roll back per [CI_CD.md](CI_CD.md)
   Section 7.

---

## 3. Alert: HighErrorRate

**Rule:** `sum(rate(flask_http_request_total{status=~"5.."}[1m])) / sum(rate(flask_http_request_total[1m])) > 0.1` for 30 seconds
**Severity:** warning
**Meaning:** More than 10% of HTTP responses are 5xx errors. The application
is failing a significant portion of requests.

### Step 1: Identify error type

```bash
curl -s "$HOST/logs?level=ERROR&limit=50" | python3 -m json.tool
# Look for: repeated error messages, stack traces
# Common patterns:
#   "Database connection failed" → DB issue (see Step 2a)
#   "Internal server error"      → Application bug (see Step 2b)
#   "Failed to generate unique code" → Short code collision (see Step 2c)
```

### Step 2a: Database errors (503s)

```bash
ssh root@<DROPLET_IP>
docker logs db --tail 20
# Check for: "too many connections", "no space left on device"

# Verify DB is responsive
docker exec db pg_isready -U postgres
# Expected: accepting connections

# If DB is down:
docker compose restart db
sleep 10
curl -s $HOST/users | head -c 100
```

### Step 2b: Application errors (500s)

```bash
docker logs app --tail 50 --timestamps
# Look for Python tracebacks
# If caused by a recent deploy: rollback per CI_CD.md Section 7
```

### Step 2c: Short code collisions

If errors are `"Failed to generate unique code"`, the short_urls table has
high collision density. This is rare with 6-character alphanumeric codes
(~56 billion combinations).

```bash
docker exec db psql -U postgres -d hackathon_db -c "SELECT COUNT(*) FROM short_urls;"
# If > 1 million rows: consider increasing code length
```

### Step 3: Verify resolution

```bash
# Check current error rate via Prometheus
curl -s "http://<DROPLET_IP>:9090/api/v1/query?query=sum(rate(flask_http_request_total{status=~\"5..\"}[1m]))/sum(rate(flask_http_request_total[1m]))"
# Expected: value < 0.1
```

### Step 4: Post-incident

1. Record the error type and root cause.
2. If a code fix is needed, deploy through CI pipeline.
3. Monitor error rate for 10 minutes to confirm stability.

---

## 4. Alert: HighLatency

**Rule:** `rate(flask_http_request_duration_seconds_sum[1m]) / rate(flask_http_request_duration_seconds_count[1m]) > 1` for 1 minute
**Severity:** warning
**Meaning:** Average request duration exceeds 1 second. The application is
responding slowly.

### Step 1: Identify the slow endpoint

```bash
# Check per-endpoint latency in Prometheus
curl -s "http://<DROPLET_IP>:9090/api/v1/query?query=rate(flask_http_request_duration_seconds_sum[1m])/rate(flask_http_request_duration_seconds_count[1m])" | python3 -m json.tool
# Look for: which endpoint has the highest value
```

### Step 2: Check database performance

```bash
ssh root@<DROPLET_IP>
docker exec db psql -U postgres -d hackathon_db -c \
  "SELECT pid, now() - query_start AS duration, query
   FROM pg_stat_activity
   WHERE state = 'active'
   ORDER BY duration DESC
   LIMIT 10;"
# Look for: queries running > 1 second
```

**If long-running queries found:**
```bash
# Cancel a specific query
docker exec db psql -U postgres -d hackathon_db -c "SELECT pg_cancel_backend(<pid>);"
```

### Step 3: Check connection pool saturation

```bash
docker exec db psql -U postgres -d hackathon_db -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'hackathon_db';"
# Max connections per app instance: 10
# If at 10: pool is saturated, requests are queuing
```

### Step 4: Check system resources

```bash
ssh root@<DROPLET_IP>
# CPU and memory
top -bn1 | head -20
# Disk I/O
iostat -x 1 3
# If CPU > 90%: see HighCPU runbook
# If disk I/O wait > 50%: database storage is the bottleneck
```

### Step 5: Resolution options

| Cause | Action |
|-------|--------|
| Slow queries | Add database indexes or optimize queries |
| Pool saturation | Increase `max_connections` in `app/database.py` (currently 10) |
| CPU saturation | Enable replicas: uncomment `deploy.replicas: 2` in `docker-compose.yml` |
| High traffic spike | Scale replicas and wait for traffic to normalize |

### Step 6: Verify resolution

```bash
curl -s $HOST/health
# Response time should be < 100ms

# Run a quick load sample
for i in $(seq 1 10); do
    curl -s -o /dev/null -w "%{time_total}\n" $HOST/urls?page=1\&per_page=10
done
# Expected: all under 1 second
```

---

## 5. Alert: HighCPU

**Rule:** `rate(process_cpu_seconds_total[1m]) > 0.9` for 2 minutes
**Severity:** warning
**Meaning:** The application process is consuming more than 90% CPU for a
sustained period.

### Step 1: Confirm CPU usage

```bash
ssh root@<DROPLET_IP>
top -bn1 | grep -E "gunicorn|python"
# Look for: %CPU column
# Also check system-wide:
uptime
# Load average > number of CPUs = saturated
```

### Step 2: Identify the cause

```bash
# Check if it's load-driven
docker logs app --tail 20 --timestamps
# High request volume: many access log entries per second

# Check request rate via Prometheus
curl -s "http://<DROPLET_IP>:9090/api/v1/query?query=rate(flask_http_request_total[1m])" | python3 -m json.tool
```

### Step 3: Resolution options

| Cause | Action |
|-------|--------|
| High request volume | Enable replicas: uncomment `deploy.replicas: 2` in `docker-compose.yml`, run `docker compose up -d` |
| Gunicorn worker spin | Restart the app: `docker compose restart app` |
| Inefficient query pattern | Check `/logs?filter=slow` and optimize |

### Step 4: Enable horizontal scaling (if needed)

```bash
ssh root@<DROPLET_IP>
cd PE_Hackathon

# Edit docker-compose.yml: uncomment replicas
# deploy:
#   replicas: 2

docker compose up -d
docker ps --filter name=app
# Should show 2 app containers
```

### Step 5: Verify resolution

```bash
# CPU should drop below 90%
ssh root@<DROPLET_IP>
top -bn1 | grep -E "gunicorn|python"

# Check process metrics
curl -s $HOST/metrics | grep process_cpu_seconds_total
```

---

## 6. Routine Procedures

### 6.1 Daily Health Check

```bash
curl -s $HOST/health
curl -s "$HOST/logs?level=ERROR&limit=10" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Errors: {d[\"count\"]}')"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 6.2 View Running Container Status

```bash
ssh root@<DROPLET_IP>
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# All services should show "Up" with healthy status
```

### 6.3 Restart a Single Service

```bash
docker compose restart <service>
# service: app, db, nginx, prometheus, alertmanager, grafana
```

### 6.4 Full Stack Restart

```bash
docker compose down
docker compose up -d --build
```

### 6.5 View Disk Usage

```bash
docker system df
df -h /var/lib/docker
# If disk > 80%:
docker image prune -af
docker volume prune -f  # WARNING: deletes unused volumes
```

### 6.6 Database Maintenance

```bash
# Check table sizes
docker exec db psql -U postgres -d hackathon_db -c \
  "SELECT relname, pg_size_pretty(pg_total_relation_size(oid))
   FROM pg_class WHERE relkind = 'r'
   ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;"

# Purge old events (if needed)
docker exec db psql -U postgres -d hackathon_db -c \
  "DELETE FROM events WHERE timestamp < NOW() - INTERVAL '90 days';"

# Reclaim space
docker exec db psql -U postgres -d hackathon_db -c "VACUUM FULL;"
```

---

## Related Documentation

- [FAILURE_MODES.md](FAILURE_MODES.md) -- Failure scenarios and chaos testing
  runbook.
- [OBSERVABILITY.md](OBSERVABILITY.md) -- Alert rule definitions and Prometheus
  configuration.
- [INCIDENT_RESPONSE_BRONZE.md](INCIDENT_RESPONSE_BRONZE.md) -- Log inspection
  and incident workflow.
- [CI_CD.md](CI_CD.md) -- Rollback procedure (Section 7).
