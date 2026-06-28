"""
C30.2.1 — Real DB E2E Report Persistence Acceptance Script.

Connects to the real development database and verifies the complete
report persistence chain end-to-end:

  Step 1: Create a test report via ReportRepository.create_report()
  Step 2: Verify it appears in list_reports() for same user
  Step 3: Verify it appears in get_report() for same user
  Step 4: Verify different user CANNOT read the report (user isolation)
  Step 5: Delete via delete_report()
  Step 6: Verify it is gone from list and get

Requirements:
  - DATABASE_URL env var (postgresql+asyncpg://...)
  - python scripts/e2e_c30_report_persistence.py

Exit codes:
  0 = all checks passed
  1 = one or more checks failed or connection error
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# ── make app package importable ───────────────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    _results.append((status, label))
    suffix = f"  ({detail})" if detail and not ok else (f"  → {detail}" if detail else "")
    print(f"  [{status}]  {label}{suffix}")
    return ok


# ── DB setup ──────────────────────────────────────────────────────────────────

async def _get_db_session():
    """Return a real AsyncSession connected to DATABASE_URL."""
    from app.core.database import engine, Base
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def run_e2e() -> bool:
    """Run the full E2E acceptance and return True if all checks pass."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.database import async_engine
    from app.repositories.report_repository import ReportRepository

    print("\n── C30.2.1 E2E Report Persistence Acceptance ───────────────────────────\n")

    report_id: uuid.UUID | None = None

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        # ── Resolve a real user_id (needed due to FK constraint) ───────────
        from sqlalchemy import text
        row = (await db.execute(text("SELECT id FROM app_users LIMIT 1"))).fetchone()
        if row is None:
            print("\n[SKIP] No users in DB — create a user account first, then re-run.\n")
            return True  # not a failure condition for CI
        owner_id    = row[0]
        stranger_id = uuid.uuid4()  # guaranteed not in DB
        print(f"  Using dev user: {str(owner_id)[:8]}...\n")

        repo = ReportRepository(db)

        # ── Step 1: Create ──────────────────────────────────────────────────
        print("Step 1: create_report()")
        try:
            report = await repo.create_report(
                user_id         = owner_id,
                market          = "CN",
                symbol          = "688146",
                stock_name      = "中船特气 [E2E test]",
                report_type     = "comprehensive",
                auto_saved      = True,
                analysis_scope  = "comprehensive",
                output_language = "zh-CN",
                report_md       = "## E2E Test Report\n\n这是 C30.2.1 E2E 验收测试生成的临时报告，可安全删除。",
                sections        = {"technical": "技术面测试内容", "fundamental": "基本面测试内容"},
                report_metadata = {"workflow_engine": "e2e_test", "test_run": True},
                warnings        = [],
                agents          = {"technical": {"status": "success", "message": None}},
            )
            report_id = report.id
            check("create_report returns AnalysisReport with id",
                  isinstance(report_id, uuid.UUID),
                  f"report_id={report_id}")
        except Exception as exc:
            check("create_report succeeded", False, str(exc))
            print("\n[ABORT] DB connection failed — is DATABASE_URL set and DB running?\n")
            return False

        # ── Step 2: List ───────────────────────────────────────────────────
        print("\nStep 2: list_reports() for owner")
        try:
            total, items = await repo.list_reports(owner_id)
            ids_in_list = {r.id for r in items}
            check("report appears in owner list",
                  report_id in ids_in_list,
                  f"total={total}, ids={[str(i)[:8] for i in ids_in_list]}")
            check("total >= 1", total >= 1, f"total={total}")
        except Exception as exc:
            check("list_reports succeeded", False, str(exc))

        # ── Step 3: Get detail ─────────────────────────────────────────────
        print("\nStep 3: get_report() for owner")
        try:
            detail = await repo.get_report(owner_id, report_id)
            check("get_report returns report for owner",
                  detail is not None,
                  f"report_id={str(report_id)[:8]}")
            if detail:
                check("report_md is non-empty", bool(detail.report_md))
                check("symbol matches", detail.symbol == "688146")
                check("auto_saved is True", detail.auto_saved is True)
        except Exception as exc:
            check("get_report succeeded", False, str(exc))

        # ── Step 4: User isolation ─────────────────────────────────────────
        print("\nStep 4: user isolation — stranger cannot read report")
        try:
            stranger_detail = await repo.get_report(stranger_id, report_id)
            check("stranger cannot read owner report",
                  stranger_detail is None,
                  f"expected None, got {stranger_detail}")
            total_stranger, items_stranger = await repo.list_reports(stranger_id)
            in_stranger_list = any(r.id == report_id for r in items_stranger)
            check("report not in stranger list", not in_stranger_list,
                  f"stranger total={total_stranger}")
        except Exception as exc:
            check("user isolation check succeeded", False, str(exc))

        # ── Step 5: Delete ─────────────────────────────────────────────────
        print("\nStep 5: delete_report()")
        try:
            deleted = await repo.delete_report(owner_id, report_id)
            check("delete_report returns True", deleted is True)

            # Stranger cannot delete (returns False)
            # (already deleted above; test False-on-not-found)
            false_delete = await repo.delete_report(stranger_id, report_id)
            check("stranger delete returns False (already gone)", false_delete is False)
        except Exception as exc:
            check("delete_report succeeded", False, str(exc))

        # ── Step 6: Verify gone ────────────────────────────────────────────
        print("\nStep 6: verify deleted report is gone")
        try:
            gone = await repo.get_report(owner_id, report_id)
            check("get_report returns None after delete", gone is None,
                  f"expected None, got {gone}")
            _, items_after = await repo.list_reports(owner_id)
            still_in_list = any(r.id == report_id for r in items_after)
            check("list_reports does not include deleted report", not still_in_list)
        except Exception as exc:
            check("post-delete verification succeeded", False, str(exc))

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for s, _ in _results if s == PASS)
    failed = sum(1 for s, _ in _results if s == FAIL)
    total  = len(_results)
    print(f"\n── {passed}/{total} passed", "🎉" if failed == 0 else f"  ({failed} FAILED)")
    print()
    return failed == 0


def main() -> int:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        # Try loading from .env
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_BACKEND_DIR, ".env"))
            database_url = os.environ.get("DATABASE_URL")
        except ImportError:
            pass

    if not database_url:
        print("\n[ERROR] DATABASE_URL not set. Set it via env var or .env file.\n"
              "  Example: DATABASE_URL=postgresql+asyncpg://user:pass@host/db "
              "python scripts/e2e_c30_report_persistence.py\n")
        return 1

    ok = asyncio.run(run_e2e())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
