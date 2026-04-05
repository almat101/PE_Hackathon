# 🚀 Scalability Engineering — Bronze Tier: Load Test Baseline

## Test Configuration

| Parameter | Value |
|-----------|-------|
| **Tool** | k6 v0.x (installed at `~/.local/bin/k6`) |
| **Target** | URL Shortener (Flask + Nginx + PostgreSQL) |
| **Concurrent Users (VUs)** | 50 |
| **Test Duration** | 60s (10s ramp-up → 30s hold → 10s ramp-down) |
| **Test Date** | 2026-04-05 |
| **Environment** | Local (Docker Compose) |

## Test Stages

```
0s  → 10s : Ramp 0 → 25 VUs
10s → 20s : Ramp 25 → 50 VUs
20s → 50s : Hold at 50 VUs (steady state)
50s → 60s : Ramp 50 → 0 VUs
```

## Endpoints Tested

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (lightweight) |
| `/shorten` | POST | Create short URL (write + DB insert) |
| `/urls?page=1&per_page=10` | GET | List URLs (read + DB query) |
| `/<short_code>` | GET | Redirect (read + DB update click count) |

---

## 📊 Baseline Results — LOCAL (50 Concurrent Users)

### Overall Latency (Response Time)

| Metric | Value |
|--------|-------|
| **avg** | 25.46 ms |
| **min** | 5.43 ms |
| **median** | 20.65 ms |
| **p90** | 46.66 ms |
| **p95 (BASELINE)** | **58.16 ms** |
| **max** | 137.59 ms |

### Error Rate

| Metric | Value |
|--------|-------|
| **Error Rate** | **0.00%** ✅ |
| **Failed Requests** | 0 / 12,858 |

### Throughput

| Metric | Value |
|--------|-------|
| **Total HTTP Requests** | 12,858 |
| **Requests/sec** | 212.75 |
| **Iterations** | 3,212 |
| **Iterations/sec** | 53.15 |
| **Data Received** | 10 MB (171 kB/s) |

### Per-Endpoint p95 Latency

| Endpoint | p95 Latency |
|----------|-------------|
| Health Check | 54.52 ms |
| Shorten URL | 55.40 ms |
| List URLs | 59.10 ms |
| Redirect | 61.54 ms |

### Check Results

| Check | Result |
|-------|--------|
| health: status 200 | ✓ 100% |
| health: body contains ok | ✓ 100% |
| shorten: status 201 | ✓ 100% |
| shorten: has short_code | ✓ 100% |
| list: status 200 | ✓ 100% |
| list: returns array | ✓ 100% |
| redirect: status 302 | ✓ 100% |
| redirect: has Location header | ✓ 100% |

### Thresholds

| Threshold | Target | Actual | Status |
|-----------|--------|--------|--------|
| p95 < 2000ms | 2000ms | 58.16ms | ✅ PASS |
| Error rate < 10% | 10% | 0.00% | ✅ PASS |

---

## 📊 Baseline Results — DROPLET (50 Concurrent Users)

**Target:** `http://161.35.198.232` (DigitalOcean Droplet)

### Overall Latency (Response Time)

| Metric | Value |
|--------|-------|
| **avg** | 814.81 ms |
| **min** | 49.40 ms |
| **median** | 958.39 ms |
| **p90** | 1,116.33 ms |
| **p95 (BASELINE)** | **1,157.92 ms** |
| **max** | 1,319.87 ms |

### Error Rate

| Metric | Value |
|--------|-------|
| **Error Rate** | **0.00%** ✅ |
| **Failed Requests** | 0 / 2,402 |

### Throughput

| Metric | Value |
|--------|-------|
| **Total HTTP Requests** | 2,402 |
| **Requests/sec** | 39.24 |
| **Iterations** | 598 |
| **Iterations/sec** | 9.77 |
| **Data Received** | 1.9 MB (31 kB/s) |

### Per-Endpoint p95 Latency

| Endpoint | p95 Latency |
|----------|-------------|
| Health Check | 1,129.40 ms |
| Shorten URL | 1,145.46 ms |
| List URLs | 1,146.23 ms |
| Redirect | 1,188.04 ms |

### Check Results

All checks passed ✓ 100% (4,784 / 4,784)

### Thresholds

| Threshold | Target | Actual | Status |
|-----------|--------|--------|--------|
| p95 < 2000ms | 2000ms | 1,157.92ms | ✅ PASS |
| Error rate < 10% | 10% | 0.00% | ✅ PASS |

---

## 📈 Comparison: Local vs Droplet

| Metric | Local | Droplet | Δ Factor |
|--------|-------|---------|----------|
| **p95 Latency** | 58.16 ms | 1,157.92 ms | ~20x slower |
| **Throughput** | 212.75 req/s | 39.24 req/s | ~5.4x lower |
| **Error Rate** | 0.00% | 0.00% | Same ✅ |
| **Iterations** | 3,212 | 598 | ~5.3x fewer |

---

## How to Run

### Locally (against Docker Compose stack)

```bash
# 1. Start the stack
docker compose up -d

# 2. Run the load test
k6 run k6/load-test-50vus.js

# 3. Results are saved to k6/results/load-test-results.json
```

### Against Droplet (remote)

```bash
# Run from your local machine, pointing to the droplet IP
k6 run -e BASE_URL=http://161.35.198.232 k6/load-test-50vus.js
```

---

## Key Takeaways

1. **The app handles 50 concurrent users with 0% error rate** in both environments — no crashes, no timeouts
2. **Droplet is ~22x slower on p95** — mostly due to network latency + limited droplet CPU (single Flask worker)
3. **Redirect endpoint is the slowest** in both tests — it does a DB read + click count update + event insert
4. **Throughput bottleneck is the single Flask worker** — scaling with `gunicorn` workers or Docker replicas would dramatically improve performance
5. **Even on the droplet, p95 stays under the 2s threshold** — the app is usable but could benefit from optimization
