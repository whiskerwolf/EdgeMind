"""
MongoDB Analysis Report Repository for EdgeMind.

Encapsulates all asynchronous document store operations for the 'analysis_reports' collection:
- Complete analysis report persistence and retrieval.
- Idempotent upsert by canonical PostgreSQL analysis_session_id.
- Pagination, sorting (newest first), and filtering by user, project, and problem.
- Serialization sanitization and safe error wrapping (zero raw PyMongo leaks).
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo import DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.config import get_settings
from core.mongodb.collections import get_reports_collection

logger = logging.getLogger("edgemind.mongodb.repository")


class ReportRepositoryError(Exception):
    """Base exception for report repository operations."""
    pass


class DuplicateReportError(ReportRepositoryError):
    """Raised when an analysis report already exists for the given analysis_session_id."""
    pass


class ReportNotFoundError(ReportRepositoryError):
    """Raised when an analysis report document cannot be found."""
    pass


def sanitize_mongo_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Sanitize MongoDB document for API responses:
    - Converts ObjectId _id to string 'id'.
    - Serializes datetimes to ISO strings.
    - Never exposes passwords, JWTs, or raw DOM elements.
    """
    if doc is None:
        return None

    cleaned = dict(doc)
    if "_id" in cleaned:
        cleaned["id"] = str(cleaned.pop("_id"))
    elif "id" not in cleaned and "analysis_session_id" in cleaned:
        cleaned["id"] = cleaned["analysis_session_id"]

    for k, v in list(cleaned.items()):
        if isinstance(v, datetime):
            cleaned[k] = v.isoformat()
        elif isinstance(v, ObjectId):
            cleaned[k] = str(v)

    return cleaned


class ReportRepository:
    """Asynchronous repository for storing and retrieving full EdgeMind analysis reports."""

    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.collection: AsyncCollection = get_reports_collection(db)
        self.settings = get_settings()

    async def create_report(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new analysis report document.
        Raises DuplicateReportError if a report for this analysis_session_id already exists.
        """
        payload = dict(doc)
        now = datetime.now(timezone.utc)
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        payload.setdefault("schema_version", "1.0.0")

        if not payload.get("analysis_session_id"):
            raise ReportRepositoryError("Document must contain a valid 'analysis_session_id'.")

        try:
            result = await self.collection.insert_one(payload)
            payload["_id"] = result.inserted_id
            return sanitize_mongo_doc(payload) or {}
        except DuplicateKeyError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.warning(f"Duplicate report rejected for session '{payload.get('analysis_session_id')}': {sanitized}")
            raise DuplicateReportError(f"A report for session ID '{payload.get('analysis_session_id')}' already exists.") from err
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to create report document in MongoDB: {sanitized}")
            raise ReportRepositoryError("Failed to store analysis report in document database.") from err

    async def upsert_report(self, session_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Idempotently create or update a report by analysis_session_id.
        """
        session_id_str = str(session_id).strip()
        payload = dict(doc)
        now = datetime.now(timezone.utc)
        payload["analysis_session_id"] = session_id_str
        payload["updated_at"] = now
        payload.setdefault("schema_version", "1.0.0")

        # Set created_at on insert if not present
        update_doc = {
            "$set": payload,
            "$setOnInsert": {"created_at": payload.get("created_at", now)},
        }

        try:
            await self.collection.update_one(
                {"analysis_session_id": session_id_str},
                update_doc,
                upsert=True,
            )
            return await self.get_report_by_session_id(session_id_str) or sanitize_mongo_doc(payload) or {}
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to upsert report for session '{session_id_str}': {sanitized}")
            raise ReportRepositoryError("Failed to persist analysis report to document database.") from err

    async def get_report_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a full analysis report by canonical PostgreSQL analysis_session_id.
        """
        session_id_str = str(session_id).strip()
        try:
            doc = await self.collection.find_one({"analysis_session_id": session_id_str})
            return sanitize_mongo_doc(doc)
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to fetch report for session '{session_id_str}': {sanitized}")
            raise ReportRepositoryError("Failed to retrieve analysis report from document database.") from err

    async def list_reports(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        problem_slug: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List paginated reports sorted newest first (created_at DESC).
        Applies optional filters for multi-tenant ownership, project, and problem.
        """
        query: Dict[str, Any] = {}
        if user_id is not None:
            query["user_id"] = str(user_id)
        if project_id is not None:
            query["project_id"] = str(project_id)
        if problem_slug is not None:
            query["problem_slug"] = str(problem_slug).strip().lower()

        skip = max(0, int(skip))
        limit = max(1, min(100, int(limit)))

        try:
            total = await self.collection.count_documents(query)
            cursor = (
                self.collection.find(query)
                .sort("created_at", DESCENDING)
                .skip(skip)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            sanitized_docs = [sanitize_mongo_doc(d) for d in docs if d is not None]
            return [d for d in sanitized_docs if d is not None], total
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to list reports from MongoDB: {sanitized}")
            raise ReportRepositoryError("Failed to query report history from document database.") from err

    async def update_report(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update specific fields of an existing report document.
        """
        session_id_str = str(session_id).strip()
        clean_updates = dict(updates)
        clean_updates.pop("_id", None)
        clean_updates.pop("analysis_session_id", None)
        clean_updates["updated_at"] = datetime.now(timezone.utc)

        try:
            res = await self.collection.update_one(
                {"analysis_session_id": session_id_str},
                {"$set": clean_updates},
            )
            if res.matched_count == 0:
                return None
            return await self.get_report_by_session_id(session_id_str)
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to update report for session '{session_id_str}': {sanitized}")
            raise ReportRepositoryError("Failed to update analysis report.") from err

    async def delete_report(self, session_id: str) -> bool:
        """
        Delete a report document by analysis_session_id.
        Returns True if a document was deleted, False otherwise.
        """
        session_id_str = str(session_id).strip()
        try:
            res = await self.collection.delete_one({"analysis_session_id": session_id_str})
            return res.deleted_count > 0
        except PyMongoError as err:
            sanitized = self.settings.sanitize_error(str(err))
            logger.error(f"Failed to delete report for session '{session_id_str}': {sanitized}")
            raise ReportRepositoryError("Failed to delete analysis report.") from err
