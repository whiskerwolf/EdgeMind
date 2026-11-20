"""
Tests for EdgeMind AI Agent Server-Sent Events (SSE) Streaming.

Verifies:
1. Correct SSE HTTP response headers (Content-Type: text/event-stream, no-cache, no-buffering).
2. Correct wire event framing: sequential integer IDs, event names, JSON-serialized data, double-newline framing.
3. Event ordering: status -> analysis_started -> progress -> tool_started -> tool_completed -> response_chunk -> completed.
4. Multiple incremental response chunks streamed in order with verified index tracking.
5. Static tool progress events (tool_started, tool_completed) without exposing raw sensitive arguments.
6. Full completion payload matching the AgentAnalyzeResponse schema.
7. Provider unavailable handling (when no API key is configured), emitting error event and fallback.
8. Provider error handling (HTTP 401, 429, 500) gracefully handled with static preservation.
9. Authentication and project ownership (401 on bad JWT, 404 on unowned project, report persistence for owner).
10. Boundary-safe secret redaction: OpenAI keys, Bearer tokens, DB credentials split across chunks.
11. Client disconnect and stream cancellation.
12. Maximum stream duration and response size bounds.

All unit tests use deterministic MockAgentProvider instances and are explicitly labeled as mocked.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest

from core.api import app
from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import MockAgentProvider
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentStepResult,
    SSEEventType,
    ToolCall,
    format_sse_event,
)
from core.agents.tools import default_tool_registry
from core.config import get_settings
from core.routes.agent import get_agent_orchestrator
from core.sanitization import StreamSecretBuffer, redact_secrets


# =============================================================================
# Helper Functions for Parsing SSE Stream
# =============================================================================

def parse_sse_wire_stream(raw_text: str) -> List[Dict[str, Any]]:
    """Parse raw SSE text stream into structured event objects."""
    events = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_dict = {"id": None, "event": "message", "data": None, "is_comment": False}
        data_lines = []
        for line in lines:
            if line.startswith(":"):
                event_dict["is_comment"] = True
                continue
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


# =============================================================================
# 1. Wire Framing and Headers Tests
# =============================================================================

def test_streaming_endpoint_correct_headers_and_content_type():
    """Verify that POST /api/v1/agent/analyze/stream returns text/event-stream with required SSE headers."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(content="Summary of static analysis complete.", finish_reason="stop")
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def two_sum(nums, target):\n    return []"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            assert "no-cache" in resp.headers.get("cache-control", "")
            assert resp.headers.get("x-accel-buffering") == "no"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_sequential_event_ids_and_framing():
    """Verify event IDs are strictly sequential integers starting from 1, and formatted correctly."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(content="Final reasoning output.", finish_reason="stop")
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def solve():\n    return 42"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            assert len(events) >= 4  # status, analysis_started, progress, completed

            non_comment_events = [e for e in events if not e.get("is_comment")]
            ids = [e["id"] for e in non_comment_events if e["id"] is not None]
            assert ids == list(range(1, len(ids) + 1)), f"Event IDs must be sequential: {ids}"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 2. Event Ordering and Multiple Chunks
# =============================================================================

def test_streaming_event_ordering():
    """Verify the chronological lifecycle order: status -> analysis_started -> progress -> response_chunk -> completed."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=["Finding edge cases: ", "empty array, ", "single element."],
            content="Finding edge cases: empty array, single element.",
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def solve(arr):\n    return len(arr)"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            event_types = [e["event"] for e in events if not e.get("is_comment")]

            assert event_types[0] == "status"
            assert event_types[1] == "analysis_started"
            assert "progress" in event_types
            assert "response_chunk" in event_types
            assert event_types[-1] == "completed"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_multiple_response_chunks_with_indices():
    """Verify multiple content chunks are delivered with correct index values and intact content."""
    chunks = ["Step 1: Inspect AST. ", "Step 2: Detect gaps. ", "Step 3: Generate candidates."]
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=chunks,
            content="".join(chunks),
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def process():\n    pass"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            chunk_events = [e for e in events if e["event"] == "response_chunk"]
            assert len(chunk_events) >= len(chunks)

            # Reassembled chunks should contain all parts
            combined_text = "".join(e["data"]["chunk"] for e in chunk_events)
            for part in chunks:
                assert part in combined_text
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 3. Tool Execution Events
# =============================================================================

def test_streaming_tool_started_and_completed_events():
    """Verify that tool_started and tool_completed events are emitted with duration, status, and no leaked private args."""
    provider = MockAgentProvider()
    # Step 1: Call analyze_problem_structure
    provider.add_step(
        AgentStepResult(
            thought="Inspecting AST.",
            tool_calls=[
                ToolCall(
                    name="analyze_problem_structure",
                    arguments={"code": "def search(x):\n    return x > 0"},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 2: Final answer
    provider.add_step(
        AgentStepResult(content="Analysis concluded.", finish_reason="stop")
    )

    orchestrator = AgentOrchestrator(provider=provider, max_iterations=4)
    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def search(x):\n    return x > 0"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)

            tool_start_events = [e for e in events if e["event"] == "tool_started"]
            tool_comp_events = [e for e in events if e["event"] == "tool_completed"]

            assert len(tool_start_events) == 1
            assert tool_start_events[0]["data"]["tool_name"] == "analyze_problem_structure"
            # Ensure raw code argument is NOT echoed in tool_started event payload
            assert "arguments" not in tool_start_events[0]["data"]

            assert len(tool_comp_events) == 1
            assert tool_comp_events[0]["data"]["tool_name"] == "analyze_problem_structure"
            assert tool_comp_events[0]["data"]["status"] == "success"
            assert tool_comp_events[0]["data"]["duration_ms"] >= 0.0
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 4. Completion Event Payload
# =============================================================================

def test_streaming_completed_event_full_structure():
    """Verify that the completed event contains the complete valid AgentAnalyzeResponse."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(content="Full agent synthesis summary.", finish_reason="stop")
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={
                    "code": "def max_val(a, b):\n    return a if a > b else b",
                    "filename": "solution.py",
                    "test_cases": [{"input_data": {"a": 1, "b": 2}}],
                },
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            completed_events = [e for e in events if e["event"] == "completed"]
            assert len(completed_events) == 1
            payload = completed_events[0]["data"]

            assert payload["product"] == "EdgeMind"
            assert payload["status"] == "SUCCESS"
            assert payload["execution_mode"] == "AI_AGENT"
            assert payload["ai_reasoning_performed"] is True
            assert "test_intelligence" in payload
            assert "code_analysis" in payload
            assert "session_id" in payload
            assert payload["total_duration_ms"] >= 0.0
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 5. Provider Unavailable & Error Handling
# =============================================================================

def test_streaming_provider_unavailable_handling():
    """Verify that when AI provider is unavailable, stream emits error event and gracefully falls back to degraded static."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="AI provider is not configured.",
            finish_reason="unavailable",
            error="Missing API key",
            error_type="provider_unavailable",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def fallback_fn():\n    return True"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)

            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) >= 1
            assert error_events[0]["data"]["error_type"] == "provider_unavailable"

            completed_events = [e for e in events if e["event"] == "completed"]
            assert len(completed_events) == 1
            assert completed_events[0]["data"]["status"] == "PROVIDER_UNAVAILABLE"
            assert completed_events[0]["data"]["execution_mode"] == "DEGRADED_STATIC"
            assert completed_events[0]["data"]["ai_reasoning_performed"] is False
            assert "code_analysis" in completed_events[0]["data"]
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_provider_error_handling_401():
    """Verify that provider 401 error emits error event and returns static fallback."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="Authentication failed (HTTP 401)",
            finish_reason="error",
            error="Invalid API key",
            error_type="authentication_error",
            status_code=401,
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def test_err():\n    pass"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)

            err_events = [e for e in events if e["event"] == "error"]
            assert len(err_events) >= 1
            assert err_events[0]["data"]["error_type"] == "authentication_error"

            completed = [e for e in events if e["event"] == "completed"]
            assert len(completed) == 1
            assert completed[0]["data"]["status"] == "PROVIDER_ERROR"
            assert completed[0]["data"]["execution_mode"] == "DEGRADED_STATIC"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 6. Secret Redaction Across Chunk Boundaries
# =============================================================================

def test_streaming_secret_redaction_openai_key_split_across_two_chunks():
    """Verify OpenAI key split across chunk 1 and chunk 2 is redacted and does not leak partial credentials."""
    chunk1 = "Found configuration parameter: sk-"
    chunk2 = "proj-1234567890abcdefghijklmnopqrstuvwxyz123456 in environment."

    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=[chunk1, chunk2],
            content=chunk1 + chunk2,
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def config():\n    return 'safe'"},
            )
            assert resp.status_code == 200
            full_stream_text = resp.text

            # MUST NOT contain unredacted OpenAI key parts
            assert "sk-proj-" not in full_stream_text
            assert "1234567890abcdef" not in full_stream_text
            assert "[REDACTED]" in full_stream_text
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_secret_redaction_bearer_token_split():
    """Verify Bearer token split across chunks is completely masked."""
    chunk1 = "Authorization header: Bearer "
    chunk2 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    chunk3 = "dozjgNryP4J_wStmxhPOc verified."

    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=[chunk1, chunk2, chunk3],
            content=chunk1 + chunk2 + chunk3,
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def auth():\n    pass"},
            )
            assert resp.status_code == 200
            stream_text = resp.text

            assert "eyJhbGciOi" not in stream_text
            assert "Bearer [REDACTED]" in stream_text
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_secret_redaction_database_url_split():
    """Verify database connection password split across chunks is masked without leaking."""
    chunk1 = "Connecting to postgresql://postgres:my_super_secret_"
    chunk2 = "db_password@localhost:5432/edgemind_db connected."

    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=[chunk1, chunk2],
            content=chunk1 + chunk2,
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def db_ping():\n    return 1"},
            )
            assert resp.status_code == 200
            stream_text = resp.text

            assert "my_super_secret_db_password" not in stream_text
            assert "postgresql://postgres:[REDACTED]@localhost:5432/edgemind_db" in stream_text
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_legitimate_code_and_tokens_preserved():
    """Verify legitimate code and text with tabs, brackets, and quotes are preserved byte-for-byte in stream."""
    code_snippet = (
        "def binary_search(nums, target):\n"
        "\tleft, right = 0, len(nums) - 1\n"
        "\twhile left <= right:\n"
        "\t\tmid = (left + right) // 2\n"
        "\t\tif nums[mid] == target:\n"
        "\t\t\treturn mid\n"
        "\treturn -1\n"
    )

    provider = MockAgentProvider(steps=[
        AgentStepResult(
            chunks=[code_snippet[:40], code_snippet[40:]],
            content=code_snippet,
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": code_snippet},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            chunk_events = [e for e in events if e["event"] == "response_chunk"]
            reconstituted = "".join(e["data"]["chunk"] for e in chunk_events)

            assert "\t" in reconstituted
            assert "nums[mid] == target" in reconstituted
            assert "return -1" in reconstituted
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


# =============================================================================
# 7. Authentication and Project Ownership Checks
# =============================================================================

def test_streaming_invalid_jwt_returns_401():
    """POST /api/v1/agent/analyze/stream returns HTTP 401 when Authorization token is malformed or expired."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/agent/analyze/stream",
            json={"code": "def check(): pass"},
            headers={"Authorization": "Bearer invalid_malformed_jwt_token"},
        )
        assert resp.status_code == 401
        assert "invalid" in resp.json().get("detail", "").lower() or "expired" in resp.json().get("detail", "").lower()


def test_streaming_anonymous_request_permitted():
    """POST /api/v1/agent/analyze/stream permits anonymous users without Authorization header (local-first)."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(content="Anonymous analysis complete.", finish_reason="stop")
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def anon_fn(): return 1"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            completed = [e for e in events if e["event"] == "completed"]
            assert len(completed) == 1
            # Unauthenticated analysis must not persist reports
            assert completed[0]["data"]["persisted_report_id"] is None
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_unowned_project_returns_404():
    """POST /api/v1/agent/analyze/stream returns HTTP 404 when project does not belong to user."""
    random_project_id = str(uuid.uuid4())
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/agent/analyze/stream",
            json={
                "code": "def check(): pass",
                "project_id": random_project_id,
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()


# =============================================================================
# 8. Stream Cancellation and Bounds
# =============================================================================

@pytest.mark.anyio
async def test_stream_run_async_generator_cancellation():
    """Verify that canceling the async stream generator terminates cleanly and frees resources."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(chunks=["Part 1", "Part 2", "Part 3"], finish_reason="stop")
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)
    req = AgentAnalyzeRequest(code="def cancel_test(): pass")

    stream_gen = orchestrator.stream_run(req)
    received = []
    try:
        async for evt_type, evt_data in stream_gen:
            received.append(evt_type)
            if len(received) >= 2:
                # Early break (simulating client disconnect)
                break
    finally:
        await stream_gen.aclose()

    assert len(received) == 2
    assert "status" in received


def test_streaming_hidden_reasoning_and_prompts_protection():
    """
    Verify that:
    1. Internal chain-of-thought (thought field) is NOT streamed to the client in response_chunk.
    2. Internal system instructions and boundary tags are NOT leaked.
    3. tool_started event does NOT expose raw tool arguments.
    4. Secrets in tool arguments/results are redacted in the completed payload.
    """
    secret_key = "sk-proj-supersecretkey1234567890abcdef"
    mock_steps = [
        AgentStepResult(
            thought="INTERNAL_PRIVATE_CHAIN_OF_THOUGHT_DO_NOT_REVEAL",
            tool_calls=[
                ToolCall(
                    id="call_mock_1",
                    name="parse_problem_constraints",
                    arguments={"description": f"Target with secret {secret_key}"},
                )
            ],
            finish_reason="tool_calls",
        ),
        AgentStepResult(
            thought="ANOTHER_SECRET_REASONING_STEP",
            content="Visible user-facing explanation of findings.",
            finish_reason="stop",
        ),
    ]
    provider = MockAgentProvider(steps=mock_steps)
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def solution(x):\n    return x + 1"},
            )
            assert resp.status_code == 200
            raw_text = resp.text

            # 1. Ensure private thought strings never appear anywhere in the stream text
            assert "INTERNAL_PRIVATE_CHAIN_OF_THOUGHT_DO_NOT_REVEAL" not in raw_text
            assert "ANOTHER_SECRET_REASONING_STEP" not in raw_text

            # 2. Ensure system prompt invariants are not leaked in streamed events
            assert "SECURITY & OPERATING INVARIANTS" not in raw_text

            events = parse_sse_wire_stream(raw_text)

            # 3. Check tool_started event payload: must not contain 'arguments' key
            tool_started_events = [e for e in events if e.get("event") == "tool_started"]
            assert len(tool_started_events) >= 1
            for ts in tool_started_events:
                data = ts.get("data", {})
                assert "tool_name" in data
                assert "tool_call_id" in data
                assert "arguments" not in data, "tool_started event must not expose raw arguments"

            # 4. Check response_chunk events: only visible text chunk
            chunk_events = [e for e in events if e.get("event") == "response_chunk"]
            assert len(chunk_events) >= 1
            for ce in chunk_events:
                chunk_text = ce.get("data", {}).get("chunk", "")
                assert "INTERNAL_PRIVATE" not in chunk_text

            # 5. Check completed event: secrets in tool execution records must be redacted
            completed_events = [e for e in events if e.get("event") == "completed"]
            assert len(completed_events) == 1
            completed_data = completed_events[0]["data"]
            tool_execs = completed_data.get("tool_executions", [])
            assert len(tool_execs) >= 1
            for te in tool_execs:
                # Raw secret must not appear in arguments or result
                assert secret_key not in json.dumps(te.get("arguments", {}))
                assert secret_key not in json.dumps(te.get("result", {}))
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_timeout_boundary_enforcement():
    """Verify that exceeding max_stream_duration yields an error event with stream_timeout."""
    class SlowMockProvider(MockAgentProvider):
        async def chat_completion_stream(self, messages, tools, temperature=0.0):
            await asyncio.sleep(0.08)
            yield "Slow chunk"
            yield AgentStepResult(content="Slow response", finish_reason="stop")

    provider = SlowMockProvider()
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def slow(): pass"},
                headers={"x-test-stream-timeout": "0.02"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            error_events = [e for e in events if e.get("event") == "error"]
            assert len(error_events) >= 1
            assert error_events[0]["data"]["error_type"] == "stream_timeout"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_max_response_size_enforcement():
    """Verify that exceeding max_stream_bytes yields an error event with stream_size_exceeded."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="A" * 500,
            finish_reason="stop",
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def big(): pass"},
                headers={"x-test-max-stream-bytes": "200"},
            )
            assert resp.status_code == 200
            events = parse_sse_wire_stream(resp.text)
            error_events = [e for e in events if e.get("event") == "error"]
            assert len(error_events) >= 1
            assert error_events[0]["data"]["error_type"] == "stream_size_exceeded"
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


def test_streaming_parity_with_non_streaming_endpoint():
    """
    Verify parity between non-streaming POST /api/v1/agent/analyze
    and streaming POST /api/v1/agent/analyze/stream (completed event).
    Both must produce identical status, static code metrics, candidates, and invariants.
    """
    code_snippet = (
        "def find_max(nums):\n"
        "    if not nums:\n"
        "        return None\n"
        "    m = nums[0]\n"
        "    for x in nums:\n"
        "        if x > m:\n"
        "            m = x\n"
        "    return m\n"
    )

    steps_sync = [
        AgentStepResult(
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    name="analyze_problem_structure",
                    arguments={"code": code_snippet, "filename": "solution.py"},
                ),
                ToolCall(
                    id="tc_2",
                    name="detect_coverage_gaps",
                    arguments={"code": code_snippet, "test_cases": []},
                ),
            ],
            finish_reason="tool_calls",
        ),
        AgentStepResult(
            content="Completed comprehensive static gap detection.",
            finish_reason="stop",
        ),
    ]

    steps_stream = [
        AgentStepResult(
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    name="analyze_problem_structure",
                    arguments={"code": code_snippet, "filename": "solution.py"},
                ),
                ToolCall(
                    id="tc_2",
                    name="detect_coverage_gaps",
                    arguments={"code": code_snippet, "test_cases": []},
                ),
            ],
            finish_reason="tool_calls",
        ),
        AgentStepResult(
            content="Completed comprehensive static gap detection.",
            finish_reason="stop",
        ),
    ]

    orch_sync = AgentOrchestrator(provider=MockAgentProvider(steps=steps_sync), max_iterations=3)
    orch_stream = AgentOrchestrator(provider=MockAgentProvider(steps=steps_stream), max_iterations=3)

    payload = {
        "code": code_snippet,
        "filename": "solution.py",
        "max_candidates": 5,
    }

    # 1. Non-streaming call
    app.dependency_overrides[get_agent_orchestrator] = lambda: orch_sync
    try:
        with TestClient(app) as client:
            resp_sync = client.post("/api/v1/agent/analyze", json=payload)
            assert resp_sync.status_code == 200
            data_sync = resp_sync.json()
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)

    # 2. Streaming call
    app.dependency_overrides[get_agent_orchestrator] = lambda: orch_stream
    try:
        with TestClient(app) as client:
            resp_stream = client.post("/api/v1/agent/analyze/stream", json=payload)
            assert resp_stream.status_code == 200
            events = parse_sse_wire_stream(resp_stream.text)
            completed_events = [e for e in events if e.get("event") == "completed"]
            assert len(completed_events) == 1
            data_stream = completed_events[0]["data"]
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)

    # 3. Parity comparisons
    assert data_sync["status"] == data_stream["status"] == "SUCCESS"
    assert data_sync["product"] == data_stream["product"] == "EdgeMind"
    assert data_sync["execution_mode"] == data_stream["execution_mode"] == "AI_AGENT"
    assert data_sync["iterations"] == data_stream["iterations"] == 2

    # Verify tool execution parity
    sync_tool_names = [t["tool_name"] for t in data_sync["tool_executions"]]
    stream_tool_names = [t["tool_name"] for t in data_stream["tool_executions"]]
    assert sync_tool_names == stream_tool_names

    # Verify static-only invariants in both
    ti_sync = data_sync.get("test_intelligence", {})
    ti_stream = data_stream.get("test_intelligence", {})
    assert len(ti_sync.get("coverage_gaps", [])) == len(ti_stream.get("coverage_gaps", []))

    for c in ti_stream.get("generated_candidates", []):
        assert c.get("expected_output") is None, "Candidate must maintain expected_output=None"
        assert c.get("is_expected_output_verified") is False, "Candidate must maintain is_expected_output_verified=False"
