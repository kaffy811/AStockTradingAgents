"""CNINFO report discovery agent for CompanyV2 report timeline.

Discovers annual, semi-annual, Q1 and Q3 reports through CNINFO announcement
query APIs. It does not enumerate static PDF IDs; PDF URLs are derived only
from CNINFO `adjunctUrl` fields and validated by the provider layer.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.datasource.cninfo_provider import discover_reports, validate_pdf_url
from app.services.cninfo_org_resolver import resolve_cninfo_stock


class CninfoReportDiscoveryAgent:
    async def discover(
        self,
        market: str,
        symbol: str,
        *,
        company_name: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        force_refresh: bool = False,
        report_types: list[str] | None = None,
    ) -> dict[str, Any]:
        current_year = date.today().year
        if end_year is None:
            end_year = current_year - 1
        if start_year is None:
            start_year = max(2000, end_year - 10)

        resolved = await resolve_cninfo_stock(market, symbol, company_name)
        org_id = resolved.get("org_id")
        reports = await discover_reports(
            resolved["symbol"],
            start_year=start_year,
            end_year=end_year,
            org_id=org_id,
            report_types=report_types,
        )

        safe_reports: list[dict[str, Any]] = []
        errors: list[str] = []
        for report in reports:
            pdf_url = report.get("pdf_url") or ""
            if pdf_url:
                valid, reason = validate_pdf_url(pdf_url)
                if not valid:
                    errors.append(f"invalid_pdf_url:{reason}")
                    continue
            safe_reports.append({k: v for k, v in report.items() if k not in {"org_id", "local_path"}})

        annual_count = sum(1 for item in safe_reports if item.get("report_type") == "annual")
        quarterly_count = sum(1 for item in safe_reports if item.get("report_type") in {"q1", "q3", "semi_annual"})
        latest = safe_reports[0] if safe_reports else {}
        return {
            "ok": True,
            "market": market.upper(),
            "symbol": resolved["symbol"],
            "cninfo_identity": resolved,
            "documents_count": len(safe_reports),
            "annual_reports_count": annual_count,
            "quarterly_reports_count": quarterly_count,
            "latest_report_year": latest.get("report_year"),
            "latest_report_type": latest.get("report_type"),
            "pdf_status": "reports_found" if safe_reports else "no_report_found",
            "rag_status": "rag_not_ingested",
            "chunks_count": 0,
            "embedding_count": 0,
            "timeline": safe_reports,
            "reports": safe_reports,
            "errors": errors,
            "from_cache": False,
            "force_refresh": force_refresh,
        }


cninfo_report_discovery_agent = CninfoReportDiscoveryAgent()
