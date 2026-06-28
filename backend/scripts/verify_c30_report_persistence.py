"""
C30.1.6 — Report Persistence Acceptance Script.

Verifies the complete C30 report-persistence chain without requiring a running server:

  T01  AnalysisRunSnapshot has report_id field
  T02  MemoryAnalysisRunRegistry.update_status accepts report_id kwarg
  T03  RedisAnalysisRunRegistry has report_id read/write (import check)
  T04  RealtimeAnalysisRunner imports save_generated_report
  T05  LangGraphRealtimeRunner imports save_generated_report (C30.1.1)
  T06  GET /runs/{id} response includes report_id field
  T07  classify_intent is imported in chat_orchestrator (C30.1.4)
  T08  intent_detected SSE event emitted in process_message
  T09  Run ID not present in execute_create_analysis_run answer text (C30.1.3)
  T10  save_generated_report signature has auto_saved kwarg

Usage:
    cd backend
    python scripts/verify_c30_report_persistence.py
"""
from __future__ import annotations

import importlib
import inspect
import re
import sys

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(label: str, condition: bool) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    return condition


def main() -> int:
    results: list[bool] = []

    print("\n── C30 Report Persistence Acceptance ──────────────────────────────────\n")

    # T01: AnalysisRunSnapshot has report_id
    from app.services.run_registry_protocol import AnalysisRunSnapshot
    snap_fields = {f.name for f in AnalysisRunSnapshot.__dataclass_fields__.values()}
    results.append(check("T01  AnalysisRunSnapshot.report_id field exists", "report_id" in snap_fields))

    # T02: MemoryAnalysisRunRegistry.update_status accepts report_id
    from app.services.analysis_run_registry import MemoryAnalysisRunRegistry
    sig = inspect.signature(MemoryAnalysisRunRegistry.update_status)
    results.append(check("T02  MemoryAnalysisRunRegistry.update_status has report_id param",
                          "report_id" in sig.parameters))

    # T03: RedisAnalysisRunRegistry importable and has report_id handling
    try:
        import app.services.redis_run_registry as rrr_mod
        src = inspect.getsource(rrr_mod)
        results.append(check("T03  RedisAnalysisRunRegistry handles report_id", "report_id" in src))
    except Exception as exc:
        results.append(check(f"T03  RedisAnalysisRunRegistry import ({exc})", False))

    # T04: RealtimeAnalysisRunner imports save_generated_report
    import app.agents.realtime_analysis_runner as rar_mod
    src = inspect.getsource(rar_mod)
    results.append(check("T04  RealtimeAnalysisRunner imports save_generated_report",
                          "save_generated_report" in src))

    # T05: LangGraphRealtimeRunner imports save_generated_report (C30.1.1)
    import app.agents.langgraph_realtime_runner as lgr_mod
    src = inspect.getsource(lgr_mod)
    results.append(check("T05  LangGraphRealtimeRunner imports save_generated_report (C30.1.1)",
                          "save_generated_report" in src))

    # T06: GET /runs/{id} response schema includes report_id
    import app.routers.analysis as analysis_router_mod
    src = inspect.getsource(analysis_router_mod)
    results.append(check("T06  GET /runs/{id} response includes report_id",
                          "snap.report_id" in src or '"report_id": snap.report_id' in src))

    # T07: classify_intent imported in chat_orchestrator
    import app.agents.chat_orchestrator as orch_mod
    src = inspect.getsource(orch_mod)
    results.append(check("T07  classify_intent imported in chat_orchestrator (C30.1.4)",
                          "from app.agents.intent_decision_agent import classify_intent" in src))

    # T08: intent_detected SSE event emitted in process_message
    results.append(check("T08  intent_detected SSE event emitted in process_message",
                          '"intent_detected"' in src and "classify_intent" in src))

    # T09: Run ID not present in execute_create_analysis_run user-visible answer
    import app.agents.chat_tools.action_tools as at_mod
    at_src = inspect.getsource(at_mod)
    # Check that "Run ID" / "run_id" is NOT in the answer= string block of execute_create_analysis_run
    # We check that the literal f"Run ID：`{run_ref.run_id}`" is gone
    results.append(check("T09  Run ID removed from user-visible answer text (C30.1.3)",
                          "Run ID：`{run_ref.run_id}`" not in at_src))

    # T10: save_generated_report has auto_saved kwarg
    from app.agents.report_persistence import save_generated_report
    sig = inspect.signature(save_generated_report)
    results.append(check("T10  save_generated_report(run_ref, full_result, db, auto_saved=...) signature",
                          "auto_saved" in sig.parameters))

    passed = sum(results)
    total  = len(results)
    print(f"\n── {passed}/{total} passed ─────────────────────────────────────────────────\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
