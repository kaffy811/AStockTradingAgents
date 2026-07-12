"""Index service and repository for Company V2 single-report RAG."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime as dt
import json
from pathlib import Path
from typing import Any

from app.services.company_v2_pdf_text_parser import LOW_COVERAGE_CODE
from app.services.company_v2_report_chunker import (
    PARSE_VERSION,
    ReportChunkDraft,
    chunk_report_pages,
    load_pages_from_sidecar,
)
from app.services.company_v2_report_embedding_service import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    company_v2_report_embedding_service,
)
from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url


VALID_RAG_STATUSES = {"pending", "indexing", "indexed", "partial", "failed", "stale"}


@dataclass(slots=True)
class ReportDescriptor:
    report_id: int
    market: str
    symbol: str
    company_name: str | None
    report_year: int
    report_type: str
    announcement_date: str | None
    source_url: str
    pdf_hash: str | None
    report_title: str | None = None
    parse_version: str = PARSE_VERSION


@dataclass(slots=True)
class ReportRagChunkRecord:
    id: int
    rag_document_id: int
    report_id: int
    chunk_index: int
    page_start: int
    page_end: int
    section_title: str | None
    text: str
    text_hash: str
    token_count: int
    embedding: list[float] | None
    metadata_json: dict[str, Any]
    created_at: str


@dataclass(slots=True)
class ReportRagDocumentRecord:
    id: int
    report_id: int
    market: str
    symbol: str
    company_name: str | None
    report_year: int
    report_type: str
    announcement_date: str | None
    source_url: str
    pdf_hash: str | None
    parse_version: str
    page_count: int
    chunk_count: int
    embedding_model: str
    embedding_version: str
    status: str
    created_at: str
    updated_at: str
    active_index: bool = True
    supersedes_rag_document_id: int | None = None
    indexed_at: str | None = None
    deleted_at: str | None = None
    index_generation: int = 1
    report_title: str | None = None
    stale_reason: str | None = None
    last_error: str | None = None
    chunks: list[ReportRagChunkRecord] = field(default_factory=list)


class CompanyV2ReportRagRepository:
    """In-memory repository backend.

    Phase 6T-J1: this backend is for isolated unit tests only
    (persistent=False). Production uses DatabaseCompanyV2ReportRagRepository
    via company_v2_report_rag_repository_factory (backend=database).
    """

    backend = "memory"
    persistent = False

    def __init__(self) -> None:
        self._documents: dict[int, ReportRagDocumentRecord] = {}
        self._history: dict[int, list[ReportRagDocumentRecord]] = {}
        self._next_document_id = 1
        self._next_chunk_id = 1

    def get_document(self, report_id: int) -> ReportRagDocumentRecord | None:
        doc = self._documents.get(int(report_id))
        if doc and not doc.deleted_at and doc.active_index:
            return doc
        return None

    def get_any_document(self, report_id: int) -> ReportRagDocumentRecord | None:
        return self._documents.get(int(report_id))

    def list_documents(self, symbol: str | None = None, *, include_deleted: bool = False) -> list[ReportRagDocumentRecord]:
        docs = list(self._documents.values())
        if symbol:
            docs = [doc for doc in docs if doc.symbol == symbol]
        if not include_deleted:
            docs = [doc for doc in docs if not doc.deleted_at]
        return sorted(docs, key=lambda doc: (doc.report_year, doc.report_type, doc.report_id), reverse=True)

    def list_history(self, report_id: int) -> list[ReportRagDocumentRecord]:
        docs = list(self._history.get(int(report_id), []))
        current = self._documents.get(int(report_id))
        if current:
            docs.append(current)
        return sorted(docs, key=lambda doc: doc.index_generation, reverse=True)

    def clear(self) -> None:
        self._documents.clear()
        self._history.clear()
        self._next_document_id = 1
        self._next_chunk_id = 1

    def mark_stale(self, report_id: int, reason: str) -> ReportRagDocumentRecord | None:
        doc = self._documents.get(int(report_id))
        if not doc or doc.deleted_at:
            return None
        doc.status = "stale"
        doc.stale_reason = reason
        doc.updated_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return doc

    def soft_delete(self, report_id: int) -> ReportRagDocumentRecord | None:
        doc = self._documents.get(int(report_id))
        if not doc:
            return None
        now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        doc.deleted_at = now
        doc.active_index = False
        doc.updated_at = now
        return doc

    def upsert_index(
        self,
        descriptor: ReportDescriptor,
        *,
        page_count: int,
        chunk_drafts: list[ReportChunkDraft],
        embeddings_by_hash: dict[str, list[float]],
        status: str,
        stale_reason: str | None = None,
        last_error: str | None = None,
        force_new_generation: bool = False,
    ) -> ReportRagDocumentRecord:
        now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        existing = self._documents.get(descriptor.report_id)

        embedding_model = company_v2_report_embedding_service.embedding_model
        embedding_version = company_v2_report_embedding_service.embedding_version
        same_index_key = (
            existing
            and existing.active_index
            and not existing.deleted_at
            and existing.pdf_hash == descriptor.pdf_hash
            and existing.parse_version == descriptor.parse_version
            and existing.embedding_version == embedding_version
        )
        if same_index_key and not force_new_generation and existing.status in {"indexed", "partial"}:
            return existing

        if existing and (force_new_generation or not same_index_key):
            existing.active_index = False
            existing.status = "stale" if not existing.deleted_at else existing.status
            existing.stale_reason = stale_reason or existing.stale_reason or "superseded_by_new_index"
            existing.updated_at = now
            self._history.setdefault(descriptor.report_id, []).append(existing)
            doc_id = self._next_document_id
            self._next_document_id += 1
            generation = existing.index_generation + 1
            supersedes = existing.id
            created_at = now
        elif existing:
            doc_id = existing.id
            generation = existing.index_generation
            supersedes = existing.supersedes_rag_document_id
            created_at = existing.created_at
        else:
            doc_id = self._next_document_id
            self._next_document_id += 1
            generation = 1
            supersedes = None
            created_at = now

        chunks: list[ReportRagChunkRecord] = []
        for draft in chunk_drafts:
            chunks.append(
                ReportRagChunkRecord(
                    id=self._next_chunk_id,
                    rag_document_id=doc_id,
                    report_id=descriptor.report_id,
                    chunk_index=draft.chunk_index,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    section_title=draft.section_title,
                    text=draft.text,
                    text_hash=draft.text_hash,
                    token_count=draft.token_count,
                    embedding=embeddings_by_hash.get(draft.text_hash),
                    metadata_json=draft.metadata_json,
                    created_at=now,
                )
            )
            self._next_chunk_id += 1

        document = ReportRagDocumentRecord(
            id=doc_id,
            report_id=descriptor.report_id,
            market=descriptor.market.upper(),
            symbol=descriptor.symbol,
            company_name=descriptor.company_name,
            report_year=descriptor.report_year,
            report_type=descriptor.report_type,
            announcement_date=descriptor.announcement_date,
            source_url=descriptor.source_url,
            pdf_hash=descriptor.pdf_hash,
            parse_version=descriptor.parse_version,
            page_count=page_count,
            chunk_count=len(chunks),
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            status=status,
            created_at=created_at,
            updated_at=now,
            active_index=True,
            supersedes_rag_document_id=supersedes,
            indexed_at=now if status in {"indexed", "partial"} else None,
            deleted_at=None,
            index_generation=generation,
            report_title=descriptor.report_title,
            stale_reason=stale_reason,
            last_error=last_error,
            chunks=chunks,
        )
        self._documents[descriptor.report_id] = document
        return document

    def to_jsonable(self, report_id: int) -> dict[str, Any] | None:
        doc = self.get_document(report_id)
        if not doc:
            return None
        payload = asdict(doc)
        for chunk in payload["chunks"]:
            chunk["text_excerpt"] = chunk.pop("text")[:800]
            chunk["embedding"] = None if chunk.get("embedding") is None else f"{len(doc.chunks[0].embedding or [])}d"
        return payload


# Phase 6T-J1: repository backend resolved via factory
# (COMPANY_V2_RAG_REPOSITORY_BACKEND, production default: database).
from app.services.company_v2_report_rag_repository_factory import (  # noqa: E402
    get_company_v2_report_rag_repository,
)

company_v2_report_rag_repository = get_company_v2_report_rag_repository()


class CompanyV2ReportRagIndexService:
    def __init__(self, repository: CompanyV2ReportRagRepository | None = None) -> None:
        self.repository = repository or company_v2_report_rag_repository

    def status(self, report_id: int) -> dict[str, Any]:
        backend_info = {
            "repository_backend": getattr(self.repository, "backend", "memory"),
            "persistent": bool(getattr(self.repository, "persistent", False)),
        }
        metadata_getter = getattr(self.repository, "get_any_document_metadata", None)
        doc = metadata_getter(report_id) if metadata_getter else self.repository.get_any_document(report_id)
        if not doc:
            return {
                **backend_info,
                "status": "pending",
                "report_id": report_id,
                "chunk_count": 0,
                "indexed_at": None,
                "embedding_model": None,
                "parse_version": None,
                "stale_reason": None,
                "last_error": None,
            }
        return {
            **backend_info,
            "status": doc.status,
            "report_id": doc.report_id,
            "chunk_count": doc.chunk_count,
            "indexed_at": doc.indexed_at,
            "embedding_model": doc.embedding_model,
            "embedding_version": doc.embedding_version,
            "parse_version": doc.parse_version,
            "stale_reason": doc.stale_reason,
            "last_error": doc.last_error,
            "active_index": doc.active_index,
            "deleted_at": doc.deleted_at,
            "index_generation": doc.index_generation,
        }

    def index_report(self, descriptor: ReportDescriptor, sidecar_path: str | Path, *, force_new_generation: bool = False) -> dict[str, Any]:
        valid_url, reason = validate_cninfo_pdf_url(descriptor.source_url)
        if not valid_url:
            return self._failed(descriptor, "INVALID_SOURCE_URL", reason)

        sidecar = Path(sidecar_path)
        if not sidecar.exists():
            return self._failed(descriptor, "PDF_NOT_PARSED", "page sidecar unavailable")

        try:
            pages, parsed = load_pages_from_sidecar(sidecar)
        except Exception as exc:
            return self._failed(descriptor, "PARSE_SIDECAR_INVALID", str(exc)[:300])

        parse_status = parsed.get("parse_status")
        warnings = list(parsed.get("warnings") or [])
        if parse_status not in {"parsed", "partial"}:
            return self._failed(descriptor, "PDF_NOT_PARSED", f"parse_status={parse_status!r}")

        metadata = {
            "symbol": descriptor.symbol,
            "report_year": descriptor.report_year,
            "report_type": descriptor.report_type,
            "source_url": descriptor.source_url,
            "parse_version": descriptor.parse_version,
        }
        chunks = chunk_report_pages(report_id=descriptor.report_id, pages=pages, metadata=metadata)
        if not chunks:
            return self._failed(descriptor, "NO_CHUNKS", "parsed report produced no chunks")

        existing = self.repository.get_document(descriptor.report_id)
        existing_hashes = {chunk.text_hash for chunk in existing.chunks} if existing else set()
        embedded, skipped = company_v2_report_embedding_service.embed_batch(
            [chunk.text for chunk in chunks],
            existing_hashes=existing_hashes,
        )
        embeddings_by_hash = {item.text_hash: item.embedding for item in embedded}
        if existing:
            embeddings_by_hash.update({chunk.text_hash: chunk.embedding for chunk in existing.chunks if chunk.embedding})

        missing_embeddings = sum(1 for chunk in chunks if chunk.text_hash not in embeddings_by_hash)
        status = "indexed" if missing_embeddings == 0 else "partial"
        if LOW_COVERAGE_CODE in warnings and status == "indexed":
            status = "partial"

        doc = self.repository.upsert_index(
            descriptor,
            page_count=int(parsed.get("page_count") or len(pages)),
            chunk_drafts=chunks,
            embeddings_by_hash=embeddings_by_hash,
            status=status,
            last_error=None if status == "indexed" else ";".join(warnings) or None,
            force_new_generation=force_new_generation,
        )
        return {
            "ok": status in {"indexed", "partial"},
            "status": doc.status,
            "rag_document_id": doc.id,
            "report_id": doc.report_id,
            "market": doc.market,
            "symbol": doc.symbol,
            "report_title": doc.report_title,
            "report_year": doc.report_year,
            "report_type": doc.report_type,
            "page_count": doc.page_count,
            "chunk_count": doc.chunk_count,
            "embedding_model": doc.embedding_model,
            "embedding_version": doc.embedding_version,
            "active_index": doc.active_index,
            "supersedes_rag_document_id": doc.supersedes_rag_document_id,
            "indexed_at": doc.indexed_at,
            "index_generation": doc.index_generation,
            "embedded_chunks": len(embedded),
            "embedding_cache_hits": skipped,
            "warnings": warnings,
        }

    def export_index_artifact(self, report_id: int, path: str | Path) -> dict[str, Any]:
        payload = self.repository.to_jsonable(report_id)
        if payload is None:
            raise ValueError(f"report_id={report_id} is not indexed")
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _failed(self, descriptor: ReportDescriptor, error_code: str, reason: str) -> dict[str, Any]:
        existing = self.repository.get_document(descriptor.report_id)
        if existing and existing.status in {"indexed", "partial", "stale"}:
            existing.last_error = f"{error_code}: {reason}"
            existing.updated_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
            return {
                "ok": False,
                "status": "failed",
                "report_id": descriptor.report_id,
                "error_code": error_code,
                "message": reason,
                "active_index_preserved": True,
                "active_rag_document_id": existing.id,
            }
        now_descriptor = descriptor
        self.repository.upsert_index(
            now_descriptor,
            page_count=0,
            chunk_drafts=[],
            embeddings_by_hash={},
            status="failed",
            last_error=f"{error_code}: {reason}",
        )
        return {
            "ok": False,
            "status": "failed",
            "report_id": descriptor.report_id,
            "error_code": error_code,
            "message": reason,
        }


company_v2_report_rag_index_service = CompanyV2ReportRagIndexService()
