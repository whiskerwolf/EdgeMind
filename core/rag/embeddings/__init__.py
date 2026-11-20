"""Embedding providers for EdgeMind RAG."""

import os
from typing import Optional

from core.config import get_settings
from core.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
)
from core.rag.embeddings.mock import MockEmbeddingProvider
from core.rag.embeddings.ollama_provider import OllamaEmbeddingProvider
from core.rag.embeddings.openai_provider import OpenAIEmbeddingProvider


def get_rag_embedding_provider(
    provider_type: Optional[str] = None,
) -> BaseEmbeddingProvider:
    """
    Factory function for RAG embedding providers.
    Supports 'ollama', 'openai', and 'mock'.
    """
    settings = get_settings()
    ptype = (
        provider_type
        or os.environ.get("RAG_EMBEDDING_PROVIDER")
        or os.environ.get("EDGEMIND_RAG_EMBEDDING_PROVIDER")
        or getattr(settings, "rag_embedding_provider", "ollama")
    ).lower()

    if ptype == "ollama":
        base_url = (
            os.environ.get("OLLAMA_BASE_URL")
            or os.environ.get("EDGEMIND_OLLAMA_BASE_URL")
            or settings.ollama_base_url
        )
        return OllamaEmbeddingProvider(
            base_url=base_url,
            model_name=os.environ.get("OLLAMA_EMBEDDING_MODEL") or getattr(settings, "ollama_embedding_model", "all-minilm:latest"),
            dimensions=int(os.environ.get("OLLAMA_EMBEDDING_DIMENSIONS") or getattr(settings, "ollama_embedding_dimensions", 384)),
            timeout=getattr(settings, "ollama_timeout", 60.0),
        )
    elif ptype == "openai":
        return OpenAIEmbeddingProvider(
            model_name=settings.rag_embedding_model,
            dimensions=settings.rag_embedding_dimensions,
        )
    elif ptype == "mock":
        return MockEmbeddingProvider(
            model_name=getattr(settings, "mock_embedding_model", "mock-embedding-v1"),
            dimensions=getattr(settings, "rag_embedding_dimensions", 1536),
        )
    else:
        return MockEmbeddingProvider()


__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingDimensionMismatchError",
    "EmbeddingError",
    "EmbeddingProviderUnavailableError",
    "MockEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_rag_embedding_provider",
]
