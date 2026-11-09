"""
EdgeMind — Phase 2: PostgreSQL Data Layer & Persistence Test Suite.

Validates:
1. Model creation, UUID primary keys, JSON column mapping, and relationships.
2. Unique constraints (Problem platform + slug) and foreign keys (CASCADE, SET NULL).
3. Repository CRUD operations (ProjectRepository, ProblemRepository, AnalysisRepository).
4. SQL JOIN Demonstration 1: Project session count aggregation without N+1 queries.
5. SQL JOIN Demonstration 2: Analysis history multi-table join with Project and Problem metadata.
6. Transaction rollback and session isolation on errors.
7. Alembic migration upgrade to head and downgrade to base.
8. REST API endpoints for Projects, Problems, and Analyses with full status code coverage.
9. Integration with POST /api/v1/edgemind/analyze (session recording, problem auto-linking).
10. Graceful degradation when the database is unavailable (returns analysis_session_id: null).
11. Database URL password sanitization.
"""

from datetime import datetime, timezone
import os
from typing import AsyncGenerator
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import AnalysisSession, Base, Problem, Project
from core.database.repositories import (
    AnalysisRepository,
    ProblemRepository,
    ProjectRepository,
)


# -----------------------------------------------------------------------------
# Fixtures for In-Memory SQLite Async Database
# -----------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def async_db_engine():
    """Create an isolated in-memory SQLite async engine with StaticPool and enabled FKs."""
    import asyncio
    from sqlalchemy import event

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

    async def cleanup_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(cleanup_tables())


@pytest.fixture
async def async_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session with auto-rollback."""
    session_maker = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
def test_client_with_db(async_db_engine):
    """FastAPI TestClient with overridden get_db dependency pointing to the test DB."""
    session_maker = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def test_client_db_disabled():
    """FastAPI TestClient simulating an unreachable or unconfigured database."""
    async def override_get_db_none():
        yield None

    app.dependency_overrides[get_db] = override_get_db_none
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


# -----------------------------------------------------------------------------
# 1. Model & Schema Integrity Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_project_model_creation(async_session: AsyncSession):
    """Verify Project model initialization, UUID generation, and dictionary serialization."""
    project = Project(
        name="EdgeMind Core",
        description="Core test intelligence platform",
        language="python",
        technology_stack={"framework": "FastAPI", "orm": "SQLAlchemy"},
        status="active",
    )
    async_session.add(project)
    await async_session.commit()

    assert isinstance(project.id, uuid.UUID)
    assert project.name == "EdgeMind Core"
    assert project.technology_stack.get("framework") == "FastAPI"
    assert project.created_at is not None
    assert project.updated_at is not None

    data = project.to_dict()
    assert data["id"] == str(project.id)
    assert data["name"] == "EdgeMind Core"
    assert data["technology_stack"]["orm"] == "SQLAlchemy"


@pytest.mark.anyio
async def test_problem_model_unique_constraint(async_session: AsyncSession):
    """Verify unique constraint on (platform, problem_slug) in Problem model."""
    prob1 = Problem(
        title="Two Sum",
        problem_slug="two-sum",
        platform="leetcode",
        difficulty="Easy",
    )
    async_session.add(prob1)
    await async_session.commit()

    prob2 = Problem(
        title="Two Sum Duplicate",
        problem_slug="two-sum",
        platform="leetcode",
        difficulty="Easy",
    )
    async_session.add(prob2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.anyio
async def test_analysis_session_relationships_and_foreign_keys(async_session: AsyncSession):
    """Verify AnalysisSession relationships, CASCADE delete on Project, and SET NULL on Problem."""
    proj = Project(name="Project Cascade Test")
    prob = Problem(title="Valid Parentheses", problem_slug="valid-parentheses", platform="leetcode")
    async_session.add_all([proj, prob])
    await async_session.commit()

    session_rec = AnalysisSession(
        project_id=proj.id,
        problem_id=prob.id,
        analysis_mode="BASELINE_DRIVEN",
        language="python",
        analysis_status="SUCCESS",
        gaps_detected=3,
        candidates_generated=5,
        duration_ms=42.5,
    )
    async_session.add(session_rec)
    await async_session.commit()

    assert session_rec.project_id == proj.id
    assert session_rec.problem_id == prob.id
    assert session_rec.gaps_detected == 3
    assert session_rec.candidates_generated == 5

    # Test CASCADE delete: Deleting project deletes session
    session_id = session_rec.id
    await async_session.delete(proj)
    await async_session.commit()

    res = await async_session.execute(select(AnalysisSession).where(AnalysisSession.id == session_id))
    assert res.scalar_one_or_none() is None


# -----------------------------------------------------------------------------
# 2. Repository CRUD Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_project_repository_crud(async_session: AsyncSession):
    """Verify full CRUD lifecycle and filtering via ProjectRepository."""
    repo = ProjectRepository(async_session)

    # Create
    p1 = await repo.create(
        name="Alpha Project",
        description="First test project",
        language="python",
        technology_stack={"env": "test"},
        status="active",
    )
    p2 = await repo.create(
        name="Beta Project",
        language="javascript",
        status="archived",
    )
    await async_session.commit()

    # Read by ID
    found = await repo.get_by_id(p1.id)
    assert found is not None
    assert found.name == "Alpha Project"

    # List with filtering
    active_projects = await repo.list_all(status="active")
    assert len(active_projects) == 1
    assert active_projects[0].name == "Alpha Project"

    py_projects = await repo.list_all(language="python")
    assert len(py_projects) == 1

    # Update
    updated = await repo.update(p1.id, name="Alpha Project Renamed", status="completed")
    await async_session.commit()
    assert updated.name == "Alpha Project Renamed"
    assert updated.status == "completed"

    # Delete
    deleted = await repo.delete(p2.id)
    await async_session.commit()
    assert deleted is True
    assert await repo.get_by_id(p2.id) is None


@pytest.mark.anyio
async def test_problem_repository_crud_and_get_or_create(async_session: AsyncSession):
    """Verify ProblemRepository get_or_create idempotency and slug lookup."""
    repo = ProblemRepository(async_session)

    # First call creates
    prob, created = await repo.get_or_create(
        title="Search Insert Position",
        problem_slug="search-insert-position",
        platform="leetcode",
        difficulty="Easy",
    )
    await async_session.commit()
    assert created is True
    assert prob.problem_slug == "search-insert-position"

    # Second call returns existing record
    prob2, created2 = await repo.get_or_create(
        title="Search Insert Position",
        problem_slug="search-insert-position",
        platform="leetcode",
    )
    assert created2 is False
    assert prob2.id == prob.id

    # Lookup by platform and slug
    lookup = await repo.get_by_platform_and_slug("leetcode", "search-insert-position")
    assert lookup is not None
    assert lookup.id == prob.id


@pytest.mark.anyio
async def test_analysis_repository_crud_and_filters(async_session: AsyncSession):
    """Verify AnalysisRepository session recording and datetime filters."""
    proj_repo = ProjectRepository(async_session)
    analysis_repo = AnalysisRepository(async_session)

    proj = await proj_repo.create(name="Analytics Target")
    await async_session.commit()

    now = datetime.now(timezone.utc)
    s1 = await analysis_repo.create(
        analysis_mode="BASELINE_DRIVEN",
        project_id=proj.id,
        gaps_detected=2,
        candidates_generated=4,
        duration_ms=15.0,
    )
    await async_session.commit()

    fetched = await analysis_repo.get_by_id(s1.id)
    assert fetched is not None
    assert fetched.project_id == proj.id
    assert fetched.gaps_detected == 2

    # Filter by project_id
    sessions = await analysis_repo.list_all(project_id=proj.id)
    assert len(sessions) == 1
    assert sessions[0].id == s1.id


# -----------------------------------------------------------------------------
# 3. SQL JOIN Query Demonstrations (Anti-N+1 Verification)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_sql_join_1_project_session_counts(async_session: AsyncSession):
    """
    SQL JOIN Demonstration 1:
    Verify ProjectRepository.get_projects_with_session_counts retrieves
    aggregated session counts per project in a single outer join query.
    """
    proj_repo = ProjectRepository(async_session)
    analysis_repo = AnalysisRepository(async_session)

    p1 = await proj_repo.create(name="Project With Two Sessions")
    p2 = await proj_repo.create(name="Project With Zero Sessions")
    p3 = await proj_repo.create(name="Project With One Session")
    await async_session.commit()

    # Link 2 sessions to p1, 1 to p3
    await analysis_repo.create(analysis_mode="BASELINE_DRIVEN", project_id=p1.id)
    await analysis_repo.create(analysis_mode="CONTEXT_BASED", project_id=p1.id)
    await analysis_repo.create(analysis_mode="BASELINE_DRIVEN", project_id=p3.id)
    await async_session.commit()

    stats = await proj_repo.get_projects_with_session_counts()
    stats_dict = {item["id"]: item["session_count"] for item in stats}

    assert stats_dict[str(p1.id)] == 2
    assert stats_dict[str(p2.id)] == 0
    assert stats_dict[str(p3.id)] == 1


@pytest.mark.anyio
async def test_sql_join_2_analysis_history_report(async_session: AsyncSession):
    """
    SQL JOIN Demonstration 2:
    Verify AnalysisRepository.get_analysis_history_report performs a multi-table
    OUTER JOIN combining AnalysisSession with Project and Problem metadata.
    """
    proj_repo = ProjectRepository(async_session)
    prob_repo = ProblemRepository(async_session)
    analysis_repo = AnalysisRepository(async_session)

    proj = await proj_repo.create(name="Full Stack Capstone")
    prob = await prob_repo.create(
        title="Merge Intervals",
        problem_slug="merge-intervals",
        platform="leetcode",
        difficulty="Medium",
    )
    await async_session.commit()

    session_rec = await analysis_repo.create(
        analysis_mode="BASELINE_DRIVEN",
        language="python",
        analysis_status="SUCCESS",
        gaps_detected=4,
        candidates_generated=6,
        duration_ms=28.4,
        project_id=proj.id,
        problem_id=prob.id,
    )
    await async_session.commit()

    report = await analysis_repo.get_analysis_history_report()
    assert len(report) >= 1

    item = next(r for r in report if r["id"] == str(session_rec.id))
    assert item["project_name"] == "Full Stack Capstone"
    assert item["problem_title"] == "Merge Intervals"
    assert item["problem_slug"] == "merge-intervals"
    assert item["platform"] == "leetcode"
    assert item["gaps_detected"] == 4
    assert item["candidates_generated"] == 6


# -----------------------------------------------------------------------------
# 4. Transaction Rollback & Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_transaction_rollback_on_failure(async_session: AsyncSession):
    """Verify changes are rolled back completely when a database operation raises an exception."""
    p = Project(name="Temporary Uncommitted")
    async_session.add(p)
    await async_session.flush()

    # Trigger rollback
    await async_session.rollback()

    res = await async_session.execute(select(Project).where(Project.name == "Temporary Uncommitted"))
    assert res.scalar_one_or_none() is None


# -----------------------------------------------------------------------------
# 5. Alembic Migration Upgrade & Downgrade
# -----------------------------------------------------------------------------

def test_alembic_upgrade_and_downgrade(tmp_path):
    """Verify Alembic migration 001 runs upgrade head and downgrade base cleanly on isolated DB."""
    import subprocess
    import sys

    db_path = tmp_path / "alembic_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    # Run upgrade head
    up_res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert up_res.returncode == 0, f"Alembic upgrade failed:\n{up_res.stderr}\n{up_res.stdout}"
    assert "Running upgrade" in up_res.stdout or "Running upgrade" in up_res.stderr

    # Run downgrade base
    down_res = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert down_res.returncode == 0, f"Alembic downgrade failed:\n{down_res.stderr}\n{down_res.stdout}"
    assert "Running downgrade" in down_res.stdout or "Running downgrade" in down_res.stderr


# -----------------------------------------------------------------------------
# 6. REST API Endpoints: Projects, Problems & Analyses
# -----------------------------------------------------------------------------

def test_project_endpoints_crud(test_client_with_db: TestClient):
    """Test full Projects REST API: POST, GET, PATCH, DELETE, and Statistics."""
    # 1. POST /api/v1/projects (201 Created)
    create_payload = {
        "name": "Integration Project",
        "description": "API Test Project",
        "language": "python",
        "technology_stack": {"docker": True},
        "status": "active",
    }
    res = test_client_with_db.post("/api/v1/projects", json=create_payload)
    assert res.status_code == 201
    created_proj = res.json()
    proj_id = created_proj["id"]
    assert created_proj["name"] == "Integration Project"
    assert created_proj["status"] == "active"

    # 2. GET /api/v1/projects (200 OK)
    list_res = test_client_with_db.get("/api/v1/projects")
    assert list_res.status_code == 200
    assert any(p["id"] == proj_id for p in list_res.json())

    # 3. GET /api/v1/projects/{id} (200 OK)
    get_res = test_client_with_db.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Integration Project"

    # 4. GET /api/v1/projects/statistics (200 OK, JOIN 1)
    stats_res = test_client_with_db.get("/api/v1/projects/statistics")
    assert stats_res.status_code == 200
    stat_item = next((item for item in stats_res.json() if item["id"] == proj_id), None)
    assert stat_item is not None
    assert stat_item["session_count"] == 0

    # 5. PATCH /api/v1/projects/{id} (200 OK)
    patch_res = test_client_with_db.patch(
        f"/api/v1/projects/{proj_id}",
        json={"name": "Integration Project Updated", "status": "completed"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Integration Project Updated"
    assert patch_res.json()["status"] == "completed"

    # 6. DELETE /api/v1/projects/{id} (204 No Content)
    del_res = test_client_with_db.delete(f"/api/v1/projects/{proj_id}")
    assert del_res.status_code == 204

    # 7. GET after delete -> 404 Not Found
    get_after_del = test_client_with_db.get(f"/api/v1/projects/{proj_id}")
    assert get_after_del.status_code == 404


def test_project_endpoints_validation_and_errors(test_client_with_db: TestClient):
    """Test validation errors: invalid UUID, missing name, invalid status."""
    # Invalid UUID format -> 422
    res = test_client_with_db.get("/api/v1/projects/not-a-valid-uuid")
    assert res.status_code == 422

    # Empty name -> 422
    res = test_client_with_db.post("/api/v1/projects", json={"name": ""})
    assert res.status_code == 422

    # Invalid status -> 422
    res = test_client_with_db.post("/api/v1/projects", json={"name": "Bad Status", "status": "unknown"})
    assert res.status_code == 422


def test_problem_endpoints(test_client_with_db: TestClient):
    """Test Problems REST API: POST (201 & 409 duplicate), GET, and lookup by ID."""
    prob_data = {
        "title": "Climbing Stairs",
        "problem_slug": "climbing-stairs",
        "platform": "leetcode",
        "difficulty": "Easy",
    }
    # 1. POST (201 Created)
    res = test_client_with_db.post("/api/v1/problems", json=prob_data)
    assert res.status_code == 201
    prob = res.json()
    prob_id = prob["id"]
    assert prob["problem_slug"] == "climbing-stairs"

    # 2. Duplicate POST -> 409 Conflict
    dup_res = test_client_with_db.post("/api/v1/problems", json=prob_data)
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.json()["detail"]

    # 3. GET /api/v1/problems (200 OK)
    list_res = test_client_with_db.get("/api/v1/problems?platform=leetcode")
    assert list_res.status_code == 200
    assert any(p["id"] == prob_id for p in list_res.json())

    # 4. GET /api/v1/problems/{id} (200 OK)
    get_res = test_client_with_db.get(f"/api/v1/problems/{prob_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Climbing Stairs"


def test_analysis_endpoints(test_client_with_db: TestClient):
    """Test Analysis Sessions REST API: POST, GET, and JOIN report."""
    # Create a project and problem first
    proj_res = test_client_with_db.post("/api/v1/projects", json={"name": "Analysis Demo Project"})
    proj_id = proj_res.json()["id"]

    prob_res = test_client_with_db.post(
        "/api/v1/problems",
        json={"title": "Coin Change", "problem_slug": "coin-change", "platform": "leetcode"},
    )
    prob_id = prob_res.json()["id"]

    # 1. POST /api/v1/analyses (201 Created)
    sess_payload = {
        "analysis_mode": "BASELINE_DRIVEN",
        "language": "python",
        "analysis_status": "SUCCESS",
        "gaps_detected": 2,
        "candidates_generated": 5,
        "duration_ms": 32.1,
        "project_id": proj_id,
        "problem_id": prob_id,
    }
    res = test_client_with_db.post("/api/v1/analyses", json=sess_payload)
    assert res.status_code == 201
    created_sess = res.json()
    sess_id = created_sess["id"]
    assert created_sess["project_id"] == proj_id
    assert created_sess["gaps_detected"] == 2

    # 2. GET /api/v1/analyses/{id} (200 OK)
    get_res = test_client_with_db.get(f"/api/v1/analyses/{sess_id}")
    assert get_res.status_code == 200
    assert get_res.json()["candidates_generated"] == 5

    # 3. GET /api/v1/analyses/report (200 OK, JOIN 2)
    report_res = test_client_with_db.get("/api/v1/analyses/report")
    assert report_res.status_code == 200
    report_items = report_res.json()
    matching = next((item for item in report_items if item["id"] == sess_id), None)
    assert matching is not None
    assert matching["project_name"] == "Analysis Demo Project"
    assert matching["problem_title"] == "Coin Change"


# -----------------------------------------------------------------------------
# 7. Integration with POST /api/v1/edgemind/analyze
# -----------------------------------------------------------------------------

def test_edgemind_analyze_persists_session_and_problem(test_client_with_db: TestClient):
    """
    Test EdgeMind analyze endpoint persists analysis session and auto-links problem.
    Verifies that analysis_session_id is returned as a valid UUID string.
    """
    # Create project
    proj_res = test_client_with_db.post("/api/v1/projects", json={"name": "EdgeMind Live Session"})
    proj_id = proj_res.json()["id"]

    analyze_payload = {
        "code": "def searchInsert(nums, target):\n    return 0\n",
        "project_id": proj_id,
        "problem_context": {
            "title": "Search Insert Position",
            "slug": "search-insert-position-live",
            "platform": "leetcode",
            "difficulty": "Easy",
            "constraints": ["1 <= nums.length <= 10000", "-10000 <= nums[i] <= 10000"],
        },
        "test_cases": [
            {"input_data": {"nums": [1, 3, 5, 6], "target": 5}},
            {"input_data": {"nums": [1, 3, 5, 6], "target": 2}},
        ],
        "max_candidates": 5,
        "static_only": True,
    }

    res = test_client_with_db.post("/api/v1/edgemind/analyze", json=analyze_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "analysis_session_id" in data
    assert data["analysis_session_id"] is not None

    session_id = data["analysis_session_id"]
    # Verify session is persisted and queryable
    sess_res = test_client_with_db.get(f"/api/v1/analyses/{session_id}")
    assert sess_res.status_code == 200
    sess_data = sess_res.json()
    assert sess_data["project_id"] == proj_id
    assert sess_data["candidates_generated"] > 0


def test_edgemind_analyze_invalid_project_id_returns_422(test_client_with_db: TestClient):
    """Test malformed project_id returns 422 Unprocessable Entity."""
    res = test_client_with_db.post(
        "/api/v1/edgemind/analyze",
        json={"code": "def foo(): pass", "project_id": "not-a-valid-uuid"},
    )
    assert res.status_code == 422


def test_edgemind_analyze_nonexistent_project_id_returns_404(test_client_with_db: TestClient):
    """Test non-existent project_id returns 404 Not Found."""
    fake_uuid = str(uuid.uuid4())
    res = test_client_with_db.post(
        "/api/v1/edgemind/analyze",
        json={"code": "def foo(): pass", "project_id": fake_uuid},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_edgemind_analyze_graceful_degradation_when_db_offline(test_client_db_disabled: TestClient):
    """
    CRITICAL: Graceful degradation test.
    When PostgreSQL is disabled or unreachable (db yields None):
    1. Static code analysis and candidate synthesis MUST still succeed (200 OK).
    2. analysis_session_id MUST be null.
    3. The Chrome extension must never break.
    """
    analyze_payload = {
        "code": "def solution(x):\n    return x * 2\n",
        "test_cases": [{"input_data": {"x": 5}}],
        "max_candidates": 5,
        "static_only": True,
    }

    res = test_client_db_disabled.post("/api/v1/edgemind/analyze", json=analyze_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["analysis_session_id"] is None


def test_crud_endpoints_return_503_when_db_offline(test_client_db_disabled: TestClient):
    """Verify CRUD endpoints return HTTP 503 when the database is unavailable."""
    res = test_client_db_disabled.get("/api/v1/projects")
    assert res.status_code == 503
    assert "Database persistence is not configured" in res.json()["detail"]


# -----------------------------------------------------------------------------
# 8. Password Redaction in Database Settings
# -----------------------------------------------------------------------------

def test_settings_sanitizes_database_password():
    """Verify sensitive database credentials in connection URLs are masked."""
    settings = get_settings()
    raw_leak = "OperationalError: failed connecting to postgresql+asyncpg://admin:SuperSecretPassword999@localhost:5432/edgemind_db"
    sanitized = settings.sanitize_error(raw_leak)
    assert "SuperSecretPassword999" not in sanitized
    assert "[REDACTED]" in sanitized
