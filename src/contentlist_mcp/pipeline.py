"""The end-to-end pipeline: query → retrieve → dedupe → rank → summarize → list.

This is the heart of the server. `search_content` (server.py) is a thin wrapper.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from .cache import CACHE, make_key
from .config import CONFIG
from .dedupe import dedupe
from .models import Candidate, ContentItem, ContentList
from .rank import rank
from .retrieval import rss, searxng, tavily
from .summarize import make_summary
from .verticals import Vertical, resolve_vertical

_FRESHNESS_DELTA = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=31),
}


def _cache_ttl(freshness: str) -> int:
    if freshness == "day":
        return CONFIG.cache_ttl_day
    if freshness == "week":
        return CONFIG.cache_ttl_week
    return CONFIG.cache_ttl_default


def _apply_freshness(candidates: list[Candidate], freshness: str) -> list[Candidate]:
    delta = _FRESHNESS_DELTA.get(freshness)
    if delta is None:  # "any"
        return candidates
    cutoff = datetime.now(timezone.utc) - delta
    # Keep undated items (feeds sometimes omit dates) rather than drop coverage.
    return [c for c in candidates if c.published_at is None or c.published_at >= cutoff]


async def _retrieve(query: str, v: Vertical, freshness: str, limit: int, lang: str) -> tuple[list[Candidate], list[str]]:
    tasks = []
    labels = []
    if v.feeds:
        tasks.append(rss.search(v.feeds))
        labels.append("rss")
    if v.use_web_search:
        tasks.append(searxng.search(query, freshness, limit, lang))
        labels.append("searxng")
    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    candidates: list[Candidate] = []
    used: list[str] = []
    for label, r in zip(labels, results):
        if isinstance(r, list) and r:
            candidates.extend(r)
            used.append(label)

    # Tavily fallback: only when web breadth is wanted but thin so far.
    if v.use_web_search and len([c for c in candidates if c.backend != "rss"]) < limit:
        tav = await tavily.search(query, v.name, freshness, limit)
        if tav:
            candidates.extend(tav)
            used.append("tavily")
    return candidates, used


async def search_content(
    query: str,
    vertical: str = "auto",
    freshness: str = "auto",
    limit: int = 10,
    summaries: bool = True,
    region: str = "US",
    lang: str = "en",
) -> ContentList:
    query = (query or "").strip()
    limit = max(1, min(limit, CONFIG.max_limit))
    v = resolve_vertical(vertical, query)
    if freshness in ("", "auto"):
        freshness = v.default_freshness

    key = make_key(query, v.name, freshness, region, lang)
    cached = await CACHE.get(key)
    if cached is not None:
        cached = cached.model_copy(deep=True)
        cached.cache = "hit"
        return cached

    candidates, used = await _retrieve(query, v, freshness, limit, lang)
    candidates = _apply_freshness(candidates, freshness)
    candidates = dedupe(candidates)
    candidates = rank(query, candidates, v)

    items: list[ContentItem] = []
    for i, c in enumerate(candidates[:limit], start=1):
        items.append(
            ContentItem(
                rank=i,
                title=c.title,
                url=c.url,
                source=c.source,
                published_at=c.published_at,
                summary=make_summary(c.summary) if summaries else "",
                thumbnail=c.thumbnail,
                cluster_size=c.cluster_size,
            )
        )

    result = ContentList(
        query=query,
        vertical=v.name,
        generated_at=datetime.now(timezone.utc),
        items=items,
        sources_used=used,
        cache="miss",
    )
    await CACHE.set(key, result, _cache_ttl(freshness))
    return result
