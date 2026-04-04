# URL Shortener — MLH PE Hackathon 2026

> **Stack:** Flask · Peewee · PostgreSQL · Gunicorn · Nginx · Docker

## Quick Start

```bash
docker compose up -d --build
curl http://localhost/health
# {"status":"ok"}
```

The database is auto-seeded from `csv/` on first boot (400 users, 2000 URLs, 3422 events).

## API Endpoints

### Health
| Method | Endpoint | Response |
|--------|----------|----------|
| GET | `/health` | `{"status":"ok"}` |

### Users
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/users` | Create user |
| GET | `/users` | List users (`?page=&per_page=`) |
| GET | `/users/<id>` | Get user by ID |
| PUT | `/users/<id>` | Update user |
| DELETE | `/users/<id>` | Delete user (cascades events/urls) |
| POST | `/users/bulk` | Bulk CSV import (`multipart/form-data`) |

### URLs
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/urls` | Create URL (auto-generates `short_code`) |
| GET | `/urls` | List URLs (`?user_id=&is_active=`) |
| GET | `/urls/<id>` | Get URL by ID |
| PUT | `/urls/<id>` | Update URL |
| DELETE | `/urls/<id>` | Delete URL (cascades events) |
| POST | `/shorten` | Quick shorten (`{"url": "..."}`) |
| GET | `/<short_code>` | 302 redirect + click event |

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events` | Create event |
| GET | `/events` | List events (`?url_id=&user_id=&event_type=`) |
| GET | `/events/<id>` | Get event by ID |
| DELETE | `/events/<id>` | Delete event |

## Error Handling

All errors return consistent JSON responses. The app never leaks stack traces or internal details to clients.

| Status | Response | When |
|--------|----------|------|
| 400 | `{"error": "Bad request"}` | Malformed JSON, missing required fields, invalid field types |
| 404 | `{"error": "Not found"}` | Resource doesn't exist (user, url, event, short code) |
| 405 | `{"error": "Method not allowed"}` | HTTP method not supported on endpoint |
| 409 | `{"error": "Username already exists"}` | Unique constraint violation (duplicate username) |
| 500 | `{"error": "Internal server error"}` | Unexpected server failure (logged, not exposed) |

Error handlers are registered globally via `app/errors.py`. Every route validates input at the boundary before touching the database:
- Type checks on all user-supplied fields (`isinstance` guards)
- Foreign key existence checks before creating relationships
- `IntegrityError` handling for duplicate/conflict scenarios
- `get_json(silent=True)` prevents crashes on non-JSON bodies

## Tests

```bash
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=50 -v
# 69 passed — 79% coverage
```

### Test coverage breakdown
| Module | Coverage |
|--------|----------|
| Models (User, ShortURL, Event) | 100% |
| Routes (users, urls, events) | 84-89% |
| Error handlers | 79% |
| App factory + DB hooks | 82-88% |
| **Total** | **79%** |

### CI Pipeline

GitHub Actions runs on every push/PR to `main`:
1. **test** — installs deps, runs pytest with `--cov-fail-under=50` (blocks merge if coverage drops)
2. **build** — builds Docker image (only runs after tests pass)

Branch protection on `main` requires the `test` job to pass before merging.

## Local Development

```bash
uv sync --dev
uv run run.py
```

