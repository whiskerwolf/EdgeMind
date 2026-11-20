"""
In-Memory Mock Redis Client for Isolated Asynchronous Testing.

Simulates redis.asyncio.Redis commands:
- get, set, delete, scan_iter, ping, aclose
- atomic sliding-window Lua script evaluation via eval()
- failure / exception injection for chaos testing
"""

import fnmatch
import math
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from redis.exceptions import ConnectionError, RedisError, TimeoutError


class MockRedisClient:
    """
    High-fidelity in-memory Redis client mock for deterministic unit testing.
    """

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._expirations: Dict[str, float] = {}  # key -> expiry_time (epoch seconds)
        self._zsets: Dict[str, List[Tuple[int, str]]] = {}  # key -> list of (score_ms, member)
        self._raise_error: Optional[Exception] = None
        self.mock_server_time_ms: Optional[int] = None

    def set_mock_server_time(self, time_ms: Optional[int]) -> None:
        """Override the simulated server time in milliseconds."""
        self.mock_server_time_ms = time_ms

    def set_raise_error(self, exc: Optional[Exception] = None) -> None:
        """Inject exception to simulate Redis outage or network timeouts."""
        self._raise_error = exc

    def _check_expiry(self, key: str) -> None:
        if key in self._expirations:
            if time.time() > self._expirations[key]:
                self._data.pop(key, None)
                self._zsets.pop(key, None)
                self._expirations.pop(key, None)

    async def ping(self) -> bool:
        if self._raise_error:
            raise self._raise_error
        return True

    async def get(self, key: str) -> Optional[str]:
        if self._raise_error:
            raise self._raise_error
        self._check_expiry(key)
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if self._raise_error:
            raise self._raise_error
        self._data[key] = str(value)
        if ex and ex > 0:
            self._expirations[key] = time.time() + ex
        else:
            self._expirations.pop(key, None)
        return True

    async def delete(self, *keys: str) -> int:
        if self._raise_error:
            raise self._raise_error
        deleted = 0
        for k in keys:
            if k in self._data or k in self._zsets:
                deleted += 1
            self._data.pop(k, None)
            self._zsets.pop(k, None)
            self._expirations.pop(k, None)
        return deleted

    async def scan_iter(self, match: str = "*", count: int = 100) -> AsyncIterator[str]:
        if self._raise_error:
            raise self._raise_error
        all_keys = list(set(list(self._data.keys()) + list(self._zsets.keys())))
        for k in all_keys:
            self._check_expiry(k)
            if fnmatch.fnmatch(k, match):
                yield k

    async def eval(self, script: str, numkeys: int, *args) -> Any:
        if self._raise_error:
            raise self._raise_error
        # Sliding-window rate limiter Lua script simulation
        # args: [key, now_ms, window_ms, limit, nonce]
        key = args[0]
        now_ms = self.mock_server_time_ms if self.mock_server_time_ms is not None else int(args[1])
        window_ms = int(args[2])
        limit = int(args[3])
        nonce = str(args[4])
        member = f"{now_ms}:{nonce}"

        self._check_expiry(key)
        zset = self._zsets.setdefault(key, [])

        clear_before = now_ms - window_ms
        # Remove items with score <= clear_before
        zset = [item for item in zset if item[0] > clear_before]
        self._zsets[key] = zset

        # Enforce unique member semantics of Redis Sorted Sets
        existing_idx = None
        for idx, (score, m) in enumerate(zset):
            if m == member:
                existing_idx = idx
                break

        current_count = len(zset)
        if existing_idx is not None:
            # Member already exists: score update, no count increase
            zset[existing_idx] = (now_ms, member)
            remaining = max(0, limit - current_count)
            return [1, current_count, remaining, 0, now_ms]

        if current_count < limit:
            zset.append((now_ms, member))
            zset.sort(key=lambda x: x[0])
            self._expirations[key] = time.time() + math.ceil(window_ms / 1000) + 2
            remaining = limit - (current_count + 1)
            return [1, current_count + 1, remaining, 0, now_ms]
        else:
            oldest_score = zset[0][0]
            expires_at = oldest_score + window_ms
            diff_ms = expires_at - now_ms
            retry_after = max(1, math.ceil(diff_ms / 1000)) if diff_ms > 0 else 1
            return [0, current_count, 0, retry_after, now_ms]

    async def aclose(self) -> None:
        pass
