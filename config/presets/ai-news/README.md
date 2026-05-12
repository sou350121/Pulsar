# AI News preset

A 10-minute, public-feed-only Pulsar deployment that tracks AI / ML news from seven RSS sources.

This preset exists to prove (and let new users verify) that the Pulsar engine is **domain-agnostic** — the same scripts that ship the VLA pipeline run unmodified here, reading whatever `active-config.json` provides.

## What it tracks

Seven public RSS feeds, no API keys required:

| Source | URL |
|---|---|
| arXiv cs.AI | `https://export.arxiv.org/rss/cs.AI` |
| arXiv cs.CL | `https://export.arxiv.org/rss/cs.CL` |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` |
| Lil'Log (Lilian Weng) | `https://lilianweng.github.io/index.xml` |
| Ahead of AI (Sebastian Raschka) | `https://magazine.sebastianraschka.com/feed` |
| The Batch (DeepLearning.AI) | `https://www.deeplearning.ai/the-batch/feed/` |
| EleutherAI Blog | `https://blog.eleuther.ai/index.xml` |

Filters: 15 high-priority keywords (`keywords_A`), 4 broad nets (`keywords_B`), 8 institutions weighted by the LLM rater.

Tracks 5 hypotheses (`AI-001` through `AI-005`) covering open-source parity, agentic adoption, inference cost, MCP, and RAG's future. See `assumptions.json`.

## The 2 cron jobs

| Time (Asia/Shanghai) | Job | Script | Verified |
|---|---|---|---|
| 07:00 | RSS Collect | `ai-app-rss-collect.py` | ✅ End-to-end (2653 fetched → 289 after keyword filter) |
| 11:00 | Calibration Check | `prep-calibration-check.py` | ✅ End-to-end (40 signals matched against 5 hypotheses) |

Both jobs are **verified to run cleanly** in a fresh sandbox `$HOME` after `quickstart.sh`. That is the bar this preset commits to — anything else is opt-in.

### Why we excluded Daily Report and Watchdog from this preset

The maintainer's full deployment has 33 cron jobs. We strip them down to 2 because the rest assume infrastructure that doesn't exist on a fresh ai-news install:

- **Daily Report (`write-ai-app-daily.py`)** — in production this is **not** a direct script call; it's a multi-page LLM-agent prompt that reads RSS output, applies time-rules, dedups, and orchestrates write-ai-app-daily as a helper. The script alone requires `--date` and `--items-json` CLI args that the cron message doesn't supply. Adding it back means writing the agent prompt — see `config/jobs.template.json` for the production version.
- **Daily Watchdog (`daily-watchdog.py`)** — 16 health checks, ~11 of which are VLA-specific (`vla_hotspots`, `vla_social`, `vla_sota`, …). On a pure ai-news deploy, those checks always FAIL and the watchdog hangs trying to self-heal by invoking missing VLA cron jobs.
- **Social intel / SOTA / Release / Deep-dive / Cross-domain / Biweekly** — all read derived state that takes 7–60 days to accumulate. Add per the timeline in [`docs/use-cases/README.md`](../../../docs/use-cases/README.md#when-to-enable-what).

### Re-adding excluded jobs

When you're ready, copy entries from `config/jobs.template.json` into your `~/.openclaw/cron/jobs.json` (gateway stopped). Substitute `/home/admin` → `$HOME` and `YOUR_TELEGRAM_CHAT_ID` → your real ID. Restart the gateway. Start with one job at a time and watch `tail -F /tmp/moltbot-gateway.log`.

## Why scripts are named `ai-app-*`

Historical. They were the first non-VLA pipeline shipped in Pulsar and the name stuck.

### What the engine reads from `active-config.json` today

The `keywords_A` and `keywords_B` lists ARE live — they drive the rating filter end-to-end (verified: with the preset's 15+4 keyword set, an end-to-end test reduced 2653 fetched items to 289 after_filter ≈ 89% noise cut). This is what makes the preset's domain swap meaningful: change keywords, change what's rated relevant.

### What's currently decorative (be honest)

- **`rss_sources`** — `ai-app-rss-collect.py` has its RSS list **hard-coded** in `FEEDS_RSS` near the top of the file (~32 sources). The preset's seven `rss_sources` entries are documentation, not data flow. The hardcoded list happens to overlap with this preset's intent (HF blog, Lilian Weng, OpenAI, Anthropic, DeepMind, LangChain, BAIR, …) so AI-news adopters get good coverage anyway.
- **`institutions`** — not consumed by any collector script in this repo today. The LLM rater can be prompted to weight these, but the rating engine itself doesn't grep them yet.

### What this means in practice

- **AI-news domain**: works out of the box. Hardcoded feeds happen to fit.
- **Another domain (climate / biomed / fintech)**: copy `ai-app-rss-collect.py` → `your-domain-rss-collect.py`, edit `FEEDS_RSS` to point at your feeds, point the cron job at the new script. `keywords_A` / `keywords_B` flow through unchanged.

A future change to make the collector read `rss_sources` from the config (eliminating the fork-and-edit step for new domains) is on the roadmap but not in this release.

## Install (3 lines)

```bash
export DASHSCOPE_API_KEY=sk-...   # or OPENAI_API_KEY / ANTHROPIC_API_KEY
cd /path/to/Pulsar
bash scripts/quickstart.sh ai-news
```

The quickstart will:

1. Verify an LLM API key is set
2. Copy `active-config.json` and `assumptions.json` into `$PULSAR_MEMORY_DIR` (default `~/clawd/memory`)
3. Path-substitute `/home/admin` → `$HOME` in `jobs.json` and stage it for `~/.openclaw/cron/jobs.json` (won't overwrite an existing file without your say-so)
4. Run `scripts/check-pipeline.py` to confirm everything parses and smoke-runs clean
5. Print the next steps (start the gateway, trigger the first RSS pull, where to look for output)

## How to expand

- **Add social intel** when you want a second daily signal stream (~ 3 days in)
- **Add deep-dive** once `ai-daily-pick.json` has accumulated a week of picks
- **Add a second domain** by cloning this preset, renaming `ai_news` → `your_domain`, and registering it in `memory/domains.json` (see `scripts/templates/domains.template.json`)

Full ladder: [`docs/use-cases/README.md`](../../../docs/use-cases/README.md).

## How to customise this preset

Edit `$PULSAR_MEMORY_DIR/active-config.json` directly — `keywords_A`/`keywords_B`/`institutions`/`rss_sources` are all live. Bump `version` and append to `_changelog` so the calibration loop sees the diff.
