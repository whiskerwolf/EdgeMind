"""
Tests for EdgeMind Multi-Step AI Agent & Tool Calling Architecture.

Validates:
1. Tool Registry: Registration, schema conversion to standard OpenAI/Gemini format.
2. Single-step Tool Calling: Agent invokes a tool, receives observation, terminates.
3. Multi-step Sequential Reasoning: 3+ turn tool-calling chain (structure -> gaps -> synth -> rank).
4. Direct Final Answer: Immediate response with 0 tool calls completes in 1 iteration.
5. Invalid Tool Name Rejection: Orchestrator safely traps unknown tool and model self-corrects.
6. Invalid Tool Arguments Validation: Pydantic rejects bad types, reports error, model recovers.
7. Tool Timeout Handling: Slow tool aborts at timeout_seconds, marked TIMEOUT.
8. Maximum Iterations Bound: Loop terminates strictly at max_iterations with MAX_ITERATIONS_REACHED.
9. Request Cancellation: cancellation_token stops the agent loop with CANCELLED.
10. Security Boundary: Zero runtime execution of user code (AST/static only).
11. REST API Endpoint: POST /api/v1/agent/analyze unauthenticated execution.
12. Input Validation: 64 KiB limit, empty code rejection, static_only=True enforcement.
13. Multi-Tenancy Isolation: Cannot run analysis against another user's project (HTTP 404).
14. Report Persistence: Authenticated requests save full JSONB document in ReportRepository.
"""

import asyncio
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.agents import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentOrchestrator,
    AgentStatus,
    AgentStepResult,
    LiveAgentProvider,
    MockAgentProvider,
    ToolCall,
    ToolExecutionStatus,
    ToolRegistry,
    default_tool_registry,
)
from core.agents.schemas import ParseConstraintsArgs
from core.api import app
from core.auth.security import create_access_token, hash_password
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import AnalysisReport, Project, User
from core.database.repositories.report_repository import ReportRepository


@pytest.fixture
def anyio_backend():
    return "asyncio"


# =============================================================================
# Unit Tests: Tool Registry & Tool Implementations
# =============================================================================

def test_tool_registry_registration_and_schemas():
    """Verify tool registration and OpenAI/Gemini JSON Schema generation."""
    registry = ToolRegistry()

    def dummy_handler(args: ParseConstraintsArgs, context=None):
        return {"parsed": True}

    registry.register(
        name="dummy_tool",
        description="A dummy test tool",
        args_model=ParseConstraintsArgs,
        handler=dummy_handler,
        timeout_seconds=2.0,
    )

    tool = registry.get_tool("dummy_tool")
    assert tool is not None
    assert tool.name == "dummy_tool"

    schemas = registry.get_schemas()
    assert len(schemas) == 1
    s = schemas[0]
    assert s["type"] == "function"
    assert s["function"]["name"] == "dummy_tool"
    assert "properties" in s["function"]["parameters"]
    assert "raw_constraints" in s["function"]["parameters"]["properties"]


def test_default_tool_registry_contains_7_analytical_tools():
    """Verify all 7 native static analysis tools are registered by default."""
    tools = default_tool_registry.list_tools()
    assert len(tools) == 7
    names = {t.name for t in tools}
    expected = {
        "parse_problem_constraints",
        "analyze_problem_structure",
        "detect_coverage_gaps",
        "retrieve_existing_analysis",
        "generate_candidate_inputs",
        "validate_candidate_inputs",
        "rank_candidate_inputs",
    }
    assert names == expected


@pytest.mark.anyio
async def test_tool_execution_timeout_isolated():
    """Verify registry raises TimeoutError when a handler exceeds its limit."""
    registry = ToolRegistry()

    async def slow_handler(args: ParseConstraintsArgs, context=None):
        await asyncio.sleep(0.2)
        return {"done": True}

    registry.register(
        name="slow_tool",
        description="A slow tool",
        args_model=ParseConstraintsArgs,
        handler=slow_handler,
        timeout_seconds=0.05,
    )

    with pytest.raises(TimeoutError) as exc_info:
        await registry.execute_tool("slow_tool", {"raw_constraints": ["x >= 0"]})
    assert "exceeded timeout" in str(exc_info.value)


# =============================================================================
# Agent Orchestration Tests (Deterministic Multi-Step Scenarios)
# =============================================================================

@pytest.mark.anyio
async def test_single_tool_call_execution():
    """Agent calls one tool, receives observation, and finishes in 2 iterations."""
    provider = MockAgentProvider()
    provider.add_step(
        AgentStepResult(
            thought="I need to parse the mathematical constraints first.",
            tool_calls=[
                ToolCall(
                    name="parse_problem_constraints",
                    arguments={"raw_constraints": ["1 <= nums.length <= 10^4"]},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    provider.add_step(
        AgentStepResult(
            content="Summary: The problem bounds array length between 1 and 10,000.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=default_tool_registry)
    req = AgentAnalyzeRequest(
        code="def solve(nums):\n    return sum(nums)",
        filename="solution.py",
    )

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.iterations == 2
    assert len(res.tool_executions) == 1
    assert res.tool_executions[0].tool_name == "parse_problem_constraints"
    assert res.tool_executions[0].status == ToolExecutionStatus.SUCCESS
    assert res.tool_executions[0].result["constraint_spec"]["max_length"] == 10000
    assert "Summary: The problem bounds" in res.final_summary


@pytest.mark.anyio
async def test_multistep_sequential_tool_calling():
    """
    Test real multi-step autonomous agent workflow (4 tool calls across 5 iterations):
    1. analyze_problem_structure
    2. detect_coverage_gaps
    3. generate_candidate_inputs
    4. rank_candidate_inputs
    5. final synthesis
    """
    sample_code = "def twoSum(nums, target):\n    lookup = {}\n    for i, x in enumerate(nums):\n        if target - x in lookup:\n            return [lookup[target - x], i]\n        lookup[x] = i\n    return []"
    sample_cases = [
        {"input_data": {"nums": [2, 7, 11, 15], "target": 9}},
        {"input_data": {"nums": [3, 2, 4], "target": 6}},
    ]

    provider = MockAgentProvider()
    # Step 1: analyze AST structure
    provider.add_step(
        AgentStepResult(
            thought="Step 1: Inspect code structure and parameter types.",
            tool_calls=[
                ToolCall(
                    name="analyze_problem_structure",
                    arguments={"code": sample_code, "test_cases": sample_cases},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 2: detect coverage gaps
    provider.add_step(
        AgentStepResult(
            thought="Step 2: Identify missing input domain partitions.",
            tool_calls=[
                ToolCall(
                    name="detect_coverage_gaps",
                    arguments={
                        "test_cases": sample_cases,
                        "parameters": ["nums", "target"],
                        "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
                    },
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 3: generate candidate edge cases
    provider.add_step(
        AgentStepResult(
            thought="Step 3: Synthesize candidate inputs for detected gaps.",
            tool_calls=[
                ToolCall(
                    name="generate_candidate_inputs",
                    arguments={
                        "test_cases": sample_cases,
                        "constraints": ["2 <= nums.length <= 10^4"],
                        "max_candidates": 10,
                    },
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 4: rank candidates
    def step_4_handler(messages, tools):
        # Dynamically extract candidates from previous step message
        last_tool_msg = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
        cands = []
        if last_tool_msg:
            import json
            data = json.loads(last_tool_msg["content"])
            cands = data.get("candidates", [])
        return AgentStepResult(
            thought="Step 4: Rank candidates for diversity and gap coverage.",
            tool_calls=[
                ToolCall(
                    name="rank_candidate_inputs",
                    arguments={
                        "candidates": cands,
                        "existing_tests": sample_cases,
                        "max_selected": 5,
                    },
                )
            ],
            finish_reason="tool_calls",
        )
    provider.add_step(step_4_handler)

    # Step 5: final summary
    provider.add_step(
        AgentStepResult(
            content="Final Analysis: Successfully extracted structure, detected edge-case gaps, and ranked 5 top candidates.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=default_tool_registry)
    req = AgentAnalyzeRequest(
        code=sample_code,
        filename="solution.py",
        test_cases=sample_cases,
        max_iterations=6,
    )

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.iterations == 5
    assert len(res.tool_executions) == 4

    # Verify tool execution sequence
    exec_names = [t.tool_name for t in res.tool_executions]
    assert exec_names == [
        "analyze_problem_structure",
        "detect_coverage_gaps",
        "generate_candidate_inputs",
        "rank_candidate_inputs",
    ]

    for t in res.tool_executions:
        assert t.status == ToolExecutionStatus.SUCCESS
        assert t.duration_ms >= 0.0

    # Verify candidates provenance invariant: GENERATED_TEST with null expected_output
    assert res.test_intelligence is not None
    generated = res.test_intelligence.get("generated_candidates", [])
    assert len(generated) > 0
    for cand in generated:
        assert cand.get("expected_output") is None
        assert cand.get("source") == "GENERATED_TEST"

    assert "Final Analysis: Successfully" in res.final_summary


@pytest.mark.anyio
async def test_direct_final_answer_termination():
    """Agent returns a final response immediately without tool calls in 1 iteration."""
    provider = MockAgentProvider()
    provider.add_step(
        AgentStepResult(
            content="Code contains no logical flaws and simple linear complexity.",
            tool_calls=[],
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider)
    req = AgentAnalyzeRequest(code="def add(a, b):\n    return a + b")

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.iterations == 1
    assert len(res.tool_executions) == 0
    assert "Code contains no logical flaws" in res.final_summary


@pytest.mark.anyio
async def test_invalid_tool_name_rejection_and_recovery():
    """Agent requests an invalid tool name; orchestrator safely returns error and model recovers."""
    provider = MockAgentProvider()
    # Step 1: Model tries to call non-existent tool
    provider.add_step(
        AgentStepResult(
            thought="Attempting to call unknown tool",
            tool_calls=[
                ToolCall(
                    name="non_existent_hack_tool",
                    arguments={"foo": "bar"},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 2: Model self-corrects after seeing error message
    provider.add_step(
        AgentStepResult(
            thought="Tool not found, falling back to parse_problem_constraints",
            tool_calls=[
                ToolCall(
                    name="parse_problem_constraints",
                    arguments={"raw_constraints": ["0 <= n <= 100"]},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 3: Final answer
    provider.add_step(
        AgentStepResult(
            content="Analysis finished after recovering from invalid tool call.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=default_tool_registry)
    req = AgentAnalyzeRequest(code="def f(n):\n    return n")

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.iterations == 3
    assert len(res.tool_executions) == 2

    # First tool execution was an ERROR
    first_exec = res.tool_executions[0]
    assert first_exec.tool_name == "non_existent_hack_tool"
    assert first_exec.status == ToolExecutionStatus.ERROR
    assert "Tool 'non_existent_hack_tool' not found" in (first_exec.error or "")

    # Second tool execution succeeded
    second_exec = res.tool_executions[1]
    assert second_exec.tool_name == "parse_problem_constraints"
    assert second_exec.status == ToolExecutionStatus.SUCCESS


@pytest.mark.anyio
async def test_invalid_tool_arguments_validation_and_recovery():
    """Pydantic rejects malformed arguments; orchestrator informs model and model recovers."""
    provider = MockAgentProvider()
    # Step 1: Model passes string instead of list for raw_constraints
    provider.add_step(
        AgentStepResult(
            thought="Calling tool with wrong parameter type",
            tool_calls=[
                ToolCall(
                    name="parse_problem_constraints",
                    arguments={"raw_constraints": "not_a_list_error"},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 2: Model fixes parameter and retries
    provider.add_step(
        AgentStepResult(
            thought="Fixing arguments to be a valid list",
            tool_calls=[
                ToolCall(
                    name="parse_problem_constraints",
                    arguments={"raw_constraints": ["1 <= n <= 50"]},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    # Step 3: Final answer
    provider.add_step(
        AgentStepResult(
            content="Valid constraints parsed after correcting arguments.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=default_tool_registry)
    req = AgentAnalyzeRequest(code="def f(n):\n    return n")

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.iterations == 3
    assert len(res.tool_executions) == 2

    first_exec = res.tool_executions[0]
    assert first_exec.status == ToolExecutionStatus.ERROR
    assert "Invalid arguments" in (first_exec.error or "")

    second_exec = res.tool_executions[1]
    assert second_exec.status == ToolExecutionStatus.SUCCESS


@pytest.mark.anyio
async def test_tool_timeout_handling_in_orchestration():
    """Slow tool execution is aborted at timeout and marked TIMEOUT without crashing agent."""
    custom_registry = ToolRegistry()

    async def slow_fn(args: ParseConstraintsArgs, context=None):
        await asyncio.sleep(0.3)
        return {"done": True}

    custom_registry.register(
        name="parse_problem_constraints",
        description="Slow mock tool",
        args_model=ParseConstraintsArgs,
        handler=slow_fn,
        timeout_seconds=0.05,
    )

    provider = MockAgentProvider()
    provider.add_step(
        AgentStepResult(
            tool_calls=[
                ToolCall(
                    name="parse_problem_constraints",
                    arguments={"raw_constraints": ["n >= 0"]},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    provider.add_step(
        AgentStepResult(
            content="Gracefully concluded despite tool timeout.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=custom_registry)
    req = AgentAnalyzeRequest(code="def f(n):\n    return n")

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert len(res.tool_executions) == 1
    assert res.tool_executions[0].status == ToolExecutionStatus.TIMEOUT
    assert "timeout" in (res.tool_executions[0].error or "").lower()


@pytest.mark.anyio
async def test_maximum_iterations_bound():
    """Agent in infinite loop is forcefully bounded by max_iterations."""
    provider = MockAgentProvider()
    # Infinite tool calling steps
    for _ in range(10):
        provider.add_step(
            AgentStepResult(
                tool_calls=[
                    ToolCall(
                        name="parse_problem_constraints",
                        arguments={"raw_constraints": ["n >= 1"]},
                    )
                ],
                finish_reason="tool_calls",
            )
        )

    orchestrator = AgentOrchestrator(
        provider=provider,
        registry=default_tool_registry,
        max_iterations=3,
    )
    req = AgentAnalyzeRequest(code="def f(n):\n    return n", max_iterations=3)

    res = await orchestrator.run(req)

    assert res.status == AgentStatus.MAX_ITERATIONS_REACHED.value
    assert res.iterations == 3
    assert len(res.tool_executions) == 3
    assert "maximum reasoning cycles" in res.final_summary.lower()


@pytest.mark.anyio
async def test_request_cancellation():
    """Cancellation event halts the agent loop cleanly."""
    provider = MockAgentProvider()
    cancel_token = asyncio.Event()
    cancel_token.set()  # Cancel prior to execution

    orchestrator = AgentOrchestrator(provider=provider)
    req = AgentAnalyzeRequest(code="def f(n):\n    return n")

    res = await orchestrator.run(req, cancellation_token=cancel_token)

    assert res.status == AgentStatus.CANCELLED.value
    assert "cancelled" in res.final_summary.lower()


@pytest.mark.anyio
async def test_zero_code_execution_security():
    """Malicious code submitted to the agent is never executed at runtime."""
    canary_file = Path("malicious_canary.txt")
    if canary_file.exists():
        canary_file.unlink()

    malicious_code = f"""
import os
with open("{canary_file.name}", "w") as f:
    f.write("COMPROMISED")
os.system("echo HACKED")
"""

    provider = MockAgentProvider()
    provider.add_step(
        AgentStepResult(
            tool_calls=[
                ToolCall(
                    name="analyze_problem_structure",
                    arguments={"code": malicious_code},
                )
            ],
            finish_reason="tool_calls",
        )
    )
    provider.add_step(
        AgentStepResult(
            content="Static analysis safely completed.",
            finish_reason="stop",
        )
    )

    orchestrator = AgentOrchestrator(provider=provider, registry=default_tool_registry)
    req = AgentAnalyzeRequest(code=malicious_code, filename="solution.py")

    res = await orchestrator.run(req)

    # Canary file must NOT exist (guaranteeing zero runtime execution)
    assert not canary_file.exists(), "Security Violation: User code was executed on host!"
    assert res.status == AgentStatus.SUCCESS.value


# =============================================================================
# REST API Endpoint Tests: POST /api/v1/agent/analyze
# =============================================================================

def test_api_agent_analyze_endpoint_unauthenticated():
    """Unauthenticated client runs agent endpoint without API key, receiving PROVIDER_UNAVAILABLE with static fallback."""
    with TestClient(app) as client:
        payload = {
            "code": "def isPalindrome(s: str) -> bool:\n    return s == s[::-1]",
            "filename": "palindrome.py",
            "test_cases": [{"input_data": {"s": "racecar"}}],
            "max_iterations": 3,
        }
        response = client.post("/api/v1/agent/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PROVIDER_UNAVAILABLE"
        assert data["execution_mode"] == "DEGRADED_STATIC"
        assert data["ai_reasoning_performed"] is False
        assert data["product"] == "EdgeMind"
        assert "session_id" in data
        assert "AI reasoning was not performed" in data["final_summary"]
        assert data["code_analysis"] is not None
        assert data["test_intelligence"] is not None
        assert data["persisted_report_id"] is None  # Unauthenticated -> not saved to user account


def test_api_agent_analyze_input_validations():
    """Enforce source code length bounds, non-empty code, and static_only invariant."""
    with TestClient(app) as client:
        # 1. Empty code rejected
        res = client.post("/api/v1/agent/analyze", json={"code": "   "})
        assert res.status_code in (400, 422)

        # 2. Code exceeding 64 KiB rejected
        large_code = "x = 1\n" * 15000  # > 65,536 bytes
        res = client.post("/api/v1/agent/analyze", json={"code": large_code})
        assert res.status_code in (400, 422)

        # 3. static_only = False rejected
        res = client.post(
            "/api/v1/agent/analyze",
            json={"code": "def f(): pass", "static_only": False},
        )
        assert res.status_code in (400, 422)


@pytest.mark.anyio
async def test_api_agent_analyze_tenant_isolation(sqlite_test_engine):
    """User cannot link analysis to a project owned by a different user."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    project_b_id = uuid.uuid4()

    async with session_factory() as session:
        user1 = User(
            id=user1_id,
            email="user1_agent@example.com",
            full_name="User One",
            password_hash=hash_password("Password123!"),
            role="user",
            is_active=True,
        )
        user2 = User(
            id=user2_id,
            email="user2_agent@example.com",
            full_name="User Two",
            password_hash=hash_password("Password123!"),
            role="user",
            is_active=True,
        )
        proj_b = Project(
            id=project_b_id,
            name="User 2 Secret Project",
            owner_user_id=user2_id,
        )
        session.add_all([user1, user2, proj_b])
        await session.commit()

    token_user1 = create_access_token(user_id=user1_id, role="user")

    with TestClient(app) as client:
        # User 1 tries to attach analysis to User 2's project
        headers = {"Authorization": f"Bearer {token_user1}"}
        payload = {
            "code": "def f(): return 1",
            "project_id": str(project_b_id),
        }
        res = client.post("/api/v1/agent/analyze", json=payload, headers=headers)
        assert res.status_code == 404
        assert "not found" in res.json().get("detail", "").lower()


@pytest.mark.anyio
async def test_api_agent_analyze_authenticated_persistence(sqlite_test_engine):
    """Authenticated user request saves full report document into ReportRepository."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    async with session_factory() as session:
        user = User(
            id=user_id,
            email="persistent_agent@example.com",
            full_name="Persistent Agent",
            password_hash=hash_password("Password123!"),
            role="user",
            is_active=True,
        )
        proj = Project(
            id=project_id,
            name="Agent Persistence Project",
            owner_user_id=user_id,
        )
        session.add_all([user, proj])
        await session.commit()

    token = create_access_token(user_id=user_id, role="user")

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "code": "def two_sum(nums, target):\n    return []",
            "filename": "two_sum.py",
            "project_id": str(project_id),
            "test_cases": [{"input_data": {"nums": [1, 2], "target": 3}}],
        }
        res = client.post("/api/v1/agent/analyze", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "PROVIDER_UNAVAILABLE"
        assert data["execution_mode"] == "DEGRADED_STATIC"
        assert data["ai_reasoning_performed"] is False
        persisted_id = data.get("persisted_report_id")
        assert persisted_id is not None

        # Verify record exists in ReportRepository
        async with session_factory() as session:
            repo = ReportRepository(session)
            report = await repo.get_report_by_session_id(uuid.UUID(data["session_id"]))
            assert report is not None
            assert report["schema_version"] == "1.0.0"
            assert report["analysis_session_id"] == data["session_id"]
            assert report["project_id"] == str(project_id)
            assert report["user_id"] == str(user_id)


def test_api_agent_analyze_static_only_mode():
    """Client can explicitly request mode='static_only' for deterministic completion."""
    with TestClient(app) as client:
        payload = {
            "code": "def solve(nums): return sum(nums)",
            "mode": "static_only",
        }
        res = client.post("/api/v1/agent/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "STATIC_ONLY"
        assert data["execution_mode"] == "STATIC_ONLY"
        assert data["ai_reasoning_performed"] is False
        assert "Deterministic static analysis" in data["final_summary"]
        assert data["code_analysis"] is not None


# =============================================================================
# LiveAgentProvider & Error Handling Tests (Mock HTTP Transport)
# =============================================================================

@pytest.mark.anyio
async def test_live_provider_missing_api_key():
    """When API key is missing, provider returns unavailable finish_reason without pretending to call tools."""
    provider = LiveAgentProvider(api_key=None)
    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "unavailable"
    assert step.error_type == "provider_unavailable"
    assert len(step.tool_calls) == 0
    assert "AI provider API key is not configured" in (step.error or "")

    # Run in orchestrator
    orchestrator = AgentOrchestrator(provider=provider)
    req = AgentAnalyzeRequest(code="def f(x):\n    return x * 2")
    res = await orchestrator.run(req)

    assert res.status == AgentStatus.PROVIDER_UNAVAILABLE.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert res.ai_reasoning_performed is False
    assert len(res.tool_executions) == 0
    assert "AI reasoning was not performed" in res.final_summary
    assert res.code_analysis is not None


@pytest.mark.anyio
async def test_live_provider_invalid_api_key_401():
    """HTTP 401 returns authentication_error and marks orchestrator status PROVIDER_ERROR."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key provided."}})

    transport = httpx.MockTransport(handler)
    provider = LiveAgentProvider(api_key="sk-invalid-key", transport=transport)

    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "error"
    assert step.error_type == "authentication_error"
    assert step.status_code == 401

    orchestrator = AgentOrchestrator(provider=provider)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert res.ai_reasoning_performed is False
    assert "authentication failed" in res.final_summary.lower()
    assert res.code_analysis is not None


@pytest.mark.anyio
async def test_live_provider_rate_limit_429():
    """HTTP 429 returns rate_limit error and marks orchestrator status PROVIDER_ERROR."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit reached for requests."}})

    transport = httpx.MockTransport(handler)
    provider = LiveAgentProvider(api_key="sk-test-key", transport=transport)

    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "error"
    assert step.error_type == "rate_limit"
    assert step.status_code == 429

    orchestrator = AgentOrchestrator(provider=provider)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert "rate limit" in res.final_summary.lower()


@pytest.mark.anyio
async def test_live_provider_server_error_500():
    """HTTP 500 returns server_error and marks orchestrator status PROVIDER_ERROR."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "Internal AI server error."}})

    transport = httpx.MockTransport(handler)
    provider = LiveAgentProvider(api_key="sk-test-key", transport=transport)

    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "error"
    assert step.error_type == "server_error"
    assert step.status_code == 500

    orchestrator = AgentOrchestrator(provider=provider)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert "server error" in res.final_summary.lower()


@pytest.mark.anyio
async def test_live_provider_timeout():
    """ReadTimeout returns timeout error and marks orchestrator status PROVIDER_ERROR."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request connection timed out while waiting for response.")

    transport = httpx.MockTransport(handler)
    provider = LiveAgentProvider(api_key="sk-test-key", timeout=0.1, transport=transport)

    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "error"
    assert step.error_type == "timeout"

    orchestrator = AgentOrchestrator(provider=provider)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert "timed out" in res.final_summary.lower()


@pytest.mark.anyio
async def test_live_provider_network_connection_failure():
    """ConnectError returns connection_error and marks orchestrator status PROVIDER_ERROR."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Network is unreachable or DNS lookup failed.")

    transport = httpx.MockTransport(handler)
    provider = LiveAgentProvider(api_key="sk-test-key", transport=transport)

    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "analyze"}],
        tools=[],
    )

    assert step.finish_reason == "error"
    assert step.error_type == "connection_error"

    orchestrator = AgentOrchestrator(provider=provider)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert "could not connect" in res.final_summary.lower()


@pytest.mark.anyio
async def test_live_provider_malformed_response():
    """Non-JSON or invalid payload structures are trapped and reported as malformed_response."""
    # Subcase A: Invalid JSON string
    def invalid_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Gateway Error</body></html>")

    provider_a = LiveAgentProvider(api_key="sk-test-key", transport=httpx.MockTransport(invalid_json_handler))
    step_a = await provider_a.chat_completion(messages=[{"role": "user", "content": "test"}], tools=[])
    assert step_a.finish_reason == "error"
    assert step_a.error_type == "malformed_response"

    # Subcase B: Empty choices array
    def empty_choices_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider_b = LiveAgentProvider(api_key="sk-test-key", transport=httpx.MockTransport(empty_choices_handler))
    step_b = await provider_b.chat_completion(messages=[{"role": "user", "content": "test"}], tools=[])
    assert step_b.finish_reason == "error"
    assert step_b.error_type == "malformed_response"

    orchestrator = AgentOrchestrator(provider=provider_b)
    res = await orchestrator.run(AgentAnalyzeRequest(code="def f(x):\n    return x"))

    assert res.status == AgentStatus.PROVIDER_ERROR.value
    assert res.execution_mode == "DEGRADED_STATIC"
    assert "malformed" in res.final_summary.lower()


@pytest.mark.anyio
async def test_live_provider_successful_response_parsing_mock_transport():
    """Verify parsing of valid OpenAI function/tool calling JSON response."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_mock_123",
                                "type": "function",
                                "function": {
                                    "name": "parse_problem_constraints",
                                    "arguments": '{"raw_constraints": ["1 <= n <= 100"]}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        return httpx.Response(200, json=payload)

    provider = LiveAgentProvider(api_key="sk-test-key", transport=httpx.MockTransport(handler))
    step = await provider.chat_completion(messages=[{"role": "user", "content": "test"}], tools=[])

    assert step.finish_reason == "tool_calls"
    assert len(step.tool_calls) == 1
    assert step.tool_calls[0].name == "parse_problem_constraints"
    assert step.tool_calls[0].get_arguments_dict() == {"raw_constraints": ["1 <= n <= 100"]}


@pytest.mark.anyio
async def test_live_provider_no_tool_call_response_handling():
    """Verify single-turn direct text response with finish_reason='stop' sets SUCCESS."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Direct final answer: The algorithm is optimal O(N) linear time.",
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ]
        }
        return httpx.Response(200, json=payload)

    provider = LiveAgentProvider(api_key="sk-test-key", transport=httpx.MockTransport(handler))
    orchestrator = AgentOrchestrator(provider=provider)

    req = AgentAnalyzeRequest(code="def f(nums):\n    return sum(nums)")
    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.execution_mode == "AI_AGENT"
    assert res.ai_reasoning_performed is True
    assert res.iterations == 1
    assert len(res.tool_executions) == 0
    assert "Direct final answer" in res.final_summary


@pytest.mark.anyio
async def test_live_provider_multiple_tool_call_rounds():
    """Verify multi-round tool-calling loop using stateful MockTransport."""
    turn_counter = 0

    def stateful_handler(request: httpx.Request) -> httpx.Response:
        nonlocal turn_counter
        turn_counter += 1

        if turn_counter == 1:
            # Round 1: Model requests analyze_problem_structure
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "call_step1",
                                        "type": "function",
                                        "function": {
                                            "name": "analyze_problem_structure",
                                            "arguments": '{"code": "def f(n): return n"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            )
        elif turn_counter == 2:
            # Round 2: Model requests parse_problem_constraints
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "call_step2",
                                        "type": "function",
                                        "function": {
                                            "name": "parse_problem_constraints",
                                            "arguments": '{"raw_constraints": ["1 <= n <= 10^3"]}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            )
        else:
            # Round 3: Final answer
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Multi-turn live reasoning complete: Structure analyzed and bounds extracted.",
                                "tool_calls": [],
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

    provider = LiveAgentProvider(api_key="sk-test-live", transport=httpx.MockTransport(stateful_handler))
    orchestrator = AgentOrchestrator(provider=provider, max_iterations=5)

    req = AgentAnalyzeRequest(code="def f(n):\n    return n")
    res = await orchestrator.run(req)

    assert res.status == AgentStatus.SUCCESS.value
    assert res.execution_mode == "AI_AGENT"
    assert res.ai_reasoning_performed is True
    assert res.iterations == 3
    assert len(res.tool_executions) == 2
    assert res.tool_executions[0].tool_name == "analyze_problem_structure"
    assert res.tool_executions[1].tool_name == "parse_problem_constraints"
    assert "Multi-turn live reasoning complete" in res.final_summary
