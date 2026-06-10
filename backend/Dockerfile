# ── TradingAgents Backend — Production Dockerfile ──────────────────────────
# python:3.12-slim keeps the image small (~130 MB base) while meeting
# the requires-python = ">=3.12" constraint in pyproject.toml.
# uv is installed as a single self-contained binary so we don't need
# a separate build stage just for the package manager.

FROM python:3.12-slim

# Install uv (pinned version for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

# System deps needed by some transitive packages (e.g. asyncpg, cryptography)
# Keep this minimal — only what compile wheels need.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory to the project root inside the container.
# uvicorn is invoked as "uvicorn app.main:app", so the parent of app/ must be CWD.
WORKDIR /app

# ── Dependency installation ──────────────────────────────────────────────────
# Copy only the lock files first so Docker layer cache is reused on code-only
# changes (i.e. the expensive uv sync step is skipped if lock files unchanged).
COPY pyproject.toml uv.lock ./

# --frozen: respect uv.lock exactly (no implicit updates)
# --no-cache: keep image lean; CI/CD layer caching is done at the Docker level
RUN uv sync --frozen --no-cache

# ── Application code ─────────────────────────────────────────────────────────
COPY app/ ./app/

# Alembic migration files — needed by the one-shot `migrate` service as well as
# any manual `docker compose exec backend uv run alembic ...` commands.
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Expose the uvicorn port
EXPOSE 8000

# Production startup — no --reload, single worker (asyncio is single-threaded
# so multiple workers would each hold their own event loop; scale horizontally
# by running more replicas instead of intra-process workers).
CMD ["uv", "run", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
