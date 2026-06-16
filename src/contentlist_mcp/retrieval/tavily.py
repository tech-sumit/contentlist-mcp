"""Tavily retrieval — managed fallback/enrichment (free tier: 1,000 credits/mo, no card).

Used when SearXNG is unconfigured/rate-limited or returns too few results. Disabled
unless TAVILY_API_KEY is set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from dateutil import parser as dateparser

from ..config import CONFIG
from ..models import Candidate
from .base import client, to_utc

_TOPIC = {"news": "news", "music": "general", "web": "general"}
_DAYS = {"day": 1, "week": 7, "month": 30, "any": 365}


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return to_utc(dateparser.parse(value))
    except (ValueError, OverflowError, TypeError):
        return None


async def search(query: str, vertical: str, freshness: str, limit: int) -> list[Candidate]:
    if not CONFIG.tavily_api_key:
        return []

    payload = {
        "api_key": CONFIG.tavily_api_key,
        "query": query,
        "topic": _TOPIC.get(vertical, "general"),
        "search_depth": "basic",
        "max_results": min(limit * 2, 20),
        "days": _DAYS.get(freshness, 7),
        "include_answer": False,
    }
    # Transport/HTTP errors propagate so the pipeline's circuit breaker can trip.
    resp = await client().post("https://api.tavily.com/search", json=payload)
    resp.raise_for_status()
    data = resp.json()

    out: list[Candidate] = []
    for r in data.get("results", []):
        url = r.get("url")
        title = r.get("title")
        if not url or not title:
            continue
        out.append(
            Candidate(
                title=title.strip(),
                url=url,
                source=urlparse(url).netloc,
                published_at=_parse_date(r.get("published_date")),
                summary=r.get("content", "") or "",
                backend="tavily",
                score=float(r.get("score", 0.0) or 0.0),
            )
        )
    return out
