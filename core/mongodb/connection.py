"""
Async MongoDB Connection & Lifecycle Management for EdgeMind.

Provides:
- Native AsyncMongoClient management using PyMongo's native asyncio support.
- Single client instance per application event loop.
- Lazy connection initialization (no connection on module import).
- Startup health checking and graceful failure handling.
- Clean resource disposal on FastAPI shutdown.
"""

import logging
from typing import AsyncGenerator, Optional

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from core.config import get_settings

logger = logging.getLogger("edgemind.mongodb")

_client: Optional[AsyncMongoClient] = None
_database: Optional[AsyncDatabase] = None


def get_mongo_client() -> Optional[AsyncMongoClient]:
    """
    Get or lazily create the AsyncMongoClient singleton.
    Does NOT connect on module import.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    if not settings.is_mongodb_enabled:
        logger.debug("MongoDB URL is not configured. MongoDB client will not be initialized.")
        return None

    try:
        _client = AsyncMongoClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
            connectTimeoutMS=settings.mongodb_server_selection_timeout_ms,
            uuidRepresentation="standard",
        )
        logger.info("Initialized AsyncMongoClient instance.")
    except Exception as exc:
        sanitized = settings.sanitize_error(str(exc))
        logger.error(f"Failed to instantiate AsyncMongoClient: {sanitized}")
        _client = None

    return _client


def get_mongo_db() -> Optional[AsyncDatabase]:
    """
    Get or lazily resolve the active AsyncDatabase handle.
    """
    global _database
    if _database is not None:
        return _database

    client = get_mongo_client()
    if client is None:
        return None

    settings = get_settings()
    _database = client[settings.mongodb_database]
    return _database


async def check_mongo_health() -> bool:
    """
    Execute a ping command to verify live MongoDB connectivity.
    Returns True if responsive, False if unreachable or unconfigured.
    """
    client = get_mongo_client()
    if client is None:
        return False

    try:
        await client.admin.command("ping")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as err:
        settings = get_settings()
        sanitized = settings.sanitize_error(str(err))
        logger.warning(f"MongoDB ping check failed: {sanitized}")
        return False
    except Exception as exc:
        settings = get_settings()
        sanitized = settings.sanitize_error(str(exc))
        logger.warning(f"Unexpected error during MongoDB health ping: {sanitized}")
        return False


async def close_mongo_client() -> None:
    """
    Cleanly close the AsyncMongoClient and release resources during application shutdown.
    """
    global _client, _database
    if _client is not None:
        logger.info("Closing AsyncMongoClient connection pool...")
        try:
            await _client.close()
        except Exception as exc:
            settings = get_settings()
            sanitized = settings.sanitize_error(str(exc))
            logger.warning(f"Error while closing AsyncMongoClient: {sanitized}")
        finally:
            _client = None
            _database = None


async def get_mongo_session() -> AsyncGenerator[Optional[AsyncDatabase], None]:
    """
    FastAPI dependency yielding the configured AsyncDatabase handle, or None if unavailable.
    """
    db = get_mongo_db()
    yield db
