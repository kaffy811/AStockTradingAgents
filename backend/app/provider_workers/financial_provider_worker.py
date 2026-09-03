"""Isolated financial provider worker.

Reads one JSON payload from stdin and writes one JSON object to stdout.
No database/Redis/LLM secrets are required or read.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _json_out(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        provider = payload.get("provider")
        operation = payload.get("operation")
        if provider != "baostock" or operation != "annual_history":
            _json_out({"ok": False, "error_code": "unsupported_operation"})
            return 2

        from app.datasource.baostock_client import (  # noqa: PLC0415
            _BULK_TABLE_FNS,
            _parse_rows,
            _to_bs_code,
        )
        from app.datasource.baostock_session_manager import (  # noqa: PLC0415
            BaoStockBatchAborted,
            run_baostock_financial_batch,
        )

        symbol = str(payload.get("symbol") or "")
        ts_code = str(payload.get("ts_code") or symbol)
        bs_code = str(payload.get("bs_code") or _to_bs_code(ts_code))
        year_quarters = [
            (int(item[0]), int(item[1]))
            for item in (payload.get("year_quarters") or [])
        ]
        try:
            by_year, calls, calls_by_endpoint, stats = run_baostock_financial_batch(
                bs_code=bs_code,
                year_quarters=year_quarters,
                table_fns=_BULK_TABLE_FNS,
                parse_rows=_parse_rows,
            )
        except BaoStockBatchAborted as exc:
            _json_out({
                "ok": False,
                "error_code": "provider_unavailable",
                "error": str(exc)[:300],
                "skipped_query_count": exc.skipped_query_count,
            })
            return 3
        _json_out({
            "ok": True,
            "by_year": by_year,
            "calls": calls,
            "calls_by_endpoint": calls_by_endpoint,
            "batch_stats": stats,
        })
        return 0
    except Exception as exc:
        _json_out({"ok": False, "error_code": "worker_exception", "error": str(exc)[:300]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
