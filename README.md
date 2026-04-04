# MLH PE Hackathon 2026 — URL Shortener

> **Event:** MLH Production Engineering Hackathon 2026 (Apr 4–5)  
> **Challenge:** Build a production-grade URL shortener and tackle 3 engineering quests
> **Current Status:** ✅ Core MVP + Tests (56% coverage) + Full infrastructure deployed

---

## 🎯 What is This?

A **URL shortener service** built with Flask, PostgreSQL, and Docker. Supports:
- RESTful API for creating & managing short links
- Multiple app instances with Nginx load balancing
- Observability stack (Prometheus, Loki, Grafana)
- Comprehensive test suite (23/24 tests passing)
- Production-ready Docker Compose setup

**Time to deployment:** ~5 minutes with Docker Compose

---

## 🚀 Quick Start (3 Options)

### Option 1: Docker Compose (Recommended ⭐)

Runs everything: app, database, cache, reverse proxy, monitoring.

**Prerequisites:** Docker + Docker Compose

```bash
# 1. Start all services
docker compose up -d --build

# 2. Wait for database initialization (~10 seconds)
sleep 10

# 3. Verify health
curl http://localhost/health
# Expected: {"status":"ok"}
```

✅ **Done!** Service is running on `http://localhost`

---

### Option 2: Docker Compose + Database Seeding

Same as Option 1, but also loads 6,822 test records.

```bash
# 1. Start services
docker compose up -d --build
sleep 10

# 2. Seed database (400 users, 2000 URLs, 3422 events)
docker compose exec app python app/seed.py

# 3. Verify
curl http://localhost/urls?limit=5
# Should return JSON array with ~5 URLs
```

---

### Option 3: Local Development (Without Docker)

For development on your machine.

**Prerequisites:** 
- Python 3.13+
- PostgreSQL 17+ running locally
- Redis (optional)

**Setup:**

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Create PostgreSQL database
createdb hackathon_db

# 4. Configure environment
cp .env.example .env
# Edit .env if your DB credentials differ from defaults

# 5. Run server
python run.py
# Running on http://localhost:5000
```

**Verify:**
```bash
curl http://localhost:5000/health
# Expected: {"status":"ok"}
```

---

## 📡 API Endpoints

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/health` | `{"status":"ok"}` | Service alive |
| POST | `/shorten` | JSON object | Create short URL |
| GET | `/<code>` | 302 redirect | Go to original URL |
| GET | `/urls` | JSON array | List all URLs (paginated) |
| DELETE | `/api/urls/<code>` | JSON object | Deactivate URL |

---

## 💻 Testing the API

### Create a Short URL

```bash
curl -X POST http://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com", "custom_code": "gh"}'

# Response (HTTP 201):
{
  "id": 1,
  "short_code": "gh",
  "short_url": "http://localhost/gh",
  "original_url": "https://github.com",
  "click_count": 0,
  "is_active": true,
  "created_at": "2026-04-04T13:12:01",
  "title": null,
  "user_id": null
}
```

### Follow the Short Link

```bash
curl -s -i http://localhost/gh
# Response: HTTP 302 Location: https://github.com
```

### List All URLs

```bash
curl http://localhost/urls

# Response (JSON array):
[
  {
    "id": 1,
    "short_code": "gh",
    "original_url": "https://github.com",
    "click_count": 1
  }
]
```

---

## 🧪 Running the Test Suite

### Prerequisites
- Docker Compose running (`docker compose up -d`)

### Test via Docker

```bash
# Run all tests with coverage
docker compose exec app pytest tests/ -v --cov=app --cov-report=term-missing

# Expected output:
# ============== test session starts ==============
# tests/test_models.py::test_create_user PASSED
# tests/test_models.py::test_short_url_unique PASSED
# ...
# ============ 23 passed in 0.25s =============
# ----------- coverage: platform linux -- 56% -----------
```

### Test Results ✅

| Component | Coverage | Status |
|-----------|----------|--------|
| Data Models | 100% | ✅ All 7 model tests passing |
| API Routes | 94% | ✅ All 15 route tests passing |
| Cache Layer | 0% | ⚠️ Integration tested only |
| **Total** | **56%** | ✅ 23/24 tests passing |

---

## 🔍 Monitoring & Observability

### Health Check

```bash
curl http://localhost/health
{"status":"ok"}
```

### View Logs (Docker)

```bash
# App logs
docker compose logs app -f

# Database logs
docker compose logs db -f

# All services
docker compose logs -f
```

### Prometheus Metrics

```bash
# Check if Prometheus is scraping targets
curl http://localhost:9090/api/v1/targets

# View metrics endpoint (if enabled)
curl http://localhost/metrics
```

### Grafana Dashboards (if running)

```
URL: http://localhost:3000
Username: admin
Password: admin

→ Explore → Loki → {container=~".*app.*"}
```

---

## 🐛 Troubleshooting

### "Connection refused" when calling API

**On Docker Compose:** Wait 10-15 seconds for database initialization.

```bash
# Check if services are up
docker compose ps

# Expected: db, redis, app should be "Up"
```

**On Local Dev:** Verify file path in `.env`:

```bash
# Should be 'localhost' for local, 'db' for Docker
cat .env | grep DATABASE_HOST
```

### "Database locked" errors

Stop the app before running tests:

```bash
# If running locally
pkill -f "python run.py"

# Then run tests
pytest tests/ -v
```

### Slow first request (10+ seconds)

Normal on first Docker start—database is initializing. Second request onwards: <100ms.

### "Port 5000 already in use"

```bash
# Find process using port 5000
lsof -i :5000

# Kill it
kill -9 <PID>
```

---

## 📊 Architecture

### Data Models

```
User
├── id (PK)
├── username (UNIQUE)
└── email

ShortURL
├── id (PK)
├── user_id (FK, nullable)
├── short_code (UNIQUE)
├── original_url
├── click_count
└── is_active

Event
├── id (PK)
├── url_id (FK)
├── user_id (FK, nullable)
├── event_type (redirect | deactivate)
└── timestamp
```

### Services (Docker Compose)

```
Nginx (http://localhost)
  ↓
  ├→ App (Gunicorn 4 workers)
  │    ↓
  │    ├→ PostgreSQL (port 5432)
  │    └→ Redis (port 6379)
  │
  ├→ Prometheus (http://localhost:9090)
  ├→ Grafana (http://localhost:3000)
  ├→ Loki (http://localhost:3100)
  └→ AlertManager (port 9093)
```

---

## 📝 Project Status

| Phase | Status | Details |
|-------|--------|---------|
| **Core MVP** | ✅ Complete | All 5 endpoints, data models, error handling |
| **Testing** | ✅ Complete | 23/24 tests, 56% coverage |
| **Docker** | ✅ Complete | 10-service orchestration |
| **CI/CD** | ✅ Complete | GitHub Actions pipeline |
| **Observability** | ✅ Complete | Prometheus, Loki, AlertManager |
| **Load Testing** | ✅ Verified | 50-concurrent burst: 0% error rate |

---

## 🤝 Contributing

Working on this project as a team?

1. **Create feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes and test locally:**
   ```bash
   docker compose down
   docker compose up -d --build
   docker compose exec app pytest tests/ -v
   ```

3. **Commit with clear message:**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

4. **Push and open PR:**
   ```bash
   git push origin feature/your-feature-name
   ```

   Create PR on GitHub—CI pipeline will validate automatically.

---

## 📚 Additional Resources

- **Full Roadmap:** See [roadmap.md](./roadmap.md) for detailed implementation guide
- **Submission Strategy:** See [SUBMISSION_STRATEGY.md](./SUBMISSION_STRATEGY.md) for quest track planning
- **Quick Start Guide:** See [QUICKSTART.md](./QUICKSTART.md) for deployment guide

---

## 📄 License

MIT License — See [LICENSE](./LICENSE)

---

**Questions?** Open an issue or ask in the team chat. Good luck! 🚀

- Check [roadmap.md](./roadmap.md) — comprehensive 2000+ line guide
- See `docs/` folder for runbooks and decision logs
- Review test files (`tests/`) for expected behavior
- Check GitHub Actions logs for CI failures (`Actions` tab)

