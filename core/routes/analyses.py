"""
Analysis Sessions REST API Router.

Endpoints:
- GET /api/v1/analyses/report (200 OK, SQL JOIN with Project & Problem metadata)
- GET /api/v1/analyses (200 OK)
- GET /api/v1/analyses/{analysis_id} (200 OK / 404 Not Found)
- POST /api/v1/analyses (201 Created)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database.connection import get_db
from core.database.models import User
from core.database.repositories.analysis_repository import AnalysisRepository
from core.database.repositories.problem_repository import ProblemRepository
from core.database.repositories.project_repository import ProjectRepository
from core.mongodb.connection import get_mongo_db
from core.mongodb.repositories import ReportRepository
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
        401: {"model": ErrorResponse, "description": "Authentication required"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_analysis_report(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[uuid.UUID] = None,
    repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """
    SQL JOIN Demonstration 2:
    Retrieve analysis history with joined Project and Problem metadata in a single query.
    Enforces user isolation for regular users; administrators can view across all users.
    """
    user_filter = None if current_user.role == "admin" else current_user.id
    return await repo.get_analysis_history_report(
        skip=skip,
        limit=limit,
        project_id=project_id,
        user_id=user_filter,
    )


@router.get(
    "",
    response_model=List[AnalysisSessionResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": List[AnalysisSessionResponse], "description": "List of analysis sessions"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
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
    current_user: User = Depends(get_current_active_user),
):
    """List analysis sessions with pagination and filters. Enforces user ownership isolation."""
    user_filter = None if current_user.role == "admin" else current_user.id
    sessions = await repo.list_all(
        skip=skip,
        limit=limit,
        project_id=project_id,
        problem_id=problem_id,
        user_id=user_filter,
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
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Analysis session not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_analysis(
    analysis_id: uuid.UUID,
    repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """Get an analysis session by UUID with ownership verification (returns 404 on cross-user access)."""
    session_rec = await repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    # Ownership isolation check: ordinary users can only access their own analysis sessions
    if current_user.role != "admin" and session_rec.user_id != current_user.id:
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
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Referenced project not found"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def create_analysis_session(
    payload: AnalysisSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Programmatically record an analysis session, assigning authenticated user ownership."""
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{payload.project_id}' not found.",
            )
        if current_user.role != "admin" and project.owner_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced project with ID '{payload.project_id}' not found.",
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
        user_id=current_user.id,
    )
    return session_rec.to_dict()


@router.get(
    "/{analysis_id}/report",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Complete detailed analysis report from document store"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Analysis session or report not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Document storage unavailable"},
    },
)
async def get_detailed_report(
    analysis_id: uuid.UUID,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve the full detailed analysis report document from MongoDB.
    Verifies ownership via PostgreSQL before accessing MongoDB.
    """
    session_rec = await analysis_repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    # Ownership isolation check
    if current_user.role != "admin" and session_rec.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document report storage is not configured or currently unreachable.",
        )

    report_repo = ReportRepository(mongo_db)
    report_doc = await report_repo.get_report_by_session_id(str(analysis_id))
    if not report_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detailed report for analysis session '{analysis_id}' was not found.",
        )

    return report_doc


@router.get(
    "/{analysis_id}/candidates",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Generated test candidates and classification summaries"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Analysis session or report not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Document storage unavailable"},
    },
)
async def get_analysis_candidates(
    analysis_id: uuid.UUID,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve generated test candidates from MongoDB for a specific analysis session.
    Verifies ownership via PostgreSQL before accessing MongoDB.
    """
    session_rec = await analysis_repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    if current_user.role != "admin" and session_rec.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document report storage is not configured or currently unreachable.",
        )

    report_repo = ReportRepository(mongo_db)
    report_doc = await report_repo.get_report_by_session_id(str(analysis_id))
    if not report_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detailed report for analysis session '{analysis_id}' was not found.",
        )

    return {
        "analysis_session_id": str(analysis_id),
        "candidates": report_doc.get("generated_candidates", []),
        "candidate_classifications": report_doc.get("candidate_classifications", {}),
        "total_candidates": len(report_doc.get("generated_candidates", [])),
        "provenance": report_doc.get("analysis_metadata", {}).get("provenance", {}),
        "limitations": report_doc.get("explanations", {}).get("limitations", []),
    }


@router.get(
    "/{analysis_id}/coverage-gaps",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Constraint and coverage gap information"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Analysis session or report not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Document storage unavailable"},
    },
)
async def get_analysis_coverage_gaps(
    analysis_id: uuid.UUID,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve constraint and coverage gap details from MongoDB for an analysis session.
    Verifies ownership via PostgreSQL before accessing MongoDB.
    """
    session_rec = await analysis_repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    if current_user.role != "admin" and session_rec.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document report storage is not configured or currently unreachable.",
        )

    report_repo = ReportRepository(mongo_db)
    report_doc = await report_repo.get_report_by_session_id(str(analysis_id))
    if not report_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detailed report for analysis session '{analysis_id}' was not found.",
        )

    return {
        "analysis_session_id": str(analysis_id),
        "coverage_gaps": report_doc.get("coverage_gaps", []),
        "total_gaps": len(report_doc.get("coverage_gaps", [])),
        "constraints": report_doc.get("constraints", {}),
        "unresolved_constraints": report_doc.get("explanations", {}).get("unresolved_constraints", []),
    }


@router.delete(
    "/{analysis_id}/report",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Detailed report deleted from MongoDB, PostgreSQL session preserved"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Analysis session not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Document storage unavailable"},
    },
)
async def delete_analysis_report(
    analysis_id: uuid.UUID,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete the detailed report document from MongoDB while preserving PostgreSQL session metadata.
    Updates report_storage_status to 'NOT_CONFIGURED'.
    """
    session_rec = await analysis_repo.get_by_id(analysis_id)
    if not session_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    if current_user.role != "admin" and session_rec.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis session with ID '{analysis_id}' not found.",
        )

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document report storage is not configured or currently unreachable.",
        )

    report_repo = ReportRepository(mongo_db)
    await report_repo.delete_report(str(analysis_id))
    await analysis_repo.update_storage_status(analysis_id, "NOT_CONFIGURED")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

