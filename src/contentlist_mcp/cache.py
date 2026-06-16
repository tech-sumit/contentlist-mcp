"""A tiny async TTL cache. In-memory by default; swap for Redis at scale.

Cache key = (normalized query, vertical, freshness bucket, region, lang). Popular
queries ("top news today") become near-free + instant warm hits.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._store[key] = (time.time() + ttl, value)


CACHE = TTLCache()


def make_key(query: str, vertical: str, freshness: str, region: str, lang: str) -> str:
    norm = " ".join(query.lower().split())
    return f"{vertical}|{freshness}|{region}|{lang}|{norm}"
