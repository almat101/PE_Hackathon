# Configuration Reference

**Document ID:** CFG-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Overview](#1-overview)
2. [Environment Variables](#2-environment-variables)
3. [.env File](#3-env-file)
4. [Gunicorn Configuration](#4-gunicorn-configuration)
5. [Nginx Configuration](#5-nginx-configuration)
6. [Prometheus Configuration](#6-prometheus-configuration)

---

## 1. Overview

Application configuration is managed exclusively through environment variables
loaded from a `.env` file. The file is not committed to version control;
credentials are injected via GitHub Secrets during CI/CD deployment.

A template is provided at `.env.example` with placeholder values.

---

## 2. Environment Variables

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_ENV` | No | `production` | Flask environment mode |
| `FLASK_DEBUG` | No | `false` | Enable Flask debug mode (never in production) |

### Database (PostgreSQL)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_NAME` | Yes | `hackathon_db` | PostgreSQL database name |
| `DATABASE_HOST` | Yes | `localhost` | Database hostname. Set to `db` inside Docker Compose network. |
| `DATABASE_PORT` | No | `5432` | Database port |
| `DATABASE_USER` | Yes | `postgres` | Database user |
| `DATABASE_PASSWORD` | Yes | `postgres` | Database password |

Defaults are defined in `app/database.py` via `os.environ.get()` fallbacks.
Inside Docker Compose, `DATABASE_HOST` must be set to `db` (the service name)
so the application resolves the database container via Docker DNS.

### Chaos Testing

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CHAOS_TOKEN` | Yes | -- | Authentication token for `GET /chaos`. Validated against `X-Chaos-Token` request header. If unset, the endpoint returns 401 for all requests. |

### Observability

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GRAFANA_ADMIN_PASSWORD` | No | -- | Grafana web UI admin password. Used by the `grafana` service in Docker Compose. |
| `DISCORD_WEBHOOK` | No | -- | Discord webhook URL for alert notifications. Used by the `alertmanager-discord` service. If unset, alerts are not forwarded to Discord. |

---

## 3. .env File

### Setup

```bash
cp .env.example .env
# Edit .env with your values
```

### Template (`.env.example`)

```bash
######################################
# Flask Application Configuration
######################################
FLASK_ENV=production
FLASK_DEBUG=false

######################################
# Database (PostgreSQL)
######################################
DATABASE_NAME=hackathon_db
DATABASE_HOST=db
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=changeme

######################################
# Chaos Testing
######################################
CHAOS_TOKEN=changeme

######################################
# Observability
######################################
GRAFANA_ADMIN_PASSWORD=changeme
DISCORD_WEBHOOK=https://discord.com/api/webhooks/your-webhook-url
```

### CI/CD Injection

In production, the `.env` file is injected from the `ENV_FILE` GitHub Secret.
The deploy job writes it to disk before rebuilding containers:

```bash
echo "$ENV_FILE" > .env
docker compose up -d --build
```

This keeps credentials out of version control entirely.

---

## 4. Gunicorn Configuration

Gunicorn is configured via CLI arguments in the Dockerfile `CMD`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--bind` | `0.0.0.0:5000` | Listen on all interfaces, port 5000 |
| `--workers` | `2` | Number of worker processes |
| `--threads` | `4` | Threads per worker |
| `--worker-class` | `gthread` | Threaded worker for I/O-bound workloads |
| `--backlog` | `2048` | Maximum pending connections queue |
| `--timeout` | `120` | Worker timeout in seconds |
| `--access-logfile` | `-` | Access log to stdout |
| `--error-logfile` | `-` | Error log to stderr |

---

## 5. Nginx Configuration

Key tuning parameters in `nginx/nginx.conf`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `worker_connections` | 4096 | Max simultaneous connections per worker |
| `keepalive` (upstream) | 32 | Persistent connections to Gunicorn |
| `proxy_connect_timeout` | 3s | Max wait to establish upstream connection |
| `proxy_read_timeout` | 30s | Max wait for upstream response |
| `proxy_send_timeout` | 30s | Max wait to send request upstream |
| `keepalive_timeout` | 65s | Client connection keep-alive duration |
| `client_max_body_size` | 10M | Max request body size |
| `gzip_min_length` | 1000 | Min response size for compression |

---

## 6. Prometheus Configuration

Scrape and evaluation settings in `prometheus/prometheus.yml`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `scrape_interval` | 5s | How often Prometheus scrapes targets |
| `evaluation_interval` | 5s | How often alert rules are evaluated |
| `alertmanager target` | `alertmanager:9093` | Where to send firing alerts |

Alertmanager routing in `alertmanager/alertmanager.yml`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `resolve_timeout` | 1m | Time before considering an alert resolved |
| `group_wait` | 10s | Wait before sending grouped alerts |
| `group_interval` | 10s | Interval between grouped notifications |
| `repeat_interval` | 1h | Re-notification interval for unresolved alerts |

---

## Related Documentation

- [CI_CD.md](CI_CD.md) -- Pipeline secrets and deployment configuration.
- [ARCHITECTURE.md](ARCHITECTURE.md) -- Service inventory and network topology.
- [OBSERVABILITY.md](OBSERVABILITY.md) -- Prometheus, Alertmanager, Grafana
  configuration details.
