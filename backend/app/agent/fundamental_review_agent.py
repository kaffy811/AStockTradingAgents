"""
app/agent/fundamental_review_agent.py — Compliance Review Agent (Phase 6I)

审核链：
1. 规则引擎（快速，必须运行）：
   - 禁词检测（买入/卖出/目标价/保证上涨）
   - 结构校验
   - source_fact_ids 校验
   - source_chunks 严格校验 + canonicalization
   - 正文引用一致性检查（"根据年报"/"财报显示"但无chunks/reports → rewrite）
   - 页码引用检测（"第12页"等 → 移除）
   - 覆盖声明检测（"完整覆盖所有财报" → 改写）
2. review_audit — 记录所有校验结果，返回给前端调试
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.agent.schemas import SAFE_PLACEHOLDER, make_review_result

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── 绝对禁止词（严重违规）────────────────────────────────────────────────────────
_SEVERE_BANNED = [
    "买入", "卖出", "加仓", "减仓", "抄底", "逃顶",
    "目标价", "价格目标", "保证收益", "必然上涨", "必然下跌",
    "强烈推荐", "值得买入", "可以入场", "推荐买入",
    "确定上涨", "确定下跌", "一定涨", "一定跌",
    "机构一致推荐买入", "完整机构一致推荐", "机构全面推荐",
]

# ── 轻微违规词（可改写）────────────────────────────────────────────────────────
_MILD_BANNED = [
    "短期会涨", "短期看涨", "短期看跌", "适合布局",
    "低估买入", "高估卖出", "适合买入",
    "上涨空间", "机构一致推荐",
]

# ── 页码引用正则（例如：第12页、第 3 页）────────────────────────────────────────
_PAGE_CITE_RE = re.compile(r"第\s*\d+\s*页", re.UNICODE)

# ── 覆盖声明模式（应改写，不reject）────────────────────────────────────────────
_COVERAGE_CLAIMS = [
    "完整覆盖所有财报",
    "完整阅读全部财报",
    "全面覆盖所有财报",
    "全部财报完整覆盖",
    "所有财报均已分析",
]

# ── 正文引用信号词（出现时需有 source_chunks 或 source_reports）────────────────
_CITATION_SIGNAL_WORDS = [
    "根据年报", "财报显示", "报告披露", "从财报片段看",
    "根据已接入财报", "年报中提到", "财报原文",
]

# ── 数字正则：提取百分比 / 倍数 / 大额金额 ──────────────────────────────────────
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|％|倍|亿|万亿|x)")

_DISCLAIMER_REQUIRED = "不构成投资建议"


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _text_of(obj: Any) -> str:
    """Recursively extract all string values for phrase checking."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(_text_of(i) for i in obj)
    if isinstance(obj, dict):
        return " ".join(_text_of(v) for v in obj.values())
    return ""


def _find_phrases(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if p in text]


# ── 结构校验 ──────────────────────────────────────────────────────────────────

def _check_structure(analysis: dict) -> list[str]:
    required = ["summary", "overall_score", "dimensions", "highlights",
                 "risks", "watch_items", "data_limitations"]
    return [f"缺少字段: {k}" for k in required if k not in analysis]


# ── source_modules 校验 ──────────────────────────────────────────────────────

def _check_source_modules(analysis: dict) -> list[str]:
    issues = []
    for item in analysis.get("highlights", []):
        if not isinstance(item, dict):
            continue
        if not item.get("source_modules"):
            issues.append(f"highlights['{item.get('title', '?')}'] 缺少 source_modules")

    for item in analysis.get("risks", []):
        if not isinstance(item, dict):
            continue
        if not item.get("source_modules"):
            issues.append(f"risks['{item.get('title', '?')}'] 缺少 source_modules")

    for dim in analysis.get("dimensions", []):
        if not isinstance(dim, dict):
            continue
        for ev in dim.get("evidence", []):
            if isinstance(ev, dict) and not ev.get("source_modules"):
                issues.append(f"dimensions['{dim.get('name','?')}'].evidence 缺少 source_modules")
                break

    return issues[:6]


# ── source_fact_ids 校验 ─────────────────────────────────────────────────────

def _check_source_fact_ids(analysis: dict, data_pack: dict) -> list[str]:
    valid_ids = {f["fact_id"] for f in data_pack.get("compressed_facts", [])}
    issues = []
    all_items = (
        analysis.get("highlights", []) +
        analysis.get("risks", []) +
        [ev for dim in analysis.get("dimensions", []) for ev in dim.get("evidence", [])] +
        [rv for dim in analysis.get("dimensions", []) for rv in dim.get("risks", [])]
    )
    for item in all_items:
        if not isinstance(item, dict):
            continue
        for fid in item.get("source_fact_ids", []):
            if fid and fid not in valid_ids:
                issues.append(f"引用了不存在的 fact_id: {fid}")
    return issues[:5]


# ── 数值幻觉校验 ─────────────────────────────────────────────────────────────

def _check_numeric_hallucination(analysis: dict, data_pack: dict) -> list[str]:
    all_facts_text = " ".join(
        str(f.get("value", "")) + " " + str(f.get("label", ""))
        for f in data_pack.get("compressed_facts", [])
    )
    all_facts_nums = set(_NUMBER_RE.findall(all_facts_text))
    analysis_text = _text_of(analysis)
    analysis_nums = _NUMBER_RE.findall(analysis_text)

    issues = []
    for num in analysis_nums:
        if num not in all_facts_nums:
            issues.append(f"数值 '{num}' 未在数据来源中找到对应依据")
    seen = set()
    deduped = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            deduped.append(i)
    return deduped[:4]


# ── 机构评级滥用检测 ─────────────────────────────────────────────────────────

def _check_analyst_ratings_misuse(analysis: dict) -> list[str]:
    misuse_patterns = [
        "机构一致推荐买入", "完整机构一致推荐", "机构全面看好",
        "机构一致预期买入", "所有机构推荐", "机构100%",
    ]
    all_text = _text_of(analysis)
    return [p for p in misuse_patterns if p in all_text]


# ── source_chunks 严格校验 + canonicalization（Phase 6I）────────────────────

def _canonicalize_source_chunks(
    analysis: dict,
    data_pack: dict,
) -> tuple[list[str], dict, dict]:
    """
    Phase 6I: Strict source_chunks validation + canonicalization.

    Rules:
    1. chunk_id must be in allowed_chunk_ids
    2. ALL metadata is taken from data_pack.report_rag_context (not trusted from LLM)
    3. Deduplication by chunk_id
    4. Cap at 8 chunks

    Returns:
      (issues, cleaned_analysis, audit_detail)
      audit_detail: {
        "chunk_ids_checked": int,
        "invalid_removed": list[int],   # removed chunk_ids
        "metadata_canonicalized": bool,  # True if any metadata was overridden
        "deduped": int,                  # num removed by dedup
        "truncated": int,                # num removed by 8-cap
      }
    """
    allowed_ids = set(data_pack.get("allowed_chunk_ids", []))
    rag_context = data_pack.get("report_rag_context", [])
    rag_by_id = {c.get("chunk_id"): c for c in rag_context if c.get("chunk_id")}

    source_chunks = analysis.get("source_chunks", [])
    if not source_chunks:
        cleaned = dict(analysis)
        cleaned["source_chunks"] = []
        return [], cleaned, {
            "chunk_ids_checked": 0, "invalid_removed": [],
            "metadata_canonicalized": False, "deduped": 0, "truncated": 0,
        }

    issues: list[str] = []
    invalid_removed: list[int] = []
    metadata_overridden = False
    seen_ids: set = set()
    valid_chunks: list[dict] = []

    for chunk in source_chunks:
        if not isinstance(chunk, dict):
            issues.append("source_chunks 中有非 dict 条目（已丢弃）")
            continue
        cid = chunk.get("chunk_id")

        # 1. Must have chunk_id
        if cid is None:
            issues.append("source_chunks 中有缺少 chunk_id 的条目（已丢弃）")
            invalid_removed.append(-1)
            continue

        # 2. Must be in allowed set
        if cid not in allowed_ids:
            issues.append(f"chunk_id={cid} 不在允许列表中（已移除）")
            invalid_removed.append(cid)
            continue

        # 3. Deduplication
        if cid in seen_ids:
            issues.append(f"chunk_id={cid} 重复（已去重）")
            continue
        seen_ids.add(cid)

        # 4. Canonicalize metadata from rag_context (override LLM's metadata)
        canonical = rag_by_id.get(cid)
        if canonical:
            # Check if LLM tried to override any field
            for field in ("report_id", "section_title", "report_type", "period", "report_year"):
                llm_val = chunk.get(field)
                real_val = canonical.get(field)
                if llm_val is not None and llm_val != real_val:
                    issues.append(
                        f"chunk_id={cid} 的 {field} 已由 LLM 篡改 "
                        f"（'{llm_val}' → 回填为 '{real_val}'）"
                    )
                    metadata_overridden = True

            valid_chunks.append({
                "chunk_id":      cid,
                "report_id":     canonical.get("report_id"),
                "ts_code":       canonical.get("ts_code"),
                "report_type":   canonical.get("report_type"),
                "report_year":   canonical.get("report_year"),
                "period":        canonical.get("period"),
                "section_title": canonical.get("section_title"),
                "content":       (canonical.get("content") or "")[:800],
                "score":         canonical.get("score"),
                # Never trust LLM's pdf_url — it doesn't know the backend route
                "pdf_url":       None,  # orchestrator fills this later if needed
                "citation":      chunk.get("citation", ""),
            })
        else:
            # chunk_id is in allowed_ids but not in rag_context (should not happen)
            issues.append(f"chunk_id={cid} 在允许列表但不在 rag_context 中（已丢弃）")
            invalid_removed.append(cid)

    # 5. Cap at 8
    truncated = max(0, len(valid_chunks) - 8)
    valid_chunks = valid_chunks[:8]

    cleaned = dict(analysis)
    cleaned["source_chunks"] = valid_chunks

    audit_detail = {
        "chunk_ids_checked": len(source_chunks),
        "invalid_removed": [x for x in invalid_removed if x != -1],
        "metadata_canonicalized": metadata_overridden,
        "deduped": len(source_chunks) - len(invalid_removed) - len(valid_chunks) - truncated,
        "truncated": truncated,
    }
    return issues, cleaned, audit_detail


# ── 正文引用一致性检查（Phase 6I）────────────────────────────────────────────

def _check_citation_consistency(analysis: dict, data_pack: dict) -> tuple[list[str], dict]:
    """
    If analysis body contains citation signal words ("根据年报", "财报显示", ...)
    but source_chunks and source_reports are both empty → rewrite those phrases.

    Returns (issues, rewritten_analysis).
    """
    # Check if there are any citations available
    has_chunks = bool(analysis.get("source_chunks"))
    has_reports = bool(data_pack.get("report_rag_context"))  # proxy for source_reports

    if has_chunks or has_reports:
        return [], analysis  # citations are backed by data, nothing to fix

    # Scan text fields for citation signal words
    text = _text_of(analysis)
    found_signals = [w for w in _CITATION_SIGNAL_WORDS if w in text]

    if not found_signals:
        return [], analysis

    issues = [
        f"正文出现引用信号词 {found_signals} 但 source_chunks/source_reports 均为空，已改写为通用措辞"
    ]

    # Rewrite: replace citation signals with generic phrasing
    replacements = {
        "根据年报": "根据已接入的结构化公开数据",
        "财报显示": "已有数据显示",
        "报告披露": "公开数据显示",
        "从财报片段看": "从已有数据看",
        "根据已接入财报": "根据已接入的公开财务数据",
        "年报中提到": "数据中显示",
        "财报原文": "已有数据",
    }
    try:
        text_json = json.dumps(analysis, ensure_ascii=False)
        for old, new in replacements.items():
            text_json = text_json.replace(old, new)
        rewritten = json.loads(text_json)
    except Exception:
        rewritten = analysis  # fallback

    return issues, rewritten


# ── 页码引用检测与移除（Phase 6I）────────────────────────────────────────────

def _check_and_remove_page_citations(analysis: dict, data_pack: dict) -> tuple[list[str], dict, bool]:
    """
    Detect "第N页" patterns.
    Since chunk page_start/page_end is not always populated, always remove page citations.

    Returns (issues, cleaned_analysis, was_removed).
    """
    text = _text_of(analysis)
    matches = _PAGE_CITE_RE.findall(text)
    if not matches:
        return [], analysis, False

    issues = [f"检测到页码引用 {set(matches)}，已移除（chunk 无真实 page 信息）"]

    try:
        text_json = json.dumps(analysis, ensure_ascii=False)
        cleaned_json = _PAGE_CITE_RE.sub("", text_json)
        cleaned = json.loads(cleaned_json)
    except Exception:
        cleaned = analysis

    return issues, cleaned, True


# ── 覆盖声明检测与改写（Phase 6I）────────────────────────────────────────────

def _check_and_rewrite_coverage_claims(analysis: dict) -> tuple[list[str], dict, bool]:
    """
    Detect and rewrite "完整覆盖所有财报" style claims.

    Returns (issues, cleaned_analysis, was_rewritten).
    """
    text = _text_of(analysis)
    found = [c for c in _COVERAGE_CLAIMS if c in text]
    if not found:
        return [], analysis, False

    issues = [f"检测到覆盖声明 {found}，已改写为准确措辞"]

    replacement = "基于已接入的公开财报片段和结构化数据"
    try:
        text_json = json.dumps(analysis, ensure_ascii=False)
        for claim in found:
            text_json = text_json.replace(claim, replacement)
        rewritten = json.loads(text_json)
    except Exception:
        rewritten = analysis

    return issues, rewritten, True


# ── review_audit 生成 ─────────────────────────────────────────────────────────

def _generate_review_audit(
    source_chunks_checked: bool,
    invalid_chunk_ids_removed: list[int],
    metadata_canonicalized: bool,
    page_citation_removed: bool,
    coverage_claim_rewritten: bool,
    citation_consistency_rewritten: bool,
    investment_advice_blocked: bool,
    mild_phrases_rewritten: list[str],
) -> dict:
    """
    Build the review_audit dict. Safe for frontend display.
    Does NOT include prompt text or full chunk content.
    """
    return {
        "source_chunks_checked": source_chunks_checked,
        "invalid_chunk_ids_removed": invalid_chunk_ids_removed,
        "metadata_canonicalized": metadata_canonicalized,
        "page_citation_removed": page_citation_removed,
        "coverage_claim_rewritten": coverage_claim_rewritten,
        "citation_consistency_rewritten": citation_consistency_rewritten,
        "investment_advice_blocked": investment_advice_blocked,
        "mild_phrases_rewritten": mild_phrases_rewritten,
    }


# ── disclaimer 注入 ────────────────────────────────────────────────────────────

def _ensure_disclaimer(analysis: dict) -> dict:
    result = dict(analysis)
    disclaimer = result.get("raw_disclaimer") or result.get("disclaimer") or ""
    if not disclaimer or _DISCLAIMER_REQUIRED not in disclaimer:
        result["disclaimer"] = "本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。"
    else:
        result["disclaimer"] = disclaimer
    result.pop("raw_disclaimer", None)
    return result


# ── mild rewrite ──────────────────────────────────────────────────────────────

def _simple_rewrite(analysis: dict, mild_phrases: list[str], fact_issues: list[str]) -> dict:
    text = json.dumps(analysis, ensure_ascii=False)
    replacements = {
        "短期会涨": "短期走势不确定",
        "短期看涨": "短期走势存在不确定性",
        "短期看跌": "短期走势存在压力",
        "适合布局": "可关注",
        "低估买入": "估值相对偏低",
        "高估卖出": "估值相对偏高",
        "适合买入": "值得持续关注",
        "上涨空间": "估值弹性",
        "机构一致推荐": "机构关注度",
    }
    for phrase, replacement in replacements.items():
        text = text.replace(phrase, replacement)
    try:
        result = json.loads(text)
    except Exception:
        result = analysis

    if fact_issues:
        limitations = result.get("data_limitations", [])
        for issue in fact_issues[:3]:
            if issue not in limitations:
                limitations.append(f"[审核注] {issue}")
        result["data_limitations"] = limitations

    return result


# ── 核心规则引擎 ──────────────────────────────────────────────────────────────

def _rule_based_review(analysis: dict, data_pack: dict) -> tuple[dict, dict]:
    """
    Full rule-based review pipeline (Phase 6I).

    Returns: (result_dict, fully_cleaned_analysis)

    result_dict keys:
      status, severe_found, mild_found, structure_errors, fact_id_issues,
      source_module_issues, numeric_issues, analyst_misuse,
      chunk_issues, chunk_audit_detail,
      page_citation_issues, coverage_claim_issues, citation_consistency_issues,
    """
    # ── 1. Canonicalize source_chunks (strict, Phase 6I) ──────────────────────
    chunk_issues, analysis_after_chunks, chunk_audit_detail = _canonicalize_source_chunks(
        analysis, data_pack
    )

    # ── 2. Remove page citations ──────────────────────────────────────────────
    page_issues, analysis_after_pages, page_removed = _check_and_remove_page_citations(
        analysis_after_chunks, data_pack
    )

    # ── 3. Rewrite coverage claims ────────────────────────────────────────────
    coverage_issues, analysis_after_coverage, coverage_rewritten = _check_and_rewrite_coverage_claims(
        analysis_after_pages
    )

    # ── 4. Citation consistency ───────────────────────────────────────────────
    citation_issues, analysis_after_citation = _check_citation_consistency(
        analysis_after_coverage, data_pack
    )

    # This is the "clean" base we work with from here
    cleaned = analysis_after_citation

    # ── 5. Standard checks on cleaned analysis ────────────────────────────────
    all_text = _text_of(cleaned)

    severe = _find_phrases(all_text, _SEVERE_BANNED)
    mild = _find_phrases(all_text, _MILD_BANNED)
    struct_errors = _check_structure(cleaned)
    fact_errors = _check_source_fact_ids(cleaned, data_pack)
    source_module_issues = _check_source_modules(cleaned)
    numeric_issues = _check_numeric_hallucination(cleaned, data_pack)
    analyst_misuse = _check_analyst_ratings_misuse(cleaned)

    all_severe = severe + analyst_misuse

    if all_severe or struct_errors:
        status = "rejected"
    elif (mild or fact_errors or source_module_issues or numeric_issues
          or chunk_issues or page_issues or coverage_issues or citation_issues):
        status = "revised_needed"
    else:
        status = "approved"

    return {
        "status": status,
        "severe_found": all_severe,
        "mild_found": mild,
        "structure_errors": struct_errors,
        "fact_id_issues": fact_errors,
        "source_module_issues": source_module_issues,
        "numeric_issues": numeric_issues,
        "analyst_misuse": analyst_misuse,
        "chunk_issues": chunk_issues,
        "chunk_audit_detail": chunk_audit_detail,
        "page_citation_issues": page_issues,
        "page_citation_removed": page_removed,
        "coverage_claim_issues": coverage_issues,
        "coverage_claim_rewritten": coverage_rewritten,
        "citation_consistency_issues": citation_issues,
        "citation_consistency_rewritten": bool(citation_issues),
    }, cleaned


# ── Review Agent ──────────────────────────────────────────────────────────────

class FundamentalReviewAgent:
    """
    合规审核层 Agent（Phase 6I 强校验版本）
    """

    async def review(self, analysis_json: dict, data_pack: dict) -> dict:
        """
        Returns make_review_result(...) dict with audit field.
        Never raises — always returns something safe.
        """
        try:
            return await self._do_review(analysis_json, data_pack)
        except Exception as e:
            log.error("Review agent unexpected error: %s", e, exc_info=True)
            safe = dict(SAFE_PLACEHOLDER)
            safe["review"]["review_notes"].append({"type": "review_error", "message": str(e)})
            audit = _generate_review_audit(
                source_chunks_checked=False, invalid_chunk_ids_removed=[],
                metadata_canonicalized=False, page_citation_removed=False,
                coverage_claim_rewritten=False, citation_consistency_rewritten=False,
                investment_advice_blocked=False, mild_phrases_rewritten=[],
            )
            return make_review_result(
                status="rejected",
                notes=[{"type": "review_error", "message": str(e)}],
                blocked=[],
                final=safe,
                audit=audit,
            )

    async def _do_review(self, analysis_json: dict, data_pack: dict) -> dict:
        rule_result, cleaned_analysis = _rule_based_review(analysis_json, data_pack)

        status = rule_result["status"]
        severe = rule_result["severe_found"]
        mild = rule_result["mild_found"]
        struct_errors = rule_result["structure_errors"]
        fact_issues = rule_result["fact_id_issues"]
        source_module_issues = rule_result["source_module_issues"]
        numeric_issues = rule_result["numeric_issues"]
        analyst_misuse = rule_result["analyst_misuse"]
        chunk_issues = rule_result["chunk_issues"]
        chunk_audit_detail = rule_result["chunk_audit_detail"]
        page_citation_removed = rule_result["page_citation_removed"]
        coverage_claim_rewritten = rule_result["coverage_claim_rewritten"]
        citation_consistency_rewritten = rule_result["citation_consistency_rewritten"]

        notes = []
        blocked = list(severe) + list(mild)

        # Build review_audit
        audit = _generate_review_audit(
            source_chunks_checked=True,
            invalid_chunk_ids_removed=chunk_audit_detail.get("invalid_removed", []),
            metadata_canonicalized=chunk_audit_detail.get("metadata_canonicalized", False),
            page_citation_removed=page_citation_removed,
            coverage_claim_rewritten=coverage_claim_rewritten,
            citation_consistency_rewritten=citation_consistency_rewritten,
            investment_advice_blocked=bool(severe or analyst_misuse),
            mild_phrases_rewritten=mild,
        )

        if status == "rejected":
            if severe:
                notes.append({
                    "type": "investment_advice_blocked",
                    "message": f"发现严重违规措辞：{', '.join(severe)}",
                })
            if analyst_misuse:
                notes.append({
                    "type": "analyst_ratings_misuse",
                    "message": f"机构评级数据使用不当：{', '.join(analyst_misuse)}",
                })
            if struct_errors:
                notes.append({
                    "type": "structure_error",
                    "message": f"结构不完整：{'; '.join(struct_errors)}",
                })

            safe = dict(SAFE_PLACEHOLDER)
            safe["review"] = {
                "review_status": "rejected",
                "review_notes": notes,
                "blocked_phrases": blocked,
            }
            return make_review_result(
                status="rejected", notes=notes, blocked=blocked, final=safe, audit=audit,
            )

        elif status == "revised_needed":
            if mild:
                notes.append({
                    "type": "mild_phrase_rewritten",
                    "message": f"已改写措辞：{', '.join(mild)}",
                })
            if fact_issues:
                notes.append({"type": "fact_id_warning", "message": "source_fact_ids 存在问题（已注记）"})
            if source_module_issues:
                notes.append({
                    "type": "source_modules_missing",
                    "message": f"部分证据缺少 source_modules：{'; '.join(source_module_issues[:3])}",
                })
            if numeric_issues:
                notes.append({
                    "type": "numeric_unverified",
                    "message": f"部分数值未在数据来源中找到依据：{'; '.join(numeric_issues[:2])}",
                })
            if chunk_issues:
                notes.append({
                    "type": "chunk_id_cleaned",
                    "message": f"无效 chunk_id 已移除或 metadata 已回填：共 {len(chunk_issues)} 条",
                })
            if page_citation_removed:
                notes.append({"type": "page_citation_removed", "message": "检测到页码引用，已移除"})
            if coverage_claim_rewritten:
                notes.append({"type": "coverage_claim_rewritten", "message": "覆盖声明已改写为准确措辞"})
            if citation_consistency_rewritten:
                notes.append({
                    "type": "citation_consistency_rewritten",
                    "message": "正文引用信号词已改写（无 source_chunks/source_reports）",
                })

            revised = _simple_rewrite(cleaned_analysis, mild, fact_issues)
            revised = _ensure_disclaimer(revised)
            revised["review"] = {
                "review_status": "revised",
                "review_notes": notes,
                "blocked_phrases": blocked,
            }
            return make_review_result(
                status="revised", notes=notes, blocked=blocked, final=revised, audit=audit,
            )

        else:
            # Approved
            final = _ensure_disclaimer(cleaned_analysis)
            # Add notes for any rewrites even when approved
            if page_citation_removed:
                notes.append({"type": "page_citation_removed", "message": "检测到页码引用，已移除"})
            if coverage_claim_rewritten:
                notes.append({"type": "coverage_claim_rewritten", "message": "覆盖声明已改写"})
            if chunk_issues:
                notes.append({
                    "type": "chunk_id_canonicalized",
                    "message": f"source_chunks 已校验并回填 metadata：{len(chunk_issues)} 项",
                })

            final["review"] = {
                "review_status": "approved",
                "review_notes": notes,
                "blocked_phrases": [],
            }
            return make_review_result(
                status="approved", notes=notes, blocked=[], final=final, audit=audit,
            )
