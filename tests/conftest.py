"""
Pytest configuration and root fixtures for EdgeMind.

Ensures:
- Test environment isolation (ENVIRONMENT="testing").
- Prevention of pooled AsyncEngine connection reuse across asyncio event loops.
- Ordinary unit and API tests use isolated in-memory SQLite sessions or mocked dependencies.
- Live PostgreSQL tests explicitly connect to 127.0.0.1:5433/edgemind.
- Automatic cleanup of dependency overrides and engine disposal between tests.
"""

import asyncio
import os
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.database.base import Base
from core.database.connection import dispose_engine, get_db


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """
    Ensure testing environment flag is active and clean up engine state between tests.
    """
    monkeypatch.setenv("ENVIRONMENT", "testing")
    yield
    dispose_engine()


@pytest.fixture(scope="session")
def sqlite_test_engine():
    """
    Session-scoped isolated SQLite async engine with StaticPool and foreign keys.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_tables())
    yield engine

    async def drop_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(drop_tables())


@pytest.fixture(autouse=True)
def default_db_isolation(sqlite_test_engine):
    """
    Provide an isolated in-memory SQLite session for any API test that does not
    explicitly define its own database fixture, preventing accidental fallback
    to live PostgreSQL connection pools during ordinary unit tests.
    """
    # Only supply default override if not already overridden by local test fixture
    had_override = get_db in app.dependency_overrides

    if not had_override:
        session_factory = async_sessionmaker(
            bind=sqlite_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async def _override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = _override_get_db

    yield

    if not had_override:
        app.dependency_overrides.pop(get_db, None)
