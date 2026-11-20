"""
OpenAI-Compatible Live Embedding Provider for EdgeMind RAG.

Communicates with standard /v1/embeddings endpoints (OpenAI or compatible gateways)
with batching, timeout handling, credential redaction, and transport customization.
"""

import logging
import os
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
        if api_key is not None:
            self._api_key = api_key
        else:
            self._api_key = (
                os.environ.get("OPENAI_API_KEY")
                or os.environ.get("EDGEMIND_AI_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or (settings.openai_api_key if "OPENAI_API_KEY" in os.environ else None)
                or (settings.edgemind_ai_key if "EDGEMIND_AI_KEY" in os.environ else None)
            )
        self._base_url = (base_url or getattr(settings, "openai_base_url", "https://api.openai.com/v1")).rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self.settings = settings
        self._last_usage: Optional[Any] = None

    @property
    def last_usage(self) -> Optional[Any]:
        """Return token accounting metadata for the most recent embedding API call."""
        return self._last_usage

    def get_last_usage(self) -> Optional[Any]:
        """Return token accounting metadata for the most recent embedding API call."""
        return self._last_usage

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
        """Generate embedding vectors for a batch of strings with caching."""
        if not texts:
            return []

        from core.redis.cache import build_cache_key, default_cache_service

        results: List[Optional[List[float]]] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []
        cache_keys: List[str] = []

        for idx, text in enumerate(texts):
            key = build_cache_key(
                namespace="embedding",
                key_data=f"{self._model_name}:{self._dimensions}:{text}",
                prefix_override=self.settings.cache_key_prefix,
            )
            cache_keys.append(key)
            cached = await default_cache_service.get(key)
            if cached is not None and isinstance(cached, list):
                results[idx] = cached
            else:
                missing_indices.append(idx)
                missing_texts.append(text)

        # If all texts were cached, return directly
        if not missing_texts:
            return [r for r in results if r is not None]

        # Ensure credentials exist before external API request
        if not self.is_available():
            raise EmbeddingProviderUnavailableError(
                "Embedding API key is not configured. Set OPENAI_API_KEY or EDGEMIND_AI_KEY."
            )

        endpoint = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self._model_name,
            "input": missing_texts,
        }
        if self._dimensions:
            payload["dimensions"] = self._dimensions

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

                if response.status_code == 400:
                    sanitized_err = self.settings.sanitize_error(response.text)
                    raise EmbeddingError(
                        f"Embedding provider rejected request (HTTP 400): {sanitized_err}"
                    )
                elif response.status_code == 401:
                    raise EmbeddingError(
                        "Embedding provider authentication failed (HTTP 401). Invalid API key."
                    )
                elif response.status_code == 403:
                    raise EmbeddingError(
                        "Embedding provider permission failure (HTTP 403). Access denied."
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

        # Extract usage and compute exact Decimal cost (Phase 5)
        raw_usage = data.get("usage")
        req_id = response.headers.get("x-request-id") or data.get("id")
        resp_model = data.get("model") or self._model_name
        if isinstance(raw_usage, dict) and "prompt_tokens" in raw_usage:
            from core.cost import default_cost_calculator, TokenUsage, UsageSource
            prompt_toks = int(raw_usage.get("prompt_tokens", 0))
            total_toks = int(raw_usage.get("total_tokens", prompt_toks))
            cost_bd = default_cost_calculator.calculate_cost(
                prompt_tokens=prompt_toks,
                completion_tokens=0,
                model=resp_model,
            )
            self._last_usage = TokenUsage(
                prompt_tokens=prompt_toks,
                completion_tokens=0,
                total_tokens=total_toks,
                model=resp_model,
                provider="openai",
                request_id=req_id,
                usage_source=UsageSource.ACTUAL_PROVIDER,
                estimated_cost_usd=cost_bd.total_cost if cost_bd.is_pricing_known else None,
                pricing_version=cost_bd.pricing_version if cost_bd.is_pricing_known else None,
                is_estimated_cost_known=cost_bd.is_pricing_known,
            )

        items = data.get("data", [])
        if len(items) != len(missing_texts):
            raise EmbeddingError(
                f"Embedding response item count mismatch: expected {len(missing_texts)}, got {len(items)}"
            )

        # Sort items by 'index' field to preserve order
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        for rel_idx, item in enumerate(sorted_items):
            vec = item.get("embedding", [])
            if self._dimensions and len(vec) != self._dimensions:
                raise EmbeddingDimensionMismatchError(
                    f"Vector dimension {len(vec)} does not match expected {self._dimensions}"
                )
            orig_idx = missing_indices[rel_idx]
            results[orig_idx] = vec
            # Cache generated embedding with 7-day TTL
            await default_cache_service.set(cache_keys[orig_idx], vec, ttl=7 * 86400)

        return [r for r in results if r is not None]

    async def embed_text(self, text: str) -> List[float]:
        """Generate an embedding vector for a single string."""
        batch = await self.embed_batch([text])
        if not batch:
            raise EmbeddingError("No embedding returned for input text.")
        return batch[0]
