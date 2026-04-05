# Root-Cause Analysis Drill

**Document ID:** RCA-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Drill Overview](#1-drill-overview)
2. [Scenario: Service Down](#2-scenario-service-down)
3. [Scenario: High Error Rate (503s)](#3-scenario-high-error-rate-503s)
4. [Scenario: Latency Spike](#4-scenario-latency-spike)
5. [Findings and Lessons](#5-findings-and-lessons)

---

## 1. Drill Overview

This document records three simulated incident drills performed using the
application's `/chaos` endpoint and the Grafana dashboard to diagnose root
causes. Each drill follows the same structure:

1. **Inject failure** (via `/chaos` or infrastructure action)
2. **Observe dashboard** (Grafana "URL Shortener -- Golden Signals")
3. **Diagnose** (identify which signal changed and why)
4. **Confirm resolution** (verify signals return to normal)

**Tools used:**
- Grafana dashboard at `http://<DROPLET_IP>:3000` (login required)
- `/chaos` endpoint with `X-Chaos-Token` header
- `curl` for triggering failures and verifying recovery
- Discord channel for alert notification verification

---

## 2. Scenario: Service Down

### 2.1 Inject Failure

```bash
curl -X GET http://<DROPLET_IP>/chaos -H "X-Chaos-Token: <token>"
```

Wait -- this request went through Nginx. With the new security hardening,
`/chaos` is blocked at Nginx (returns 403). The correct approach is to
exec into the Docker network:

```bash
ssh root@<DROPLET_IP>
docker exec -it app curl -X GET http://localhost:5000/chaos \
  -H "X-Chaos-Token: $CHAOS_TOKEN"
```

This sends SIGTERM to the Gunicorn master (PID 1), crashing the container.

### 2.2 Dashboard Observations

| Signal | Before | During | After |
|--------|--------|--------|-------|
| **Traffic** | ~5 req/s (baseline) | 0 req/s | ~5 req/s (recovered) |
| **Errors** | 0% | N/A (no requests processed) | 0% |
| **Latency** | ~10 ms avg | N/A | ~10 ms avg |
| **Saturation (CPU)** | ~2% | 0% (process dead) | ~2% |

**Key dashboard indicator:** The **App Status** stat panel changes from
green "UP" to red "DOWN". The `up{job="flask_app"}` metric drops to 0.

### 2.3 Alert Timeline

| Time | Event |
|------|-------|
| T+0s | `/chaos` kills PID 1, container exits |
| T+5s | Prometheus scrape fails (`up` → 0) |
| T+10s | **ServiceDown** alert fires (10s threshold) |
| T+15s | Alertmanager sends notification to Discord |
| T+20s | Docker `restart: always` restarts the container |
| T+30s | App passes healthcheck, `up` → 1 |
| T+35s | ServiceDown alert resolves |

### 2.4 Root-Cause Diagnosis

**How identified on the dashboard:**
1. **App Status** panel turned red/DOWN
2. **Traffic** panel dropped to zero (no requests served)
3. **CPU** panel dropped to zero (process not running)

**Root cause:** Application process terminated (SIGTERM to PID 1).
In a real incident this could be caused by: OOM kill, unhandled exception
in worker initialization, or a bad deployment.

**Resolution:** Automatic -- Docker `restart: always` policy restarted the
container within ~20 seconds. No manual intervention required.

---

## 3. Scenario: High Error Rate (503s)

### 3.1 Inject Failure

Simulate database unavailability by pausing the database container:

```bash
ssh root@<DROPLET_IP>
docker pause db
```

The app container stays running, but all database operations fail. The
`before_request` hook catches the connection error and returns HTTP 503.

### 3.2 Dashboard Observations

| Signal | Before | During | After |
|--------|--------|--------|-------|
| **Traffic** | ~5 req/s | ~5 req/s (requests still arrive) | ~5 req/s |
| **Errors** | 0% | **~100%** (all requests return 503) | 0% |
| **Latency** | ~10 ms | **~2 ms** (fast-fail, no DB query) | ~10 ms |
| **Saturation** | ~2% CPU | ~1% CPU (less work per request) | ~2% |

### 3.3 Root-Cause Diagnosis

**How identified on the dashboard:**
1. **Error Rate** panel spiked to ~100% (red zone, threshold > 10%)
2. **Responses by Status Code** panel showed all responses as `503`
3. **Latency** paradoxically *decreased* — the app fails fast without
   waiting for database queries
4. **Traffic** remained constant — requests were arriving but failing

**Diagnosis logic:**
- High error rate + low latency = fast-fail pattern → database is down
- If latency were *high* alongside high errors, the cause would more likely
  be timeouts (network issue, slow queries)

**Resolution:**
```bash
docker unpause db
# Wait for app to reconnect (next request triggers pool reconnect)
curl -s http://<DROPLET_IP>/health
# Expected: {"status":"ok"}
```

### 3.4 Alert Timeline

| Time | Event |
|------|-------|
| T+0s | `docker pause db` — database stops responding |
| T+1s | Application returns 503 for all DB-dependent requests |
| T+30s | **HighErrorRate** alert fires (>10% for 30s threshold) |
| T+35s | Discord notification received |
| T+2m | Operator runs `docker unpause db` |
| T+2m5s | Next request succeeds, error rate drops to 0% |
| T+3m | HighErrorRate alert resolves |

---

## 4. Scenario: Latency Spike

### 4.1 Inject Failure

Simulate CPU saturation with a stress tool:

```bash
ssh root@<DROPLET_IP>
# Install stress in the app container
docker exec app apt-get update -qq && docker exec app apt-get install -y -qq stress
# Burn CPU for 60 seconds
docker exec -d app stress --cpu 2 --timeout 60
```

### 4.2 Dashboard Observations

| Signal | Before | During | After |
|--------|--------|--------|-------|
| **Traffic** | ~5 req/s | ~3 req/s (reduced throughput) | ~5 req/s |
| **Errors** | 0% | 0% (no errors, just slow) | 0% |
| **Latency** | ~10 ms | **~500+ ms** (CPU contention) | ~10 ms |
| **Saturation** | ~2% CPU | **~95%+ CPU** (red zone) | ~2% |

### 4.3 Root-Cause Diagnosis

**How identified on the dashboard:**
1. **CPU Usage** panel spiked to >90% (red threshold breached)
2. **Avg Latency** panel showed significant increase
3. **Traffic** panel showed slight decrease (fewer requests completed/sec)
4. **Error Rate** stayed at 0% — requests succeeded, just slowly

**Diagnosis logic:**
- High latency + high CPU + zero errors = CPU saturation
- If errors were also elevated, the cause would be resource exhaustion
  (OOM, connection limits)
- The correlation between CPU spike and latency spike confirms causation

**Resolution:** The stress process exits after 60 seconds (timeout). In a
real incident:
- Identify the CPU-consuming process: `docker exec app top -bn1`
- If traffic-driven: enable 2nd replica (`deploy.replicas: 2`)
- If process-driven: kill the runaway process

### 4.4 Alert Timeline

| Time | Event |
|------|-------|
| T+0s | Stress process starts consuming CPU |
| T+5s | CPU metrics rise above 90% |
| T+1m | **HighLatency** alert fires (avg > 1s for 1m) |
| T+2m | **HighCPU** alert fires (>90% for 2m) |
| T+2m5s | Two Discord notifications received |
| T+60s | Stress process exits (timeout) |
| T+65s | CPU drops below 90%, latency normalizes |
| T+3m | Both alerts resolve |

---

## 5. Findings and Lessons

### 5.1 Dashboard Effectiveness

| Golden Signal | Correctly identified incident? | Panel used |
|---------------|-------------------------------|------------|
| **Latency** | Yes — distinguished fast-fail (DB down) from CPU contention | Request Latency, Percentiles |
| **Traffic** | Yes — confirmed requests still arriving during errors | Request Rate by Endpoint |
| **Errors** | Yes — error rate panel immediately showed 503 spike | Error Rate, Responses by Status |
| **Saturation** | Yes — CPU panel correlated directly with latency spike | CPU Usage, Memory Usage |

### 5.2 Key Diagnostic Patterns

| Pattern | Likely Cause |
|---------|-------------|
| High errors + **low** latency | Database down (fast-fail) |
| High errors + **high** latency | Upstream timeout, network issue |
| High latency + high CPU + no errors | CPU saturation |
| Zero traffic + app DOWN | Container crash (check App Status) |
| High latency + normal CPU | Database slow queries, pool exhaustion |

### 5.3 Lessons Learned

1. **Fast-fail is a feature.** When the database is down, the app returns
   503 in ~2 ms instead of hanging for 30 seconds. This is a direct result
   of the `before_request` connection hook catching failures early.

2. **Latency direction matters.** Latency going *down* during an incident
   is counterintuitive but diagnostic: it means the application is
   short-circuiting before the slow path (database query).

3. **Correlation across signals is key.** No single panel diagnoses the
   issue. The combination of signals narrows the root cause:
   - CPU + Latency together → CPU-bound problem
   - Errors + Latency apart → data-layer problem

4. **Alert timing is appropriate.** ServiceDown fires in 10s (critical),
   HighErrorRate in 30s (allows transient spikes), HighCPU in 2m (avoids
   false positives from brief bursts).

---

## Related Documentation

- [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) -- Step-by-step alert
  response procedures.
- [FAILURE_MODES.md](FAILURE_MODES.md) -- Comprehensive failure scenario
  catalog.
- [OBSERVABILITY.md](OBSERVABILITY.md) -- Alert rule definitions and
  Prometheus configuration.
