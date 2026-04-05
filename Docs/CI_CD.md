# CI/CD Pipeline

**Document ID:** CICD-2026-001
**Version:** 1.0
**Last Updated:** 2026-04-05
**Classification:** Internal -- Engineering

---

## Table of Contents

1. [Overview](#1-overview)
2. [Pipeline Stages](#2-pipeline-stages)
3. [Test Job](#3-test-job)
4. [Build Job](#4-build-job)
5. [Deploy Job](#5-deploy-job)
6. [Required Secrets](#6-required-secrets)
7. [Branch Protection](#7-branch-protection)

---

## 1. Overview

The CI/CD pipeline is implemented as a GitHub Actions workflow
(`.github/workflows/ci.yml`). It runs on every push and pull request to the
`main` branch.

```
                  push/PR to main
                        │
                        ▼
                   ┌─────────┐
                   │  test   │   pytest --cov-fail-under=70
                   └────┬────┘
                        │ pass
              ┌─────────┴─────────┐
              ▼                   ▼
        ┌──────────┐        ┌──────────┐
        │  build   │        │  deploy  │
        │ (push)   │        │ (main)   │
        └──────────┘        └──────────┘
```

| Job | Triggers | Depends On |
|-----|----------|------------|
| `test` | push, pull_request | -- |
| `build` | push only | `test` |
| `deploy` | push to `main` only | `test` |

---

## 2. Pipeline Stages

### Execution Order

1. **test** runs on every push and pull request.
2. **build** runs only on push events, after `test` passes.
3. **deploy** runs only when pushing to `main`, after `test` passes.

Build and deploy run in parallel after test succeeds. The deploy job does not
depend on the build job because the deployment target builds its own image
locally on the droplet.

---

## 3. Test Job

**Runner:** `ubuntu-latest`

**Steps:**

1. Checkout repository (`actions/checkout@v4`)
2. Install uv (`astral-sh/setup-uv@v4`)
3. Install dependencies (`uv sync --dev`)
4. Run tests:
   ```bash
   uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -v
   ```

### Coverage Gate

The `--cov-fail-under=70` flag causes pytest to exit with a non-zero status if
total line coverage drops below 70%. This blocks the pipeline and prevents
merging.

Current state: 75 tests, 78% coverage (as of 2026-04-05).

| Module | Coverage |
|--------|----------|
| Models (User, ShortURL, Event) | 100% |
| Routes (users, urls, events) | 83-89% |
| Monitoring | 83% |
| Error handlers | 71% |
| App factory + database hooks | 76% |
| Seed | 0% (excluded from test scope) |
| **Total** | **78%** |

### Test Infrastructure

- Tests run against an in-memory SQLite database (`tests/conftest.py`)
- Each test gets fresh tables (created before, dropped after)
- Prometheus metrics collection is disabled during tests (`TESTING=True`)
- No external services required (no Docker, no PostgreSQL)

---

## 4. Build Job

**Runner:** `ubuntu-latest`
**Condition:** `github.event_name == 'push'`
**Depends on:** `test`

**Steps:**

1. Checkout repository
2. Set up Docker Buildx (`docker/setup-buildx-action@v2`)
3. Build Docker image (`docker/build-push-action@v4`):
   - `push: false` -- image is built but not pushed to a registry
   - `cache-from: type=gha` -- reads layer cache from GitHub Actions cache
   - `cache-to: type=gha,mode=max` -- writes all layers to cache

The build job validates that the Docker image builds successfully. It does not
push to any registry; the deploy job builds directly on the target host.

### Dockerfile Build Process

```
python:3.13-slim
    ↓
Install system deps (gcc, libpq-dev, curl, procps)
    ↓
Install uv from ghcr.io/astral-sh/uv:latest
    ↓
Copy pyproject.toml + uv.lock → uv sync (layer cached)
    ↓
Copy application code
    ↓
HEALTHCHECK: curl -f http://localhost:5000/health
    ↓
CMD: gunicorn (2 workers, 4 threads, gthread)
```

---

## 5. Deploy Job

**Runner:** `ubuntu-latest`
**Condition:** `github.ref == 'refs/heads/main'`
**Depends on:** `test`

**Action:** `appleboy/ssh-action@v1`

**Deploy script executed on droplet:**

```bash
cd PE_Hackathon
git pull origin main
echo "$ENV_FILE" > .env
docker compose up -d --build
docker image prune -f
```

### Deploy Sequence

1. Pull latest code from `main`
2. Write the `.env` file from GitHub secret (contains database credentials,
   `CHAOS_TOKEN`, `DISCORD_WEBHOOK`, etc.)
3. Rebuild and restart all containers
4. Prune dangling images to reclaim disk space

The `.env` file is injected from the `ENV_FILE` secret rather than committed
to the repository. This keeps credentials out of version control.

---

## 6. Required Secrets

The following GitHub repository secrets must be configured for the deploy job:

| Secret | Description |
|--------|-------------|
| `DROPLET_IP` | IP address of the DigitalOcean droplet |
| `DROPLET_USER` | SSH username (e.g., `root`) |
| `DROPLET_SSH_KEY` | Private SSH key for authentication |
| `ENV_FILE` | Complete contents of the `.env` file |

The `ENV_FILE` secret contains all environment variables required by the
application:

| Variable | Purpose |
|----------|---------|
| `DATABASE_NAME` | PostgreSQL database name |
| `DATABASE_HOST` | Database hostname (`db` in Docker network) |
| `DATABASE_PORT` | Database port (5432) |
| `DATABASE_USER` | Database user |
| `DATABASE_PASSWORD` | Database password |
| `CHAOS_TOKEN` | Authentication token for `/chaos` endpoint |
| `DISCORD_WEBHOOK` | Discord webhook URL for alert notifications |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin interface password |

---

## 7. Rollback Procedure

If a deployment introduces a regression, roll back to the previous known-good
state using the following procedure.

### 7.1 Identify the Last Good Commit

```bash
# SSH into the droplet
ssh root@<DROPLET_IP>

# View recent deploy history
cd PE_Hackathon
git log --oneline -10
```

### 7.2 Roll Back the Code

```bash
# Option A: Revert to a specific commit
git checkout <known-good-sha>

# Option B: Revert the last commit (creates a new commit)
git revert HEAD --no-edit
```

### 7.3 Rebuild and Restart

```bash
docker compose up -d --build
docker image prune -f
```

### 7.4 Verify Recovery

```bash
curl -s http://localhost/health
# Expected: {"status":"ok"}

curl -s http://localhost/users | head -c 100
# Expected: JSON array (not error)
```

### 7.5 Post-Rollback

1. Confirm the service is healthy via `/health` and `/logs?level=ERROR`.
2. Notify the team of the rollback and the commit that was reverted.
3. Fix the issue on a branch, get tests passing, and re-deploy through the
   normal CI pipeline.

### Emergency: Full Stack Reset

If the database is corrupted or containers are in a crash loop:

```bash
docker compose down -v       # Destroys all data volumes
docker compose up -d --build # App auto-seeds from csv/ on boot
```

This destroys all data. Use only as a last resort.

---

## 8. Branch Protection

Branch protection rules on `main` require:

- The `test` job must pass before a pull request can be merged
- This enforces the 70% coverage minimum on all code entering `main`

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) -- Container configuration and service
  topology.
- [OBSERVABILITY.md](OBSERVABILITY.md) -- Prometheus, Alertmanager, and Grafana
  setup.
