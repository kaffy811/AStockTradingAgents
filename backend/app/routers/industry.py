"""
Industry Router — 行业分类 & 热门股查询。

路由：
  GET  /industries                                        查询市场下所有已录入行业
  GET  /industries/stocks/{market}/{symbol}               查询单只股票的行业归属
  GET  /industries/stocks/{market}/{symbol}/dynamic-peers 查询股票动态同行（PEER_MAP > Hot Top5）
  GET  /industries/{market}/{industry_code}/constituents  查询行业成分股
  GET  /industries/{market}/{industry_code}/hot-stocks    查询行业热门股 Top-N

所有接口均需要 Bearer token 鉴权。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.industry import (
    IndustryConstituentsResponse,
    IndustryConstituentItem,
    IndustryInfoResponse,
    StockIndustryResponse,
)
from app.models.industry_hot_stock import HotStockItem, HotStockDataQuality, HotStockResponse
from app.models.user import User
from app.services.dynamic_peer_discovery_service import dynamic_peer_discovery_service
from app.services.industry_classification_service import industry_classification_service
from app.services.industry_hot_stock_service import industry_hot_stock_service


# ── Pydantic schemas for dynamic peer discovery ───────────────────────────────

class DynamicPeerItem(BaseModel):
    market:        str
    symbol:        str
    name:          str | None = None
    peer_source:   str
    rank:          int
    hot_score:     float | None = None
    score_factors: dict[str, Any] | None = None


class DynamicPeerIndustry(BaseModel):
    industry_code:  str
    industry_name:  str
    industry_level: int | None = None
    source:         str | None = None
    last_synced_at: str | None = None


class DynamicPeerDataQuality(BaseModel):
    peer_source:       str
    hot_stock_date:    str | None = None
    hot_score_version: str | None = None
    fallback_reason:   str | None = None
    message:           str | None = None


class DynamicPeerResponse(BaseModel):
    market:       str
    symbol:       str
    industry:     DynamicPeerIndustry | None = None
    peers:        list[DynamicPeerItem]
    data_quality: DynamicPeerDataQuality


router = APIRouter(prefix="/industries", tags=["industries"])


_HOT_NONE: dict = {
    "hot_score":      None,
    "stock_count":    0,
    "up_count":       0,
    "down_count":     0,
    "avg_change_pct": None,
    "amount":         None,
    "trade_date":     None,
    "score_version":  None,
    "data_quality": {
        "status":  "none",
        "message": "当前暂无行业热度快照",
    },
}


@router.get("/", response_model=list[IndustryInfoResponse])
async def list_industries(
    market: str = "CN",
    user:   User         = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
) -> list[IndustryInfoResponse]:
    """
    查询某市场下所有已录入的申万一级行业，含行业热度摘要。

    热度摘要基于 industry_hot_stock_snapshot 最新 trade_date 聚合。
    无快照的行业返回 hot_score=null，data_quality.status="none"。
    """
    rows = await industry_classification_service.list_industries(db, market)
    hot_summary = await industry_hot_stock_service.get_industry_hot_summary(db, market)

    result: list[IndustryInfoResponse] = []
    for row in rows:
        summary = hot_summary.get(row["industry_code"], _HOT_NONE)
        result.append(IndustryInfoResponse.model_validate({**row, **summary}))
    return result


@router.get("/stocks/{market}/{symbol}", response_model=StockIndustryResponse)
async def get_stock_industry(
    market: str,
    symbol: str,
    user:   User         = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
) -> StockIndustryResponse:
    """查询单只股票的主行业分类。找不到时返回 404。"""
    row = await industry_classification_service.get_stock_industry(
        db, market.upper(), symbol.strip()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Industry mapping not found",
        )
    return StockIndustryResponse.model_validate(row)


@router.get(
    "/stocks/{market}/{symbol}/dynamic-peers",
    response_model=DynamicPeerResponse,
)
async def get_dynamic_peers(
    market: str,
    symbol: str,
    limit:  int          = Query(5, ge=1, le=20),
    user:   User         = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
) -> DynamicPeerResponse:
    """
    动态同行发现。优先级：PEER_MAP 手动配置 > CN 行业 Hot Top-N。

    非 CN 市场且无 PEER_MAP 时返回 peers=[]，HTTP 200，data_quality.message 说明原因。
    """
    result = await dynamic_peer_discovery_service.discover_peers(
        db=db,
        market=market,
        symbol=symbol,
        limit=limit,
    )
    return DynamicPeerResponse(
        market   = result["market"],
        symbol   = result["symbol"],
        industry = DynamicPeerIndustry(**result["industry"]) if result["industry"] else None,
        peers    = [DynamicPeerItem(**p) for p in result["peers"]],
        data_quality = DynamicPeerDataQuality(**result["data_quality"]),
    )


@router.get(
    "/{market}/{industry_code}/constituents",
    response_model=IndustryConstituentsResponse,
)
async def get_industry_constituents(
    market:        str,
    industry_code: str,
    limit:         int          = Query(1000, ge=1, le=5000),
    user:          User         = Depends(get_current_user),
    db:            AsyncSession = Depends(get_db),
) -> IndustryConstituentsResponse:
    """查询某行业的所有成分股。行业不存在时返回空列表（不报错）。"""
    market = market.upper()
    rows = await industry_classification_service.get_industry_constituents(
        db, market, industry_code, limit
    )

    # 从第一条记录取行业名称；如果没有记录，industry_name 留空
    industry_name = rows[0]["industry_name"] if rows else ""

    return IndustryConstituentsResponse(
        market        = market,
        industry_code = industry_code,
        industry_name = industry_name,
        total         = len(rows),
        items         = [IndustryConstituentItem.model_validate(r) for r in rows],
    )


@router.get(
    "/{market}/{industry_code}/hot-stocks",
    response_model=HotStockResponse,
)
async def get_industry_hot_stocks(
    market:        str,
    industry_code: str,
    limit:         int          = Query(20, ge=1, le=100),
    user:          User         = Depends(get_current_user),
    db:            AsyncSession = Depends(get_db),
) -> HotStockResponse:
    """
    查询行业最新 trade_date 的热门股 Top-N（上限 100）。

    无快照时返回 items=[]，HTTP 200，data_quality.message 说明原因。
    """
    result = await industry_hot_stock_service.get_latest_hot_stocks(
        db, market.upper(), industry_code, limit
    )
    return HotStockResponse(
        market        = result["market"],
        industry_code = result["industry_code"],
        industry_name = result["industry_name"],
        trade_date    = result["trade_date"],
        score_version = result["score_version"],
        total         = result.get("total", 0),
        items         = [HotStockItem.model_validate(i) for i in result["items"]],
        data_quality  = HotStockDataQuality(**result["data_quality"]),
    )
