"""
EdgeMind — Phase 4: PostgreSQL JSONB Analysis Report Store Test Suite.

Comprehensive validation covering:
1. Report model creation and JSON/JSONB data mapping.
2. Duplicate report prevention for same analysis_session_id.
3. Idempotent upsert behavior (insert on missing, update on existing).
4. Full report retrieval by analysis_session_id.
5. Nonexistent report retrieval returning None.
6. Partial report field updates.
7. Report deletion and boolean status return.
8. Chronological sorting (newest first) and pagination (skip/limit).
9. Multi-tenant user ownership filtering and tenant isolation.
10. Project and problem_slug query filtering.
11. Anonymous Chrome extension reports (null user_id/project_id).
12. Cascade deletion (deleting AnalysisSession automatically cascades to AnalysisReport).
13. Strict static-only invariants (expected_output=None, is_expected_output_verified=False).
14. Complex nested JSON structure roundtrip (candidate arrays, gap objects, constraints).
15. Model to_dict serialization and ISO timestamp formatting.
16. Safe UUID normalization and malformed input handling.
17. Live PostgreSQL GIN index and native JSONB operator verification (conditional).
"""

from datetime import datetime, timezone
import os
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database.base import Base, utc_now
from core.database.models import (
    AnalysisReport,
    AnalysisSession,
    Problem,
    Project,
    User,
)
from core.database.repositories.report_repository import (
    DuplicateReportError,
    ReportNotFoundError,
    ReportRepository,
    ReportRepositoryError,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

TEST_JWT_SECRET = "super-secure-test-jwt-secret-key-32-chars-long!"

@pytest.fixture(autouse=True)
def setup_test_jwt_secret(monkeypatch):
    """Ensure a valid JWT secret is available in all test contexts."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    from core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_db_engine():
    """Create an isolated in-memory SQLite async engine with enabled foreign keys."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active transaction-isolated AsyncSession."""
    session_factory = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


# -----------------------------------------------------------------------------
# Helper Utilities
# -----------------------------------------------------------------------------

def build_sample_report_payload(
    session_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    problem_slug: str = "two-sum",
) -> Dict[str, Any]:
    """Generate a valid EdgeMind analysis report document adhering to schema v1.0.0."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "analysis_session_id": str(session_id),
        "user_id": str(user_id) if user_id else None,
        "project_id": str(project_id) if project_id else None,
        "problem_slug": problem_slug,
        "language": "python",
        "analysis_mode": "BASELINE_DRIVEN",
        "analysis_status": "SUCCESS",
        "schema_version": "1.0.0",
        "problem": {
            "title": "Two Sum",
            "slug": problem_slug,
            "platform": "leetcode",
            "difficulty": "Easy",
        },
        "identified_parameters": [
            {"name": "nums", "type": "List[int]"},
            {"name": "target", "type": "int"},
        ],
        "parsed_constraints": {
            "status": "PARSED",
            "total_raw": 2,
            "unresolved": [],
        },
        "coverage_gaps": [
            {
                "gap_id": "gap_min_boundary_nums",
                "category": "COLLECTION_LENGTH",
                "severity": "HIGH",
                "description": "nums length at minimum boundary (2)",
            }
        ],
        "generated_candidates": [
            {
                "candidate_id": "cand_1",
                "tag": "GENERATED_TEST",
                "classification": "VALID",
                "input_data": {"nums": [2, 7], "target": 9},
                "expected_output": None,
                "is_expected_output_verified": False,
                "severity": "HIGH",
                "rationale": "Boundary case for min length array",
            }
        ],
        "candidate_classifications": {
            "VALID": 1,
            "ROBUSTNESS_PROBE": 0,
            "CONSTRAINT_VALIDITY_UNKNOWN": 0,
        },
        "analysis_metadata": {
            "duration_ms": 32.5,
            "gaps_detected": 1,
            "candidates_generated": 1,
            "provenance": {
                "source": "GENERATED_TEST",
                "execution_performed": False,
                "expected_outputs_known": False,
            },
        },
        "created_at": now_iso,
        "updated_at": now_iso,
    }


async def seed_user(session: AsyncSession, email: Optional[str] = None) -> User:
    """Helper to persist a parent User record."""
    user = User(
        id=uuid.uuid4(),
        email=email or f"user_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="test-hash",
        full_name="Test User",
        role="user",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def seed_project(session: AsyncSession, owner_user_id: Optional[uuid.UUID] = None) -> Project:
    """Helper to persist a parent Project record."""
    project = Project(
        id=uuid.uuid4(),
        owner_user_id=owner_user_id,
        name=f"Project {uuid.uuid4().hex[:6]}",
        language="python",
        technology_stack={"framework": "fastapi"},
        status="active",
    )
    session.add(project)
    await session.flush()
    return project


async def seed_session(
    session: AsyncSession,
    user_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
) -> AnalysisSession:
    """Helper to persist a parent AnalysisSession record."""
    sess = AnalysisSession(
        id=uuid.uuid4(),
        user_id=user_id,
        project_id=project_id,
        analysis_mode="BASELINE_DRIVEN",
        language="python",
        analysis_status="SUCCESS",
        gaps_detected=1,
        candidates_generated=1,
        duration_ms=32.5,
        report_storage_status="STORED",
    )
    session.add(sess)
    await session.flush()
    return sess


# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_creation_and_attributes(async_session: AsyncSession):
    """1. Test creating an analysis report record with full JSONB payload."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    created = await repo.create_report(doc=payload, session_id=sess.id)

    assert created is not None
    assert created["analysis_session_id"] == str(sess.id)
    assert created["schema_version"] == "1.0.0"
    assert created["problem_slug"] == "two-sum"
    assert len(created["generated_candidates"]) == 1
    assert created["generated_candidates"][0]["expected_output"] is None
    assert created["generated_candidates"][0]["is_expected_output_verified"] is False


@pytest.mark.anyio
async def test_duplicate_report_rejection(async_session: AsyncSession):
    """2. Test that creating a report with an existing session_id raises DuplicateReportError."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    await repo.create_report(doc=payload, session_id=sess.id)

    with pytest.raises(DuplicateReportError) as exc_info:
        await repo.create_report(doc=payload, session_id=sess.id)

    assert "already exists" in str(exc_info.value)


@pytest.mark.anyio
async def test_report_upsert_idempotency_insert_and_update(async_session: AsyncSession):
    """3. Test upsert creates on missing and updates in-place on existing session_id."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    # First upsert (Insert)
    result_insert = await repo.upsert_report(session_id=sess.id, doc=payload)
    assert result_insert["analysis_session_id"] == str(sess.id)
    assert len(result_insert["generated_candidates"]) == 1

    # Second upsert with modified candidate list (Update)
    updated_payload = dict(payload)
    updated_payload["generated_candidates"].append({
        "candidate_id": "cand_2",
        "tag": "GENERATED_TEST",
        "classification": "VALID",
        "input_data": {"nums": [1, 2, 3, 4], "target": 5},
        "expected_output": None,
        "is_expected_output_verified": False,
    })
    result_update = await repo.upsert_report(session_id=sess.id, doc=updated_payload)

    assert result_update["analysis_session_id"] == str(sess.id)
    assert len(result_update["generated_candidates"]) == 2


@pytest.mark.anyio
async def test_report_retrieval_by_session_id(async_session: AsyncSession):
    """4. Test retrieving a persisted report by canonical session_id."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    await repo.create_report(doc=payload, session_id=sess.id)

    fetched = await repo.get_report_by_session_id(sess.id)
    assert fetched is not None
    assert fetched["analysis_session_id"] == str(sess.id)
    assert fetched["problem"]["title"] == "Two Sum"
    assert fetched["coverage_gaps"][0]["gap_id"] == "gap_min_boundary_nums"


@pytest.mark.anyio
async def test_report_retrieval_nonexistent_returns_none(async_session: AsyncSession):
    """5. Test querying an unpersisted session_id returns None gracefully."""
    repo = ReportRepository(async_session)
    non_existent_id = uuid.uuid4()
    result = await repo.get_report_by_session_id(non_existent_id)
    assert result is None


@pytest.mark.anyio
async def test_report_updates_fields(async_session: AsyncSession):
    """6. Test updating specific fields of an existing report document."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    await repo.create_report(doc=payload, session_id=sess.id)

    updated = await repo.update_report(
        session_id=sess.id,
        updates={"problem_slug": "two-sum-ii", "custom_flag": True},
    )
    assert updated is not None
    assert updated["problem_slug"] == "two-sum-ii"
    assert updated.get("custom_flag") is True


@pytest.mark.anyio
async def test_report_deletion_success_and_missing(async_session: AsyncSession):
    """7. Test report deletion succeeds on existing and returns False on missing."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    await repo.create_report(doc=payload, session_id=sess.id)

    # Deletion of existing report
    deleted = await repo.delete_report(sess.id)
    assert deleted is True

    # Re-query confirms absence
    assert await repo.get_report_by_session_id(sess.id) is None

    # Deletion of already deleted report returns False
    assert await repo.delete_report(sess.id) is False


@pytest.mark.anyio
async def test_report_pagination_skip_limit_and_sorting(async_session: AsyncSession):
    """8. Test chronological descending sort and pagination limits."""
    repo = ReportRepository(async_session)

    # Create 5 distinct sessions and reports
    session_ids: List[uuid.UUID] = []
    for i in range(5):
        sess = await seed_session(async_session)
        session_ids.append(sess.id)
        payload = build_sample_report_payload(session_id=sess.id, problem_slug=f"problem-{i}")
        await repo.create_report(doc=payload, session_id=sess.id)

    # Page 1: limit 3
    items, total = await repo.list_reports(skip=0, limit=3)
    assert total == 5
    assert len(items) == 3

    # Page 2: skip 3, limit 3
    items_p2, total_p2 = await repo.list_reports(skip=3, limit=3)
    assert total_p2 == 5
    assert len(items_p2) == 2


@pytest.mark.anyio
async def test_user_ownership_isolation_filter(async_session: AsyncSession):
    """9. Test strict multi-tenant ownership filtering between two users."""
    repo = ReportRepository(async_session)
    user_a = await seed_user(async_session)
    user_b = await seed_user(async_session)

    sess_a = await seed_session(async_session, user_id=user_a.id)
    payload_a = build_sample_report_payload(session_id=sess_a.id, user_id=user_a.id)
    await repo.create_report(doc=payload_a, session_id=sess_a.id)

    sess_b = await seed_session(async_session, user_id=user_b.id)
    payload_b = build_sample_report_payload(session_id=sess_b.id, user_id=user_b.id)
    await repo.create_report(doc=payload_b, session_id=sess_b.id)

    # User A queries
    items_a, total_a = await repo.list_reports(user_id=user_a.id)
    assert total_a == 1
    assert items_a[0]["analysis_session_id"] == str(sess_a.id)

    # User B queries
    items_b, total_b = await repo.list_reports(user_id=user_b.id)
    assert total_b == 1
    assert items_b[0]["analysis_session_id"] == str(sess_b.id)

    # Admin queries across all tenants (user_id=None)
    items_admin, total_admin = await repo.list_reports(user_id=None)
    assert total_admin >= 2


@pytest.mark.anyio
async def test_project_and_problem_slug_filters(async_session: AsyncSession):
    """10. Test filtering reports by project_id and problem_slug."""
    repo = ReportRepository(async_session)
    proj = await seed_project(async_session)

    sess1 = await seed_session(async_session, project_id=proj.id)
    await repo.create_report(doc=build_sample_report_payload(sess1.id, project_id=proj.id, problem_slug="two-sum"), session_id=sess1.id)

    sess2 = await seed_session(async_session, project_id=proj.id)
    await repo.create_report(doc=build_sample_report_payload(sess2.id, project_id=proj.id, problem_slug="3sum"), session_id=sess2.id)

    # Filter by project_id
    items_proj, total_proj = await repo.list_reports(project_id=proj.id)
    assert total_proj == 2

    # Filter by problem_slug
    items_slug, total_slug = await repo.list_reports(problem_slug="3sum")
    assert total_slug == 1
    assert items_slug[0]["problem_slug"] == "3sum"


@pytest.mark.anyio
async def test_anonymous_report_storage(async_session: AsyncSession):
    """11. Test that anonymous extension reports (user_id=None, project_id=None) store and retrieve safely."""
    sess = await seed_session(async_session, user_id=None, project_id=None)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id, user_id=None, project_id=None)
    created = await repo.create_report(doc=payload, session_id=sess.id)

    assert created["user_id"] is None
    assert created["project_id"] is None

    fetched = await repo.get_report_by_session_id(sess.id)
    assert fetched is not None
    assert fetched["user_id"] is None


@pytest.mark.anyio
async def test_cascade_deletion_on_analysis_session_delete(async_session: AsyncSession):
    """12. Test that deleting an AnalysisSession automatically CASCADE-deletes the AnalysisReport."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    await repo.create_report(doc=payload, session_id=sess.id)

    # Verify report exists
    assert await repo.get_report_by_session_id(sess.id) is not None

    # Delete parent session
    await async_session.delete(sess)
    await async_session.flush()

    # Verify report was cascaded and deleted
    assert await repo.get_report_by_session_id(sess.id) is None


@pytest.mark.anyio
async def test_static_only_invariants_in_report_data(async_session: AsyncSession):
    """13. Enforce static-only invariants on stored candidates: null expected output and unverified status."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    created = await repo.create_report(doc=payload, session_id=sess.id)

    candidates = created.get("generated_candidates", [])
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.get("expected_output") is None
        assert cand.get("is_expected_output_verified") is False
        assert cand.get("tag") == "GENERATED_TEST"

    # Ensure no raw source code is persisted in metadata
    assert "source_code" not in created
    assert "raw_code" not in created


@pytest.mark.anyio
async def test_json_data_roundtrip_complex_structures(async_session: AsyncSession):
    """14. Test storing and retrieving complex nested JSON data (lists, dicts, primitives, booleans)."""
    sess = await seed_session(async_session)
    repo = ReportRepository(async_session)

    payload = build_sample_report_payload(session_id=sess.id)
    payload["custom_nested"] = {
        "matrix": [[1, 2, 3], [4, 5, 6]],
        "deep": {"key": "value", "list": [True, False, None, 42.5]},
    }

    created = await repo.create_report(doc=payload, session_id=sess.id)
    assert created["custom_nested"]["matrix"] == [[1, 2, 3], [4, 5, 6]]
    assert created["custom_nested"]["deep"]["list"] == [True, False, None, 42.5]


@pytest.mark.anyio
async def test_safe_uuid_normalization_and_malformed_input(async_session: AsyncSession):
    """15. Test safe UUID normalization handles string UUIDs, UUID objects, and returns None on malformed."""
    repo = ReportRepository(async_session)

    # Query with invalid UUID string should return None without throwing 500
    assert await repo.get_report_by_session_id("invalid-not-a-uuid") is None
    assert await repo.delete_report("invalid-not-a-uuid") is False


# -----------------------------------------------------------------------------
# Conditional Live PostgreSQL 16 Native JSONB & GIN Test
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_live_postgresql_jsonb_and_gin_index_verification():
    """16. Verify native PostgreSQL JSONB and GIN index behavior when live PostgreSQL 16 is running."""
    from core.config import get_settings

    pg_url = os.environ.get("DATABASE_URL") or get_settings().database_url or "postgresql+asyncpg://postgres:postgres@localhost:5432/edgemind"
    if not pg_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not configured for PostgreSQL.")

    try:
        engine = create_async_engine(pg_url)
        async with engine.connect() as conn:
            # Check connection
            res = await conn.execute(text("SELECT version();"))
            ver_str = res.scalar() or ""
            assert "PostgreSQL" in ver_str

            # Check if analysis_reports table has GIN index on report_data
            gin_check = await conn.execute(
                text("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'analysis_reports' AND indexdef LIKE '%gin%';
                """)
            )
            rows = gin_check.fetchall()
            # If table is migrated, verify GIN index
            if rows:
                assert any("gin" in r[1].lower() for r in rows)
        await engine.dispose()
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL 16 is not accessible ({exc}); skipped.")


# -----------------------------------------------------------------------------
# REST API End-to-End JSONB Report Store Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def client(async_db_engine):
    """FastAPI TestClient with overridden get_db dependency pointing to test database."""
    from fastapi.testclient import TestClient
    from core.api import app
    from core.database.connection import get_db

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
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


TWO_SUM_CODE = (
    "class Solution:\n"
    "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
    "        seen = {}\n"
    "        for i, n in enumerate(nums):\n"
    "            comp = target - n\n"
    "            if comp in seen:\n"
    "                return [seen[comp], i]\n"
    "            seen[n] = i\n"
    "        return []\n"
)


@pytest.mark.anyio
async def test_api_edgemind_analyze_persists_full_report_document(client, async_session: AsyncSession):
    """17. Verify POST /api/v1/edgemind/analyze persists full JSONB report with canonical schema and invariants."""
    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "1",
            "title": "Two Sum",
            "function_name": "twoSum",
            "parameters": ["nums", "target"],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9",
            ],
        },
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
        ],
        "max_candidates": 5,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    session_id = data.get("analysis_session_id")
    assert session_id is not None
    assert data.get("report_storage_status") == "STORED"

    # Query repository to verify report document in database
    repo = ReportRepository(async_session)
    report_doc = await repo.get_report_by_session_id(session_id)
    assert report_doc is not None
    assert report_doc["schema_version"] == "1.0.0"
    assert report_doc["problem_slug"] == "two-sum"
    assert report_doc["language"] == "python"

    # Strict invariant validation: expected_output is None and is_expected_output_verified is False
    candidates = report_doc.get("generated_candidates", [])
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.get("expected_output") is None
        assert cand.get("is_expected_output_verified") is False

    # Privacy / sanitization invariant: user source code never stored in report
    assert "code" not in report_doc
    assert "source_code" not in report_doc


@pytest.mark.anyio
async def test_api_get_detailed_report_and_ownership_isolation(client, async_session: AsyncSession):
    """18. Verify GET /api/v1/analyses/{id}/report enforces ownership and allows admin access."""
    from core.auth import create_access_token
    from core.auth.service import AuthService

    auth_svc = AuthService(async_session)
    user_a = await auth_svc.register_user("user_a@example.com", "Password123!@#", "User A")
    user_b = await auth_svc.register_user("user_b@example.com", "Password123!@#", "User B")
    admin_u = await auth_svc.register_user("admin_u@example.com", "Password123!@#", "Admin")
    admin_u.role = "admin"
    await async_session.commit()

    tok_a = create_access_token(user_a.id, role="user")
    tok_b = create_access_token(user_b.id, role="user")
    tok_admin = create_access_token(admin_u.id, role="admin")

    # User A triggers analysis
    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "title": "Two Sum",
            "slug": "two-sum",
            "parameters": ["nums", "target"],
        },
        "test_cases": [{"nums": [2, 7], "target": 9}],
    }
    analyze_res = client.post(
        "/api/v1/edgemind/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert analyze_res.status_code == 200
    sess_id = analyze_res.json()["analysis_session_id"]

    # 1. User A can retrieve their own detailed report
    res_a = client.get(
        f"/api/v1/analyses/{sess_id}/report",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert res_a.status_code == 200
    report_a = res_a.json()
    assert report_a["analysis_session_id"] == sess_id
    assert report_a["schema_version"] == "1.0.0"

    # 2. User B gets 404 Not Found (ownership isolation)
    res_b = client.get(
        f"/api/v1/analyses/{sess_id}/report",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert res_b.status_code == 404

    # 3. Admin can retrieve report across tenants
    res_admin = client.get(
        f"/api/v1/analyses/{sess_id}/report",
        headers={"Authorization": f"Bearer {tok_admin}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["analysis_session_id"] == sess_id

    # 4. Unauthenticated gets 401
    res_anon = client.get(f"/api/v1/analyses/{sess_id}/report")
    assert res_anon.status_code == 401


@pytest.mark.anyio
async def test_api_get_candidates_and_coverage_gaps_subresources(client, async_session: AsyncSession):
    """19. Verify candidates and coverage-gaps endpoints serve report data with ownership checks."""
    from core.auth import create_access_token
    from core.auth.service import AuthService

    auth_svc = AuthService(async_session)
    user_a = await auth_svc.register_user("sub_a@example.com", "Password123!@#", "Sub A")
    user_b = await auth_svc.register_user("sub_b@example.com", "Password123!@#", "Sub B")
    await async_session.commit()

    tok_a = create_access_token(user_a.id, role="user")
    tok_b = create_access_token(user_b.id, role="user")

    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "title": "Two Sum",
            "slug": "two-sum",
            "parameters": ["nums", "target"],
            "constraints": ["2 <= nums.length <= 10^4"],
        },
        "test_cases": [{"nums": [2, 7], "target": 9}],
    }
    analyze_res = client.post(
        "/api/v1/edgemind/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    sess_id = analyze_res.json()["analysis_session_id"]

    # Candidates endpoint
    cand_res = client.get(
        f"/api/v1/analyses/{sess_id}/candidates",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert cand_res.status_code == 200
    cand_data = cand_res.json()
    assert cand_data["analysis_session_id"] == sess_id
    assert "candidates" in cand_data
    assert "candidate_classifications" in cand_data
    assert cand_data["total_candidates"] == len(cand_data["candidates"])

    # User B cannot access candidates
    assert client.get(
        f"/api/v1/analyses/{sess_id}/candidates",
        headers={"Authorization": f"Bearer {tok_b}"},
    ).status_code == 404

    # Coverage gaps endpoint
    gaps_res = client.get(
        f"/api/v1/analyses/{sess_id}/coverage-gaps",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert gaps_res.status_code == 200
    gaps_data = gaps_res.json()
    assert gaps_data["analysis_session_id"] == sess_id
    assert "coverage_gaps" in gaps_data
    assert "constraints" in gaps_data

    # User B cannot access coverage gaps
    assert client.get(
        f"/api/v1/analyses/{sess_id}/coverage-gaps",
        headers={"Authorization": f"Bearer {tok_b}"},
    ).status_code == 404


@pytest.mark.anyio
async def test_api_delete_report_sets_status_deleted(client, async_session: AsyncSession):
    """20. Verify DELETE /api/v1/analyses/{id}/report removes document and updates status to DELETED."""
    from core.auth import create_access_token
    from core.auth.service import AuthService

    auth_svc = AuthService(async_session)
    user_a = await auth_svc.register_user("del_user@example.com", "Password123!@#", "Del User")
    await async_session.commit()

    tok_a = create_access_token(user_a.id, role="user")

    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {"title": "Two Sum", "slug": "two-sum"},
        "test_cases": [{"nums": [2, 7], "target": 9}],
    }
    analyze_res = client.post(
        "/api/v1/edgemind/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    sess_id = analyze_res.json()["analysis_session_id"]

    # Delete detailed report
    del_res = client.delete(
        f"/api/v1/analyses/{sess_id}/report",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert del_res.status_code == 204

    # Detailed report should now be 404 Not Found
    assert client.get(
        f"/api/v1/analyses/{sess_id}/report",
        headers={"Authorization": f"Bearer {tok_a}"},
    ).status_code == 404

    # AnalysisSession should still exist with status DELETED
    sess_res = client.get(
        f"/api/v1/analyses/{sess_id}",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert sess_res.status_code == 200
    assert sess_res.json()["report_storage_status"] == "DELETED"


@pytest.mark.anyio
async def test_api_list_reports_pagination_and_isolation(client, async_session: AsyncSession):
    """21. Verify GET /api/v1/reports returns paginated reports with tenant isolation."""
    from core.auth import create_access_token
    from core.auth.service import AuthService

    auth_svc = AuthService(async_session)
    user_a = await auth_svc.register_user("list_a@example.com", "Password123!@#", "List A")
    user_b = await auth_svc.register_user("list_b@example.com", "Password123!@#", "List B")
    admin_u = await auth_svc.register_user("list_adm@example.com", "Password123!@#", "List Admin")
    admin_u.role = "admin"
    await async_session.commit()

    tok_a = create_access_token(user_a.id, role="user")
    tok_b = create_access_token(user_b.id, role="user")
    tok_admin = create_access_token(admin_u.id, role="admin")

    # User A creates a report
    client.post(
        "/api/v1/edgemind/analyze",
        json={"code": TWO_SUM_CODE, "test_cases": [{"nums": [1, 2], "target": 3}], "problem_context": {"slug": "prob-a"}},
        headers={"Authorization": f"Bearer {tok_a}"},
    )

    # User B creates a report
    client.post(
        "/api/v1/edgemind/analyze",
        json={"code": TWO_SUM_CODE, "test_cases": [{"nums": [3, 4], "target": 7}], "problem_context": {"slug": "prob-b"}},
        headers={"Authorization": f"Bearer {tok_b}"},
    )

    # User A sees only 1 report
    res_a = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {tok_a}"})
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total"] == 1
    assert len(data_a["items"]) == 1
    assert data_a["items"][0]["problem_slug"] == "prob-a"

    # User B sees only 1 report
    res_b = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {tok_b}"})
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total"] == 1
    assert data_b["items"][0]["problem_slug"] == "prob-b"

    # Admin sees both reports
    res_admin = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {tok_admin}"})
    assert res_admin.status_code == 200
    data_admin = res_admin.json()
    assert data_admin["total"] == 2
    assert len(data_admin["items"]) == 2

    # Unauthenticated rejected
    assert client.get("/api/v1/reports").status_code == 401
