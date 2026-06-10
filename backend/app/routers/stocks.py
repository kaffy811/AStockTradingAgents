import asyncio
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.analysis_report import AnalysisReport
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.services.stock_data_service import stock_data_service
from app.services.fundamental_data_service import fundamental_data_service
from app.services.peer_comparison_service import peer_comparison_service
from app.services.news_data_service import news_data_service
from app.services.industry_classification_service import industry_classification_service

router = APIRouter(prefix="/stocks", tags=["stocks"])

# ── Search schemas ────────────────────────────────────────────────────────────

class StockSearchItem(BaseModel):
    market:        str
    symbol:        str
    name:          str | None
    industry_code: str | None
    industry_name: str | None
    source:        str


class StockSearchResponse(BaseModel):
    market:       str
    query:        str
    total:        int
    items:        list[StockSearchItem]
    data_quality: dict


# ── Search route (must be before /{market}/{symbol}/... path-param routes) ────

@router.get("/search", response_model=StockSearchResponse)
async def search_stocks(
    market: str = Query("CN",  description="CN / HK"),
    q:      str = Query("",    description="股票代码前缀或名称关键词"),
    limit:  int = Query(10,    ge=1, le=20),
    _:  User         = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StockSearchResponse:
    """
    股票搜索 / 代码联想。

    - CN：支持 symbol 前缀匹配（600519 → 贵州茅台）+ 名称模糊匹配（茅台 → 600519）
    - HK：支持 5 位补零格式（00700）、短格式（700）、中文名称（腾讯）搜索
    - q 为空：返回 items=[]
    - 数据源：stock_master（优先）；stock_master 无该市场数据时 fallback 到 stock_industry_map
    """
    market = market.upper()
    if market not in {"CN", "HK"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"market 只支持 CN 或 HK，收到 '{market}'",
        )

    items: list[dict] = []

    if q.strip():
        items = await industry_classification_service.search_stocks(db, market, q, limit)

    # data_quality.source reflects which table actually served the results.
    dq_source = items[0]["source"] if items else "stock_master"

    return StockSearchResponse(
        market=market,
        query=q,
        total=len(items),
        items=[StockSearchItem(**i) for i in items],
        data_quality={"source": dq_source, "message": None},
    )


# ── Adjust parameter normalisation ───────────────────────────────────────────

_VALID_ADJUST = {"", "qfq", "hfq"}

_ADJUST_EMPTY_ALIASES = {
    None, "", " ", '"', '""', "none", "null", "NONE", "NULL",
}


def _normalize_adjust(raw: str | None) -> str:
    if raw is None:
        return ""
    stripped = raw.strip()
    if stripped in _ADJUST_EMPTY_ALIASES or stripped.lower() in {"none", "null"}:
        return ""
    if stripped not in _VALID_ADJUST:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"adjust 参数非法：'{raw}'。只支持 qfq（前复权）、hfq（后复权）或空字符串。",
        )
    return stripped


# ── Response schemas ──────────────────────────────────────────────────────────

class QuoteResponse(BaseModel):
    market: str
    symbol: str
    provider: str
    cached: bool = False
    stale: bool = False
    fallback_chain: list[dict] = []
    message: str | None = None
    data: dict


class KlineResponse(BaseModel):
    market: str
    symbol: str
    provider: str
    period: str
    adjust: str
    count: int
    volume_unit: str          # "lot" for CN (1 lot = 100 shares), "share" for HK
    cached: bool = False
    stale: bool = False
    fallback_chain: list[dict] = []
    message: str | None = None
    data: list[dict]


# ── Fundamentals response schemas ─────────────────────────────────────────────

class FundamentalsCompany(BaseModel):
    name:             str | None
    industry:         str | None
    business_summary: str | None


class FundamentalsValuation(BaseModel):
    pe:              float | None
    pb:              float | None
    ps:              float | None
    market_cap:      float | None
    market_cap_unit: str | None
    dividend_yield:  float | None


class FundamentalsProfitability(BaseModel):
    roe:          float | None
    gross_margin: float | None
    net_margin:   float | None


class FundamentalsGrowth(BaseModel):
    revenue_growth_yoy:    float | None
    net_profit_growth_yoy: float | None


class FundamentalsFinancialHealth(BaseModel):
    debt_ratio:         float | None
    operating_cashflow: float | None


class FundamentalsDataQuality(BaseModel):
    provider:           str | None
    data_sources:       dict
    missing_fields:     list[str]
    stale:              bool
    message:            str | None
    latest_report_date: str | None = None   # ISO date of most recent financial report


class FundamentalsResponse(BaseModel):
    market:           str
    symbol:           str
    company:          FundamentalsCompany
    valuation:        FundamentalsValuation
    profitability:    FundamentalsProfitability
    growth:           FundamentalsGrowth
    financial_health: FundamentalsFinancialHealth
    data_quality:     FundamentalsDataQuality


# ── Peer comparison response schemas ─────────────────────────────────────────

class PeerStockEntry(BaseModel):
    market:       str
    symbol:       str
    name:         str | None
    fundamentals: dict        # FundamentalsResponse-shaped dict


class ComparisonFields(BaseModel):
    candidate:           list[str]
    available:           list[str]
    missing_in_target:   list[str]
    missing_in_all:      list[str]
    missing_in_any_peer: list[str]


class PeerDataQuality(BaseModel):
    peer_source:         str
    latest_report_dates: dict[str, str | None]
    missing_peers:       list[str]
    missing_fields:      dict[str, list[str]]
    message:             str | None
    # Phase 1D: dynamic peer discovery metadata (None for manual_map / no-peers cases)
    industry_code:       str | None = None
    industry_name:       str | None = None
    hot_stock_date:      str | None = None
    hot_score_version:   str | None = None
    fallback_reason:     str | None = None


class PeerFundamentalsResponse(BaseModel):
    market:            str
    symbol:            str
    target:            PeerStockEntry
    peers:             list[PeerStockEntry]
    comparison_fields: ComparisonFields
    data_quality:      PeerDataQuality


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{market}/{symbol}/quote", response_model=QuoteResponse)
async def get_quote(
    market: str,
    symbol: str,
    _: User = Depends(get_current_user),
):
    """
    Fetch the latest snapshot quote for a stock.

    CN fallback: EastMoney → Sina → Tencent → stale cache → 503
    HK fallback: Tencent HK → AkShare → stale cache → 503
    """
    market = market.upper()
    try:
        r = stock_data_service.get_quote(market, symbol)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    body = QuoteResponse(
        market=market,
        symbol=symbol,
        provider=r.provider,
        cached=r.cached,
        stale=r.stale,
        fallback_chain=r.fallback_chain,
        message=r.message,
        data=r.data,
    )
    return JSONResponse(status_code=r.http_status, content=body.model_dump())


@router.get("/{market}/{symbol}/kline", response_model=KlineResponse)
async def get_kline(
    market: str,
    symbol: str,
    period: str = Query(default="daily", description="daily | weekly | monthly"),
    adjust: str = Query(default="", description="'' | qfq | hfq"),
    limit: int = Query(default=120, ge=1, le=500, description="Max bars (1-500)"),
    _: User = Depends(get_current_user),
):
    """
    Fetch historical OHLCV candlestick data.

    CN fallback: EastmoneyKline → AkShare → stale cache → 503
    HK fallback: AkShare → stale cache → 503
    """
    market = market.upper()
    adjust = _normalize_adjust(adjust)

    try:
        r = stock_data_service.get_kline(market, symbol, period, adjust, limit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    # CN kline volume 单位是手(lot)，HK kline volume 单位是股(share)
    volume_unit = "lot" if market == "CN" else "share"

    # 有 stale 数据时 http_status=200，无数据时 http_status=503，均通过 JSONResponse 传递
    body = KlineResponse(
        market=market,
        symbol=symbol,
        provider=r.provider,
        period=period,
        adjust=adjust,
        count=len(r.bars),
        volume_unit=volume_unit,
        cached=r.cached,
        stale=r.stale,
        fallback_chain=r.fallback_chain,
        message=r.message,
        data=r.bars,
    )
    return JSONResponse(status_code=r.http_status, content=body.model_dump())


@router.get(
    "/{market}/{symbol}/fundamentals",
    response_model=FundamentalsResponse,
    summary="基本面快照（Phase 1）",
    description=(
        "返回股票基本面快照。\n\n"
        "**Phase 1 有真实值的字段：**\n"
        "- `company.name`（CN: AkShare；HK: Tencent/AkShare quote）\n"
        "- `valuation.pe`（CN only，AkShare 动态市盈率）\n"
        "- `valuation.pb`（CN only，AkShare 市净率）\n"
        "- `valuation.market_cap`（可选，yfinance；失败返回 null）\n\n"
        "**其余字段 Phase 1 均为 null**，待 Phase 2 接入财报数据。\n\n"
        "- 任何数据源失败不阻塞接口，拿不到的字段返回 null 并写入 `missing_fields`\n"
        "- 有历史缓存时返回 stale 数据（`data_quality.stale=true`），不返回 5xx\n"
        "- 缓存 TTL = 10 分钟\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def get_fundamentals(
    market: str,
    symbol: str,
    _: User = Depends(get_current_user),
) -> FundamentalsResponse:
    """基本面快照（Phase 1）。业务逻辑全在 FundamentalDataService。"""
    market = market.upper()
    if market not in {"CN", "HK"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"market 只支持 CN 或 HK，收到 '{market}'",
        )
    result = await asyncio.to_thread(
        fundamental_data_service.get_fundamentals, market, symbol
    )
    return result


@router.get(
    "/{market}/{symbol}/peers/fundamentals",
    response_model=PeerFundamentalsResponse,
    summary="同行基本面对比（Phase 1）",
    description=(
        "返回目标股及其同行的基本面快照，并给出字段可用性分析。\n\n"
        "**Phase 1 同行识别方式：** 手动 PEER_MAP，未配置的股票返回空 peers 列表。\n\n"
        "**comparison_fields 结构：**\n"
        "- `available`：target 和 ≥1 peer 均有值，可用于横向对比\n"
        "- `missing_in_target`：target 本身为 null，不得对目标股该字段下结论\n"
        "- `missing_in_all`：target 和所有 peers 均为 null，完全不能用于对比\n"
        "- `missing_in_any_peer`：target 有值但部分 peers 缺失，覆盖不完整\n\n"
        "- 单只 peer 获取失败不影响整体响应\n"
        "- target + peers 并发拉取，有缓存时几乎零延迟\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def get_peer_fundamentals(
    market: str,
    symbol: str,
    _:  User         = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeerFundamentalsResponse:
    """
    同行基本面对比（Phase 1D：动态同行）。

    同行来源优先级（由 PeerComparisonService.get_peer_fundamentals_dynamic 处理）：
      1. PEER_MAP 手动配置（最高优先级，任何市场）
      2. CN 市场：同一申万一级行业 Hot Score Top-N
      3. 其他情况：peers=[]，data_quality 说明原因
    """
    market = market.upper()
    if market not in {"CN", "HK"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"market 只支持 CN 或 HK，收到 '{market}'",
        )

    return await peer_comparison_service.get_peer_fundamentals_dynamic(db, market, symbol)


# ── News response schemas ─────────────────────────────────────────────────────

class NewsItem(BaseModel):
    title:        str
    summary:      str | None = None
    url:          str | None = None
    source:       str | None = None
    publish_time: str | None = None
    type:         str
    symbols:      list[str]


class NewsDataQuality(BaseModel):
    provider: str | None = None
    cached:   bool       = False
    message:  str | None = None


class NewsResponse(BaseModel):
    market:       str
    symbol:       str
    items:        list[NewsItem]
    count:        int
    data_quality: NewsDataQuality


# ── News route ────────────────────────────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/news",
    response_model=NewsResponse,
    summary="个股新闻（Phase 1）",
    description=(
        "获取个股最近新闻列表。\n\n"
        "**数据源：** 东方财富 AkShare `stock_news_em`，固定返回最近 10 条原始数据，"
        "在服务层按 `hours_back` 时间窗口过滤后返回。\n\n"
        "**HK 说明：** 港股通过关键词搜索（5 位补零代码，如 700 → 00700）获取，"
        "结果可能包含弱相关内容，`data_quality.message` 中会注明。\n\n"
        "- provider 失败 → `items=[]`，`message` 说明失败原因，不返回 5xx\n"
        "- provider 失败但有缓存 → 返回旧数据，`cached=true`\n"
        "- 缓存 TTL = 10 分钟\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def get_stock_news(
    market:     str,
    symbol:     str,
    hours_back: int = Query(default=72,  ge=1,  le=720, description="最近 N 小时内的新闻"),
    limit:      int = Query(default=20,  ge=1,  le=50,  description="最多返回条数"),
    _: User = Depends(get_current_user),
) -> NewsResponse:
    market = market.upper()
    symbol = symbol.strip()

    if market not in {"CN", "HK"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"market 只支持 CN 或 HK，收到 '{market}'",
        )
    if not symbol:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "symbol 不能为空")

    result = await asyncio.to_thread(
        news_data_service.get_stock_news, market, symbol, hours_back, limit
    )
    return NewsResponse(
        market=result["market"],
        symbol=result["symbol"],
        items=[NewsItem(**item) for item in result["items"]],
        count=result["count"],
        data_quality=NewsDataQuality(**result["data_quality"]),
    )


# ── Profile response schemas ──────────────────────────────────────────────────

class ProfileQuote(BaseModel):
    latest_price: float | None = None
    change_pct:   float | None = None
    open:         float | None = None
    high:         float | None = None
    low:          float | None = None
    prev_close:   float | None = None
    volume:       float | None = None
    amount:       float | None = None
    trade_time:   str   | None = None
    status:       str          = "success"
    message:      str   | None = None


class ProfileIndustry(BaseModel):
    industry_code: str
    industry_name: str
    source:        str = "stock_industry_map"


class ProfileWatchlist(BaseModel):
    in_watchlist: bool
    watchlist_id: str | None = None
    note:         str | None = None


class ProfileLatestReport(BaseModel):
    id:              str
    stock_name:      str | None = None
    analysis_scope:  str        = "comprehensive"
    auto_saved:      bool       = False
    created_at:      datetime
    summary_excerpt: str | None = None


class ProfileDataQuality(BaseModel):
    quote_status:    str        = "success"
    industry_status: str        = "success"
    watchlist_status: str       = "success"
    report_status:   str        = "success"
    message:         str | None = None


class StockProfileResponse(BaseModel):
    market:        str
    symbol:        str
    stock_name:    str | None = None
    quote:         ProfileQuote
    industry:      ProfileIndustry | None = None
    watchlist:     ProfileWatchlist
    latest_report: ProfileLatestReport | None = None
    data_quality:  ProfileDataQuality


# ── Profile helper ────────────────────────────────────────────────────────────

def _extract_summary(report_md: str, max_chars: int = 160) -> str | None:
    """
    Extract summary excerpt from report markdown.

    Priority:
    1. Content after 「核心摘要」 section header
    2. Content after 「核心结论」 section header
    3. Fallback: first max_chars chars with markdown stripped
    """
    if not report_md:
        return None

    _SECTION_PATTERNS = [
        r"#{1,3}\s*[一二三四五六七八九十\d]*[、.．\s]*核心摘要[^\n]*\n+(.*?)(?=\n#{1,3}|\Z)",
        r"#{1,3}\s*核心摘要[^\n]*\n+(.*?)(?=\n#{1,3}|\Z)",
        r"#{1,3}\s*[一二三四五六七八九十\d]*[、.．\s]*核心结论[^\n]*\n+(.*?)(?=\n#{1,3}|\Z)",
    ]
    for pattern in _SECTION_PATTERNS:
        m = re.search(pattern, report_md, re.DOTALL)
        if m:
            text = m.group(1).strip()
            text = re.sub(r"[*_`#>]+", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text[:max_chars] + ("…" if len(text) > max_chars else "")

    # Fallback
    text = re.sub(r"#{1,6}\s+", "", report_md)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        return text[:max_chars] + ("…" if len(text) > max_chars else "")
    return None


# ── Profile route ─────────────────────────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/profile",
    response_model=StockProfileResponse,
    summary="股票详情页首屏聚合数据",
    description=(
        "将股票身份、行情、行业、自选状态、最近报告摘要聚合为单一接口，"
        "减少首屏多次请求。\n\n"
        "- 任一子数据失败不阻塞整体，降级返回 null/failed 状态\n"
        "- quote: asyncio.create_task + asyncio.to_thread 并发获取\n"
        "- HK 不返回申万行业（industry=null）\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def get_stock_profile(
    market: str,
    symbol: str,
    user:   User         = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
) -> StockProfileResponse:
    """股票详情页首屏聚合接口。各子数据失败时降级，不返回 500。"""
    market_upper = market.upper()
    symbol_clean = symbol.strip()

    if market_upper not in {"CN", "HK"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"market 只支持 CN 或 HK，收到 '{market}'",
        )
    if not symbol_clean:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "symbol 不能为空")

    dq = ProfileDataQuality()

    # ── Quote: start as background task (runs while DB queries proceed) ────────
    async def _do_quote() -> ProfileQuote:
        try:
            r = await asyncio.to_thread(stock_data_service.get_quote, market_upper, symbol_clean)
            if r.http_status == 200 and r.data:
                d = r.data
                return ProfileQuote(
                    latest_price = d.get("price"),
                    change_pct   = d.get("change_pct"),
                    open         = d.get("open"),
                    high         = d.get("high"),
                    low          = d.get("low"),
                    prev_close   = d.get("prev_close"),
                    volume       = d.get("volume"),
                    amount       = d.get("amount"),
                    trade_time   = str(d["trade_time"]) if d.get("trade_time") else None,
                    status       = "success",
                )
            return ProfileQuote(status="failed", message=getattr(r, "message", None))
        except Exception as exc:
            return ProfileQuote(status="failed", message=str(exc)[:120])

    quote_task = asyncio.create_task(_do_quote())

    # ── Industry: DB query (CN only) ──────────────────────────────────────────
    industry: ProfileIndustry | None = None
    if market_upper == "CN":
        try:
            row = await industry_classification_service.get_stock_industry(
                db, market_upper, symbol_clean
            )
            if row:
                industry = ProfileIndustry(
                    industry_code = row["industry_code"],
                    industry_name = row["industry_name"],
                    source        = row.get("source", "stock_industry_map"),
                )
            else:
                dq.industry_status = "unavailable"
        except Exception:
            dq.industry_status = "failed"
    else:
        dq.industry_status = "unavailable"

    # ── Watchlist: DB query ───────────────────────────────────────────────────
    watchlist_data = ProfileWatchlist(in_watchlist=False)
    try:
        wl_stmt = select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.market  == market_upper,
            WatchlistItem.symbol  == symbol_clean,
        )
        wl_item = (await db.execute(wl_stmt)).scalar_one_or_none()
        if wl_item:
            watchlist_data = ProfileWatchlist(
                in_watchlist = True,
                watchlist_id = str(wl_item.id),
                note         = wl_item.note,
            )
    except Exception:
        dq.watchlist_status = "failed"

    # ── Latest report: DB query ───────────────────────────────────────────────
    latest_report_data: ProfileLatestReport | None = None
    stock_name_from_report: str | None = None
    try:
        report_stmt = (
            select(
                AnalysisReport.id,
                AnalysisReport.stock_name,
                AnalysisReport.analysis_scope,
                AnalysisReport.auto_saved,
                AnalysisReport.created_at,
                AnalysisReport.report_md,
            )
            .where(
                AnalysisReport.user_id == user.id,
                AnalysisReport.market  == market_upper,
                AnalysisReport.symbol  == symbol_clean,
            )
            .order_by(AnalysisReport.created_at.desc())
            .limit(1)
        )
        report_row = (await db.execute(report_stmt)).mappings().first()
        if report_row:
            stock_name_from_report = report_row["stock_name"] or None
            latest_report_data = ProfileLatestReport(
                id              = str(report_row["id"]),
                stock_name      = report_row["stock_name"],
                analysis_scope  = report_row["analysis_scope"] or "comprehensive",
                auto_saved      = bool(report_row["auto_saved"]),
                created_at      = report_row["created_at"],
                summary_excerpt = _extract_summary(report_row["report_md"] or ""),
            )
        else:
            dq.report_status = "none"
    except Exception:
        dq.report_status = "failed"

    # ── Stock name: report → search fallback ──────────────────────────────────
    stock_name: str | None = stock_name_from_report
    if not stock_name:
        try:
            items = await industry_classification_service.search_stocks(
                db, market_upper, symbol_clean, 3
            )
            hit = next(
                (i for i in items
                 if i["symbol"] == symbol_clean
                 or i["symbol"].lstrip("0") == symbol_clean.lstrip("0")),
                items[0] if items else None,
            )
            stock_name = hit["name"] if hit else None
        except Exception:
            pass

    # ── Await quote ───────────────────────────────────────────────────────────
    profile_quote = await quote_task
    if profile_quote.status != "success":
        dq.quote_status = "failed"

    return StockProfileResponse(
        market        = market_upper,
        symbol        = symbol_clean,
        stock_name    = stock_name,
        quote         = profile_quote,
        industry      = industry,
        watchlist     = watchlist_data,
        latest_report = latest_report_data,
        data_quality  = dq,
    )
