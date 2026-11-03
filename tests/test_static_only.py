import json
import os
import subprocess
import sys
from unittest.mock import MagicMock
import pytest

from core.analyzer import analyze_file, is_error, print_report
from core.json_reporter import create_report_dict, generate_json_report


def test_cli_accepts_static_only():
    """Verify that --static-only is accepted by the CLI and skips runtime execution."""
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--static-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "EDGEMIND REPORT" in result.stdout
    assert "RUNTIME: SKIPPED" in result.stdout
    # In name_error_demo.py, NameError happens at runtime. Static-only skips it.
    assert "NameError" not in result.stdout
    assert "UnusedVariable" in result.stdout
    assert "Overall Result: PASS WITH WARNINGS" in result.stdout


def test_static_only_does_not_invoke_check_runtime(monkeypatch):
    """Verify that analyze_file with static_only=True never calls check_runtime."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("check_runtime() was called in static-only mode!")

    monkeypatch.setattr("core.analyzer.check_runtime", fail_if_called)

    # Must succeed without invoking check_runtime
    results = analyze_file("tests/name_error_demo.py", static_only=True)
    assert any(r.get("type") == "UnusedVariable" for r in results)
    assert not any(r.get("type") == "NameError" for r in results)


def test_static_only_does_not_invoke_run_code(monkeypatch):
    """Verify that analyze_file with static_only=True never calls core.runner.run_code."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_code() was called in static-only mode!")

    monkeypatch.setattr("core.runner.run_code", fail_if_called)

    results = analyze_file("tests/name_error_demo.py", static_only=True)
    assert isinstance(results, list)


def test_target_script_top_level_side_effect_not_executed(tmp_path):
    """Verify that a target script with top-level side effects is never executed."""
    canary = tmp_path / "side_effect_marker.txt"
    script = tmp_path / "dangerous_script.py"

    # Use raw string / escaped path to avoid Windows backslash issues
    canary_repr = repr(str(canary))
    script.write_text(
        f"with open({canary_repr}, 'w', encoding='utf-8') as f:\n"
        f"    f.write('SIDE_EFFECT_TRIGGERED')\n",
        encoding="utf-8",
    )

    # 1. Direct Python API with static_only=True
    results = analyze_file(str(script), static_only=True)
    assert not canary.exists(), "Target file side effects were executed in static-only mode!"
    assert [r for r in results if is_error(r)] == []

    # 2. Subprocess CLI with --static-only
    cli_result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", str(script), "--static-only"],
        capture_output=True,
        text=True,
    )
    assert cli_result.returncode == 0
    assert "RUNTIME: SKIPPED" in cli_result.stdout
    assert not canary.exists(), "Target file side effects were executed by CLI in --static-only mode!"


def test_syntax_errors_still_detected(tmp_path, capsys):
    """Verify that syntax errors are still detected and reported without executing code."""
    broken = tmp_path / "broken_syntax.py"
    broken.write_text("def broken_func(:\n    pass\n", encoding="utf-8")

    results = analyze_file(str(broken), static_only=True)
    syntax_issues = [r for r in results if r.get("type") == "SyntaxError"]
    assert len(syntax_issues) == 1
    assert is_error(syntax_issues[0])

    print_report(str(broken), results=results, static_only=True)
    captured = capsys.readouterr().out
    assert "SYNTAX: FAIL" in captured
    assert "RUNTIME: SKIPPED" in captured
    assert "Overall Result: FAIL" in captured


def test_static_logic_and_quality_findings_still_reported():
    """Verify that AST-based logic, smell, and quality checks run in static-only mode."""
    # Logic error test file
    logic_results = analyze_file("tests/test06_logic_error.py", static_only=True)
    assert any(
        r.get("type") in {"LogicError", "Possible Logic Error"}
        for r in logic_results
    ), "Static logic check should still detect precedence error in average calculation"

    # Nested loops code smell test file
    smell_results = analyze_file("tests/test10_complexity.py", static_only=True)
    assert any(
        r.get("type") == "NestedLoops"
        for r in smell_results
    ), "Static smell check should still detect NestedLoops"

    # Quality check in name_error_demo.py
    quality_results = analyze_file("tests/name_error_demo.py", static_only=True)
    assert any(
        r.get("type") == "UnusedVariable"
        for r in quality_results
    ), "Static quality check should still detect UnusedVariable"
    assert not any(
        r.get("type") == "NameError"
        for r in quality_results
    ), "Runtime NameError must not be present in static-only results"


def test_normal_mode_still_invokes_runtime_analysis():
    """Verify that normal mode (static_only=False) still runs runtime analysis as before."""
    results = analyze_file("tests/name_error_demo.py", static_only=False)
    name_errors = [r for r in results if r.get("type") == "NameError"]
    assert len(name_errors) == 1
    assert is_error(name_errors[0])
    assert name_errors[0]["concept"] == "Runtime Error Handling"


def test_json_reporting_represents_skipped_runtime_status():
    """Verify that JSON reports correctly record runtime_status as SKIPPED."""
    report = create_report_dict("tests/name_error_demo.py", static_only=True)
    assert report["runtime_status"] == "SKIPPED"
    assert report["summary"]["runtime"] == "SKIPPED"
    assert report["syntax_status"] == "PASS"
    assert report["overall_status"] == "PASS WITH WARNINGS"
    assert report["total_errors"] == 0
    assert report["total_warnings"] == 1
    assert report["score"] == 95

    # Test CLI invocation with --static-only --json
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--static-only", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["runtime_status"] == "SKIPPED"
    assert parsed["summary"]["runtime"] == "SKIPPED"
    assert parsed["score"] == 95
    assert parsed["overall_status"] == "PASS WITH WARNINGS"


def test_static_only_with_ai_preserves_consent_gate():
    """Verify that combining --static-only and --ai still strictly enforces source consent."""
    # Without consent: must skip sending code
    result_no_consent = subprocess.run(
        [
            sys.executable,
            "-m",
            "core.analyzer",
            "tests/test11_clean_code.py",
            "--static-only",
            "--ai",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result_no_consent.returncode == 0
    parsed = json.loads(result_no_consent.stdout)
    assert parsed["runtime_status"] == "SKIPPED"
    assert "ai_reasoning" in parsed
    assert parsed["ai_reasoning"]["status"] == "skipped"
    assert "--share-source" in result_no_consent.stderr
