"""URL canonicalization + near-duplicate clustering.

Collapses "same story, many outlets" into one item carrying a `cluster_size`.
Keeps the candidate with the richest metadata as the cluster representative.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse

from .models import Candidate

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "ref_src", "spm")
_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "with", "as", "at", "by", "from", "this", "that", "it", "its", "new",
}


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/amp/?$", "", p.path).rstrip("/") or "/"
    # Drop tracking query params entirely (kept simple: strip the whole query).
    return urlunparse((p.scheme or "https", netloc, path, "", "", ""))


def _stem(word: str) -> str:
    """Strip common inflectional suffixes so 'launches'/'launched' cluster together."""
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _title_key(title: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return frozenset(_stem(w) for w in words if w not in _STOPWORDS and len(w) > 2)


def _similar(a: str, b: str) -> bool:
    ka, kb = _title_key(a), _title_key(b)
    if not ka or not kb:
        return False
    jaccard = len(ka & kb) / len(ka | kb)
    if jaccard >= 0.6:
        return True
    # Fall back to sequence ratio for short / reworded headlines.
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.85


def _richness(c: Candidate) -> tuple:
    return (c.published_at is not None, len(c.summary), c.thumbnail is not None)


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    # 1) Exact canonical-URL dedupe.
    by_url: dict[str, Candidate] = {}
    for c in candidates:
        key = canonical_url(c.url)
        existing = by_url.get(key)
        if existing is None:
            by_url[key] = c
        else:
            existing.cluster_size += 1
            if _richness(c) > _richness(existing):
                c.cluster_size = existing.cluster_size
                by_url[key] = c

    # 2) Title-similarity clustering across different URLs.
    clusters: list[Candidate] = []
    for c in by_url.values():
        match = next((rep for rep in clusters if rep.source != c.source and _similar(rep.title, c.title)), None)
        if match is None:
            clusters.append(c)
        else:
            match.cluster_size += c.cluster_size
            if _richness(c) > _richness(match):
                c.cluster_size = match.cluster_size
                clusters[clusters.index(match)] = c
    return clusters
