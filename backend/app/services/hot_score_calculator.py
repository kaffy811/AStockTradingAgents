"""
Hot Score Calculator
====================
纯函数，不访问数据库，不调用外部接口。

输入：list[dict]，每条含 symbol、stock_name、amount、change_pct
输出：按 hot_score 降序排序的 list[dict]，附 rank

公式（v1）：
    HotScore = 0.7 * amount_norm + 0.3 * change_abs_norm

归一化：行业内 min-max；若 max == min 则统一置 0（而非 0.5）。
"""

from __future__ import annotations

import re

SCORE_VERSION = "v1"
DATA_SOURCE   = "akshare_stock_zh_a_spot"

# 正则：名称中含 ST、*ST、退 的股票剔除（不区分大小写）
_ST_PATTERN = re.compile(r"ST|\*ST|退", re.IGNORECASE)


def _minmax(values: list[float]) -> list[float]:
    """对 values 做 min-max 归一化；若 max==min 则全部置 0。"""
    mn = min(values)
    mx = max(values)
    if mx == mn:
        return [0.0] * len(values)
    rng = mx - mn
    return [(v - mn) / rng for v in values]


def calculate_hot_scores(
    stocks: list[dict],
    top_n: int | None = None,
) -> list[dict]:
    """
    计算行业内 Hot Score 并返回 Top-N 列表。

    参数
    ----
    stocks : list[dict]
        每条至少含 symbol、stock_name、amount、change_pct。
    top_n  : int | None
        若指定，只返回前 top_n 条；None 表示全部返回。

    返回
    ----
    list[dict]，包含 rank、symbol、stock_name、hot_score 等字段，按 hot_score 降序。
    """
    # ── 1. 过滤 ──────────────────────────────────────────────────────────────
    valid: list[dict] = []
    for s in stocks:
        name   = str(s.get("stock_name") or "")
        amount = s.get("amount")
        pct    = s.get("change_pct")

        if _ST_PATTERN.search(name):
            continue
        if amount is None or (isinstance(amount, float) and amount != amount):  # NaN
            continue
        try:
            amount_f = float(amount)
        except (TypeError, ValueError):
            continue
        if amount_f <= 0:
            continue
        if pct is None:
            continue
        try:
            pct_f = float(pct)
        except (TypeError, ValueError):
            continue

        valid.append({**s, "_amount_f": amount_f, "_pct_f": pct_f})

    if not valid:
        return []

    # ── 2. 归一化 ────────────────────────────────────────────────────────────
    amounts      = [r["_amount_f"] for r in valid]
    abs_changes  = [abs(r["_pct_f"]) for r in valid]

    amount_norms    = _minmax(amounts)
    change_abs_norms = _minmax(abs_changes)

    # ── 3. Hot Score ─────────────────────────────────────────────────────────
    scored: list[tuple[float, dict]] = []
    for i, r in enumerate(valid):
        an  = round(amount_norms[i],     6)
        cn  = round(change_abs_norms[i], 6)
        hs  = round(0.7 * an + 0.3 * cn, 6)

        scored.append((hs, {
            "symbol":          r.get("symbol", ""),
            "stock_name":      r.get("stock_name"),
            "amount":          r["_amount_f"],
            "change_pct":      r["_pct_f"],
            "amount_norm":     an,
            "change_abs_norm": cn,
            "hot_score":       hs,
            "score_version":   SCORE_VERSION,
            "data_source":     DATA_SOURCE,
            "score_factors": {
                "amount":           r["_amount_f"],
                "change_pct":       r["_pct_f"],
                "abs_change_pct":   abs(r["_pct_f"]),
                "amount_norm":      an,
                "change_abs_norm":  cn,
                "hot_score":        hs,
                "formula":          "0.7*amount_norm+0.3*change_abs_norm",
                "score_version":    SCORE_VERSION,
                "data_source":      DATA_SOURCE,
            },
        }))

    # 降序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 截断
    if top_n is not None:
        scored = scored[:top_n]

    # 加 rank
    result = []
    for rank, (_, item) in enumerate(scored, start=1):
        result.append({"rank": rank, **item})

    return result
