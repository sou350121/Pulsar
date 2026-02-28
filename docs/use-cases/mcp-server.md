# MCP Server — Use Cases

> **Status**: ✅ Done | **Priority**: P0 | **Issue**: [#1](https://github.com/sou350121/Pulsar/issues/1)

Exposes Pulsar's memory and pipeline state as 11 MCP tools so any Claude conversation can query signals, assumptions, health, and predictions without leaving the chat.

---

## Use Case 1: Morning Briefing — Top VLA Signals This Week

**Scenario**: The researcher opens Claude Desktop on Monday morning and wants a ranked summary of the most important VLA papers from the past 7 days before deciding what to read.

**What happens**: Claude calls `get_vla_signals` with a date-range filter. The tool reads `vla-daily-hotspots-*.json` files from the past 7 days, aggregates ⚡-rated entries, and returns titles, ratings, and one-line abstracts sorted by signal strength.

**Example**:
```
User: "Give me the top VLA signals from this week."

Tool call: get_vla_signals(days=7, min_rating="⚡")

Response excerpt:
- ⚡ "DexGrasp-Anything: Generalizable Dexterous Grasping via ..." (2026-02-25)
- ⚡ "UniManip: Unified Manipulation Policy via VLA ..." (2026-02-24)
- 🔧 "Tactile Feedback Integration in RT-2 ..." (2026-02-23)
```

---

## Use Case 2: Hypothesis Validation — What Does Pulsar Know About Tactile Sensing?

**Scenario**: The researcher is writing a survey section on tactile sensing in VLA models and wants to know whether Pulsar has picked up any relevant papers or signals in the past 30 days.

**What happens**: Claude calls `search_signals` with keyword `"tactile sensing"` across both domains. The tool scans all cached signal JSONs and returns matching entries with dates and ratings, giving the researcher a ready audit trail.

**Example**:
```
Tool call: search_signals(query="tactile sensing", domains=["vla", "ai_app"], days=30)

Result:
- [vla] ⚡ "Touch-VLA: Tactile-Conditioned ... " — 2026-02-18
- [vla] 🔧 "GelSight integration with OpenVLA ..." — 2026-02-11
- [ai_app] ❌ "Consumer haptic API roundup ..." — 2026-02-05 (not relevant)
```

---

## Use Case 3: Pipeline Health Check in Conversation

**Scenario**: The researcher suspects something went wrong overnight (no Telegram message arrived) and wants to diagnose without SSH-ing into the server.

**What happens**: Claude calls `get_pipeline_health`, which reads the latest watchdog output and today's signal files, then reports which checks passed/failed, any self-healing actions taken, and disk usage.

**Example**:
```
Tool call: get_pipeline_health()

Result:
- vla_rss: ✅ checked_at=2026-02-28
- vla_rating: ✅
- aiapp_daily: ❌ missing (file not found for 2026-02-28)
- disk_space: ✅ 61% used
- Watchdog self-heal: triggered aiapp_rss re-run at 10:22
```

---

## Use Case 4: Cross-domain Search — Keyword Across Both Pipelines

**Scenario**: The researcher notices "foundation model" appearing heavily in AI App news and wonders if VLA papers are also converging on that framing this month.

**What happens**: Claude calls `search_signals` without a domain filter, so both `vla` and `ai_app` sources are scanned. Results are grouped by domain, letting the researcher see convergence patterns or domain-specific divergence.

**Example**:
```
Tool call: search_signals(query="foundation model", days=28)

vla hits (12): ⚡ x4, 🔧 x6, 📖 x2
ai_app hits (19): ⚡ x7, 🔧 x8, ❌ x4

Overlap dates: heavy overlap 2026-02-18 to 2026-02-22 — possible coordinated wave.
```

---

## Use Case 5: Prediction Review — Did Last Biweekly's Forecasts Come True?

**Scenario**: Before writing the new biweekly reflection, the researcher asks Claude to pull the last 3 biweekly prediction sets and evaluate each against what actually arrived in the signal stream.

**What happens**: Claude calls `get_predictions` (returns stored prediction blocks from biweekly JSONs), then calls `get_vla_signals` and `get_ai_signals` for the intervening period. Claude cross-references and labels each prediction ✅/❌/⏳.

**Example**:
```
Tool call: get_predictions(domain="vla", last_n=3)

Prediction (2026-02-14): "Dexterous hand papers will surge in March"
Verdict: ⏳ — only 2 papers so far, window not closed

Prediction (2026-01-31): "OpenVLA fine-tuning tooling will appear as OSS"
Verdict: ✅ — "OpenVLA-OFT" repo appeared 2026-02-20 (⚡ rated)

Prediction (2026-01-17): "Tactile sensing will reach RT-2 scale"
Verdict: ❌ — no ⚡ paper matched this claim in window
```

---

*See also: [Multi-domain Config](multi-domain-config.md), [Spike Detector](spike-detector.md)*
