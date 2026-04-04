# Failure Modes and Recovery Procedures

**Document ID:** FM-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-04
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Scope](#1-scope)
2. [System Architecture](#2-system-architecture)
3. [Failure Mode Catalog](#3-failure-mode-catalog)
   - 3.1 [Application Process Crash](#31-application-process-crash)
   - 3.2 [Database Connection Failure](#32-database-connection-failure)
   - 3.3 [Database Disk Exhaustion](#33-database-disk-exhaustion)
   - 3.4 [Reverse Proxy Failure](#34-reverse-proxy-failure)
   - 3.5 [Network Partition Between Services](#35-network-partition-between-services)
   - 3.6 [Malformed Client Input](#36-malformed-client-input)
   - 3.7 [Container Out-of-Memory Kill](#37-container-out-of-memory-kill)
   - 3.8 [Volume Data Corruption](#38-volume-data-corruption)
   - 3.9 [Upstream Dependency Timeout](#39-upstream-dependency-timeout)
   - 3.10 [Concurrent Write Conflicts](#310-concurrent-write-conflicts)
4. [Recovery Procedures](#4-recovery-procedures)
5. [Chaos Testing Runbook](#5-chaos-testing-runbook)
6. [Monitoring and Detection](#6-monitoring-and-detection)

---

## 1. Scope

This document catalogs all known failure modes of the URL Shortener service, describes their observable symptoms, documents the automated and manual recovery mechanisms in place, and provides runbooks for chaos testing.

The system under scope consists of three containerized services:

| Service | Image | Role |
|---------|-------|------|
| `app` | Custom (Python 3.13 / Gunicorn) | Application server |
| `db` | postgres:17-alpine | Persistent data store |
| `nginx` | nginx:1.28-alpine | Reverse proxy and load balancer |

---

## 2. System Architecture

```
Client --> Nginx (:80) --> Gunicorn (:5000, 4 workers) --> PostgreSQL (:5432)
```

All services run within a single Docker Compose stack on a shared bridge network (`app-network`). Data persistence is provided by the `pgdata` named volume.

**Resiliency controls in place:**

| Control | Implementation |
|---------|---------------|
| Process supervision | `restart: always` on all three services |
| Health monitoring | Docker `HEALTHCHECK` on `app` (HTTP) and `db` (pg_isready) |
| Startup ordering | `depends_on` with `condition: service_healthy` |
| Connection management | Per-request connect/disconnect via Peewee hooks |
| Graceful shutdown | Gunicorn SIGTERM handling with 120s worker timeout |
| Input validation | Boundary validation on all route handlers |
| Error isolation | Global exception handler returns JSON, never stack traces |

---

## 3. Failure Mode Catalog

### 3.1 Application Process Crash

**Trigger:** Unhandled signal, segfault in native extension, or internal process crash.

**Detection:**
- Docker daemon detects container exit (non-zero status).
- Nginx receives `502 Bad Gateway` on upstream connection refusal.
- Docker healthcheck fails after three consecutive probes.

**Impact:**
- All in-flight requests to the affected container receive `502`.
- No data loss; database transactions are atomic.
- Redirect click counts for requests in transit may not be recorded.

**Automated Recovery:**
- Docker restart policy (`restart: always`) restarts the container.
- Gunicorn preloads the application; workers are ready within seconds.
- Nginx retries upstream on the next client request after restart.

**Note on `docker kill` vs internal crash:** Docker treats `docker kill` and
`docker stop` as deliberate manual stops and suppresses the restart policy. To
trigger automatic restart, the main process (PID 1) must terminate from within
the container (e.g., crash, `kill 1` via `docker exec`).

**Estimated Recovery Time:** 3-10 seconds (container restart + healthcheck).

**Verification:**
```bash
# Send SIGTERM to the gunicorn master (PID 1) inside the container
docker exec hack-app-1 kill -TERM 1

# Poll for recovery (expect < 10 seconds)
for i in $(seq 1 20); do
    sleep 1
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo "Recovered after ${i}s"
        break
    fi
done
```

---

### 3.2 Database Connection Failure

**Trigger:** PostgreSQL service crash, restart, network disruption, or max connections exceeded.

**Detection:**
- `before_request` hook catches `OperationalError` on `db.connect()`.
- Application returns HTTP 503 with `{"error": "Service unavailable"}`.
- Container healthcheck eventually fails if database remains down.

**Impact:**
- All data operations fail. Health endpoint continues to respond (no DB dependency).
- Clients receive 503 instead of unhandled exceptions or connection timeouts.
- No data corruption; uncommitted transactions are rolled back by PostgreSQL.

**Automated Recovery:**
- PostgreSQL container has `restart: always` and its own healthcheck.
- Application reconnects on the next request after database recovers (per-request connection model).
- No connection pool staling; each request opens a fresh connection.

**Estimated Recovery Time:** 5-15 seconds (PostgreSQL restart + healthcheck pass).

**Verification:**
```bash
docker stop hack-db-1
curl -s http://localhost/users
# Expected: {"error":"Service unavailable","status":503}
docker start hack-db-1
# Wait for healthcheck
curl -s http://localhost/users
# Expected: [...]
```

---

### 3.3 Database Disk Exhaustion

**Trigger:** `pgdata` volume fills to capacity.

**Detection:**
- PostgreSQL logs `PANIC: could not write to file` or `No space left on device`.
- Write operations (POST, PUT, DELETE) fail with HTTP 500.
- Read operations may continue to succeed from buffer cache.

**Impact:**
- All write operations fail. Reads may continue temporarily.
- PostgreSQL may shut down if WAL cannot be written.
- Auto-seed on startup will fail silently (caught by `try/except` in app factory).

**Manual Recovery:**
1. Identify large tables: `docker exec hack-db-1 psql -U postgres -c "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) FROM pg_class ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;"`
2. Purge old events: `DELETE FROM event WHERE timestamp < NOW() - INTERVAL '90 days';`
3. Run `VACUUM FULL;` to reclaim space.
4. If volume is unrecoverable, recreate: `docker compose down -v && docker compose up -d`

**Estimated Recovery Time:** Minutes (manual intervention required).

---

### 3.4 Reverse Proxy Failure

**Trigger:** Nginx container crash, misconfiguration, or port binding conflict.

**Detection:**
- Clients receive connection refused on port 80.
- Docker daemon detects container exit.

**Impact:**
- All external traffic is blocked. Application and database remain functional.
- Direct access to port 5000 is not exposed; service is fully unavailable externally.

**Automated Recovery:**
- `restart: always` restarts the Nginx container.
- Nginx startup is near-instant (sub-second).

**Estimated Recovery Time:** 1-3 seconds.

**Verification:**
```bash
docker kill hack-nginx-1
# Wait 3 seconds
curl -s http://localhost/health
# Expected: {"status":"ok"}
```

---

### 3.5 Network Partition Between Services

**Trigger:** Docker network failure, DNS resolution failure within `app-network`.

**Detection:**
- Application logs connection timeouts to `db:5432`.
- Nginx logs upstream connection failures to `app:5000`.
- HTTP responses return 503 (app-to-db) or 502 (nginx-to-app).

**Impact:**
- Partial or total service disruption depending on which link is severed.
- No data loss; PostgreSQL maintains data integrity independently.

**Manual Recovery:**
1. Inspect network: `docker network inspect hack_app-network`
2. Restart affected containers: `docker compose restart`
3. If persistent, recreate network: `docker compose down && docker compose up -d`

**Estimated Recovery Time:** Seconds (restart) to minutes (network recreation).

---

### 3.6 Malformed Client Input

**Trigger:** Non-JSON body, missing required fields, invalid field types, SQL injection attempts.

**Detection:**
- Application returns HTTP 400 with `{"error": "Bad request"}` or field-specific error.
- No server-side exceptions; all input is validated at route boundaries.

**Impact:**
- Rejected request only. No side effects on other clients or system state.
- No stack trace exposure. No partial writes.

**Behavior by input type:**

| Input | Endpoint | Response |
|-------|----------|----------|
| Empty body | POST /users | 400 `{"error": "Invalid JSON"}` |
| Non-JSON Content-Type | POST /users | 400 `{"error": "Invalid JSON"}` |
| Missing `username` | POST /users | 400 `{"error": "Invalid or missing username"}` |
| Integer where string expected | POST /users (`username: 123`) | 400 `{"error": "Invalid or missing username"}` |
| Duplicate username | POST /users | 409 `{"error": "Username already exists"}` |
| Non-existent foreign key | POST /urls (`user_id: 99999`) | 404 `{"error": "User not found"}` |
| Non-existent resource | GET /users/99999 | 404 `{"error": "User not found"}` |
| Invalid HTTP method | PATCH /users | 405 `{"error": "Method not allowed"}` |
| SQL injection in field | POST /users (`username: "'; DROP TABLE--"`) | Safely handled by parameterized queries (Peewee ORM) |

**Automated Recovery:** None required. System remains stable.

---

### 3.7 Container Out-of-Memory Kill

**Trigger:** Application memory usage exceeds container or host limits. Possible causes: large CSV bulk import, memory leak in long-running worker.

**Detection:**
- Docker logs: `OOMKilled: true` in container inspect output.
- Container exits with code 137 (SIGKILL).

**Impact:**
- Immediate process termination. In-flight requests are dropped.
- Gunicorn workers do not get graceful shutdown; open database connections are abandoned.
- PostgreSQL detects abandoned connections and cleans up automatically.

**Automated Recovery:**
- `restart: always` restarts the container.
- Gunicorn spawns fresh workers with no residual memory pressure.

**Mitigation:**
- Bulk CSV import processes rows in batches of 100 to limit memory allocation.
- Gunicorn `--timeout 120` kills workers that hang, preventing memory accumulation.
- Per-request database connections prevent connection object accumulation.

**Estimated Recovery Time:** 3-10 seconds.

---

### 3.8 Volume Data Corruption

**Trigger:** Host filesystem failure, power loss during write, or forced container removal during PostgreSQL checkpoint.

**Detection:**
- PostgreSQL fails to start; logs indicate WAL corruption or catalog inconsistency.
- Container enters restart loop (healthcheck never passes).

**Impact:**
- Total data loss if volume is unrecoverable.
- Application starts but auto-seed creates a fresh dataset from CSV files.

**Manual Recovery:**
1. Attempt PostgreSQL recovery: `docker exec hack-db-1 pg_resetwal /var/lib/postgresql/data`
2. If unrecoverable, destroy and rebuild:
   ```bash
   docker compose down -v
   docker compose up -d
   ```
3. Application auto-seeds from `csv/` on first boot when tables are empty.

**Estimated Recovery Time:** Minutes to hours depending on data recovery complexity.

---

### 3.9 Upstream Dependency Timeout

**Trigger:** PostgreSQL query takes longer than Nginx or Gunicorn timeout thresholds.

**Detection:**
- Nginx returns 504 Gateway Timeout (30s `proxy_read_timeout`).
- Gunicorn kills the worker after 120s timeout.

**Impact:**
- Single request fails. Other workers continue serving traffic.
- If caused by lock contention, the blocking transaction may still be running.

**Timeout chain:**

| Component | Timeout | Behavior on Expiry |
|-----------|---------|-------------------|
| Nginx | 30s (`proxy_read_timeout`) | Returns 504 to client |
| Gunicorn | 120s (`--timeout`) | SIGKILL to worker, spawns replacement |
| PostgreSQL | None (default) | Query runs until completion or cancellation |

**Manual Recovery:**
1. Identify long-running queries: `docker exec hack-db-1 psql -U postgres -c "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;"`
2. Cancel problematic query: `SELECT pg_cancel_backend(<pid>);`

---

### 3.10 Concurrent Write Conflicts

**Trigger:** Two requests attempt to create users with the same username, or two redirects update the same click counter simultaneously.

**Detection:**
- `IntegrityError` caught by route handlers.
- Client receives 409 for duplicate username conflicts.
- Click counter uses atomic `UPDATE ... SET click_count = click_count + 1` (no lost updates).

**Impact:**
- No data corruption. Conflicting request receives a descriptive error.
- Short code generation retries up to 10 times on collision before returning 500.

**Automated Recovery:** Built into application logic. No intervention required.

---

## 4. Recovery Procedures

### 4.1 Full Stack Restart

```bash
docker compose down
docker compose up -d --build
```

Services start in dependency order: `db` (waits for healthcheck) then `app` then `nginx`.

### 4.2 Single Service Restart

```bash
docker compose restart <service>
# Example: docker compose restart app
```

### 4.3 Data Reset

```bash
docker compose down -v       # Destroys pgdata volume
docker compose up -d --build # App auto-seeds from csv/ on boot
```

### 4.4 Emergency Read-Only Mode

If the database is under write pressure, disable writes at the Nginx level:

```nginx
# Add to nginx.conf server block temporarily
if ($request_method !~ ^(GET|HEAD)$) {
    return 503 '{"error":"Service unavailable","status":503}';
}
```

Reload without downtime: `docker exec hack-nginx-1 nginx -s reload`

---

## 5. Chaos Testing Runbook

The following tests validate that automated recovery mechanisms function as documented.

### Test 1: Application Process Crash

**Objective:** Verify `restart: always` recovers the application after an internal crash.

**Important:** `docker kill` and `docker stop` are treated as deliberate manual
stops by the Docker daemon. The restart policy is intentionally suppressed for
manually stopped containers. To test automatic restart, the main process must
terminate from within the container.

```bash
# Send SIGTERM to the gunicorn master (PID 1) inside the container.
# Gunicorn handles SIGTERM with a graceful shutdown, then exits.
# Docker sees the process exit and triggers the restart policy.
docker exec hack-app-1 kill -TERM 1

# Poll for recovery (expect < 10 seconds)
for i in $(seq 1 20); do
    sleep 1
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo "Recovered after ${i}s"
        break
    fi
done
```

**Expected:** Service recovers in under 10 seconds. Health endpoint returns 200.

### Test 2: Database Unavailability

**Objective:** Verify graceful degradation when the database is unavailable.

```bash
# Stop DB (manual stop, used intentionally here to keep it down)
docker stop hack-db-1

# Application should return 503, not crash
curl -s http://localhost/users
# Expected: {"error":"Service unavailable","status":503}

# Health endpoint is DB-independent
curl -s http://localhost/health
# Expected: {"status":"ok"}

# Restore the database
docker start hack-db-1
sleep 10

# Full recovery
curl -s http://localhost/users
# Expected: [...] (user list)
```

**Expected:** 503 during outage. Full recovery after database restart.

### Test 3: Nginx Process Crash

**Objective:** Verify proxy recovery.

```bash
# Kill nginx master process from inside the container
docker exec hack-nginx-1 nginx -s quit

# Poll for recovery
for i in $(seq 1 10); do
    sleep 1
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo "Recovered after ${i}s"
        break
    fi
done
```

**Expected:** Recovery in under 5 seconds.

### Test 4: Garbage Data Injection

**Objective:** Verify input validation does not crash the application.

```bash
# Empty body
curl -s -X POST http://localhost/users -H "Content-Type: application/json"
# Expected: 400

# Invalid JSON
curl -s -X POST http://localhost/users -H "Content-Type: application/json" -d "not json"
# Expected: 400

# Wrong types
curl -s -X POST http://localhost/users -H "Content-Type: application/json" \
     -d '{"username": 12345, "email": null}'
# Expected: 400

# Non-existent resource
curl -s http://localhost/users/999999
# Expected: 404

# Wrong HTTP method
curl -s -X PATCH http://localhost/users
# Expected: 405
```

**Expected:** All requests return structured JSON errors. No stack traces. No server crashes.

### Test 5: Rapid Successive Crashes

**Objective:** Verify the system stabilizes after multiple rapid failures.

```bash
for i in $(seq 1 5); do
    docker exec hack-app-1 kill -TERM 1 2>/dev/null
    sleep 5
done

sleep 10
curl -s http://localhost/health
# Expected: {"status":"ok"}
```

**Expected:** System stabilizes. No permanent degradation.

---

## 6. Monitoring and Detection

### Health Endpoints

| Endpoint | Purpose | DB Dependency |
|----------|---------|---------------|
| `GET /health` | Application liveness | No |
| Docker HEALTHCHECK (app) | Container-level liveness | Calls `/health` |
| Docker HEALTHCHECK (db) | Database readiness | `pg_isready` |

### Log Locations

| Service | Log Output | Access |
|---------|-----------|--------|
| app (Gunicorn) | stdout/stderr | `docker logs hack-app-1` |
| db (PostgreSQL) | stdout/stderr | `docker logs hack-db-1` |
| nginx | JSON access log + error log | `docker logs hack-nginx-1` |

### Key Indicators of Failure

| Indicator | Meaning | Action |
|-----------|---------|--------|
| HTTP 502 from Nginx | App container is down | Check `docker ps`; container should auto-restart |
| HTTP 503 from App | Database is unreachable | Check `docker logs hack-db-1` |
| HTTP 500 from App | Unhandled application error | Check `docker logs hack-app-1` for exception |
| Container restart count increasing | Crash loop | Check logs for root cause; fix configuration |
| Healthcheck `unhealthy` | Service degraded | Inspect specific container logs |

---

*End of document.*
