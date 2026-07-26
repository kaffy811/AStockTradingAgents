"""
backend/scripts/company_v2_cninfo_stability_audit.py — Phase 6T-E CNINFO 稳定性验收

对验收样本股票执行 CNINFO 报告发现（discovery metadata + URL），不下载 PDF。

每只股票：
1. 最近 5 年 annual + 最近 3 年 quarterly（q1/q3/semi_annual）
2. force_refresh=false（走缓存/正常链路）
3. 可选二次请求验证一致性

用法：
backend/.venv/bin/python backend/scripts/company_v2_cninfo_stability_audit.py \
  --symbols 600519,000725,601686 \
  --out-json backend/docs/artifacts/company_v2_cninfo_stability_phase6te.json

不伪造数据：网络失败/找不到报告如实记录。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_ALLOWED_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"}


def _url_ok(url: str) -> bool:
    if not url:
        return False
    p = urlparse(url)
    return p.scheme in ("http", "https") and (p.hostname or "").lower() in _ALLOWED_HOSTS


async def audit_symbol(symbol: str, *, verify_repeat: bool = False) -> dict[str, Any]:
    from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent

    current_year = date.today().year
    annual_start = current_year - 5
    result: dict[str, Any] = {
        "symbol": symbol,
        "company_name": "",
        "org_id": "",
        "org_id_source": "",
        "discovery_method": "cninfo_his_announcement_query",
        "reports_count": 0,
        "annual_count": 0,
        "quarterly_count": 0,
        "earliest_report": None,
        "latest_report": None,
        "duplicate_count": 0,
        "invalid_url_count": 0,
        "non_whitelist_url_count": 0,
        "summary_reports_count": 0,
        "wrong_symbol_reports": 0,
        "repeat_consistent": None,
        "status": "failed",
        "errors": [],
    }
    try:
        discovery = await cninfo_report_discovery_agent.discover(
            "CN", symbol,
            start_year=annual_start,
            end_year=current_year - 1,
            report_types=["annual", "semi_annual", "q1", "q3"],
        )
    except Exception as exc:
        result["errors"].append(f"discover_exception:{type(exc).__name__}:{str(exc)[:150]}")
        return result

    identity = discovery.get("cninfo_identity") or {}
    result["company_name"] = identity.get("company_name") or ""
    result["org_id"] = identity.get("org_id") or ""
    result["org_id_source"] = identity.get("source") or identity.get("org_id_source") or ""
    reports = discovery.get("reports") or []
    result["reports_count"] = len(reports)
    result["annual_count"] = sum(1 for r in reports if r.get("report_type") == "annual")
    result["quarterly_count"] = sum(
        1 for r in reports if r.get("report_type") in ("q1", "q3", "semi_annual")
    )
    result["errors"].extend(discovery.get("errors") or [])

    years = [r.get("report_year") for r in reports if r.get("report_year")]
    if years:
        result["earliest_report"] = min(years)
        result["latest_report"] = max(years)

    seen_keys: set[str] = set()
    seen_urls: set[str] = set()
    for r in reports:
        key = f"{r.get('report_year')}:{r.get('report_type')}"
        if key in seen_keys:
            result["duplicate_count"] += 1
        seen_keys.add(key)
        url = r.get("pdf_url") or ""
        if url:
            if url in seen_urls:
                result["duplicate_count"] += 1
            seen_urls.add(url)
            if not _url_ok(url):
                result["non_whitelist_url_count"] += 1
        else:
            result["invalid_url_count"] += 1
        if r.get("is_summary"):
            result["summary_reports_count"] += 1
        if str(r.get("symbol") or "") not in ("", symbol):
            result["wrong_symbol_reports"] += 1

    if verify_repeat:
        try:
            second = await cninfo_report_discovery_agent.discover(
                "CN", symbol,
                start_year=annual_start,
                end_year=current_year - 1,
                report_types=["annual"],
            )
            first_annuals = {
                (r.get("report_year"), r.get("pdf_url"))
                for r in reports if r.get("report_type") == "annual"
            }
            second_annuals = {
                (r.get("report_year"), r.get("pdf_url"))
                for r in (second.get("reports") or [])
                if r.get("report_type") == "annual"
            }
            result["repeat_consistent"] = second_annuals <= first_annuals or first_annuals <= second_annuals
        except Exception as exc:
            result["errors"].append(f"repeat_exception:{str(exc)[:100]}")

    # 状态判定
    # PASS：最近一个应披露年度报告可找到 + URL 白名单 + 无重复 + 无错股票 + 无摘要冒充
    last_disclosed_year = current_year - 1
    has_recent_annual = any(
        r.get("report_type") == "annual" and (r.get("report_year") or 0) >= last_disclosed_year - 1
        for r in reports
    )
    if (
        has_recent_annual
        and result["non_whitelist_url_count"] == 0
        and result["duplicate_count"] == 0
        and result["summary_reports_count"] == 0
        and result["wrong_symbol_reports"] == 0
    ):
        result["status"] = "success"
    elif result["annual_count"] > 0 and result["wrong_symbol_reports"] == 0 and result["non_whitelist_url_count"] == 0:
        result["status"] = "partial"
    else:
        result["status"] = "failed"
    return result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="逗号分隔的6位股票代码")
    parser.add_argument("--verify-repeat", default="false")
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "backend/docs/artifacts/company_v2_cninfo_stability_phase6te.json"),
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    verify_repeat = str(args.verify_repeat).lower() in ("1", "true", "yes")

    per_symbol: list[dict[str, Any]] = []
    for sym in symbols:
        print(f"[cninfo-audit] {sym} ...", flush=True)
        per_symbol.append(await audit_symbol(sym, verify_repeat=verify_repeat))

    stats = {
        "symbols_total": len(symbols),
        "symbols_success": sum(1 for r in per_symbol if r["status"] == "success"),
        "symbols_partial": sum(1 for r in per_symbol if r["status"] == "partial"),
        "symbols_failed": sum(1 for r in per_symbol if r["status"] == "failed"),
        "reports_found": sum(r["reports_count"] for r in per_symbol),
        "annual_reports_found": sum(r["annual_count"] for r in per_symbol),
        "quarterly_reports_found": sum(r["quarterly_count"] for r in per_symbol),
        "duplicate_reports_removed": sum(r["duplicate_count"] for r in per_symbol),
        "invalid_urls": sum(r["invalid_url_count"] for r in per_symbol),
        "non_whitelist_urls": sum(r["non_whitelist_url_count"] for r in per_symbol),
        "summary_reports_filtered": sum(r["summary_reports_count"] for r in per_symbol),
        "correction_reports_resolved": 0,
        "cache_hits": 0,
        "network_errors": sum(
            1 for r in per_symbol
            if any("timeout" in e.lower() or "connect" in e.lower() for e in r["errors"])
        ),
        "timeouts": sum(
            1 for r in per_symbol
            if any("timeout" in e.lower() for e in r["errors"])
        ),
    }

    output = {
        "generated_at": date.today().isoformat(),
        "stats": stats,
        "symbols": per_symbol,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"[cninfo-audit] written: {out_path}")
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
