"""
app/services/free_mode_visibility_service.py — Free Mode 模块可见性决策服务

根据 diagnostics 结果决定哪些 Company Tab section 可见。

免费模式下，许多 Tushare 付费接口无数据，此服务帮助前端决定哪些区块需要显示
（始终显示）以及哪些区块应根据数据可用性动态隐藏。
"""
from __future__ import annotations

# ── 始终显示的 section（不依赖数据可用性）───────────────────────────────────
ALWAYS_SHOW_SECTION_IDS: frozenset[str] = frozenset({
    "overview",
    "highlight-risk",
    "ai-analysis",
    "report-documents",
})

# ── 数据驱动的 section（至少一个关联 module_key 有数据才显示）───────────────
SHOW_IF_DATA_SECTIONS: dict[str, list[str]] = {
    "valuation":        ["valuation"],
    "dividend":         ["dividend_history"],
    "main-business":    ["main_business"],
    "industry":         ["industry_rank"],
    "growth":           ["growth", "financial_summary"],
    "profitability":    ["profitability", "expense_analysis"],
    "earnings-quality": ["cashflow_quality"],
    "asset-structure":  ["asset_structure"],
    "solvency":         ["solvency"],
    "capital":          ["capital_occupation"],
    "operations":       ["operation_capability"],
    "dupont":           ["dupont"],
    "shareholders":     ["major_holders", "equity_structure"],
}


def compute_section_visibility(module_diagnostics: list[dict]) -> dict[str, bool]:
    """
    根据 diagnostics 结果计算每个 section 的可见性。

    Parameters
    ----------
    module_diagnostics : list[dict]
        每个 dict 包含：
          - module_key : str
          - status     : "ok" | "partial" | "empty" | "failed"
          - rows_count : int

    Returns
    -------
    dict[str, bool]
        section_id → True（显示）/ False（隐藏）
    """
    # 建立 module_key → diagnostic 快速查找
    diag_by_key: dict[str, dict] = {}
    for d in module_diagnostics:
        key = d.get("module_key", "")
        if key:
            diag_by_key[key] = d

    visibility: dict[str, bool] = {}

    # ALWAYS_SHOW sections
    for section_id in ALWAYS_SHOW_SECTION_IDS:
        visibility[section_id] = True

    # SHOW_IF_DATA sections
    for section_id, module_keys in SHOW_IF_DATA_SECTIONS.items():
        section_visible = False
        for mk in module_keys:
            d = diag_by_key.get(mk)
            if d is None:
                continue
            status = d.get("status", "failed")
            rows_count = d.get("rows_count", 0) or 0
            if status in ("ok", "partial") or rows_count > 0:
                section_visible = True
                break
        visibility[section_id] = section_visible

    return visibility


def get_unavailable_sections(
    visibility: dict[str, bool],
    all_section_ids: list[str],
) -> list[str]:
    """
    返回在 all_section_ids 中但不可见（visibility 为 False）的 section ID 列表。

    Parameters
    ----------
    visibility : dict[str, bool]
        compute_section_visibility 的返回值。
    all_section_ids : list[str]
        前端所有已知 section ID。

    Returns
    -------
    list[str]
        不可见的 section ID 列表（按 all_section_ids 顺序）。
    """
    return [
        sid for sid in all_section_ids
        if not visibility.get(sid, True)
    ]
