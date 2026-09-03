from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_phase6u_d3_company_profile_000725_merges_cninfo(monkeypatch):
    from app.services import company_v2_stock_basic_service as svc

    async def fake_bs(ts_code: str):
        return {
            "symbol": "000725",
            "ts_code": ts_code,
            "company_name": "京东方科技集团股份有限公司",
            "exchange": "深交所",
            "market": "CN",
            "list_date": "2001-01-12",
            "industry": "制造业",
            "source": "baostock",
        }

    async def fake_cninfo(symbol: str):
        return {
            "company_name": "京东方科技集团股份有限公司",
            "short_name": "京东方Ａ",
            "industry": "计算机、通信和其他电子设备制造业",
            "registered_address": "北京市朝阳区酒仙桥路10号",
            "office_address": "北京市北京经济技术开发区西环中路12号",
            "main_business": "为信息交互和人类健康提供智慧端口产品和专业服务",
            "business_scope": "制造电子产品、通信设备。",
            "introduction": "公司的前身为北京电子管厂。",
            "source": "cninfo_company_profile",
        }

    monkeypatch.setattr(svc, "_fetch_baostock_stock_basic", fake_bs)
    monkeypatch.setattr(svc, "_fetch_akshare_stock_info", fake_cninfo)

    profile = await svc.get_stock_basic("000725")
    assert profile["company_name"] == "京东方科技集团股份有限公司"
    assert profile["short_name"] == "京东方Ａ"
    assert profile["main_business"]
    assert profile["introduction"]
    assert profile["field_availability"]["main_business"] is True
    assert profile["source_metadata"]["company_profile"] == "cninfo_company_profile"


@pytest.mark.asyncio
async def test_phase6u_d3_company_profile_600519_missing_fields_compatible(monkeypatch):
    from app.services import company_v2_stock_basic_service as svc

    async def fake_bs(ts_code: str):
        return {"company_name": "贵州茅台酒股份有限公司", "list_date": "2001-08-27", "exchange": "上交所", "source": "baostock"}

    async def fake_cninfo(symbol: str):
        return {"short_name": "贵州茅台", "main_business": "", "introduction": "", "source": "cninfo_company_profile"}

    monkeypatch.setattr(svc, "_fetch_baostock_stock_basic", fake_bs)
    monkeypatch.setattr(svc, "_fetch_akshare_stock_info", fake_cninfo)

    profile = await svc.get_stock_basic("600519")
    assert profile["company_name"] == "贵州茅台酒股份有限公司"
    assert profile["short_name"] == "贵州茅台"
    assert profile["field_availability"]["introduction"] is False


def test_phase6u_d3_reports_summary_and_list_same_source():
    from app.routers.company_v2_debug import _reports_view_model

    reports = [
        {"report_type": "annual", "chunk_count": 10, "rag_status": "indexed"},
        {"report_type": "annual", "chunk_count": 0, "rag_status": "pending"},
        {"report_type": "q1", "chunk_count": 2, "rag_status": "pending"},
    ]
    model = _reports_view_model(reports, state="persisted_found")
    assert model["summary"]["report_count"] == len(reports)
    assert model["summary"]["annual_count"] == 2
    assert model["summary"]["chunk_count"] == 12
    assert model["summary"]["rag_status"] == "indexed"
    assert model["view_state"] == "persisted_found"


def test_phase6u_d3_manual_url_whitelist_validation():
    from app.routers.company_v2_debug import _validate_manual_pdf_url

    assert _validate_manual_pdf_url("https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF")[0] is True
    ok, reason = _validate_manual_pdf_url("https://example.com/report.PDF")
    assert ok is False
    assert "whitelist" in reason
    ok, reason = _validate_manual_pdf_url("file:///tmp/report.PDF")
    assert ok is False
    assert "http/https" in reason


def test_phase6u_d3_report_api_additive_schema_contract():
    from app.routers.company_v2_debug import _reports_view_model

    model = _reports_view_model([], state="empty")
    for key in ["report_status", "view_state", "summary", "report_count", "annual_count", "chunk_count", "rag_status", "errors"]:
        assert key in model
    assert model["summary"]["report_count"] == 0
