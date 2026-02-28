# Multi-Domain Configuration

Pulsar supports multiple research domains under a shared pipeline infrastructure. Each domain has its own config file, memory namespace, GitHub archive, and Telegram delivery channel — all registered in a single `domains.json` registry.

## Current Domains

| Key | Name | Description |
|-----|------|-------------|
| `vla` | VLA | Vision-Language-Action models for robotics and manipulation |
| `ai_app` | AI App | AI application and agent ecosystem — tools, frameworks, products |

---

## Registry: `domains.json`

`memory/domains.json` is the single source of truth for all configured domains.

**Schema:**
```json
{
  "version": 1,
  "domains": {
    "<key>": {
      "name": "Human-readable name",
      "description": "Short description",
      "enabled": true,
      "active_config": "<config-file>.json",
      "shadow_config": "<shadow-config-file>.json",
      "pending_changes": "<pending-file>.json",
      "github_config": "<github-config-file>.json",
      "tg_account": "<telegram-account-name>",
      "tg_target": "<telegram-chat-id>",
      "memory_files": {
        "<key>": "<filename>.json"
      }
    }
  }
}
```

---

## Shared Loader: `_domain_loader.py`

New scripts should use the shared loader instead of hardcoding config paths.

```python
from _domain_loader import load_domain, list_domains

# List all enabled domains
for key in list_domains():
    d = load_domain(key)
    print(d.key, d.name, d.description)

# Load config for a specific domain
domain = load_domain("vla")
cfg    = domain.active_config()          # parsed active-config.json
gh_cfg = domain.github_config()         # parsed github-config-*.json

# Access delivery settings
print(domain.tg_account)                # "original"
print(domain.tg_target)                 # "1898430254"

# Access memory file paths
path = domain.memory_path("hotspots")   # absolute path to vla-daily-hotspots.json
```

**CLI:**
```bash
python3 scripts/_domain_loader.py --list        # list all enabled domains
python3 scripts/_domain_loader.py --show vla    # show full domain metadata
```

---

## Adding a New Domain

### Step 1 — Create the config file

Copy an existing config and adapt it:
```bash
cp memory/active-config.json memory/bio-active-config.json
# Edit: update tag, keywords_A, keywords_B, research_directions
```

### Step 2 — Create the GitHub config (if archiving to a repo)

```bash
cp memory/github-config-vla-handbook.json memory/github-config-bio-archive.json
# Edit: update tag and repo fields
```

### Step 3 — Register in `domains.json`

Add a new entry under `"domains"`:
```json
"bio": {
  "name": "BioMed",
  "description": "Biomedical AI and drug discovery",
  "enabled": true,
  "active_config": "bio-active-config.json",
  "shadow_config": "bio-shadow-active-config.json",
  "pending_changes": "bio-pending-changes.json",
  "github_config": "github-config-bio-archive.json",
  "tg_account": "bio_bot",
  "tg_target": "1898430254",
  "memory_files": {
    "hotspots": "bio-daily-hotspots.json",
    "sota":     "bio-sota-tracker.json"
  }
}
```

### Step 4 — Create domain scripts

Follow the `prep → run → post` naming pattern:
```
scripts/bio-rss-collect.py
scripts/prep-bio-social.py
scripts/post-bio-hotspots.py
```

Use `_domain_loader` at the top:
```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from _domain_loader import load_domain
domain = load_domain("bio")
cfg = domain.active_config()
```

### Step 5 — Add cron jobs

```bash
moltbot cron add --name "Bio RSS" --cron "0 8 * * *" \
  --command "python3 /home/admin/clawd/scripts/bio-rss-collect.py"
```

### Step 6 — Verify via MCP

```
list_domains()          → should include "bio"
get_domain_config("bio") → returns bio-active-config.json contents
```

---

## MCP Tools for Domains

| Tool | Description |
|------|-------------|
| `list_domains()` | List all configured domains with key, name, description |
| `get_domain_config(domain)` | Return the active config (keywords, directions) for a domain |

---

## Design Principles

- **Shared scheduler, isolated memory**: All domains run under the same cron scheduler; each domain's data files are prefixed or namespaced separately
- **No cross-domain state**: Domain scripts are independent; cross-domain reasoning happens in dedicated cross-domain tools (see Cross-domain Rule Engine roadmap item)
- **Read-only registry**: `domains.json` is read at runtime; never modified by pipeline scripts
- **2 GB RAM budget**: Domains run sequentially, not in parallel — schedule them at different times
