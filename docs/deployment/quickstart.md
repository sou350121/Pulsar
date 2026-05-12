# Quickstart — 10-minute verification

Goal: prove Pulsar's pipeline works on your machine *before* you adapt it to
your domain. We use the bundled `ai-news` preset — seven public RSS feeds, no
API keys required beyond an LLM key. By the end, you'll have a fresh
`memory/ai-app-rss-YYYY-MM-DD.json` on disk and the moltbot gateway running.

If you hit any error, jump to [`troubleshooting.md`](troubleshooting.md).

---

## 1. Prerequisites

- **OS**: Linux (recommended) or macOS
- **Python**: 3.10+ (the `mcp` package requires it; older Python will fail at install)
- **Node.js**: 22+
- **RAM**: 2 GB minimum (reference deployment runs on a 2 GB VPS)
- **One LLM API key**: DashScope, OpenAI, or Anthropic — any one works
- **Optional for verification**: GitHub token, Telegram bot token + chat ID
  (the preset's `jobs.json` keeps Telegram targets as `YOUR_TELEGRAM_CHAT_ID`
  placeholders, so messages won't be delivered until you fill those in)

---

## 2. Clone and install the moltbot CLI

```bash
git clone https://github.com/sou350121/Pulsar ~/clawd
cd ~/clawd
npm install -g moltbot
```

> Scripts assume the repo lives at `~/clawd`. If you clone elsewhere, see the
> path-substitution snippet in [`../../AGENTS.md`](../../AGENTS.md#setup-notes-verified).

---

## 3. Install the Python dependency

```bash
pip install mcp
```

`mcp` is the only Python package Pulsar's MCP server needs. If `pip` complains
that `mcp` requires Python ≥ 3.10, install a newer Python first (see
[`troubleshooting.md`](troubleshooting.md#pip-install-mcp-fails-with-requires-python-310)).

---

## 4. Export keys

At minimum, export one LLM API key. Everything else is optional for the
quickstart verification:

```bash
export DASHSCOPE_API_KEY=sk-...          # required (or OPENAI_API_KEY / ANTHROPIC_API_KEY)
export GITHUB_TOKEN=ghp_...              # optional (no GitHub push during verification)
export TELEGRAM_BOT_TOKEN=...            # optional (no TG delivery during verification)
export TELEGRAM_CHAT_ID=...              # optional
```

`scripts/quickstart.sh` checks for `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, or
`ANTHROPIC_API_KEY` and fails fast if none are set.

---

## 5. Run quickstart with the `ai-news` preset

```bash
bash scripts/quickstart.sh ai-news
```

This script (non-interactive, ~30 seconds) does six things:

1. Verifies an LLM API key is set
2. Confirms `config/presets/ai-news/` exists and has all three required files
3. Creates `$PULSAR_MEMORY_DIR` (default `~/clawd/memory`) if missing
4. Copies the preset's `active-config.json` and `assumptions.json` into the
   memory dir (won't overwrite existing files)
5. Substitutes `/home/admin` → `$HOME` in the preset's `jobs.json` and stages
   it at `~/.openclaw/cron/jobs.ai-news.staged.json`. If
   `~/.openclaw/cron/jobs.json` already exists, the staged file is left alone
   and you'll see a `diff` hint instead of an overwrite
6. Runs `python3 scripts/check-pipeline.py --quiet` — fails loudly if not green

For the full preset description (which RSS feeds, which 5 hypotheses, which 4
cron jobs), see [`../../config/presets/ai-news/README.md`](../../config/presets/ai-news/README.md).

---

## 6. Verify the install

`scripts/quickstart.sh` already runs the self-check, but you can rerun it any
time to confirm nothing has drifted:

```bash
python3 scripts/check-pipeline.py
```

Expected: every script line ends with `OK` and the final line reads
`all green ✓`. Exit code `0` = healthy, `1` = something to fix.

The check AST-parses every script, confirms the shared helpers
(`_vla_expert.py`, `_domain_loader.py`, `_gh_issues_config.py`) import, and
smoke-runs the leaf mechanical scripts (field-state, cross-domain,
gh-adoption, community-context, gh-issues collector) against a temporary
empty memory dir. Day-1 "no upstream data" exits are pinned to their expected
error messages so this check is meaningful before any real cron run.

---

## 7. Start the moltbot gateway

The gateway is the cron scheduler. Start it on the loopback interface:

```bash
pkill -f moltbot-gateway || true
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
```

Confirm it's listening and that the cron jobs registered:

```bash
ss -ltnp | grep 18789
moltbot cron list
tail -n 20 /tmp/moltbot-gateway.log
```

You should see four jobs from the `ai-news` preset: RSS collect (07:00), daily
report (08:00), calibration check (11:00), watchdog (23:00).

---

## 8. Manually trigger the first RSS pull

Don't wait for 07:00 — pull the first signal batch immediately:

```bash
python3 scripts/ai-app-rss-collect.py
ls ~/clawd/memory/ai-app-rss-$(date +%Y-%m-%d).json
```

`ai-app-rss-collect.py` exits silently on success. The `ls` confirms the
output file landed. Schema:
`{date, source_status, total_fetched, after_filter, items[], generated_at}`.

If the file is empty or missing, see
[`troubleshooting.md`](troubleshooting.md#memoryai-app-rss-json-is-empty-or-missing).

---

## 9. Known limitations of this verification

You've verified L1 (input) and the rating engine. A few things are
*intentionally* not exercised in the 10-minute path:

- **No Telegram delivery yet** — the preset's `jobs.json` ships with
  `"to": "YOUR_TELEGRAM_CHAT_ID"` placeholders. Replace them once you have a
  bot token and chat ID.
- **No GitHub push yet** — the preset doesn't ship a `github-config-*.json`.
  Push targets are configured per-domain; see step 5 of
  [`your-own-domain.md`](your-own-domain.md#5-edit-memoryactive-configjson).
- **No Watchdog auto-heal output yet** — Watchdog needs a few days of history
  to compare against; on day 1 it reports `MISSING` for everything that hasn't
  run yet. That's expected.
- **No deep-dive, no cross-domain, no semantic search** — these all have data
  dependencies (Day 3 / 7 / 14 / 28 / 60 — see the
  [enablement timeline](../use-cases/README.md#when-to-enable-what)).

---

## 10. Next steps

Pulsar is running. To track *your* domain instead of AI news:

→ [`your-own-domain.md`](your-own-domain.md)

If anything in steps 1–9 went wrong:

→ [`troubleshooting.md`](troubleshooting.md)
