"""
Projects REST API Router.

Endpoints:
- POST /api/v1/projects (201 Created)
- GET /api/v1/projects (200 OK)
- GET /api/v1/projects/statistics (200 OK, SQL JOIN with session counts)
- GET /api/v1/projects/{project_id} (200 OK / 404 Not Found)
- PATCH /api/v1/projects/{project_id} (200 OK / 404 Not Found)
- DELETE /api/v1/projects/{project_id} (204 No Content / 404 Not Found)
"""

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_optional_current_user
from core.database.connection import get_db
from core.database.models import User
from core.database.repositories.project_repository import ProjectRepository
from core.schemas import (
    ErrorResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ProjectWithStatsResponse,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


def get_project_repo(db: Optional[AsyncSession] = Depends(get_db)) -> ProjectRepository:
    """Dependency ensuring active database session is available."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )
    return ProjectRepository(db)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": ProjectResponse, "description": "Project successfully created"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def create_project(
    payload: ProjectCreate,
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Create a new Project record, assigning the authenticated user as owner."""
    owner_id = current_user.id if current_user else None
    project = await repo.create(
        name=payload.name,
        description=payload.description,
        language=payload.language or "python",
        technology_stack=payload.technology_stack or {},
        status=payload.status or "active",
        owner_user_id=owner_id,
    )
    return project.to_dict()


@router.get(
    "/statistics",
    response_model=List[ProjectWithStatsResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": List[ProjectWithStatsResponse], "description": "Projects with joined session counts"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_projects_statistics(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    SQL JOIN Demonstration 1:
    Retrieve projects along with aggregated session counts in a single query.
    Enforces tenant isolation for regular users; administrators can view across tenants.
    """
    owner_filter = None
    if current_user and current_user.role != "admin":
        owner_filter = current_user.id

    return await repo.get_projects_with_session_counts(skip=skip, limit=limit, owner_user_id=owner_filter)


@router.get(
    "",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": List[ProjectResponse], "description": "List of projects"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    language: Optional[str] = None,
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """List projects with pagination and filters. Enforces user ownership isolation."""
    owner_filter = None
    if current_user and current_user.role != "admin":
        owner_filter = current_user.id

    projects = await repo.list_all(
        skip=skip,
        limit=limit,
        status=status_filter,
        language=language,
        owner_user_id=owner_filter,
    )
    return [p.to_dict() for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": ProjectResponse, "description": "Project details"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_project(
    project_id: uuid.UUID,
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Get project details by UUID with ownership verification (returns 404 on cross-user access)."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    # Ownership isolation check
    if project.owner_user_id is not None:
        if not current_user or (current_user.id != project.owner_user_id and current_user.role != "admin"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' not found.",
            )

    return project.to_dict()


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": ProjectResponse, "description": "Project updated"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"model": ErrorResponse, "description": "Invalid request data"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Update project fields with ownership verification."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    if project.owner_user_id is not None:
        if not current_user or (current_user.id != project.owner_user_id and current_user.role != "admin"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' not found.",
            )

    updated = await repo.update(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        language=payload.language,
        technology_stack=payload.technology_stack,
        status=payload.status,
    )
    return updated.to_dict()


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Project deleted"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def delete_project(
    project_id: uuid.UUID,
    repo: ProjectRepository = Depends(get_project_repo),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Delete a project by UUID with ownership verification."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    if project.owner_user_id is not None:
        if not current_user or (current_user.id != project.owner_user_id and current_user.role != "admin"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' not found.",
            )

    await repo.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

