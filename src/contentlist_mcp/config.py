"""Runtime configuration, read from environment variables.

Everything has a sensible free default so the server runs with zero setup:
no SearXNG and no Tavily key still gives you working news/music verticals via RSS.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass
class Config:
    # --- Retrieval backends -------------------------------------------------
    # Self-hosted SearXNG base URL, e.g. "http://localhost:8080". Empty => disabled.
    searxng_url: str = field(default_factory=lambda: os.environ.get("SEARXNG_URL", "").rstrip("/"))
    # Tavily free-tier API key (1,000 credits/mo, no card). Empty => disabled.
    tavily_api_key: str = field(default_factory=lambda: os.environ.get("TAVILY_API_KEY", ""))

    # --- Networking ---------------------------------------------------------
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "CONTENTLIST_USER_AGENT",
            "contentlist-mcp/0.1 (+https://github.com/tech-sumit/contentlist-mcp)",
        )
    )
    http_timeout: float = field(default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT", "8")))
    fetch_concurrency: int = field(default_factory=lambda: int(os.environ.get("FETCH_CONCURRENCY", "8")))

    # --- Cache --------------------------------------------------------------
    cache_ttl_day: int = field(default_factory=lambda: int(os.environ.get("CACHE_TTL_DAY", "300")))      # 5 min
    cache_ttl_week: int = field(default_factory=lambda: int(os.environ.get("CACHE_TTL_WEEK", "3600")))   # 1 h
    cache_ttl_default: int = field(default_factory=lambda: int(os.environ.get("CACHE_TTL_DEFAULT", "86400")))

    # --- Behaviour ----------------------------------------------------------
    max_limit: int = field(default_factory=lambda: int(os.environ.get("MAX_LIMIT", "25")))
    blocked_domains: list[str] = field(default_factory=lambda: _csv("BLOCKED_DOMAINS"))

    # --- MCP transport ------------------------------------------------------
    # "streamable-http" (default, hosted) or "stdio" (local dev with an MCP client).
    transport: str = field(default_factory=lambda: os.environ.get("MCP_TRANSPORT", "streamable-http"))
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8000")))


CONFIG = Config()
