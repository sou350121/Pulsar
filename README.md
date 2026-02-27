# Pulsar · 照见: Automated Domain Intelligence Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Lang](https://img.shields.io/badge/README-中文-red)](README_CN.md)

Pulsar is a server-side domain intelligence pipeline that continuously monitors AI/VLA research ecosystems, distills raw signals into structured knowledge assets through multi-stage LLM processing, and improves its own judgment accuracy through monthly calibration.

Open-sourced in 2026 by the 照见 (Pulsar) system.

---

## Core Problems It Solves

Engineers building or maintaining domain intelligence systems face six recurring problems:

1. **Signal overload** — arXiv publishes 30+ VLA papers daily; without a rating mechanism it's pure noise, and reading everything is impossible
2. **Opaque reasoning** — AI summaries tell you "this is important" without explaining why; you can't trust or reproduce the judgment
3. **Knowledge doesn't accumulate** — papers read today, community debates from last week — all lost in inboxes and message streams
4. **Unreliable pipelines** — cron jobs fail silently with no alert; by the time you notice, a week of data is missing
5. **Unverifiable judgments** — "AI trend predictions" have no historical accuracy record; there's no way to evaluate the source's credibility
6. **Static assumptions** — domain beliefs never update as new evidence arrives, drifting further from reality over time

---

## Six Core Mechanisms

**1. Rate first — cut noise before LLM cost**  
A four-tier rating engine (⚡/🔧/📖/❌) evaluates every paper before it enters LLM reasoning. 30 raw inputs → 3–5 selected for deep analysis, saving 80%+ inference cost. Rating criteria: topic relevance × institution weight × engineering applicability.

**2. Three-stage observable reasoning chain**  
`prep (structured collection) → agent (LLM reasoning) → post (semantic validation + structured output)`. Each stage has defined I/O formats and intermediate artifacts written to disk. When something breaks, you see exactly which stage failed.

**3. Structured knowledge written to Git**  
All outputs are Markdown, pushed to public repositories ([VLA-Handbook](https://github.com/sou350121/VLA-Handbook) / [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)) via the GitHub Contents API. Full commit history, full-text grep-able, no SaaS dependency.

**4. Watchdog self-healing system**  
`daily-watchdog.py` monitors 15 health signals. On failure, it auto-triggers re-runs in DAG order (rss → daily → social), covering 7 failure categories without human intervention. Run logs are persisted to `memory/watchdog-log.json` — kills, recoveries, and backfills all recorded.

**5. Biweekly predictions with ✅/❌ accountability**  
Every biweekly reasoning report includes verifiable predictions. The next report must grade them: ✅ confirmed / ❌ wrong / ⏳ pending. Accuracy history is on record. Source credibility is measured, not assumed.

**6. Monthly hypothesis calibration**  
The system maintains 19 domain hypotheses, each with a confidence score (0–1). Monthly, it computes 30-day trigger rates and conservatively updates confidence (max ±0.08/month). Hypotheses with declining confidence enter a watch-list — the system automatically injects more signal to investigate them in the next cycle.

---

## How Pulsar Compares

Each tool has a real sweet spot. Here's an honest breakdown:

**Pick Feedly AI** if you want zero setup, a polished mobile experience, team collaboration, and 1M+ curated sources — it's a mature product that just works.  
**Pick ResearchRabbit** if you're doing academic literature reviews — visual citation graphs and 270M+ papers are genuinely hard to beat for systematic discovery.  
**Pick MineContext** if you want to capture *your own* reading and work context — local-first, private, no domain definition needed upfront.  
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

| Layer | Biological Analog | Pulsar Component |
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
| Hardware requirement | **2 GB RAM** — minimal VPS |

---

## Quick Start

**Requirements**: Node 22+ · Python 3.9+ · [Moltbot](https://molt.bot) · DashScope API Key · GitHub Token · Telegram Bot Token

\`\`\`bash
git clone https://github.com/sou350121/Pulsar-KenVersion
cp config/.env.example .env          # fill in your keys
moltbot gateway run --bind loopback --port 18789 --force
moltbot cron import config/jobs.template.json
python3 scripts/vla-rss-collect.py   # test one pipeline
\`\`\`

Full setup: [AGENTS.md](AGENTS.md)

---

## Output Repositories

| Repo | Domain | What It Contains |
|------|--------|-----------------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Robotics · VLA research | Daily ratings · theory deep dives · biweekly forecasts |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI apps · agent tools | Tool index · framework analyses · community signals |

---

*MIT License — fork, adapt, make it your own domain's Pulsar.*
