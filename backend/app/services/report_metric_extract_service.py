"""
app/services/report_metric_extract_service.py — PDF 年报指标提取服务（Phase 6N-8B）

从已解析的年报 PDF 文本或 RAG chunks 中提取关键财务指标，
写入 report_extracted_metrics 表（需 DB migration 创建）。

安全原则：
- confidence >= 0.75 才可作为 extracted_confirmed（进入核心卡片）
- confidence < 0.75 只作为 candidate，不进入核心卡片
- 不编造数值，无法提取则返回空
- RAG chunk 只作为 evidence，不作为 confirmed structural metric
- source 显示 "来自年报 PDF 抽取"
- 不编造页码
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# ── 目标指标定义 ────────────────────────────────────────────────────────────────

METRIC_DEFINITIONS = [
    {
        "metric_key":  "revenue",
        "metric_name": "营业收入",
        "unit":        "元",
        "patterns": [
            r"营业(?:总)?收入[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
            r"revenue[：:\s]*([0-9,，\.]+)\s*(?:billion|million|yuan)?",
        ],
        "scale_hints": {"亿元": 1e8, "万元": 1e4, "元": 1.0},
    },
    {
        "metric_key":  "net_profit_parent",
        "metric_name": "归母净利润",
        "unit":        "元",
        "patterns": [
            r"归(?:属于母公司股东的)?净利润[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
            r"归母净利润[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
        ],
        "scale_hints": {"亿元": 1e8, "万元": 1e4, "元": 1.0},
    },
    {
        "metric_key":  "operating_cashflow",
        "metric_name": "经营活动现金流量净额",
        "unit":        "元",
        "patterns": [
            r"经营活动(?:产生的)?现金流量净额[：:\s]*([0-9,，\.\-]+)\s*(?:亿元|万元|元)?",
        ],
        "scale_hints": {"亿元": 1e8, "万元": 1e4, "元": 1.0},
    },
    {
        "metric_key":  "total_assets",
        "metric_name": "总资产",
        "unit":        "元",
        "patterns": [
            r"资产总(?:计|额)[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
            r"总资产[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
        ],
        "scale_hints": {"亿元": 1e8, "万元": 1e4, "元": 1.0},
    },
    {
        "metric_key":  "equity_parent",
        "metric_name": "归母净资产",
        "unit":        "元",
        "patterns": [
            r"归(?:属于母公司股东的)?(?:所有者)?权益合计[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
            r"归母净资产[：:\s]*([0-9,，\.]+)\s*(?:亿元|万元|元)?",
        ],
        "scale_hints": {"亿元": 1e8, "万元": 1e4, "元": 1.0},
    },
    {
        "metric_key":  "eps_basic",
        "metric_name": "基本每股收益",
        "unit":        "元/股",
        "patterns": [
            r"基本(?:每股收益|EPS)[：:\s]*([0-9,，\.\-]+)\s*元(?:/股)?",
            r"每股收益(?:（基本）)?[：:\s]*([0-9,，\.\-]+)",
        ],
        "scale_hints": {},
    },
    {
        "metric_key":  "roe_weighted",
        "metric_name": "加权平均净资产收益率",
        "unit":        "%",
        "patterns": [
            r"加权平均净资产收益率[：:\s]*([0-9,，\.\-]+)%?",
            r"加权ROE[：:\s]*([0-9,，\.\-]+)%?",
        ],
        "scale_hints": {},
    },
    {
        "metric_key":  "debt_ratio",
        "metric_name": "资产负债率",
        "unit":        "%",
        "patterns": [
            r"资产负债率[：:\s]*([0-9,，\.]+)%?",
        ],
        "scale_hints": {},
    },
    {
        "metric_key":  "dividend_per_share",
        "metric_name": "每股分红",
        "unit":        "元/股",
        "patterns": [
            r"每(?:10)?股(?:派发)?现金红利[：:\s]*([0-9,，\.]+)元",
            r"每股分红[：:\s]*([0-9,，\.]+)元?",
        ],
        "scale_hints": {},
    },
]


def _clean_num(raw: str) -> float | None:
    """Clean number string → float. Returns None on failure."""
    try:
        s = raw.replace(",", "").replace("，", "").replace(" ", "")
        return float(s)
    except (ValueError, TypeError):
        return None


def extract_metrics_from_text(
    text: str,
    report_id: str,
    ts_code: str,
    period: str,
    extraction_method: str = "regex",
) -> list[dict[str, Any]]:
    """
    Extract financial metrics from plain text (e.g. from PDF extraction).

    Returns a list of metric dicts ready for insertion into report_extracted_metrics.
    Only metrics with confidence >= 0.35 are returned (caller filters on 0.75 threshold).
    """
    results = []

    for defn in METRIC_DEFINITIONS:
        for pattern in defn["patterns"]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if not matches:
                continue

            raw_val = matches[0] if matches else None
            if raw_val is None:
                continue

            num = _clean_num(raw_val)
            if num is None:
                continue

            # Detect scale from surrounding context (search near the match)
            scale = 1.0
            for scale_kw, scale_factor in defn.get("scale_hints", {}).items():
                # look for scale keyword near the pattern match
                pattern_pos = text.find(raw_val)
                context = text[max(0, pattern_pos - 20): pattern_pos + len(raw_val) + 10]
                if scale_kw in context:
                    scale = scale_factor
                    break

            value = num * scale

            # Confidence heuristic: full match with scale → 0.85, without → 0.70
            confidence = 0.85 if scale != 1.0 or defn["unit"] in ("%", "元/股") else 0.70

            # Find source_text: a window around the match
            idx = text.find(raw_val)
            source_text = text[max(0, idx - 50): idx + 100].strip() if idx >= 0 else ""

            results.append({
                "report_id":         report_id,
                "ts_code":           ts_code,
                "period":            period,
                "metric_key":        defn["metric_key"],
                "metric_name":       defn["metric_name"],
                "value":             value,
                "unit":              defn["unit"],
                "source_text":       source_text[:500],
                "confidence":        confidence,
                "extraction_method": extraction_method,
                "page_hint":         None,  # page info not available from plain text
            })
            break  # stop trying patterns for this metric once found

    return results


def filter_confirmed(metrics: list[dict]) -> list[dict]:
    """
    Return only metrics with confidence >= 0.75 (extracted_confirmed).
    Lower confidence metrics are candidates only — do not put them in core cards.
    """
    return [m for m in metrics if m.get("confidence", 0) >= 0.75]


async def extract_and_store_metrics(
    db: Any,
    report_id: str,
    ts_code: str,
    period: str,
    text: str,
) -> dict[str, Any]:
    """
    Extract metrics from PDF text and store them in report_extracted_metrics table.

    Returns a summary dict: {extracted: int, confirmed: int, candidates: int}.
    Silently skips DB insert if table does not exist (migration not yet run).
    """
    all_metrics = extract_metrics_from_text(
        text=text,
        report_id=report_id,
        ts_code=ts_code,
        period=period,
    )

    confirmed = filter_confirmed(all_metrics)
    candidates = [m for m in all_metrics if m not in confirmed]

    log.info(
        "PDF metric extraction: report_id=%s ts_code=%s "
        "total=%d confirmed=%d candidates=%d",
        report_id, ts_code, len(all_metrics), len(confirmed), len(candidates),
    )

    if db is not None and all_metrics:
        try:
            await _store_metrics(db, all_metrics)
        except Exception as exc:
            log.warning(
                "report_extracted_metrics insert failed (table may not exist): %s",
                exc,
            )

    return {
        "extracted":  len(all_metrics),
        "confirmed":  len(confirmed),
        "candidates": len(candidates),
        "metrics":    confirmed,  # only return confirmed to callers
    }


async def _store_metrics(db: Any, metrics: list[dict]) -> None:
    """
    Insert/upsert metrics into report_extracted_metrics table.
    Silently skips if table does not exist.
    """
    from sqlalchemy import text as sa_text
    from datetime import datetime, timezone

    for m in metrics:
        await db.execute(
            sa_text("""
                INSERT INTO report_extracted_metrics
                    (report_id, ts_code, period, metric_key, metric_name,
                     value, unit, source_text, confidence, extraction_method,
                     page_hint, created_at)
                VALUES
                    (:report_id, :ts_code, :period, :metric_key, :metric_name,
                     :value, :unit, :source_text, :confidence, :extraction_method,
                     :page_hint, :created_at)
                ON CONFLICT (report_id, metric_key) DO UPDATE SET
                    value             = EXCLUDED.value,
                    confidence        = EXCLUDED.confidence,
                    source_text       = EXCLUDED.source_text,
                    extraction_method = EXCLUDED.extraction_method,
                    created_at        = EXCLUDED.created_at
            """),
            {
                **m,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    await db.commit()


async def get_confirmed_metrics_for_stock(
    db: Any,
    ts_code: str,
    period: str | None = None,
    min_confidence: float = 0.75,
) -> list[dict]:
    """
    Retrieve confirmed extracted metrics for a stock from the DB.
    Returns [] if table does not exist or no data found.
    """
    from sqlalchemy import text as sa_text

    try:
        q = """
            SELECT metric_key, metric_name, value, unit, source_text, confidence,
                   extraction_method, period, report_id
            FROM report_extracted_metrics
            WHERE ts_code = :ts_code AND confidence >= :min_confidence
        """
        params: dict = {"ts_code": ts_code, "min_confidence": min_confidence}
        if period:
            q += " AND period = :period"
            params["period"] = period
        q += " ORDER BY confidence DESC, created_at DESC"

        result = await db.execute(sa_text(q), params)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as exc:
        log.debug("get_confirmed_metrics_for_stock failed: %s", exc)
        return []
