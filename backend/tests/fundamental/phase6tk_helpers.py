from __future__ import annotations

import json
from datetime import datetime


class FakeScalars:
    def __init__(self, item):
        self._item = item

    def first(self):
        return self._item


class FakeResult:
    def __init__(self, item):
        self._item = item

    def scalars(self):
        return FakeScalars(self._item)


class FakeDb:
    def __init__(self, item):
        self.item = item
        self.committed = False

    async def execute(self, _stmt):
        return FakeResult(self.item)

    async def commit(self):
        self.committed = True

    async def refresh(self, _row):
        return None


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def make_doc(tmp_path, *, symbol: str = "600519", report_id: int = 2):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / f"report_{report_id}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    pdf.with_suffix(".pages.json").write_text(
        json.dumps({"page_count": 1, "parse_status": "parsed", "warnings": [], "text_pages": [{"page": 1, "text": "单位：元 营业收入 1"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return ReportDocument(
        id=report_id,
        ts_code=f"{symbol}.SH" if not symbol.startswith("0") and not symbol.startswith("3") else f"{symbol}.SZ",
        report_type="annual",
        report_year=2025,
        title="annual",
        disclosure_date="2026-04-01",
        pdf_url="https://static.cninfo.com.cn/finalpage/2026-04-01/test.PDF",
        local_path=str(pdf),
        file_sha256="sha-test",
        parsed=True,
        parse_status="parsed",
        download_status="downloaded",
        created_at=datetime.utcnow(),
    )
