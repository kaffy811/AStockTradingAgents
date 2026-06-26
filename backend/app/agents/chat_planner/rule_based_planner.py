"""
C7 RuleBasedPlanner — pattern-based compound task detector.

Detects when a user message describes a multi-step research task and builds
a PlannerResult with ordered PlanSteps.  No LLM involved — pure regex rules.

Supported compound intent types
────────────────────────────────
anomaly_then_risk      "为什么涨…然后重点看风险"
report_then_risk       "解释报告…并告诉我最大的风险"
watchlist_scan         "看看自选股里有没有最近波动大的"
industry_then_stocks   "哪些行业热？每个行业挑几个股票看一下"
research_then_action   "分析688146，如果可以就加入自选"
compare_then_report    "比较宁德时代和紫金矿业，然后生成报告"

MAX_STEPS = 5
"""
from __future__ import annotations

import logging
import re

from app.agents.chat_planner.base import PlanStep, PlannerResult

log = logging.getLogger(__name__)

MAX_STEPS = 5

# ── Compound connector words ───────────────────────────────────────────────────

_COMPOUND_RE = re.compile(
    r"然后|再帮我|之后|并且|同时|如果|顺便|再看|接着|还要|还想|并告诉|并告知|顺带",
    re.IGNORECASE,
)

# ── Intent signal patterns ─────────────────────────────────────────────────────

_ANOMALY_SIG   = re.compile(
    r"为什么.{0,15}(涨|跌|异动|波动)"
    r"|(涨|跌|异动|波动).{0,15}(原因|为什么|怎么了)"
    r"|异动|异常波动|涨这么多|跌这么多",
    re.IGNORECASE,
)
_RISK_SIG      = re.compile(r"风险|最大风险|重点.*风险|风险.*研究|主要风险", re.IGNORECASE)
_REPORT_SIG    = re.compile(
    r"解释.{0,8}报告|报告.{0,8}解释|报告.{0,8}结论|最近.{0,4}报告|这份报告|报告里",
    re.IGNORECASE,
)
_WATCHLIST_SIG = re.compile(r"自选股|自选", re.IGNORECASE)
_SCAN_SIG      = re.compile(
    r"波动大|巡检|研究线索|最近涨|哪些.*关注|有没有.*值得|有没有.*关注",
    re.IGNORECASE,
)
_INDUSTRY_SIG  = re.compile(r"行业|热点|板块", re.IGNORECASE)
_STOCKS_DEEP_SIG = re.compile(r"股票|具体.*股|挑.*股|找.*股|每个.*股", re.IGNORECASE)
_COMPARE_SIG   = re.compile(r"对比|比较", re.IGNORECASE)
_ADD_WL_SIG    = re.compile(r"加入自选|添加.*自选|添加自选|加自选", re.IGNORECASE)
_GEN_RPT_SIG   = re.compile(r"生成.*报告|综合报告|分析报告|帮我.*报告", re.IGNORECASE)


class RuleBasedPlanner:
    """
    Pure rule-based compound task planner.

    Usage:
        planner = RuleBasedPlanner()
        if planner.is_compound(msg):
            result = planner.plan(msg)   # PlannerResult or None
    """

    def is_compound(self, message: str) -> bool:
        """Return True if the message looks like a multi-step research task."""
        has_connector = bool(_COMPOUND_RE.search(message))
        intent_count  = self._count_intent_signals(message)
        return has_connector or intent_count >= 2

    def plan(self, message: str) -> PlannerResult | None:
        """
        Build a plan for the given compound message.
        Returns None if no compound intent is detected.
        """
        if not self.is_compound(message):
            return None

        intent_type = self._detect_intent_type(message)
        if intent_type == "unknown":
            return None   # Let SkillRegistry handle it

        if intent_type == "clarification":
            return PlannerResult(
                ok=True,
                intent_type="clarification",
                steps=[PlanStep(
                    step_id=PlanStep.make_id("clarify"),
                    step_type="clarification",
                    name="clarification",
                    metadata={"reason": "无法确定目标股票或研究范围，请提供更多信息"},
                )],
                reason="无法从消息中确定具体研究目标，需要用户澄清",
            )

        steps = self._build_steps(intent_type, message)
        if not steps:
            return None

        # Enforce max steps
        steps = steps[:MAX_STEPS]

        return PlannerResult(
            ok=True,
            intent_type=intent_type,
            steps=steps,
            reason=f"检测到复合任务：{intent_type}",
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _count_intent_signals(self, msg: str) -> int:
        signals = [
            bool(_ANOMALY_SIG.search(msg)),
            bool(_RISK_SIG.search(msg)),
            bool(_REPORT_SIG.search(msg)),
            bool(_WATCHLIST_SIG.search(msg)) and bool(_SCAN_SIG.search(msg)),
            bool(_INDUSTRY_SIG.search(msg)) and bool(_STOCKS_DEEP_SIG.search(msg)),
            bool(_COMPARE_SIG.search(msg)),
            bool(_ADD_WL_SIG.search(msg)) and (
                bool(_ANOMALY_SIG.search(msg)) or bool(_REPORT_SIG.search(msg))
            ),
        ]
        return sum(signals)

    def _detect_intent_type(self, msg: str) -> str:
        has_anomaly   = bool(_ANOMALY_SIG.search(msg))
        has_risk      = bool(_RISK_SIG.search(msg))
        has_report    = bool(_REPORT_SIG.search(msg))
        has_watchlist = bool(_WATCHLIST_SIG.search(msg))
        has_industry  = bool(_INDUSTRY_SIG.search(msg))
        has_stocks_d  = bool(_STOCKS_DEEP_SIG.search(msg))
        has_compare   = bool(_COMPARE_SIG.search(msg))
        has_add_wl    = bool(_ADD_WL_SIG.search(msg))
        has_gen_rpt   = bool(_GEN_RPT_SIG.search(msg))
        has_scan      = bool(_SCAN_SIG.search(msg))

        # research_then_action: any research + add_watchlist
        if (has_anomaly or has_report or has_risk) and has_add_wl:
            return "research_then_action"

        # anomaly_then_risk
        if has_anomaly and has_risk:
            return "anomaly_then_risk"

        # report_then_risk
        if has_report and has_risk:
            return "report_then_risk"

        # watchlist_scan: watchlist + scan indicator
        if has_watchlist and has_scan:
            return "watchlist_scan"

        # industry_then_stocks
        if has_industry and has_stocks_d:
            return "industry_then_stocks"

        # compare_then_report: compare + generate-report
        if has_compare and has_gen_rpt:
            return "compare_then_report"

        return "unknown"

    def _build_steps(self, intent_type: str, msg: str) -> list[PlanStep]:
        if intent_type == "anomaly_then_risk":
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="skill",
                    name="stock_anomaly_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("s2"),
                    step_type="skill",
                    name="risk_first_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("fin"),
                    step_type="final_summary",
                    name="final_summary",
                ),
            ]

        elif intent_type == "report_then_risk":
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="skill",
                    name="report_explanation_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("s2"),
                    step_type="skill",
                    name="risk_first_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("fin"),
                    step_type="final_summary",
                    name="final_summary",
                ),
            ]

        elif intent_type == "watchlist_scan":
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="skill",
                    name="watchlist_review_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("fin"),
                    step_type="final_summary",
                    name="final_summary",
                ),
            ]

        elif intent_type == "industry_then_stocks":
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="skill",
                    name="industry_hotspot_skill",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("fin"),
                    step_type="final_summary",
                    name="final_summary",
                ),
            ]

        elif intent_type == "research_then_action":
            # Prefer anomaly skill for research; fallback to risk_first
            research_skill = (
                "stock_anomaly_skill" if _ANOMALY_SIG.search(msg) else "risk_first_skill"
            )
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="skill",
                    name=research_skill,
                ),
                PlanStep(
                    step_id=PlanStep.make_id("fin"),
                    step_type="final_summary",
                    name="final_summary",
                ),
                PlanStep(
                    step_id=PlanStep.make_id("act"),
                    step_type="action",
                    name="add_watchlist",
                    requires_confirmation=True,
                    metadata={"action_type": "add_watchlist"},
                ),
            ]

        elif intent_type == "compare_then_report":
            # Can't safely determine which stock to generate a report for → clarify
            return [
                PlanStep(
                    step_id=PlanStep.make_id("s1"),
                    step_type="action",
                    name="create_compare",
                    requires_confirmation=True,
                    metadata={"action_type": "create_compare"},
                ),
                PlanStep(
                    step_id=PlanStep.make_id("clarify"),
                    step_type="clarification",
                    name="clarification",
                    metadata={"reason": "请指定要为哪一只股票生成报告"},
                ),
            ]

        return []
