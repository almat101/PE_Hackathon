# Technical Decision Log

**Document ID:** ADR-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Format](#1-format)
2. [ADR-001: Python + Flask](#2-adr-001-python--flask)
3. [ADR-002: PostgreSQL](#3-adr-002-postgresql)
4. [ADR-003: Peewee ORM](#4-adr-003-peewee-orm)
5. [ADR-004: Gunicorn with gthread Workers](#5-adr-004-gunicorn-with-gthread-workers)
6. [ADR-005: Nginx Reverse Proxy](#6-adr-005-nginx-reverse-proxy)
7. [ADR-006: Docker Compose](#7-adr-006-docker-compose)
8. [ADR-007: Per-Request Database Connections](#8-adr-007-per-request-database-connections)
9. [ADR-008: Prometheus + Alertmanager + Grafana](#9-adr-008-prometheus--alertmanager--grafana)
10. [ADR-009: uv Package Manager](#10-adr-009-uv-package-manager)
11. [ADR-010: Gunicorn as PID 1](#11-adr-010-gunicorn-as-pid-1)
12. [ADR-011: 2 Workers, 4 Threads](#12-adr-011-2-workers-4-threads)
13. [ADR-012: SQLite for Tests](#13-adr-012-sqlite-for-tests)

---

## 1. Format

Each decision follows a lightweight Architecture Decision Record (ADR) format:

- **Context:** The problem or constraint that prompted the decision.
- **Options considered:** Alternatives evaluated.
- **Decision:** What was chosen.
- **Rationale:** Why this option was selected over alternatives.
- **Consequences:** Trade-offs and implications.

---

## 2. ADR-001: Python + Flask

**Context:** The hackathon project requires a web API with database
integration, deployed in Docker containers. The team needs to iterate quickly.

**Options considered:**
- **Flask** -- Micro-framework, minimal boilerplate, explicit routing.
- **Django** -- Full-featured, includes ORM and admin, heavier.
- **FastAPI** -- Async, automatic OpenAPI docs, Pydantic validation.
- **Express.js (Node.js)** -- JavaScript ecosystem, async by default.

**Decision:** Flask 3.1 on Python 3.13.

**Rationale:**
- Minimal boilerplate allows rapid prototyping during a hackathon.
- Explicit control over every component (ORM, logging, metrics) rather than
  framework opinions.
- Broad library ecosystem for monitoring (`prometheus-flask-exporter`),
  logging (`python-json-logger`), and database access (`peewee`).
- Team familiarity with Python.

**Consequences:**
- No built-in async support. I/O-bound workloads require threaded workers
  (addressed by Gunicorn gthread).
- No automatic API documentation. Endpoints are documented manually in the
  README.

---

## 3. ADR-002: PostgreSQL

**Context:** The application requires persistent storage for users, URLs, and
events with relational integrity (foreign keys, unique constraints).

**Options considered:**
- **PostgreSQL** -- Full-featured RDBMS, ACID, connection pooling support.
- **MySQL** -- Widely used, less strict defaults.
- **SQLite** -- Zero-config, no server, file-based.
- **MongoDB** -- Document store, schema-less.

**Decision:** PostgreSQL 17 (alpine image).

**Rationale:**
- ACID compliance and strict constraint enforcement (UNIQUE, FK) catch data
  integrity issues at the database level.
- `PooledPostgresqlDatabase` from Peewee provides built-in connection pooling
  without external tools (PgBouncer).
- The alpine image has a small footprint (~80 MB), suitable for 1-vCPU
  droplets.
- `pg_isready` provides a reliable health check primitive for Docker Compose
  startup ordering.

**Consequences:**
- Requires a running database server (vs. SQLite embedded).
- Connection pool management adds configuration complexity
  (`max_connections`, `stale_timeout`).

---

## 4. ADR-003: Peewee ORM

**Context:** The application needs an ORM to interact with PostgreSQL,
supporting model definitions, migrations, and query building.

**Options considered:**
- **Peewee** -- Lightweight, Pythonic, built-in connection pooling.
- **SQLAlchemy** -- Feature-rich, industrial-strength, steeper learning curve.
- **Raw SQL** -- Maximum control, no abstraction overhead.
- **Tortoise ORM** -- Async-first, Django-style.

**Decision:** Peewee 3.17.

**Rationale:**
- Lightweight and Pythonic: model definitions are concise (3 models in ~50
  lines total).
- Built-in `PooledPostgresqlDatabase` provides connection pooling without
  external dependencies.
- `DatabaseProxy` allows swapping the database at runtime (production
  PostgreSQL vs. test SQLite).
- Parameterized queries by default prevent SQL injection without additional
  configuration.

**Consequences:**
- Less ecosystem support than SQLAlchemy (fewer tutorials, extensions).
- No built-in migration tool; schema changes require manual table creation
  with `safe=True`.

---

## 5. ADR-004: Gunicorn with gthread Workers

**Context:** Flask's built-in development server is single-threaded and not
suitable for production. A production WSGI server is needed.

**Options considered:**
- **Gunicorn (sync workers)** -- Process-based concurrency, simple.
- **Gunicorn (gthread workers)** -- Thread-based concurrency within processes.
- **uWSGI** -- Feature-rich, complex configuration.
- **Uvicorn** -- ASGI server, requires async framework.

**Decision:** Gunicorn with `gthread` worker class.

**Rationale:**
- The application is I/O-bound (database queries, not CPU-intensive
  computation). Threads allow concurrent request handling during database
  waits without the memory overhead of separate processes.
- `gthread` workers share the Python interpreter within a process, reducing
  memory usage on 1 GB RAM droplets.
- Gunicorn's simplicity: configuration is a single `CMD` line in the
  Dockerfile.
- Worker timeout (120s) automatically kills and replaces hung workers.

**Consequences:**
- Python's GIL limits true CPU parallelism within a single worker process.
  Acceptable because the workload is I/O-bound,not CPU-bound.
- Thread safety must be considered for shared state (not an issue: Flask
  request context is thread-local, database connections are per-request).

---

## 6. ADR-005: Nginx Reverse Proxy

**Context:** The application needs a reverse proxy for connection management,
load balancing across replicas, and defense against slow clients.

**Options considered:**
- **Nginx** -- Battle-tested, high performance, low memory.
- **Traefik** -- Auto-discovery, Let's Encrypt integration, Docker-aware.
- **Caddy** -- Automatic HTTPS, simple config.
- **No proxy (expose Gunicorn directly)** -- Simplest option.

**Decision:** Nginx 1.28 (alpine image).

**Rationale:**
- Upstream keepalive (32 connections) eliminates TCP handshake overhead
  between Nginx and Gunicorn.
- JSON error pages (404, 502, 503, 504) ensure clients always receive
  `application/json`, even when the application is down.
- Request buffering (`proxy_buffering on`) frees Gunicorn workers quickly by
  absorbing slow client uploads.
- Docker DNS round-robin provides automatic load balancing when replicas are
  enabled, without additional configuration.
- Sub-millisecond overhead and ~5 MB memory footprint.

**Consequences:**
- No automatic TLS. HTTPS would require manual certificate management or
  adding Certbot.
- Additional service to manage and monitor.

---

## 7. ADR-006: Docker Compose

**Context:** The application consists of multiple services (app, database,
proxy, monitoring) that need to be orchestrated together.

**Options considered:**
- **Docker Compose** -- Declarative, single-file, good for single-host.
- **Kubernetes** -- Container orchestration at scale, complex.
- **Docker Swarm** -- Multi-host, built into Docker, simpler than K8s.
- **Bare metal** -- No containerization.

**Decision:** Docker Compose with a single `docker-compose.yml`.

**Rationale:**
- Single-host deployment (1-vCPU DigitalOcean droplet). Kubernetes is
  unnecessary overhead for this scale.
- `depends_on` with `service_healthy` conditions ensures correct startup
  ordering.
- `restart: always` provides basic process supervision without systemd units.
- `deploy.replicas` enables horizontal scaling when needed (currently
  commented out).
- All 7 services defined in one file; reproducible with
  `docker compose up -d`.

**Consequences:**
- Single-host limitation: all services run on one machine.
- No built-in rolling updates. Deploys rebuild all containers simultaneously
  (`docker compose up -d --build`).

---

## 8. ADR-007: Per-Request Database Connections

**Context:** Database connections must be managed across request lifecycles.
Two approaches: persistent connections (held open) or per-request connections
(open on request start, close on request end).

**Options considered:**
- **Per-request connect/disconnect** via Flask hooks.
- **Persistent connection pool** with connections held open across requests.
- **External pooler** (PgBouncer) as a connection proxy.

**Decision:** Per-request connect/disconnect using Flask `before_request` and
`teardown_appcontext` hooks, backed by `PooledPostgresqlDatabase`.

**Rationale:**
- Clean lifecycle: each request gets a fresh connection from the pool and
  returns it after the response. No stale connections.
- `PooledPostgresqlDatabase` with `stale_timeout=300` automatically discards
  connections idle for more than 5 minutes.
- Graceful degradation: if the database is down, `before_request` catches the
  connection error and returns HTTP 503 instead of crashing.
- No external dependencies (PgBouncer) to deploy and configure.

**Consequences:**
- Connection setup overhead on every request (~1-2 ms). Acceptable at the
  current request volume.
- Pool size (10) limits concurrent database operations per app instance.

---

## 9. ADR-008: Prometheus + Alertmanager + Grafana

**Context:** The application needs observability: metrics collection,
alerting, and dashboards.

**Options considered:**
- **Prometheus + Alertmanager + Grafana** -- Industry standard, pull-based.
- **Datadog** -- SaaS, hosted, auto-instrumentation.
- **ELK stack** -- Elasticsearch + Logstash + Kibana.
- **Application-only logging** -- No metrics infrastructure.

**Decision:** Prometheus + Alertmanager + Grafana, self-hosted in Docker
Compose.

**Rationale:**
- `prometheus-flask-exporter` adds metrics to Flask with 2 lines of code.
  Zero application changes beyond importing the library.
- Pull-based model (Prometheus scrapes `/metrics`) requires no push
  infrastructure.
- Alert rules defined in YAML alongside application code (version-controlled).
- Grafana provides real-time dashboards without writing code.
- All components are Docker images with sub-second startup.
- No SaaS costs or external dependencies.

**Consequences:**
- Self-hosted monitoring adds 3 containers to the stack (Prometheus,
  Alertmanager, Grafana), consuming additional memory on the droplet.
- Prometheus has no built-in long-term retention. Data is stored locally on
  the `prometheus_data` volume.

---

## 10. ADR-009: uv Package Manager

**Context:** Python package installation is needed both locally (development)
and in Docker (production).

**Options considered:**
- **uv** -- Fast Rust-based installer, drop-in pip replacement.
- **pip** -- Standard Python package installer.
- **Poetry** -- Dependency management with lock files.
- **pipenv** -- Virtual environment + dependency management.

**Decision:** uv.

**Rationale:**
- 10-100x faster than pip for dependency resolution and installation.
- Lock file (`uv.lock`) ensures deterministic builds across environments.
- `uv sync` installs exact versions from the lock file in one command.
- Docker layer caching: `COPY pyproject.toml uv.lock` + `RUN uv sync`
  creates a cacheable layer. Dependencies are only re-installed when the
  lock file changes.

**Consequences:**
- uv must be installed in the Docker image (copied from
  `ghcr.io/astral-sh/uv:latest`).
- Developers must install uv locally (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

---

## 11. ADR-010: Gunicorn as PID 1

**Context:** Docker's restart policy only triggers when PID 1 exits. The
`/chaos` endpoint needs to crash the container from within to trigger
automatic restart.

**Options considered:**
- **Gunicorn as PID 1** via Dockerfile CMD.
- **Shell wrapper** (`bash -c "gunicorn ..."`) as PID 1.
- **Init system** (tini, dumb-init) as PID 1.

**Decision:** Gunicorn runs directly as PID 1 (no shell wrapper).

**Rationale:**
- `os.kill(1, signal.SIGTERM)` in the `/chaos` endpoint sends the signal
  directly to the Gunicorn master process.
- Gunicorn handles SIGTERM gracefully: finishes in-flight requests, then
  exits. Docker detects the exit and restarts the container.
- Shell wrappers intercept SIGTERM and may not forward it correctly.
- No additional packages needed (no tini or dumb-init).

**Consequences:**
- Gunicorn must handle signal propagation to worker processes (it does by
  default).
- `procps` package is installed for debugging (`ps`, `kill` commands inside
  the container).

---

## 12. ADR-011: 2 Workers, 4 Threads

**Context:** Gunicorn worker/thread count must be tuned for the target
infrastructure (1-vCPU, 1 GB RAM DigitalOcean droplet).

**Options considered:**
- **4 workers, 1 thread each** -- `2 * CPU + 1` rule.
- **2 workers, 4 threads each** -- Fewer processes, more threads.
- **1 worker, 8 threads** -- Minimal process overhead.

**Decision:** 2 workers, 4 threads each (8 concurrent requests per container).

**Rationale:**
- 2 processes on a 1-vCPU machine avoids excessive context switching (4
  processes would over-subscribe the CPU).
- 4 threads per worker handles I/O-bound database waits concurrently.
  Threads share memory within a process, keeping total RSS under ~100 MB.
- Load test results confirm: 200 VUs at p95 = 8.94 ms (2 replicas), 50 VUs
  at p95 = 58.16 ms (1 replica). The configuration handles the target load.

**Consequences:**
- Maximum 8 concurrent requests per container. At higher load, requests queue
  in the backlog (2048 slots).
- For scaling beyond 8 concurrent requests, enable `deploy.replicas: 2` in
  Docker Compose (total: 16 concurrent).

---

## 13. ADR-012: SQLite for Tests

**Context:** Tests need a database, but requiring a running PostgreSQL
instance for `pytest` adds setup complexity and slows CI.

**Options considered:**
- **SQLite in-memory** -- Zero-config, fast, runs anywhere.
- **PostgreSQL in Docker** -- Matches production, slower setup.
- **PostgreSQL testcontainers** -- Auto-provisioned, Docker required.

**Decision:** In-memory SQLite via Peewee's `SqliteDatabase(":memory:")`.

**Rationale:**
- Zero external dependencies: tests run with `uv run pytest` on any machine.
- In-memory database is created and destroyed per test (~1 ms overhead).
- Peewee's `DatabaseProxy` allows swapping SQLite for PostgreSQL at runtime
  without changing application code.
- CI pipeline runs tests without Docker, reducing pipeline time.

**Consequences:**
- SQLite lacks some PostgreSQL features (e.g., `ON CONFLICT ... PRESERVE`,
  `pg_get_serial_sequence`). Seed module and some conflict-resolution
  queries are not exercised in tests.
- SQLite's type system is more permissive. Some type-related bugs may only
  surface in production.

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) -- Resulting system design from these
  decisions.
- [CAPACITY_PLAN.md](CAPACITY_PLAN.md) -- Performance implications of worker
  and connection pool sizing.
