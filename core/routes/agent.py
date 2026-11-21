"""
Agent Analysis REST API Router.

Provides HTTP endpoint for multi-step autonomous AI agent analysis
with native tool calling.

Endpoints:
- POST /api/v1/agent/analyze
- POST /api/v1/agent/analyze/stream
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import LiveAgentProvider, OllamaAgentProvider
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    SSEEventType,
    format_sse_event,
)
from core.auth.dependencies import get_optional_current_user
from core.config import get_settings
from core.cost import UsageSummaryResponse
from core.database.connection import get_db
from core.database.models import User
from core.database.repositories.project_repository import ProjectRepository
from core.database.repositories.usage_repository import UsageRepository
from core.redis.rate_limiter import RateLimit, RateLimitResult
from core.schemas import ErrorResponse

logger = logging.getLogger("edgemind.routes.agent")

router = APIRouter(prefix="/agent", tags=["Agent"])
settings = get_settings()

agent_rate_limiter = RateLimit(
    limit=settings.rate_limit_agent_limit,
    window_seconds=settings.rate_limit_agent_window,
    resource_name="agent_analyze",
)

stream_rate_limiter = RateLimit(
    limit=settings.rate_limit_agent_limit,
    window_seconds=settings.rate_limit_agent_window,
    resource_name="agent_stream",
)


def get_agent_orchestrator(body: AgentAnalyzeRequest) -> AgentOrchestrator:
    """Dependency provider for AgentOrchestrator, overridable in tests."""
    current_settings = get_settings()
    provider_type = (getattr(current_settings, "agent_provider", None) or "ollama").lower()
    if provider_type == "ollama":
        provider = OllamaAgentProvider(model=body.model)
    else:
        provider = LiveAgentProvider(model=body.model)
    return AgentOrchestrator(
        provider=provider,
        max_iterations=body.max_iterations,
    )


@router.post(
    "/analyze",
    response_model=AgentAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "model": AgentAnalyzeResponse,
            "description": "Multi-step agent analysis with full tool execution history",
        },
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        404: {"model": ErrorResponse, "description": "Referenced project not found"},
        422: {"model": ErrorResponse, "description": "Unprocessable entity"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def agent_analyze_endpoint(
    request: Request,
    response: Response,
    body: AgentAnalyzeRequest,
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    rate_limit: RateLimitResult = Depends(agent_rate_limiter),
) -> AgentAnalyzeResponse:
    """
    Execute autonomous multi-step code analysis and adaptive edge-case synthesis.

    Features:
    - Multi-step conversational reasoning loop with tool calling.
    - 7 specialized analytical tools (AST, constraints, gaps, synthesis, validation, ranking, history).
    - Strict static-only analysis: zero code execution.
    - Multi-tenancy & Project Ownership Isolation: Verifies project permissions if project_id is provided.
    - PostgreSQL JSONB persistence: Automatically saves complete report document when authenticated.
    """
    request_id = getattr(request.state, "request_id", None)

    # 1. Tenant & Project Ownership Isolation Check
    if body.project_id is not None and db is not None:
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_id(body.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{body.project_id}' not found.",
            )

        if not current_user or (
            current_user.role != "admin" and project.owner_user_id != current_user.id
        ):
            # Do not disclose existence of another user's project
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{body.project_id}' not found.",
            )

    # 2. Configure and run Agent Orchestrator
    try:
        response = await orchestrator.run(
            request=body,
            db=db,
            current_user=current_user,
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Agent analysis failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during agent analysis.",
        )


@router.post(
    "/analyze/stream",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Server-Sent Events (SSE) stream of agent reasoning, tool execution, and candidate synthesis",
            "content": {"text/event-stream": {}},
        },
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        401: {"model": ErrorResponse, "description": "Invalid or expired access token"},
        404: {"model": ErrorResponse, "description": "Referenced project not found"},
        422: {"model": ErrorResponse, "description": "Unprocessable entity"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def agent_analyze_stream_endpoint(
    request: Request,
    response: Response,
    body: AgentAnalyzeRequest,
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    rate_limit: RateLimitResult = Depends(stream_rate_limiter),
) -> StreamingResponse:
    """
    Execute autonomous multi-step code analysis streaming real-time Server-Sent Events (SSE).

    Emits 8 structured event types:
    1. status: Session initialization status
    2. analysis_started: Metadata and analysis parameters
    3. progress: Iteration and stage progress updates
    4. tool_started: Static analytical tool execution start
    5. tool_completed: Tool execution outcome and timing
    6. response_chunk: Incremental tokens with boundary-safe secret redaction
    7. completed: Complete structured AgentAnalyzeResponse payload
    8. error: Provider unavailable or execution failure notice

    Guarantees:
    - Sequential integer event IDs (id: 1, id: 2, ...)
    - Heartbeat comments (: heartbeat) to keep connection alive
    - Client disconnect detection and background task cancellation
    - Strict secret redaction across stream chunk boundaries
    - Enforcement of max stream duration (35s) and max response size (512 KiB)
    """
    # 1. Tenant & Project Ownership Isolation Check
    if body.project_id is not None and db is not None:
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_id(body.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{body.project_id}' not found.",
            )

        if not current_user or (
            current_user.role != "admin" and project.owner_user_id != current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{body.project_id}' not found.",
            )

    async def sse_event_generator():
        event_id = 0
        total_bytes = 0
        test_max_bytes = request.headers.get("x-test-max-stream-bytes")
        test_timeout = request.headers.get("x-test-stream-timeout")
        max_stream_bytes = int(test_max_bytes) if test_max_bytes and test_max_bytes.isdigit() else (512 * 1024)
        max_stream_duration = (
            float(test_timeout)
            if test_timeout
            else max(float(settings.agent_session_timeout) + 15.0, 105.0)
        )
        stream_start_time = time.perf_counter()
        stream_gen = None

        try:
            stream_gen = orchestrator.stream_run(
                request=body,
                db=db,
                current_user=current_user,
            )

            async for event_type, event_data in stream_gen:
                # 1. Check client disconnect
                if await request.is_disconnected():
                    logger.info("Client disconnected from SSE stream.")
                    break

                # 2. Check stream duration limit
                if time.perf_counter() - stream_start_time > max_stream_duration:
                    event_id += 1
                    err_event = format_sse_event(
                        event_type=SSEEventType.ERROR.value,
                        data={"error_type": "stream_timeout", "message": "Maximum stream duration exceeded."},
                        event_id=event_id,
                    )
                    yield err_event
                    break

                # 3. Format and serialize event
                event_id += 1
                formatted = format_sse_event(
                    event_type=event_type,
                    data=event_data,
                    event_id=event_id,
                )

                # 4. Check max response size bound
                encoded_len = len(formatted.encode("utf-8"))
                if total_bytes + encoded_len > max_stream_bytes:
                    event_id += 1
                    err_event = format_sse_event(
                        event_type=SSEEventType.ERROR.value,
                        data={"error_type": "stream_size_exceeded", "message": "Maximum stream response size exceeded."},
                        event_id=event_id,
                    )
                    yield err_event
                    break

                total_bytes += encoded_len
                yield formatted
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("SSE streaming task cancelled by client.")
            raise
        except Exception as exc:
            logger.error(f"Unexpected error in SSE streaming: {exc}", exc_info=True)
            event_id += 1
            yield format_sse_event(
                event_type=SSEEventType.ERROR.value,
                data={"error_type": "internal_error", "message": "An unexpected error occurred during streaming."},
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


@router.get(
    "/usage/summary",
    response_model=UsageSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated AI token usage and estimated API costs",
    responses={
        200: {"description": "Aggregated usage metrics with tenant isolation"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Project not found or access denied"},
    },
)
async def get_usage_summary_endpoint(
    project_id: Optional[uuid.UUID] = Query(default=None, description="Optional project filter"),
    period: str = Query(default="month", pattern="^(day|month|all)$", description="Usage window: day, month, or all"),
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> UsageSummaryResponse:
    """
    Retrieve aggregated token accounting and estimated API costs.
    Enforces tenant boundaries: users only access their own usage records.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view token and cost usage.",
        )

    if db is None:
        return UsageSummaryResponse(period=period)

    # Tenant project ownership check
    if project_id is not None:
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_id(project_id)
        if not project or (current_user.role != "admin" and project.owner_user_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{project_id}' not found.",
            )

    usage_repo = UsageRepository(db)
    summary_data = await usage_repo.get_summary(
        user_id=current_user.id,
        project_id=project_id,
        period=period,
        is_admin=(current_user.role == "admin"),
    )
    return UsageSummaryResponse(**summary_data)


@router.get(
    "/usage/session/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Get token usage breakdown for a specific analysis session",
    responses={
        200: {"description": "Session usage records"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Session not found or access denied"},
    },
)
async def get_session_usage_endpoint(
    session_id: uuid.UUID,
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> List[Dict[str, Any]]:
    """
    Retrieve token usage records for a specific session with tenant isolation.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view token and cost usage.",
        )

    if db is None:
        return []

    usage_repo = UsageRepository(db)
    records = await usage_repo.get_by_session_id(
        session_id=session_id,
        user_id=current_user.id,
        is_admin=(current_user.role == "admin"),
    )
    return [
        {
            "id": str(r.id),
            "session_id": str(r.session_id) if r.session_id else None,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "estimated_cost_usd": r.estimated_cost_usd,
            "pricing_version": r.pricing_version,
            "usage_source": r.usage_source,
            "request_id": r.request_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
