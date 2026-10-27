# Phase 6W-R2.2 — Database Recovery Evidence

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d  
**Gate:** G1

---

## Current State: BLOCKED

Production Supabase project `qvpdtnazhxbfifrjdfdf` remains paused.  
This artifact will be updated to PASS after owner resumes the project.

---

## Connectivity Audit (Current — Paused State)

| Layer | Target | Result | Evidence |
|-------|--------|--------|---------|
| DNS — pooler | `aws-1-ap-northeast-2.pooler.supabase.com` | **PASS** | Resolves → 43.202.154.182 |
| TCP — pooler | Port 6543 | **PASS** | Connection established |
| DNS — project | `qvpdtnazhxbfifrjdfdf.supabase.co` | **FAIL** | `[Errno 8] nodename nor servname provided, or not known` |
| HTTPS — project REST | `https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/` | **FAIL** | `SSL: UNEXPECTED_EOF_WHILE_READING` |
| asyncpg SELECT 1 | Transaction pooler | **NOT TESTED** | DNS failure prevents asyncpg connect |

**Classification:** `SUPABASE_PROJECT_PAUSED` — confirmed by:
1. Pooler infrastructure is reachable (TCP PASS) — network path is healthy
2. Project subdomain DNS fails — project tenant not serving
3. SSL EOF on HTTPS — server closes connection without TLS handshake
4. This matches documented Supabase free-tier auto-pause behavior

---

## Owner Action Required

```
1. Open: https://supabase.com/dashboard
2. Select project: qvpdtnazhxbfifrjdfdf
3. Click: "Resume project"
4. Wait: ~60 seconds
5. Verify (run from any terminal):
   curl -I https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/
   → Expected: HTTP/1.1 401 Unauthorized
   → NOT: SSL EOF or connection refused
```

---

## Post-Resume Verification Script

Run after owner confirms project is active:

```bash
python3 -c "
import asyncio, asyncpg, os

async def test_db():
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        print('ERROR: DATABASE_URL not set')
        return

    # Layer 1: DNS
    import socket
    host = 'qvpdtnazhxbfifrjdfdf.supabase.co'
    try:
        ip = socket.gethostbyname(host)
        print(f'DNS project: PASS  -> {ip}')
    except Exception as e:
        print(f'DNS project: FAIL  {e}')
        return

    # Layer 2: asyncpg
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(dsn, ssl='require', timeout=12),
            timeout=15
        )
        result = await conn.fetchval('SELECT 1')
        print(f'asyncpg SELECT 1: PASS  result={result}')
        
        # Layer 3: table presence
        tables = await conn.fetch(
            '''SELECT table_name FROM information_schema.tables
               WHERE table_schema = \$1
               AND table_name = ANY(\$2)
               ORDER BY table_name''',
            'public',
            ['alembic_version', 'chat_messages', 'chat_sessions',
             'company_v2_report_rag_chunks', 'company_v2_report_rag_documents',
             'report_documents', 'users']
        )
        print(f'Core tables: {len(tables)}/7 present')
        for t in tables:
            print(f'  ✓ {t[\"table_name\"]}')
        
        await conn.close()
    except Exception as e:
        print(f'asyncpg: FAIL  {e}')

asyncio.run(test_db())
"
```

Expected output:
```
DNS project: PASS  -> <IP>
asyncpg SELECT 1: PASS  result=1
Core tables: 7/7 present
  ✓ alembic_version
  ✓ chat_messages
  ✓ chat_sessions
  ✓ company_v2_report_rag_chunks
  ✓ company_v2_report_rag_documents
  ✓ report_documents
  ✓ users
```

---

## G1 Verdict

**BLOCKED** — awaiting owner action (Supabase resume).

*Update this file after successful asyncpg SELECT 1.*
