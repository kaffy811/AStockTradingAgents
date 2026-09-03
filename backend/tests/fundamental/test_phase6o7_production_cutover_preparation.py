from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_LEGACY_MESSAGE = "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据"


def test_cutover_docs_exist_and_define_required_sections():
    required = {
        "backend/docs/artifacts/company_v2_monitoring_plan.md": [
            "company_v2_debug_full_latency_ms_p50",
            "company_v2_fallback_to_legacy_count",
            "request_id",
            "error_code",
            "Do not log secrets",
        ],
        "backend/docs/artifacts/company_v2_production_rollback_checklist.md": [
            "VITE_COMPANY_TAB_VERSION=legacy",
            "company_v2=0",
            "Do not roll back database migrations",
            "incident report",
        ],
        "backend/docs/artifacts/company_v2_production_cutover_checklist.md": [
            "Pre-Cutover",
            "Cutover",
            "Post-Cutover",
            "VITE_COMPANY_TAB_VERSION=v2",
        ],
        "backend/docs/artifacts/company_v2_production_cutover_manual_acceptance.md": [
            "600519",
            "000725",
            "601686",
            "Bottom sentinel visible",
            "company_v2=0",
        ],
    }

    for relpath, snippets in required.items():
        text = (ROOT / relpath).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in text, f"{snippet!r} missing from {relpath}"


def test_production_and_staging_config_strategy_is_documented():
    root_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    backend_env = (ROOT / "backend/.env.example").read_text(encoding="utf-8")
    frontend_env = (ROOT / "frontend/.env.example").read_text(encoding="utf-8")
    prod_env = (ROOT / "frontend/.env.production.example").read_text(encoding="utf-8")
    rollout_doc = (ROOT / "backend/docs/artifacts/company_v2_staged_rollout.md").read_text(encoding="utf-8")

    assert "VITE_COMPANY_TAB_VERSION=v2" in frontend_env
    assert "VITE_COMPANY_TAB_VERSION=v2" in prod_env
    assert "production default after Phase 6S cutover" in root_env
    assert "company_v2=1 forces v2" in root_env
    assert "company_v2=0 forces legacy" in root_env
    assert "Do not put secrets in VITE_" in root_env
    assert "production default after Phase 6S cutover: VITE_COMPANY_TAB_VERSION=v2" in backend_env
    assert "Do not put secrets in VITE_" in backend_env
    assert "Priority" in rollout_doc
    assert "One-line rollback config" in rollout_doc


def test_stock_detail_cutover_and_rollback_contract():
    source = (ROOT / "frontend/src/views/StockDetailView.vue").read_text(encoding="utf-8")

    assert "import.meta.env.PROD ? 'legacy' : 'v2'" in source
    assert "companyV2Query.value === '1'" in source
    assert "companyV2Query.value !== '0'" in source
    assert "VITE_ENABLE_COMPANY_V2" in source
    assert "companyV2TabFailed" in source
    assert "onCompanyV2LoadError" in source
    assert "CompanyFundamentalsPanel" in source


def test_company_v2_summary_exposes_monitoring_fields():
    from app.services.company_v2_debug_service import company_v2_debug_service

    modules = {
        "quote_overview": {
            "source_chain": [{"provider": "baostock", "success": True, "cache_hit": True}],
            "render": {"has_displayable_data": True},
            "errors": [],
            "diagnosis": {"primary_issue": "OK"},
        },
        "report_documents": {
            "source_chain": [{"provider": "pdf_metrics", "success": False, "error_code": "PROVIDER_EMPTY"}],
            "render": {"has_displayable_data": False},
            "errors": [{"error_code": "REPORT_PDF_NOT_FOUND"}],
            "diagnosis": {"primary_issue": "REPORT_PDF_NOT_FOUND"},
        },
        "profitability": {
            "source_chain": [{"provider": "baostock", "success": False, "error_code": "PROVIDER_TIMEOUT", "status": "timeout"}],
            "render": {"has_displayable_data": False},
            "errors": [{"error_code": "MAPPING_ERROR"}],
            "diagnosis": {"primary_issue": "MAPPING_ERROR"},
        },
    }

    summary = company_v2_debug_service._summary(modules)
    expected = {
        "providers_attempted",
        "providers_success",
        "providers_timeout",
        "modules_renderable",
        "modules_unavailable",
        "cache_hit_count",
        "cache_stale_count",
        "cache_unavailable_count",
        "report_pdf_not_found_count",
        "report_not_ingested_count",
        "mapping_error_count",
        "render_rule_error_count",
        "fallback_to_legacy_count",
    }
    assert expected.issubset(summary.keys())
    assert summary["providers_timeout"] == 1
    assert summary["report_pdf_not_found_count"] == 1
    assert summary["mapping_error_count"] == 1
    assert summary["fallback_to_legacy_count"] == 0


def test_company_v2_sources_do_not_include_forbidden_legacy_or_advice_words():
    paths = [
        ROOT / "frontend/src/views/CompanyV2View.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2Section.vue",
        ROOT / "backend/app/services/company_v2_debug_service.py",
        ROOT / "backend/app/services/company_v2_debug_diagnosis_service.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert FORBIDDEN_LEGACY_MESSAGE not in source
    for phrase in ("target_price", "analyst_rating", "建议买入", "建议卖出", "保证上涨"):
        assert phrase not in source


def test_debug_sanitization_contract_and_test_commands():
    provider_runner = (ROOT / "backend/app/datasource/debug_provider_runner.py").read_text(encoding="utf-8")
    structured_logger = (ROOT / "backend/app/core/structured_debug_logger.py").read_text(encoding="utf-8")
    test_commands = (ROOT / "backend/docs/artifacts/company_v2_test_commands.md").read_text(encoding="utf-8")

    assert "raw_full" in provider_runner
    assert "include_raw" in provider_runner
    assert "sanitize_debug_payload" in provider_runner
    assert "local_path" in structured_logger
    assert "token" in structured_logger
    assert "[redacted]" in structured_logger
    assert "pytest -q" in test_commands
    assert "npm run test" in test_commands
    assert "npm run build" in test_commands
    assert "npx playwright test" in test_commands
