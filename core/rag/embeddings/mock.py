"""
Deterministic Mock Embedding Provider for Automated Testing and CI.

Generates reproducible, L2-normalized unit vectors from text content
without external API calls or network access.
"""

import hashlib
import math
import random
import re
from typing import List

from core.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingProviderUnavailableError,
)


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic embedding provider for CI pipelines and reproducible tests.
    Produces unit-length vectors derived deterministically from text hashes.
    """

    def __init__(
        self,
        model_name: str = "mock-embedding-v1",
        dimensions: int = 1536,
        simulate_failure: bool = False,
        simulate_unavailable: bool = False,
    ):
        if dimensions <= 0:
            raise ValueError(f"Dimensions must be positive, got {dimensions}")
        self._model_name = model_name
        self._dimensions = dimensions
        self._simulate_failure = simulate_failure
        self._simulate_unavailable = simulate_unavailable

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def is_available(self) -> bool:
        return not self._simulate_unavailable

    def _generate_vector(self, text: str) -> List[float]:
        """Generate a deterministic L2-normalized float vector from text content and tokens."""
        if self._simulate_failure:
            raise RuntimeError("Simulated mock embedding provider internal failure.")

        if self._simulate_unavailable:
            raise EmbeddingProviderUnavailableError("Mock embedding provider is marked unavailable.")

        # Extract tokens for semantic overlap simulation
        words = re.findall(r"\w+", text.lower())
        if not words:
            words = [text.strip().lower() or "empty"]

        accum = [0.0] * self._dimensions

        # Blend word token vectors
        for word in words:
            seed = int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:8], "big")
            rng = random.Random(seed)
            for i in range(self._dimensions):
                accum[i] += rng.gauss(0.0, 1.0)

        # Normalize to unit length (L2 norm = 1.0)
        norm = math.sqrt(sum(x * x for x in accum))
        if norm == 0.0:
            norm = 1.0
        normalized = [round(x / norm, 6) for x in accum]

        if len(normalized) != self._dimensions:
            raise EmbeddingDimensionMismatchError(
                f"Generated vector length {len(normalized)} does not match {self._dimensions}"
            )

        return normalized

    async def embed_text(self, text: str) -> List[float]:
        return self._generate_vector(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]
