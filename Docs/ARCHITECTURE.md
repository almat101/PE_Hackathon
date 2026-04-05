# System Architecture

**Document ID:** ARCH-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Diagram](#2-system-diagram)
3. [Service Inventory](#3-service-inventory)
4. [Network Topology](#4-network-topology)
5. [Request Flow](#5-request-flow)
6. [Data Model](#6-data-model)
7. [Connection Management](#7-connection-management)
8. [Container Health Checks](#8-container-health-checks)
9. [Startup Ordering](#9-startup-ordering)
10. [Process Model](#10-process-model)

---

## 1. Overview

The URL Shortener is a seven-service Docker Compose stack that handles URL
shortening, redirect tracking, and analytics event storage. The application
layer is a Flask 3.1 WSGI application served by Gunicorn behind an Nginx
reverse proxy. Observability is provided by Prometheus, Alertmanager, Grafana,
and a Discord webhook bridge.

---

## 2. System Diagram

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    Docker Compose Stack                      │
                    │                    Network: app-network                      │
                    │                                                              │
                    │  ┌─────────────┐      ┌───────────────┐     ┌────────────┐  │
  Client (:80) ────────► Nginx       ├──────► Gunicorn      ├─────► PostgreSQL │  │
                    │  │ 1.28-alpine │      │ 2w × 4t       │     │ 17-alpine  │  │
                    │  │             │      │ gthread        │     │            │  │
                    │  │ keepalive:32│      │ /health        │     │ pgdata vol │  │
                    │  │ JSON errors │      │ /metrics       │     └────────────┘  │
                    │  └─────────────┘      │ /logs          │                     │
                    │                       │ /chaos         │                     │
                    │                       └───────┬────────┘                     │
                    │                               │                              │
                    │                       scrape /metrics                        │
                    │                               │                              │
                    │  ┌─────────────┐      ┌───────┴────────┐                    │
                    │  │ Grafana     │      │ Prometheus     │                    │
                    │  │ :3000       │      │ :9090          │                    │
                    │  │ dashboards  │      │ alerts.yml     │                    │
                    │  └─────────────┘      └───────┬────────┘                    │
                    │                               │                              │
                    │                          fire alerts                         │
                    │                               │                              │
                    │                       ┌───────▼────────┐                    │
                    │                       │ Alertmanager   │                    │
                    │                       │ :9093          │                    │
                    │                       └───────┬────────┘                    │
                    │                               │                              │
                    │                          webhook POST                        │
                    │                               │                              │
                    │                       ┌───────▼────────┐                    │
                    │                       │ alertmanager-  │                    │
                    │                       │ discord :9094  ├──────► Discord     │
                    │                       └────────────────┘                    │
                    └─────────────────────────────────────────────────────────────┘
```

---

## 3. Service Inventory

### 3.1 Application Server (`app`)

| Property | Value |
|----------|-------|
| Base image | `python:3.13-slim` |
| WSGI server | Gunicorn 25.x |
| Worker class | `gthread` (threaded) |
| Workers | 2 |
| Threads per worker | 4 |
| Backlog | 2048 |
| Worker timeout | 120s |
| Framework | Flask 3.1 |
| ORM | Peewee 3.17 |
| Dependency manager | uv (installed from `ghcr.io/astral-sh/uv:latest`) |
| Exposed port | 5000 (internal only) |
| Restart policy | `always` |
| PID 1 process | Gunicorn master (receives SIGTERM directly) |

Gunicorn runs as PID 1 inside the container. This is required for the `/chaos`
endpoint to function: `os.kill(1, signal.SIGTERM)` sends the signal to the
Gunicorn master, which performs graceful shutdown and triggers Docker's restart
policy.

### 3.2 Database (`db`)

| Property | Value |
|----------|-------|
| Image | `postgres:17-alpine` |
| Volume | `pgdata` (named volume, persistent) |
| Credentials | Via environment variables from `.env` |
| Restart policy | `always` |

### 3.3 Reverse Proxy (`nginx`)

| Property | Value |
|----------|-------|
| Image | `nginx:1.28-alpine` |
| Listen port | 80 (mapped to host) |
| Upstream | `app:5000` |
| Upstream keepalive | 32 connections |
| Log format | JSON (`json_combined`) |
| Gzip | Enabled for `text/plain`, `text/css`, `application/json` (min 1000 bytes) |
| Restart policy | `always` |

**Timeouts:**

| Parameter | Value |
|-----------|-------|
| `proxy_connect_timeout` | 3s |
| `proxy_read_timeout` | 30s |
| `proxy_send_timeout` | 30s |
| `keepalive_timeout` | 65s |

**JSON error pages:** Nginx intercepts 404, 502, 503, and 504 errors and
returns structured JSON responses instead of default HTML pages. This ensures
clients always receive `application/json` regardless of which layer produces the
error.

**Proxy headers forwarded:**

| Header | Source |
|--------|--------|
| `Host` | `$host` |
| `X-Real-IP` | `$remote_addr` |
| `X-Forwarded-For` | `$proxy_add_x_forwarded_for` |
| `X-Forwarded-Proto` | `$scheme` |
| `X-Request-ID` | `$request_id` |

### 3.4 Prometheus (`prometheus`)

| Property | Value |
|----------|-------|
| Image | `prom/prometheus:v3.2.1` |
| Port | 9090 |
| Scrape interval | 5s |
| Evaluation interval | 5s |
| Storage | `prometheus_data` named volume |
| Config | `prometheus/prometheus.yml` |
| Alert rules | `prometheus/alerts.yml` |

Scrapes two targets:
- `flask_app` job: `app:5000/metrics`
- `prometheus` job: `localhost:9090` (self-monitoring)

### 3.5 Alertmanager (`alertmanager`)

| Property | Value |
|----------|-------|
| Image | `prom/alertmanager:v0.28.0` |
| Port | 9093 |
| Storage | `alertmanager_data` named volume |
| Resolve timeout | 1m |
| Group wait | 10s |
| Repeat interval | 1h |
| Receiver | `discord_webhook` via `alertmanager-discord:9094` |

### 3.6 Grafana (`grafana`)

| Property | Value |
|----------|-------|
| Image | `grafana/grafana-oss:11.5.2` |
| Port | 3000 |
| Storage | `grafana_data` named volume |
| Admin password | Via `GRAFANA_ADMIN_PASSWORD` env var |
| Sign-up | Disabled (`GF_USERS_ALLOW_SIGN_UP=false`) |

### 3.7 Discord Alert Bridge (`alertmanager-discord`)

| Property | Value |
|----------|-------|
| Image | `benjojo/alertmanager-discord` |
| Port | 9094 |
| Webhook | Via `DISCORD_WEBHOOK` env var |

---

## 4. Network Topology

All seven services connect to a single Docker bridge network: `app-network`.

```
app-network (bridge)
├── app           (5000)
├── db            (5432)
├── nginx         (80 → host)
├── prometheus    (9090 → host)
├── alertmanager  (9093 → host)
├── grafana       (3000 → host)
└── alertmanager-discord (9094 → host)
```

Service discovery uses Docker's built-in DNS. Each service name resolves to
the corresponding container IP. When `deploy.replicas` is set on the `app`
service, the `app` DNS entry resolves to all replica IPs and Nginx
round-robins across them automatically.

**Ports exposed to host:**

| Port | Service |
|------|---------|
| 80 | Nginx |
| 9090 | Prometheus |
| 9093 | Alertmanager |
| 3000 | Grafana |
| 9094 | alertmanager-discord |

Port 5000 (Gunicorn) and 5432 (PostgreSQL) are internal to the Docker network
and not mapped to the host.

---

## 5. Request Flow

### Standard API Request

```
1. Client sends HTTP request to Nginx (:80)
2. Nginx proxies to upstream flask_app (app:5000) via keepalive connection
3. Gunicorn assigns request to an available worker thread
4. Flask before_request hook opens a database connection (PooledPostgresqlDatabase)
5. Route handler processes request, validates input, executes queries
6. Response is returned to the client
7. Flask teardown_appcontext hook closes the database connection
```

### Redirect Flow (`GET /<short_code>`)

```
1. Client sends GET /<short_code>
2. Route handler queries ShortURL by short_code
3. If not found or is_active=false: returns 404
4. Atomically increments click_count: UPDATE ... SET click_count = click_count + 1
5. Creates an Event record with event_type="click"
6. Returns 302 redirect with Location header set to original_url
```

### URL Creation Flow (`POST /urls`)

```
1. Validates JSON body: original_url required, user_id existence check
2. Generates random 6-character alphanumeric short_code
3. Attempts INSERT with up to 10 retries on IntegrityError (code collision)
4. Creates an Event record with event_type="created"
5. Returns 201 with the URL object
```

---

## 6. Data Model

```
┌──────────┐       ┌──────────────┐       ┌──────────┐
│  users   │       │  short_urls  │       │  events  │
├──────────┤       ├──────────────┤       ├──────────┤
│ id (PK)  │◄──┐   │ id (PK)      │◄──┐   │ id (PK)  │
│ username │   └───│ user (FK)    │   └───│ url (FK) │
│ email    │       │ original_url │       │ user(FK) │
│ created_ │       │ short_code   │       │ event_   │
│   at     │       │ title        │       │   type   │
└──────────┘       │ is_active    │       │ timestamp│
                   │ click_count  │       │ details  │
                   │ created_at   │       └──────────┘
                   │ updated_at   │
                   └──────────────┘
```

| Table | Constraints |
|-------|-------------|
| `users` | `username` UNIQUE |
| `short_urls` | `short_code` UNIQUE, indexed. `user` FK nullable. |
| `events` | `url` FK nullable. `user` FK nullable. |

All foreign keys are nullable. Cascade deletes are handled in application code
(route handlers delete child records before parent).

---

## 7. Connection Management

### Application to Database

| Setting | Value |
|---------|-------|
| Pool class | `PooledPostgresqlDatabase` (Peewee playhouse) |
| Max connections | 10 |
| Stale timeout | 300s |
| Connection lifecycle | Per-request (open on `before_request`, close on `teardown_appcontext`) |

Connection pooling is managed by Peewee's `PooledPostgresqlDatabase`. Each
request opens a connection from the pool and returns it on completion. Stale
connections (idle > 300s) are automatically discarded.

### Nginx to Gunicorn

| Setting | Value |
|---------|-------|
| Protocol | HTTP/1.1 |
| Keepalive | 32 persistent connections |
| Buffering | Enabled (4k buffer size, 8 buffers) |

---

## 8. Container Health Checks

| Service | Check | Interval | Timeout | Retries | Start Period |
|---------|-------|----------|---------|---------|--------------|
| `app` | `curl -f http://localhost:5000/health` | 15s | 5s | 3 | 10s |
| `app` (Dockerfile) | `curl -f http://localhost:5000/health` | 30s | 10s | 3 | 15s |
| `db` | `pg_isready -U ${DATABASE_USER}` | 5s | 5s | 5 | 10s |

The `app` service has two health check definitions: the Dockerfile HEALTHCHECK
(used by Docker daemon for container status) and the Compose healthcheck (used
for `depends_on` conditions). Both call the `/health` endpoint which returns
`{"status":"ok"}` without any database dependency.

---

## 9. Startup Ordering

```
db (service_healthy) ──► app ──► nginx
```

1. `db` starts first. Compose waits until `pg_isready` passes.
2. `app` starts after `db` is healthy. On boot, the app factory:
   - Connects to the database
   - Creates tables if they do not exist (`safe=True`)
   - Seeds data from `csv/` if tables are empty
   - If the database is not yet ready, the exception is caught silently and the
     app starts anyway. The `before_request` hook returns 503 for individual
     requests until the database becomes reachable.
3. `nginx` starts after `app` is running.
4. `prometheus`, `alertmanager`, `grafana`, `alertmanager-discord` start
   independently with no ordering constraints.

---

## 10. Process Model

### Gunicorn Configuration

```
gunicorn --bind 0.0.0.0:5000
         --workers 2
         --threads 4
         --worker-class gthread
         --backlog 2048
         --timeout 120
         --access-logfile -
         --error-logfile -
         run:app
```

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Workers | 2 | Matches 1-vCPU droplet (avoids context-switching overhead) |
| Threads | 4 per worker | Handles I/O-bound database waits concurrently |
| Worker class | `gthread` | Thread-based concurrency for I/O-bound workloads |
| Backlog | 2048 | Queues connections during load spikes |
| Timeout | 120s | Allows slow database queries to complete before worker kill |

Total concurrency per container: 2 workers x 4 threads = 8 concurrent requests.

### Horizontal Scaling

The `docker-compose.yml` supports `deploy.replicas` on the `app` service
(currently commented out). When enabled, Docker DNS resolves `app` to all
replica IPs and Nginx distributes requests via round-robin. Each replica
maintains its own connection pool (10 connections each).

---

## Related Documentation

- [ERROR_HANDLING.md](ERROR_HANDLING.md) -- HTTP error codes and error
  propagation flow.
- [FAILURE_MODES.md](FAILURE_MODES.md) -- Failure scenarios, recovery
  procedures, and chaos testing.
- [OBSERVABILITY.md](OBSERVABILITY.md) -- Prometheus, Alertmanager, Grafana
  configuration.
