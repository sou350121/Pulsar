<div align="center">

# ✦ Pulsar · 照見

### Automated Domain Intelligence Pipeline for AI/VLA Research

[English](#) · [快速开始](#-quick-start) · [架构](#-architecture) · [与同类工具的区别](#-how-pulsar-differs)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Moltbot](https://img.shields.io/badge/Powered%20by-Moltbot-purple)](https://molt.bot)
[![Auto-updated](https://img.shields.io/badge/Pipeline-33%20cron%20jobs-green)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

</div>

---

## 📌 Overview

### The Problem with "Context Capture"

Tools like [MineContext](https://github.com/volcengine/MineContext) do one thing well: they capture *your personal activity* (screen, documents) and surface it back to *your* AI sessions. That solves personal memory.

But if you're a researcher or engineer tracking a fast-moving domain — VLA robotics, AI Agent ecosystems — the real problem is different:

- **Domain signals are too scattered**: arXiv, GitHub releases, community debates, social media, benchmark updates — no single feed covers it all.
- **Raw RSS is noise**: 30 papers a day, 90% irrelevant. You need filtering, rating, and interpretation, not just aggregation.
- **Context capture ≠ knowledge asset**: Screenshots of what you read don't become structured, searchable, citable knowledge.
- **No epistemic feedback loop**: You read a trend, form a belief, move on. There's no system to track whether you were right.

### The Pulsar Solution

**Pulsar (照见)** is a server-side domain intelligence pipeline. Instead of capturing what you do, it monitors a domain 24/7, runs LLM-powered analysis on schedule, and writes structured knowledge assets to GitHub and Telegram — automatically.

- **Signal Extraction** → **Cuts noise to signal**: Rates every paper ⚡/🔧/📖/❌ before processing; only strategic items enter the deep pipeline.
- **Staged LLM Processing** → **Depth without hallucination**: `prep → agent → post` three-stage architecture separates collection, generation, and deterministic output.
- **Scheduled Intelligence** → **Knowledge accumulates over time**: 33 cron jobs write to two structured GitHub repos daily. Content compounds.
- **Self-Healing Watchdog** → **No silent failures**: `daily-watchdog.py` checks 15 pipeline health signals, auto-triggers recovery for RSS failures and LLM timeouts.
- **Epistemic Calibration Loop** → **Beliefs are testable**: Biweekly reports include explicit predictions. The next report grades them ✅/❌/⏳. Monthly calibration updates confidence scores.

---

## 🆚 How Pulsar Differs

### vs MineContext

| Dimension | MineContext | Pulsar |
|---|---|---|
| **What it monitors** | Your personal activity (screen, docs) | A domain (VLA research + AI App ecosystem) |
| **Who drives it** | You — it captures what you do | Autonomous — runs on schedule, no human trigger |
| **Output** | Context surfaced back to your AI sessions | Structured knowledge assets (GitHub repos + Telegram) |
| **Architecture** | Desktop app (Mac/Windows) | Server-side pipeline (33 cron jobs) |
| **Depth** | Capture → store → retrieve | Collect → rate → LLM analyze → write → calibrate |
| **Epistemic layer** | None | Biweekly predictions + monthly back-testing |
| **Use case** | "What did I read last week?" | "What happened in VLA this week, and what does it mean?" |

> MineContext answers: *"What was my context?"*  
> Pulsar answers: *"What is happening in this domain, and is my mental model still accurate?"*

---

## 🏗 Architecture

```
                          ┌─────────────────────────────────┐
                          │         PULSAR PIPELINE          │
                          └─────────────────────────────────┘

  SIGNAL LAYER                PROCESSING LAYER              OUTPUT LAYER
  ─────────────               ─────────────────             ────────────
  arXiv RSS                   rate-vla-daily.py             → Telegram
  GitHub releases    ──────►  ⚡/🔧/📖/❌ rating   ──────►  (daily hotspots
  Community feeds             prep → agent → post            social intel
  Social media                two-phase LLM runner           weekly digest)
  Web search                  
                              ─────────────────             ────────────
  AI App RSS                  prep-ai-*.py                  → GitHub
  Tool releases      ──────►  run-ai-*-two-phase.py ──────►  (VLA-Handbook
  Community debates           post-ai-*.py                   Agent-Playbook
  "I built X" posts           expert curation                app_index.md
                                                             deep dives)
                              ─────────────────
                              SYSTEM LAYER
                              daily-watchdog.py     (15 health checks, self-healing)
                              prep-calibration.py   (daily assumption scan)
                              monthly-calibration-agg.py  (confidence updates)
```

### Pipeline Cadence

| Time (Shanghai) | Job |
|---|---|
| 06:45 | AI RSS collect |
| 07:00 | AI 日报 → `cognition/app_index.md` |
| 07:15 | AI 每日精选 (web search + editorial tiers) |
| 07:45 | AI 社交情报 (opinion / debate / viral) |
| 09:xx | VLA RSS → rate (⚡/🔧/📖/❌) → hotspots → TG |
| 10:xx | VLA SOTA / Release / 社交情报 |
| 11:00 | Calibration check (19 assumptions) |
| 15:30 Tue/Thu/Sat | AI Deep Dive → `cognition/frameworks/` |
| 15:45 Mon/Wed/Fri/Sun | AI 工作流灵感 |
| Weekly Sun 10:30 | Weekly quality review + 风向洞察 |
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
moltbot channels connect telegram   # enter your bot token when prompted
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot channels status --probe     # verify
```

### 3. Deploy scripts

```bash
mkdir -p ~/clawd/scripts ~/clawd/memory/tmp
cp scripts/* ~/clawd/scripts/
```

### 4. Configure GitHub output targets

```bash
cp config/github-config.template.json ~/clawd/memory/github-config.json
# Edit: fill in your GitHub token and target repo names
```

### 5. Import cron jobs

```bash
# Edit config/jobs.template.json:
# - Replace YOUR_TELEGRAM_CHAT_ID with your chat ID
# - Adjust schedule timezones if needed
moltbot cron import config/jobs.template.json
moltbot cron list   # verify 33 jobs imported
```

### 6. Verify

```bash
# Force-run a single job to test end-to-end
moltbot cron run <job-id> --force --timeout 180000 --expect-final
tail -f /tmp/moltbot-gateway.log
```

---

## 📂 Repository Structure

```
Pulsar-KenVersion/
├── scripts/                  # 55 pipeline scripts
│   ├── vla-rss-collect.py    # VLA paper RSS ingestion
│   ├── rate-vla-daily.py     # ⚡/🔧/📖/❌ paper rating
│   ├── run-*-two-phase.py    # LLM agent runners
│   ├── daily-watchdog.py     # Self-healing system monitor
│   ├── prep-calibration-check.py
│   └── SCRIPTS.md            # Full DAG reference
├── config/
│   ├── jobs.template.json    # 33 cron jobs (sanitized)
│   ├── active-config.template.json
│   ├── assumptions.template.json
│   └── github-config.template.json
├── .env.example
└── README.md
```

See [`scripts/SCRIPTS.md`](./scripts/SCRIPTS.md) for the complete pipeline DAG and naming conventions.

---

## 📤 Output Repositories

Pulsar writes into two structured knowledge repos:

| Repo | What Pulsar writes | Cadence |
|---|---|---|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | Paper deep dives, weekly reports, biweekly reports, SOTA tracker | Daily + weekly |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | Tool index (`app_index.md`), Deep Dives, biweekly reports, social intel | Daily + biweekly |

---

## 🤝 Contributing

PRs welcome — especially for new signal sources, additional LLM pipeline stages, or output adapters for other platforms.

## 📄 License

MIT
