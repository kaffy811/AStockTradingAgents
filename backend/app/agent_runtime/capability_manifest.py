"""Capability manifests for Pi-compatible financial agents."""
from __future__ import annotations

from app.agent_runtime.contracts import AgentCapabilityManifest


official_report_pdf_manifest = AgentCapabilityManifest(
    agent_id="official_report_pdf_pi_v1",
    version="1.0.0",
    purpose="返回指定公司和期间的官方报告 PDF",
    supported_intents=["official_report_pdf"],
    supported_markets=["CN"],
    execution_mode="pi_compatible",
    model_profile="tool_routing_light",
    allowed_tools=["resolve_security", "get_official_reports"],
    required_data_quality={
        "official_source_required": True,
        "provenance_required": True,
        "period_verified": True,
    },
    max_turns=3,
    max_tool_calls=4,
    deadline_ms=5000,
    read_only=True,
    output_schema="OfficialReportPdfAnswerV1",
    compliance_profile="financial_research",
    fallback="legacy_official_report_pdf",
)


agent_manifests = {
    official_report_pdf_manifest.agent_id: official_report_pdf_manifest,
}
