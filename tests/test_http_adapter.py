import io
import json
import socket
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from adapters.http_adapter import HttpAdapter
from core.models import AIRequest, AIResponse


def _make_mock_response(payload_dict: dict) -> MagicMock:
    """Helper to create a mock urllib response returning JSON bytes."""
    data_bytes = json.dumps(payload_dict).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = data_bytes
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_missing_user_consent():
    adapter = HttpAdapter()
    request = AIRequest(
        file_path="sample.py",
        code="a = 1\n",
        findings=[{"type": "UnusedVariable", "line": 1}],
        user_consent=False,
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        response = adapter.analyze(request)
        mock_urlopen.assert_not_called()

    assert response.status == "skipped"
    assert "consent" in response.summary.lower()
    assert response.insights == []
    assert response.error is None


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("CODEDOCTOR_AI_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    adapter = HttpAdapter()
    request = AIRequest(
        file_path="sample.py",
        code="a = 1\n",
        findings=[],
        user_consent=True,
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        response = adapter.analyze(request)
        mock_urlopen.assert_not_called()

    assert response.status == "failed"
    assert "API key not found" in response.summary
    assert "Missing API key" in response.error


def test_valid_provider_response(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "test-valid-key")

    inner_json = json.dumps({
        "summary": "NameError caused by typo in identifier.",
        "insights": [
            {
                "finding_type": "NameError",
                "line": 2,
                "line_number": 2,
                "explanation": "studnet_name does not exist; misspelled student_name.",
                "suggested_fix": "Change studnet_name to student_name.",
                "confidence": "high",
            }
        ],
    })

    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": inner_json}
                    ]
                }
            }
        ]
    }

    adapter = HttpAdapter()
    request = AIRequest(
        file_path="demo.py",
        code="student_name = 'Rithwik'\nprint(studnet_name)\n",
        findings=[{"type": "NameError", "line": 2}],
        user_consent=True,
    )

    with patch("urllib.request.urlopen", return_value=_make_mock_response(gemini_payload)):
        response = adapter.analyze(request)

    assert response.status == "success"
    assert response.provider == "gemini"
    assert response.summary == "NameError caused by typo in identifier."
    assert len(response.insights) == 1
    assert response.insights[0]["finding_type"] == "NameError"
    assert response.insights[0]["line"] == 2
    assert response.insights[0]["confidence"] == "high"
    assert response.error is None


def test_http_401_response(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "invalid-key")

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    http_error = urllib.error.HTTPError(
        url="https://api.example.com",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b""),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert response.error == "HTTP 401: Unauthorized"
    assert "Authentication failed" in response.summary


def test_http_429_response(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "rate-limited-key")

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    http_error = urllib.error.HTTPError(
        url="https://api.example.com",
        code=429,
        msg="Too Many Requests",
        hdrs={},
        fp=io.BytesIO(b""),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert response.error == "HTTP 429: Rate limit exceeded"
    assert "rate limit" in response.summary.lower()


def test_network_connection_failure(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "any-key")

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    url_error = urllib.error.URLError(reason="Connection refused")

    with patch("urllib.request.urlopen", side_effect=url_error):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert "Network connection to AI provider failed." in response.summary
    assert "Connection refused" in response.error


def test_request_timeout(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "any-key")

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    timeout_error = urllib.error.URLError(reason=socket.timeout("The read operation timed out"))

    with patch("urllib.request.urlopen", side_effect=timeout_error):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert "timed out" in response.summary.lower()
    assert response.error == "Network timeout"


def test_invalid_json(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "any-key")

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert "invalid json" in response.summary.lower()
    assert "Invalid JSON" in response.error


def test_missing_or_malformed_response_fields(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "any-key")

    # Case A: 'insights' is a string instead of a list
    inner_bad_type = json.dumps({"summary": "test", "insights": "this should be a list"})
    bad_payload = {
        "candidates": [{"content": {"parts": [{"text": inner_bad_type}]}}]
    }

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    with patch("urllib.request.urlopen", return_value=_make_mock_response(bad_payload)):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert "did not match expected schema" in response.summary
    assert "Malformed schema" in response.error

    # Case B: item in 'insights' is not a dict
    inner_bad_item = json.dumps({"summary": "test", "insights": ["not a dict"]})
    bad_item_payload = {
        "candidates": [{"content": {"parts": [{"text": inner_bad_item}]}}]
    }

    with patch("urllib.request.urlopen", return_value=_make_mock_response(bad_item_payload)):
        response2 = adapter.analyze(request)

    assert response2.status == "failed"
    assert "Malformed schema" in response2.error


def test_api_key_is_not_exposed_in_returned_errors(monkeypatch):
    LEAKY_SECRET = "AIzaSySecretApiKeyThatMustNeverLeak12345"
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", LEAKY_SECRET)

    adapter = HttpAdapter()
    request = AIRequest(code="x = 1\n", user_consent=True)

    url_error = urllib.error.URLError(reason=f"Failed connection using {LEAKY_SECRET} to host")

    with patch("urllib.request.urlopen", side_effect=url_error):
        response = adapter.analyze(request)

    assert response.status == "failed"
    assert LEAKY_SECRET not in str(response.error)
    assert LEAKY_SECRET not in str(response.summary)
    assert "[REDACTED]" in response.error


def test_existing_deterministic_report_data_is_not_modified(monkeypatch):
    monkeypatch.setenv("CODEDOCTOR_AI_KEY", "valid-key")

    original_findings = [
        {
            "type": "ZeroDivisionError",
            "line": 5,
            "message": "division by zero",
            "why": "denominator is zero",
            "fix": "check denominator",
            "concept": "Division",
        }
    ]
    # Pass a copy for analysis
    findings_copy = [dict(f) for f in original_findings]

    inner_json = json.dumps({
        "summary": "Division by zero detected",
        "insights": [
            {
                "finding_type": "ZeroDivisionError",
                "line": 5,
                "explanation": "AI explains division by zero",
                "suggested_fix": "AI suggests fix",
                "confidence": "high",
            }
        ],
    })
    payload = {
        "candidates": [{"content": {"parts": [{"text": inner_json}]}}]
    }

    adapter = HttpAdapter()
    request = AIRequest(
        file_path="div.py",
        code="x = 1 / 0\n",
        findings=findings_copy,
        user_consent=True,
    )

    with patch("urllib.request.urlopen", return_value=_make_mock_response(payload)):
        response = adapter.analyze(request)

    assert response.status == "success"
    # Deterministic findings must not be mutated
    assert findings_copy == original_findings
    assert original_findings[0]["type"] == "ZeroDivisionError"
    assert original_findings[0]["why"] == "denominator is zero"
