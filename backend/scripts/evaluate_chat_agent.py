#!/usr/bin/env python3
"""
evaluate_chat_agent.py — Phase C10 Agent Evaluation Script.

Runs the C10 golden task test suite and generates a structured evaluation report
at docs/chat_agent_evaluation_report.md.

Usage:
    python backend/scripts/evaluate_chat_agent.py
    python backend/scripts/evaluate_chat_agent.py --output docs/my_report.md
    python backend/scripts/evaluate_chat_agent.py --suite all

Options:
    --output PATH     Output path for evaluation report (default: docs/chat_agent_evaluation_report.md)
    --suite SUITE     Test suite to run: golden | manifest | all (default: golden)
    --verbose         Show full pytest output

The script exits with code 0 if all tests pass, 1 if any fail.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # TradingAgents/
BACKEND = ROOT / "backend"
DOCS = ROOT / "docs"

SUITE_FILES = {
    "golden": "backend/tests/test_c10_agent_golden_tasks.py",
    "manifest": "backend/tests/test_c10_capability_manifest.py",
}

CATEGORY_LABELS = {
    "TestGT_A_Tools": "A. Tools",
    "TestGT_B_Skills": "B. Skills",
    "TestGT_C_Planner": "C. Planner",
    "TestGT_D_Actions": "D. Actions",
    "TestGT_E_MemoryAudit": "E. Memory/Audit",
    "TestGT_F_Safety": "F. Safety",
    "TestManifestFileExistence": "Manifest Files",
    "TestManifestJSONContent": "Manifest Content",
    "TestManifestCodebaseAlignment": "Manifest Alignment",
}


def _run_pytest(test_paths: list[str], verbose: bool = False) -> tuple[int, str]:
    """Run pytest on given paths, return (returncode, stdout+stderr)."""
    cmd = [
        sys.executable, "-m", "pytest",
        *test_paths,
        "--tb=short",
        "-q",
        "--no-header",
    ]
    if verbose:
        cmd.append("-v")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    output = proc.stdout + proc.stderr
    return proc.returncode, output


def _parse_pytest_output(output: str) -> dict:
    """Extract pass/fail counts and test names from pytest -q output."""
    passed = 0
    failed = 0
    errors = 0
    failures: list[str] = []

    # Parse summary line: "30 passed" or "28 passed, 2 failed"
    summary_match = re.search(
        r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+error",
        output,
    )
    for m in re.finditer(r"(\d+)\s+(passed|failed|error)", output):
        count, kind = int(m.group(1)), m.group(2)
        if kind == "passed":
            passed = count
        elif kind == "failed":
            failed = count
        elif kind == "error":
            errors = count

    # Extract FAILED lines
    for line in output.splitlines():
        if line.startswith("FAILED "):
            failures.append(line.replace("FAILED ", "").strip())

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": passed + failed + errors,
        "failures": failures,
    }


def _build_report(results: dict[str, dict], run_at: str, all_passed: bool) -> str:
    """Build markdown evaluation report from parsed pytest results."""
    lines = []
    lines.append("# Chat Agent Evaluation Report")
    lines.append("")
    lines.append(f"**Generated:** {run_at}  ")
    lines.append(f"**Version:** c10_v1  ")
    lines.append(f"**Overall Status:** {'PASS' if all_passed else 'FAIL'}  ")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    total_passed = sum(r["passed"] for r in results.values())
    total_failed = sum(r["failed"] + r["errors"] for r in results.values())
    total_all = total_passed + total_failed

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Tests | {total_all} |")
    lines.append(f"| Passed | {total_passed} |")
    lines.append(f"| Failed | {total_failed} |")
    lines.append(f"| Pass Rate | {100 * total_passed // total_all if total_all else 0}% |")
    lines.append("")

    for suite_name, result in results.items():
        lines.append(f"## Suite: {suite_name}")
        lines.append("")
        status = "PASS" if result["failed"] == 0 and result["errors"] == 0 else "FAIL"
        lines.append(f"**Status:** {status}  ")
        lines.append(f"**Passed:** {result['passed']}  ")
        lines.append(f"**Failed:** {result['failed'] + result['errors']}  ")
        lines.append("")

        if result["failures"]:
            lines.append("### Failures")
            lines.append("")
            for f in result["failures"]:
                lines.append(f"- `{f}`")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Golden Task Categories")
    lines.append("")
    lines.append("| Category | Description | Expected |")
    lines.append("|----------|-------------|----------|")
    lines.append("| A. Tools | Intent → correct tool routing | 8 tasks |")
    lines.append("| B. Skills | Skill routing + metadata injection | 6 tasks |")
    lines.append("| C. Planner | Compound task detection + execution | 4 tasks |")
    lines.append("| D. Actions | Confirmation flow for write operations | 4 tasks |")
    lines.append("| E. Memory/Audit | Session memory + audit fields | 3 tasks |")
    lines.append("| F. Safety | Trading guard + disclaimer | 5 tasks |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Capability Coverage")
    lines.append("")
    lines.append("| Layer | Status |")
    lines.append("|-------|--------|")
    lines.append("| 9 Read-only Tools | Covered by GT-A |")
    lines.append("| 3 Action Tools | Covered by GT-D |")
    lines.append("| 6 Financial Skills | Covered by GT-B |")
    lines.append("| 6 Compound Planner Intents | Covered by GT-C |")
    lines.append("| Session Memory | Covered by GT-E |")
    lines.append("| Audit Trail | Covered by GT-E |")
    lines.append("| Safety Guard (9 patterns) | Covered by GT-F |")
    lines.append("| Disclaimer Enforcement | Covered by GT-F |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Report auto-generated by `backend/scripts/evaluate_chat_agent.py`_")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Chat Agent golden tasks")
    parser.add_argument(
        "--output",
        default=str(DOCS / "chat_agent_evaluation_report.md"),
        help="Output path for evaluation report",
    )
    parser.add_argument(
        "--suite",
        choices=["golden", "manifest", "all"],
        default="golden",
        help="Test suite to run",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[evaluate_chat_agent] Starting evaluation at {run_at}")

    # Determine which suites to run
    if args.suite == "all":
        suites_to_run = list(SUITE_FILES.keys())
    else:
        suites_to_run = [args.suite]

    results: dict[str, dict] = {}
    all_passed = True

    for suite in suites_to_run:
        test_file = SUITE_FILES[suite]
        print(f"[evaluate_chat_agent] Running suite: {suite} ({test_file})")
        returncode, output = _run_pytest([test_file], verbose=args.verbose)

        parsed = _parse_pytest_output(output)
        results[suite] = parsed

        status = "PASS" if returncode == 0 else "FAIL"
        print(
            f"[evaluate_chat_agent] {suite}: {status} "
            f"({parsed['passed']}/{parsed['total']} passed)"
        )
        if parsed["failures"]:
            for f in parsed["failures"]:
                print(f"  FAILED: {f}")

        if returncode != 0:
            all_passed = False

        if args.verbose:
            print(output)

    # Generate report
    report_md = _build_report(results, run_at, all_passed)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")
    print(f"[evaluate_chat_agent] Report written to: {output_path}")

    overall = "PASS" if all_passed else "FAIL"
    print(f"[evaluate_chat_agent] Overall: {overall}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
