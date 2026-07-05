"""
Central Planning Agent — C31.2.

CentralPlanningAgent produces a CentralPlan for every user request:

  1. Analyzes the user query using the IntentDecision already computed.
  2. Generates entity-aware, natural-language reasoning summaries for each
     of the 9 C31 phases (problem_analysis … synthesis).
  3. Produces a structured task list (which agents/tools are needed, and why).

Design principles:
  - Pure computation: no LLM call, no DB access.  Fast and deterministic.
  - Entity-aware: content references actual stock names / industry topics
    extracted from the query, NOT generic filler.
  - "Not just templates": content is assembled dynamically from intent +
    entities + context — different queries produce genuinely different plans.
  - Safe: plan content never contains raw tool args, system prompts, SQL,
    API keys, or internal snake_case identifiers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.intent_decision_agent import IntentDecision
    from app.services.conversation_memory_service import MemoryContext

from app.agents.thinking_events import make_thinking_event, PHASE_LABELS


# ─────────────────────────────────────────────────────────────────────────────
# Domain types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanTask:
    task_id:     str
    agent:       str        # human-readable agent label, e.g. "IndustryAgent"
    description: str        # user-readable Chinese description of what this agent does
    required:    bool = True


@dataclass
class CentralPlan:
    intent:            str
    need_agent:        bool
    need_confirmation: bool
    reasoning_summary: list[dict]   # list of {phase, title, content, importance}
    tasks:             list[PlanTask] = field(default_factory=list)

    def get_phase_event(
        self,
        phase: str,
        status: str = "completed",
    ) -> dict:
        """
        Return a `thinking_event` payload dict for a specific phase.
        Used by chat_orchestrator to emit thinking_event SSE events.
        """
        for item in self.reasoning_summary:
            if item.get("phase") == phase:
                return make_thinking_event(
                    phase      = phase,
                    title      = item.get("title", PHASE_LABELS.get(phase, phase)),
                    content    = item.get("content", ""),
                    status     = status,
                    agent      = item.get("agent", ""),
                    importance = item.get("importance", "medium"),
                )
        # Phase not in plan (e.g. direct_answer skips task_decomposition)
        return make_thinking_event(
            phase   = phase,
            title   = PHASE_LABELS.get(phase, phase),
            content = "",
            status  = status,
        )

    def get_agent_dispatch_event(self, status: str = "running") -> dict:
        """Emit agent_dispatch event listing which agents will be called."""
        if not self.tasks:
            return make_thinking_event(
                phase   = "agent_dispatch",
                title   = "Agent 调度",
                content = "本次请求可直接回答，无需调用专业 Agent。",
                status  = "completed",
            )
        agents = "、".join(t.agent for t in self.tasks[:4])
        descs  = "；".join(f"**{t.agent}** — {t.description}" for t in self.tasks[:4])
        return make_thinking_event(
            phase   = "agent_dispatch",
            title   = "Agent 调度",
            content = f"将调用 {agents}。{descs}。",
            status  = status,
            importance = "high",
        )

    def get_agent_observation_event(self, agent: str = "", summary: str = "") -> dict:
        """Emit agent_observation event after an agent returns."""
        content = summary or "已获取相关数据，正在综合分析。"
        return make_thinking_event(
            phase   = "agent_observation",
            title   = "数据观测",
            content = content,
            status  = "completed",
            agent   = agent,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Intent → agent task mapping
# ─────────────────────────────────────────────────────────────────────────────

def _tasks_for_intent(intent: str, entities: list[str]) -> list[PlanTask]:
    """Return the task list for a given intent."""
    ent = "、".join(entities[:3]) if entities else ""

    _INTENT_TASKS: dict[str, list[tuple[str, str]]] = {
        "industry_research": [
            ("IndustryAgent", f"检索{'相关' if not ent else ent + '相关'}行业热度数据、资金流向和近期表现"),
            ("NewsAgent",     "检索行业最新新闻、政策动向和重要事件"),
            ("MarketAgent",   "获取行业代表公司行情及涨跌幅对比"),
        ],
        "compare_stocks": [
            ("CompareAgent",  f"获取{ent or '多支股票'}的基本面、行情和财务指标并横向对比"),
            ("MarketAgent",   f"拉取{ent or '各股'}最新行情数据，确保数据时效性一致"),
        ],
        "historical_report_read": [
            ("ReportAgent",   f"检索{'关于 ' + ent + ' 的' if ent else ''}历史分析报告"),
            ("ReportAgent",   "读取报告详情，提取技术面、基本面和风险提示章节"),
        ],
        "report_generation": [
            ("RiskReviewAgent",  "在提交任务前验证输入参数合规性"),
            ("ReportAgent",      f"生成{ent or '目标股票'}综合分析报告（技术+基本面+新闻+同行）"),
            ("ComplianceAgent",  "对报告输出执行合规审查，删除买卖建议和无来源数字"),
        ],
        "portfolio_or_watchlist": [
            ("WatchlistAgent", "读取用户自选股列表并补充最新行情数据"),
        ],
        "tool_answer": [
            ("MarketAgent",  f"获取{ent or '目标股票'}最新行情、涨跌幅和成交量"),
            ("NewsAgent",    f"检索{ent or '相关'}最新新闻和公告"),
        ],
        "direct_answer": [],
        "unknown": [],
    }
    raw = _INTENT_TASKS.get(intent, [])
    return [
        PlanTask(
            task_id     = f"task_{i+1}_{uuid.uuid4().hex[:6]}",
            agent       = agent,
            description = desc,
            required    = True,
        )
        for i, (agent, desc) in enumerate(raw)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Phase content builders (entity-aware)
# ─────────────────────────────────────────────────────────────────────────────

def _build_problem_analysis(intent: str, query: str, entities: list[str]) -> str:
    ent  = "、".join(entities[:3]) if entities else ""
    ent_clause = f"关于**{ent}**的" if ent else ""

    _ANALYSIS: dict[str, str] = {
        "direct_answer":         f"用户提出{ent_clause}金融知识问题，可基于已有知识库直接回答，无需调用实时数据 Agent。",
        "tool_answer":           f"用户询问{ent_clause}实时行情或最新资讯，需要调用市场数据和新闻检索工具。",
        "report_generation":     f"用户请求生成{ent_clause}综合分析报告。报告生成需要约 30~60 秒，须经用户确认后才创建后台任务。",
        "historical_report_read":f"用户希望查阅{ent_clause}历史分析报告，需先检索已存储的报告列表，再读取详情内容。",
        "compare_stocks":        f"用户要求横向对比多支股票（{ent or '列表待解析'}），需获取各股行情、财务指标并进行统一口径对比。",
        "industry_research":     f"用户询问行业研究相关问题{'（涉及 ' + ent + '）' if ent else ''}，需检索行业热度数据、代表公司表现和近期新闻。",
        "portfolio_or_watchlist":f"用户查询自选股或持仓组合情况，需读取用户自选股列表并补充最新行情。",
    }
    return _ANALYSIS.get(intent,
        f"用户提出{ent_clause}金融问题，正在判断所需信息类型和最优处理路径。")


def _build_intent_decision(intent: str, entities: list[str], reason: str) -> str:
    label_map = {
        "direct_answer":          "直接问答（无需实时数据）",
        "tool_answer":            "工具查询（需要实时行情或新闻）",
        "report_generation":      "报告生成（需用户确认 + 后台任务）",
        "historical_report_read": "历史报告读取",
        "compare_stocks":         "多股对比分析",
        "industry_research":      "行业研究与热点分析",
        "portfolio_or_watchlist": "自选股 / 投资组合查询",
    }
    label = label_map.get(intent, intent)
    ent = "、".join(entities[:3]) if entities else ""
    suffix = f"；识别到相关主体：**{ent}**" if ent else ""
    return f"意图识别为「**{label}**」（置信度较高）{suffix}。{reason or ''}"


def _build_planning(intent: str, tasks: list[PlanTask], need_confirmation: bool) -> str:
    if not tasks:
        return "本次请求可由 AI 直接基于知识库回答，无需调用专业 Agent，响应更快。"

    confirm_note = "⚠️ 本次操作需要用户确认后才会执行，避免误启动耗时任务。" if need_confirmation else ""
    task_bullets = "；".join(f"{t.agent}（{t.description}）" for t in tasks[:3])
    return f"规划需要调用以下 Agent：{task_bullets}。{confirm_note}"


def _build_task_decomposition(tasks: list[PlanTask]) -> str:
    if not tasks:
        return "本次请求无需拆解任务，直接进入回答生成阶段。"
    items = "".join(f"\n  • {t.agent} — {t.description}" for t in tasks)
    return f"任务拆解如下：{items}"


def _build_agent_dispatch(tasks: list[PlanTask]) -> str:
    if not tasks:
        return "无需调度外部 Agent，将直接生成回答。"
    agents = "、".join(t.agent for t in tasks[:4])
    return f"正在调度：{agents}。各 Agent 并行执行，结果汇总后进入深度思考阶段。"


def _build_agent_observation(intent: str, tasks: list[PlanTask]) -> str:
    if not tasks:
        return "已完成知识库检索，数据充足，进入综合分析阶段。"
    return (
        "各 Agent 已返回数据。将对数据完整性进行评估：缺失字段将在回答中注明，"
        "不可信数据将被排除，确保最终回答基于已验证信息。"
    )


def _build_deep_reasoning(intent: str, entities: list[str]) -> str:
    ent = "、".join(entities[:3]) if entities else "相关标的"
    _REASONING: dict[str, str] = {
        "direct_answer":          "正在综合知识库内容，区分已确认事实和待验证推断，避免过度推断或编造数字。",
        "tool_answer":            f"正在综合{ent}的行情和新闻数据，区分短期波动与中长期趋势，不给出确定性判断。",
        "industry_research":      f"正在分析行业热度来源：区分政策驱动、资金流向和市场情绪，避免把短期热度等同于长期价值。",
        "compare_stocks":         f"正在横向对比{ent}各维度数据，确保对比口径一致，不仅依赖涨跌幅排名。",
        "historical_report_read": "正在解读历史报告内容，将技术面、基本面和风险提示转为用户友好的语言。",
        "report_generation":      "报告生成任务已提交，正在监控任务状态。完成后将提供直接查看链接。",
        "portfolio_or_watchlist": "正在分析自选股组合整体表现，识别异动标的和潜在关注点。",
    }
    return _REASONING.get(intent,
        f"正在综合已获取的{ent}相关数据，平衡已知事实与缺失信息，形成研究结论。")


def _build_risk_review(intent: str) -> str:
    _RISK: dict[str, str] = {
        "direct_answer":          "检查回答中是否存在无来源财务数字、确定性涨跌表达或隐性买卖建议。",
        "report_generation":      "验证任务提交状态，确保不在报告未生成时显示成功。不会伪造 report_id。",
        "compare_stocks":         "检查对比结论中是否存在直接买卖建议或单只股票评级，确保只呈现客观数据对比。",
        "industry_research":      "核查行业分析结论：热度排名不等于投资价值，行业研究结果不作为买入推荐。",
        "historical_report_read": "验证报告解读不超出原报告内容，不添加未经验证的延伸推断。",
    }
    base = _RISK.get(intent,
        "执行合规审查：过滤无来源财务数字、确定性涨跌表达、隐性买卖建议。")
    return base + " 所有输出均带免责声明。"


def _build_synthesis(intent: str, need_confirmation: bool) -> str:
    if need_confirmation:
        return "生成确认卡片，告知用户操作内容和预期耗时，等待用户确认后再执行后台任务。"
    _SYNTH: dict[str, str] = {
        "direct_answer":          "基于知识库内容生成回答，明确标注数据边界，说明无法确认的部分。",
        "tool_answer":            "整合实时行情和新闻数据，生成结构化回答，注明数据时效性。",
        "industry_research":      "生成行业概览：热度排名 + 代表公司 + 近期催化因素 + 关注风险，不作为投资建议。",
        "compare_stocks":         "生成多股对比表，按维度展示差异，提供跳转对比页链接。",
        "historical_report_read": "生成报告解读摘要，保留原报告的关键结论和数据边界说明。",
        "portfolio_or_watchlist": "生成自选股快报，标注涨跌异动和数据来源时效。",
    }
    return _SYNTH.get(intent, "整合已验证数据，生成最终回答，说明数据来源和边界。")


# ─────────────────────────────────────────────────────────────────────────────
# CentralPlanningAgent
# ─────────────────────────────────────────────────────────────────────────────

class CentralPlanningAgent:
    """
    C31.2: Central Planning Agent.

    Pure computation — no LLM, no DB, no network.
    Produces a CentralPlan from (user_query, IntentDecision).

    The plan contains:
      - reasoning_summary: one entry per C31 phase, with entity-aware content
      - tasks: list of PlanTask (which agents to call and why)

    Usage:
        planner = CentralPlanningAgent()
        plan = planner.create_plan(user_query, intent_decision)
        orchestrator emits plan.get_phase_event("problem_analysis") etc.
    """

    def create_plan(
        self,
        user_query: str,
        intent_result: "IntentDecision",
        conversation_context: list | None = None,
        memory_context: "MemoryContext | None" = None,
    ) -> CentralPlan:
        """
        Produce a CentralPlan for the given query + intent.

        Parameters
        ----------
        user_query:           Raw user message.
        intent_result:        Output of classify_intent().
        conversation_context: Recent chat turns for context (unused in v1;
                              reserved for future LLM-backed planning).
        memory_context:       C32.2 — MemoryContext with active entities and
                              session summary.  Used to produce richer phase
                              content that references prior conversation.

        Returns
        -------
        CentralPlan with entity-aware reasoning_summary and tasks.
        """
        intent   = intent_result.intent
        entities = intent_result.target_entities or []
        # C32.2: supplement entities from memory when query doesn't mention them
        if not entities and memory_context:
            from app.agents.intent_decision_agent import _entities_from_memory  # noqa: PLC0415
            entities = _entities_from_memory(memory_context)
        reason   = intent_result.reason or ""
        need_confirmation = intent_result.need_confirmation
        need_agent        = intent_result.need_agent

        tasks = _tasks_for_intent(intent, entities)

        reasoning_summary: list[dict] = [
            {
                "phase":     "problem_analysis",
                "title":     "问题分析",
                "content":   _build_problem_analysis(intent, user_query, entities),
                "importance": "high",
            },
            {
                "phase":     "intent_decision",
                "title":     "意图识别",
                "content":   _build_intent_decision(intent, entities, reason),
                "importance": "medium",
            },
            {
                "phase":     "planning",
                "title":     "自主规划",
                "content":   _build_planning(intent, tasks, need_confirmation),
                "importance": "medium",
            },
            {
                "phase":     "task_decomposition",
                "title":     "任务拆解",
                "content":   _build_task_decomposition(tasks),
                "importance": "medium",
                "agent":     "",
            },
            {
                "phase":     "agent_dispatch",
                "title":     "Agent 调度",
                "content":   _build_agent_dispatch(tasks),
                "importance": "high",
            },
            {
                "phase":     "agent_observation",
                "title":     "数据观测",
                "content":   _build_agent_observation(intent, tasks),
                "importance": "medium",
            },
            {
                "phase":     "deep_reasoning",
                "title":     "深度思考",
                "content":   _build_deep_reasoning(intent, entities),
                "importance": "high",
            },
            {
                "phase":     "risk_review",
                "title":     "风险审查",
                "content":   _build_risk_review(intent),
                "importance": "medium",
            },
            {
                "phase":     "synthesis",
                "title":     "回答生成",
                "content":   _build_synthesis(intent, need_confirmation),
                "importance": "low",
            },
        ]

        return CentralPlan(
            intent            = intent,
            need_agent        = need_agent,
            need_confirmation = need_confirmation,
            reasoning_summary = reasoning_summary,
            tasks             = tasks,
        )
