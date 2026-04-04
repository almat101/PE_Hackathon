# Multi-stage Dockerfile for URL Shortener
# Production: Gunicorn with 4 workers
# Development: Flask dev server (via run.py)

FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl procps && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for faster dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and install
# Layer caching: if pyproject.toml hasn't changed, this layer is reused
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen 2>/dev/null || uv sync && \
    ln -s /app/.venv/bin/python /usr/local/bin/python-app && \
    ln -s /app/.venv/bin/gunicorn /usr/local/bin/gunicorn

# Copy application code
COPY . .

EXPOSE 5000

# Health check — Docker knows when container is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Production: Gunicorn as PID 1 for proper signal handling and restart
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "run:app"]
