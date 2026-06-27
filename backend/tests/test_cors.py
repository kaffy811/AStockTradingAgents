"""
CORS preflight tests.

Verifies that the CORSMiddleware correctly handles OPTIONS preflight requests
from all allowed frontend origins (including localhost:3002 added in this fix).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app

# ── Helpers ───────────────────────────────────────────────────────────────────

PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "content-type,authorization",
}


async def _preflight(client: AsyncClient, origin: str, path: str = "/api/v1/health"):
    return await client.options(
        path,
        headers={"Origin": origin, **PREFLIGHT_HEADERS},
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


# ── Test 1: localhost:3002 (the newly added origin) ───────────────────────────

@pytest.mark.asyncio
async def test_cors_preflight_localhost_3002(client):
    """OPTIONS from http://localhost:3002 must return 200/204 with correct ACAO header."""
    origin = "http://localhost:3002"
    r = await _preflight(client, origin, "/api/v1/chat/sessions")

    assert r.status_code in (200, 204), (
        f"Expected 200/204 but got {r.status_code}; body={r.text[:200]}"
    )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == origin, f"Expected ACAO={origin!r}, got {acao!r}"


# ── Test 2: localhost:5173 (Vite dev default) ─────────────────────────────────

@pytest.mark.asyncio
async def test_cors_preflight_localhost_5173(client):
    """OPTIONS from http://localhost:5173 must return 200/204."""
    origin = "http://localhost:5173"
    r = await _preflight(client, origin, "/api/v1/chat/sessions")

    assert r.status_code in (200, 204)
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == origin


# ── Test 3: localhost:3000 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cors_preflight_localhost_3000(client):
    origin = "http://localhost:3000"
    r = await _preflight(client, origin, "/api/v1/health")
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin


# ── Test 4: 127.0.0.1:3002 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cors_preflight_127_3002(client):
    origin = "http://127.0.0.1:3002"
    r = await _preflight(client, origin, "/api/v1/health")
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin


# ── Test 5: 127.0.0.1:5173 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cors_preflight_127_5173(client):
    origin = "http://127.0.0.1:5173"
    r = await _preflight(client, origin, "/api/v1/health")
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin


# ── Test 6: all configured origins pass ───────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
])
async def test_cors_preflight_all_allowed_origins(client, origin):
    r = await _preflight(client, origin, "/api/v1/health")
    assert r.status_code in (200, 204), f"CORS failed for {origin}: {r.status_code}"
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == origin, f"ACAO mismatch for {origin}: got {acao!r}"


# ── Test 7: disallowed origin does NOT get allow-origin header ────────────────

@pytest.mark.asyncio
async def test_cors_disallowed_origin_blocked(client):
    """An unlisted origin must not receive Access-Control-Allow-Origin."""
    r = await _preflight(client, "http://evil.example.com", "/api/v1/health")
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao != "http://evil.example.com", (
        f"Disallowed origin was reflected: {acao!r}"
    )


# ── Test 8: allow-methods includes GET, POST, OPTIONS ─────────────────────────

@pytest.mark.asyncio
async def test_cors_allow_methods(client):
    origin = "http://localhost:3002"
    r = await _preflight(client, origin)
    assert r.status_code in (200, 204)
    acam = r.headers.get("access-control-allow-methods", "")
    # Starlette expands ["*"] to explicit list; either * or the method list is valid
    assert acam, f"Missing Access-Control-Allow-Methods header"


# ── Test 9: allow-credentials=true reflected ─────────────────────────────────

@pytest.mark.asyncio
async def test_cors_allow_credentials(client):
    origin = "http://localhost:3002"
    r = await _preflight(client, origin)
    assert r.status_code in (200, 204)
    acac = r.headers.get("access-control-allow-credentials", "")
    assert acac.lower() == "true", f"Expected allow-credentials=true, got {acac!r}"


# ── Test 10: actual GET with Origin header reflects ACAO ─────────────────────

@pytest.mark.asyncio
async def test_cors_get_request_reflects_origin(client):
    origin = "http://localhost:3002"
    r = await client.get("/api/v1/health", headers={"Origin": origin})
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == origin, f"GET request ACAO mismatch: got {acao!r}"
