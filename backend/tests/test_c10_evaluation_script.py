"""
test_c10_evaluation_script.py — Phase C10 Evaluation Script validation tests.

Validates that:
1. evaluate_chat_agent.py exists and is importable as a module
2. _parse_pytest_output() correctly extracts counts
3. _build_report() generates valid markdown
4. main() function exists and accepts expected arguments
5. Script can be invoked via subprocess (dry-run with --help)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "evaluate_chat_agent.py"
ROOT = SCRIPT_PATH.parent.parent.parent


class TestEvaluationScriptExists:

    def test_script_file_exists(self):
        """evaluate_chat_agent.py must exist."""
        assert SCRIPT_PATH.exists(), f"Missing: {SCRIPT_PATH}"

    def test_script_is_python(self):
        """Script must have .py extension."""
        assert SCRIPT_PATH.suffix == ".py"

    def test_script_nonempty(self):
        """Script must have content."""
        assert SCRIPT_PATH.stat().st_size > 500


class TestEvaluationScriptImport:
    """Import the script as a module and test internal functions."""

    @pytest.fixture(scope="class")
    def script_module(self):
        """Import evaluate_chat_agent as a module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("evaluate_chat_agent", SCRIPT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_script_has_main_function(self, script_module):
        """Script must have main() function."""
        assert hasattr(script_module, "main")
        assert callable(script_module.main)

    def test_script_has_parse_pytest_output(self, script_module):
        """Script must have _parse_pytest_output() function."""
        assert hasattr(script_module, "_parse_pytest_output")

    def test_script_has_build_report(self, script_module):
        """Script must have _build_report() function."""
        assert hasattr(script_module, "_build_report")

    def test_script_has_run_pytest(self, script_module):
        """Script must have _run_pytest() function."""
        assert hasattr(script_module, "_run_pytest")

    def test_parse_output_all_passed(self, script_module):
        """_parse_pytest_output handles '30 passed' format."""
        sample = "30 passed in 5.12s"
        result = script_module._parse_pytest_output(sample)
        assert result["passed"] == 30
        assert result["failed"] == 0

    def test_parse_output_mixed(self, script_module):
        """_parse_pytest_output handles '28 passed, 2 failed' format."""
        sample = "28 passed, 2 failed in 5.12s"
        result = script_module._parse_pytest_output(sample)
        assert result["passed"] == 28
        assert result["failed"] == 2

    def test_parse_output_extracts_failures(self, script_module):
        """_parse_pytest_output extracts FAILED test names."""
        sample = (
            "FAILED backend/tests/test_c10_agent_golden_tasks.py::TestGT_A_Tools::test_gt_a1\n"
            "1 passed, 1 failed in 1.0s"
        )
        result = script_module._parse_pytest_output(sample)
        assert len(result["failures"]) == 1
        assert "test_gt_a1" in result["failures"][0]

    def test_build_report_contains_headings(self, script_module):
        """_build_report() generates markdown with required headings."""
        results = {
            "golden": {"passed": 30, "failed": 0, "errors": 0, "total": 30, "failures": []}
        }
        report = script_module._build_report(results, "2026-06-18 00:00 UTC", all_passed=True)
        assert "# Chat Agent Evaluation Report" in report
        assert "## Summary" in report
        assert "PASS" in report

    def test_build_report_fail_status(self, script_module):
        """_build_report() shows FAIL when tests fail."""
        results = {
            "golden": {
                "passed": 28,
                "failed": 2,
                "errors": 0,
                "total": 30,
                "failures": ["tests/test_c10.py::TestA::test_1"],
            }
        }
        report = script_module._build_report(results, "2026-06-18 00:00 UTC", all_passed=False)
        assert "FAIL" in report
        assert "test_1" in report

    def test_build_report_has_category_table(self, script_module):
        """_build_report() includes golden task category table."""
        results = {
            "golden": {"passed": 30, "failed": 0, "errors": 0, "total": 30, "failures": []}
        }
        report = script_module._build_report(results, "2026-06-18 00:00 UTC", all_passed=True)
        assert "A. Tools" in report
        assert "F. Safety" in report

    def test_suite_files_dict_has_golden_and_manifest(self, script_module):
        """SUITE_FILES dict has 'golden' and 'manifest' keys."""
        assert "golden" in script_module.SUITE_FILES
        assert "manifest" in script_module.SUITE_FILES


class TestEvaluationScriptRunnable:
    """Test that the script can be invoked as a subprocess."""

    def test_script_help_flag(self):
        """Script responds to --help without error."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        # argparse --help exits with code 0
        assert result.returncode == 0
        assert "--suite" in result.stdout or "--output" in result.stdout

    def test_script_is_executable_python(self):
        """Script starts with a valid Python shebang or is runnable."""
        content = SCRIPT_PATH.read_text()
        assert "def main" in content
        assert 'if __name__ == "__main__"' in content
