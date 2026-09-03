from __future__ import annotations

import json


def _descriptor(report_id=1, symbol="601686"):
    from app.services.company_v2_report_rag_index_service import ReportDescriptor

    return ReportDescriptor(
        report_id=report_id,
        market="CN",
        symbol=symbol,
        company_name="友发集团",
        report_year=2024,
        report_type="annual",
        announcement_date="2025-04-25",
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        pdf_hash="abc",
    )


def _sidecar(tmp_path, text=None):
    text = text or (
        "第二节 公司简介和主要财务指标\n单位：元\n营业收入 600 亿元\n归属于上市公司股东的净利润 5 亿元\n"
        + "公司主营业务为焊接钢管研发、生产和销售，产品用于建筑、机械制造、能源等领域。\n" * 12
    )
    path = tmp_path / "report.pages.json"
    path.write_text(json.dumps({"page_count": 1, "parse_status": "parsed", "warnings": [], "text_pages": [{"page": 12, "text": text}]}, ensure_ascii=False), encoding="utf-8")
    return path


def test_index_report_is_idempotent_by_text_hash(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagIndexService, CompanyV2ReportRagRepository

    repo = CompanyV2ReportRagRepository()
    service = CompanyV2ReportRagIndexService(repo)
    first = service.index_report(_descriptor(), _sidecar(tmp_path))
    second = service.index_report(_descriptor(), _sidecar(tmp_path))

    assert first["status"] == "indexed"
    assert second["status"] == "indexed"
    assert second["chunk_count"] == first["chunk_count"]
    assert second["embedding_cache_hits"] == first["chunk_count"]
    doc = repo.get_document(1)
    assert doc is not None
    assert doc.chunks[0].page_start == 12


def test_index_rejects_unparsed_pdf(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagIndexService, CompanyV2ReportRagRepository

    sidecar = tmp_path / "bad.pages.json"
    sidecar.write_text(json.dumps({"page_count": 1, "parse_status": "failed", "text_pages": []}), encoding="utf-8")
    result = CompanyV2ReportRagIndexService(CompanyV2ReportRagRepository()).index_report(_descriptor(), sidecar)

    assert result["ok"] is False
    assert result["error_code"] == "PDF_NOT_PARSED"


def test_index_rejects_non_cninfo_url(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagIndexService, CompanyV2ReportRagRepository, ReportDescriptor

    descriptor = ReportDescriptor(1, "CN", "601686", "友发", 2024, "annual", None, "https://example.com/a.PDF", "hash")
    result = CompanyV2ReportRagIndexService(CompanyV2ReportRagRepository()).index_report(descriptor, _sidecar(tmp_path))

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_SOURCE_URL"


def test_status_and_export_do_not_expose_local_path(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagIndexService, CompanyV2ReportRagRepository

    repo = CompanyV2ReportRagRepository()
    service = CompanyV2ReportRagIndexService(repo)
    service.index_report(_descriptor(), _sidecar(tmp_path))
    out = tmp_path / "index.json"
    payload = service.export_index_artifact(1, out)

    assert service.status(1)["status"] == "indexed"
    assert out.exists()
    assert "local_path" not in json.dumps(payload, ensure_ascii=False)
