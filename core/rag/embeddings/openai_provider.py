"""
OpenAI-Compatible Live Embedding Provider for EdgeMind RAG.

Communicates with standard /v1/embeddings endpoints (OpenAI or compatible gateways)
with batching, timeout handling, credential redaction, and transport customization.
"""

import logging
from typing import Any, Dict, List, Optional
import httpx

from core.config import get_settings
from core.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
)

logger = logging.getLogger("edgemind.rag.embeddings.openai")


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """
    Live embedding provider using standard OpenAI-compatible REST API endpoints.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimensions: Optional[int] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        settings = get_settings()
        self._model_name = model_name or settings.rag_embedding_model
        self._dimensions = dimensions or settings.rag_embedding_dimensions
        self._api_key = api_key or settings.openai_api_key or settings.get_ai_api_key()
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self.settings = settings

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def is_available(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self._api_key and str(self._api_key).strip())

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of strings."""
        if not self.is_available():
            raise EmbeddingProviderUnavailableError(
                "Embedding API key is not configured. Set OPENAI_API_KEY or EDGEMIND_AI_KEY."
            )

        if not texts:
            return []

        endpoint = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self._model_name,
            "input": texts,
        }
        if self._dimensions:
            payload["dimensions"] = self._dimensions

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

                if response.status_code == 401:
                    raise EmbeddingError(
                        "Embedding provider authentication failed (HTTP 401). Invalid API key."
                    )
                elif response.status_code == 429:
                    raise EmbeddingError(
                        "Embedding provider rate limit exceeded (HTTP 429)."
                    )
                elif response.status_code >= 500:
                    raise EmbeddingError(
                        f"Embedding provider internal server error (HTTP {response.status_code})."
                    )

                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            raise EmbeddingError(f"Embedding request timed out ({self._timeout}s): {sanitized}") from exc
        except httpx.RequestError as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            raise EmbeddingError(f"Embedding network connection error: {sanitized}") from exc

        items = data.get("data", [])
        if len(items) != len(texts):
            raise EmbeddingError(
                f"Embedding response item count mismatch: expected {len(texts)}, got {len(items)}"
            )

        # Sort items by 'index' field to preserve order
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        vectors: List[List[float]] = []
        for item in sorted_items:
            vec = item.get("embedding", [])
            if self._dimensions and len(vec) != self._dimensions:
                raise EmbeddingDimensionMismatchError(
                    f"Vector dimension {len(vec)} does not match expected {self._dimensions}"
                )
            vectors.append(vec)

        return vectors

    async def embed_text(self, text: str) -> List[float]:
        """Generate an embedding vector for a single string."""
        batch = await self.embed_batch([text])
        if not batch:
            raise EmbeddingError("No embedding returned for input text.")
        return batch[0]
