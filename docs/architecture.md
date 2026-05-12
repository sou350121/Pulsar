# Pulsar Architecture

A bird's-eye view of how raw signals become structured knowledge — and how the system audits itself.

> **Design principle**: mechanical guardrails fire first; LLM judgement only sees a pre-cleaned candidate set. Every layer below LLM is deterministic and reproducible.

---

## 4-Layer Model

```
┌─────────────────────────────────────────────────────────────────┐
│  L1 · INPUT — multi-source collection + mechanical filtering    │
│                                                                 │
│   RSS / arXiv / Tophub / GitHub-issues / community feeds        │
│        ↓                                                        │
│   Per-source dedup → keyword A/B filter → 3-pass content dedup  │
│        ↓                                                        │
│   ≤220 candidates/day (hard cap)                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  L2 · PROCESSING — staged LLM reasoning                         │
│                                                                 │
│   Rating engine (⚡/🔧/📖/❌, rule-based)                          │
│        ↓                                                        │
│   prep → agent (LLM) → post  (3-stage observable chain)         │
│        ↓                                                        │
│   Devil's-advocate counterargument pass                         │
│        ↓                                                        │
│   Atomic write to memory/                                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  L3 · OUTPUT — knowledge delivery + indexing                    │
│                                                                 │
│   Telegram (per-domain routing)                                 │
│   GitHub Contents API (append-only)                             │
│   MCP server (12 read-only tools)                               │
│   Semantic index (DashScope text-embedding-v3, 60-day window)   │
└─────────────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────────────┐
│  L4 · QUALITY — self-checks + closed correction loop            │
│                                                                 │
│   Watchdog (16 checks, DAG-ordered self-healing)                │
│   Drift detector (7-day rolling baseline + quality plateau)     │
│   Field-state trigger (6 trigger types, zero-LLM gate)          │
│   Cross-domain engine v2 (7 built-in rules, R001-R007)          │
│   Calibration loop v4 (assumptions × confidence, monthly)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Input

### Why mechanical filtering before LLM

Cost and signal-to-noise. Dozens-to-hundreds of raw items per day; sending all of them to a language model is wasteful and amplifies low-quality signals. Pulsar enforces three filtering passes before any LLM sees text:

1. **Per-source dedup** — strip near-identical entries (same title, same canonical URL).
2. **Keyword A/B filter** — A-list keywords (domain-defining) gain priority, B-list (peripheral) drop unless co-occurring with A.
3. **Content dedup (3-pass)** — Jaccard similarity at the **0.50** threshold to remove rephrasings of the same paper / press release. The same metric at the **0.40** threshold separately flags follow-up content (used for connecting story arcs across days, not as a filter).

The output is capped at **≤220 candidates/day**.

### Two related dedup thresholds — do not confuse them

| Threshold | Purpose | Where |
|-----------|---------|-------|
| **Jaccard ≥ 0.50** | Remove duplicates (today's collection vs. recent items) | Layer-1 content dedup |
| **Jaccard ≥ 0.40** | Mark a story as a follow-up of a prior story | Topic fingerprinting (downstream of L1) |

The 0.40 threshold is intentionally looser — follow-ups should fire even when the new article shifts framing. Filtering at 0.40 would over-collapse the corpus.

---

## Layer 2 — Processing

### Rating Engine

Four-tier rule-based scoring (`⚡` / `🔧` / `📖` / `❌`). Conditions are defined in `memory/active-config.json` — keywords, institution tags, relevance rules. **No LLM involved.** Only `⚡` and `🔧` items advance to the LLM chain.

### Three-stage chain

Every reasoning pipeline follows the same prep → agent → post structure:

```
prep-*.py          →    run-*-two-phase.py    →    post-*.py
(structured collect)     (LLM reasoning)           (validate + memory + GitHub + TG)
      ↓                        ↓                         ↓
candidates JSON          llm-output JSON           memory + GitHub + TG
```

Intermediate artifacts in `memory/tmp/` make failures debuggable. Watchdog can resume from `post` if a downstream step crashed.

### Devil's Advocate pass

After the main reasoning step but before publishing, an adversarial agent generates the **strongest counterargument** in 2 sentences. The counterargument is appended to the report — readers see the system's own objection to its conclusion. This reduces confirmation bias without doubling report length.

---

## Layer 3 — Output

### Telegram routing

Each domain has its own bot account and target ID. The `_domain_loader.py` shared loader resolves the right pair per domain — VLA goes to one channel under one account, AI to another, even if they share the same chat ID.

### GitHub (append-only)

All outputs are pushed to your configured knowledge-base repos via the GitHub Contents API. Permanent commit history, full-text grep (`git log -S "your keyword"`), no SaaS dependency, forkable.

### MCP server (12 tools)

The `mcp_server.py` exposes the knowledge base to any MCP client. All tools are read-only. See [docs/mcp.md](mcp.md).

### Semantic index

Rolling 60-day window, DashScope `text-embedding-v3` (1024-dim). Incremental build via `semantic-index-builder.py`; pure-Python cosine query via `semantic-search.py`. Also exposed as the `search_memory` MCP tool.

---

## Layer 4 — Quality (the closed loop)

### Watchdog (16 checks)

`daily-watchdog.py` checks 16 health signals, in DAG order so RSS gates downstream rerun. 7 failure categories self-heal automatically (re-trigger upstream collectors). Lockfile prevents OOM under tight RAM budgets.

Run log: `memory/watchdog-log.json` (retains 60 entries; killed runs and recoveries both recorded).

### Drift Detector

`quality-drift-check.py` watches signal density, rating distribution, and LLM output quality per source. **7-day rolling baseline** compared against today; **30-day sustained-degradation** detection catches slow decay that one-day comparisons would miss.

### Field-State Trigger

`ai-field-state.py` evaluates 6 trigger types mechanically — no LLM:

- `breakthrough_density`, `paradigm_shift`, `consensus_drift`, `silent_decay`, `cross_domain_pull`, `release_clustering`

Runs *before* deep-dive scheduling: only triggered signals become deep-dive candidates. Bounds LLM cost; keeps audit trail mechanical.

### Cross-domain Engine v2 (7 rules)

`cross-domain-rule-engine.py` — deterministic rules R001 through R007:

| ID | Direction | Triggers |
|----|-----------|---------|
| R001 | VLA technique → AI App | Technique transfer (diffusion, RLHF, quantization, …) |
| R002 | AI App framework → VLA | New agent frameworks adopted in robotics stacks |
| R003 | AI embodied → VLA | Embodied-AI papers from generalist labs |
| R004 | VLA foundations → AI | Foundation-model methods originating in robotics |
| R005 | Paradigm fusion | Both domains converging on same paradigm same week |
| R006 | GitHub-repo convergence | ≥3 monitored repos touching shared dependency |
| R007 | Hypothesis-driven transfer | LLM-generated transfer hypotheses (AI → VLA) |

Each insight batch gets a one-sentence "cross-domain significance" line from an LLM — the rules are deterministic, the framing is LLM-assisted.

### Calibration Loop v4 (assumptions × confidence)

```
  Daily signals
       │
       ▼
  Calibration check ─── each signal matched against hypotheses
       │
       │  (monthly, on the 28th)
       ▼
  Trigger rate computed per hypothesis
       │
       ├── confirmed by data ──▶ confidence ▲  (max +0.08)
       │
       └── drifting / low evidence ──▶ confidence ▼
                                            │
                                            ▼
                                      Watch-list entry
                                            │
                                            ▼
                                 Next cycle: signal boost
                                 (extra relevant signals
                                  injected from RSS/social)
                                            │
                                            ▼
                                 More evidence → re-evaluate
                                            │
                                            └──▶ loop continues

  Biweekly predictions ──▶ ✅/❌ grade ──▶ accuracy history in Git
```

The system actively investigates what it might be wrong about — declining confidence triggers signal boost on the next cycle, not just a metric update. Confidence history is committed to Git; belief changes are traceable, never silent.

---

## End-to-end timing example

For the reference VLA pipeline (Asia/Shanghai TZ):

```
00:50  upstream-signal-monitor.py        — arxiv cs.CL / cs.AI / stat.ML scan
07:30  collect-github-issues.py          — tier-1 OSS repos
09:05  vla-rss-collect.py                — RSS / arXiv cs.RO
09:15  post-vla-hotspots                 — rating engine → daily hotspots
09:50  post-vla-sota                     — SOTA tracker
09:55  entity-tracker.py                 — author / lab / method index
09:56  ai-field-state.py                 — trigger gate
10:10  quality-drift-check.py            — drift detector
10:20  cross-domain-rule-engine.py       — 7-rule cross-domain pass
10:30  daily-watchdog.py                 — 16-check audit + self-heal
11:00  calibration-check                 — hypothesis trigger rates
11:15  semantic-index-builder.py         — incremental embedding refresh
```

Friday 13:00 runs the GitHub adoption analysis; Friday afternoon hosts weekly deep dives; the 28th of each month runs the calibration aggregation that updates assumption confidence.

---

## Why this layering

- **L1 (Input)** doesn't trust LLMs to cut noise — keyword rules + Jaccard dedup are auditable and free.
- **L2 (Processing)** uses LLMs only on a small, pre-rated candidate set; every LLM call has a structured prep input and a validation post step.
- **L3 (Output)** writes to Git and Telegram — both durable, both diffable.
- **L4 (Quality)** is what makes Pulsar *self-evolving*: drift detection, field-state triggers, cross-domain rules, and the assumption × confidence loop all run autonomously. Without L4, the system degrades silently; with it, the system reveals its own blind spots.

---

## Further reading

- [`docs/mcp.md`](mcp.md) — the 12-tool MCP API
- [`docs/multi-domain.md`](multi-domain.md) — multi-domain configuration
- [`scripts/SCRIPTS.md`](../scripts/SCRIPTS.md) — full DAG of all pipeline scripts
- [`AGENTS.md`](../AGENTS.md) — deployment notes
