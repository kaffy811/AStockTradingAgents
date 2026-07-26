"""Phase 6T-J1: PostgreSQL-backed Company V2 report RAG repository.

Persists RAG documents/chunks to the existing tables
``company_v2_report_rag_documents`` / ``company_v2_report_rag_chunks``
(aligned by migration i7j8k9l0m1n2) while exposing the same synchronous
surface as the in-memory ``CompanyV2ReportRagRepository`` so the index
service, retrievers, comparison and fusion paths work unchanged.

Design notes:
- Only asyncpg is installed (no sync PG driver), so this repository owns a
  private daemon-thread event loop with a dedicated AsyncEngine. Synchronous
  methods submit coroutines via ``run_coroutine_threadsafe``. This keeps the
  engine off the FastAPI loop (asyncpg connections are loop-bound).
- ``upsert_index`` is fully transactional: pending generation -> batched
  chunk insert -> persisted-count check -> activate new generation ->
  deactivate/stale old generation -> COMMIT. Any failure rolls back and the
  previous active generation stays intact.
- Idempotency key: (report_id, pdf_hash, parse_version, embedding_version).
  Identical identity with an active indexed/partial generation is reused
  without inserting anything (duplicate_index_avoided).
- No silent memory fallback: initialization or query errors raise
  ``CompanyV2RagRepositoryError``.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import datetime as dt
import json
import threading
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database_pool_policy import resolve_database_pool_policy
from app.models.company_v2_report_rag import ReportRagChunk as ChunkRow
from app.models.company_v2_report_rag import ReportRagDocument as DocumentRow
from app.services.company_v2_report_chunker import ReportChunkDraft


class CompanyV2RagRepositoryError(RuntimeError):
    """Structured repository failure (no fallback is performed)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.message = message


def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _dt_to_iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds") + "Z"


class DatabaseCompanyV2ReportRagRepository:
    """PostgreSQL persistence for Company V2 report RAG (persistent=True)."""

    backend = "database"
    persistent = True
    _shared_lock = threading.Lock()
    _shared_loop: asyncio.AbstractEventLoop | None = None
    _shared_thread: threading.Thread | None = None
    _shared_sessionmakers: dict[str, tuple[AsyncEngine, async_sessionmaker[AsyncSession]]] = {}

    def __init__(self, database_url: str | None = None, *, chunk_batch_size: int | None = None) -> None:
        self._database_url = database_url or settings.database_url
        self._chunk_batch_size = int(chunk_batch_size or settings.company_v2_rag_chunk_batch_size or 200)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._lock = threading.Lock()
        self.last_batch_stats: dict[str, Any] = {}

    # ── private loop-thread bridge ────────────────────────────────────────────

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        cls = type(self)
        with cls._shared_lock:
            if cls._shared_loop is None or cls._shared_loop.is_closed():
                loop = asyncio.new_event_loop()

                def _run() -> None:
                    asyncio.set_event_loop(loop)
                    loop.run_forever()

                thread = threading.Thread(target=_run, name="company-v2-rag-db", daemon=True)
                thread.start()
                cls._shared_loop = loop
                cls._shared_thread = thread
            self._loop = cls._shared_loop
            self._thread = cls._shared_thread
            return cls._shared_loop

    def _run(self, coro: Any) -> Any:
        loop = self._ensure_loop()
        timeout = float(settings.company_v2_rag_db_run_timeout_seconds or 60.0)
        outer_timeout = timeout + 5.0

        async def _with_timeout() -> Any:
            return await asyncio.wait_for(coro, timeout=timeout)

        future = asyncio.run_coroutine_threadsafe(_with_timeout(), loop)
        try:
            return future.result(timeout=outer_timeout)
        except (FutureTimeoutError, TimeoutError) as exc:
            future.cancel()
            self._discard_shared_resources(loop)
            raise CompanyV2RagRepositoryError(
                "RAG_DB_QUERY_TIMEOUT",
                f"timeout_after={timeout:.1f}s",
            ) from exc
        except CompanyV2RagRepositoryError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as structured error, never fallback
            raise CompanyV2RagRepositoryError("RAG_DB_QUERY_FAILED", str(exc)[:400]) from exc

    async def _get_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            try:
                database_url = make_url(self._database_url)
                cache_key = database_url.render_as_string(hide_password=False)
                shared = type(self)._shared_sessionmakers.get(cache_key)
                if shared is not None:
                    self._engine, self._sessionmaker = shared
                    return self._sessionmaker

                # Mirror app.core.database without constructing or importing
                # the request-loop engine in this private loop-thread bridge.
                policy = resolve_database_pool_policy(
                    self._database_url,
                    settings.database_transaction_pool_strategy,
                    connection_mode=settings.database_connection_mode,
                    pool_pre_ping=settings.database_pool_pre_ping,
                    command_timeout_seconds=settings.database_command_timeout_seconds,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    direct_pool_size=settings.database_direct_pool_size,
                    direct_max_overflow=settings.database_direct_max_overflow,
                    pool_recycle_seconds=settings.database_pool_recycle_seconds,
                    pool_timeout_seconds=settings.database_pool_timeout_seconds,
                )
                engine_kwargs = dict(policy.pool_kwargs)
                self._engine = create_async_engine(
                    self._database_url,
                    echo=False,
                    **engine_kwargs,
                )
                self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
                type(self)._shared_sessionmakers[cache_key] = (self._engine, self._sessionmaker)
            except Exception as exc:  # noqa: BLE001
                raise CompanyV2RagRepositoryError("RAG_DB_INIT_FAILED", str(exc)[:400]) from exc
        return self._sessionmaker

    @classmethod
    def _discard_shared_resources(cls, loop: asyncio.AbstractEventLoop) -> None:
        """Drop a timed-out loop/engine so later calls start from clean state."""
        with cls._shared_lock:
            if cls._shared_loop is not loop:
                return
            thread = cls._shared_thread
            cls._shared_sessionmakers = {}
            cls._shared_loop = None
            cls._shared_thread = None
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
            if thread is not None:
                thread.join(timeout=1.0)

    @classmethod
    def close_shared_resources(cls, *, timeout: float | None = None) -> None:
        """Dispose shared DB resources, primarily for tests and app shutdown hooks."""
        with cls._shared_lock:
            loop = cls._shared_loop
            thread = cls._shared_thread
            engines = [engine for engine, _ in cls._shared_sessionmakers.values()]
            cls._shared_sessionmakers = {}
            cls._shared_loop = None
            cls._shared_thread = None
        if loop is None:
            return

        async def _dispose() -> None:
            for engine in engines:
                await engine.dispose()

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_dispose(), loop)
            try:
                future.result(timeout=timeout or settings.company_v2_rag_db_run_timeout_seconds)
            except Exception:
                future.cancel()
            loop.call_soon_threadsafe(loop.stop)
            if thread is not None:
                thread.join(timeout=timeout or 5.0)
        if not loop.is_closed():
            loop.close()

    def status(self) -> dict[str, Any]:
        return {"repository_backend": self.backend, "persistent": self.persistent}

    # ── row -> dataclass mapping (keeps retriever/services unchanged) ────────

    @staticmethod
    def _chunk_record(row: ChunkRow) -> "ReportRagChunkRecord":
        from app.services.company_v2_report_rag_index_service import ReportRagChunkRecord

        embedding = None
        if row.embedding:
            try:
                embedding = json.loads(row.embedding)
            except Exception:  # noqa: BLE001
                embedding = None
        try:
            metadata = json.loads(row.metadata_json) if row.metadata_json else {}
        except Exception:  # noqa: BLE001
            metadata = {}
        return ReportRagChunkRecord(
            id=int(row.id),
            rag_document_id=int(row.rag_document_id),
            report_id=int(row.report_id),
            chunk_index=int(row.chunk_index),
            page_start=int(row.page_start),
            page_end=int(row.page_end),
            section_title=row.section_title,
            text=row.text,
            text_hash=row.text_hash,
            token_count=int(row.token_count or 0),
            embedding=embedding,
            metadata_json=metadata,
            created_at=_dt_to_iso(row.created_at) or _now_iso(),
        )

    def _document_record(self, row: DocumentRow, chunks: list[ChunkRow]) -> "ReportRagDocumentRecord":
        from app.services.company_v2_report_rag_index_service import ReportRagDocumentRecord

        return ReportRagDocumentRecord(
            id=int(row.id),
            report_id=int(row.report_id),
            market=row.market,
            symbol=row.symbol,
            company_name=row.company_name,
            report_year=int(row.report_year),
            report_type=row.report_type,
            announcement_date=row.announcement_date,
            source_url=row.source_url,
            pdf_hash=row.pdf_hash,
            parse_version=row.parse_version,
            page_count=int(row.page_count or 0),
            chunk_count=int(row.chunk_count or 0),
            embedding_model=row.embedding_model or "",
            embedding_version=row.embedding_version or "",
            status=row.status,
            created_at=_dt_to_iso(row.created_at) or _now_iso(),
            updated_at=_dt_to_iso(row.updated_at) or _now_iso(),
            active_index=bool(row.active_index),
            supersedes_rag_document_id=row.supersedes_rag_document_id,
            indexed_at=_dt_to_iso(row.indexed_at),
            deleted_at=_dt_to_iso(row.deleted_at),
            index_generation=int(row.index_generation or 1),
            report_title=None,
            stale_reason=row.stale_reason,
            last_error=None,
            chunks=[self._chunk_record(chunk) for chunk in chunks],
        )

    # ── reads ────────────────────────────────────────────────────────────────

    async def _load_document(self, session: AsyncSession, row: DocumentRow) -> "ReportRagDocumentRecord":
        chunk_rows = (
            await session.execute(
                select(ChunkRow).where(ChunkRow.rag_document_id == row.id).order_by(ChunkRow.chunk_index)
            )
        ).scalars().all()
        return self._document_record(row, list(chunk_rows))

    async def _get_document_async(self, report_id: int, *, active_only: bool) -> "ReportRagDocumentRecord | None":
        maker = await self._get_sessionmaker()
        async with maker() as session:
            stmt = select(DocumentRow).where(DocumentRow.report_id == int(report_id))
            if active_only:
                stmt = stmt.where(DocumentRow.active_index == 1, DocumentRow.deleted_at.is_(None))
            stmt = stmt.order_by(DocumentRow.index_generation.desc())
            row = (await session.execute(stmt)).scalars().first()
            if not row:
                return None
            return await self._load_document(session, row)

    async def _get_document_metadata_async(self, report_id: int, *, active_only: bool) -> "ReportRagDocumentRecord | None":
        maker = await self._get_sessionmaker()
        async with maker() as session:
            stmt = select(DocumentRow).where(DocumentRow.report_id == int(report_id))
            if active_only:
                stmt = stmt.where(DocumentRow.active_index == 1, DocumentRow.deleted_at.is_(None))
            stmt = stmt.order_by(DocumentRow.index_generation.desc())
            row = (await session.execute(stmt)).scalars().first()
            if not row:
                return None
            return self._document_record(row, [])

    def get_document(self, report_id: int):
        """Active, non-deleted document (protocol: get_active_document)."""
        return self._run(self._get_document_async(report_id, active_only=True))

    # protocol aliases
    get_active_document = get_document
    get_document_by_report_id = get_document

    async def get_document_async(self, report_id: int):
        """Native async active document lookup for request-path tools."""
        return await self._get_document_async(report_id, active_only=True)

    def get_any_document(self, report_id: int):
        return self._run(self._get_document_async(report_id, active_only=False))

    async def get_any_document_async(self, report_id: int):
        """Native async document lookup, including stale/deleted generations."""
        return await self._get_document_async(report_id, active_only=False)

    def get_any_document_metadata(self, report_id: int):
        return self._run(self._get_document_metadata_async(report_id, active_only=False))

    async def get_any_document_metadata_async(self, report_id: int):
        """Native async metadata lookup without loading chunks."""
        return await self._get_document_metadata_async(report_id, active_only=False)

    async def query_chunks_async(self, report_id: int, *, limit: int = 8):
        """Native async chunk lookup for layered Chat request paths."""
        doc = await self.get_document_async(report_id)
        if not doc:
            return []
        return list(doc.chunks or [])[: max(1, min(int(limit or 8), 20))]

    async def get_structured_fields_async(self, report_id: int):
        """Native async structured-field facade.

        Field extraction is owned by the report financial extractor service; this
        repository method exists so runtime tools have an async, non-bridge entry
        point and never need the deprecated sync facade.
        """
        return {"report_id": int(report_id), "fields": {}}

    async def get_latest_indexed_report_async(self, *, symbol: str, market: str | None = None):
        """Native async latest active indexed report metadata lookup."""
        maker = await self._get_sessionmaker()
        async with maker() as session:
            stmt = (
                select(DocumentRow)
                .where(DocumentRow.symbol == symbol, DocumentRow.active_index == 1, DocumentRow.deleted_at.is_(None))
                .order_by(DocumentRow.report_year.desc(), DocumentRow.index_generation.desc())
            )
            if market:
                stmt = stmt.where(DocumentRow.market == market)
            row = (await session.execute(stmt)).scalars().first()
            if not row:
                return None
            return self._document_record(row, [])

    def list_documents(self, symbol: str | None = None, *, include_deleted: bool = False):
        async def _list() -> list[Any]:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                stmt = select(DocumentRow).where(DocumentRow.active_index == 1)
                if symbol:
                    stmt = stmt.where(DocumentRow.symbol == symbol)
                if not include_deleted:
                    stmt = stmt.where(DocumentRow.deleted_at.is_(None))
                rows = (await session.execute(stmt)).scalars().all()
                docs = [await self._load_document(session, row) for row in rows]
                return sorted(docs, key=lambda d: (d.report_year, d.report_type, d.report_id), reverse=True)

        return self._run(_list())

    def list_history(self, report_id: int):
        async def _hist() -> list[Any]:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                rows = (
                    await session.execute(
                        select(DocumentRow)
                        .where(DocumentRow.report_id == int(report_id))
                        .order_by(DocumentRow.index_generation.desc())
                    )
                ).scalars().all()
                return [await self._load_document(session, row) for row in rows]

        return self._run(_hist())

    def count_chunks(self, report_id: int) -> int:
        async def _count() -> int:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                active = (
                    await session.execute(
                        select(DocumentRow.id)
                        .where(
                            DocumentRow.report_id == int(report_id),
                            DocumentRow.active_index == 1,
                            DocumentRow.deleted_at.is_(None),
                        )
                    )
                ).scalars().first()
                if active is None:
                    return 0
                return int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ChunkRow).where(ChunkRow.rag_document_id == active)
                        )
                    ).scalar()
                    or 0
                )

        return self._run(_count())

    # ── mutations ────────────────────────────────────────────────────────────

    def mark_stale(self, report_id: int, reason: str):
        async def _stale() -> Any:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                row = (
                    await session.execute(
                        select(DocumentRow).where(
                            DocumentRow.report_id == int(report_id),
                            DocumentRow.active_index == 1,
                            DocumentRow.deleted_at.is_(None),
                        )
                    )
                ).scalars().first()
                if not row:
                    return None
                row.status = "stale"
                row.stale_reason = reason
                row.updated_at = dt.datetime.utcnow()
                await session.commit()
                return await self._get_document_async(report_id, active_only=False)

        return self._run(_stale())

    def soft_delete(self, report_id: int):
        async def _delete() -> Any:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                row = (
                    await session.execute(
                        select(DocumentRow)
                        .where(DocumentRow.report_id == int(report_id), DocumentRow.deleted_at.is_(None))
                        .order_by(DocumentRow.index_generation.desc())
                    )
                ).scalars().first()
                if not row:
                    return None
                row.deleted_at = dt.datetime.utcnow()
                row.active_index = 0
                row.updated_at = dt.datetime.utcnow()
                await session.commit()
                return await self._get_document_async(report_id, active_only=False)

        return self._run(_delete())

    def clear(self) -> None:
        """Delete ALL RAG rows. Guarded: intended for isolated tests only."""
        async def _clear() -> None:
            maker = await self._get_sessionmaker()
            async with maker() as session:
                await session.execute(delete(ChunkRow))
                await session.execute(delete(DocumentRow))
                await session.commit()

        self._run(_clear())

    # ── transactional index upsert ───────────────────────────────────────────

    def upsert_index(
        self,
        descriptor: Any,
        *,
        page_count: int,
        chunk_drafts: list[ReportChunkDraft],
        embeddings_by_hash: dict[str, list[float]],
        status: str,
        stale_reason: str | None = None,
        last_error: str | None = None,
        force_new_generation: bool = False,
    ):
        return self._run(
            self._upsert_index_async(
                descriptor,
                page_count=page_count,
                chunk_drafts=chunk_drafts,
                embeddings_by_hash=embeddings_by_hash,
                status=status,
                stale_reason=stale_reason,
                force_new_generation=force_new_generation,
            )
        )

    async def _upsert_index_async(
        self,
        descriptor: Any,
        *,
        page_count: int,
        chunk_drafts: list[ReportChunkDraft],
        embeddings_by_hash: dict[str, list[float]],
        status: str,
        stale_reason: str | None,
        force_new_generation: bool,
    ):
        from app.services.company_v2_report_embedding_service import company_v2_report_embedding_service

        embedding_model = company_v2_report_embedding_service.embedding_model
        embedding_version = company_v2_report_embedding_service.embedding_version
        maker = await self._get_sessionmaker()
        batch_stats = {"batches_total": 0, "batches_success": 0, "batches_failed": 0, "persisted_chunk_count": 0}

        async with maker() as session:
            try:
                existing = (
                    await session.execute(
                        select(DocumentRow)
                        .where(
                            DocumentRow.report_id == int(descriptor.report_id),
                            DocumentRow.active_index == 1,
                            DocumentRow.deleted_at.is_(None),
                        )
                        .order_by(DocumentRow.index_generation.desc())
                    )
                ).scalars().first()

                same_identity = (
                    existing is not None
                    and existing.pdf_hash == descriptor.pdf_hash
                    and existing.parse_version == descriptor.parse_version
                    and existing.embedding_version == embedding_version
                )
                if same_identity and not force_new_generation and existing.status in {"indexed", "partial"}:
                    # duplicate_index_avoided: reuse active generation, insert nothing
                    self.last_batch_stats = {**batch_stats, "duplicate_index_avoided": True}
                    return await self._load_document(session, existing)

                generation = 1
                supersedes: int | None = None
                if existing is not None:
                    top = (
                        await session.execute(
                            select(func.max(DocumentRow.index_generation)).where(
                                DocumentRow.report_id == int(descriptor.report_id)
                            )
                        )
                    ).scalar()
                    generation = int(top or existing.index_generation) + 1
                    supersedes = int(existing.id)

                now = dt.datetime.utcnow()
                new_doc = DocumentRow(
                    report_id=int(descriptor.report_id),
                    market=descriptor.market.upper(),
                    symbol=descriptor.symbol,
                    company_name=descriptor.company_name,
                    report_year=int(descriptor.report_year),
                    report_type=descriptor.report_type,
                    announcement_date=descriptor.announcement_date,
                    source_url=descriptor.source_url,
                    pdf_hash=descriptor.pdf_hash,
                    parse_version=descriptor.parse_version,
                    page_count=int(page_count),
                    chunk_count=len(chunk_drafts),
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                    status="pending",
                    active_index=0,  # activated only after all chunks persisted
                    supersedes_rag_document_id=supersedes,
                    stale_reason=stale_reason,
                    indexed_at=None,
                    deleted_at=None,
                    index_generation=generation,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_doc)
                await session.flush()  # assign new_doc.id

                # batched chunk insert (Core executemany — one roundtrip batch,
                # never per-chunk statements/commits)
                batch_size = max(1, self._chunk_batch_size)
                for start in range(0, len(chunk_drafts), batch_size):
                    batch = chunk_drafts[start : start + batch_size]
                    batch_stats["batches_total"] += 1
                    rows: list[dict[str, Any]] = []
                    for draft in batch:
                        if not (draft.text or "").strip():
                            raise CompanyV2RagRepositoryError("EMPTY_CHUNK", f"chunk_index={draft.chunk_index}")
                        embedding = embeddings_by_hash.get(draft.text_hash)
                        rows.append(
                            {
                                "rag_document_id": new_doc.id,
                                "report_id": int(descriptor.report_id),
                                "chunk_index": int(draft.chunk_index),
                                "page_start": int(draft.page_start),
                                "page_end": int(draft.page_end),
                                "section_title": draft.section_title,
                                "text": draft.text,
                                "text_hash": draft.text_hash,
                                "token_count": int(draft.token_count or 0),
                                "embedding": json.dumps(embedding) if embedding is not None else None,
                                "metadata_json": json.dumps(
                                    {
                                        **(draft.metadata_json or {}),
                                        "chunking_version": descriptor.parse_version,
                                        "embedding_model": embedding_model,
                                        "embedding_version": embedding_version,
                                        "index_generation": generation,
                                    },
                                    ensure_ascii=False,
                                ),
                                "created_at": now,
                            }
                        )
                    await session.execute(insert(ChunkRow), rows)
                    batch_stats["batches_success"] += 1
                    batch_stats["persisted_chunk_count"] += len(rows)

                # verify persisted count inside the transaction
                persisted = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ChunkRow).where(ChunkRow.rag_document_id == new_doc.id)
                        )
                    ).scalar()
                    or 0
                )
                if persisted != len(chunk_drafts):
                    raise CompanyV2RagRepositoryError(
                        "PERSISTED_COUNT_MISMATCH", f"persisted={persisted} expected={len(chunk_drafts)}"
                    )

                # deactivate old generation, then activate the new one (single tx)
                if existing is not None:
                    existing.active_index = 0
                    existing.status = "stale"
                    existing.stale_reason = stale_reason or "superseded_by_new_index"
                    existing.updated_at = now
                new_doc.status = status
                new_doc.active_index = 1 if status in {"indexed", "partial"} else 0
                new_doc.indexed_at = now if status in {"indexed", "partial"} else None
                await session.commit()
                self.last_batch_stats = {**batch_stats, "duplicate_index_avoided": False}
                return await self._load_document(session, new_doc)
            except Exception:
                batch_stats["batches_failed"] += 1
                self.last_batch_stats = {**batch_stats, "duplicate_index_avoided": False}
                await session.rollback()
                raise

    def to_jsonable(self, report_id: int) -> dict[str, Any] | None:
        doc = self.get_document(report_id)
        if not doc:
            return None
        from dataclasses import asdict

        payload = asdict(doc)
        for chunk in payload["chunks"]:
            chunk["text_excerpt"] = chunk.pop("text")[:800]
            chunk["embedding"] = None if chunk.get("embedding") is None else f"{len(chunk['embedding'])}d"
        return payload
