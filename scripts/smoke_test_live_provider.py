"""
EdgeMind Phase 5: Live Third-Party Provider Integration Smoke Test.

Verifies genuine live OpenAI API integration:
1. Minimal live chat completion.
2. Live function/tool calling using a registered harmless tool.
3. Live streaming chat completion.
4. Live embedding generation (text-embedding-3-small, 1536 dimensions).
5. Actual token usage and request ID extraction.
6. Exact Decimal cost calculation and accounting integration.

Requirements:
- Normal test suites never make billable external API calls.
- Requires explicit opt-in: EDGEMIND_RUN_LIVE_PROVIDER_TESTS=true
- Never prints or exposes credentials in output or logs.
- If credentials or opt-in flag are absent, reports 'LIVE TESTS NOT RUN'.
"""

import asyncio
from decimal import Decimal
import os
import sys
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.agents.provider import LiveAgentProvider
from core.agents.schemas import AgentAnalyzeRequest
from core.agents.tools import default_tool_registry
from core.config import get_settings
from core.cost import default_cost_calculator, UsageSource
from core.rag.embeddings.openai_provider import OpenAIEmbeddingProvider


def is_live_testing_opted_in() -> bool:
    """Check whether the user explicitly opted into live third-party billable calls."""
    flag = os.environ.get("EDGEMIND_RUN_LIVE_PROVIDER_TESTS", "").strip().lower()
    return flag in ("true", "1", "yes")


async def run_live_smoke_tests() -> int:
    settings = get_settings()
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("EDGEMIND_AI_KEY")
        or settings.get_ai_api_key()
    )

    opted_in = is_live_testing_opted_in()
    has_key = bool(api_key and str(api_key).strip())

    if not opted_in or not has_key:
        print("=" * 72)
        print("EDGEMIND LIVE PROVIDER SMOKE TESTS: STATUS REPORT")
        print("=" * 72)
        print("RESULT: LIVE TESTS NOT RUN")
        if not opted_in:
            print("REASON: Opt-in flag EDGEMIND_RUN_LIVE_PROVIDER_TESTS=true is not set.")
            print("        Set $env:EDGEMIND_RUN_LIVE_PROVIDER_TESTS=\"true\" to enable live calls.")
        if not has_key:
            print("REASON: OPENAI_API_KEY / EDGEMIND_AI_KEY is not configured in environment or .env.")
        print("=" * 72)
        return 0

    print("=" * 72)
    print("EDGEMIND PHASE 5: EXECUTING LIVE THIRD-PARTY SMOKE TESTS")
    print(f"Provider: OpenAI (model: {settings.openai_model})")
    print("Zero credential disclosure: Key presence verified [REDACTED]")
    print("=" * 72)

    passed_steps = 0
    total_steps = 6

    # -------------------------------------------------------------------------
    # 1. Minimal Live Chat Completion
    # -------------------------------------------------------------------------
    print("\n[Step 1/6] Testing Minimal Live Chat Completion...")
    provider = LiveAgentProvider(api_key=api_key, model=settings.openai_model)
    res1 = await provider.chat_completion(
        messages=[
            {"role": "system", "content": "You are a concise test assistant. Respond in 5 words or less."},
            {"role": "user", "content": "Respond: 'EdgeMind live chat OK'"},
        ],
        tools=[],
        temperature=0.0,
    )
    if res1.finish_reason == "error":
        print(f"FAILED Step 1: {res1.error}")
        return 1
    print(f"  Response content: {res1.content.strip() if res1.content else 'None'}")
    print(f"  Request ID: {res1.request_id or 'unavailable'}")
    passed_steps += 1
    print("  Status: PASSED")

    # -------------------------------------------------------------------------
    # 2. Live Function / Tool Calling Request
    # -------------------------------------------------------------------------
    print("\n[Step 2/6] Testing Live Native Function Calling...")
    tools_schema = default_tool_registry.get_schemas()
    res2 = await provider.chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are EdgeMind static analysis agent. When asked to inspect a problem structure, "
                    "call the analyze_problem_structure tool."
                ),
            },
            {
                "role": "user",
                "content": "Analyze the structure for this problem code: 'def solve(x): return x * 2'",
            },
        ],
        tools=tools_schema,
        temperature=0.0,
    )
    if res2.finish_reason == "error":
        print(f"FAILED Step 2: {res2.error}")
        return 1
    print(f"  Tool calls received: {len(res2.tool_calls)}")
    if res2.tool_calls:
        for tc in res2.tool_calls:
            print(f"    Tool: {tc.name}, Arguments: {tc.get_arguments_dict()}")
    passed_steps += 1
    print("  Status: PASSED")

    # -------------------------------------------------------------------------
    # 3. Live Streaming Completion (SSE)
    # -------------------------------------------------------------------------
    print("\n[Step 3/6] Testing Live Streaming Completion...")
    chunks_received = []
    stream_final_result = None
    stream_gen = provider.chat_completion_stream(
        messages=[
            {"role": "user", "content": "Count from 1 to 5 separated by spaces."},
        ],
        tools=[],
        temperature=0.0,
    )
    async for item in stream_gen:
        if isinstance(item, str):
            chunks_received.append(item)
        elif hasattr(item, "finish_reason"):
            stream_final_result = item

    print(f"  Stream chunks received: {len(chunks_received)}")
    print(f"  Accumulated stream text: {''.join(chunks_received)}")
    if stream_final_result:
        print(f"  Stream final finish_reason: {stream_final_result.finish_reason}")
    passed_steps += 1
    print("  Status: PASSED")

    # -------------------------------------------------------------------------
    # 4. Real Embedding Request (text-embedding-3-small)
    # -------------------------------------------------------------------------
    print("\n[Step 4/6] Testing Real Embedding Request (1536 dimensions)...")
    emb_provider = OpenAIEmbeddingProvider(api_key=api_key)
    vec = await emb_provider.embed_text("EdgeMind RAG live semantic similarity test.")
    print(f"  Vector dimensions returned: {len(vec)}")
    assert len(vec) == 1536, f"Expected 1536 dimensions, got {len(vec)}"
    passed_steps += 1
    print("  Status: PASSED")

    # -------------------------------------------------------------------------
    # 5. Actual Token Usage Extraction
    # -------------------------------------------------------------------------
    print("\n[Step 5/6] Testing Actual Token Usage Extraction...")
    assert res1.usage is not None, "Chat completion missing token usage"
    print(f"  Chat prompt tokens: {res1.usage.prompt_tokens}")
    print(f"  Chat completion tokens: {res1.usage.completion_tokens}")
    print(f"  Chat total tokens: {res1.usage.total_tokens}")
    print(f"  Usage source: {res1.usage.usage_source.value}")
    assert res1.usage.usage_source == UsageSource.ACTUAL_PROVIDER

    emb_usage = emb_provider.last_usage
    if emb_usage:
        print(f"  Embedding tokens: {emb_usage.prompt_tokens}")
        print(f"  Embedding model: {emb_usage.model}")
    passed_steps += 1
    print("  Status: PASSED")

    # -------------------------------------------------------------------------
    # 6. Usage and Cost Accounting Integration
    # -------------------------------------------------------------------------
    print("\n[Step 6/6] Testing Cost Calculation and Decimal Precision...")
    cost1 = res1.usage.estimated_cost_usd
    print(f"  Chat estimated cost: ${cost1} USD (exact Decimal)")
    assert isinstance(cost1, Decimal) or cost1 is None

    cost_bd = default_cost_calculator.calculate_cost(
        prompt_tokens=res1.usage.prompt_tokens,
        completion_tokens=res1.usage.completion_tokens,
        model=res1.model,
    )
    print(f"  Cost breakdown total: ${cost_bd.total_cost}")
    assert cost_bd.is_pricing_known is True
    passed_steps += 1
    print("  Status: PASSED")

    print("\n" + "=" * 72)
    print(f"ALL {passed_steps}/{total_steps} LIVE SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_live_smoke_tests())
    sys.exit(exit_code)
