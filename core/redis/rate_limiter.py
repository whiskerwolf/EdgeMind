"""
EdgeMind Distributed Sliding-Window Rate Limiter.

Features:
- Atomic Redis sliding-window tracking via custom Lua script
- Tenant/User-aware rate limiting (authenticated user > client IP)
- Trusted proxy validation (defending against X-Forwarded-For header spoofing)
- Standard HTTP 429 responses with Retry-After and X-RateLimit-* headers
- Configurable failure policy (production fail-closed vs testing fail-open)
- Stream-safe: 1 streaming session = 1 charge
"""

from dataclasses import dataclass
import ipaddress
import logging
import math
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import uuid

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.auth.dependencies import get_optional_current_user
from core.config import get_settings
from core.database.models import User
from core.redis.connection import get_rate_limit_redis

logger = logging.getLogger("edgemind.redis.rate_limiter")

# Atomic Sliding-Window Lua Script
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local nonce = ARGV[4]

-- 1. Prefer Redis server TIME to eliminate application clock drift
local now_ms = tonumber(ARGV[1])
local ok, time_res = pcall(redis.call, 'TIME')
if ok and time_res and #time_res >= 2 then
    local sec = tonumber(time_res[1])
    local usec = tonumber(time_res[2])
    if sec and usec then
        now_ms = (sec * 1000) + math.floor(usec / 1000)
    end
end

-- 2. Construct unique member: ensures simultaneous same-ms requests never collapse
local member = tostring(now_ms) .. ':' .. tostring(nonce)

local clear_before = now_ms - window_ms

-- 3. Prune entries outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

-- 4. Count active requests in window
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- 5. Allowed: record unique member with score = now_ms
    redis.call('ZADD', key, now_ms, member)
    local ttl_seconds = math.ceil(window_ms / 1000) + 2
    redis.call('EXPIRE', key, ttl_seconds)
    local remaining = limit - (current_count + 1)
    return {1, current_count + 1, remaining, 0, now_ms}
else
    -- 6. Exceeded: calculate exact retry-after based on oldest member in window
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        local oldest_score = tonumber(oldest[2])
        local expires_at = oldest_score + window_ms
        local diff_ms = expires_at - now_ms
        if diff_ms > 0 then
            retry_after = math.ceil(diff_ms / 1000)
        end
    end
    return {0, current_count, 0, retry_after, now_ms}
end
"""


@dataclass
class RateLimitResult:
    """Outcome of a rate-limit check."""
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    retry_after: int
    reset_epoch: int
    identifier: str
    resource: str

    @property
    def headers(self) -> Dict[str, str]:
        """Construct standard HTTP rate-limiting headers."""
        h = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }
        if not self.allowed and self.retry_after > 0:
            h["Retry-After"] = str(self.retry_after)
        return h


def extract_client_ip(request: Request, trusted_proxies: Optional[List[str]] = None) -> str:
    """
    Extract genuine client IP address while preventing header spoofing attacks.

    Security Rules:
    1. Direct TCP host (request.client.host) is always inspected first.
    2. If direct host is NOT in trusted_proxies, X-Forwarded-For is completely IGNORED.
    3. If direct host IS in trusted_proxies, X-Forwarded-For is parsed to retrieve the
       genuine client IP.
    """
    settings = get_settings()
    trusted = set(trusted_proxies or settings.trusted_proxy_ips)

    direct_host = request.client.host if request.client else "127.0.0.1"

    # If the direct peer is not a trusted reverse proxy, use direct host directly
    if direct_host not in trusted:
        return direct_host

    # Direct peer IS trusted: check X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        # Check X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
        return direct_host

    # Split comma-separated chain (client, proxy1, proxy2)
    # The genuine client IP is the first entry from the left
    ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
    if not ips:
        return direct_host

    # Validate IP address syntax
    candidate = ips[0]
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        logger.warning(f"Malformed IP '{candidate}' in X-Forwarded-For header. Falling back to direct host.")
        return direct_host


def resolve_rate_limit_identifier(
    request: Request,
    current_user: Optional[User] = None,
    trusted_proxies: Optional[List[str]] = None,
) -> str:
    """
    Determine unique rate limit identifier:
    - Authenticated users are keyed by user ID (prevents IP hopping by authenticated abusers).
    - Unauthenticated callers are keyed by verified client IP.
    """
    if current_user is not None and getattr(current_user, "id", None):
        return f"user:{current_user.id}"

    client_ip = extract_client_ip(request, trusted_proxies)
    return f"ip:{client_ip}"


class RateLimiterService:
    """
    Coordinates distributed rate-limiting checks against Redis using atomic Lua scripting.
    """

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        prefix: Optional[str] = None,
        enabled: Optional[bool] = None,
        fallback_allow: Optional[bool] = None,
    ):
        settings = get_settings()
        self._explicit_client = redis_client
        self.prefix = prefix or f"{settings.cache_key_prefix}:rl"
        self.enabled = enabled if enabled is not None else settings.rate_limit_enabled
        self.fallback_allow = fallback_allow if fallback_allow is not None else settings.rate_limit_fallback_allow
        self.settings = settings
        self._script_sha: Optional[str] = None

    async def _get_client(self) -> Optional[Redis]:
        if not self.enabled:
            return None
        if self._explicit_client is not None:
            return self._explicit_client
        return await get_rate_limit_redis()

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        resource_name: str = "default",
    ) -> RateLimitResult:
        """
        Evaluate sliding-window rate limit for a given identifier and resource.
        """
        now_sec = time.time()
        now_ms = int(now_sec * 1000)
        window_ms = int(window_seconds * 1000)
        reset_epoch = int(now_sec + window_seconds)

        if not self.enabled:
            return RateLimitResult(
                allowed=True,
                current_count=0,
                limit=limit,
                remaining=limit,
                retry_after=0,
                reset_epoch=reset_epoch,
                identifier=identifier,
                resource=resource_name,
            )

        client = await self._get_client()
        if client is None:
            # Check if Redis was configured but failed to connect
            is_configured = self.settings.is_redis_enabled or self._explicit_client is not None
            if is_configured and not self.fallback_allow:
                logger.error(
                    f"Redis unavailable for rate limiting ({resource_name}:{identifier}). "
                    "Strict policy active (fail-closed)."
                )
                return RateLimitResult(
                    allowed=False,
                    current_count=limit,
                    limit=limit,
                    remaining=0,
                    retry_after=window_seconds,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )
            else:
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )

        redis_key = f"{self.prefix}:{resource_name}:{identifier}"
        nonce = uuid.uuid4().hex

        try:
            # Execute atomic Lua script
            eval_result = await client.eval(
                SLIDING_WINDOW_LUA,
                1,  # number of keys
                redis_key,
                str(now_ms),
                str(window_ms),
                str(limit),
                nonce,
            )

            # eval_result: [allowed (0 or 1), current_count, remaining, retry_after, now_ms]
            is_allowed = bool(eval_result[0] == 1)
            count = int(eval_result[1])
            remaining = int(eval_result[2])
            retry_after = int(eval_result[3])
            if len(eval_result) >= 5 and eval_result[4] is not None:
                server_now_ms = int(eval_result[4])
                reset_epoch = int((server_now_ms + window_ms) / 1000)

            return RateLimitResult(
                allowed=is_allowed,
                current_count=count,
                limit=limit,
                remaining=remaining,
                retry_after=retry_after,
                reset_epoch=reset_epoch,
                identifier=identifier,
                resource=resource_name,
            )

        except RedisError as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            logger.warning(f"Redis rate limit eval failed: {sanitized}")
            if self.fallback_allow:
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )
            else:
                return RateLimitResult(
                    allowed=False,
                    current_count=limit,
                    limit=limit,
                    remaining=0,
                    retry_after=window_seconds,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )
        except Exception as exc:
            sanitized = self.settings.sanitize_error(str(exc))
            logger.error(f"Unexpected error in rate limiting: {sanitized}")
            if self.fallback_allow:
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )
            else:
                return RateLimitResult(
                    allowed=False,
                    current_count=limit,
                    limit=limit,
                    remaining=0,
                    retry_after=window_seconds,
                    reset_epoch=reset_epoch,
                    identifier=identifier,
                    resource=resource_name,
                )


# Default singleton rate limiter service
default_rate_limiter = RateLimiterService()


class RateLimitDependency:
    """
    FastAPI dependency callable that enforces rate limits on route handlers.

    Usage:
        @router.post("/endpoint", dependencies=[Depends(RateLimit(limit=10, window_seconds=60))])
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        resource_name: str = "default",
        limiter: Optional[RateLimiterService] = None,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.resource_name = resource_name
        self.limiter = limiter or default_rate_limiter

    async def __call__(
        self,
        request: Request,
        response: Response,
        current_user: Optional[User] = Depends(get_optional_current_user),
    ) -> RateLimitResult:
        # Resolve user or IP
        user = current_user or getattr(request.state, "current_user", None)
        identifier = resolve_rate_limit_identifier(request, current_user=user)

        result = await self.limiter.check_rate_limit(
            identifier=identifier,
            limit=self.limit,
            window_seconds=self.window_seconds,
            resource_name=self.resource_name,
        )

        # Attach rate-limit headers to outgoing response
        for k, v in result.headers.items():
            response.headers[k] = v

        if not result.allowed:
            request_id = getattr(request.state, "request_id", None)
            detail_msg = (
                f"Rate limit exceeded for resource '{self.resource_name}'. "
                f"Maximum {self.limit} requests per {self.window_seconds}s allowed. "
                f"Please retry after {result.retry_after} second(s)."
            )
            # Raise consistent HTTP 429
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail_msg,
                headers=result.headers,
            )

        return result


def RateLimit(
    limit: int,
    window_seconds: int,
    resource_name: str = "default",
    limiter: Optional[RateLimiterService] = None,
) -> RateLimitDependency:
    """Factory helper creating RateLimitDependency."""
    return RateLimitDependency(
        limit=limit,
        window_seconds=window_seconds,
        resource_name=resource_name,
        limiter=limiter,
    )
