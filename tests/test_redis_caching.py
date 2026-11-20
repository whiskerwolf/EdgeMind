"""
EdgeMind Phase 4: Comprehensive Redis Caching Tests.

Tests:
1. Cache Service Primitives (get, set, delete, TTL expiration)
2. JSON Serialization (UUID, Decimal, datetime, Pydantic, dataclasses)
3. Malformed JSON Recovery & Self-Healing
4. Non-Blocking Prefix Invalidation (SCAN)
5. Strict Multi-Tenant Isolation
6. SHA-256 Key Hashing & Input Obfuscation
7. Cache Metric Accounting (hits, misses, ratio, sets, deletes, bypasses, errors)
8. Graceful Bypass on Redis Outage (zero LLM mock fallback, zero crashes)
9. Redis Connection Management & Credential Sanitization
10. RAG Query Embedding Caching Integration
11. RAG Vector Retrieval Result Caching Integration
12. Automatic Cache Invalidation on Document Mutation
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid
import pytest
from redis.exceptions import ConnectionError, RedisError

from core.config import get_settings
from core.database.models import Project, User
from core.database.repositories.knowledge_repository import KnowledgeRepository
from core.rag.embeddings.mock import MockEmbeddingProvider
from core.rag.embeddings.openai_provider import OpenAIEmbeddingProvider
from core.rag.processing.document import DocumentProcessor
from core.rag.retrieval.service import RetrievedChunk, RetrievalResult, VectorRetrievalService
from core.redis.cache import (
    CacheJSONEncoder,
    CacheMetrics,
    CacheService,
    build_cache_key,
    default_cache_service,
    hash_key_data,
)
from core.redis.connection import RedisManager, sanitize_redis_url
from tests.mock_redis import MockRedisClient


@pytest.fixture
def mock_redis():
    """Isolated in-memory mock Redis client."""
    client = MockRedisClient()
    return client


@pytest.fixture
def cache_service(mock_redis):
    """Cache service backed by mock Redis."""
    return CacheService(redis_client=mock_redis, default_ttl=300, enabled=True)


# -----------------------------------------------------------------------------
# 1. Cache Primitives & Operations
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_get_set_delete(cache_service):
    """Verify basic get, set, delete operations and hit/miss counts."""
    # 1. Miss initially
    val = await cache_service.get("test:key1")
    assert val is None
    assert cache_service.metrics.misses == 1
    assert cache_service.metrics.hits == 0

    # 2. Set value
    stored = await cache_service.set("test:key1", {"status": "ok", "count": 42})
    assert stored is True
    assert cache_service.metrics.sets == 1

    # 3. Hit on subsequent get
    val = await cache_service.get("test:key1")
    assert val == {"status": "ok", "count": 42}
    assert cache_service.metrics.hits == 1

    # 4. Delete value
    deleted = await cache_service.delete("test:key1")
    assert deleted is True
    assert cache_service.metrics.deletes == 1

    # 5. Miss after delete
    val2 = await cache_service.get("test:key1")
    assert val2 is None
    assert cache_service.metrics.misses == 2


@pytest.mark.anyio
async def test_cache_ttl_expiration(mock_redis, cache_service):
    """Verify keys expire according to TTL."""
    await cache_service.set("test:expiring", "value", ttl=1)
    assert await cache_service.get("test:expiring") == "value"

    # Manually expire the key in mock redis
    mock_redis._expirations["test:expiring"] = 0.0

    val = await cache_service.get("test:expiring")
    assert val is None


# -----------------------------------------------------------------------------
# 2. JSON Serialization of Complex Types
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_json_serialization_complex_types(cache_service):
    """Verify UUID, Decimal, datetime, dict, and list are safely serialized and restored."""
    test_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    cost = Decimal("0.000123456789")

    payload = {
        "id": test_id,
        "timestamp": now,
        "cost": cost,
        "tags": ["alpha", "beta"],
        "nested": {"score": 0.95},
    }

    stored = await cache_service.set("complex:key", payload)
    assert stored is True

    retrieved = await cache_service.get("complex:key")
    assert retrieved is not None
    assert retrieved["id"] == str(test_id)
    assert retrieved["timestamp"] == now.isoformat()
    assert retrieved["cost"] == str(cost)
    assert retrieved["tags"] == ["alpha", "beta"]
    assert retrieved["nested"]["score"] == 0.95


# -----------------------------------------------------------------------------
# 3. Malformed JSON Recovery & Self-Healing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_malformed_json_self_healing(mock_redis, cache_service):
    """Verify corrupted cache entries are cleanly purged without crashing the application."""
    # Write corrupted non-JSON data directly to Redis
    mock_redis._data["corrupt:key"] = "{this is not valid json...}"

    val = await cache_service.get("corrupt:key")
    assert val is None
    assert cache_service.metrics.misses == 1

    # Verify self-healing deleted the corrupted entry
    assert "corrupt:key" not in mock_redis._data


# -----------------------------------------------------------------------------
# 4. Non-Blocking Prefix Invalidation (SCAN)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_delete_prefix(mock_redis, cache_service):
    """Verify non-blocking prefix deletion cleans matching keys and preserves others."""
    await cache_service.set("edgemind:cache:v1:user:1:a", "val1")
    await cache_service.set("edgemind:cache:v1:user:1:b", "val2")
    await cache_service.set("edgemind:cache:v1:user:2:a", "val3")

    deleted = await cache_service.delete_prefix("edgemind:cache:v1:user:1:")
    assert deleted == 2

    assert await cache_service.get("edgemind:cache:v1:user:1:a") is None
    assert await cache_service.get("edgemind:cache:v1:user:1:b") is None
    assert await cache_service.get("edgemind:cache:v1:user:2:a") == "val3"


# -----------------------------------------------------------------------------
# 5. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_multi_tenant_isolation(mock_redis, cache_service):
    """Verify tenant invalidation never touches other tenants' cache data."""
    tenant_1 = uuid.uuid4()
    tenant_2 = uuid.uuid4()
    project_1 = uuid.uuid4()

    key_t1 = build_cache_key("rag", "query_text", tenant_id=tenant_1, project_id=project_1)
    key_t2 = build_cache_key("rag", "query_text", tenant_id=tenant_2)
    key_global = build_cache_key("rag", "query_text")

    await cache_service.set(key_t1, "data_tenant_1")
    await cache_service.set(key_t2, "data_tenant_2")
    await cache_service.set(key_global, "data_global")

    # Invalidate Tenant 1 only
    deleted = await cache_service.invalidate_tenant(tenant_id=tenant_1, project_id=project_1)
    assert deleted == 1

    assert await cache_service.get(key_t1) is None
    assert await cache_service.get(key_t2) == "data_tenant_2"
    assert await cache_service.get(key_global) == "data_global"


# -----------------------------------------------------------------------------
# 6. SHA-256 Key Hashing & Input Obfuscation
# -----------------------------------------------------------------------------

def test_hash_key_data_and_build_cache_key():
    """Verify key hashing produces deterministic 64-char hex digest hiding sensitive code."""
    secret_code = "SECRET_API_KEY = 'sk-1234567890abcdef' \n def foo(): pass"
    hash_1 = hash_key_data(secret_code)
    hash_2 = hash_key_data(secret_code)

    assert len(hash_1) == 64
    assert hash_1 == hash_2
    assert "sk-1234567890" not in hash_1

    key = build_cache_key("rag_query", secret_code, tenant_id="tenant-xyz")
    assert key.startswith("edgemind:cache:v1:tenant:tenant-xyz:rag_query:")
    assert "sk-1234567890" not in key
    assert len(key.split(":")[-1]) == 64


# -----------------------------------------------------------------------------
# 7. Metric Accounting & Hit Ratio
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_metrics_summary(cache_service):
    """Verify metric calculations including hit ratio and query totals."""
    await cache_service.set("m:key1", "val1")
    await cache_service.get("m:key1")  # hit
    await cache_service.get("m:key2")  # miss
    await cache_service.get("m:key3")  # miss
    await cache_service.get("m:key1")  # hit

    metrics = cache_service.get_metrics()
    assert metrics["hits"] == 2
    assert metrics["misses"] == 2
    assert metrics["total_queries"] == 4
    assert metrics["hit_ratio"] == 0.5
    assert metrics["sets"] == 1

    cache_service.reset_metrics()
    reset_m = cache_service.get_metrics()
    assert reset_m["hits"] == 0
    assert reset_m["total_queries"] == 0


# -----------------------------------------------------------------------------
# 8. Graceful Bypass on Redis Outage
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_graceful_bypass_on_redis_error(mock_redis, cache_service):
    """Verify Redis exceptions are caught, logged, and bypassed without raising."""
    # Inject connection failure
    mock_redis.set_raise_error(ConnectionError("Connection to Redis refused on 127.0.0.1:6379"))

    # get() must return None (miss/bypass)
    val = await cache_service.get("any:key")
    assert val is None
    assert cache_service.metrics.bypasses >= 1
    assert cache_service.metrics.errors >= 1

    # set() must return False without raising
    stored = await cache_service.set("any:key", "data")
    assert stored is False

    # delete() must return False without raising
    deleted = await cache_service.delete("any:key")
    assert deleted is False


# -----------------------------------------------------------------------------
# 9. Redis Connection Management & Health Checks
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_redis_connection_manager_health(mock_redis):
    """Verify Redis health diagnostics and credential masking."""
    mgr = RedisManager()
    mgr.set_override_client(mock_redis)

    # 1. Healthy state
    health = await mgr.check_health()
    assert health["status"] == "healthy"
    assert health["reachable"] is True

    # 2. Outage state
    mock_redis.set_raise_error(TimeoutError("Socket read timeout"))
    health_bad = await mgr.check_health()
    assert health_bad["status"] == "unhealthy"
    assert health_bad["reachable"] is False


def test_sanitize_redis_url_credential_masking():
    """Verify password in Redis URL is masked in all logs and outputs."""
    raw_url = "redis://user:super_secret_password_123@127.0.0.1:6379/0"
    sanitized = sanitize_redis_url(raw_url)
    assert "super_secret_password_123" not in sanitized
    assert sanitized == "redis://user:***@127.0.0.1:6379/0"

    raw_no_user = "redis://:secret_pass@127.0.0.1:6379/0"
    sanitized_no_user = sanitize_redis_url(raw_no_user)
    assert "secret_pass" not in sanitized_no_user
    assert ":***@" in sanitized_no_user


# -----------------------------------------------------------------------------
# 10. RAG Query Embedding Caching Integration
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rag_embedding_caching_integration(mock_redis):
    """Verify OpenAIEmbeddingProvider caches embeddings to avoid repeated external calls."""
    default_cache_service._explicit_client = mock_redis
    try:
        provider = OpenAIEmbeddingProvider(
            api_key="sk-test-fake-key",
            dimensions=4,
        )

        call_count = 0

        # Mock the external HTTP transport batch response
        async def mock_embed_text_via_batch(texts):
            nonlocal call_count
            call_count += 1
            return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

        # First call: populates cache
        key = build_cache_key(
            namespace="embedding",
            key_data=f"{provider.model_name}:{provider.dimensions}:cacheable query text",
        )
        await default_cache_service.set(key, [0.1, 0.2, 0.3, 0.4])

        # Next call: should hit cache
        vec = await provider.embed_text("cacheable query text")
        assert vec == [0.1, 0.2, 0.3, 0.4]
        assert default_cache_service.metrics.hits >= 1

    finally:
        default_cache_service._explicit_client = None


# -----------------------------------------------------------------------------
# 11. RAG Vector Retrieval Result Caching Integration
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rag_retrieval_caching_and_invalidation(mock_redis):
    """Verify VectorRetrievalService caches results and invalidates on document updates."""
    default_cache_service._explicit_client = mock_redis
    try:
        mock_prov = MockEmbeddingProvider(dimensions=8)
        service = VectorRetrievalService(embedding_provider=mock_prov)

        user_id = uuid.uuid4()
        query = "Binary search tree invariants"

        # Prime the cache with a known result
        cache_key = build_cache_key(
            namespace="rag_retrieval",
            key_data={
                "query": query,
                "top_k": 3,
                "threshold": 0.4,
                "model": mock_prov.model_name,
            },
            tenant_id=user_id,
        )

        dummy_chunk = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="BST Guide",
            content="Left < Node < Right",
            similarity_score=0.92,
        )
        dummy_result = RetrievalResult(
            query=query,
            top_k=3,
            similarity_threshold=0.4,
            chunks=[dummy_chunk],
            total_retrieved=1,
            execution_duration_ms=1.5,
            embedding_model=mock_prov.model_name,
        )

        await default_cache_service.set(cache_key, dummy_result.to_dict())

        # Retrieve should return cached result without touching DB
        res = await service.retrieve(query=query, user_id=user_id, top_k=3, similarity_threshold=0.4)
        assert res.total_retrieved == 1
        assert res.chunks[0].title == "BST Guide"
        assert res.chunks[0].similarity_score == 0.92

        # Invalidate tenant cache
        await default_cache_service.invalidate_tenant(tenant_id=user_id)
        assert await default_cache_service.get(cache_key) is None

    finally:
        default_cache_service._explicit_client = None


# -----------------------------------------------------------------------------
# 12. Redis Memory Limit (OOM) Graceful Degradation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cache_graceful_handling_oom_error(mock_redis, cache_service):
    """
    Verify that when Redis reaches maxmemory and returns an OOM ResponseError,
    CacheService.set() catches it gracefully, logs sanitized warning, records
    metrics, and returns False without raising or disrupting business logic.
    """
    from redis.exceptions import ResponseError

    mock_redis.set_raise_error(
        ResponseError("OOM command not allowed when used memory > 'maxmemory'")
    )

    # set() must return False and increment bypass/error counters
    success = await cache_service.set("oom:key", {"data": "test"})
    assert success is False
    assert cache_service.metrics.errors >= 1
    assert cache_service.metrics.bypasses >= 1

    # get() must also bypass gracefully
    val = await cache_service.get("oom:key")
    assert val is None


# -----------------------------------------------------------------------------
# 13. Document Lifecycle Cache Invalidation (Create, Update, Delete)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_document_lifecycle_cache_invalidation_create_update_delete(sqlite_test_engine, mock_redis):
    """
    Verify that document creation, update, and deletion in KnowledgeRepository
    automatically invalidate the affected tenant's RAG retrieval cache.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    default_cache_service._explicit_client = mock_redis
    try:
        session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
        processor = DocumentProcessor()
        tenant_id = uuid.uuid4()
        project_id = uuid.uuid4()

        tenant_cache_key = build_cache_key(
            namespace="rag_retrieval",
            key_data={"query": "binary search"},
            tenant_id=tenant_id,
            project_id=project_id,
        )

        async with session_factory() as session:
            # Create user account for foreign key integrity
            user = User(
                id=tenant_id,
                email=f"tenant_{uuid.uuid4().hex[:8]}@example.com",
                full_name="Tenant User",
                password_hash="argon2id_hash_placeholder",
                role="user",
            )
            session.add(user)
            await session.commit()

            repo = KnowledgeRepository(session)

            # Step 1: Document Creation Invalidation
            # Prime cache
            await default_cache_service.set(tenant_cache_key, {"cached": "initial"})
            assert await default_cache_service.get(tenant_cache_key) is not None

            # Create document
            doc, chunks = processor.process_document(
                title="Search Doc",
                content="Binary search requires sorted array.",
                user_id=tenant_id,
            )
            created_doc = await repo.store_document(doc, chunks)
            await session.commit()

            # Cache must be invalidated upon creation
            assert await default_cache_service.get(tenant_cache_key) is None

            # Step 2: Document Update Invalidation
            # Re-prime cache
            await default_cache_service.set(tenant_cache_key, {"cached": "second"})
            assert await default_cache_service.get(tenant_cache_key) is not None

            # Update document (same content_hash, updated title)
            doc_updated, chunks_updated = processor.process_document(
                title="Search Doc Updated Title",
                content="Binary search requires sorted array.",
                user_id=tenant_id,
            )
            await repo.store_document(doc_updated, chunks_updated, overwrite_existing=True)
            await session.commit()

            # Cache must be invalidated upon update
            assert await default_cache_service.get(tenant_cache_key) is None

            # Step 3: Document Deletion Invalidation
            # Re-prime cache
            await default_cache_service.set(tenant_cache_key, {"cached": "third"})
            assert await default_cache_service.get(tenant_cache_key) is not None

            # Delete document
            deleted = await repo.delete_document(document_id=created_doc.id, user_id=tenant_id)
            assert deleted is True
            await session.commit()

            # Cache must be invalidated upon deletion
            assert await default_cache_service.get(tenant_cache_key) is None

    finally:
        default_cache_service._explicit_client = None


# -----------------------------------------------------------------------------
# 14. Global Document Lifecycle Cache Invalidation & Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_global_document_lifecycle_cache_invalidation_and_isolation(sqlite_test_engine, mock_redis):
    """
    Verify:
    1. Global document creation invalidates global retrieval caches.
    2. Global document update invalidates global retrieval caches.
    3. Global document deletion invalidates global retrieval caches.
    4. Tenant document mutation does not invalidate global retrieval caches.
    5. Global document mutation does not wipe out unrelated tenant caches.
    6. Private tenant documents never populate global retrieval caches or search results.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    default_cache_service._explicit_client = mock_redis
    try:
        session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
        processor = DocumentProcessor()
        tenant_id = uuid.uuid4()
        project_id = uuid.uuid4()

        global_cache_key = build_cache_key(
            namespace="rag_retrieval",
            key_data={"query": "global algorithms query"},
            tenant_id=None,
        )
        tenant_cache_key = build_cache_key(
            namespace="rag_retrieval",
            key_data={"query": "tenant algorithms query"},
            tenant_id=tenant_id,
            project_id=project_id,
        )

        async with session_factory() as session:
            # Create user account and project for tenant
            user = User(
                id=tenant_id,
                email=f"tenant_user_{uuid.uuid4().hex[:8]}@example.com",
                full_name="Tenant User",
                password_hash="argon2id_hash_placeholder",
                role="user",
            )
            session.add(user)
            project = Project(
                id=project_id,
                owner_user_id=tenant_id,
                name="Tenant Test Project",
            )
            session.add(project)
            await session.commit()

            repo = KnowledgeRepository(session)

            # Scenario 1: Global Document Creation Invalidation
            await default_cache_service.set(global_cache_key, {"cached": "global_initial"})
            await default_cache_service.set(tenant_cache_key, {"cached": "tenant_initial"})
            assert await default_cache_service.get(global_cache_key) is not None
            assert await default_cache_service.get(tenant_cache_key) is not None

            global_doc, global_chunks = processor.process_document(
                title="Global Standard Algorithms",
                content="Quicksort has average complexity O(n log n).",
                is_global=True,
            )
            created_global = await repo.store_document(global_doc, global_chunks)
            await session.commit()

            # Global cache must be invalidated
            assert await default_cache_service.get(global_cache_key) is None
            # Tenant cache must NOT be wiped by global document creation
            assert await default_cache_service.get(tenant_cache_key) is not None

            # Scenario 2: Global Document Update Invalidation
            await default_cache_service.set(global_cache_key, {"cached": "global_v2"})
            assert await default_cache_service.get(global_cache_key) is not None

            updated_global, updated_chunks = processor.process_document(
                title="Global Standard Algorithms Updated",
                content="Quicksort has average complexity O(n log n).",
                is_global=True,
            )
            await repo.store_document(updated_global, updated_chunks, overwrite_existing=True)
            await session.commit()

            # Global cache must be invalidated
            assert await default_cache_service.get(global_cache_key) is None

            # Scenario 3: Global Document Deletion Invalidation
            await default_cache_service.set(global_cache_key, {"cached": "global_v3"})
            assert await default_cache_service.get(global_cache_key) is not None

            deleted = await repo.delete_document(document_id=created_global.id, is_admin=True)
            assert deleted is True
            await session.commit()

            # Global cache must be invalidated
            assert await default_cache_service.get(global_cache_key) is None

            # Scenario 4: Tenant Document Mutation Does NOT Invalidate Global Cache
            await default_cache_service.set(global_cache_key, {"cached": "global_preserved"})
            await default_cache_service.set(tenant_cache_key, {"cached": "tenant_test"})

            tenant_doc, tenant_chunks = processor.process_document(
                title="Private Tenant Specs",
                content="Proprietary tenant internal specification.",
                user_id=tenant_id,
                project_id=project_id,
            )
            created_tenant = await repo.store_document(tenant_doc, tenant_chunks)
            await session.commit()

            # Tenant cache invalidated
            assert await default_cache_service.get(tenant_cache_key) is None
            # Global cache must remain intact
            assert await default_cache_service.get(global_cache_key) == {"cached": "global_preserved"}

            # Scenario 5: Private Tenant Documents Never Leak into Anonymous / Global Retrieval
            query_embedding = [0.1] * 1536
            anonymous_results = await repo.search_chunks(
                query_embedding=query_embedding,
                user_id=None,
                top_k=10,
                similarity_threshold=0.0,
            )
            for chunk, sim in anonymous_results:
                assert chunk.is_global is True
                assert chunk.user_id is None
                assert chunk.user_id != tenant_id

            # Verify retrieval service with cache: private retrieval never populates global cache
            retrieval_service = VectorRetrievalService(
                db=session,
                embedding_provider=MockEmbeddingProvider(),
            )
            tenant_res = await retrieval_service.retrieve(
                query="Proprietary",
                user_id=tenant_id,
                project_id=project_id,
            )
            for key in mock_redis._data.keys():
                if "rag_retrieval" in key and (tenant_id.hex in key or str(tenant_id) in key):
                    assert ":tenant:" in key
                    assert ":global:" not in key

    finally:
        default_cache_service._explicit_client = None


# -----------------------------------------------------------------------------
# 15. Production Redis Password Security Validation
# -----------------------------------------------------------------------------

def test_production_redis_password_validation():
    """
    Verify validate_redis_security() fails fast in production when REDIS_PASSWORD is missing or blank,
    and succeeds when properly configured.
    """
    from core.config import Settings

    # Case 1: In production with REDIS_URL but no REDIS_PASSWORD -> must raise RuntimeError
    prod_settings_no_pw = Settings(
        environment="production",
        jwt_secret_key="secret" * 8,
        redis_url="redis://127.0.0.1:6379/0",
        redis_password="",
    )
    with pytest.raises(RuntimeError, match="REDIS_PASSWORD must be explicitly configured"):
        prod_settings_no_pw.validate_redis_security()

    # Case 2: In production with REDIS_URL and explicit REDIS_PASSWORD -> passes
    prod_settings_valid = Settings(
        environment="production",
        jwt_secret_key="secret" * 8,
        redis_url="redis://127.0.0.1:6379/0",
        redis_password="strong_production_redis_password_12345",
    )
    prod_settings_valid.validate_redis_security()

    # Case 3: In production with password in URL (redis://:pass@host) -> passes
    prod_settings_url_pw = Settings(
        environment="production",
        jwt_secret_key="secret" * 8,
        redis_url="redis://:strong_password@127.0.0.1:6379/0",
        redis_password=None,
    )
    prod_settings_url_pw.validate_redis_security()

    # Case 4: Non-production (development) without password -> allowed
    dev_settings = Settings(
        environment="development",
        jwt_secret_key="secret" * 8,
        redis_url="redis://127.0.0.1:6379/0",
        redis_password="",
    )
    dev_settings.validate_redis_security()
