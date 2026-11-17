"""
Abstract Base Embedding Provider for EdgeMind RAG Pipeline.

Defines the interface for text embedding generation with vector dimension enforcement,
batching support, provider availability checks, and error sanitization.
"""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingError(Exception):
    """Base exception for all embedding generation errors."""
    pass


class EmbeddingProviderUnavailableError(EmbeddingError):
    """Raised when an embedding provider API key is missing or endpoint unreachable."""
    pass


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when returned vector dimension does not match configured dimension."""
    pass


class BaseEmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier name (e.g. 'mock', 'openai', 'gemini')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Embedding model identifier (e.g. 'text-embedding-3-small')."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimension size (e.g. 1536)."""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate a single normalized embedding vector for the given text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate a batch of normalized embedding vectors for the given texts."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is fully configured with required credentials."""
        pass
