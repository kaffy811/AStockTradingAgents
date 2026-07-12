"""
app/services/report_embedding_provider.py — Report RAG Embedding Provider（Phase 6G-1）

Provider hierarchy:
  BaseReportEmbeddingProvider  (ABC)
  ├── MockReportEmbeddingProvider     — deterministic SHA256 hash, 0-cost, CI default
  ├── LocalSentenceTransformerProvider — sentence-transformers local model
  └── DisabledReportEmbeddingProvider  — embedding disabled, keyword fallback only

Config (env):
  REPORT_EMBEDDING_PROVIDER=mock | local | disabled
  REPORT_EMBEDDING_MODEL=<name_or_path>    # for local provider
  REPORT_EMBEDDING_DIM=384                 # must match pgvector schema dimension (default: 384)

Dimension enforcement (Phase 6G-1):
  If a local model outputs dim != REPORT_EMBEDDING_DIM, a RuntimeError is raised.
  Silent pad/truncate has been REMOVED. Choose a model whose native dim matches the schema,
  or run the appropriate schema migration first. See docs/22_local_embedding_rag_quality.md.
"""
from __future__ import annotations

import abc
import hashlib
import logging
import math
from typing import Optional

log = logging.getLogger(__name__)

# Module-level import so tests can patch app.services.report_embedding_provider.get_settings
from app.core.config import get_settings  # noqa: E402

# ── Abstract base ──────────────────────────────────────────────────────────────


class BaseReportEmbeddingProvider(abc.ABC):
    """Abstract interface for report-RAG embedding providers."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def embedding_dim(self) -> int:
        ...

    @abc.abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        ...

    def is_available(self) -> bool:
        return True

    def unavailability_reason(self) -> Optional[str]:
        return None


# ── Mock provider ─────────────────────────────────────────────────────────────


class MockReportEmbeddingProvider(BaseReportEmbeddingProvider):
    """Deterministic SHA-256 seeded embedding, no external dependencies."""

    def __init__(self, target_dim: int = 384) -> None:
        self._dim = target_dim

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def _mock_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big")
        # LCG PRNG
        a, c, m = 1664525, 1013904223, 2**32
        floats = []
        x = seed
        for _ in range(self._dim):
            x = (a * x + c) % m
            floats.append((x / m) * 2.0 - 1.0)
        # L2-normalize
        norm = math.sqrt(sum(v * v for v in floats)) or 1.0
        return [v / norm for v in floats]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._mock_vector(t) for t in texts]


# ── Disabled provider ─────────────────────────────────────────────────────────


class DisabledReportEmbeddingProvider(BaseReportEmbeddingProvider):
    """Embedding disabled. Chunks are stored but not embedded. Keyword fallback only."""

    def __init__(self, target_dim: int = 384) -> None:
        self._dim = target_dim

    @property
    def provider_name(self) -> str:
        return "disabled"

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def is_available(self) -> bool:
        return False

    def unavailability_reason(self) -> Optional[str]:
        return "REPORT_EMBEDDING_PROVIDER=disabled — embedding skipped, keyword fallback only"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Embedding is disabled (REPORT_EMBEDDING_PROVIDER=disabled)")


# ── Local sentence-transformers provider ───────────────────────────────────────


class LocalSentenceTransformerProvider(BaseReportEmbeddingProvider):
    """
    Local embedding using sentence-transformers library.

    Recommended models (native 384-dim, matches default schema):
      BAAI/bge-small-zh-v1.5      — Chinese-optimised, ~95MB
      intfloat/multilingual-e5-small — multilingual, ~120MB

    Other dims require a schema migration:
      768-dim: BAAI/bge-base-zh-v1.5, intfloat/multilingual-e5-base
      1024-dim: BAAI/bge-large-zh-v1.5

    Dimension enforcement (Phase 6G-1):
      If model_dim != target_dim, embed_texts() raises RuntimeError.
      Silent pad/truncate has been removed. The model dim must match
      REPORT_EMBEDDING_DIM exactly. Run a schema migration first if needed.
    """

    def __init__(
        self,
        model_name_or_path: str,
        target_dim: int = 384,
        batch_size: int = 16,
    ) -> None:
        self._model_name = model_name_or_path
        self._target_dim = target_dim
        self._batch_size = batch_size
        self._model = None
        self._model_dim: Optional[int] = None
        self._init_error: Optional[str] = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._model_dim = self._model.get_sentence_embedding_dimension()
            log.info(
                "LocalSentenceTransformerProvider: loaded model=%s dim=%d target_dim=%d",
                self._model_name, self._model_dim, self._target_dim,
            )
            if self._model_dim != self._target_dim:
                self._init_error = (
                    f"Model '{self._model_name}' outputs dim={self._model_dim} but "
                    f"REPORT_EMBEDDING_DIM={self._target_dim}. "
                    f"Either set REPORT_EMBEDDING_DIM={self._model_dim} and run a schema migration, "
                    f"or choose a model that natively outputs {self._target_dim} dims. "
                    f"See docs/22_local_embedding_rag_quality.md — silent pad/truncate removed in Phase 6G-1."
                )
                log.error("LocalSentenceTransformerProvider: %s", self._init_error)
                self._model = None  # Mark unavailable
        except ImportError:
            self._init_error = "sentence-transformers not installed. Run: uv pip install sentence-transformers"
            log.warning("LocalSentenceTransformerProvider: %s", self._init_error)
        except Exception as e:
            self._init_error = f"Failed to load model {self._model_name!r}: {e}"
            log.warning("LocalSentenceTransformerProvider: %s", self._init_error)

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def embedding_dim(self) -> int:
        return self._target_dim

    def is_available(self) -> bool:
        return self._model is not None and self._init_error is None

    def unavailability_reason(self) -> Optional[str]:
        return self._init_error

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.is_available():
            raise RuntimeError(self._init_error or "Local model not available")

        import asyncio
        loop = asyncio.get_event_loop()

        def _encode() -> list[list[float]]:
            # normalize_embeddings=True for cosine similarity
            embeddings = self._model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vecs = [list(map(float, vec)) for vec in embeddings]
            # Strict dim check — no pad/truncate (Phase 6G-1)
            for vec in vecs:
                if len(vec) != self._target_dim:
                    raise RuntimeError(
                        f"Model returned dim={len(vec)} but target_dim={self._target_dim}. "
                        f"This should have been caught at load time. Aborting embed."
                    )
            return vecs

        # Run in executor to avoid blocking event loop
        vectors = await loop.run_in_executor(None, _encode)
        return vectors


# ── Factory ───────────────────────────────────────────────────────────────────


def get_report_embedding_provider() -> BaseReportEmbeddingProvider:
    """
    Build the configured embedding provider for report RAG.
    Never raises — on any error returns MockReportEmbeddingProvider.
    """
    try:
        settings = get_settings()
        provider_name = (settings.report_embedding_provider or "mock").lower().strip()
        target_dim    = settings.report_embedding_dim or 1536

        if provider_name == "disabled":
            return DisabledReportEmbeddingProvider(target_dim=target_dim)

        if provider_name == "local":
            model = settings.report_embedding_model
            if not model:
                log.warning(
                    "REPORT_EMBEDDING_PROVIDER=local but REPORT_EMBEDDING_MODEL not set. "
                    "Falling back to mock. Set REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5"
                )
                return MockReportEmbeddingProvider(target_dim=target_dim)
            p = LocalSentenceTransformerProvider(model, target_dim=target_dim)
            if not p.is_available():
                log.warning(
                    "Local provider unavailable (%s), falling back to mock",
                    p.unavailability_reason(),
                )
                return MockReportEmbeddingProvider(target_dim=target_dim)
            return p

        # Default: mock
        return MockReportEmbeddingProvider(target_dim=target_dim)

    except Exception as e:
        log.error("get_report_embedding_provider failed: %s — using mock", e)
        return MockReportEmbeddingProvider(target_dim=384)
