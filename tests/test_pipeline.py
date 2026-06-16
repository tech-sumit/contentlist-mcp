from datetime import datetime, timezone

from contentlist_mcp import pipeline
from contentlist_mcp.config import CONFIG
from contentlist_mcp.models import Candidate


def _now():
    return datetime.now(timezone.utc)


async def test_pipeline_builds_news_list(monkeypatch):
    monkeypatch.setattr(CONFIG, "enable_enrichment", False)

    async def fake_retrieve(query, v, freshness, limit, lang):
        return [
            Candidate(title="Big story", url="https://npr.org/1", source="NPR",
                      backend="rss", published_at=_now(), summary="Lead paragraph."),
            Candidate(title="Other story", url="https://apnews.com/2", source="AP",
                      backend="rss", published_at=_now(), summary="More text."),
        ], ["rss"]

    monkeypatch.setattr(pipeline, "_retrieve", fake_retrieve)
    res = await pipeline.search_content("top news today now", limit=5)

    assert res.vertical == "news"
    assert res.sources_used == ["rss"]
    assert res.cache == "miss"
    assert [i.rank for i in res.items] == [1, 2]
    # Extractive by default → a summary, no why_it_matters.
    assert res.items[0].summary
    assert res.items[0].why_it_matters == ""


async def test_music_query_routes_to_music_vertical(monkeypatch):
    monkeypatch.setattr(CONFIG, "enable_enrichment", False)

    async def fake_retrieve(query, v, freshness, limit, lang):
        assert v.name == "music"  # routed by keywords
        return [Candidate(title="New album", url="https://music.apple.com/x",
                          source="Apple Music", backend="itunes", published_at=_now())], ["music"]

    monkeypatch.setattr(pipeline, "_retrieve", fake_retrieve)
    res = await pipeline.search_content("what's new in songs this week", limit=5)
    assert res.vertical == "music"
    assert res.sources_used == ["music"]


async def test_summaries_off_yields_empty_summary(monkeypatch):
    monkeypatch.setattr(CONFIG, "enable_enrichment", False)

    async def fake_retrieve(query, v, freshness, limit, lang):
        return [Candidate(title="X", url="https://npr.org/1", source="NPR",
                          backend="rss", published_at=_now(), summary="text")], ["rss"]

    monkeypatch.setattr(pipeline, "_retrieve", fake_retrieve)
    res = await pipeline.search_content("breaking news right now today", summaries=False, limit=3)
    assert res.items[0].summary == ""
