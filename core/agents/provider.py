"""
AI Provider Interface and Implementations for EdgeMind Agent.

Defines:
- BaseAgentProvider: Abstract interface supporting function/tool calling.
- MockAgentProvider: Scriptable, deterministic provider for automated testing
  (multi-step sequences, error injection, tool calls, malformed responses).
- LiveAgentProvider: Real LLM provider (OpenAI / Gemini function calling) with
  graceful fallback and credential redaction.
"""

from abc import ABC, abstractmethod
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

import httpx

from core.agents.schemas import AgentStepResult, ToolCall
from core.config import get_settings

logger = logging.getLogger("edgemind.agents.provider")


class BaseAgentProvider(ABC):
    """Abstract base class for all agent LLM reasoning providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier name (e.g. 'mock', 'openai', 'gemini')."""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        """
        Request the next reasoning step from the provider.
        May return tool calls, intermediate thought, or final content.
        """
        pass


class MockAgentProvider(BaseAgentProvider):
    """
    Deterministic provider for automated testing and verifiable agent workflows.
    Allows scripting a sequence of tool calls and final responses.
    """

    def __init__(
        self,
        steps: Optional[List[Union[AgentStepResult, Callable[..., AgentStepResult]]]] = None,
        default_final_answer: str = "Analysis complete: all edge cases evaluated and ranked.",
    ):
        self._steps: List[Union[AgentStepResult, Callable[..., AgentStepResult]]] = list(steps or [])
        self._default_final_answer = default_final_answer
        self.call_history: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    def add_step(self, step: Union[AgentStepResult, Callable[..., AgentStepResult]]) -> "MockAgentProvider":
        """Add an execution step to the provider's scripted queue."""
        self._steps.append(step)
        return self

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        # Record invocation for test assertion
        self.call_history.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        })

        if not self._steps:
            # Default termination step
            return AgentStepResult(
                content=self._default_final_answer,
                tool_calls=[],
                finish_reason="stop",
            )

        next_step = self._steps.pop(0)
        if callable(next_step):
            res = next_step(messages, tools)
            if hasattr(res, "__await__"):
                return await res
            return res

        return next_step


class LiveAgentProvider(BaseAgentProvider):
    """
    Live AI reasoning provider communicating via standard function calling APIs.
    Supports OpenAI-compatible endpoints or Google Gemini API.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.settings = get_settings()
        self._api_key = api_key or self.settings.get_ai_api_key()
        self._model = model or "gpt-4o-mini"
        self._base_url = base_url or "https://api.openai.com/v1"
        self._timeout = timeout
        self._transport = transport

    @property
    def name(self) -> str:
        return "live_llm"

    def is_available(self) -> bool:
        """Return True if an API key is configured for live AI reasoning."""
        return bool(self._api_key and str(self._api_key).strip())

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        if not self._api_key or not str(self._api_key).strip():
            logger.info("LiveAgentProvider: No API key configured. Returning unavailable status.")
            return AgentStepResult(
                content="AI provider API key is not configured. AI reasoning was not performed.",
                tool_calls=[],
                finish_reason="unavailable",
                error="AI provider API key is not configured.",
                error_type="provider_unavailable",
            )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(
                    f"{self._base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 401:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider authentication failed (HTTP 401): {sanitized_err}")
                    return AgentStepResult(
                        content="AI provider authentication failed (HTTP 401): Invalid or unauthorized API key.",
                        finish_reason="error",
                        error="Authentication failure: HTTP 401 Unauthorized",
                        error_type="authentication_error",
                        status_code=401,
                    )

                if response.status_code == 429:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider rate limit exceeded (HTTP 429): {sanitized_err}")
                    return AgentStepResult(
                        content="AI provider rate limit exceeded (HTTP 429).",
                        finish_reason="error",
                        error="Rate limit exceeded: HTTP 429 Too Many Requests",
                        error_type="rate_limit",
                        status_code=429,
                    )

                if response.status_code >= 500:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider server error (HTTP {response.status_code}): {sanitized_err}")
                    return AgentStepResult(
                        content=f"AI provider server error (HTTP {response.status_code}).",
                        finish_reason="error",
                        error=f"Server error: HTTP {response.status_code}",
                        error_type="server_error",
                        status_code=response.status_code,
                    )

                if response.status_code != 200:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider HTTP error {response.status_code}: {sanitized_err}")
                    return AgentStepResult(
                        content=f"AI provider returned HTTP error {response.status_code}.",
                        finish_reason="error",
                        error=f"HTTP error: {response.status_code}",
                        error_type="http_error",
                        status_code=response.status_code,
                    )

                try:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Response body is not a JSON object.")
                    choices = data.get("choices")
                    if not isinstance(choices, list) or len(choices) == 0:
                        raise ValueError("Response JSON missing non-empty 'choices' array.")
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise ValueError("First choice element is not a JSON object.")
                    message = choice.get("message")
                    if not isinstance(message, dict):
                        raise ValueError("Choice missing valid 'message' dictionary.")
                except Exception as parse_err:
                    sanitized_parse = self.settings.sanitize_error(str(parse_err))
                    logger.warning(f"Malformed AI provider response: {sanitized_parse}")
                    return AgentStepResult(
                        content="AI provider returned a malformed response.",
                        finish_reason="error",
                        error=f"Malformed provider response: {sanitized_parse}",
                        error_type="malformed_response",
                    )

                raw_tool_calls = message.get("tool_calls") or []
                if not isinstance(raw_tool_calls, list):
                    return AgentStepResult(
                        content="AI provider returned invalid tool_calls structure.",
                        finish_reason="error",
                        error="Malformed provider response: tool_calls must be a list",
                        error_type="malformed_response",
                    )

                parsed_tool_calls = []
                for tc in raw_tool_calls:
                    if not isinstance(tc, dict):
                        return AgentStepResult(
                            content="AI provider returned invalid tool call element.",
                            finish_reason="error",
                            error="Malformed provider response: tool_call item must be a dictionary",
                            error_type="malformed_response",
                        )
                    fn = tc.get("function")
                    if not isinstance(fn, dict):
                        return AgentStepResult(
                            content="AI provider returned tool call missing 'function' object.",
                            finish_reason="error",
                            error="Malformed provider response: tool_call missing 'function'",
                            error_type="malformed_response",
                        )
                    call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                    name = str(fn.get("name") or "")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        if not isinstance(args_dict, dict):
                            args_dict = {}
                    except Exception:
                        args_dict = {}
                    parsed_tool_calls.append(
                        ToolCall(id=call_id, name=name, arguments=args_dict)
                    )

                finish_reason = str(choice.get("finish_reason") or ("tool_calls" if parsed_tool_calls else "stop"))
                return AgentStepResult(
                    thought=message.get("refusal") or None,
                    tool_calls=parsed_tool_calls,
                    content=message.get("content"),
                    finish_reason=finish_reason,
                )

        except httpx.TimeoutException as exc:
            logger.warning(f"Live provider request timed out: {exc}")
            return AgentStepResult(
                content=f"AI provider request timed out after {self._timeout}s.",
                finish_reason="error",
                error=f"Request timeout: exceeded {self._timeout}s",
                error_type="timeout",
            )
        except httpx.ConnectError as exc:
            sanitized_exc = self.settings.sanitize_error(str(exc))
            logger.warning(f"Live provider connection failed: {sanitized_exc}")
            return AgentStepResult(
                content="Could not connect to AI reasoning provider.",
                finish_reason="error",
                error=f"Connection failure: {sanitized_exc}",
                error_type="connection_error",
            )
        except Exception as exc:
            sanitized_exc = self.settings.sanitize_error(str(exc))
            logger.error(f"Live provider request failed: {sanitized_exc}")
            return AgentStepResult(
                content=f"AI provider request failed: {sanitized_exc}",
                finish_reason="error",
                error=f"Unexpected provider error: {sanitized_exc}",
                error_type="unexpected_error",
            )
