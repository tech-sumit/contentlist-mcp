"""The end-to-end pipeline: query → retrieve → dedupe → rank → enrich → summarize → list.

This is the heart of the server. `search_content` (server.py) is a thin wrapper.

Retrieval fans out across the vertical's backends, each web/API backend guarded by a
circuit breaker so a throttled source trips open and we fall through to the next layer
(SearXNG → Tavily) rather than hard-failing. Thin items are optionally enriched with
fetched page text, and summaries are extractive by default or Claude Haiku when enabled.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from . import summarize
from .cache import CACHE, make_key
from .config import CONFIG
from .dedupe import dedupe
from .extract import fetch_clean
from .models import Candidate, ContentItem, ContentList
from .rank import rank
from .reliability import CircuitBreaker, guarded_call
from .retrieval import music, rss, searxng, tavily
from .verticals import Vertical, resolve_vertical

_FRESHNESS_DELTA = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=31),
}

# One breaker per flaky backend (RSS is per-feed best-effort, so it needs none).
_BREAKERS: dict[str, CircuitBreaker] = {
    name: CircuitBreaker(name, CONFIG.breaker_fail_threshold, CONFIG.breaker_reset_seconds)
    for name in ("searxng", "tavily", "music")
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
    jobs: list[tuple[str, "asyncio.Future | object"]] = []
    if v.feeds:
        jobs.append(("rss", rss.search(v.feeds)))
    if v.use_music_apis:
        jobs.append(("music", guarded_call(_BREAKERS["music"], lambda: music.search(query, freshness, limit))))
    if v.use_web_search:
        jobs.append(("searxng", guarded_call(_BREAKERS["searxng"], lambda: searxng.search(query, freshness, limit, lang))))

    results = await asyncio.gather(*(j for _, j in jobs), return_exceptions=True) if jobs else []

    candidates: list[Candidate] = []
    used: list[str] = []
    for (label, _), r in zip(jobs, results):
        if isinstance(r, list) and r:
            candidates.extend(r)
            used.append(label)

    # Tavily fallback: only when web breadth is wanted but thin so far.
    web_count = sum(1 for c in candidates if c.backend in ("searxng", "tavily"))
    if v.use_web_search and web_count < limit:
        tav = await guarded_call(_BREAKERS["tavily"], lambda: tavily.search(query, v.name, freshness, limit))
        if tav:
            candidates.extend(tav)
            used.append("tavily")
    return candidates, used


async def _enrich(candidates: list[Candidate]) -> None:
    """Fetch + extract full page text for the top items whose summary is too thin."""
    if not CONFIG.enable_enrichment:
        return
    targets = [
        c for c in candidates[: CONFIG.enrichment_max_items]
        if c.url.startswith("http") and len(summarize.clean_text(c.summary)) < CONFIG.enrichment_min_chars
    ]
    if not targets:
        return
    sem = asyncio.Semaphore(CONFIG.fetch_concurrency)

    async def one(c: Candidate) -> None:
        async with sem:
            data = await fetch_clean(c.url)
        text = data.get("text") or ""
        if len(text) > len(summarize.clean_text(c.summary)):
            c.summary = text

    await asyncio.gather(*(one(c) for c in targets), return_exceptions=True)


async def _build_items(candidates: list[Candidate], summaries: bool) -> list[ContentItem]:
    llm: list[tuple[str, str]] | None = None
    if summaries and summarize.llm_enabled():
        payload = [{"title": c.title, "source": c.source, "text": c.summary} for c in candidates]
        llm = await summarize.llm_summaries(payload)

    items: list[ContentItem] = []
    for i, c in enumerate(candidates, start=1):
        if llm is not None:
            summary, why = llm[i - 1]
        elif summaries:
            summary, why = summarize.make_summary(c.summary), ""
        else:
            summary, why = "", ""
        items.append(
            ContentItem(
                rank=i,
                title=c.title,
                url=c.url,
                source=c.source,
                published_at=c.published_at,
                summary=summary,
                why_it_matters=why,
                thumbnail=c.thumbnail,
                cluster_size=c.cluster_size,
            )
        )
    return items


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
    candidates = candidates[:limit]

    await _enrich(candidates)
    items = await _build_items(candidates, summaries)

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
