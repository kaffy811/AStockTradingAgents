"""
backend/scripts/company_v2_cross_stock_acceptance.py — Phase 6T-E/6T-E1 跨股票真实验收

两阶段模式（Phase 6T-E1）：
- --mode fast：8 股 annual full-history，不跑全部 quarterly、不跑 CNINFO，
  输出每只股票 provider_calls 与耗时；
- --mode deep：代表股票 quarterly（默认最近 5 年）+ CNINFO discovery + payload 对比。

可靠性：
- --per-symbol-timeout（默认 180s）：单股票硬超时，超时记 structured timeout 并继续；
- checkpoint/resume：已完成股票写入 <out-json>.checkpoint.json，重跑自动跳过。

不使用 mock；provider 失败/超时如实记录，不伪造结果。

用法示例：
backend/.venv/bin/python backend/scripts/company_v2_cross_stock_acceptance.py \
  --mode fast --symbols 600519,... --period annual --history true --cninfo false \
  --per-symbol-timeout 180 --out-json ... --out-md ...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _parse_bool(v: str | bool) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _empty_result(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "stage": "initialized",
        "stage_elapsed_ms": 0,
        "performance_progress": {
            "provider_calls_completed": 0,
            "provider_calls_planned": 0,
            "years_completed": [],
            "current_year": None,
            "current_quarter": None,
            "modules_completed": [],
            "cache_hits": 0,
            "last_successful_operation": "",
        },
        "provider_call_accounting": {
            "planned_calls": 0,
            "actual_calls": 0,
            "calls_by_endpoint": {},
            "duplicate_calls_avoided": 0,
        },
        "deep_chart_gate_status": "not_evaluated",
        "deep_chart_gate_reason": "",
        "chart_contract_regression": False,
        "deep_history_gate_status": "not_evaluated",
        "deep_history_gate_reason": "",
        "company_profile_ok": False,
        "stock_basic_ok": False,
        "list_date": "",
        "history_modules_ok": 0,
        "annual_rows_by_module": {},
        "quarterly_rows_by_module": {},
        "quarterly_range": "",
        "history_completeness": {},
        "history_truncated": None,
        "history_range_label": "",
        "chart_contract_valid": True,
        "invalid_chart_contracts": [],
        "cninfo_reports_count": None,
        "cninfo_status": "skipped",
        "provider_calls": None,
        "login_batches": None,
        "years_from_cache": None,
        "years_fetched": None,
        "cache_hit": False,
        "elapsed_ms": 0,
        "warm_latency_ms": None,
        "response_size_bytes": 0,
        "page_profile_size_bytes": None,
        "debug_profile_size_bytes": None,
        "baostock_aggregate_calls": None,
        "timeout": False,
        "blocking_issues": [],
        "warnings": [],
        "final_status": "failed",
    }


async def accept_symbol(
    symbol: str,
    *,
    period: str,
    quarterly_years: int,
    run_cninfo: bool,
    run_payload_compare: bool,
    financial_timeout: int = 180,
    cninfo_timeout: int = 60,
    stage_writer=None,
) -> dict[str, Any]:
    from app.services.company_v2_history_completeness_audit import audit_symbol_history
    from app.services.company_v2_history_service import build_company_history_dashboard
    from app.services.company_v2_response_profile import apply_response_profile
    from app.services.company_v2_stock_basic_service import get_stock_basic

    out = _empty_result(symbol)
    requested_window: dict[str, Any] | None = None
    if period == "quarterly":
        from app.services.company_v2_period_classifier import resolve_quarterly_window
        requested_window = resolve_quarterly_window(date.today(), years=quarterly_years)
        expected_periods = requested_window.get("expected_periods") or []
        out["quarterly_range"] = f"{expected_periods[0]}—{expected_periods[-1]}" if expected_periods else ""
        out["performance_progress"].update({
            "provider_calls_planned": len(requested_window.get("valid_quarters") or []) * 6,
            "current_year": requested_window.get("start_year"),
            "current_quarter": 1,
            "last_successful_operation": "quarterly_window_resolved",
        })
        out["provider_call_accounting"]["planned_calls"] = len(requested_window.get("valid_quarters") or []) * 6
        out["provider_calls"] = 0
        out["stage"] = "session_login"
        if stage_writer:
            stage_writer(out)

    # 1. stock basic
    try:
        basic = await get_stock_basic(symbol)
        out["stock_basic_ok"] = bool(basic.get("symbol"))
        out["company_profile_ok"] = bool(basic.get("company_name"))
        out["list_date"] = basic.get("list_date") or ""
        if not basic.get("company_name"):
            out["warnings"].append("company_name_missing")
        out["performance_progress"]["last_successful_operation"] = "stock_basic"
        if stage_writer:
            stage_writer(out)
    except Exception as exc:
        out["blocking_issues"].append(f"stock_basic_failed:{str(exc)[:120]}")

    # 2. 历史（fast=annual 上市以来；deep=quarterly 最近 N 年）
    print(f"[acceptance] {symbol} phase=history period={period} ...", flush=True)
    t0 = time.perf_counter()
    out["stage"] = "quarterly_fetch" if period == "quarterly" else "annual_fetch"
    if stage_writer:
        stage_writer(out)
    kwargs: dict[str, Any] = {"period": period}
    if period == "quarterly" and requested_window:
        kwargs["end_year"] = requested_window["end_year"]
    try:
        dashboard = await asyncio.wait_for(
            build_company_history_dashboard("CN", symbol, **kwargs),
            timeout=financial_timeout,
        )
    except asyncio.TimeoutError:
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        out["stage_elapsed_ms"] = out["elapsed_ms"]
        out["timeout"] = True
        out["blocking_issues"].append(f"financial_timeout_exceeded:{financial_timeout}s")
        out["blocking_issues"].append(f"per_symbol_timeout_exceeded:{financial_timeout}s")
        out["cninfo_status"] = "not_run_due_to_financial_timeout"
        out["deep_history_gate_status"] = "not_evaluated"
        out["deep_history_gate_reason"] = "financial_timeout"
        out["deep_chart_gate_status"] = "not_evaluated"
        out["deep_chart_gate_reason"] = "financial_timeout"
        out["performance_progress"]["last_successful_operation"] = "financial_timeout"
        out["final_status"] = "failed"
        if stage_writer:
            stage_writer(out)
        return out
    except Exception as exc:
        out["blocking_issues"].append(f"history_dashboard_failed:{str(exc)[:150]}")
        return out
    out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    perf = dashboard.get("performance_summary") or {}
    out["response_size_bytes"] = perf.get("response_size_bytes", 0)
    out["baostock_aggregate_calls"] = perf.get("baostock_aggregate_calls")
    out["provider_calls"] = perf.get("provider_calls")
    out["login_batches"] = perf.get("login_batches")
    out["years_from_cache"] = perf.get("years_from_cache")
    out["years_fetched"] = perf.get("years_fetched")
    out["cache_hit"] = bool(perf.get("cache_hit"))
    out["performance_progress"].update({
        "provider_calls_completed": perf.get("provider_calls", 0),
        "provider_calls_planned": perf.get("provider_calls_planned", perf.get("planned_calls", 0)),
        "years_completed": perf.get("years_completed", []) or (
            list(range(requested_window["start_year"], requested_window["end_year"] + 1))
            if requested_window else []
        ),
        "current_year": requested_window["end_year"] if requested_window else None,
        "current_quarter": 4 if requested_window else None,
        "cache_hits": perf.get("years_from_cache", 0),
        "last_successful_operation": "financial_dashboard",
    })
    out["provider_call_accounting"] = {
        "planned_calls": perf.get("planned_calls", perf.get("provider_calls_planned", 0)),
        "actual_calls": perf.get("actual_calls", perf.get("provider_calls", 0)),
        "calls_by_endpoint": perf.get("calls_by_endpoint", {}),
        "duplicate_calls_avoided": perf.get("duplicate_calls_avoided", 0),
    }
    out["history_truncated"] = dashboard.get("history_truncated")
    out["history_range_label"] = dashboard.get("history_range_label", "")

    modules = dashboard.get("modules") or {}
    out["history_modules_ok"] = sum(1 for m in modules.values() if m.get("data_success"))
    for mk, mdata in modules.items():
        rows = mdata.get("history") or []
        annual_count = sum(1 for r in rows if str(r.get("period") or "").endswith("12-31"))
        if period == "annual":
            out["annual_rows_by_module"][mk] = len(rows)
        else:
            out["quarterly_rows_by_module"][mk] = len(rows)
            out["annual_rows_by_module"][mk] = annual_count
        validation = mdata.get("chart_contract_validation") or {}
        if not validation.get("valid", True):
            out["chart_contract_valid"] = False
            out["invalid_chart_contracts"].append({mk: validation.get("issues")})
    if period == "quarterly":
        quarterly_periods = [
            str(r.get("period") or "")
            for mdata in modules.values()
            for r in (mdata.get("history") or [])
            if str(r.get("period") or "").endswith(("-03-31", "-06-30", "-09-30", "-12-31"))
        ]
        if quarterly_periods:
            out["quarterly_range"] = f"{min(quarterly_periods)}—{max(quarterly_periods)}"

    if out["history_modules_ok"] == 0:
        out["blocking_issues"].append("provider_unavailable:no_module_returned_history")

    # 3. 完整性审计
    audit = audit_symbol_history(symbol, dashboard)
    out["history_completeness"] = {
        mk: {
            "status": a["status"],
            "rows_count": a["rows_count"],
            "completeness_pct": a["completeness_pct"],
            "missing_periods_count": len(a["missing_periods"]),
            "duplicate_period_count": a["duplicate_period_count"],
            "invalid_period_count": a["invalid_period_count"],
            "future_periods": a["future_periods"],
            "pre_listing_periods": a["pre_listing_periods"],
            "latest_matches_history": a["latest_matches_history"],
            "period_order_valid": a["period_order_valid"],
            "start_period": a["start_period"],
            "end_period": a["end_period"],
        }
        for mk, a in audit["modules"].items()
    }
    for mk, a in audit["modules"].items():
        if a["status"] == "fail":
            out["blocking_issues"].append(f"history_audit_fail:{mk}")
        elif a["status"] == "warning" and a["rows_count"] > 0:
            out["warnings"].append(f"history_audit_warning:{mk}")
    out["stage"] = "chart_validation"
    out["deep_history_gate_status"] = "failed" if any(
        b.startswith("history_audit_fail") for b in out["blocking_issues"]
    ) else "passed"
    out["deep_chart_gate_status"] = "passed" if out["chart_contract_valid"] else "failed"
    out["deep_chart_gate_reason"] = "" if out["chart_contract_valid"] else "chart_contract_failed"
    out["chart_contract_regression"] = not out["chart_contract_valid"]
    out["performance_progress"]["modules_completed"] = list(modules.keys())
    out["performance_progress"]["last_successful_operation"] = "chart_validation"
    if stage_writer:
        stage_writer(out)

    # 4. page/debug payload 对比（deep）
    if run_payload_compare:
        print(f"[acceptance] {symbol} phase=payload_compare ...", flush=True)
        out["stage"] = "payload_compare"
        if stage_writer:
            stage_writer(out)
        t1 = time.perf_counter()
        try:
            async def _payload_compare() -> None:
                from app.services.company_v2_debug_service import company_v2_debug_service
                full = await company_v2_debug_service.build_full(
                    "CN", symbol,
                    include_raw=False, providers=None, force_refresh=False,
                    max_raw_chars=20000, db=None,
                    history=True, period="annual",
                )
                out["warm_latency_ms"] = int((time.perf_counter() - t1) * 1000)
                debug_payload = apply_response_profile(full, "debug")
                page_payload = apply_response_profile(full, "page")
                out["debug_profile_size_bytes"] = len(
                    json.dumps(debug_payload, ensure_ascii=False, default=str).encode("utf-8"))
                out["page_profile_size_bytes"] = len(
                    json.dumps(page_payload, ensure_ascii=False, default=str).encode("utf-8"))
            await asyncio.wait_for(_payload_compare(), timeout=60)
            out["performance_progress"]["last_successful_operation"] = "payload_compare"
        except asyncio.TimeoutError:
            out["warnings"].append("payload_compare_timeout:60s")
        except Exception as exc:
            out["warnings"].append(f"debug_full_measure_failed:{str(exc)[:120]}")
        if stage_writer:
            stage_writer(out)

    out["stage"] = "artifact_write"
    out["performance_progress"]["last_successful_operation"] = "financial_stage_artifact_write"
    if stage_writer:
        stage_writer(out)

    # 5. CNINFO 年报发现（deep）
    if run_cninfo:
        print(f"[acceptance] {symbol} phase=cninfo ...", flush=True)
        out["stage"] = "cninfo_discovery"
        if stage_writer:
            stage_writer(out)
        try:
            async def _discover_cninfo() -> None:
                from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent
                current_year = date.today().year
                discovery = await cninfo_report_discovery_agent.discover(
                    "CN", symbol,
                    start_year=current_year - 3, end_year=current_year - 1,
                    report_types=["annual"],
                )
                reports = discovery.get("reports") or []
                out["cninfo_reports_count"] = len(reports)
                recent = [r for r in reports if (r.get("report_year") or 0) >= current_year - 2]
                urls_ok = all(
                    str(r.get("pdf_url") or "").startswith("http")
                    and "cninfo.com.cn" in str(r.get("pdf_url") or "")
                    for r in reports if r.get("pdf_url")
                )
                no_summary = all(not r.get("is_summary") for r in reports)
                if recent and urls_ok and no_summary:
                    out["cninfo_status"] = "success"
                elif reports:
                    out["cninfo_status"] = "partial"
                    out["warnings"].append("cninfo_recent_annual_missing_or_url_issue")
                else:
                    out["cninfo_status"] = "failed"
                    out["warnings"].append("cninfo_no_reports_found")
            await asyncio.wait_for(_discover_cninfo(), timeout=cninfo_timeout)
            out["performance_progress"]["last_successful_operation"] = "cninfo_discovery"
        except asyncio.TimeoutError:
            out["cninfo_status"] = "timeout"
            out["warnings"].append(f"cninfo_timeout:{cninfo_timeout}s")
        except Exception as exc:
            out["cninfo_status"] = "failed"
            out["warnings"].append(f"cninfo_exception:{str(exc)[:120]}")
        if stage_writer:
            stage_writer(out)

    if out["blocking_issues"]:
        out["final_status"] = "failed"
    elif out["warnings"]:
        out["final_status"] = "warning"
    else:
        out["final_status"] = "passed"
    return out


def _gates(
    per_symbol: list[dict[str, Any]],
    *,
    mode: str,
    run_cninfo: bool,
    period: str,
) -> dict[str, Any]:
    total = len(per_symbol)
    timed_out = [s for s in per_symbol if s.get("timeout")]
    completed = [s for s in per_symbol if not s.get("timeout")]

    no_audit_fail = all(
        not any(b.startswith("history_audit_fail") for b in s["blocking_issues"])
        for s in completed
    )
    multi_annual = sum(
        1 for s in completed
        if max([*s["annual_rows_by_module"].values(), 0]) >= 2
    )
    history_gate = (
        bool(completed)
        and no_audit_fail
        and not timed_out
        and multi_annual >= min(6, total)
        and all(s["history_modules_ok"] > 0 for s in completed)
    )
    chart_gate = bool(completed) and all(s["chart_contract_valid"] for s in completed)
    chart_not_evaluated = bool(timed_out) and not any(
        not s.get("chart_contract_valid", True) for s in completed
    )
    history_not_evaluated = bool(timed_out) and not any(
        any(b.startswith("history_audit_fail") for b in s["blocking_issues"])
        for s in completed
    )

    if run_cninfo:
        cninfo_ok = sum(1 for s in completed if s["cninfo_status"] == "success")
        cninfo_gate = cninfo_ok >= max(len(completed) - 1, 1)
    else:
        cninfo_gate = None  # 本阶段未执行

    # Performance Gate（6T-E1 调用次数门槛）
    call_threshold = 130 if period == "annual" else 130  # BaoStock 仅支持按(年,季)查询：年批×6表
    perf_checks = []
    for s in completed:
        calls = s.get("provider_calls")
        perf_checks.append(
            (calls is None or calls <= call_threshold)
            and (s.get("login_batches") is None or s["login_batches"] <= 3)
            and (s.get("baostock_aggregate_calls") or 0) <= 1
            and s["elapsed_ms"] <= 180000
        )
    performance_gate = bool(completed) and all(perf_checks) and not timed_out

    return {
        "mode": mode,
        "symbols_total": total,
        "symbols_passed": sum(1 for s in per_symbol if s["final_status"] == "passed"),
        "symbols_warning": sum(1 for s in per_symbol if s["final_status"] == "warning"),
        "symbols_failed": sum(1 for s in per_symbol if s["final_status"] == "failed"),
        "symbols_timeout": len(timed_out),
        "history_gate_passed": history_gate,
        "chart_gate_passed": chart_gate,
        "deep_history_gate_status": "not_evaluated" if history_not_evaluated else ("passed" if history_gate else "failed"),
        "deep_chart_gate_status": "not_evaluated" if chart_not_evaluated else ("passed" if chart_gate else "failed"),
        "deep_chart_gate_reason": "financial_timeout" if chart_not_evaluated else "",
        "chart_contract_regression": any(not s.get("chart_contract_valid", True) for s in completed),
        "cninfo_gate_passed": cninfo_gate,
        "performance_gate_passed": performance_gate,
        "phase_gate_passed": history_gate and chart_gate and performance_gate
        and (cninfo_gate is not False),
    }


def _markdown(per_symbol: list[dict[str, Any]], gates: dict[str, Any]) -> str:
    lines = [
        f"# Phase 6T-E1 跨股票真实验收报告（mode={gates['mode']}）",
        "",
        f"生成日期：{date.today().isoformat()}",
        "",
        "## Gates",
        "",
        f"- history_gate_passed: **{gates['history_gate_passed']}**",
        f"- chart_gate_passed: **{gates['chart_gate_passed']}**",
        f"- cninfo_gate_passed: **{gates['cninfo_gate_passed']}**",
        f"- performance_gate_passed: **{gates['performance_gate_passed']}**",
        f"- phase_gate_passed: **{gates['phase_gate_passed']}**",
        "",
        f"symbols: {gates['symbols_passed']} passed / {gates['symbols_warning']} warning / "
        f"{gates['symbols_failed']} failed / {gates['symbols_timeout']} timeout",
        "",
        "## Per-symbol",
        "",
        "| symbol | list_date | modules_ok | annual rows(max) | quarterly rows(max) | provider_calls | logins | cache | elapsed ms | range label | cninfo | status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in per_symbol:
        max_annual = max([*s["annual_rows_by_module"].values(), 0])
        max_quarterly = max([*s["quarterly_rows_by_module"].values(), 0])
        lines.append(
            f"| {s['symbol']} | {s['list_date'] or '—'} | {s['history_modules_ok']} "
            f"| {max_annual} | {max_quarterly or '—'} "
            f"| {s['provider_calls'] if s['provider_calls'] is not None else '—'} "
            f"| {s['login_batches'] if s['login_batches'] is not None else '—'} "
            f"| {'hit' if s['cache_hit'] else 'cold'} | {s['elapsed_ms']} "
            f"| {s['history_range_label'] or '—'} | {s['cninfo_status']} "
            f"| {'TIMEOUT' if s.get('timeout') else s['final_status']} |"
        )
    lines += ["", "## Blocking issues / warnings", ""]
    for s in per_symbol:
        if s["blocking_issues"] or s["warnings"]:
            lines.append(f"### {s['symbol']}")
            for b in s["blocking_issues"]:
                lines.append(f"- BLOCKING: {b}")
            for w in s["warnings"]:
                lines.append(f"- warning: {w}")
            lines.append("")
    lines.append("> 本报告为真实数据验收结果，不构成投资建议。")
    return "\n".join(lines)


def _load_checkpoint(path: Path, mode: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("mode") == mode:
            done: dict[str, dict] = {}
            for s in data.get("symbols", []):
                if s.get("timeout") or s.get("blocking_issues") or s.get("final_status") in ("passed", "warning"):
                    done[s["symbol"]] = s
            return done
    except (ValueError, KeyError):
        pass
    return {}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--mode", default="fast", choices=["fast", "deep"])
    parser.add_argument("--period", default=None, help="annual|quarterly（默认由 mode 决定）")
    parser.add_argument("--quarterly-years", type=int, default=5)
    parser.add_argument("--history", default="true")
    parser.add_argument("--cninfo", default=None)
    parser.add_argument("--performance", default="true")
    parser.add_argument("--per-symbol-timeout", type=int, default=180)
    parser.add_argument("--financial-timeout", type=int, default=None)
    parser.add_argument("--cninfo-timeout", type=int, default=60)
    parser.add_argument("--payload-compare", default="false")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    mode = args.mode
    period = args.period or ("annual" if mode == "fast" else "quarterly")
    run_cninfo = _parse_bool(args.cninfo) if args.cninfo is not None else (mode == "deep")
    run_payload_compare = _parse_bool(args.payload_compare)
    financial_timeout = args.financial_timeout or args.per_symbol_timeout
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    out_json = Path(args.out_json)
    checkpoint_path = out_json.with_suffix(".checkpoint.json")
    done = {} if args.no_resume else _load_checkpoint(checkpoint_path, mode)

    per_symbol: list[dict[str, Any]] = []
    for sym in symbols:
        if sym in done:
            print(f"[acceptance] {sym} resume from checkpoint → {done[sym]['final_status']}", flush=True)
            per_symbol.append(done[sym])
            continue
        print(f"[acceptance] {sym} start (timeout={args.per_symbol_timeout}s)", flush=True)
        def _write_stage_checkpoint(partial: dict[str, Any]) -> None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(json.dumps(
                {
                    "mode": mode,
                    "symbols": [*per_symbol, partial],
                    "current_symbol": partial.get("symbol"),
                    "current_stage": partial.get("stage"),
                },
                ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        result = await accept_symbol(
            sym, period=period,
            quarterly_years=args.quarterly_years,
            run_cninfo=run_cninfo,
            run_payload_compare=run_payload_compare,
            financial_timeout=financial_timeout,
            cninfo_timeout=args.cninfo_timeout,
            stage_writer=_write_stage_checkpoint,
        )
        print(f"[acceptance] {sym} → {'TIMEOUT' if result.get('timeout') else result['final_status']} "
              f"(calls={result.get('provider_calls')}, elapsed={result['elapsed_ms']}ms, "
              f"cache={'hit' if result.get('cache_hit') else 'cold'})", flush=True)
        per_symbol.append(result)
        # checkpoint 每股票落盘
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps(
            {"mode": mode, "symbols": per_symbol},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    gates = _gates(per_symbol, mode=mode, run_cninfo=run_cninfo, period=period)
    output = {
        "generated_at": date.today().isoformat(),
        "mode": mode,
        "period": period,
        "quarterly_years": args.quarterly_years if period == "quarterly" else None,
        "gates": gates,
        "symbols": per_symbol,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    Path(args.out_md).write_text(_markdown(per_symbol, gates), encoding="utf-8")

    print(json.dumps(gates, ensure_ascii=False, indent=2))
    print(f"[acceptance] written: {out_json}")
    print(f"[acceptance] written: {args.out_md}")
    return 0 if gates["phase_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
