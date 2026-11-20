"""
EdgeMind Redis Connection & Pool Management Module.

Provides asynchronous Redis connection pooling, health checks, credential sanitization,
and FastAPI lifespan management using redis.asyncio.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional
from urllib.parse import urlparse

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from core.config import get_settings

logger = logging.getLogger("edgemind.redis.connection")


def sanitize_redis_url(url: Optional[str]) -> str:
    """
    Mask passwords in Redis connection URLs to prevent credential leakage in logs.
    e.g. 'redis://:supersecret@127.0.0.1:6379/0' -> 'redis://:***@127.0.0.1:6379/0'
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Reconstruct with masked password
            netloc = parsed.hostname or "localhost"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            user_part = f"{parsed.username or ''}:***@"
            return f"{parsed.scheme}://{user_part}{netloc}{parsed.path}"
        return url
    except Exception:
        return "redis://***"


class RedisManager:
    """
    Manages singleton Redis connection pools and client instances for caching
    and distributed rate limiting, supporting dedicated isolated instances.
    """

    def __init__(self):
        # Cache Redis
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._override_client: Optional[Any] = None

        # Rate Limiting Redis (dedicated instance)
        self._rate_limit_pool: Optional[ConnectionPool] = None
        self._rate_limit_client: Optional[Redis] = None
        self._override_rate_limit_client: Optional[Any] = None

        self._lock = asyncio.Lock()

    @property
    def is_initialized(self) -> bool:
        """Return True if any client or override client is active."""
        return (
            self._override_client is not None
            or self._client is not None
            or self._override_rate_limit_client is not None
            or self._rate_limit_client is not None
        )

    def set_override_client(self, client: Optional[Any]) -> None:
        """
        Set a custom or mock Redis client for caching (primarily for isolated unit tests).
        Passing None clears the override.
        """
        self._override_client = client

    def set_override_rate_limit_client(self, client: Optional[Any]) -> None:
        """
        Set a custom or mock Redis client for rate limiting.
        Passing None clears the override.
        """
        self._override_rate_limit_client = client

    async def get_client(self) -> Optional[Redis]:
        """
        Retrieve active Cache Redis client, initializing pool on first use if configured.
        Returns None if Redis is not configured or unavailable.
        """
        if self._override_client is not None:
            return self._override_client

        if self._client is not None:
            return self._client

        async with self._lock:
            if self._override_client is not None:
                return self._override_client
            if self._client is not None:
                return self._client

            settings = get_settings()
            if not settings.is_redis_enabled:
                return None

            # Validate security requirements in production
            settings.validate_redis_security()

            url = settings.redis_url or settings.redis_rate_limit_url
            if not url or not url.strip():
                return None

            try:
                sanitized = sanitize_redis_url(url)
                logger.info(f"Initializing Cache Redis connection pool to {sanitized}")
                pool_kwargs = {
                    "max_connections": settings.redis_pool_size,
                    "socket_connect_timeout": settings.redis_connect_timeout,
                    "socket_timeout": settings.redis_socket_timeout,
                    "decode_responses": True,
                }
                password = settings.redis_password
                if password and "@" not in url:
                    pool_kwargs["password"] = password

                self._pool = ConnectionPool.from_url(
                    url,
                    **pool_kwargs,
                )
                self._client = Redis(connection_pool=self._pool)
                await self._client.ping()
                logger.info("Successfully connected to Cache Redis.")
                return self._client
            except Exception as exc:
                sanitized_err = settings.sanitize_error(str(exc))
                logger.warning(
                    f"Failed to connect to Cache Redis during initialization: {sanitized_err}. "
                    "Operating in degraded / bypass mode."
                )
                if self._client:
                    try:
                        await self._client.aclose()
                    except Exception:
                        pass
                    self._client = None
                if self._pool:
                    try:
                        await self._pool.disconnect()
                    except Exception:
                        pass
                    self._pool = None
                return None

    async def get_rate_limit_client(self) -> Optional[Redis]:
        """
        Retrieve active Rate Limit Redis client.
        If a dedicated redis_rate_limit_url is configured, connects to that instance.
        Otherwise falls back to the primary cache Redis client.
        """
        if self._override_rate_limit_client is not None:
            return self._override_rate_limit_client

        settings = get_settings()
        if not settings.is_rate_limit_redis_dedicated:
            # Shared Redis configuration
            if self._override_client is not None:
                return self._override_client
            return await self.get_client()

        if self._rate_limit_client is not None:
            return self._rate_limit_client

        async with self._lock:
            if self._override_rate_limit_client is not None:
                return self._override_rate_limit_client
            if self._rate_limit_client is not None:
                return self._rate_limit_client

            # Validate security requirements in production
            settings.validate_redis_security()

            url = settings.redis_rate_limit_url
            if not url or not url.strip():
                return await self.get_client()

            try:
                sanitized = sanitize_redis_url(url)
                logger.info(f"Initializing dedicated Rate Limit Redis connection pool to {sanitized}")
                pool_kwargs = {
                    "max_connections": settings.redis_pool_size,
                    "socket_connect_timeout": settings.redis_connect_timeout,
                    "socket_timeout": settings.redis_socket_timeout,
                    "decode_responses": True,
                }
                password = settings.redis_rate_limit_password or settings.redis_password
                if password and "@" not in url:
                    pool_kwargs["password"] = password

                self._rate_limit_pool = ConnectionPool.from_url(
                    url,
                    **pool_kwargs,
                )
                self._rate_limit_client = Redis(connection_pool=self._rate_limit_pool)
                await self._rate_limit_client.ping()
                logger.info("Successfully connected to dedicated Rate Limit Redis.")
                return self._rate_limit_client
            except Exception as exc:
                sanitized_err = settings.sanitize_error(str(exc))
                logger.warning(
                    f"Failed to connect to dedicated Rate Limit Redis: {sanitized_err}."
                )
                if self._rate_limit_client:
                    try:
                        await self._rate_limit_client.aclose()
                    except Exception:
                        pass
                    self._rate_limit_client = None
                if self._rate_limit_pool:
                    try:
                        await self._rate_limit_pool.disconnect()
                    except Exception:
                        pass
                    self._rate_limit_pool = None
                return None

    async def ping(self) -> bool:
        """
        Check whether Redis connection is alive and responding.
        Returns False without raising exceptions if unreachable.
        """
        client = await self.get_client()
        if client is None:
            return False
        try:
            res = await client.ping()
            return bool(res)
        except Exception as exc:
            settings = get_settings()
            logger.debug(f"Redis ping check failed: {settings.sanitize_error(str(exc))}")
            return False

    async def check_health(self) -> Dict[str, Any]:
        """
        Produce structured, sanitized health metadata for monitoring and diagnostics.
        Zero credential disclosure guaranteed.
        """
        settings = get_settings()
        if not settings.is_redis_enabled and self._override_client is None:
            return {
                "status": "disabled",
                "configured": False,
                "reachable": False,
                "message": "Redis is not configured in environment.",
            }

        client = await self.get_client()
        if client is None:
            return {
                "status": "unhealthy",
                "configured": True,
                "reachable": False,
                "message": "Redis is configured but connection could not be established.",
            }

        try:
            start = asyncio.get_event_loop().time()
            alive = await client.ping()
            latency_ms = round((asyncio.get_event_loop().time() - start) * 1000.0, 2)
            res = {
                "status": "healthy" if alive else "unhealthy",
                "configured": True,
                "reachable": bool(alive),
                "latency_ms": latency_ms,
                "dedicated_rate_limiter": settings.is_rate_limit_redis_dedicated,
            }
            if settings.is_rate_limit_redis_dedicated:
                rl_client = await self.get_rate_limit_client()
                rl_alive = bool(rl_client and await rl_client.ping())
                res["rate_limiter_reachable"] = rl_alive
            return res
        except Exception as exc:
            return {
                "status": "unhealthy",
                "configured": True,
                "reachable": False,
                "error": settings.sanitize_error(str(exc)),
            }

    async def close(self) -> None:
        """
        Gracefully dispose all Redis clients and connection pools during application shutdown.
        """
        async with self._lock:
            # Dispose Cache Redis
            if self._client is not None:
                try:
                    await self._client.aclose()
                    logger.info("Closed Cache Redis client connection.")
                except Exception as exc:
                    logger.warning(f"Error closing Cache Redis client: {exc}")
                self._client = None

            if self._pool is not None:
                try:
                    await self._pool.disconnect()
                    logger.info("Disconnected Cache Redis connection pool.")
                except Exception as exc:
                    logger.warning(f"Error disconnecting Cache Redis pool: {exc}")
                self._pool = None

            # Dispose Rate Limit Redis
            if self._rate_limit_client is not None:
                try:
                    await self._rate_limit_client.aclose()
                    logger.info("Closed Rate Limit Redis client connection.")
                except Exception as exc:
                    logger.warning(f"Error closing Rate Limit Redis client: {exc}")
                self._rate_limit_client = None

            if self._rate_limit_pool is not None:
                try:
                    await self._rate_limit_pool.disconnect()
                    logger.info("Disconnected Rate Limit Redis connection pool.")
                except Exception as exc:
                    logger.warning(f"Error disconnecting Rate Limit Redis pool: {exc}")
                self._rate_limit_pool = None

    def reset(self) -> None:
        """Reset internal references for test isolation."""
        self._override_client = None
        self._client = None
        self._pool = None
        self._override_rate_limit_client = None
        self._rate_limit_client = None
        self._rate_limit_pool = None


# Global singleton manager
redis_manager = RedisManager()


async def get_redis() -> Optional[Redis]:
    """
    FastAPI dependency and utility function to acquire the Cache Redis client.
    Returns None if Redis is not configured or currently unreachable.
    """
    return await redis_manager.get_client()


async def get_rate_limit_redis() -> Optional[Redis]:
    """
    FastAPI dependency and utility function to acquire the Rate Limit Redis client.
    Connects to the dedicated rate-limit instance if configured.
    """
    return await redis_manager.get_rate_limit_client()


async def init_redis_pool() -> Optional[Redis]:
    """Initialize Redis pools on application startup."""
    client = await redis_manager.get_client()
    settings = get_settings()
    if settings.is_rate_limit_redis_dedicated:
        await redis_manager.get_rate_limit_client()
    return client


async def close_redis_pool() -> None:
    """Close Redis pools on application shutdown."""
    await redis_manager.close()
