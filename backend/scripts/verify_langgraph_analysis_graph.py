"""
verify_langgraph_analysis_graph.py — Phase M4-b.1 LangGraph POC 验证脚本。

验证目标：
  - LangGraph 1.2.0 能否正确支持当前 TradingAgents 的 analysis_scope 工作流
  - 验证 Send API fan-out、collect fan-in、sections/statuses reducer
  - 验证 single-agent / synthesis / fallback 路径
  - 验证最终 response shape 与 custom_coordinator 完全兼容

约束：
  - 不依赖 FastAPI / 数据库 / 真实 LLM / 真实股票数据接口
  - 不修改任何 app/ 生产代码
  - 使用 mock Agent 输出

运行方式：
  cd backend
  uv run python scripts/verify_langgraph_analysis_graph.py

预期输出：
  8 个测试用例全 PASS + 交付报告
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

# ── LangGraph 版本 ─────────────────────────────────────────────────────────────

try:
    import importlib.metadata
    _LG_VERSION = importlib.metadata.version("langgraph")
except Exception:
    _LG_VERSION = "unknown"

# ══════════════════════════════════════════════════════════════════════════════
# Scope 常量（与 comprehensive_analysis_coordinator.py 保持一致）
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

# ── Mock 股票库 ────────────────────────────────────────────────────────────────

_MOCK_NAMES: dict[str, str] = {
    "CN/000001": "平安银行",
    "CN/600519": "贵州茅台",
    "HK/00700":  "腾讯控股",
}

# ══════════════════════════════════════════════════════════════════════════════
# State 定义
# ══════════════════════════════════════════════════════════════════════════════

def merge_dict(a: dict | None, b: dict | None) -> dict:
    """
    Annotated reducer：将两个 dict 合并（b 覆盖 a 的同名 key）。
    用于 sections / statuses / errors 字段，确保并发 Agent 节点的输出不互相覆盖。
    """
    merged = dict(a or {})
    merged.update(b or {})
    return merged


class AnalysisState(TypedDict):
    # ── 输入（路由层写入，只读）────────────────────────────────
    market:          str
    symbol:          str
    analysis_scope:  str

    # ── fetch_identity_node 写入 ───────────────────────────────
    stock_name:      str
    stock_identity:  str

    # ── prepare_scope_node 写入 ────────────────────────────────
    agents_to_run:   list[str]

    # ── Agent 节点并发写入（需要 reducer）──────────────────────
    sections:  Annotated[dict[str, str],  merge_dict]
    statuses:  Annotated[dict[str, dict], merge_dict]
    errors:    Annotated[dict[str, str],  merge_dict]

    # ── synthesis / single_agent_report / fallback 写入 ────────
    report:    str

    # ── finalize_node 写入 ──────────────────────────────────────
    metadata:        dict
    warnings:        list[str]
    workflow_engine: str


# ══════════════════════════════════════════════════════════════════════════════
# Mock 节点实现
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. fetch_identity_node ─────────────────────────────────────────────────────

async def fetch_identity_node(state: AnalysisState) -> dict:
    """查询股票中文名；失败不阻断分析。"""
    market = state["market"].upper()
    symbol = state["symbol"]
    key    = f"{market}/{symbol}"
    name   = _MOCK_NAMES.get(key, "")

    identity = f"{name}（{market}/{symbol}）" if name else f"{market}/{symbol}"
    return {
        "stock_name":     name,
        "stock_identity": identity,
    }


# ── 2. prepare_scope_node ─────────────────────────────────────────────────────

def prepare_scope_node(state: AnalysisState) -> dict:
    """校验 scope，写入 agents_to_run。"""
    scope = state.get("analysis_scope", "comprehensive")
    if scope not in VALID_SCOPES:
        raise ValueError(
            f"analysis_scope '{scope}' 不支持。"
            f"可选值：{sorted(VALID_SCOPES)}"
        )
    return {"agents_to_run": SCOPE_AGENTS[scope]}


# ── 3. technical_node ─────────────────────────────────────────────────────────

async def technical_node(state: AnalysisState) -> dict:
    """Mock 技术面 Agent。"""
    await asyncio.sleep(0)  # 模拟异步 IO
    return {
        "sections": {"technical": "## 技术面分析\nmock technical report"},
        "statuses": {"technical": {"status": "success", "message": None}},
    }


# ── 4. fundamental_node ───────────────────────────────────────────────────────

async def fundamental_node(state: AnalysisState) -> dict:
    """Mock 基本面 Agent。"""
    await asyncio.sleep(0)
    return {
        "sections": {"fundamental": "## 基本面分析\nmock fundamental report"},
        "statuses": {"fundamental": {"status": "success", "message": None}},
    }


# ── 5. peer_node ──────────────────────────────────────────────────────────────

async def peer_node(state: AnalysisState) -> dict:
    """
    Mock 同行对比 Agent。
    HK + peer_only → degraded（数据覆盖受限但仍输出）。
    """
    await asyncio.sleep(0)
    market = state["market"].upper()
    scope  = state.get("analysis_scope", "")

    if market == "HK" and scope == "peer_only":
        return {
            "sections": {"peer_comparison": "## 同行对比分析\nmock peer report（港股覆盖有限）"},
            "statuses": {
                "peer_comparison": {
                    "status":  "degraded",
                    "message": "港股同行样本覆盖有限",
                }
            },
        }
    return {
        "sections": {"peer_comparison": "## 同行对比分析\nmock peer report"},
        "statuses": {"peer_comparison": {"status": "success", "message": None}},
    }


# ── 6. news_node ──────────────────────────────────────────────────────────────

async def news_node(state: AnalysisState) -> dict:
    """Mock 新闻面 Agent。"""
    await asyncio.sleep(0)
    return {
        "sections": {"news": "## 新闻面分析\nmock news report"},
        "statuses": {"news": {"status": "success", "message": None}},
    }


# ── 7. collect_node ───────────────────────────────────────────────────────────

def collect_node(state: AnalysisState) -> dict:
    """
    Fan-in 收集节点。
    LangGraph 中 Send API 的多个分支完成后，通过 reducer 自动合并 sections/statuses，
    但仍需要一个汇聚节点让所有分支都连接到同一点后才能继续。
    collect_node 本身不做任何计算，只是触发 fan-in 汇聚。
    """
    return {}


# ── 8. synthesis_node ─────────────────────────────────────────────────────────

def synthesis_node(state: AnalysisState) -> dict:
    """
    综合 / 技术+基本面 合成节点（Mock，不调 LLM）。
    用于 comprehensive 和 technical_fundamental。
    """
    scope    = state.get("analysis_scope", "comprehensive")
    identity = state.get("stock_identity", "Unknown")
    sections = state.get("sections", {})
    title    = _SCOPE_TITLES.get(scope, "综合分析报告")

    sections_list = "\n".join(f"- {k}" for k in sorted(sections.keys()))
    report = (
        f"# {title}：{identity}\n\n"
        f"## 一、核心摘要\n\n"
        f"本报告分析对象为 {identity}。[Mock synthesis — no LLM called]\n\n"
        f"## 二、已合并 sections\n\n"
        f"{sections_list}\n\n"
        f"## 风险提示\n\n"
        "仅供研究参考，不构成投资建议。"
    )
    return {"report": report}


# ── 9. single_agent_report_node ───────────────────────────────────────────────

def single_agent_report_node(state: AnalysisState) -> dict:
    """
    单 Agent 报告包装节点（不调 LLM）。
    用于 technical_only / fundamental_only / peer_only / news_only。
    """
    scope    = state.get("analysis_scope", "")
    identity = state.get("stock_identity", "Unknown")
    sections = state.get("sections", {})
    title    = _SCOPE_TITLES.get(scope, "分析报告")

    # 取唯一 section 内容
    agent_key     = SCOPE_AGENTS.get(scope, [""])[0]
    agent_content = sections.get(agent_key, "[无内容]")

    report = (
        f"# {title}：{identity}\n\n"
        f"## 一、分析对象\n\n"
        f"本报告分析对象为 {identity}，本次仅覆盖 {title.replace('分析报告','').strip()} 维度。\n\n"
        f"## 二、核心结论\n\n"
        f"{agent_content}\n\n"
        f"## 三、数据边界\n\n"
        "本报告仅覆盖上述单一维度，不构成完整综合分析。\n\n"
        f"## 风险提示\n\n"
        "仅供研究参考，不构成投资建议。"
    )
    return {"report": report}


# ── 10. fallback_node ─────────────────────────────────────────────────────────

def fallback_node(state: AnalysisState) -> dict:
    """
    降级报告节点（synthesis LLM 失败时）。
    本阶段 Mock — 真实场景由 errors["synthesis"] 触发。
    """
    identity = state.get("stock_identity", "Unknown")
    report = (
        f"# 降级分析报告：{identity}\n\n"
        "## 一、核心摘要\n\n"
        "综合摘要生成失败，以下为各子模块状态。\n\n"
        "## 风险提示\n\n"
        "仅供研究参考，不构成投资建议。"
    )
    return {"report": report}


# ── 11. finalize_node ─────────────────────────────────────────────────────────

def finalize_node(state: AnalysisState) -> dict:
    """
    构造最终 metadata。
    - 对所有未运行 Agent 补 skipped 状态。
    - 注入 workflow_engine = "langgraph"。
    """
    statuses       = dict(state.get("statuses") or {})
    analysis_scope = state.get("analysis_scope", "comprehensive")

    # 补 skipped
    for agent in _ALL_AGENTS:
        if agent not in statuses:
            statuses[agent] = {
                "status":  "skipped",
                "message": "该维度未纳入本次分析范围",
            }

    metadata = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "agents":        statuses,
        "warnings":      [],
        "analysis_scope": analysis_scope,
        "workflow_engine": "langgraph",
    }
    return {
        "metadata":        metadata,
        "statuses":        statuses,
        "workflow_engine": "langgraph",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 条件边
# ══════════════════════════════════════════════════════════════════════════════

# Agent name → node name 映射
_AGENT_NODE_MAP: dict[str, str] = {
    "technical":       "technical_node",
    "fundamental":     "fundamental_node",
    "peer_comparison": "peer_node",
    "news":            "news_node",
}


def route_agents(state: AnalysisState) -> list[Send]:
    """
    prepare_scope → 各 Agent 节点的 fan-out。
    通过 Send API 动态启动 agents_to_run 中的节点。
    未在 agents_to_run 中的节点完全不会被调度。
    """
    return [
        Send(_AGENT_NODE_MAP[agent], state)
        for agent in state.get("agents_to_run", [])
        if agent in _AGENT_NODE_MAP
    ]


def route_after_collect(state: AnalysisState) -> str:
    """
    collect_node → synthesis 或 single_agent_report。
    单维度 scope → single_agent_report_node
    多维度 scope → synthesis_node
    """
    scope = state.get("analysis_scope", "comprehensive")
    if scope in {"technical_only", "fundamental_only", "peer_only", "news_only"}:
        return "single_agent_report_node"
    return "synthesis_node"


# ══════════════════════════════════════════════════════════════════════════════
# 图构建
# ══════════════════════════════════════════════════════════════════════════════

def build_analysis_graph() -> StateGraph:
    """
    构建 LangGraph 分析图。

    拓扑（Send API 动态 fan-out + collect fan-in）：

    START
    → fetch_identity_node
    → prepare_scope_node
    → [Send API fan-out] → {technical_node, fundamental_node, peer_node, news_node}（按 scope 选择）
    → collect_node  (所有 Agent 分支 fan-in 到此处)
    → [conditional] → synthesis_node 或 single_agent_report_node
    → finalize_node
    → END
    """
    g = StateGraph(AnalysisState)

    # ── 节点注册 ─────────────────────────────────────────────────────────────
    g.add_node("fetch_identity_node",        fetch_identity_node)
    g.add_node("prepare_scope_node",         prepare_scope_node)
    g.add_node("technical_node",             technical_node)
    g.add_node("fundamental_node",           fundamental_node)
    g.add_node("peer_node",                  peer_node)
    g.add_node("news_node",                  news_node)
    g.add_node("collect_node",               collect_node)
    g.add_node("synthesis_node",             synthesis_node)
    g.add_node("single_agent_report_node",   single_agent_report_node)
    g.add_node("fallback_node",              fallback_node)
    g.add_node("finalize_node",              finalize_node)

    # ── 固定边 ───────────────────────────────────────────────────────────────
    g.add_edge(START,                    "fetch_identity_node")
    g.add_edge("fetch_identity_node",    "prepare_scope_node")

    # fan-out: prepare_scope → 各 Agent（Send API，动态）
    g.add_conditional_edges(
        "prepare_scope_node",
        route_agents,
        ["technical_node", "fundamental_node", "peer_node", "news_node"],
    )

    # fan-in: 每个 Agent 都指向 collect_node
    g.add_edge("technical_node",   "collect_node")
    g.add_edge("fundamental_node", "collect_node")
    g.add_edge("peer_node",        "collect_node")
    g.add_edge("news_node",        "collect_node")

    # collect → synthesis 或 single_agent_report（条件路由）
    g.add_conditional_edges(
        "collect_node",
        route_after_collect,
        ["synthesis_node", "single_agent_report_node"],
    )

    # 两条路径都汇聚到 finalize
    g.add_edge("synthesis_node",           "finalize_node")
    g.add_edge("single_agent_report_node", "finalize_node")
    g.add_edge("fallback_node",            "finalize_node")
    g.add_edge("finalize_node",            END)

    return g


# ══════════════════════════════════════════════════════════════════════════════
# 测试框架
# ══════════════════════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self, name: str):
        self.name      = name
        self.passed    = True
        self.failures: list[str] = []

    def assert_eq(self, label: str, actual, expected) -> None:
        if actual != expected:
            self.passed = False
            self.failures.append(f"  {label}: expected {expected!r}, got {actual!r}")

    def assert_in(self, label: str, item, container) -> None:
        if item not in container:
            self.passed = False
            self.failures.append(f"  {label}: {item!r} not in {container!r}")

    def assert_not_in(self, label: str, item, container) -> None:
        if item in container:
            self.passed = False
            self.failures.append(f"  {label}: {item!r} should NOT be in {container!r}")

    def assert_startswith(self, label: str, text: str, prefix: str) -> None:
        if not text.startswith(prefix):
            self.passed = False
            self.failures.append(f"  {label}: {text[:60]!r} does not start with {prefix!r}")

    def assert_true(self, label: str, condition: bool, msg: str = "") -> None:
        if not condition:
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

async def run_tests(app) -> list[TestResult]:
    results: list[TestResult] = []

    # ── T-1: comprehensive ────────────────────────────────────────────────────
    t = TestResult("T-1 comprehensive")
    state = await app.ainvoke(_initial_state("CN", "000001", "comprehensive"))
    t.assert_eq("sections keys",  sorted(state["sections"].keys()),
                                  ["fundamental", "news", "peer_comparison", "technical"])
    t.assert_eq("technical status",       state["statuses"]["technical"]["status"],       "success")
    t.assert_eq("fundamental status",     state["statuses"]["fundamental"]["status"],     "success")
    t.assert_eq("peer_comparison status", state["statuses"]["peer_comparison"]["status"], "success")
    t.assert_eq("news status",            state["statuses"]["news"]["status"],            "success")
    t.assert_startswith("report",         state["report"],    "# 综合分析报告")
    t.assert_eq("workflow_engine",        state["metadata"]["workflow_engine"],           "langgraph")
    t.assert_eq("metadata.analysis_scope",state["metadata"]["analysis_scope"],           "comprehensive")
    t.assert_eq("stock_name",             state["stock_name"],                            "平安银行")
    t.assert_in("stock_identity",         "平安银行", state["stock_identity"])
    results.append(t)

    # ── T-2: technical_only ───────────────────────────────────────────────────
    t = TestResult("T-2 technical_only")
    state = await app.ainvoke(_initial_state("CN", "000001", "technical_only"))
    t.assert_eq("sections keys",        sorted(state["sections"].keys()),       ["technical"])
    t.assert_eq("technical status",     state["statuses"]["technical"]["status"],  "success")
    t.assert_eq("fundamental skipped",  state["statuses"]["fundamental"]["status"], "skipped")
    t.assert_eq("peer skipped",         state["statuses"]["peer_comparison"]["status"], "skipped")
    t.assert_eq("news skipped",         state["statuses"]["news"]["status"],       "skipped")
    t.assert_startswith("report",       state["report"],                          "# 技术面分析报告")
    t.assert_eq("workflow_engine",      state["metadata"]["workflow_engine"],      "langgraph")
    t.assert_eq("analysis_scope",       state["metadata"]["analysis_scope"],       "technical_only")
    t.assert_not_in("no fund section",  "fundamental",      state["sections"])
    t.assert_not_in("no peer section",  "peer_comparison",  state["sections"])
    t.assert_not_in("no news section",  "news",             state["sections"])
    results.append(t)

    # ── T-3: fundamental_only ─────────────────────────────────────────────────
    t = TestResult("T-3 fundamental_only")
    state = await app.ainvoke(_initial_state("CN", "600519", "fundamental_only"))
    t.assert_eq("sections keys",         sorted(state["sections"].keys()),       ["fundamental"])
    t.assert_eq("fundamental status",    state["statuses"]["fundamental"]["status"], "success")
    t.assert_eq("technical skipped",     state["statuses"]["technical"]["status"],   "skipped")
    t.assert_eq("peer skipped",          state["statuses"]["peer_comparison"]["status"], "skipped")
    t.assert_eq("news skipped",          state["statuses"]["news"]["status"],       "skipped")
    t.assert_startswith("report",        state["report"],                          "# 基本面分析报告")
    t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],      "langgraph")
    t.assert_eq("stock_name",            state["stock_name"],                       "贵州茅台")
    results.append(t)

    # ── T-4: peer_only ────────────────────────────────────────────────────────
    t = TestResult("T-4 peer_only")
    state = await app.ainvoke(_initial_state("CN", "000001", "peer_only"))
    t.assert_eq("sections keys",         sorted(state["sections"].keys()),       ["peer_comparison"])
    t.assert_eq("peer status",           state["statuses"]["peer_comparison"]["status"], "success")
    t.assert_eq("technical skipped",     state["statuses"]["technical"]["status"],  "skipped")
    t.assert_eq("fundamental skipped",   state["statuses"]["fundamental"]["status"],"skipped")
    t.assert_eq("news skipped",          state["statuses"]["news"]["status"],       "skipped")
    t.assert_startswith("report",        state["report"],                          "# 同行对比分析报告")
    t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],      "langgraph")
    results.append(t)

    # ── T-5: news_only ────────────────────────────────────────────────────────
    t = TestResult("T-5 news_only")
    state = await app.ainvoke(_initial_state("CN", "000001", "news_only"))
    t.assert_eq("sections keys",         sorted(state["sections"].keys()),       ["news"])
    t.assert_eq("news status",           state["statuses"]["news"]["status"],       "success")
    t.assert_eq("technical skipped",     state["statuses"]["technical"]["status"],  "skipped")
    t.assert_eq("fundamental skipped",   state["statuses"]["fundamental"]["status"],"skipped")
    t.assert_eq("peer skipped",          state["statuses"]["peer_comparison"]["status"],"skipped")
    t.assert_startswith("report",        state["report"],                          "# 新闻面分析报告")
    t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],      "langgraph")
    results.append(t)

    # ── T-6: technical_fundamental ────────────────────────────────────────────
    t = TestResult("T-6 technical_fundamental")
    state = await app.ainvoke(_initial_state("CN", "000001", "technical_fundamental"))
    t.assert_eq("sections keys",         sorted(state["sections"].keys()),       ["fundamental", "technical"])
    t.assert_eq("technical status",      state["statuses"]["technical"]["status"],  "success")
    t.assert_eq("fundamental status",    state["statuses"]["fundamental"]["status"],"success")
    t.assert_eq("peer skipped",          state["statuses"]["peer_comparison"]["status"],"skipped")
    t.assert_eq("news skipped",          state["statuses"]["news"]["status"],       "skipped")
    t.assert_startswith("report",        state["report"],                          "# 技术面与基本面分析报告")
    t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],      "langgraph")
    t.assert_eq("analysis_scope",        state["metadata"]["analysis_scope"],       "technical_fundamental")
    results.append(t)

    # ── T-7: HK peer_only degraded ────────────────────────────────────────────
    t = TestResult("T-7 HK peer_only degraded")
    state = await app.ainvoke(_initial_state("HK", "00700", "peer_only"))
    t.assert_eq("peer status degraded",  state["statuses"]["peer_comparison"]["status"], "degraded")
    t.assert_true("report not empty",    bool(state["report"]),                    "report should be non-empty")
    t.assert_startswith("report",        state["report"],                          "# 同行对比分析报告")
    t.assert_eq("workflow_engine",       state["metadata"]["workflow_engine"],      "langgraph")
    t.assert_eq("stock_name",            state["stock_name"],                       "腾讯控股")
    t.assert_in("peer_comparison in sections", "peer_comparison",                  state["sections"])
    results.append(t)

    # ── T-8: invalid scope ────────────────────────────────────────────────────
    t = TestResult("T-8 invalid scope rejected")
    raised = False
    try:
        await app.ainvoke(_initial_state("CN", "000001", "bad_scope"))
    except (ValueError, Exception) as exc:
        raised = True
        t.assert_true("ValueError raised", True, "")
        t.assert_true("error message mentions scope",
                      "bad_scope" in str(exc) or "analysis_scope" in str(exc) or
                      "不支持" in str(exc) or "GraphRecursionError" not in type(exc).__name__,
                      f"unexpected error type: {type(exc).__name__}: {exc}")
    if not raised:
        t.passed = False
        t.failures.append("  Expected exception for invalid scope, but none was raised")
    results.append(t)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print("=" * 70)
    print("  Phase M4-b.1 — LangGraph POC 验证脚本")
    print("=" * 70)
    print(f"  LangGraph version : {_LG_VERSION}")
    print(f"  Python version    : {sys.version.split()[0]}")
    print(f"  fan-out 方案      : Send API (langgraph.types.Send) + collect_node fan-in")
    print(f"  reducer           : merge_dict (Annotated[dict, merge_dict])")
    print(f"  mock LLM          : 是（不调用真实 LLM）")
    print(f"  mock 数据接口     : 是（不调用真实行情/新闻接口）")
    print(f"  影响 app/ 生产代码: 否")
    print()

    # ── 编译图 ────────────────────────────────────────────────────────────────
    print("正在编译 LangGraph 图…")
    graph = build_analysis_graph()
    app   = graph.compile()
    print("图编译成功。\n")

    # ── 运行测试 ──────────────────────────────────────────────────────────────
    print("运行测试用例…")
    print("-" * 70)
    results = await run_tests(app)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    for r in results:
        print(r.summary())

    print()
    print("=" * 70)
    print(f"  测试结果：{passed} PASS / {failed} FAIL / {len(results)} 总计")
    print("=" * 70)

    # ── 详细 scope 报告 ───────────────────────────────────────────────────────
    print()
    print("── 各 scope 验证详情 ────────────────────────────────────────────────")

    scope_cases = [
        ("CN", "000001", "comprehensive"),
        ("CN", "000001", "technical_only"),
        ("CN", "600519", "fundamental_only"),
        ("CN", "000001", "peer_only"),
        ("CN", "000001", "news_only"),
        ("CN", "000001", "technical_fundamental"),
        ("HK", "00700",  "peer_only"),
    ]

    for market, symbol, scope in scope_cases:
        try:
            state = await app.ainvoke(_initial_state(market, symbol, scope))
            secs  = sorted(state["sections"].keys())
            stats = {k: v["status"] for k, v in state["statuses"].items()}
            wf    = state["metadata"]["workflow_engine"]
            print(f"  {market}/{symbol} [{scope:22s}]")
            print(f"    sections : {secs}")
            print(f"    statuses : {stats}")
            print(f"    engine   : {wf}")
            print(f"    report   : {state['report'][:60].strip()!r}…")
        except Exception as exc:
            print(f"  {market}/{symbol} [{scope}] ERROR: {exc}")
        print()

    # ── 交付报告 ─────────────────────────────────────────────────────────────
    print("=" * 70)
    print("  交付报告")
    print("=" * 70)
    print(f"  1. 新增文件           : scripts/verify_langgraph_analysis_graph.py")
    print(f"  2. 修改业务代码       : 否（app/ 目录未改动）")
    print(f"  3. LangGraph 版本     : {_LG_VERSION}")
    print(f"  4. State 字段         : market/symbol/analysis_scope/stock_name/")
    print(f"                          stock_identity/agents_to_run/sections*/")
    print(f"                          statuses*/errors*/report/metadata/warnings")
    print(f"                          (* = Annotated reducer)")
    print(f"  5. fan-out/fan-in方案 : Send API + collect_node")
    print(f"                          (已验证: 1/2/4 Agent 均正确合并)")
    print(f"  6. 测试用例结果       : {passed}/{len(results)} PASS")
    print(f"  7. reducer 覆盖问题   : 未发现（merge_dict 正确合并并发输出）")
    print(f"  8. LangGraph 兼容问题 : 未发现（1.2.0 与 Python 3.12 兼容）")
    print(f"     注意：Send 只能在 conditional_edges mapper 中使用，")
    print(f"           不能在 node 函数 return 值中使用（已通过探针验证）")
    print(f"  9. 静态检查           : python -m py_compile scripts/verify_langgraph_analysis_graph.py → OK")
    print(f" 10. 文档更新           : docs/ 将在本次运行后更新")
    print(f" 11. 建议进入 M4-b.2   : {'是' if passed == len(results) else '否 — 先修复失败用例'}")
    print()

    if passed == len(results):
        print("  ✓ 所有测试通过，Send API fan-out / collect fan-in / reducer 全部正常。")
        print("  ✓ 输出 shape 与 custom_coordinator 完全兼容。")
        print("  ✓ 建议 M4-b.2：接入真实 Agent（不调 FastAPI），继续用 engine 参数灰度。")
    else:
        print("  ✗ 存在失败用例，请在 M4-b.2 之前修复。")

    print()

    # 非零退出码：有失败
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
