from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_LEGACY_MESSAGE = "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据"


def test_rollout_docs_and_inventory_exist():
    required = [
        "backend/docs/artifacts/company_v2_legacy_inventory.md",
        "backend/docs/artifacts/company_v2_production_rollout_gate.md",
        "backend/docs/artifacts/company_v2_legacy_deprecation_plan.md",
        "backend/docs/artifacts/company_v2_staged_rollout.md",
        "backend/docs/artifacts/company_v2_test_commands.md",
    ]
    for relpath in required:
        path = ROOT / relpath
        assert path.exists(), f"missing rollout doc: {relpath}"
        text = path.read_text(encoding="utf-8")
        assert "legacy" in text.lower()
        assert "CompanyV2" in text


def test_legacy_inventory_marks_key_files_and_policy():
    text = (ROOT / "backend/docs/artifacts/company_v2_legacy_inventory.md").read_text(encoding="utf-8")

    assert "CompanyFundamentalsPanel.vue" in text
    assert "DataSourceBanner.vue" in text
    assert "frontend/src/utils/fundamentalAdapters.js" in text
    assert "frontend/src/api/fundamentals.js" in text
    assert "backend/app/routers/fundamentals.py" in text
    assert "backend/app/tools/fundamental/base.py" in text
    assert "freeze" in text
    assert "remove_after_prod_cutover" in text
    assert "New data sources" in text or "New data source" in text


def test_staged_defaults_and_rollback_source_contract():
    stock_detail = (ROOT / "frontend/src/views/StockDetailView.vue").read_text(encoding="utf-8")
    env_example = (ROOT / "frontend/.env.example").read_text(encoding="utf-8")
    prod_example = (ROOT / "frontend/.env.production.example").read_text(encoding="utf-8")

    assert "import.meta.env.PROD ? 'legacy' : 'v2'" in stock_detail
    assert "companyV2Query.value === '1'" in stock_detail
    assert "companyV2Query.value !== '0'" in stock_detail
    assert "companyV2TabFailed" in stock_detail
    assert "CompanyFundamentalsPanel" in stock_detail
    assert "VITE_COMPANY_TAB_VERSION=v2" in env_example
    assert "VITE_COMPANY_TAB_VERSION=v2" in prod_example
    assert "company_v2=0" in prod_example


def test_company_v2_sources_do_not_include_legacy_data_mode_message_or_advice():
    paths = [
        ROOT / "frontend/src/views/CompanyV2View.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2Section.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2MetricCards.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2FallbackTable.vue",
        ROOT / "backend/app/services/company_v2_debug_service.py",
        ROOT / "backend/app/services/company_v2_debug_diagnosis_service.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert FORBIDDEN_LEGACY_MESSAGE not in source
    for phrase in ("建议买入", "建议卖出", "目标价", "保证上涨", "target_price", "analyst_rating"):
        assert phrase not in source


def test_legacy_generic_data_mode_message_is_marked_deprecated():
    base = (ROOT / "backend/app/tools/fundamental/base.py").read_text(encoding="utf-8")

    assert FORBIDDEN_LEGACY_MESSAGE in base
    assert "Deprecated legacy Company Tab message" in base
    assert "CompanyV2 must use DebugEnvelope" in base


def test_root_pytest_collection_is_scoped_away_from_playwright_script():
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    test_stock_detail = ROOT / "test_stock_detail.py"

    assert test_stock_detail.exists()
    assert "testpaths = backend/tests" in pytest_ini
    assert "pythonpath = backend" in pytest_ini
    assert "frontend" in pytest_ini
    assert "test_stock_detail.py" not in pytest_ini


def test_test_command_docs_define_standard_and_optional_e2e_commands():
    text = (ROOT / "backend/docs/artifacts/company_v2_test_commands.md").read_text(encoding="utf-8")

    assert "pytest -q" in text
    assert "npm run test" in text
    assert "npm run build" in text
    assert "npx playwright test" in text
    assert "not part of default pytest collection" in text
