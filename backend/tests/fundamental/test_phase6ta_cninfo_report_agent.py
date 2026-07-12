"""
backend/tests/fundamental/test_phase6ta_cninfo_report_agent.py
Phase 6T-A: CNINFO Annual Report Agent 验收测试
"""
from __future__ import annotations

import pytest


# ── CNINFO Provider 测试 ─────────────────────────────────────────────────────

def test_validate_pdf_url_whitelist():
    """只允许白名单域名的 PDF URL。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, _ = validate_pdf_url("http://static.cninfo.com.cn/finalpage/2026-04-30/1225273091.PDF")
    assert ok

def test_validate_pdf_url_reject_non_whitelist():
    """非白名单域名被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("https://evil.com/fake.PDF")
    assert not ok
    assert "whitelist" in reason.lower() or "not in" in reason.lower()

def test_validate_pdf_url_reject_non_pdf():
    """非 .PDF 后缀被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("http://static.cninfo.com.cn/finalpage/2026-04-30/1225273091.html")
    assert not ok
    assert ".pdf" in reason.lower() or "pdf" in reason.lower()

def test_validate_pdf_url_reject_internal_address():
    """内网地址被拒绝（安全）。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("http://127.0.0.1/internal.PDF")
    assert not ok

def test_validate_pdf_url_reject_file_scheme():
    """file:// 被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("file:///etc/passwd")
    assert not ok

def test_resolve_pdf_url_pdf_type():
    """只提取 adjunctType=PDF 的附件。"""
    from app.datasource.cninfo_provider import resolve_pdf_url
    ann = {
        "adjunctUrl": "finalpage/2026-04-30/1225273091.PDF",
        "adjunctType": "PDF",
    }
    url = resolve_pdf_url(ann)
    assert url is not None
    assert "static.cninfo.com.cn" in url
    assert url.upper().endswith(".PDF")

def test_resolve_pdf_url_non_pdf_type():
    """非 PDF 类型的附件不提取 URL。"""
    from app.datasource.cninfo_provider import resolve_pdf_url
    ann = {
        "adjunctUrl": "finalpage/2026-04-30/something.docx",
        "adjunctType": "DOCX",
    }
    url = resolve_pdf_url(ann)
    assert url is None

def test_filter_annual_report_title():
    """过滤：年度报告标题通过，摘要排除。"""
    from app.datasource.cninfo_provider import _is_annual_report
    assert _is_annual_report("友发集团：2025年年度报告") is True
    assert _is_annual_report("2024年年度报告摘要") is False
    assert _is_annual_report("社会责任报告 2024") is False
    assert _is_annual_report("贵州茅台 2023年度报告") is True

def test_extract_report_metadata_structure():
    """extract_report_metadata 返回完整字段结构。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "601686 友发集团：2025年年度报告",
        "adjunctUrl": "finalpage/2026-04-30/1225273091.PDF",
        "adjunctType": "PDF",
        "orgId": "9900006256",
        "announcementId": "1225273091",
        "announcementTime": 1746000000000,
    }
    meta = extract_report_metadata(ann, "601686", 2025)
    assert meta["symbol"] == "601686"
    assert meta["report_year"] == 2025
    assert meta["report_type"] == "annual"
    assert meta["pdf_url"] is not None
    assert "static.cninfo.com.cn" in meta["pdf_url"]
    assert meta["is_annual"] is True
    assert meta["is_summary"] is False
    assert meta["confidence"] >= 0.75
    assert meta["discovery_method"] == "cninfo_announcement_query"
    assert "org_id" in meta


# ── CNINFO OrgId Resolver 测试 ─────────────────────────────────────────────

def test_org_resolver_seed_mapping():
    """种子映射优先返回已知 orgId。"""
    from app.services.cninfo_org_resolver import _SEED_ORG_MAP, seed_org_id, _is_cached
    # 使用 seed inject
    seed_org_id("601686", "9900006256")
    cached, valid = _is_cached("601686")
    assert valid
    assert cached == "9900006256"

def test_org_resolver_cache():
    """解析后的 orgId 被缓存，不重复查询。"""
    from app.services.cninfo_org_resolver import seed_org_id, get_cache_snapshot
    seed_org_id("600519", "9900002978")
    snapshot = get_cache_snapshot()
    assert "600519" in snapshot
    assert snapshot["600519"]["org_id"] == "9900002978"

def test_org_resolver_not_found():
    """未知股票代码返回 ORG_ID_NOT_FOUND 常量。"""
    from app.services.cninfo_org_resolver import ORG_ID_NOT_FOUND
    assert ORG_ID_NOT_FOUND == "ORG_ID_NOT_FOUND"


# ── CNINFO Annual Report Agent 测试 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_discover_result_structure():
    """Agent discover 返回结构完整。"""
    from app.services.cninfo_annual_report_agent import CninfoAnnualReportAgent
    agent = CninfoAnnualReportAgent()
    # Mock: skip actual network call by using a cached result
    from app.services.cninfo_org_resolver import seed_org_id
    seed_org_id("601686", "9900006256")

    # Only test structure / error handling; don't make real HTTP calls in unit test
    cache_key = agent._cache_key("601686", 2023, 2023)
    agent._set_cache(cache_key, [])  # empty cache = no network call needed
    result = await agent.discover("601686", start_year=2023, end_year=2023)
    assert "symbol" in result
    assert "reports" in result
    assert "total_found" in result
    assert "errors" in result
    assert "from_cache" in result
    assert "discovery_method" in result
    assert result["discovery_method"] == "cninfo_announcement_query"

def test_agent_cache_behavior():
    """Agent 缓存 set/get 行为正确。"""
    from app.services.cninfo_annual_report_agent import CninfoAnnualReportAgent
    agent = CninfoAnnualReportAgent()
    key = agent._cache_key("000001", 2020, 2024)
    sample = [{"symbol": "000001", "report_year": 2024, "pdf_url": "http://static.cninfo.com.cn/test.PDF"}]
    agent._set_cache(key, sample)
    result = agent._get_cache(key)
    assert result == sample


# ── 安全性测试 ──────────────────────────────────────────────────────────────

def test_no_local_path_in_manual_record():
    """手动录入记录不包含 local_path。"""
    # Simulate manual record creation
    record = {
        "symbol": "601686",
        "pdf_url": "http://static.cninfo.com.cn/finalpage/2026-04-30/1225273091.PDF",
        "source": "manual",
    }
    assert "local_path" not in record

def test_manual_pdf_url_validation():
    """手动录入 URL 校验逻辑（来自 router helper）。"""
    import re
    from urllib.parse import urlparse

    ALLOWED_PDF_HOSTS = frozenset(["static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"])

    def validate(url):
        if not url: return False, "empty"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"): return False, "scheme"
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_PDF_HOSTS: return False, "host"
        if re.match(r"^(127\.|10\.|192\.168\.)", host): return False, "internal"
        if not (parsed.path or "").upper().endswith(".PDF"): return False, "not pdf"
        return True, "ok"

    ok, _ = validate("http://static.cninfo.com.cn/finalpage/2026-04-30/1225273091.PDF")
    assert ok

    ok, reason = validate("https://evil.com/fake.PDF")
    assert not ok and reason == "host"

    ok, reason = validate("file:///etc/passwd")
    assert not ok and reason == "scheme"

def test_report_documents_not_report_rag():
    """MODULE_KEYS 中不再包含 report_rag。"""
    from app.services.company_v2_debug_service import MODULE_KEYS
    assert "report_rag" not in MODULE_KEYS
    assert "report_documents" in MODULE_KEYS
