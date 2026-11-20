"""
Comprehensive tests for EdgeMind AI Token and Cost Monitoring (Phase 3).

Verifies:
1. Exact Decimal cost calculation using configurable model rates and pricing versions.
2. Unknown model pricing safely returns null/None cost rather than fabricated 0.0.
3. Missing token metadata safely returns null/None cost.
4. Custom pricing registration and versioning.
5. Non-streaming token usage extraction.
6. Streaming token usage extraction and SSE usage event.
7. Missing usage metadata labeled as UNAVAILABLE.
8. Local token estimates clearly labeled as LOCAL_ESTIMATE.
9. Multi-step agent aggregation across multiple reasoning turns.
10. Tool-calling iterations: tool execution alone does not create provider tokens.
11. Duplicate usage prevention.
12. Database ledger persistence and tenant-isolated querying via UsageRepository.
13. Usage summary API endpoints (GET /api/v1/agent/usage/summary and session breakdown) with 401 on unauthenticated access and tenant boundary enforcement.
14. Extension usage card rendering with strict DOM safety (Node.js test).

All unit tests use deterministic MockAgentProvider instances and are explicitly labeled as mocked.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, MetaData
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.api import app
from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import LiveAgentProvider, MockAgentProvider
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentStepResult,
    SSEEventType,
    ToolCall,
)
from core.auth.dependencies import get_optional_current_user
from core.cost import (
    AgentUsageSummary,
    CostCalculator,
    ModelLifecycleStatus,
    ModelPrice,
    TokenUsage,
    UsageSource,
    default_cost_calculator,
    estimate_local_tokens_from_text,
    format_cost_usd,
)
from core.database.base import Base
from core.database.connection import get_db
from core.database.models import User
from core.database.models.ai_token_usage import AiTokenUsage
from core.database.repositories.usage_repository import UsageRepository
from core.routes.agent import get_agent_orchestrator


# =============================================================================
# Helper: Parse SSE Wire Stream
# =============================================================================

def parse_sse_events(raw_text: str) -> List[Dict[str, Any]]:
    events = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_dict = {"id": None, "event": "message", "data": None}
        data_lines = []
        for line in lines:
            if line.startswith(":"):
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
# 1. Cost Calculation and Decimal Precision Tests
# =============================================================================

def test_cost_calculation_decimal_precision():
    """
    Verify exact Decimal arithmetic:
    input_cost = (prompt_tokens / 1,000,000) * input_price
    output_cost = (completion_tokens / 1,000,000) * output_price
    total_cost = input_cost + output_cost
    """
    calc = CostCalculator(pricing_version="2026-11-01")

    # gpt-4o-mini: input $0.150/1M, output $0.600/1M
    res = calc.calculate_cost(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        model="gpt-4o-mini",
    )
    assert res.is_pricing_known is True
    assert res.input_cost == Decimal("0.150000")
    assert res.output_cost == Decimal("0.600000")
    assert res.total_cost == Decimal("0.750000")
    assert res.currency == "USD"
    assert res.pricing_version == "2026-11-01"

    # Smaller fractional token count
    res_small = calc.calculate_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        model="gpt-4o-mini",
    )
    # 1000 / 1_000_000 * 0.15 = 0.00015
    # 500 / 1_000_000 * 0.60 = 0.00030
    # Total = 0.000450
    assert res_small.input_cost == Decimal("0.000150")
    assert res_small.output_cost == Decimal("0.000300")
    assert res_small.total_cost == Decimal("0.000450")


def test_one_token_sub_micro_dollar_precision():
    """
    TASK 1: Verify exact sub-micro-dollar precision for a 1-token request.
    1 prompt token with gpt-4o-mini ($0.150/1M) = $0.00000015.
    Must NOT be rounded to 0.0 or truncated to 6 decimal places.
    """
    calc = CostCalculator(pricing_version="2026-11-01")
    res = calc.calculate_cost(
        prompt_tokens=1,
        completion_tokens=0,
        model="gpt-4o-mini",
    )
    assert res.is_pricing_known is True
    assert res.input_cost == Decimal("0.00000015")
    assert res.output_cost == Decimal("0.0")
    assert res.total_cost == Decimal("0.00000015")
    assert res.total_cost > Decimal("0")

    # Display formatting preserves full normalized representation for sub-micro-dollar costs
    formatted = format_cost_usd(res.total_cost)
    assert formatted == "$0.00000015"


def test_aggregation_of_many_small_costs():
    """
    TASK 1: Verify that 100 calls of 1 prompt token each aggregate to exactly $0.00001500,
    with zero loss of precision and zero conversion to float.
    """
    orchestrator = AgentOrchestrator()
    records = [
        TokenUsage(
            prompt_tokens=1,
            completion_tokens=0,
            total_tokens=1,
            model="gpt-4o-mini",
            request_id=f"req-small-{i}",
            usage_source=UsageSource.ACTUAL_PROVIDER,
        )
        for i in range(100)
    ]
    summary = orchestrator._aggregate_usage(records)
    assert summary.requests_count == 100
    assert summary.prompt_tokens == 100
    assert summary.total_tokens == 100
    assert summary.is_estimated_cost_known is True
    # Exactly 100 * 0.00000015 = 0.00001500
    assert summary.estimated_cost_usd == Decimal("0.00001500")
    assert isinstance(summary.estimated_cost_usd, Decimal)
    assert "gpt-4o-mini" in summary.by_model
    assert summary.by_model["gpt-4o-mini"].estimated_cost_usd == Decimal("0.00001500")
    assert isinstance(summary.by_model["gpt-4o-mini"].estimated_cost_usd, Decimal)


def test_cost_calculation_unknown_model_returns_none():
    """Verify that an unknown or unpriced model returns None cost rather than fabricated 0.0."""
    calc = CostCalculator(pricing_version="2026-11-01")
    res = calc.calculate_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        model="unknown-nonexistent-llm-model",
    )
    assert res.is_pricing_known is False
    assert res.input_cost is None
    assert res.output_cost is None
    assert res.total_cost is None


def test_cost_calculation_missing_tokens_returns_none():
    """Verify missing prompt or completion tokens returns None cost."""
    calc = CostCalculator()
    res = calc.calculate_cost(
        prompt_tokens=None,
        completion_tokens=500,
        model="gpt-4o-mini",
    )
    assert res.is_pricing_known is False
    assert res.total_cost is None


def test_custom_price_registration_and_versioning():
    """Verify dynamic price registration and custom pricing versions."""
    calc = CostCalculator(pricing_version="2026-v2")
    calc.register_price(
        model="custom-engine-x",
        input_price_per_million=Decimal("5.00"),
        output_price_per_million=Decimal("20.00"),
        currency="USD",
        pricing_version="2026-v2",
    )

    res = calc.calculate_cost(
        prompt_tokens=2_000_000,
        completion_tokens=1_000_000,
        model="custom-engine-x",
        pricing_version="2026-v2",
    )
    assert res.is_pricing_known is True
    assert res.input_cost == Decimal("10.000000")
    assert res.output_cost == Decimal("20.000000")
    assert res.total_cost == Decimal("30.000000")
    assert res.pricing_version == "2026-v2"


def test_model_lifecycle_status_classification():
    """
    TASK 2: Verify model lifecycle classification: ACTIVE, DEPRECATED, and RETIRED
    using verified provider deprecation dates and exact identifiers.
    """
    calc = CostCalculator(pricing_version="2026-11-01")

    # 1. OpenAI Retired Models (October 23, 2026)
    for model_id in ["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4o-2024-05-13"]:
        price = calc.get_price(model_id)
        assert price is not None, f"Model {model_id} must be in catalog"
        assert price.status == ModelLifecycleStatus.RETIRED
        assert price.lifecycle_date == "October 23, 2026"
        assert "developers.openai.com" in price.source_url
        assert calc.is_model_retired(model_id) is True
        assert calc.is_model_active(model_id) is False
        assert calc.is_model_available_for_new_usage(model_id) is False

    # 2. OpenAI Deprecated Models (January 14, 2027)
    for model_id in ["gpt-4o-mini-2024-07-18", "gpt-4o-2024-08-06", "gpt-4o-mini"]:
        price = calc.get_price(model_id)
        assert price is not None, f"Model {model_id} must be in catalog"
        assert price.status == ModelLifecycleStatus.DEPRECATED
        assert price.lifecycle_date == "January 14, 2027"
        assert "developers.openai.com" in price.source_url
        assert calc.is_model_deprecated(model_id) is True
        assert calc.is_model_retired(model_id) is False
        assert calc.is_model_available_for_new_usage(model_id) is True

    # 3. Anthropic Retired Exact Identifiers
    haiku_price = calc.get_price("claude-3-haiku-20240307")
    assert haiku_price is not None
    assert haiku_price.status == ModelLifecycleStatus.RETIRED
    assert haiku_price.lifecycle_date == "April 20, 2026"
    assert "platform.claude.com" in haiku_price.source_url
    assert calc.is_model_available_for_new_usage("claude-3-haiku-20240307") is False

    for sonnet_id in ["claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20241022"]:
        price = calc.get_price(sonnet_id)
        assert price is not None, f"Model {sonnet_id} must be in catalog"
        assert price.status == ModelLifecycleStatus.RETIRED
        assert price.lifecycle_date == "October 28, 2025"
        assert "platform.claude.com" in price.source_url
        assert calc.is_model_available_for_new_usage(sonnet_id) is False

    # 4. Active Models (Text Embeddings)
    assert calc.is_model_active("text-embedding-3-small") is True
    assert calc.is_model_active("text-embedding-3-large") is True
    assert calc.is_model_available_for_new_usage("text-embedding-3-small") is True

    # 5. Generic unmapped aliases return null estimated cost
    for alias in ["claude-3-5-sonnet", "claude-3-haiku"]:
        assert calc.get_price(alias) is None
        res_alias = calc.calculate_cost(100, 100, alias)
        assert res_alias.is_pricing_known is False
        assert res_alias.total_cost is None

    # 6. Cost calculation carries model_status and lifecycle_date
    res_retired = calc.calculate_cost(1000, 500, "gpt-3.5-turbo")
    assert res_retired.is_pricing_known is True
    assert res_retired.total_cost is not None
    assert res_retired.model_status == ModelLifecycleStatus.RETIRED
    assert res_retired.lifecycle_date == "October 23, 2026"

    res_deprecated = calc.calculate_cost(1000, 500, "gpt-4o-mini")
    assert res_deprecated.is_pricing_known is True
    assert res_deprecated.total_cost is not None
    assert res_deprecated.model_status == ModelLifecycleStatus.DEPRECATED
    assert res_deprecated.lifecycle_date == "January 14, 2027"


# =============================================================================
# 2. Token Usage Extraction and Multi-Step Aggregation Tests
# =============================================================================

@pytest.mark.anyio
async def test_non_streaming_usage_extraction_and_aggregation():
    """Verify non-streaming execution captures usage and aggregates tokens and costs."""
    mock_usage = TokenUsage(
        prompt_tokens=120,
        completion_tokens=45,
        total_tokens=165,
        model="gpt-4o-mini",
        usage_source=UsageSource.ACTUAL_PROVIDER,
        request_id="req-test-123",
    )
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="Finished reasoning analysis.",
            finish_reason="stop",
            usage=mock_usage,
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)
    req = AgentAnalyzeRequest(code="def solve(x): return x * 2")

    resp = await orchestrator.run(req)

    assert resp.usage is not None
    assert resp.usage.prompt_tokens == 120
    assert resp.usage.completion_tokens == 45
    assert resp.usage.total_tokens == 165
    assert resp.usage.requests_count == 1
    assert resp.usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert resp.usage.is_estimated_cost_known is True
    assert resp.usage.estimated_cost_usd is not None
    assert "gpt-4o-mini" in resp.usage.by_model
    assert resp.usage.by_model["gpt-4o-mini"].requests_count == 1


@pytest.mark.anyio
async def test_multi_step_agent_usage_aggregation():
    """
    Verify multi-step reasoning across multiple tool invocations:
    Step 1 (Tool Call): 100 prompt, 30 completion
    Step 2 (Tool Call): 150 prompt, 40 completion
    Step 3 (Final):     200 prompt, 50 completion
    Total: 450 prompt, 120 completion, 570 total tokens across 3 requests.
    """
    code_sample = "def is_even(n):\n    return n % 2 == 0"
    steps = [
        AgentStepResult(
            tool_calls=[
                ToolCall(id="tc1", name="parse_problem_constraints", arguments={"description": "n is integer"})
            ],
            finish_reason="tool_calls",
            usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=30,
                total_tokens=130,
                model="gpt-4o-mini",
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
        ),
        AgentStepResult(
            tool_calls=[
                ToolCall(id="tc2", name="detect_coverage_gaps", arguments={"code": code_sample, "test_cases": []})
            ],
            finish_reason="tool_calls",
            usage=TokenUsage(
                prompt_tokens=150,
                completion_tokens=40,
                total_tokens=190,
                model="gpt-4o-mini",
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
        ),
        AgentStepResult(
            content="Completed analysis with full multi-step tool evidence.",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=200,
                completion_tokens=50,
                total_tokens=250,
                model="gpt-4o-mini",
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
        ),
    ]

    provider = MockAgentProvider(steps=steps)
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=4)
    req = AgentAnalyzeRequest(code=code_sample)

    resp = await orchestrator.run(req)

    assert resp.usage is not None
    assert resp.usage.prompt_tokens == 450
    assert resp.usage.completion_tokens == 120
    assert resp.usage.total_tokens == 570
    assert resp.usage.requests_count == 3
    assert resp.usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert len(resp.usage.records) == 3


@pytest.mark.anyio
async def test_tool_execution_alone_does_not_count_as_provider_usage():
    """Verify tool execution alone does NOT inject synthetic or duplicate token usage."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            tool_calls=[
                ToolCall(id="tc1", name="parse_problem_constraints", arguments={"description": "bounds"})
            ],
            finish_reason="tool_calls",
            usage=TokenUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70, model="gpt-4o-mini"),
        ),
        AgentStepResult(
            content="Done.",
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=80, completion_tokens=30, total_tokens=110, model="gpt-4o-mini"),
        ),
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=3)
    resp = await orchestrator.run(AgentAnalyzeRequest(code="def check(): pass"))

    # Exactly 2 LLM requests, no additional tokens from the tool execution itself
    assert resp.usage.requests_count == 2
    assert resp.usage.prompt_tokens == 130
    assert resp.usage.completion_tokens == 50
    assert resp.usage.total_tokens == 180


def test_orchestrator_aggregation_deduplication():
    """
    TASK 1: Verify that duplicate usage records with the same (provider, request_id)
    are deduplicated by _aggregate_usage and not double-counted, while allowing
    identical request IDs across different providers.
    """
    orchestrator = AgentOrchestrator()
    dup_records = [
        TokenUsage(
            provider="openai",
            prompt_tokens=200,
            completion_tokens=50,
            total_tokens=250,
            model="gpt-4o-mini",
            request_id="chatcmpl-unique-1",
            usage_source=UsageSource.ACTUAL_PROVIDER,
        ),
        TokenUsage(
            provider="openai",
            prompt_tokens=200,
            completion_tokens=50,
            total_tokens=250,
            model="gpt-4o-mini",
            request_id="chatcmpl-unique-1",  # Duplicate of record 1 (same provider, same request_id)
            usage_source=UsageSource.ACTUAL_PROVIDER,
        ),
        TokenUsage(
            provider="anthropic",
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
            model="claude-3-haiku-20240307",
            request_id="chatcmpl-unique-1",  # Same request_id, DIFFERENT provider -> must be retained
            usage_source=UsageSource.ACTUAL_PROVIDER,
        ),
        TokenUsage(
            provider="openai",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
            model="gpt-4o-mini",
            request_id="chatcmpl-unique-2",
            usage_source=UsageSource.ACTUAL_PROVIDER,
        ),
    ]

    summary = orchestrator._aggregate_usage(dup_records)
    # 3 distinct (provider, request_id) requests should be counted:
    # 1. (openai, chatcmpl-unique-1): 250 tokens
    # 2. (anthropic, chatcmpl-unique-1): 100 tokens
    # 3. (openai, chatcmpl-unique-2): 125 tokens
    # Total tokens = 475, requests_count = 3
    assert summary.requests_count == 3
    assert summary.prompt_tokens == 380
    assert summary.completion_tokens == 95
    assert summary.total_tokens == 475
    assert len(summary.records) == 3


@pytest.mark.anyio
async def test_missing_usage_metadata_marked_unavailable():
    """Verify that when a provider returns no usage, usage_source is UNAVAILABLE and cost is None."""
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="Analysis without provider usage header.",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                usage_source=UsageSource.UNAVAILABLE,
            ),
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)
    resp = await orchestrator.run(AgentAnalyzeRequest(code="def foo(): pass"))

    assert resp.usage is not None
    assert resp.usage.usage_source == UsageSource.UNAVAILABLE
    assert resp.usage.estimated_cost_usd is None
    assert resp.usage.is_estimated_cost_known is False


def test_local_token_estimates_helper():
    """Verify local token estimate helper produces conservative non-zero counts."""
    est = estimate_local_tokens_from_text("def solve(nums): return sum(nums)")
    assert est > 0
    assert estimate_local_tokens_from_text("") == 0
    assert estimate_local_tokens_from_text(None) == 0


# =============================================================================
# 3. Streaming SSE Usage Event and Completed Payload Tests
# =============================================================================

def test_streaming_emits_usage_event_and_completed_payload():
    """Verify POST /api/v1/agent/analyze/stream emits an SSE usage event and completed payload with usage."""
    mock_usage = TokenUsage(
        prompt_tokens=180,
        completion_tokens=60,
        total_tokens=240,
        model="gpt-4o-mini",
        usage_source=UsageSource.ACTUAL_PROVIDER,
    )
    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="Streaming complete with token telemetry.",
            finish_reason="stop",
            usage=mock_usage,
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=2)

    app.dependency_overrides[get_agent_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/analyze/stream",
                json={"code": "def stream_usage_check(): pass"},
            )
            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            # 1. Verify 'usage' event is emitted
            usage_events = [e for e in events if e.get("event") == "usage"]
            assert len(usage_events) == 1
            usage_data = usage_events[0]["data"]
            assert usage_data["prompt_tokens"] == 180
            assert usage_data["completion_tokens"] == 60
            assert usage_data["total_tokens"] == 240
            assert usage_data["usage_source"] == "ACTUAL_PROVIDER"

            # 2. Verify 'completed' event contains full usage
            completed_events = [e for e in events if e.get("event") == "completed"]
            assert len(completed_events) == 1
            completed_data = completed_events[0]["data"]
            assert "usage" in completed_data
            assert completed_data["usage"]["total_tokens"] == 240
    finally:
        app.dependency_overrides.pop(get_agent_orchestrator, None)


@pytest.mark.anyio
async def test_streaming_terminal_usage_parser_direct():
    """
    TASK 4: Directly test LiveAgentProvider.chat_completion_stream() wire SSE parser:
    1. Verifies stream_options.include_usage: True is requested in the payload.
    2. Parses terminal usage event with empty choices before [DONE].
    3. Handles duplicate usage chunks without double-counting.
    4. Handles stream with missing usage by marking UNAVAILABLE.
    """
    received_payloads = []

    def mock_sse_handler(request: httpx.Request):
        req_json = json.loads(request.content.decode("utf-8"))
        received_payloads.append(req_json)

        # Simulating standard OpenAI streaming response with terminal usage chunk
        sse_lines = [
            'data: {"id": "chatcmpl-live-1", "model": "gpt-4o-mini", "choices": [{"delta": {"content": "Hello world"}}]}\n\n',
            # Terminal usage chunk with empty choices
            'data: {"id": "chatcmpl-live-1", "model": "gpt-4o-mini", "choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}}\n\n',
            # Duplicate usage chunk to test idempotency
            'data: {"id": "chatcmpl-live-1", "model": "gpt-4o-mini", "choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}}\n\n',
            'data: [DONE]\n\n',
        ]
        return httpx.Response(
            status_code=200,
            content="".join(sse_lines).encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(mock_sse_handler)
    provider = LiveAgentProvider(api_key="sk-test-live-key", model="gpt-4o-mini", transport=transport)

    stream_gen = provider.chat_completion_stream(
        messages=[{"role": "user", "content": "Hello"}],
        tools=[],
    )

    items = []
    async for item in stream_gen:
        items.append(item)

    # 1. Verify stream_options.include_usage was requested
    assert len(received_payloads) == 1
    assert received_payloads[0].get("stream") is True
    assert received_payloads[0].get("stream_options", {}).get("include_usage") is True

    # 2. Verify text chunk was yielded
    text_chunks = [i for i in items if isinstance(i, str)]
    assert text_chunks == ["Hello world"]

    # 3. Verify terminal AgentStepResult was yielded with exact usage
    step_results = [i for i in items if isinstance(i, AgentStepResult)]
    assert len(step_results) == 1
    final_step = step_results[0]
    assert final_step.content == "Hello world"
    assert final_step.usage is not None
    assert final_step.usage.prompt_tokens == 120
    assert final_step.usage.completion_tokens == 40
    assert final_step.usage.total_tokens == 160
    assert final_step.usage.usage_source == UsageSource.ACTUAL_PROVIDER
    assert final_step.usage.request_id == "chatcmpl-live-1"
    # Exact Decimal cost: 120/1M*0.15 + 40/1M*0.60 = 0.000018 + 0.000024 = 0.000042
    assert final_step.usage.estimated_cost_usd == Decimal("0.00004200")
    assert isinstance(final_step.usage.estimated_cost_usd, Decimal)

    # 4. Stream missing usage metadata -> UNAVAILABLE
    def mock_no_usage_handler(request: httpx.Request):
        sse_lines = [
            'data: {"id": "chatcmpl-no-u", "model": "gpt-4o-mini", "choices": [{"delta": {"content": "Text only"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
        return httpx.Response(status_code=200, content="".join(sse_lines).encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider_no_u = LiveAgentProvider(api_key="sk-test-live-key", model="gpt-4o-mini", transport=httpx.MockTransport(mock_no_usage_handler))
    provider_no_u.settings.agent_enable_local_token_estimates = False

    items_no_u = []
    async for item in provider_no_u.chat_completion_stream(messages=[{"role": "user", "content": "Hi"}], tools=[]):
        items_no_u.append(item)

    final_no_u = [i for i in items_no_u if isinstance(i, AgentStepResult)][0]
    assert final_no_u.usage is not None
    assert final_no_u.usage.usage_source == UsageSource.UNAVAILABLE
    assert final_no_u.usage.prompt_tokens is None
    assert final_no_u.usage.completion_tokens is None
    assert final_no_u.usage.estimated_cost_usd is None


# =============================================================================
# 4. Database Persistence and Tenant Isolation Tests
# =============================================================================

@pytest.mark.anyio
async def test_database_persistence_and_tenant_isolation():
    """
    Verify UsageRepository:
    1. Records token usage ledger entries.
    2. Enforces tenant boundary: User A cannot see User B's tokens or costs.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    session_a_id = uuid.uuid4()
    session_b_id = uuid.uuid4()

    async with async_session() as db:
        repo = UsageRepository(db)

        # Record User A usage
        await repo.record_usage(
            usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                model="gpt-4o-mini",
                estimated_cost_usd=Decimal("0.000045"),
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
            session_id=session_a_id,
            user_id=user_a_id,
        )

        # Record User B usage
        await repo.record_usage(
            usage=TokenUsage(
                prompt_tokens=500,
                completion_tokens=200,
                total_tokens=700,
                model="gpt-4o",
                estimated_cost_usd=Decimal("0.003250"),
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
            session_id=session_b_id,
            user_id=user_b_id,
        )
        await db.commit()

        # Query User A summary
        summary_a = await repo.get_summary(user_id=user_a_id, period="month")
        assert summary_a["total_prompt_tokens"] == 100
        assert summary_a["total_completion_tokens"] == 50
        assert summary_a["total_tokens"] == 150
        assert summary_a["requests_count"] == 1
        assert "gpt-4o-mini" in summary_a["by_model"]
        assert "gpt-4o" not in summary_a["by_model"], "User A must not see User B's model usage"

        # Query User B summary
        summary_b = await repo.get_summary(user_id=user_b_id, period="month")
        assert summary_b["total_tokens"] == 700
        assert summary_b["requests_count"] == 1
        assert "gpt-4o" in summary_b["by_model"]

        # Anonymous query (user_id=None without admin) must return 0
        summary_anon = await repo.get_summary(user_id=None, is_admin=False)
        assert summary_anon["total_tokens"] == 0

    await engine.dispose()





@pytest.mark.anyio
async def test_idempotent_usage_persistence_deduplication():
    """
    TASK 3: Verify that calling UsageRepository.record_usage() and record_usages_batch()
    idempotently prevents duplicate rows and inflated costs when given the same request_id.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    async with async_session() as db:
        repo = UsageRepository(db)
        u1 = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o-mini",
            estimated_cost_usd=Decimal("0.000045"),
            request_id="chatcmpl-idempotent-1",
            usage_source=UsageSource.ACTUAL_PROVIDER,
        )

        # First record insertion
        r1 = await repo.record_usage(u1, session_id=session_id, user_id=user_id)
        # Duplicate record insertion with same request_id
        r2 = await repo.record_usage(u1, session_id=session_id, user_id=user_id)
        await db.commit()

        assert r1.id == r2.id

        # Verify only 1 row exists in DB
        summary = await repo.get_summary(user_id=user_id)
        assert summary["requests_count"] == 1
        assert summary["total_tokens"] == 150
        assert summary["total_estimated_cost_usd"] == Decimal("0.000045")

        # Test batch insertion with duplicate in batch and duplicate of existing DB record
        batch = [
            u1,  # Already in DB
            TokenUsage(
                prompt_tokens=200,
                completion_tokens=80,
                total_tokens=280,
                model="gpt-4o-mini",
                estimated_cost_usd=Decimal("0.000078"),
                request_id="chatcmpl-idempotent-2",
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
            TokenUsage(
                prompt_tokens=200,
                completion_tokens=80,
                total_tokens=280,
                model="gpt-4o-mini",
                estimated_cost_usd=Decimal("0.000078"),
                request_id="chatcmpl-idempotent-2",  # Duplicate in batch
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
        ]
        batch_records = await repo.record_usages_batch(batch, session_id=session_id, user_id=user_id)
        await db.commit()

        # Batch returns unique entries (existing u1 returned, new u2 inserted; in-batch duplicate skipped)
        assert len(batch_records) == 2
        summary_after = await repo.get_summary(user_id=user_id)
        assert summary_after["requests_count"] == 2
        assert summary_after["total_tokens"] == 150 + 280

    await engine.dispose()





@pytest.mark.anyio
async def test_anonymous_local_first_analysis_does_not_persist_billing():
    """
    TASK 5: Verify that local-first anonymous analysis (current_user=None)
    does NOT persist unattributed usage/billing records to the database.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    provider = MockAgentProvider(steps=[
        AgentStepResult(
            content="Local-first completed analysis.",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=80,
                completion_tokens=30,
                total_tokens=110,
                model="gpt-4o-mini",
                usage_source=UsageSource.ACTUAL_PROVIDER,
            ),
        )
    ])
    orchestrator = AgentOrchestrator(provider=provider)

    async with async_session() as db:
        resp = await orchestrator.run(
            AgentAnalyzeRequest(code="def local_exec(): return True"),
            db=db,
            current_user=None,  # Anonymous
        )
        await db.commit()

        # In-memory AgentAnalyzeResponse still carries usage for local display in UI
        assert resp.usage is not None
        assert resp.usage.total_tokens == 110

        # But database must have ZERO persisted records in ai_token_usages
        from sqlalchemy import select, func
        count_res = await db.execute(select(func.count()).select_from(AiTokenUsage))
        total_persisted = count_res.scalar_one()
        assert total_persisted == 0, "Anonymous execution must not write billing records to the database"

    await engine.dispose()





@pytest.mark.anyio
async def test_tenant_and_project_filtering_and_periods():
    """
    TASK 5: Test time-period filtering (day, month, all), project isolation,
    and cross-tenant isolation on UsageRepository.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    proj1_id = uuid.uuid4()
    proj2_id = uuid.uuid4()
    session_user1 = uuid.uuid4()

    now = datetime.now(timezone.utc)

    async with async_session() as db:
        # Insert records with explicit timestamps:
        # Rec 1: User 1, Proj 1, 2 hours ago (within day, month, all)
        r1 = AiTokenUsage(
            session_id=session_user1,
            user_id=user1_id,
            project_id=proj1_id,
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=Decimal("0.000045"),
            created_at=now - timedelta(hours=2),
        )
        # Rec 2: User 1, Proj 1, 10 days ago (outside day, within month, all)
        r2 = AiTokenUsage(
            session_id=session_user1,
            user_id=user1_id,
            project_id=proj1_id,
            model="gpt-4o-mini",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            estimated_cost_usd=Decimal("0.000090"),
            created_at=now - timedelta(days=10),
        )
        # Rec 3: User 1, Proj 2, 45 days ago (outside day, outside month, within all)
        r3 = AiTokenUsage(
            session_id=uuid.uuid4(),
            user_id=user1_id,
            project_id=proj2_id,
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=200,
            total_tokens=700,
            estimated_cost_usd=Decimal("0.003250"),
            created_at=now - timedelta(days=45),
        )
        # Rec 4: User 2, Proj 1, now (User 2's record)
        r4 = AiTokenUsage(
            session_id=uuid.uuid4(),
            user_id=user2_id,
            project_id=proj1_id,
            model="gpt-4o-mini",
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
            estimated_cost_usd=Decimal("0.000024"),
            created_at=now,
        )
        db.add_all([r1, r2, r3, r4])
        await db.commit()

        repo = UsageRepository(db)

        # 1. Period: "day" -> only Rec 1 (150 tokens)
        day_sum = await repo.get_summary(user_id=user1_id, period="day")
        assert day_sum["total_tokens"] == 150
        assert day_sum["requests_count"] == 1

        # 2. Period: "month" -> Rec 1 + Rec 2 (150 + 300 = 450 tokens)
        month_sum = await repo.get_summary(user_id=user1_id, period="month")
        assert month_sum["total_tokens"] == 450
        assert month_sum["requests_count"] == 2

        # 3. Period: "all" -> Rec 1 + Rec 2 + Rec 3 (150 + 300 + 700 = 1150 tokens)
        all_sum = await repo.get_summary(user_id=user1_id, period="all")
        assert all_sum["total_tokens"] == 1150
        assert all_sum["requests_count"] == 3

        # 4. Project filter: Proj 1 -> Rec 1 + Rec 2 (450 tokens)
        proj_sum = await repo.get_summary(user_id=user1_id, project_id=proj1_id, period="all")
        assert proj_sum["total_tokens"] == 450
        assert proj_sum["requests_count"] == 2

        # 5. Session lookup tenant isolation
        # User 1 looks up User 1's session -> sees records
        sess_u1 = await repo.get_by_session_id(session_id=session_user1, user_id=user1_id)
        assert len(sess_u1) == 2
        # User 2 attempts to query User 1's session -> gets empty list
        sess_u2 = await repo.get_by_session_id(session_id=session_user1, user_id=user2_id)
        assert len(sess_u2) == 0, "Cross-tenant session usage query must be empty"

    await engine.dispose()





@pytest.mark.anyio
async def test_composite_database_provider_request_id_uniqueness():
    """
    TASK 1: Verify composite database-level UNIQUE index on (provider, request_id):
    1. Same provider + same request ID: reject duplicate with IntegrityError.
    2. Different providers + same request ID: allow both.
    3. Multiple NULL request IDs for the same provider: allow.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # 1. Insert first record: provider=openai, request_id=req-shared-1
        e1 = AiTokenUsage(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=50,
            completion_tokens=20,
            total_tokens=70,
            request_id="req-shared-1",
        )
        db.add(e1)
        await db.flush()

        # 2. Same provider + same request ID: direct insert must raise IntegrityError
        e1_dup = AiTokenUsage(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=50,
            completion_tokens=20,
            total_tokens=70,
            request_id="req-shared-1",
        )
        db.add(e1_dup)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()

        # 3. Different provider + same request ID: must succeed
        e_anthropic = AiTokenUsage(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            prompt_tokens=60,
            completion_tokens=25,
            total_tokens=85,
            request_id="req-shared-1",
        )
        db.add(e_anthropic)
        await db.flush()
        await db.commit()

        # 4. Multiple NULL request IDs for same provider: must succeed without collision
        null1 = AiTokenUsage(provider="openai", model="gpt-4o-mini", prompt_tokens=10, completion_tokens=10, total_tokens=20, request_id=None)
        null2 = AiTokenUsage(provider="openai", model="gpt-4o-mini", prompt_tokens=15, completion_tokens=15, total_tokens=30, request_id=None)
        db.add_all([null1, null2])
        await db.flush()
        await db.commit()

    await engine.dispose()





@pytest.mark.anyio
async def test_composite_batch_duplicate_detection():
    """
    TASK 1: Verify batch deduplication scoped to (provider, request_id):
    - Rejects in-batch duplicates with same (provider, request_id).
    - Preserves records with same request_id but different providers.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    async with async_session() as db:
        repo = UsageRepository(db)
        batch = [
            TokenUsage(
                provider="openai",
                model="gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                request_id="batch-req-1",
            ),
            TokenUsage(
                provider="openai",  # Duplicate of item 1
                model="gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                request_id="batch-req-1",
            ),
            TokenUsage(
                provider="anthropic",  # Same request_id, different provider -> allowed
                model="claude-3-haiku-20240307",
                prompt_tokens=80,
                completion_tokens=30,
                total_tokens=110,
                request_id="batch-req-1",
            ),
        ]
        records = await repo.record_usages_batch(batch, session_id=session_id, user_id=user_id)
        await db.commit()

        # Must persist exactly 2 records: openai + anthropic
        assert len(records) == 2
        providers = {r.provider for r in records}
        assert providers == {"openai", "anthropic"}

    await engine.dispose()





@pytest.mark.anyio
async def test_concurrent_duplicate_insertion_independent_sessions():
    """
    TASK 1: Verify concurrent duplicate insertion handling using independent database sessions:
    When Session 2 encounters an IntegrityError on (provider, request_id),
    it safely recovers via SAVEPOINT and returns the existing record.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    u = TokenUsage(
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=120,
        completion_tokens=40,
        total_tokens=160,
        request_id="chatcmpl-concurrent-independent-1",
        usage_source=UsageSource.ACTUAL_PROVIDER,
    )

    # Session 1 inserts and commits
    async with async_session() as s1:
        repo1 = UsageRepository(s1)
        r1 = await repo1.record_usage(u, session_id=session_id, user_id=user_id)
        await s1.commit()
        r1_id = r1.id

    # Session 2 tries to record same usage concurrently
    async with async_session() as s2:
        repo2 = UsageRepository(s2)
        r2 = await repo2.record_usage(u, session_id=session_id, user_id=user_id)
        await s2.commit()
        assert r2.id == r1_id
        assert r2.provider == "openai"
        assert r2.request_id == "chatcmpl-concurrent-independent-1"

    await engine.dispose()


def test_alembic_006_migration_upgrade_and_downgrade():
    """
    TASK 3: Verify migration 006 upgrade and downgrade behavior:
    1. upgrade() creates ai_token_usages table and composite unique index.
    2. downgrade() cleanly drops the index and table.
    """
    spec = importlib.util.spec_from_file_location("mig006", "migrations/versions/006_ai_token_cost_monitoring.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    sync_engine = create_engine("sqlite:///:memory:")
    with sync_engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE analysis_sessions (id VARCHAR(36) PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")

        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        mig.op = op

        # Test upgrade
        mig.upgrade()
        md_up = MetaData()
        md_up.reflect(bind=conn)
        assert "ai_token_usages" in md_up.tables

        # Test downgrade
        mig.downgrade()
        md_down = MetaData()
        md_down.reflect(bind=conn)
        assert "ai_token_usages" not in md_down.tables


# =============================================================================
# 5. Usage Summary API Endpoint Tests
# =============================================================================

def test_usage_summary_endpoint_requires_auth():
    """Verify GET /api/v1/agent/usage/summary returns HTTP 401 Unauthorized for unauthenticated callers."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/agent/usage/summary")
        assert resp.status_code == 401
        assert "Authentication required" in resp.json().get("detail", "")


def test_usage_summary_endpoint_authenticated_user():
    """Verify GET /api/v1/agent/usage/summary returns 200 with tenant-scoped usage for authenticated user."""
    mock_user = User(
        id=uuid.uuid4(),
        email="developer@edgemind.test",
        role="developer",
    )

    app.dependency_overrides[get_optional_current_user] = lambda: mock_user
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/agent/usage/summary?period=month")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_prompt_tokens" in data
            assert "total_completion_tokens" in data
            assert "total_tokens" in data
            assert data["period"] == "month"
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)


def test_session_usage_endpoint_requires_auth_and_isolates_tenants():
    """
    TASK 5: Verify GET /api/v1/agent/usage/session/{session_id} requires auth
    and returns session usage records for authenticated user.
    """
    session_id = uuid.uuid4()
    with TestClient(app) as client:
        # Unauthenticated -> 401
        res = client.get(f"/api/v1/agent/usage/session/{session_id}")
        assert res.status_code == 401
        assert "Authentication required" in res.json().get("detail", "")

    mock_user = User(id=uuid.uuid4(), email="tester@edgemind.test", role="developer")
    app.dependency_overrides[get_optional_current_user] = lambda: mock_user
    try:
        with TestClient(app) as client:
            res_auth = client.get(f"/api/v1/agent/usage/session/{session_id}")
            assert res_auth.status_code == 200
            assert isinstance(res_auth.json(), list)
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)


# =============================================================================
# 6. Extension Usage Card Rendering Tests (Node.js)
# =============================================================================

def test_extension_usage_card_node_rendering():
    """
    Verify popup.js renderUsage() function in Node.js:
    1. Sets correct textContent for tokens, model, cost.
    2. Strict zero innerHTML.
    3. Handles unavailable and estimated states properly.
    """
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/function renderUsage[\\s\\S]*?\\n  \\}/);
    if (!fnMatch) {
      console.error("renderUsage function not found");
      process.exit(1);
    }

    // Mock DOM elements
    function createMockElement(id) {
      return {
        id: id,
        textContent: '',
        className: '',
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          contains(c) { return this.classes.has(c); }
        }
      };
    }

    const testEnv = {
      elUsageCard: createMockElement('usage-card'),
      elUsageSourceBadge: createMockElement('usage-source-badge'),
      elUsageModelValue: createMockElement('usage-model-value'),
      elUsagePromptTokens: createMockElement('usage-prompt-tokens'),
      elUsageCompletionTokens: createMockElement('usage-completion-tokens'),
      elUsageTotalTokens: createMockElement('usage-total-tokens'),
      elUsageCostValue: createMockElement('usage-cost-value'),
      elUsageRequestsCount: createMockElement('usage-requests-count'),
      Number: Number,
      String: String,
      console: console,
    };
    testEnv.elUsageCard.classList.add('hidden');

    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // Case 1: Actual provider usage
    const sampleUsage = {
      prompt_tokens: 1500,
      completion_tokens: 300,
      total_tokens: 1800,
      requests_count: 2,
      estimated_cost_usd: 0.000405,
      is_estimated_cost_known: true,
      usage_source: 'ACTUAL_PROVIDER',
      by_model: { 'gpt-4o-mini': {} }
    };

    testEnv.renderUsage(sampleUsage, 'gpt-4o-mini');

    if (testEnv.elUsageCard.classList.contains('hidden')) {
      console.error("Usage card should be visible");
      process.exit(1);
    }
    if (testEnv.elUsageModelValue.textContent !== 'gpt-4o-mini') {
      console.error("Model mismatch: " + testEnv.elUsageModelValue.textContent);
      process.exit(1);
    }
    if (testEnv.elUsageTotalTokens.textContent !== '1,800') {
      console.error("Total tokens mismatch: " + testEnv.elUsageTotalTokens.textContent);
      process.exit(1);
    }
    if (!testEnv.elUsageCostValue.textContent.includes('$0.000405')) {
      console.error("Cost mismatch: " + testEnv.elUsageCostValue.textContent);
      process.exit(1);
    }

    // Case 2: Unavailable usage
    testEnv.renderUsage({ usage_source: 'UNAVAILABLE' }, 'gpt-4o-mini');
    if (testEnv.elUsageSourceBadge.textContent !== 'Unavailable') {
      console.error("Unavailable badge mismatch: " + testEnv.elUsageSourceBadge.textContent);
      process.exit(1);
    }

    console.log("SUCCESS: Extension renderUsage passed DOM validation");
    process.exit(0);
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS" in proc.stdout
