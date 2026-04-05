# URL Shortener

Production-grade URL shortening service built for the MLH PE Hackathon 2026.

**Stack:** Python 3.13, Flask 3.1, Gunicorn, Peewee ORM, PostgreSQL 17, Nginx 1.28, Docker Compose, Prometheus, Alertmanager, Grafana

---

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [API Reference](#api-reference)
4. [Operational Endpoints](#operational-endpoints)
5. [Error Handling](#error-handling)
6. [Testing](#testing)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Observability](#observability)
9. [Local Development](#local-development)
10. [Documentation Index](#documentation-index)

---

## Architecture

```
                        ┌──────────────────────────────────────────────────┐
                        │              Docker Compose Stack                │
                        │                                                  │
Client ──► Nginx (:80) ─┤──► Gunicorn (:5000) ──► PostgreSQL (:5432)      │
                        │    2 workers, 4 threads   PooledPostgresql       │
                        │    gthread worker class   max 10 connections     │
                        │                                                  │
                        │    Prometheus (:9090) ──► Alertmanager (:9093)   │
                        │         │                       │                │
                        │         ▼                       ▼                │
                        │    Grafana (:3000)     alertmanager-discord      │
                        │                           (:9094)                │
                        └──────────────────────────────────────────────────┘
```

| Service | Image | Role |
|---------|-------|------|
| `app` | Custom (python:3.13-slim + Gunicorn) | Application server |
| `db` | postgres:17-alpine | Persistent data store |
| `nginx` | nginx:1.28-alpine | Reverse proxy, keepalive pooling, JSON error pages |
| `prometheus` | prom/prometheus:v3.2.1 | Metrics collection and alerting rules |
| `alertmanager` | prom/alertmanager:v0.28.0 | Alert routing and deduplication |
| `grafana` | grafana/grafana-oss:11.5.2 | Metrics dashboards |
| `alertmanager-discord` | benjojo/alertmanager-discord | Discord webhook bridge |

All services run on a shared bridge network (`app-network`) with `restart: always`. Startup ordering is enforced via `depends_on` with health check conditions. Full architecture details: [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md).

---

## Quick Start

```bash
cp .env.example .env    # configure database credentials and tokens
docker compose up -d --build
curl http://localhost/health
# {"status":"ok"}
```

The database is auto-seeded from `csv/` on first boot (400 users, 2000 URLs, 3422 events).

---

## API Reference

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/users` | Create user (`username`, `email` required) |
| GET | `/users` | List users (`?page=&per_page=`) |
| GET | `/users/<id>` | Get user by ID |
| PUT | `/users/<id>` | Update user |
| DELETE | `/users/<id>` | Delete user (cascades URLs and events) |
| POST | `/users/bulk` | Bulk CSV import (`multipart/form-data`, batched in 100s) |

### URLs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/shorten` | Quick shorten (`{"url": "..."}`) -- returns `short_code` and `short_url` |
| POST | `/urls` | Create URL with metadata (`original_url` required, optional `user_id`, `title`) |
| GET | `/urls` | List URLs (`?user_id=&is_active=&page=&per_page=`) |
| GET | `/urls/<id>` | Get URL by ID |
| PUT | `/urls/<id>` | Update URL (`title`, `is_active`, `original_url`) |
| DELETE | `/urls/<id>` | Delete URL (cascades events) |
| GET | `/<short_code>` | 302 redirect to `original_url` + click event. Returns 404 if `is_active=false`. |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events` | Create event (`event_type` required, `details` must be a JSON object) |
| GET | `/events` | List events (`?url_id=&user_id=&event_type=&page=&per_page=`) |
| GET | `/events/<id>` | Get event by ID |
| DELETE | `/events/<id>` | Delete event |

Events are also generated automatically: `created` on URL creation, `updated` on URL update, `click` on redirect.

---

## Operational Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | Liveness probe. Returns `{"status":"ok"}`. No database dependency. |
| `/metrics` | GET | None | Prometheus-format metrics (HTTP latency histograms, request counts, process stats). |
| `/logs` | GET | None | JSON log query API. Params: `limit` (max 200), `filter` (substring), `level` (INFO/ERROR/WARNING). |
| `/chaos` | GET | `X-Chaos-Token` header | Sends SIGTERM to PID 1 (Gunicorn master), triggering container restart via Docker restart policy. Token validated against `CHAOS_TOKEN` env var. Returns 401 without valid token, 204 on success. |

---

## Error Handling

All errors return JSON. No HTML pages, no stack traces, no empty bodies (except 204 on DELETE).

| Status | Response | Trigger |
|--------|----------|---------|
| 400 | `{"error": "..."}` | Malformed JSON, missing required fields, invalid field types |
| 404 | `{"error": "Not found"}` | Resource does not exist, inactive short URL redirect |
| 405 | `{"error": "Method not allowed"}` | Unsupported HTTP method |
| 409 | `{"error": "Username already exists"}` | Unique constraint violation |
| 500 | `{"error": "Internal server error"}` | Unhandled exception (logged server-side) |
| 502 | `{"error": "Service temporarily unavailable"}` | Nginx cannot reach upstream |
| 503 | `{"error": "Service unavailable"}` | Database connection failure |
| 504 | `{"error": "Gateway timeout"}` | Upstream exceeds `proxy_connect_timeout` (3s) |

Global handlers in `app/errors.py` include a catch-all `Exception` handler. Nginx returns JSON error pages for 404, 502, 503, 504. Full reference: [Docs/ERROR_HANDLING.md](Docs/ERROR_HANDLING.md).

---

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -v
# 75 passed -- 78% coverage
```

| Module | Coverage |
|--------|----------|
| Models (User, ShortURL, Event) | 100% |
| Routes (users, urls, events) | 83-89% |
| Monitoring | 83% |
| Error handlers | 71% |
| App factory + database hooks | 76% |
| **Total** | **78%** |

Test infrastructure uses an in-memory SQLite database (`conftest.py`) with automatic table creation and teardown per test. Metrics collection is disabled during tests to avoid Prometheus registry conflicts.

---

## CI/CD Pipeline

GitHub Actions runs on every push and pull request to `main`:

```
test ──► build ──► deploy
```

| Job | Trigger | Description |
|-----|---------|-------------|
| `test` | push, PR | `uv sync --dev`, `pytest --cov-fail-under=70`. Blocks merge on failure. |
| `build` | push only | Docker image build with BuildKit layer caching (`type=gha`). |
| `deploy` | push to main | SSH to DigitalOcean droplet, `git pull`, rebuild containers, prune images. |

Branch protection on `main` requires the `test` job to pass. Full pipeline details: [Docs/CI_CD.md](Docs/CI_CD.md).

---

## Observability

The monitoring stack scrapes application metrics every 5 seconds and evaluates alert rules continuously.

| Alert | Condition | Severity |
|-------|-----------|----------|
| ServiceDown | `up{job="flask_app"} == 0` for 10s | critical |
| HighErrorRate | 5xx rate > 10% for 30s | warning |
| HighLatency | Average response > 1s for 1m | warning |
| HighCPU | CPU > 90% for 2m | warning |

Alerts route through Alertmanager to Discord via webhook. Grafana provides dashboards on `:3000`. Full configuration: [Docs/OBSERVABILITY.md](Docs/OBSERVABILITY.md).

---

## Local Development

```bash
uv sync --dev
uv run run.py          # Flask dev server on :5000
```

```bash
docker compose up -d   # Full stack with Nginx, Prometheus, Grafana
```

### Load Testing

```bash
# Bronze: 50 VUs, 60s
k6 run k6/load-test-50vus.js

# Silver: 200 VUs, 180s
k6 run k6/load-test-200vus.js

# Against remote
k6 run -e BASE_URL=http://<droplet-ip> k6/load-test-50vus.js
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md) | System architecture, service configuration, network topology, data flow |
| [Docs/ERROR_HANDLING.md](Docs/ERROR_HANDLING.md) | HTTP status codes, error handlers, route validation, error propagation |
| [Docs/FAILURE_MODES.md](Docs/FAILURE_MODES.md) | 10 failure scenarios, recovery procedures, chaos testing runbook |
| [Docs/INCIDENT_RESPONSE_BRONZE.md](Docs/INCIDENT_RESPONSE_BRONZE.md) | Monitoring, structured logging, `/logs` endpoint, incident workflow |
| [Docs/OBSERVABILITY.md](Docs/OBSERVABILITY.md) | Prometheus, Alertmanager, Grafana, Discord alerting, metrics reference |
| [Docs/CI_CD.md](Docs/CI_CD.md) | CI/CD pipeline, coverage gate, Docker build, SSH deploy |
| [Docs/load-test-baseline.md](Docs/load-test-baseline.md) | Bronze tier load test results (50 VUs, local + droplet) |
| [Docs/load-test-silver.md](Docs/load-test-silver.md) | Silver tier load test results (200 VUs, 2 replicas) |

