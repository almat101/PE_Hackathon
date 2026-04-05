# Incident Response -- Bronze Tier

**Document ID:** IR-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Scope](#1-scope)
2. [Monitoring Data Exposure](#2-monitoring-data-exposure)
3. [Structured Logging](#3-structured-logging)
4. [Remote Log Inspection](#4-remote-log-inspection)
5. [Incident Response Workflow](#5-incident-response-workflow)

**Command**:
```bash
curl "http://localhost/logs?filter=database&limit=50"
```

**Response**: All logs mentioning "database" (case-insensitive)
```json
{
  "count": 3,
  "logs": [
    {
      "asctime": "2026-04-04 20:37:00,100",
      "levelname": "INFO",
      "message": "Database connection established",
      "name": "app",
      "pathname": "/app/database.py",
      "lineno": 28
    },
    {
      "asctime": "2026-04-04 20:38:45,123",
      "levelname": "ERROR",
      "message": "Database connection failed: timeout",
---

## 1. Scope

This document describes the monitoring and log inspection capabilities
implemented for the URL Shortener service. The stack provides three
observability surfaces: Prometheus-compatible metrics, structured JSON logging,
and an HTTP log inspection endpoint.

| Component | Purpose |
|-----------|---------|
| `/metrics` endpoint | Prometheus-format metrics (process, GC, HTTP) |
| JSON logging | Machine-readable log output via `python-json-logger` |
| `/logs` endpoint | Remote log query API with filtering |

---

## 2. Monitoring Data Exposure

The application exposes a `/metrics` endpoint in Prometheus text format. The
endpoint is registered automatically by `prometheus-flask-exporter` and excluded
from its own request tracking to avoid feedback loops.

**Access:**

```bash
curl http://localhost/metrics
```

**Metrics categories:**

| Family | Examples |
|--------|----------|
| Python GC | `python_gc_objects_collected_total`, `python_gc_collections_total` |
| Process | `process_virtual_memory_bytes`, `process_resident_memory_bytes`, `process_cpu_seconds_total` |
| HTTP | Per-endpoint latency histograms, request counts, status code counters |

**Implementation:** `app/monitoring.py` -- `PrometheusMetrics(app)`. Metrics
collection is disabled when `app.config["TESTING"]` is set to avoid registry
conflicts during test runs.

---

## 3. Structured Logging

All application logs are emitted as JSON objects using `python-json-logger`.
This applies to Flask, Gunicorn, and application-level loggers.

**Access:**

```bash
docker compose logs app
```

**Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `asctime` | string | Timestamp in `YYYY-MM-DD HH:MM:SS,mmm` format |
| `name` | string | Logger name (e.g., `app`, `werkzeug`) |
| `levelname` | string | Severity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `message` | string | Human-readable event description |
| `pathname` | string | Source file absolute path |
| `lineno` | integer | Source line number |

**Example:**

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

**Implementation:** `app/monitoring.py` -- configures a `JsonFormatter` on the
root logger and attaches a `LogBuffer` handler (ring buffer, 1000 entries) for
the `/logs` API.

---

## 4. Remote Log Inspection

The `/logs` endpoint provides HTTP access to recent log entries without
requiring SSH or direct container access.

**Endpoint:** `GET /logs`

**Query parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `limit` | 50 | Number of entries to return (max 200) |
| `filter` | -- | Case-insensitive substring match against the log message |
| `level` | -- | Filter by severity (`INFO`, `ERROR`, `WARNING`, `CRITICAL`) |

**Example -- retrieve recent errors:**

```bash
curl -s "http://localhost/logs?level=ERROR&limit=20"
```

**Response:**

```json
{
  "count": 1,
  "logs": [
    {
      "asctime": "2026-04-04 20:38:45,123",
      "levelname": "ERROR",
      "message": "Database connection failed",
      "name": "app",
      "pathname": "/app/app/database.py",
      "lineno": 34
    }
  ]
}
```

**Example -- keyword search:**

```bash
curl -s "http://localhost/logs?filter=timeout&limit=100"
```

**Example -- count errors programmatically:**

```bash
curl -s "http://localhost/logs?level=ERROR&limit=100" | jq '.count'
```

---

## 5. Incident Response Workflow

The following sequence describes how an operator diagnoses an incident using
the available tooling, without SSH access.

```
Step 1: Confirm service is reachable
    curl http://localhost/health
    Expected: {"status": "ok"}

Step 2: Check for errors
    curl -s "http://localhost/logs?level=ERROR&limit=20"
    Review: count field and log entries

Step 3: Search for a specific pattern
    curl -s "http://localhost/logs?filter=database&limit=50"
    Review: matching entries for root cause

Step 4: Inspect process-level metrics
    curl -s http://localhost/metrics | grep process_resident_memory_bytes
    Review: memory and CPU utilization

Step 5: Confirm resolution
    curl http://localhost/health
    Expected: {"status": "ok"}
```

---

## Related Documentation

- [ERROR_HANDLING.md](ERROR_HANDLING.md) -- HTTP status codes and error
  response format.
- [FAILURE_MODES.md](FAILURE_MODES.md) -- Failure scenarios and recovery
  procedures.
