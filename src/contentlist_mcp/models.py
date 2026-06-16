"""Public data models — these define the MCP tool's structured output contract."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContentItem(BaseModel):
    """One curated entry in a content list."""

    rank: int
    title: str
    url: str
    source: str = Field(description="Human-readable source/outlet name, e.g. 'Ars Technica'.")
    published_at: Optional[datetime] = None
    summary: str = ""
    why_it_matters: str = ""
    thumbnail: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    cluster_size: int = Field(1, description="How many sources covered this same story.")


class ContentList(BaseModel):
    """The finished, ranked list returned to the agent."""

    query: str
    vertical: str
    generated_at: datetime
    items: list[ContentItem]
    sources_used: list[str] = Field(default_factory=list)
    cache: str = Field("miss", description="hit | miss | partial")


class Candidate(BaseModel):
    """Internal pre-ranking record produced by a retrieval source."""

    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None
    summary: str = ""
    thumbnail: Optional[str] = None
    backend: str = ""  # which retrieval backend produced it (searxng/rss/tavily)
    score: float = 0.0
    cluster_size: int = 1
