"""
langgraph_analysis_graph.py — LangGraph 分析图（M4-b.4 灰度接入版）。

提供 LangGraphAnalysisRunner，接口与 ComprehensiveAnalysisCoordinator.analyze_scoped() 完全兼容。
通过 POST /analysis/comprehensive-v2?engine=langgraph 接入，默认仍为 custom_coordinator。

设计原则：
  - 不修改 ComprehensiveAnalysisCoordinator 及任何现有 Agent。
  - 只 import 现有模块方法，不重写业务逻辑。
  - 返回 dict 与 ComprehensiveV2Response 字段完全对齐。
  - 单个 Agent 失败不导致整图崩溃（_run_agent 包装器）。
  - synthesis LLM 失败 → errors["synthesis"] 记录，_fallback_report 生成降级报告。
  - metadata.workflow_engine = "langgraph"。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.technical_analyst import TechnicalAnalystAgent
from app.agents.fundamental_analyst import FundamentalAnalystAgent
from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent
from app.agents.news_analyst import NewsAnalystAgent

# ── coordinator helpers（只 import，不修改） ────────────────────────────────────
# _synthesize_tech_fundamental 因内部 swallow exception 不复用，见 synthesis_node
from app.agents.comprehensive_analysis_coordinator import (
    ComprehensiveAnalysisCoordinator,
    VALID_SCOPES,
    SCOPE_AGENTS,
    OUTPUT_LANGUAGE_LABELS,
    _SYSTEM_PROMPT,
    _fallback_report,
    _build_metadata,
    _build_single_agent_report,
    _trunc,
)

log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
_AGENT_TIMEOUT    = 300
_SECTION_MAX_CHARS = 4000

_SCOPE_TITLES: dict[str, str] = {
    "technical_only":        "技术面分析报告",
    "fundamental_only":      "基本面分析报告",
    "peer_only":             "同行对比分析报告",
    "news_only":             "新闻面分析报告",
    "technical_fundamental": "技术面与基本面分析报告",
    "comprehensive":         "综合分析报告",
}

_ALL_AGENTS = ["technical", "fundamental", "peer_comparison", "news"]
_SINGLE_AGENT_SCOPES = frozenset({"technical_only", "fundamental_only", "peer_only", "news_only"})

# ══════════════════════════════════════════════════════════════════════════════
# State 定义
# ══════════════════════════════════════════════════════════════════════════════

def _merge_dict(a: dict | None, b: dict | None) -> dict:
    """Annotated reducer：合并两个 dict，b 覆盖 a 的同名 key。"""
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

    # 并发写入字段，使用 reducer 确保正确合并
    sections:  Annotated[dict[str, str],  _merge_dict]
    statuses:  Annotated[dict[str, dict], _merge_dict]
    errors:    Annotated[dict[str, str],  _merge_dict]

    output_language: str

    report:          str
    metadata:        dict
    warnings:        list[str]
    workflow_engine: str


# ══════════════════════════════════════════════════════════════════════════════
# 统一 Agent 执行包装器
# ══════════════════════════════════════════════════════════════════════════════

async def _run_agent(agent_key: str, coro, timeout: int = _AGENT_TIMEOUT) -> dict:
    """
    统一包装单个 Agent 执行，捕获所有异常。
    成功 → sections[key] = result, statuses[key].status = "success"
    超时 → status = "timeout"
    异常 → status = "failed"
    任何情况下均返回合法 dict，不传播到图层。
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        log.info("LangGraph Agent '%s' OK (%d chars)", agent_key, len(result))
        return {
            "sections": {agent_key: result},
            "statuses": {agent_key: {"status": "success", "message": None}},
        }
    except asyncio.TimeoutError:
        msg = f"Agent timed out after {timeout}s"
        log.warning("LangGraph Agent '%s' timeout", agent_key)
        return {
            "sections": {agent_key: f"[{agent_key} 模块超时，暂不可用]"},
            "statuses": {agent_key: {"status": "timeout", "message": msg}},
            "errors":   {agent_key: "timeout"},
        }
    except Exception as exc:
        msg = str(exc)
        log.warning("LangGraph Agent '%s' failed: %s", agent_key, msg)
        return {
            "sections": {agent_key: f"[{agent_key} 模块暂时不可用：{msg}]"},
            "statuses": {agent_key: {"status": "failed", "message": msg}},
            "errors":   {agent_key: msg},
        }


# ══════════════════════════════════════════════════════════════════════════════
# 图节点
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_identity_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """
    查询股票中文名，构建完整身份标识。
    复用 ComprehensiveAnalysisCoordinator._fetch_stock_name（static method）。
    """
    market = state["market"].upper()
    symbol = state["symbol"]
    db: AsyncSession | None = config["configurable"].get("db")

    stock_name = ""
    if db is not None:
        try:
            stock_name = await ComprehensiveAnalysisCoordinator._fetch_stock_name(
                db, market, symbol
            ) or ""
        except Exception as exc:
            log.warning("LangGraph fetch_identity failed [%s/%s]: %s", market, symbol, exc)

    identity = f"{stock_name}（{market}/{symbol}）" if stock_name else f"{market}/{symbol}"
    return {"stock_name": stock_name, "stock_identity": identity}


def _prepare_scope_node(state: AnalysisState) -> dict:
    """校验 analysis_scope，写入 agents_to_run。"""
    scope = state.get("analysis_scope", "comprehensive")
    if scope not in VALID_SCOPES:
        raise ValueError(
            f"analysis_scope '{scope}' 不支持。可选值：{sorted(VALID_SCOPES)}"
        )
    return {"agents_to_run": SCOPE_AGENTS[scope]}


async def _technical_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm             = config["configurable"]["llm"]
    agent           = TechnicalAnalystAgent(llm)
    market          = state["market"]
    symbol          = state["symbol"]
    output_language = state.get("output_language", "zh-CN")
    return await _run_agent(
        "technical",
        asyncio.to_thread(agent.analyze, market, symbol, output_language),
    )


async def _fundamental_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm             = config["configurable"]["llm"]
    agent           = FundamentalAnalystAgent(llm)
    market          = state["market"]
    symbol          = state["symbol"]
    output_language = state.get("output_language", "zh-CN")
    return await _run_agent(
        "fundamental",
        asyncio.to_thread(agent.analyze, market, symbol, output_language),
    )


async def _peer_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm             = config["configurable"]["llm"]
    db: AsyncSession | None = config["configurable"].get("db")
    agent           = PeerComparisonAnalystAgent(llm)
    market          = state["market"]
    symbol          = state["symbol"]
    output_language = state.get("output_language", "zh-CN")

    if db is None:
        log.warning("LangGraph peer_node: db session not provided, degrading to failed")
        return {
            "sections": {"peer_comparison": "[peer_comparison 模块暂时不可用：db session 未注入]"},
            "statuses": {"peer_comparison": {"status": "failed", "message": "db session not in config"}},
            "errors":   {"peer_comparison": "db session not in config"},
        }

    return await _run_agent(
        "peer_comparison",
        agent.analyze_async(db, market, symbol, output_language),
    )


async def _news_node(state: AnalysisState, config: RunnableConfig) -> dict:
    llm             = config["configurable"]["llm"]
    agent           = NewsAnalystAgent(llm)
    market          = state["market"]
    symbol          = state["symbol"]
    output_language = state.get("output_language", "zh-CN")
    return await _run_agent(
        "news",
        asyncio.to_thread(agent.analyze, market, symbol, 72, 10, output_language),
    )


def _collect_node(state: AnalysisState) -> dict:
    """fan-in 汇聚点，所有 Agent 分支在此收敛，本身不做计算。"""
    return {}


async def _synthesis_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """
    真实 LLM synthesis 节点。

    comprehensive  → _build_synthesis_prompt（coordinator static method）+ _SYSTEM_PROMPT + llm.chat
    technical_fundamental → 自行构建 prompt + llm.chat
      （不复用 _synthesize_tech_fundamental，因其内部 swallow exception，外部无法感知失败）

    synthesis 失败 → errors["synthesis"] 写入，_fallback_report 生成降级报告，图不崩溃。
    """
    llm             = config["configurable"]["llm"]
    scope           = state.get("analysis_scope", "comprehensive")
    market          = state["market"]
    symbol          = state["symbol"]
    identity        = state.get("stock_identity", f"{market}/{symbol}")
    sections        = state.get("sections", {})
    output_language = state.get("output_language", "zh-CN")

    lang_label = OUTPUT_LANGUAGE_LABELS.get(output_language, "简体中文")
    lang_instruction = (
        f"\n【输出语言】请使用 {lang_label} 撰写报告，"
        "除股票名称、代码、专有名词、财务字段名称可保留原文外，其余均应使用该语言。\n"
    ) if output_language != "zh-CN" else ""

    # ── technical_fundamental ──────────────────────────────────────────────────
    if scope == "technical_fundamental":
        tech_text = _trunc(sections.get("technical",   ""), "技术面", _SECTION_MAX_CHARS)
        fund_text = _trunc(sections.get("fundamental", ""), "基本面", _SECTION_MAX_CHARS)
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
            f"{lang_instruction}"
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
            report = await asyncio.to_thread(llm.chat, messages, temperature=0.3)
        except Exception as exc:
            log.error("LangGraph synthesis_node tech_fund LLM failed: %s", exc)
            report = _fallback_report(market, symbol, sections, exc, identity,
                                      title_override="技术面与基本面分析报告",
                                      output_language=output_language)
            return {"report": report, "errors": {"synthesis": str(exc)}}
        return {"report": report}

    # ── comprehensive ──────────────────────────────────────────────────────────
    else:
        synthesis_user = ComprehensiveAnalysisCoordinator._build_synthesis_prompt(
            market, symbol, sections, identity, output_language=output_language,
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": synthesis_user},
        ]
        try:
            report = await asyncio.to_thread(llm.chat, messages, temperature=0.3)
        except Exception as exc:
            log.error("LangGraph synthesis_node comprehensive LLM failed: %s", exc)
            report = _fallback_report(market, symbol, sections, exc, identity,
                                      output_language=output_language)
            return {"report": report, "errors": {"synthesis": str(exc)}}
        return {"report": report}


def _single_agent_report_node(state: AnalysisState) -> dict:
    """
    单 Agent scope 报告包装（不调用 synthesis LLM）。
    复用 coordinator._build_single_agent_report（module-level function）。
    """
    scope    = state.get("analysis_scope", "")
    identity = state.get("stock_identity", "Unknown")
    sections = state.get("sections", {})
    statuses = state.get("statuses", {})

    agent_key     = SCOPE_AGENTS.get(scope, [""])[0]
    agent_content = sections.get(agent_key, "[无内容]")
    agent_status  = statuses.get(agent_key, {}).get("status", "unknown")

    # 如果 agent 失败/超时，在报告中注明
    if agent_status in ("failed", "timeout"):
        title = _SCOPE_TITLES.get(scope, "分析报告")
        agent_content = (
            f"> ⚠️ {title.replace('分析报告', '').strip()} Agent "
            f"执行状态：**{agent_status}**。以下内容为错误说明，请稍后重试。\n\n"
            + agent_content
        )

    output_language = state.get("output_language", "zh-CN")
    report = _build_single_agent_report(identity, scope, agent_content,
                                        output_language=output_language)
    return {"report": report}


def _finalize_node(state: AnalysisState) -> dict:
    """
    构造最终 metadata：
    - 调用 coordinator._build_metadata（warnings / agents 计算）
    - 补 skipped（未运行 Agent）
    - 注入 analysis_scope 与 workflow_engine = "langgraph"
    """
    statuses       = dict(state.get("statuses") or {})
    analysis_scope = state.get("analysis_scope", "comprehensive")
    market         = state.get("market", "")
    sections       = state.get("sections", {})
    errors         = state.get("errors", {})

    # 补 skipped
    for agent in _ALL_AGENTS:
        if agent not in statuses:
            statuses[agent] = {
                "status":  "skipped",
                "message": "该维度未纳入本次分析范围",
            }

    # 复用 coordinator 的 warnings 计算逻辑
    metadata = _build_metadata(market, sections, statuses)

    # synthesis 失败时也追加 warning
    if "synthesis" in errors:
        metadata["warnings"].append(f"synthesis llm failed: {errors['synthesis'][:60]}.")

    # 注入 LangGraph 专属字段
    metadata["analysis_scope"]  = analysis_scope
    metadata["workflow_engine"] = "langgraph"
    metadata["output_language"] = state.get("output_language", "zh-CN")

    return {
        "metadata":        metadata,
        "statuses":        statuses,
        "warnings":        metadata["warnings"],
        "workflow_engine": "langgraph",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 条件边
# ══════════════════════════════════════════════════════════════════════════════

_AGENT_NODE_MAP: dict[str, str] = {
    "technical":       "_technical_node",
    "fundamental":     "_fundamental_node",
    "peer_comparison": "_peer_node",
    "news":            "_news_node",
}


def _route_agents(state: AnalysisState) -> list[Send]:
    """fan-out：根据 agents_to_run 动态发射 Agent 节点。"""
    return [
        Send(_AGENT_NODE_MAP[agent], state)
        for agent in state.get("agents_to_run", [])
        if agent in _AGENT_NODE_MAP
    ]


def _route_after_collect(state: AnalysisState) -> str:
    """collect → synthesis（多 Agent）或 single_agent_report（单 Agent）。"""
    scope = state.get("analysis_scope", "comprehensive")
    if scope in _SINGLE_AGENT_SCOPES:
        return "_single_agent_report_node"
    return "_synthesis_node"


# ══════════════════════════════════════════════════════════════════════════════
# 图构建
# ══════════════════════════════════════════════════════════════════════════════

def build_analysis_graph() -> StateGraph:
    """构建并返回 LangGraph StateGraph（未编译）。"""
    g = StateGraph(AnalysisState)

    g.add_node("_fetch_identity_node",       _fetch_identity_node)
    g.add_node("_prepare_scope_node",        _prepare_scope_node)
    g.add_node("_technical_node",            _technical_node)
    g.add_node("_fundamental_node",          _fundamental_node)
    g.add_node("_peer_node",                 _peer_node)
    g.add_node("_news_node",                 _news_node)
    g.add_node("_collect_node",              _collect_node)
    g.add_node("_synthesis_node",            _synthesis_node)
    g.add_node("_single_agent_report_node",  _single_agent_report_node)
    g.add_node("_finalize_node",             _finalize_node)

    g.add_edge(START,                    "_fetch_identity_node")
    g.add_edge("_fetch_identity_node",   "_prepare_scope_node")

    g.add_conditional_edges(
        "_prepare_scope_node",
        _route_agents,
        ["_technical_node", "_fundamental_node", "_peer_node", "_news_node"],
    )

    g.add_edge("_technical_node",   "_collect_node")
    g.add_edge("_fundamental_node", "_collect_node")
    g.add_edge("_peer_node",        "_collect_node")
    g.add_edge("_news_node",        "_collect_node")

    g.add_conditional_edges(
        "_collect_node",
        _route_after_collect,
        ["_synthesis_node", "_single_agent_report_node"],
    )

    g.add_edge("_synthesis_node",          "_finalize_node")
    g.add_edge("_single_agent_report_node","_finalize_node")
    g.add_edge("_finalize_node",            END)

    return g


# ══════════════════════════════════════════════════════════════════════════════
# Runner（FastAPI 接口层调用入口）
# ══════════════════════════════════════════════════════════════════════════════

class LangGraphAnalysisRunner:
    """
    LangGraph 分析执行器，接口与 ComprehensiveAnalysisCoordinator.analyze_scoped() 兼容。

    用法：
        runner = LangGraphAnalysisRunner(llm)
        result = await runner.analyze(db, "CN", "000001", "technical_only")
        # result 可直接用于 ComprehensiveV2Response(**result)
    """

    def __init__(self, llm) -> None:
        graph      = build_analysis_graph()
        self._app  = graph.compile()
        self._llm  = llm

    async def analyze(
        self,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        analysis_scope:  str = "comprehensive",
        output_language: str = "zh-CN",
    ) -> dict:
        """
        执行 LangGraph 分析，返回与 ComprehensiveV2Response 完全兼容的 dict。

        Args:
            db:             AsyncSession（FastAPI Depends(get_db) 注入）
            market:         "CN" 或 "HK"
            symbol:         股票代码
            analysis_scope: 分析范围（VALID_SCOPES 之一）

        Returns:
            {
                "market", "symbol", "stock_name",
                "report", "sections",
                "metadata": {generated_at, agents, warnings, analysis_scope, workflow_engine},
                "analysis_scope",
            }
        """
        market = market.upper()

        if analysis_scope not in VALID_SCOPES:
            raise ValueError(
                f"analysis_scope '{analysis_scope}' 不支持。可选值：{sorted(VALID_SCOPES)}"
            )

        initial_state = {
            "market":          market,
            "symbol":          symbol,
            "analysis_scope":  analysis_scope,
            "output_language": output_language,
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

        log.info(
            "LangGraphAnalysisRunner.analyze: start [%s/%s] scope=%s",
            market, symbol, analysis_scope,
        )

        state = await self._app.ainvoke(
            initial_state,
            config={
                "configurable": {
                    "llm": self._llm,
                    "db":  db,
                }
            },
        )

        log.info(
            "LangGraphAnalysisRunner.analyze: done [%s/%s] scope=%s engine=langgraph",
            market, symbol, analysis_scope,
        )

        return {
            "market":          market,
            "symbol":          symbol,
            "stock_name":      state.get("stock_name", ""),
            "report":          state.get("report", ""),
            "sections":        dict(state.get("sections") or {}),
            "metadata":        state.get("metadata", {}),
            "analysis_scope":  analysis_scope,
            "output_language": output_language,
        }
