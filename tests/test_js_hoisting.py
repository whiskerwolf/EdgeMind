"""
Comprehensive Test Suite for EdgeMind JavaScript Hoisting Static Analyzer.

Covers all Batch 1 requirements (A-L):
A. var access before initialization
B. Valid function declaration hoisting (no false positives)
C. let access before initialization (TDZ)
D. const access before initialization (TDZ)
E. Valid block-scoped declarations vs function-scoped var leaks / out-of-block access
F. Function expression called before initialization (const, let, var, arrow)
G. Class accessed/instantiated before initialization (TDZ)
H. Multiple hoisting issues in a single file
I. Valid complex JS producing zero false positives (comments, strings, properties, recursion, deferred fn calls)
J. Malformed / incomplete JavaScript safe SyntaxError handling
K. Source location line accuracy (including template `${expr}` interpolation)
L. Analyzer pipeline integration (`analyze_code`, `analyze_file`, `POST /api/v1/analyze`, Python parity)
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from core.analyzer import analyze_file, is_error
from core.api import app
from core.js_hoisting import check_js_hoisting, is_javascript_filename
from core.service import analyze_code


# =============================================================================
# A. var Hoisting
# =============================================================================

def test_var_access_before_initialization():
    code = (
        "console.log(user);\n"
        'var user = "Rithwik";\n'
    )
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == "VarHoistingWarning"
    assert not is_error(f)
    assert f["line"] == 1
    assert "user" in f["message"]
    assert "undefined" in f["why"].lower()
    assert "hoisted" in f["why"].lower()
    assert f["fix"]
    assert f["concept"] == "JavaScript Hoisting"


# =============================================================================
# B. Function Declaration Hoisting (Valid)
# =============================================================================

def test_valid_function_declaration_hoisting_no_error():
    code = (
        "greet();\n"
        "\n"
        "function greet() {\n"
        '    console.log("Hello");\n'
        "}\n"
    )
    findings = check_js_hoisting(code)
    assert findings == []

    report = analyze_code(code, filename="greet.js")
    assert report["overall_status"] == "PASS"
    assert report["score"] == 100
    assert report["total_errors"] == 0
    assert report["total_warnings"] == 0


# =============================================================================
# C & D. let and const Temporal Dead Zone (TDZ)
# =============================================================================

def test_let_access_before_initialization_tdz():
    code = (
        "console.log(value);\n"
        "let value = 10;\n"
    )
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == "TemporalDeadZoneError"
    assert is_error(f)
    assert f["line"] == 1
    assert "Temporal Dead Zone" in f["why"]
    assert "ReferenceError" in f["why"]
    assert "let value" in f["fix"]


def test_const_access_before_initialization_tdz():
    code = (
        "const doubled = limit * 2;\n"
        "const limit = 25;\n"
        "console.log(doubled);\n"
    )
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == "TemporalDeadZoneError"
    assert is_error(f)
    assert f["line"] == 1
    assert "limit" in f["message"]


# =============================================================================
# E. Block Scope vs Function Scope
# =============================================================================

def test_valid_block_scoped_declarations_no_false_positives():
    code = (
        "function demo() {\n"
        "    {\n"
        "        var a = 10;\n"
        "        let b = 20;\n"
        "        const c = 30;\n"
        "        console.log(b + c);\n"
        "    }\n"
        "    console.log(a);\n"
        "}\n"
        "demo();\n"
    )
    findings = check_js_hoisting(code)
    assert findings == []


def test_block_scope_let_out_of_block_and_var_hoisted_out_of_block():
    code = (
        "function scopeTrap() {\n"
        "    console.log(a);\n"
        "    {\n"
        "        var a = 10;\n"
        "        let b = 20;\n"
        "    }\n"
        "    console.log(b);\n"
        "}\n"
    )
    findings = check_js_hoisting(code)
    by_type = {f["type"]: f for f in findings}

    assert "VarHoistingWarning" in by_type
    assert by_type["VarHoistingWarning"]["line"] == 2
    assert "function/global scope" in by_type["VarHoistingWarning"]["why"]

    assert "BlockScopeError" in by_type
    assert is_error(by_type["BlockScopeError"])
    assert by_type["BlockScopeError"]["line"] == 7
    assert "block-scoped" in by_type["BlockScopeError"]["why"].lower()


# =============================================================================
# F. Function Expression Hoisting
# =============================================================================

@pytest.mark.parametrize(
    "decl_line,expected_err_kind",
    [
        ('const run = function() { console.log("Running"); };', "ReferenceError"),
        ('let run = () => console.log("Running");', "ReferenceError"),
        ('var run = function() { console.log("Running"); };', "TypeError"),
    ],
)
def test_function_expression_called_before_initialization(decl_line: str, expected_err_kind: str):
    code = f"run();\n\n{decl_line}\n"
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == "FunctionExpressionHoistingError"
    assert is_error(f)
    assert f["line"] == 1
    assert expected_err_kind in f["why"]
    assert f["fix"]


# =============================================================================
# G. Class Hoisting
# =============================================================================

def test_class_accessed_before_initialization_tdz():
    code = (
        "const instance = new User();\n"
        "\n"
        "class User {\n"
        "    constructor() {}\n"
        "}\n"
    )
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    f = findings[0]
    assert f["type"] == "ClassHoistingError"
    assert is_error(f)
    assert f["line"] == 1
    assert "User" in f["message"]
    assert "Temporal Dead Zone" in f["why"]
    assert "ReferenceError" in f["why"]


# =============================================================================
# H. Multiple Issues in One File
# =============================================================================

def test_multiple_hoisting_issues_in_single_file():
    code = (
        "console.log(legacyName);\n"          # Line 1: VarHoistingWarning
        "console.log(modernCount);\n"         # Line 2: TemporalDeadZoneError
        "runTask();\n"                        # Line 3: FunctionExpressionHoistingError
        "const u = new Account();\n"          # Line 4: ClassHoistingError
        "\n"                                  # Line 5
        'var legacyName = "EdgeMind";\n'      # Line 6
        "const modernCount = 42;\n"           # Line 7
        "const runTask = () => true;\n"       # Line 8
        "class Account {}\n"                  # Line 9
    )
    findings = check_js_hoisting(code)
    types_and_lines = [(f["type"], f["line"]) for f in findings]

    assert ("VarHoistingWarning", 1) in types_and_lines
    assert ("TemporalDeadZoneError", 2) in types_and_lines
    assert ("FunctionExpressionHoistingError", 3) in types_and_lines
    assert ("ClassHoistingError", 4) in types_and_lines
    assert len(findings) == 4


# =============================================================================
# I & K. Valid Code Zero False Positives & Source Location Accuracy
# =============================================================================

def test_valid_javascript_produces_zero_false_positives():
    code = (
        "// console.log(user); var user = 'commented';\n"
        'const msg = "console.log(value); let value = 10;";\n'
        "const obj = { user: 123, value: 456 };\n"
        "console.log(obj.user, obj.value);\n"
        "const user = 'Rithwik';\n"
        "let value = 10;\n"
        "\n"
        "function greet(user) {\n"
        "    return user;\n"
        "}\n"
        "\n"
        "function readOuterLater() {\n"
        "    return laterValue;\n"
        "}\n"
        "const laterValue = 99;\n"
        "readOuterLater();\n"
        "\n"
        "const factorial = function(n) {\n"
        "    if (n <= 1) return 1;\n"
        "    return n * factorial(n - 1);\n"
        "};\n"
    )
    assert check_js_hoisting(code) == []


def test_source_location_accuracy_including_template_interpolation():
    code = (
        "const ok = 1;\n"
        "// padding line\n"
        "const text = `Result: ${lateValue}`;\n"
        "let lateValue = 50;\n"
    )
    findings = check_js_hoisting(code)
    assert len(findings) == 1
    assert findings[0]["type"] == "TemporalDeadZoneError"
    assert findings[0]["line"] == 3


# =============================================================================
# J. Malformed / Incomplete JavaScript
# =============================================================================

@pytest.mark.parametrize(
    "bad_js",
    [
        "function broken( {\n  var a = 1;",
        'const text = "unterminated string;\nlet x = 1;',
        "let = 10;",
        "class Incomplete",
    ],
)
def test_malformed_javascript_handled_safely_with_syntax_finding(bad_js: str):
    findings = check_js_hoisting(bad_js)
    assert len(findings) >= 1
    assert any(f["type"] == "SyntaxError" for f in findings)

    report = analyze_code(bad_js, filename="broken.js")
    assert report["overall_status"] == "FAIL"
    assert report["syntax_status"] == "FAIL"


# =============================================================================
# L. Pipeline Integration & Python Parity
# =============================================================================

def test_pipeline_integration_service_file_api_and_python_unaffected(tmp_path: Path):
    assert is_javascript_filename("app.js") is True
    assert is_javascript_filename("module.mjs") is True
    assert is_javascript_filename("solution.py") is False

    js_code = (
        "console.log(user);\n"
        'var user = "Rithwik";\n'
        "const c = new Box();\n"
        "class Box {}\n"
    )

    # 1. analyze_code via .js filename
    report_service = analyze_code(js_code, filename="demo.js")
    assert report_service["overall_status"] == "FAIL"
    assert report_service["total_errors"] == 1
    assert report_service["total_warnings"] == 1
    assert report_service["detailed_errors"][0]["type"] == "ClassHoistingError"
    assert report_service["detailed_warnings"][0]["type"] == "VarHoistingWarning"

    # 2. analyze_code via explicit language parameter
    report_explicit = analyze_code(js_code, filename="snippet.txt", language="javascript")
    assert report_explicit["total_errors"] == 1
    assert report_explicit["total_warnings"] == 1

    # 3. analyze_file with .js path
    js_path = tmp_path / "hoist.js"
    js_path.write_text(js_code, encoding="utf-8")
    file_results = analyze_file(str(js_path), static_only=True)
    assert len(file_results) == 2

    # 4. POST /api/v1/analyze REST endpoint
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/analyze",
            json={"code": js_code, "filename": "api_check.js"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["file"] == "api_check.js"
        assert body["total_errors"] == 1
        assert body["total_warnings"] == 1

        # Verify Python analysis still runs normally
        py_resp = client.post(
            "/api/v1/analyze",
            json={"code": "def ok(x):\n    return x + 1\n", "filename": "ok.py"},
        )
        assert py_resp.status_code == 200
        assert py_resp.json()["overall_status"] == "PASS"
