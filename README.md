<div align="center">

<picture>
  <img alt="Pulsar · 照見" src="docs/banner.svg" width="100%" height="auto">
</picture>

### Pulsar · 照見: Automated Domain Intelligence Pipeline

[English](#) · [中文](README_CN.md)

<a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">Issues</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Moltbot](https://img.shields.io/badge/Powered%20by-Moltbot-purple)](https://molt.bot)
[![Pipeline](https://img.shields.io/badge/Pipeline-33%20cron%20jobs-green)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

</div>

---

## Overview

### The Problem with "Context Capture"

Tools like [MineContext](https://github.com/volcengine/MineContext) do one thing well: they capture *your personal activity* (screen, documents) and surface it back to your AI sessions. That solves personal memory.

But if you're a researcher or engineer tracking a fast-moving domain — VLA robotics, AI Agent ecosystems — the real problem is different:

- **Domain signals are too scattered**: arXiv, GitHub releases, community debates, social media, benchmark updates — no single feed covers it all.
- **Raw feeds are noise**: 30 papers a day, 90% irrelevant. You need filtering, rating, and interpretation — not just aggregation.
- **Context capture ≠ knowledge asset**: Screenshots of what you read don't become structured, searchable, citable knowledge.
- **No epistemic feedback loop**: You read a trend, form a belief, move on. There's no system to track whether you were right.

### The Pulsar Solution

**Pulsar (照见)** is a server-side domain intelligence pipeline. Instead of capturing what you do, it monitors a domain 24/7, runs LLM-powered analysis on schedule, and writes structured knowledge assets to GitHub and Telegram — automatically.

- **Signal Rating Before Processing** → **Cuts noise to signal**: Every paper rated ⚡/🔧/📖/❌ before entering the deep pipeline. Only strategic items get LLM analysis.
- **Staged LLM Architecture** → **Depth without hallucination**: `prep → agent → post` three-stage design separates collection, generation, and deterministic output.
- **Scheduled Intelligence** → **Knowledge compounds over time**: 33 cron jobs write to two structured GitHub repos daily. Content accumulates and cross-references.
- **Self-Healing Watchdog** → **No silent failures**: `daily-watchdog.py` monitors 15 pipeline health signals and auto-triggers recovery for RSS failures, LLM timeouts, and orphaned phases.
- **Epistemic Calibration Loop** → **Beliefs are testable**: Biweekly reports make explicit predictions. The next report grades them ✅/❌/⏳. Monthly aggregation updates confidence scores across 19 tracked assumptions.

---

## 🆚 How Pulsar Differs

### vs MineContext

| Dimension | MineContext | Pulsar |
|---|---|---|
| **What it monitors** | Your personal activity (screen, docs) | A domain (VLA research + AI App ecosystem) |
| **Who drives it** | You — it captures what you do | Autonomous — runs on schedule, no human trigger |
| **Output** | Context surfaced to your AI sessions | Structured knowledge assets (GitHub repos + Telegram) |
| **Architecture** | Desktop app (Mac/Windows) | Server-side pipeline (33 cron jobs) |
| **Depth** | Capture → store → retrieve | Collect → rate → LLM analyze → write → calibrate |
| **Epistemic layer** | None | Biweekly predictions + monthly back-testing |
| **Use case** | "What did I read last week?" | "What happened in this domain, and is my model still right?" |

> MineContext answers: *"What was my context?"*  
> Pulsar answers: *"What is happening in this domain, and is my mental model still accurate?"*

---

## 🏗 Architecture

```
                    ┌─────────────────────────────────────┐
                    │           PULSAR PIPELINE            │
                    └─────────────────────────────────────┘

SIGNAL LAYER              PROCESSING LAYER           OUTPUT LAYER
────────────              ────────────────           ────────────
arXiv RSS                 rate-vla-daily.py          → Telegram
GitHub releases  ──────►  ⚡/🔧/📖/❌ rating ──────►  daily hotspots
Community feeds           prep → agent → post         social intel
Social / web              two-phase LLM runner        weekly digest

AI App RSS                prep-ai-*.py               → GitHub
Tool releases    ──────►  run-ai-*-two-phase ──────►  VLA-Handbook
Community debates         post-ai-*.py                Agent-Playbook
"I built X" posts         expert curation             app_index.md

                          ─────────────────
                          SYSTEM LAYER
                          daily-watchdog.py      15 checks · self-healing
                          prep-calibration.py    daily assumption scan
                          monthly-calibration    confidence updates
```

### Pipeline Schedule (Shanghai time)

| Time | Job |
|---|---|
| 06:45 | AI RSS collect |
| 07:00 | AI 日报 → `cognition/app_index.md` |
| 07:15 | AI 每日精选 (web search + editorial tiers) |
| 07:45 | AI 社交情报 (opinion / debate / viral) |
| 09:xx | VLA RSS → rate → hotspots → Telegram |
| 10:xx | VLA SOTA / Release / 社交情报 |
| 11:00 | Calibration check (19 assumptions) |
| 15:30 Tue/Thu/Sat | AI Deep Dive → `cognition/frameworks/` |
| 15:45 Mon/Wed/Fri/Sun | AI 工作流灵感 |
| Sun 10:30 | Weekly quality review + 风向洞察 |
| Monthly 28th | Monthly calibration aggregation |

---

## 🚀 Quick Start

### Prerequisites

- Node 22+ and [Moltbot](https://molt.bot) (`npm i -g moltbot@latest`)
- Python 3.9+
- DashScope API key (Alibaba Cloud — Qwen models)
- GitHub token (write access to your output repos)
- Telegram bot token

### 1. Clone and configure

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion.git
cd Pulsar-KenVersion
cp .env.example .env
# Fill in your API keys
```

### 2. Start the Moltbot gateway

```bash
moltbot config set gateway.mode=local
moltbot channels connect telegram
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot channels status --probe
```

### 3. Deploy scripts and config

```bash
mkdir -p ~/clawd/scripts ~/clawd/memory/tmp
cp scripts/* ~/clawd/scripts/
cp config/github-config.template.json ~/clawd/memory/github-config.json
# Edit github-config.json: fill in your token and target repos
```

### 4. Import cron jobs

```bash
# Edit config/jobs.template.json:
# - Replace YOUR_TELEGRAM_CHAT_ID
# - Adjust schedules if needed
moltbot cron import config/jobs.template.json
moltbot cron list   # verify 33 jobs
```

### 5. Verify end-to-end

```bash
moltbot cron run <job-id> --force --timeout 180000 --expect-final
tail -f /tmp/moltbot-gateway.log
```

---

## 📂 Repository Structure

```
Pulsar-KenVersion/
├── scripts/                  # 55 pipeline scripts
│   ├── vla-rss-collect.py
│   ├── rate-vla-daily.py     # ⚡/🔧/📖/❌ paper rating
│   ├── run-*-two-phase.py    # LLM agent runners
│   ├── daily-watchdog.py     # Self-healing monitor (v6, 15 checks)
│   ├── prep-calibration-check.py
│   └── SCRIPTS.md            # Full DAG + naming conventions
├── config/
│   ├── jobs.template.json    # 33 cron jobs (sanitized)
│   ├── active-config.template.json
│   ├── assumptions.template.json
│   └── github-config.template.json
├── .env.example
└── docs/
    └── banner.svg
```

---

## 📤 Output Repositories

| Repo | What Pulsar writes | Cadence |
|---|---|---|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Paper deep dives, weekly/biweekly reports, SOTA tracker | Daily + weekly |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | Tool index, Deep Dives, biweekly reports, social intel | Daily + biweekly |

---

## 🤝 Contributing

PRs welcome — new signal sources, LLM pipeline stages, or output adapters.

## 📄 License

MIT
