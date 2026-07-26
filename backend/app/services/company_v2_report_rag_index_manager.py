"""Index management for Company V2 multi-report RAG."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
from app.services.company_v2_report_rag_index_service import (
    ReportDescriptor,
    company_v2_report_rag_index_service,
    company_v2_report_rag_repository,
)


class CompanyV2ReportRagIndexManager:
    def __init__(self) -> None:
        self.repository = company_v2_report_rag_repository
        self.index_service = company_v2_report_rag_index_service
        self.queue = company_v2_report_rag_index_queue

    def list_indexes(self, symbol: str) -> list[dict[str, Any]]:
        rows = []
        for doc in self.repository.list_documents(symbol):
            rows.append(
                {
                    "rag_document_id": doc.id,
                    "report_id": doc.report_id,
                    "report_year": doc.report_year,
                    "report_type": doc.report_type,
                    "report_title": doc.report_title,
                    "status": doc.status,
                    "stale": doc.status == "stale",
                    "stale_reason": doc.stale_reason,
                    "chunk_count": doc.chunk_count,
                    "indexed_at": doc.indexed_at,
                    "embedding_version": doc.embedding_version,
                    "active_index": doc.active_index,
                    "index_generation": doc.index_generation,
                    "deleted_at": doc.deleted_at,
                }
            )
        return rows

    def get_index(self, report_id: int) -> dict[str, Any]:
        status = self.index_service.status(report_id)
        history = [
            {
                "rag_document_id": doc.id,
                "status": doc.status,
                "active_index": doc.active_index,
                "embedding_version": doc.embedding_version,
                "index_generation": doc.index_generation,
                "supersedes_rag_document_id": doc.supersedes_rag_document_id,
                "deleted_at": doc.deleted_at,
            }
            for doc in self.repository.list_history(report_id)
        ]
        return {**status, "history": history}

    def create_index(self, descriptor: ReportDescriptor, sidecar_path: str | Path) -> dict[str, Any]:
        return self.index_service.index_report(descriptor, sidecar_path)

    def refresh_index(self, descriptor: ReportDescriptor, sidecar_path: str | Path) -> dict[str, Any]:
        return self.index_service.index_report(descriptor, sidecar_path, force_new_generation=True)

    def delete_index(self, report_id: int) -> dict[str, Any]:
        doc = self.repository.soft_delete(report_id)
        if not doc:
            return {"ok": False, "status": "failed", "report_id": report_id, "error_code": "REPORT_NOT_INDEXED"}
        return {
            "ok": True,
            "status": "deleted",
            "report_id": doc.report_id,
            "rag_document_id": doc.id,
            "deleted_at": doc.deleted_at,
            "pdf_deleted": False,
            "sidecar_deleted": False,
        }

    def mark_stale(self, report_id: int, reason: str) -> dict[str, Any]:
        doc = self.repository.mark_stale(report_id, reason)
        if not doc:
            return {"ok": False, "status": "failed", "report_id": report_id, "error_code": "REPORT_NOT_INDEXED"}
        return {"ok": True, "status": "stale", "report_id": report_id, "stale_reason": reason}

    def rebuild_stale_index(self, descriptor: ReportDescriptor, sidecar_path: str | Path) -> dict[str, Any]:
        doc = self.repository.get_any_document(descriptor.report_id)
        if doc and doc.status != "stale":
            return {"ok": False, "status": doc.status, "report_id": descriptor.report_id, "error_code": "INDEX_NOT_STALE"}
        return self.refresh_index(descriptor, sidecar_path)

    def get_index_progress(self, report_id: int, job_id: str | None = None) -> dict[str, Any]:
        if job_id:
            job = self.queue.get_job(job_id)
            return job or {"status": "failed", "error_code": "JOB_NOT_FOUND", "report_id": report_id}
        return self.queue.get_active_job_for_report(report_id) or {"status": "idle", "report_id": report_id}

    def enqueue_create_index(self, descriptor: ReportDescriptor, sidecar_path: str | Path) -> dict[str, Any]:
        return self.queue.submit(
            report_id=descriptor.report_id,
            operation="index",
            work=lambda: self.create_index(descriptor, sidecar_path),
            run_background=True,
        )

    def enqueue_refresh_index(self, descriptor: ReportDescriptor, sidecar_path: str | Path) -> dict[str, Any]:
        return self.queue.submit(
            report_id=descriptor.report_id,
            operation="refresh",
            work=lambda: self.refresh_index(descriptor, sidecar_path),
            run_background=True,
        )


company_v2_report_rag_index_manager = CompanyV2ReportRagIndexManager()
