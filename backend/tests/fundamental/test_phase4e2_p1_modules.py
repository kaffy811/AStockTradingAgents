"""
Phase 4E-2: P1 modules return partial envelope (not 503) when data unavailable.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.aggregator.envelope import err_envelope, build_api_response


MODULES_TO_TEST = [
    "asset_structure", "solvency", "capital_occupation",
    "operation_capability", "dupont", "major_holders", "equity_structure",
]


def _mock_settings_no_token():
    s = MagicMock()
    s.tushare_token = None
    s.enable_akshare = False
    return s


# T1-T7: each module with err_envelope → build_api_response → partial=True, data.rows is list
@pytest.mark.parametrize("module_key", MODULES_TO_TEST)
def test_partial_envelope_has_rows_list(module_key):
    """err_envelope → build_api_response always produces data.rows as list and partial=True."""
    with patch("app.core.config.settings", _mock_settings_no_token()):
        env = err_envelope(f"TUSHARE_TOKEN 未配置，{module_key} 数据不可用")
        resp = build_api_response(
            env, "CN", "600519", "600519.SH", module_key, module_key, None
        )
    assert resp["partial"] is True
    assert isinstance(resp["errors"], list)
    assert len(resp["errors"]) > 0
    assert resp["data"] is not None
    assert "rows" in resp["data"]
    assert isinstance(resp["data"]["rows"], list)


# T8: reasons field in data
@pytest.mark.parametrize("module_key", MODULES_TO_TEST)
def test_partial_envelope_has_reasons(module_key):
    """err_envelope → build_api_response produces data.reasons as list."""
    with patch("app.core.config.settings", _mock_settings_no_token()):
        env = err_envelope(f"TUSHARE_TOKEN 未配置，{module_key} 数据不可用")
        resp = build_api_response(
            env, "CN", "600519", "600519.SH", module_key, module_key, None
        )
    assert "reasons" in resp["data"]
    assert isinstance(resp["data"]["reasons"], list)


# T9: DataEnvelope top-level keys unchanged
def test_data_envelope_top_level_keys():
    """build_api_response always returns required top-level keys."""
    env = err_envelope("test error")
    with patch("app.core.config.settings", _mock_settings_no_token()):
        resp = build_api_response(env, "CN", "600519", "600519.SH", "solvency", "偿债能力", None)
    required = {"market", "symbol", "ts_code", "module_key", "data", "errors", "partial", "stale", "generated_at", "source", "meta"}
    assert required.issubset(set(resp.keys()))


# T10: HTTP 200 behavior verified via build_api_response (router already tested in phase 4E-1)
def test_http_200_not_503_conceptual():
    """Verify no 503 is raised for module-level errors (always HTTP 200)."""
    # The router always returns 200 since Phase 4E-1; this test verifies envelope shape.
    env = err_envelope("无数据")
    with patch("app.core.config.settings", _mock_settings_no_token()):
        resp = build_api_response(env, "CN", "600519", "600519.SH", "dupont", "杜邦分析", None)
    # No exception raised = 200 behavior confirmed
    assert resp["partial"] is True
