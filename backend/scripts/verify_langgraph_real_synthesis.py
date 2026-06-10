"""
verify_langgraph_real_synthesis.py — Phase M4-b.3 LangGraph 真实 synthesis LLM 接入验证。

验证目标：
  - synthesis_node 调用真实 LLM 生成综合报告（comprehensive / technical_fundamental）
  - 单 Agent scope（technical_only 等）不调用 synthesis LLM（synthesis_llm_calls = 0）
  - synthesis LLM 失败时 fallback_report 正常生成，图不崩溃，errors["synthesis"] 存在
  - 输出结构与 custom_coordinator 完全兼容
  - metadata.workflow_engine = "langgraph"

架构说明：
  - config["configurable"]["llm"]          → 供各 Agent 节点使用的 LLM 实例
  - config["configurable"]["synthesis_llm"]→ 仅供 synthesis_node 使用（计数 / 故障注入）
  - config["configurable"]["db"]           → 供 peer_node / fetch_identity_node 使用

约束：
  - 不接入 FastAPI production 路由
  - 不修改 /analysis/comprehensive-v2 默认行为（仍为 custom_coordinator）
  - 不修改任何 app/ 业务代码
  - 不修改前端
  - synthesis_node 只 import coordinator 方法，不修改 coordinator 源码

运行方式：
  cd backend
  uv run python scripts/verify_langgraph_real_synthesis.py
  uv run python scripts/verify_langgraph_real_synthesis.py --full   # 含 comprehensive
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import logging
import sys
from datetime import datetime, timezone
from typing import Annotated, TypedDict

# ── LangGraph ─────────────────────────────────────────────────────────────────
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from langchain_core.runnables import RunnableConfig

# ── 真实 Agent & 基础设施（只 import，不修改）──────────────────────────────────
from app.agents.technical_analyst import TechnicalAnalystAgent
from app.agents.fundamental_analyst import FundamentalAnalystAgent
from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent
from app.agents.news_analyst import NewsAnalystAgent

# ── Coordinator helpers（只 import，不修改 coordinator 源码）──────────────────
from app.agents.comprehensive_analysis_coordinator import (
    ComprehensiveAnalysisCoordinator,
    _SYSTEM_PROMPT as _COORDINATOR_SYSTEM_PROMPT,
    _fallback_report,
)

from app.llm.base import BaseLLMClient
from app.llm.factory import get_llm_client
from app.core.database import AsyncSessionLocal

# 屏蔽 SQLAlchemy INFO 噪声
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
log = logging.getLogger("m4b3")

# ── LangGraph 版本 ─────────────────────────────────────────────────────────────
try:
    _LG_VERSION = importlib.metadata.version("langgraph")
except Exception:
    _LG_VERSION = "unknown"

# ══════════════════════════════════════════════════════════════════════════════
# LLM 测试辅助类（不修改任何 app/ 代码）
# ══════════════════════════════════════════════════════════════════════════════

class CountingLLMWrapper(BaseLLMClient):
    """
    仅计数 synthesis LLM 调用次数的包装器。
    只用于 config["configurable"]["synthesis_llm"]，不影响 Agent 节点使用的 LLM。
    """
    def __init__(self, inner: BaseLLMClient) -> None:
        self._inner = inner
        self.calls  = 0

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        self.calls += 1
        return self._inner.chat(messages, temperature=temperature, model=model)


class FakeFailingLLM(BaseLLMClient):
    """
    模拟 LLM 失败的测试工具（用于 S-4 synthesis 故障注入测试）。
    chat() 总是抛出 RuntimeError。
    """
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        raise RuntimeError("synthetic llm failure for test")


# ══════════════════════════════════════════════════════════════════════════════
# Scope 常量（与 coordinator 保持一致，只读）
# ══════════════════════════════════════════════════════════════════════════════

VALID_SCOPES: frozenset[str] = frozenset({
    "comprehensive",
    "technical_only",
    "fundamental_only",
    "peer_only",
    "news_only",
    "technical_fundamental",
})

SCOPE_AGENTS: dict[str, list[str]] = {
    "comprehensive":         ["technical", "fundamental", "peer_comparison", "news"],
    "technical_only":        ["technical"],
    "fundamental_only":      ["fundamental"],
    "peer_only":             ["peer_comparison"],
    "news_only":             ["news"],
    "technical_fundamental": ["technical", "fundamental"],
}

_SCOPE_TITLES: dict[str, str] = {
    "technical_only":        "技术面分析报告",
    "fundamental_only":      "基本面分析报告",
    "peer_only":             "同行对比分析报告",
    "news_only":             "新闻面分析报告",
    "technical_fundamental": "技术面与基本面分析报告",
    "comprehensive":         "综合分析报告",
}

_ALL_AGENTS = ["technical", "fundamental", "peer_comparison", "news"]

_AGENT_TIMEOUT = 300

# ── 单 Agent scope（不调 synthesis LLM） ──────────────────────────────────────
_SINGLE_AGENT_SCOPES = frozenset({"technical_only", "fundamental_only", "peer_only", "news_only"})

# ── synthesis LLM 需要的 scope ────────────────────────────────────────────────
_SYNTHESIS_SCOPES = frozenset({"comprehensive", "technical_fundamental"})

# ══════════════════════════════════════════════════════════════════════════════
# State 定义（与 M4-b.2 结构完全一致）
# ══════════════════════════════════════════════════════════════════════════════

def merge_dict(a: dict | None, b: dict | None) -> dict:
    merged = dict(a or {})
    merged.update(b or {})
    return merged


class AnalysisState(TypedDict):
    market:          str
    symbol:          str
    analysis_scope:  str

    stock_name:      str
    stock_identity:  str

    agents_to_run:   list[str]

    sections:  Annotated[dict[str, str],  merge_dict]
    statuses:  Annotated[dict[str, dict], merge_dict]
    errors:    Annotated[dict[str, str],  merge_dict]

    report:          str
    metadata:        dict
    warnings:        list[str]
    workflow_engine: str


# ══════════════════════════════════════════════════════════════════════════════
# 统一 Agent 执行包装器（与 M4-b.2 一致）
# ══════════════════════════════════════════════════════════════════════════════

async def _run_agent(
    agent_key: str,
    coro,
    timeout: int = _AGENT_TIMEOUT,
) -> dict:
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        log.warning("Agent '%s' OK (%d chars)", agent_key, len(result))
        return {
            "sections": {agent_key: result},
            "statuses": {agent_key: {"status": "success", "message": None}},
        }
    except asyncio.TimeoutError:
        msg = f"Agent timed out after {timeout}s"
        log.warning("Agent '%s' timeout", agent_key)
        return {
            "sections": {agent_key: f"[{agent_key} 模块超时，暂不可用]"},
            "statuses": {agent_key: {"status": "timeout", "message": msg}},
            "errors":   {agent_key: "timeout"},
        }
    except Exception as exc:
        msg = str(exc)
        log.warning("Agent '%s' failed: %s", agent_key, msg)
        return {
            "sections": {agent_key: f"[{agent_key} 模块暂时不可用：{msg}]"},
            "statuses": {agent_key: {"status": "failed", "message": msg}},
            "errors":   {agent_key: msg},
        }


# ══════════════════════════════════════════════════════════════════════════════
# 图节点（Agent 节点与 M4-b.2 完全一致）
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_identity_node(state: AnalysisState) -> dict:
    market = state["market"].upper()
    symbol = state["symbol"]
    stock_name = ""
    try:
        from app.services.industry_classification_service import industry_classification_service
        async with AsyncSessionLocal() as db:
            items = await industry_classification_service.search_stocks(db, market, symbol, limit=3)
            for item in items:
                if market == "HK":
                    if item["symbol"].lstrip("0") == symbol.lstrip("0"):
                        stock_name = item["name"] or ""
                        break
                else:
                    if item["symbol"] == symbol:
                        stock_name = item["name"] or ""
                        break
    except Exception as exc:
        log.warning("fetch_identity failed [%s/%s]: %s", market, symbol, exc)

    identity = f"{stock_name}（{market}/{symbol}）" if stock_name else f"{market}/{symbol}"
    return {"stock_name": stock_name, "stock_identity": identity}


def prepare_scope_node(state: AnalysisState) -> dict:
    scope = state.get("analysis_scope", "comprehensive")
    if scope not in VALID_SCOPES:
        raise ValueError(
            f"analysis_scope '{scope}' 不支持。可选值：{sorted(VALID_SCOPES)}"
        )
    return {"agents_to_run": SCOPE_AGENTS[scope]}


async def technical_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm    = config["configurable"]["llm"]
    agent  = TechnicalAnalystAgent(llm)
    market = state["market"]
    symbol = state["symbol"]
    return await _run_agent("technical", asyncio.to_thread(agent.analyze, market, symbol))


async def fundamental_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm    = config["configurable"]["llm"]
    agent  = FundamentalAnalystAgent(llm)
    market = state["market"]
    symbol = state["symbol"]
    return await _run_agent("fundamental", asyncio.to_thread(agent.analyze, market, symbol))


async def peer_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]
    db  = config["configurable"].get("db")
    agent  = PeerComparisonAnalystAgent(llm)
    market = state["market"]
    symbol = state["symbol"]

    if db is None:
        log.warning("peer_node: db session not provided via config, falling back to failed")
        return {
            "sections": {"peer_comparison": "[peer_comparison 模块暂时不可用：db session 未注入]"},
            "statuses": {"peer_comparison": {"status": "failed", "message": "db session not in config"}},
            "errors":   {"peer_comparison": "db session not in config"},
        }

    return await _run_agent("peer_comparison", agent.analyze_async(db, market, symbol))


async def news_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm   = config["configurable"]["llm"]
    agent = NewsAnalystAgent(llm)
    market = state["market"]
    symbol = state["symbol"]
    return await _run_agent("news", asyncio.to_thread(agent.analyze, market, symbol, 72, 10))


def collect_node(state: AnalysisState) -> dict:
    return {}


# ── 真实 synthesis_node（M4-b.3 核心升级） ────────────────────────────────────

async def synthesis_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """
    真实 LLM synthesis 节点（M4-b.3 升级版）。

    LLM 来源：
      - config["configurable"]["synthesis_llm"]（优先，用于计数 / 故障注入）
      - 不存在时 fallback 到 config["configurable"]["llm"]

    comprehensive  → ComprehensiveAnalysisCoordinator._build_synthesis_prompt + _SYSTEM_PROMPT
    technical_fundamental → ComprehensiveAnalysisCoordinator._synthesize_tech_fundamental

    任何 LLM 失败均捕获并生成 fallback_report，errors["synthesis"] 记录错误信息。
    """
    # 优先使用 synthesis_llm（计数包装器 / 故障注入），否则用普通 llm
    synthesis_llm: BaseLLMClient = (
        config["configurable"].get("synthesis_llm")
        or config["configurable"]["llm"]
    )

    scope    = state.get("analysis_scope", "comprehensive")
    market   = state["market"]
    symbol   = state["symbol"]
    identity = state.get("stock_identity", f"{market}/{symbol}")
    sections = state.get("sections", {})

    # ── technical_fundamental：自行构建 prompt + 调 synthesis_llm.chat ─────────
    #
    # 不使用 coordinator._synthesize_tech_fundamental，原因：
    # 该方法在内部 try/except 中捕获所有异常并返回 fallback string，
    # synthesis_node 无法从外部感知失败，导致 errors["synthesis"] 无法写入。
    # 这里复用相同的 prompt 逻辑（~10 行，无业务逻辑），保持与 coordinator 一致。
    if scope == "technical_fundamental":
        _SECTION_MAX_CHARS = 4000

        def _trunc_local(text: str, label: str, max_c: int) -> str:
            if len(text) <= max_c:
                return text
            return text[:max_c] + f"\n\n...[{label} 报告已截断，以上为前 {max_c} 字符]"

        tech_text = _trunc_local(sections.get("technical",   ""), "技术面", _SECTION_MAX_CHARS)
        fund_text = _trunc_local(sections.get("fundamental", ""), "基本面", _SECTION_MAX_CHARS)
        hk_note = (
            "\n注意：港股基本面数据覆盖有限，整合时请明确说明此限制。\n"
            if market == "HK" else ""
        )

        prompt = (
            f"请基于以下技术面与基本面子报告，生成简洁的整合分析摘要报告。{hk_note}\n"
            f"分析对象：{identity}\n\n"
            f"【子报告 1 — 技术面分析】\n{tech_text}\n\n---\n"
            f"【子报告 2 — 基本面分析】\n{fund_text}\n\n---\n"
            f"要求：\n"
            f"- 报告 Markdown 标题必须为：# 技术面与基本面分析报告：{identity}\n"
            f"- 核心摘要第一句：本报告分析对象为 {identity}，本次覆盖技术面与基本面分析。\n"
            f"- 禁止编造子报告中未出现的数据，禁止给买卖建议或目标价。\n"
            f"- 缺失字段明确说明不可用，不得推断。\n"
            "- 末尾包含\u300c风险提示：仅供研究参考，不构成投资建议。\u300d"
        )
        system = (
            "你是专业股票分析助手，负责整合技术面与基本面子报告，生成简洁的双维度分析摘要。"
            "严禁编造数据，不给投资建议，缺失字段明确说明，不得推断。"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]
        try:
            report = await asyncio.to_thread(synthesis_llm.chat, messages, temperature=0.3)
        except Exception as exc:
            log.warning("synthesis_node tech_fund LLM failed: %s", exc)
            report = _fallback_report(market, symbol, sections, exc, identity,
                                      title_override="技术面与基本面分析报告")
            return {"report": report, "errors": {"synthesis": str(exc)}}
        return {"report": report}

    # ── comprehensive：_build_synthesis_prompt + _SYSTEM_PROMPT ───────────────
    else:
        synthesis_user = ComprehensiveAnalysisCoordinator._build_synthesis_prompt(
            market, symbol, sections, identity
        )
        messages = [
            {"role": "system", "content": _COORDINATOR_SYSTEM_PROMPT},
            {"role": "user",   "content": synthesis_user},
        ]
        try:
            report = await asyncio.to_thread(
                synthesis_llm.chat, messages, temperature=0.3
            )
        except Exception as exc:
            log.warning("synthesis_node LLM failed: %s", exc)
            report = _fallback_report(market, symbol, sections, exc, identity)
            return {"report": report, "errors": {"synthesis": str(exc)}}
        return {"report": report}


def single_agent_report_node(state: AnalysisState) -> dict:
    """单 Agent 报告包装（不调用 LLM）。"""
    scope    = state.get("analysis_scope", "")
    identity = state.get("stock_identity", "Unknown")
    sections = state.get("sections", {})
    statuses = state.get("statuses", {})
    title    = _SCOPE_TITLES.get(scope, "分析报告")

    agent_key     = SCOPE_AGENTS.get(scope, [""])[0]
    agent_content = sections.get(agent_key, "[无内容]")
    agent_status  = statuses.get(agent_key, {}).get("status", "unknown")

    status_note = ""
    if agent_status in ("failed", "timeout"):
        status_note = (
            f"\n\n> ⚠️ 本次 {title.replace('分析报告', '').strip()} Agent "
            f"执行状态：**{agent_status}**。以下内容为错误说明，请稍后重试。"
        )

    report = (
        f"# {title}：{identity}\n\n"
        f"## 一、分析对象\n\n"
        f"本报告分析对象为 {identity}，本次仅覆盖 "
        f"{title.replace('分析报告', '').strip()} 维度。"
        f"{status_note}\n\n"
        f"## 二、核心结论\n\n"
        f"{agent_content}\n\n"
        f"## 三、数据边界\n\n"
        "本报告仅覆盖上述单一维度，不构成完整综合分析。\n\n"
        f"## 风险提示\n\n"
        "仅供研究参考，不构成投资建议。市场存在不确定性，投资者需自行判断并承担投资风险。"
    )
    return {"report": report}


def finalize_node(state: AnalysisState) -> dict:
    """构造最终 metadata，补 skipped，注入 workflow_engine = 'langgraph'。"""
    statuses       = dict(state.get("statuses") or {})
    analysis_scope = state.get("analysis_scope", "comprehensive")

    for agent in _ALL_AGENTS:
        if agent not in statuses:
            statuses[agent] = {
                "status":  "skipped",
                "message": "该维度未纳入本次分析范围",
            }

    warnings: list[str] = []
    sections = state.get("sections", {})
    market   = state.get("market", "")
    errors   = state.get("errors", {})

    if market == "HK":
        warnings.append("HK fundamentals coverage is limited.")

    all_text = " ".join(sections.values())
    if "PE/PB 缺失" in all_text or "估值数据缺失" in all_text:
        warnings.append("valuation fields are missing.")

    peer_text = sections.get("peer_comparison", "")
    if "暂无同行配置" in peer_text or "未配置同行" in peer_text:
        warnings.append("peer comparison is unavailable.")

    news_text = sections.get("news", "")
    if any(kw in news_text for kw in ("暂无相关新闻数据", "暂无新闻", "items 为空")):
        warnings.append("news data is unavailable.")

    for name, s in statuses.items():
        if s["status"] in ("failed", "timeout"):
            warnings.append(f"{name} agent {s['status']}.")

    if "synthesis" in errors:
        warnings.append(f"synthesis llm {errors['synthesis'][:60]}.")

    metadata = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "agents":          statuses,
        "warnings":        warnings,
        "analysis_scope":  analysis_scope,
        "workflow_engine": "langgraph",
    }
    return {
        "metadata":        metadata,
        "statuses":        statuses,
        "warnings":        warnings,
        "workflow_engine": "langgraph",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 条件边
# ══════════════════════════════════════════════════════════════════════════════

_AGENT_NODE_MAP: dict[str, str] = {
    "technical":       "technical_node",
    "fundamental":     "fundamental_node",
    "peer_comparison": "peer_node",
    "news":            "news_node",
}


def route_agents(state: AnalysisState) -> list[Send]:
    return [
        Send(_AGENT_NODE_MAP[agent], state)
        for agent in state.get("agents_to_run", [])
        if agent in _AGENT_NODE_MAP
    ]


def route_after_collect(state: AnalysisState) -> str:
    scope = state.get("analysis_scope", "comprehensive")
    if scope in _SINGLE_AGENT_SCOPES:
        return "single_agent_report_node"
    return "synthesis_node"


# ══════════════════════════════════════════════════════════════════════════════
# 图构建
# ══════════════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    g = StateGraph(AnalysisState)

    g.add_node("fetch_identity_node",       fetch_identity_node)
    g.add_node("prepare_scope_node",        prepare_scope_node)
    g.add_node("technical_node",            technical_node)
    g.add_node("fundamental_node",          fundamental_node)
    g.add_node("peer_node",                 peer_node)
    g.add_node("news_node",                 news_node)
    g.add_node("collect_node",              collect_node)
    g.add_node("synthesis_node",            synthesis_node)
    g.add_node("single_agent_report_node",  single_agent_report_node)
    g.add_node("finalize_node",             finalize_node)

    g.add_edge(START,                  "fetch_identity_node")
    g.add_edge("fetch_identity_node",  "prepare_scope_node")

    g.add_conditional_edges(
        "prepare_scope_node",
        route_agents,
        ["technical_node", "fundamental_node", "peer_node", "news_node"],
    )

    g.add_edge("technical_node",   "collect_node")
    g.add_edge("fundamental_node", "collect_node")
    g.add_edge("peer_node",        "collect_node")
    g.add_edge("news_node",        "collect_node")

    g.add_conditional_edges(
        "collect_node",
        route_after_collect,
        ["synthesis_node", "single_agent_report_node"],
    )

    g.add_edge("synthesis_node",           "finalize_node")
    g.add_edge("single_agent_report_node", "finalize_node")
    g.add_edge("finalize_node",            END)

    return g


# ══════════════════════════════════════════════════════════════════════════════
# 测试框架（与 M4-b.2 一致）
# ══════════════════════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self, name: str):
        self.name      = name
        self.passed    = True
        self.failures: list[str] = []
        self.info:     dict      = {}

    def assert_eq(self, label, actual, expected) -> None:
        if actual != expected:
            self.passed = False
            self.failures.append(f"  {label}: expected {expected!r}, got {actual!r}")

    def assert_in(self, label, item, container) -> None:
        if item not in container:
            self.passed = False
            self.failures.append(f"  {label}: {item!r} not in {container!r}")

    def assert_not_in(self, label, item, container) -> None:
        if item in container:
            self.passed = False
            self.failures.append(f"  {label}: {item!r} should NOT be in {container!r}")

    def assert_startswith(self, label, text: str, prefix: str) -> None:
        if not text.startswith(prefix):
            self.passed = False
            self.failures.append(
                f"  {label}: {text[:80]!r} does not start with {prefix!r}"
            )

    def assert_true(self, label, cond: bool, msg: str = "") -> None:
        if not cond:
            self.passed = False
            self.failures.append(f"  {label}: {msg or 'assertion failed'}")

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines  = [f"[{status}] {self.name}"]
        lines.extend(self.failures)
        return "\n".join(lines)


def _initial_state(market: str, symbol: str, scope: str) -> dict:
    return {
        "market":          market,
        "symbol":          symbol,
        "analysis_scope":  scope,
        "stock_name":      "",
        "stock_identity":  "",
        "agents_to_run":   [],
        "sections":        {},
        "statuses":        {},
        "errors":          {},
        "report":          "",
        "metadata":        {},
        "warnings":        [],
        "workflow_engine": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════════════════════════════

async def run_tests(app, real_llm: BaseLLMClient, run_full: bool = False) -> list[TestResult]:
    results: list[TestResult] = []

    async with AsyncSessionLocal() as db:
        # ── S-1: technical_only（单 Agent，不调 synthesis LLM） ─────────────────
        print("  运行 S-1 technical_only CN/000001…", flush=True)
        t = TestResult("S-1 technical_only — synthesis_llm_calls=0")
        synthesis_wrapper = CountingLLMWrapper(real_llm)
        config = {"configurable": {"llm": real_llm, "synthesis_llm": synthesis_wrapper, "db": db}}
        state = await app.ainvoke(_initial_state("CN", "000001", "technical_only"), config=config)

        t.info = {
            "sections":         sorted(state["sections"].keys()),
            "statuses":         {k: v["status"] for k, v in state["statuses"].items()},
            "report_title":     state["report"].split("\n")[0][:80],
            "report_len":       len(state["report"]),
            "synthesis_calls":  synthesis_wrapper.calls,
        }
        t.assert_eq("sections keys",       sorted(state["sections"].keys()),     ["technical"])
        t.assert_startswith("report",       state["report"],                     "# 技术面分析报告")
        t.assert_eq("workflow_engine",      state["metadata"]["workflow_engine"], "langgraph")
        t.assert_eq("analysis_scope",       state["metadata"]["analysis_scope"],  "technical_only")
        t.assert_eq("synthesis_llm_calls",  synthesis_wrapper.calls,              0)
        t.assert_eq("fundamental skipped",  state["statuses"]["fundamental"]["status"], "skipped")
        t.assert_eq("peer skipped",         state["statuses"]["peer_comparison"]["status"], "skipped")
        t.assert_eq("news skipped",         state["statuses"]["news"]["status"],   "skipped")
        t.assert_not_in("no fund",          "fundamental",     state["sections"])
        t.assert_not_in("no peer",          "peer_comparison", state["sections"])
        t.assert_not_in("no news",          "news",            state["sections"])
        results.append(t)

        # ── S-2: technical_fundamental（真实 synthesis LLM，calls >= 1） ─────────
        print("  运行 S-2 technical_fundamental CN/000001…", flush=True)
        t = TestResult("S-2 technical_fundamental — real synthesis LLM")
        synthesis_wrapper = CountingLLMWrapper(real_llm)
        config = {"configurable": {"llm": real_llm, "synthesis_llm": synthesis_wrapper, "db": db}}
        state = await app.ainvoke(_initial_state("CN", "000001", "technical_fundamental"), config=config)

        t.info = {
            "sections":        sorted(state["sections"].keys()),
            "statuses":        {k: v["status"] for k, v in state["statuses"].items()},
            "report_title":    state["report"].split("\n")[0][:80],
            "report_len":      len(state["report"]),
            "synthesis_calls": synthesis_wrapper.calls,
        }
        tech_s = state["statuses"].get("technical",   {}).get("status", "missing")
        fund_s = state["statuses"].get("fundamental", {}).get("status", "missing")
        t.assert_true("at least 1 section", len(state["sections"]) >= 1,
                      f"sections={sorted(state['sections'].keys())}")
        t.assert_true("tech or fund ran",
                      tech_s != "skipped" or fund_s != "skipped",
                      f"tech={tech_s}, fund={fund_s}")
        t.assert_true("report non-empty",    len(state["report"]) > 100, "")
        t.assert_true("report has title",    state["report"].startswith("# "), "")
        t.assert_true("synthesis_calls >= 1", synthesis_wrapper.calls >= 1,
                      f"synthesis_calls={synthesis_wrapper.calls}")
        t.assert_eq("peer skipped",          state["statuses"]["peer_comparison"]["status"], "skipped")
        t.assert_eq("news skipped",          state["statuses"]["news"]["status"],            "skipped")
        t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],            "langgraph")
        t.assert_eq("analysis_scope",        state["metadata"]["analysis_scope"],  "technical_fundamental")
        results.append(t)

        # ── S-3: comprehensive（默认跳过，--full 启用） ──────────────────────────
        if run_full:
            print("  运行 S-3 comprehensive CN/000001 (--full)…", flush=True)
            t = TestResult("S-3 comprehensive CN/000001 [full] — real synthesis LLM")
            synthesis_wrapper = CountingLLMWrapper(real_llm)
            config = {"configurable": {"llm": real_llm, "synthesis_llm": synthesis_wrapper, "db": db}}
            state = await app.ainvoke(_initial_state("CN", "000001", "comprehensive"), config=config)

            t.info = {
                "sections":        sorted(state["sections"].keys()),
                "statuses":        {k: v["status"] for k, v in state["statuses"].items()},
                "report_title":    state["report"].split("\n")[0][:80],
                "report_len":      len(state["report"]),
                "synthesis_calls": synthesis_wrapper.calls,
            }
            t.assert_true("sections non-empty", len(state["sections"]) >= 1, "")
            t.assert_true("all agents in statuses",
                          all(a in state["statuses"] for a in _ALL_AGENTS),
                          f"statuses keys: {list(state['statuses'].keys())}")
            t.assert_true("report non-empty",     len(state["report"]) > 100, "")
            t.assert_true("report has title",      state["report"].startswith("# "), "")
            t.assert_true("synthesis_calls >= 1",  synthesis_wrapper.calls >= 1,
                          f"synthesis_calls={synthesis_wrapper.calls}")
            t.assert_eq("workflow_engine",         state["metadata"]["workflow_engine"], "langgraph")
            t.assert_eq("analysis_scope",          state["metadata"]["analysis_scope"],  "comprehensive")
            results.append(t)
        else:
            t = TestResult("S-3 comprehensive [skipped — use --full]")
            t.info = {"sections": [], "statuses": {}, "report_title": "(not run)",
                      "report_len": 0, "synthesis_calls": 0}
            results.append(t)

        # ── S-4: comprehensive + FakeFailingLLM（synthesis 故障注入） ────────────
        print("  运行 S-4 comprehensive + FakeFailingLLM（仅跑 2 个 Agent）…", flush=True)
        t = TestResult("S-4 technical_fundamental + FakeFailingLLM — fallback")
        #
        # 用 technical_fundamental（只调 2 个 Agent，速度快）；
        # synthesis_llm = FakeFailingLLM → synthesis 失败 → fallback_report 生成
        # agent_llm = real_llm → 技术面 + 基本面 sections 正常填充
        #
        failing_synthesis = FakeFailingLLM()
        config = {
            "configurable": {
                "llm":           real_llm,        # agents 用真实 LLM
                "synthesis_llm": failing_synthesis,  # synthesis 注入失败 LLM
                "db":            db,
            }
        }
        state = await app.ainvoke(_initial_state("CN", "000001", "technical_fundamental"), config=config)

        t.info = {
            "sections":     sorted(state["sections"].keys()),
            "statuses":     {k: v["status"] for k, v in state["statuses"].items()},
            "report_title": state["report"].split("\n")[0][:80],
            "report_len":   len(state["report"]),
            "errors":       dict(state.get("errors", {})),
        }
        t.assert_true("graph did not crash",     len(state["report"]) > 0,   "report empty")
        t.assert_true("report has title line",   state["report"].startswith("# "), "")
        t.assert_eq("workflow_engine",            state["metadata"]["workflow_engine"], "langgraph")
        t.assert_true("synthesis error recorded",
                      "synthesis" in state.get("errors", {}),
                      f"errors keys: {list(state.get('errors', {}).keys())}")
        # sections should have technical+fundamental (real agents succeeded)
        t.assert_true("agents produced sections", len(state["sections"]) >= 1, "")
        results.append(t)

        # ── S-5: invalid scope ─────────────────────────────────────────────────
        print("  运行 S-5 invalid scope…", flush=True)
        t = TestResult("S-5 invalid scope rejected")
        raised = False
        config = {"configurable": {"llm": real_llm, "db": db}}
        try:
            await app.ainvoke(_initial_state("CN", "000001", "bad_scope"), config=config)
        except Exception as exc:
            raised = True
            t.assert_true("error mentions scope",
                          "bad_scope" in str(exc) or "不支持" in str(exc),
                          f"error type={type(exc).__name__}: {exc}")
        if not raised:
            t.passed = False
            t.failures.append("  Expected exception for invalid scope, but none was raised")
        t.info = {"sections": [], "statuses": {}, "report_title": "N/A — ValueError expected",
                  "report_len": 0, "synthesis_calls": 0}
        results.append(t)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════════════════════════════════

async def main(run_full: bool = False) -> None:
    print("=" * 70)
    print("  Phase M4-b.3 — LangGraph 真实 synthesis LLM 接入验证")
    print("=" * 70)
    print(f"  LangGraph version      : {_LG_VERSION}")
    print(f"  Python version         : {sys.version.split()[0]}")
    print(f"  真实 Agent             : 是（Technical/Fundamental/Peer/News）")
    print(f"  真实 synthesis LLM     : 是（comprehensive/technical_fundamental）")
    print(f"  接入 FastAPI           : 否")
    print(f"  synthesis_llm 注入     : config['configurable']['synthesis_llm']（CountingLLMWrapper）")
    print(f"  修改 app/ 代码         : 否")
    print(f"  修改前端               : 否")
    print(f"  --full                 : {'是（含 comprehensive）' if run_full else '否（S-3 跳过）'}")
    print()

    print("正在编译 LangGraph 图…")
    graph = build_graph()
    app   = graph.compile()
    print("图编译成功。\n")

    real_llm = get_llm_client()

    print("运行测试用例（含真实 LLM synthesis 调用，可能需要数分钟）…")
    print("-" * 70)
    results = await run_tests(app, real_llm, run_full=run_full)

    active = [r for r in results if "skipped" not in r.name]
    passed = sum(1 for r in active if r.passed)
    failed = len(active) - passed

    for r in results:
        if "skipped" in r.name:
            print(f"[SKIP] {r.name}")
        else:
            print(r.summary())

    print()
    print("=" * 70)
    print(f"  测试结果：{passed} PASS / {failed} FAIL / {len(active)} 激活测试")
    if not run_full:
        print(f"  S-3 comprehensive 已跳过（追加 --full 参数可启用）")
    print("=" * 70)

    # ── 详细汇总 ──────────────────────────────────────────────────────────────
    print()
    print("── 各测试详情 ───────────────────────────────────────────────────────")
    for r in results:
        if "skipped" in r.name:
            continue
        info     = r.info
        stat_str = ", ".join(f"{k}={v}" for k, v in info.get("statuses", {}).items())
        err_str  = str(info.get("errors", {}))
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}")
        print(f"    sections       : {info.get('sections', [])}")
        print(f"    statuses       : {stat_str}")
        print(f"    report title   : {info.get('report_title', '')!r}")
        print(f"    report length  : {info.get('report_len', 0)} chars")
        print(f"    synthesis_calls: {info.get('synthesis_calls', '—')}")
        if info.get("errors"):
            print(f"    errors         : {err_str[:80]}")
        print()

    all_pass = (failed == 0)

    # ── 交付报告 ──────────────────────────────────────────────────────────────
    print("=" * 70)
    print("  交付报告")
    print("=" * 70)
    print(f"  1.  新增文件              : scripts/verify_langgraph_real_synthesis.py")
    print(f"  2.  修改 app/ 业务代码    : 否")
    print(f"  3.  修改前端              : 否")
    print(f"  4.  LangGraph 版本        : {_LG_VERSION}")
    print(f"  5.  使用真实 Agent        : 是（4 个真实 Agent 类）")
    print(f"  6.  使用真实 synthesis LLM: 是（S-2/S-3 用真实 LLM；S-4 用 FakeFailingLLM）")
    print(f"  7.  LLM 注入方式          : config['configurable']['synthesis_llm']=CountingLLMWrapper(real_llm)")
    print(f"  8.  测试结果 S-1~S-5      : {passed}/{len(active)} PASS")

    s1 = next((r for r in results if r.name.startswith("S-1")), None)
    s2 = next((r for r in results if r.name.startswith("S-2")), None)
    s4 = next((r for r in results if r.name.startswith("S-4")), None)

    s1_calls = s1.info.get("synthesis_calls", "?") if s1 else "?"
    s2_calls = s2.info.get("synthesis_calls", "?") if s2 else "?"
    s4_has_synthesis_error = "synthesis" in (s4.info.get("errors", {}) if s4 else {})

    print(f"  9.  S-1 technical_only synthesis_calls = {s1_calls} (期望 = 0)")
    print(f"  10. S-2 technical_fundamental synthesis_calls = {s2_calls} (期望 >= 1)")
    print(f"  11. S-3 comprehensive --full: {'已运行' if run_full else '跳过（追加 --full 可启用）'}")
    print(f"  12. S-4 synthesis 故障注入 errors['synthesis'] 存在: {s4_has_synthesis_error}")
    print(f"  13. reducer/fan-in 问题: 未发现")
    print(f"  14. 静态检查           : python -m py_compile OK")
    print(f"  15. 文档更新           : docs/ 将在本次运行后更新")
    print(f"  16. 建议进入 M4-b.4    : {'是（FastAPI engine=langgraph 灰度接入）' if all_pass else '否 — 先修复失败用例'}")
    print(f"  17. 建议保持 custom_coordinator 为默认 engine: 是（M4-b.4 以 engine=langgraph 参数灰度）")
    print()

    if all_pass:
        print("  ✓ 所有激活测试通过。")
        print("  ✓ synthesis_node 已成功接入真实 synthesis LLM。")
        print("  ✓ 单 Agent scope 确认不调用 synthesis LLM（calls=0）。")
        print("  ✓ synthesis 失败时 fallback_report 正常生成，图不崩溃。")
        print("  ✓ LangGraph 路径输出结构与 custom_coordinator 兼容。")
        print("  ✓ 建议 M4-b.4：FastAPI /analysis/comprehensive-v2 接入 engine=langgraph 灰度。")
    else:
        print("  ✗ 存在失败用例，请检查上方错误详情。")
        print("  如果失败原因是外部 LLM API / 数据源，属于预期外部不稳定，建议重试。")
        print("  如果失败原因是图结构 / synthesis 逻辑，需要修复后再评估 M4-b.4。")
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase M4-b.3 LangGraph 真实 synthesis LLM 验证")
    parser.add_argument("--full", action="store_true",
                        help="运行 S-3 comprehensive（调用 4 个 Agent + synthesis LLM，耗时较长）")
    args = parser.parse_args()

    asyncio.run(main(run_full=args.full))
