"""
EdgeMind — PostgreSQL 16 & pgvector Vector Query Verification Suite.

Validates:
1. SQL Dialect compilation using pgvector <=> operator under postgresql dialect.
2. Database-side cosine distance ordering (ORDER BY <=> ASC).
3. Tenant isolation in SQL WHERE prior to ORDER BY and LIMIT.
4. Top-k selection at the database level.
5. Column compilation to vector(1536) on PostgreSQL and JSON on SQLite.
6. Migration 005 structure (extension, HNSW index, downgrade cleanup).
7. Live PostgreSQL integration verification (conditional on reachable pgvector instance).
"""

import os
from typing import List
import uuid

import pytest
from sqlalchemy import or_, select
from sqlalchemy.dialects import postgresql, sqlite

from core.database.models.knowledge_chunk import KnowledgeChunk, get_embedding_column_type
from core.database.models.knowledge_document import KnowledgeDocument
from core.database.repositories.knowledge_repository import KnowledgeRepository


# ==============================================================================
# Part 1: Deterministic PostgreSQL Dialect & SQL Compilation Tests
# (Verifies SQL semantics and pgvector operator generation without requiring a running DB)
# ==============================================================================

def test_postgres_vector_query_operator_compilation():
    """Verify that KnowledgeRepository compiles genuine pgvector <=> cosine distance operator."""
    repo = KnowledgeRepository(None)
    dummy_embedding = [0.05] * 1536
    user_id = uuid.uuid4()

    stmt = repo.build_postgres_search_query(
        query_embedding=dummy_embedding,
        user_id=user_id,
        project_id=None,
        top_k=5,
        similarity_threshold=0.7,
    )

    compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))

    # 1. Cosine distance operator <=> in SELECT and WHERE
    assert "knowledge_chunks.embedding <=> %(" in compiled_sql, (
        f"Expected pgvector <=> operator in SQL, got:\n{compiled_sql}"
    )

    # 2. Database-side cosine distance ordering (ASC = closest first)
    assert "ORDER BY (knowledge_chunks.embedding <=> %(" in compiled_sql, (
        f"Expected ORDER BY <=> ASC in SQL, got:\n{compiled_sql}"
    )
    assert "ASC" in compiled_sql

    # 3. Database-side LIMIT
    assert "LIMIT %(" in compiled_sql, (
        f"Expected database-side LIMIT in SQL, got:\n{compiled_sql}"
    )


def test_tenant_filtering_precedes_top_k_selection_in_sql():
    """Verify that tenant isolation WHERE clauses precede ORDER BY and LIMIT in the compiled SQL."""
    repo = KnowledgeRepository(None)
    dummy_embedding = [0.1] * 1536
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    stmt = repo.build_postgres_search_query(
        query_embedding=dummy_embedding,
        user_id=user_id,
        project_id=project_id,
        top_k=3,
        similarity_threshold=0.6,
    )

    compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))

    # Find clause positions
    where_pos = compiled_sql.find("WHERE")
    order_pos = compiled_sql.find("ORDER BY")
    limit_pos = compiled_sql.find("LIMIT")

    assert where_pos != -1, "WHERE clause missing from compiled SQL"
    assert order_pos != -1, "ORDER BY clause missing from compiled SQL"
    assert limit_pos != -1, "LIMIT clause missing from compiled SQL"

    # WHERE (tenant filtering) MUST come before ORDER BY and LIMIT
    assert where_pos < order_pos < limit_pos, (
        "SQL execution order violation: WHERE clause must precede ORDER BY and LIMIT"
    )

    # Verify tenant condition components exist in WHERE
    where_clause = compiled_sql[where_pos:order_pos]
    assert "knowledge_chunks.is_global IS true" in where_clause
    assert "knowledge_chunks.user_id =" in where_clause
    assert "knowledge_chunks.project_id =" in where_clause


def test_embedding_column_dialect_compilation():
    """Verify that KnowledgeChunk.embedding column compiles to vector(1536) on PostgreSQL and JSON on SQLite."""
    col_type = get_embedding_column_type(1536)

    # Under PostgreSQL dialect, it must compile to vector(1536)
    pg_col = col_type.compile(dialect=postgresql.dialect())
    assert "vector(1536)" in pg_col.lower(), f"Expected vector(1536) on PostgreSQL, got: {pg_col}"

    # Under SQLite dialect, it must compile to JSON
    sqlite_col = col_type.compile(dialect=sqlite.dialect())
    assert "json" in sqlite_col.lower(), f"Expected JSON on SQLite, got: {sqlite_col}"


def test_migration_005_contains_pgvector_and_hnsw_definitions():
    """Verify migration 005 script declares vector extension, HNSW indexing, and downgrade cleanup."""
    migration_path = os.path.join(
        os.path.dirname(__file__), "..", "migrations", "versions", "005_rag_vector_storage.py"
    )
    with open(migration_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Extension creation
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in content
    # 2. HNSW cosine index creation
    assert "ix_knowledge_chunks_embedding_hnsw" in content
    assert "USING hnsw (embedding vector_cosine_ops)" in content
    # 3. Clean drop in downgrade
    assert "DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw;" in content
    # 4. Correct down_revision
    assert 'down_revision: Union[str, None] = "004_postgresql_jsonb_report_store"' in content


# ==============================================================================
# Part 2: Live PostgreSQL Integration Tests (Conditional)
# ==============================================================================

def get_live_postgres_url() -> str:
    """Check if a live PostgreSQL connection URL is available."""
    url = (
        os.environ.get("TEST_POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )
    if "postgresql" in url:
        return url
    return ""


@pytest.mark.anyio
async def test_live_postgres_vector_pipeline():
    """
    Live PostgreSQL + pgvector integration test.
    Automatically skipped if PostgreSQL daemon with pgvector is not accessible.
    When available, validates:
    - CREATE EXTENSION vector
    - Vector insertion (1536 dimensions)
    - Vector persistence
    - Cosine similarity ordering (<=>)
    - Top-k selection
    - Tenant isolation
    - Retrieval provenance
    """
    pg_url = get_live_postgres_url()
    if not pg_url:
        pytest.skip(
            "Live PostgreSQL server is not available (Docker engine offline). "
            "Set TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/db to run live integration tests."
        )

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import text
    from core.database.base import Base

    try:
        engine = create_async_engine(pg_url, echo=False)
        async with engine.connect() as conn:
            # Check if vector extension is available on the server
            ext_check = await conn.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            )
            if not ext_check.scalar():
                pytest.skip("PostgreSQL server is reachable, but pgvector extension is not installed.")

            # Create extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.commit()
    except Exception as exc:
        pytest.skip(f"Could not connect to live PostgreSQL: {exc}")

    # Create tables on disposable DB schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_maker() as session:
            repo = KnowledgeRepository(session)

            user_a = uuid.uuid4()
            user_b = uuid.uuid4()

            # 1. Store private document for User A
            from core.rag.processing.document import ProcessedChunk, ProcessedDocument
            doc_a = ProcessedDocument(
                id=uuid.uuid4(),
                title="User A Python Secrets",
                source_uri="file:///secrets_a.py",
                content_hash="hash_a_1234567890abcdef",
                metadata={"classification": "confidential"},
                chunks=[],
                total_chunks=2,
                user_id=user_a,
                is_global=False,
            )
            # Create two 1536-dim chunks with distinct vectors
            vec_target = [0.0] * 1536
            vec_target[0] = 1.0  # Points along dim 0

            vec_orthogonal = [0.0] * 1536
            vec_orthogonal[1] = 1.0  # Orthogonal along dim 1

            chunks_a = [
                ProcessedChunk(
                    id=uuid.uuid4(),
                    document_id=doc_a.id,
                    chunk_index=0,
                    content="User A primary secret vector target",
                    content_hash="chunk_hash_0",
                    embedding=vec_target,
                    embedding_model="text-embedding-3-small",
                    vector_dim=1536,
                    metadata={"index": 0},
                ),
                ProcessedChunk(
                    id=uuid.uuid4(),
                    document_id=doc_a.id,
                    chunk_index=1,
                    content="User A orthogonal vector content",
                    content_hash="chunk_hash_1",
                    embedding=vec_orthogonal,
                    embedding_model="text-embedding-3-small",
                    vector_dim=1536,
                    metadata={"index": 1},
                ),
            ]
            await repo.store_document(doc_a, chunks_a)

            # 2. Store global document accessible to all
            doc_global = ProcessedDocument(
                id=uuid.uuid4(),
                title="Global Python Guidelines",
                source_uri="file:///global_guidelines.md",
                content_hash="hash_global_abcdef1234567890",
                metadata={"public": True},
                chunks=[],
                total_chunks=1,
                user_id=None,
                is_global=True,
            )
            vec_global = [0.0] * 1536
            vec_global[0] = 0.9
            vec_global[1] = 0.1

            chunks_global = [
                ProcessedChunk(
                    id=uuid.uuid4(),
                    document_id=doc_global.id,
                    chunk_index=0,
                    content="Global public guidelines for python optimization",
                    content_hash="chunk_global_0",
                    embedding=vec_global,
                    embedding_model="text-embedding-3-small",
                    vector_dim=1536,
                    metadata={"public": True},
                )
            ]
            await repo.store_document(doc_global, chunks_global)
            await session.commit()

            # 3. Test genuine PostgreSQL similarity search for User A
            query_vec = [0.0] * 1536
            query_vec[0] = 1.0  # Identical to vec_target

            results_a = await repo.search_chunks(
                query_embedding=query_vec,
                user_id=user_a,
                top_k=2,
                similarity_threshold=0.5,
            )
            # Must return vec_target first (cosine similarity ~1.0)
            assert len(results_a) >= 1
            top_chunk, top_score = results_a[0]
            assert top_chunk.content == "User A primary secret vector target"
            assert top_score >= 0.99

            # 4. Test Tenant Isolation: User B searching with identical query
            results_b = await repo.search_chunks(
                query_embedding=query_vec,
                user_id=user_b,
                top_k=5,
                similarity_threshold=0.5,
            )
            # User B must NOT see User A's private chunk
            for chunk, _ in results_b:
                assert chunk.user_id != user_a
                assert chunk.is_global is True

            # 5. Test Retrieval Provenance
            assert top_chunk.document is not None
            assert top_chunk.document.title == "User A Python Secrets"
            assert top_chunk.document.source_uri == "file:///secrets_a.py"
    finally:
        await engine.dispose()
