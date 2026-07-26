from __future__ import annotations

import errno
import sys
from types import SimpleNamespace

import pytest

from app.datasource.baostock_session_manager import (
    BaoStockBatchAborted,
    run_baostock_financial_batch,
    run_provider_subprocess,
)


class _FakeResult:
    fields = ["code", "pubDate", "statDate", "value"]
    error_code = "0"

    def __init__(self) -> None:
        self._done = False

    def next(self):
        if self._done:
            return False
        self._done = True
        return True

    def get_row_data(self):
        return ["sh.600519", "2025-04-01", "2024-12-31", "1.0"]


def _parse_rows(rs):
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(dict(zip(rs.fields, rs.get_row_data())))
    return rows


def test_d6_2_baostock_batch_login_logout_once(monkeypatch, capsys):
    calls = {"login": 0, "logout": 0, "query": 0}

    def _query(**kwargs):
        calls["query"] += 1
        return _FakeResult()

    fake = SimpleNamespace(
        login=lambda: (calls.__setitem__("login", calls["login"] + 1), print("login success")),
        logout=lambda: calls.__setitem__("logout", calls["logout"] + 1),
        query_profit_data=_query,
        query_growth_data=_query,
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)

    by_year, query_count, endpoints, stats = run_baostock_financial_batch(
        bs_code="sh.600519",
        year_quarters=[(2024, 4), (2023, 4)],
        table_fns={"profit": "query_profit_data", "growth": "query_growth_data"},
        parse_rows=_parse_rows,
    )
    assert stats["login_count"] == 1
    assert stats["logout_count"] == 1
    assert calls == {"login": 1, "logout": 1, "query": 4}
    assert query_count == 4
    assert endpoints == {"profit": 2, "growth": 2}
    assert sorted(by_year) == [2023, 2024]
    captured = capsys.readouterr()
    assert "%" not in captured.out
    assert "it/s" not in captured.out
    assert "████" not in captured.out


def test_d6_2_baostock_ebadf_aborts_remaining_queries(monkeypatch):
    calls = {"login": 0, "logout": 0, "query": 0}

    def _query(**kwargs):
        calls["query"] += 1
        if calls["query"] == 2:
            raise OSError(errno.EBADF, "Bad file descriptor")
        return _FakeResult()

    fake = SimpleNamespace(
        login=lambda: calls.__setitem__("login", calls["login"] + 1),
        logout=lambda: calls.__setitem__("logout", calls["logout"] + 1),
        query_profit_data=_query,
        query_growth_data=_query,
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)

    with pytest.raises(BaoStockBatchAborted) as exc:
        run_baostock_financial_batch(
            bs_code="sh.600519",
            year_quarters=[(2024, 4), (2023, 4), (2022, 4)],
            table_fns={"profit": "query_profit_data", "growth": "query_growth_data"},
            parse_rows=_parse_rows,
        )
    assert calls["login"] == 1
    assert calls["logout"] == 1
    assert calls["query"] == 2
    assert exc.value.skipped_query_count == 4


def test_d6_2_subprocess_runner_nonzero_returns_provider_unavailable(monkeypatch):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=9, stdout="", stderr="native abort")

    monkeypatch.setattr("app.datasource.baostock_session_manager.subprocess.run", _fake_run)
    result = run_provider_subprocess({"provider": "baostock", "operation": "annual_history"})
    assert result["ok"] is False
    assert result["error_code"] == "provider_unavailable"
    assert result["exit_code"] == 9


def test_d6_2_subprocess_runner_success(monkeypatch):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "provider": "baostock", "results": {"2024": {}}}',
            stderr="",
        )

    monkeypatch.setattr("app.datasource.baostock_session_manager.subprocess.run", _fake_run)
    result = run_provider_subprocess({"provider": "baostock", "operation": "annual_history"})
    assert result["ok"] is True
    assert result["provider"] == "baostock"
    assert result["results"] == {"2024": {}}


def test_d6_2_subprocess_runner_timeout_bubbles_as_timeout(monkeypatch):
    import subprocess

    def _fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="worker", timeout=20)

    monkeypatch.setattr("app.datasource.baostock_session_manager.subprocess.run", _fake_run)
    result = run_provider_subprocess({"provider": "baostock", "operation": "annual_history"})
    assert result["ok"] is False
    assert result["error_code"] == "provider_unavailable"
    assert result["timeout"] == 20.0
