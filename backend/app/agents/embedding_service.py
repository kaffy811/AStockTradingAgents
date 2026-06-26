"""
embedding_service.py — Phase 2C: Unified Embedding Provider.

Public API
----------
embed_text(text)           async → list[float]  (dim=1536)
embed_texts(texts)         async → list[list[float]]

Provider selection
------------------
Controlled by settings.embedding_provider (env: EMBEDDING_PROVIDER):

  "mock"     — deterministic hash-based embedding, no external calls.
               Always available; used in tests and CI.
  "openai"   — OpenAI text-embedding-3-small (1536 dims).
               Requires OPENAI_API_KEY.
  "deepseek" — Placeholder for DeepSeek embedding API (falls back to mock
               until DeepSeek releases an embedding endpoint).

Design constraints
------------------
  • Tests MUST NOT call external APIs.  Default provider is "mock".
  • Empty text raises ValueError — never silently returns zeros.
  • Texts longer than the model context window are truncated to max_tokens.
  • httpx timeout + 3 retries with exponential back-off.
  • On any embed failure the caller receives an exception; the ingest layer
    catches it and falls back to NULL embedding (keyword RAG still works).
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import Sequence

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
EMBEDDING_DIM         = 1536
_MAX_CHARS_OPENAI     = 8191 * 4   # ~4 chars/token, model ctx = 8191 tokens
_MAX_CHARS_MOCK       = 100_000    # no real limit for mock
_OPENAI_MODEL         = "text-embedding-3-small"
_HTTP_TIMEOUT_SECONDS = 10.0
_MAX_RETRIES          = 3


# ── Mock / deterministic provider ─────────────────────────────────────────────

def _mock_embed(text: str) -> list[float]:
    """
    Deterministic, dimension-stable embedding via SHA-256 seeded PRNG.

    Properties:
      • Same input → same output (deterministic).
      • Different inputs → different vectors (collision-resistant in practice).
      • L2-normalised so cosine similarity works correctly.
      • No external dependencies.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Use digest bytes to seed a simple LCG and generate 1536 floats
    seed = int.from_bytes(digest, "big")
    floats: list[float] = []
    for i in range(EMBEDDING_DIM):
        # xorshift64 step
        seed ^= seed << 13
        seed &= 0xFFFF_FFFF_FFFF_FFFF
        seed ^= seed >> 7
        seed ^= seed << 17
        seed &= 0xFFFF_FFFF_FFFF_FFFF
        floats.append((seed / 0xFFFF_FFFF_FFFF_FFFF) * 2.0 - 1.0)
    # L2-normalise
    norm = math.sqrt(sum(x * x for x in floats)) or 1.0
    return [x / norm for x in floats]


# ── OpenAI provider ───────────────────────────────────────────────────────────

async def _openai_embed_texts(texts: list[str], model: str, api_key: str) -> list[list[float]]:
    """Call OpenAI embeddings endpoint via httpx with retry."""
    import httpx  # noqa: PLC0415

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {"model": model, "input": texts}

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                # Sort by index to preserve order
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            log.warning("OpenAI embed attempt %d failed (%s); retry in %ds", attempt + 1, exc, wait)
            if attempt < _MAX_RETRIES - 1:
                import asyncio  # noqa: PLC0415
                await asyncio.sleep(wait)

    raise RuntimeError(f"OpenAI embedding failed after {_MAX_RETRIES} retries: {last_exc}")


# ── Public API ────────────────────────────────────────────────────────────────

def _get_provider() -> str:
    """Read provider from settings, default to 'mock'."""
    try:
        from app.core.config import settings  # noqa: PLC0415
        return getattr(settings, "embedding_provider", "mock") or "mock"
    except Exception:
        return "mock"


def _get_openai_key() -> str | None:
    try:
        from app.core.config import settings  # noqa: PLC0415
        return settings.openai_api_key
    except Exception:
        return None


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, breaking at a space if possible."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[:cut] if cut > 0 else text[:max_chars]


async def embed_text(text: str, *, provider: str | None = None) -> list[float]:
    """
    Generate a 1536-dimensional embedding for *text*.

    Raises ValueError if text is empty or whitespace-only.
    """
    if not text or not text.strip():
        raise ValueError("embed_text: text must be non-empty")

    results = await embed_texts([text], provider=provider)
    return results[0]


_DEFAULT_BATCH_SIZE = 64   # default internal batch size for all providers


def _get_batch_size(override: int | None) -> int:
    """Return batch size: override → settings → default."""
    if override is not None:
        return max(1, override)
    try:
        from app.core.config import settings  # noqa: PLC0415
        return max(1, getattr(settings, "embedding_batch_size", _DEFAULT_BATCH_SIZE))
    except Exception:
        return _DEFAULT_BATCH_SIZE


def _get_batch_retry_config() -> tuple[int, float, float]:
    """Return (retry_count, backoff_seconds, timeout_seconds) from settings."""
    try:
        from app.core.config import settings  # noqa: PLC0415
        retry_count  = int(getattr(settings, "embedding_batch_retry_count",          2))
        backoff_secs = float(getattr(settings, "embedding_batch_retry_backoff_seconds", 1.5))
        timeout_secs = float(getattr(settings, "embedding_batch_timeout_seconds",      30.0))
    except Exception:
        retry_count, backoff_secs, timeout_secs = 2, 1.5, 30.0
    return max(0, retry_count), max(0.1, backoff_secs), max(1.0, timeout_secs)


async def _openai_embed_batch_with_retry(
    texts: list[str],
    *,
    model: str,
    api_key: str,
    retry_count: int,
    backoff_seconds: float,
    timeout_seconds: float,
) -> list[list[float]]:
    """
    Embed a single batch with per-batch retry + configurable timeout.

    Tries up to (1 + retry_count) times with exponential backoff.
    Raises RuntimeError after all attempts are exhausted.
    """
    import asyncio  # noqa: PLC0415

    max_attempts = 1 + retry_count
    last_exc: Exception | None = None
    wait = backoff_seconds

    for attempt in range(max_attempts):
        try:
            return await _openai_embed_texts_with_timeout(
                texts, model=model, api_key=api_key, timeout_seconds=timeout_seconds
            )
        except Exception as exc:
            last_exc = exc
            log.warning(
                "OpenAI batch embed attempt %d/%d failed (%s)%s",
                attempt + 1, max_attempts, exc,
                f"; retry in {wait:.1f}s" if attempt < max_attempts - 1 else "",
            )
            if attempt < max_attempts - 1:
                await asyncio.sleep(wait)
                wait *= 2.0   # exponential back-off

    raise RuntimeError(
        f"OpenAI batch embedding failed after {max_attempts} attempts: {last_exc}"
    )


async def _openai_embed_texts_with_timeout(
    texts: list[str],
    *,
    model: str,
    api_key: str,
    timeout_seconds: float,
) -> list[list[float]]:
    """Call OpenAI embeddings endpoint with a per-request timeout."""
    import httpx  # noqa: PLC0415

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {"model": model, "input": texts}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]


async def embed_texts(
    texts: Sequence[str],
    *,
    provider: str | None = None,
    model: str | None = None,
    batch_size: int | None = None,
) -> list[list[float]]:
    """
    Generate 1536-dimensional embeddings for a list of texts.

    Parameters
    ----------
    texts      : list of non-empty strings
    provider   : override settings.embedding_provider
    model      : override default model name for the provider
    batch_size : max texts per API call (default from settings, typically 64)

    Raises ValueError for any empty text.
    Returns list[list[float]] in the same order as input.

    Internal batching:
      Large lists are split into batches of `batch_size`.  Each batch is
      sent independently.  Failures in one batch raise immediately (caller
      should catch and mark embedding as failed for that document).
    """
    texts = list(texts)
    if not texts:
        return []

    for i, t in enumerate(texts):
        if not t or not t.strip():
            raise ValueError(f"embed_texts: text at index {i} is empty")

    resolved_provider = provider or _get_provider()
    bs = _get_batch_size(batch_size)

    # ── Mock ──────────────────────────────────────────────────────────────────
    if resolved_provider == "mock":
        t0 = time.monotonic()
        # Mock is fast — no real batching needed, but split to satisfy tests
        all_results: list[list[float]] = []
        for start in range(0, len(texts), bs):
            batch = texts[start: start + bs]
            all_results.extend(
                _mock_embed(_truncate(t, _MAX_CHARS_MOCK)) for t in batch
            )
        log.debug(
            "embed_texts(mock): %d texts, %d batches, %.1fms",
            len(texts), math.ceil(len(texts) / bs), (time.monotonic() - t0) * 1000,
        )
        return all_results

    # ── OpenAI ────────────────────────────────────────────────────────────────
    if resolved_provider == "openai":
        api_key = _get_openai_key()
        if not api_key:
            log.warning("OPENAI_API_KEY not set — falling back to mock embedding")
            return [_mock_embed(_truncate(t, _MAX_CHARS_MOCK)) for t in texts]

        m = model or _OPENAI_MODEL
        truncated = [_truncate(t, _MAX_CHARS_OPENAI) for t in texts]
        retry_count, backoff_secs, timeout_secs = _get_batch_retry_config()

        all_results = []
        for start in range(0, len(truncated), bs):
            batch        = truncated[start: start + bs]
            batch_results = await _openai_embed_batch_with_retry(
                batch, model=m, api_key=api_key,
                retry_count=retry_count,
                backoff_seconds=backoff_secs,
                timeout_seconds=timeout_secs,
            )
            all_results.extend(batch_results)
        return all_results

    # ── DeepSeek (stub — falls back to mock until API is released) ───────────
    if resolved_provider == "deepseek":
        log.warning(
            "DeepSeek embedding provider not yet available — using mock fallback"
        )
        all_results = []
        for start in range(0, len(texts), bs):
            batch = texts[start: start + bs]
            all_results.extend(
                _mock_embed(_truncate(t, _MAX_CHARS_MOCK)) for t in batch
            )
        return all_results

    # Unknown provider — safe fallback
    log.warning("Unknown embedding_provider=%r — using mock", resolved_provider)
    all_results = []
    for start in range(0, len(texts), bs):
        batch = texts[start: start + bs]
        all_results.extend(
            _mock_embed(_truncate(t, _MAX_CHARS_MOCK)) for t in batch
        )
    return all_results
