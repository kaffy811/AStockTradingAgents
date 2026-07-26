"""
app/agent/fundamental_analysis_agent.py — Analysis Agent (Phase 3)

调用 DeepSeek LLM，基于 data_pack 生成结构化财报分析 JSON。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

BANNED_PHRASES = [
    "买入", "卖出", "加仓", "减仓", "抄底", "逃顶",
    "目标价", "价格目标", "上涨空间", "保证收益",
    "必然上涨", "必然下跌", "强烈推荐", "值得买入",
    "可以入场", "适合买入", "低估买入", "高估卖出",
    "短期会涨", "短期看涨", "适合布局", "推荐买入",
]


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("Prompt file not found: %s", path)
        return ""


def _strip_json_fence(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _compress_data_pack_for_prompt(data_pack: dict, facts_limit: int = 60) -> str:
    """Build a compact JSON string of data_pack for the prompt (limit tokens)."""
    compact = {
        "ts_code": data_pack.get("ts_code"),
        "collected_modules": data_pack.get("collected_modules", []),
        "missing_modules": data_pack.get("missing_modules", []),
        "data_quality": data_pack.get("data_quality", {}),
        # Include compressed_facts up to facts_limit (30 for summary, 60 for full)
        "compressed_facts": data_pack.get("compressed_facts", [])[:facts_limit],
        # Include module_summaries
        "module_summaries": {
            k: v for k, v in data_pack.get("module_summaries", {}).items()
            if k in data_pack.get("collected_modules", [])
        },
        # Include RAG context chunks for report citation
        "report_rag_context": data_pack.get("report_rag_context", []),
    }
    return json.dumps(compact, ensure_ascii=False, indent=None)


class FundamentalAnalysisAgent:
    """
    分析层 Agent — 调用 DeepSeek 生成结构化财报分析。
    """

    async def analyze(self, data_pack: dict, mode: str = "summary") -> dict:
        """
        Returns analysis JSON dict.
        Raises RuntimeError if LLM is unavailable.
        Raises ValueError if LLM output cannot be parsed.
        """
        from app.core.config import settings

        if not settings.ai_enabled:
            raise RuntimeError("AI 分析功能已关闭（AI_ENABLED=false）")
        if not settings.ai_api_key:
            raise RuntimeError("AI API Key 未配置，AI 分析暂不可用")

        try:
            from app.llm.deepseek_client import DeepSeekClient
            client = DeepSeekClient()
        except ValueError as e:
            raise RuntimeError(f"AI 服务初始化失败: {e}") from e

        system_prompt = _load_prompt("analysis_agent_system.md")
        user_template = _load_prompt("analysis_agent_user.md")

        facts_limit = 30 if mode == "summary" else 60
        data_json = _compress_data_pack_for_prompt(data_pack, facts_limit=facts_limit)
        user_prompt = user_template.replace("{data_pack_json}", data_json)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        # Use pro model for better analysis quality; fallback to flash
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            raw_text = await loop.run_in_executor(
                None,
                lambda: client.chat(messages, temperature=0.2, model=settings.deepseek_pro_model),
            )
        except Exception as e:
            log.error("Analysis Agent LLM call failed: %s", e)
            raise RuntimeError(f"AI 服务调用失败: {e}") from e

        # Parse JSON
        cleaned = _strip_json_fence(raw_text)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.error("Analysis Agent JSON parse failed. Raw: %s", cleaned[:500])
            raise ValueError(f"LLM 输出解析失败（非合法 JSON）: {e}") from e

        # Validate structure
        from app.agent.schemas import validate_analysis_output
        errors = validate_analysis_output(result)
        if errors:
            log.warning("Analysis output validation errors: %s", errors)
            # Still return but log the issues

        # Ensure raw_disclaimer exists
        if not result.get("raw_disclaimer"):
            result["raw_disclaimer"] = "本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。"

        return result
