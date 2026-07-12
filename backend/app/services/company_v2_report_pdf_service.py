"""CompanyV2 CNINFO PDF download service.

Strict wrapper around report PDF storage:
- accepts only HTTPS CNINFO PDF URLs
- blocks localhost/internal/file URLs
- stores local path internally but never returns it to API callers
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument

ALLOWED_PDF_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn"}
DEFAULT_MAX_BYTES = 80 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
DOWNLOAD_DIR = Path(os.environ.get("COMPANY_V2_REPORT_PDF_DIR", "/tmp/company_v2_report_pdfs"))


def validate_cninfo_pdf_url(url: str) -> tuple[bool, str]:
    if not url:
        return False, "empty URL"
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False, "only https is allowed"
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_PDF_HOSTS:
        return False, f"host {host!r} not allowed"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, "internal IP blocked"
    except ValueError:
        pass
    if host in {"localhost"} or host.endswith(".localhost"):
        return False, "localhost blocked"
    if not (parsed.path or "").upper().endswith(".PDF"):
        return False, "URL must point to a PDF"
    return True, "ok"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_download_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in {"local_path", "path"}}


def _page_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


class CompanyV2ReportPdfService:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir or DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def download_report(
        self,
        report_id: int,
        db: AsyncSession,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return {"ok": False, "status": "download_failed", "report_id": report_id, "error_code": "REPORT_NOT_FOUND"}

        valid, reason = validate_cninfo_pdf_url(doc.pdf_url or "")
        if not valid:
            doc.download_status = "download_failed"
            doc.download_error = reason
            await db.commit()
            return {"ok": False, "status": "download_failed", "report_id": report_id, "error_code": "INVALID_PDF_URL", "reason": reason}

        if doc.download_status in {"downloaded", "parsed", "verified"} and doc.local_path and Path(doc.local_path).exists():
            return _safe_download_response({
                "ok": True,
                "status": doc.download_status,
                "report_id": report_id,
                "file_hash": doc.file_sha256,
                "file_size": doc.file_size,
                "page_count": _page_count(Path(doc.local_path)),
            })

        doc.download_status = "downloading"
        await db.commit()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(doc.pdf_url, headers={"User-Agent": "TradingAgentsResearch/1.0"})
                response.raise_for_status()
            content = response.content
            if len(content) > max_bytes:
                raise ValueError(f"PDF exceeds {max_bytes} bytes")
            if not content.startswith(b"%PDF"):
                content_type = (response.headers.get("content-type") or "").lower()
                if "pdf" not in content_type:
                    raise ValueError(f"unexpected content type: {content_type or 'unknown'}")

            file_hash = _sha256(content)
            file_path = self.download_dir / f"company_v2_report_{report_id}_{file_hash[:16]}.pdf"
            file_path.write_bytes(content)
            page_count = _page_count(file_path)

            doc.local_path = str(file_path)
            doc.file_sha256 = file_hash
            doc.file_size = len(content)
            doc.download_status = "downloaded"
            doc.parse_status = doc.parse_status or "parse_pending"
            doc.download_error = None
            await db.commit()
            return {
                "ok": True,
                "status": "downloaded",
                "report_id": report_id,
                "file_hash": file_hash,
                "file_size": len(content),
                "page_count": page_count,
            }
        except Exception as exc:
            doc.download_status = "download_failed"
            doc.download_error = str(exc)[:500]
            await db.commit()
            return {"ok": False, "status": "download_failed", "report_id": report_id, "error_code": "PDF_DOWNLOAD_FAILED", "reason": str(exc)[:300]}


company_v2_report_pdf_service = CompanyV2ReportPdfService()
