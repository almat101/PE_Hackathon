# Capacity Plan

**Document ID:** CP-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Current Infrastructure](#1-current-infrastructure)
2. [Measured Performance](#2-measured-performance)
3. [Capacity Limits](#3-capacity-limits)
4. [Bottleneck Analysis](#4-bottleneck-analysis)
5. [Scaling Thresholds](#5-scaling-thresholds)
6. [Storage Growth Projections](#6-storage-growth-projections)
7. [Scaling Playbook](#7-scaling-playbook)
8. [Cost Projections](#8-cost-projections)

---

## 1. Current Infrastructure

| Resource | Specification |
|----------|--------------|
| Droplet | DigitalOcean, 1 vCPU, 1 GB RAM, 25 GB SSD |
| App replicas | 1 (2 available via `deploy.replicas: 2`) |
| Workers per replica | 2 (Gunicorn `gthread`) |
| Threads per worker | 4 |
| Max concurrent requests | 8 per replica (16 with 2 replicas) |
| DB connection pool | 10 per replica (`PooledPostgresqlDatabase`) |
| Nginx keepalive | 32 upstream connections |
| Gunicorn backlog | 2048 queued connections |

---

## 2. Measured Performance

Data from load tests: [load-test-baseline.md](load-test-baseline.md) and
[load-test-silver.md](load-test-silver.md).

### 2.1 Single Replica (1 instance)

| Environment | VUs | Req/s | p95 Latency | Error Rate |
|-------------|-----|-------|-------------|------------|
| Local | 50 | 212.75 | 58.16 ms | 0.00% |
| Droplet | 50 | 39.24 | 1,157.92 ms | 0.00% |

### 2.2 Two Replicas (2 instances)

| Environment | VUs | Req/s | p95 Latency | Error Rate |
|-------------|-----|-------|-------------|------------|
| Local | 200 | 76.48 | 8.94 ms | 0.00% |

### 2.3 Key Observations

- **Local vs. droplet gap:** The droplet (1 vCPU) delivers ~5.4x lower
  throughput than the local dev machine. CPU is the primary constraint.
- **Scaling efficiency:** 2 replicas with 4x the load (200 VUs) achieved
  6.5x lower p95 latency than 1 replica at 50 VUs (local). Nginx keepalive
  and connection reuse contribute to better-than-linear scaling.
- **Zero errors:** No HTTP errors under any tested load level. The system
  degrades gracefully (higher latency) rather than failing.

---

## 3. Capacity Limits

### 3.1 Per-Replica Limits

| Resource | Limit | Implication |
|----------|-------|-------------|
| Gunicorn concurrent slots | 8 (2w × 4t) | Request 9+ queues in backlog |
| DB connection pool | 10 connections | Query 11+ blocks until a connection is returned |
| Gunicorn backlog | 2048 slots | Connection 2049+ receives `ECONNREFUSED` |

### 3.2 System-Wide Limits (1 vCPU droplet)

| Metric | 1 Replica | 2 Replicas |
|--------|-----------|------------|
| Max sustainable req/s | ~39 | ~70 (estimated) |
| Max concurrent users (p95 < 1s) | ~40 | ~80 |
| Max concurrent users (p95 < 2s) | ~50 | ~100 |
| Max concurrent users (0% errors) | ~50+ | ~200+ |

**Method:** Values extrapolated from measured load test data. The 1-replica
droplet figure (39 req/s) is directly measured. The 2-replica droplet figure
is estimated at ~1.8x (accounting for shared CPU, not linear scaling on
single vCPU).

### 3.3 Absolute Capacity Ceiling

On the current 1-vCPU droplet with 2 replicas, the system will begin
degrading (p95 > 2 seconds) at approximately **100 concurrent users**. Errors
(connection refused) are not expected until the backlog is exhausted, which
requires sustained load above ~500 concurrent connections.

---

## 4. Bottleneck Analysis

### 4.1 Bottleneck Ranking

| # | Bottleneck | Limit | Impact |
|---|-----------|-------|--------|
| 1 | **CPU (1 vCPU)** | 100% utilization | All processes (app, DB, Nginx, Prometheus) share a single core. Gunicorn workers context-switch under load. |
| 2 | **RAM (1 GB)** | ~900 MB usable | Each Gunicorn worker uses ~50 MB. 2 replicas × 2 workers = ~200 MB for app alone. PostgreSQL shared_buffers default ~128 MB. Prometheus ~100 MB. |
| 3 | **DB connection pool (10/replica)** | 10-20 total | At high concurrency, all pool slots are occupied. Additional requests wait for a connection. |
| 4 | **Gunicorn concurrent slots (8/replica)** | 8-16 total | Beyond this, requests queue in the kernel backlog. Latency increases. |
| 5 | **Disk I/O (SSD)** | 25 GB capacity | Not a throughput bottleneck currently. Becomes relevant for DB growth over months. |

### 4.2 Bottleneck Evidence

- **CPU is bottleneck #1:** Droplet throughput (39 req/s) is 5.4x lower than
  local (212 req/s). The local machine has multiple cores; the droplet has 1.
  Latency on the droplet (p95 = 1158 ms) is 20x higher than local (58 ms).
  Network latency contributes only ~40-50 ms (RTT to DigitalOcean), so the
  remaining ~1100 ms is CPU/scheduling overhead.
- **RAM is not yet a bottleneck:** `docker stats` shows total memory usage
  under 600 MB with all 7 services running.
- **DB pool not yet saturated:** Zero connection errors in all load tests.
  Pool utilization peaks below 10 at 50 VUs.

---

## 5. Scaling Thresholds

### 5.1 When to Scale

| Metric | Threshold | Action |
|--------|-----------|--------|
| p95 latency | > 500 ms sustained | Enable 2nd replica |
| p95 latency (2 replicas) | > 1 s sustained | Upgrade droplet CPU |
| CPU usage | > 80% for 5 minutes | Enable 2nd replica or upgrade |
| DB pool active connections | > 8 per replica | Increase `max_connections` to 20 |
| Error rate | > 1% | Immediate investigation (see Runbook) |
| Disk usage | > 80% | Expand volume or prune old data |

### 5.2 Scaling Actions (in order)

1. **Enable 2nd replica** (free, ~2x capacity): Uncomment
   `deploy.replicas: 2` in `docker-compose.yml`, run
   `docker compose up -d`.
2. **Increase DB pool size** (free, reduces wait time): Change
   `max_connections=20` in `app/database.py`.
3. **Upgrade droplet** ($): Move from 1-vCPU/1GB to 2-vCPU/2GB. Expected
   ~2x throughput improvement.
4. **Add Gunicorn workers** (free with more CPU): Increase to 4 workers on
   2-vCPU machine (follows `2 × CPU` rule).
5. **External connection pooler** (when pool > 50): Deploy PgBouncer between
   app and database.

---

## 6. Storage Growth Projections

### 6.1 Per-Record Sizes (estimated)

| Table | Avg Row Size | Growth Driver |
|-------|-------------|---------------|
| `users` | ~100 bytes | User registration |
| `short_urls` | ~200 bytes | URL shortening |
| `events` | ~150 bytes | Every redirect click |

### 6.2 Growth Scenarios

Assuming 100 new URLs/day, 1000 redirects/day, 10 new users/day:

| Timeframe | URLs | Events | Users | Total DB Size |
|-----------|------|--------|-------|---------------|
| 1 month | 3,000 | 30,000 | 300 | ~6 MB |
| 6 months | 18,000 | 180,000 | 1,800 | ~35 MB |
| 1 year | 36,000 | 360,000 | 3,600 | ~70 MB |
| 5 years | 180,000 | 1,800,000 | 18,000 | ~350 MB |

**Conclusion:** At projected usage, the 25 GB SSD will not be a constraint
for years. The `events` table is the fastest-growing table. Implementing
event retention (e.g., delete events older than 90 days) would keep the
table under 30,000 rows permanently.

### 6.3 Prometheus Data

Prometheus stores timeseries data on the `prometheus_data` volume. At the
default 15-day retention and 5-second scrape interval:
- ~200 timeseries × 86,400 samples/day × 15 days × ~2 bytes/sample ≈ **50 MB**.
- Not a storage concern.

---

## 7. Scaling Playbook

### 7.1 Enable Second Replica

```bash
ssh root@<DROPLET_IP>
cd PE_Hackathon

# Uncomment replicas in docker-compose.yml
sed -i 's/#   replicas: 2/  replicas: 2/' docker-compose.yml
# Also remove the container_name for app (required for replicas)
sed -i '/container_name: app/d' docker-compose.yml

docker compose up -d
docker ps --filter name=app
# Should show 2 running app containers
```

### 7.2 Increase DB Pool Size

Edit `app/database.py`:

```python
# Change max_connections from 10 to 20
database = PooledPostgresqlDatabase(None, max_connections=20, stale_timeout=300)
```

Rebuild:

```bash
docker compose up -d --build
```

### 7.3 Upgrade Droplet

1. Create a snapshot of the current droplet (DigitalOcean dashboard).
2. Resize to 2-vCPU/2GB ($18/month → $24/month).
3. Update Gunicorn CMD to 4 workers:
   `CMD gunicorn -w 4 -k gthread --threads 4 ...`
4. Redeploy.

---

## 8. Cost Projections

| Configuration | Monthly Cost | Max Concurrent Users (p95 < 1s) |
|---------------|-------------|--------------------------------|
| 1 vCPU / 1 GB, 1 replica | $6 | ~40 |
| 1 vCPU / 1 GB, 2 replicas | $6 | ~80 |
| 2 vCPU / 2 GB, 2 replicas | $18 | ~200 |
| 4 vCPU / 8 GB, 4 replicas | $48 | ~600 |

**Cost efficiency:** At $6/month with 2 replicas, the system supports ~80
concurrent users with sub-second p95 latency. This is sufficient for a
hackathon project and small production workloads.

---

## Related Documentation

- [load-test-baseline.md](load-test-baseline.md) -- Raw data: 50 VUs, single
  instance.
- [load-test-silver.md](load-test-silver.md) -- Raw data: 200 VUs, 2
  replicas.
- [DECISION_LOG.md](DECISION_LOG.md) -- ADR-011 (worker/thread sizing
  rationale).
- [ARCHITECTURE.md](ARCHITECTURE.md) -- System topology and connection
  management.
