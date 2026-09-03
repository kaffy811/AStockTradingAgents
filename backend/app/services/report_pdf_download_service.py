"""
app/services/report_pdf_download_service.py — PDF 下载与缓存服务（Phase 6E）

安全约束：
- 只下载已知域名的 PDF（同 report_discovery.py 白名单）
- 文件大小上限 50MB
- 只接受 Content-Type: application/pdf 或 application/octet-stream
- SHA-256 校验防重复
- 下载失败写 download_error，不抛出异常
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument

log = logging.getLogger(__name__)

_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
_TIMEOUT = 30.0  # seconds
_DOWNLOAD_DIR = Path(os.environ.get("REPORT_PDF_DIR", "/tmp/report_pdfs"))

_ALLOWED_DOMAINS = [
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "cninfo.com.cn",
    "disc.szse.cn",
    "www.szse.cn",
    "szse.cn",
    "www.sse.com.cn",
    "sse.com.cn",
    "query.sse.com.cn",
]

_ALLOWED_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}


def _is_trusted_domain(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(domain == d or domain.endswith("." + d) for d in _ALLOWED_DOMAINS)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReportPdfDownloadService:
    """Download and cache annual report PDFs."""

    def __init__(self, download_dir: Path | None = None) -> None:
        self._dir = download_dir or _DOWNLOAD_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    async def download(
        self,
        report_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Download the PDF for a report_document entry.

        Returns:
            {"status": "downloaded"|"exists"|"failed", "report_id": int, "reason": str}
        """
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        doc: ReportDocument | None = result.scalars().first()

        if not doc:
            return {"status": "failed", "report_id": report_id, "reason": "report_id not found"}

        pdf_url = doc.pdf_url or ""
        if not pdf_url:
            return {"status": "failed", "report_id": report_id, "reason": "no pdf_url on record"}

        if not _is_trusted_domain(pdf_url):
            return {"status": "failed", "report_id": report_id, "reason": f"untrusted domain: {urlparse(pdf_url).netloc}"}

        # If already downloaded and file exists, skip
        if doc.download_status == "downloaded" and doc.local_path:
            local = Path(doc.local_path)
            if local.exists():
                return {"status": "exists", "report_id": report_id, "reason": "already downloaded", "local_path": str(local)}

        # Download
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(pdf_url, headers={"User-Agent": "TradingAgents-ResearchBot/1.0"})
                response.raise_for_status()

            # Content-Type check (lenient: headers may be missing)
            ct = response.headers.get("content-type", "").lower().split(";")[0].strip()
            if ct and ct not in _ALLOWED_CONTENT_TYPES and "pdf" not in ct:
                err = f"unexpected Content-Type: {ct}"
                await self._mark_failed(doc, err, db)
                return {"status": "failed", "report_id": report_id, "reason": err}

            content = response.content

            # Size check
            if len(content) > _MAX_SIZE_BYTES:
                err = f"file too large: {len(content)} bytes (limit {_MAX_SIZE_BYTES})"
                await self._mark_failed(doc, err, db)
                return {"status": "failed", "report_id": report_id, "reason": err}

            sha = _sha256(content)

            # Check for duplicate by sha256 (another doc may have same file)
            if doc.file_sha256 and doc.file_sha256 == sha and doc.local_path:
                return {"status": "exists", "report_id": report_id, "reason": "sha256 match, already have file"}

            # Save to disk
            filename = f"report_{report_id}_{sha[:16]}.pdf"
            local_path = self._dir / filename
            local_path.write_bytes(content)

            # Update DB
            doc.download_status = "downloaded"
            doc.local_path = str(local_path)
            doc.file_sha256 = sha
            doc.file_size = len(content)
            doc.download_error = None
            await db.commit()

            log.info("Downloaded report_id=%d → %s (%d bytes)", report_id, local_path, len(content))
            return {
                "status": "downloaded",
                "report_id": report_id,
                "local_path": str(local_path),
                "file_size": len(content),
                "sha256": sha,
                "reason": "ok",
            }

        except Exception as e:
            err = str(e)[:500]
            log.warning("PDF download failed report_id=%d: %s", report_id, err)
            await self._mark_failed(doc, err, db)
            return {"status": "failed", "report_id": report_id, "reason": err}

    async def _mark_failed(self, doc: ReportDocument, error: str, db: AsyncSession) -> None:
        doc.download_status = "failed"
        doc.download_error = error[:500]
        try:
            await db.commit()
        except Exception:
            await db.rollback()


report_pdf_download_service = ReportPdfDownloadService()
