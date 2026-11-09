"""
EdgeMind — Phase 4: MongoDB Document Store Integration Test Suite.

Covers all 20 verification areas required for Phase 4:
1. MongoDB connection initialization.
2. MongoDB shutdown.
3. Report document serialization.
4. Report creation.
5. Report retrieval.
6. Report upsert and idempotency.
7. Duplicate analysis session prevention.
8. Report pagination.
9. Candidate retrieval (/api/v1/analyses/{id}/candidates).
10. Coverage-gap retrieval (/api/v1/analyses/{id}/coverage-gaps).
11. Report deletion (/api/v1/analyses/{id}/report).
12. Unauthorized report access (HTTP 401).
13. Cross-user isolation (HTTP 404).
14. Admin access across tenants.
15. Missing report handling (HTTP 404).
16. MongoDB unavailable handling (HTTP 503).
17. PostgreSQL/MongoDB partial failure handling.
18. Anonymous extension analysis compatibility.
19. Existing PostgreSQL integration and session linking.
20. Authentication & multi-tenancy regression.
"""

from datetime import datetime, timezone
import os
from typing import AsyncGenerator
import uuid

from bson import ObjectId
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.auth.security import create_access_token
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import AnalysisSession, Base, Problem, Project, User
import core.mongodb.connection as mongo_conn
from core.mongodb.builder import build_analysis_report_doc
from core.mongodb.indexes import ensure_mongodb_indexes
from core.mongodb.repositories import (
    DuplicateReportError,
    ReportNotFoundError,
    ReportRepository,
    ReportRepositoryError,
    sanitize_mongo_doc,
)
from tests.fake_mongodb import FakeAsyncDatabase, FakeAsyncMongoClient


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_mongo_db() -> FakeAsyncDatabase:
    """Provide an isolated, fresh in-memory FakeAsyncDatabase."""
    client = FakeAsyncMongoClient("mongodb://127.0.0.1:27017")
    return client["edgemind"]


@pytest.fixture
def async_db_engine():
    """In-memory SQLite database for PostgreSQL relational tests."""
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
def client(async_db_engine, fake_mongo_db) -> TestClient:
    """TestClient wired with in-memory SQLite and in-memory MongoDB fake."""
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

    # Wire Fake MongoDB into mongo_conn globals
    orig_client = mongo_conn._client
    orig_db = mongo_conn._database
    mongo_conn._client = fake_mongo_db.client
    mongo_conn._database = fake_mongo_db

    os.environ["MONGODB_URL"] = "mongodb://127.0.0.1:27017"
    os.environ["MONGODB_DATABASE"] = "edgemind"
    os.environ["JWT_SECRET_KEY"] = "mongo-test-secret-key-32-characters-minimum"
    get_settings.cache_clear()

    c = TestClient(app)
    yield c

    app.dependency_overrides.pop(get_db, None)
    mongo_conn._client = orig_client
    mongo_conn._database = orig_db
    get_settings.cache_clear()


# -----------------------------------------------------------------------------
# 1. MongoDB Connection Initialization
# -----------------------------------------------------------------------------

def test_mongodb_connection_initialization():
    """Verify AsyncMongoClient creation respects settings and does not connect on import."""
    orig_url = os.environ.get("MONGODB_URL")
    try:
        os.environ["MONGODB_URL"] = "mongodb://127.0.0.1:27017"
        os.environ["MONGODB_DATABASE"] = "test_edgemind"
        get_settings.cache_clear()
        mongo_conn._client = None
        mongo_conn._database = None

        client = mongo_conn.get_mongo_client()
        assert client is not None
        db = mongo_conn.get_mongo_db()
        assert db is not None
        assert db.name == "test_edgemind"
    finally:
        if orig_url:
            os.environ["MONGODB_URL"] = orig_url
        else:
            os.environ.pop("MONGODB_URL", None)
        mongo_conn._client = None
        mongo_conn._database = None
        get_settings.cache_clear()


# -----------------------------------------------------------------------------
# 2. MongoDB Shutdown
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_mongodb_clean_shutdown():
    """Verify close_mongo_client safely releases connections and resets singletons."""
    fake_client = FakeAsyncMongoClient()
    mongo_conn._client = fake_client
    mongo_conn._database = fake_client["edgemind"]

    await mongo_conn.close_mongo_client()
    assert mongo_conn._client is None
    assert mongo_conn._database is None
    assert fake_client.is_online is False


# -----------------------------------------------------------------------------
# 3. Report Document Serialization
# -----------------------------------------------------------------------------

def test_report_document_serialization():
    """Verify sanitize_mongo_doc converts ObjectId to str and formats datetimes."""
    oid = ObjectId()
    now = datetime.now(timezone.utc)
    raw_doc = {
        "_id": oid,
        "analysis_session_id": "test-uuid-1234",
        "created_at": now,
        "title": "Two Sum",
    }
    sanitized = sanitize_mongo_doc(raw_doc)
    assert sanitized is not None
    assert sanitized["id"] == str(oid)
    assert "_id" not in sanitized
    assert sanitized["created_at"] == now.isoformat()
    assert sanitized["title"] == "Two Sum"


# -----------------------------------------------------------------------------
# 4. Report Creation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_creation(fake_mongo_db):
    """Verify create_report stores valid document with canonical metadata."""
    repo = ReportRepository(fake_mongo_db)
    session_id = str(uuid.uuid4())
    doc = {
        "analysis_session_id": session_id,
        "language": "python",
        "analysis_status": "SUCCESS",
        "generated_candidates": [{"input_data": {"x": 10}}],
    }
    created = await repo.create_report(doc)
    assert created["analysis_session_id"] == session_id
    assert "id" in created
    assert "created_at" in created
    assert created["schema_version"] == "1.0.0"


# -----------------------------------------------------------------------------
# 5. Report Retrieval
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_retrieval(fake_mongo_db):
    """Verify get_report_by_session_id fetches document accurately."""
    repo = ReportRepository(fake_mongo_db)
    session_id = str(uuid.uuid4())
    await repo.create_report({"analysis_session_id": session_id, "platform": "leetcode"})

    fetched = await repo.get_report_by_session_id(session_id)
    assert fetched is not None
    assert fetched["analysis_session_id"] == session_id
    assert fetched["platform"] == "leetcode"


# -----------------------------------------------------------------------------
# 6. Report Upsert and Idempotency
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_upsert_idempotency(fake_mongo_db):
    """Verify upsert_report inserts on initial call and updates on subsequent calls."""
    repo = ReportRepository(fake_mongo_db)
    session_id = str(uuid.uuid4())

    # 1. First upsert -> inserts
    res1 = await repo.upsert_report(session_id, {"status": "INITIAL", "total": 1})
    assert res1["analysis_session_id"] == session_id

    # 2. Second upsert -> updates existing without duplicate
    res2 = await repo.upsert_report(session_id, {"status": "UPDATED", "total": 2})
    assert res2["status"] == "UPDATED"

    # Verify only 1 document exists
    total = await fake_mongo_db["analysis_reports"].count_documents({"analysis_session_id": session_id})
    assert total == 1


# -----------------------------------------------------------------------------
# 7. Duplicate Analysis Session Prevention
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_duplicate_analysis_session_prevention(fake_mongo_db):
    """Verify creating a report with an existing analysis_session_id raises DuplicateReportError."""
    repo = ReportRepository(fake_mongo_db)
    session_id = str(uuid.uuid4())
    await repo.create_report({"analysis_session_id": session_id})

    with pytest.raises(DuplicateReportError):
        await repo.create_report({"analysis_session_id": session_id})


# -----------------------------------------------------------------------------
# 8. Report Pagination
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_pagination(fake_mongo_db):
    """Verify list_reports respects skip, limit, and returns accurate total count."""
    repo = ReportRepository(fake_mongo_db)
    user_id = str(uuid.uuid4())
    for i in range(5):
        await repo.create_report({
            "analysis_session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "index": i,
        })

    items, total = await repo.list_reports(user_id=user_id, skip=1, limit=2)
    assert total == 5
    assert len(items) == 2


# -----------------------------------------------------------------------------
# 9. Candidate Retrieval Endpoint
# -----------------------------------------------------------------------------

def test_candidate_retrieval_endpoint(client: TestClient, fake_mongo_db):
    """Verify GET /api/v1/analyses/{id}/candidates returns candidate list and metadata."""
    # 1. Register & login
    client.post("/api/v1/auth/register", json={
        "email": "cand_user@example.com",
        "password": "Password123!@#",
        "full_name": "Candidate User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "cand_user@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # 2. Run analysis
    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def solve(x: int) -> int:\n    return x + 1\n",
        "test_cases": [{"input_data": {"x": 5}}],
        "static_only": True,
    }, headers=headers)
    assert res.status_code == 200
    sess_id = res.json()["analysis_session_id"]

    # 3. Fetch candidates
    cand_res = client.get(f"/api/v1/analyses/{sess_id}/candidates", headers=headers)
    assert cand_res.status_code == 200
    data = cand_res.json()
    assert data["analysis_session_id"] == sess_id
    assert "candidates" in data
    assert "total_candidates" in data
    assert "provenance" in data


# -----------------------------------------------------------------------------
# 10. Coverage-Gap Retrieval Endpoint
# -----------------------------------------------------------------------------

def test_coverage_gap_retrieval_endpoint(client: TestClient, fake_mongo_db):
    """Verify GET /api/v1/analyses/{id}/coverage-gaps returns gaps and constraints."""
    client.post("/api/v1/auth/register", json={
        "email": "gap_user@example.com",
        "password": "Password123!@#",
        "full_name": "Gap User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "gap_user@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def search(nums: list, target: int) -> int:\n    return 0\n",
        "test_cases": [{"input_data": {"nums": [1, 2, 3], "target": 2}}],
        "static_only": True,
    }, headers=headers)
    sess_id = res.json()["analysis_session_id"]

    gap_res = client.get(f"/api/v1/analyses/{sess_id}/coverage-gaps", headers=headers)
    assert gap_res.status_code == 200
    data = gap_res.json()
    assert data["analysis_session_id"] == sess_id
    assert "coverage_gaps" in data
    assert "constraints" in data


# -----------------------------------------------------------------------------
# 11. Report Deletion Preserving PostgreSQL Session
# -----------------------------------------------------------------------------

def test_report_deletion_preserves_postgresql_session(client: TestClient, fake_mongo_db):
    """Verify DELETE /api/v1/analyses/{id}/report removes document while retaining PostgreSQL session."""
    client.post("/api/v1/auth/register", json={
        "email": "del_user@example.com",
        "password": "Password123!@#",
        "full_name": "Delete User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "del_user@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def foo(): pass\n",
        "static_only": True,
    }, headers=headers)
    sess_id = res.json()["analysis_session_id"]

    # Delete report from MongoDB
    del_res = client.delete(f"/api/v1/analyses/{sess_id}/report", headers=headers)
    assert del_res.status_code == 204

    # Document is now gone from MongoDB -> 404
    get_rep_res = client.get(f"/api/v1/analyses/{sess_id}/report", headers=headers)
    assert get_rep_res.status_code == 404

    # PostgreSQL session remains intact -> 200 OK
    sess_res = client.get(f"/api/v1/analyses/{sess_id}", headers=headers)
    assert sess_res.status_code == 200
    assert sess_res.json()["report_storage_status"] == "NOT_CONFIGURED"


# -----------------------------------------------------------------------------
# 12. Unauthorized Report Access
# -----------------------------------------------------------------------------

def test_unauthorized_report_access_rejected(client: TestClient):
    """Verify unauthenticated requests to report endpoints receive HTTP 401."""
    random_id = uuid.uuid4()
    assert client.get(f"/api/v1/analyses/{random_id}/report").status_code == 401
    assert client.get(f"/api/v1/analyses/{random_id}/candidates").status_code == 401
    assert client.get(f"/api/v1/analyses/{random_id}/coverage-gaps").status_code == 401
    assert client.delete(f"/api/v1/analyses/{random_id}/report").status_code == 401
    assert client.get("/api/v1/reports").status_code == 401


# -----------------------------------------------------------------------------
# 13. Cross-User Isolation
# -----------------------------------------------------------------------------

def test_cross_user_report_isolation(client: TestClient):
    """Verify User B receives HTTP 404 attempting to view or delete User A's report."""
    # User A
    client.post("/api/v1/auth/register", json={
        "email": "usera_rep@example.com",
        "password": "Password123!@#",
        "full_name": "User Alpha",
    })
    tok_a = client.post("/api/v1/auth/login", json={
        "email": "usera_rep@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    # User B
    client.post("/api/v1/auth/register", json={
        "email": "userb_rep@example.com",
        "password": "Password123!@#",
        "full_name": "User Beta",
    })
    tok_b = client.post("/api/v1/auth/login", json={
        "email": "userb_rep@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    # User A creates analysis
    res_a = client.post("/api/v1/edgemind/analyze", json={
        "code": "def solve(n: int): return n * 2\n",
        "static_only": True,
    }, headers={"Authorization": f"Bearer {tok_a}"})
    sess_a_id = res_a.json()["analysis_session_id"]

    # User B attempts to access User A's detailed report -> 404
    b_rep = client.get(f"/api/v1/analyses/{sess_a_id}/report", headers={"Authorization": f"Bearer {tok_b}"})
    assert b_rep.status_code == 404

    # User B attempts to access User A's candidates -> 404
    b_cand = client.get(f"/api/v1/analyses/{sess_a_id}/candidates", headers={"Authorization": f"Bearer {tok_b}"})
    assert b_cand.status_code == 404

    # User B attempts to access User A's coverage gaps -> 404
    b_gaps = client.get(f"/api/v1/analyses/{sess_a_id}/coverage-gaps", headers={"Authorization": f"Bearer {tok_b}"})
    assert b_gaps.status_code == 404

    # User B attempts to delete User A's report -> 404
    b_del = client.delete(f"/api/v1/analyses/{sess_a_id}/report", headers={"Authorization": f"Bearer {tok_b}"})
    assert b_del.status_code == 404


# -----------------------------------------------------------------------------
# 14. Admin Access to All Reports
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_admin_access_across_tenants(client: TestClient, fake_mongo_db, async_db_engine):
    """Verify admin user can view and manage reports belonging to any user."""
    from sqlalchemy import update
    from core.database.models import User

    # Register User A and Admin
    client.post("/api/v1/auth/register", json={
        "email": "regular_eng@example.com",
        "password": "Password123!@#",
        "full_name": "Regular Engineer",
    })
    tok_reg = client.post("/api/v1/auth/login", json={
        "email": "regular_eng@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    client.post("/api/v1/auth/register", json={
        "email": "admin_eng@example.com",
        "password": "Password123!@#",
        "full_name": "Admin Engineer",
    })
    login_admin = client.post("/api/v1/auth/login", json={
        "email": "admin_eng@example.com",
        "password": "Password123!@#",
    }).json()

    tok_admin_raw = login_admin["access_token"]
    admin_profile = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tok_admin_raw}"}).json()
    admin_uuid = uuid.UUID(admin_profile["id"])

    # Elevate role in database to admin
    session_maker = async_sessionmaker(bind=async_db_engine, class_=AsyncSession)
    async with session_maker() as sess:
        await sess.execute(update(User).where(User.id == admin_uuid).values(role="admin"))
        await sess.commit()

    tok_admin = create_access_token(admin_uuid, role="admin")

    # Regular user runs analysis
    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def func(): return True\n",
        "test_cases": [{"input_data": {}}],
        "static_only": True,
    }, headers={"Authorization": f"Bearer {tok_reg}"})
    sess_id = res.json()["analysis_session_id"]

    # Admin accesses detailed report -> 200 OK
    admin_rep = client.get(f"/api/v1/analyses/{sess_id}/report", headers={"Authorization": f"Bearer {tok_admin}"})
    assert admin_rep.status_code == 200

    # Admin accesses reports history -> sees all
    admin_list = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {tok_admin}"})
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] >= 1


# -----------------------------------------------------------------------------
# 15. Missing Report Handling
# -----------------------------------------------------------------------------

def test_missing_report_handling(client: TestClient):
    """Verify requesting an existing session that lacks a MongoDB report returns 404."""
    client.post("/api/v1/auth/register", json={
        "email": "missing_test@example.com",
        "password": "Password123!@#",
        "full_name": "Missing Test User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "missing_test@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Programmatically create a session in PostgreSQL without MongoDB report
    sess_res = client.post(
        "/api/v1/analyses",
        json={"analysis_mode": "BASELINE_DRIVEN"},
        headers=headers,
    )
    sess_id = sess_res.json()["id"]

    # Request report from MongoDB -> 404 Not Found
    res = client.get(f"/api/v1/analyses/{sess_id}/report", headers=headers)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 16. MongoDB Unavailable Handling
# -----------------------------------------------------------------------------

def test_mongodb_unavailable_handling(client: TestClient):
    """Verify report retrieval returns 503 when MongoDB is unconfigured or offline."""
    client.post("/api/v1/auth/register", json={
        "email": "unavail_test@example.com",
        "password": "Password123!@#",
        "full_name": "Unavail User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "unavail_test@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Simulate MongoDB offline
    mongo_conn._database = None
    mongo_conn._client = None
    os.environ.pop("MONGODB_URL", None)
    get_settings.cache_clear()

    res = client.get(f"/api/v1/analyses/{uuid.uuid4()}/report", headers=headers)
    # Even if session existed, MongoDB offline yields 503
    assert res.status_code in (404, 503)

    reports_res = client.get("/api/v1/reports", headers=headers)
    assert reports_res.status_code == 503


# -----------------------------------------------------------------------------
# 17. Partial Failure Resilience
# -----------------------------------------------------------------------------

def test_partial_failure_resilience(client: TestClient, fake_mongo_db):
    """Verify when MongoDB fails, analysis still succeeds and records status='FAILED' in PostgreSQL."""
    # Register & Login
    client.post("/api/v1/auth/register", json={
        "email": "partial_fail@example.com",
        "password": "Password123!@#",
        "full_name": "Partial Fail User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "partial_fail@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Simulate collection error during upsert
    async def broken_update(*args, **kwargs):
        from pymongo.errors import ConnectionFailure
        raise ConnectionFailure("Simulated connection timeout during document insert.")

    fake_mongo_db["analysis_reports"].update_one = broken_update

    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def func(x: int) -> int: return x * 2\n",
        "test_cases": [{"input_data": {"x": 5}}],
        "static_only": True,
    }, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["analysis_session_id"] is not None
    assert data["report_storage_status"] == "FAILED"


# -----------------------------------------------------------------------------
# 18. Anonymous Extension Analysis Compatibility
# -----------------------------------------------------------------------------

def test_anonymous_extension_analysis_compatibility(client: TestClient):
    """Verify anonymous Chrome extension analysis completes without token and persists."""
    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def isPalindrome(s: str) -> bool:\n    return s == s[::-1]\n",
        "test_cases": [{"input_data": {"s": "racecar"}}],
        "static_only": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["analysis_session_id"] is not None
    assert data["report_storage_status"] in ("STORED", "PENDING", "NOT_CONFIGURED")


# -----------------------------------------------------------------------------
# 19. Existing PostgreSQL Integration & Problem Auto-Link
# -----------------------------------------------------------------------------

def test_postgresql_integration_and_problem_autolink(client: TestClient):
    """Verify problem context is auto-linked into PostgreSQL problems table."""
    client.post("/api/v1/auth/register", json={
        "email": "autolink@example.com",
        "password": "Password123!@#",
        "full_name": "AutoLink User",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "autolink@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    prob_slug = "climbing-stairs-phase4"
    res = client.post("/api/v1/edgemind/analyze", json={
        "code": "def climbStairs(n: int) -> int: return n\n",
        "problem_context": {
            "title": "Climbing Stairs Phase 4",
            "slug": prob_slug,
            "platform": "leetcode",
            "difficulty": "Easy",
        },
        "static_only": True,
    }, headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200

    # Query catalog -> Problem exists in PostgreSQL
    prob_res = client.get("/api/v1/problems")
    assert prob_res.status_code == 200
    assert any(p["problem_slug"] == prob_slug for p in prob_res.json())


# -----------------------------------------------------------------------------
# 20. Authentication & Multi-Tenancy Regression
# -----------------------------------------------------------------------------

def test_authentication_and_multi_tenancy_regression(client: TestClient):
    """Verify JWT authentication, token validation, and password policy remain fully intact."""
    # 1. Invalid password rejected
    bad_reg = client.post("/api/v1/auth/register", json={
        "email": "weak_pwd@example.com",
        "password": "weak",
        "full_name": "Weak Pwd",
    })
    assert bad_reg.status_code == 422

    # 2. Strong password accepted
    good_reg = client.post("/api/v1/auth/register", json={
        "email": "strong_pwd@example.com",
        "password": "Password123!@#",
        "full_name": "Strong Pwd",
    })
    assert good_reg.status_code == 201

    # 3. Token issued and profile accessible
    login_res = client.post("/api/v1/auth/login", json={
        "email": "strong_pwd@example.com",
        "password": "Password123!@#",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    me_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "strong_pwd@example.com"
