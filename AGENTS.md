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
See `scripts/SCRIPTS.md` for full DAG and [`docs/architecture.md`](docs/architecture.md) for the 4-layer model + closed self-correction loop.

## Cron Schedule (Reference Deployment)

> ⚠️ The slots below are from the **maintainer's live deployment**, not all of
> them ship in `config/jobs.template.json`. The shipped template defines the
> **33 core jobs**; the newer advanced scripts (field-state, GH adoption,
> cross-domain v2) are intentionally **not pre-scheduled** because the right
> cadence depends on your domain and signal volume. Add them via
> `moltbot cron add --message "..."` (or by editing `~/.openclaw/cron/jobs.json`
> while the gateway is stopped) once you've tuned the rest of the pipeline.

Notable slots (Asia/Shanghai TZ):

| Time | Job |
|------|-----|
| 00:50 | Upstream signal monitor (arxiv cs.CL / cs.AI / stat.ML) |
| 07:30 | GitHub Issues daily collector (tier-1 repos) |
| 09:05 | VLA RSS collect → 09:15 hotspots → 09:30 social → 09:50 SOTA |
| 09:55 | Entity tracker |
| 09:56 | Field-state trigger (`ai-field-state.py`) |
| 10:10 | Drift detector (7-day rolling + 30-day decay) |
| 10:20 | Cross-domain rule engine v2 (R001-R007) |
| 10:30 | Daily watchdog (16 checks, DAG-ordered self-healing) |
| 11:00 | Calibration check — hypothesis trigger scan |
| 11:15 | Semantic index incremental refresh |
| Fri 13:00 | GitHub adoption analysis (tier-1 + tier-2) |
| Fri 16:30 | VLA weekly deep dive |
| Mon/Wed/Fri/Sun 15:45 | AI workflow inspiration |
| 28th monthly | Calibration aggregation — confidence updates |

Deep-dive slots are FIFO-queued with water-level quota gates; on Fridays the daytime deep-dive slots skip in favor of weekly deep-dive runs.

### Scheduling a new script

After you've copied the relevant scripts and verified they run manually,
schedule them via Moltbot. Minimal recipe (replace the cron expression and
script path):

```bash
moltbot cron add \
  --name "Field-State Trigger" \
  --cron "56 9 * * *" \
  --session isolated \
  --timeout 90000 \
  --message $'你是「场态触发器」定时任务。严格执行：\n1) 运行：timeout 60 python3 ~/clawd/scripts/ai-field-state.py\n2) 退出码0=正常，非0=错误\n3) 脚本执行完毕后绝对静默'
```

Pulsar cron jobs need the identity-frame message pattern (`你是…定时任务`) — bare
command strings cause the runtime to skip the tool call. Use `~` or
`$HOME/clawd/...` once you've run the `find scripts/ -name "*.py" |
xargs sed -i "s|/home/admin|/home/$USER|g"` substitution from the README.

## Key Scripts Added in Recent Releases

- `cross-domain-rule-engine.py` — v2 with 7 built-in rules
- `ai-field-state.py` — mechanical trigger gate (zero LLM)
- `collect-github-issues.py` + `compute-gh-adoption.py` + `_gh_issues_config.py` + `update-gh-field-notes.py` — GitHub Issues Adoption Sensor
- `prep-community-context.py` — community + adoption context bundler
- `semantic-index-builder.py` + `semantic-search.py` — DashScope embedding index
- `entity-tracker.py` — author/lab/method/benchmark index
- `upstream-signal-monitor.py` — upstream-domain early signals

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
