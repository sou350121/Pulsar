# Pulsar Use Cases

Each entry below explains one Pulsar capability — what problem it solves,
how it works, and how to enable it. Use this as the entry point when you want
to know *whether* a feature exists before reading its full design doc.

## Status legend

- ✅ **Done** — shipped in this repo, runnable today
- 📋 **Planned** — designed but not built
- ⏭️ **Skipped** — superseded by another feature; design preserved for reference

## P0 · Foundations

| Use case | What it does | Status |
|----------|--------------|--------|
| [MCP Server](mcp-server.md) | 12-tool MCP endpoint exposing signals, knowledge, predictions, and full-text memory search to any MCP client (Claude Desktop, Cursor) | ✅ |
| [Multi-domain Config](multi-domain-config.md) | `memory/domains.json` registry + shared loader so one Pulsar instance can track N domains side-by-side | ✅ |
| [One-click Deploy](one-click-deploy.md) | `scripts/setup.sh` — guided installer for Python, mcp, configs, path substitution, Claude Desktop JSON output | ✅ |

## P1 · Quality & Bridging

| Use case | What it does | Status |
|----------|--------------|--------|
| [Quality Drift Detector](quality-drift-detector.md) | 7-day rolling baseline + 30-day sustained-decay; catches silent pipeline degradation that watchdog misses | ✅ |
| [Agent Role-Switching](agent-role-switching.md) | Refactor prep → agent → post into named roles (Reader / Analyst / Memory / Delivery), each pluggable to a different model size | ✅ |
| [Cross-domain Rule Engine](cross-domain-rule-engine.md) → [**v2**](cross-domain-engine-v2.md) | Deterministic IF/THEN rules for cross-domain signal bridging; v2 ships 7 built-in rules + LLM significance per insight batch | ✅ |
| [Field-State Trigger](field-state-trigger.md) | Mechanical zero-LLM gate (6 trigger types) that decides whether a daily deep-dive should run at all — bounds LLM cost without losing signal | ✅ |

## P2 · Knowledge & Discovery

| Use case | What it does | Status |
|----------|--------------|--------|
| [Spike Detector](spike-detector.md) | Out-of-schedule alert for keyword-density bursts | ⏭️ Skipped (superseded by Field-State Trigger) |
| [Devil's Advocate Report](devils-advocate-report.md) | Adversarial counterargument pass appended to every reasoning report | ✅ |
| [Entity Tracker](entity-tracker.md) | 90-day rolling JSON index of `{author, lab, benchmark, method}` extracted from ⚡/🔧 signals | ✅ |
| [Upstream Signal Monitor](upstream-signal-monitor.md) | Track 1–2 upstream domains for signals that historically precede breakthroughs | ✅ |
| [Semantic Memory Search](semantic-memory-search.md) | DashScope `text-embedding-v3` vector index over the rolling 60-day window; MCP-exposed as `search_memory` | ✅ |
| [GitHub Issues Adoption Sensor](gh-issues-adoption-sensor.md) | Watch OSS-repo issue/PR cadence; infer adoption phase (incubation → growth → mainstream → maturity), DFI, cross-repo convergence | ✅ |

## P3+ · Roadmap

| Use case | What it does | Status |
|----------|--------------|--------|
| [GraphRAG Knowledge Graph](graphrag.md) | Convert entity tracker + commit history into a relationship graph | 📋 Planned |
| [Prediction Score Public API](prediction-score-api.md) | Expose biweekly prediction hit-rate + hypothesis confidence as a public credibility-score endpoint | 📋 Planned |
| [Config Marketplace](config-marketplace.md) | Community hub for sharing domain configs / RSS feed lists / hypothesis starter sets | 📋 Planned |

## When to enable what

Most P0 capabilities should be enabled from day 1 (MCP, multi-domain, setup).
The P1 and P2 capabilities have data dependencies — enabling them before the
upstream collectors have run a few days produces empty / misleading output:

| After… | Enable… | Why |
|--------|---------|-----|
| Day 1 | MCP server · setup.sh · Devil's Advocate | Zero data dependency |
| Day 3 | Field-State Trigger · Cross-domain v2 | Needs a small daily corpus to compute density |
| Day 7 | Quality Drift Detector | Needs a 7-day rolling baseline |
| Day 14 | Entity Tracker queries · GitHub Adoption analysis | Needs an issues index and rated-signal accumulation |
| Day 28 | Calibration aggregation · Upstream Monitor analysis | Monthly cadence; first run on the 28th |
| Day 60 | Semantic Memory Search (full-quality) | Full 60-day embedding window |

Run `python3 scripts/check-pipeline.py` at any point to verify the scripts
themselves are healthy — independent of whether you have enough data yet.
