"""
tests/fundamental/test_phase6n8a_auth_error_classification.py

Phase 6N-8A: Auth 401 Misclassification Fix & Protected API Token Propagation

Covers:
  A. Protected routes without token → HTTP 401 + error_code=AUTH_REQUIRED:
  T01  GET /api/v1/watchlist/            → 401 AUTH_REQUIRED
  T02  GET /api/v1/reports/              → 401 AUTH_REQUIRED
  T03  GET /api/v1/stocks/CN/601686/quote → 401 AUTH_REQUIRED
  T04  GET /api/v1/stocks/search         → 401 AUTH_REQUIRED
  T05  bogus Bearer token                → 401 AUTH_REQUIRED (Invalid or expired token)
  T06  401 payload keeps `detail` (backward compat) + adds `message`

  B. Exception handler classification:
  T07  403 "Not authenticated" → error_code=AUTH_REQUIRED（HTTPBearer 缺 header 语义）
  T08  403 other detail        → error_code=FORBIDDEN
  T09  dict detail passes through unchanged (router-provided structured payload)

  C. Provider errors carry DATA_SOURCE_* — never masquerade as auth:
  T10  err_envelope(error_code=...) serialises error_code
  T11  err_envelope() without error_code → key absent (legacy shape preserved)
  T12  free mode: both providers raise network errors → DATA_SOURCE_UNAVAILABLE
  T13  free mode: providers not implemented / empty → DATA_SOURCE_EMPTY
  T14  free-mode fallback error_code is never AUTH_REQUIRED
  T15  _is_network_error classification (timeout/connection vs ValueError)

  D. Public fundamentals endpoints do not require auth (provider errors ≠ 401):
  T16  fundamentals compat routes have no get_current_user dependency
  T17  error_codes module exposes AUTH_REQUIRED / FORBIDDEN / DATA_SOURCE_EMPTY

  E. Safety:
  T18  6N-8A touched files contain no investment advice wording
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.aggregator.envelope import err_envelope
from app.core import error_codes as ec
from app.main import app

_BACKEND = Path(__file__).resolve().parents[2]

client = TestClient(app, raise_server_exceptions=False)

PROTECTED_ROUTES = [
    "/api/v1/watchlist/",
    "/api/v1/reports/?limit=5&offset=0",
    "/api/v1/stocks/CN/601686/quote",
    "/api/v1/stocks/search?market=CN&q=601686&limit=3",
]


# ── A. Protected routes without token ────────────────────────────────────────

@pytest.mark.parametrize("path", PROTECTED_ROUTES)
def test_t01_t04_protected_route_returns_auth_required(path):
    res = client.get(path)
    assert res.status_code == 401, f"{path} → {res.status_code}"
    body = res.json()
    assert body.get("error_code") == ec.AUTH_REQUIRED, body
    # 绝不能出现 provider 归因
    assert "BaoStock" not in str(body)
    assert "AkShare" not in str(body)


def test_t05_bogus_token_returns_auth_required():
    res = client.get("/api/v1/watchlist/", headers={"Authorization": "Bearer bogus"})
    assert res.status_code == 401
    assert res.json().get("error_code") == ec.AUTH_REQUIRED


def test_t06_401_payload_backward_compatible():
    res = client.get("/api/v1/watchlist/")
    body = res.json()
    assert "detail" in body           # 旧前端读取 detail
    assert body.get("message") == "Authentication required"


# ── B. Exception handler classification ──────────────────────────────────────

def _run_handler(exc):
    import asyncio
    from app.main import _http_exception_handler
    return asyncio.run(_http_exception_handler(None, exc))


def test_t07_403_not_authenticated_maps_to_auth_required():
    from starlette.exceptions import HTTPException
    resp = _run_handler(HTTPException(status_code=403, detail="Not authenticated"))
    import json
    body = json.loads(resp.body)
    assert body["error_code"] == ec.AUTH_REQUIRED


def test_t08_403_other_maps_to_forbidden():
    from starlette.exceptions import HTTPException
    resp = _run_handler(HTTPException(status_code=403, detail="admin only"))
    import json
    body = json.loads(resp.body)
    assert body["error_code"] == ec.FORBIDDEN


def test_t09_dict_detail_passthrough():
    from starlette.exceptions import HTTPException
    detail = {"error_code": "REPORT_CHAT_RATE_LIMITED", "message": "slow down"}
    resp = _run_handler(HTTPException(status_code=429, detail=detail))
    import json
    body = json.loads(resp.body)
    assert body == detail


# ── C. Provider errors carry DATA_SOURCE_* ───────────────────────────────────

def test_t10_err_envelope_with_error_code():
    env = err_envelope("no data", error_code=ec.DATA_SOURCE_EMPTY)
    assert env["ok"] is False
    assert env["error_code"] == ec.DATA_SOURCE_EMPTY


def test_t11_err_envelope_legacy_shape():
    env = err_envelope("no data")
    assert "error_code" not in env


class _DummyTool:
    """Minimal BaseFundamentalTool stand-in for _fetch_free_mode."""
    module_key = "dummy"

    def __init__(self, bs_exc=None, ak_exc=None):
        self._bs_exc = bs_exc
        self._ak_exc = ak_exc

    async def fetch_baostock(self, market, symbol):
        raise self._bs_exc or NotImplementedError()

    async def fetch_akshare(self, market, symbol):
        raise self._ak_exc or NotImplementedError()


def _make_tool(bs_exc=None, ak_exc=None):
    from app.tools.fundamental.base import BaseFundamentalTool
    tool = _DummyTool(bs_exc, ak_exc)
    tool._fetch_free_mode = BaseFundamentalTool._fetch_free_mode.__get__(tool)
    tool._is_network_error = BaseFundamentalTool._is_network_error
    return tool


async def _run_free_mode(tool, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "enable_baostock", True, raising=False)
    monkeypatch.setattr(settings, "enable_akshare", True, raising=False)
    return await tool._fetch_free_mode("CN", "601686")


async def test_t12_network_failure_maps_to_unavailable(monkeypatch):
    tool = _make_tool(
        bs_exc=ConnectionError("connection refused"),
        ak_exc=TimeoutError("read timed out"),
    )
    env = await _run_free_mode(tool, monkeypatch)
    assert env["ok"] is False
    assert env["error_code"] == ec.DATA_SOURCE_UNAVAILABLE


async def test_t13_empty_maps_to_data_source_empty(monkeypatch):
    tool = _make_tool()   # both NotImplementedError
    env = await _run_free_mode(tool, monkeypatch)
    assert env["ok"] is False
    assert env["error_code"] == ec.DATA_SOURCE_EMPTY


async def test_t14_free_mode_never_auth_code(monkeypatch):
    for tool in (_make_tool(), _make_tool(bs_exc=ValueError("boom"))):
        env = await _run_free_mode(tool, monkeypatch)
        assert env["error_code"] != ec.AUTH_REQUIRED
        assert env["error_code"] in (ec.DATA_SOURCE_EMPTY, ec.DATA_SOURCE_UNAVAILABLE)


def test_t15_is_network_error_classification():
    from app.tools.fundamental.base import BaseFundamentalTool
    f = BaseFundamentalTool._is_network_error
    assert f(TimeoutError("timed out")) is True
    assert f(ConnectionError("proxy refused")) is True
    assert f(ValueError("bad column")) is False


# ── D. Public fundamentals endpoints ─────────────────────────────────────────

def test_t16_fundamentals_routes_public():
    """公开基本面路由不挂 get_current_user——provider 错误不可能变成 401。"""
    for fname in ("fundamentals.py", "fundamentals_compat.py"):
        text = (_BACKEND / "app" / "routers" / fname).read_text(encoding="utf-8")
        assert "Depends(get_current_user)" not in text, f"{fname} unexpectedly protected"


def test_t17_error_codes_present():
    assert ec.AUTH_REQUIRED == "AUTH_REQUIRED"
    assert ec.FORBIDDEN == "FORBIDDEN"
    assert ec.DATA_SOURCE_EMPTY == "DATA_SOURCE_EMPTY"
    assert ec.DATA_SOURCE_UNAVAILABLE == "DATA_SOURCE_UNAVAILABLE"


# ── E. Safety ─────────────────────────────────────────────────────────────────

def test_t18_no_investment_advice_wording():
    touched = [
        _BACKEND / "app" / "main.py",
        _BACKEND / "app" / "core" / "error_codes.py",
        _BACKEND / "app" / "aggregator" / "envelope.py",
        _BACKEND / "app" / "tools" / "fundamental" / "base.py",
    ]
    banned = ("买入建议", "卖出建议", "目标价", "建议买入", "建议卖出",
              "target_price", "analyst_rating", "institutional_consensus")
    for f in touched:
        text = f.read_text(encoding="utf-8")
        for term in banned:
            assert term not in text, f"{f.name} contains banned wording: {term}"
