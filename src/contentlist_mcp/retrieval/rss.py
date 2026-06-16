"""RSS/Atom retrieval — the clean, free, time-stamped backbone for verticals.

Feeds are published *for* consumption, so this is the most reliable and most
legally-clean source. We parse them concurrently and normalize to Candidates.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import feedparser

from ..models import Candidate
from .base import client, to_utc


def _entry_published(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _entry_thumbnail(entry) -> Optional[str]:
    media = getattr(entry, "media_thumbnail", None) or getattr(entry, "media_content", None)
    if media and isinstance(media, list) and media and media[0].get("url"):
        return media[0]["url"]
    for link in getattr(entry, "links", []) or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    return None


def _source_name(feed, url: str) -> str:
    title = getattr(getattr(feed, "feed", None), "title", None)
    return title or urlparse(url).netloc


async def _fetch_feed(url: str) -> list[Candidate]:
    try:
        resp = await client().get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception:
        return []

    source = _source_name(parsed, url)
    out: list[Candidate] = []
    for e in parsed.entries:
        link = getattr(e, "link", None)
        title = getattr(e, "title", None)
        if not link or not title:
            continue
        summary = getattr(e, "summary", "") or ""
        out.append(
            Candidate(
                title=title.strip(),
                url=link,
                source=source,
                published_at=to_utc(_entry_published(e)),
                summary=summary,
                thumbnail=_entry_thumbnail(e),
                backend="rss",
            )
        )
    return out


async def search(feeds: list[str]) -> list[Candidate]:
    if not feeds:
        return []
    results = await asyncio.gather(*[_fetch_feed(u) for u in feeds], return_exceptions=True)
    candidates: list[Candidate] = []
    for r in results:
        if isinstance(r, list):
            candidates.extend(r)
    return candidates
