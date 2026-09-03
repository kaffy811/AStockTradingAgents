# Phase 6L — Deployment Guide (Free Mode)

## Prerequisites

| Component | Version | Notes |
|-----------|---------|-------|
| Python | ≥ 3.12 | |
| PostgreSQL | ≥ 15 | + pgvector extension |
| Redis | ≥ 7 | Recommended; fail-open if absent |
| uv | ≥ 0.4 | Dependency manager |
| Node.js | ≥ 20 | Frontend build |
| npm | ≥ 10 | |

---

## 1. Backend Startup

```bash
cd backend

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, SECRET_KEY, DEEPSEEK_API_KEY, REDIS_URL, CORS_ORIGINS

# Run database migrations
uv run alembic upgrade head

# Start server (single worker for development)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production (multi-worker)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 2. Frontend Build & Deploy

```bash
cd frontend

npm install
npm run build          # Output: dist/

# Type-check (optional):
npm run typecheck

# Preview locally:
npm run preview
```

Serve `dist/` with Nginx or any static file server.

---

## 3. PostgreSQL + pgvector Initialisation

```sql
-- Create extension (requires superuser or pg_extension_owner)
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify:
SELECT installed_version FROM pg_available_extensions WHERE name = 'vector';
```

Then run Alembic migrations:

```bash
uv run alembic upgrade head
```

All migrations are idempotent and safe to re-run.

---

## 4. Redis

```bash
# Start Redis (Docker):
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Or via system package:
brew install redis && brew services start redis   # macOS
sudo apt install redis-server && sudo systemctl start redis  # Ubuntu
```

Set `REDIS_URL=redis://localhost:6379` in `.env`.

Redis is used for:
- Report-chat answer cache (TTL 1800s)
- Rate limiting (INCR+EXPIRE per minute/hour)
- Session memory (LIST, TTL 3600s)
- Analysis run registry (`ANALYSIS_RUN_REGISTRY=redis`)

All features fail-open if Redis is unavailable.

---

## 5. Free Data Sources (BaoStock + AkShare)

### Installation

```bash
# These are already in pyproject.toml:
uv sync
```

Or manually:

```bash
uv pip install baostock akshare
```

### Verification

```bash
uv run python scripts/check_data_sources.py
```

Expected output:
```
[✓] baostock: available  0.8.9
[✓] akshare: available   1.x.y
[✓] baostock_login: ok
[✓] akshare_callable: ok
[✓] domain_static.cninfo.com.cn: resolvable
```

### Caveats

- BaoStock requires a one-time registration at baostock.com (free)
- AkShare is scraping-based; field names may change; pin version in `pyproject.toml`
- Data freshness is typically T+1 (previous trading day)
- Metric coverage is narrower than Tushare Pro

---

## 6. PDF Storage

Report PDFs are downloaded to the path configured in `REPORT_PDF_STORAGE_PATH`
(default: `./data/report_pdfs/`).

```bash
mkdir -p data/report_pdfs
```

Ensure the process has write permission. In Docker, mount as a volume:

```yaml
volumes:
  - ./data/report_pdfs:/app/data/report_pdfs
```

---

## 7. Local Embedding Model

Required when `REPORT_EMBEDDING_PROVIDER=local`.

```bash
# Model is downloaded on first use (~100 MB):
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

# For air-gapped environments, pre-download:
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"
# Then set REPORT_EMBEDDING_MODEL=/path/to/cached/model
```

Dimension must match the schema: `REPORT_EMBEDDING_DIM=384`.

---

## 8. Nginx Configuration (CORS + SSE)

```nginx
server {
    listen 443 ssl;
    server_name your-app.example.com;

    # Frontend static files
    location / {
        root /var/www/tradingagents/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # SSE streaming (analysis reports)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        chunked_transfer_encoding on;
    }
}
```

Set `CORS_ORIGINS=["https://your-app.example.com"]` in `.env`.

---

## 9. Health Check (Load Balancer)

Configure your load balancer or container orchestrator to poll:

```
GET /api/v1/health
```

Expected response (HTTP 200):
```json
{"status": "ok", "db_status": "ok", ...}
```

For deep readiness check (deploy gate, monitoring):
```
GET /api/v1/health/deep
```

---

## 10. Cron Jobs

Recommended cron schedule:

```cron
# Daily smoke check at 07:00
0 7 * * * cd /app/backend && uv run python scripts/free_mode_smoke_check.py --json >> /var/log/smoke.log 2>&1

# Weekly report index rebuild at 02:00 Sunday
0 2 * * 0 cd /app/backend && uv run python scripts/rebuild_report_index.py --limit 50 >> /var/log/rebuild.log 2>&1

# Weekly cache cleanup at 03:00 Sunday
0 3 * * 0 cd /app/backend && uv run python scripts/cleanup_report_cache.py >> /var/log/cleanup.log 2>&1

# Monthly data source check
0 6 1 * * cd /app/backend && uv run python scripts/check_data_sources.py --json >> /var/log/datasources.log 2>&1
```

---

## 11. Backup Strategy

| Data | Backup method | Frequency |
|------|---------------|-----------|
| PostgreSQL | `pg_dump tradingagents | gzip > backup.sql.gz` | Daily |
| `data/report_pdfs/` | rsync to offsite | Daily |
| Redis | `BGSAVE` or `redis-cli save` | Not critical (caches are regenerable) |

Redis data (cache/rate-limit/memory) is all ephemeral and regenerates automatically.
The only critical data is PostgreSQL (users, watchlists, analysis runs, report documents, report chunks).

---

## 12. Rollback Strategy

1. **Code rollback**: `git revert` + redeploy + `uv run alembic downgrade -1`
2. **Alembic downgrade order** (latest first):
   - Phase 6L: no new migrations
   - Phase 6K: no new migrations
   - Phase 6G-1: `g5h6i7j8k9l0` (vector dim change — requires re-embed)
   - Phase 6F: `f4a5b6c7d8e9` (report_chunks table)
   - Phase 6E: `e3f4a5b6c7d8` (report_documents table)

3. **Cache invalidation**: bump `REPORT_CHAT_CACHE_VERSION=v2` to invalidate all existing cache entries without Redis FLUSHDB.

---

## 13. Common Issues

### `pgvector` not installed

```
DETAIL: extension "vector" is not available
HINT: Run "CREATE EXTENSION vector;" as superuser.
```

Install pgvector: https://github.com/pgvector/pgvector

### BaoStock login fails

```
[baostock] error_code=10002 error_msg=用户名或密码错误
```

Re-register at baostock.com. The free account registration is instant.

### AkShare `AttributeError`

```python
AttributeError: module 'akshare' has no attribute 'stock_zh_a_spot_em'
```

AkShare changed interface names. Pin the last known-good version or update callers.

### Report chat returns `REPORT_RAG_NOT_READY`

No chunks are indexed for this stock. Run:
```bash
uv run python scripts/rebuild_report_index.py --symbol 600519.SH
```

If no reports are found, run discovery + download first:
```
POST /api/v1/stocks/CN/600519/reports/discover
POST /api/v1/stocks/CN/600519/reports/discover/latest  (download PDF)
POST /api/v1/stocks/CN/600519/reports/{id}/chunk
POST /api/v1/stocks/CN/600519/reports/{id}/embed
```

### Redis connection refused

Set `REDIS_URL=redis://localhost:6379` or unset to disable Redis features.
All cache/rate-limit/memory features fail-open — the service continues to operate.
