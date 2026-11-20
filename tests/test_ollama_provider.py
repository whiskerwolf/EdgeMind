"""
Tests for Ollama Local AI Provider Integration in EdgeMind.

Verifies:
- OllamaAgentProvider initialization and configuration.
- Non-streaming chat completions.
- Native tool-calling parsing (dict arguments & string arguments).
- Multi-turn tool execution round-trip.
- Multiple tool calls within a single reasoning step.
- Streaming responses with incremental token delivery.
- Streaming cancellation and network interruption handling.
- Ollama unavailable / connection refused handling (HTTP 503).
- Request timeout handling (HTTP 504).
- Model not found handling (HTTP 404).
- Internal thinking exclusion (message.thinking and <think> tags).
- Local token usage accounting (LOCAL_INFERENCE source, 0/None API cost).
- Provider selection (ollama vs openai).
- Zero external OpenAI calls when Ollama is active.
- Opt-in live test against local Ollama running qwen3:4b.
"""

import asyncio
from decimal import Decimal
import json
import os
from typing import Any, Dict, List
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import (
    LiveAgentProvider,
    MockAgentProvider,
    OllamaAgentProvider,
    ThinkTagFilter,
)
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentStatus,
    ToolCall,
)
from core.agents.tools import ToolRegistry, default_tool_registry
from core.config import get_settings
from core.cost import (
    TokenUsage,
    UsageSource,
    default_cost_calculator,
)
from core.database.models import User
from core.database.repositories.usage_repository import UsageRepository
from core.routes.agent import get_agent_orchestrator


# -----------------------------------------------------------------------------
# 1. Initialization and Configuration
# -----------------------------------------------------------------------------

def test_ollama_provider_initialization_defaults():
    """Verify OllamaAgentProvider initializes with expected defaults."""
    provider = OllamaAgentProvider()
    assert provider.name == "ollama"
    assert provider.is_available() is True
    assert provider._model == "qwen3:4b"
    assert "11434" in provider._base_url
    assert provider._timeout >= 30.0


def test_ollama_provider_custom_parameters():
    """Verify custom parameters override defaults."""
    custom_transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    provider = OllamaAgentProvider(
        model="custom-model:latest",
        base_url="http://192.168.1.100:11434/",
        timeout=120.0,
        transport=custom_transport,
    )
    assert provider._model == "custom-model:latest"
    assert provider._base_url == "http://192.168.1.100:11434"
    assert provider._timeout == 120.0
    assert provider._transport is custom_transport


# -----------------------------------------------------------------------------
# 2. Non-Streaming Response and Token Accounting
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_non_streaming_chat_completion_success():
    """Verify non-streaming chat completion parses content and extracts local token accounting."""
    dummy_resp = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "Analysis completed. No boundary gaps detected.",
            "thinking": "Thinking through the constraints...",
        },
        "done": True,
        "prompt_eval_count": 45,
        "eval_count": 18,
        "total_duration": 1500000000,
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/chat"
        req_data = json.loads(req.content.decode("utf-8"))
        assert req_data["model"] == "qwen3:4b"
        assert req_data["stream"] is False
        return httpx.Response(200, json=dummy_resp)

    provider = OllamaAgentProvider(transport=httpx.MockTransport(mock_handler))
    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "Analyze code"}],
        tools=[],
    )

    assert step.finish_reason == "stop"
    assert step.content == "Analysis completed. No boundary gaps detected."
    assert step.thought is None  # Thinking field suppressed
    assert len(step.tool_calls) == 0

    # Local token accounting verification
    assert step.usage is not None
    assert step.usage.provider == "ollama"
    assert step.usage.model == "qwen3:4b"
    assert step.usage.prompt_tokens == 45
    assert step.usage.completion_tokens == 18
    assert step.usage.total_tokens == 63
    assert step.usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert step.usage.estimated_cost_usd is None  # Zero/None fabricated cost
    assert step.usage.is_estimated_cost_known is False


# -----------------------------------------------------------------------------
# 3. Native Tool Calling Parsing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_native_tool_call_parsing_dict_and_string():
    """Verify Ollama native tool calls are parsed whether arguments are dict or JSON string."""
    tool_resp = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_dict_1",
                    "function": {
                        "name": "parse_problem_constraints",
                        "arguments": {"raw_constraints": ["1 <= nums.length <= 1000"]},
                    },
                },
                {
                    "id": "call_str_2",
                    "function": {
                        "name": "analyze_problem_structure",
                        "arguments": json.dumps({"source_code": "def f(): pass"}),
                    },
                },
            ],
        },
        "done": True,
        "prompt_eval_count": 80,
        "eval_count": 25,
    }

    provider = OllamaAgentProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=tool_resp)))
    step = await provider.chat_completion(messages=[{"role": "user", "content": "test"}], tools=[])

    assert step.finish_reason == "tool_calls"
    assert len(step.tool_calls) == 2

    # Dict arguments parsed
    assert step.tool_calls[0].name == "parse_problem_constraints"
    assert step.tool_calls[0].id == "call_dict_1"
    assert step.tool_calls[0].get_arguments_dict()["raw_constraints"] == ["1 <= nums.length <= 1000"]

    # String arguments parsed
    assert step.tool_calls[1].name == "analyze_problem_structure"
    assert step.tool_calls[1].id == "call_str_2"
    assert step.tool_calls[1].get_arguments_dict()["source_code"] == "def f(): pass"


# -----------------------------------------------------------------------------
# 4. Multi-Turn Tool Execution Round Trip in Orchestrator
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_multi_turn_tool_execution_round_trip():
    """Verify AgentOrchestrator coordinates multi-turn tool calling with Ollama."""
    call_count = 0

    async def multi_turn_handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        data = json.loads(req.content.decode("utf-8"))

        if call_count == 1:
            # Turn 1: Model requests parse_problem_constraints tool
            return httpx.Response(
                200,
                json={
                    "model": "qwen3:4b",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_step1",
                                "function": {
                                    "name": "parse_problem_constraints",
                                    "arguments": {"raw_constraints": ["0 <= x <= 100"]},
                                },
                            }
                        ],
                    },
                    "done": True,
                    "prompt_eval_count": 50,
                    "eval_count": 20,
                },
            )
        else:
            # Turn 2: Verify tool result was passed back formatted as a tool role message
            messages = data["messages"]
            tool_msg = next((m for m in messages if m.get("role") == "tool"), None)
            assert tool_msg is not None, "Tool response message missing in turn 2"
            assert "constraint_spec" in tool_msg["content"]

            return httpx.Response(
                200,
                json={
                    "model": "qwen3:4b",
                    "message": {
                        "role": "assistant",
                        "content": "Synthesized edge case: x = 0 (minimum bound) and x = 100 (maximum bound).",
                    },
                    "done": True,
                    "prompt_eval_count": 90,
                    "eval_count": 35,
                },
            )

    provider = OllamaAgentProvider(transport=httpx.MockTransport(multi_turn_handler))
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)

    req = AgentAnalyzeRequest(
        code="def solve(x: int): return x * 2",
        filename="solution.py",
    )
    res = await orchestrator.run(req)

    assert res.status == "SUCCESS"
    assert res.ai_reasoning_performed is True
    assert len(res.tool_executions) == 1
    assert res.tool_executions[0].tool_name == "parse_problem_constraints"
    assert "Synthesized edge case" in (res.final_summary or "")
    assert res.usage is not None
    assert res.usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert res.usage.requests_count == 2


# -----------------------------------------------------------------------------
# 5. Multiple Tool Calls in Single Turn
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_multiple_tool_calls_in_single_turn():
    """Verify orchestrator processes multiple tool calls returned in a single turn."""
    call_idx = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return httpx.Response(
                200,
                json={
                    "model": "qwen3:4b",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "function": {
                                    "name": "parse_problem_constraints",
                                    "arguments": {"raw_constraints": ["1 <= n <= 50"]},
                                },
                            },
                            {
                                "id": "tc_2",
                                "function": {
                                    "name": "analyze_problem_structure",
                                    "arguments": {"source_code": "def count(n): pass"},
                                },
                            },
                        ],
                    },
                    "done": True,
                    "prompt_eval_count": 60,
                    "eval_count": 30,
                },
            )
        else:
            return httpx.Response(
                200,
                json={
                    "model": "qwen3:4b",
                    "message": {
                        "role": "assistant",
                        "content": "Both tools inspected. Analysis concluded.",
                    },
                    "done": True,
                    "prompt_eval_count": 110,
                    "eval_count": 15,
                },
            )

    provider = OllamaAgentProvider(transport=httpx.MockTransport(handler))
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)

    req = AgentAnalyzeRequest(code="def count(n): pass")
    res = await orchestrator.run(req)

    assert res.status == "SUCCESS"
    assert len(res.tool_executions) == 2
    assert res.tool_executions[0].tool_name == "parse_problem_constraints"
    assert res.tool_executions[1].tool_name == "analyze_problem_structure"


# -----------------------------------------------------------------------------
# 6. Streaming Responses with Incremental Content
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_streaming_response_parsing():
    """Verify streaming yields content chunks incrementally and terminates with AgentStepResult."""
    stream_lines = [
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "Analyzing "}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "problem "}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "boundaries."}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 30, "eval_count": 12}),
    ]
    raw_stream = "\n".join(stream_lines) + "\n"

    async def mock_stream_handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content.decode("utf-8"))["stream"] is True
        return httpx.Response(
            200,
            content=raw_stream.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
        )

    provider = OllamaAgentProvider(transport=httpx.MockTransport(mock_stream_handler))
    generator = provider.chat_completion_stream(
        messages=[{"role": "user", "content": "stream test"}],
        tools=[],
    )

    chunks = []
    final_step = None
    async for item in generator:
        if isinstance(item, str):
            chunks.append(item)
        else:
            final_step = item

    assert chunks == ["Analyzing ", "problem ", "boundaries."]
    assert final_step is not None
    assert final_step.finish_reason == "stop"
    assert final_step.content == "Analyzing problem boundaries."
    assert final_step.usage is not None
    assert final_step.usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert final_step.usage.prompt_tokens == 30
    assert final_step.usage.completion_tokens == 12


# -----------------------------------------------------------------------------
# 7. Thinking Field Exclusion (Non-Streaming and Streaming)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_thinking_field_exclusion_non_streaming():
    """Verify message.thinking and <think> tags are stripped in non-streaming responses."""
    resp_data = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "<think>Private thoughts: consider empty array.</think>The safe edge case is nums = [].",
            "thinking": "Model internal reasoning chain that must never leak.",
        },
        "done": True,
        "prompt_eval_count": 40,
        "eval_count": 15,
    }

    provider = OllamaAgentProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=resp_data)))
    step = await provider.chat_completion(messages=[{"role": "user", "content": "hi"}], tools=[])

    assert step.thought is None
    assert "Private thoughts" not in (step.content or "")
    assert "Model internal reasoning" not in (step.content or "")
    assert step.content == "The safe edge case is nums = []."


@pytest.mark.anyio
async def test_ollama_thinking_field_exclusion_streaming():
    """Verify message.thinking and <think>...</think> tags are filtered from stream chunks."""
    stream_lines = [
        # Chunk with thinking field (must be suppressed)
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "", "thinking": "Internal reasoning"}, "done": False}),
        # Chunks with split <think> tags in content (must be filtered)
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "Safe start. <thi"}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "nk>Secret thought</thi"}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": "nk> Safe end."}, "done": False}),
        json.dumps({"model": "qwen3:4b", "message": {"role": "assistant", "content": ""}, "done": True}),
    ]
    raw_stream = "\n".join(stream_lines) + "\n"

    provider = OllamaAgentProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw_stream.encode("utf-8")))
    )
    generator = provider.chat_completion_stream(messages=[{"role": "user", "content": "stream"}], tools=[])

    emitted_chunks = []
    final_step = None
    async for item in generator:
        if isinstance(item, str):
            emitted_chunks.append(item)
        else:
            final_step = item

    full_emitted = "".join(emitted_chunks)
    assert "Internal reasoning" not in full_emitted
    assert "Secret thought" not in full_emitted
    assert "<think>" not in full_emitted
    assert "</think>" not in full_emitted
    assert "Safe start." in full_emitted
    assert "Safe end." in full_emitted
    assert final_step.content == "Safe start.  Safe end."


# -----------------------------------------------------------------------------
# 8. Error Handling Matrix (Unavailable, Timeout, 404, Disconnect)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_unavailable_connection_refused():
    """Verify connection failure returns explicit 503 ollama_unavailable error without crashing."""
    def connect_error_handler(req: httpx.Request):
        raise httpx.ConnectError("Connection refused on 127.0.0.1:11434")

    provider = OllamaAgentProvider(transport=httpx.MockTransport(connect_error_handler))
    step = await provider.chat_completion(messages=[{"role": "user", "content": "ping"}], tools=[])

    assert step.finish_reason == "error"
    assert step.error_type == "ollama_unavailable"
    assert step.status_code == 503
    assert "Ensure Ollama is running" in step.content


@pytest.mark.anyio
async def test_ollama_request_timeout():
    """Verify timeout returns explicit 504 timeout error."""
    def timeout_handler(req: httpx.Request):
        raise httpx.TimeoutException("Read timed out")

    provider = OllamaAgentProvider(timeout=5.0, transport=httpx.MockTransport(timeout_handler))
    step = await provider.chat_completion(messages=[{"role": "user", "content": "ping"}], tools=[])

    assert step.finish_reason == "error"
    assert step.error_type == "timeout"
    assert step.status_code == 504


@pytest.mark.anyio
async def test_ollama_model_not_found_404():
    """Verify HTTP 404 returns explicit model_not_found error with pull instructions."""
    provider = OllamaAgentProvider(
        model="nonexistent-model:latest",
        transport=httpx.MockTransport(lambda r: httpx.Response(404, text="model nonexistent-model not found")),
    )
    step = await provider.chat_completion(messages=[{"role": "user", "content": "ping"}], tools=[])

    assert step.finish_reason == "error"
    assert step.error_type == "model_not_found"
    assert step.status_code == 404
    assert "ollama pull" in step.content


@pytest.mark.anyio
async def test_ollama_streaming_cancellation():
    """Verify stream disconnection marks finish_reason as interrupted without fabricating zeros."""
    async def interrupted_stream_handler(req: httpx.Request) -> httpx.Response:
        # Emit one chunk then disconnect with transport error
        async def mock_aiter():
            yield json.dumps({"model": "qwen3:4b", "message": {"content": "Initial chunk"}, "done": False}).encode("utf-8") + b"\n"
            raise httpx.ReadError("Connection severed by peer")

        return httpx.Response(200, content=mock_aiter())

    provider = OllamaAgentProvider(transport=httpx.MockTransport(interrupted_stream_handler))
    generator = provider.chat_completion_stream(messages=[{"role": "user", "content": "stream"}], tools=[])

    final_step = None
    async for item in generator:
        if not isinstance(item, str):
            final_step = item

    assert final_step is not None
    assert final_step.finish_reason == "interrupted"
    assert final_step.error_type == "interrupted_stream"
    assert final_step.usage.usage_source == UsageSource.UNAVAILABLE
    assert final_step.usage.prompt_tokens is None  # Never fabricated


# -----------------------------------------------------------------------------
# 9. Local Token Accounting Persistence
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ollama_local_token_accounting_persistence(sqlite_test_engine):
    """Verify Ollama usage is persisted in ai_token_usages and distinguished from OpenAI."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    tenant_id = uuid.uuid4()

    dummy_resp = {
        "model": "qwen3:4b",
        "message": {"role": "assistant", "content": "Complete static report."},
        "done": True,
        "prompt_eval_count": 120,
        "eval_count": 40,
    }

    provider = OllamaAgentProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=dummy_resp)))
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=1)

    async with session_factory() as session:
        user = User(
            id=tenant_id,
            email="ollama_user@example.com",
            full_name="Local User",
            password_hash="hash_placeholder",
            role="user",
        )
        session.add(user)
        await session.commit()

        req = AgentAnalyzeRequest(code="def check(): return True")
        res = await orchestrator.run(req, db=session, current_user=user)

        assert res.status == "SUCCESS"
        assert res.usage.usage_source == UsageSource.LOCAL_INFERENCE
        assert res.usage.total_tokens == 160
        assert res.usage.estimated_cost_usd is None

        # Verify database record in UsageRepository
        usage_repo = UsageRepository(session)
        summary = await usage_repo.get_summary(user_id=tenant_id)
        assert summary["requests_count"] == 1
        assert summary["total_prompt_tokens"] == 120
        assert summary["total_completion_tokens"] == 40
        assert summary["by_source"].get("LOCAL_INFERENCE") == 1
        assert summary["total_estimated_cost_usd"] is None  # Zero cloud cost


# -----------------------------------------------------------------------------
# 10. Provider Selection and Zero Accidental OpenAI Calls
# -----------------------------------------------------------------------------

def test_provider_selection_env_configuration(monkeypatch):
    """Verify provider selection matches environment configuration."""
    body = AgentAnalyzeRequest(code="def f(): pass")

    # Mode 1: Ollama
    monkeypatch.setattr(get_settings(), "agent_provider", "ollama")
    orch_ollama = get_agent_orchestrator(body)
    assert isinstance(orch_ollama.provider, OllamaAgentProvider)

    # Mode 2: OpenAI
    monkeypatch.setattr(get_settings(), "agent_provider", "openai")
    orch_openai = get_agent_orchestrator(body)
    assert isinstance(orch_openai.provider, LiveAgentProvider)


@pytest.mark.anyio
async def test_no_accidental_openai_calls_in_ollama_mode(monkeypatch):
    """Verify that when Ollama is configured, no requests are dispatched to OpenAI endpoints."""
    openai_called = False

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        nonlocal openai_called
        if "openai.com" in str(req.url):
            openai_called = True
            return httpx.Response(500, text="Unexpected OpenAI call")
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "Executed locally."},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    provider = OllamaAgentProvider(transport=httpx.MockTransport(mock_handler))
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=1)

    req = AgentAnalyzeRequest(code="def test(): pass")
    res = await orchestrator.run(req)

    assert res.status == "SUCCESS"
    assert openai_called is False, "Accidental request dispatched to OpenAI!"


# -----------------------------------------------------------------------------
# 11. Opt-In Local Genuine Ollama Integration Test (Real qwen3:4b)
# -----------------------------------------------------------------------------

def is_local_ollama_online() -> bool:
    """Check whether local Ollama server is responsive at 127.0.0.1:11434."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not (
        (os.environ.get("EDGEMIND_RUN_LOCAL_OLLAMA_TESTS", "").lower() in ("true", "1", "yes") or is_local_ollama_online())
    ),
    reason="LOCAL OLLAMA TESTS NOT RUN: Requires running Ollama server at http://127.0.0.1:11434 with qwen3:4b",
)
@pytest.mark.anyio
async def test_real_local_ollama_qwen3_integration():
    """
    Live smoke test against real local Ollama installation running qwen3:4b.
    Verifies actual HTTP response, tool calling, and local token metrics.
    """
    provider = OllamaAgentProvider(model="qwen3:4b", timeout=120.0)

    # 1. Non-streaming live chat
    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "Respond 'Local OK' in 2 words."}],
        tools=[],
    )

    assert step.finish_reason == "stop"
    assert step.content is not None
    assert "Local" in step.content or "OK" in step.content
    assert step.thought is None  # Suppressed thinking field
    assert step.usage is not None
    assert step.usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert step.usage.provider == "ollama"
    assert step.usage.model == "qwen3:4b"
    assert step.usage.prompt_tokens > 0
    assert step.usage.completion_tokens > 0
    assert step.usage.estimated_cost_usd is None

    # 2. Native tool call against real qwen3:4b
    tools = default_tool_registry.get_schemas()
    tool_step = await provider.chat_completion(
        messages=[{"role": "user", "content": "What are the constraints for '1 <= nums.length <= 100'? Use the parse_problem_constraints tool."}],
        tools=tools,
    )

    assert tool_step.finish_reason in ("tool_calls", "stop")
    if tool_step.tool_calls:
        tc = tool_step.tool_calls[0]
        assert tc.name == "parse_problem_constraints"
        args = tc.get_arguments_dict()
        assert "raw_constraints" in args
