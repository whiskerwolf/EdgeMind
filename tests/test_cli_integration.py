import io
import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

from core.analyzer import run_ai_reasoning, print_report, generate_json_report
from core.models import AIResponse


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--json" in result.stdout
    assert "--ai" in result.stdout
    assert "--share-source" in result.stdout
    assert "--static-only" in result.stdout


def test_cli_default_terminal():
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "EDGEMIND REPORT" in result.stdout
    assert "Overall Result: FAIL" in result.stdout
    assert "AI REASONING" not in result.stdout


def test_cli_default_json():
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["file_path"] == "tests/name_error_demo.py"
    assert parsed["overall_status"] == "FAIL"
    # ai_reasoning must not be present when --ai is omitted
    assert "ai_reasoning" not in parsed


def test_cli_ai_without_consent_terminal():
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--ai"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "AI REASONING" in result.stdout
    assert "Status: SKIPPED" in result.stdout
    assert "--share-source" in result.stderr


def test_cli_ai_without_consent_json():
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--ai", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # stdout must be single valid JSON
    parsed = json.loads(result.stdout)
    assert "ai_reasoning" in parsed
    assert parsed["ai_reasoning"]["status"] == "skipped"
    assert "consent" in parsed["ai_reasoning"]["summary"].lower()
    # Diagnostic message went to stderr, not stdout
    assert "--share-source" in result.stderr


def test_cli_ai_with_consent_missing_key(monkeypatch):
    env = os.environ.copy()
    env.pop("CODEDOCTOR_AI_KEY", None)
    env.pop("GEMINI_API_KEY", None)

    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/name_error_demo.py", "--ai", "--share-source", "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "ai_reasoning" in parsed
    assert parsed["ai_reasoning"]["status"] in {"disabled", "failed"}
    # Deterministic findings remain untouched
    assert parsed["score"] == 75
    assert parsed["total_errors"] == 1
    assert parsed["total_warnings"] == 1


def test_run_ai_reasoning_with_mock_adapter():
    mock_adapter = MagicMock()
    mock_adapter.name = "mock_provider"
    mock_adapter.is_available.return_value = True
    mock_adapter.analyze.return_value = AIResponse(
        status="success",
        provider="mock_provider",
        summary="Variable studnet_name is misspelled.",
        insights=[
            {
                "finding_type": "NameError",
                "line": 2,
                "explanation": "Typo in name",
                "suggested_fix": "Fix typo",
                "confidence": "high",
            }
        ],
    )

    findings = [{"type": "NameError", "line": 2, "message": "name error"}]
    reasoning = run_ai_reasoning(
        filename="tests/name_error_demo.py",
        findings=findings,
        user_consent=True,
        adapter=mock_adapter,
    )

    assert reasoning["status"] == "success"
    assert reasoning["provider"] == "mock_provider"
    assert len(reasoning["insights"]) == 1
    assert reasoning["insights"][0]["explanation"] == "Typo in name"


def test_terminal_report_with_ai_reasoning(capsys):
    ai_reasoning = {
        "status": "success",
        "provider": "mock_provider",
        "summary": "Reasoning summary test",
        "insights": [
            {
                "finding_type": "NameError",
                "line": 2,
                "explanation": "Variable is misspelled",
                "suggested_fix": "Correct the spelling",
                "confidence": "high",
            }
        ],
    }

    print_report("tests/name_error_demo.py", ai_reasoning=ai_reasoning)
    captured = capsys.readouterr().out

    assert "EDGEMIND REPORT" in captured
    assert "AI REASONING" in captured
    assert "Status: SUCCESS" in captured
    assert "Provider: mock_provider" in captured
    assert "[AI INSIGHT] NameError (Line 2)" in captured
    assert "Reasoning: Variable is misspelled" in captured
    assert "Suggestion: Correct the spelling" in captured
