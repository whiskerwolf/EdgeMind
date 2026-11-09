"""
MongoDB Index Definitions & Initialization for EdgeMind.

Ensures:
1. Unique index on analysis_session_id (canonical reference to PostgreSQL).
2. Compound index on (user_id, created_at DESC) for user report history queries.
3. Index on project_id for project-level reporting.
4. Index on problem_slug for problem-level metrics.
5. Index on created_at DESC for global pagination and chronological sorting.
"""

import logging
from typing import List

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from core.config import get_settings
from core.mongodb.collections import get_reports_collection

logger = logging.getLogger("edgemind.mongodb.indexes")


async def ensure_mongodb_indexes(db: AsyncDatabase) -> List[str]:
    """
    Ensure all required indexes exist on MongoDB collections.
    Does not crash application startup if indexing encounters issues.
    """
    settings = get_settings()
    created_indexes: List[str] = []

    try:
        collection = get_reports_collection(db)
        index_models = [
            IndexModel(
                [("analysis_session_id", ASCENDING)],
                unique=True,
                name="uq_analysis_reports_session_id",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_analysis_reports_user_created",
            ),
            IndexModel(
                [("project_id", ASCENDING)],
                name="ix_analysis_reports_project_id",
            ),
            IndexModel(
                [("problem_slug", ASCENDING)],
                name="ix_analysis_reports_problem_slug",
            ),
            IndexModel(
                [("created_at", DESCENDING)],
                name="ix_analysis_reports_created_at",
            ),
        ]

        result = await collection.create_indexes(index_models)
        created_indexes.extend(result)
        logger.info(f"Successfully ensured MongoDB indexes on 'analysis_reports': {result}")
    except PyMongoError as err:
        sanitized = settings.sanitize_error(str(err))
        logger.warning(f"Failed to ensure MongoDB indexes (will retry on next startup): {sanitized}")
    except Exception as exc:
        sanitized = settings.sanitize_error(str(exc))
        logger.warning(f"Unexpected error creating MongoDB indexes: {sanitized}")

    return created_indexes
