# URL Shortener — MLH PE Hackathon 2026

> **Stack:** Flask · Peewee · PostgreSQL · Gunicorn · Nginx · Docker

## Quick Start

```bash
docker compose up -d --build
curl http://localhost/health
# {"status":"ok"}
```

### Seed Database (optional)

```bash
docker compose exec app uv run python -c "
from run import app
with app.app_context():
    from app.database import db
    db.connect(reuse_if_open=True)
    from app.seed import seed_all
    seed_all()
    db.close()
"
```

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
| POST | `/users/bulk` | Bulk CSV import (`multipart/form-data`) |

### URLs
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/urls` | Create URL (auto-generates `short_code`) |
| GET | `/urls` | List URLs (`?user_id=`) |
| GET | `/urls/<id>` | Get URL by ID |
| PUT | `/urls/<id>` | Update URL |
| POST | `/shorten` | Quick shorten (`{"url": "..."}`) |
| GET | `/<short_code>` | 302 redirect |

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events` | List events (`?url_id=&user_id=`) |

## Tests

```bash
uv run pytest --cov=app --cov-report=term-missing -v
# 54 passed — 77% coverage
```

## Local Development

```bash
uv sync --dev
uv run run.py
```

