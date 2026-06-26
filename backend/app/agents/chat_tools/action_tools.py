"""
C5 Action Tools — real write operations triggered after user confirms a pending action.

These are NOT part of the read-only ToolRegistry; they are invoked directly from
chat_orchestrator.process_confirm after the user clicks "确认".

Three actions:
  execute_add_to_watchlist       — INSERT into watchlist_items (idempotent)
  execute_create_analysis_run    — create AnalysisRun via registry + background task
  execute_create_compare_selection — generate compare URL (no DB write, synchronous)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.realtime_analysis_runner import RealtimeAnalysisRunner
from app.core.database import AsyncSessionLocal
from app.llm.factory import get_llm_client
from app.services.run_registry_factory import get_run_registry

log = logging.getLogger(__name__)

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"


# ── ActionResult ───────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    ok: bool
    action: str              # "add_watchlist" | "create_analysis_run" | "create_compare"
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    data: dict = field(default_factory=dict)   # extra context (run_id, already_exists…)
    error: str | None = None


# ── Private helpers ────────────────────────────────────────────────────────────

def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


def _tool_event(name: str, detail: str, status: str = "success") -> dict:
    return {"name": name, "status": status, "detail": detail}


# ── execute_add_to_watchlist ───────────────────────────────────────────────────

async def execute_add_to_watchlist(
    params: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> ActionResult:
    """
    Insert stock into watchlist_items.
    Idempotent: returns already_exists=True (not an error) if already present.
    """
    from app.models.watchlist_item import WatchlistItem

    market = params.get("market", "CN").upper()
    symbol = params.get("symbol", "")
    name   = params.get("name", symbol)

    # Check for existing entry
    stmt = select(WatchlistItem).where(
        WatchlistItem.user_id == user_id,
        WatchlistItem.market  == market,
        WatchlistItem.symbol  == symbol,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        return ActionResult(
            ok=True,
            action="add_watchlist",
            answer=(
                f"**{name}（{market}/{symbol}）** 已在你的自选股中，无需重复添加。"
                + _DISCLAIMER
            ),
            tool_events=[
                _tool_event("add_to_watchlist_tool",
                            f"{name} 已在自选股（already_exists）")
            ],
            cards=[
                _card("watchlist_action", {
                    "name": name, "market": market, "symbol": symbol,
                    "already_exists": True,
                    "links": [{"label": "查看自选股", "path": "/watchlist"}],
                })
            ],
            data={"already_exists": True},
        )

    # Insert new item — use a savepoint so IntegrityError only rolls back
    # the nested transaction, leaving the outer session intact for the router.
    item = WatchlistItem(
        user_id    = user_id,
        market     = market,
        symbol     = symbol,
        name       = name,
        sort_order = 0,
    )
    try:
        async with db.begin_nested():
            db.add(item)
            await db.flush()
    except IntegrityError:
        # Race condition: concurrent insert; treat as already_exists.
        # Savepoint rolled back; outer transaction still valid.
        return ActionResult(
            ok=True,
            action="add_watchlist",
            answer=f"**{name}（{market}/{symbol}）** 已在你的自选股中。" + _DISCLAIMER,
            tool_events=[
                _tool_event("add_to_watchlist_tool",
                            f"{name} 并发重复，已存在", "success")
            ],
            cards=[
                _card("watchlist_action", {
                    "name": name, "market": market, "symbol": symbol,
                    "already_exists": True,
                    "links": [{"label": "查看自选股", "path": "/watchlist"}],
                })
            ],
            data={"already_exists": True},
        )

    return ActionResult(
        ok=True,
        action="add_watchlist",
        answer=(
            f"✓ 已将 **{name}（{market}/{symbol}）** 加入自选股。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool_event("add_to_watchlist_tool", f"{name} 已成功加入自选股")
        ],
        cards=[
            _card("watchlist_action", {
                "name": name, "market": market, "symbol": symbol,
                "already_exists": False,
                "links": [{"label": "查看自选股", "path": "/watchlist"}],
            })
        ],
        data={"already_exists": False, "item_id": str(item.id)},
    )


# ── execute_create_analysis_run ────────────────────────────────────────────────

async def execute_create_analysis_run(
    params: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    output_language: str = "zh-CN",
) -> ActionResult:
    """
    Create a real analysis run via AnalysisRunRegistry and start a background task.
    Mirrors the logic in POST /analysis/runs.
    """
    market = params.get("market", "CN").upper()
    symbol = params.get("symbol", "")
    name   = params.get("name", symbol)
    scope  = params.get("scope", "comprehensive")
    save_to_history = params.get("save_to_history", False)
    requested_from  = params.get("requested_from", "chat_agent")

    try:
        llm = get_llm_client()
    except ValueError as exc:
        log.error("execute_create_analysis_run: LLM init failed: %s", exc)
        return ActionResult(
            ok=False,
            action="create_analysis_run",
            answer="分析服务暂不可用（LLM 客户端初始化失败），请稍后再试。" + _DISCLAIMER,
            tool_events=[
                _tool_event("create_analysis_run_tool",
                            f"LLM 初始化失败: {exc}", "error")
            ],
            error=str(exc),
        )

    try:
        registry = get_run_registry()
    except Exception as exc:
        log.error("execute_create_analysis_run: Registry init failed: %s", exc)
        return ActionResult(
            ok=False,
            action="create_analysis_run",
            answer="分析服务暂不可用（Registry 初始化失败），请稍后再试。" + _DISCLAIMER,
            tool_events=[
                _tool_event("create_analysis_run_tool",
                            f"Registry 失败: {exc}", "error")
            ],
            error=str(exc),
        )

    run_ref = await registry.create_run(
        user_id         = str(user_id),
        market          = market,
        symbol          = symbol,
        analysis_scope  = scope,
        workflow_engine = "custom_coordinator",
        output_language = output_language,
    )

    runner = RealtimeAnalysisRunner(llm)

    async def _background() -> None:
        async with AsyncSessionLocal() as bg_db:
            await runner.run_analysis(run_ref, registry, bg_db)

    asyncio.create_task(_background(), name=f"chat_analysis_{run_ref.run_id}")

    return ActionResult(
        ok=True,
        action="create_analysis_run",
        answer=(
            f"✓ 已为 **{name}（{market}/{symbol}）** 创建分析任务。\n\n"
            f"Run ID：`{run_ref.run_id}`。报告生成需要约 30～60 秒，"
            "完成后可在**报告中心**查看。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool_event(
                "create_analysis_run_tool",
                (
                    f"{name} {scope} 分析已提交（run_id={run_ref.run_id}"
                    + (", save_to_history=true" if save_to_history else "")
                    + f", from={requested_from}）"
                ),
            )
        ],
        cards=[
            _card("analysis_run", {
                "run_id":  run_ref.run_id,
                "name":    name,
                "market":  market,
                "symbol":  symbol,
                "scope":   scope,
                "status":  "queued",
                "links": [
                    {"label": "查看报告中心", "path": "/history"},
                    {"label": "前往分析页",   "path": f"/analysis?market={market}&symbol={symbol}"},
                ],
            })
        ],
        data={"run_id": run_ref.run_id, "status": "queued"},
    )


# ── execute_create_compare_selection ──────────────────────────────────────────

def execute_create_compare_selection(params: dict) -> ActionResult:
    """
    Build a compare URL from the stock list. No DB write — synchronous.
    """
    stocks      = params.get("stocks", [])
    compare_url = params.get("compare_url") or (
        "/compare?stocks=" + ",".join(
            f"{s['market']}:{s['symbol']}" for s in stocks
        )
    )
    stock_desc = "、".join(f"{s['name']}（{s['symbol']}）" for s in stocks)

    return ActionResult(
        ok=True,
        action="create_compare",
        answer=(
            f"已准备好对比页面，从研究维度对比 **{stock_desc}**。"
            "点击下方按钮进入完整对比。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool_event(
                "create_compare_selection_tool",
                f"对比页面已生成：{len(stocks)} 只股票",
            )
        ],
        cards=[
            _card("compare_link", {
                "stocks":     stocks,
                "compareUrl": compare_url,
                "links": [{"label": "进入对比页", "path": compare_url}],
            })
        ],
        data={"compare_url": compare_url},
    )
