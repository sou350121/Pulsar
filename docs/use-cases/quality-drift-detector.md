# Quality Drift Detector — Use Cases

> **Status**: 📋 Planned | **Priority**: P1 | **Issue**: [#4](https://github.com/sou350121/Pulsar/issues/4)

Monitors the pipeline's own output quality over time, detecting gradual degradation in topic relevance, rating distributions, source health, and report reasoning depth before the researcher notices manually.

---

## Use Case 1: Detecting Gradual Topic Drift — VLA Picks Shifting Away from Core Direction

**Scenario**: Over 30 days the researcher notices that VLA daily reports feel increasingly off-topic — more general ML optimization papers, fewer embodied-AI papers — but no single day was obviously wrong. The pipeline never flagged anything.

**What happens**: The drift detector runs weekly (or on-demand via MCP). It loads the past 30 days of `vla-daily-hotspots-*.json`, extracts all ⚡ and 🔧 entries, and computes keyword overlap against the domain's `config.keywords.primary` list. If average overlap drops below a threshold (e.g. < 40% of top picks match primary keywords for 2 consecutive weeks), it fires a Telegram alert and writes a `drift-report-{date}.json`.

**Example**:
```
Drift report — 2026-02-28:
  Primary keywords: ["VLA", "robot learning", "dexterous manipulation", "embodied AI"]
  Week of 2026-02-14: overlap = 68% ✅
  Week of 2026-02-21: overlap = 41% ⚠️
  Week of 2026-02-28: overlap = 33% ❌ DRIFT DETECTED

  Top non-matching picks this week:
  - "Efficient Attention for Long Sequences" (no embodiment signal)
  - "LoRA Fine-tuning Survey" (general ML)

  Recommended action: review vla-config.json exclude list; re-check source RSS feeds.
```

---

## Use Case 2: Rating Distribution Shift — More Failures, Fewer Breakthroughs

**Scenario**: The researcher trusts the ⚡/🔧/📖/❌ ratings, but after two weeks of unusually quiet Telegram messages wonders if qwen3.5-plus started rating everything ❌ due to a prompt regression or model behavior change.

**What happens**: The detector maintains a rolling 14-day rating histogram. It compares the current week's distribution to the prior 3-week baseline. A shift where ❌ share increases by more than 20 percentage points, or ⚡ share drops by more than 15 points, triggers an alert with a side-by-side histogram.

**Example**:
```
Rating distribution alert — 2026-02-28:
  Baseline (2026-02-01 to 2026-02-21):
    ⚡ 18% | 🔧 42% | 📖 25% | ❌ 15%

  Current week (2026-02-22 to 2026-02-28):
    ⚡  4% | 🔧 28% | 📖 21% | ❌ 47%  ← ❌ ANOMALY

  Possible causes:
  - LLM prompt regression (check rate-vla-daily.py last modified)
  - DashScope model rollout (qwen3.5-plus behavior change)
  - Genuine field lull (check raw RSS item count)
```

---

## Use Case 3: Social Intel Source Degradation — Tracked Account Goes Silent

**Scenario**: A key Twitter/X account that consistently produced VLA social signals stops posting. The pipeline still runs without error (the account exists), but signal quality quietly drops because that source is no longer contributing.

**What happens**: The detector tracks per-source contribution counts in the social intel JSON files. If a previously active source (defined as contributing >= 2 items/week over the prior month) produces zero items for 10+ consecutive days, it logs a `source-health` warning entry and includes it in the next watchdog report.

**Example**:
```
Source health warning — 2026-02-28 (vla_social):
  Source: twitter/@OpenRoboticsLab
  Last contribution: 2026-02-17 (11 days ago)
  Prior 30-day avg: 3.2 items/week

  Source: twitter/@StanfordAILab
  Status: ✅ active (4 items this week)

  Action: verify account is still posting; consider replacing with @CMU_Robotics.
```

---

## Use Case 4: Biweekly Report Quality Decline — Reasoning Depth Drops

**Scenario**: The researcher reads the last three biweekly VLA reflections and feels the reasoning is getting shallower — fewer specific citations, more generic statements. But it is hard to quantify without a baseline.

**What happens**: Each biweekly report is scored at generation time on three dimensions: citation density (number of specific paper/date references per 100 words), prediction specificity (does each prediction include a time window and measurable criterion?), and section completeness (are all required sections — signals, SOTA, social, previous-prediction review — non-empty?). Scores are stored in `quality-review.json` (180-day retention). The detector flags a downward trend of 2+ consecutive reports on any dimension.

**Example**:
```json
// quality-review.json entry:
{
  "date": "2026-02-28",
  "report": "vla-biweekly",
  "scores": {
    "citation_density": 2.1,     // refs per 100 words (baseline: 3.4) ⚠️
    "prediction_specificity": 0.6, // 0-1 scale (baseline: 0.85) ⚠️
    "section_completeness": 1.0   // all sections present ✅
  },
  "trend": "declining (3rd consecutive drop on citation_density)"
}
```

---

*See also: [Spike Detector](spike-detector.md), [MCP Server](mcp-server.md)*
