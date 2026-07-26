"""
app/routers/report_rag.py — 财报 RAG API（Phase 6F）

端点：
  POST /api/v1/stocks/{market}/{code}/reports/{report_id}/chunk
  POST /api/v1/stocks/{market}/{code}/reports/{report_id}/embed
  POST /api/v1/stocks/{market}/{code}/reports/{report_id}/rag/build
  POST /api/v1/stocks/{market}/{code}/reports/rag/query
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.report_chunk_service import report_chunk_service
from app.services.report_embedding_service import report_embedding_service
from app.services.report_rag_service import report_rag_service
from app.datasource.tushare_client import _to_ts_code

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/stocks",
    tags=["report-rag"],
)


class RagQueryRequest(BaseModel):
    query: str
    report_types: list[str] | None = None
    years: list[int] | None = None
    top_k: int = 6


# ── POST .../reports/{report_id}/chunk ────────────────────────────────────────

@router.post(
    "/{market}/{code}/reports/{report_id}/chunk",
    summary="将年报 PDF 文本切分为 chunks",
)
async def chunk_report(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """切分 text_excerpt 或本地 PDF 全文为 800-1200 字 chunks。幂等操作。"""
    result = await report_chunk_service.chunk_report(report_id, db)
    return JSONResponse(result)


# ── POST .../reports/{report_id}/embed ────────────────────────────────────────

@router.post(
    "/{market}/{code}/reports/{report_id}/embed",
    summary="为 chunks 生成向量 embedding",
)
async def embed_report(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """使用配置的 embedding provider（默认: mock，0成本）为 report_chunks 生成向量。"""
    result = await report_embedding_service.embed_report(report_id, db)
    return JSONResponse(result)


# ── POST .../reports/{report_id}/rag/build ────────────────────────────────────

@router.post(
    "/{market}/{code}/reports/{report_id}/rag/build",
    summary="一键切分 + 向量化（chunk + embed）",
)
async def build_report_rag(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """串行执行 chunk → embed。幂等：重复调用不重复插入。"""
    chunk_result = await report_chunk_service.chunk_report(report_id, db)
    if chunk_result["status"] not in ("chunked", "ok"):
        return JSONResponse({
            "status": "failed",
            "report_id": report_id,
            "chunk_result": chunk_result,
            "embed_result": None,
            "reason": chunk_result.get("reason", "chunk failed"),
        })

    embed_result = await report_embedding_service.embed_report(report_id, db)

    return JSONResponse({
        "status": embed_result["status"],
        "report_id": report_id,
        "chunk_result": chunk_result,
        "embed_result": embed_result,
        "reason": embed_result.get("reason", "ok"),
    })


# ── POST .../reports/rag/query ────────────────────────────────────────────────

@router.post(
    "/{market}/{code}/reports/rag/query",
    summary="语义检索年报相关片段",
)
async def rag_query(
    body: RagQueryRequest,
    market: str = Path(...),
    code: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    对该股票已入库的年报 chunks 进行语义搜索。

    安全约束：
    - 只检索 ts_code 归属于该股票的 chunks
    - 不跨股票泄露
    - content 截断至 1500 字
    - 不暴露 local_path
    """
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=422, detail="query 不能为空")

    ts_code = _to_ts_code(market, code)
    result = await report_rag_service.query(
        ts_code=ts_code,
        query_text=body.query,
        db=db,
        report_types=body.report_types,
        years=body.years,
        top_k=body.top_k,
    )

    # Enrich with pdf_proxy_url (not local_path)
    for chunk in result.get("chunks", []):
        rid = chunk.get("report_id")
        if rid:
            chunk["pdf_url"] = f"/api/v1/stocks/{market}/{code}/reports/{rid}/pdf"

    result["disclaimer"] = (
        "本内容基于已接入的公开数据和可用财报片段生成，"
        "仅供信息参考，不构成投资建议。"
    )
    return JSONResponse(result)
