import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from adapters.base import AIAdapter
from core.models import AIInsight, AIRequest, AIResponse


class HttpAdapter(AIAdapter):
    """
    HTTP-based AI reasoning adapter using Python's standard urllib.request.
    Communicates with external AI providers over HTTPS with strict timeout,
    input validation, and credential sanitization.
    """

    DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def __init__(
        self,
        api_key_env_var: str = "EDGEMIND_AI_KEY",
        endpoint: Optional[str] = None,
        timeout: float = 5.0,
        provider_name: str = "gemini",
    ):
        self.api_key_env_var = api_key_env_var
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout
        self.provider_name = provider_name

    @property
    def name(self) -> str:
        return self.provider_name

    def get_api_key(self) -> Optional[str]:
        """Read API key exclusively from centralized settings or environment variables."""
        try:
            from core.config import get_settings
            cfg_key = get_settings().get_ai_api_key()
            if cfg_key:
                return cfg_key
        except Exception:
            pass
        return (
            os.environ.get(self.api_key_env_var)
            or os.environ.get("EDGEMIND_AI_KEY")
            or os.environ.get("CODEDOCTOR_AI_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    def is_available(self) -> bool:
        """Check if API key is present in environment."""
        return bool(self.get_api_key())

    def _sanitize_error(self, message: str, key: Optional[str] = None) -> str:
        """Redact sensitive API keys or credentials from error strings."""
        sanitized = message
        if key and key in sanitized:
            sanitized = sanitized.replace(key, "[REDACTED]")
        try:
            from core.config import get_settings
            sanitized = get_settings().sanitize_error(sanitized)
        except Exception:
            pass
        active_key = self.get_api_key()
        if active_key and active_key in sanitized:
            sanitized = sanitized.replace(active_key, "[REDACTED]")
        return sanitized

    def _build_prompt(self, request: AIRequest) -> str:
        """Build instructions and context for structured diagnostic explanation."""
        findings_json = json.dumps(request.findings, indent=2)
        return (
            "You are EdgeMind's AI reasoning assistant.\n"
            "Analyze the following Python source code and deterministic diagnostic findings.\n"
            "Explain the issues and suggest educational, safe improvements.\n\n"
            "RULES:\n"
            "1. Output valid JSON only, without markdown fences.\n"
            "2. Do NOT remove, deny, or override the deterministic findings.\n"
            "3. Format schema:\n"
            "{\n"
            '  "summary": "Short overall reasoning summary",\n'
            '  "insights": [\n'
            "    {\n"
            '      "finding_type": "type name",\n'
            '      "line": 0,\n'
            '      "explanation": "why this occurred",\n'
            '      "suggested_fix": "how to resolve",\n'
            '      "confidence": "high"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"FILE: {request.file_path}\n"
            f"FINDINGS:\n{findings_json}\n\n"
            f"SOURCE CODE:\n{request.code}\n"
        )

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """Extract inner JSON string from common LLM response envelopes."""
        # Gemini envelope: candidates[0].content.parts[0].text
        if "candidates" in data and isinstance(data["candidates"], list) and data["candidates"]:
            candidate = data["candidates"][0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            if parts and isinstance(parts, list):
                first_part = parts[0]
                if isinstance(first_part, dict) and "text" in first_part:
                    return first_part["text"]

        # OpenAI envelope: choices[0].message.content
        if "choices" in data and isinstance(data["choices"], list) and data["choices"]:
            choice = data["choices"][0]
            message = choice.get("message", {})
            if isinstance(message, dict) and "content" in message:
                return message["content"]

        # If already formatted directly as top-level dict
        if "insights" in data or "summary" in data:
            return json.dumps(data)

        raise ValueError("Response payload does not contain expected content structure.")

    def _validate_and_parse_insights(self, content_str: str) -> tuple[str, List[Dict[str, Any]]]:
        """Validate response JSON against strict schema and return parsed insights."""
        cleaned = content_str.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Response must be a JSON object.")

        summary = str(payload.get("summary", "Analysis completed."))
        raw_insights = payload.get("insights", [])

        if not isinstance(raw_insights, list):
            raise ValueError("'insights' field must be a list.")

        validated_insights = []
        for idx, item in enumerate(raw_insights):
            if not isinstance(item, dict):
                raise ValueError(f"Insight at index {idx} must be a dictionary.")

            raw_type = item.get("finding_type", item.get("type", "Unknown"))
            raw_line = item.get("line", item.get("line_number", 0))
            try:
                line_num = int(raw_line) if raw_line is not None else 0
            except (ValueError, TypeError):
                line_num = 0

            explanation = str(item.get("explanation", item.get("why", "")))
            suggested_fix = str(item.get("suggested_fix", item.get("fix", "")))
            confidence = str(item.get("confidence", "medium"))

            insight = AIInsight(
                finding_type=str(raw_type),
                line=line_num,
                line_number=line_num,
                explanation=explanation,
                suggested_fix=suggested_fix,
                confidence=confidence,
            )
            validated_insights.append(insight.to_dict())

        return summary, validated_insights

    def analyze(self, request: AIRequest) -> AIResponse:
        """Execute AI analysis over HTTPS with strict validation and error handling."""
        # 1. Require explicit user consent before transmitting any code
        if not request.user_consent:
            return AIResponse(
                status="skipped",
                provider=self.name,
                summary="Source-sharing consent not granted.",
                insights=[],
                error=None,
            )

        # 2. Check API key
        api_key = self.get_api_key()
        if not api_key:
            return AIResponse(
                status="failed",
                provider=self.name,
                summary="API key not found in environment.",
                insights=[],
                error="Missing API key in environment variable.",
            )

        # 3. Construct payload
        prompt = self._build_prompt(request)
        payload_data = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        body_bytes = json.dumps(payload_data).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "EdgeMind-Analyzer/1.0",
            "x-goog-api-key": api_key,
        }

        req = urllib.request.Request(
            url=self.endpoint,
            data=body_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_text = response.read().decode("utf-8")
                raw_json = json.loads(response_text)

            content_str = self._extract_content(raw_json)
            summary, insights = self._validate_and_parse_insights(content_str)

            return AIResponse(
                status="success",
                provider=self.name,
                summary=summary,
                insights=insights,
                error=None,
            )

        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return AIResponse(
                    status="failed",
                    provider=self.name,
                    summary="Authentication failed. Verify your API key.",
                    insights=[],
                    error="HTTP 401: Unauthorized",
                )
            elif exc.code == 429:
                return AIResponse(
                    status="failed",
                    provider=self.name,
                    summary="AI service rate limit exceeded. Please try again later.",
                    insights=[],
                    error="HTTP 429: Rate limit exceeded",
                )
            else:
                return AIResponse(
                    status="failed",
                    provider=self.name,
                    summary=f"AI service returned HTTP error {exc.code}.",
                    insights=[],
                    error=f"HTTP {exc.code}: {exc.reason}",
                )

        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            is_timeout = isinstance(exc, (socket.timeout, TimeoutError))
            if not is_timeout and hasattr(exc, "reason"):
                is_timeout = (
                    isinstance(exc.reason, socket.timeout)
                    or "timed out" in str(exc.reason).lower()
                )

            if is_timeout:
                return AIResponse(
                    status="failed",
                    provider=self.name,
                    summary="AI reasoning request timed out.",
                    insights=[],
                    error="Network timeout",
                )

            clean_reason = self._sanitize_error(str(getattr(exc, "reason", exc)), api_key)
            return AIResponse(
                status="failed",
                provider=self.name,
                summary="Network connection to AI provider failed.",
                insights=[],
                error=f"Network error: {clean_reason}",
            )

        except json.JSONDecodeError:
            return AIResponse(
                status="failed",
                provider=self.name,
                summary="AI service returned invalid JSON.",
                insights=[],
                error="Invalid JSON in provider response",
            )

        except ValueError as exc:
            return AIResponse(
                status="failed",
                provider=self.name,
                summary="AI response did not match expected schema.",
                insights=[],
                error=f"Malformed schema: {self._sanitize_error(str(exc), api_key)}",
            )

        except Exception as exc:
            return AIResponse(
                status="failed",
                provider=self.name,
                summary="An unexpected error occurred during AI reasoning.",
                insights=[],
                error=f"Unexpected error: {self._sanitize_error(str(exc), api_key)}",
            )
