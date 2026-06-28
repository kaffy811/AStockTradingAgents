"""
C30.2 — Agent Planner

Maps an IntentDecision → AgentPlan (a structured list of agent steps).

Available agent types:
  MarketAgent        — quote, kline, technical indicators
  FundamentalAgent   — financial statements, valuation
  NewsAgent          — news, announcements, events
  IndustryAgent      — industry hotspot, sector stocks
  ReportAgent        — report generation, read, persistence
  CompareAgent       — multi-stock comparison
  RiskReviewAgent    — risk screening (mandatory for report generation)
  ComplianceAgent    — financial language compliance (mandatory for report generation)
  SynthesisAgent     — final synthesis / summary

Rules:
  - direct_answer: no agent plan (or empty plan)
  - tool_answer: lightweight agents only (Market/News/Industry)
  - industry_research: IndustryAgent + NewsAgent + SynthesisAgent
  - compare_stocks: CompareAgent (+ Market for data)
  - report_generation: full 7-agent pipeline, requires_confirmation=True
  - historical_report_read: ReportAgent only
  - portfolio_or_watchlist: no heavy agents
  - RiskReviewAgent + ComplianceAgent ALWAYS included for report_generation
  - requires_confirmation=True for any action that writes to the database
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.agents.intent_decision_agent import IntentDecision


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentStep:
    agent:    str         # e.g. "IndustryAgent"
    task:     str         # human-readable task description
    required: bool = True


@dataclass
class AgentPlan:
    plan_id:               str
    intent:                str
    steps:                 list[AgentStep] = field(default_factory=list)
    requires_confirmation: bool = False
    notes:                 str  = ""

    def is_empty(self) -> bool:
        return len(self.steps) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Planner
# ─────────────────────────────────────────────────────────────────────────────

def build_plan(decision: IntentDecision) -> AgentPlan:
    """
    Build an AgentPlan from an IntentDecision.

    Returns an AgentPlan with zero steps for intents that need no agent
    (direct_answer, portfolio_or_watchlist without enrichment).
    """
    plan_id = str(uuid.uuid4())[:8]
    intent  = decision.intent

    if intent == "direct_answer":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [],
            notes   = "Plain Q&A — answered directly by LLM, no agent pipeline",
        )

    if intent == "tool_answer":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("MarketAgent", "获取实时行情、技术面数据", required=True),
                AgentStep("NewsAgent",   "检索最新新闻与公告",        required=False),
            ],
            requires_confirmation = False,
            notes = "Lightweight tool calls for real-time data",
        )

    if intent == "industry_research":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("IndustryAgent", "获取行业热度、龙头股列表",     required=True),
                AgentStep("NewsAgent",     "检索行业近期新闻与事件催化",   required=True),
                AgentStep("SynthesisAgent","综合行业研究结论，说明数据边界",required=True),
            ],
            requires_confirmation = False,
            notes = "Industry hotspot research — no compare card, no auto-navigate to compare page",
        )

    if intent == "compare_stocks":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("MarketAgent",  "获取各股票行情与技术面数据", required=True),
                AgentStep("CompareAgent", "执行多股横向对比分析",       required=True),
                AgentStep("SynthesisAgent","生成对比摘要",              required=True),
            ],
            requires_confirmation = False,
            notes = "Explicit multi-stock comparison",
        )

    if intent == "report_generation":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("MarketAgent",      "获取行情、技术指标",                         required=True),
                AgentStep("FundamentalAgent", "读取财务报表、估值数据",                     required=True),
                AgentStep("NewsAgent",        "检索相关新闻与公告",                         required=True),
                AgentStep("ReportAgent",      "调用综合分析协调器生成报告并落库",           required=True),
                AgentStep("RiskReviewAgent",  "风险审查：确认报告不含违规投资建议",         required=True),
                AgentStep("ComplianceAgent",  "金融合规审查：去除买卖建议/价格预测话语",    required=True),
                AgentStep("SynthesisAgent",   "生成最终综合摘要与报告链接",                 required=True),
            ],
            requires_confirmation = True,   # C30.2 Rule 6: write-to-DB needs confirmation
            notes = "Full 7-agent pipeline with risk + compliance gate. "
                    "Report is NOT created until user confirms.",
        )

    if intent == "historical_report_read":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("ReportAgent", "查找并读取历史报告内容", required=True),
            ],
            requires_confirmation = False,
            notes = "Read-only report lookup — no new report created",
        )

    if intent == "portfolio_or_watchlist":
        return AgentPlan(
            plan_id = plan_id,
            intent  = intent,
            steps   = [
                AgentStep("MarketAgent", "获取自选股最新行情数据", required=False),
            ],
            requires_confirmation = False,
            notes = "Watchlist / portfolio query",
        )

    # Fallback
    return AgentPlan(
        plan_id = plan_id,
        intent  = "unknown",
        steps   = [],
        notes   = f"Unknown intent '{intent}' — fallback to direct LLM answer",
    )
