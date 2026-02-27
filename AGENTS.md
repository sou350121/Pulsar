# Pulsar · 照見 — Agent Notes

## System Identity
- Chinese: 照見（Zhàojiàn）
- English: Pulsar
- Purpose: Automated AI/VLA signal intelligence pipeline

## Key Paths (after setup)
- Scripts: `~/clawd/scripts/`
- Memory/state: `~/clawd/memory/`
- Cron jobs: `~/.openclaw/cron/jobs.json`
- Gateway log: `/tmp/moltbot-gateway.log`

## Pipeline Overview
See `scripts/SCRIPTS.md` for full DAG.

## Environment
- API keys in `~/.clawdbot/.env` or system environment
- DashScope key in `~/.moltbot/agents/reports/agent/auth-profiles.json`

## Setup Notes (verified)

**Clone path**: scripts hardcode `/home/admin/clawd/` — clone to `~/clawd/` or
update paths after cloning:
```bash
MYUSER=$(whoami)
find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
```

**Keys file**: `.env.example` is in the repo root (not `config/`):
```bash
cp .env.example .env
```

**Cron jobs**: no `moltbot cron import` command exists. Load the template by
copying before the gateway starts:
```bash
pkill -f moltbot-gateway || true
mkdir -p ~/.openclaw/cron
cp config/jobs.template.json ~/.openclaw/cron/jobs.json
```

**GitHub config files**: not in repo — create from template:
```bash
mkdir -p memory
cp config/github-config.template.json memory/github-config-vla-handbook.json
cp config/github-config.template.json memory/github-config-agent-playbook.json
# Edit each to set "repo" to your fork name
```

**vla-rss-collect.py**: exits silently on success (no stdout). Verify via:
```bash
ls ~/clawd/memory/vla-rss-$(date +%Y-%m-%d).json
```
Output file schema: `{date, feed_status, total_fetched, after_filter, papers[], generated_at}`

**vla-daily-hotspots.json schema**: top-level key is `reported_papers` (not `hotspots`):
```python
papers = d.get("reported_papers", [])  # each has: title, date, url, rating, reason, affiliation
```
