"""
Project Repository: Reusable database access functions for Project entity.
"""

from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import AnalysisSession, Project


class ProjectRepository:
    """Encapsulates all asynchronous CRUD and reporting queries for Projects."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        language: Optional[str] = "python",
        technology_stack: Optional[Dict[str, Any]] = None,
        status: str = "active",
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> Project:
        """Create and persist a new Project record with optional owner."""
        project = Project(
            name=name.strip(),
            description=description.strip() if description else None,
            language=language.strip().lower() if language else "python",
            technology_stack=technology_stack or {},
            status=status.strip().lower(),
            owner_user_id=owner_user_id,
        )
        self.session.add(project)
        await self.session.flush()
        return project

    async def get_by_id(
        self,
        project_id: uuid.UUID,
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[Project]:
        """Fetch a project by UUID, optionally enforcing owner isolation."""
        stmt = select(Project).where(Project.id == project_id)
        if owner_user_id is not None:
            stmt = stmt.where(Project.owner_user_id == owner_user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        language: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> List[Project]:
        """List projects with pagination and optional filters (including owner isolation)."""
        stmt = select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
        if owner_user_id is not None:
            stmt = stmt.where(Project.owner_user_id == owner_user_id)
        if status:
            stmt = stmt.where(Project.status == status.strip().lower())
        if language:
            stmt = stmt.where(Project.language == language.strip().lower())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        project_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
        technology_stack: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[Project]:
        """Update existing project fields, strictly enforcing ownership if specified."""
        project = await self.get_by_id(project_id, owner_user_id=owner_user_id)
        if not project:
            return None

        if name is not None:
            project.name = name.strip()
        if description is not None:
            project.description = description.strip() if description else None
        if language is not None:
            project.language = language.strip().lower()
        if technology_stack is not None:
            project.technology_stack = technology_stack
        if status is not None:
            project.status = status.strip().lower()

        await self.session.flush()
        return project

    async def delete(
        self,
        project_id: uuid.UUID,
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Delete a project by UUID, strictly enforcing ownership if specified."""
        project = await self.get_by_id(project_id, owner_user_id=owner_user_id)
        if not project:
            return False

        await self.session.delete(project)
        await self.session.flush()
        return True

    async def get_projects_with_session_counts(
        self,
        skip: int = 0,
        limit: int = 50,
        owner_user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        SQL JOIN Query: Retrieve projects along with their total analysis session count.
        Avoids N+1 query patterns by performing an aggregation OUTER JOIN.
        """
        stmt = (
            select(
                Project,
                func.count(AnalysisSession.id).label("session_count"),
            )
            .outerjoin(AnalysisSession, Project.id == AnalysisSession.project_id)
        )
        if owner_user_id is not None:
            stmt = stmt.where(Project.owner_user_id == owner_user_id)

        stmt = (
            stmt.group_by(Project.id)
            .order_by(func.count(AnalysisSession.id).desc(), Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        output = []
        for project, count in rows:
            data = project.to_dict()
            data["session_count"] = count
            output.append(data)
        return output

