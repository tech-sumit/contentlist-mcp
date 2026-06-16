from contentlist_mcp.dedupe import canonical_url, dedupe
from contentlist_mcp.models import Candidate


def test_canonical_url_strips_tracking_www_amp():
    assert canonical_url("https://www.Example.com/a/amp/?utm_source=x") == "https://example.com/a"
    assert canonical_url("http://example.com/path/") == "http://example.com/path"


def test_dedupe_same_url_counts_cluster():
    c1 = Candidate(title="Big news", url="https://x.com/a?utm=1", source="X")
    c2 = Candidate(title="Big news", url="https://www.x.com/a/", source="X")
    out = dedupe([c1, c2])
    assert len(out) == 1
    assert out[0].cluster_size == 2


def test_dedupe_similar_titles_across_sources():
    a = Candidate(title="Company launches new AI chip today", url="https://a.com/1", source="A")
    b = Candidate(title="New AI chip launched by company", url="https://b.com/2", source="B")
    out = dedupe([a, b])
    assert len(out) == 1
    assert out[0].cluster_size == 2
