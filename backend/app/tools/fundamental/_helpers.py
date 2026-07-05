"""
公共工具 helper，供 Phase 2A 各财务分析工具复用。
不允许 LLM 调用，不允许引入爬虫。
"""
from __future__ import annotations
from typing import Any
import pandas as pd


def safe_float(v: Any, ndigits: int = 4) -> float | None:
    if v is None: return None
    try:
        f = float(v)
        return None if f != f else round(f, ndigits)  # NaN guard
    except (TypeError, ValueError):
        return None


def safe_div(num: Any, den: Any, ndigits: int = 4) -> float | None:
    """安全除法：分母 <= 0 或为 None 时返回 None。"""
    n = safe_float(num)
    d = safe_float(den)
    if n is None or d is None or d <= 0:
        return None
    return round(n / d, ndigits)


def safe_pct(num: Any, den: Any, ndigits: int = 2) -> float | None:
    """num/den * 100，分母 <=0 → None。"""
    r = safe_div(num, den, ndigits=6)
    return round(r * 100, ndigits) if r is not None else None


def filter_report_type(df: pd.DataFrame) -> pd.DataFrame:
    """只保留合并报表（report_type='1'）。"""
    if "report_type" in df.columns:
        merged = df[df["report_type"].astype(str) == "1"]
        return merged if not merged.empty else df
    return df


def filter_annual(df: pd.DataFrame) -> pd.DataFrame:
    """只保留年报（end_date 以 1231 结尾）。"""
    if "end_date" in df.columns:
        annual = df[df["end_date"].astype(str).str.endswith("1231")]
        return annual if not annual.empty else df
    return df


def fmt_date(s: Any) -> str | None:
    """YYYYMMDD → YYYY-MM-DD。"""
    if s is None: return None
    r = str(s).strip()
    if len(r) == 8:
        return f"{r[:4]}-{r[4:6]}-{r[6:]}"
    return r


def row_get(row: Any, col: str) -> Any:
    """从 DataFrame row 或 dict 安全获取值，缺列时返回 None。"""
    try:
        v = row[col] if hasattr(row, '__getitem__') else getattr(row, col, None)
        return None if (v is not None and isinstance(v, float) and v != v) else v  # NaN→None
    except (KeyError, AttributeError):
        return None
