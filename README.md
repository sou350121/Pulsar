<div align="center">

<img src="docs/banner.svg" width="100%" alt="Pulsar · 照见">

### Pulsar · 照见: Automated Domain Intelligence Engine

[中文](README_CN.md) / English

<a href="https://github.com/sou350121/Pulsar-KenVersion">GitHub</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">Issues</a> · <a href="AGENTS.md">Deployment Docs</a> · <a href="scripts/SCRIPTS.md">Pipeline DAG</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Node](https://img.shields.io/badge/Node-22%2B-green)](https://nodejs.org)
[![Stars](https://img.shields.io/github/stars/sou350121/Pulsar-KenVersion?style=social)](https://github.com/sou350121/Pulsar-KenVersion/stargazers)

👋 Join the community

📡 <a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">GitHub Issues</a>

</div>

---

## Overview

### The Challenges of Domain Intelligence

Anyone tracking a fast-moving technical domain runs into the same six problems eventually:

- **Signal overload** — arXiv publishes 30+ VLA papers daily; without a rating mechanism it's pure noise, and reading everything is impossible
- **Opaque reasoning** — AI summaries tell you "this is important" without explaining why; you can't trust or reproduce the judgment
- **Knowledge doesn't accumulate** — papers you read today, community debates from last week — all lost in inboxes and message streams
- **Unreliable pipelines** — cron jobs fail silently with no alert; by the time you notice, a week of data is missing
- **Unverifiable judgments** — "AI trend predictions" have no historical accuracy record; there's no way to evaluate the source's credibility
- **Static assumptions** — domain beliefs never update as new evidence arrives, drifting further from reality over time

### How Pulsar Solves Them

Pulsar is a server-side domain intelligence pipeline. It doesn't read things for you — it **automates the question of what to read**: rating, filtering, reasoning, archiving, self-healing, and self-calibration, all running autonomously.

- **Rate first, cut noise before LLM cost → solves signal overload**: A four-tier rating engine (⚡/🔧/📖/❌) evaluates every signal before it reaches the LLM. 30 raw papers → 3–5 selected for deep analysis, saving 80%+ inference cost
- **Three-stage observable reasoning chain → transparent and reproducible**: `prep → agent → post`, each stage with defined I/O formats and intermediate artifacts written to disk; when something breaks, you see exactly which stage failed
- **Structured knowledge written to Git → knowledge accumulates permanently**: All outputs are Markdown pushed to GitHub via the Contents API; full commit history, full-text grep, no SaaS dependency
- **Watchdog self-healing → pipelines recover automatically**: 15 health checks, 7 failure categories handled automatically in DAG order, full run logs persisted to `memory/watchdog-log.json`
- **Biweekly predictions + ✅/❌ tracking → accountability on record**: Every reasoning report includes verifiable predictions; the next report must grade them; accuracy history is tracked, not assumed
- **Monthly hypothesis calibration → beliefs update with evidence**: 19 domain hypotheses each with confidence scores; monthly trigger-rate analysis conservatively updates confidence; declining hypotheses automatically receive more signal in the next cycle

---

## Quick Start

### Prerequisites

Before you begin, make sure your environment meets these requirements:

- **OS**: Linux (recommended), macOS
- **Python**: 3.9 or higher
- **Node.js**: 22 or higher
- **Moltbot**: [https://molt.bot](https://molt.bot) — handles cron scheduling and Telegram delivery
- **Network**: stable access to arXiv, GitHub API, and DashScope API

**Four keys required**:

| Key | Purpose | Where to get it |
|-----|---------|----------------|
| DashScope API Key | LLM calls (qwen3.5-plus) | [Alibaba Cloud Bailian](https://dashscope.aliyun.com) → API Keys |
| GitHub Token | Push knowledge to GitHub repos | GitHub Settings → Developer Settings → Tokens (repo write) |
| Telegram Bot Token | Send daily intelligence updates | Telegram → search @BotFather → /newbot |
| Telegram Chat ID | Target channel or user ID | Telegram → search @userinfobot, send any message |

---

### 1. Clone the Repository

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion ~/clawd
cd ~/clawd
```

> ⚠️ **Important**: Scripts are pre-configured for the `~/clawd/` directory. Cloning elsewhere requires updating hardcoded paths with:
> ```bash
> MYUSER=$(whoami)
> find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
> ```

---

### 2. Configure Your Keys

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=xxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
MOLTBOT_GATEWAY_PORT=18789
```

> 💡 **Tip**: Telegram Chat ID is a positive integer for users, negative for channels. For channels, add the Bot as an admin first.

👇 Expand for detailed configuration examples:

<details>
<summary><b>Example 1: DashScope (Alibaba Cloud)</b></summary>

All Pulsar LLM calls use DashScope with OpenAI-compatible SDK format.

1. Register at [https://dashscope.aliyun.com](https://dashscope.aliyun.com) and enable the service
2. Go to "API Keys" and create a new key
3. Recommended model: `qwen3.5-plus` (best quality/speed balance)

Once configured, all scripts will call through this endpoint:

```
https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

No code changes needed — the `DASHSCOPE_API_KEY` in `.env` takes effect automatically.

</details>

<details>
<summary><b>Example 2: Telegram Bot Setup</b></summary>

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

> 💡 **Tip**: Pulsar supports multiple TG accounts (VLA channel / AI Agent channel separately). See [AGENTS.md](AGENTS.md).

</details>

<details>
<summary><b>Example 3: GitHub Token Setup</b></summary>

Pulsar pushes daily outputs to your knowledge-base repos via the GitHub Contents API.

1. Go to GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Create a new token; under Repository access, select your target repos (VLA-Handbook / Agent-Playbook)
3. Set permission: `Contents: Read and Write`
4. Add the token to `GITHUB_TOKEN` in `.env`

Create the GitHub config files in `memory/` (these are not in the repo — create them from the template):

```bash
mkdir -p memory
cp config/github-config.template.json memory/github-config-vla-handbook.json
cp config/github-config.template.json memory/github-config-agent-playbook.json
```

Then edit each to point to your forks:

```json
{
  "repo": "your-username/VLA-Handbook",
  "api_base": "https://api.github.com",
  "token_env": "GITHUB_TOKEN",
  "branch": "main"
}
```

</details>

---

### 3. Start the Moltbot Gateway

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
# Check the port
ss -ltnp | grep 18789

# Check the gateway log
tail -n 20 /tmp/moltbot-gateway.log
```

Expected output:

```
Gateway running on ws://127.0.0.1:18789
```

---

### 4. Load Cron Jobs

The 33 scheduled jobs are stored in `config/jobs.template.json`. Load them by copying to the Moltbot cron directory **before** starting the gateway (or stop it first if already running):

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

You should see 33 scheduled jobs covering both the VLA and AI pipelines.

---

### 5. Run Your First Pipeline

Let's run a complete VLA signal collection example to experience Pulsar's core functionality.

#### Collect today's arXiv VLA papers

```bash
python3 scripts/vla-rss-collect.py
```

#### Expected output

```
(no output — silent on success by design)
```

Verify the collection worked:

```bash
# Check today's RSS file was created
ls ~/clawd/memory/vla-rss-*.json

# Inspect the top 3 recent papers
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
# Run the rating pipeline (auto-pushes to Telegram when complete)
moltbot cron run <vla-hotspots-job-id> --force --timeout 180000 --expect-final
```

> 📝 **Note**: First run takes 3–5 minutes for LLM inference. The gateway must be running.

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

Rating script: `scripts/rate-vla-daily.py`. Only ⚡ and 🔧 papers enter downstream LLM analysis; the rest are filtered out.

**Result**: 28 raw papers per day → average 4–6 enter reasoning → ~80% reduction in LLM cost.

---

### 2. Three-Stage Reasoning Chain

Every pipeline follows the same three-stage structure:

```
prep-*.py          →    run-*-two-phase.py    →    post-*.py
(structured collect)     (LLM reasoning)           (validation + output)
      ↓                        ↓                         ↓
candidates JSON          LLM output JSON           memory + GitHub + TG
```

All intermediate artifacts are written to `memory/tmp/` for debugging:

```bash
ls memory/tmp/
# vla-social-candidates-2026-XX-XX-*.json   ← prep stage output
# vla-social-llm-output-2026-XX-XX-*.json   ← agent stage output
```

If a pipeline fails mid-run, Watchdog detects the orphaned `llm-output` file and **resumes from the post stage** — skipping the expensive collection and LLM steps.

---

### 3. Knowledge Written to Git

All valuable outputs are pushed to public repos via the GitHub Contents API:

```
Output type                 →    Target path
VLA paper ratings           →    VLA-Handbook/theory/...
AI social intelligence      →    Agent-Playbook/memory/blog/archives/ai-social-intel/
AI daily picks              →    Agent-Playbook/memory/blog/archives/ai-daily-pick/
Biweekly reasoning reports  →    */reports/biweekly/
Biweekly reflection prompts →    */reports/biweekly/reflection_*.md
```

Push script: `scripts/gh-contents-upload.py` (handles create/update, auto-resolves SHA).

**Benefits**:
- Full-text grep across all historical outputs (`git log -S "flow matching"`)
- Permanent archive, zero SaaS dependency
- Fork either knowledge repo and build your own domain knowledge graph

---

### 4. Watchdog Self-Healing

`scripts/daily-watchdog.py` runs daily at 10:15 Shanghai time and checks 15 health signals:

| Check | Pass condition | Self-healing action |
|-------|---------------|---------------------|
| `vla_rss` | Today's RSS collected | Trigger `vla-rss-collect.py` |
| `vla_hotspots` | Today's hotspots updated | Trigger hotspots cron job |
| `vla_social` | Today's social intel has signals | Trigger social pipeline |
| `vla_release` | Release tracker checked today | Trigger release tracker |
| `vla_rating` | Rating completed within 10h | Warn (no auto-heal) |
| `aiapp_social` | Today's AI social intel > 0 signals | Trigger social pipeline |
| `ai_daily_pick` | Today's picks generated | Warn |
| `disk_space` | Disk usage < 85% | Warn; > 95% → error |
| ... | ... | ... |

Self-healing follows DAG order (rss → daily → social) to avoid consuming data that hasn't been collected yet.

Run log: `memory/watchdog-log.json` (retains 60 entries; killed runs and recoveries both recorded).

---

### 5. Biweekly Prediction ✅/❌ Loop

Every two weeks, Pulsar generates a reasoning report containing verifiable predictions:

```markdown
### Predictions (2026-XX-XX to 2026-XX-XX)
1. ⏳ Flow matching will surpass diffusion policy as the dominant VLA policy-learning approach
   — Verification: ⚡-rated papers with flow matching > 50%
2. ⏳ A third-party community plugin will appear for the Unitree G1 SDK
   — Verification: findable repo on GitHub search
```

The next report reviews those predictions:

```markdown
### Previous Predictions Review
1. ✅ Confirmed — 4/5 ⚡ papers this period used flow matching (GenPlanner, SafeFlowMatcher...)
2. ❌ Not confirmed — no third-party plugin found; G1 community still centered on official SDK
```

This makes the system's judgment accuracy traceable and measurable, not just claimed.

---

### 6. Monthly Hypothesis Calibration

The system maintains `memory/assumptions.json` — 19 domain hypotheses, each with a confidence score (0–1):

```json
{
  "id": "V-001",
  "text": "Flow matching is replacing diffusion policy as the dominant VLA strategy-learning paradigm",
  "confidence": 0.72,
  "last_updated": "2026-02-01"
}
```

On the 28th of each month, `monthly-calibration-agg.py` automatically:
1. Computes 30-day trigger rates for each hypothesis
2. Conservatively updates confidence scores (max ±0.08/month)
3. Writes hypotheses with declining confidence to `watch-list.json`

The watch-list feeds back into `prep-calibration-check.py`, which injects extra signals for watched hypotheses on the next daily check — **the system proactively investigates its own blind spots** without human intervention.

---

## Project Architecture

```
Pulsar-KenVersion/
├── scripts/                    # 55 pipeline scripts
│   ├── prep-*.py               # Data collection layer (RSS, web search, GitHub API)
│   ├── run-*-two-phase.py      # Two-phase execution layer (prep + LLM agent)
│   ├── post-*.py               # Post-processing layer (validate + memory + GitHub + TG)
│   ├── daily-watchdog.py       # Health monitoring + self-healing (15 checks)
│   ├── memory-janitor.py       # Periodic cleanup of expired files
│   ├── memory-upsert.py        # Generic append-write tool for memory files
│   ├── gh-contents-upload.py   # GitHub Contents API push
│   ├── _vla_expert.py          # Shared module for VLA pipeline
│   └── SCRIPTS.md              # Full pipeline DAG documentation
│
├── config/
│   ├── active-config.template.json  # Research directions + keyword tracking config
│   ├── assumptions.template.json    # 19 domain hypotheses template
│   ├── github-config.template.json  # GitHub push target template
│   └── jobs.template.json           # 33 cron job configurations
│
├── memory/                     # Local knowledge store (.gitignored, auto-created)
│   ├── vla-daily-hotspots.json # VLA daily hotspot papers
│   ├── vla-social-intel.json   # VLA social intelligence (90-day rolling)
│   ├── ai-app-social-intel.json# AI app social intelligence (90-day rolling)
│   ├── assumptions.json        # 19 domain hypotheses + confidence scores
│   ├── watchdog-log.json       # Watchdog run history
│   ├── tmp/                    # Pipeline intermediates (auto-cleaned after 60 days)
│   └── github-config-*.json    # GitHub push targets (create from config template)
│
├── docs/
│   └── banner.svg              # Project banner
│
├── AGENTS.md                   # Full deployment guide (AI agent-readable)
├── .env.example                # Key template (copy to .env and fill in)
└── LICENSE                     # MIT
```

---

## How Pulsar Compares

Each tool has a genuine sweet spot — here's an honest breakdown:

**Pick Feedly AI** if you want zero setup, polished mobile UX, 1M+ curated sources, and team collaboration — it's a mature product that just works.  
**Pick ResearchRabbit** if you're doing academic literature reviews — visual citation graphs and 270M+ papers are genuinely hard to beat for systematic discovery.  
**Pick MineContext** if you want to capture *your own* reading context — local-first, private, no domain definition needed upfront.  
**Pick Pulsar** if you need a server-side pipeline that runs autonomously, generates structured knowledge assets, self-heals on failure, and self-calibrates monthly.

| Dimension | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|-----------|-----------|---------------|-------------|------------|
| **Best at** | Team intel feeds, mobile | Academic citation mapping | Personal context capture | Autonomous domain pipeline |
| **Hosting** | ☁️ SaaS only | ☁️ SaaS only | ✅ Local / OSS | ✅ Self-hosted / OSS |
| **Cost** | \$1,600–3,200 / month | Closed pricing | Free | Free |
| **Setup effort** | ✅ Zero | ✅ Zero | ✅ Desktop install | ⚠️ ~1 hour |
| **Signal rating** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ before LLM |
| **Reasoning transparency** | ❌ Black-box summaries | ❌ | ❌ | ✅ 3-stage observable chain |
| **Self-healing** | ❌ | ❌ | ❌ | ✅ 7 auto-recovery paths |
| **Belief calibration** | ❌ | ❌ | ❌ | ✅ 19 hypotheses, monthly |
| **Prediction tracking** | ❌ | ❌ | ❌ | ✅ ✅/❌ every 2 weeks |
| **Knowledge output** | Feed / inbox | Graph visualization | Local summaries | Structured Markdown → Git |
| **RAM footprint** | N/A (cloud) | N/A (cloud) | Desktop app | **2 GB VPS** |

---

## Biomimetic Architecture

Pulsar's internal layers follow a cognitive organism model, not a traditional data pipeline:

| Layer | Biological analog | Pulsar component |
|-------|------------------|-----------------|
| **Perception** | Sensory organs | arXiv RSS · GitHub releases · community feeds |
| **Filtering** | Thalamic gate | Rating engine (⚡/🔧/📖/❌) — noise cut before LLM |
| **Reasoning** | Cortical processing | Three-stage LLM: prep → agent → post |
| **Memory** | Hippocampal encoding | Structured Markdown → GitHub |
| **Metacognition** | Prefrontal reflection | Biweekly prediction reviews · monthly calibration |
| **Immune system** | Autoimmune response | Watchdog: 15 health checks, 7 self-healing paths |

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Scheduled jobs | **33** fully automated cron jobs |
| Pipeline scripts | **55** across two research domains |
| Tracked hypotheses | **19** with monthly confidence auto-updates |
| Watchdog checks | **15** health signals, **7** auto-recovery paths |
| End-to-end latency | **< 2 hours**: RSS → rated papers → TG notification |
| Knowledge retention | Social intel / hotspots **90-day** rolling · reports permanent in Git |
| Hardware requirement | **2 GB RAM** — minimal VPS |

---

## Output Repositories

Pulsar pushes content to two public repos every day:

| Repo | Domain | What's inside |
|------|--------|--------------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Robotics · VLA research | Daily paper ratings · theory deep dives · biweekly forecasts · VLA social intel |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI apps · agent tools | Tool index · framework analyses · AI social intel · daily picks |

Fork either repo and deploy Pulsar to get a complete, self-updating domain knowledge system.

---

## Further Reading

| Document | Contents |
|----------|---------|
| [AGENTS.md](AGENTS.md) | Full deployment guide: key config · path reference · troubleshooting |
| [scripts/SCRIPTS.md](scripts/SCRIPTS.md) | Full DAG of all 55 scripts · I/O for each script |
| [VLA-Handbook/scripts/](https://github.com/sou350121/VLA-Handbook/tree/main/scripts) | Example pipeline outputs for VLA |
| [Agent-Playbook/reports/biweekly/](https://github.com/sou350121/Agent-Playbook/tree/main/reports/biweekly) | Biweekly reasoning report archive (with prediction reviews) |

---

## Community & Contributing

Have a question, idea, or want to fork this into your own domain's Pulsar?

- 💬 **File an issue**: [GitHub Issues](https://github.com/sou350121/Pulsar-KenVersion/issues)
- 🔀 **Pull requests**: improvements to pipelines, new domain support, and bug fixes are welcome
- 📡 **See the outputs**: [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) · [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)

---

*MIT License — fork it, adapt it, make it your own domain's Pulsar.*

