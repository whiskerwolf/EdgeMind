"""
Tests for Phase 1: Backend Foundations.

Validates:
1. Centralized Pydantic Settings configuration (core/config.py).
2. Environment variable and secrets management (masking/sanitization).
3. CORS middleware (Vite frontend and Chrome extension origins).
4. Request logging and timing middleware (X-Process-Time).
5. Request correlation ID headers (X-Request-ID propagation).
6. Typed Pydantic request and response schemas (core/schemas.py).
7. Consistent HTTP error handling without stack trace leakage.
"""

import json
import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.config import Settings, get_settings
from core.schemas import (
    AnalyzeCodeRequest,
    EdgeMindAnalyzeRequest,
    ErrorResponse,
    HealthResponse,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_settings_default_values():
    """Verify Settings load with correct baseline defaults."""
    settings = get_settings()
    assert settings.app_name == "EdgeMind API"
    assert settings.app_version == "1.0.0"
    assert settings.static_only is True
    assert settings.max_source_size == 65536
    assert "http://localhost:5173" in settings.cors_origins
    assert "http://127.0.0.1:5173" in settings.cors_origins
    assert settings.request_id_header == "X-Request-ID"
    assert settings.process_time_header == "X-Process-Time"


def test_settings_environment_override(monkeypatch):
    """Verify Settings dynamically reflect environment variable overrides."""
    monkeypatch.setenv("APP_NAME", "EdgeMind Capstone Enterprise")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("DEBUG", "true")

    custom_settings = Settings()
    assert custom_settings.app_name == "EdgeMind Capstone Enterprise"
    assert custom_settings.port == 9000
    assert custom_settings.debug is True


def test_secrets_sanitization_and_masking(monkeypatch):
    """Verify sensitive AI credentials are never leaked in error messages."""
    secret_key = "sk-edgemind-super-secret-key-123456"
    monkeypatch.setenv("EDGEMIND_AI_KEY", secret_key)

    settings = Settings()
    assert settings.get_ai_api_key() == secret_key

    leak_candidate = f"Failed to connect using key {secret_key} at endpoint."
    sanitized = settings.sanitize_error(leak_candidate)
    assert secret_key not in sanitized
    assert "[REDACTED]" in sanitized


def test_request_id_auto_generation(client):
    """Verify X-Request-ID is automatically generated and returned in headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    request_id = response.headers["x-request-id"]
    assert len(request_id) > 10, "Generated Request ID must be a non-trivial UUID string"


def test_request_id_propagation_from_client(client):
    """Verify client-supplied X-Request-ID is preserved and echoed."""
    client_id = "test-trace-id-abc-98765"
    response = client.get("/health", headers={"X-Request-ID": client_id})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == client_id


def test_process_time_header_presence(client):
    """Verify X-Process-Time latency header is attached to responses."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-process-time" in response.headers
    process_time = response.headers["x-process-time"]
    assert process_time.endswith("ms")
    # Verify the numeric portion is a non-negative float
    val = float(process_time.replace("ms", ""))
    assert val >= 0.0


def test_cors_preflight_for_vite_frontend(client):
    """Verify CORS preflight and actual request from Vite frontend (localhost:5173)."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type,X-Request-ID",
    }
    # Preflight OPTIONS
    options_resp = client.options("/api/v1/analyze", headers=headers)
    assert options_resp.status_code == 200
    assert options_resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in options_resp.headers.get("access-control-allow-methods", "")

    # Actual request with Origin
    post_resp = client.post(
        "/api/v1/analyze",
        json={"code": "x = 1\n"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert post_resp.status_code == 200
    assert post_resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "x-request-id" in post_resp.headers.get("access-control-expose-headers", "").lower()
    assert "x-process-time" in post_resp.headers.get("access-control-expose-headers", "").lower()


def test_cors_origin_regex_for_chrome_extension(client):
    """Verify CORS headers match unpacked Chrome extension origins."""
    ext_origin = "chrome-extension://dcpgjneeokaigdhocommnadngnbaebgg"
    headers = {
        "Origin": ext_origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/api/v1/edgemind/analyze", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ext_origin


def test_typed_pydantic_schemas_valid():
    """Verify Pydantic models validate valid structures cleanly."""
    req = AnalyzeCodeRequest(code="x = 1\n", filename="test.py")
    assert req.code == "x = 1\n"
    assert req.filename == "test.py"
    assert req.static_only is True

    edgemind_req = EdgeMindAnalyzeRequest(
        code="def f(): pass",
        problem_context={"title": "Test Problem"},
        test_cases=[{"input_data": {"n": 5}}],
        max_candidates=5,
    )
    assert edgemind_req.code == "def f(): pass"
    assert edgemind_req.max_candidates == 5

    health = HealthResponse(status="healthy", service="EdgeMind")
    assert health.status == "healthy"

    err = ErrorResponse(error="Bad Request", detail="Sample validation failure", request_id="req-123")
    assert err.error == "Bad Request"
    assert err.request_id == "req-123"


def test_consistent_error_response_structure_on_400(client):
    """Verify HTTP 400 responses return a consistent error structure."""
    response = client.post("/api/v1/analyze", json={"code": ""})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "detail" in data
    assert data["error"] == "Bad Request"
    assert "x-request-id" in response.headers


def test_consistent_error_response_structure_on_500(client, monkeypatch):
    """Verify HTTP 500 responses return a consistent error structure without stack traces."""
    def crash(*args, **kwargs):
        raise RuntimeError("Internal crash error with sensitive path: C:\\Secrets\\key.pem")

    monkeypatch.setattr("core.api.analyze_code", crash)

    response = client.post("/api/v1/analyze", json={"code": "x = 1\n"})
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "Internal Server Error"
    assert "Internal crash error" not in data["detail"]
    assert "Secrets" not in data["detail"]
    assert "x-request-id" in response.headers
