"""Per-item summaries. Extractive and free by default (strip HTML, take lead text).

Swap in an LLM pass (e.g. Claude Haiku) behind this same function later for nicer
1-liners + 'why it matters' — keep it optional so the server can run at zero cost.
"""

from __future__ import annotations

import html
import re

from .extract import first_sentences

_TAG = re.compile(r"<[^>]+>")


def clean_text(raw: str) -> str:
    text = _TAG.sub(" ", raw or "")
    text = html.unescape(text)
    return " ".join(text.split())


def make_summary(raw_summary: str, max_chars: int = 240) -> str:
    return first_sentences(clean_text(raw_summary), max_chars=max_chars) or ""
