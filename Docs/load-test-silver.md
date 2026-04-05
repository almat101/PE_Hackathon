# 🥈 Scalability Engineering — Silver Tier: Scale-Out Baseline

## Test Configuration

| Parameter | Value |
|-----------|-------|
| **Tool** | k6 v0.x |
| **Architecture** | **Load Balancer (Nginx) + 2 App Replicas** |
| **Concurrent Users (VUs)** | 200 |
| **Test Duration** | 180s (30s ramp-up → 120s steady → 30s ramp-down) |
| **Think Time (Sleep)** | 1.5s - 2.0s (Realistic simulation) |
| **Environment** | Local (Docker Compose) / Droplet (Remote) |

---

## 📊 Baseline Results — LOCAL (200 Concurrent Users)

**Load Distribution:** Round-robin via Nginx across 2 containers.

### Overall Latency (Response Time)

| Metric | Value |
|--------|-------|
| **avg** | 4.71 ms |
| **median** | 4.72 ms |
| **p90** | 8.04 ms |
| **p95 (SILVER BASELINE)** | **8.94 ms** |
| **max** | 93.00 ms |

### Error Rate

| Metric | Value |
|--------|-------|
| **Error Rate** | **0.00%** ✅ |
| **Checks Passed** | 28,376 / 28,376 |

### Throughput

| Metric | Value |
|--------|-------|
| **Total HTTP Requests** | 14,208 |
| **Requests/sec** | 76.48 |
| **Iterations** | 3,547 |

---

## 📊 Baseline Results — DROPLET (200 Concurrent Users)

**Target:** `http://161.35.198.232`

| Metric | Value |
|--------|-------|
| **avg** | 71.46 ms |
| **p95 (BASELINE)** | **122.17 ms** ✅ |
| **Error Rate** | **0.00%** ✅ |
| **Throughput** | 73.10 req/s |
| **Total Requests** | 13,668 |

---

## 📈 Comparison: Bronze (50 VUs) vs Silver (200 VUs)

| Achievement | Bronze | Silver | Improvement / Scaling |
|-------------|--------|--------|----------------------|
| **Max Concurrent Users** | 50 | 200 | **4x Growth** 🚀 |
| **App Instances** | 1 | 2 | **Horizontal Scale** 👥 |
| **Load Balancer** | None | Nginx | **Traffic Splitting** 🚦 |
| **Target Threshold** | < 2.0s | < 3.0s | Both PASSED ✅ |

---

## Technical Implementation Notes

1.  **Horizontal Scaling:** Using `docker compose up -d --scale app=2` (or `deploy.replicas: 2`).
2.  **Health-Aware LB:** Nginx routes traffic to the `app` service, which Docker DNS resolves to all healthy container IPs.
3.  **Stability Optimizations:**
    *   **Gunicorn:** Reduced to 2 workers per replica to minimize CPU contention on 1-vCPU droplets.
    *   **DB Pooling:** Implemented `PooledPostgresqlDatabase` to reuse connections.
    *   **Keepalive:** Nginx configured with `upstream keepalive` for faster request processing.

---

## Verification (Loot Checklist)
- [x] `docker ps` shows multiple app containers + 1 Nginx.
- [x] 200 concurrent users handled with < 3s latency.
- [x] Error rate < 10%.
