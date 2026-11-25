"""
Administrator RBAC REST API Router.

Provides privilege-enforced administrative analytics endpoints built on
EdgeMind's existing `require_role("admin")` dependency and `UsageRepository`.

Endpoints:
- GET /api/v1/admin/usage (200 OK / 401 Unauthorized / 403 Forbidden / 503 Unavailable)
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_role
from core.config import get_settings
from core.cost import AdminUsageAnalyticsResponse
from core.database.connection import get_db
from core.database.models import User
from core.database.repositories.usage_repository import UsageRepository
from core.schemas import ErrorResponse

logger = logging.getLogger("edgemind.routes.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/usage",
    response_model=AdminUsageAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get global AI token usage and cost analytics (Admin only)",
    responses={
        200: {
            "model": AdminUsageAnalyticsResponse,
            "description": "Cross-tenant aggregated token usage and cost analytics",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Administrator privileges required"},
        503: {"model": ErrorResponse, "description": "Database persistence unavailable"},
    },
)
async def get_admin_usage_analytics(
    period: str = Query(
        default="month",
        pattern="^(day|month|all)$",
        description="Aggregation time window: day, month, or all",
    ),
    user_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Optional tenant user UUID filter",
    ),
    project_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Optional project UUID filter",
    ),
    provider: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern="^[a-zA-Z0-9_.-]+$",
        description="Optional AI provider filter (e.g. openai, ollama)",
    ),
    model: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern="^[a-zA-Z0-9_.:/-]+$",
        description="Optional model identifier filter",
    ),
    db: Optional[AsyncSession] = Depends(get_db),
    admin_user: User = Depends(require_role("admin")),
) -> AdminUsageAnalyticsResponse:
    """
    Retrieve system-wide AI token usage and estimated USD cost analytics.

    Access Control:
    - Enforced strictly via `require_role("admin")` (JWT signature + live DB role check).
    - Client-supplied parameters cannot elevate user privileges.
    - Returns only aggregated token/cost metadata and pseudonymous UUIDs (never API keys,
      passwords, emails, raw prompts, or user source code).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )

    usage_repo = UsageRepository(db)
    try:
        analytics = await usage_repo.get_admin_usage_analytics(
            period=period,
            user_id=user_id,
            project_id=project_id,
            provider=provider,
            model=model,
        )
        logger.info(
            "Admin usage analytics queried by admin_id=%s period=%s requests=%d",
            admin_user.id,
            period,
            analytics["requests_count"],
        )
        return AdminUsageAnalyticsResponse(**analytics)
    except HTTPException:
        raise
    except Exception as exc:
        sanitized = get_settings().sanitize_error(str(exc))
        logger.error("Failed to compute admin usage analytics: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute usage analytics.",
        )
