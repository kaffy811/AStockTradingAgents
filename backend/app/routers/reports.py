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
from app.repositories.report_repository import ReportRepository

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/", response_model=ReportCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportCreateResponse:
    """保存一份综合分析报告。user_id 从 JWT 中读取，不接受请求体传入。"""
    repo = ReportRepository(db)
    report = await repo.create_report(
        user_id         = user.id,
        market          = body.market,
        symbol          = body.symbol,
        report_type     = body.report_type,
        stock_name      = body.stock_name or None,
        auto_saved      = body.auto_saved,
        analysis_scope  = body.analysis_scope,
        output_language = body.output_language if hasattr(body, "output_language") else "zh-CN",
        report_md       = body.report_md,
        sections        = body.sections,
        report_metadata = body.report_metadata,
        warnings        = body.warnings,
        agents          = body.agents,
    )
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
    repo = ReportRepository(db)
    total, reports = await repo.list_reports(
        user.id,
        market         = market,
        symbol         = symbol,
        analysis_scope = analysis_scope,
        auto_saved     = auto_saved,
        start_date     = start_date,
        end_date       = end_date,
        limit          = limit,
        offset         = offset,
    )
    items = [ReportListItem.model_validate(r) for r in reports]
    return ReportListResponse(total=total, items=items)


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """查看单份报告详情。不属于当前用户的 report_id 返回 404。"""
    repo = ReportRepository(db)
    report = await repo.get_report(user.id, report_id)
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
    repo = ReportRepository(db)
    deleted = await repo.delete_report(user.id, report_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
