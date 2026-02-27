<div align="center">

<img src="docs/banner.svg" width="100%" alt="Pulsar · 照见">

### Pulsar · 照见: Automated Domain Intelligence Engine

[中文](README_CN.md) / English

<a href="https://github.com/sou350121/Pulsar">GitHub</a> · <a href="https://github.com/sou350121/Pulsar/issues">Issues</a> · <a href="AGENTS.md">Deployment Docs</a> · <a href="scripts/SCRIPTS.md">Pipeline DAG</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Node](https://img.shields.io/badge/Node-22%2B-green)](https://nodejs.org)
[![Stars](https://img.shields.io/github/stars/sou350121/Pulsar?style=social)](https://github.com/sou350121/Pulsar/stargazers)

👋 Join the community

📡 <a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar/issues">GitHub Issues</a>

</div>

---

## Overview

### The Challenges of Domain Intelligence

Anyone tracking a fast-moving technical domain runs into the same six problems eventually:

- **Signal overload** — dozens of new papers/articles daily; without a rating mechanism it's pure noise, and reading everything is impossible
- **Opaque reasoning** — AI summaries tell you "this is important" without explaining why; you can't trust or reproduce the judgment
- **Knowledge doesn't accumulate** — papers you read today, community debates from last week — all lost in inboxes and message streams
- **Unreliable pipelines** — cron jobs fail silently with no alert; by the time you notice, a week of data is missing
- **Unverifiable judgments** — "AI trend predictions" have no historical accuracy record; there's no way to evaluate the source's credibility
- **Static assumptions** — domain beliefs never update as new evidence arrives, drifting further from reality over time

### How Pulsar Solves Them

Pulsar is a server-side domain intelligence pipeline. **You define the domain; Pulsar runs the engine.** Configure your RSS feeds, keywords, and LLM provider once — then rating, filtering, reasoning, archiving, self-healing, and self-calibration all run autonomously.

- **Rate first, cut noise before LLM cost → solves signal overload**: A four-tier rating engine (⚡/🔧/📖/❌) evaluates every signal before it reaches the LLM. Raw signals → 3–5 selected for deep analysis, saving 80%+ inference cost
- **Three-stage observable reasoning chain → transparent and reproducible**: `prep → agent → post`, each stage with defined I/O formats and intermediate artifacts written to disk; when something breaks, you see exactly which stage failed
- **Structured knowledge written to Git → knowledge accumulates permanently**: All outputs are Markdown pushed to GitHub via the Contents API; full commit history, full-text grep, no SaaS dependency
- **Watchdog self-healing → pipelines recover automatically**: 15 health checks, 7 failure categories handled automatically in DAG order, full run logs persisted to `memory/watchdog-log.json`
- **Biweekly predictions + ✅/❌ tracking → accountability on record**: Every reasoning report includes verifiable predictions; the next report must grade them; accuracy history is tracked, not assumed
- **Monthly hypothesis calibration → beliefs update with evidence**: Domain hypotheses each with confidence scores; monthly trigger-rate analysis conservatively updates confidence; declining hypotheses automatically receive more signal in the next cycle

---

## Quick Start

### Prerequisites

- **OS**: Linux (recommended), macOS
- **Python**: 3.9 or higher
- **Node.js**: 22 or higher
- **Moltbot**: [https://molt.bot](https://molt.bot) — handles cron scheduling and Telegram delivery
- **Network**: stable access to your RSS sources, GitHub API, and your chosen LLM provider

**Keys required**:

| Key | Purpose | Compatible providers |
|-----|---------|---------------------|
| LLM API Key | All inference calls (rating, reasoning, intel) | Any OpenAI-compatible endpoint — OpenAI, DeepSeek, Moonshot, DashScope (Alibaba), Groq, etc. |
| GitHub Token | Push knowledge to your GitHub repos | GitHub Settings → Developer Settings → Fine-grained tokens (repo write) |
| Telegram Bot Token | Send daily intelligence updates | Telegram → search @BotFather → /newbot |
| Telegram Chat ID | Target channel or user ID | Telegram → search @userinfobot, send any message |
| Tophub API Key *(optional)* | Trending tech article feed | [tophubdata.com](https://www.tophubdata.com/) |

---

### 1. Clone the Repository

```bash
git clone https://github.com/sou350121/Pulsar ~/clawd
cd ~/clawd
```

> ⚠️ **Important**: Scripts are pre-configured for the `~/clawd/` directory. Cloning elsewhere requires updating hardcoded paths with:
> ```bash
> MYUSER=$(whoami)
> find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
> ```

---

### 2. Configure Your Research Domain

Copy the config template and edit it for your domain:

```bash
mkdir -p memory
cp config/active-config.template.json memory/active-config.json
```

Open `memory/active-config.json` and define:

- **RSS feeds** — any Atom/RSS URLs: arXiv category feeds, blog feeds, GitHub release feeds, news sites, anything with a feed
- **Keywords** — terms that mark a signal as domain-relevant (used by the rating engine to filter noise)
- **Institution labels** — org/lab tags for rating priority (e.g. `"[MIT]"`, `"[Google DeepMind]"`, `"[YCombinator]"`)
- **Hypotheses** — the domain beliefs you want to track and calibrate monthly

The included reference configuration tracks **VLA robotics** (arXiv `cs.RO`, `cs.AI`) and **AI developer tools** (tech news feeds). The pipeline logic is fully domain-agnostic — swap the config to track fintech, biomedical research, climate policy, or any other domain.

Also set your GitHub knowledge-base target:

```bash
cp config/github-config.template.json memory/github-config-primary.json
# Edit: set "repo" to your knowledge-base repo (e.g. "your-username/your-domain-handbook")
```

---

### 3. Set Up Environment Variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
# LLM provider key — any OpenAI-compatible endpoint works (see detail below)
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=xxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
MOLTBOT_GATEWAY_PORT=18789
TOPHUB_API_KEY=your_tophubdata_api_key   # optional: trending tech articles
```

> 💡 **Tip**: Telegram Chat ID is a positive integer for users, negative for channels. For channels, add the Bot as an admin first.

👇 Expand for configuration details:

<details>
<summary><b>LLM Provider — any OpenAI-compatible API works</b></summary>

All Pulsar LLM calls use the OpenAI SDK format throughout, so any compatible provider works without changing pipeline logic. The reference deployment uses **DashScope + qwen3.5-plus**, but you can swap to any provider:

| Provider | Base URL | Example model |
|----------|----------|---------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| DashScope (Alibaba) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.5-plus` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| Self-hosted | your endpoint | Ollama, vLLM, llama.cpp, etc. |

**To switch providers**: put your provider's API key in `DASHSCOPE_API_KEY` (or rename the var), then update the base URL constant in `scripts/_vla_expert.py` — a single-line change.

</details>

<details>
<summary><b>Telegram Bot Setup</b></summary>

Pulsar sends daily intelligence updates via Moltbot — no direct Telegram API calls needed.

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`, follow prompts, and get your Token (format: `123456789:ABCdef...`)
3. Add the Token to `TELEGRAM_BOT_TOKEN` in `.env`
4. Get your Chat ID: search `@userinfobot`, send any message — it replies with your ID
5. Add the Chat ID to `TELEGRAM_CHAT_ID` in `.env`

To push to a channel:

```bash
# Add Bot as channel admin first, then get the channel ID
# Channel IDs are negative integers, e.g. -1001234567890
```

> 💡 **Tip**: Pulsar supports multiple TG accounts (e.g. separate channels per domain). See [AGENTS.md](AGENTS.md).

</details>

<details>
<summary><b>GitHub Token Setup</b></summary>

Pulsar pushes daily outputs to your knowledge-base repos via the GitHub Contents API.

1. Go to GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Create a new token; under Repository access, select your target repos
3. Set permission: `Contents: Read and Write`
4. Add the token to `GITHUB_TOKEN` in `.env`

Create the GitHub config file in `memory/` (not in the repo — created from the template):

```bash
mkdir -p memory
cp config/github-config.template.json memory/github-config-primary.json
```

Then edit to point to your repo:

```json
{
  "repo": "your-username/your-domain-handbook",
  "api_base": "https://api.github.com",
  "token_env": "GITHUB_TOKEN",
  "branch": "main"
}
```

</details>

---

### 4. Start the Moltbot Gateway

Moltbot schedules all cron jobs and sends Telegram messages. Install first:

```bash
npm install -g moltbot
```

Then start the gateway:

```bash
pkill -f moltbot-gateway || true
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
```

Verify it's running:

```bash
ss -ltnp | grep 18789
tail -n 20 /tmp/moltbot-gateway.log
```

Expected output:

```
Gateway running on ws://127.0.0.1:18789
```

---

### 5. Load Cron Jobs

The scheduled jobs are stored in `config/jobs.template.json`. Load them by copying to the Moltbot cron directory **before** starting the gateway (or stop it first):

```bash
pkill -f moltbot-gateway || true
mkdir -p ~/.openclaw/cron
cp config/jobs.template.json ~/.openclaw/cron/jobs.json
```

Then restart the gateway and verify:

```bash
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot cron list
```

---

### 6. Run Your First Pipeline

The reference deployment ships a complete VLA robotics + AI developer tools configuration. Here's how to verify it end to end:

#### Collect today's signals (VLA robotics example)

```bash
python3 scripts/vla-rss-collect.py
```

Verify the collection worked:

```bash
ls ~/clawd/memory/vla-rss-*.json

python3 -c "
import json
with open('memory/vla-daily-hotspots.json') as f:
    d = json.load(f)
papers = sorted(d.get('reported_papers', []), key=lambda x: x.get('date',''), reverse=True)[:3]
for p in papers:
    print(p.get('rating','?'), p.get('title',''))
"
```

#### Trigger the full rating + push pipeline

```bash
moltbot cron run <vla-hotspots-job-id> --force --timeout 180000 --expect-final
```

> 📝 **Adapting to your domain**: the reference scripts are named `vla-*` and `ai-app-*`. To track a different domain, update `memory/active-config.json` with your RSS feeds and keywords, then fork and rename the relevant scripts. The three-stage structure (`prep → run → post`) stays the same.

Congratulations — Pulsar is live! 🎉

---

## Core Concepts

### 1. Signal Rating Engine

Pulsar runs a rule-based rating engine on every raw signal *before* any LLM call — it doesn't feed everything to the model.

**Four-tier system**:

| Rating | Meaning | Criteria | Daily cap |
|--------|---------|----------|-----------|
| ⚡ | Breakthrough | All 4 conditions met (top institution + key technology + high engineering value + strong relevance) | 1 |
| 🔧 | Engineering value | 3 of 4 conditions | 5 |
| 📖 | Worth watching | 2 of 4 conditions | unlimited |
| ❌ | Not relevant | 0–1 conditions | — |

The rating conditions — keywords, institution tags, relevance rules — are **all defined in your `memory/active-config.json`**. No code changes needed to adapt the rating engine to a new domain.

Only ⚡ and 🔧 signals enter downstream LLM analysis; the rest are filtered out.

**Result**: dozens of raw signals per day → average 4–6 enter reasoning → ~80% reduction in LLM cost.

---

### 2. Three-Stage Reasoning Chain

Every pipeline follows the same three-stage structure:

```
prep-*.py          →    run-*-two-phase.py    →    post-*.py
(structured collect)     (LLM reasoning)           (validation + output)
      ↓                        ↓                         ↓
candidates JSON          LLM output JSON           memory + GitHub + TG
```

All intermediate artifacts are written to `memory/tmp/` for debugging. If a pipeline fails mid-run, Watchdog detects the orphaned `llm-output` file and **resumes from the post stage** — skipping the expensive collection and LLM steps.

---

### 3. Knowledge Written to Git

All outputs are pushed to your configured repos via the GitHub Contents API:

```
Output type                 →    Target path (set in memory/github-config-*.json)
Domain signal ratings       →    your-repo/knowledge/ratings/
Social intelligence         →    your-repo/memory/blog/archives/social-intel/
Daily picks                 →    your-repo/memory/blog/archives/daily-pick/
Biweekly reasoning reports  →    your-repo/reports/biweekly/
```

Push script: `scripts/gh-contents-upload.py` (handles create/update, auto-resolves SHA).

**Benefits**:
- Full-text grep across all historical outputs (`git log -S "your keyword"`)
- Permanent archive, zero SaaS dependency
- Fork any knowledge repo and build your own domain knowledge graph

---

### 4. Watchdog Self-Healing

`scripts/daily-watchdog.py` runs daily and checks 15 health signals:

| Check | Pass condition | Self-healing action |
|-------|---------------|---------------------|
| `rss` | Today's RSS collected | Trigger RSS collector script |
| `hotspots` | Today's hotspots updated | Trigger hotspots cron job |
| `social` | Today's social intel has signals | Trigger social pipeline |
| `release` | Release tracker checked today | Trigger release tracker |
| `rating` | Rating completed within 10h | Warn (no auto-heal) |
| `disk_space` | Disk usage < 85% | Warn; > 95% → error |
| ... | ... | ... |

Self-healing follows DAG order (rss → daily → social) to avoid consuming data that hasn't been collected yet.

Run log: `memory/watchdog-log.json` (retains 60 entries; killed runs and recoveries both recorded).

---

### 5. Biweekly Prediction ✅/❌ Loop

Every two weeks, Pulsar generates a reasoning report containing verifiable predictions:

```markdown
### Predictions (next 2 weeks)
1. ⏳ [Your hypothesis] — Verification: [specific, measurable condition]
2. ⏳ [Another hypothesis] — Verification: [what you'd observe if true]
```

The next report reviews those predictions:

```markdown
### Previous Predictions Review
1. ✅ Confirmed — [evidence found]
2. ❌ Not confirmed — [counter-evidence]
```

This makes the system's judgment accuracy traceable and measurable, not just claimed.

---

### 6. Monthly Hypothesis Calibration

The system maintains `memory/assumptions.json` — domain hypotheses, each with a confidence score (0–1):

```json
{
  "id": "V-001",
  "text": "Your domain hypothesis here",
  "confidence": 0.72,
  "last_updated": "2026-02-01"
}
```

On the 28th of each month, `monthly-calibration-agg.py` automatically:
1. Computes 30-day trigger rates for each hypothesis
2. Conservatively updates confidence scores (max ±0.08/month)
3. Writes hypotheses with declining confidence to `watch-list.json`

The watch-list feeds back into `prep-calibration-check.py`, which injects extra signals for watched hypotheses — **the system proactively investigates its own blind spots** without human intervention.

---

## Project Architecture

```
Pulsar/
├── scripts/                    # Pipeline scripts
│   ├── prep-*.py               # Data collection (RSS, web search, GitHub API)
│   ├── run-*-two-phase.py      # Two-phase execution (prep + LLM agent)
│   ├── post-*.py               # Post-processing (validate + memory + GitHub + TG)
│   ├── daily-watchdog.py       # Health monitoring + self-healing (15 checks)
│   ├── memory-janitor.py       # Periodic cleanup of expired files
│   ├── memory-upsert.py        # Generic append-write tool for memory files
│   ├── gh-contents-upload.py   # GitHub Contents API push
│   ├── _vla_expert.py          # Shared LLM client + domain context module
│   └── SCRIPTS.md              # Full pipeline DAG documentation
│
├── config/
│   ├── active-config.template.json  # ← Start here: RSS feeds, keywords, domain settings
│   ├── assumptions.template.json    # Domain hypotheses template
│   ├── github-config.template.json  # GitHub push target template
│   └── jobs.template.json           # Cron job configurations
│
├── memory/                     # Local knowledge store (.gitignored, auto-created at runtime)
│   ├── active-config.json      # Your domain config (created from template)
│   ├── assumptions.json        # Domain hypotheses + confidence scores
│   ├── watchdog-log.json       # Watchdog run history
│   ├── tmp/                    # Pipeline intermediates (auto-cleaned after 60 days)
│   └── github-config-*.json    # GitHub push targets (created from template)
│
├── docs/
│   └── banner.svg
│
├── AGENTS.md                   # Full deployment guide (AI agent-readable)
├── .env.example                # Key template (copy to .env and fill in)
└── LICENSE                     # MIT
```

---

## How Pulsar Compares

Each tool has a genuine sweet spot — here's an honest breakdown:

**Pick Feedly AI** if you want zero setup, polished mobile UX, 1M+ curated sources, and team collaboration.
**Pick ResearchRabbit** if you're doing academic literature reviews — visual citation graphs and 270M+ papers.
**Pick MineContext** if you want to capture *your own* reading context — local-first, private.
**Pick Pulsar** if you need a server-side pipeline that runs autonomously, generates structured knowledge assets, self-heals on failure, and self-calibrates monthly.

| Dimension | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|-----------|-----------|---------------|-------------|------------|
| **Best at** | Team intel feeds, mobile | Academic citation mapping | Personal context capture | Autonomous domain pipeline |
| **Hosting** | ☁️ SaaS only | ☁️ SaaS only | ✅ Local / OSS | ✅ Self-hosted / OSS |
| **Cost** | \$1,600–3,200 / month | Closed pricing | Free | Free |
| **Setup effort** | ✅ Zero | ✅ Zero | ✅ Desktop install | ⚠️ ~1 hour |
| **LLM provider** | ❌ Fixed | ❌ Fixed | ❌ Fixed | ✅ Any OpenAI-compatible |
| **RSS configurable** | ⚠️ Limited | ❌ | ❌ | ✅ Any feed URL |
| **Domain configurable** | ⚠️ Topic filters | ❌ | ❌ | ✅ Fully custom |
| **Signal rating** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ before LLM |
| **Reasoning transparency** | ❌ Black-box | ❌ | ❌ | ✅ 3-stage observable chain |
| **Self-healing** | ❌ | ❌ | ❌ | ✅ 7 auto-recovery paths |
| **Belief calibration** | ❌ | ❌ | ❌ | ✅ Hypotheses, monthly |
| **Prediction tracking** | ❌ | ❌ | ❌ | ✅ ✅/❌ every 2 weeks |
| **Knowledge output** | Feed / inbox | Graph visualization | Local summaries | Structured Markdown → Git |
| **RAM footprint** | N/A (cloud) | N/A (cloud) | Desktop app | **2 GB VPS** |

---

## Biomimetic Architecture

Pulsar's internal layers follow a cognitive organism model, not a traditional data pipeline:

| Layer | Biological analog | Pulsar component |
|-------|------------------|-----------------|
| **Perception** | Sensory organs | Configurable RSS feeds · GitHub releases · community feeds |
| **Filtering** | Thalamic gate | Rating engine (⚡/🔧/📖/❌) — noise cut before LLM |
| **Reasoning** | Cortical processing | Three-stage LLM: prep → agent → post |
| **Memory** | Hippocampal encoding | Structured Markdown → GitHub |
| **Metacognition** | Prefrontal reflection | Biweekly prediction reviews · monthly calibration |
| **Immune system** | Autoimmune response | Watchdog: 15 health checks, 7 self-healing paths |

---

## Reference Deployment: Key Numbers

The included configuration tracks two domains simultaneously — VLA robotics research and AI developer tools. Numbers below reflect this dual-domain setup:

| Metric | Value |
|--------|-------|
| Scheduled jobs | **33** cron jobs across both domains |
| Pipeline scripts | **55** across VLA and AI pipelines |
| Tracked hypotheses | **19** with monthly confidence auto-updates |
| Watchdog checks | **15** health signals, **7** auto-recovery paths |
| End-to-end latency | **< 2 hours**: RSS → rated signals → TG notification |
| Knowledge retention | Social intel / hotspots **90-day** rolling · reports permanent in Git |
| Hardware requirement | **2 GB RAM** — minimal VPS |

A single-domain deployment needs roughly half the scripts and cron jobs.

---

## Reference Output Repositories

The reference deployment pushes content to these public repos daily:

| Repo | Domain | Contents |
|------|--------|---------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Robotics · VLA research | Daily paper ratings · theory deep dives · biweekly forecasts |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI apps · agent tools | Tool index · framework analyses · daily picks |

To connect Pulsar to your own repos, edit `memory/github-config-*.json` (copied from `config/github-config.template.json`).

---

## Further Reading

| Document | Contents |
|----------|---------|
| [AGENTS.md](AGENTS.md) | Full deployment guide: key config · path reference · troubleshooting |
| [scripts/SCRIPTS.md](scripts/SCRIPTS.md) | Full DAG of all pipeline scripts · I/O for each script |
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Reference VLA knowledge repo (live output) |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | Reference AI tools knowledge repo (live output) |

---

## Acknowledgements

Pulsar is built on top of [**Moltbot**](https://molt.bot) (formerly OpenClaw) — the agent gateway that handles cron scheduling, LLM routing, and Telegram delivery. Without Moltbot's reliable scheduling and agent runtime, the 33-job autonomous pipeline wouldn't be possible.

Thanks to the [Moltbot](https://molt.bot) team for building and maintaining the infrastructure that Pulsar runs on.

---

## Community & Contributing

Have a question, idea, or want to fork this into your own domain's Pulsar?

- 💬 **File an issue**: [GitHub Issues](https://github.com/sou350121/Pulsar/issues)
- 🔀 **Pull requests**: improvements to pipelines, new domain support, and bug fixes are welcome
- 📡 **See the reference outputs**: [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) · [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)

---

*MIT License — fork it, adapt it, make it your own domain's Pulsar.*
