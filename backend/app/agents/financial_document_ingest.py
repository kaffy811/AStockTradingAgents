"""
financial_document_ingest.py — Phase 2B: Financial Document Ingest Pipeline.

Public API
----------
ingest_financial_document(...)  async — parse → clean → chunk → write DB
clean_financial_text(text)       sync  — whitespace/header cleanup
chunk_financial_text(text, ...)  sync  — paragraph-aware chunker

Supported input formats
-----------------------
  PDF  — via pypdf (page-aware, retains page metadata)
  HTML — via beautifulsoup4 (strips nav/footer/script/style)
  TXT  — plain read
  MD   — plain read (Markdown syntax preserved, no rendering needed)

Design constraints
------------------
  • embedding column left NULL — upgraded in Phase 2C (pgvector)
  • content_hash dedup: hash(title + source + published_at + raw_text[:5000])
  • Entire insert is wrapped in a savepoint; rollback on any chunk failure
  • Never raises to caller — always returns {"ok": bool, ...}
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ── Chunk sizing constants ─────────────────────────────────────────────────────

_CN_CHUNK_TARGET   = 700      # chars for Chinese-heavy text
_EN_CHUNK_TARGET   = 1200     # chars for English-heavy text
_CHUNK_OVERLAP     = 150      # overlap between consecutive chunks
_MAX_CHUNKS        = 2000     # safety cap — never write more than 2000 chunks per doc
_MIN_CHUNK_CHARS   = 30       # discard chunks shorter than this
_CONTENT_HASH_LEN  = 5000     # prefix length used for dedup hash


# ── Text cleaning ──────────────────────────────────────────────────────────────

def clean_financial_text(text: str) -> str:
    """
    Lightly clean raw financial document text.

    Rules:
    1. Normalize line endings.
    2. Remove purely decorative lines (========, --------, •••••).
    3. Collapse runs of 3+ blank lines to 2.
    4. Strip trailing whitespace from each line.
    5. Preserve numbers, percentages, currency symbols, and table structure.
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace per line (but keep indentation)
    lines = [ln.rstrip() for ln in text.split("\n")]

    # Remove purely decorative separator lines
    _DECOR = re.compile(r"^[\s=\-_•·*~#]{5,}$")
    lines = [ln for ln in lines if not _DECOR.match(ln)]

    # Collapse runs of 3+ empty lines to 2
    out: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append(ln)
        else:
            blank_run = 0
            out.append(ln)

    result = "\n".join(out).strip()
    return result


# ── Chunking ──────────────────────────────────────────────────────────────────

def _detect_lang_target(text: str) -> int:
    """Return target chunk size based on character composition."""
    cn_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if cn_count / max(len(text), 1) > 0.2:
        return _CN_CHUNK_TARGET
    return _EN_CHUNK_TARGET


def chunk_financial_text(
    text: str,
    *,
    page_map: list[dict] | None = None,
    section: str = "",
) -> list[dict]:
    """
    Split text into overlapping chunks suitable for keyword / vector retrieval.

    Parameters
    ----------
    text     : cleaned document text
    page_map : optional list of {start_char: int, end_char: int, page: int}
               from PDF parser — used to populate chunk metadata
    section  : optional section label (e.g. "Risk Factors")

    Returns
    -------
    list of {chunk_index, chunk_text, metadata}
    """
    if not text.strip():
        return []

    target_size = _detect_lang_target(text)
    paragraphs  = re.split(r"\n{2,}", text.strip())

    chunks: list[dict] = []
    current_chars: list[str] = []
    current_len = 0

    def _flush(current_chars: list[str]) -> None:
        chunk_text = "\n\n".join(current_chars).strip()
        if len(chunk_text) >= _MIN_CHUNK_CHARS:
            idx = len(chunks)
            meta: dict[str, Any] = {}
            if section:
                meta["section"] = section
            # Resolve page range from page_map
            if page_map:
                chunk_start = sum(len(t) + 2 for t in current_chars[:-1]) if current_chars else 0
                chunk_end   = chunk_start + len(chunk_text)
                pages = [
                    pm["page"] for pm in page_map
                    if pm["start_char"] <= chunk_end and pm["end_char"] >= chunk_start
                ]
                if pages:
                    meta["page_start"] = min(pages)
                    meta["page_end"]   = max(pages)
            chunks.append({
                "chunk_index": idx,
                "chunk_text":  chunk_text,
                "metadata":    meta,
            })

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Paragraph fits in one chunk
        if len(para) <= target_size:
            if current_len + len(para) + 2 > target_size and current_chars:
                _flush(current_chars)
                # Overlap: keep last paragraph for context
                current_chars = [current_chars[-1]] if current_chars else []
                current_len   = len(current_chars[0]) if current_chars else 0

            current_chars.append(para)
            current_len += len(para) + 2

        else:
            # Long paragraph: hard-split at sentence boundaries or character count
            if current_chars:
                _flush(current_chars)
                current_chars = []
                current_len   = 0

            # Split long para by target_size with overlap
            pos = 0
            while pos < len(para):
                end = min(pos + target_size, len(para))
                # Try to break at sentence end
                if end < len(para):
                    cut = para.rfind("。", pos, end)
                    if cut == -1:
                        cut = para.rfind(". ", pos, end)
                    if cut != -1:
                        end = cut + 1

                chunk_text = para[pos:end].strip()
                if len(chunk_text) >= _MIN_CHUNK_CHARS:
                    meta: dict[str, Any] = {}
                    if section:
                        meta["section"] = section
                    chunks.append({
                        "chunk_index": len(chunks),
                        "chunk_text":  chunk_text,
                        "metadata":    meta,
                    })
                pos = max(pos + 1, end - _CHUNK_OVERLAP)

    if current_chars:
        _flush(current_chars)

    return chunks[:_MAX_CHUNKS]


# ── Format parsers ────────────────────────────────────────────────────────────

def _parse_pdf(file_path: str) -> tuple[str, list[dict]]:
    """
    Parse a PDF file.

    Returns (full_text, page_map) where page_map is:
        [{page: int, start_char: int, end_char: int}, ...]

    Raises RuntimeError if pypdf is unavailable or file unreadable.
    """
    try:
        import pypdf  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF parsing. "
            "Install with: uv add pypdf"
        ) from exc

    try:
        reader = pypdf.PdfReader(file_path)
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF {file_path!r}: {exc}") from exc

    parts: list[str] = []
    page_map: list[dict] = []
    pos = 0

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            page_map.append({
                "page":       page_num,
                "start_char": pos,
                "end_char":   pos + len(page_text),
            })
            parts.append(page_text)
            pos += len(page_text) + 1  # +1 for separator newline

    return "\n".join(parts), page_map


def _parse_html(html_content: str) -> str:
    """
    Extract readable text from HTML.

    Removes: <script>, <style>, <nav>, <footer>, <header>, <aside>
    Keeps:   main body text, paragraphs, headings, table cells
    """
    try:
        from bs4 import BeautifulSoup  # noqa: PLC0415
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer",
                         "header", "aside", "noscript", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text
    except ImportError:
        # TODO: upgrade to bs4 when available; for now strip tags with regex
        log.warning("beautifulsoup4 not available — falling back to regex HTML strip")
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        return text


# ── Content hash ──────────────────────────────────────────────────────────────

def _compute_content_hash(
    title: str,
    source: str,
    published_at: str | None,
    raw_text: str,
) -> str:
    """SHA-256 of title|source|published_at|raw_text[:5000]. Returns 64-char hex."""
    content = f"{title}|{source}|{published_at or ''}|{raw_text[:_CONTENT_HASH_LEN]}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Main ingest function ───────────────────────────────────────────────────────

async def ingest_financial_document(
    *,
    db: AsyncSession,
    file_path: str | None = None,
    raw_text: str | None = None,
    url: str | None = None,
    symbol: str | None = None,
    market: str | None = None,
    title: str,
    source_type: str,
    source: str,
    published_at: str | None = None,
    metadata: dict | None = None,
    enable_embedding: bool = True,
    embedding_model: str | None = None,
) -> dict:
    """
    Parse, clean, chunk, and store a financial document.

    Priority for content source: file_path > raw_text > url (url not
    downloaded here — caller should fetch and pass raw_text).

    Parameters
    ----------
    enable_embedding : if True, call embed_texts() after chunking and write
                       embedding_vector / embedding_model / embedded_at.
                       Embedding failures are non-fatal: chunks still insert,
                       warnings["embedding_failed"] is set in the return value.
    embedding_model  : override settings.embedding_model for this call.

    Returns
    -------
    Success:
        {"ok": True, "document_id": str, "chunks_inserted": int,
         "title": str, "source_type": str, "symbol": str, "market": str,
         "duplicate": bool, "warnings": list[str]}
    Failure:
        {"ok": False, "error": str}
    """
    t0 = time.monotonic()
    metadata = metadata or {}
    ingest_warnings: list[str] = []

    # ── Step 1: resolve raw_text ──────────────────────────────────────────────
    page_map: list[dict] = []

    if file_path is not None:
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext == "pdf":
            try:
                raw_text, page_map = _parse_pdf(file_path)
            except RuntimeError as exc:
                return {"ok": False, "error": str(exc)}
        elif ext in ("html", "htm"):
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    raw_text = _parse_html(f.read())
            except OSError as exc:
                return {"ok": False, "error": f"Cannot read HTML file: {exc}"}
        else:
            # TXT / MD / unknown
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    raw_text = f.read()
            except OSError as exc:
                return {"ok": False, "error": f"Cannot read file: {exc}"}

    if not raw_text or not raw_text.strip():
        return {"ok": False, "error": "No text content found — document appears empty."}

    # ── Step 2: clean ─────────────────────────────────────────────────────────
    clean_text = clean_financial_text(raw_text)
    if not clean_text.strip():
        return {"ok": False, "error": "Document text is empty after cleaning."}

    # ── Step 3: compute hash for dedup ────────────────────────────────────────
    content_hash = _compute_content_hash(title, source, published_at, raw_text)

    # ── Step 4: check duplicate ───────────────────────────────────────────────
    try:
        dup_sql = text(
            "SELECT id FROM financial_documents WHERE content_hash = :h LIMIT 1"
        )
        dup_result = await db.execute(dup_sql, {"h": content_hash})
        existing = dup_result.fetchone()
        if existing:
            return {
                "ok":              True,
                "duplicate":       True,
                "document_id":     str(existing[0]),
                "chunks_inserted": 0,
                "title":           title,
                "source_type":     source_type,
                "symbol":          symbol,
                "market":          market,
            }
    except Exception as exc:
        # Table may not exist yet (before migration) — skip dedup check
        log.debug("content_hash dedup check failed (table may be missing): %s", exc)

    # ── Step 5: chunk ─────────────────────────────────────────────────────────
    chunks = chunk_financial_text(clean_text, page_map=page_map or None)
    if not chunks:
        return {"ok": False, "error": "Chunking produced no usable text segments."}

    # ── Step 5b: generate embeddings (non-fatal) ──────────────────────────────
    import json as _json
    from datetime import datetime, timezone

    chunk_vectors: list[list[float] | None] = [None] * len(chunks)
    resolved_embed_model: str | None = None

    if enable_embedding:
        try:
            from app.agents.embedding_service import embed_texts, EMBEDDING_DIM  # noqa: PLC0415
            from app.core.config import settings  # noqa: PLC0415
            resolved_embed_model = (
                embedding_model
                or getattr(settings, "embedding_model", None)
                or "mock"
            )
            chunk_texts = [ch["chunk_text"] for ch in chunks]
            vectors = await embed_texts(chunk_texts)
            if len(vectors) == len(chunks):
                chunk_vectors = vectors  # type: ignore[assignment]
            else:
                log.warning("embed_texts returned %d vectors for %d chunks", len(vectors), len(chunks))
                ingest_warnings.append("embedding_count_mismatch")
        except Exception as emb_exc:
            log.warning("Embedding failed (non-fatal): %s", emb_exc)
            ingest_warnings.append("embedding_failed")

    # ── Step 6: insert document + chunks in a transaction ────────────────────
    document_id = str(uuid.uuid4())
    embedded_at_val = datetime.now(timezone.utc).isoformat() if enable_embedding and not ingest_warnings else None
    try:
        # Insert document
        doc_sql = text("""
            INSERT INTO financial_documents
                (id, symbol, market, title, source_type, source,
                 published_at, url, raw_text, metadata, content_hash)
            VALUES
                (:id, :symbol, :market, :title, :source_type, :source,
                 :published_at, :url, :raw_text, :metadata::jsonb, :content_hash)
        """)
        await db.execute(doc_sql, {
            "id":           document_id,
            "symbol":       symbol,
            "market":       market,
            "title":        title,
            "source_type":  source_type,
            "source":       source,
            "published_at": published_at,
            "url":          url,
            "raw_text":     raw_text[:500_000],  # cap to avoid huge blobs
            "metadata":     _json.dumps(metadata, ensure_ascii=False),
            "content_hash": content_hash,
        })

        # Determine if embedding_vector column exists (pgvector installed)
        _has_vector_col = await _check_vector_column_exists(db)

        # Batch-insert chunks
        for i, ch in enumerate(chunks):
            ch_meta = {**metadata, **ch.get("metadata", {})}
            vec = chunk_vectors[i]

            if _has_vector_col and vec is not None:
                # Write embedding_vector as a PostgreSQL array literal
                vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
                chunk_sql = text("""
                    INSERT INTO financial_document_chunks
                        (id, document_id, symbol, market, chunk_index, chunk_text,
                         embedding, metadata,
                         embedding_vector, embedding_model, embedded_at)
                    VALUES
                        (:id, :doc_id, :symbol, :market, :chunk_index, :chunk_text,
                         NULL, :metadata::jsonb,
                         :vec::vector, :emb_model, :embedded_at)
                """)
                await db.execute(chunk_sql, {
                    "id":          str(uuid.uuid4()),
                    "doc_id":      document_id,
                    "symbol":      symbol,
                    "market":      market,
                    "chunk_index": ch["chunk_index"],
                    "chunk_text":  ch["chunk_text"],
                    "metadata":    _json.dumps(ch_meta, ensure_ascii=False),
                    "vec":         vec_str,
                    "emb_model":   resolved_embed_model,
                    "embedded_at": embedded_at_val,
                })
            else:
                # No vector column or no vector available — write NULL
                chunk_sql = text("""
                    INSERT INTO financial_document_chunks
                        (id, document_id, symbol, market, chunk_index, chunk_text,
                         embedding, metadata)
                    VALUES
                        (:id, :doc_id, :symbol, :market, :chunk_index, :chunk_text,
                         NULL, :metadata::jsonb)
                """)
                await db.execute(chunk_sql, {
                    "id":          str(uuid.uuid4()),
                    "doc_id":      document_id,
                    "symbol":      symbol,
                    "market":      market,
                    "chunk_index": ch["chunk_index"],
                    "chunk_text":  ch["chunk_text"],
                    "metadata":    _json.dumps(ch_meta, ensure_ascii=False),
                })

        await db.flush()   # make rows visible in current transaction

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "ingest_financial_document: inserted doc=%s chunks=%d elapsed=%dms warnings=%s",
            document_id, len(chunks), elapsed_ms, ingest_warnings,
        )
        return {
            "ok":              True,
            "duplicate":       False,
            "document_id":     document_id,
            "chunks_inserted": len(chunks),
            "title":           title,
            "source_type":     source_type,
            "symbol":          symbol,
            "market":          market,
            "elapsed_ms":      elapsed_ms,
            "warnings":        ingest_warnings,
        }

    except Exception as exc:
        log.error("ingest_financial_document: DB write failed, rolling back: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": f"DB write failed: {exc}"}


async def _check_vector_column_exists(db: AsyncSession) -> bool:
    """Return True if financial_document_chunks has an embedding_vector column."""
    try:
        result = await db.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'financial_document_chunks'
              AND column_name = 'embedding_vector'
            LIMIT 1
        """))
        return result.fetchone() is not None
    except Exception:
        return False
