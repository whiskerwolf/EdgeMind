"""
PostgreSQL JSONB Analysis Report Repository for EdgeMind.

Encapsulates all asynchronous SQLAlchemy 2.0 operations for the 'analysis_reports' table:
- Complete analysis report persistence and retrieval using native JSONB.
- Idempotent upsert by canonical analysis_session_id.
- Pagination, sorting (newest first), and filtering by user, project, and problem.
- Serialization sanitization and safe error wrapping (zero raw database leaks).
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database.base import utc_now
from core.database.models import AnalysisReport

logger = logging.getLogger("edgemind.database.report_repository")


class ReportRepositoryError(Exception):
    """Base exception for report repository operations."""
    pass


class DuplicateReportError(ReportRepositoryError):
    """Raised when an analysis report already exists for the given analysis_session_id."""
    pass


class ReportNotFoundError(ReportRepositoryError):
    """Raised when an analysis report document cannot be found."""
    pass


def _normalize_uuid(val: Any) -> Optional[uuid.UUID]:
    """Safely convert a string, UUID, or None into an optional uuid.UUID."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        val_str = str(val).strip()
        return uuid.UUID(val_str) if val_str else None
    except (ValueError, TypeError):
        return None


class ReportRepository:
    """Asynchronous repository for storing and retrieving full EdgeMind analysis reports via PostgreSQL JSONB."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def create_report(
        self,
        doc: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        project_id: Optional[Union[str, uuid.UUID]] = None,
        problem_id: Optional[Union[str, uuid.UUID]] = None,
        problem_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new analysis report document.
        Raises DuplicateReportError if a report for this analysis_session_id already exists.
        """
        payload = dict(doc)
        effective_session_id = _normalize_uuid(session_id or payload.get("analysis_session_id"))
        if not effective_session_id:
            raise ReportRepositoryError("Document must contain a valid 'analysis_session_id'.")

        effective_user_id = _normalize_uuid(user_id or payload.get("user_id"))
        effective_project_id = _normalize_uuid(project_id or payload.get("project_id"))
        effective_problem_id = _normalize_uuid(problem_id or payload.get("problem_id"))
        effective_slug = str(problem_slug or payload.get("problem_slug") or "").strip().lower() or None

        # Check existing record by session ID
        existing = await self.get_report_by_session_id(effective_session_id)
        if existing is not None:
            raise DuplicateReportError(
                f"A report for session ID '{effective_session_id}' already exists."
            )

        payload["analysis_session_id"] = str(effective_session_id)
        payload["user_id"] = str(effective_user_id) if effective_user_id else None
        payload["project_id"] = str(effective_project_id) if effective_project_id else None
        payload["problem_id"] = str(effective_problem_id) if effective_problem_id else None
        payload["problem_slug"] = effective_slug
        payload.setdefault("schema_version", "1.0.0")

        now = utc_now()
        report_record = AnalysisReport(
            analysis_session_id=effective_session_id,
            user_id=effective_user_id,
            project_id=effective_project_id,
            problem_id=effective_problem_id,
            problem_slug=effective_slug,
            report_data=payload,
            schema_version=payload.get("schema_version", "1.0.0"),
            created_at=now,
            updated_at=now,
        )

        try:
            self.session.add(report_record)
            await self.session.flush()
            return report_record.to_dict()
        except IntegrityError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.warning(f"Integrity error creating report for session '{effective_session_id}': {sanitized}")
            raise DuplicateReportError(
                f"A report for session ID '{effective_session_id}' already exists."
            ) from err
        except SQLAlchemyError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Database error creating report for session '{effective_session_id}': {sanitized}")
            raise ReportRepositoryError("Failed to store analysis report in database.") from err

    async def upsert_report(
        self,
        session_id: Union[str, uuid.UUID],
        doc: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Idempotently create or update a report by analysis_session_id.
        """
        norm_session_id = _normalize_uuid(session_id)
        if not norm_session_id:
            raise ReportRepositoryError(f"Invalid analysis_session_id: '{session_id}'")

        payload = dict(doc)
        payload["analysis_session_id"] = str(norm_session_id)
        effective_user_id = _normalize_uuid(payload.get("user_id"))
        effective_project_id = _normalize_uuid(payload.get("project_id"))
        effective_problem_id = _normalize_uuid(payload.get("problem_id"))
        effective_slug = str(payload.get("problem_slug") or "").strip().lower() or None
        now = utc_now()

        try:
            stmt = select(AnalysisReport).where(AnalysisReport.analysis_session_id == norm_session_id)
            result = await self.session.execute(stmt)
            report_record = result.scalar_one_or_none()

            if report_record is not None:
                # Update existing record
                report_record.report_data = payload
                report_record.user_id = effective_user_id or report_record.user_id
                report_record.project_id = effective_project_id or report_record.project_id
                report_record.problem_id = effective_problem_id or report_record.problem_id
                if effective_slug:
                    report_record.problem_slug = effective_slug
                report_record.updated_at = now
                await self.session.flush()
                return report_record.to_dict()
            else:
                # Insert new record
                report_record = AnalysisReport(
                    analysis_session_id=norm_session_id,
                    user_id=effective_user_id,
                    project_id=effective_project_id,
                    problem_id=effective_problem_id,
                    problem_slug=effective_slug,
                    report_data=payload,
                    schema_version=payload.get("schema_version", "1.0.0"),
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(report_record)
                await self.session.flush()
                return report_record.to_dict()
        except IntegrityError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.warning(f"Integrity conflict upserting report for session '{norm_session_id}': {sanitized}")
            raise DuplicateReportError(f"Conflict while upserting report for session '{norm_session_id}'.") from err
        except SQLAlchemyError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to upsert report for session '{norm_session_id}': {sanitized}")
            raise ReportRepositoryError("Failed to persist analysis report to database.") from err

    async def get_report_by_session_id(
        self,
        session_id: Union[str, uuid.UUID],
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a full analysis report by canonical analysis_session_id.
        """
        norm_session_id = _normalize_uuid(session_id)
        if not norm_session_id:
            return None

        try:
            stmt = select(AnalysisReport).where(AnalysisReport.analysis_session_id == norm_session_id)
            result = await self.session.execute(stmt)
            report = result.scalar_one_or_none()
            return report.to_dict() if report else None
        except SQLAlchemyError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to fetch report for session '{norm_session_id}': {sanitized}")
            raise ReportRepositoryError("Failed to retrieve analysis report from database.") from err

    async def list_reports(
        self,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        project_id: Optional[Union[str, uuid.UUID]] = None,
        problem_slug: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List paginated reports sorted newest first (created_at DESC).
        Applies optional filters for multi-tenant ownership, project, and problem.
        """
        skip = max(0, int(skip))
        limit = max(1, min(100, int(limit)))

        stmt = select(AnalysisReport)
        count_stmt = select(func.count(AnalysisReport.id))

        if user_id is not None:
            norm_uid = _normalize_uuid(user_id)
            if norm_uid:
                stmt = stmt.where(AnalysisReport.user_id == norm_uid)
                count_stmt = count_stmt.where(AnalysisReport.user_id == norm_uid)

        if project_id is not None:
            norm_pid = _normalize_uuid(project_id)
            if norm_pid:
                stmt = stmt.where(AnalysisReport.project_id == norm_pid)
                count_stmt = count_stmt.where(AnalysisReport.project_id == norm_pid)

        if problem_slug is not None:
            slug_clean = str(problem_slug).strip().lower()
            if slug_clean:
                stmt = stmt.where(AnalysisReport.problem_slug == slug_clean)
                count_stmt = count_stmt.where(AnalysisReport.problem_slug == slug_clean)

        try:
            total_count = (await self.session.execute(count_stmt)).scalar() or 0

            stmt = stmt.order_by(AnalysisReport.created_at.desc()).offset(skip).limit(limit)
            result = await self.session.execute(stmt)
            records = result.scalars().all()
            return [r.to_dict() for r in records], total_count
        except SQLAlchemyError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to query report history from database: {sanitized}")
            raise ReportRepositoryError("Failed to query report history from database.") from err

    async def update_report(
        self,
        session_id: Union[str, uuid.UUID],
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update specific fields of an existing report document.
        """
        norm_session_id = _normalize_uuid(session_id)
        if not norm_session_id:
            return None

        try:
            stmt = select(AnalysisReport).where(AnalysisReport.analysis_session_id == norm_session_id)
            result = await self.session.execute(stmt)
            report = result.scalar_one_or_none()
            if not report:
                return None

            clean_updates = dict(updates)
            clean_updates.pop("id", None)
            clean_updates.pop("analysis_session_id", None)

            current_data = dict(report.report_data) if report.report_data else {}
            current_data.update(clean_updates)
            report.report_data = current_data

            if "problem_slug" in clean_updates:
                report.problem_slug = str(clean_updates["problem_slug"]).strip().lower()
            if "project_id" in clean_updates:
                report.project_id = _normalize_uuid(clean_updates["project_id"])
            if "user_id" in clean_updates:
                report.user_id = _normalize_uuid(clean_updates["user_id"])

            report.updated_at = utc_now()
            await self.session.flush()
            return report.to_dict()
        except SQLAlchemyError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to update report for session '{norm_session_id}': {sanitized}")
            raise ReportRepositoryError("Failed to update analysis report.") from err

    async def delete_report(
        self,
        session_id: Union[str, uuid.UUID],
    ) -> bool:
        """
        Delete a report document by analysis_session_id.
        Returns True if a document was deleted, False otherwise.
        """
        norm_session_id = _normalize_uuid(session_id)
        if not norm_session_id:
            return False

        try:
            stmt = select(AnalysisReport).where(AnalysisReport.analysis_session_id == norm_session_id)
            result = await self.session.execute(stmt)
            report = result.scalar_one_or_none()
            if not report:
                return False

            await self.session.delete(report)
            await self.session.flush()
            return True
        except SQLAlchemyError as err:
            await self.session.rollback()
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to delete report for session '{norm_session_id}': {sanitized}")
            raise ReportRepositoryError("Failed to delete analysis report.") from err
