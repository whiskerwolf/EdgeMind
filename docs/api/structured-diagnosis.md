# EdgeMind Structured LLM Outputs Architecture

## Overview

EdgeMind enforces strict Pydantic schema validation on structured AI finding diagnoses while keeping SSE streaming (`POST /api/v1/diagnose/stream`), conversational multi-step agent loops (`AgentOrchestrator`), and user-facing Markdown rendering backward-compatible.

## Schemas (`core/schemas.py`)

- `StructuredDiagnosisOutput` (`extra="forbid"`):
  - Required: `summary`, `root_cause`, `explanation`, `severity` (`error` | `warning` | `info`), `findings` (non-empty list of `DiagnosisFindingItem`), `recommendations` (non-empty list of strings).
  - Optional: `code_locations` (`List[CodeLocation]`), `confidence` (`Optional[float]` in `[0.0, 1.0]`, defaults to `None` and is never fabricated), `example_fix` (`Optional[str]`).
  - Validators normalize Unicode, strip null bytes, enforce line-range consistency (`end_line >= start_line`), and reject malformed/empty/hallucinated fields.
- `DiagnosisExecutionResult`: Wraps `status` (`structured`, `fallback_markdown`, `fallback_static`, `unavailable`, `error`), optional validated `StructuredDiagnosisOutput`, rendered canonical Markdown (`markdown`), `used_fallback`, sanitized `validation_error`, provider/model metadata, usage tracking, and `to_report_payload()`.

## Provider Integration (`core/agents/provider.py`)

When `chat_completion(..., response_schema=StructuredDiagnosisOutput)` is invoked:
- **OpenAI / OpenAI-Compatible (`LiveAgentProvider`)**: Emits `response_format={"type": "json_schema", "json_schema": {"name": ..., "strict": True, "schema": ...}}` with `additionalProperties: false` and explicit `required` keys across nested `$defs`.
- **Google Gemini (`LiveAgentProvider`)**:
  - OpenAI-compatible Gemini endpoint (`/openai`) uses `response_format`.
  - Native Gemini REST (`generativelanguage.googleapis.com` without `/openai`) sends `x-goog-api-key` and `generationConfig={"responseMimeType": "application/json", "responseSchema": ...}` with `$ref`/`$defs` inlined.
- **Ollama (`OllamaAgentProvider`)**: Gated by `supports_ollama_structured_output(model)` (prefixes such as `qwen2.5`, `qwen3`, `llama3.1+`, `mistral`, `gemma2/3`, `deepseek`, `phi4`, `command-r`) or explicit `supports_structured_outputs` override. Only supported models receive the `"format"` JSON schema parameter; unknown models omit `"format"`, and an HTTP `400` triggers one automatic retry without `"format"`.
- **Mock (`MockAgentProvider`)**: Records `response_schema` in `call_history` and returns scripted JSON or failure outputs deterministically.

## Validation, Security & Fallback (`core/diagnosis_service.py`)

`DiagnosisService.diagnose_structured(request)` and `POST /api/v1/diagnose/structured`:
1. Wraps untrusted source code in `<untrusted_source_code>` tags (`wrap_untrusted`).
2. Strips accidental Markdown JSON code fences, parses JSON, and validates strictly against `StructuredDiagnosisOutput`.
3. Redacts configured credentials (`redact_secrets` / `settings.sanitize_error`) from both structured fields and fallback/error text.
4. Falls back deterministically on invalid JSON, `ValidationError`, provider errors, or unavailable credentials:
   - Preserves valid Markdown section responses as `status="fallback_markdown"`.
   - Generates deterministic static explanation Markdown from `FindingPayload` (`static_why` / `static_fix`) as `status="fallback_static"` or `"unavailable"`.
5. Converts validated `StructuredDiagnosisOutput` into canonical Markdown (`### Root Cause`, `### Why This Happens`, `### Recommended Fix`, `### Example`) for downstream UI and report compatibility.

## Limitations

- Structured schema enforcement is applied to non-streaming single-turn diagnosis (`DiagnosisService.diagnose_structured` / `POST /api/v1/diagnose/structured`); incremental SSE streams (`POST /api/v1/diagnose/stream` and multi-step `AgentOrchestrator`) intentionally remain token-streamed Markdown/tool calls to preserve low latency and conversational behavior.
- Ollama model support varies by upstream model quantization and Ollama server version; unknown models rely on prompt-guided JSON and deterministic fallback if validation fails.
- Provider schema integration tests execute against `httpx.MockTransport`; live third-party API accuracy depends on the active model configured at runtime.
