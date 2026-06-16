from datetime import datetime, timedelta, timezone

from contentlist_mcp.models import Candidate
from contentlist_mcp.rank import rank
from contentlist_mcp.verticals import VERTICALS


def _c(title, url, source, hours_old, summary=""):
    return Candidate(
        title=title, url=url, source=source, summary=summary,
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
    )


def test_fresher_relevant_item_ranks_higher():
    fresh = _c("AI chip breakthrough", "https://npr.org/1", "NPR", 1, "ai chip news")
    stale = _c("Old unrelated story", "https://blog.example.com/2", "Blog", 200, "cooking")
    out = rank("ai chip news", [stale, fresh], VERTICALS["news"])
    assert out[0].url == "https://npr.org/1"


def test_returns_all_candidates():
    items = [_c(f"t{i}", f"https://s{i}.com/{i}", f"S{i}", i) for i in range(5)]
    out = rank("t", items, VERTICALS["news"])
    assert len(out) == 5
