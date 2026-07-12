"""
app/tools/fundamental/ai_analysis.py — AI Analysis Tool stub (Phase 3)

This stub satisfies TOOL_REGISTRY requirements.
The actual implementation routes through FundamentalAIOrchestrator in
the router layer (fundamentals_compat.py) before the aggregator is called.
"""
from __future__ import annotations

from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.aggregator.envelope import DataEnvelope, err_envelope


class AiAnalysisTool(BaseFundamentalTool):
    """
    AI 财报分析工具占位。

    在生产路由中，ai_analysis 请求在到达聚合器之前
    已由 fundamentals_compat.py 路由至 FundamentalAIOrchestrator。
    本类仅用于满足 TOOL_REGISTRY 注册要求。
    """

    module_key = "ai_analysis"
    cache_ttl_seconds = 86400   # 24h — AI results are expensive
    stale_ttl_seconds = 172800  # 48h stale window

    async def fetch(self, market: str, symbol: str) -> dict:
        # Should not be reached in normal operation (router intercepts first)
        raise FundamentalToolError(
            "ai_analysis 模块通过 FundamentalAIOrchestrator 处理，不走标准工具层。"
        )

    async def fetch_akshare(self, market: str, symbol: str) -> dict:
        raise NotImplementedError

    async def fetch_with_fallback(self, market: str, symbol: str) -> DataEnvelope:
        return err_envelope(
            "ai_analysis 模块通过 FundamentalAIOrchestrator 处理，请使用 /api/v1/stock/{code}/modules/ai_analysis"
        )
