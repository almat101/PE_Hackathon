# Load Test -- Silver Tier (Scale-Out)

**Document ID:** LT-2026-002
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Scope](#1-scope)
2. [Infrastructure Changes from Bronze](#2-infrastructure-changes-from-bronze)
3. [Test Configuration](#3-test-configuration)
4. [Results -- Local Environment](#4-results----local-environment)
5. [Bronze vs. Silver Comparison](#5-bronze-vs-silver-comparison)
6. [Reproduction Steps](#6-reproduction-steps)

---

## 1. Scope

This document records load test results for the URL Shortener service under
200 concurrent virtual users with horizontal scaling enabled (2 application
replicas behind Nginx). The test script is `k6/load-test-200vus.js`. Results
demonstrate the improvement from adding a second application instance.

---

## 2. Infrastructure Changes from Bronze

| Component | Bronze | Silver |
|-----------|--------|--------|
| App replicas | 1 | 2 (`deploy.replicas: 2` in `docker-compose.yml`) |
| Load balancing | None | Nginx round-robin via Docker DNS |
| Gunicorn workers | 2 per replica | 2 per replica (4 total across cluster) |
| Gunicorn threads | 4 per worker | 4 per worker |
| DB connection pool | `PooledPostgresqlDatabase`, max 10 | Same per replica (20 total) |
| Nginx upstream keepalive | 32 | 32 |

Docker DNS resolves the `app` service name to all healthy container IPs. Nginx
round-robins across them without additional configuration.

---

## 3. Test Configuration

| Parameter | Value |
|-----------|-------|
| Tool | k6 |
| Concurrent users (VUs) | 200 |
| Total duration | 180 s |
| p95 threshold | < 3000 ms |
| Error rate threshold | < 10% |

**Stages:**

```
  0s -  30s : Ramp 0 -> 50 VUs
 30s -  60s : Ramp 50 -> 100 VUs
 60s -  90s : Ramp 100 -> 200 VUs
 90s - 150s : Hold at 200 VUs (steady state)
150s - 180s : Ramp 200 -> 0 VUs
```

**Endpoints exercised:** Same as bronze (`/health`, `/shorten`, `/urls`,
`/<short_code>`).

---

## 4. Results -- Local Environment

**Load distribution:** Round-robin across 2 app containers via Nginx.

### Latency

| Metric | Value |
|--------|-------|
| Average | 4.71 ms |
| Median | 4.72 ms |
| p90 | 8.04 ms |
| p95 | 8.94 ms |
| Maximum | 93.00 ms |

### Throughput

| Metric | Value |
|--------|-------|
| Total requests | 14,208 |
| Requests/s | 76.48 |
| Iterations | 3,547 |

### Error Rate

| Failed Checks | Total Checks | Rate |
|---------------|--------------|------|
| 0 | 28,376 | 0.00% |

### Threshold Evaluation

| Threshold | Target | Actual | Result |
|-----------|--------|--------|--------|
| p95 latency | < 3000 ms | 8.94 ms | PASS |
| Error rate | < 10% | 0.00% | PASS |

---

## 5. Bronze vs. Silver Comparison

| Metric | Bronze (50 VUs, 1 replica) | Silver (200 VUs, 2 replicas) |
|--------|----------------------------|------------------------------|
| Concurrent users | 50 | 200 |
| App instances | 1 | 2 |
| p95 latency | 58.16 ms | 8.94 ms |
| Error rate | 0.00% | 0.00% |
| Threshold | < 2000 ms | < 3000 ms |
| Result | PASS | PASS |

With 4x the concurrent users and 2x the app instances, p95 latency dropped
from 58.16 ms to 8.94 ms. The improvement beyond the expected 2x is
attributable to Nginx upstream keepalive connections and the threaded Gunicorn
worker model (`gthread`) distributing I/O-bound database waits across threads.

---

## 6. Reproduction Steps

**Local:**

```bash
docker compose up -d
docker ps   # verify 2 app containers are running
k6 run k6/load-test-200vus.js
```

**Remote:**

```bash
k6 run -e BASE_URL=http://161.35.198.232 k6/load-test-200vus.js
```

---

## Related Documentation

- [load-test-baseline.md](load-test-baseline.md) -- Bronze tier baseline
  (50 VUs, single instance).
