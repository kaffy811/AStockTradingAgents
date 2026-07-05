"""
tests/fundamental/test_phase2b_etl_and_rankings.py — Phase 2B ETL + 行业排名测试

覆盖范围（12 大场景）：
  C1  : MODULE_CATALOG display / alias_of / status 字段行为
  C2  : /api/v1/modules 不返回 alias（display=False）
  C3  : alias 路由仍可访问（兼容路由）
  C4  : MYSQL_DSN/ETL 缺失时 industry_rank 返回 partial=True + reason
  C5  : industry_rank 不会循环调用 Tushare
  C6  : SQL 排名函数 higher_is_better 排序正确（compute_ranks_in_memory）
  C7  : lower_is_better 排序正确
  C8  : 缺失值不参与排名
  C9  : peer_count 正确
  C10 : percentile_in_industry 正确
  C11 : ETL upsert SQL 生成正确（build_upsert_sql）
  C12 : 全量 pytest 不回归（通过 test_phase1/2a 不破坏）

原则：不发真实 HTTP / DB 请求，不依赖真实 Tushare Token / PostgreSQL。
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── 被测模块 ──────────────────────────────────────────────────────────────────
from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
from app.tools.fundamental.industry_rank import IndustryRankTool
from app.aggregator.envelope import ok_envelope, err_envelope, build_api_response
from app.etl.db import build_upsert_sql, etl_available
from app.etl.rankings import compute_ranks_in_memory
from app.routers.fundamentals_compat import compat_router, _resolve_module_id


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# C1 — MODULE_CATALOG display / alias_of / status 字段
# ═══════════════════════════════════════════════════════════════════════════

class TestC1ModuleCatalogFields:
    """MODULE_CATALOG 必须包含 display / alias_of 字段，且字段值符合规范。"""

    def test_c1_1_all_entries_have_display(self):
        """C1-1: 所有 catalog 条目都有 display 字段。"""
        for m in MODULE_CATALOG:
            assert "display" in m, f"{m['key']} 缺少 display 字段"

    def test_c1_2_all_entries_have_alias_of(self):
        """C1-2: 所有 catalog 条目都有 alias_of 字段。"""
        for m in MODULE_CATALOG:
            assert "alias_of" in m, f"{m['key']} 缺少 alias_of 字段"

    def test_c1_3_canonical_modules_have_alias_of_none(self):
        """C1-3: display=True 的规范模块 alias_of=None。"""
        for m in MODULE_CATALOG:
            if m.get("display", True):
                assert m["alias_of"] is None, (
                    f"{m['key']} display=True 但 alias_of={m['alias_of']}，应为 None"
                )

    def test_c1_4_alias_modules_have_alias_of_set(self):
        """C1-4: display=False 的 alias 模块 alias_of 指向规范 key。"""
        for m in MODULE_CATALOG:
            if not m.get("display", True):
                assert m["alias_of"] is not None, (
                    f"{m['key']} display=False 但 alias_of=None，应指向规范 key"
                )
                assert m["alias_of"] in TOOL_REGISTRY, (
                    f"{m['key']}.alias_of={m['alias_of']} 不在 TOOL_REGISTRY"
                )

    def test_c1_5_alias_modules_status_hidden(self):
        """C1-5: display=False 的模块 status=hidden。"""
        for m in MODULE_CATALOG:
            if not m.get("display", True):
                assert m.get("status") == "hidden", (
                    f"{m['key']} display=False 但 status={m['status']}，应为 hidden"
                )

    def test_c1_6_industry_rank_in_catalog_available(self):
        """C1-6: industry_rank 在 catalog 中且 status=available。"""
        ir = next((m for m in MODULE_CATALOG if m["key"] == "industry_rank"), None)
        assert ir is not None, "industry_rank 不在 MODULE_CATALOG"
        assert ir["status"] == "available"
        assert ir["display"] is True

    def test_c1_7_industry_rank_aliases_are_hidden(self):
        """C1-7: industry_ranking / peer_rank / industry_position 是 hidden alias。"""
        aliases = {"industry_ranking", "peer_rank", "industry_position"}
        catalog_map = {m["key"]: m for m in MODULE_CATALOG}
        for key in aliases:
            assert key in catalog_map, f"{key} 不在 MODULE_CATALOG"
            m = catalog_map[key]
            assert m["status"] == "hidden"
            assert m["display"] is False
            assert m["alias_of"] == "industry_rank"

    def test_c1_8_no_duplicate_keys(self):
        """C1-8: MODULE_CATALOG 无重复 key。"""
        keys = [m["key"] for m in MODULE_CATALOG]
        assert len(keys) == len(set(keys))

    def test_c1_9_seq_unique(self):
        """C1-9: 所有 seq 值唯一。"""
        seqs = [m["seq"] for m in MODULE_CATALOG]
        assert len(seqs) == len(set(seqs))

    def test_c1_10_display_counts(self):
        """C1-10: display=True 至少 13 个规范模块；display=False 至少 7 个 alias。"""
        display_true = [m for m in MODULE_CATALOG if m.get("display", True)]
        display_false = [m for m in MODULE_CATALOG if not m.get("display", True)]
        assert len(display_true) >= 13, f"display=True 只有 {len(display_true)} 个"
        assert len(display_false) >= 7, f"display=False 只有 {len(display_false)} 个"


# ═══════════════════════════════════════════════════════════════════════════
# C2 — /api/v1/modules 不返回 alias
# ═══════════════════════════════════════════════════════════════════════════

def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(compat_router)
    return app


class TestC2ModulesEndpoint:
    """GET /api/v1/modules 只返回 display=True 且 status != hidden 的模块。"""

    ALIAS_KEYS = {
        "quote_snapshot", "cashflow_health", "cashflow", "growth_metrics",
        "profit_quality", "operating_efficiency", "industry_ranking",
        "peer_rank", "industry_position",
    }

    def _call_modules(self):
        from app.aggregator.fundamentals_aggregator import FundamentalsAggregator
        mock_agg = MagicMock(spec=FundamentalsAggregator)
        # Use real list_modules()
        agg = FundamentalsAggregator()
        mock_agg.list_modules.return_value = agg.list_modules()

        with patch("app.routers.fundamentals_compat.get_aggregator", return_value=mock_agg), \
             patch("app.core.config.settings") as ms:
            ms.enable_akshare = False
            client = TestClient(_make_test_app())
            return client.get("/api/v1/modules").json()

    def test_c2_1_no_alias_keys_in_response(self):
        """C2-1: /api/v1/modules 返回列表中不含任何 alias key。"""
        modules = self._call_modules()
        returned_keys = {m["key"] for m in modules}
        overlap = returned_keys & self.ALIAS_KEYS
        assert not overlap, f"/api/v1/modules 返回了 alias: {overlap}"

    def test_c2_2_industry_rank_in_response(self):
        """C2-2: /api/v1/modules 包含 industry_rank。"""
        modules = self._call_modules()
        keys = {m["key"] for m in modules}
        assert "industry_rank" in keys

    def test_c2_3_no_hidden_status_in_response(self):
        """C2-3: /api/v1/modules 返回列表中无 status=hidden 条目。"""
        modules = self._call_modules()
        hidden = [m for m in modules if m.get("status") == "hidden"]
        assert not hidden, f"出现了 hidden 条目: {[m['key'] for m in hidden]}"

    def test_c2_4_response_count_reasonable(self):
        """C2-4: 返回模块数量 >= 13（规范模块数）。"""
        modules = self._call_modules()
        assert len(modules) >= 13


# ═══════════════════════════════════════════════════════════════════════════
# C3 — alias 路由仍可访问
# ═══════════════════════════════════════════════════════════════════════════

class TestC3AliasRoute:
    """alias key 通过 /api/v1/stock/{code}/modules/{alias} 仍可访问。"""

    def _get_module(self, module_id: str) -> dict:
        """通过 mock aggregator 访问模块路由，返回响应 JSON。"""
        envelope = ok_envelope(data={"series": [], "comment": "test", "source": "tushare"})
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=envelope)

        with patch("app.routers.fundamentals_compat.get_aggregator", return_value=mock_agg), \
             patch("app.core.config.settings") as ms:
            ms.enable_akshare = False
            client = TestClient(_make_test_app())
            resp = client.get(f"/api/v1/stock/600519/modules/{module_id}")
        return {"status_code": resp.status_code, "json": resp.json()}

    def test_c3_1_industry_ranking_alias(self):
        """C3-1: industry_ranking → industry_rank 路由可访问。"""
        result = self._get_module("industry_ranking")
        assert result["status_code"] == 200

    def test_c3_2_peer_rank_alias(self):
        """C3-2: peer_rank → industry_rank 路由可访问。"""
        result = self._get_module("peer_rank")
        assert result["status_code"] == 200

    def test_c3_3_cashflow_alias(self):
        """C3-3: cashflow → cashflow_quality 路由可访问。"""
        result = self._get_module("cashflow")
        assert result["status_code"] == 200

    def test_c3_4_growth_metrics_alias(self):
        """C3-4: growth_metrics → growth 路由可访问。"""
        result = self._get_module("growth_metrics")
        assert result["status_code"] == 200

    def test_c3_5_resolve_module_id_aliases(self):
        """C3-5: _resolve_module_id 正确解析所有 Phase 2B alias。"""
        assert _resolve_module_id("industry_ranking") == "industry_rank"
        assert _resolve_module_id("peer_rank") == "industry_rank"
        assert _resolve_module_id("industry_position") == "industry_rank"
        assert _resolve_module_id("growth_metrics") == "growth"
        assert _resolve_module_id("profit_quality") == "profitability"
        assert _resolve_module_id("operating_efficiency") == "operation_capability"

    def test_c3_6_canonical_key_unchanged(self):
        """C3-6: 规范 key 不被 alias 解析（passthrough）。"""
        assert _resolve_module_id("industry_rank") == "industry_rank"
        assert _resolve_module_id("growth") == "growth"
        assert _resolve_module_id("solvency") == "solvency"


# ═══════════════════════════════════════════════════════════════════════════
# C4 — ETL 缺失时 industry_rank 返回 partial=True
# ═══════════════════════════════════════════════════════════════════════════

class TestC4ETLGracefulDegradation:
    """ETL 未启用或 DB 表不存在时，industry_rank 工具返回 partial=True + reason。"""

    def test_c4_1_etl_disabled_returns_partial(self):
        """C4-1: ETL_ENABLED=false 时 fetch() 返回含 _partial_errors 的 dict。"""
        with patch("app.etl.db.etl_available", return_value=False):
            result = _run(IndustryRankTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "_partial_errors" in result
        errors = result["_partial_errors"]
        assert len(errors) > 0
        assert result["ranks"] == []

    def test_c4_2_table_not_exists_returns_partial(self):
        """C4-2: industry_rank_snapshot 表不存在时返回 partial。"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.etl.db.etl_available", return_value=True), \
             patch("app.core.database.AsyncSessionLocal", return_value=mock_session), \
             patch("app.etl.db.table_exists", AsyncMock(return_value=False)):
            result = _run(IndustryRankTool().fetch("CN", "600519"))

        assert "_partial_errors" in result
        assert result["ranks"] == []

    def test_c4_3_partial_errors_is_list(self):
        """C4-3: _partial_errors 始终是 list（不是 str）。"""
        with patch("app.etl.db.etl_available", return_value=False):
            result = _run(IndustryRankTool().fetch("CN", "600519"))
        assert isinstance(result["_partial_errors"], list)

    def test_c4_4_etl_available_check(self):
        """C4-4: etl_available() 读取 settings.etl_enabled。"""
        with patch("app.core.config.settings") as ms:
            ms.etl_enabled = False
            assert etl_available() is False
        with patch("app.core.config.settings") as ms:
            ms.etl_enabled = True
            assert etl_available() is True


# ═══════════════════════════════════════════════════════════════════════════
# C5 — industry_rank 不循环调用 Tushare
# ═══════════════════════════════════════════════════════════════════════════

class TestC5NoTushareLoop:
    """IndustryRankTool 在任何路径下都不调用 Tushare 的 per-stock 方法。"""

    def test_c5_1_no_tushare_calls_when_etl_disabled(self):
        """C5-1: ETL disabled 时 Tushare 方法 0 次调用。"""
        with patch("app.etl.db.etl_available", return_value=False), \
             patch("app.datasource.tushare_client.tushare_client.get_daily_basic") as mock_db, \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator") as mock_fi, \
             patch("app.datasource.tushare_client.tushare_client.get_balancesheet") as mock_bs:
            _run(IndustryRankTool().fetch("CN", "600519"))
        mock_db.assert_not_called()
        mock_fi.assert_not_called()
        mock_bs.assert_not_called()

    def test_c5_2_no_tushare_calls_when_table_missing(self):
        """C5-2: 表不存在时 Tushare 方法 0 次调用。"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.etl.db.etl_available", return_value=True), \
             patch("app.core.database.AsyncSessionLocal", return_value=mock_session), \
             patch("app.etl.db.table_exists", AsyncMock(return_value=False)), \
             patch("app.datasource.tushare_client.tushare_client.get_daily_basic") as mock_db:
            _run(IndustryRankTool().fetch("CN", "600519"))
        mock_db.assert_not_called()

    def test_c5_3_industry_rank_tool_no_tushare_import(self):
        """C5-3: industry_rank.py 不导入 tushare_client 的 get_daily_basic 等方法。"""
        import inspect
        import app.tools.fundamental.industry_rank as ir_module
        src = inspect.getsource(ir_module)
        # 不应直接调用 get_daily_basic / get_balancesheet / get_income 等 per-stock 方法
        assert "get_daily_basic(" not in src
        assert "get_balancesheet(" not in src
        assert "get_income(" not in src
        assert "get_fina_indicator(" not in src


# ═══════════════════════════════════════════════════════════════════════════
# C6 — higher_is_better 排序正确
# ═══════════════════════════════════════════════════════════════════════════

class TestC6HigherIsBetter:
    """compute_ranks_in_memory 对 higher_is_better 指标：值越大排名越前。"""

    def _make_rows(self, values: list[float | None]) -> list[dict]:
        return [
            {"ts_code": f"00{i:04d}.SZ", "industry": "白酒", "roe": v}
            for i, v in enumerate(values)
        ]

    def test_c6_1_highest_value_rank_1(self):
        """C6-1: ROE 最高的股票 rank_in_industry=1。"""
        rows = self._make_rows([10.0, 30.0, 20.0])
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["000001.SZ"]["rank_in_industry"] == 1  # 30.0

    def test_c6_2_lowest_value_last_rank(self):
        """C6-2: ROE 最低的股票排名最后。"""
        rows = self._make_rows([10.0, 30.0, 20.0])
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["000000.SZ"]["rank_in_industry"] == 3  # 10.0

    def test_c6_3_all_ranks_covered(self):
        """C6-3: 3 个股票排名 {1, 2, 3}。"""
        rows = self._make_rows([10.0, 30.0, 20.0])
        result = [r for r in compute_ranks_in_memory(rows, "roe", "higher_is_better") if r.get("roe") is not None]
        ranks = {r["rank_in_industry"] for r in result}
        assert ranks == {1, 2, 3}


# ═══════════════════════════════════════════════════════════════════════════
# C7 — lower_is_better 排序正确
# ═══════════════════════════════════════════════════════════════════════════

class TestC7LowerIsBetter:
    """compute_ranks_in_memory 对 lower_is_better：值越小排名越前（pe_ttm / debt_to_assets 等）。"""

    def _make_rows(self, pes: list[float | None]) -> list[dict]:
        return [
            {"ts_code": f"60{i:04d}.SH", "industry": "银行", "pe_ttm": v}
            for i, v in enumerate(pes)
        ]

    def test_c7_1_lowest_pe_rank_1(self):
        """C7-1: pe_ttm 最小的股票 rank_in_industry=1。"""
        rows = self._make_rows([15.0, 8.0, 25.0])
        result = compute_ranks_in_memory(rows, "pe_ttm", "lower_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["600001.SH"]["rank_in_industry"] == 1  # pe=8.0

    def test_c7_2_highest_pe_last_rank(self):
        """C7-2: pe_ttm 最大的股票排名最后。"""
        rows = self._make_rows([15.0, 8.0, 25.0])
        result = compute_ranks_in_memory(rows, "pe_ttm", "lower_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["600002.SH"]["rank_in_industry"] == 3  # pe=25.0

    def test_c7_3_debt_to_assets_lower_is_better(self):
        """C7-3: debt_to_assets 低排名前（偿债能力强）。"""
        rows = [
            {"ts_code": "A", "industry": "地产", "debt_to_assets": 80.0},
            {"ts_code": "B", "industry": "地产", "debt_to_assets": 40.0},
            {"ts_code": "C", "industry": "地产", "debt_to_assets": 60.0},
        ]
        result = compute_ranks_in_memory(rows, "debt_to_assets", "lower_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["B"]["rank_in_industry"] == 1  # 40.0 最低


# ═══════════════════════════════════════════════════════════════════════════
# C8 — 缺失值不参与排名
# ═══════════════════════════════════════════════════════════════════════════

class TestC8MissingValues:
    """value=None 的行不参与排名，rank_in_industry=None。"""

    def test_c8_1_none_excluded_from_rank(self):
        """C8-1: None 值的行 rank_in_industry=None。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 20.0},
            {"ts_code": "B", "industry": "X", "roe": None},
            {"ts_code": "C", "industry": "X", "roe": 10.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["B"]["rank_in_industry"] is None
        assert by_ts["A"]["rank_in_industry"] is not None

    def test_c8_2_peer_count_excludes_none(self):
        """C8-2: None 值不计入 peer_count。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 20.0},
            {"ts_code": "B", "industry": "X", "roe": None},
            {"ts_code": "C", "industry": "X", "roe": 10.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        # peer_count = 2（只有 A 和 C 参与）
        assert by_ts["A"]["peer_count"] == 2
        assert by_ts["C"]["peer_count"] == 2

    def test_c8_3_valid_rows_still_ranked(self):
        """C8-3: 有 None 行时，有效行仍然排名正确。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 30.0},
            {"ts_code": "B", "industry": "X", "roe": None},
            {"ts_code": "C", "industry": "X", "roe": 10.0},
            {"ts_code": "D", "industry": "X", "roe": 20.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["A"]["rank_in_industry"] == 1
        assert by_ts["D"]["rank_in_industry"] == 2
        assert by_ts["C"]["rank_in_industry"] == 3
        assert by_ts["B"]["rank_in_industry"] is None


# ═══════════════════════════════════════════════════════════════════════════
# C9 — peer_count 正确
# ═══════════════════════════════════════════════════════════════════════════

class TestC9PeerCount:
    """peer_count 等于行业内参与排名的有效样本数。"""

    def test_c9_1_peer_count_all_valid(self):
        """C9-1: 全部有效 → peer_count = total rows in industry。"""
        rows = [
            {"ts_code": f"A{i}", "industry": "白酒", "roe": float(i + 1)}
            for i in range(5)
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        for r in result:
            assert r["peer_count"] == 5

    def test_c9_2_peer_count_excludes_none(self):
        """C9-2: 2 个 None → peer_count = total - 2。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 10.0},
            {"ts_code": "B", "industry": "X", "roe": None},
            {"ts_code": "C", "industry": "X", "roe": 20.0},
            {"ts_code": "D", "industry": "X", "roe": None},
            {"ts_code": "E", "industry": "X", "roe": 15.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["A"]["peer_count"] == 3
        assert by_ts["C"]["peer_count"] == 3

    def test_c9_3_multi_industry_peer_count_independent(self):
        """C9-3: 多行业时 peer_count 各自独立计算。"""
        rows = [
            {"ts_code": "A1", "industry": "白酒", "roe": 10.0},
            {"ts_code": "A2", "industry": "白酒", "roe": 20.0},
            {"ts_code": "B1", "industry": "银行", "roe": 15.0},
            {"ts_code": "B2", "industry": "银行", "roe": 12.0},
            {"ts_code": "B3", "industry": "银行", "roe": 18.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["A1"]["peer_count"] == 2
        assert by_ts["B1"]["peer_count"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# C10 — percentile_in_industry 正确
# ═══════════════════════════════════════════════════════════════════════════

class TestC10Percentile:
    """percentile_in_industry = 1 - (rank - 1) / max(peer_count - 1, 1)"""

    def test_c10_1_rank1_percentile_1(self):
        """C10-1: 第 1 名 percentile = 1.0。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 30.0},
            {"ts_code": "B", "industry": "X", "roe": 10.0},
            {"ts_code": "C", "industry": "X", "roe": 20.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["A"]["percentile_in_industry"] == pytest.approx(1.0)

    def test_c10_2_last_rank_percentile_0(self):
        """C10-2: 最后一名 percentile ≈ 0.0（peer_count > 1）。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 30.0},
            {"ts_code": "B", "industry": "X", "roe": 10.0},
            {"ts_code": "C", "industry": "X", "roe": 20.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["B"]["percentile_in_industry"] == pytest.approx(0.0)

    def test_c10_3_single_stock_percentile_1(self):
        """C10-3: 只有 1 只股票时 percentile = 1.0（max(peer-1, 1) = 1, rank-1=0）。"""
        rows = [{"ts_code": "A", "industry": "X", "roe": 15.0}]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        assert result[0]["percentile_in_industry"] == pytest.approx(1.0)

    def test_c10_4_middle_rank_percentile(self):
        """C10-4: 3 只股票中间排名 percentile = 0.5。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": 30.0},  # rank 1 → 1.0
            {"ts_code": "B", "industry": "X", "roe": 20.0},  # rank 2 → 0.5
            {"ts_code": "C", "industry": "X", "roe": 10.0},  # rank 3 → 0.0
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["B"]["percentile_in_industry"] == pytest.approx(0.5)

    def test_c10_5_none_value_percentile_none(self):
        """C10-5: 缺失值 percentile=None。"""
        rows = [
            {"ts_code": "A", "industry": "X", "roe": None},
            {"ts_code": "B", "industry": "X", "roe": 20.0},
        ]
        result = compute_ranks_in_memory(rows, "roe", "higher_is_better")
        by_ts = {r["ts_code"]: r for r in result}
        assert by_ts["A"]["percentile_in_industry"] is None


# ═══════════════════════════════════════════════════════════════════════════
# C11 — ETL upsert SQL 生成
# ═══════════════════════════════════════════════════════════════════════════

class TestC11UpsertSQL:
    """build_upsert_sql 生成正确的 PostgreSQL INSERT ... ON CONFLICT SQL。"""

    def test_c11_1_sql_contains_on_conflict(self):
        """C11-1: 生成 SQL 含 ON CONFLICT 子句。"""
        rows = [{"ts_code": "600519.SH", "trade_date": "20260705", "close": 1800.0}]
        sql, _ = build_upsert_sql(
            table="etl_daily_basic",
            rows=rows,
            conflict_cols=["ts_code", "trade_date"],
            update_cols=["close"],
        )
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql

    def test_c11_2_sql_contains_table_name(self):
        """C11-2: 生成 SQL 含目标表名。"""
        rows = [{"ts_code": "600519.SH"}]
        sql, _ = build_upsert_sql(
            table="etl_stock_basic",
            rows=rows,
            conflict_cols=["ts_code"],
            update_cols=[],
        )
        # Even with empty update_cols, table name should appear
        assert "etl_stock_basic" in sql

    def test_c11_3_conflict_cols_in_sql(self):
        """C11-3: conflict_cols 出现在 ON CONFLICT 括号内。"""
        rows = [{"ts_code": "A", "end_date": "20251231", "roe": 15.0}]
        sql, _ = build_upsert_sql(
            table="etl_fina_indicator",
            rows=rows,
            conflict_cols=["ts_code", "end_date"],
            update_cols=["roe"],
        )
        assert "ts_code, end_date" in sql or "ts_code,end_date" in sql.replace(" ", "")

    def test_c11_4_update_excluded_in_sql(self):
        """C11-4: update_cols 使用 EXCLUDED.col 格式。"""
        rows = [{"ts_code": "A", "trade_date": "20260705", "pe_ttm": 25.0}]
        sql, _ = build_upsert_sql(
            table="etl_daily_basic",
            rows=rows,
            conflict_cols=["ts_code", "trade_date"],
            update_cols=["pe_ttm"],
        )
        assert "EXCLUDED.pe_ttm" in sql

    def test_c11_5_empty_rows_returns_empty(self):
        """C11-5: 空 rows 返回 ('', [])。"""
        sql, rows = build_upsert_sql(
            table="etl_stock_basic",
            rows=[],
            conflict_cols=["ts_code"],
            update_cols=["name"],
        )
        assert sql == ""
        assert rows == []

    def test_c11_6_industry_rank_snapshot_upsert_sql(self):
        """C11-6: industry_rank_snapshot 的 upsert SQL 包含 4 个 conflict 列。"""
        rows = [{
            "ts_code": "600519.SH", "trade_date": "20260705",
            "end_date": "20251231", "industry": "白酒",
            "metric": "roe", "value": 30.0,
            "rank_in_industry": 3, "peer_count": 42,
            "percentile_in_industry": 0.951,
            "direction": "higher_is_better",
            "source_table": "etl_fina_indicator",
            "generated_at": "2026-07-05",
        }]
        sql, _ = build_upsert_sql(
            table="industry_rank_snapshot",
            rows=rows,
            conflict_cols=["ts_code", "trade_date", "end_date", "metric"],
            update_cols=["value", "rank_in_industry", "peer_count", "percentile_in_industry"],
        )
        assert "industry_rank_snapshot" in sql
        assert "ON CONFLICT" in sql
        assert "metric" in sql


# ═══════════════════════════════════════════════════════════════════════════
# C12 — 全量回归（Phase 1/2A tests 不破坏）
# ═══════════════════════════════════════════════════════════════════════════

class TestC12Regression:
    """Phase 2B 不破坏 Phase 1/2A 的测试和接口。"""

    def test_c12_1_phase15_tools_still_in_registry(self):
        """C12-1: Phase 1.5 核心 key 仍在 TOOL_REGISTRY。"""
        phase15_keys = {"snapshot", "financial_summary", "valuation", "dupont", "cashflow_quality"}
        for key in phase15_keys:
            assert key in TOOL_REGISTRY, f"{key} 不在 TOOL_REGISTRY"

    def test_c12_2_phase2a_tools_still_in_registry(self):
        """C12-2: Phase 2A 核心 key 仍在 TOOL_REGISTRY。"""
        phase2a_keys = {
            "growth", "profitability", "expense_analysis", "asset_structure",
            "solvency", "operation_capability", "capital_occupation",
        }
        for key in phase2a_keys:
            assert key in TOOL_REGISTRY, f"{key} 不在 TOOL_REGISTRY"

    def test_c12_3_industry_rank_in_registry(self):
        """C12-3: industry_rank 已注册到 TOOL_REGISTRY。"""
        assert "industry_rank" in TOOL_REGISTRY
        from app.tools.fundamental.industry_rank import IndustryRankTool
        assert TOOL_REGISTRY["industry_rank"] is IndustryRankTool

    def test_c12_4_catalog_display_true_count(self):
        """C12-4: display=True 的规范模块数量正确（>= 26，Phase 2C 后扩展）。"""
        canonical = [m for m in MODULE_CATALOG if m.get("display", True) and m.get("status") != "hidden"]
        assert len(canonical) >= 26, f"display=True 模块数量期望 >= 26，实际 {len(canonical)}"

    def test_c12_5_catalog_hidden_alias_count(self):
        """C12-5: display=False 的 alias 数量 >= 7（Phase 1.5 + 2A + 2B alias）。"""
        aliases = [m for m in MODULE_CATALOG if not m.get("display", True)]
        assert len(aliases) >= 7, f"alias 数量期望 >= 7，实际 {len(aliases)}"

    def test_c12_6_ai_requires_llm_true(self):
        """C12-6: ai_analysis requires_llm=True（其余均 False）。"""
        catalog = {m["key"]: m for m in MODULE_CATALOG}
        assert catalog["ai_analysis"]["requires_llm"] is True
        for m in MODULE_CATALOG:
            if m["key"] != "ai_analysis":
                assert m["requires_llm"] is False, f"{m['key']} requires_llm 应为 False"

    def test_c12_7_industry_rank_envelope_structure(self):
        """C12-7: industry_rank partial 响应通过 build_api_response 格式正确。"""
        partial_data = {
            "symbol": "600519", "ts_code": "600519.SH",
            "industry": None, "trade_date": None, "end_date": None,
            "ranks": [], "source": "unavailable",
        }
        env = ok_envelope(data=partial_data, partial_errors=["ETL 未启用"])
        resp = build_api_response(
            env, market="CN", symbol="600519", ts_code="600519.SH",
            module_key="industry_rank", module_name="行业排名",
        )
        assert isinstance(resp["errors"], list)
        assert resp["partial"] is True
        for field in ("market", "symbol", "ts_code", "module_key", "data", "errors", "partial"):
            assert field in resp
