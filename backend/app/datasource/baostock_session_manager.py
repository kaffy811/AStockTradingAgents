"""Canonical BaoStock session manager.

BaoStock keeps process-global socket state. All production calls that touch
`bs.login/query/logout` must go through this module so one batch owns the
session from login through logout.
"""
from __future__ import annotations

import errno
import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

_SESSION_LOCK = threading.RLock()


class BaoStockBatchAborted(RuntimeError):
    def __init__(self, message: str, *, skipped_query_count: int = 0) -> None:
        super().__init__(message)
        self.skipped_query_count = skipped_query_count


@contextmanager
def suppress_baostock_output():
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def is_baostock_fatal_error(exc: BaseException | str) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EBADF:
        return True
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return True
    text = str(exc)
    return any(
        marker in text
        for marker in (
            "Bad file descriptor",
            "[Errno 9]",
            "接收数据异常",
            "socket closed",
            "Connection reset",
        )
    )


def run_baostock_financial_batch(
    *,
    bs_code: str,
    year_quarters: list[tuple[int, int]],
    table_fns: dict[str, str],
    parse_rows,
) -> tuple[dict[int, dict[str, list[dict]]], int, dict[str, int], dict[str, Any]]:
    """Run one serialized BaoStock financial batch with exactly one login/logout."""
    import baostock as bs

    batch_id = str(uuid.uuid4())
    thread_id = threading.get_ident()
    started = time.monotonic()
    table_keys = tuple(table_fns.keys())
    stats: dict[str, Any] = {
        "batch_id": batch_id,
        "symbol": bs_code,
        "thread_id": thread_id,
        "start_monotonic": started,
        "end_monotonic": None,
        "login_count": 0,
        "query_count": 0,
        "successful_query_count": 0,
        "logout_count": 0,
        "skipped_query_count": 0,
        "state": "pending",
        "error": None,
    }
    by_year: dict[int, dict[str, list[dict]]] = {}
    calls_by_endpoint: dict[str, int] = {k: 0 for k in table_keys}
    total_planned = len(year_quarters) * len(table_keys)

    with _SESSION_LOCK:
        try:
            with suppress_baostock_output():
                bs.login()
            stats["login_count"] = 1
            stats["state"] = "active"

            for year, quarter in year_quarters:
                year_tables = by_year.setdefault(year, {k: [] for k in table_keys})
                for table_key, api_fn_name in table_fns.items():
                    api_fn = getattr(bs, api_fn_name, None)
                    if api_fn is None:
                        continue
                    try:
                        stats["query_count"] += 1
                        rs = api_fn(code=bs_code, year=year, quarter=quarter)
                        stats["successful_query_count"] += 1
                        calls_by_endpoint[table_key] = calls_by_endpoint.get(table_key, 0) + 1
                        if getattr(rs, "error_code", "0") not in ("0", 0):
                            err_msg = getattr(rs, "error_msg", "") or ""
                            if is_baostock_fatal_error(err_msg):
                                raise BaoStockBatchAborted(err_msg)
                        year_tables[table_key].extend(parse_rows(rs))
                    except Exception as exc:
                        if is_baostock_fatal_error(exc):
                            stats["state"] = "invalid"
                            stats["error"] = str(exc)[:300]
                            stats["skipped_query_count"] = max(
                                0, total_planned - int(stats["query_count"])
                            )
                            log.warning(
                                "BaoStock batch aborted batch_id=%s symbol=%s error=%s skipped=%s",
                                batch_id,
                                bs_code,
                                stats["error"],
                                stats["skipped_query_count"],
                            )
                            raise BaoStockBatchAborted(
                                str(exc),
                                skipped_query_count=int(stats["skipped_query_count"]),
                            ) from exc
                        log.debug("BaoStock query failed [%s %s %sQ%s]: %s", bs_code, table_key, year, quarter, exc)
            if stats["state"] != "invalid":
                stats["state"] = "completed"
        finally:
            try:
                with suppress_baostock_output():
                    bs.logout()
                stats["logout_count"] = 1
            except Exception as exc:
                if stats["state"] != "invalid":
                    stats["state"] = "logout_failed"
                    stats["error"] = str(exc)[:300]
            stats["end_monotonic"] = time.monotonic()

    return by_year, int(stats["successful_query_count"]), calls_by_endpoint, stats


def run_provider_subprocess(payload: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    """Run financial provider worker in an isolated Python subprocess."""
    worker = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "provider_workers", "financial_provider_worker.py")
    )
    safe_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "REDIS_URL", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}
    }
    try:
        proc = subprocess.run(
            [sys.executable, worker],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=safe_env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error_code": "provider_unavailable",
            "timeout": timeout,
            "stderr": str(exc)[:1000],
        }
    stderr = (proc.stderr or "")[:1000]
    if proc.returncode != 0:
        return {
            "ok": False,
            "error_code": "provider_unavailable",
            "exit_code": proc.returncode,
            "stderr": stderr,
        }
    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error_code": "provider_invalid_json", "stderr": stderr}
    if stderr:
        result.setdefault("stderr", stderr)
    return result


def run_with_baostock_lock(fn):
    """Run a synchronous BaoStock operation under the global session lock."""
    with _SESSION_LOCK:
        return fn()
