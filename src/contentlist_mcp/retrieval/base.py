"""Shared HTTP client + helpers for retrieval backends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from ..config import CONFIG

_client: Optional[httpx.AsyncClient] = None


def client() -> httpx.AsyncClient:
    """A lazily-created, shared async HTTP client (connection pooling)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=CONFIG.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": CONFIG.user_agent},
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
