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
import asyncio
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

import httpx

from core.agents.schemas import AgentStepResult, ToolCall
from core.config import get_settings
from core.cost import (
    TokenUsage,
    UsageSource,
    default_cost_calculator,
    estimate_local_tokens_from_text,
)

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

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ):
        """
        Stream reasoning chunks.
        Yields `str` for incremental content chunks,
        and finally yields `AgentStepResult` as the complete step result.
        """
        res = await self.chat_completion(messages, tools, temperature)
        if res.content:
            yield res.content
        yield res


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

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ):
        """Deterministic streaming for automated testing."""
        self.call_history.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        })

        if not self._steps:
            res = AgentStepResult(
                content=self._default_final_answer,
                tool_calls=[],
                finish_reason="stop",
            )
            yield res.content
            yield res
            return

        next_step = self._steps.pop(0)
        if callable(next_step):
            res = next_step(messages, tools)
            if hasattr(res, "__await__"):
                res = await res
        else:
            res = next_step

        if res.chunks:
            for chunk in res.chunks:
                yield chunk
        elif res.content:
            yield res.content

        yield res


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
        if api_key is not None:
            self._api_key = api_key
        else:
            self._api_key = (
                os.environ.get("OPENAI_API_KEY")
                or os.environ.get("EDGEMIND_AI_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or (self.settings.openai_api_key if "OPENAI_API_KEY" in os.environ else None)
                or (self.settings.edgemind_ai_key if "EDGEMIND_AI_KEY" in os.environ else None)
                or (self.settings.gemini_api_key if "GEMINI_API_KEY" in os.environ else None)
            )
        self._model = model or getattr(self.settings, "openai_model", "gpt-4o-mini")
        self._base_url = base_url or getattr(self.settings, "openai_base_url", "https://api.openai.com/v1")
        self._timeout = timeout
        self._transport = transport

    @property
    def model(self) -> str:
        """Active model identifier."""
        return self._model

    @property
    def name(self) -> str:
        return "live_llm"

    def is_available(self) -> bool:
        """Return True if an API key is configured for live AI reasoning."""
        return bool(self._api_key and str(self._api_key).strip())

    def _sanitize(self, text: str) -> str:
        """Sanitize message, masking both settings secrets and instance API key."""
        if not text:
            return ""
        from core.sanitization import redact_secrets
        custom = [self._api_key] if self._api_key else []
        return self.settings.sanitize_error(redact_secrets(text, custom_secrets=custom))

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

                if response.status_code == 400:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider invalid request (HTTP 400): {sanitized_err}")
                    return AgentStepResult(
                        content="AI provider rejected request (HTTP 400): Invalid request format or parameters.",
                        finish_reason="error",
                        error=f"Invalid request: HTTP 400 {sanitized_err}",
                        error_type="invalid_request",
                        status_code=400,
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

                if response.status_code == 403:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    logger.warning(f"Live provider permission denied (HTTP 403): {sanitized_err}")
                    return AgentStepResult(
                        content="AI provider permission denied (HTTP 403): Access denied or region restricted.",
                        finish_reason="error",
                        error="Permission failure: HTTP 403 Forbidden",
                        error_type="permission_error",
                        status_code=403,
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

                raw_usage = data.get("usage")
                resp_req_id = data.get("id") or response.headers.get("x-request-id")
                resp_model = data.get("model") or self._model
                step_usage: Optional[TokenUsage] = None

                if isinstance(raw_usage, dict) and "prompt_tokens" in raw_usage:
                    cost_breakdown = default_cost_calculator.calculate_cost(
                        prompt_tokens=raw_usage.get("prompt_tokens"),
                        completion_tokens=raw_usage.get("completion_tokens"),
                        model=resp_model,
                    )
                    step_usage = TokenUsage(
                        prompt_tokens=raw_usage.get("prompt_tokens"),
                        completion_tokens=raw_usage.get("completion_tokens"),
                        total_tokens=raw_usage.get("total_tokens"),
                        model=resp_model,
                        provider="openai",
                        request_id=resp_req_id,
                        usage_source=UsageSource.ACTUAL_PROVIDER,
                        estimated_cost_usd=cost_breakdown.total_cost if cost_breakdown.is_pricing_known else None,
                        pricing_version=cost_breakdown.pricing_version if cost_breakdown.is_pricing_known else None,
                        is_estimated_cost_known=cost_breakdown.is_pricing_known,
                    )
                elif self.settings.agent_enable_local_token_estimates:
                    est_prompt = estimate_local_tokens_from_text(json.dumps(messages))
                    est_completion = estimate_local_tokens_from_text(message.get("content") or "")
                    est_total = est_prompt + est_completion
                    cost_breakdown = default_cost_calculator.calculate_cost(
                        prompt_tokens=est_prompt,
                        completion_tokens=est_completion,
                        model=resp_model,
                    )
                    step_usage = TokenUsage(
                        prompt_tokens=est_prompt,
                        completion_tokens=est_completion,
                        total_tokens=est_total,
                        model=resp_model,
                        provider="openai",
                        request_id=resp_req_id,
                        usage_source=UsageSource.LOCAL_ESTIMATE,
                        estimated_cost_usd=cost_breakdown.total_cost if cost_breakdown.is_pricing_known else None,
                        pricing_version=cost_breakdown.pricing_version if cost_breakdown.is_pricing_known else None,
                        is_estimated_cost_known=cost_breakdown.is_pricing_known,
                    )
                else:
                    step_usage = TokenUsage(
                        prompt_tokens=None,
                        completion_tokens=None,
                        total_tokens=None,
                        model=resp_model,
                        provider="openai",
                        request_id=resp_req_id,
                        usage_source=UsageSource.UNAVAILABLE,
                        estimated_cost_usd=None,
                        is_estimated_cost_known=False,
                    )

                finish_reason = str(choice.get("finish_reason") or ("tool_calls" if parsed_tool_calls else "stop"))
                return AgentStepResult(
                    thought=message.get("refusal") or None,
                    tool_calls=parsed_tool_calls,
                    content=message.get("content"),
                    finish_reason=finish_reason,
                    usage=step_usage,
                    request_id=resp_req_id,
                    model=resp_model,
                )

        except httpx.TimeoutException as exc:
            sanitized_exc = self._sanitize(str(exc))
            logger.warning(f"Live provider request timed out: {sanitized_exc}")
            return AgentStepResult(
                content=f"AI provider request timed out after {self._timeout}s.",
                finish_reason="error",
                error=f"Request timeout: exceeded {self._timeout}s",
                error_type="timeout",
            )
        except httpx.ConnectError as exc:
            sanitized_exc = self._sanitize(str(exc))
            logger.warning(f"Live provider connection failed: {sanitized_exc}")
            return AgentStepResult(
                content="Could not connect to AI reasoning provider.",
                finish_reason="error",
                error=f"Connection failure: {sanitized_exc}",
                error_type="connection_error",
            )
        except Exception as exc:
            sanitized_exc = self._sanitize(str(exc))
            logger.error(f"Live provider request failed: {sanitized_exc}")
            return AgentStepResult(
                content=f"AI provider request failed: {sanitized_exc}",
                finish_reason="error",
                error=f"Unexpected provider error: {sanitized_exc}",
                error_type="unexpected_error",
            )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ):
        """
        Live streaming chat completion via OpenAI-compatible SSE streaming.
        Yields text chunks as they arrive from the live provider,
        and finally yields the complete AgentStepResult.
        """
        if not self._api_key or not str(self._api_key).strip():
            logger.info("LiveAgentProvider: No API key configured. Returning unavailable status.")
            yield AgentStepResult(
                content="AI provider API key is not configured. AI reasoning was not performed.",
                tool_calls=[],
                finish_reason="unavailable",
                error="AI provider API key is not configured.",
                error_type="provider_unavailable",
            )
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code == 400:
                        yield AgentStepResult(
                            content="AI provider rejected request (HTTP 400): Invalid request format or parameters.",
                            finish_reason="error",
                            error="Invalid request: HTTP 400 Bad Request",
                            error_type="invalid_request",
                            status_code=400,
                        )
                        return

                    if response.status_code == 401:
                        sanitized_err = self.settings.sanitize_error(await response.aread().decode("utf-8", "replace")) if hasattr(response, "aread") else "HTTP 401"
                        yield AgentStepResult(
                            content="AI provider authentication failed (HTTP 401): Invalid or unauthorized API key.",
                            finish_reason="error",
                            error="Authentication failure: HTTP 401 Unauthorized",
                            error_type="authentication_error",
                            status_code=401,
                        )
                        return

                    if response.status_code == 403:
                        yield AgentStepResult(
                            content="AI provider permission denied (HTTP 403): Access denied or region restricted.",
                            finish_reason="error",
                            error="Permission failure: HTTP 403 Forbidden",
                            error_type="permission_error",
                            status_code=403,
                        )
                        return

                    if response.status_code == 429:
                        yield AgentStepResult(
                            content="AI provider rate limit exceeded (HTTP 429).",
                            finish_reason="error",
                            error="Rate limit exceeded: HTTP 429 Too Many Requests",
                            error_type="rate_limit",
                            status_code=429,
                        )
                        return

                    if response.status_code >= 500:
                        yield AgentStepResult(
                            content=f"AI provider server error (HTTP {response.status_code}).",
                            finish_reason="error",
                            error=f"Server error: HTTP {response.status_code}",
                            error_type="server_error",
                            status_code=response.status_code,
                        )
                        return

                    if response.status_code != 200:
                        yield AgentStepResult(
                            content=f"AI provider returned HTTP error {response.status_code}.",
                            finish_reason="error",
                            error=f"HTTP error: {response.status_code}",
                            error_type="http_error",
                            status_code=response.status_code,
                        )
                        return

                    accumulated_content: List[str] = []
                    accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}
                    accumulated_usage: Optional[Dict[str, Any]] = None
                    accumulated_request_id: Optional[str] = response.headers.get("x-request-id")
                    accumulated_model: str = self._model
                    finish_reason = "stop"
                    stream_interrupted = False

                    try:
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line == "data: [DONE]":
                                break
                            if line.startswith("data: "):
                                raw_data = line[6:].strip()
                                try:
                                    chunk_json = json.loads(raw_data)
                                    if chunk_json.get("id"):
                                        accumulated_request_id = chunk_json.get("id")
                                    if chunk_json.get("model"):
                                        accumulated_model = chunk_json.get("model")
                                    chunk_usage = chunk_json.get("usage")
                                    if isinstance(chunk_usage, dict) and "prompt_tokens" in chunk_usage:
                                        accumulated_usage = chunk_usage

                                    choices = chunk_json.get("choices") or []
                                    if choices:
                                        delta = choices[0].get("delta") or {}
                                        f_reason = choices[0].get("finish_reason")
                                        if f_reason:
                                            finish_reason = f_reason
                                        content_chunk = delta.get("content")
                                        if content_chunk:
                                            accumulated_content.append(content_chunk)
                                            yield content_chunk
                                        tc_deltas = delta.get("tool_calls") or []
                                        for tc_delta in tc_deltas:
                                            idx = tc_delta.get("index", 0)
                                            if idx not in accumulated_tool_calls:
                                                accumulated_tool_calls[idx] = {
                                                    "id": tc_delta.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                                    "name": tc_delta.get("function", {}).get("name", ""),
                                                    "arguments": "",
                                                }
                                            fn_delta = tc_delta.get("function") or {}
                                            if fn_delta.get("name"):
                                                accumulated_tool_calls[idx]["name"] = fn_delta["name"]
                                            if fn_delta.get("arguments"):
                                                accumulated_tool_calls[idx]["arguments"] += fn_delta["arguments"]
                                except Exception:
                                    continue
                    except (httpx.RequestError, httpx.HTTPError, asyncio.CancelledError) as stream_err:
                        stream_interrupted = True
                        logger.warning(f"Live provider stream interrupted: {self.settings.sanitize_error(str(stream_err))}")

                    parsed_tcs = []
                    for idx in sorted(accumulated_tool_calls.keys()):
                        tc_data = accumulated_tool_calls[idx]
                        raw_args = tc_data["arguments"]
                        try:
                            parsed_args = json.loads(raw_args) if raw_args else {}
                        except Exception:
                            parsed_args = {}
                        parsed_tcs.append(ToolCall(
                            id=tc_data["id"],
                            name=tc_data["name"],
                            arguments=parsed_args,
                        ))

                    if parsed_tcs:
                        finish_reason = "tool_calls"

                    if stream_interrupted:
                        finish_reason = "interrupted"

                    stream_usage: Optional[TokenUsage] = None
                    if not stream_interrupted and accumulated_usage and "prompt_tokens" in accumulated_usage:
                        cost_breakdown = default_cost_calculator.calculate_cost(
                            prompt_tokens=accumulated_usage.get("prompt_tokens"),
                            completion_tokens=accumulated_usage.get("completion_tokens"),
                            model=accumulated_model,
                        )
                        stream_usage = TokenUsage(
                            prompt_tokens=accumulated_usage.get("prompt_tokens"),
                            completion_tokens=accumulated_usage.get("completion_tokens"),
                            total_tokens=accumulated_usage.get("total_tokens"),
                            model=accumulated_model,
                            provider="openai",
                            request_id=accumulated_request_id,
                            usage_source=UsageSource.ACTUAL_PROVIDER,
                            estimated_cost_usd=cost_breakdown.total_cost if cost_breakdown.is_pricing_known else None,
                            pricing_version=cost_breakdown.pricing_version if cost_breakdown.is_pricing_known else None,
                            is_estimated_cost_known=cost_breakdown.is_pricing_known,
                        )
                    elif not stream_interrupted and self.settings.agent_enable_local_token_estimates:
                        est_prompt = estimate_local_tokens_from_text(json.dumps(messages))
                        est_completion = estimate_local_tokens_from_text("".join(accumulated_content))
                        est_total = est_prompt + est_completion
                        cost_breakdown = default_cost_calculator.calculate_cost(
                            prompt_tokens=est_prompt,
                            completion_tokens=est_completion,
                            model=accumulated_model,
                        )
                        stream_usage = TokenUsage(
                            prompt_tokens=est_prompt,
                            completion_tokens=est_completion,
                            total_tokens=est_total,
                            model=accumulated_model,
                            provider="openai",
                            request_id=accumulated_request_id,
                            usage_source=UsageSource.LOCAL_ESTIMATE,
                            estimated_cost_usd=cost_breakdown.total_cost if cost_breakdown.is_pricing_known else None,
                            pricing_version=cost_breakdown.pricing_version if cost_breakdown.is_pricing_known else None,
                            is_estimated_cost_known=cost_breakdown.is_pricing_known,
                        )
                    else:
                        stream_usage = TokenUsage(
                            prompt_tokens=None,
                            completion_tokens=None,
                            total_tokens=None,
                            model=accumulated_model,
                            provider="openai",
                            request_id=accumulated_request_id,
                            usage_source=UsageSource.UNAVAILABLE,
                            estimated_cost_usd=None,
                            is_estimated_cost_known=False,
                        )

                    final_content = "".join(accumulated_content) if accumulated_content else None
                    yield AgentStepResult(
                        content=final_content,
                        tool_calls=parsed_tcs,
                        finish_reason=finish_reason,
                        error="Streaming connection interrupted before completion." if stream_interrupted else None,
                        error_type="interrupted_stream" if stream_interrupted else None,
                        usage=stream_usage,
                        request_id=accumulated_request_id,
                        model=accumulated_model,
                    )

        except httpx.TimeoutException as exc:
            yield AgentStepResult(
                content=f"AI provider request timed out after {self._timeout}s.",
                finish_reason="error",
                error=f"Request timeout: exceeded {self._timeout}s",
                error_type="timeout",
            )
        except httpx.ConnectError as exc:
            sanitized_exc = self.settings.sanitize_error(str(exc))
            yield AgentStepResult(
                content="Could not connect to AI reasoning provider.",
                finish_reason="error",
                error=f"Connection failure: {sanitized_exc}",
                error_type="connection_error",
            )
        except Exception as exc:
            sanitized_exc = self.settings.sanitize_error(str(exc))
            yield AgentStepResult(
                content=f"AI provider request failed: {sanitized_exc}",
                finish_reason="error",
                error=f"Unexpected provider error: {sanitized_exc}",
                error_type="unexpected_error",
            )


class ThinkTagFilter:
    """
    Incremental filter to strip <think>...</think> blocks across stream chunks.
    Ensures that internal reasoning tokens are never leaked to user-facing streams
    even when tags span across arbitrary chunk boundaries.
    """

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def filter(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.buffer += chunk
        output = []

        while self.buffer:
            if not self.in_think:
                start = self.buffer.find("<think>")
                if start != -1:
                    if start > 0:
                        output.append(self.buffer[:start])
                    self.buffer = self.buffer[start + len("<think>"):]
                    self.in_think = True
                else:
                    # Check for partial prefix e.g. "<", "<th", "<think"
                    potential_prefix = False
                    for i in range(1, len("<think>")):
                        if self.buffer.endswith("<think>"[:i]):
                            emit_len = len(self.buffer) - i
                            if emit_len > 0:
                                output.append(self.buffer[:emit_len])
                                self.buffer = self.buffer[emit_len:]
                            potential_prefix = True
                            break
                    if not potential_prefix:
                        output.append(self.buffer)
                        self.buffer = ""
                    else:
                        break
            else:
                end = self.buffer.find("</think>")
                if end != -1:
                    self.buffer = self.buffer[end + len("</think>"):]
                    self.in_think = False
                else:
                    # Inside thinking; check if buffer ends with a partial prefix of "</think>"
                    potential_prefix = False
                    for i in range(1, len("</think>")):
                        if self.buffer.endswith("</think>"[:i]):
                            self.buffer = self.buffer[-i:]
                            potential_prefix = True
                            break
                    if not potential_prefix:
                        self.buffer = ""
                    break

        return "".join(output)

    def flush(self) -> str:
        """Flush any remaining buffered text when stream closes."""
        if not self.in_think and self.buffer:
            out = self.buffer
            self.buffer = ""
            return out
        self.buffer = ""
        return ""


class OllamaAgentProvider(BaseAgentProvider):
    """
    Local AI provider using Ollama's native /api/chat endpoint.
    Supports local models such as qwen3:4b with native tool/function calling,
    Server-Sent Events (SSE) streaming, local token accounting (LOCAL_INFERENCE),
    robust error sanitization, internal thinking suppression, and zero external network calls.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.settings = get_settings()
        self._model = model or getattr(self.settings, "ollama_model", "qwen3:4b")
        raw_url = base_url or getattr(self.settings, "ollama_base_url", "http://127.0.0.1:11434")
        self._base_url = raw_url.rstrip("/")
        self._timeout = timeout or getattr(self.settings, "ollama_timeout", 60.0)
        self._transport = transport

    @property
    def model(self) -> str:
        """Active model identifier."""
        return self._model

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Local Ollama does not require an API key; availability depends on local connectivity."""
        return True

    def _sanitize(self, text: str) -> str:
        """Sanitize message, masking secrets and server diagnostics."""
        if not text:
            return ""
        return self.settings.sanitize_error(text)

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format messages for Ollama's native /api/chat format.
        Ensures function.arguments in assistant tool_calls is a dictionary (not JSON string),
        and tool responses conform to native role='tool' specifications.
        """
        formatted = []
        for msg in messages:
            m = dict(msg)
            # Normalize assistant tool_calls arguments from string to dict if needed
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tcs = []
                for tc in m["tool_calls"]:
                    tc_copy = dict(tc)
                    fn = tc_copy.get("function")
                    if isinstance(fn, dict):
                        fn_copy = dict(fn)
                        raw_args = fn_copy.get("arguments")
                        if isinstance(raw_args, str):
                            try:
                                fn_copy["arguments"] = json.loads(raw_args)
                            except Exception:
                                fn_copy["arguments"] = {}
                        tc_copy["function"] = fn_copy
                    tcs.append(tc_copy)
                m["tool_calls"] = tcs

            formatted.append(m)
        return formatted

    def _clean_content(self, raw_content: Optional[str]) -> Optional[str]:
        """Strip <think>...</think> tags and trim whitespace from content."""
        if not raw_content:
            return None
        cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        return cleaned if cleaned else None

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        """Execute a non-streaming chat completion request against Ollama /api/chat."""
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        endpoint = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(endpoint, json=payload)

                if response.status_code == 404:
                    sanitized_err = self._sanitize(response.text)
                    logger.warning(f"Ollama model '{self._model}' not found (HTTP 404): {sanitized_err}")
                    return AgentStepResult(
                        content=f"Ollama model '{self._model}' was not found. Please verify `ollama pull {self._model}`.",
                        finish_reason="error",
                        error=f"Model not found: {sanitized_err}",
                        error_type="model_not_found",
                        status_code=404,
                    )

                if response.status_code == 400:
                    sanitized_err = self._sanitize(response.text)
                    logger.warning(f"Ollama invalid request (HTTP 400): {sanitized_err}")
                    return AgentStepResult(
                        content="Ollama rejected request (HTTP 400): Invalid request format or parameters.",
                        finish_reason="error",
                        error=f"Invalid request: HTTP 400 {sanitized_err}",
                        error_type="invalid_request",
                        status_code=400,
                    )

                if response.status_code != 200:
                    sanitized_err = self._sanitize(response.text)
                    logger.warning(f"Ollama server error (HTTP {response.status_code}): {sanitized_err}")
                    return AgentStepResult(
                        content=f"Ollama inference error (HTTP {response.status_code}).",
                        finish_reason="error",
                        error=f"Server error: HTTP {response.status_code} {sanitized_err}",
                        error_type="server_error",
                        status_code=response.status_code,
                    )

                data = response.json()

        except httpx.ConnectError as exc:
            sanitized_err = self._sanitize(str(exc))
            logger.warning(f"Ollama connection refused at {self._base_url}: {sanitized_err}")
            return AgentStepResult(
                content=f"Could not connect to local Ollama server at {self._base_url}. Ensure Ollama is running.",
                finish_reason="error",
                error=f"Ollama connection refused at {self._base_url}: {sanitized_err}",
                error_type="ollama_unavailable",
                status_code=503,
            )
        except httpx.TimeoutException as exc:
            logger.warning(f"Ollama request timed out after {self._timeout}s: {exc}")
            return AgentStepResult(
                content=f"Local Ollama inference request timed out after {self._timeout}s.",
                finish_reason="error",
                error=f"Request timeout: exceeded {self._timeout}s",
                error_type="timeout",
                status_code=504,
            )
        except Exception as exc:
            sanitized_err = self._sanitize(str(exc))
            logger.error(f"Ollama request failed: {sanitized_err}")
            return AgentStepResult(
                content=f"Local Ollama request failed: {sanitized_err}",
                finish_reason="error",
                error=f"Request failure: {sanitized_err}",
                error_type="provider_error",
                status_code=500,
            )

        # Parse Ollama response message
        msg = data.get("message", {})
        raw_content = msg.get("content")
        clean_content = self._clean_content(raw_content)

        # Tool calls parsing
        raw_tcs = msg.get("tool_calls") or []
        parsed_tcs: List[ToolCall] = []
        for tc in raw_tcs:
            fn = tc.get("function") or {}
            call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    pass
            parsed_tcs.append(ToolCall(id=call_id, name=name, arguments=args))

        # Local Token Accounting
        prompt_eval_count = data.get("prompt_eval_count")
        eval_count = data.get("eval_count")
        model_name = data.get("model") or self._model
        req_id = f"ollama_{uuid.uuid4().hex[:12]}"

        usage = None
        if prompt_eval_count is not None or eval_count is not None:
            p_tok = int(prompt_eval_count or 0)
            c_tok = int(eval_count or 0)
            usage = TokenUsage(
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=p_tok + c_tok,
                model=model_name,
                provider="ollama",
                request_id=req_id,
                usage_source=UsageSource.LOCAL_INFERENCE,
                estimated_cost_usd=None,
                pricing_version=None,
                is_estimated_cost_known=False,
            )

        finish_reason = "tool_calls" if parsed_tcs else "stop"

        return AgentStepResult(
            content=clean_content,
            thought=None,  # Strictly suppress internal reasoning chain
            tool_calls=parsed_tcs,
            finish_reason=finish_reason,
            usage=usage,
            request_id=req_id,
            model=model_name,
        )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ):
        """
        Stream reasoning chunks from Ollama /api/chat.
        Yields str for user-facing content chunks (suppressing internal thinking),
        and finally yields AgentStepResult containing complete execution metadata.
        """
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        endpoint = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                async with client.stream("POST", endpoint, json=payload) as response:
                    if response.status_code == 404:
                        raw_bytes = await response.aread()
                        sanitized_err = self._sanitize(raw_bytes.decode("utf-8", errors="replace"))
                        yield AgentStepResult(
                            content=f"Ollama model '{self._model}' was not found. Please verify `ollama pull {self._model}`.",
                            finish_reason="error",
                            error=f"Model not found: {sanitized_err}",
                            error_type="model_not_found",
                            status_code=404,
                        )
                        return

                    if response.status_code == 400:
                        raw_bytes = await response.aread()
                        sanitized_err = self._sanitize(raw_bytes.decode("utf-8", errors="replace"))
                        yield AgentStepResult(
                            content="Ollama rejected request (HTTP 400): Invalid request format or parameters.",
                            finish_reason="error",
                            error=f"Invalid request: HTTP 400 {sanitized_err}",
                            error_type="invalid_request",
                            status_code=400,
                        )
                        return

                    if response.status_code != 200:
                        raw_bytes = await response.aread()
                        sanitized_err = self._sanitize(raw_bytes.decode("utf-8", errors="replace"))
                        yield AgentStepResult(
                            content=f"Ollama inference error (HTTP {response.status_code}).",
                            finish_reason="error",
                            error=f"Server error: HTTP {response.status_code} {sanitized_err}",
                            error_type="server_error",
                            status_code=response.status_code,
                        )
                        return

                    accumulated_content: List[str] = []
                    accumulated_tool_calls: List[ToolCall] = []
                    prompt_eval_count = None
                    eval_count = None
                    model_name = self._model
                    stream_interrupted = False
                    think_filter = ThinkTagFilter()

                    try:
                        async for line in response.aiter_lines():
                            if not line or not line.strip():
                                continue

                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            model_name = chunk.get("model") or model_name
                            msg = chunk.get("message") or {}

                            # 1. Check for tool_calls in chunk
                            chunk_tcs = msg.get("tool_calls") or []
                            for tc in chunk_tcs:
                                fn = tc.get("function") or {}
                                call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                                name = fn.get("name", "")
                                args = fn.get("arguments", {})
                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except Exception:
                                        pass
                                accumulated_tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))

                            # 2. Content chunk: filter out <think> tags, and ignore msg["thinking"]
                            raw_chunk = msg.get("content")
                            if raw_chunk:
                                safe_chunk = think_filter.filter(raw_chunk)
                                if safe_chunk:
                                    accumulated_content.append(safe_chunk)
                                    yield safe_chunk

                            # 3. Terminal metrics
                            if chunk.get("done") is True:
                                prompt_eval_count = chunk.get("prompt_eval_count")
                                eval_count = chunk.get("eval_count")
                                break

                    except (httpx.RequestError, httpx.HTTPError, asyncio.CancelledError) as exc:
                        logger.warning(f"Ollama stream severed before completion: {exc}")
                        stream_interrupted = True

                    # Flush any pending safe text from the think filter
                    flushed = think_filter.flush()
                    if flushed:
                        accumulated_content.append(flushed)
                        yield flushed

                    req_id = f"ollama_{uuid.uuid4().hex[:12]}"
                    usage = None
                    if stream_interrupted:
                        usage = TokenUsage(
                            prompt_tokens=None,
                            completion_tokens=None,
                            total_tokens=None,
                            model=model_name,
                            provider="ollama",
                            request_id=req_id,
                            usage_source=UsageSource.UNAVAILABLE,
                            estimated_cost_usd=None,
                            pricing_version=None,
                            is_estimated_cost_known=False,
                        )
                    elif prompt_eval_count is not None or eval_count is not None:
                        p_tok = int(prompt_eval_count or 0)
                        c_tok = int(eval_count or 0)
                        usage = TokenUsage(
                            prompt_tokens=p_tok,
                            completion_tokens=c_tok,
                            total_tokens=p_tok + c_tok,
                            model=model_name,
                            provider="ollama",
                            request_id=req_id,
                            usage_source=UsageSource.LOCAL_INFERENCE,
                            estimated_cost_usd=None,
                            pricing_version=None,
                            is_estimated_cost_known=False,
                        )

                    finish_reason = "interrupted" if stream_interrupted else ("tool_calls" if accumulated_tool_calls else "stop")
                    final_content = "".join(accumulated_content).strip() if accumulated_content else None

                    yield AgentStepResult(
                        content=final_content,
                        thought=None,
                        tool_calls=accumulated_tool_calls,
                        finish_reason=finish_reason,
                        error="Streaming connection interrupted before completion." if stream_interrupted else None,
                        error_type="interrupted_stream" if stream_interrupted else None,
                        usage=usage,
                        request_id=req_id,
                        model=model_name,
                    )

        except httpx.TimeoutException as exc:
            yield AgentStepResult(
                content=f"Local Ollama request timed out after {self._timeout}s.",
                finish_reason="error",
                error=f"Request timeout: exceeded {self._timeout}s",
                error_type="timeout",
                status_code=504,
            )
        except httpx.ConnectError as exc:
            sanitized_exc = self._sanitize(str(exc))
            yield AgentStepResult(
                content=f"Could not connect to local Ollama server at {self._base_url}. Ensure Ollama is running.",
                finish_reason="error",
                error=f"Connection failure: {sanitized_exc}",
                error_type="ollama_unavailable",
                status_code=503,
            )
        except Exception as exc:
            sanitized_exc = self._sanitize(str(exc))
            yield AgentStepResult(
                content=f"Local Ollama request failed: {sanitized_exc}",
                finish_reason="error",
                error=f"Unexpected provider error: {sanitized_exc}",
                error_type="unexpected_error",
                status_code=500,
            )
