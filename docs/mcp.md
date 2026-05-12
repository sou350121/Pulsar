# Pulsar MCP Server

Pulsar exposes its knowledge base as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server, making it queryable by Claude, Cursor, or any MCP-compatible client — without custom integration.

## Quick Start

**Install dependency:**
```bash
pip install mcp   # requires Python 3.11+
```

**Run** (substitute your clone path; the script auto-detects sibling helpers):
```bash
python3.11 ~/clawd/scripts/mcp_server.py
```

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json`) — use an
absolute path so Claude Desktop can resolve it under your home:
```json
{
  "mcpServers": {
    "pulsar": {
      "command": "python3.11",
      "args": ["/Users/you/clawd/scripts/mcp_server.py"]
    }
  }
}
```

Override paths:
```bash
PULSAR_MEMORY_DIR=/your/memory \
PULSAR_SCRIPTS_DIR=/your/scripts \
python3.11 mcp_server.py
```

---

## Tools

### Signal Tools

| Tool | Args | Description |
|------|------|-------------|
| `get_vla_signals` | `days=7`, `min_rating="🔧"` | VLA paper signals filtered by recency and rating (⚡ > 🔧 > 📖 > ❌) |
| `get_ai_signals` | `days=7` | AI App / Agent daily picks |
| `search_signals` | `keyword`, `days=30` | Full-text search across VLA papers + AI picks |

### Knowledge Tools

| Tool | Args | Description |
|------|------|-------------|
| `get_assumptions` | `domain="all"` | Active research hypotheses (`vla`, `ai_app`, or `all`) |
| `get_vla_sota` | `days=30` | SOTA benchmark records (pass `days=0` for all-time) |
| `get_vla_releases` | `days=30` | Model/library release events |
| `get_social_intel` | `domain="vla"`, `days=14` | Community signals: VLA (structured JSON) or AI (markdown reports) |

### Meta Tools

| Tool | Args | Description |
|------|------|-------------|
| `get_predictions` | `domain="all"` | Latest biweekly predictions + previous-round results |
| `get_pipeline_health` | — | Last watchdog run status + 7-day signal volume stats |

### Domain Registry

| Tool | Args | Description |
|------|------|-------------|
| `list_domains` | — | All configured Pulsar domains (`memory/domains.json`) with keys, names, and descriptions |
| `get_domain_config` | `domain` | Active config (keywords, hypotheses, RSS sources, research directions) for one domain |

### Search

| Tool | Args | Description |
|------|------|-------------|
| `search_memory` | `query`, `days=60`, `top=5`, `source_type=""` | Semantic search over the 60-day memory window via DashScope `text-embedding-v3` + cosine similarity. `source_type` filters to e.g. `social`, `daily-pick`, `theory`. |

> **Tool count: 12.** All tools are read-only; the server never writes to memory files.

---

## Rating Scale

| Rating | Meaning |
|--------|---------|
| ⚡ | Breakthrough — top-tier paper, major release, or paradigm shift |
| 🔧 | Solid — meaningful technical advance, worth tracking |
| 📖 | Reference — informational, low immediate impact |
| ❌ | Noise — irrelevant or low quality |

`get_vla_signals` defaults to `min_rating="🔧"`, returning ⚡ and 🔧 items only.

---

## Example Queries (via Claude)

```
What are the top VLA breakthroughs in the last 7 days?
→ get_vla_signals(days=7, min_rating="⚡")

Search for papers about diffusion models in robotics
→ search_signals(keyword="diffusion", days=30)

What hypotheses does Pulsar currently track?
→ get_assumptions(domain="vla")

Is the pipeline healthy? Any failed checks today?
→ get_pipeline_health()

What were last month's predictions and did they come true?
→ get_predictions(domain="all")

What domains is this Pulsar instance tracking?
→ list_domains()

What keywords does the AI app domain use for rating?
→ get_domain_config(domain="ai_app")

What evidence contradicted assumption V-003 last month?
→ search_memory(query="V-003 contradicted", days=30, top=5)
```

---

## Implementation Notes

- **Runtime:** Python 3.11 + `mcp 1.26.0` (FastMCP)
- **Transport:** stdio (local process, zero network exposure)
- **Memory directory:** defaults to `~/clawd/memory/` (the reference deployment path) and is overridable via `PULSAR_MEMORY_DIR`
- **Scripts directory:** auto-detected from `mcp_server.py` path (overridable via `PULSAR_SCRIPTS_DIR`); needs to contain `_domain_loader.py` and `semantic-search.py`
- **Read-only:** the server never writes to memory files
- **AI social intel** is stored as dated `.md` files (`_ai_social_YYYY-MM-DD.md`); `get_social_intel(domain="ai")` globs and returns the relevant range
- **`search_memory` dependencies:** semantic index files (`memory/semantic-index/{chunks.jsonl,vectors.bin}`) must be built by `semantic-index-builder.py` first; if missing, the tool returns a friendly "index not built" message
