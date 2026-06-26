"""
Agent schemas — Phase 1.

Unified data structures for financial agent responses.
Used by FinancialAgent and GeneralFinancialAnswerSkill.
"""
from __future__ import annotations

import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ThinkingStep(BaseModel):
    type: Literal["thinking"] = "thinking"
    content: str
    timestamp: float = Field(default_factory=time.time)


class ToolCallRecord(BaseModel):
    tool_name: str
    display_name: str = ""
    arguments: dict[str, Any] = {}
    status: Literal["success", "failed"] = "success"
    result_summary: Optional[str] = None
    raw_result: Optional[Any] = None
    error: Optional[str] = None


class DataPoint(BaseModel):
    label: str
    value: str


class SourceRef(BaseModel):
    """A reference to a financial document chunk returned by RAG search."""
    title: str
    source_type: str = "document"   # annual_report | research_report | announcement | document
    source: str = ""                # e.g. "SEC", "HKEX", "内部研报"
    published_at: str = ""
    url: str = ""
    page: Optional[int] = None
    # Phase 2C: quality metadata (all optional for backward compatibility)
    source_level: str = ""          # official_exchange | official_company | authoritative_media | general
    verified: bool = False
    authority_score: float = 0.0
    report_year: Optional[int] = None
    report_type: str = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    search_mode_used: str = ""      # vector | keyword | hybrid


class DataQuality(BaseModel):
    """Phase 2B: data provenance and reliability metadata for the final answer."""
    report_verified:       bool = False
    report_source_level:   str  = ""    # official_exchange | official_company | authoritative_media | general
    market_data_available: bool = False
    warnings: list[str]       = []


class FinalAnswer(BaseModel):
    summary:    str
    data_points: list[DataPoint] = []
    analysis:   str = ""
    # Phase 2B: extended structured sections (backward-compatible, all optional)
    business_analysis: str = ""   # 经营表现分析 from financial report
    market_analysis:   str = ""   # 行情复盘
    linkage_analysis:  str = ""   # 基本面与行情联动
    risk_points:  list[str] = []
    sources:      list[SourceRef] = []    # Phase 2A: RAG citations
    data_quality: DataQuality = Field(default_factory=DataQuality)  # Phase 2B
    disclaimer:   str = "仅供研究参考，不构成任何投资建议。"


class AgentResponse(BaseModel):
    request_id: str
    query: str
    thinking_steps: list[ThinkingStep] = []
    tool_calls: list[ToolCallRecord] = []
    final_answer: FinalAnswer
    answer_text: str = ""  # Full markdown answer for existing answer_delta channel
