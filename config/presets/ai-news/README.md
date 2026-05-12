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

## The 4 cron jobs

| Time (Asia/Shanghai) | Job | Script |
|---|---|---|
| 07:00 | RSS Collect | `ai-app-rss-collect.py` |
| 08:00 | Daily Report | `write-ai-app-daily.py` |
| 11:00 | Calibration Check | `prep-calibration-check.py` |
| 23:00 | Daily Watchdog | `daily-watchdog.py` |

That's deliberately minimal. We **exclude** social-intel, SOTA tracker, release tracker, deep-dive, cross-domain, and biweekly jobs from the first deploy: those scripts read derived state that doesn't exist on day 1. Add them once `memory/` has a few days of accumulated signal — see [`docs/use-cases/README.md`](../../../docs/use-cases/README.md) for the "When to enable what" ladder.

## Why scripts are named `ai-app-*`

Historical. They were the first non-VLA pipeline shipped in Pulsar and the name stuck. The engine itself is domain-agnostic: every one of those scripts reads `active-config.json` (keywords, institutions, RSS sources, research directions) without any hard-coded "AI" assumption. Drop a different `active-config.json` into `$PULSAR_MEMORY_DIR/` and the same scripts will track that domain.

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
