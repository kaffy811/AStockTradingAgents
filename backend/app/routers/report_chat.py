"""
app/routers/report_chat.py — 问财报 Chat Copilot API Router

Endpoint:
  POST /api/v1/stock/{code}/report-chat

Path param `code` formats supported:
  600519        → CN, 600519
  600519.SH     → CN, 600519
  000001.SZ     → CN, 000001
  688981.SH     → CN, 688981
  838030.BJ     → CN, 838030
  00700.HK      → HK, 00700   (graceful 200 + partial error)
  AAPL          → US, AAPL    (graceful 200 + partial error)

Only CN market is supported; HK/US return HTTP 200 with partial=True + error.

Phase 6K additions:
  - Request: force_refresh, session_id, use_memory fields
  - Response headers: X-RateLimit-Limit-Minute, X-RateLimit-Remaining-Minute,
                      X-RateLimit-Limit-Hour, X-RateLimit-Remaining-Hour
  - HTTP 429 when rate limit exceeded (with Retry-After header)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.core.database import get_db
from app.core.error_codes import (
    REPORT_CHAT_RATE_LIMITED,
    REPORT_RAG_NOT_READY,
    INTERNAL_ERROR,
)

log = logging.getLogger(__name__)

report_chat_router = APIRouter(
    prefix="/api/v1",
    tags=["report-chat"],
)

# ── Constants ─────────────────────────────────────────────────────────────────

_DISCLAIMER_HEADER = (
    "For informational purposes only. "
    "Not investment advice. Invest at your own risk."
)

# Canonical disclaimer for report-chat context (Phase 6L)
_CANONICAL_DISCLAIMER = (
    "本内容基于已接入的公开数据和可用财报片段生成，"
    "仅供信息参考，不构成投资建议。"
)

_MAX_QUESTION_LEN = 500
_MAX_TOP_K = 10

# 当财报索引尚未建立时，引导用户执行的操作建议
_ACTION_SUGGESTIONS_NO_RAG = [
    {"action": "discover_reports", "label": "自动查找财报"},
    {"action": "build_index",      "label": "生成索引（需先下载财报）"},
]


# ── Request / Response schemas ────────────────────────────────────────────────

class ReportChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LEN)
    report_types: Optional[list[str]] = Field(
        default=None,
        description="Filter by report types, e.g. ['annual', 'semi-annual']",
    )
    years: Optional[list[int]] = Field(
        default=None,
        description="Filter by report year(s), e.g. [2022, 2023]",
    )
    top_k: int = Field(
        default=6,
        ge=1,
        description="Number of RAG chunks to retrieve (1–10, capped at 10)",
    )
    # Phase 6K fields
    force_refresh: bool = Field(
        default=False,
        description="Bypass Redis cache and force a fresh LLM call",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Client session ID for conversation memory (same stock only)",
    )
    use_memory: bool = Field(
        default=True,
        description="Whether to inject previous turns from session memory into the prompt",
    )

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v[:_MAX_QUESTION_LEN]

    @field_validator("top_k")
    @classmethod
    def cap_top_k(cls, v: int) -> int:
        return min(v, _MAX_TOP_K)

    @field_validator("session_id")
    @classmethod
    def sanitize_session_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        # Allow only safe ASCII for Redis key safety
        import re
        if not re.match(r"^[a-zA-Z0-9_\-:\.]{1,128}$", v):
            return None
        return v


# ── Code parsing ──────────────────────────────────────────────────────────────

def _parse_code(code: str) -> tuple[str, str]:
    """
    Parse a stock code string into (market, symbol).

    Supports:
      "600519"      → ("CN", "600519")
      "600519.SH"   → ("CN", "600519")
      "000001.SZ"   → ("CN", "000001")
      "838030.BJ"   → ("CN", "838030")
      "00700.HK"    → ("HK", "00700")
      "700.HK"      → ("HK", "00700")
      "AAPL"        → ("US", "AAPL")
    """
    code = code.strip()

    if "." in code:
        parts = code.rsplit(".", 1)
        symbol_part = parts[0]
        suffix = parts[1].upper()

        if suffix in ("SH", "SZ", "BJ"):
            return "CN", symbol_part
        elif suffix == "HK":
            # Ensure 5-digit zero-padded
            digits = symbol_part.lstrip("0") or "0"
            return "HK", digits.zfill(5)
        else:
            return "US", symbol_part
    else:
        if code.isdigit():
            if len(code) == 6:
                return "CN", code
            elif len(code) <= 5:
                return "HK", code.zfill(5)
        return "US", code


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request headers or connection."""
    # Check forwarded headers first (behind proxy/nginx)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


def _disclaimer_response(
    data: dict,
    status_code: int = 200,
    extra_headers: dict | None = None,
) -> JSONResponse:
    headers = {"X-Data-Disclaimer": _DISCLAIMER_HEADER}
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers=headers,
    )


def _rate_limit_headers(rl_result) -> dict:
    """Build rate-limit HTTP response headers from a RateLimitResult."""
    return {
        "X-RateLimit-Limit-Minute":     str(rl_result.limit_minute),
        "X-RateLimit-Remaining-Minute": str(rl_result.remaining_minute),
        "X-RateLimit-Limit-Hour":       str(rl_result.limit_hour),
        "X-RateLimit-Remaining-Hour":   str(rl_result.remaining_hour),
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────

@report_chat_router.post(
    "/stock/{code}/report-chat",
    summary="问财报 — 基于公开财报的 Q&A",
    description=(
        "基于已接入的公开财报片段，使用 AI 回答关于指定股票的财务问题。\n\n"
        "- 仅支持 A 股（CN 市场）\n"
        "- 不提供投资建议或目标价\n"
        "- 答案仅基于已接入的财报片段，数据覆盖以系统实际接入情况为准\n"
        "- 支持 Redis 缓存（force_refresh=true 绕过缓存）\n"
        "- 支持会话记忆（传 session_id 开启同股票追问）"
    ),
    response_description="结构化问答结果，含引用片段、置信度、合规审核摘要、缓存元信息、记忆元信息",
)
async def report_chat(
    code: str,
    body: ReportChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    POST /api/v1/stock/{code}/report-chat

    Never returns HTTP 500 — all errors are surfaced as partial=True in the JSON body.
    HTTP 429 is returned only when rate limit is exceeded.
    """
    from app.services.rate_limit_service import check_rate_limit, rate_limit_meta_dict

    request_id = str(uuid.uuid4())[:8]

    # ── 1. Parse stock code ───────────────────────────────────────────────────
    try:
        market, symbol = _parse_code(code)
    except Exception as e:
        log.warning("report_chat parse_error request_id=%s code=%r: %s", request_id, code, e)
        return _disclaimer_response({
            "answer": f"无法解析股票代码 '{code}'，请使用标准格式（如 600519、600519.SH）。",
            "source_chunks": [],
            "review_audit": {},
            "rag_status": "unavailable",
            "confidence": "low",
            "evidence_used": [],
            "data_limitations": [f"代码解析失败: {e}"],
            "disclaimer": _CANONICAL_DISCLAIMER,
            "error_code": INTERNAL_ERROR,
            "errors": [f"代码解析失败"],
            "partial": True,
            "request_id": request_id,
        })

    # ── 2. Rate limiting ──────────────────────────────────────────────────────
    client_ip = _get_client_ip(request)
    rl_result = await check_rate_limit(
        user_id=None,        # no auth in this router; extend when auth is wired
        session_id=body.session_id,
        ip=client_ip,
    )
    rl_headers = _rate_limit_headers(rl_result)

    if not rl_result.allowed:
        log.info("report_chat rate_limited request_id=%s code=%s ip=%s", request_id, code, client_ip)
        rate_limit_body = {
            "answer": "请求过于频繁，请稍后再试。",
            "source_chunks": [],
            "review_audit": {},
            "rag_status": "unavailable",
            "confidence": "high",
            "evidence_used": [],
            "data_limitations": ["速率限制：请求过于频繁"],
            "disclaimer": _CANONICAL_DISCLAIMER,
            "error_code": REPORT_CHAT_RATE_LIMITED,
            "errors": ["rate_limit_exceeded"],
            "partial": True,
            "rate_limit_meta": rate_limit_meta_dict(rl_result),
            "request_id": request_id,
        }
        extra = dict(rl_headers)
        if rl_result.retry_after_seconds:
            extra["Retry-After"] = str(rl_result.retry_after_seconds)
        return _disclaimer_response(rate_limit_body, status_code=429, extra_headers=extra)

    # ── 3. Market gate — only CN supported ───────────────────────────────────
    if market != "CN":
        market_label = {"HK": "港股", "US": "美股"}.get(market, market)
        return _disclaimer_response(
            {
                "answer": (
                    f"当前问财报功能仅支持 A 股（CN 市场）。"
                    f"您输入的代码 '{code}' 被识别为{market_label}，暂不支持。"
                ),
                "source_chunks": [],
                "review_audit": {},
                "rag_status": "unavailable",
                "confidence": "high",
                "evidence_used": [],
                "data_limitations": [f"不支持市场: {market}（仅支持 CN）"],
                "disclaimer": _CANONICAL_DISCLAIMER,
                "errors": [f"Unsupported market: {market}"],
                "partial": True,
                "rate_limit_meta": rate_limit_meta_dict(rl_result),
            },
            extra_headers=rl_headers,
        )

    # ── 4. Delegate to ReportChatCopilotAgent ─────────────────────────────────
    try:
        from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
        result = await ReportChatCopilotAgent().chat(
            market=market,
            symbol=symbol,
            question=body.question,
            db=db,
            report_types=body.report_types,
            years=body.years,
            top_k=body.top_k,
            force_refresh=body.force_refresh,
            session_id=body.session_id,
            use_memory=body.use_memory,
        )
    except Exception as e:
        log.error("report_chat unhandled_error request_id=%s code=%s: %s", request_id, code, type(e).__name__, exc_info=True)
        result = {
            "answer": "服务暂时不可用，请稍后重试。",
            "source_chunks": [],
            "review_audit": {},
            "rag_status": "unavailable",
            "confidence": "low",
            "evidence_used": [],
            "data_limitations": ["服务暂时不可用"],
            "disclaimer": _CANONICAL_DISCLAIMER,
            "error_code": INTERNAL_ERROR,
            "errors": ["service_unavailable"],
            "partial": True,
            "request_id": request_id,
        }

    # ── 4a. Inject REPORT_RAG_NOT_READY error code when no index exists ──────
    rag_status = result.get("rag_status", "")
    source_chunks = result.get("source_chunks") or []
    if rag_status == "unavailable" and not source_chunks and "error_code" not in result:
        result["error_code"] = REPORT_RAG_NOT_READY
        result["answer"] = (
            "当前尚未接入可检索的财报索引。你可以先在'年报文件'中点击'自动查找财报'，"
            "找到年报后执行下载和索引，再进行问财报。"
        )
        result["action_suggestions"] = _ACTION_SUGGESTIONS_NO_RAG

    # Inject rate_limit_meta and request_id into every response
    result["rate_limit_meta"] = rate_limit_meta_dict(rl_result)
    result.setdefault("request_id", request_id)
    result.setdefault("disclaimer", _CANONICAL_DISCLAIMER)

    log.info(
        "report_chat completed request_id=%s code=%s rag_status=%s partial=%s cache_hit=%s",
        request_id, code,
        result.get("rag_status", "unknown"),
        result.get("partial", False),
        result.get("cache_meta", {}).get("hit", False),
    )

    return _disclaimer_response(result, extra_headers=rl_headers)
