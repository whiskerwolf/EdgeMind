"""
EdgeMind Asynchronous Database Connection & Session Management.

Provides:
- Lazy async SQLAlchemy 2.0 engine creation with connection pooling.
- Async sessionmaker and FastAPI get_db dependency.
- Graceful connection error handling and lifecycle management.
- Zero connection on module import.
"""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config import get_settings
from core.database.models import Base

logger = logging.getLogger("edgemind.database")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> Optional[AsyncEngine]:
    """
    Get or lazily initialize the asynchronous SQLAlchemy engine.
    Does NOT connect on module import.
    """
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    if not settings.is_database_enabled:
        logger.debug("Database URL is not configured. Database engine will not be created.")
        return None

    db_url = settings.database_url
    # Configure pooling arguments depending on driver/dialect
    is_sqlite = db_url.startswith("sqlite")

    engine_kwargs = {
        "echo": settings.db_echo,
    }

    if is_sqlite:
        # SQLite in-memory or file testing
        engine_kwargs["poolclass"] = NullPool
    else:
        # PostgreSQL / asyncpg connection pool settings
        engine_kwargs.update({
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout,
            "pool_recycle": settings.db_pool_recycle,
            "pool_pre_ping": settings.db_pool_pre_ping,
        })

    try:
        _engine = create_async_engine(db_url, **engine_kwargs)
        logger.info(f"Initialized async SQLAlchemy engine ({'sqlite' if is_sqlite else 'postgresql'})")
    except Exception as exc:
        sanitized = settings.sanitize_error(str(exc))
        logger.error(f"Failed to create database engine: {sanitized}")
        _engine = None

    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """
    Get or lazily initialize the async sessionmaker factory.
    """
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine()
    if engine is None:
        return None

    _session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return _session_factory


async def get_db() -> AsyncGenerator[Optional[AsyncSession], None]:
    """
    FastAPI dependency yielding an asynchronous SQLAlchemy database session.
    Commits on normal exit, rolls back on exception, and guarantees session closure.
    Yields None if the database is not configured or unavailable.
    """
    factory = get_session_factory()
    if factory is None:
        yield None
        return

    session = factory()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        await session.rollback()
        settings = get_settings()
        sanitized = settings.sanitize_error(str(exc))
        logger.error(f"Database session rolled back due to error: {sanitized}")
        raise
    finally:
        await session.close()


async def close_db():
    """
    Dispose of connection pool and release resources on application shutdown.
    """
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Disposing database connection pool...")
        await _engine.dispose()
        _engine = None
        _session_factory = None

