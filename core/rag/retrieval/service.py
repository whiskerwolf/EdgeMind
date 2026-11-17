"""
Vector Similarity Retrieval Service for EdgeMind RAG.

Orchestrates embedding generation, vector similarity search,
re-ranking, threshold filtering, and tenant-isolated knowledge retrieval.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.rag.embeddings.base import BaseEmbeddingProvider
from core.rag.embeddings.mock import MockEmbeddingProvider
from core.rag.embeddings.openai_provider import OpenAIEmbeddingProvider

logger = logging.getLogger("edgemind.rag.retrieval.service")


@dataclass
class RetrievedChunk:
    """A scored knowledge chunk returned from similarity retrieval."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    content: str
    similarity_score: float
    source_uri: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_global: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "title": self.title,
            "content": self.content,
            "similarity_score": round(self.similarity_score, 4),
            "source_uri": self.source_uri,
            "metadata": self.metadata,
            "is_global": self.is_global,
        }


@dataclass
class RetrievalResult:
    """Full structured result of a similarity retrieval operation."""
    query: str
    top_k: int
    similarity_threshold: float
    chunks: List[RetrievedChunk]
    total_retrieved: int
    execution_duration_ms: float
    embedding_model: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "similarity_threshold": self.similarity_threshold,
            "chunks": [c.to_dict() for c in self.chunks],
            "total_retrieved": self.total_retrieved,
            "execution_duration_ms": round(self.execution_duration_ms, 2),
            "embedding_model": self.embedding_model,
        }


class VectorRetrievalService:
    """
    Coordinates semantic vector retrieval against the knowledge store.
    """

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        default_top_k: Optional[int] = None,
        default_similarity_threshold: Optional[float] = None,
    ):
        settings = get_settings()
        self.db = db
        if embedding_provider:
            self.embedding_provider = embedding_provider
        else:
            live = OpenAIEmbeddingProvider()
            self.embedding_provider = live if live.is_available() else MockEmbeddingProvider()

        self.top_k = default_top_k or settings.rag_top_k
        self.similarity_threshold = (
            default_similarity_threshold
            if default_similarity_threshold is not None
            else settings.rag_similarity_threshold
        )

    async def retrieve(
        self,
        query: str,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Execute semantic vector similarity retrieval:
        1. Validates and normalizes query text.
        2. Generates query embedding vector.
        3. Queries KnowledgeRepository with strict tenant isolation filter.
        4. Calculates cosine similarity and filters by threshold.
        5. Ranks and returns top-k chunks with source metadata.
        """
        start_time = time.perf_counter()
        k = top_k or self.top_k
        threshold = similarity_threshold if similarity_threshold is not None else self.similarity_threshold

        clean_query = query.strip()
        if not clean_query:
            duration = (time.perf_counter() - start_time) * 1000.0
            return RetrievalResult(
                query="",
                top_k=k,
                similarity_threshold=threshold,
                chunks=[],
                total_retrieved=0,
                execution_duration_ms=duration,
                embedding_model=self.embedding_provider.model_name,
            )

        # Truncate query if excessive to prevent embedding DoS
        if len(clean_query) > 2000:
            clean_query = clean_query[:2000]

        # 1. Generate query embedding
        try:
            query_embedding = await self.embedding_provider.embed_text(clean_query)
        except Exception as exc:
            logger.error(f"Failed to generate query embedding: {exc}")
            duration = (time.perf_counter() - start_time) * 1000.0
            return RetrievalResult(
                query=clean_query,
                top_k=k,
                similarity_threshold=threshold,
                chunks=[],
                total_retrieved=0,
                execution_duration_ms=duration,
                embedding_model=self.embedding_provider.model_name,
            )

        # 2. If database is not attached (or in-memory mock context)
        if self.db is None:
            duration = (time.perf_counter() - start_time) * 1000.0
            return RetrievalResult(
                query=clean_query,
                top_k=k,
                similarity_threshold=threshold,
                chunks=[],
                total_retrieved=0,
                execution_duration_ms=duration,
                embedding_model=self.embedding_provider.model_name,
            )

        # 3. Query repository
        from core.database.repositories.knowledge_repository import KnowledgeRepository
        repo = KnowledgeRepository(self.db)
        scored_chunks = await repo.search_chunks(
            query_embedding=query_embedding,
            user_id=user_id,
            project_id=project_id,
            top_k=k,
            similarity_threshold=threshold,
        )

        retrieved: List[RetrievedChunk] = []
        for chunk, score in scored_chunks:
            title = chunk.document.title if chunk.document else "Knowledge Reference"
            source_uri = chunk.document.source_uri if chunk.document else None
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=title,
                    content=chunk.content,
                    similarity_score=score,
                    source_uri=source_uri,
                    metadata=chunk.chunk_metadata,
                    is_global=chunk.is_global,
                )
            )

        duration = (time.perf_counter() - start_time) * 1000.0
        return RetrievalResult(
            query=clean_query,
            top_k=k,
            similarity_threshold=threshold,
            chunks=retrieved,
            total_retrieved=len(retrieved),
            execution_duration_ms=duration,
            embedding_model=self.embedding_provider.model_name,
        )
