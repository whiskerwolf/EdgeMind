"""
EdgeMind Redis & Distributed Caching / Rate Limiting Package.
"""

from core.redis.cache import (
    CacheMetrics,
    CacheService,
    build_cache_key,
    default_cache_service,
    get_cache_service,
    hash_key_data,
)
from core.redis.connection import (
    RedisManager,
    close_redis_pool,
    get_redis,
    init_redis_pool,
    redis_manager,
    sanitize_redis_url,
)
from core.redis.rate_limiter import (
    RateLimit,
    RateLimitDependency,
    RateLimitResult,
    RateLimiterService,
    default_rate_limiter,
    extract_client_ip,
    resolve_rate_limit_identifier,
)

__all__ = [
    # Connection
    "RedisManager",
    "redis_manager",
    "get_redis",
    "init_redis_pool",
    "close_redis_pool",
    "sanitize_redis_url",
    # Cache
    "CacheService",
    "CacheMetrics",
    "default_cache_service",
    "get_cache_service",
    "build_cache_key",
    "hash_key_data",
    # Rate Limiting
    "RateLimiterService",
    "RateLimit",
    "RateLimitDependency",
    "RateLimitResult",
    "default_rate_limiter",
    "extract_client_ip",
    "resolve_rate_limit_identifier",
]
