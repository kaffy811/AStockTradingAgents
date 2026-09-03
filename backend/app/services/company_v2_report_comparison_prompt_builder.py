"""Prompt contract for explicit Company V2 report comparison."""
from __future__ import annotations

from typing import Any


SYSTEM_RULES = [
    "Compare only the explicitly selected reports.",
    "Treat each report as an isolated evidence source.",
    "Do not use unselected reports.",
    "Do not infer missing values.",
    "Do not compare incompatible periods or definitions.",
    "Cite report year, type, and page for every major claim.",
    "Do not provide investment advice or future predictions.",
    "If evidence is incomplete, say so.",
]


def build_comparison_prompt(question: str, evidence_matrix: list[dict[str, Any]]) -> dict[str, Any]:
    selected_reports = []
    for item in evidence_matrix:
        for row in item.get("reports", []):
            selected_reports.append(
                {
                    "report_id": row.get("report_id"),
                    "report_year": row.get("report_year"),
                    "report_type": row.get("report_type"),
                    "pages": row.get("evidence_pages") or [],
                }
            )
    return {
        "system_rules": SYSTEM_RULES,
        "question": question,
        "selected_reports": selected_reports,
        "evidence_topics": [item.get("topic") for item in evidence_matrix],
    }

