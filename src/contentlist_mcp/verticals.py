"""Vertical definitions: which sources to prefer and how to rank, per query type.

Adding a vertical is just adding an entry here — feeds + ranking weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Vertical:
    name: str
    # Curated RSS/Atom feeds consulted first (free, clean, time-stamped).
    feeds: list[str] = field(default_factory=list)
    # Default freshness window when the caller asks for "auto".
    default_freshness: str = "day"
    # Whether to also hit web search (SearXNG/Tavily) for breadth.
    use_web_search: bool = False
    # Ranking weights: freshness, source authority/diversity, relevance.
    w_fresh: float = 0.5
    w_auth: float = 0.3
    w_rel: float = 0.2
    # Keywords that route an "auto" query to this vertical.
    keywords: tuple[str, ...] = ()


VERTICALS: dict[str, Vertical] = {
    "news": Vertical(
        name="news",
        feeds=[
            "https://feeds.npr.org/1001/rss.xml",            # NPR top stories
            "https://www.theguardian.com/world/rss",         # Guardian world
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.theverge.com/rss/index.xml",
            "https://hnrss.org/frontpage",                   # Hacker News front page
            "https://apnews.com/hub/ap-top-news/rss",        # AP top news
        ],
        default_freshness="day",
        use_web_search=True,
        w_fresh=0.55, w_auth=0.30, w_rel=0.15,
        keywords=("news", "headlines", "today", "breaking", "happening", "latest"),
    ),
    "music": Vertical(
        name="music",
        feeds=[
            "https://pitchfork.com/rss/news/",
            "https://pitchfork.com/rss/reviews/albums/",
            "https://www.billboard.com/feed/",
        ],
        default_freshness="week",
        use_web_search=True,
        w_fresh=0.50, w_auth=0.25, w_rel=0.25,
        keywords=("song", "songs", "music", "album", "albums", "track", "tracks", "artist", "release"),
    ),
    "web": Vertical(
        name="web",
        feeds=[],
        default_freshness="any",
        use_web_search=True,
        w_fresh=0.20, w_auth=0.30, w_rel=0.50,
        keywords=(),
    ),
}


def resolve_vertical(requested: str, query: str) -> Vertical:
    """Pick a vertical. Explicit request wins; 'auto' is keyword-routed; fallback is web."""
    requested = (requested or "auto").lower()
    if requested in VERTICALS:
        return VERTICALS[requested]

    q = query.lower()
    best: tuple[int, str] = (0, "web")
    for name, v in VERTICALS.items():
        hits = sum(1 for kw in v.keywords if kw in q)
        if hits > best[0]:
            best = (hits, name)
    return VERTICALS[best[1]]
