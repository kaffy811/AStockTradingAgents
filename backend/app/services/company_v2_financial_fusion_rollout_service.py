"""Rollout and eligibility checks for Company V2 financial evidence fusion."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


_INELIGIBLE_REASONS = {
    "DISABLED",
    "NOT_IN_ALLOWLIST",
    "OUTSIDE_ROLLOUT",
    "ALLOWLIST",
    "FORCE_ENABLED",
    "REPORT_NOT_READY",
    "RAG_NOT_INDEXED",
    "STRUCTURED_DATA_UNAVAILABLE",
}


def _stable_bucket(symbol: str, report_id: int) -> int:
    digest = hashlib.sha256(f"{symbol}:{int(report_id)}:financial_fusion".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _parse_allowlist(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


@dataclass(slots=True)
class FinancialFusionEligibility:
    enabled: bool
    eligible: bool
    reason: str
    rollout_bucket: int
    rollout_percent: int
    auto_run: bool
    report_ready: bool
    rag_ready: bool
    structured_ready: bool
    supported_fields: list[str]
    cached: bool = False
    last_run_at: str | None = None
    force_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "eligible": self.eligible,
            "reason": self.reason,
            "rollout_bucket": self.rollout_bucket,
            "rollout_percent": self.rollout_percent,
            "auto_run": self.auto_run,
            "report_ready": self.report_ready,
            "rag_ready": self.rag_ready,
            "structured_ready": self.structured_ready,
            "supported_fields": self.supported_fields,
            "cached": self.cached,
            "last_run_at": self.last_run_at,
            "force_enabled": self.force_enabled,
        }


class CompanyV2FinancialFusionRolloutService:
    def evaluate(
        self,
        *,
        symbol: str,
        report_id: int,
        report_ready: bool,
        rag_ready: bool,
        structured_ready: bool,
        cached: bool = False,
        last_run_at: str | None = None,
        force_enabled: bool = False,
        supported_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        enabled = bool(getattr(settings, "company_v2_financial_fusion_enabled", False))
        rollout_percent = int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0)
        auto_run = bool(getattr(settings, "company_v2_financial_fusion_auto_run", False))
        allowlist = _parse_allowlist(getattr(settings, "company_v2_financial_fusion_symbol_allowlist", ""))
        bucket = _stable_bucket(symbol, report_id)
        supported_fields = list(supported_fields or [])

        if not enabled and not force_enabled:
            return FinancialFusionEligibility(
                enabled=False,
                eligible=False,
                reason="DISABLED",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=force_enabled,
            ).to_dict()

        if not report_ready:
            return FinancialFusionEligibility(
                enabled=True,
                eligible=False,
                reason="REPORT_NOT_READY",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=force_enabled,
            ).to_dict()

        if not rag_ready:
            return FinancialFusionEligibility(
                enabled=True,
                eligible=False,
                reason="RAG_NOT_INDEXED",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=force_enabled,
            ).to_dict()

        if not structured_ready:
            return FinancialFusionEligibility(
                enabled=True,
                eligible=False,
                reason="STRUCTURED_DATA_UNAVAILABLE",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=force_enabled,
            ).to_dict()

        if force_enabled:
            return FinancialFusionEligibility(
                enabled=enabled,
                eligible=True,
                reason="FORCE_ENABLED",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=True,
            ).to_dict()

        if symbol in allowlist:
            return FinancialFusionEligibility(
                enabled=True,
                eligible=True,
                reason="ALLOWLIST",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=False,
            ).to_dict()

        if bucket < rollout_percent:
            return FinancialFusionEligibility(
                enabled=True,
                eligible=True,
                reason="ALLOWLIST" if symbol in allowlist else "OUTSIDE_ROLLOUT",
                rollout_bucket=bucket,
                rollout_percent=rollout_percent,
                auto_run=auto_run,
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                supported_fields=supported_fields,
                cached=cached,
                last_run_at=last_run_at,
                force_enabled=False,
            ).to_dict()

        return FinancialFusionEligibility(
            enabled=True,
            eligible=False,
            reason="OUTSIDE_ROLLOUT",
            rollout_bucket=bucket,
            rollout_percent=rollout_percent,
            auto_run=auto_run,
            report_ready=report_ready,
            rag_ready=rag_ready,
            structured_ready=structured_ready,
            supported_fields=supported_fields,
            cached=cached,
            last_run_at=last_run_at,
            force_enabled=force_enabled,
        ).to_dict()


company_v2_financial_fusion_rollout_service = CompanyV2FinancialFusionRolloutService()
