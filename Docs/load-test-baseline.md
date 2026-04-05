# Load Test Baseline -- Bronze Tier

**Document ID:** LT-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Scope](#1-scope)
2. [Test Configuration](#2-test-configuration)
3. [Results -- Local Environment](#3-results----local-environment)
4. [Results -- Droplet Environment](#4-results----droplet-environment)
5. [Local vs. Droplet Comparison](#5-local-vs-droplet-comparison)
6. [Reproduction Steps](#6-reproduction-steps)

---

## 1. Scope

This document records the baseline load test results for the URL Shortener
service under 50 concurrent virtual users. The test script is
`k6/load-test-50vus.js`. Results establish the performance floor against which
future optimizations are measured.

**Infrastructure under test:**

| Component | Configuration |
|-----------|---------------|
| Application | Flask 3.1, Gunicorn (2 workers, 4 threads each, `gthread`) |
| Database | PostgreSQL 17, `PooledPostgresqlDatabase` (max 10 connections) |
| Proxy | Nginx 1.28, upstream keepalive 32 |
| Replicas | 1 (single app instance for bronze baseline) |

---

## 2. Test Configuration

| Parameter | Value |
|-----------|-------|
| Tool | k6 |
| Concurrent users (VUs) | 50 |
| Total duration | 60 s |
| p95 threshold | < 2000 ms |
| Error rate threshold | < 10% |

**Stages:**

```
 0s - 10s : Ramp 0 -> 25 VUs
10s - 20s : Ramp 25 -> 50 VUs
20s - 50s : Hold at 50 VUs (steady state)
50s - 60s : Ramp 50 -> 0 VUs
```

**Endpoints exercised:**

| Endpoint | Method | Operation |
|----------|--------|-----------|
| `/health` | GET | Health check (no database) |
| `/shorten` | POST | Create short URL (write) |
| `/urls?page=1&per_page=10` | GET | List URLs (read) |
| `/<short_code>` | GET | Redirect lookup (read + event insert) |

---

## 3. Results -- Local Environment

### Latency

| Metric | Value |
|--------|-------|
| Average | 25.46 ms |
| Minimum | 5.43 ms |
| Median | 20.65 ms |
| p90 | 46.66 ms |
| p95 | 58.16 ms |
| Maximum | 137.59 ms |

### Throughput

| Metric | Value |
|--------|-------|
| Total requests | 12,858 |
| Requests/s | 212.75 |
| Iterations | 3,212 |
| Data received | 10 MB (171 kB/s) |

### Per-Endpoint p95 Latency

| Endpoint | p95 |
|----------|-----|
| `/health` | 54.52 ms |
| `/shorten` | 55.40 ms |
| `/urls` | 59.10 ms |
| `/<short_code>` | 61.54 ms |

### Error Rate

| Failed Requests | Total Requests | Rate |
|-----------------|----------------|------|
| 0 | 12,858 | 0.00% |

### Threshold Evaluation

| Threshold | Target | Actual | Result |
|-----------|--------|--------|--------|
| p95 latency | < 2000 ms | 58.16 ms | PASS |
| Error rate | < 10% | 0.00% | PASS |

---

## 4. Results -- Droplet Environment

**Target:** `http://161.35.198.232` (DigitalOcean, 1 vCPU, 1 GB RAM)

### Latency

| Metric | Value |
|--------|-------|
| Average | 814.81 ms |
| Minimum | 49.40 ms |
| Median | 958.39 ms |
| p90 | 1,116.33 ms |
| p95 | 1,157.92 ms |
| Maximum | 1,319.87 ms |

### Throughput

| Metric | Value |
|--------|-------|
| Total requests | 2,402 |
| Requests/s | 39.24 |
| Iterations | 598 |
| Data received | 1.9 MB (31 kB/s) |

### Per-Endpoint p95 Latency

| Endpoint | p95 |
|----------|-----|
| `/health` | 1,129.40 ms |
| `/shorten` | 1,145.46 ms |
| `/urls` | 1,146.23 ms |
| `/<short_code>` | 1,188.04 ms |

### Error Rate

| Failed Requests | Total Requests | Rate |
|-----------------|----------------|------|
| 0 | 2,402 | 0.00% |

### Threshold Evaluation

| Threshold | Target | Actual | Result |
|-----------|--------|--------|--------|
| p95 latency | < 2000 ms | 1,157.92 ms | PASS |
| Error rate | < 10% | 0.00% | PASS |

---

## 5. Local vs. Droplet Comparison

| Metric | Local | Droplet | Factor |
|--------|-------|---------|--------|
| p95 latency | 58.16 ms | 1,157.92 ms | 19.9x |
| Throughput | 212.75 req/s | 39.24 req/s | 5.4x |
| Iterations | 3,212 | 598 | 5.4x |
| Error rate | 0.00% | 0.00% | -- |

The latency difference is attributable to network round-trip time between the
local k6 client and the remote droplet, combined with the single-vCPU
constraint on the droplet host. The redirect endpoint (`/<short_code>`) is
consistently the slowest across both environments because it performs a database
read, a click-count update, and an event insert per request.

---

## 6. Reproduction Steps

**Local:**

```bash
docker compose up -d
k6 run k6/load-test-50vus.js
```

**Remote:**

```bash
k6 run -e BASE_URL=http://161.35.198.232 k6/load-test-50vus.js
```

---

## Related Documentation

- [load-test-silver.md](load-test-silver.md) -- Silver tier results (200 VUs,
  horizontal scaling).
