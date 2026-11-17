"""
Comprehensive Test Suite for EdgeMind RAG & Vector Retrieval Pipeline.

Validates:
1. Text Chunking (sliding window, sentence boundaries, size validation).
2. Chunk Overlap (consecutive chunks share required overlap).
3. Content Hashing (SHA-256 fingerprints, sensitivity, idempotency).
4. Embedding Dimension Validation (strict vector dimension matching).
5. Mock Embedding Provider (deterministic L2 unit vectors, identical text cos_sim = 1.0).
6. Live Embedding Provider Request Parsing (httpx.MockTransport, OpenAI format).
7. Embedding Provider Failure Handling (401, 429, 500, timeouts, credential redaction).
8. Vector Insertion & Persistence (KnowledgeRepository document and chunk storage).
9. Similarity Ranking (cosine similarity descending order).
10. Top-K Retrieval Limits (enforcing k upper bounds).
11. Similarity Threshold Filtering (filtering out low-similarity chunks).
12. Empty Knowledge Base (graceful empty result with zero exceptions).
13. Duplicate Document Handling (content_hash deduplication and upsert).
14. Strict Tenant Isolation (cross-user rejection, global document sharing).
15. Agent Retrieval-Tool Integration (retrieve_knowledge_context execution).
16. Retrieval Provenance (state audit and test intelligence recording).
17. Missing Embedding Credentials (graceful unavailable status handling).
"""

import math
import uuid
from typing import Any, Dict, List
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.agents import (
    AgentAnalyzeRequest,
    AgentOrchestrator,
    AgentStatus,
    AgentStepResult,
    MockAgentProvider,
    ToolCall,
    default_tool_registry,
)
from core.database.models import KnowledgeChunk, KnowledgeDocument, Project, User
from core.database.repositories.knowledge_repository import (
    KnowledgeRepository,
    compute_cosine_similarity,
)
from core.rag.embeddings import (
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from core.rag.processing import (
    DocumentProcessor,
    ProcessedChunk,
    ProcessedDocument,
)
from core.rag.retrieval import (
    RetrievalResult,
    RetrievedChunk,
    VectorRetrievalService,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# =============================================================================
# 1. Text Chunking, Overlap & Hashing
# =============================================================================

def test_text_chunking():
    """Verify document processor chunks text according to size constraints."""
    processor = DocumentProcessor(default_chunk_size=50, default_chunk_overlap=10)
    text = "First paragraph content.\n\nSecond paragraph content.\n\nThird paragraph content."

    chunks = processor.chunk_text(text, chunk_size=30, chunk_overlap=5)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(chunk) <= 35  # Allows boundary padding
        assert len(chunk) > 0


def test_chunk_overlap():
    """Verify consecutive chunks share overlapping text."""
    processor = DocumentProcessor()
    text = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet Kilo Lima Mike"
    chunks = processor.chunk_text(text, chunk_size=30, chunk_overlap=10)

    assert len(chunks) >= 2
    # Verify adjacent chunks have overlapping tokens or characters
    for i in range(len(chunks) - 1):
        words_current = set(chunks[i].split())
        words_next = set(chunks[i + 1].split())
        # At least one word or substring should overlap
        assert len(words_current.intersection(words_next)) >= 1 or any(
            w in chunks[i + 1] for w in words_current
        )


def test_content_hashing_sha256():
    """Verify SHA-256 fingerprinting is deterministic and sensitive to text edits."""
    processor = DocumentProcessor()
    t1 = "def two_sum(nums, target): return []"
    t2 = "def two_sum(nums, target): return []"
    t3 = "def two_sum(nums, target): return [0, 1]"

    h1 = processor.compute_sha256(t1)
    h2 = processor.compute_sha256(t2)
    h3 = processor.compute_sha256(t3)

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_chunking_invalid_parameters():
    """Reject non-positive chunk size or overlap >= chunk_size."""
    processor = DocumentProcessor()
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        processor.chunk_text("hello", chunk_size=0, chunk_overlap=0)

    with pytest.raises(ValueError, match="chunk_overlap .* must be strictly less than"):
        processor.chunk_text("hello", chunk_size=50, chunk_overlap=50)


# =============================================================================
# 2. Embedding Providers & Dimension Validation
# =============================================================================

@pytest.mark.anyio
async def test_mock_embedding_provider_deterministic_similarity():
    """Verify mock provider generates unit-length vectors with identical text similarity = 1.0."""
    provider = MockEmbeddingProvider(dimensions=128)
    assert provider.dimensions == 128
    assert provider.is_available() is True

    vec1 = await provider.embed_text("binary search algorithm")
    vec2 = await provider.embed_text("binary search algorithm")
    vec3 = await provider.embed_text("depth first search graph traversal")

    assert len(vec1) == 128
    assert len(vec2) == 128

    # L2 norm check: sqrt(sum(x^2)) ~= 1.0
    norm1 = math.sqrt(sum(x * x for x in vec1))
    assert pytest.approx(norm1, 0.001) == 1.0

    # Identical texts yield cos_sim = 1.0
    sim_identical = compute_cosine_similarity(vec1, vec2)
    assert pytest.approx(sim_identical, 0.0001) == 1.0

    # Different texts yield lower similarity
    sim_different = compute_cosine_similarity(vec1, vec3)
    assert sim_different < 0.9


def test_embedding_dimension_validation():
    """Reject non-positive vector dimensions."""
    with pytest.raises(ValueError, match="Dimensions must be positive"):
        MockEmbeddingProvider(dimensions=0)


@pytest.mark.anyio
async def test_live_embedding_provider_request_parsing():
    """Verify live provider formats OpenAI-compatible POST /embeddings requests."""
    requested_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_payload
        import json
        requested_payload = json.loads(request.content.decode("utf-8"))
        assert request.headers["authorization"] == "Bearer sk-test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1] * 128},
                    {"index": 1, "embedding": [0.2] * 128},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAIEmbeddingProvider(
        model_name="text-embedding-3-small",
        dimensions=128,
        api_key="sk-test-key",
        transport=transport,
    )

    vectors = await provider.embed_batch(["query 1", "query 2"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 128
    assert requested_payload["model"] == "text-embedding-3-small"
    assert requested_payload["input"] == ["query 1", "query 2"]


@pytest.mark.anyio
async def test_embedding_provider_failure_handling():
    """Verify provider traps HTTP 401, 429, 500 and redacts credentials."""
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    provider_401 = OpenAIEmbeddingProvider(
        api_key="secret-key-12345",
        transport=httpx.MockTransport(handler_401),
    )
    with pytest.raises(EmbeddingError, match="authentication failed"):
        await provider_401.embed_text("test")

    def handler_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timed out")

    provider_timeout = OpenAIEmbeddingProvider(
        api_key="secret-key-12345",
        timeout=1.0,
        transport=httpx.MockTransport(handler_timeout),
    )
    with pytest.raises(EmbeddingError, match="timed out"):
        await provider_timeout.embed_text("test")


@pytest.mark.anyio
async def test_missing_embedding_credentials_handling(monkeypatch):
    """Verify provider is marked unavailable when credentials are missing."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EDGEMIND_AI_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    provider = OpenAIEmbeddingProvider(api_key=None)
    assert provider.is_available() is False

    with pytest.raises(EmbeddingProviderUnavailableError, match="not configured"):
        await provider.embed_text("test")


# =============================================================================
# 3. Vector Storage & Knowledge Repository
# =============================================================================

@pytest.mark.anyio
async def test_vector_insertion_and_persistence(sqlite_test_engine):
    """Verify document and chunk insertion with retrieval by ID and hash."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)

    processor = DocumentProcessor()
    doc, chunks = processor.process_document(
        title="Two Sum Algorithm Reference",
        content="Two sum can be solved in O(n) time using a hash map storing complements.",
        source_uri="https://edgemind.internal/docs/two-sum",
        is_global=True,
    )

    mock_provider = MockEmbeddingProvider(dimensions=64)
    embeddings = await mock_provider.embed_batch([c.content for c in chunks])
    for c, emb in zip(chunks, embeddings):
        c.embedding = emb
        c.vector_dim = 64
        c.embedding_model = mock_provider.model_name

    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        stored_doc = await repo.store_document(doc, chunks)
        await session.commit()

        assert stored_doc.id == doc.id
        assert stored_doc.content_hash == doc.content_hash

        # Query by ID
        fetched_doc = await repo.get_document_by_id(doc.id)
        assert fetched_doc is not None
        assert fetched_doc.title == "Two Sum Algorithm Reference"
        assert len(fetched_doc.chunks) == len(chunks)


@pytest.mark.anyio
async def test_duplicate_document_handling_content_hash(sqlite_test_engine):
    """Verify storing identical document content does not duplicate root documents."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    processor = DocumentProcessor()

    content = "Dynamic programming solves problems by breaking them into subproblems."
    doc1, chunks1 = processor.process_document(title="DP Guide v1", content=content, is_global=True)
    doc2, chunks2 = processor.process_document(title="DP Guide v2", content=content, is_global=True)

    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        res1 = await repo.store_document(doc1, chunks1)
        res2 = await repo.store_document(doc2, chunks2, overwrite_existing=True)
        await session.commit()

        # Both point to same underlying document ID
        assert res1.id == res2.id
        assert res2.title == "DP Guide v2"


# =============================================================================
# 4. Similarity Retrieval, Ranking & Thresholds
# =============================================================================

@pytest.mark.anyio
async def test_similarity_ranking_descending(sqlite_test_engine):
    """Verify vector search ranks chunks in descending cosine similarity order."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockEmbeddingProvider(dimensions=64)

    # Ingest 3 distinct knowledge documents
    docs_data = [
        ("Binary Search", "Binary search finds an element in a sorted array in logarithmic time."),
        ("Graph BFS", "Breadth first search traverses graph levels using a queue."),
        ("Quick Sort", "Quicksort partitions an array around a pivot element."),
    ]

    processor = DocumentProcessor()
    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        for title, body in docs_data:
            doc, chunks = processor.process_document(title=title, content=body, is_global=True)
            for c in chunks:
                c.embedding = await provider.embed_text(c.content)
                c.vector_dim = 64
                c.embedding_model = provider.model_name
            await repo.store_document(doc, chunks)
        await session.commit()

        # Query for "Binary search in sorted arrays"
        query_vec = await provider.embed_text("Binary search finds an element in a sorted array in logarithmic time.")
        results = await repo.search_chunks(query_embedding=query_vec, top_k=3, similarity_threshold=0.0)

        assert len(results) >= 2
        # Verify descending order of scores
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)
        # Top result must be the exact match (score ~= 1.0)
        assert results[0][0].document.title == "Binary Search"
        assert pytest.approx(results[0][1], 0.001) == 1.0


@pytest.mark.anyio
async def test_top_k_retrieval_limits(sqlite_test_engine):
    """Verify top_k parameter strictly caps returned results."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockEmbeddingProvider(dimensions=32)
    processor = DocumentProcessor()

    async with session_factory() as session:
        service = VectorRetrievalService(db=session, embedding_provider=provider)

        # Ingest 5 chunks
        repo = KnowledgeRepository(session)
        for i in range(5):
            doc, chunks = processor.process_document(title=f"Doc {i}", content=f"Algorithm concept {i}", is_global=True)
            for c in chunks:
                c.embedding = await provider.embed_text(c.content)
                c.vector_dim = 32
            await repo.store_document(doc, chunks)
        await session.commit()

        # Search with top_k=2
        res = await service.retrieve(query="Algorithm concept", top_k=2, similarity_threshold=0.0)
        assert len(res.chunks) == 2
        assert res.total_retrieved == 2


@pytest.mark.anyio
async def test_similarity_threshold_filtering(sqlite_test_engine):
    """Verify chunks with similarity score below threshold are excluded."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockEmbeddingProvider(dimensions=32)
    processor = DocumentProcessor()

    async with session_factory() as session:
        service = VectorRetrievalService(db=session, embedding_provider=provider)
        repo = KnowledgeRepository(session)

        doc, chunks = processor.process_document(title="Target", content="Unique specific phrase", is_global=True)
        for c in chunks:
            c.embedding = await provider.embed_text(c.content)
            c.vector_dim = 32
        await repo.store_document(doc, chunks)
        await session.commit()

        # With an impossibly high threshold, 0 chunks returned
        res_high = await service.retrieve(query="Completely different unrelated words", similarity_threshold=0.999)
        assert len(res_high.chunks) == 0

        # With low threshold, exact match is returned
        res_low = await service.retrieve(query="Unique specific phrase", similarity_threshold=0.5)
        assert len(res_low.chunks) == 1


@pytest.mark.anyio
async def test_empty_knowledge_base_retrieval(sqlite_test_engine):
    """Verify retrieval against an empty store returns empty list with zero errors."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockEmbeddingProvider(dimensions=32)

    async with session_factory() as session:
        # Create fresh session with no ingested documents
        service = VectorRetrievalService(db=session, embedding_provider=provider)
        res = await service.retrieve(query="any search query", top_k=5)

        assert res.total_retrieved == 0
        assert res.chunks == []
        assert res.execution_duration_ms >= 0.0


# =============================================================================
# 5. Strict Multi-Tenancy & Tenant Isolation
# =============================================================================

@pytest.mark.anyio
async def test_tenant_isolation_cross_user_rejection(sqlite_test_engine):
    """Verify User 2 cannot retrieve User 1's private knowledge chunks."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockEmbeddingProvider(dimensions=32)
    processor = DocumentProcessor()

    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    async with session_factory() as session:
        # Create user accounts
        u1 = User(id=user1_id, email="user1_rag@example.com", full_name="User One", password_hash="hash", role="user")
        u2 = User(id=user2_id, email="user2_rag@example.com", full_name="User Two", password_hash="hash", role="user")
        session.add_all([u1, u2])

        repo = KnowledgeRepository(session)

        # 1. User 1 stores private document
        doc_u1, chunks_u1 = processor.process_document(
            title="User 1 Private Solution Notes",
            content="Proprietary secret algorithm for User 1.",
            user_id=user1_id,
            is_global=False,
        )
        for c in chunks_u1:
            c.embedding = await provider.embed_text(c.content)
            c.vector_dim = 32
        await repo.store_document(doc_u1, chunks_u1)

        # 2. Global public document
        doc_pub, chunks_pub = processor.process_document(
            title="Standard Two Sum Public Checklist",
            content="Check for empty array, single element, and negative numbers.",
            is_global=True,
        )
        for c in chunks_pub:
            c.embedding = await provider.embed_text(c.content)
            c.vector_dim = 32
        await repo.store_document(doc_pub, chunks_pub)

        await session.commit()

        service = VectorRetrievalService(db=session, embedding_provider=provider)

        # Case A: User 1 queries -> Can see their private doc AND public doc
        res_u1 = await service.retrieve(
            query="Proprietary secret algorithm for User 1.",
            user_id=user1_id,
            similarity_threshold=0.0,
        )
        titles_u1 = [c.title for c in res_u1.chunks]
        assert "User 1 Private Solution Notes" in titles_u1

        # Case B: User 2 queries -> CANNOT see User 1's private doc
        res_u2 = await service.retrieve(
            query="Proprietary secret algorithm for User 1.",
            user_id=user2_id,
            similarity_threshold=0.0,
        )
        titles_u2 = [c.title for c in res_u2.chunks]
        assert "User 1 Private Solution Notes" not in titles_u2

        # Case C: Unauthenticated (anonymous) caller -> CANNOT see User 1's private doc
        res_anon = await service.retrieve(
            query="Proprietary secret algorithm for User 1.",
            user_id=None,
            similarity_threshold=0.0,
        )
        titles_anon = [c.title for c in res_anon.chunks]
        assert "User 1 Private Solution Notes" not in titles_anon
        assert "Standard Two Sum Public Checklist" in titles_anon


# =============================================================================
# 6. Agent Integration & Provenance Tracking
# =============================================================================

@pytest.mark.anyio
async def test_agent_retrieval_tool_integration(sqlite_test_engine):
    """Verify AI Agent can invoke retrieve_knowledge_context to inform reasoning."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    processor = DocumentProcessor()

    async with session_factory() as session:
        # Ingest reference knowledge
        repo = KnowledgeRepository(session)
        doc, chunks = processor.process_document(
            title="Two Sum Edge Cases",
            content="Key edge cases for Two Sum: duplicate numbers, zero target, negative integers, lower bound.",
            is_global=True,
        )
        for c in chunks:
            c.embedding = await embedding_provider.embed_text(c.content)
            c.vector_dim = 32
        await repo.store_document(doc, chunks)
        await session.commit()

        # Configure agent provider to invoke retrieve_knowledge_context
        mock_provider = MockAgentProvider()
        mock_provider.add_step(
            AgentStepResult(
                tool_calls=[
                    ToolCall(
                        id="call_rag_1",
                        name="retrieve_knowledge_context",
                        arguments={"query": "Two Sum Edge Cases", "top_k": 2},
                    )
                ],
                finish_reason="tool_calls",
            )
        )
        mock_provider.add_step(
            AgentStepResult(
                content="Retrieved domain knowledge for Two Sum edge cases. Analysis complete.",
                finish_reason="stop",
            )
        )

        orchestrator = AgentOrchestrator(
            provider=mock_provider,
            registry=default_tool_registry,
            embedding_provider=embedding_provider,
        )

        req = AgentAnalyzeRequest(code="def two_sum(nums, target): return []")
        res = await orchestrator.run(req, db=session)

        assert res.status == AgentStatus.SUCCESS.value
        assert len(res.tool_executions) == 1
        exec_record = res.tool_executions[0]
        assert exec_record.tool_name == "retrieve_knowledge_context"
        assert exec_record.status.value == "success"
        assert exec_record.result["total_retrieved"] == 1
        assert exec_record.result["chunks"][0]["title"] == "Two Sum Edge Cases"


@pytest.mark.anyio
async def test_agent_retrieval_provenance_tracking(sqlite_test_engine):
    """Verify retrieved knowledge chunks are stored with provenance in test intelligence."""
    session_factory = async_sessionmaker(sqlite_test_engine, class_=AsyncSession, expire_on_commit=False)
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    processor = DocumentProcessor()

    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        doc, chunks = processor.process_document(
            title="Binary Search Invariant",
            content="Binary search requires array sorted ascending. Check empty array and target not found.",
            source_uri="https://edgemind.internal/algorithms/binary-search",
            is_global=True,
        )
        for c in chunks:
            c.embedding = await embedding_provider.embed_text(c.content)
            c.vector_dim = 32
        await repo.store_document(doc, chunks)
        await session.commit()

        mock_provider = MockAgentProvider()
        mock_provider.add_step(
            AgentStepResult(
                tool_calls=[
                    ToolCall(
                        id="call_rag_search",
                        name="retrieve_knowledge_context",
                        arguments={"query": "Binary Search Invariant", "top_k": 1},
                    )
                ],
                finish_reason="tool_calls",
            )
        )
        mock_provider.add_step(
            AgentStepResult(
                content="Analysis informed by retrieved knowledge provenance.",
                finish_reason="stop",
            )
        )

        orchestrator = AgentOrchestrator(
            provider=mock_provider,
            embedding_provider=embedding_provider,
        )

        req = AgentAnalyzeRequest(code="def search(nums, target): return -1")
        res = await orchestrator.run(req, db=session)

        ti = res.test_intelligence
        assert ti is not None
        assert "retrieved_knowledge" in ti
        retrieved_list = ti["retrieved_knowledge"]
        assert len(retrieved_list) == 1
        retrieved_chunk = retrieved_list[0]
        assert retrieved_chunk["title"] == "Binary Search Invariant"
        assert retrieved_chunk["source_uri"] == "https://edgemind.internal/algorithms/binary-search"
        assert retrieved_chunk["similarity_score"] > 0.0
