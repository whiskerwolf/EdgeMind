import json
import subprocess
import sys

from core.analyzer import analyze_file
from core.json_reporter import (
    create_report_dict,
    generate_json_report,
    serialize_finding,
)


def test_valid_json_serialization(tmp_path):
    file = tmp_path / "sample.py"
    file.write_text("x = 1\ny = 2\n", encoding="utf-8")

    json_str = generate_json_report(str(file))
    report = json.loads(json_str)

    assert isinstance(report, dict)
    expected_keys = {
        "file_path",
        "file",
        "overall_status",
        "status",
        "score",
        "total_errors",
        "total_warnings",
        "syntax_status",
        "runtime_status",
        "logic_status",
        "quality_status",
        "complexity_status",
        "detailed_errors",
        "errors",
        "detailed_warnings",
        "warnings",
        "summary",
    }
    for key in expected_keys:
        assert key in report, f"Missing expected key: {key}"

    assert isinstance(report["summary"], dict)
    assert "syntax" in report["summary"]
    assert "runtime" in report["summary"]


def test_correct_error_and_warning_counts():
    report_dict = create_report_dict("tests/name_error_demo.py")

    assert report_dict["total_errors"] == len(report_dict["detailed_errors"])
    assert report_dict["total_warnings"] == len(report_dict["detailed_warnings"])
    assert report_dict["total_errors"] == 1
    assert report_dict["total_warnings"] == 1
    assert report_dict["overall_status"] == "FAIL"
    assert report_dict["score"] == 75


def test_correct_line_numbers_and_finding_details():
    report_dict = create_report_dict("tests/name_error_demo.py")

    errors = report_dict["detailed_errors"]
    assert len(errors) == 1
    err = errors[0]
    assert err["type"] == "NameError"
    assert err["line"] == 2
    assert err["line_number"] == 2
    assert "studnet_name" in err["message"]
    assert err["explanation"]
    assert err["suggested_fix"]
    assert err["concept"] == "Runtime Error Handling"

    warnings = report_dict["detailed_warnings"]
    assert len(warnings) == 1
    warn = warnings[0]
    assert warn["type"] == "UnusedVariable"
    assert warn["line"] == 1
    assert warn["line_number"] == 1
    assert "student_name" in warn["message"]
    assert warn["explanation"]
    assert warn["suggested_fix"]
    assert warn["concept"] == "Code Quality"


def test_missing_optional_fields():
    # Test completely empty finding
    empty_serialized = serialize_finding({})
    assert empty_serialized["type"] == "Unknown"
    assert empty_serialized["line"] == 0
    assert empty_serialized["line_number"] == 0
    assert empty_serialized["message"] == ""
    assert empty_serialized["explanation"] == ""
    assert empty_serialized["suggested_fix"] == ""
    assert empty_serialized["concept"] == "General"

    # Test partial finding
    partial_serialized = serialize_finding({"type": "CustomIssue"})
    assert partial_serialized["type"] == "CustomIssue"
    assert partial_serialized["line"] == 0
    assert partial_serialized["line_number"] == 0
    assert partial_serialized["message"] == ""

    # Test report creation with missing fields in finding list
    report = create_report_dict(
        "dummy.py",
        results=[{"type": "UnusedVariable"}],
    )
    assert report["total_warnings"] == 1
    assert report["detailed_warnings"][0]["type"] == "UnusedVariable"
    assert report["detailed_warnings"][0]["line"] == 0


def test_empty_findings(tmp_path):
    file = tmp_path / "clean.py"
    file.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8"
    )

    json_str = generate_json_report(str(file))
    report = json.loads(json_str)

    assert report["total_errors"] == 0
    assert report["total_warnings"] == 0
    assert report["score"] == 100
    assert report["overall_status"] == "PASS"
    assert report["status"] == "PASS"
    assert report["detailed_errors"] == []
    assert report["errors"] == []
    assert report["detailed_warnings"] == []
    assert report["warnings"] == []
    assert report["syntax_status"] == "PASS"
    assert report["runtime_status"] == "PASS"


def test_correct_runtime_status(tmp_path):
    file = tmp_path / "div_zero.py"
    file.write_text("val = 10 / 0\n", encoding="utf-8")

    report = create_report_dict(str(file))

    assert report["runtime_status"] == "FAIL"
    assert report["overall_status"] == "FAIL"
    assert report["total_errors"] >= 1
    assert any(
        err["type"] == "ZeroDivisionError"
        for err in report["detailed_errors"]
    )


def test_file_not_found_error_remains_error(tmp_path):
    # Target script tries to open a non-existent file at runtime
    file = tmp_path / "read_missing.py"
    file.write_text(
        'with open("non_existent_test_file_987.txt", "r") as f:\n'
        '    data = f.read()\n',
        encoding="utf-8"
    )

    report = create_report_dict(str(file))

    assert report["runtime_status"] == "FAIL"
    assert report["overall_status"] == "FAIL"
    assert report["total_errors"] == 1
    fnf_errors = [
        err for err in report["detailed_errors"]
        if err["type"] == "FileNotFoundError"
    ]
    assert len(fnf_errors) == 1
    assert fnf_errors[0]["concept"] == "Runtime Error Handling"
    # Ensure it is not in warnings
    assert not any(
        w["type"] == "FileNotFoundError"
        for w in report["detailed_warnings"]
    )

    # Missing target file directly analyzed
    missing_report = create_report_dict("missing_target_file_12345.py")
    assert missing_report["overall_status"] == "FAIL"
    assert missing_report["total_errors"] == 1
    assert any(
        err["type"] == "FileError"
        for err in missing_report["detailed_errors"]
    )


def test_existing_quality_warnings_remain_warnings(tmp_path):
    file = tmp_path / "quality_code.py"
    file.write_text(
        "import math\n\n"
        "def compute():\n"
        "    unused_val = 42\n"
        "    return 10\n",
        encoding="utf-8"
    )

    report = create_report_dict(str(file))

    assert report["total_errors"] == 0
    assert report["total_warnings"] >= 1
    assert report["overall_status"] == "PASS WITH WARNINGS"
    assert report["quality_status"] == "WARNING"
    assert report["runtime_status"] == "PASS"
    assert len(report["detailed_errors"]) == 0
    assert len(report["detailed_warnings"]) >= 1

    warning_types = {w["type"] for w in report["detailed_warnings"]}
    assert "UnusedImport" in warning_types or "UnusedVariable" in warning_types


def test_cli_output_parses_with_json_loads():
    # Test --json flag after filename
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["file_path"] == "tests/name_error_demo.py"
    assert parsed["overall_status"] == "FAIL"
    assert "EDGEMIND REPORT" not in result.stdout
    assert "ANALYSIS SUMMARY" not in result.stdout

    # Test --json flag before filename
    result_before = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "--json", "tests/name_error_demo.py"],
        capture_output=True,
        text=True,
    )
    assert result_before.returncode == 0
    parsed_before = json.loads(result_before.stdout)
    assert parsed_before["file_path"] == "tests/name_error_demo.py"


def test_existing_human_readable_cli_behavior_remains_unchanged():
    # CLI without --json outputs human-readable report
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "EDGEMIND REPORT" in result.stdout
    assert "ANALYSIS SUMMARY" in result.stdout
    assert "Overall Result: FAIL" in result.stdout

    # Ensure stdout cannot be parsed as pure JSON
    try:
        json.loads(result.stdout)
        assert False, "Default CLI output should not be valid JSON"
    except json.JSONDecodeError:
        pass

    # CLI with no arguments exits with code 1 and prints usage
    no_args_result = subprocess.run(
        [sys.executable, "-m", "core.analyzer"],
        capture_output=True,
        text=True,
    )
    assert no_args_result.returncode == 1
    assert "Usage: python -m core.analyzer" in no_args_result.stdout
