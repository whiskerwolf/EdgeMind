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
    ):
        self.settings = get_settings()
        self._api_key = api_key or self.settings.get_ai_api_key()
        self._model = model or "gpt-4o-mini"
        self._base_url = base_url or "https://api.openai.com/v1"
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "live_llm"

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        if not self._api_key:
            logger.info("LiveAgentProvider: No API key configured. Returning graceful fallback step.")
            return AgentStepResult(
                content=(
                    "External AI reasoning provider key is not configured. "
                    "EdgeMind completed static intelligence and edge-case synthesis using deterministic pipelines."
                ),
                tool_calls=[],
                finish_reason="stop",
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
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 200:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider HTTP error {response.status_code}: {sanitized_err}")
                    return AgentStepResult(
                        content=f"AI provider returned HTTP error {response.status_code}.",
                        finish_reason="error",
                    )

                data = response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                raw_tool_calls = message.get("tool_calls") or []

                parsed_tool_calls = []
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args_dict = {}
                    parsed_tool_calls.append(
                        ToolCall(id=call_id, name=name, arguments=args_dict)
                    )

                return AgentStepResult(
                    thought=message.get("refusal") or None,
                    tool_calls=parsed_tool_calls,
                    content=message.get("content"),
                    finish_reason=choice.get("finish_reason", "stop"),
                )

        except Exception as exc:
            sanitized_exc = self.settings.sanitize_error(str(exc))
            logger.error(f"Live provider request failed: {sanitized_exc}")
            return AgentStepResult(
                content=f"AI provider request failed: {sanitized_exc}",
                finish_reason="error",
            )
