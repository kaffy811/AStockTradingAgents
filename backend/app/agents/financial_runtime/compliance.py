"""L5 compliance gate for layered financial runtime."""
from __future__ import annotations

import re

from app.agents.financial_runtime.contracts import ComplianceReview, STATUS_SUCCESS, StructuredAnswer


_BANNED_TRADING_RE = re.compile(r"(建议|应该|可以).{0,6}(买入|卖出|持有)|目标价|保证收益|稳赚|必涨")


class ComplianceGate:
    """Rule-based policy and financial logic validation.

    The gate returns structured instructions only. It does not do global string
    replacements and it does not append disclaimers.
    """

    def review(self, answer: StructuredAnswer) -> ComplianceReview:
        policy_findings: list[dict] = []
        logic_findings: list[dict] = []
        text = "\n".join([
            answer.conclusion or "",
            "\n".join(answer.findings or []),
            "\n".join(answer.risks or []),
        ])
        if _BANNED_TRADING_RE.search(text):
            policy_findings.append({"code": "INVESTMENT_ADVICE_LANGUAGE", "severity": "block"})

        for table in answer.tables:
            for row in table.get("rows") or []:
                for key, value in row.items():
                    if key != "指标" and value in {"0", 0, "0.0"} and "暂无" in str(row):
                        logic_findings.append({"code": "MISSING_VALUE_AS_ZERO", "severity": "error"})

        edit_instructions = []
        if policy_findings:
            edit_instructions.append({
                "action": "replace_answer",
                "reason": "policy_violation",
                "replacement": "该问题涉及高风险投资建议或确定性预测，无法提供此类结论。",
            })
        return ComplianceReview(
            trace_id=answer.trace_id,
            status=STATUS_SUCCESS,
            passed=not policy_findings and not logic_findings,
            policy_findings=policy_findings,
            logic_findings=logic_findings,
            edit_instructions=edit_instructions,
        )


compliance_gate = ComplianceGate()
