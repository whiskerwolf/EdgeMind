"""
Analysis Reports Document REST API Router for EdgeMind.

Endpoints:
- GET /api/v1/reports (200 OK, paginated report history with strict ownership isolation)
"""

from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_active_user
from core.database.models import User
from core.mongodb.connection import get_mongo_db
from core.mongodb.repositories import ReportRepository
from core.schemas import ErrorResponse

router = APIRouter(prefix="/reports", tags=["Analysis Reports"])


class PaginatedReportsResponse(BaseModel):
    """Schema for paginated report history."""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    skip: int = Field(default=0)
    limit: int = Field(default=50)


@router.get(
    "",
    response_model=PaginatedReportsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": PaginatedReportsResponse, "description": "Paginated report document history"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        503: {"model": ErrorResponse, "description": "Document storage unavailable"},
    },
)
async def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[uuid.UUID] = None,
    problem_slug: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    List paginated analysis reports from MongoDB.
    Enforces user ownership isolation: ordinary users see only their own reports,
    while administrators can access reports across all tenants.
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document report storage is not configured or currently unreachable.",
        )

    user_filter = None if current_user.role == "admin" else str(current_user.id)
    proj_filter = str(project_id) if project_id else None

    repo = ReportRepository(db)
    items, total = await repo.list_reports(
        user_id=user_filter,
        project_id=proj_filter,
        problem_slug=problem_slug,
        skip=skip,
        limit=limit,
    )
    return PaginatedReportsResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )
