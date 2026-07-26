"""Lightweight in-process index queue for Company V2 report RAG."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import asyncio
import datetime as dt
import uuid
from typing import Any, Callable


@dataclass(slots=True)
class ReportRagIndexJob:
    job_id: str
    report_id: int
    operation: str
    status: str
    pages_processed: int = 0
    chunks_created: int = 0
    chunks_embedded: int = 0
    total_pages: int = 0
    percent: int = 0
    result: dict[str, Any] | None = None
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompanyV2ReportRagIndexQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, ReportRagIndexJob] = {}
        self._active_by_report: dict[int, str] = {}

    def clear(self) -> None:
        self._jobs.clear()
        self._active_by_report.clear()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def get_active_job_for_report(self, report_id: int) -> dict[str, Any] | None:
        job_id = self._active_by_report.get(int(report_id))
        return self.get_job(job_id) if job_id else None

    def submit(
        self,
        *,
        report_id: int,
        operation: str,
        work: Callable[[], dict[str, Any]],
        run_background: bool = True,
    ) -> dict[str, Any]:
        existing = self.get_active_job_for_report(report_id)
        if existing and existing["status"] in {"queued", "running"}:
            return {**existing, "duplicate": True}

        now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        job = ReportRagIndexJob(
            job_id=str(uuid.uuid4()),
            report_id=int(report_id),
            operation=operation,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        self._active_by_report[int(report_id)] = job.job_id

        if run_background:
            try:
                asyncio.get_running_loop().create_task(self._run_job(job.job_id, work))
            except RuntimeError:
                self._run_job_sync(job.job_id, work)
        else:
            self._run_job_sync(job.job_id, work)
        return job.to_dict()

    async def _run_job(self, job_id: str, work: Callable[[], dict[str, Any]]) -> None:
        await asyncio.to_thread(self._run_job_sync, job_id, work)

    def _run_job_sync(self, job_id: str, work: Callable[[], dict[str, Any]]) -> None:
        job = self._jobs[job_id]
        self._update(job, status="running", percent=5)
        try:
            result = work()
            total_pages = int(result.get("page_count") or 0)
            chunk_count = int(result.get("chunk_count") or 0)
            embedded = int(result.get("embedded_chunks") or chunk_count or 0)
            status = "succeeded" if result.get("ok") else "failed"
            self._update(
                job,
                status=status,
                pages_processed=total_pages,
                total_pages=total_pages,
                chunks_created=chunk_count,
                chunks_embedded=embedded,
                percent=100 if status == "succeeded" else 0,
                result=result,
                last_error=result.get("message") if not result.get("ok") else None,
            )
        except Exception as exc:
            self._update(job, status="failed", percent=0, last_error=str(exc)[:500])
        finally:
            current = self._active_by_report.get(job.report_id)
            if current == job.job_id:
                self._active_by_report.pop(job.report_id, None)

    @staticmethod
    def _update(job: ReportRagIndexJob, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


company_v2_report_rag_index_queue = CompanyV2ReportRagIndexQueue()
