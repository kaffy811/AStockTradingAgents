"""Pi-compatible financial agent runtime prototype."""

from app.agent_runtime.capability_manifest import official_report_pdf_manifest
from app.agent_runtime.executor import PiCompatibleAgentExecutor
from app.agent_runtime.shadow_runner import PiCompatibleShadowRunner

__all__ = [
    "PiCompatibleAgentExecutor",
    "PiCompatibleShadowRunner",
    "official_report_pdf_manifest",
]
