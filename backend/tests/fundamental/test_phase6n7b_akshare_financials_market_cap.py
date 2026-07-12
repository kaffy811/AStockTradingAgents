"""
tests/fundamental/test_phase6n7b_akshare_financials_market_cap.py

Phase 6N-7B: AKShare Financials + Market Cap Integration

Covers:
  A. AKShare provider column mapping / normalization:
  T01  _map_row maps EM profit columns → core_schema fields
  T02  _map_row missing column → COLUMN_RENAMED error (no silent null)
  T03  _map_row present-but-empty → PROVIDER_EMPTY error (no silent null)
  T04  SPOT_EM_COLUMN_MAP covers market_cap/circ_mv/latest_price/pe/pb/turnover_rate
  T05  _safe_float handles '--' / '' / None / 'nan'
  T06  _exc_reason_code: timeout → PROVIDER_TIMEOUT; connection → NETWORK_UNAVAILABLE
  T07  _to_em_code / _to_sina_code symbol conversion
  T08  SINA_INDICATOR_MAP declares percent for roe, ratio for ocf_to_np

  B. merge_coverage_rows (priority / units / computed):
  T09  ak_quote keys normalized: latest_price→close, market_cap→total_mv, volume→vol
  T10  source priority: etl_daily_basic > baostock_kline > akshare_spot_em
  T11  BaoStock kline valuation fields (peTTM/pbMRQ/psTTM/pcfNcfTTM) survive merge
       with source=baostock_kline
  T12  ocf_to_np computed with formula+dependencies when direct value missing
  T13  ocf_to_np NOT computed (direct value kept) when provider returns it
  T14  gross_profit computed from operating_income − operating_cost
  T15  total_share/float_share promoted from fina row into daily row

  C. Valuation P0/P1 split:
  T16  P0 complete + all P1 missing → p0_completeness=1.0 (P1 cannot drag P0)
  T17  P0/P1 totals: 3 P0 fields, 7 P1 fields, priority tag on each entry
  T18  missing valuation field → structured reason_code (PERMISSION_DENIED when
       Tushare ETL empty)
  T19  computed market_cap entry carries formula+dependencies and counts as ok

  D. Financial statements enter coverage:
  T20  ak_stmt fields flow into income/balance/cashflow audits with
       source=akshare_em_report

  E. Indicators:
  T21  indicator audit picks akshare_sina_indicator source
  T22  ocf_to_np missing dependency → stays missing with structured reason_code

  F. RAG coverage semantics (empty ≠ 100%):
  T23  RAG_COMPLETENESS_MAP: ready=1.0 / not_indexed=0.3 / empty=0.0 / failed=0.0
  T24  _audit_rag empty → completeness=0.0, reason_code=REPORT_NOT_INGESTED,
       data_status=empty, diagnostic_status=ok
  T25  _audit_rag unknown → diagnostic_status=unknown, completeness=0.0
  T26  RAG chunks never leak into financial categories; overall_without_rag
       excludes rag; rag is evidence-only (no rag field in income/balance/etc.)
  T27  report.to_dict(): rag_completeness=0.0 when empty (regression guard)

  G. Failure resilience:
  T28  _fetch_akshare_supplement: provider raising → no exception (no 500),
       meta carries status=failed + reason_code
  T29  AkshareQuoteProvider timeout → meta reason_code=PROVIDER_TIMEOUT

  H. Diagnostics visibility:
  T30  provider meta includes provider/interface/status/reason_code/elapsed_ms

  I. Cache-first / low-frequency guards (static):
  T31  akshare_coverage_providers only imported by coverage_audit_service +
       scripts (never in request-time tools/routers/services)
  T32  coverage_audit_service not imported by any router/tool (offline CLI only)

  J. Safety guards (static):
  T33  no target_price / analyst_rating / institutional_consensus in 6N-7B files
  T34  no investment-advice wording (买入/卖出/目标价建议) in 6N-7B files

  K. Free-mode page path (BaoStock kline valuation → quote_snapshot):
  T35  fetch_baostock passes pe_ttm/pb/ps_ttm/pcf_ttm/turnover_rate/change_pct
       from kline record; total_mv stays None (kline has no share count)
  T36  fetch_baostock tolerates legacy record without valuation keys (all None)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.datasource.akshare_coverage_providers import (
    EM_BALANCE_MAP,
    EM_CASHFLOW_MAP,
    EM_PROFIT_MAP,
    SINA_INDICATOR_MAP,
    SPOT_EM_COLUMN_MAP,
    AkshareQuoteProvider,
    _exc_reason_code,
    _map_row,
    _safe_float,
    _to_em_code,
    _to_sina_code,
)
from app.models.data_field import ReasonCode
from app.services.coverage_audit_service import (
    CategoryCoverage,
    CoverageAuditService,
    CoverageReport,
    merge_coverage_rows,
)

_BACKEND = Path(__file__).resolve().parents[2]


def _svc() -> CoverageAuditService:
    svc = CoverageAuditService.__new__(CoverageAuditService)
    svc._trade_date = "2026-07-08"
    return svc


def _merge(daily=None, fina=None, bs_q=None, bs_f=None, ak_q=None, ak_s=None, ak_i=None):
    return merge_coverage_rows(
        daily or {}, fina or {}, bs_q or {}, bs_f or {},
        ak_q or {}, ak_s or {}, ak_i or {},
    )


# ── A. Column mapping / normalization ────────────────────────────────────────

def test_t01_map_row_em_profit():
    row = {
        "TOTAL_OPERATE_INCOME": "150900000000",
        "OPERATE_PROFIT":       "88000000000",
        "NETPROFIT":            "64000000000",
        "PARENT_NETPROFIT":     "63800000000",
        "OPERATE_INCOME":       "150000000000",
        "OPERATE_COST":         "12000000000",
    }
    data, source_fields, errors = _map_row(row, EM_PROFIT_MAP, set(row.keys()))
    assert data["revenue"] == 150900000000.0
    assert data["net_profit"] == 64000000000.0
    assert data["net_profit_parent"] == 63800000000.0
    assert source_fields["revenue"] == "TOTAL_OPERATE_INCOME"
    assert errors == []


def test_t02_map_row_column_renamed():
    row = {"TOTAL_OPERATE_INCOME": "100"}
    data, _, errors = _map_row(row, EM_PROFIT_MAP, {"TOTAL_OPERATE_INCOME"})
    assert "revenue" in data
    assert "net_profit" not in data           # 不静默 null
    renamed = [e for e in errors if e["reason_code"] == "COLUMN_RENAMED"]
    assert any(e["field"] == "net_profit" for e in renamed)


def test_t03_map_row_provider_empty():
    row = {"TOTAL_OPERATE_INCOME": "--", "NETPROFIT": None}
    cols = {"TOTAL_OPERATE_INCOME", "NETPROFIT"}
    data, _, errors = _map_row(row, EM_PROFIT_MAP, cols)
    assert "revenue" not in data
    empties = [e for e in errors if e["reason_code"] == "PROVIDER_EMPTY"]
    assert {e["field"] for e in empties} >= {"revenue", "net_profit"}


def test_t04_spot_em_map_key_fields():
    mapped = set(SPOT_EM_COLUMN_MAP.values())
    for f in ("latest_price", "change_pct", "volume", "amount",
              "market_cap", "circ_mv", "turnover_rate", "pe", "pb"):
        assert f in mapped, f"SPOT_EM_COLUMN_MAP missing {f}"
    assert SPOT_EM_COLUMN_MAP["总市值"] == "market_cap"    # 元
    assert SPOT_EM_COLUMN_MAP["流通市值"] == "circ_mv"     # 元


def test_t05_safe_float():
    assert _safe_float("--") is None
    assert _safe_float("") is None
    assert _safe_float(None) is None
    assert _safe_float("nan") is None
    assert _safe_float("17.97") == 17.97
    assert _safe_float(0) == 0.0


def test_t06_exc_reason_code():
    assert _exc_reason_code(TimeoutError("read timeout")) == "PROVIDER_TIMEOUT"
    assert _exc_reason_code(ConnectionError("proxy refused")) == "NETWORK_UNAVAILABLE"
    assert _exc_reason_code(ValueError("weird")) == "PROVIDER_EMPTY"


def test_t07_symbol_conversion():
    assert _to_em_code("600519.SH") == "SH600519"
    assert _to_em_code("000725.SZ") == "SZ000725"
    assert _to_sina_code("600519.SH") == "sh600519"
    assert _to_sina_code("000725.SZ") == "sz000725"


def test_t08_sina_indicator_units():
    assert SINA_INDICATOR_MAP["净资产收益率(%)"] == ("roe", "percent")
    # probe 验证：该列虽带 (%) 后缀，实际值为原始比率，不除 100
    field, unit = SINA_INDICATOR_MAP["经营现金净流量与净利润的比率(%)"]
    assert field == "ocf_to_np"
    assert unit == "ratio"


# ── B. merge_coverage_rows ────────────────────────────────────────────────────

def test_t09_ak_quote_key_normalization():
    ak_q = {"latest_price": 1780.0, "market_cap": 2.23e12, "volume": 25000.0,
            "circ_mv": 2.2e12}
    daily, _ = _merge(ak_q=ak_q)
    assert daily["close"] == 1780.0
    assert daily["total_mv"] == 2.23e12
    assert daily["vol"] == 25000.0
    assert daily["circ_mv"] == 2.2e12
    src = daily["__src__"]
    assert src["close"] == "akshare_spot_em"
    assert src["total_mv"] == "akshare_spot_em"


def test_t10_source_priority():
    ak_q = {"latest_price": 1.0, "pe": 10.0}
    bs_q = {"close": 2.0, "pe_ttm": 17.97}
    etl  = {"close": 3.0, "pe_ttm": 18.01}
    daily, _ = _merge(daily=etl, bs_q=bs_q, ak_q=ak_q)
    # ETL 优先级最高
    assert daily["close"] == 3.0
    assert daily["pe_ttm"] == 18.01
    assert daily["__src__"]["close"] == "etl_daily_basic"
    # ETL 缺失时 BaoStock 覆盖 AKShare
    daily2, _ = _merge(bs_q=bs_q, ak_q=ak_q)
    assert daily2["close"] == 2.0
    assert daily2["__src__"]["close"] == "baostock_kline"


def test_t11_baostock_valuation_fields_merge():
    # BaoStock kline: peTTM→pe_ttm, pbMRQ→pb, psTTM→ps_ttm, pcfNcfTTM→pcf_ttm
    bs_q = {"pe_ttm": 17.97, "pb": 5.49, "ps_ttm": 8.48, "pcf_ttm": 1046.7}
    daily, _ = _merge(bs_q=bs_q)
    for k, v in bs_q.items():
        assert daily[k] == v
        assert daily["__src__"][k] == "baostock_kline"


def test_t12_ocf_to_np_computed():
    ak_s = {"operating_cashflow": 9.6e10, "net_profit": 1.0e11}
    _, fina = _merge(ak_s=ak_s)
    assert fina["ocf_to_np"] == pytest.approx(0.96)
    assert fina["__src__"]["ocf_to_np"] == "computed"
    meta = fina["__computed__"]["ocf_to_np"]
    assert meta["formula"] == "operating_cashflow / net_profit"
    assert meta["dependencies"] == ["operating_cashflow", "net_profit"]


def test_t13_ocf_to_np_direct_value_kept():
    ak_i = {"ocf_to_np": 0.9558}
    ak_s = {"operating_cashflow": 1.0, "net_profit": 2.0}
    _, fina = _merge(ak_s=ak_s, ak_i=ak_i)
    assert fina["ocf_to_np"] == 0.9558
    assert "ocf_to_np" not in fina["__computed__"]


def test_t14_gross_profit_computed():
    ak_s = {"operating_income": 100.0, "operating_cost": 70.0}
    _, fina = _merge(ak_s=ak_s)
    assert fina["gross_profit"] == 30.0
    assert fina["__src__"]["gross_profit"] == "computed"
    assert fina["__computed__"]["gross_profit"]["dependencies"] == [
        "operating_income", "operating_cost"]


def test_t15_share_promotion():
    bs_f = {"total_share": 1.256e9, "float_share": 1.25e9}
    daily, _ = _merge(bs_f=bs_f)
    assert daily["total_share"] == 1.256e9
    assert daily["float_share"] == 1.25e9


# ── C. Valuation P0/P1 ────────────────────────────────────────────────────────

def test_t16_p0_independent_of_p1():
    row = {"pe_ttm": 17.97, "pb": 5.49, "total_mv": 2.23e12,
           "__src__": {"pe_ttm": "baostock_kline", "pb": "baostock_kline",
                       "total_mv": "computed"}}
    cov = _svc()._audit_valuation(row)
    assert cov.extra["p0_completeness"] == 1.0
    assert cov.extra["p1_completeness"] == 0.0
    assert cov.extra["p0_ok"] == 3


def test_t17_p0_p1_totals_and_tags():
    cov = _svc()._audit_valuation({})
    assert cov.extra["p0_total"] == 3
    assert cov.extra["p1_total"] == 7
    p0_names = {f["field_name"] for f in cov.fields if f["priority"] == "P0"}
    assert p0_names == {"pe_ttm", "pb", "market_cap"}
    p1_names = {f["field_name"] for f in cov.fields if f["priority"] == "P1"}
    assert p1_names == {"circ_mv", "total_share", "float_share", "turnover_rate",
                        "dividend_yield", "ps_ttm", "pcf_ttm"}


def test_t18_missing_valuation_structured_reason():
    cov = _svc()._audit_valuation({}, ReasonCode.PERMISSION_DENIED.value)
    for f in cov.fields:
        assert f["status"] == "missing"
        assert f["reason_code"] == "PERMISSION_DENIED"
        assert f["priority"] in ("P0", "P1")


def test_t19_computed_market_cap_entry():
    row = {
        "total_mv": 2.23e12,
        "__src__": {"total_mv": "computed"},
        "__computed__": {"market_cap": {
            "formula": "close × total_share",
            "dependencies": ["close", "total_share"],
        }},
    }
    cov = _svc()._audit_valuation(row)
    mc = next(f for f in cov.fields if f["field_name"] == "market_cap")
    assert mc["status"] == "ok"
    assert mc["source"] == "computed"
    assert mc["formula"] == "close × total_share"
    assert mc["dependencies"] == ["close", "total_share"]


# ── D. Statements into coverage ───────────────────────────────────────────────

def test_t20_statements_enter_coverage():
    ak_s = {
        "revenue": 1.5e11, "gross_profit": 1.38e11, "operating_profit": 8.8e10,
        "net_profit": 6.4e10, "net_profit_parent": 6.38e10,
        "total_assets": 3.0e11, "total_liabilities": 5.0e10, "total_equity": 2.5e11,
        "current_assets": 2.4e11, "current_liabilities": 4.6e10,
        "operating_cashflow": 9.1e10, "investing_cashflow": -5.0e9,
        "financing_cashflow": -6.4e10,
    }
    _, fina = _merge(ak_s=ak_s)
    svc = _svc()
    income   = svc._audit_income(fina)
    balance  = svc._audit_balance(fina)
    cashflow = svc._audit_cashflow(fina)
    assert income.completeness == 1.0
    assert balance.completeness == 1.0
    assert cashflow.completeness == 1.0
    for cov in (income, balance, cashflow):
        for f in cov.fields:
            assert f["source"] == "akshare_em_report", f
    # financial_statement_completeness 聚合
    rpt = CoverageReport("600519.SH", "2026-07-08",
                         {"income": income, "balance": balance, "cashflow": cashflow})
    assert rpt.to_dict()["financial_statement_completeness"] == 1.0


# ── E. Indicators ─────────────────────────────────────────────────────────────

def test_t21_indicator_source_attribution():
    ak_i = {"roe": 0.078, "gross_margin": 0.9199, "debt_ratio": 0.1656}
    _, fina = _merge(ak_i=ak_i)
    cov = _svc()._audit_indicators(fina)
    roe = next(f for f in cov.fields if f["field_name"] == "roe")
    assert roe["status"] == "ok"
    assert roe["source"] == "akshare_sina_indicator"


def test_t22_ocf_to_np_missing_dependency_stays_missing():
    ak_s = {"operating_cashflow": 9.6e10}    # net_profit missing → 不可计算
    _, fina = _merge(ak_s=ak_s)
    assert fina.get("ocf_to_np") is None
    cov = _svc()._audit_indicators(fina, ReasonCode.PERMISSION_DENIED.value)
    ocf = next(f for f in cov.fields if f["field_name"] == "ocf_to_np")
    assert ocf["status"] == "missing"
    assert ocf["reason_code"] is not None


# ── F. RAG coverage semantics ─────────────────────────────────────────────────

def test_t23_rag_completeness_map():
    m = CoverageAuditService.RAG_COMPLETENESS_MAP
    assert m["ready"] == 1.0
    assert m["not_indexed"] == 0.3
    assert m["empty"] == 0.0
    assert m["failed"] == 0.0
    assert m["unknown"] == 0.0


def test_t24_audit_rag_empty():
    cov = _svc()._audit_rag({
        "documents_count": 0, "chunks_count": 0,
        "embedding_count": 0, "rag_status": "empty",
    })
    assert cov.completeness == 0.0
    assert cov.extra["data_status"] == "empty"
    assert cov.extra["diagnostic_status"] == "ok"
    assert cov.extra["reason_code"] == "REPORT_NOT_INGESTED"
    assert cov.extra["documents_count"] == 0


def test_t25_audit_rag_unknown():
    cov = _svc()._audit_rag({"rag_status": "unknown"})
    assert cov.extra["diagnostic_status"] == "unknown"
    assert cov.completeness == 0.0


def test_t26_rag_is_evidence_only():
    # RAG 文本 chunk 不进入结构化财务字段
    _, fina = _merge(ak_s={"revenue": 1.0})
    for rag_key in ("chunks_count", "embedding_count", "documents_count", "rag_status"):
        assert rag_key not in fina
    # overall_without_rag 不受 rag 影响
    svc = _svc()
    cats = {
        "income": svc._audit_income({"revenue": 1.0, "__src__": {}}),
        "rag":    svc._audit_rag({"rag_status": "empty"}),
    }
    rpt = CoverageReport("600519.SH", "2026-07-08", cats)
    d = rpt.to_dict()
    assert d["overall_without_rag"] == pytest.approx(1 / 5)   # income 1/5，rag 不计
    # financial_statement_completeness 不含 rag 分量
    assert d["financial_statement_completeness"] == pytest.approx(round(1 / 5 / 3, 4), abs=1e-4)


def test_t27_rag_empty_never_100pct():
    svc = _svc()
    cats = {"rag": svc._audit_rag({"rag_status": "empty",
                                   "documents_count": 0, "chunks_count": 0,
                                   "embedding_count": 0})}
    rpt = CoverageReport("601686.SH", "2026-07-08", cats, rag_status="empty")
    d = rpt.to_dict()
    assert d["rag_completeness"] == 0.0
    assert d["rag_status"] == "empty"


# ── G. Failure resilience ─────────────────────────────────────────────────────

async def test_t28_akshare_supplement_no_500_on_provider_error():
    svc = _svc()
    boom = AsyncMock(side_effect=RuntimeError("network down"))
    with patch("app.datasource.akshare_coverage_providers.akshare_quote_provider.fetch", boom), \
         patch("app.datasource.akshare_coverage_providers.akshare_statement_provider.fetch", boom), \
         patch("app.datasource.akshare_coverage_providers.akshare_indicator_provider.fetch", boom):
        ak_q, ak_s, ak_i, meta = await svc._fetch_akshare_supplement("600519.SH")
    assert ak_q == {} and ak_s == {} and ak_i == {}
    for part in ("quote", "statements", "indicators"):
        assert meta[part]["status"] == "failed"
        assert meta[part]["reason_code"] is not None


async def test_t29_quote_provider_timeout_reason_code():
    provider = AkshareQuoteProvider()

    async def _never(*a, **kw):
        raise asyncio.TimeoutError()

    with patch("asyncio.wait_for", _never):
        data, meta = await provider.fetch("600519.SH", timeout_s=0.01)
    assert data == {}
    assert meta["status"] == "failed"
    assert meta["reason_code"] == "PROVIDER_TIMEOUT"


# ── H. Diagnostics visibility ─────────────────────────────────────────────────

def test_t30_provider_meta_shape():
    provider = AkshareQuoteProvider()
    meta = provider._meta("failed", 0.0, reason_code="NETWORK_UNAVAILABLE")
    for key in ("provider", "interface", "source", "status",
                "elapsed_ms", "reason_code", "source_fields", "errors"):
        assert key in meta, f"meta missing {key}"
    assert meta["provider"] == "akshare"
    assert meta["interface"] == "stock_zh_a_spot_em"


# ── I. Cache-first / low-frequency guards ─────────────────────────────────────

def _py_files(*rel_dirs: str) -> list[Path]:
    files: list[Path] = []
    for rel in rel_dirs:
        files.extend((_BACKEND / rel).rglob("*.py"))
    return [f for f in files if "__pycache__" not in str(f)]


def test_t31_coverage_providers_not_in_request_path():
    # 低频 provider 只允许 coverage_audit_service 与 scripts 引用
    offenders = []
    for f in _py_files("app/routers", "app/tools", "app/agents"):
        if "akshare_coverage_providers" in f.read_text(encoding="utf-8"):
            offenders.append(str(f))
    svc_files = [
        f for f in _py_files("app/services")
        if "akshare_coverage_providers" in f.read_text(encoding="utf-8")
        and f.name != "coverage_audit_service.py"
    ]
    assert offenders == [], f"high-frequency path imports coverage providers: {offenders}"
    assert svc_files == [], f"unexpected service imports: {svc_files}"


def test_t32_coverage_service_offline_only():
    offenders = []
    for f in _py_files("app/routers", "app/tools"):
        if "coverage_audit_service" in f.read_text(encoding="utf-8"):
            offenders.append(str(f))
    assert offenders == [], (
        f"coverage_audit_service must stay offline/CLI-only, found in: {offenders}"
    )


# ── J. Safety guards ──────────────────────────────────────────────────────────

_PHASE_FILES = [
    _BACKEND / "app" / "datasource" / "akshare_coverage_providers.py",
    _BACKEND / "app" / "services" / "coverage_audit_service.py",
    _BACKEND / "scripts" / "probe_akshare_quote.py",
    _BACKEND / "scripts" / "probe_akshare_financials.py",
    _BACKEND / "scripts" / "probe_akshare_indicators.py",
    _BACKEND / "scripts" / "coverage_audit.py",
]


def test_t33_no_banned_analyst_fields():
    banned = ("target_price", "analyst_rating", "institutional_consensus")
    for f in _PHASE_FILES:
        text = f.read_text(encoding="utf-8")
        for term in banned:
            assert term not in text, f"{f.name} contains banned field: {term}"


def test_t34_no_investment_advice_wording():
    banned = ("买入建议", "卖出建议", "目标价", "建议买入", "建议卖出")
    for f in _PHASE_FILES:
        text = f.read_text(encoding="utf-8")
        for term in banned:
            assert term not in text, f"{f.name} contains advice wording: {term}"


# ── K. Free-mode page path: kline valuation → quote_snapshot ─────────────────

async def test_t35_fetch_baostock_carries_kline_valuation():
    from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool

    rec = {
        "ts_code": "600519.SH", "trade_date": "2026-07-07", "close": 1414.0,
        "change_pct": -0.53, "turnover_rate": 0.19,
        "pe_ttm": 17.97, "pb": 5.49, "ps_ttm": 8.48, "pcf_ttm": 1046.7,
        "source": "baostock_kline_fallback",
    }
    with patch("app.datasource.baostock_client.baostock_client.get_recent_close",
               AsyncMock(return_value=rec)):
        tool = QuoteSnapshotTool()
        result = await tool.fetch_baostock("CN", "600519")
    assert result["source"] == "baostock_kline_fallback"
    assert result["close"] == 1414.0
    assert result["pe_ttm"] == 17.97
    assert result["pb"] == 5.49
    assert result["ps_ttm"] == 8.48
    assert result["pcf_ttm"] == 1046.7
    assert result["turnover_rate"] == 0.19
    assert result["change_pct"] == -0.53
    assert result["total_mv"] is None      # kline 无股本 → 不编造市值
    assert result["circ_mv"] is None


async def test_t36_fetch_baostock_legacy_record_all_none():
    from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool

    rec = {"ts_code": "600519.SH", "trade_date": "2026-07-07", "close": 1414.0,
           "source": "baostock_kline_fallback"}
    with patch("app.datasource.baostock_client.baostock_client.get_recent_close",
               AsyncMock(return_value=rec)):
        tool = QuoteSnapshotTool()
        result = await tool.fetch_baostock("CN", "600519")
    assert result["close"] == 1414.0
    for k in ("pe_ttm", "pb", "ps_ttm", "pcf_ttm", "turnover_rate", "change_pct"):
        assert result[k] is None
