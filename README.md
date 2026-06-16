# contentlist-mcp

A free **"search engine for AI agents."** Connect this MCP server to Claude, ChatGPT,
Cursor, Gemini — any MCP client — and one tool call turns a natural-language query into a
**ranked, deduped, cited content list**:

> "top tech news today" · "what's new in songs this week" · "latest in AI"

The server does the whole curation pipeline (search → fetch → extract → dedupe → rank →
summarize) **server-side**, so the agent just renders the list instead of opening pages and
burning tokens.

> Full architecture & rationale: [`docs/design.md`](docs/design.md).

## How it works

```
Agent ──search_content("top news today")──▶  contentlist-mcp
                                              ├─ RSS / vertical feeds   (free, clean, fresh)
                                              ├─ SearXNG (self-hosted)  (free, broad web)
                                              └─ Tavily free tier        (managed fallback)
              ◀── ranked, deduped, cited list ──┘  (cached for instant warm hits)
```

**"Free like Google":** the default backends are **truly free** — self-hosted SearXNG
(metasearch over 70+ engines) + publisher RSS feeds, with Tavily's free tier (1,000
credits/mo, no card) as an automatic fallback. Paid backends (Brave/Bing) are a drop-in
upgrade behind the same contract — no change to the agent integration.

## MCP tools

| Tool | What it returns |
|------|-----------------|
| `search_content(query, vertical, freshness, limit, summaries, region, lang)` | A ranked content list: each item has `title, url, source, published_at, summary, thumbnail, cluster_size`. |
| `fetch_page(url)` | Cleaned main text + metadata for one URL (read an item in full). |
| `list_verticals()` | Supported verticals + default freshness windows. |

Verticals: `news`, `music`, `web` — or `auto` (routed from the query's keywords).
Freshness: `day`, `week`, `month`, `any` (or `auto` per vertical).

## Quickstart

### Run everything with Docker (recommended — includes the free SearXNG backend)
```bash
cp .env.example .env          # optional: add TAVILY_API_KEY
docker compose up --build
# MCP server: http://localhost:8000/mcp
```

### Run from source
```bash
pip install -e ".[dev]"
# Option A — RSS-only, zero config (news/music verticals work out of the box):
contentlist-mcp
# Option B — add the free web engine: point at a SearXNG instance
SEARXNG_URL=http://localhost:8080 contentlist-mcp
```

### Connect a client
**Claude Code / Cursor (`.mcp.json` / `~/.cursor/mcp.json`):**
```json
{ "mcpServers": { "contentlist": { "type": "http", "url": "http://localhost:8000/mcp" } } }
```
**Claude Desktop / Codex (stdio):**
```json
{ "mcpServers": { "contentlist": { "command": "contentlist-mcp", "env": { "MCP_TRANSPORT": "stdio" } } } }
```

## Configuration

All optional — see [`.env.example`](.env.example). Key ones:

| Var | Default | Purpose |
|-----|---------|---------|
| `SEARXNG_URL` | _(empty)_ | Self-hosted SearXNG base URL; empty = RSS-only |
| `TAVILY_API_KEY` | _(empty)_ | Enables the managed fallback (free tier) |
| `MCP_TRANSPORT` | `streamable-http` | `streamable-http` (hosted) or `stdio` (local) |
| `CACHE_TTL_DAY` | `300` | Warm-cache TTL (s) for daily-fresh queries |
| `MAX_LIMIT` | `25` | Hard cap on items per request |
| `BLOCKED_DOMAINS` | _(empty)_ | CSV of domains to drop |

## Development

```bash
pip install -e ".[dev]"
pytest          # dedupe + ranking unit tests
ruff check .
```

## Project layout
```
src/contentlist_mcp/
  server.py        # MCP tools (search_content, fetch_page, list_verticals)
  pipeline.py      # retrieve → dedupe → rank → summarize orchestration
  verticals.py     # per-vertical feeds + ranking weights
  retrieval/       # rss · searxng · tavily backends (pluggable)
  dedupe.py rank.py extract.py summarize.py cache.py config.py models.py
docs/design.md     # architecture, backend comparison, roadmap
docker-compose.yml # SearXNG + server
```

## Status
Phase-0 MVP: `news` + `music` (RSS) and generic `web` (SearXNG/Tavily), extractive
summaries, in-memory cache, prompt-injection-aware. Roadmap in `docs/design.md` §12.

## Security
Scraped content is untrusted input to an LLM — it's returned as **data, never
instructions**. `fetch_page` has SSRF guards (blocks private/loopback IPs) and honors a
domain blocklist. Run your own SearXNG to keep queries private.

## License
Proprietary — © tech-sumit. All rights reserved.
