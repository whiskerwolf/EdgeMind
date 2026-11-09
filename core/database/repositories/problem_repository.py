"""
Problem Repository: Reusable database access functions for Problem entity.
"""

from typing import List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Problem


class ProblemRepository:
    """Encapsulates all asynchronous CRUD operations for Problems."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        title: str,
        problem_slug: str,
        platform: str = "leetcode",
        difficulty: Optional[str] = None,
    ) -> Problem:
        """Create and persist a new Problem record."""
        problem = Problem(
            title=title.strip(),
            problem_slug=problem_slug.strip().lower(),
            platform=platform.strip().lower(),
            difficulty=difficulty.strip() if difficulty else None,
        )
        self.session.add(problem)
        await self.session.flush()
        return problem

    async def get_by_id(self, problem_id: uuid.UUID) -> Optional[Problem]:
        """Fetch a problem by UUID."""
        stmt = select(Problem).where(Problem.id == problem_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_platform_and_slug(
        self,
        platform: str,
        problem_slug: str,
    ) -> Optional[Problem]:
        """Fetch a problem by platform and unique slug."""
        stmt = select(Problem).where(
            Problem.platform == platform.strip().lower(),
            Problem.problem_slug == problem_slug.strip().lower(),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        title: str,
        problem_slug: str,
        platform: str = "leetcode",
        difficulty: Optional[str] = None,
    ) -> Tuple[Problem, bool]:
        """
        Idempotently find an existing problem or create a new one.
        Returns (problem, created_flag).
        """
        existing = await self.get_by_platform_and_slug(platform, problem_slug)
        if existing:
            return existing, False

        new_problem = await self.create(
            title=title,
            problem_slug=problem_slug,
            platform=platform,
            difficulty=difficulty,
        )
        return new_problem, True

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        platform: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> List[Problem]:
        """List problems with pagination and optional filters."""
        stmt = select(Problem).order_by(Problem.created_at.desc()).offset(skip).limit(limit)
        if platform:
            stmt = stmt.where(Problem.platform == platform.strip().lower())
        if difficulty:
            stmt = stmt.where(Problem.difficulty == difficulty.strip())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

