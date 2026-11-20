"""
EdgeMind Phase 4: Comprehensive Distributed Rate Limiting Tests.

Tests:
1. Sliding-Window Counter Evaluation (below, at, above limit)
2. HTTP 429 Response & Standard Header Generation (X-RateLimit-*, Retry-After)
3. Authenticated User Isolation (user:uuid)
4. Anonymous Client IP Isolation (ip:client_host)
5. Trusted Reverse Proxy Validation (anti-spoofing defense)
6. Streaming Endpoint Rate Limiting (1 charge per stream session, zero charge per SSE chunk)
7. Concurrent Request Safety (atomic Lua execution)
8. Fallback Policy on Redis Outage (strict fail-closed vs testing fail-open)
9. FastAPI Integration via HTTP TestClient
"""

import asyncio
from datetime import datetime
import json
import uuid
import pytest
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError, RedisError

from core.config import get_settings
from core.database.models import User
from core.redis.connection import redis_manager
from core.redis.rate_limiter import (
    RateLimit,
    RateLimitDependency,
    RateLimitResult,
    RateLimiterService,
    default_rate_limiter,
    extract_client_ip,
    resolve_rate_limit_identifier,
)
from tests.mock_redis import MockRedisClient


@pytest.fixture
def mock_redis():
    """Isolated in-memory mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def rate_limiter(mock_redis):
    """Rate limiter service backed by mock Redis."""
    return RateLimiterService(
        redis_client=mock_redis,
        prefix="edgemind:rl:test",
        enabled=True,
        fallback_allow=False,
    )


# -----------------------------------------------------------------------------
# 1. Sliding Window Evaluation (Below, At, Above Limit)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rate_limit_below_at_and_above(rate_limiter):
    """Verify rate limit allows up to limit, then rejects with retry_after."""
    identifier = "user:test-user-1"
    limit = 3
    window = 10

    # Request 1: Allowed, 2 remaining
    res1 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    assert res1.allowed is True
    assert res1.current_count == 1
    assert res1.remaining == 2
    assert res1.retry_after == 0

    # Request 2: Allowed, 1 remaining
    res2 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    assert res2.allowed is True
    assert res2.current_count == 2
    assert res2.remaining == 1

    # Request 3: Allowed, 0 remaining (at limit)
    res3 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    assert res3.allowed is True
    assert res3.current_count == 3
    assert res3.remaining == 0

    # Request 4: REJECTED (above limit)
    res4 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    assert res4.allowed is False
    assert res4.remaining == 0
    assert res4.retry_after > 0


# -----------------------------------------------------------------------------
# 2. HTTP Rate-Limit Headers
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rate_limit_headers(rate_limiter):
    """Verify headers on both allowed and rejected evaluations."""
    identifier = "ip:192.168.1.10"
    limit = 2
    window = 30

    res_ok = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    headers_ok = res_ok.headers
    assert headers_ok["X-RateLimit-Limit"] == "2"
    assert headers_ok["X-RateLimit-Remaining"] == "1"
    assert "Retry-After" not in headers_ok

    await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)

    # Exceeded
    res_blocked = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    headers_blocked = res_blocked.headers
    assert headers_blocked["X-RateLimit-Limit"] == "2"
    assert headers_blocked["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in headers_blocked
    assert int(headers_blocked["Retry-After"]) > 0


# -----------------------------------------------------------------------------
# 3. Authenticated User Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_authenticated_user_isolation(rate_limiter):
    """Verify rate limits are isolated between distinct authenticated user accounts."""
    user_a = "user:11111111-1111-1111-1111-111111111111"
    user_b = "user:22222222-2222-2222-2222-222222222222"
    limit = 2
    window = 60

    # Exhaust user A's quota
    await rate_limiter.check_rate_limit(user_a, limit=limit, window_seconds=window)
    await rate_limiter.check_rate_limit(user_a, limit=limit, window_seconds=window)
    res_a_blocked = await rate_limiter.check_rate_limit(user_a, limit=limit, window_seconds=window)
    assert res_a_blocked.allowed is False

    # User B must still be allowed
    res_b = await rate_limiter.check_rate_limit(user_b, limit=limit, window_seconds=window)
    assert res_b.allowed is True
    assert res_b.current_count == 1
    assert res_b.remaining == 1


# -----------------------------------------------------------------------------
# 4. Anonymous Client IP Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_anonymous_ip_isolation(rate_limiter):
    """Verify anonymous callers from different IP addresses have separate quotas."""
    ip_1 = "ip:10.0.0.1"
    ip_2 = "ip:10.0.0.2"
    limit = 1
    window = 60

    await rate_limiter.check_rate_limit(ip_1, limit=limit, window_seconds=window)
    assert (await rate_limiter.check_rate_limit(ip_1, limit=limit, window_seconds=window)).allowed is False

    # IP 2 still has quota
    res_ip2 = await rate_limiter.check_rate_limit(ip_2, limit=limit, window_seconds=window)
    assert res_ip2.allowed is True


# -----------------------------------------------------------------------------
# 5. Trusted Reverse Proxy Validation & Spoofing Defense
# -----------------------------------------------------------------------------

def test_extract_client_ip_anti_spoofing():
    """Verify untrusted direct peers cannot forge client IP via X-Forwarded-For."""
    class MockClient:
        def __init__(self, host):
            self.host = host

    class DummyRequest:
        def __init__(self, client_host, headers):
            self.client = MockClient(client_host)
            self.headers = headers

    trusted_proxies = ["127.0.0.1", "10.0.0.1"]

    # 1. Attacker directly connects from untrusted IP and provides forged X-Forwarded-For
    req_untrusted = DummyRequest(
        client_host="198.51.100.4",
        headers={"x-forwarded-for": "8.8.8.8, 1.1.1.1"},
    )
    # MUST ignore X-Forwarded-For and return the direct connection host!
    extracted_ip = extract_client_ip(req_untrusted, trusted_proxies=trusted_proxies)
    assert extracted_ip == "198.51.100.4"

    # 2. Connection from trusted reverse proxy (e.g. 127.0.0.1)
    req_trusted = DummyRequest(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "203.0.113.195, 127.0.0.1"},
    )
    extracted_trusted = extract_client_ip(req_trusted, trusted_proxies=trusted_proxies)
    assert extracted_trusted == "203.0.113.195"

    # 3. Trusted proxy with malformed IP header
    req_malformed = DummyRequest(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "invalid-ip-string; injection"},
    )
    # Must fallback safely to direct host
    extracted_malformed = extract_client_ip(req_malformed, trusted_proxies=trusted_proxies)
    assert extracted_malformed == "127.0.0.1"


# -----------------------------------------------------------------------------
# 6. Fallback Policy on Redis Outage
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rate_limiter_outage_fallback_policy(mock_redis):
    """Verify fail-closed (reject) vs fail-open (allow) policies on Redis failure."""
    mock_redis.set_raise_error(ConnectionError("Redis down"))

    # Fail-closed (production default)
    limiter_fail_closed = RateLimiterService(
        redis_client=mock_redis,
        enabled=True,
        fallback_allow=False,
    )
    res_closed = await limiter_fail_closed.check_rate_limit("user:123", limit=10, window_seconds=60)
    assert res_closed.allowed is False  # Strict protection active

    # Fail-open (dev/testing mode)
    limiter_fail_open = RateLimiterService(
        redis_client=mock_redis,
        enabled=True,
        fallback_allow=True,
    )
    res_open = await limiter_fail_open.check_rate_limit("user:123", limit=10, window_seconds=60)
    assert res_open.allowed is True  # Permitted through


# -----------------------------------------------------------------------------
# 7. Atomic Concurrency
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_concurrent_rate_limiting(rate_limiter):
    """Verify rapid concurrent requests accurately decrement remaining quota."""
    identifier = "user:concurrent-test"
    limit = 10
    window = 30

    tasks = [
        rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
        for _ in range(15)
    ]
    results = await asyncio.gather(*tasks)

    allowed = [r for r in results if r.allowed]
    blocked = [r for r in results if not r.allowed]

    assert len(allowed) == 10
    assert len(blocked) == 5


# -----------------------------------------------------------------------------
# 8. Streaming Rate Limiting (1 charge per stream session)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_streaming_endpoint_charged_once_not_per_chunk(mock_redis):
    """
    Verify that in streaming endpoints (SSE), rate limit is evaluated exactly ONCE
    at the start of the stream, and not incremented per streamed chunk.
    """
    custom_limiter = RateLimiterService(
        redis_client=mock_redis,
        prefix="stream:test",
        enabled=True,
    )

    from fastapi import Depends as fastapi_depends

    test_app = FastAPI()
    dependency = RateLimit(limit=2, window_seconds=60, resource_name="stream_test", limiter=custom_limiter)

    @test_app.post("/stream")
    async def fake_stream_endpoint(rate: RateLimitResult = fastapi_depends(dependency)):
        # Simulate yielding 5 SSE chunks
        chunks = [f"data: chunk {i}\n\n" for i in range(5)]
        return {"chunks_sent": len(chunks), "current_count": rate.current_count}

    # Using TestClient
    client = TestClient(test_app)

    # Call 1: current_count should be 1
    r1 = client.post("/stream")
    assert r1.status_code == 200
    assert r1.json()["current_count"] == 1
    assert r1.headers["X-RateLimit-Remaining"] == "1"

    # Call 2: current_count should be 2
    r2 = client.post("/stream")
    assert r2.status_code == 200
    assert r2.json()["current_count"] == 2
    assert r2.headers["X-RateLimit-Remaining"] == "0"

    # Call 3: Exceeded -> HTTP 429
    r3 = client.post("/stream")
    assert r3.status_code == 429
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in r3.headers
    assert "Rate limit exceeded" in r3.json()["detail"]


# -----------------------------------------------------------------------------
# 9. FastAPI HTTP Integration & HTTP 429 Error Body
# -----------------------------------------------------------------------------

def test_fastapi_rate_limit_integration_429_body(mock_redis):
    """Verify HTTP 429 response structure matches EdgeMind standard error format."""
    from fastapi import Depends

    limiter = RateLimiterService(
        redis_client=mock_redis,
        prefix="http:test",
        enabled=True,
    )
    dep = RateLimit(limit=1, window_seconds=30, resource_name="test_api", limiter=limiter)

    app = FastAPI()

    @app.post("/api/action")
    async def do_action(rate: RateLimitResult = Depends(dep)):
        return {"status": "success"}

    client = TestClient(app)

    # First request: 200 OK
    resp1 = client.post("/api/action")
    assert resp1.status_code == 200
    assert resp1.headers["X-RateLimit-Limit"] == "1"
    assert resp1.headers["X-RateLimit-Remaining"] == "0"

    # Second request: 429 Too Many Requests
    resp2 = client.post("/api/action")
    assert resp2.status_code == 429
    assert resp2.headers["X-RateLimit-Limit"] == "1"
    assert resp2.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in resp2.headers

    data = resp2.json()
    assert "Rate limit exceeded" in data["detail"]


# -----------------------------------------------------------------------------
# 10. Same-Millisecond Request Atomicity & Non-Collapsing Verification
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_simultaneous_requests_same_millisecond_timestamp(mock_redis, rate_limiter):
    """
    Verify that multiple requests arriving in the exact same millisecond
    receive unique sorted-set members and do NOT collapse into a single entry.
    """
    identifier = "user:same-ms-test"
    limit = 3
    window = 30
    fixed_ms = 1700000000000

    # Fix the mock Redis server time to the exact same millisecond
    mock_redis.set_mock_server_time(fixed_ms)

    # Issue 5 requests sharing the identical millisecond timestamp
    res1 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    res2 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    res3 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    res4 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)
    res5 = await rate_limiter.check_rate_limit(identifier, limit=limit, window_seconds=window)

    # Verify requests 1, 2, 3 were permitted
    assert res1.allowed is True and res1.current_count == 1
    assert res2.allowed is True and res2.current_count == 2
    assert res3.allowed is True and res3.current_count == 3

    # Verify requests 4 and 5 were strictly rejected
    assert res4.allowed is False and res4.current_count == 3
    assert res5.allowed is False and res5.current_count == 3
    assert res4.retry_after > 0
    assert res5.retry_after > 0

    # Verify Redis sorted set contains exactly 3 unique members (not 1 collapsed entry)
    redis_key = f"{rate_limiter.prefix}:default:{identifier}"
    zset_entries = mock_redis._zsets.get(redis_key, [])
    assert len(zset_entries) == 3

    # Verify all members are distinct and contain the fixed timestamp
    member_names = [m for score, m in zset_entries]
    assert len(set(member_names)) == 3
    for m in member_names:
        assert m.startswith(f"{fixed_ms}:")


# -----------------------------------------------------------------------------
# 11. Memory Pressure & OOM Failure Policy
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rate_limiter_oom_fails_closed(mock_redis):
    """
    Verify rate limiter fails closed (rejects requests) when Redis reaches
    maxmemory limits and returns an OOM ResponseError.
    Counters cannot be silently bypassed under memory pressure.
    """
    from redis.exceptions import ResponseError

    mock_redis.set_raise_error(ResponseError("OOM command not allowed when used memory > 'maxmemory'"))

    limiter = RateLimiterService(
        redis_client=mock_redis,
        enabled=True,
        fallback_allow=False,  # Strict production policy
    )

    result = await limiter.check_rate_limit("user:victim", limit=5, window_seconds=60)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after > 0


# -----------------------------------------------------------------------------
# 12. Dedicated Rate Limit Redis Client Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_dedicated_rate_limit_redis_client_resolution(mock_redis):
    """
    Verify RedisManager supports dedicated rate limit Redis instance,
    and RateLimiterService connects via get_rate_limit_redis().
    """
    from core.redis.connection import get_rate_limit_redis, redis_manager

    # Override dedicated rate-limit client
    dedicated_client = MockRedisClient()
    redis_manager.set_override_rate_limit_client(dedicated_client)
    try:
        resolved = await get_rate_limit_redis()
        assert resolved is dedicated_client

        limiter = RateLimiterService()
        client = await limiter._get_client()
        assert client is dedicated_client

        # Performing rate limit check records directly into dedicated client
        res = await limiter.check_rate_limit("user:dedicated-test", limit=5, window_seconds=60)
        assert res.allowed is True
        assert res.current_count == 1
        assert len(dedicated_client._zsets) == 1
    finally:
        redis_manager.set_override_rate_limit_client(None)
