# Pulsar MCP Server

Pulsar exposes its knowledge base as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server, making it queryable by Claude, Cursor, or any MCP-compatible client — without custom integration.

## Quick Start

**Install dependency:**
```bash
pip install mcp   # requires Python 3.11+
```

**Run:**
```bash
python3.11 /home/admin/clawd/scripts/mcp_server.py
```

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "pulsar": {
      "command": "python3.11",
      "args": ["/home/admin/clawd/scripts/mcp_server.py"]
    }
  }
}
```

Override the memory directory:
```bash
PULSAR_MEMORY_DIR=/your/path python3.11 scripts/mcp_server.py
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
```

---

## Implementation Notes

- **Runtime:** Python 3.11 + `mcp 1.26.0` (FastMCP)
- **Transport:** stdio (local process, zero network exposure)
- **Memory directory:** `/home/admin/clawd/memory/` (overridable via `PULSAR_MEMORY_DIR`)
- **Read-only:** the server never writes to memory files
- **AI social intel** is stored as dated `.md` files (`_ai_social_YYYY-MM-DD.md`); `get_social_intel(domain="ai")` globs and returns the relevant range
