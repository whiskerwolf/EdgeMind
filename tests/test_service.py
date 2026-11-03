import json
import pytest

from core.service import MAX_SOURCE_SIZE, analyze_code, validate_filename


def test_valid_clean_source():
    """Verify that valid clean source produces a 100 score PASS report."""
    clean_code = (
        "def calculate_area(length, width):\n"
        "    area = length * width\n"
        "    return area\n"
        "\n"
        "result = calculate_area(5, 10)\n"
        "print(result)\n"
    )
    report = analyze_code(clean_code)
    assert report["overall_status"] == "PASS"
    assert report["status"] == "PASS"
    assert report["score"] == 100
    assert report["total_errors"] == 0
    assert report["total_warnings"] == 0
    assert report["detailed_errors"] == []
    assert report["detailed_warnings"] == []
    assert report["runtime_status"] == "SKIPPED"
    assert report["summary"]["runtime"] == "SKIPPED"


def test_logic_warning_detection():
    """Verify that logic bugs (unparenthesized average) are detected statically."""
    logic_code = (
        "def calculate_average(a, b):\n"
        "    return a + b / 2\n"
        "\n"
        "print(calculate_average(10, 20))\n"
    )
    report = analyze_code(logic_code)
    assert report["overall_status"] == "PASS WITH WARNINGS"
    assert report["logic_status"] == "WARNING"
    assert report["summary"]["logic"] == "WARNING"
    assert report["total_warnings"] >= 1
    assert any(
        w["type"] in {"LogicError", "Possible Logic Error"}
        for w in report["detailed_warnings"]
    )


def test_syntax_error_detection():
    """Verify that syntax errors are detected safely without code execution."""
    broken_code = "def broken_function(:\n    pass\n"
    report = analyze_code(broken_code)
    assert report["overall_status"] == "FAIL"
    assert report["syntax_status"] == "FAIL"
    assert report["summary"]["syntax"] == "FAIL"
    assert report["runtime_status"] == "SKIPPED"
    assert report["total_errors"] == 1
    assert len(report["detailed_errors"]) == 1
    assert report["detailed_errors"][0]["type"] == "SyntaxError"
    assert report["detailed_errors"][0]["line"] == 1
    assert report["score"] == 80


def test_empty_source_rejection():
    """Verify that empty source code is rejected with ValueError."""
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        analyze_code("")


def test_whitespace_only_source_rejection():
    """Verify that whitespace-only source is rejected with ValueError."""
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        analyze_code("   \n\t  \r\n   ")


def test_non_string_input_rejection():
    """Verify that non-string code inputs are rejected with TypeError."""
    for invalid in [None, 12345, ["print('hi')"], b"print('hi')", {"code": "x = 1"}]:
        with pytest.raises(TypeError, match="must be a string"):
            analyze_code(invalid)


def test_oversized_source_rejection():
    """Verify that source code exceeding MAX_SOURCE_SIZE (64 KiB) is rejected with ValueError."""
    huge_code = "x = 1\n" + "# padding line\n" * 5000
    assert len(huge_code.encode("utf-8")) > MAX_SOURCE_SIZE
    with pytest.raises(ValueError, match="exceeds the maximum allowed limit"):
        analyze_code(huge_code)


def test_filename_path_traversal_input_validation():
    """Verify that filename path traversal, directory paths, and invalid types are rejected."""
    code = "result = 42\nprint(result)\n"

    # Traversal and path separator attempts
    for bad_name in [
        "../../etc/passwd",
        "..\\secret.py",
        "../file.py",
        "/absolute/root.py",
        "C:\\Windows\\cmd.exe",
        "sub/folder.py",
        "sub\\folder.py",
        "",
        "   ",
    ]:
        with pytest.raises(ValueError):
            analyze_code(code, filename=bad_name)

    # Non-string filenames
    for non_str in [None, 123, ["filename.py"]]:
        with pytest.raises(TypeError):
            analyze_code(code, filename=non_str)

    # Valid display label succeeds
    report = analyze_code(code, filename="custom_label.py")
    assert report["file_path"] == "custom_label.py"
    assert report["file"] == "custom_label.py"


def test_runtime_status_equals_skipped():
    """Verify that runtime_status is always reported as SKIPPED in service reports."""
    report = analyze_code("val = 1\nprint(val)\n")
    assert report["runtime_status"] == "SKIPPED"
    assert report["summary"]["runtime"] == "SKIPPED"


def test_runtime_execution_functions_never_called(monkeypatch):
    """Verify that runtime execution engines and subprocesses are never invoked."""
    def fail_call(*args, **kwargs):
        raise AssertionError("Runtime execution engine or subprocess must never be invoked!")

    monkeypatch.setattr("core.runner.run_code", fail_call)
    monkeypatch.setattr("core.runner.execute_target_process", fail_call)
    monkeypatch.setattr("core.runtime.check_runtime", fail_call)
    monkeypatch.setattr("subprocess.Popen", fail_call)
    monkeypatch.setattr("subprocess.run", fail_call)

    # Must succeed purely via static AST analysis
    report = analyze_code("a = 10\nb = 20\nprint(a + b)\n")
    assert report["score"] == 100
    assert report["runtime_status"] == "SKIPPED"


def test_no_temporary_files_created(monkeypatch):
    """Verify that no temporary files or directories are created by analyze_code."""
    def fail_temp(*args, **kwargs):
        raise AssertionError("Temporary file creation functions must not be called!")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", fail_temp)
    monkeypatch.setattr("tempfile.mkstemp", fail_temp)
    monkeypatch.setattr("tempfile.TemporaryDirectory", fail_temp)

    report = analyze_code("x = 100\nprint(x)\n")
    assert isinstance(report, dict)
    assert report["overall_status"] == "PASS"


def test_json_serialization_succeeds():
    """Verify that the dictionary returned by analyze_code is directly JSON-serializable."""
    report = analyze_code("val = 42\nprint(val)\n")
    json_str = json.dumps(report, indent=2)
    assert isinstance(json_str, str)
    decoded = json.loads(json_str)
    assert decoded == report


def test_static_only_false_explicitly_rejected():
    """Verify that requesting static_only=False raises an explicit ValueError."""
    with pytest.raises(ValueError, match="Runtime execution is disabled.*static_only must be True"):
        analyze_code("print('test')", static_only=False)

    with pytest.raises(ValueError):
        analyze_code("print('test')", static_only=None)


def test_multiple_requests_do_not_leak_findings():
    """Verify that successive calls to analyze_code do not leak state or findings."""
    # Request 1: code with warnings
    code_warn = "x = 1\ny = 2\n"
    res1 = analyze_code(code_warn, filename="req1.py")
    assert res1["total_warnings"] > 0
    assert res1["file_path"] == "req1.py"

    # Request 2: clean code must not retain warnings from Request 1
    code_clean = "def area(a, b): return a * b\nprint(area(2, 3))\n"
    res2 = analyze_code(code_clean, filename="req2.py")
    assert res2["total_warnings"] == 0
    assert res2["total_errors"] == 0
    assert res2["score"] == 100
    assert res2["file_path"] == "req2.py"
    assert len(res2["detailed_warnings"]) == 0

    # Request 3: code with syntax error
    code_syntax = "def broken(:\n"
    res3 = analyze_code(code_syntax, filename="req3.py")
    assert res3["total_errors"] == 1
    assert res3["syntax_status"] == "FAIL"

    # Request 4: clean code again must remain clean
    res4 = analyze_code(code_clean, filename="req4.py")
    assert res4["total_warnings"] == 0
    assert res4["total_errors"] == 0
    assert res4["score"] == 100


def test_existing_score_and_finding_aliases_compatible():
    """Verify that report schema preserves all established field aliases and score rules."""
    code = "x = 1\n"
    report = analyze_code(code)

    # Top-level aliases
    assert report["file_path"] == report["file"]
    assert report["overall_status"] == report["status"]
    assert report["detailed_errors"] == report["errors"]
    assert report["detailed_warnings"] == report["warnings"]

    # Summary structure
    for key in ("syntax", "runtime", "logic", "quality", "complexity"):
        assert key in report["summary"]

    # Finding aliases in warnings
    assert len(report["detailed_warnings"]) >= 1
    warn = report["detailed_warnings"][0]
    assert warn["line"] == warn["line_number"]
    assert warn["fix"] == warn["suggested_fix"]
    assert warn["why"] == warn["explanation"]

    # Score calculation formula check
    calc_score = 100 - (report["total_errors"] * 20) - (report["total_warnings"] * 5)
    assert report["score"] == max(0, min(100, calc_score))
