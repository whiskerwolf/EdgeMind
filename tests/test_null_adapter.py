import json
import pytest
import time

from adapters.base import AIAdapter
from adapters.null_adapter import NullAdapter
from core.models import AIInsight, AIRequest, AIResponse


def test_ai_adapter_is_abstract():
    with pytest.raises(TypeError):
        AIAdapter()


def test_null_adapter_implements_interface():
    adapter = NullAdapter()
    assert isinstance(adapter, AIAdapter)
    assert adapter.name == "null"
    assert adapter.is_available() is True


def test_null_adapter_without_user_consent():
    adapter = NullAdapter()
    request = AIRequest(
        file_path="test.py",
        code="x = 1\n",
        findings=[{"type": "UnusedVariable", "line": 1}],
        user_consent=False,
    )

    response = adapter.analyze(request)
    assert isinstance(response, AIResponse)
    assert response.status == "skipped"
    assert response.provider == "null"
    assert "consent" in response.summary.lower()
    assert response.insights == []
    assert response.error is None


def test_null_adapter_with_user_consent():
    custom_reason = "No AI key provided."
    adapter = NullAdapter(reason=custom_reason)
    request = AIRequest(
        file_path="test.py",
        code="x = 1\n",
        findings=[],
        user_consent=True,
    )

    response = adapter.analyze(request)
    assert isinstance(response, AIResponse)
    assert response.status == "disabled"
    assert response.provider == "null"
    assert response.summary == custom_reason
    assert response.insights == []
    assert response.error is None


def test_null_adapter_performance_and_isolation():
    adapter = NullAdapter()
    request = AIRequest(code="print('offline')", user_consent=True)

    start = time.perf_counter()
    response = adapter.analyze(request)
    duration = time.perf_counter() - start

    assert duration < 0.01  # Instantaneous, under 10ms
    assert response.status == "disabled"


def test_ai_data_models_serialization():
    insight = AIInsight(
        finding_type="NameError",
        line=2,
        line_number=2,
        explanation="Typo in variable name",
        suggested_fix="Fix typo",
        confidence="high",
    )
    insight_dict = insight.to_dict()
    assert insight_dict["finding_type"] == "NameError"
    assert insight_dict["line"] == 2
    assert insight_dict["line_number"] == 2
    assert insight_dict["explanation"] == "Typo in variable name"
    assert insight_dict["confidence"] == "high"

    req = AIRequest(
        file_path="main.py",
        code="print(x)",
        findings=[{"type": "NameError", "line": 1}],
        user_consent=True,
    )
    req_dict = req.to_dict()
    assert req_dict["file_path"] == "main.py"
    assert req_dict["user_consent"] is True

    resp = AIResponse(
        status="success",
        provider="test_provider",
        summary="Analysis successful",
        insights=[insight_dict],
        error=None,
    )
    resp_dict = resp.to_dict()
    json_str = json.dumps(resp_dict)
    loaded = json.loads(json_str)
    assert loaded["status"] == "success"
    assert loaded["provider"] == "test_provider"
    assert len(loaded["insights"]) == 1
