"""
Finding AI Diagnosis Streaming REST API Router.

Provides HTTP SSE endpoint for single-turn AI diagnosis of static analysis findings.

Endpoints:
- POST /api/v1/diagnose/stream
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from core.agents.schemas import format_sse_event
from core.auth.dependencies import get_optional_current_user
from core.config import get_settings
from core.database.models import User
from core.diagnosis_service import DiagnosisService
from core.redis.rate_limiter import RateLimit, RateLimitResult
from core.schemas import DiagnoseFindingRequest, DiagnosisExecutionResult, ErrorResponse

logger = logging.getLogger("edgemind.routes.diagnose")

router = APIRouter(prefix="/diagnose", tags=["Diagnosis"])
settings = get_settings()

diagnose_rate_limiter = RateLimit(
    limit=settings.rate_limit_agent_limit,
    window_seconds=settings.rate_limit_agent_window,
    resource_name="diagnose_stream",
)


def get_diagnosis_service() -> DiagnosisService:
    """Dependency provider for DiagnosisService, overridable in tests."""
    return DiagnosisService()


def _get_utc_timestamp() -> str:
    """Return ISO 8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream AI diagnosis for a static analysis finding",
    responses={
        200: {
            "description": "Server-Sent Events (SSE) stream of finding diagnosis chunks",
            "content": {"text/event-stream": {}},
        },
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        422: {"model": ErrorResponse, "description": "Unprocessable entity schema error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def diagnose_stream_endpoint(
    request: Request,
    response: Response,
    body: DiagnoseFindingRequest,
    service: DiagnosisService = Depends(get_diagnosis_service),
    rate_limit: RateLimitResult = Depends(diagnose_rate_limiter),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> StreamingResponse:
    """
    Execute single-turn AI diagnosis streaming real-time Server-Sent Events (SSE).

    Emits 4 structured event types:
    1. diagnosis_started: Finding metadata and session identifiers
    2. response_chunk: Incremental Markdown tokens with secret redaction
    3. completed: Completion metrics (duration, finish reason, status)
    4. error: Provider unavailable, stream timeout, or unexpected error notice

    Guarantees:
    - Sequential integer event IDs (id: 1, id: 2, ...)
    - Immediate token streaming without full buffering
    - Clean UTF-8 encoding and double-newline SSE wire framing
    - Client disconnect detection and generator cleanup
    - Bounded streaming duration with safe timeout events
    - Zero exposure of internal stack traces or secrets
    """
    session_id = f"diag_{uuid.uuid4().hex[:12]}"
    finding_id = body.finding.finding_id

    async def sse_event_generator() -> AsyncIterator[str]:
        event_id = 0
        stream_gen: Optional[AsyncIterator[str]] = None
        stream_start_time = time.perf_counter()

        test_timeout = request.headers.get("x-test-stream-timeout")
        max_stream_duration = (
            float(test_timeout)
            if test_timeout
            else min(float(settings.ollama_timeout), 60.0)
        )

        try:
            # 1. Emit diagnosis_started event
            event_id += 1
            start_payload = {
                "session_id": session_id,
                "finding_id": finding_id,
                "finding_type": body.finding.type,
                "line": body.finding.line,
                "sequence_id": event_id,
                "timestamp": _get_utc_timestamp(),
            }
            yield format_sse_event(
                event_type="diagnosis_started",
                data=start_payload,
                event_id=event_id,
            )

            # 2. Check provider availability upfront
            if hasattr(service, "is_available") and not service.is_available():
                event_id += 1
                unavail_payload = {
                    "session_id": session_id,
                    "finding_id": finding_id,
                    "error_type": "provider_unavailable",
                    "message": "AI diagnosis is currently unavailable. No AI reasoning provider or API key is configured.",
                    "retryable": False,
                    "sequence_id": event_id,
                    "timestamp": _get_utc_timestamp(),
                }
                yield format_sse_event(
                    event_type="error",
                    data=unavail_payload,
                    event_id=event_id,
                )
                return

            # 3. Stream diagnosis chunks
            stream_gen = service.stream_diagnose(body)
            has_error = False

            async for chunk in stream_gen:
                # Disconnect check
                if await request.is_disconnected():
                    logger.info("Client disconnected from diagnosis stream [Session: %s]", session_id)
                    return

                # Duration / timeout check
                if time.perf_counter() - stream_start_time > max_stream_duration:
                    event_id += 1
                    timeout_payload = {
                        "session_id": session_id,
                        "finding_id": finding_id,
                        "error_type": "stream_timeout",
                        "message": "Maximum diagnosis streaming duration exceeded.",
                        "retryable": True,
                        "sequence_id": event_id,
                        "timestamp": _get_utc_timestamp(),
                    }
                    yield format_sse_event(
                        event_type="error",
                        data=timeout_payload,
                        event_id=event_id,
                    )
                    has_error = True
                    break

                # Check if chunk contains a provider error notice
                if "**Diagnosis Error:**" in chunk or "**Diagnosis Streaming Error:**" in chunk:
                    event_id += 1
                    error_payload = {
                        "session_id": session_id,
                        "finding_id": finding_id,
                        "error_type": "upstream_provider_failure",
                        "message": chunk.strip(),
                        "retryable": True,
                        "sequence_id": event_id,
                        "timestamp": _get_utc_timestamp(),
                    }
                    yield format_sse_event(
                        event_type="error",
                        data=error_payload,
                        event_id=event_id,
                    )
                    has_error = True
                    break

                # Normal token chunk
                event_id += 1
                chunk_payload = {
                    "session_id": session_id,
                    "finding_id": finding_id,
                    "chunk": chunk,
                    "sequence_id": event_id,
                    "timestamp": _get_utc_timestamp(),
                }
                yield format_sse_event(
                    event_type="response_chunk",
                    data=chunk_payload,
                    event_id=event_id,
                )
                await asyncio.sleep(0)

            # 4. Emit completed event ONLY if no error and no disconnect occurred
            if not has_error and not await request.is_disconnected():
                elapsed_ms = (time.perf_counter() - stream_start_time) * 1000.0
                event_id += 1
                completed_payload = {
                    "session_id": session_id,
                    "finding_id": finding_id,
                    "status": "completed",
                    "duration_ms": round(elapsed_ms, 2),
                    "token_usage": None,
                    "finish_reason": "stop",
                    "sequence_id": event_id,
                    "timestamp": _get_utc_timestamp(),
                }
                yield format_sse_event(
                    event_type="completed",
                    data=completed_payload,
                    event_id=event_id,
                )

        except asyncio.CancelledError:
            logger.info("Diagnosis streaming task cancelled by client [Session: %s]", session_id)
            raise
        except Exception as exc:
            logger.error("Unexpected error in diagnosis streaming [Session: %s]: %s", session_id, exc, exc_info=True)
            event_id += 1
            sanitized_err = settings.sanitize_error(str(exc))
            error_payload = {
                "session_id": session_id,
                "finding_id": finding_id,
                "error_type": "internal_error",
                "message": f"An unexpected error occurred during diagnosis: {sanitized_err}",
                "retryable": False,
                "sequence_id": event_id,
                "timestamp": _get_utc_timestamp(),
            }
            yield format_sse_event(
                event_type="error",
                data=error_payload,
                event_id=event_id,
            )
        finally:
            if stream_gen is not None:
                try:
                    await stream_gen.aclose()
                except Exception:
                    pass

    stream_headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",
    }
    stream_headers.update(rate_limit.headers)

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers=stream_headers,
    )


@router.post(
    "/structured",
    response_model=DiagnosisExecutionResult,
    status_code=status.HTTP_200_OK,
    summary="Execute schema-validated structured AI diagnosis for a static analysis finding",
    responses={
        200: {"model": DiagnosisExecutionResult, "description": "Validated structured diagnosis or safe fallback"},
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        422: {"model": ErrorResponse, "description": "Unprocessable entity schema error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def diagnose_structured_endpoint(
    body: DiagnoseFindingRequest,
    service: DiagnosisService = Depends(get_diagnosis_service),
    rate_limit: RateLimitResult = Depends(diagnose_rate_limiter),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> DiagnosisExecutionResult:
    """
    Execute non-streaming finding diagnosis enforcing strict Pydantic structured output
    validation with deterministic fallback and user-facing Markdown compatibility.
    """
    try:
        return await service.diagnose_structured(body)
    except HTTPException:
        raise
    except Exception as exc:
        sanitized_err = settings.sanitize_error(str(exc))
        logger.error("Unexpected error in structured diagnosis: %s", sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during structured diagnosis.",
        )
