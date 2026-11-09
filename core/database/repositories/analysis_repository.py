"""
Analysis Session Repository: Reusable database access functions for AnalysisSession entity.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database.models import AnalysisSession, Problem, Project


class AnalysisRepository:
    """Encapsulates all asynchronous CRUD and reporting queries for Analysis Sessions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        analysis_mode: str,
        language: str = "python",
        analysis_status: str = "SUCCESS",
        gaps_detected: int = 0,
        candidates_generated: int = 0,
        duration_ms: float = 0.0,
        project_id: Optional[uuid.UUID] = None,
        problem_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> AnalysisSession:
        """Create and persist a new AnalysisSession record with optional user ownership."""
        session_record = AnalysisSession(
            analysis_mode=analysis_mode.strip(),
            language=language.strip().lower() if language else "python",
            analysis_status=analysis_status.strip(),
            gaps_detected=max(0, int(gaps_detected)),
            candidates_generated=max(0, int(candidates_generated)),
            duration_ms=max(0.0, float(duration_ms)),
            project_id=project_id,
            problem_id=problem_id,
            user_id=user_id,
        )
        self.session.add(session_record)
        await self.session.flush()
        return session_record

    async def get_by_id(
        self,
        analysis_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[AnalysisSession]:
        """Fetch an analysis session by UUID with eager-loaded relations and optional user isolation."""
        stmt = (
            select(AnalysisSession)
            .options(
                selectinload(AnalysisSession.project),
                selectinload(AnalysisSession.problem),
            )
            .where(AnalysisSession.id == analysis_id)
        )
        if user_id is not None:
            stmt = stmt.where(AnalysisSession.user_id == user_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        project_id: Optional[uuid.UUID] = None,
        problem_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AnalysisSession]:
        """List analysis sessions with pagination, date, and user ownership filters."""
        stmt = (
            select(AnalysisSession)
            .order_by(AnalysisSession.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(AnalysisSession.user_id == user_id)
        if project_id:
            stmt = stmt.where(AnalysisSession.project_id == project_id)
        if problem_id:
            stmt = stmt.where(AnalysisSession.problem_id == problem_id)
        if start_date:
            stmt = stmt.where(AnalysisSession.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AnalysisSession.created_at <= end_date)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_analysis_history_report(
        self,
        skip: int = 0,
        limit: int = 50,
        project_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        SQL JOIN Query: Retrieve analysis history joined with Project and Problem metadata.
        Demonstrates a multi-table JOIN without N+1 query patterns, enforcing user isolation.
        """
        stmt = (
            select(
                AnalysisSession,
                Project.name.label("project_name"),
                Problem.title.label("problem_title"),
                Problem.problem_slug.label("problem_slug"),
                Problem.platform.label("platform"),
            )
            .outerjoin(Project, AnalysisSession.project_id == Project.id)
            .outerjoin(Problem, AnalysisSession.problem_id == Problem.id)
            .order_by(AnalysisSession.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(AnalysisSession.user_id == user_id)
        if project_id:
            stmt = stmt.where(AnalysisSession.project_id == project_id)

        result = await self.session.execute(stmt)
        rows = result.all()

        output = []
        for session_item, proj_name, prob_title, prob_slug, platform in rows:
            record = session_item.to_dict()
            record["project_name"] = proj_name
            record["problem_title"] = prob_title
            record["problem_slug"] = prob_slug
            record["platform"] = platform
            output.append(record)
        return output

