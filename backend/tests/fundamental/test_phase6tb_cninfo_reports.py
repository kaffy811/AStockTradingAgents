"""
backend/tests/fundamental/test_phase6tb_cninfo_reports.py
Phase 6T-B: CNINFO Reports（含季报）验收测试
"""
from __future__ import annotations

import pytest


# ── 报告类型识别测试 ─────────────────────────────────────────────────────────

def test_classify_report_type_annual():
    """年度报告正确识别。"""
    from app.datasource.cninfo_provider import classify_report_type
    assert classify_report_type("友发集团：2025年年度报告") == "annual"
    assert classify_report_type("贵州茅台：2024年度报告") == "annual"
    assert classify_report_type("ANNUAL REPORT 2024") == "annual"


def test_classify_report_type_semi_annual():
    """半年度报告正确识别。"""
    from app.datasource.cninfo_provider import classify_report_type
    assert classify_report_type("某公司2024年半年度报告") == "semi_annual"
    assert classify_report_type("2024年中期报告") == "semi_annual"


def test_classify_report_type_q1():
    """第一季度报告正确识别。"""
    from app.datasource.cninfo_provider import classify_report_type
    assert classify_report_type("某公司2024年第一季度报告") == "q1"
    assert classify_report_type("某公司2024年一季报") == "q1"


def test_classify_report_type_q3():
    """第三季度报告正确识别。"""
    from app.datasource.cninfo_provider import classify_report_type
    assert classify_report_type("某公司2024年第三季度报告") == "q3"
    assert classify_report_type("2024年三季报") == "q3"


def test_classify_report_type_exclude_summary():
    """摘要版本不识别为正式报告。"""
    from app.datasource.cninfo_provider import classify_report_type
    result = classify_report_type("2024年年度报告摘要")
    assert result is None


def test_classify_report_type_exclude_social_responsibility():
    """社会责任报告不识别为财报。"""
    from app.datasource.cninfo_provider import classify_report_type
    result = classify_report_type("2024年社会责任报告")
    assert result is None


def test_classify_report_type_exclude_bond():
    """债券报告被全局排除。"""
    from app.datasource.cninfo_provider import classify_report_type
    result = classify_report_type("2024年债券年度报告")
    assert result is None


def test_is_report_of_type_annual():
    """_is_report_of_type 检查标题是否匹配指定类型。"""
    from app.datasource.cninfo_provider import _is_report_of_type
    assert _is_report_of_type("2024年年度报告", "annual") is True
    assert _is_report_of_type("2024年半年度报告", "annual") is False
    assert _is_report_of_type("2024年第一季度报告", "annual") is False


def test_is_report_of_type_quarterly():
    """_is_report_of_type 正确识别季报类型。"""
    from app.datasource.cninfo_provider import _is_report_of_type
    assert _is_report_of_type("2024年第三季度报告", "q3") is True
    assert _is_report_of_type("2024年第三季度报告", "q1") is False
    assert _is_report_of_type("2024年三季报", "q3") is True


# ── extract_report_metadata 测试 ────────────────────────────────────────────

def test_extract_report_metadata_annual():
    """extract_report_metadata 正确处理年报。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "601686 友发集团：2025年年度报告",
        "adjunctUrl": "finalpage/2026-04-30/1225273091.PDF",
        "adjunctType": "PDF",
        "orgId": "9900006256",
        "announcementId": "1225273091",
        "announcementTime": 1746000000000,
    }
    meta = extract_report_metadata(ann, "601686", 2025, "annual")
    assert meta["report_type"] == "annual"
    assert meta["is_annual"] is True
    assert meta["is_summary"] is False
    assert meta["pdf_url"] is not None
    assert "static.cninfo.com.cn" in meta["pdf_url"]
    assert meta["adjunct_url"] == "finalpage/2026-04-30/1225273091.PDF"
    assert meta["confidence"] >= 0.9


def test_extract_report_metadata_semi_annual():
    """extract_report_metadata 正确处理半年报。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "某公司2024年半年度报告",
        "adjunctUrl": "finalpage/2024-08-30/abcdef.PDF",
        "adjunctType": "PDF",
        "orgId": "123456",
        "announcementId": "98765",
        "announcementTime": 1724000000000,
    }
    meta = extract_report_metadata(ann, "600001", 2024, "semi_annual")
    assert meta["report_type"] == "semi_annual"
    assert meta["is_summary"] is False
    assert meta["pdf_url"] is not None


def test_extract_report_metadata_no_pdf():
    """没有 PDF 附件时 pdf_url 为 None。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "2024年年度报告",
        "adjunctUrl": "",
        "adjunctType": "PDF",
        "orgId": "123456",
        "announcementId": "98765",
        "announcementTime": 1724000000000,
    }
    meta = extract_report_metadata(ann, "600001", 2024, "annual")
    assert meta["pdf_url"] is None
    assert meta["confidence"] < 0.5


def test_extract_report_metadata_is_correction():
    """更正版本标记 is_correction=True。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "2024年年度报告更正说明",
        "adjunctUrl": "finalpage/2025-05-01/updated.PDF",
        "adjunctType": "PDF",
        "orgId": "123456",
        "announcementId": "11111",
        "announcementTime": 1746000000000,
    }
    meta = extract_report_metadata(ann, "600001", 2024)
    assert meta["is_correction"] is True


def test_extract_report_metadata_is_summary():
    """摘要版本标记 is_summary=True。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "2024年年度报告摘要",
        "adjunctUrl": "finalpage/2025-05-01/summary.PDF",
        "adjunctType": "PDF",
        "orgId": "123456",
        "announcementId": "22222",
        "announcementTime": 1746000000000,
    }
    meta = extract_report_metadata(ann, "600001", 2024)
    assert meta["is_summary"] is True


# ── PDF URL 安全校验测试 ─────────────────────────────────────────────────────

def test_validate_pdf_url_whitelist_static():
    """static.cninfo.com.cn 域名允许。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, _ = validate_pdf_url("http://static.cninfo.com.cn/finalpage/2026-04-30/1225273091.PDF")
    assert ok is True


def test_validate_pdf_url_reject_non_whitelist():
    """非白名单域名被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("https://evil.com/fake.PDF")
    assert ok is False
    assert "whitelist" in reason.lower() or "not in" in reason.lower()


def test_validate_pdf_url_reject_non_pdf():
    """非 .PDF 后缀被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("http://static.cninfo.com.cn/finalpage/2026-04-30/doc.html")
    assert ok is False
    assert "pdf" in reason.lower()


def test_validate_pdf_url_reject_localhost():
    """localhost 被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("http://localhost/test.PDF")
    assert ok is False


def test_validate_pdf_url_reject_file_scheme():
    """file:// 被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("file:///etc/passwd")
    assert ok is False


def test_validate_pdf_url_reject_internal_ip():
    """内网 IP 被拒绝。"""
    from app.datasource.cninfo_provider import validate_pdf_url
    ok, reason = validate_pdf_url("http://192.168.1.1/report.PDF")
    assert ok is False


# ── adjunctUrl 到 PDF URL 转换测试 ──────────────────────────────────────────

def test_resolve_pdf_url_relative_path():
    """adjunctUrl 为相对路径时自动补全域名。"""
    from app.datasource.cninfo_provider import resolve_pdf_url
    ann = {
        "adjunctUrl": "finalpage/2026-04-30/1225273091.PDF",
        "adjunctType": "PDF",
    }
    url = resolve_pdf_url(ann)
    assert url is not None
    assert url.startswith("https://static.cninfo.com.cn/")
    assert url.upper().endswith(".PDF")


def test_resolve_pdf_url_reject_non_pdf_type():
    """adjunctType 非 PDF 时不提取 URL。"""
    from app.datasource.cninfo_provider import resolve_pdf_url
    ann = {
        "adjunctUrl": "finalpage/2026-04-30/doc.docx",
        "adjunctType": "DOCX",
    }
    url = resolve_pdf_url(ann)
    assert url is None


def test_resolve_pdf_url_empty_adjunct():
    """adjunctUrl 为空时返回 None。"""
    from app.datasource.cninfo_provider import resolve_pdf_url
    ann = {"adjunctUrl": "", "adjunctType": "PDF"}
    url = resolve_pdf_url(ann)
    assert url is None


# ── 报告时间线发现测试 ────────────────────────────────────────────────────────

def test_discover_reports_function_exists():
    """discover_reports 函数已导出。"""
    from app.datasource.cninfo_provider import discover_reports
    assert callable(discover_reports)


def test_category_map_has_all_types():
    """_CATEGORY_MAP 包含所有报告类型。"""
    from app.datasource.cninfo_provider import _CATEGORY_MAP
    assert "annual" in _CATEGORY_MAP
    assert "semi_annual" in _CATEGORY_MAP
    assert "q1" in _CATEGORY_MAP
    assert "q3" in _CATEGORY_MAP
    # 每个类型至少有1个 category
    for rtype, cats in _CATEGORY_MAP.items():
        assert len(cats) >= 1, f"{rtype} has no categories"


def test_report_type_config_has_all_types():
    """_REPORT_TYPE_CONFIG 配置了所有报告类型。"""
    from app.datasource.cninfo_provider import _REPORT_TYPE_CONFIG
    required = {"annual", "semi_annual", "q1", "q3"}
    assert required == set(_REPORT_TYPE_CONFIG.keys())
    for rtype, cfg in _REPORT_TYPE_CONFIG.items():
        assert "include_kws" in cfg, f"{rtype} missing include_kws"
        assert "exclude_kws" in cfg, f"{rtype} missing exclude_kws"
        assert "categories" in cfg, f"{rtype} missing categories"
        assert "display" in cfg, f"{rtype} missing display"


# ── report_rag 不独立展示测试 ────────────────────────────────────────────────

def test_report_rag_not_in_module_keys():
    """report_rag 不应该出现在 MODULE_KEYS 中。"""
    from app.services.company_v2_debug_service import MODULE_KEYS
    assert "report_rag" not in MODULE_KEYS


def test_report_rag_hidden_flag():
    """_REPORT_RAG_HIDDEN 标志为 True。"""
    from app.services.company_v2_debug_service import _REPORT_RAG_HIDDEN
    assert _REPORT_RAG_HIDDEN is True


# ── local_path 不泄露测试 ─────────────────────────────────────────────────────

def test_extract_report_metadata_no_local_path():
    """extract_report_metadata 返回的字段中不含 local_path。"""
    from app.datasource.cninfo_provider import extract_report_metadata
    ann = {
        "announcementTitle": "2025年年度报告",
        "adjunctUrl": "finalpage/2026-04-30/1225273091.PDF",
        "adjunctType": "PDF",
        "orgId": "9900006256",
        "announcementId": "1225273091",
        "announcementTime": 1746000000000,
    }
    meta = extract_report_metadata(ann, "601686", 2025)
    assert "local_path" not in meta
    assert "file_path" not in meta
    assert "local_file" not in meta
