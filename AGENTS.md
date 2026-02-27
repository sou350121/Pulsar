# Pulsar · 照見 — Agent Notes

## System Identity
- Chinese: 照見（Zhàojiàn）
- English: Pulsar
- Purpose: Automated domain intelligence pipeline (configurable for any research domain)

## Key Paths (after setup)
- Scripts: `~/clawd/scripts/`
- Memory/state: `~/clawd/memory/`
- Cron jobs: `~/.openclaw/cron/jobs.json`
- Gateway log: `/tmp/moltbot-gateway.log`

## Pipeline Overview
See `scripts/SCRIPTS.md` for full DAG.

## Environment
- API keys in `~/.clawdbot/.env` or system environment
- LLM key: `DASHSCOPE_API_KEY` (works with any OpenAI-compatible provider; update base URL in `scripts/_vla_expert.py` to switch)
- DashScope key also in `~/.moltbot/agents/reports/agent/auth-profiles.json`
- Tophub API key in `~/.clawdbot/.env` as `TOPHUB_API_KEY`

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
# Then fill in DASHSCOPE_API_KEY, GITHUB_TOKEN, TELEGRAM_BOT_TOKEN,
# TELEGRAM_CHAT_ID, MOLTBOT_GATEWAY_PORT, TOPHUB_API_KEY
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
cp config/github-config.template.json memory/github-config-primary.json
# Edit: set "repo" to your knowledge-base repo (e.g. "your-username/your-domain-handbook")
# For the reference dual-domain deployment, create two configs:
cp config/github-config.template.json memory/github-config-vla-handbook.json
cp config/github-config.template.json memory/github-config-agent-playbook.json
```

**vla-rss-collect.py**: exits silently on success (no stdout). Verify via:
```bash
ls ~/clawd/memory/vla-rss-$(date +%Y-%m-%d).json
```
Output file schema: `{date, feed_status, total_fetched, after_filter, papers[], generated_at}`

**ai-app-rss-collect.py**: exits silently on success. Verify via:
```bash
ls ~/clawd/memory/ai-app-rss-$(date +%Y-%m-%d).json
```
Output file schema: `{date, source_status, total_fetched, after_filter, items[], generated_at}`

**Note**: `memory/` is auto-created at runtime and ignored by `.gitignore`.
Do not commit files from `memory/` or `tmp/` into the repo.

**vla-daily-hotspots.json schema**: top-level key is `reported_papers` (not `hotspots`):
```python
papers = d.get("reported_papers", [])  # each has: title, date, url, rating, reason, affiliation
```
