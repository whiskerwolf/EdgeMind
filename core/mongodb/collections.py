"""
MongoDB Collection Names & Accessors for EdgeMind.
"""

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

# Canonical collection names
COLLECTION_ANALYSIS_REPORTS = "analysis_reports"


def get_reports_collection(db: AsyncDatabase) -> AsyncCollection:
    """Return the AsyncCollection handle for analysis_reports."""
    return db[COLLECTION_ANALYSIS_REPORTS]
