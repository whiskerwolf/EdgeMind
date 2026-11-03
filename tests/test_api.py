import json
import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.service import MAX_SOURCE_SIZE


@pytest.fixture
def client():
    return TestClient(app)


def test_get_health(client):
    """1. Test GET /health returns 200 with expected service status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "healthy",
        "service": "EdgeMind",
    }


def test_successful_analysis_request(client):
    """2. Test successful analysis of clean Python code."""
    payload = {
        "code": "def add(a, b):\n    return a + b\n\nresult = add(1, 2)\nprint(result)\n",
        "filename": "solution.py",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "PASS"
    assert data["status"] == "PASS"
    assert data["score"] == 100
    assert data["total_errors"] == 0
    assert data["total_warnings"] == 0
    assert data["file_path"] == "solution.py"
    assert data["file"] == "solution.py"
    assert data["runtime_status"] == "SKIPPED"


def test_logic_warning_response(client):
    """3. Test that code with logic issues returns a warning report."""
    payload = {
        "code": "def calculate_average(a, b):\n    return a + b / 2\n\nprint(calculate_average(10, 20))\n",
        "filename": "average.py",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "PASS WITH WARNINGS"
    assert data["logic_status"] == "WARNING"
    assert data["summary"]["logic"] == "WARNING"
    assert data["total_warnings"] >= 1
    assert any(
        w["type"] in {"LogicError", "Possible Logic Error"}
        for w in data["detailed_warnings"]
    )


def test_syntax_error_input(client):
    """4. Test that syntax errors return a FAIL report without crashing or executing."""
    payload = {
        "code": "def broken(:\n    pass\n",
        "filename": "broken.py",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "FAIL"
    assert data["syntax_status"] == "FAIL"
    assert data["summary"]["syntax"] == "FAIL"
    assert data["runtime_status"] == "SKIPPED"
    assert data["total_errors"] == 1
    assert data["detailed_errors"][0]["type"] == "SyntaxError"
    assert data["detailed_errors"][0]["line"] == 1


def test_missing_code(client):
    """5. Test that requests omitting the 'code' key are rejected with HTTP 400."""
    response = client.post("/api/v1/analyze", json={"filename": "solution.py"})
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"
    assert "code" in err["detail"].lower()


def test_non_string_code(client):
    """6. Test that non-string 'code' fields are rejected with HTTP 400."""
    for invalid in [12345, None, ["print('hi')"], {"code": "print(1)"}]:
        response = client.post("/api/v1/analyze", json={"code": invalid})
        assert response.status_code == 400
        err = response.json()
        assert err["error"] == "Bad Request"
        assert "string" in err["detail"].lower()


def test_empty_code(client):
    """7. Test that empty or whitespace-only code strings are rejected with HTTP 400."""
    for empty in ["", "   ", "\n\t  \r\n"]:
        response = client.post("/api/v1/analyze", json={"code": empty})
        assert response.status_code == 400
        err = response.json()
        assert err["error"] == "Bad Request"
        assert "empty or whitespace" in err["detail"].lower()


def test_oversized_source(client):
    """8. Test that payloads exceeding 64 KiB are rejected with HTTP 400."""
    huge_code = "x = 1\n" + "# padding line\n" * 5000
    assert len(huge_code.encode("utf-8")) > MAX_SOURCE_SIZE
    response = client.post("/api/v1/analyze", json={"code": huge_code})
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"
    assert "exceeds" in err["detail"].lower()


def test_invalid_filename(client):
    """9. Test that path traversal and directory paths in filename are rejected with HTTP 400."""
    code = "result = 42\nprint(result)\n"
    for bad_name in [
        "../../etc/passwd",
        "..\\secret.py",
        "/absolute/root.py",
        "C:\\Windows\\cmd.exe",
        "folder/script.py",
        "folder\\script.py",
        "",
        "   ",
    ]:
        response = client.post("/api/v1/analyze", json={"code": code, "filename": bad_name})
        assert response.status_code == 400
        err = response.json()
        assert err["error"] == "Bad Request"
        assert "filename" in err["detail"].lower()


def test_malformed_json(client):
    """10. Test that malformed JSON payloads are rejected with HTTP 400."""
    response = client.post(
        "/api/v1/analyze",
        content="{\"code\": unquoted_malformed_value",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"
    assert "malformed" in err["detail"].lower() or "json" in err["detail"].lower()


def test_response_serialization(client):
    """11. Test that the API returns properly formatted application/json content."""
    payload = {"code": "x = 10\nprint(x)\n", "filename": "test.py"}
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    parsed = response.json()
    assert isinstance(parsed, dict)
    assert parsed["file_path"] == "test.py"


def test_runtime_execution_functions_never_called(client, monkeypatch):
    """12. Verify that runtime execution and subprocess engines are never invoked."""
    def fail_call(*args, **kwargs):
        raise AssertionError("Runtime execution engine or subprocess must never be invoked!")

    monkeypatch.setattr("core.runner.run_code", fail_call)
    monkeypatch.setattr("core.runner.execute_target_process", fail_call)
    monkeypatch.setattr("core.runtime.check_runtime", fail_call)
    monkeypatch.setattr("subprocess.Popen", fail_call)
    monkeypatch.setattr("subprocess.run", fail_call)

    payload = {"code": "import sys\nprint('hello world')\n"}
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["runtime_status"] == "SKIPPED"


def test_existing_report_fields_and_aliases_preserved(client):
    """13. Verify that all established report fields, summary sections, and aliases are preserved."""
    payload = {"code": "x = 1\n", "filename": "alias_check.py"}
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Top-level aliases
    assert data["file_path"] == data["file"] == "alias_check.py"
    assert data["overall_status"] == data["status"]
    assert data["detailed_errors"] == data["errors"]
    assert data["detailed_warnings"] == data["warnings"]
    assert "score" in data
    assert "total_errors" in data
    assert "total_warnings" in data
    assert "summary" in data

    # Summary keys
    for k in ("syntax", "runtime", "logic", "quality", "complexity"):
        assert k in data["summary"]

    # Finding aliases in warnings
    assert len(data["detailed_warnings"]) >= 1
    w = data["detailed_warnings"][0]
    assert w["line"] == w["line_number"]
    assert w["fix"] == w["suggested_fix"]
    assert w["why"] == w["explanation"]


def test_unexpected_errors_do_not_expose_stack_traces(client, monkeypatch):
    """14. Verify that unexpected exceptions return 500 without leaking stack traces or paths."""
    def crash(*args, **kwargs):
        raise RuntimeError("SensitiveInternalError: /var/secrets/app.py:99 occurred!")

    monkeypatch.setattr("core.api.analyze_code", crash)

    response = client.post("/api/v1/analyze", json={"code": "x = 1\n"})
    assert response.status_code == 500
    err = response.json()
    assert err["error"] == "Internal Server Error"
    # Never leak internal error message, tracebacks, or file paths
    assert "SensitiveInternalError" not in err["detail"]
    assert "/var/secrets" not in err["detail"]
    assert "traceback" not in json.dumps(err).lower()


def test_analyze_solution_class_with_self_has_no_unused_variable_warning(client):
    """15. Verify LeetCode instance method with conventional self parameter returns PASS, 100/100, no warnings."""
    code = (
        "class Solution:\n"
        "    def average(self, a: int, b: int) -> float:\n"
        "        return (a + b) / 2\n"
    )
    payload = {
        "code": code,
        "filename": "solution.py",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "PASS"
    assert data["score"] == 100
    assert data["total_warnings"] == 0
    assert data["total_errors"] == 0
    assert not any(w["type"] == "UnusedVariable" for w in data["detailed_warnings"])

