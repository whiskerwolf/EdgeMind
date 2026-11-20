"""
Ollama Embedding Provider for EdgeMind Local RAG Pipeline.

Uses local Ollama /api/embed endpoint with model identification,
strict vector dimension enforcement (384 dimensions for all-minilm:latest),
Redis caching, and unauthenticated local token accounting.
"""

from decimal import Decimal
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union
import uuid

import httpx

from core.config import get_settings
from core.cost.models import TokenUsage, UsageSource
from core.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingProviderUnavailableError,
)

logger = logging.getLogger("edgemind.rag.embeddings.ollama")


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """
    Local Ollama Embedding Provider utilizing POST /api/embed.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        dimensions: Optional[int] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        settings = get_settings()
        self.settings = settings
        self._base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or os.environ.get("EDGEMIND_OLLAMA_BASE_URL")
            or getattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
        ).rstrip("/")
        self._model_name = (
            model_name
            or os.environ.get("OLLAMA_EMBEDDING_MODEL")
            or os.environ.get("EDGEMIND_OLLAMA_EMBEDDING_MODEL")
            or getattr(settings, "ollama_embedding_model", "all-minilm:latest")
        )
        self._dimensions = (
            dimensions
            if dimensions is not None
            else int(
                os.environ.get("OLLAMA_EMBEDDING_DIMENSIONS")
                or os.environ.get("EDGEMIND_OLLAMA_EMBEDDING_DIMENSIONS")
                or getattr(settings, "ollama_embedding_dimensions", 384)
            )
        )
        self._timeout = timeout if timeout is not None else getattr(settings, "ollama_timeout", 60.0)
        self._transport = transport
        self._last_usage: Optional[TokenUsage] = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def last_usage(self) -> Optional[TokenUsage]:
        """Return the TokenUsage of the most recent embedding call, if available."""
        return self._last_usage

    def is_available(self) -> bool:
        """Return True if base_url is configured."""
        return bool(self._base_url and self._base_url.strip())

    async def embed_batch(
        self,
        texts: List[str],
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        project_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[List[float]]:
        """
        Generate embedding vectors for a batch of strings using POST /api/embed.
        Integrates Redis caching per item.
        """
        if not texts:
            return []

        from core.redis.cache import build_cache_key, default_cache_service

        results: List[Optional[List[float]]] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []
        cache_keys: List[str] = []

        for idx, text in enumerate(texts):
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            key = build_cache_key(
                namespace="embedding",
                key_data={
                    "provider": self.provider_name,
                    "model": self._model_name,
                    "dimensions": self._dimensions,
                    "hash": text_hash,
                },
                tenant_id=tenant_id,
                project_id=project_id,
                prefix_override=self.settings.cache_key_prefix,
            )
            cache_keys.append(key)
            cached = await default_cache_service.get(key)
            if cached is not None and isinstance(cached, list):
                results[idx] = cached
            else:
                missing_indices.append(idx)
                missing_texts.append(text)

        # If all texts were resolved from cache, return immediately
        if not missing_texts:
            return [r for r in results if r is not None]

        endpoint = f"{self._base_url}/api/embed"
        payload = {
            "model": self._model_name,
            "input": missing_texts,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(endpoint, json=payload)

                if response.status_code == 404:
                    raise EmbeddingError(
                        f"Ollama model '{self._model_name}' not found. "
                        f"Ensure it is installed using 'ollama pull {self._model_name}'."
                    )
                elif response.status_code == 400:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    raise EmbeddingError(
                        f"Ollama rejected embedding request (HTTP 400): {sanitized_err}"
                    )
                elif response.status_code >= 500:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    raise EmbeddingProviderUnavailableError(
                        f"Ollama server error (HTTP {response.status_code}): {sanitized_err}"
                    )
                elif response.status_code != 200:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    raise EmbeddingError(
                        f"Ollama embedding request failed (HTTP {response.status_code}): {sanitized_err}"
                    )

                data = response.json()

        except httpx.ConnectError as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            raise EmbeddingProviderUnavailableError(
                f"Ollama service unavailable at {self._base_url}: {sanitized}"
            ) from exc
        except httpx.TimeoutException as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            raise EmbeddingError(
                f"Ollama embedding request timed out after {self._timeout}s: {sanitized}"
            ) from exc
        except (EmbeddingError, EmbeddingProviderUnavailableError):
            raise
        except Exception as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            raise EmbeddingError(f"Ollama embedding unexpected error: {sanitized}") from exc

        # Parse embeddings from response
        raw_embeddings = data.get("embeddings", [])
        if len(raw_embeddings) != len(missing_texts):
            raise EmbeddingError(
                f"Ollama response count mismatch: expected {len(missing_texts)}, got {len(raw_embeddings)}"
            )

        # Validate vector dimensions
        for vec in raw_embeddings:
            if len(vec) != self._dimensions:
                raise EmbeddingDimensionMismatchError(
                    f"Vector dimension {len(vec)} does not match expected {self._dimensions}"
                )

        # Local inference token accounting
        prompt_eval_count = data.get("prompt_eval_count")
        actual_model = data.get("model", self._model_name)
        if prompt_eval_count is not None:
            self._last_usage = TokenUsage(
                prompt_tokens=int(prompt_eval_count),
                completion_tokens=0,
                total_tokens=int(prompt_eval_count),
                model=actual_model,
                provider="ollama",
                request_id=response.headers.get("x-request-id"),
                usage_source=UsageSource.LOCAL_INFERENCE,
                estimated_cost_usd=None,
                pricing_version=None,
                is_estimated_cost_known=False,
            )

        # Populate results and store in Redis cache with 7-day TTL
        for rel_idx, vec in enumerate(raw_embeddings):
            orig_idx = missing_indices[rel_idx]
            results[orig_idx] = vec
            await default_cache_service.set(cache_keys[orig_idx], vec, ttl=7 * 86400)

        return [r for r in results if r is not None]

    async def embed_text(
        self,
        text: str,
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        project_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[float]:
        """Generate an embedding vector for a single string."""
        if not text:
            return [0.0] * self._dimensions
        vectors = await self.embed_batch([text], tenant_id=tenant_id, project_id=project_id)
        if not vectors:
            raise EmbeddingError("Ollama failed to return an embedding for input text.")
        return vectors[0]
