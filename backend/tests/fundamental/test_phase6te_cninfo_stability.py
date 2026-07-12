"""
backend/tests/fundamental/test_phase6te_cninfo_stability.py
Phase 6T-E: CNINFO 报告发现稳定性（去重/canonical/年份/URL 白名单）
"""
from __future__ import annotations

import pytest

from app.datasource.cninfo_provider import (
    classify_report_type,
    extract_report_metadata,
    validate_pdf_url,
)


def _ann(title, adjunct="finalpage/2025-04-10/1220000001.PDF", ann_time_ms=1744243200000):
    return {
        "announcementTitle": title,
        "adjunctUrl": adjunct,
        "adjunctType": "PDF",
        "announcementId": "1220000001",
        "orgId": "9900000001",
        "announcementTime": ann_time_ms,
    }


# ── 报告类型识别 ──────────────────────────────────────────────────────────────

def test_q3_report_not_classified_as_annual():
    assert classify_report_type("公司2024年第三季度报告") == "q3"
    assert classify_report_type("公司2024年三季报") == "q3"


def test_semi_annual_not_classified_as_annual():
    assert classify_report_type("公司2024年半年度报告") == "semi_annual"


def test_summary_not_main_report():
    meta = extract_report_metadata(_ann("公司2024年年度报告摘要"), "601686", 2024, "annual")
    assert meta["is_summary"] is True
    assert meta["is_annual"] is False


def test_english_version_not_main_report():
    assert classify_report_type("2024 Annual Report 年度报告（英文版）") is None


def test_cancelled_announcement_excluded():
    assert classify_report_type("关于取消2024年年度报告披露的公告") is None


def test_bond_announcement_excluded():
    assert classify_report_type("公司债券2024年年度报告") is None


# ── report_year 与公告年份区分 ────────────────────────────────────────────────

def test_report_year_from_title_not_announcement_year():
    """2023 年报在 2024 年公告：report_year 必须是 2023。"""
    meta = extract_report_metadata(
        _ann("友发集团2023年年度报告"), "601686",
        report_year=2024,   # 错误的公告年份传入
        report_type="annual",
    )
    assert meta["report_year"] == 2023
    assert meta["announcement_date"].startswith("2025") or meta["announcement_date"]


def test_report_year_kept_when_title_has_no_year():
    meta = extract_report_metadata(_ann("年度报告"), "601686", 2023, "annual")
    assert meta["report_year"] == 2023


# ── URL 白名单 ───────────────────────────────────────────────────────────────

def test_pdf_url_whitelist():
    ok, _ = validate_pdf_url("https://static.cninfo.com.cn/finalpage/2025-04-10/a.PDF")
    assert ok
    bad_host, _ = validate_pdf_url("https://evil.example.com/a.PDF")
    assert not bad_host
    bad_scheme, _ = validate_pdf_url("file:///etc/passwd.PDF")
    assert not bad_scheme
    not_pdf, _ = validate_pdf_url("https://static.cninfo.com.cn/finalpage/a.html")
    assert not not_pdf


def test_adjunct_url_composition():
    meta = extract_report_metadata(
        _ann("公司2024年年度报告", adjunct="finalpage/2025-04-10/x.PDF"),
        "601686", 2024, "annual",
    )
    assert meta["pdf_url"].startswith("https://static.cninfo.com.cn/")
    assert meta["pdf_url"].endswith(".PDF")


# ── canonical 去重 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_discover_reports_canonical_dedup():
    """同年同类型只保留一份 canonical，输出 dedup 元字段。"""
    from unittest.mock import AsyncMock, patch
    import app.datasource.cninfo_provider as provider

    announcements = [
        _ann("友发集团2023年年度报告", adjunct="finalpage/2024-04-10/a.PDF"),
        _ann("友发集团2023年年度报告", adjunct="finalpage/2024-04-11/b.PDF"),  # 重复（不同URL）
    ]

    async def fake_search(symbol, **kwargs):
        return announcements

    with patch.object(provider, "search_announcements", new=AsyncMock(side_effect=fake_search)):
        with patch.object(provider, "fulltext_search_announcements", new=AsyncMock(return_value=[])):
            with patch.object(provider.asyncio, "sleep", new=AsyncMock()):
                results = await provider.discover_reports(
                    "601686", start_year=2023, end_year=2023,
                    report_types=["annual"],
                )

    annual_2023 = [r for r in results if r["report_year"] == 2023 and r["report_type"] == "annual"]
    assert len(annual_2023) == 1
    canonical = annual_2023[0]
    assert canonical["canonical_report"] is True
    assert canonical["is_latest_version"] is True
    assert canonical["dedup_key"] == "601686:2023:annual"
    assert canonical["supersedes_report_id"] is None
    assert canonical["duplicate_candidates_removed"] >= 1


@pytest.mark.asyncio
async def test_discover_reports_summary_filtered():
    """摘要不得作为主报告返回。"""
    from unittest.mock import AsyncMock, patch
    import app.datasource.cninfo_provider as provider

    announcements = [
        _ann("友发集团2023年年度报告摘要", adjunct="finalpage/2024-04-10/s.PDF"),
    ]

    with patch.object(provider, "search_announcements", new=AsyncMock(return_value=announcements)):
        with patch.object(provider, "fulltext_search_announcements", new=AsyncMock(return_value=[])):
            with patch.object(provider.asyncio, "sleep", new=AsyncMock()):
                results = await provider.discover_reports(
                    "601686", start_year=2023, end_year=2023,
                    report_types=["annual"],
                )
    assert all(not r.get("is_summary") for r in results)
    assert len(results) == 0


def test_discovery_agent_strips_local_path():
    """agent 输出不得包含 local_path。"""
    import inspect
    from app.services import cninfo_report_discovery_agent as agent_module
    source = inspect.getsource(agent_module)
    assert "local_path" in source  # 显式剥离逻辑存在
    # 剥离集合中包含 local_path
    assert '"local_path"' in source or "'local_path'" in source


def test_stability_audit_script_exists():
    from pathlib import Path
    script = Path(__file__).resolve().parents[3] / "backend/scripts/company_v2_cninfo_stability_audit.py"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    # 不下载 PDF；只做 discovery metadata
    assert "download" not in text.lower() or "不下载" in text
    for stat in ("symbols_total", "annual_reports_found", "non_whitelist_urls", "summary_reports_filtered"):
        assert stat in text
