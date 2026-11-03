import copy
import pytest

from adapters.base import AIAdapter
from adapters.null_adapter import NullAdapter
from core.ai_engine import AIEngine
from core.models import AIInsight, AIRequest, AIResponse


class MockAIAdapter(AIAdapter):
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.received_request = None

    @property
    def name(self) -> str:
        return "mock_ai"

    def is_available(self) -> bool:
        return True

    def analyze(self, request: AIRequest) -> AIResponse:
        self.received_request = request
        if self._exception:
            raise self._exception
        return self._response or AIResponse(status="success", provider="mock_ai")


def test_valid_ai_response_produces_separate_insights():
    mock_insight = {
        "finding_type": "NameError",
        "line": 2,
        "line_number": 2,
        "explanation": "Variable studnet_name is misspelled.",
        "suggested_fix": "Change studnet_name to student_name.",
        "confidence": "high",
    }
    adapter = MockAIAdapter(
        response=AIResponse(
            status="success",
            provider="mock_ai",
            summary="Identified typo.",
            insights=[mock_insight],
        )
    )

    engine = AIEngine(adapter=adapter)
    base_report = {
        "file_path": "demo.py",
        "score": 75,
        "overall_status": "FAIL",
        "status": "FAIL",
        "total_errors": 1,
        "total_warnings": 0,
        "detailed_errors": [
            {
                "type": "NameError",
                "line": 2,
                "message": "name 'studnet_name' is not defined",
                "why": "Python cannot find 'studnet_name'.",
                "fix": "Replace 'studnet_name' with 'student_name'.",
                "concept": "Runtime Error Handling",
            }
        ],
        "detailed_warnings": [],
    }

    code = "student_name = 'Rithwik'\nprint(studnet_name)\n"
    enriched = engine.enrich_report(base_report, code=code, user_consent=True)

    # Deterministic findings must remain preserved
    assert len(enriched["detailed_errors"]) == 1
    assert enriched["detailed_errors"][0]["type"] == "NameError"
    assert enriched["detailed_errors"][0]["why"] == "Python cannot find 'studnet_name'."

    # AI findings are stored separately in ai_reasoning
    ai_reasoning = enriched["ai_reasoning"]
    assert ai_reasoning["status"] == "success"
    assert ai_reasoning["provider"] == "mock_ai"
    assert ai_reasoning["summary"] == "Identified typo."
    assert len(ai_reasoning["insights"]) == 1
    assert ai_reasoning["insights"][0]["explanation"] == "Variable studnet_name is misspelled."


def test_disabled_adapter_uses_safe_fallback():
    engine = AIEngine(adapter=NullAdapter())

    base_report = {
        "file_path": "clean.py",
        "score": 100,
        "overall_status": "PASS",
        "status": "PASS",
        "total_errors": 0,
        "total_warnings": 0,
        "detailed_errors": [],
        "detailed_warnings": [],
    }

    enriched = engine.enrich_report(base_report, code="x = 1\n", user_consent=True)

    assert enriched["score"] == 100
    assert enriched["overall_status"] == "PASS"
    assert enriched["ai_reasoning"]["status"] == "disabled"
    assert enriched["ai_reasoning"]["insights"] == []


def test_missing_consent_never_sends_source_code():
    adapter = MockAIAdapter(response=AIResponse(status="skipped", summary="No consent"))
    engine = AIEngine(adapter=adapter)

    secret_code = "SECRET_KEY = 'super_secret_value_12345'\n"
    response = engine.analyze(
        file_path="secret.py",
        code=secret_code,
        findings=[],
        user_consent=False,
    )

    assert adapter.received_request is not None
    assert adapter.received_request.user_consent is False
    assert adapter.received_request.code == ""
    assert secret_code not in adapter.received_request.code


def test_adapter_exception_handled_safely():
    adapter = MockAIAdapter(exception=RuntimeError("Internal adapter explosion"))
    engine = AIEngine(adapter=adapter)

    response = engine.analyze(
        file_path="sample.py",
        code="x = 1\n",
        findings=[],
        user_consent=True,
    )

    assert isinstance(response, AIResponse)
    assert response.status == "failed"
    assert "Internal adapter explosion" in str(response.error)
    assert response.insights == []


def test_malformed_ai_response_rejected():
    # Case A: adapter returns non-AIResponse object
    adapter_bad_type = MockAIAdapter(response={"status": "success", "insights": []})
    engine_bad_type = AIEngine(adapter=adapter_bad_type)
    resp1 = engine_bad_type.analyze("test.py", "x = 1\n", [], user_consent=True)
    assert resp1.status == "failed"
    assert "Invalid response object" in str(resp1.error)

    # Case B: response insights is not a list
    resp_obj = AIResponse(status="success", provider="test")
    resp_obj.insights = "not-a-list"
    adapter_bad_insights = MockAIAdapter(response=resp_obj)
    engine_bad_insights = AIEngine(adapter=adapter_bad_insights)
    resp2 = engine_bad_insights.analyze("test.py", "x = 1\n", [], user_consent=True)
    assert resp2.status == "failed"
    assert "Malformed insights" in str(resp2.error)

    # Case C: response insight element is not a dict
    resp_obj2 = AIResponse(status="success", provider="test", insights=["not-a-dict"])
    adapter_bad_item = MockAIAdapter(response=resp_obj2)
    engine_bad_item = AIEngine(adapter=adapter_bad_item)
    resp3 = engine_bad_item.analyze("test.py", "x = 1\n", [], user_consent=True)
    assert resp3.status == "failed"
    assert "Malformed insight item" in str(resp3.error)


def test_original_findings_remain_unchanged():
    class MutatingAdapter(AIAdapter):
        @property
        def name(self):
            return "mutator"

        def is_available(self):
            return True

        def analyze(self, request: AIRequest) -> AIResponse:
            request.findings.clear()
            return AIResponse(status="success", provider="mutator")

    original_findings = [
        {"type": "ZeroDivisionError", "line": 5, "message": "div zero"}
    ]
    findings_copy = copy.deepcopy(original_findings)

    engine = AIEngine(adapter=MutatingAdapter())
    engine.analyze("test.py", "1 / 0\n", findings_copy, user_consent=True)

    assert findings_copy == original_findings
    assert len(findings_copy) == 1
    assert findings_copy[0]["type"] == "ZeroDivisionError"


def test_score_errors_warnings_status_remain_unchanged():
    adapter = MockAIAdapter(
        response=AIResponse(
            status="success",
            provider="mock_ai",
            summary="All clear",
            insights=[],
        )
    )
    engine = AIEngine(adapter=adapter)

    base_report = {
        "file_path": "broken.py",
        "score": 40,
        "overall_status": "FAIL",
        "status": "FAIL",
        "total_errors": 2,
        "total_warnings": 4,
        "detailed_errors": [{"type": "SyntaxError", "line": 1}],
        "detailed_warnings": [{"type": "UnusedVariable", "line": 3}],
    }

    enriched = engine.enrich_report(base_report, code="x = 1\n", user_consent=True)

    assert enriched["score"] == 40
    assert enriched["overall_status"] == "FAIL"
    assert enriched["status"] == "FAIL"
    assert enriched["total_errors"] == 2
    assert enriched["total_warnings"] == 4
    assert len(enriched["detailed_errors"]) == 1
    assert len(enriched["detailed_warnings"]) == 1


def test_empty_findings_handled_correctly():
    adapter = MockAIAdapter(
        response=AIResponse(
            status="success",
            provider="mock_ai",
            summary="Code looks great!",
            insights=[],
        )
    )
    engine = AIEngine(adapter=adapter)

    clean_report = {
        "file_path": "clean.py",
        "score": 100,
        "overall_status": "PASS",
        "status": "PASS",
        "total_errors": 0,
        "total_warnings": 0,
        "detailed_errors": [],
        "detailed_warnings": [],
    }

    enriched = engine.enrich_report(clean_report, code="def add(a, b): return a + b\n", user_consent=True)

    assert enriched["score"] == 100
    assert enriched["overall_status"] == "PASS"
    assert enriched["ai_reasoning"]["status"] == "success"
    assert enriched["ai_reasoning"]["summary"] == "Code looks great!"
    assert enriched["ai_reasoning"]["insights"] == []


def test_bounded_source_code_truncation():
    adapter = MockAIAdapter(response=AIResponse(status="success"))
    engine = AIEngine(adapter=adapter)

    # Test line count bound
    long_code = "\n".join([f"x_{i} = {i}" for i in range(500)])
    engine.analyze("long.py", code=long_code, findings=[], user_consent=True)
    assert adapter.received_request is not None
    assert len(adapter.received_request.code.splitlines()) <= engine.MAX_SOURCE_LINES + 2
    assert "truncated" in adapter.received_request.code

    # Test char count bound
    huge_code = "a" * (engine.MAX_SOURCE_CHARS + 5000)
    engine.analyze("huge.py", code=huge_code, findings=[], user_consent=True)
    assert len(adapter.received_request.code) < engine.MAX_SOURCE_CHARS + 200
    assert "truncated" in adapter.received_request.code
