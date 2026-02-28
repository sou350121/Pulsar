# Upstream Signal Monitor — Use Cases

> **Status**: 📋 Planned | **Priority**: P2 | **Issue**: [#10](https://github.com/sou350121/Pulsar/issues/10)

Watches upstream sources — GitHub repos, conference calendars, citation graphs, and preprint servers — for events that matter before they reach the daily RSS pipeline.

---

## Use Case 1: GitHub Repo Watcher

**Scenario**: The researcher relies on LeRobot, openpi, and RoboVLMs as bellwether open-source projects. A new release or a large commit burst in these repos often signals a paper drop 24–48 hours later.

**What happens**: The upstream monitor polls the GitHub API (releases + commits endpoints) for a configured list of repos every 6 hours. When a new release tag is published or commit count exceeds a threshold (default: 10 commits in 6 hours to non-doc files), it fires an alert to Telegram and pre-caches the repo metadata so the downstream VLA pipeline can correlate it with any arxiv paper that cites the same repo URL.

**Example**:
```
[UPSTREAM: GITHUB RELEASE]
Repo: huggingface/lerobot — v1.4.0 released 2026-02-28 03:14 UTC
Highlights (auto-summarised from release notes):
  - New ACT policy with diffusion head option
  - IsaacLab integration (beta)
Pre-cache: linked to keyword "lerobot" in vla-daily pipeline
```

Tracked repos (initial list): `huggingface/lerobot`, `Physical-Intelligence/openpi`, `microsoft/RoboVLMs`, `embodied-intelligence/RoboticsDiffusionTransformer`, `isaac-sim/IsaacLab`.

---

## Use Case 2: Conference Deadline Tracker

**Scenario**: The researcher occasionally submits to top venues and wants a 14-day heads-up for submission deadlines so they can align the Pulsar biweekly deep dive with their own writing sprint.

**What happens**: A static YAML file (`config/conference-deadlines.yaml`) stores submission dates for NeurIPS, ICML, ICLR, CoRL, RSS, ICRA, and RA-L. The upstream monitor checks dates daily at 07:00 Shanghai time and sends a Telegram alert 14 days and 3 days before each deadline. The alert includes a link to the cfp and a one-line summary of which open Pulsar predictions are most relevant to that venue's typical topics.

**Example**:
```
[UPSTREAM: DEADLINE — 14 days]
Conference: CoRL 2026
Abstract deadline: 2026-03-14 (paper: 2026-03-21)
CFP: https://corl2026.org/cfp
Relevant open predictions: "Diffusion policies for contact-rich tasks" (confidence 0.79),
  "Sim-to-real gap < 15% on standard benchmarks" (confidence 0.62)
```

---

## Use Case 3: Key Paper Citation Alert

**Scenario**: RT-2, pi0, and Octo are foundational papers the researcher tracks as proxy metrics for field momentum. When 3 or more new papers cite any of them on the same day, it signals a research burst worth investigating immediately.

**What happens**: The upstream monitor queries the Semantic Scholar API daily for new citations to a watchlist of paper IDs. When the daily new-citation count for any watched paper exceeds the configured threshold (default: 3), it fires a "citation burst" alert. The cited papers are fetched, pre-rated with a lightweight keyword match, and injected into the next VLA daily pipeline run as priority items.

**Example**:
```
[UPSTREAM: CITATION BURST]
Paper: "Octo: An Open-Source Generalist Robot Policy" (SemanticScholar ID: 2f3a...)
New citations today: 5
Pre-rated injected papers:
  - "OctoFine: Few-Shot Adaptation of Octo to Surgical Tasks" → likely 🔧
  - "Scaling Octo with Synthetic Data from Genesis" → likely ⚡
  - "Benchmarking Octo vs RT-2 on LIBERO" → likely 🔧
```

Citation watchlist lives in `config/citation-watchlist.json`.

---

## Use Case 4: Preprint Server Early Monitor

**Scenario**: The daily RSS pipeline runs at 09:00 Shanghai. The researcher wants to catch cs.RO and cs.AI papers matching high-priority keywords (e.g. "dexterous manipulation", "VLA", "robot foundation model") as soon as arxiv publishes the nightly batch — typically 06:30 Shanghai — to get a 2.5-hour head start.

**What happens**: At 06:35 Shanghai, the upstream monitor queries the arxiv API for papers submitted in the past 24 hours matching the priority keyword list. Papers are lightly scored using keyword density (no LLM call, to save RAM on the 2GB server). Any paper exceeding a score threshold is pre-cached in `tmp/_upstream_arxiv_{date}.json` and merged into the 09:00 VLA RSS pipeline as a supplemental feed, ensuring they appear in the daily rating run without duplicates.

**Example**:
```json
{
  "source": "arxiv_early",
  "fetched_at": "2026-02-28T06:36:02+08:00",
  "items": [
    {
      "title": "VisuoTactile Transformer for In-Hand Manipulation",
      "arxiv_id": "2602.12345",
      "keyword_score": 0.81,
      "matched_keywords": ["tactile", "dexterous", "VLA"],
      "pre_status": "priority_inject"
    }
  ]
}
```

---

*See also: [Entity Tracker](entity-tracker.md), [Semantic Memory Search](semantic-memory-search.md)*
