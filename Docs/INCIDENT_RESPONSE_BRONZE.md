# Incident Response - Bronze Tier Evidence

## Overview

This document provides evidence for the **Bronze Tier (The Watchtower)** of the Incident Response quest in the MLH PE Hackathon 2026. The application implements:

- ✅ **Structured Logging**: All application logs emit as JSON with machine-readable fields
- ✅ **Metrics Exposure**: `/metrics` endpoint exposes Prometheus-compatible metrics
- ✅ **Manual Inspection Tools**: Logs accessible via Docker and HTTP endpoints

---

## Evidence 1: Monitoring Data Exposure - `/metrics` Endpoint

**What**: The application exposes a `/metrics` endpoint that emits metrics in Prometheus text format.

**How to access**:
```bash
curl http://localhost/metrics
```

**Example output**:
```
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 652.0
python_gc_objects_collected_total{generation="1"} 226.0
python_gc_objects_collected_total{generation="2"} 0.0

# HELP python_gc_objects_uncollectable_total Uncollectable objects found during GC
# TYPE python_gc_objects_uncollectable_total counter
python_gc_objects_uncollectable_total{generation="0"} 0.0
python_gc_objects_uncollectable_total{generation="1"} 0.0
python_gc_objects_uncollectable_total{generation="2"} 0.0

# HELP python_gc_collections_total Number of times this generation was collected
# TYPE python_gc_collections_total counter
python_gc_collections_total{generation="0"} 31.0
python_gc_collections_total{generation="1"} 2.0
python_gc_collections_total{generation="2"} 0.0

# HELP process_virtual_memory_bytes Virtual memory size in bytes.
# TYPE process_virtual_memory_bytes gauge
process_virtual_memory_bytes 9.0136576e+07

# HELP process_resident_memory_bytes Resident memory size in bytes.
# TYPE process_resident_memory_bytes gauge
process_resident_memory_bytes 5.7954304e+07

# HELP process_start_time_seconds Start time of the process since unix epoch in seconds.
# TYPE process_start_time_seconds gauge
process_start_time_seconds 1.77533238199e+09

# HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 0.74
```

**Key metrics exposed**:
- `python_gc_*` - Python garbage collection statistics
- `process_virtual_memory_bytes` - Memory usage
- `process_resident_memory_bytes` - Resident memory
- `process_start_time_seconds` - Process uptime origin
- `process_cpu_seconds_total` - CPU usage tracking

**What this shows**: The `/metrics` endpoint is actively collecting and exposing operational metrics in a standardized format that can be scraped by monitoring systems like Prometheus.

---

## Evidence 2: Machine-Readable Logs - JSON Structured Logging

**What**: Application logs are emitted in JSON format with machine-readable fields for parsing and aggregation.

**How to access**:
```bash
docker compose logs app
```

**Example structured log output**:
```json
{
  "asctime": "2026-04-04 19:53:04,066",
  "name": "app",
  "levelname": "INFO",
  "message": "Monitoring setup complete: JSON logging and /metrics enabled.",
  "pathname": "/app/app/monitoring.py",
  "lineno": 35
}
```

**JSON field breakdown**:
- `asctime` - **Timestamp** in ISO format for time-series correlation
- `name` - **Logger name** for filtering by component
- `levelname` - **Log level** (INFO, WARN, ERROR) for severity filtering
- `message` - **Log message** describing the event
- `pathname` - **Source file** for identifying where the log originated
- `lineno` - **Line number** for precise debugging

**What this shows**: Each log entry is a machine-readable JSON object with structured fields. An operator can:
- Filter logs by severity: `levelname == "ERROR"`
- Correlate events by timestamp
- Identify source components
- Parse and aggregate logs programmatically

**Implementation**: Uses `python-json-logger` (v4.1.0) to automatically convert all Flask/application logs to JSON format.

---

## Evidence 3: Remote Log Inspection - Operator Tooling Path

**What**: Step-by-step tooling path that an operator would follow to remotely inspect and diagnose issues without direct SSH access.

### Incident Response Workflow

**Scenario**: Alert triggered - "Service error rate elevated"

---

#### **Step 1: Verify Service Status (No SSH Required)**

**Command**:
```bash
docker compose ps app
```

**Output**:
```
NAME                  STATUS
pe_hackathon-app-1    Up 2 hours (healthy)
```

**What operator learns**: Service is running and container is healthy. Proceeds to check logs.

---

#### **Step 2: Fetch Recent Error Logs**

**Command**:
```bash
docker compose logs app --tail=50 | grep -i error
```

**Output**: Reports matching the search pattern to identify errors

**What operator learns**: Sees which errors occurred and approximately when

---

#### **Step 3: Get Full Context Around the Error**

**Command**:
```bash
docker compose logs app --tail=100 | grep -B3 -A3 "error pattern"
```

**Output**: Shows 3 lines before and after the error for context

**What operator learns**: Understands what led to the error and what happened after

---

#### **Step 4: Follow Logs in Real-Time (Live Monitoring)**

**Command**:
```bash
docker compose logs -f app
```

**Output**: Streams new log lines as they're generated

**What operator learns**: Watches live as service processes requests, can see if error repeats

---

#### **Step 5: Validate Health Check (Quick Verification)**

**Command**:
```bash
curl http://localhost/health
# Expected: {"status":"ok"}
```

**What operator learns**: Confirms service is responding to HTTP requests and is considered healthy

---

### Tooling Path Benefits

| Requirement | How Satisfied |
|---|---|
| **No SSH needed** | ✅ All commands use `docker compose` or `curl` |
| **Remote access** | ✅ Works from any machine with Docker/network access |
| **Structured diagnosis** | ✅ Step-by-step path to root cause |
| **Real-time monitoring** | ✅ `docker compose logs -f` provides live stream |
| **Historical analysis** | ✅ `--tail` and `grep` enable past log inspection |
| **Health validation** | ✅ HTTP endpoint confirms service state |

---



---

## Architecture Summary

```
┌─────────────────────┐
│   Flask Application │
│  (5000/tcp)         │
├─────────────────────┤
│ JSON Structured     │
│ Logging             │
│ ├─ pythonjsonlogger │
│ └─ INFO/ERROR/WARN  │
├─────────────────────┤
│ Prometheus Metrics  │
│ ├─ /metrics (HTTP)  │
│ ├─ Process stats    │
│ ├─ Python GC        │
│ └─ Custom metrics   │
├─────────────────────┤
│ Docker Logging      │
│ ├─ docker logs      │
│ ├─ compose logs     │
│ └─ streaming        │
└─────────────────────┘
```

---

## Requirements Verification

| Requirement | Evidence | Status |
|---|---|---|
| **Structured Logging** | JSON logs with `asctime`, `levelname`, `message`, `pathname`, `lineno` | ✅ Implemented |
| **Metrics Endpoint** | `/metrics` exposes Prometheus-compatible metrics | ✅ Live at http://localhost/metrics |
| **Remote Log Access** | Can inspect logs via `docker compose logs` without SSH | ✅ Available |
| **Machine-Readable Fields** | JSON format with parseable fields | ✅ All fields typed and structured |
| **Operator Tooling Path** | Clear commands for remote inspection | ✅ Documented above |

---

## Next Steps (Silver Tier)

For **Silver Tier (The Alarm)**, the next phase will:
1. Add **Prometheus** to scrape `/metrics` endpoint
2. Add **Alertmanager** to define alert rules
3. Integrate **Discord Webhook** for notifications

This Bronze evidence provides the foundation for Silver tier alerting.

---

## Technical Stack

- **Language**: Python 3.13
- **Framework**: Flask 3.1
- **Logging Library**: python-json-logger 4.1.0
- **Metrics Library**: prometheus-flask-exporter 0.23.2
- **Container Runtime**: Docker/Docker Compose
- **Log Format**: JSON (RFC 7159)
- **Metrics Format**: OpenMetrics / Prometheus text format

---

## References

- [Prometheus Metrics Format](https://prometheus.io/docs/instrumenting/exposition_formats/)
- [JSON Logging Best Practices](https://www.splunk.com/en_us/blog/security/json-logging-best-practices.html)
- [Docker Compose Logs](https://docs.docker.com/compose/reference/logs/)
- [ML Hackathon 2026 - Incident Response Quest](./Production_Engineering_Hackathon.md)
