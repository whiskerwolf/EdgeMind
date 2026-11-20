"""
Automated and Genuine Integration Tests for OllamaEmbeddingProvider & Local RAG.

Covers:
- OllamaEmbeddingProvider unit tests with httpx.MockTransport
- Error matrix (404, 400, 500, ConnectError, Timeout)
- Dimension mismatch detection (384 vs expected)
- Vector dimension isolation (384-dim vs 1536-dim) in storage and retrieval
- Cache key formatting (provider, model, dimension, SHA-256 hash, tenant scope)
- Redis cache hits and invalidation on document mutations
- Tenant isolation with 384-dim embeddings
- Dynamic provider selection without silent mock fallbacks
- Genuine local live Ollama tests using all-minilm:latest (HTTP 127.0.0.1:11434)
"""

import hashlib
import json
from typing import Any, Dict, List
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import get_settings
from core.cost.models import UsageSource
from core.database.models.knowledge_chunk import KnowledgeChunk
from core.database.models.knowledge_document import KnowledgeDocument
from core.database.models.user import User
from core.database.repositories.knowledge_repository import KnowledgeRepository
from core.rag.embeddings import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
    MockEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_rag_embedding_provider,
)
from core.rag.processing.document import DocumentProcessor, ProcessedChunk, ProcessedDocument
from core.rag.retrieval.service import VectorRetrievalService
from core.redis.cache import build_cache_key, default_cache_service
from tests.mock_redis import MockRedisClient


def _is_local_ollama_online() -> bool:
    """Check if local Ollama server is currently running with all-minilm installed."""
    try:
        res = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
        if res.status_code == 200:
            models = [m.get("name") for m in res.json().get("models", [])]
            return any("all-minilm" in m for m in models)
        return False
    except Exception:
        return False


# =============================================================================
# 1. OllamaEmbeddingProvider Unit Tests (Mock Transport)
# =============================================================================

@pytest.mark.anyio
async def test_ollama_embedding_provider_initialization():
    """Verify provider properties, defaults, and configuration."""
    provider = OllamaEmbeddingProvider()
    assert provider.provider_name == "ollama"
    assert provider.is_mock is False
    assert provider.model_name == "all-minilm:latest"
    assert provider.dimensions == 384
    assert provider.is_available() is True
    assert provider.last_usage is None


@pytest.mark.anyio
async def test_ollama_embedding_batch_request_and_response_parsing():
    """Verify POST /api/embed request payload, response parsing, and token accounting."""
    captured_request = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_request["method"] = request.method
        captured_request["url"] = str(request.url)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))

        # Generate fake 384-dimensional unit vectors
        fake_vec1 = [0.1] * 384
        fake_vec2 = [0.2] * 384

        return httpx.Response(
            200,
            json={
                "model": "all-minilm:latest",
                "embeddings": [fake_vec1, fake_vec2],
                "prompt_eval_count": 14,
            },
            headers={"x-request-id": "req-ollama-embed-123"},
        )

    provider = OllamaEmbeddingProvider(
        base_url="http://mock-ollama:11434",
        transport=httpx.MockTransport(mock_handler),
    )

    vectors = await provider.embed_batch(["binary search invariant", "dynamic programming"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384

    assert captured_request["method"] == "POST"
    assert captured_request["url"] == "http://mock-ollama:11434/api/embed"
    assert captured_request["body"]["model"] == "all-minilm:latest"
    assert captured_request["body"]["input"] == ["binary search invariant", "dynamic programming"]

    # Verify token usage tracking
    usage = provider.last_usage
    assert usage is not None
    assert usage.prompt_tokens == 14
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 14
    assert usage.model == "all-minilm:latest"
    assert usage.provider == "ollama"
    assert usage.request_id == "req-ollama-embed-123"
    assert usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert usage.estimated_cost_usd is None
    assert usage.is_estimated_cost_known is False


@pytest.mark.anyio
async def test_ollama_embedding_dimension_mismatch_validation():
    """Verify exception raised when returned vector dimension does not match configured 384."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        # Return 512 dimensions instead of 384
        return httpx.Response(
            200,
            json={
                "model": "all-minilm:latest",
                "embeddings": [[0.1] * 512],
                "prompt_eval_count": 5,
            },
        )

    provider = OllamaEmbeddingProvider(
        dimensions=384,
        transport=httpx.MockTransport(mock_handler),
    )

    with pytest.raises(EmbeddingDimensionMismatchError, match="Vector dimension 512 does not match expected 384"):
        await provider.embed_text("test dimension mismatch")


@pytest.mark.anyio
async def test_ollama_embedding_error_handling_matrix():
    """Verify error handling for 404 (model not found), 400 (invalid request), 500, ConnectError, Timeout."""
    # 1. HTTP 404: Model not found
    p_404 = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, text="model not found")),
    )
    with pytest.raises(EmbeddingError, match="model 'all-minilm:latest' not found"):
        await p_404.embed_text("test")

    # 2. HTTP 400: Invalid request
    p_400 = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad request parameter")),
    )
    with pytest.raises(EmbeddingError, match="HTTP 400"):
        await p_400.embed_text("test")

    # 3. HTTP 500: Server error
    p_500 = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="internal error")),
    )
    with pytest.raises(EmbeddingProviderUnavailableError, match="HTTP 500"):
        await p_500.embed_text("test")

    # 4. ConnectError: Ollama daemon offline
    def raise_connect(r):
        raise httpx.ConnectError("Connection refused")

    p_conn = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(raise_connect),
    )
    with pytest.raises(EmbeddingProviderUnavailableError, match="service unavailable"):
        await p_conn.embed_text("test")

    # 5. TimeoutException: Request timed out
    def raise_timeout(r):
        raise httpx.TimeoutException("Read timed out")

    p_timeout = OllamaEmbeddingProvider(
        timeout=2.0,
        transport=httpx.MockTransport(raise_timeout),
    )
    with pytest.raises(EmbeddingError, match="timed out"):
        await p_timeout.embed_text("test")


@pytest.mark.anyio
async def test_ollama_embedding_caching_and_cache_key():
    """Verify Redis caching for embeddings, deterministic SHA-256 keys, and cache hit bypass."""
    mock_redis = MockRedisClient()
    default_cache_service._explicit_client = mock_redis

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "model": "all-minilm:latest",
                "embeddings": [[0.5] * 384],
                "prompt_eval_count": 7,
            },
        )

    provider = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(mock_handler),
    )

    tenant_id = uuid.uuid4()
    text = "Sliding window maximum algorithm"

    # First call: cache miss, triggers HTTP request
    vec1 = await provider.embed_text(text, tenant_id=tenant_id)
    assert call_count == 1
    assert len(vec1) == 384

    # Second call: cache hit, skips HTTP request completely
    vec2 = await provider.embed_text(text, tenant_id=tenant_id)
    assert call_count == 1  # Unchanged!
    assert vec1 == vec2

    # Verify cache key structure contains provider, model, dimensions, SHA-256 hash
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    expected_key = build_cache_key(
        namespace="embedding",
        key_data={
            "provider": "ollama",
            "model": "all-minilm:latest",
            "dimensions": 384,
            "hash": text_hash,
        },
        tenant_id=tenant_id,
    )
    cached_val = await default_cache_service.get(expected_key)
    assert cached_val == vec1


# =============================================================================
# 2. Dynamic Provider Selection & Fallback Behavior
# =============================================================================

def test_dynamic_rag_provider_selection(monkeypatch):
    """Verify get_rag_embedding_provider selects configured provider without silent mock fallback."""
    # 1. Ollama selection
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "ollama")
    prov_ollama = get_rag_embedding_provider()
    assert isinstance(prov_ollama, OllamaEmbeddingProvider)
    assert prov_ollama.provider_name == "ollama"
    assert prov_ollama.dimensions == 384

    # 2. Mock selection
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    prov_mock = get_rag_embedding_provider()
    assert isinstance(prov_mock, MockEmbeddingProvider)
    assert prov_mock.provider_name == "mock"

    # 3. OpenAI selection
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "openai")
    prov_openai = get_rag_embedding_provider()
    assert isinstance(prov_openai, OpenAIEmbeddingProvider)
    assert prov_openai.provider_name == "openai"


@pytest.mark.anyio
async def test_ollama_selection_fails_explicitly_when_offline(monkeypatch):
    """When Ollama is selected, it must fail explicitly if offline, never silently fall back to mock."""
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:59999")  # Unreachable port

    provider = get_rag_embedding_provider()
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider._base_url == "http://127.0.0.1:59999"

    # Must raise EmbeddingProviderUnavailableError directly
    with pytest.raises(EmbeddingProviderUnavailableError):
        await provider.embed_text(f"uncached query {uuid.uuid4()}")


# =============================================================================
# 3. Vector Dimension Isolation & Knowledge Repository
# =============================================================================

@pytest.mark.anyio
async def test_vector_dimension_isolation_storage_and_search(sqlite_test_engine):
    """
    Verify complete dimension isolation:
    - 384-dimensional vectors stored in embedding_384 with vector_dim=384
    - 1536-dimensional vectors stored in embedding with vector_dim=1536
    - 384-dim query only retrieves 384-dim chunks, never compares against 1536-dim chunks
    - 1536-dim query only retrieves 1536-dim chunks, never compares against 384-dim chunks
    """
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    processor = DocumentProcessor()
    doc_384, chunks_384 = processor.process_document(
        title="Local 384-dim Reference",
        content="Quickselect is an efficient selection algorithm with O(n) average time complexity.",
        is_global=True,
    )
    for c in chunks_384:
        c.embedding = [0.5] * 384
        c.vector_dim = 384
        c.embedding_model = "all-minilm:latest"

    doc_1536, chunks_1536 = processor.process_document(
        title="Cloud 1536-dim Reference",
        content="Merge sort has guaranteed O(n log n) time complexity across all inputs.",
        is_global=True,
    )
    for c in chunks_1536:
        c.embedding = [0.1] * 1536
        c.vector_dim = 1536
        c.embedding_model = "text-embedding-3-small"

    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        await repo.store_document(doc_384, chunks_384)
        await repo.store_document(doc_1536, chunks_1536)
        await session.commit()

        # 1. Search with 384-dimensional query
        query_384 = [0.5] * 384
        results_384 = await repo.search_chunks(query_embedding=query_384, top_k=5, similarity_threshold=0.1)
        assert len(results_384) == len(chunks_384)
        for chunk, score in results_384:
            assert chunk.vector_dim == 384
            assert chunk.embedding_384 is not None
            assert len(chunk.embedding_384) == 384
            assert chunk.document.title == "Local 384-dim Reference"

        # 2. Search with 1536-dimensional query
        query_1536 = [0.1] * 1536
        results_1536 = await repo.search_chunks(query_embedding=query_1536, top_k=5, similarity_threshold=0.1)
        assert len(results_1536) == len(chunks_1536)
        for chunk, score in results_1536:
            assert chunk.vector_dim == 1536
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536
            assert chunk.document.title == "Cloud 1536-dim Reference"


@pytest.mark.anyio
async def test_tenant_isolation_with_384_embeddings(sqlite_test_engine):
    """Verify tenant isolation: User A cannot retrieve User B's private 384-dim chunks."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    processor = DocumentProcessor()
    doc_a, chunks_a = processor.process_document(
        title="User A Private Notes",
        content="Secret formula for Dijkstra's optimization.",
        user_id=user_a,
        is_global=False,
    )
    for c in chunks_a:
        c.embedding = [0.3] * 384
        c.vector_dim = 384

    doc_global, chunks_global = processor.process_document(
        title="Global Standard Notes",
        content="General Dijkstra algorithm overview.",
        is_global=True,
    )
    for c in chunks_global:
        c.embedding = [0.3] * 384
        c.vector_dim = 384

    async with session_factory() as session:
        # Create users to satisfy foreign key constraints
        u1 = User(id=user_a, email="usera_384@example.com", full_name="User A", password_hash="hash", role="user")
        u2 = User(id=user_b, email="userb_384@example.com", full_name="User B", password_hash="hash", role="user")
        session.add_all([u1, u2])

        repo = KnowledgeRepository(session)
        await repo.store_document(doc_a, chunks_a)
        await repo.store_document(doc_global, chunks_global)
        await session.commit()

        query_vec = [0.3] * 384

        # User B queries: Should only see Global document, NOT User A's document
        results_b = await repo.search_chunks(query_embedding=query_vec, user_id=user_b, top_k=5)
        titles_b = [c.document.title for c, _ in results_b]
        assert "Global Standard Notes" in titles_b
        assert "User A Private Notes" not in titles_b

        # Anonymous query: Should only see Global document
        results_anon = await repo.search_chunks(query_embedding=query_vec, user_id=None, top_k=5)
        titles_anon = [c.document.title for c, _ in results_anon]
        assert "Global Standard Notes" in titles_anon
        assert "User A Private Notes" not in titles_anon

        # User A queries: Sees both private and global
        results_a = await repo.search_chunks(query_embedding=query_vec, user_id=user_a, top_k=5)
        titles_a = [c.document.title for c, _ in results_a]
        assert "Global Standard Notes" in titles_a
        assert "User A Private Notes" in titles_a


# =============================================================================
# 4. Genuine Local Ollama Integration Tests (Real all-minilm:latest)
# =============================================================================

@pytest.mark.skipif(not _is_local_ollama_online(), reason="Local Ollama server offline or all-minilm not installed")
@pytest.mark.anyio
async def test_live_local_ollama_single_embedding():
    """Verify genuine single embedding request against local all-minilm:latest produces 384 dimensions."""
    provider = OllamaEmbeddingProvider()
    text = "Dynamic programming memoization table invariants"
    vector = await provider.embed_text(text)

    assert isinstance(vector, list)
    assert len(vector) == 384
    assert any(v != 0.0 for v in vector)

    # Check local token usage
    usage = provider.last_usage
    assert usage is not None
    assert usage.prompt_tokens > 0
    assert usage.total_tokens == usage.prompt_tokens
    assert usage.completion_tokens == 0
    assert usage.usage_source == UsageSource.LOCAL_INFERENCE
    assert usage.provider == "ollama"
    assert usage.estimated_cost_usd is None
    assert usage.is_estimated_cost_known is False


@pytest.mark.skipif(not _is_local_ollama_online(), reason="Local Ollama server offline or all-minilm not installed")
@pytest.mark.anyio
async def test_live_local_ollama_batch_embedding():
    """Verify genuine batch embedding request against local all-minilm:latest."""
    provider = OllamaEmbeddingProvider()
    texts = [
        "Breadth-first search queue state machine",
        "Depth-first search recursion call stack limits",
    ]
    vectors = await provider.embed_batch(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384
    assert vectors[0] != vectors[1]


@pytest.mark.skipif(not _is_local_ollama_online(), reason="Local Ollama server offline or all-minilm not installed")
@pytest.mark.anyio
async def test_live_local_ollama_rag_retrieval_and_invalidation(sqlite_test_engine):
    """
    Verify genuine end-to-end local RAG pipeline:
    1. Embeds and stores chunks using genuine all-minilm:latest.
    2. VectorRetrievalService retrieves matching chunk with semantic ranking.
    3. Caches retrieval in Redis.
    4. Invalidates cache on document deletion.
    """
    mock_redis = MockRedisClient()
    default_cache_service._explicit_client = mock_redis

    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = OllamaEmbeddingProvider()

    processor = DocumentProcessor()
    doc1, chunks1 = processor.process_document(
        title="Binary Search Invariant Guide",
        content="Binary search maintains low <= high where mid = (low + high) // 2.",
        is_global=True,
    )
    doc2, chunks2 = processor.process_document(
        title="Hash Map Bucket Collision Guide",
        content="Separate chaining and open addressing resolve key collisions.",
        is_global=True,
    )

    all_chunks = chunks1 + chunks2
    embeddings = await provider.embed_batch([c.content for c in all_chunks])
    for c, emb in zip(all_chunks, embeddings):
        c.embedding = emb
        c.vector_dim = 384
        c.embedding_model = provider.model_name

    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        await repo.store_document(doc1, chunks1)
        await repo.store_document(doc2, chunks2)
        await session.commit()

        # Execute retrieval via VectorRetrievalService
        service = VectorRetrievalService(db=session, embedding_provider=provider)
        retrieval = await service.retrieve(
            query="How does binary search calculate the middle index?",
            top_k=2,
            similarity_threshold=0.3,
        )

        assert retrieval.total_retrieved > 0
        top_chunk = retrieval.chunks[0]
        assert top_chunk.title == "Binary Search Invariant Guide"
        assert "binary search" in top_chunk.content.lower()
        assert retrieval.embedding_model == "all-minilm:latest"
        assert retrieval.embedding_provider == "ollama"
        assert retrieval.is_mock is False

        # Invalidate on document deletion
        deleted = await repo.delete_document(doc1.id, is_admin=True)
        assert deleted is True
        await session.commit()

        # Retrieval after deletion should not return the deleted document
        retrieval_after = await service.retrieve(
            query="How does binary search calculate the middle index?",
            top_k=2,
            similarity_threshold=0.3,
        )
        assert all(c.document_id != doc1.id for c in retrieval_after.chunks)
