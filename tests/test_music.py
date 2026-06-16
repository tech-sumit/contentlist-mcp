import pytest

from contentlist_mcp.models import Candidate
from contentlist_mcp.retrieval import music


async def test_musicbrainz_skips_generic_queries():
    # No specific artist/album terms → no network call, empty result.
    assert await music._musicbrainz("what's new in songs this week", 10) == []
    assert await music._musicbrainz("top music", 10) == []


async def test_search_aggregates_sources(monkeypatch):
    async def fake_itunes(limit):
        return [Candidate(title="Song A", url="https://music.apple.com/a", source="Apple Music", backend="itunes")]

    async def fake_lb(freshness):
        return [Candidate(title="Album B", url="https://musicbrainz.org/release/b", source="ListenBrainz", backend="listenbrainz")]

    async def fake_mb(query, limit):
        return []

    monkeypatch.setattr(music, "_itunes", fake_itunes)
    monkeypatch.setattr(music, "_listenbrainz", fake_lb)
    monkeypatch.setattr(music, "_musicbrainz", fake_mb)

    out = await music.search("new songs", "week", 10)
    backends = {c.backend for c in out}
    assert backends == {"itunes", "listenbrainz"}
    assert len(out) == 2


async def test_search_raises_when_all_backends_fail(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(music, "_itunes", boom)
    monkeypatch.setattr(music, "_listenbrainz", boom)
    monkeypatch.setattr(music, "_musicbrainz", boom)

    # All sources down → raise so the pipeline's circuit breaker can trip.
    with pytest.raises(RuntimeError):
        await music.search("new songs", "week", 10)
