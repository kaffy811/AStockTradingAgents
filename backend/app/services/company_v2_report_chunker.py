"""Page-grounded chunking for Company V2 report QA."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_TARGET_TOKENS = 560
DEFAULT_OVERLAP_TOKENS = 100
DEFAULT_MAX_TOKENS = 900
DEFAULT_MIN_TOKENS = 80
PARSE_VERSION = "company-v2-pages-v1"


@dataclass(slots=True)
class ReportPage:
    page: int
    text: str


@dataclass(slots=True)
class ReportChunkDraft:
    report_id: int
    chunk_index: int
    page_start: int
    page_end: int
    section_title: str | None
    text: str
    text_hash: str
    token_count: int
    metadata_json: dict[str, Any] = field(default_factory=dict)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return len(_tokenize(text))


def load_pages_from_sidecar(path: str | Path) -> tuple[list[ReportPage], dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = [
        ReportPage(page=int(item.get("page") or idx + 1), text=str(item.get("text") or ""))
        for idx, item in enumerate(data.get("text_pages") or [])
    ]
    return pages, data


def _tokenize(text: str) -> list[str]:
    # CJK characters, Latin words, numbers, and financial symbols are counted as
    # retrieval tokens. This avoids fixed character chopping while preserving
    # units, years, percentages, and numeric table context.
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_.%+-]+|[^\s]", text or "")


def _tokens_to_text(tokens: list[str]) -> str:
    out: list[str] = []
    prev_ascii = False
    for tok in tokens:
        ascii_tok = bool(re.match(r"^[A-Za-z0-9_.%+-]+$", tok))
        if out and ascii_tok and prev_ascii:
            out.append(" ")
        out.append(tok)
        prev_ascii = ascii_tok
    return "".join(out)


def _normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line or "").strip()
    line = re.sub(r"\d+\s*/\s*\d+", "{page}/{pages}", line)
    return line


def _is_keep_context_line(line: str) -> bool:
    return bool(re.search(r"单位[:：]|万元|亿元|人民币|营业收入|净利润|现金流|风险|主营业务", line))


def _is_section_heading(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) > 80:
        return False
    patterns = [
        r"^第[一二三四五六七八九十\d]+[章节]\s+",
        r"^[一二三四五六七八九十\d]+[、.．]\s*[\u4e00-\u9fff]",
        r"^[(（][一二三四五六七八九十\d]+[)）]\s*[\u4e00-\u9fff]",
    ]
    return any(re.search(pattern, stripped) for pattern in patterns)


def _detect_repeated_lines(pages: list[ReportPage]) -> set[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        seen_on_page: set[str] = set()
        for raw in page.text.splitlines():
            line = _normalize_line(raw)
            if len(line) < 4 or _is_keep_context_line(line):
                continue
            if re.search(r"年度报告|公司代码|公司简称|{page}/{pages}", line):
                seen_on_page.add(line)
        counts.update(seen_on_page)
    threshold = max(3, min(10, len(pages) // 8))
    return {line for line, count in counts.items() if count >= threshold}


def _clean_page_lines(page: ReportPage, repeated: set[str]) -> list[str]:
    lines: list[str] = []
    for raw in page.text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        normalized = _normalize_line(line)
        if normalized in repeated and not _is_keep_context_line(line):
            continue
        # Drop pure page counters but keep table unit and financial context.
        if re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _split_long_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    tokens = _tokenize(text)
    if len(tokens) <= max_tokens:
        return [text]
    parts: list[str] = []
    start = 0
    step = max(1, max_tokens - overlap_tokens)
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        parts.append(_tokens_to_text(tokens[start:end]))
        if end >= len(tokens):
            break
        start += step
    return parts


def chunk_report_pages(
    *,
    report_id: int,
    pages: list[ReportPage],
    metadata: dict[str, Any],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    min_tokens: int = DEFAULT_MIN_TOKENS,
) -> list[ReportChunkDraft]:
    """Create report-scoped chunks from parsed pages without crossing reports."""
    if not pages:
        return []

    repeated = _detect_repeated_lines(pages)
    segments: list[dict[str, Any]] = []
    current_section: str | None = None

    for page in pages:
        lines = _clean_page_lines(page, repeated)
        paragraph: list[str] = []
        for line in lines + [""]:
            if line and _is_section_heading(line):
                if paragraph:
                    segments.append({"page": page.page, "section": current_section, "text": "\n".join(paragraph).strip()})
                    paragraph = []
                current_section = line
                paragraph.append(line)
                continue
            if line:
                paragraph.append(line)
            elif paragraph:
                segments.append({"page": page.page, "section": current_section, "text": "\n".join(paragraph).strip()})
                paragraph = []

    expanded: list[dict[str, Any]] = []
    for segment in segments:
        for part in _split_long_text(segment["text"], max_tokens, overlap_tokens):
            expanded.append({**segment, "text": part})

    chunks: list[ReportChunkDraft] = []
    current: list[str] = []
    current_pages: list[int] = []
    current_section: str | None = None
    overlap_text = ""

    def flush() -> None:
        nonlocal current, current_pages, current_section, overlap_text
        text = "\n\n".join(part for part in current if part).strip()
        if not text:
            current = []
            current_pages = []
            return
        token_count = estimate_tokens(text)
        if chunks and token_count < min_tokens and current_section == chunks[-1].section_title:
            previous = chunks[-1]
            merged = f"{previous.text}\n\n{text}".strip()
            chunks[-1] = ReportChunkDraft(
                report_id=previous.report_id,
                chunk_index=previous.chunk_index,
                page_start=min(previous.page_start, min(current_pages)),
                page_end=max(previous.page_end, max(current_pages)),
                section_title=previous.section_title,
                text=merged,
                text_hash=text_hash(merged),
                token_count=estimate_tokens(merged),
                metadata_json=previous.metadata_json,
            )
        elif token_count >= min_tokens:
            chunk = ReportChunkDraft(
                report_id=report_id,
                chunk_index=len(chunks),
                page_start=min(current_pages),
                page_end=max(current_pages),
                section_title=current_section,
                text=text,
                text_hash=text_hash(text),
                token_count=token_count,
                metadata_json={**metadata, "page_numbers": sorted(set(current_pages)), "section_path": [current_section] if current_section else []},
            )
            chunks.append(chunk)
        toks = _tokenize(text)
        overlap_text = _tokens_to_text(toks[-overlap_tokens:]) if len(toks) > overlap_tokens else text
        current = []
        current_pages = []

    for segment in expanded:
        seg_text = segment["text"]
        seg_tokens = estimate_tokens(seg_text)
        candidate_tokens = estimate_tokens("\n\n".join(current + [seg_text]))
        if current and (candidate_tokens > max_tokens or (candidate_tokens > target_tokens and current_section != segment["section"])):
            flush()
        if not current and overlap_text and segment["section"] == current_section:
            current.append(overlap_text)
        current.append(seg_text)
        current_pages.append(int(segment["page"]))
        current_section = segment["section"] or current_section
        if seg_tokens >= max_tokens or estimate_tokens("\n\n".join(current)) >= target_tokens:
            flush()
    if current:
        flush()

    # Normalize chunk_index after any merging.
    return [
        ReportChunkDraft(
            report_id=chunk.report_id,
            chunk_index=index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_title=chunk.section_title,
            text=chunk.text,
            text_hash=chunk.text_hash,
            token_count=chunk.token_count,
            metadata_json={**chunk.metadata_json, "chunk_index": index},
        )
        for index, chunk in enumerate(chunks)
    ]
