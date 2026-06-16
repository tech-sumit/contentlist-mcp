"""Page fetch + main-content extraction (Trafilatura) for the `fetch_page` tool
and for enriching summaries when a feed/search result is thin.

Returns clean main text + metadata, never raw HTML. Includes basic SSRF guards.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

import trafilatura

from .config import CONFIG
from .retrieval.base import client


def _is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower()
    if any(host == d or host.endswith("." + d) for d in CONFIG.blocked_domains):
        return False
    try:  # block requests to private / loopback ranges (SSRF)
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


async def fetch_clean(url: str) -> dict:
    """Fetch a URL and return {title, text, author, date, sitename, url, error?}."""
    if not _is_safe_url(url):
        return {"url": url, "error": "blocked or unsafe URL", "text": ""}
    try:
        resp = await client().get(url)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:  # noqa: BLE001 - surface a clean error to the agent
        return {"url": url, "error": f"fetch failed: {type(e).__name__}", "text": ""}

    extracted = trafilatura.extract(
        html, include_comments=False, include_tables=False, favor_precision=True
    )
    meta = trafilatura.extract_metadata(html)
    return {
        "url": url,
        "title": getattr(meta, "title", None),
        "author": getattr(meta, "author", None),
        "date": getattr(meta, "date", None),
        "sitename": getattr(meta, "sitename", None),
        "text": extracted or "",
    }


def first_sentences(text: str, max_chars: int = 240) -> Optional[str]:
    """Cheap extractive summary: first sentence(s) up to a length cap."""
    text = " ".join((text or "").split())
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > 60 else cut).rstrip() + "…"
