"""
Analysis Sessions REST API Router.

Endpoints:
- GET /api/v1/analyses/report (200 OK, SQL JOIN with Project & Problem metadata)
- GET /api/v1/analyses (200 OK)
- GET /api/v1/analyses/{analysis_id} (200 OK / 404 Not Found)
- POST /api/v1/analyses (201 Created)
"""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.connection import get_db
from core.database.repositories.analysis_repository import AnalysisRepository
from core.database.repositories.problem_repository import ProblemRepository
from core.database.repositories.project_repository import ProjectRepository
from core.schemas import (
    AnalysisReportItemResponse,
    AnalysisSessionCreate,
    AnalysisSessionResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/analyses", tags=["Analysis Sessions"])


def get_analysis_repo(db: Optional[AsyncSession] = Depends(get_db)) -> AnalysisRepository:
    """Dependency ensuring active database session is available."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )
    return AnalysisRepository(db)


@router.get(
    "/report",
    response_model=List[AnalysisReportItemResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "model": List[AnalysisReportItemResponse],
            "description": "Analysis sessions joined with Project and Problem metadata",
        },
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_analysis_report(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[uuid.UUID] = None,
    repo: AnalysisRepository = Depends(get_analysis_repo),
):
    """
    SQL JOIN Demonstration 2:
    Retrieve analysis history with joined Project and Problem metadata in a single query.
    Eliminates N+1 query patterns.
    """
    return await repo.get_analysis_history_report(skip=skip, limit=limit, project_id=project_id)


@router.get(
    "",
    response_model=List[AnalysisSessionResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": List[AnalysisSessionResponse], "description": "List of analysis sessions"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def list_analyses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[uuid.UUID] = None,
    problem_id: Optional[uuid.UUID] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    repo: AnalysisRepository = Depends(get_analysis_repo),
):
    """List analysis sessions with pagination and filters."""
    sessions = await repo.list_all(
        skip=skip,
        limit=limit,
        project_id=project_id,
        problem_id=problem_id,
        start_date=start_date,
        end_date=end_date,
    )
    return [s.to_dict() for s in sessions]


@router.get(
    "/{analysis_id}",
    response_model=AnalysisSessionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": AnalysisSessionResponse, "description": "Analysis session details"},
        404: {"model": ErrorResponse, "description": "Analysis session not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_analysis(
    analysis_id: uuid.UUID,
    repo: AnalysisRepository = Depends(get_analysis_repo),
):
    """Get an analysis session by UUID."""
    session_rec = await repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )
    return session_rec.to_dict()


@router.post(
    "",
    response_model=AnalysisSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": AnalysisSessionResponse, "description": "Analysis session created"},
        400: {"model": ErrorResponse, "description": "Invalid foreign key or payload"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def create_analysis_session(
    payload: AnalysisSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Programmatically record an analysis session."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )

    project_repo = ProjectRepository(db)
    problem_repo = ProblemRepository(db)
    analysis_repo = AnalysisRepository(db)

    proj_uuid = None
    if payload.project_id:
        try:
            proj_uuid = uuid.UUID(payload.project_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid project_id UUID format: '{payload.project_id}'",
            )
        project = await project_repo.get_by_id(proj_uuid)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Referenced project with ID '{payload.project_id}' does not exist.",
            )

    prob_uuid = None
    if payload.problem_id:
        try:
            prob_uuid = uuid.UUID(payload.problem_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid problem_id UUID format: '{payload.problem_id}'",
            )
        problem = await problem_repo.get_by_id(prob_uuid)
        if not problem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Referenced problem with ID '{payload.problem_id}' does not exist.",
            )

    session_rec = await analysis_repo.create(
        analysis_mode=payload.analysis_mode,
        language=payload.language or "python",
        analysis_status=payload.analysis_status or "SUCCESS",
        gaps_detected=payload.gaps_detected or 0,
        candidates_generated=payload.candidates_generated or 0,
        duration_ms=payload.duration_ms or 0.0,
        project_id=proj_uuid,
        problem_id=prob_uuid,
    )
    return session_rec.to_dict()

