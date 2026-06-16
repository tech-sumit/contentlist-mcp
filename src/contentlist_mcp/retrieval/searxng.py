"""Self-hosted SearXNG retrieval — the 'free like Google' generic web backend.

SearXNG is a metasearch engine aggregating 70+ engines. Point SEARXNG_URL at your
instance (see docker-compose.yml). Returns empty if not configured so the pipeline
degrades gracefully to feeds/Tavily.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from dateutil import parser as dateparser

from ..config import CONFIG
from ..models import Candidate
from .base import client, to_utc

# SearXNG time_range maps to our freshness buckets.
_TIME_RANGE = {"day": "day", "week": "week", "month": "month", "any": ""}


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return to_utc(dateparser.parse(value))
    except (ValueError, OverflowError, TypeError):
        return None


async def search(query: str, freshness: str, limit: int, lang: str = "en") -> list[Candidate]:
    if not CONFIG.searxng_url:
        return []

    params = {
        "q": query,
        "format": "json",
        "language": lang,
        "safesearch": "1",
    }
    tr = _TIME_RANGE.get(freshness, "")
    if tr:
        params["time_range"] = tr

    # Transport/HTTP errors propagate so the pipeline's circuit breaker can trip.
    resp = await client().get(f"{CONFIG.searxng_url}/search", params=params)
    resp.raise_for_status()
    data = resp.json()

    out: list[Candidate] = []
    for r in data.get("results", [])[: limit * 3]:
        url = r.get("url")
        title = r.get("title")
        if not url or not title:
            continue
        out.append(
            Candidate(
                title=title.strip(),
                url=url,
                source=r.get("engine") or urlparse(url).netloc,
                published_at=_parse_date(r.get("publishedDate")),
                summary=r.get("content", "") or "",
                thumbnail=r.get("img_src"),
                backend="searxng",
                score=float(r.get("score", 0.0) or 0.0),
            )
        )
    return out
