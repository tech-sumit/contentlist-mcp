"""Ranking & curation — turn a candidate pool into an ordered content list.

score = w_fresh·recency + w_auth·authority + w_rel·relevance, plus a small
diversity bonus for stories covered by multiple outlets (cluster_size).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .models import Candidate
from .verticals import Vertical

# A light, hand-curated authority prior. Unknown domains get a neutral 0.5.
_AUTHORITY: dict[str, float] = {
    "npr.org": 0.9, "theguardian.com": 0.9, "apnews.com": 0.95, "reuters.com": 0.95,
    "bbc.com": 0.9, "arstechnica.com": 0.85, "theverge.com": 0.8,
    "news.ycombinator.com": 0.7, "pitchfork.com": 0.85, "billboard.com": 0.85,
    "music.apple.com": 0.8, "musicbrainz.org": 0.75,
}

_TOKEN = re.compile(r"[a-z0-9]+")


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _recency(published_at: datetime | None, half_life_hours: float = 18.0) -> float:
    if published_at is None:
        return 0.4  # unknown date: neutral-ish, don't punish too hard
    now = datetime.now(timezone.utc)
    age_h = max((now - published_at).total_seconds() / 3600.0, 0.0)
    return math.exp(-age_h / half_life_hours)  # 1.0 fresh -> ~0 old


def _relevance(query: str, c: Candidate) -> float:
    q = set(_TOKEN.findall(query.lower()))
    if not q:
        return 0.5
    text = set(_TOKEN.findall(f"{c.title} {c.summary}".lower()))
    overlap = len(q & text) / len(q)
    backend_boost = min(c.score, 1.0) * 0.2 if c.backend in ("searxng", "tavily") else 0.0
    return min(overlap + backend_boost, 1.0)


def rank(query: str, candidates: list[Candidate], vertical: Vertical) -> list[Candidate]:
    seen_domains: dict[str, int] = {}
    for c in candidates:
        authority = _AUTHORITY.get(_domain(c.url), 0.5)
        recency = _recency(c.published_at)
        relevance = _relevance(query, c)
        diversity = min(math.log1p(c.cluster_size) * 0.15, 0.3)
        c.score = (
            vertical.w_fresh * recency
            + vertical.w_auth * authority
            + vertical.w_rel * relevance
            + diversity
        )

    ordered = sorted(candidates, key=lambda c: c.score, reverse=True)

    # Light source-diversity pass: demote the 3rd+ item from the same domain.
    final: list[Candidate] = []
    for c in ordered:
        d = _domain(c.url)
        n = seen_domains.get(d, 0)
        if n >= 2:
            c.score *= 0.6
        seen_domains[d] = n + 1
        final.append(c)
    final.sort(key=lambda c: c.score, reverse=True)
    return final
