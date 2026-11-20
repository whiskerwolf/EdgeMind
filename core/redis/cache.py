"""
EdgeMind Reusable Redis Cache Service.

Provides asynchronous, tenant-isolated caching with:
- SHA-256 key hashing for sensitive or variable-length inputs
- JSON serialization with UUID, Decimal, and datetime support
- Configurable TTLs and namespace versioning
- Metric counters (hits, misses, sets, bypasses, errors, hit ratio)
- Non-blocking prefix deletion via SCAN
- Graceful bypass on Redis failure (zero service disruption)
"""

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.config import get_settings
from core.redis.connection import get_redis

logger = logging.getLogger("edgemind.redis.cache")


class CacheJSONEncoder(json.JSONEncoder):
    """
    JSON encoder supporting UUID, datetime, date, Decimal, and dataclass objects.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return super().default(obj)


def hash_key_data(data: Any) -> str:
    """
    Produce a deterministic SHA-256 hex digest of arbitrary key data (string, dict, list).
    Prevents sensitive data disclosure in Redis keyspace and normalizes key length.
    """
    if isinstance(data, str):
        normalized = data.strip().encode("utf-8")
    elif isinstance(data, (int, float, bool)):
        normalized = str(data).encode("utf-8")
    else:
        try:
            normalized = json.dumps(data, sort_keys=True, cls=CacheJSONEncoder).encode("utf-8")
        except Exception:
            normalized = str(data).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def build_cache_key(
    namespace: str,
    key_data: Any,
    tenant_id: Optional[Union[str, uuid.UUID]] = None,
    project_id: Optional[Union[str, uuid.UUID]] = None,
    prefix_override: Optional[str] = None,
) -> str:
    """
    Construct a structured, tenant-isolated cache key with SHA-256 hashed data.

    Structure:
    - Global: {prefix}:global:{namespace}:{sha256}
    - Tenant-only: {prefix}:tenant:{tenant_id}:{namespace}:{sha256}
    - Tenant + Project: {prefix}:tenant:{tenant_id}:project:{project_id}:{namespace}:{sha256}
    """
    settings = get_settings()
    prefix = prefix_override or settings.cache_key_prefix
    clean_ns = namespace.strip(":").lower()
    data_hash = hash_key_data(key_data)

    if tenant_id is not None:
        tid = str(tenant_id).strip()
        if project_id is not None:
            pid = str(project_id).strip()
            return f"{prefix}:tenant:{tid}:project:{pid}:{clean_ns}:{data_hash}"
        return f"{prefix}:tenant:{tid}:{clean_ns}:{data_hash}"

    return f"{prefix}:global:{clean_ns}:{data_hash}"


class CacheMetrics:
    """In-memory counters for cache hits, misses, sets, bypasses, and errors."""

    def __init__(self):
        self.hits: int = 0
        self.misses: int = 0
        self.sets: int = 0
        self.deletes: int = 0
        self.bypasses: int = 0
        self.errors: int = 0

    def record_hit(self) -> None:
        self.hits += 1

    def record_miss(self) -> None:
        self.misses += 1

    def record_set(self) -> None:
        self.sets += 1

    def record_delete(self) -> None:
        self.deletes += 1

    def record_bypass(self) -> None:
        self.bypasses += 1

    def record_error(self) -> None:
        self.errors += 1

    def get_summary(self) -> Dict[str, Any]:
        total_queries = self.hits + self.misses
        ratio = round(self.hits / total_queries, 4) if total_queries > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_queries": total_queries,
            "hit_ratio": ratio,
            "sets": self.sets,
            "deletes": self.deletes,
            "bypasses": self.bypasses,
            "errors": self.errors,
        }

    def reset(self) -> None:
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.bypasses = 0
        self.errors = 0


class CacheService:
    """
    Asynchronous cache service providing tenant-isolated cache operations,
    graceful failure bypass, and metric instrumentation.
    """

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        default_ttl: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        settings = get_settings()
        self._explicit_client = redis_client
        self.default_ttl = default_ttl if default_ttl is not None else settings.cache_default_ttl
        self.enabled = enabled if enabled is not None else settings.cache_enabled
        self.metrics = CacheMetrics()
        self.settings = settings

    async def _get_client(self) -> Optional[Redis]:
        """Obtain active Redis client or return None if caching is disabled/unreachable."""
        if not self.enabled:
            return None
        if self._explicit_client is not None:
            return self._explicit_client
        return await get_redis()

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve and JSON-deserialize a cached value by key.
        Returns None on cache miss, cache disabled, or Redis error (graceful bypass).
        """
        client = await self._get_client()
        if client is None:
            self.metrics.record_bypass()
            return None

        try:
            raw = await client.get(key)
            if raw is None:
                self.metrics.record_miss()
                return None

            try:
                val = json.loads(raw)
                self.metrics.record_hit()
                return val
            except (json.JSONDecodeError, ValueError) as decode_err:
                logger.warning(f"Cache key '{key}' contained malformed JSON. Deleting corrupted entry: {decode_err}")
                await self.delete(key)
                self.metrics.record_miss()
                return None

        except RedisError as exc:
            self.metrics.record_error()
            self.metrics.record_bypass()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.warning(f"Redis get failed on key '{key}': {sanitized}. Bypassing cache.")
            return None
        except Exception as exc:
            self.metrics.record_error()
            self.metrics.record_bypass()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.error(f"Unexpected error in cache get for key '{key}': {sanitized}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Serialize and store a value in cache with an expiration time in seconds.
        Returns True if stored, False if skipped, disabled, or on error.
        """
        client = await self._get_client()
        if client is None:
            self.metrics.record_bypass()
            return False

        effective_ttl = ttl if ttl is not None else self.default_ttl

        try:
            serialized = json.dumps(value, cls=CacheJSONEncoder)
            if effective_ttl and effective_ttl > 0:
                await client.set(key, serialized, ex=effective_ttl)
            else:
                await client.set(key, serialized)
            self.metrics.record_set()
            return True
        except RedisError as exc:
            self.metrics.record_error()
            self.metrics.record_bypass()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.warning(f"Redis set failed for key '{key}': {sanitized}. Continuing without caching.")
            return False
        except Exception as exc:
            self.metrics.record_error()
            self.metrics.record_bypass()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.error(f"Failed to serialize/store value for key '{key}': {sanitized}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Remove a single cache key.
        Returns True if deleted, False otherwise.
        """
        client = await self._get_client()
        if client is None:
            self.metrics.record_bypass()
            return False

        try:
            deleted_count = await client.delete(key)
            if deleted_count > 0:
                self.metrics.record_delete()
                return True
            return False
        except RedisError as exc:
            self.metrics.record_error()
            self.metrics.record_bypass()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.warning(f"Redis delete failed for key '{key}': {sanitized}")
            return False
        except Exception as exc:
            self.metrics.record_error()
            logger.error(f"Unexpected error deleting key '{key}': {exc}")
            return False

    async def delete_prefix(self, prefix: str) -> int:
        """
        Delete all keys matching the given prefix using non-blocking SCAN.
        Returns total number of keys removed.
        """
        client = await self._get_client()
        if client is None:
            self.metrics.record_bypass()
            return 0

        pattern = f"{prefix}*" if not prefix.endswith("*") else prefix
        total_deleted = 0

        try:
            batch: List[str] = []
            async for matched_key in client.scan_iter(match=pattern, count=100):
                batch.append(matched_key)
                if len(batch) >= 100:
                    del_count = await client.delete(*batch)
                    total_deleted += del_count
                    batch = []

            if batch:
                del_count = await client.delete(*batch)
                total_deleted += del_count

            for _ in range(total_deleted):
                self.metrics.record_delete()

            logger.info(f"Invalidated {total_deleted} cache entries matching pattern '{pattern}'")
            return total_deleted

        except RedisError as exc:
            self.metrics.record_error()
            sanitized = self.settings.sanitize_error(str(exc))
            logger.warning(f"Redis delete_prefix failed for pattern '{pattern}': {sanitized}")
            return total_deleted
        except Exception as exc:
            self.metrics.record_error()
            logger.error(f"Unexpected error invalidating prefix '{pattern}': {exc}")
            return total_deleted

    async def invalidate_tenant(
        self,
        tenant_id: Union[str, uuid.UUID],
        project_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> int:
        """
        Invalidate all cached data belonging to a specific tenant (and optional project).
        Guarantees tenant isolation: never affects other tenants' caches.
        """
        settings = get_settings()
        prefix = settings.cache_key_prefix
        tid = str(tenant_id).strip()

        if project_id is not None:
            pid = str(project_id).strip()
            pattern = f"{prefix}:tenant:{tid}:project:{pid}:"
        else:
            pattern = f"{prefix}:tenant:{tid}:"

        return await self.delete_prefix(pattern)

    async def invalidate_namespace(self, namespace: str) -> int:
        """
        Invalidate global cache entries for a specific namespace (e.g. 'embedding').
        """
        settings = get_settings()
        prefix = settings.cache_key_prefix
        clean_ns = namespace.strip(":").lower()
        pattern = f"{prefix}:global:{clean_ns}:"
        return await self.delete_prefix(pattern)

    async def invalidate_global_retrieval(self) -> int:
        """
        Invalidate all global RAG retrieval cache entries.
        """
        settings = get_settings()
        prefix = settings.cache_key_prefix
        pattern = f"{prefix}:global:rag_retrieval:"
        return await self.delete_prefix(pattern)

    def get_metrics(self) -> Dict[str, Any]:
        """Return snapshot of hit, miss, bypass, set, and error counts."""
        return self.metrics.get_summary()

    def reset_metrics(self) -> None:
        """Reset metric counters."""
        self.metrics.reset()


# Default singleton cache service
default_cache_service = CacheService()


def get_cache_service() -> CacheService:
    """Dependency provider returning singleton CacheService."""
    return default_cache_service
