"""Music vertical retrieval — iTunes RSS + ListenBrainz + MusicBrainz (all keyless, free).

These give the music vertical the freshness RSS news feeds can't:
  • iTunes RSS (Apple Marketing Tools JSON feeds) — most-played songs/albums charts.
  • ListenBrainz fresh-releases — new releases in the requested window.
  • MusicBrainz release search — for artist/album-specific queries.

Each source is best-effort; if the network is fully down the aggregate raises so the
pipeline's circuit breaker can trip and fall back. Returns normalized Candidates.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Optional

from dateutil import parser as dateparser

from ..config import CONFIG
from ..models import Candidate
from .base import client, to_utc

# Tokens that route a query *to* the music vertical — not useful for MusicBrainz search.
_GENERIC = {
    "song", "songs", "music", "album", "albums", "track", "tracks", "new", "latest",
    "this", "week", "today", "top", "best", "trending", "release", "releases", "what",
    "whats", "in", "the", "a", "an", "of", "to", "on", "for", "and",
}
_TOKEN = re.compile(r"[a-z0-9]+")
_DAYS = {"day": 2, "week": 7, "month": 30, "any": 30}


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return to_utc(dateparser.parse(value))
    except (ValueError, OverflowError, TypeError):
        return None


async def _itunes(limit: int) -> list[Candidate]:
    """Apple Marketing Tools 'most-played' charts (songs + albums). Keyless JSON feeds."""
    sf = CONFIG.music_storefront
    n = max(min(limit, 50), 10)
    urls = [
        ("song", f"https://rss.applemarketingtools.com/api/v2/{sf}/music/most-played/{n}/songs.json"),
        ("album", f"https://rss.applemarketingtools.com/api/v2/{sf}/music/most-played/{n}/albums.json"),
    ]
    out: list[Candidate] = []
    for kind, url in urls:
        resp = await client().get(url)
        resp.raise_for_status()
        for r in resp.json().get("feed", {}).get("results", []):
            link = r.get("url")
            name = r.get("name")
            if not link or not name:
                continue
            artist = r.get("artistName", "")
            out.append(
                Candidate(
                    title=f"{name} — {artist}" if artist else name,
                    url=link,
                    source="Apple Music",
                    published_at=_parse_date(r.get("releaseDate")),
                    summary=f"{kind.title()} by {artist}." if artist else "",
                    thumbnail=r.get("artworkUrl100"),
                    backend="itunes",
                )
            )
    return out


async def _listenbrainz(freshness: str) -> list[Candidate]:
    """ListenBrainz fresh-releases — recent/new releases within the freshness window."""
    days = _DAYS.get(freshness, 7)
    url = "https://api.listenbrainz.org/1/explore/fresh-releases/"
    params = {"days": days, "sort": "release_date", "past": "true", "future": "false"}
    resp = await client().get(url, params=params)
    resp.raise_for_status()
    releases = resp.json().get("payload", {}).get("releases", [])

    out: list[Candidate] = []
    for r in releases:
        name = r.get("release_name")
        mbid = r.get("release_mbid")
        if not name or not mbid:
            continue
        artist = r.get("artist_credit_name", "")
        thumb = f"https://coverartarchive.org/release/{mbid}/front-250" if r.get("caa_id") else None
        out.append(
            Candidate(
                title=f"{name} — {artist}" if artist else name,
                url=f"https://musicbrainz.org/release/{mbid}",
                source="ListenBrainz",
                published_at=_parse_date(r.get("release_date")),
                summary=f"New release by {artist}." if artist else "New release.",
                thumbnail=thumb,
                backend="listenbrainz",
            )
        )
    return out


async def _musicbrainz(query: str, limit: int) -> list[Candidate]:
    """MusicBrainz release search — only for queries with specific artist/album terms."""
    terms = [t for t in _TOKEN.findall(query.lower()) if t not in _GENERIC and len(t) > 1]
    if not terms:
        return []
    url = "https://musicbrainz.org/ws/2/release/"
    params = {"query": " ".join(terms), "fmt": "json", "limit": min(limit, 25)}
    resp = await client().get(url, params=params)
    resp.raise_for_status()
    out: list[Candidate] = []
    for r in resp.json().get("releases", []):
        name = r.get("title")
        mbid = r.get("id")
        if not name or not mbid:
            continue
        artist = ", ".join(a.get("name", "") for a in r.get("artist-credit", []) if isinstance(a, dict))
        out.append(
            Candidate(
                title=f"{name} — {artist}" if artist else name,
                url=f"https://musicbrainz.org/release/{mbid}",
                source="MusicBrainz",
                published_at=_parse_date(r.get("date")),
                summary=f"Release by {artist}." if artist else "",
                backend="musicbrainz",
            )
        )
    return out


async def search(query: str, freshness: str, limit: int) -> list[Candidate]:
    results = await asyncio.gather(
        _itunes(limit),
        _listenbrainz(freshness),
        _musicbrainz(query, limit),
        return_exceptions=True,
    )
    candidates: list[Candidate] = []
    errors = 0
    for r in results:
        if isinstance(r, list):
            candidates.extend(r)
        else:
            errors += 1
    # If every source errored (e.g. network down), raise so the breaker can trip.
    if errors == len(results):
        raise RuntimeError("all music backends failed")
    return candidates
