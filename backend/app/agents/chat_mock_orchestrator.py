"""
Chat Mock Orchestrator — Phase C3.

Mirrors the 5 scenarios in frontend/src/mocks/chatMock.js but runs server-side.
Does NOT call any real LLM, real financial tools, or write to real user assets.

All responses carry "仅供研究参考，不构成投资建议。" disclaimer.
Financial safety rules: no 买入/卖出/持有/目标价.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"


@dataclass
class OrchestratorResult:
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    # None, or dict: {id, type, text, params}
    confirmation: dict | None = None


@dataclass
class ConfirmResult:
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)


def _tool(name: str, detail: str, status: str = "success") -> dict:
    return {"name": name, "status": status, "detail": detail}


def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


def _confirm_id(suffix: str) -> str:
    return f"confirm_{suffix}_{int(time.time() * 1000)}"


# ── Scenario matchers ──────────────────────────────────────────────────────────

def _match_anomaly(msg: str) -> bool:
    return bool(
        re.search(r"中船特气|688146", msg)
        or (re.search(r"为什么|原因|涨|跌|异动", msg) and re.search(r"股票|股", msg))
    )


def _match_report(msg: str) -> bool:
    return bool(re.search(r"生成.{0,10}报告|综合报告|分析报告|帮我分析", msg))


def _match_watchlist(msg: str) -> bool:
    return bool(
        re.search(r"加入自选|添加到自选|自选股", msg)
        and not re.search(r"查看自选股", msg)
    )


def _match_compare(msg: str) -> bool:
    return bool(re.search(r"对比|比较", msg))


def _match_industry(msg: str) -> bool:
    return bool(re.search(r"行业|热点|板块|哪些值得|热门", msg))


# ── Scenario handlers ──────────────────────────────────────────────────────────

def _scenario_anomaly(_msg: str) -> OrchestratorResult:
    answer = (
        "**中船特气（CN/688146）近期技术面偏强，以下为多维度观察：**\n\n"
        "**技术面：**\n"
        "价格大幅站上所有短期及中期均线，均线呈多头排列，近20日涨幅约 147.87%，"
        "价格偏离 MA20 达 87%，短期技术性回调风险较高。\n\n"
        "**新闻面：**\n"
        "近期因「六氟化钨」概念获市场关注，尾盘多次冲击涨停。公司已就股价严重异常波动发布公告，"
        "并澄清未公开披露产品价格信息，市场传闻存在不确定性。\n\n"
        "**风险提示：**\n"
        "短期涨幅较大，成交换手率处于高位（14.47%），存在高位分化风险。"
        "公司异常波动公告及监管关注信号值得持续跟踪。"
        + _DISCLAIMER
    )
    return OrchestratorResult(
        answer=answer,
        tool_events=[
            _tool("resolve_stock_tool",       "CN/688146 → 中船特气"),
            _tool("get_quote_tool",            "当前价 330.5（+12.3%）"),
            _tool("get_kline_summary_tool",    "近20日涨幅 147.87%，均线多头排列"),
            _tool("get_latest_news_tool",      "获取6条近72小时新闻"),
        ],
        cards=[
            _card("stock_summary", {
                "name": "中船特气",
                "market": "CN",
                "symbol": "688146",
                "price": "330.5",
                "changePct": "+12.3%",
                "changeDir": "up",
                "summary": "技术面偏强 · 新闻催化明显 · 短期存在回调风险",
                "links": [
                    {"label": "查看股票详情", "path": "/stocks/CN/688146"},
                    {"label": "生成综合报告 →", "action": "generate_report",
                     "symbol": "688146", "market": "CN", "name": "中船特气"},
                ],
            })
        ],
    )


def _extract_report_stock(msg: str) -> dict:
    if re.search(r"688146|中船特气", msg):
        return {"name": "中船特气", "market": "CN", "symbol": "688146"}
    if re.search(r"600519|茅台", msg):
        return {"name": "贵州茅台", "market": "CN", "symbol": "600519"}
    return {"name": "中船特气", "market": "CN", "symbol": "688146"}


def _scenario_report(msg: str) -> OrchestratorResult:
    stock = _extract_report_stock(msg)
    cid = _confirm_id("report")
    return OrchestratorResult(
        answer="",
        tool_events=[
            _tool("resolve_stock_tool", f"CN/{stock['symbol']} → {stock['name']}"),
        ],
        cards=[],
        confirmation={
            "id": cid,
            "type": "create_analysis_run",
            "text": (
                f"我将为 **{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                " 生成综合分析报告，预计需要 30~60 秒。是否确认？"
            ),
            "params": stock,
        },
    )


def _scenario_watchlist(msg: str) -> OrchestratorResult:
    stock = (
        {"name": "中船特气", "market": "CN", "symbol": "688146"}
        if re.search(r"688146|中船特气", msg)
        else {"name": "中船特气", "market": "CN", "symbol": "688146"}
    )
    cid = _confirm_id("watchlist")
    return OrchestratorResult(
        answer="",
        tool_events=[
            _tool("resolve_stock_tool", f"CN/{stock['symbol']} → {stock['name']}"),
            _tool("get_watchlist_tool",  "检查自选股列表，未发现重复"),
        ],
        cards=[],
        confirmation={
            "id": cid,
            "type": "add_watchlist",
            "text": (
                f"我将把 **{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                " 加入你的自选股，是否确认？"
            ),
            "params": stock,
        },
    )


def _scenario_compare(msg: str) -> OrchestratorResult:
    stocks = [
        {"name": "宁德时代", "market": "CN", "symbol": "300750"},
        {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
        {"name": "华大九天", "market": "CN", "symbol": "301269"},
    ]
    if re.search(r"600519|茅台", msg):
        stocks = [
            {"name": "贵州茅台", "market": "CN", "symbol": "600519"},
            {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
        ]
    compare_url = "/compare?stocks=" + ",".join(
        f"{s['market']}:{s['symbol']}" for s in stocks
    )
    stock_desc = "、".join(f"{s['name']}（{s['symbol']}）" for s in stocks)
    cid = _confirm_id("compare")
    return OrchestratorResult(
        answer="",
        tool_events=[
            *[
                _tool("resolve_stock_tool", f"{s['market']}/{s['symbol']} → {s['name']}")
                for s in stocks
            ],
            _tool("create_compare_selection_tool", f"已准备 {len(stocks)} 只股票对比"),
        ],
        cards=[],
        confirmation={
            "id": cid,
            "type": "create_compare",
            "text": (
                f"我将打开对比页，从研究维度对比 **{stock_desc}**，是否确认？"
            ),
            "params": {"stocks": stocks, "compare_url": compare_url},
        },
    )


def _scenario_industry(_msg: str) -> OrchestratorResult:
    return OrchestratorResult(
        answer=(
            "以下为当前申万行业热度排行（基于成交额 × 涨跌幅综合评分），"
            "仅作研究线索，不代表投资价值判断。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool("get_industry_hot_tool", "电子/医药/电力设备等行业热度快照"),
        ],
        cards=[
            _card("industry_hot", {
                "items": [
                    {"name": "电子",    "code": "801080", "hotScore": 4.82, "changePct": "+3.5%"},
                    {"name": "医药生物", "code": "801150", "hotScore": 4.31, "changePct": "+1.8%"},
                    {"name": "电力设备", "code": "801730", "hotScore": 3.97, "changePct": "+2.1%"},
                    {"name": "有色金属", "code": "801050", "hotScore": 3.65, "changePct": "+0.9%"},
                    {"name": "计算机",   "code": "801750", "hotScore": 3.44, "changePct": "-0.3%"},
                ],
                "links": [{"label": "查看行业页", "path": "/industries"}],
            })
        ],
    )


def _scenario_default(_msg: str) -> OrchestratorResult:
    return OrchestratorResult(
        answer=(
            "你好！我是 TradingAgents Chat Copilot，可以帮你完成以下研究任务：\n\n"
            "- **股票异动分析**：例如：中船特气最近为什么涨这么多\n"
            "- **生成研究报告**：例如：帮我生成 688146 的综合报告\n"
            "- **加入自选股**：例如：把中船特气加入自选\n"
            "- **多股对比**：例如：对比宁德时代、紫金矿业\n"
            "- **行业热点**：例如：今天哪些行业值得关注\n"
            + _DISCLAIMER
        ),
    )


# ── Confirm handlers ───────────────────────────────────────────────────────────

def _confirm_report(params: dict) -> ConfirmResult:
    name   = params.get("name",   "中船特气")
    market = params.get("market", "CN")
    symbol = params.get("symbol", "688146")
    return ConfirmResult(
        answer=(
            f"✓ 报告生成任务已提交。\n\n"
            "**综合判断：分歧**\n"
            "技术面偏强，但基本面数据不完整，无法全面评估当前估值，"
            "信号存在分歧。建议结合公司财报数据进一步判断。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool("create_analysis_run_tool", "综合分析任务已创建（Mock）"),
        ],
        cards=[
            _card("report_link", {
                "name": name, "market": market, "symbol": symbol,
                "scope": "综合分析",
                "verdict": "分歧",
                "links": [
                    {"label": "查看历史报告", "path": "/history"},
                    {"label": "前往综合分析", "path": "/"},
                ],
            })
        ],
    )


def _confirm_watchlist(params: dict) -> ConfirmResult:
    name   = params.get("name",   "中船特气")
    market = params.get("market", "CN")
    symbol = params.get("symbol", "688146")
    return ConfirmResult(
        answer=(
            f"✓ 已成功将 **{name}（{market}/{symbol}）** 加入自选股。"
            + _DISCLAIMER
        ),
        tool_events=[
            _tool("add_to_watchlist_tool", f"{name} 已加入自选股（Mock）"),
        ],
        cards=[
            _card("watchlist_success", {
                "name": name, "market": market, "symbol": symbol,
                "links": [{"label": "查看自选股", "path": "/watchlist"}],
            })
        ],
    )


def _confirm_compare(params: dict) -> ConfirmResult:
    stocks      = params.get("stocks", [])
    compare_url = params.get("compare_url", "/compare")
    return ConfirmResult(
        answer=(
            f"已准备好对比页面。以下为 {len(stocks)} 只股票的研究维度概览"
            "（点击下方按钮进入完整对比）。"
            + _DISCLAIMER
        ),
        tool_events=[],
        cards=[
            _card("compare_link", {
                "stocks": stocks,
                "compareUrl": compare_url,
                "links": [{"label": "进入对比页", "path": compare_url}],
            })
        ],
    )


# ── Public API ─────────────────────────────────────────────────────────────────

_SCENARIOS = [
    # More specific intents first so "生成报告" beats a bare stock-code match
    (_match_report,    _scenario_report),
    (_match_watchlist, _scenario_watchlist),
    (_match_compare,   _scenario_compare),
    (_match_industry,  _scenario_industry),
    (_match_anomaly,   _scenario_anomaly),
]

_CONFIRM_HANDLERS = {
    "create_analysis_run": _confirm_report,
    "add_watchlist":        _confirm_watchlist,
    "create_compare":       _confirm_compare,
}


def process_message(content: str, output_language: str = "zh-CN") -> OrchestratorResult:
    """
    Route user message to appropriate mock scenario.
    output_language reserved for future LLM integration.
    """
    msg = content.strip().lower()
    for matcher, handler in _SCENARIOS:
        if matcher(msg):
            return handler(msg)
    return _scenario_default(msg)


def process_confirm(confirmation_type: str, params: dict) -> ConfirmResult:
    """
    Execute the confirmed action (mock — no real side effects).
    Returns follow-up tool_events, answer, and cards.
    """
    handler = _CONFIRM_HANDLERS.get(confirmation_type)
    if handler is None:
        return ConfirmResult(
            answer="操作已完成。" + _DISCLAIMER,
        )
    return handler(params)
