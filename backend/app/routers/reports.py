"""
Reports Router — 报告历史 CRUD。

路由：
  POST   /reports/          保存一份综合分析报告
  GET    /reports/          查询当前用户的历史报告列表
  GET    /reports/{id}      查看单份报告详情
  DELETE /reports/{id}      删除报告

所有接口均需要 Bearer token 鉴权。
用户只能访问自己的报告；不属于自己的 report_id 一律返回 404。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.analysis_report import (
    AnalysisReport,
    ReportCreateRequest,
    ReportCreateResponse,
    ReportDetailResponse,
    ReportListItem,
    ReportListResponse,
)
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/", response_model=ReportCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportCreateResponse:
    """保存一份综合分析报告。user_id 从 JWT 中读取，不接受请求体传入。"""
    report = AnalysisReport(
        user_id         = user.id,
        market          = body.market,
        symbol          = body.symbol,
        report_type     = body.report_type,
        stock_name      = body.stock_name or None,
        auto_saved      = body.auto_saved,
        analysis_scope  = body.analysis_scope,
        report_md       = body.report_md,
        sections        = body.sections,
        report_metadata = body.report_metadata,
        warnings        = body.warnings,
        agents          = body.agents,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return ReportCreateResponse.model_validate(report)


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    market:         str | None  = None,
    symbol:         str | None  = None,
    analysis_scope: str | None  = None,
    auto_saved:     bool | None = Query(None),
    start_date:     date | None = Query(None),
    end_date:       date | None = Query(None),
    limit:          int = Query(20, ge=1, le=50),
    offset:         int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """查询当前用户的历史报告列表（不含大字段 report_md / sections）。"""
    # Base filter: 只看自己的报告
    filters = [AnalysisReport.user_id == user.id]

    if market:
        filters.append(AnalysisReport.market == market.upper())
    if symbol:
        filters.append(AnalysisReport.symbol == symbol.strip())
    if analysis_scope:
        filters.append(AnalysisReport.analysis_scope == analysis_scope.strip())
    if auto_saved is not None:
        filters.append(AnalysisReport.auto_saved == auto_saved)
    if start_date:
        dt_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        filters.append(AnalysisReport.created_at >= dt_start)
    if end_date:
        dt_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) + timedelta(days=1)
        filters.append(AnalysisReport.created_at < dt_end)

    # 总数查询
    count_stmt = select(func.count()).select_from(AnalysisReport).where(*filters)
    total: int = (await db.execute(count_stmt)).scalar_one()

    # 列表查询（只取轻量字段，JSONB 仍会返回 warnings/agents，但不返回 report_md/sections）
    list_stmt = (
        select(
            AnalysisReport.id,
            AnalysisReport.market,
            AnalysisReport.symbol,
            AnalysisReport.report_type,
            AnalysisReport.stock_name,
            AnalysisReport.auto_saved,
            AnalysisReport.analysis_scope,
            AnalysisReport.warnings,
            AnalysisReport.agents,
            AnalysisReport.created_at,
        )
        .where(*filters)
        .order_by(AnalysisReport.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).mappings().all()
    items = [ReportListItem.model_validate(dict(row)) for row in rows]

    return ReportListResponse(total=total, items=items)


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """查看单份报告详情。不属于当前用户的 report_id 返回 404。"""
    stmt = select(AnalysisReport).where(
        AnalysisReport.id      == report_id,
        AnalysisReport.user_id == user.id,
    )
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportDetailResponse.model_validate(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """删除报告。不属于当前用户的 report_id 返回 404。"""
    stmt = select(AnalysisReport).where(
        AnalysisReport.id      == report_id,
        AnalysisReport.user_id == user.id,
    )
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await db.delete(report)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
