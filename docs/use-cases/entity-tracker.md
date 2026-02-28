# Entity Tracker — Use Cases

> **Status**: 📋 Planned | **Priority**: P2 | **Issue**: [#9](https://github.com/sou350121/Pulsar/issues/9)

Tracks named entities — labs, researchers, and companies — across all ingested signals, maintaining per-entity publication velocity, recency, and relevance scores.

---

## Use Case 1: Lab Publication Velocity Tracking

**Scenario**: The researcher wants to know which robotics labs are accelerating their VLA output — not just who published, but whether their cadence is increasing month-over-month.

**What happens**: The entity tracker maintains a rolling count of ⚡/🔧-rated papers per lab per 30-day window. When a lab's velocity increases by more than 50% versus the prior window, it emits a "velocity spike" event in the daily VLA report. Tracked labs are defined in `domains.json` under `vla.entities.labs`.

**Example**:
```json
{
  "lab": "Physical Intelligence (Pi)",
  "velocity_30d": 8,
  "velocity_prior_30d": 3,
  "change_pct": 167,
  "flag": "SPIKE",
  "top_signal": "pi0.5 (2026-02-19, ⚡) — new generalist manipulation policy"
}
```

Labs currently tracked: Stanford RAIL, CMU Robotics, Google DeepMind Robotics, Physical Intelligence, MIT CSAIL, Berkeley AUTOLab, ETH Zurich RSL.

---

## Use Case 2: Researcher-Level Author Following

**Scenario**: The researcher follows Sergey Levine and Chelsea Finn closely and wants to be alerted any time a new preprint from either appears in Pulsar's arxiv cs.RO feed — not just when it makes the curated daily list.

**What happens**: The entity tracker runs a name-match pass over raw RSS items before rating. Any item whose author list contains a watched researcher is tagged `entity:researcher:<name>` and forwarded immediately to Telegram regardless of its eventual ⚡/🔧/📖/❌ rating. This ensures high-priority authors bypass the noise filter.

**Example**:
```
[ENTITY ALERT] New preprint by Sergey Levine
Title: "Cal-QL: Calibrated Offline RL for Robot Manipulation"
ArXiv: 2402.XXXXX | Rating pending (will appear in tonight's VLA digest)
Authors matched: Levine S., Kumar A.
```

Watched researchers are stored as `vla.entities.researchers` in `domains.json`.

---

## Use Case 3: Company Model Release Tracker (AI App Domain)

**Scenario**: The researcher monitors the AI App domain and needs to catch new model releases from OpenAI, Google, Anthropic, Mistral, and Alibaba within hours — not the next day.

**What happens**: The entity tracker scans the AI RSS feed (`ai-app-rss-{date}.json`) and tophub sources for press release language ("we are releasing", "now available", "API access", "model weights") associated with tracked company names. Matches are rated 🔧 or ⚡ and pushed to the `--account ai_agent_dailybot --target 1898430254` channel with an `[ENTITY: MODEL RELEASE]` prefix.

**Example**:
```
[ENTITY: MODEL RELEASE] Alibaba — Qwen3-235B-A22B
Source: ithome (2026-02-27), tophub rank #2
Trigger words: "开源发布", "API 正式上线"
Rating: ⚡ (new frontier-class MoE model, directly relevant to AI App pipeline)
```

Tracked companies: OpenAI, Google DeepMind, Anthropic, Mistral, Alibaba (Qwen), Meta AI, xAI.

---

## Use Case 4: Rising Entity Detection

**Scenario**: A new lab (e.g., a stealth robotics startup or a university group) starts appearing frequently in ⚡-rated papers but is not yet in the tracked entity list. The researcher wants Pulsar to surface it automatically rather than miss the emergence.

**What happens**: Once per week (Sunday quality review), the entity tracker counts mentions of unlisted org names across the past 7 days of rated signals. Any name appearing in 3 or more ⚡/🔧 items that is not already in the tracked list is flagged as a "rising entity candidate" and included in the weekly quality review Telegram report. The researcher can confirm or dismiss each candidate.

**Example**:
```
[RISING ENTITIES — week of 2026-02-23]
Candidate: "Skild AI"
  Appearances: 4 (3x ⚡, 1x 🔧)
  Context: large-scale generalist robot brain; Series A announcement + 2 preprints
  Action: [ADD TO TRACKED] | [DISMISS]

Candidate: "RoboVerse Lab (Tsinghua)"
  Appearances: 3 (2x ⚡, 1x 🔧)
  Context: sim-to-real transfer, Genesis simulator contributions
  Action: [ADD TO TRACKED] | [DISMISS]
```

---

*See also: [Upstream Signal Monitor](upstream-signal-monitor.md), [GraphRAG](graphrag.md)*
