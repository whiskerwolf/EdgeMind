"""
EdgeMind RAG (Retrieval-Augmented Generation) Package.

Modular embeddings, document chunking, PostgreSQL vector storage,
and semantic vector retrieval integrated with the AI agent.
"""

from core.rag.embeddings import (
    BaseEmbeddingProvider,
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

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingDimensionMismatchError",
    "EmbeddingError",
    "EmbeddingProviderUnavailableError",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "DocumentProcessor",
    "ProcessedChunk",
    "ProcessedDocument",
    "RetrievalResult",
    "RetrievedChunk",
    "VectorRetrievalService",
]
