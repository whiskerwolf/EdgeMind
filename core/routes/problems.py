"""
Problems REST API Router.

Endpoints:
- POST /api/v1/problems (201 Created / 409 Conflict)
- GET /api/v1/problems (200 OK)
- GET /api/v1/problems/{problem_id} (200 OK / 404 Not Found)
"""

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.connection import get_db
from core.database.repositories.problem_repository import ProblemRepository
from core.schemas import ErrorResponse, ProblemCreate, ProblemResponse

router = APIRouter(prefix="/problems", tags=["Problems"])


def get_problem_repo(db: Optional[AsyncSession] = Depends(get_db)) -> ProblemRepository:
    """Dependency ensuring active database session is available."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )
    return ProblemRepository(db)


@router.post(
    "",
    response_model=ProblemResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": ProblemResponse, "description": "Problem successfully created"},
        409: {"model": ErrorResponse, "description": "Problem with platform and slug already exists"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def create_problem(
    payload: ProblemCreate,
    repo: ProblemRepository = Depends(get_problem_repo),
):
    """Create a new Problem record with unique constraint validation."""
    platform = payload.platform or "leetcode"
    existing = await repo.get_by_platform_and_slug(
        platform=platform,
        problem_slug=payload.problem_slug,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Problem with slug '{payload.problem_slug}' on platform '{platform}' already exists.",
        )

    problem = await repo.create(
        title=payload.title,
        problem_slug=payload.problem_slug,
        platform=platform,
        difficulty=payload.difficulty,
    )
    return problem.to_dict()


@router.get(
    "",
    response_model=List[ProblemResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": List[ProblemResponse], "description": "List of problems"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def list_problems(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    platform: Optional[str] = None,
    difficulty: Optional[str] = None,
    repo: ProblemRepository = Depends(get_problem_repo),
):
    """List problems with pagination and optional filters."""
    problems = await repo.list_all(
        skip=skip,
        limit=limit,
        platform=platform,
        difficulty=difficulty,
    )
    return [p.to_dict() for p in problems]


@router.get(
    "/{problem_id}",
    response_model=ProblemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": ProblemResponse, "description": "Problem details"},
        404: {"model": ErrorResponse, "description": "Problem not found"},
        422: {"model": ErrorResponse, "description": "Invalid UUID format"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
async def get_problem(
    problem_id: uuid.UUID,
    repo: ProblemRepository = Depends(get_problem_repo),
):
    """Get problem details by UUID."""
    problem = await repo.get_by_id(problem_id)
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem with ID '{problem_id}' not found.",
        )
    return problem.to_dict()

