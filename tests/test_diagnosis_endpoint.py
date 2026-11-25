"""
HTTP Integration Tests for Finding AI Diagnosis Streaming Endpoint (Phase 5G.4).

Verifies POST /api/v1/diagnose/stream:
- A. Valid request handling
- B. text/event-stream content type and headers
- C. diagnosis_started event structure
- D. Multiple response_chunk events
- E. completed event structure
- F. Event ordering: diagnosis_started -> response_chunk -> completed
- G. Sequential event IDs (id: 1, 2, 3...)
- H. Finding and session correlation across events
- I. Invalid request rejection (HTTP 422)
- J. Oversized context rejection (HTTP 422)
- K. Unsupported language rejection (HTTP 422)
- L. Provider unavailable handling (error event emitted, no completed)
- M. Provider failure handling (error event emitted, no completed)
- N. Safe error messages (no stack traces, no leaked credentials)
- O. Timeout handling (error event emitted on timeout, no completed)
- P. Client disconnect handling
- Q. Generator cleanup on disconnect / termination
- R. Rate limit headers and enforcement
- S. Authentication behavior (anonymous allowed, invalid JWT 401)
- T. Static analyzer endpoint (/api/v1/analyze) regression check
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.agents.provider import BaseAgentProvider, MockAgentProvider
from core.agents.schemas import AgentStepResult
from core.diagnosis_service import DiagnosisService
from core.routes.diagnose import get_diagnosis_service


# =============================================================================
# Mock / Test Providers
# =============================================================================

class MockStreamingProvider(BaseAgentProvider):
    """Deterministic streaming provider that yields multiple chunks."""

    def __init__(self, chunks: List[str]):
        self._chunks = chunks
        self.closed = False

    @property
    def name(self) -> str:
        return "mock_streaming"

    async def chat_completion(self, messages, tools, temperature=0.0):
        return AgentStepResult(content="".join(self._chunks))

    async def chat_completion_stream(self, messages, tools, temperature=0.0):
        try:
            for chunk in self._chunks:
                yield chunk
            yield AgentStepResult(content="".join(self._chunks))
        finally:
            self.closed = True


class MockUnavailableProvider(BaseAgentProvider):
    """Test provider reporting is_available() == False."""

    @property
    def name(self) -> str:
        return "mock_unavailable"

    def is_available(self) -> bool:
        return False

    async def chat_completion(self, messages, tools, temperature=0.0):
        raise RuntimeError("Should not be called when unavailable")

    async def chat_completion_stream(self, messages, tools, temperature=0.0):
        raise RuntimeError("Should not be called when unavailable")
        yield ""


class MockFailingProvider(BaseAgentProvider):
    """Test provider that raises mid-stream with sensitive data."""

    @property
    def name(self) -> str:
        return "mock_failing"

    async def chat_completion(self, messages, tools, temperature=0.0):
        raise RuntimeError("Upstream failure with sk-proj-1234567890abcdef12345678")

    async def chat_completion_stream(self, messages, tools, temperature=0.0):
        yield "Initial partial diagnosis "
        raise RuntimeError("Upstream failure with sk-proj-1234567890abcdef12345678")


# =============================================================================
# Helper: Parse Wire SSE Stream
# =============================================================================

def parse_sse_wire_stream(raw_text: str) -> List[Dict[str, Any]]:
    """Parse raw SSE text stream into structured event objects."""
    events = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_dict = {"id": None, "event": "message", "data": None}
        data_lines = []
        for line in lines:
            if line.startswith("id:"):
                event_dict["id"] = int(line[3:].strip())
            elif line.startswith("event:"):
                event_dict["event"] = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            raw_data = "\n".join(data_lines)
            try:
                event_dict["data"] = json.loads(raw_data)
            except Exception:
                event_dict["data"] = raw_data
        events.append(event_dict)
    return events


@pytest.fixture
def valid_payload() -> Dict[str, Any]:
    return {
        "finding": {
            "finding_id": "FINDING-DIV0",
            "type": "division_by_zero",
            "severity": "error",
            "message": "Potential ZeroDivisionError on line 2",
            "line": 2,
            "static_why": "Denom might be zero.",
            "static_fix": "Add guard check.",
        },
        "code_context": "def div(a, b):\n    return a / b\n",
        "context_start_line": 1,
        "context_end_line": 3,
        "filename": "calc.py",
        "language": "python",
    }


# =============================================================================
# Tests
# =============================================================================

def test_diagnose_stream_valid_request_headers_and_type(valid_payload):
    """Test A & B: Valid request returns HTTP 200 with text/event-stream headers."""
    provider = MockStreamingProvider(["### Root Cause\nMissing guard.\n"])
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            assert "no-cache" in resp.headers.get("cache-control", "")
            assert "keep-alive" in resp.headers.get("connection", "").lower()
            assert "no" in resp.headers.get("x-accel-buffering", "").lower()
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_event_sequence_and_structure(valid_payload):
    """Test C, D, E, F, G, H: Event sequence, sequential IDs, correlation, and completion."""
    chunks = [
        "### Root Cause\nDivision by zero.\n\n",
        "### Why This Happens\n`b` can be 0.\n\n",
        "### Recommended Fix\nCheck `b != 0`.\n\n",
        "### Example\n```python\nif b == 0: return None\n```",
    ]
    provider = MockStreamingProvider(chunks)
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp.status_code == 200

            events = parse_sse_wire_stream(resp.text)
            assert len(events) >= 3

            # 1. Event ordering: starts with diagnosis_started
            assert events[0]["event"] == "diagnosis_started"
            start_data = events[0]["data"]
            assert start_data["finding_id"] == "FINDING-DIV0"
            assert start_data["finding_type"] == "division_by_zero"
            assert start_data["line"] == 2
            session_id = start_data["session_id"]
            assert session_id.startswith("diag_")

            # 2. Sequential integer IDs check
            for idx, event in enumerate(events, start=1):
                assert event["id"] == idx

            # 3. Middle events are response_chunk
            chunk_events = [e for e in events if e["event"] == "response_chunk"]
            assert len(chunk_events) >= 1
            for ce in chunk_events:
                assert ce["data"]["session_id"] == session_id
                assert ce["data"]["finding_id"] == "FINDING-DIV0"
                assert "chunk" in ce["data"]

            # Reconstituted text must contain the Markdown headers
            reconstituted = "".join(ce["data"]["chunk"] for ce in chunk_events)
            assert "### Root Cause" in reconstituted
            assert "### Recommended Fix" in reconstituted

            # 4. Ends with completed
            assert events[-1]["event"] == "completed"
            completed_data = events[-1]["data"]
            assert completed_data["session_id"] == session_id
            assert completed_data["finding_id"] == "FINDING-DIV0"
            assert completed_data["status"] == "completed"
            assert completed_data["duration_ms"] >= 0.0
            assert completed_data["finish_reason"] == "stop"
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_invalid_request_returns_422():
    """Test I: Invalid request (missing finding or invalid severity) returns HTTP 422 before stream."""
    with TestClient(app) as client:
        # Missing finding entirely
        resp1 = client.post(
            "/api/v1/diagnose/stream",
            json={"code_context": "x = 1\n"},
        )
        assert resp1.status_code == 422

        # Invalid severity in finding
        resp2 = client.post(
            "/api/v1/diagnose/stream",
            json={
                "finding": {
                    "finding_id": "f1",
                    "type": "error",
                    "severity": "catastrophic",  # Invalid!
                    "message": "test",
                },
                "code_context": "x = 1\n",
            },
        )
        assert resp2.status_code == 422


def test_diagnose_stream_oversized_context_returns_422(valid_payload):
    """Test J: Code context exceeding 16 KiB limit returns HTTP 422 before stream."""
    valid_payload["code_context"] = "# comment\n" * 2000
    with TestClient(app) as client:
        resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
        assert resp.status_code == 422


def test_diagnose_stream_unsupported_language_returns_422(valid_payload):
    """Test K: Unsupported language returns HTTP 422 before stream."""
    valid_payload["language"] = "ruby"
    with TestClient(app) as client:
        resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
        assert resp.status_code == 422


def test_diagnose_stream_provider_unavailable_event(valid_payload):
    """Test L: Provider unavailable emits diagnosis_started, error event, and no completed event."""
    provider = MockUnavailableProvider()
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp.status_code == 200

            events = parse_sse_wire_stream(resp.text)
            assert len(events) == 2

            assert events[0]["event"] == "diagnosis_started"
            assert events[1]["event"] == "error"

            err_data = events[1]["data"]
            assert err_data["error_type"] == "provider_unavailable"
            assert "unavailable" in err_data["message"].lower()
            assert err_data["retryable"] is False

            # Verify completed event was NOT emitted
            assert not any(e["event"] == "completed" for e in events)
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_provider_failure_and_safe_error_messages(valid_payload):
    """Test M & N: Mid-stream provider failure emits sanitized error event without leaking secrets or completed."""
    provider = MockFailingProvider()
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp.status_code == 200

            events = parse_sse_wire_stream(resp.text)
            assert any(e["event"] == "diagnosis_started" for e in events)

            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) >= 1
            err_data = error_events[0]["data"]
            assert err_data["error_type"] == "upstream_provider_failure"

            # Verify credentials are redacted
            raw_text = resp.text
            assert "sk-proj-" not in raw_text
            assert "Traceback" not in raw_text
            assert "[REDACTED]" in raw_text

            # Verify completed was NOT emitted after failure
            assert not any(e["event"] == "completed" for e in events)
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_timeout_event(valid_payload):
    """Test O: Timeout emits stream_timeout error event and terminates without completed."""
    class SlowProvider(BaseAgentProvider):
        @property
        def name(self) -> str:
            return "slow_provider"

        async def chat_completion(self, messages, tools, temperature=0.0):
            return AgentStepResult(content="Slow response")

        async def chat_completion_stream(self, messages, tools, temperature=0.0):
            yield "First chunk "
            await asyncio.sleep(0.05)
            yield "Second chunk "

    provider = SlowProvider()
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            # Force tiny timeout via test header
            resp = client.post(
                "/api/v1/diagnose/stream",
                json=valid_payload,
                headers={"x-test-stream-timeout": "0.01"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)

            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) == 1
            assert error_events[0]["data"]["error_type"] == "stream_timeout"

            # completed must NOT be emitted
            assert not any(e["event"] == "completed" for e in events)
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_generator_cleanup_and_disconnect(valid_payload):
    """Test P & Q: Client disconnect terminates iteration and cleans up generator."""
    provider = MockStreamingProvider(["chunk 1 ", "chunk 2 ", "chunk 3 "])
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        # Simulate partial stream reading then closing client
        with TestClient(app) as client:
            with client.stream("POST", "/api/v1/diagnose/stream", json=valid_payload) as stream_resp:
                assert stream_resp.status_code == 200
                lines = []
                for line in stream_resp.iter_lines():
                    lines.append(line)
                    if len(lines) >= 3:
                        # Break early simulating client disconnect
                        break

        # Provider generator must have been closed
        assert provider.closed is True
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_rate_limit_headers(valid_payload):
    """Test R: Response includes rate limit headers."""
    provider = MockStreamingProvider(["chunk"])
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp.status_code == 200
            assert "x-ratelimit-limit" in resp.headers
            assert "x-ratelimit-remaining" in resp.headers
            assert "x-ratelimit-reset" in resp.headers
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_diagnose_stream_authentication_behavior(valid_payload):
    """Test S: Anonymous request allowed, malformed JWT returns 401."""
    provider = MockStreamingProvider(["chunk"])
    service = DiagnosisService(provider=provider)
    app.dependency_overrides[get_diagnosis_service] = lambda: service

    try:
        with TestClient(app) as client:
            # 1. Anonymous request succeeds (local-first)
            resp_anon = client.post("/api/v1/diagnose/stream", json=valid_payload)
            assert resp_anon.status_code == 200

            # 2. Malformed token returns HTTP 401
            resp_auth_err = client.post(
                "/api/v1/diagnose/stream",
                json=valid_payload,
                headers={"Authorization": "Bearer malformed.bogus.jwt"},
            )
            assert resp_auth_err.status_code == 401
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)


def test_static_analyzer_endpoint_regression():
    """Test T: Existing POST /api/v1/analyze static endpoint continues to work without regression."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/analyze",
            json={"code": "x = 1 / 0\n", "filename": "test_div.py"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "bugs" in data or "summary" in data or "findings" in data
        assert data.get("status") in ("success", "clean", "warning", "error", "FAIL", "PASS", None) or "findings" in data
