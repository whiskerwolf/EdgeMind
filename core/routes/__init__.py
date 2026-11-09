"""
Routes Package: Exports all REST API routers for EdgeMind.
"""

from core.auth.router import auth_router, users_router
from core.routes.analyses import router as analyses_router
from core.routes.problems import router as problems_router
from core.routes.projects import router as projects_router

__all__ = [
    "auth_router",
    "users_router",
    "projects_router",
    "problems_router",
    "analyses_router",
]

