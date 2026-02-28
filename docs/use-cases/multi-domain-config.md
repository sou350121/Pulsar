# Multi-domain Config — Use Cases

> **Status**: ✅ Done | **Priority**: P0 | **Issue**: [#2](https://github.com/sou350121/Pulsar/issues/2)

Centralizes all domain-specific settings (memory paths, Telegram accounts, GitHub configs, keyword lists) in `memory/domains.json` so new research domains can be added without touching existing scripts.

---

## Use Case 1: Adding a 3rd Research Domain — Biomedical AI

**Scenario**: The researcher wants to start monitoring biomedical AI (e.g. protein folding, medical imaging LLMs) in parallel with VLA and AI App, reusing the same cron infrastructure.

**What happens**: A new entry is added to `memory/domains.json`. The shared `_domain_loader.py` picks it up automatically. New scripts for the domain use `load_domain("biomedical")` to get paths and config; existing VLA and AI App scripts are untouched.

**Example**:
```json
// memory/domains.json — add third entry:
{
  "biomedical": {
    "display_name": "Biomedical AI",
    "config_path": "memory/biomedical-config.json",
    "memory_files": {
      "signals": "biomedical-signals-{date}.json",
      "hotspots": "biomedical-hotspots-{date}.json"
    },
    "telegram_account": "biomedical_bot",
    "telegram_target": 1898430254,
    "github_config": "github-config-biomedical.json"
  }
}
```
```python
# In any new script:
from _domain_loader import load_domain
cfg = load_domain("biomedical")
signals_path = cfg["memory_files"]["signals"].format(date=today)
```

---

## Use Case 2: Per-domain Telegram Routing — No Cross-posting

**Scenario**: VLA reports must arrive via the `@original` Telegram account and AI App reports via `@ai_agent_dailybot`. The researcher wants to enforce this separation at the config layer, not scattered across individual scripts.

**What happens**: Each domain entry in `domains.json` carries `telegram_account` and `telegram_target`. Post scripts call `load_domain(name)` and read these values instead of hardcoding account flags. Swapping accounts for a domain requires one JSON edit.

**Example**:
```python
cfg = load_domain("vla")
# cfg["telegram_account"] == "original"
# cfg["telegram_target"] == 1898430254

subprocess.run([
    "moltbot", "message", "send",
    "--account", cfg["telegram_account"],
    "--target", str(cfg["telegram_target"]),
    "--message", report_text
])
```
Changing VLA to a new Telegram channel: edit `domains.json` only. No script changes.

---

## Use Case 3: Updating AI App Keywords Without Touching VLA Config

**Scenario**: The AI App pipeline is missing "agentic RAG" papers because the keyword list is stale. The researcher wants to add the term without any risk of disturbing VLA configuration.

**What happens**: Each domain's `config_path` points to a separate JSON file (e.g. `memory/ai-app-config.json`). The researcher edits only that file. `_domain_loader.py` reads domain configs lazily; VLA's config is never loaded during AI App runs.

**Example**:
```json
// memory/ai-app-config.json — keywords section:
{
  "keywords": {
    "primary": ["AI agent", "LLM app", "tool use", "agentic RAG"],
    "secondary": ["RAG pipeline", "function calling", "multi-agent"],
    "exclude": ["cryptocurrency", "marketing automation"]
  }
}
```
VLA's `memory/vla-config.json` has its own `keywords.primary` list (e.g. `["VLA", "robot learning", "dexterous manipulation"]`) and is never read during AI App cron jobs.

---

## Use Case 4: New Contributor Sets Up a Custom Domain Fork

**Scenario**: A team member wants to run their own Pulsar instance monitoring a different field (e.g. autonomous driving) without forking the entire codebase or conflicting with the researcher's instance.

**What happens**: The contributor clones `Pulsar-KenVersion`, runs the deploy script, then adds their domain to `domains.json` and creates matching config and memory files. `list_domains()` from `_domain_loader` lets scripts and MCP tools enumerate all configured domains dynamically.

**Example**:
```bash
# After clone + deploy:
cp memory/vla-config.json memory/autodrive-config.json
# Edit autodrive-config.json with domain-specific keywords, sources

# Add to domains.json:
# "autodrive": { "display_name": "Autonomous Driving", ... }

# Verify:
python3 -c "from _domain_loader import list_domains; print(list_domains())"
# ['vla', 'ai_app', 'autodrive']
```
Cron jobs for the new domain reference `autodrive` domain key; all shared infra (watchdog, MCP, GitHub push) works without modification.

---

*See also: [One-click Deploy](one-click-deploy.md), [Cross-domain Rule Engine](cross-domain-rule-engine.md)*
