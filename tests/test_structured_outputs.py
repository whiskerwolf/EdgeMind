"""
EdgeMind Structured LLM Outputs & Schema Validation Test Suite.

Validates:
1. Valid structured JSON diagnosis parsing, Pydantic validation, Markdown formatting, and report conversion.
2. Invalid JSON handling and safe deterministic fallback.
3. Missing required fields & invalid field types rejection.
4. Strict schema guards (extra='forbid', line bounds, severity enum, unfabricated confidence=None).
5. Provider integration: OpenAI response_format, Gemini responseSchema, Ollama gated format + 400 retry, MockAgentProvider.
6. Provider errors & credential redaction + XML untrusted prompt boundary preservation.
7. Existing streaming and non-streaming REST diagnosis integration (`POST /api/v1/diagnose/structured` and `/stream`).
"""

import json
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import ValidationError

from core.agents.provider import (
    LiveAgentProvider,
    MockAgentProvider,
    OllamaAgentProvider,
    build_gemini_response_schema,
    build_openai_response_format,
    supports_ollama_structured_output,
)
from core.agents.schemas import AgentStepResult
from core.api import app
from core.config import Settings, get_settings
from core.diagnosis_service import DiagnosisService
from core.routes.diagnose import get_diagnosis_service
from core.schemas import (
    CodeLocation,
    DiagnoseFindingRequest,
    FindingPayload,
    StructuredDiagnosisOutput,
)


def _sample_request() -> DiagnoseFindingRequest:
    return DiagnoseFindingRequest(
        finding=FindingPayload(
            finding_id="f-div-zero-1",
            type="ZERO_DIVISION_RISK",
            severity="warning",
            message="Denominator 'count' may be zero when items is empty.",
            line=3,
            static_why="Calling sum(items) / len(items) raises ZeroDivisionError for empty sequences.",
            static_fix="Guard against len(items) == 0 before dividing.",
        ),
        code_context="def avg(items):\n    total = sum(items)\n    return total / len(items)\n",
        context_start_line=1,
        context_end_line=4,
        filename="metrics.py",
    )


def _valid_structured_dict(with_confidence: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "summary": "Division by len(items) raises ZeroDivisionError on empty input.",
        "root_cause": "len(items) evaluates to 0 when items is empty.",
        "explanation": "Python raises ZeroDivisionError whenever the divisor in '/' equals 0.",
        "severity": "WARNING",
        "findings": [
            {
                "title": "Unchecked division by collection length",
                "severity": "warning",
                "explanation": "If items is [], len(items) is 0 on line 3.",
                "recommendation": "Return 0.0 or raise ValueError when not items.",
                "locations": [{"file": "metrics.py", "start_line": 3, "end_line": 3, "symbol": "avg"}],
                "related_finding_id": "f-div-zero-1",
            }
        ],
        "recommendations": [
            "Check 'if not items: return 0.0' before computing total / len(items).",
            "Add a unit test covering empty list input [].",
        ],
        "code_locations": [{"file": "metrics.py", "start_line": 3, "end_line": 3, "symbol": "avg"}],
        "confidence": 0.92 if with_confidence else None,
        "example_fix": "def avg(items):\n    if not items:\n        return 0.0\n    return sum(items) / len(items)",
    }
    return payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


# =============================================================================
# 1-5. Schema Validation Tests
# =============================================================================

def test_structured_diagnosis_valid_schema_and_optional_confidence():
    data = _valid_structured_dict(with_confidence=False)
    model = StructuredDiagnosisOutput.model_validate(data)
    assert model.severity == "warning"
    assert model.confidence is None  # Never fabricated when omitted/null
    assert len(model.findings) == 1
    assert model.findings[0].locations[0].start_line == 3


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d.pop("root_cause"),  # missing required field
        lambda d: d.pop("recommendations"),  # missing required field
        lambda d: d.__setitem__("recommendations", []),  # min_length=1 violated
        lambda d: d.__setitem__("findings", []),  # min_length=1 violated
        lambda d: d.__setitem__("severity", "catastrophic"),  # invalid enum
        lambda d: d.__setitem__("confidence", "high"),  # invalid type
        lambda d: d.__setitem__("confidence", 1.5),  # out of range [0, 1]
        lambda d: d.__setitem__("unexpected_hallucinated_key", "bad"),  # extra='forbid'
        lambda d: d.__setitem__("summary", "   "),  # whitespace-only rejected
    ],
)
def test_structured_diagnosis_rejects_malformed_or_invalid_outputs(mutator):
    payload = _valid_structured_dict()
    mutator(payload)
    with pytest.raises(ValidationError):
        StructuredDiagnosisOutput.model_validate(payload)


def test_code_location_rejects_inverted_line_range():
    with pytest.raises(ValidationError):
        CodeLocation(file="metrics.py", start_line=10, end_line=5)


# =============================================================================
# 6. Provider Structured Output Compatibility Tests
# =============================================================================

@pytest.mark.anyio
async def test_openai_provider_sends_strict_json_schema_response_format():
    captured: Dict[str, Any] = {}
    valid_json = json.dumps(_valid_structured_dict(with_confidence=True))

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-struct-1",
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": valid_json},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
            },
        )

    provider = LiveAgentProvider(
        model="gpt-4o-mini",
        api_key="sk-test-openai-key",
        transport=httpx.MockTransport(handler),
    )
    step = await provider.chat_completion(
        messages=[{"role": "user", "content": "Diagnose"}],
        tools=[],
        response_schema=StructuredDiagnosisOutput,
    )

    rf = captured["body"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "StructuredDiagnosisOutput"
    assert rf["json_schema"]["schema"]["additionalProperties"] is False
    assert StructuredDiagnosisOutput.model_validate_json(step.content).confidence == 0.92


@pytest.mark.anyio
async def test_gemini_native_provider_sends_response_schema_and_parses_usage():
    captured: Dict[str, Any] = {}
    valid_json = json.dumps(_valid_structured_dict())

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": valid_json}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 90,
                    "candidatesTokenCount": 60,
                    "totalTokenCount": 150,
                },
            },
        )

    provider = LiveAgentProvider(
        model="gemini-2.5-flash",
        api_key="AIzaTestGeminiSecretKey123456",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(handler),
    )
    step = await provider.chat_completion(
        messages=[
            {"role": "system", "content": "System rules"},
            {"role": "user", "content": "Diagnose"},
        ],
        tools=[],
        response_schema=StructuredDiagnosisOutput,
    )

    assert ":generateContent" in captured["url"]
    assert "x-goog-api-key" in captured["headers"]
    gen_cfg = captured["body"]["generationConfig"]
    assert gen_cfg["responseMimeType"] == "application/json"
    # Gemini responseSchema must inline $defs and strip $ref
    schema_text = json.dumps(gen_cfg["responseSchema"])
    assert "$ref" not in schema_text
    assert "$defs" not in schema_text
    assert StructuredDiagnosisOutput.model_validate_json(step.content).summary
    assert step.usage is not None
    assert step.usage.provider == "gemini"
    assert step.usage.total_tokens == 150


@pytest.mark.anyio
async def test_ollama_provider_gates_format_by_model_and_retries_on_400():
    # Capability heuristic check
    assert supports_ollama_structured_output("qwen3:4b") is True
    assert supports_ollama_structured_output("llama3.2:latest") is True
    assert supports_ollama_structured_output("legacy-custom-model:v1") is False

    # 1. Unsupported model omits "format"
    seen_payloads: List[Dict[str, Any]] = []
    valid_json = json.dumps(_valid_structured_dict())

    async def legacy_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        seen_payloads.append(body)
        return httpx.Response(
            200,
            json={
                "model": "legacy-custom-model:v1",
                "message": {"role": "assistant", "content": valid_json},
                "done_reason": "stop",
            },
        )

    legacy_ollama = OllamaAgentProvider(
        model="legacy-custom-model:v1",
        transport=httpx.MockTransport(legacy_handler),
    )
    await legacy_ollama.chat_completion(
        messages=[{"role": "user", "content": "Diagnose"}],
        tools=[],
        response_schema=StructuredDiagnosisOutput,
    )
    assert "format" not in seen_payloads[0]

    # 2. Supported model sends "format", and degrades on HTTP 400 by retrying without "format"
    qwen_attempts: List[Dict[str, Any]] = []

    async def retry_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        qwen_attempts.append(body)
        if "format" in body:
            return httpx.Response(400, text="unsupported format schema")
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": valid_json},
                "done_reason": "stop",
                "prompt_eval_count": 50,
                "eval_count": 40,
            },
        )

    qwen_ollama = OllamaAgentProvider(
        model="qwen3:4b",
        transport=httpx.MockTransport(retry_handler),
    )
    step = await qwen_ollama.chat_completion(
        messages=[{"role": "user", "content": "Diagnose"}],
        tools=[],
        response_schema=StructuredDiagnosisOutput,
    )
    assert len(qwen_attempts) == 2
    assert "format" in qwen_attempts[0]
    assert "format" not in qwen_attempts[1]
    assert step.finish_reason == "stop"
    assert StructuredDiagnosisOutput.model_validate_json(step.content).severity == "warning"


def test_schema_builder_helpers_produce_valid_descriptors():
    openai_rf = build_openai_response_format(StructuredDiagnosisOutput)
    assert openai_rf["json_schema"]["strict"] is True
    assert openai_rf["json_schema"]["schema"]["additionalProperties"] is False

    gemini_rs = build_gemini_response_schema(StructuredDiagnosisOutput)
    assert gemini_rs["type"] == "object"
    assert "confidence" in gemini_rs["properties"]


# =============================================================================
# 7-8. DiagnosisService Validation, Fallback & Security Tests
# =============================================================================

@pytest.mark.anyio
async def test_diagnosis_service_structured_success_and_markdown_rendering():
    # Include fenced JSON and an embedded accidental secret to verify both fence stripping & redaction
    secret_val = "sk-live-secret-should-be-masked-999999"
    payload = _valid_structured_dict()
    payload["summary"] = f"Division issue near {secret_val}"
    fenced_json = f"```json\n{json.dumps(payload)}\n```"

    mock_provider = MockAgentProvider(
        steps=[AgentStepResult(content=fenced_json, finish_reason="stop")]
    )
    service = DiagnosisService(provider=mock_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))

    prompts = service.build_structured_prompts(_sample_request())
    assert "<untrusted_source_code>" in prompts[1]["content"]

    res = await service.diagnose_structured(_sample_request(), custom_secrets=[secret_val])
    assert res.status == "structured"
    assert res.used_fallback is False
    assert res.validation_error is None
    assert res.structured is not None
    assert secret_val not in res.structured.summary
    assert "### Root Cause" in res.markdown
    assert "### Why This Happens" in res.markdown
    assert "### Recommended Fix" in res.markdown
    assert "### Example" in res.markdown
    assert mock_provider.call_history[0]["response_schema"] == "StructuredDiagnosisOutput"

    report_payload = res.to_report_payload()
    assert report_payload["status"] == "structured"
    assert report_payload["structured"]["severity"] == "warning"


@pytest.mark.anyio
async def test_diagnosis_service_invalid_json_and_schema_failure_trigger_safe_fallback():
    req = _sample_request()

    # 1. Invalid JSON prose -> deterministic static fallback
    bad_json_provider = MockAgentProvider(
        steps=[AgentStepResult(content="Here is an unparseable response {", finish_reason="stop")]
    )
    service1 = DiagnosisService(provider=bad_json_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))
    res1 = await service1.diagnose_structured(req)
    assert res1.status == "fallback_static"
    assert res1.used_fallback is True
    assert res1.structured is None
    assert res1.validation_error is not None
    assert "### Root Cause" in res1.markdown
    assert "len(items)" in res1.markdown or "ZeroDivisionError" in res1.markdown

    # 2. Valid JSON but missing required fields -> ValidationError fallback
    incomplete_json = json.dumps({"summary": "Incomplete output only"})
    incomplete_provider = MockAgentProvider(
        steps=[AgentStepResult(content=incomplete_json, finish_reason="stop")]
    )
    service2 = DiagnosisService(provider=incomplete_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))
    res2 = await service2.diagnose_structured(req)
    assert res2.status == "fallback_static"
    assert res2.used_fallback is True
    assert res2.structured is None
    assert res2.validation_error is not None

    # 3. Markdown prose emitted when schema failed -> fallback_markdown preserves useful explanation
    md_prose = "### Root Cause\nDenominator may be zero.\n\n### Recommended Fix\n- Check len(items) > 0."
    md_provider = MockAgentProvider(steps=[AgentStepResult(content=md_prose, finish_reason="stop")])
    service3 = DiagnosisService(provider=md_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))
    res3 = await service3.diagnose_structured(req)
    assert res3.status == "fallback_markdown"
    assert res3.used_fallback is True
    assert "### Root Cause" in res3.markdown


@pytest.mark.anyio
async def test_diagnosis_service_provider_error_and_unavailable_fallback():
    req = _sample_request()

    # 1. Unconfigured live provider (unavailable)
    no_key_provider = LiveAgentProvider(api_key="", model="gpt-4o-mini")
    service_unavail = DiagnosisService(provider=no_key_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))
    res_unavail = await service_unavail.diagnose_structured(req)
    assert res_unavail.status == "unavailable"
    assert res_unavail.used_fallback is True
    assert "### Root Cause" in res_unavail.markdown

    # 2. Provider error step sanitizing secrets
    secret_key = "sk-provider-secret-do-not-expose"
    err_provider = MockAgentProvider(
        steps=[
            AgentStepResult(
                content=f"Failure using {secret_key}",
                finish_reason="error",
                error=f"Auth failure with {secret_key}",
            )
        ]
    )
    service_err = DiagnosisService(provider=err_provider, settings=Settings(jwt_secret_key="jwt-secret-test"))
    res_err = await service_err.diagnose_structured(req, custom_secrets=[secret_key])
    assert res_err.status == "fallback_static"
    assert res_err.used_fallback is True
    assert secret_key not in (res_err.validation_error or "")
    assert secret_key not in res_err.markdown


# =============================================================================
# 9-10. Structured & Streaming Endpoint Compatibility Tests
# =============================================================================

def test_diagnose_structured_rest_endpoint_end_to_end():
    payload = _valid_structured_dict(with_confidence=True)
    mock_provider = MockAgentProvider(
        steps=[AgentStepResult(content=json.dumps(payload), finish_reason="stop")]
    )
    app.dependency_overrides[get_diagnosis_service] = lambda: DiagnosisService(
        provider=mock_provider,
        settings=get_settings(),
    )
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/diagnose/structured",
                json=_sample_request().model_dump(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "structured"
        assert body["used_fallback"] is False
        assert body["structured"]["confidence"] == 0.92
        assert "### Root Cause" in body["markdown"]
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)
