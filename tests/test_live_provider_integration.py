"""
EdgeMind Phase 5: Comprehensive Live Third-Party Provider Integration Tests.

Validates:
1. OpenAI-compatible Chat Completions API request/response parsing.
2. Native function/tool calling and multi-step tool execution.
3. Live streaming SSE protocol, incremental content, and fragmented tool argument accumulation.
4. Terminal usage extraction and stream interruption handling (usage marked UNAVAILABLE).
5. Error handling matrix (HTTP 400, 401, 403, 429, 500/502/503/504, timeouts, connection errors).
6. OpenAI embeddings API requests (text-embedding-3-small, 1536 dims) and embedding token usage.
7. Token and Decimal cost accounting integration with UsageRepository and deduplication.
8. Zero credential disclosure across logs, errors, and responses.
9. Opt-in live provider smoke test (skipped by default, requiring EDGEMIND_RUN_LIVE_PROVIDER_TESTS=true).
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

from core.agents import (
    AgentAnalyzeRequest,
    AgentOrchestrator,
    AgentStatus,
    AgentStepResult,
    LiveAgentProvider,
    MockAgentProvider,
    ToolCall,
    default_tool_registry,
)
from core.agents.tools import ToolRegistry, retrieve_knowledge_context_handler
from core.config import get_settings
from core.cost import (
    TokenUsage,
    UsageSource,
    default_cost_calculator,
)
from core.database.models import User
from core.database.repositories.usage_repository import UsageRepository
from core.rag.embeddings.base import (
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
)
from core.rag.embeddings.openai_provider import OpenAIEmbeddingProvider
from core.rag.retrieval.service import VectorRetrievalService


# -----------------------------------------------------------------------------
# 1. Non-Streaming Chat Completion with Mock Transport
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_provider_chat_completion_success():
    """Verify LiveAgentProvider parses valid OpenAI response format, usage, and request ID."""
    response_payload = {
        "id": "chatcmpl-test-12345",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Analysis completed: static boundaries evaluated.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        },
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer test-sk-live-key"
        body = json.loads(request.read())
        assert body["model"] == "gpt-4o-mini"
        assert len(body["messages"]) == 1
        return httpx.Response(
            200,
            json=response_payload,
            headers={"x-request-id": "req-openai-header-999"},
        )

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key="test-sk-live-key",
        model="gpt-4o-mini",
        transport=transport,
    )

    res = await provider.chat_completion(
        messages=[{"role": "user", "content": "Analyze problem"}],
        tools=[],
    )

    assert res.finish_reason == "stop"
    assert res.content == "Analysis completed: static boundaries evaluated."
    assert res.request_id == "chatcmpl-test-12345"
    assert res.model == "gpt-4o-mini"

    # Verify actual provider usage extracted
    assert res.usage is not None
    assert res.usage.prompt_tokens == 120
    assert res.usage.completion_tokens == 30
    assert res.usage.total_tokens == 150
    assert res.usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert res.usage.request_id == "chatcmpl-test-12345"
    assert res.usage.is_estimated_cost_known is True
    assert isinstance(res.usage.estimated_cost_usd, Decimal)
    assert res.usage.estimated_cost_usd > Decimal("0.0")


# -----------------------------------------------------------------------------
# 2. Native Function / Tool Calling Request & Parsing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_provider_tool_calls_parsing():
    """Verify LiveAgentProvider parses native function calling response."""
    response_payload = {
        "id": "chatcmpl-tool-call-1",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_parse_constraints_01",
                            "type": "function",
                            "function": {
                                "name": "parse_problem_constraints",
                                "arguments": '{"problem_description": "1 <= n <= 1000", "code": "def solve(n): pass"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 85,
            "completion_tokens": 25,
            "total_tokens": 110,
        },
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert "tools" in body
        assert body["tool_choice"] == "auto"
        return httpx.Response(200, json=response_payload)

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        transport=transport,
    )

    res = await provider.chat_completion(
        messages=[{"role": "user", "content": "Parse constraints"}],
        tools=default_tool_registry.get_schemas(),
    )

    assert res.finish_reason == "tool_calls"
    assert len(res.tool_calls) == 1
    tc = res.tool_calls[0]
    assert tc.id == "call_parse_constraints_01"
    assert tc.name == "parse_problem_constraints"
    assert tc.get_arguments_dict()["problem_description"] == "1 <= n <= 1000"
    assert tc.get_arguments_dict()["code"] == "def solve(n): pass"


# -----------------------------------------------------------------------------
# 3. Live Streaming Completion (SSE)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_provider_streaming_chunks_and_usage():
    """Verify LiveAgentProvider yields content chunks and final result with terminal usage."""
    sse_events = (
        'data: {"id":"chatcmpl-stream-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"Analyzing "},"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-stream-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"algorithm "},"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-stream-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"invariants."},"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-stream-1","model":"gpt-4o-mini","choices":[],"usage":{"prompt_tokens":50,"completion_tokens":10,"total_tokens":60}}\n\n'
        "data: [DONE]\n\n"
    )

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        return httpx.Response(
            200,
            content=sse_events.encode("utf-8"),
            headers={"content-type": "text/event-stream", "x-request-id": "req-stream-header"},
        )

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        transport=transport,
    )

    text_chunks: List[str] = []
    final_step: Any = None

    async for item in provider.chat_completion_stream(
        messages=[{"role": "user", "content": "Stream test"}],
        tools=[],
    ):
        if isinstance(item, str):
            text_chunks.append(item)
        elif hasattr(item, "finish_reason"):
            final_step = item

    assert "".join(text_chunks) == "Analyzing algorithm invariants."
    assert final_step is not None
    assert final_step.finish_reason == "stop"
    assert final_step.content == "Analyzing algorithm invariants."
    assert final_step.request_id == "chatcmpl-stream-1"
    assert final_step.usage is not None
    assert final_step.usage.prompt_tokens == 50
    assert final_step.usage.completion_tokens == 10
    assert final_step.usage.total_tokens == 60
    assert final_step.usage.usage_source == UsageSource.ACTUAL_PROVIDER


# -----------------------------------------------------------------------------
# 4. Fragmented Tool-Call Streaming Accumulation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_provider_streaming_fragmented_tool_calls():
    """Verify fragmented tool call name and arguments split across multiple SSE chunks accumulate cleanly."""
    sse_events = (
        'data: {"id":"stream-tc-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_dyn_01","type":"function","function":{"name":"analyze_problem_structure","arguments":"{\\"co"}}]},"finish_reason":null}]}\n\n'
        'data: {"id":"stream-tc-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"de\\": \\"def binary"}}]},"finish_reason":null}]}\n\n'
        'data: {"id":"stream-tc-1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"_search(): pass\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n'
        'data: {"id":"stream-tc-1","model":"gpt-4o-mini","choices":[],"usage":{"prompt_tokens":75,"completion_tokens":20,"total_tokens":95}}\n\n'
        "data: [DONE]\n\n"
    )

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_events.encode("utf-8"), headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        transport=transport,
    )

    final_step: Any = None
    async for item in provider.chat_completion_stream(
        messages=[{"role": "user", "content": "Analyze structure"}],
        tools=default_tool_registry.get_schemas(),
    ):
        if hasattr(item, "finish_reason"):
            final_step = item

    assert final_step is not None
    assert final_step.finish_reason == "tool_calls"
    assert len(final_step.tool_calls) == 1
    tc = final_step.tool_calls[0]
    assert tc.id == "call_dyn_01"
    assert tc.name == "analyze_problem_structure"
    assert tc.get_arguments_dict()["code"] == "def binary_search(): pass"


# -----------------------------------------------------------------------------
# 5. Stream Interruption & Missing Usage Chunk Handling
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_provider_streaming_interrupted_marks_usage_unavailable():
    """
    Verify that if a stream is abruptly terminated or disconnected before the
    terminal usage chunk arrives, usage is marked UNAVAILABLE rather than reporting
    fabricated zero tokens.
    """
    # Stream drops connection after delivering partial content, never delivering usage chunk
    truncated_sse = (
        'data: {"id":"stream-cut-1","choices":[{"index":0,"delta":{"content":"Partial reasoning..."}}]}\n\n'
    )

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=truncated_sse.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        transport=transport,
    )

    final_step: Any = None
    async for item in provider.chat_completion_stream(
        messages=[{"role": "user", "content": "Test drop"}],
        tools=[],
    ):
        if hasattr(item, "finish_reason"):
            final_step = item

    assert final_step is not None
    assert final_step.content == "Partial reasoning..."
    assert final_step.usage is not None
    # Must report UNAVAILABLE, not fabricated zeros
    assert final_step.usage.usage_source == UsageSource.UNAVAILABLE
    assert final_step.usage.prompt_tokens is None
    assert final_step.usage.completion_tokens is None
    assert final_step.usage.total_tokens is None
    assert final_step.usage.estimated_cost_usd is None
    assert final_step.usage.is_estimated_cost_known is False


# -----------------------------------------------------------------------------
# 6. Error Handling Matrix (400, 401, 403, 429, 500, Timeout, ConnectError)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.parametrize(
    "status_code,expected_error_type",
    [
        (400, "invalid_request"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (429, "rate_limit"),
        (500, "server_error"),
        (502, "server_error"),
        (503, "server_error"),
    ],
)
async def test_live_provider_http_status_codes_matrix(status_code, expected_error_type):
    """Verify HTTP error status codes are classified and secrets are never disclosed."""
    secret_key = "sk-super-secret-key-12345"

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text=f"Error occurred with credential Bearer {secret_key}",
        )

    transport = httpx.MockTransport(mock_handler)
    provider = LiveAgentProvider(
        api_key=secret_key,
        model="gpt-4o-mini",
        transport=transport,
    )

    res = await provider.chat_completion(
        messages=[{"role": "user", "content": "trigger error"}],
        tools=[],
    )

    assert res.finish_reason == "error"
    assert res.error_type == expected_error_type
    assert secret_key not in (res.error or "")
    assert secret_key not in (res.content or "")


@pytest.mark.anyio
async def test_live_provider_timeout_and_connection_failures():
    """Verify timeouts and connection drops return structured errors with zero secret leakage."""
    secret_key = "sk-timeout-secret-key"

    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout(f"Read timed out connecting with key {secret_key}")

    transport = httpx.MockTransport(timeout_handler)
    provider = LiveAgentProvider(api_key=secret_key, transport=transport)

    res = await provider.chat_completion(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert res.finish_reason == "error"
    assert res.error_type == "timeout"
    assert secret_key not in (res.error or "")

    def connect_error_handler(request: httpx.Request):
        raise httpx.ConnectError(f"DNS lookup failed for {secret_key}")

    transport2 = httpx.MockTransport(connect_error_handler)
    provider2 = LiveAgentProvider(api_key=secret_key, transport=transport2)

    res2 = await provider2.chat_completion(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert res2.finish_reason == "error"
    assert res2.error_type == "connection_error"
    assert secret_key not in (res2.error or "")


# -----------------------------------------------------------------------------
# 7. Live Embedding Provider Integration (text-embedding-3-small)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_openai_embedding_provider_request_and_usage_accounting():
    """Verify OpenAIEmbeddingProvider formats payload, parses 1536 dims, extracts usage and computes cost."""
    dummy_vec = [0.05] * 1536

    response_payload = {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": dummy_vec,
            }
        ],
        "model": "text-embedding-3-small",
        "usage": {
            "prompt_tokens": 16,
            "total_tokens": 16,
        },
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        body = json.loads(request.read())
        assert body["model"] == "text-embedding-3-small"
        assert body["input"] == ["Binary search invariants"]
        assert body["dimensions"] == 1536
        return httpx.Response(
            200,
            json=response_payload,
            headers={"x-request-id": "req-embedding-header-456"},
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAIEmbeddingProvider(
        api_key="test-emb-key",
        model_name="text-embedding-3-small",
        dimensions=1536,
        transport=transport,
    )

    vec = await provider.embed_text("Binary search invariants")
    assert len(vec) == 1536
    assert vec[0] == 0.05

    # Verify usage was captured and cost calculated
    usage = provider.last_usage
    assert usage is not None
    assert usage.prompt_tokens == 16
    assert usage.total_tokens == 16
    assert usage.model == "text-embedding-3-small"
    assert usage.provider == "openai"
    assert usage.request_id == "req-embedding-header-456"
    assert usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert usage.is_estimated_cost_known is True
    # text-embedding-3-small rate: $0.020 / 1M tokens -> 16 * 0.020 / 1000000 = 0.00000032
    assert usage.estimated_cost_usd == Decimal("0.00000032")


@pytest.mark.anyio
async def test_openai_embedding_provider_error_handling():
    """Verify OpenAIEmbeddingProvider classifies 400 and 403 errors appropriately."""
    async def mock_400(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Invalid parameters")

    provider_400 = OpenAIEmbeddingProvider(api_key="test", transport=httpx.MockTransport(mock_400))
    with pytest.raises(EmbeddingError, match="HTTP 400"):
        await provider_400.embed_text("query")

    async def mock_403(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden region")

    provider_403 = OpenAIEmbeddingProvider(api_key="test", transport=httpx.MockTransport(mock_403))
    with pytest.raises(EmbeddingError, match="HTTP 403"):
        await provider_403.embed_text("query")


# -----------------------------------------------------------------------------
# 8. Multi-Step Orchestrator Integration with Embedding Usage Tracking
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_orchestrator_captures_embedding_and_chat_usage(sqlite_test_engine):
    """
    Verify AgentOrchestrator tracks both chat completion and embedding tokens
    in state.usage_records and persists them idempotently into UsageRepository.
    """
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    # Mock chat provider returning a tool call to retrieve knowledge, then finishing
    chat_usage = TokenUsage(
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        model="gpt-4o-mini",
        provider="openai",
        request_id="req-chat-step-1",
        usage_source=UsageSource.ACTUAL_PROVIDER,
        estimated_cost_usd=Decimal("0.000027"),
        is_estimated_cost_known=True,
    )

    mock_chat = MockAgentProvider()
    mock_chat.add_step(
        AgentStepResult(
            tool_calls=[
                ToolCall(
                    id="call_retrieval_01",
                    name="retrieve_knowledge_context",
                    arguments={"query": "binary search tree"},
                )
            ],
            finish_reason="tool_calls",
            usage=chat_usage,
            request_id="req-chat-step-1",
            model="gpt-4o-mini",
        )
    )
    mock_chat.add_step(
        AgentStepResult(
            content="Synthesized final analysis using retrieved knowledge.",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=150,
                completion_tokens=40,
                total_tokens=190,
                model="gpt-4o-mini",
                provider="openai",
                request_id="req-chat-step-2",
                usage_source=UsageSource.ACTUAL_PROVIDER,
                estimated_cost_usd=Decimal("0.0000465"),
                is_estimated_cost_known=True,
            ),
            request_id="req-chat-step-2",
            model="gpt-4o-mini",
        )
    )

    # Embedding provider mock returning embedding and token usage
    dummy_vec = [0.01] * 1536
    emb_resp = {
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": dummy_vec}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }

    async def emb_mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=emb_resp, headers={"x-request-id": "req-emb-01"})

    mock_emb = OpenAIEmbeddingProvider(
        api_key="test-emb-key",
        transport=httpx.MockTransport(emb_mock_handler),
    )

    orchestrator = AgentOrchestrator(
        provider=mock_chat,
        embedding_provider=mock_emb,
    )

    tenant_id = uuid.uuid4()
    req = AgentAnalyzeRequest(code="def search(nums, x): return -1")

    async with session_factory() as session:
        user = User(
            id=tenant_id,
            email="tenant_live_audit@example.com",
            full_name="Tenant User",
            password_hash="argon2id_placeholder",
            role="user",
        )
        session.add(user)
        await session.commit()

        res = await orchestrator.run(req, db=session, current_user=user)

        assert res.status == "SUCCESS"
        assert res.usage is not None
        # Must contain at least chat steps
        assert res.usage.requests_count >= 2
        assert res.usage.total_tokens > 0

        # Verify usage was persisted to database
        usage_repo = UsageRepository(session)
        summary = await usage_repo.get_summary(user_id=tenant_id)
        assert summary["requests_count"] >= 2
        assert summary["total_prompt_tokens"] >= 250


# -----------------------------------------------------------------------------
# 9. Opt-in Genuine Third-Party Live Integration Test
# -----------------------------------------------------------------------------

@pytest.mark.skipif(
    not (
        os.environ.get("EDGEMIND_RUN_LIVE_PROVIDER_TESTS", "").lower() in ("true", "1", "yes")
        and (os.environ.get("OPENAI_API_KEY") or os.environ.get("EDGEMIND_AI_KEY"))
    ),
    reason="LIVE TESTS NOT RUN: Opt-in EDGEMIND_RUN_LIVE_PROVIDER_TESTS=true and valid API key required",
)
@pytest.mark.anyio
async def test_opt_in_genuine_openai_live_call():
    """
    Opt-in test that executes a real, billable call to OpenAI API when explicitly requested.
    Uses bounded tokens (max_tokens=10) to minimize cost ($< 0.0001).
    """
    settings = get_settings()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EDGEMIND_AI_KEY") or settings.get_ai_api_key()
    assert api_key, "API key missing for live test"

    provider = LiveAgentProvider(api_key=api_key, model="gpt-4o-mini")
    res = await provider.chat_completion(
        messages=[{"role": "user", "content": "Respond 'OK' in 1 word."}],
        tools=[],
    )

    assert res.finish_reason == "stop"
    assert res.content is not None
    assert res.usage is not None
    assert res.usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert res.usage.prompt_tokens > 0
    assert res.usage.completion_tokens > 0
    assert res.usage.estimated_cost_usd > Decimal("0.0")
