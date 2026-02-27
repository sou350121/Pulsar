# Pulsar · 照見

**A self-evolving domain intelligence organism.**  
Not a scraper. Not a news aggregator. A system that watches, rates, reasons — and gets sharper every month.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Lang](https://img.shields.io/badge/README-中文-red)](README_CN.md)

---

## The Core Idea

Most monitoring tools collect. Pulsar *evolves*.

Every two weeks, it reviews its own predictions — grading each ✅ verified, ❌ wrong, ⏳ pending.  
Every month, it recalibrates 19 tracked hypotheses based on what actually happened.  
Underperforming assumptions get flagged, watch-listed, and injected with extra signal next cycle.  

**The system knows what it doesn't know — and corrects itself.**

---

## Biomimetic Architecture

Pulsar is modeled on a cognitive organism, not a data pipeline:

| Layer | Biological Analog | Pulsar Component |
|-------|------------------|-----------------|
| **Perception** | Sensory organs | arXiv RSS · GitHub releases · community feeds |
| **Filtering** | Thalamic gate | Rating engine (⚡/🔧/📖/❌) — cuts noise before LLM cost |
| **Reasoning** | Cortical processing | Three-stage LLM: `prep → agent → post` |
| **Memory** | Hippocampal encoding | Structured Markdown → GitHub (VLA-Handbook · Agent-Playbook) |
| **Metacognition** | Prefrontal reflection | Biweekly prediction reviews · monthly calibration |
| **Immune system** | Autoimmune response | Watchdog: 15 health checks, 7 self-healing recovery paths |

---

## The Evolution Loop

```
Signal intake ─► Rating ─► LLM reasoning ─► Knowledge output
                                                    │
                                          Biweekly predictions
                                          (✅/❌/⏳ grading)
                                                    │
                                          Monthly calibration
                                          19 hypotheses updated
                                                    │
                                          Watch-list: struggling
                                          assumptions boosted
                                                    │
                                          ──────────┘ (feeds back into signal intake)
```

The system doesn't just run — it learns which of its own beliefs need more evidence, then hunts for it.

---

## Standout Numbers

| Metric | Value |
|--------|-------|
| Scheduled jobs | **33** fully automated cron jobs |
| Pipeline scripts | **55** across two research domains |
| Tracked hypotheses | **19** with monthly confidence auto-updates |
| Watchdog checks | **15** health signals, **7** auto-recovery paths |
| End-to-end latency | **< 2 hours**: arXiv RSS → rated papers → TG notification |
| Hardware requirement | **2 GB RAM** — runs on a minimal VPS |
| Output repositories | **2** GitHub repos, daily commits, full history |

---

## How Pulsar Compares

| Dimension | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|-----------|-----------|---------------|-------------|------------|
| **Purpose** | Market/threat intel feeds | Paper citation discovery | Personal desktop context | Domain intelligence pipeline |
| **Hosting** | ☁️ SaaS only | ☁️ SaaS only | ✅ Local / OSS | ✅ Self-hosted / OSS |
| **Cost** | $1,600–3,200 / month | Closed pricing | Free | Free |
| **Signal rating** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ before LLM |
| **LLM reasoning** | ⚠️ Summaries only | ❌ | ⚠️ Single-pass | ✅ 3-stage pipeline |
| **Self-healing** | ❌ | ❌ | ❌ | ✅ 7 auto-recovery paths |
| **Belief calibration** | ❌ | ❌ | ❌ | ✅ 19 hypotheses, monthly |
| **Prediction tracking** | ❌ | ❌ | ❌ | ✅ ✅/❌ every 2 weeks |
| **Knowledge output** | Feed / inbox | Graph view | Local summaries | Structured Markdown → Git |
| **RAM footprint** | N/A (cloud) | N/A (cloud) | Desktop app | **2 GB VPS** |

> Feedly AI costs more per month than most engineers earn in a week — and still can't tell you if its own assessments were right.

---

## Pipeline Overview

```
arXiv RSS ──────────────────►┐
GitHub releases ─────────────►│  Rating (⚡/🔧/📖/❌)
Community discussions ────────►│       │
Social signals ──────────────►┘       │
                                       ▼
                              Three-stage LLM pipeline
                              (prep → agent → post)
                                       │
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                   ▼
             Daily hotspots    Theory deep dives    Calibration check
                    │                  │                   │
                    └──────────────────┴───────────────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                         VLA-Handbook    Agent-Playbook
                         Telegram channels (2 domains)
```

---

## Quick Start

**Requirements**: Node 22+ · Python 3.9+ · [Moltbot](https://molt.bot) · DashScope API Key · GitHub Token · Telegram Bot Token

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion
cp config/.env.example .env          # fill in your keys
moltbot gateway run --bind loopback --port 18789 --force
moltbot cron import config/jobs.template.json
python3 scripts/vla-rss-collect.py   # test one pipeline
```

Full setup: [AGENTS.md](AGENTS.md)

---

## Output Repositories

| Repo | Domain | What It Contains |
|------|--------|-----------------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Robotics · VLA research | Daily ratings · theory deep dives · biweekly forecasts |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI apps · agent tools | Tool index · framework analyses · community signals |

---

*MIT License — fork, adapt, make it your own domain's Pulsar.*
