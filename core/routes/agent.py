"""
Agent Analysis REST API Router.

Provides HTTP endpoint for multi-step autonomous AI agent analysis
with native tool calling.

Endpoint:
- POST /api/v1/agent/analyze
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import LiveAgentProvider
from core.agents.schemas import AgentAnalyzeRequest, AgentAnalyzeResponse
from core.auth.dependencies import get_optional_current_user
from core.database.connection import get_db
from core.database.models import User
from core.database.repositories.project_repository import ProjectRepository
from core.schemas import ErrorResponse

logger = logging.getLogger("edgemind.routes.agent")

router = APIRouter(prefix="/agent", tags=["Agent"])


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
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def agent_analyze_endpoint(
    request: Request,
    body: AgentAnalyzeRequest,
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
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
        provider = LiveAgentProvider(model=body.model)
        orchestrator = AgentOrchestrator(
            provider=provider,
            max_iterations=body.max_iterations,
        )

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
