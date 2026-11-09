"""
MongoDB Document Store Package for EdgeMind.

Provides:
- PyMongo native AsyncMongoClient connection lifecycle management.
- Analysis reports document collections and index management.
- Asynchronous report repositories.
"""

from core.mongodb.builder import build_analysis_report_doc
from core.mongodb.collections import (
    COLLECTION_ANALYSIS_REPORTS,
    get_reports_collection,
)
from core.mongodb.connection import (
    check_mongo_health,
    close_mongo_client,
    get_mongo_client,
    get_mongo_db,
    get_mongo_session,
)
from core.mongodb.indexes import ensure_mongodb_indexes
from core.mongodb.repositories import (
    DuplicateReportError,
    ReportNotFoundError,
    ReportRepository,
    ReportRepositoryError,
    sanitize_mongo_doc,
)

__all__ = [
    "COLLECTION_ANALYSIS_REPORTS",
    "DuplicateReportError",
    "ReportNotFoundError",
    "ReportRepository",
    "ReportRepositoryError",
    "build_analysis_report_doc",
    "check_mongo_health",
    "close_mongo_client",
    "ensure_mongodb_indexes",
    "get_mongo_client",
    "get_mongo_db",
    "get_mongo_session",
    "get_reports_collection",
    "sanitize_mongo_doc",
]
