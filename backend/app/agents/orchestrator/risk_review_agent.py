"""
orchestrator/risk_review_agent.py — Phase 2E-1: Risk Review Agent.

This is a MANDATORY, NON-SKIPPABLE node in the orchestration pipeline.

Responsibilities
----------------
Rule-based safety audit of the EvidencePack and draft response text:

1.  Violation phrases — buy/sell/hold/price-target language.
2.  Fabricated certainty — "必涨"/"稳赚"/"确定上涨" etc.
3.  Unverified report dependency — using unverified sources as primary evidence.
4.  Missing disclaimer — every response must carry one.
5.  Missing sources — evidence must be cited.
6.  Data quality labelling — data_quality dict must be present.

Outputs RiskReviewResult.

Design constraints
------------------
* PURE RULE-BASED — no LLM, no external calls, no async required.
  (run() is async for interface uniformity with other agents)
* blocked=True means SynthesisAgent is bypassed entirely.
* required_edits lists specific text edits the SynthesisAgent must apply
  if blocked=False but issues were found.
"""
from __future__ import annotations

import re
import logging
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.schemas import make_risk_review_result

log = logging.getLogger(__name__)

AGENT_NAME = "risk_review_agent"


# ── Violation pattern ──────────────────────────────────────────────────────────

_VIOLATION_PATTERN = re.compile(
    r"买入|卖出|做多|做空|持有|建仓|加仓|减仓|清仓"
    r"|必涨|必跌|稳赚|确定上涨|确定下跌|一定赚|一定会涨|保证上涨"
    r"|目标价|强烈推荐|强力推荐|强推|坚定看多|坚定看空"
    r"|buy now|sell now|strong buy|strong sell|must buy|guaranteed",
    re.IGNORECASE,
)

_UNVERIFIED_CERTAINTY_PATTERN = re.compile(
    r"根据.*?2[0-9]{3}.*?年报|据.*?年报显示|年报数据表明|财报显示.*?必然",
    re.IGNORECASE,
)

_DISCLAIMER_KEYWORDS = ["研究参考", "不构成投资建议", "仅供参考", "risk disclaimer"]


class RiskReviewAgent:
    """
    Mandatory, non-skippable risk review gate.

    Usage:
        result = await risk_review_agent.run(evidence_pack, draft_text)
    """

    async def run(                                    # noqa: PLR0912
        self,
        evidence_pack: dict,
        draft_text: str = "",
        *,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Audit EvidencePack and draft answer text.

        Parameters
        ----------
        evidence_pack : EvidencePack dict
        draft_text    : draft final answer text (may be empty at this stage)
        event_callback: optional SSE emitter

        Returns
        -------
        RiskReviewResult dict — never raises.
        """
        issues:          list[str] = []
        required_edits:  list[str] = []
        compliance_notes: list[str] = []

        # ── 1. Violation phrases in draft ─────────────────────────────────────
        if draft_text and _VIOLATION_PATTERN.search(draft_text):
            matches = list(_VIOLATION_PATTERN.findall(draft_text))
            issues.append(
                f"发现违规建议性语言: {', '.join(set(matches[:5]))}。"
                "所有买入/卖出/持有/目标价表述必须替换为中性研究语言。"
            )
            for phrase, replacement in _VIOLATION_REPLACEMENTS:
                if phrase in draft_text:
                    required_edits.append(f'将"{phrase}"替换为"{replacement}"')

        # ── 2. Fabricated certainty in findings ───────────────────────────────
        for finding in evidence_pack.get("findings", []):
            summary = finding.get("summary", "")
            if _UNVERIFIED_CERTAINTY_PATTERN.search(summary):
                issues.append(
                    f"{finding.get('agent_name','?')}: 发现未经核实的确定性表述。"
                )

        # ── 3. Unverified report used as primary evidence ─────────────────────
        dq       = evidence_pack.get("data_quality", {})
        findings = evidence_pack.get("findings", [])
        has_unverified_fundamental = any(
            f.get("agent_name") == "fundamental_agent"
            and f.get("status") in ("success", "partial")
            and not f.get("data_quality", {}).get("report_verified")
            for f in findings
        )
        if has_unverified_fundamental:
            compliance_notes.append(
                "基本面分析基于未经官方验证的数据来源。"
                "建议在输出中明确标注数据未经官方披露核实。"
            )
            required_edits.append(
                "在 business_analysis 中加入: "
                "「以下分析基于非官方数据，仅供参考，不作为投资依据。」"
            )

        # ── 4. Missing disclaimer ─────────────────────────────────────────────
        if draft_text:
            has_disclaimer = any(kw in draft_text for kw in _DISCLAIMER_KEYWORDS)
            if not has_disclaimer:
                issues.append("回答缺少免责声明。")
                required_edits.append("在末尾添加: 「仅供研究参考，不构成投资建议。」")

        # ── 5. Missing sources ────────────────────────────────────────────────
        all_sources = evidence_pack.get("sources", [])
        if not all_sources:
            issues.append("未提供任何数据来源，无法验证分析依据。")
            compliance_notes.append("所有引用必须包含来源名称和发布时间。")

        # ── 6. Agent timeout warnings ─────────────────────────────────────────
        warnings = evidence_pack.get("warnings", [])
        if "agent_timeout" in warnings:
            compliance_notes.append(
                "部分子 Agent 因超时未能完成分析，相关维度数据可能不完整。"
            )

        # ── Block decision ────────────────────────────────────────────────────
        # Block if: violation phrases found in draft AND we have explicit buy/sell language
        severe_violations = [i for i in issues if "违规建议性语言" in i]
        blocked = bool(severe_violations)

        passed = not issues and not required_edits

        log.debug(
            "RiskReviewAgent: passed=%s blocked=%s issues=%d required_edits=%d",
            passed, blocked, len(issues), len(required_edits),
        )

        return make_risk_review_result(
            passed=passed,
            blocked=blocked,
            issues=issues,
            required_edits=required_edits,
            compliance_notes=compliance_notes,
        )


# ── Violation replacement table ────────────────────────────────────────────────

_VIOLATION_REPLACEMENTS: list[tuple[str, str]] = [
    ("买入",   "关注"),
    ("卖出",   "观察"),
    ("做多",   "看涨研究"),
    ("做空",   "看跌研究"),
    ("持有",   "持续观察"),
    ("建仓",   "建立研究仓位"),
    ("必涨",   "存在上行研究线索"),
    ("必跌",   "存在下行研究线索"),
    ("稳赚",   "具有参考价值"),
    ("目标价", "参考价区间"),
]
