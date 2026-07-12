"""
app/routers/report_discovery.py — 报告自动发现 API（Phase 6D）

端点：
  POST /api/v1/stocks/{market}/{code}/reports/discover
  POST /api/v1/stocks/{market}/{code}/reports/discover/latest
  GET  /api/v1/stocks/{market}/{code}/reports/{report_id}/pdf

安全：
  - PDF 路由仅允许已入库的 report_id
  - 不允许任意 open redirect
  - 不暴露 local_path
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.report_discovery_agent import report_discovery_agent, HIGH_CONFIDENCE_THRESHOLD
from app.core.database import get_db
from app.datasource.tushare_client import _to_ts_code
from app.services.report_document_service import report_document_service
from app.services.report_pdf_download_service import report_pdf_download_service
from app.services.report_text_extract_service import report_text_extract_service

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/stocks",
    tags=["report-discovery"],
)

_DISCLAIMER = (
    "本内容基于已接入的公开数据和可用财报片段生成，"
    "仅供信息参考，不构成投资建议。"
    "报告来自公开披露平台（CNINFO/SSE/SZSE）。"
)

_ALLOWED_DOMAINS = [
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "cninfo.com.cn",
    "disc.szse.cn",
    "www.szse.cn",
    "szse.cn",
    "www.sse.com.cn",
    "sse.com.cn",
    "query.sse.com.cn",
]


class DiscoverRequest(BaseModel):
    report_type: str = "annual"   # annual/semi/q1/q3
    report_year: int = 2024
    company_name: str = ""
    auto_insert: bool = True


# ── POST /api/v1/stocks/{market}/{code}/reports/discover ──────────────────────

@router.post(
    "/{market}/{code}/reports/discover",
    summary="自动发现定期报告 PDF（按报告类型+年份）",
)
async def discover_reports(
    body: DiscoverRequest,
    market: str = Path(..., description="市场代码：CN / HK / US"),
    code: str = Path(..., description="股票代码，如 600519"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    调用 CNINFO/SSE/SZSE 搜索指定报告，自动入库 confidence >= 0.75 的候选。

    - auto_insert=true: 置信度 >= 0.75 的候选自动写入 report_documents
    - auto_insert=false: 仅返回候选，不写入
    - 找不到时返回 partial=true + reason，不报 5xx
    """
    market_upper = market.upper()
    if market_upper != "CN":
        return JSONResponse({
            "candidates": [], "inserted": [], "skipped": [], "errors": [],
            "partial": True, "reason": "报告发现功能当前仅支持 A 股（CN 市场）",
            "disclaimer": _DISCLAIMER,
        })

    try:
        result = await report_discovery_agent.discover(
            stock_code=code,
            company_name=body.company_name,
            report_type=body.report_type,
            report_year=body.report_year,
        )
    except Exception as e:
        log.error("discover_reports failed [%s]: %s", code, e)
        return JSONResponse({
            "candidates": [], "inserted": [], "skipped": [],
            "errors": [f"搜索失败: {e}"],
            "partial": True, "reason": str(e),
            "disclaimer": _DISCLAIMER,
        })

    candidates = result.get("candidates") or []
    inserted = []
    skipped = []

    if body.auto_insert:
        for candidate in candidates:
            upsert_result = await report_document_service.upsert_discovered_report(candidate, db)
            if upsert_result["status"] == "inserted":
                inserted.append({**candidate, "report_id": upsert_result["report_id"]})
            else:
                skipped.append({**candidate, "skip_reason": upsert_result["reason"]})
    else:
        skipped = candidates

    return JSONResponse({
        "candidates":       candidates,
        "inserted":         inserted,
        "skipped":          skipped,
        "errors":           result.get("errors") or [],
        "partial":          result.get("partial", False),
        "sources_searched": result.get("sources_searched") or [],
        "total_found":      result.get("total_found", 0),
        "disclaimer":       _DISCLAIMER,
    })


# ── POST /api/v1/stocks/{market}/{code}/reports/discover/latest ───────────────

@router.post(
    "/{market}/{code}/reports/discover/latest",
    summary="一键查找最新年报/半年报/季报（每类最多 1 条高置信度）",
)
async def discover_latest_reports(
    market: str = Path(..., description="市场代码：CN"),
    code: str = Path(..., description="股票代码"),
    report_year: int = Query(default=2024, description="报告年份"),
    company_name: str = Query(default="", description="公司简称"),
    try_year_fallback: bool = Query(
        default=True,
        description="若指定年份无报告，自动尝试前两个年份（report_year-1, report_year-2）",
    ),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    并发搜索最近年度报告/半年报/一季报/三季报，自动插入高置信度结果。
    每种 report_type 最多插入 1 条最高置信度报告。

    新增：try_year_fallback=true 时，若指定年份找不到任何报告，
    自动降级到 report_year-1、report_year-2，直到找到为止。
    """
    market_upper = market.upper()
    if market_upper != "CN":
        return JSONResponse({
            "candidates": [], "inserted": [], "errors": [],
            "partial": True, "reason": "报告发现功能当前仅支持 A 股（CN 市场）",
            "disclaimer": _DISCLAIMER,
        })

    # 确定需要尝试的年份序列
    if try_year_fallback:
        years_to_try = [report_year, report_year - 1, report_year - 2]
    else:
        years_to_try = [report_year]

    matched_year = report_year
    year_fallback_used = False
    result: dict = {"candidates": [], "total_found": 0, "errors": [], "partial": False}
    discovery_attempts: list[dict] = []

    for year in years_to_try:
        try:
            year_result = await report_discovery_agent.discover_latest(
                stock_code=code,
                company_name=company_name,
                report_year=year,
            )
        except Exception as e:
            log.error("discover_latest failed [%s] year=%d: %s", code, year, e)
            year_result = {"candidates": [], "total_found": 0, "errors": [str(e)], "partial": True}

        found_count = year_result.get("total_found", 0) or len(year_result.get("candidates") or [])
        discovery_attempts.append({
            "year":            year,
            "status":          "candidate_found" if found_count > 0 else "empty",
            "candidate_count": found_count,
            "providers":       year_result.get("sources_searched") or [],
            "errors":          year_result.get("errors") or [],
        })

        if found_count > 0:
            result = year_result
            matched_year = year
            year_fallback_used = (year != report_year)
            break

        # 最后一个年份也没结果，保留最后一次的错误信息
        result = year_result

    candidates = result.get("candidates") or []
    inserted = []

    for candidate in candidates:
        upsert_result = await report_document_service.upsert_discovered_report(candidate, db)
        if upsert_result["status"] == "inserted":
            inserted.append({**candidate, "report_id": upsert_result["report_id"]})

    message = ""
    if year_fallback_used:
        message = f"未找到 {report_year} 年报，已找到最近可用 {matched_year} 年报"

    return JSONResponse({
        "candidates":         candidates,
        "inserted":           inserted,
        "errors":             result.get("errors") or [],
        "partial":            result.get("partial", False),
        "total_found":        result.get("total_found", 0),
        "matched_year":       matched_year,
        "year_fallback_used": year_fallback_used,
        "requested_year":     report_year,
        "message":            message,
        "discovery_attempts": discovery_attempts,
        "disclaimer":         _DISCLAIMER,
    })


# ── GET /api/v1/stocks/{market}/{code}/reports/{report_id}/pdf ────────────────

@router.get(
    "/{market}/{code}/reports/{report_id}/pdf",
    summary="查看/代理年报 PDF（仅限已入库 report_id）",
)
async def get_report_pdf(
    market: str = Path(..., description="市场代码"),
    code: str = Path(..., description="股票代码"),
    report_id: int = Path(..., description="report_documents.id"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    安全 PDF 查看路由：
    - 只允许已入库的 report_id（防止任意 redirect）
    - 只 redirect 到 cninfo / sse / szse 域名
    - 不暴露 local_path
    - 不允许任意外部 URL
    """
    doc = await report_document_service.get_by_id(report_id, db)

    if not doc:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    # Verify the report belongs to the requested stock code
    ts_code = _to_ts_code(market, code)
    if doc.ts_code != ts_code:
        raise HTTPException(status_code=403, detail="报告不属于指定股票")

    # Check pdf_url is from a trusted domain (prevent open redirect)
    pdf_url = doc.pdf_url or ""

    if not pdf_url:
        raise HTTPException(status_code=404, detail="该报告暂无 PDF 链接")

    parsed = urlparse(pdf_url)
    domain = parsed.netloc.lower()
    if not any(domain == d or domain.endswith("." + d) for d in _ALLOWED_DOMAINS):
        log.warning("PDF redirect to untrusted domain rejected: %s", domain)
        raise HTTPException(status_code=403, detail="PDF 链接来源不在可信域名列表，禁止跳转")

    return RedirectResponse(url=pdf_url, status_code=302)


# ── POST /api/v1/stocks/{market}/{code}/reports/{report_id}/download ──────────

@router.post(
    "/{market}/{code}/reports/{report_id}/download",
    summary="下载年报 PDF 到本地缓存",
)
async def download_report_pdf(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """触发服务端 PDF 下载并缓存。返回下载状态和文件信息。"""
    result = await report_pdf_download_service.download(report_id, db)
    return JSONResponse(result)


# ── POST /api/v1/stocks/{market}/{code}/reports/{report_id}/parse ─────────────

@router.post(
    "/{market}/{code}/reports/{report_id}/parse",
    summary="解析已下载年报 PDF，提取文本摘录",
)
async def parse_report_pdf(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """从本地缓存 PDF 提取文本摘录（5000-8000 字符），供 AI 分析引用。"""
    result = await report_text_extract_service.parse(report_id, db)
    return JSONResponse(result)


# ── GET /api/v1/stocks/{market}/{code}/reports/{report_id}/text ───────────────

@router.get(
    "/{market}/{code}/reports/{report_id}/text",
    summary="获取年报文本摘录",
)
async def get_report_text(
    market: str = Path(...),
    code: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """返回已解析年报的 text_excerpt 内容，用于前端展示和 AI 引用。"""
    result = await report_text_extract_service.get_text(report_id, db)
    if not result["found"]:
        raise HTTPException(status_code=404, detail="报告不存在")
    return JSONResponse(result)
