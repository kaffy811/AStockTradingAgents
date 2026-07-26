"""Change calculator for Company V2 explicit report comparison."""
from __future__ import annotations

from typing import Any


def _sort_reports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[int, int]:
        year = int(row.get("report_year") or 0)
        report_type = str(row.get("report_type") or "")
        type_rank = {"annual": 3, "q3": 2, "quarterly": 2, "semiannual": 1, "semi_annual": 1, "q1": 0}.get(report_type, 0)
        return (year, type_rank)

    return sorted(rows, key=key)


def _period_warning(rows: list[dict[str, Any]]) -> str | None:
    report_types = {str(row.get("report_type") or "") for row in rows if row.get("report_type")}
    if "annual" in report_types and any(t in {"q1", "q3", "quarterly"} for t in report_types):
        return "period_basis_warning"
    if len({row.get("report_year") for row in rows if row.get("report_year") is not None}) > 1 and any(
        row.get("report_type") in {"q1", "q3", "quarterly"} for row in rows
    ):
        return "period_basis_warning"
    return None


def calculate_comparison_change(matrix_item: dict[str, Any]) -> dict[str, Any]:
    rows = _sort_reports([row for row in matrix_item.get("reports", []) if row.get("report_id") is not None])
    if len(rows) < 2:
        return {
            "metric": matrix_item.get("topic"),
            "comparable": False,
            "warning": "insufficient_evidence",
            "computed": False,
            "reports": rows,
        }

    previous = rows[0]
    latest = rows[-1]
    warnings: list[str] = []
    period_warning = _period_warning(rows)
    if period_warning:
        warnings.append(period_warning)

    if previous.get("unit") and latest.get("unit") and previous.get("unit") != latest.get("unit"):
        warnings.append("unit_mismatch")
        comparable = False
    elif previous.get("numeric_value") is None or latest.get("numeric_value") is None:
        warnings.append("insufficient_evidence")
        comparable = False
    else:
        comparable = True

    if not comparable:
        return {
            "metric": matrix_item.get("topic"),
            "previous": previous,
            "latest": latest,
            "absolute_change": None,
            "percentage_change": None,
            "change_unit": latest.get("unit") or previous.get("unit") or None,
            "computed": False,
            "comparable": False,
            "warnings": sorted(set(warnings)),
            "reports": rows,
        }

    previous_value = float(previous["numeric_value"])
    latest_value = float(latest["numeric_value"])
    absolute_change = latest_value - previous_value
    percentage_change = None
    if previous_value != 0:
        percentage_change = (absolute_change / abs(previous_value)) * 100.0
    if latest.get("unit") == "%" or previous.get("unit") == "%":
        change_unit = "percentage_points"
    else:
        change_unit = latest.get("unit") or previous.get("unit") or None
    if period_warning and change_unit != "percentage_points":
        warnings.append(period_warning)
    return {
        "metric": matrix_item.get("topic"),
        "previous": previous,
        "latest": latest,
        "absolute_change": absolute_change,
        "percentage_change": percentage_change,
        "change_unit": change_unit,
        "computed": True,
        "comparable": True,
        "warnings": sorted(set(warnings)),
        "reports": rows,
    }

