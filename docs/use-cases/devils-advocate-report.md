# Devil's Advocate Report — Use Cases

> **Status**: 📋 Planned | **Priority**: P2 | **Issue**: [#8](https://github.com/sou350121/Pulsar/issues/8)

Generates a structured counter-evidence report that challenges existing predictions and assumptions by surfacing disconfirming signals from Pulsar's archive.

---

## Use Case 1: Monthly Counter-Evidence Pass

**Scenario**: Before the biweekly reflection runs at 15:45, the researcher wants to stress-test open predictions rather than letting confirmation bias accumulate across two weeks.

**What happens**: The report scans `assumptions.json` for all predictions with status `open`, retrieves signals from the past 14 days that carry a rating of ⚡ or 🔧, and for each prediction generates a structured rebuttal block listing contrary evidence, alternative explanations, and a challenge score (0–10, where 10 = strong disconfirmation).

**Example**:
```json
{
  "prediction": "Diffusion-based policies will outperform transformer-only baselines on contact-rich tasks by Q3 2026",
  "challenge_score": 7,
  "contrary_signals": [
    "RT-H (2026-02-21, ⚡): transformer-only approach closes 94% of gap on dexterous in-hand tasks",
    "Octo-2 ablation (2026-02-18, 🔧): diffusion head adds 340ms latency, unacceptable for real-time grasping"
  ],
  "alternative_hypothesis": "Hybrid architectures (transformer backbone + diffusion head) may dominate, not pure diffusion"
}
```

---

## Use Case 2: Assumption Stress-Test Before Adding to assumptions.json

**Scenario**: The researcher wants to add a new hypothesis — "Embodied foundation models trained on internet video will transfer to manipulation without task-specific fine-tuning" — but wants to verify it is not already contradicted by tracked signals before committing it.

**What happens**: Pulsar runs a one-shot devil's advocate pass against the proposed assumption text, searching the archive (last 90 days) for ⚡/🔧 signals that address the claim. It returns a confidence recommendation (add / add with caveats / do not add) and a list of the top 3 disconfirming papers.

**Example**:
```
Recommendation: ADD WITH CAVEATS
Disconfirming evidence (3 signals found):
  - SpatioTemporal Pretraining paper (2026-01-14, ⚡): internet video features degrade sharply
    for precise finger-tip control tasks; fine-tuning still required.
  - OpenVLA-v2 benchmark (2026-02-03, 🔧): zero-shot transfer success rate 31% vs 89% fine-tuned.
Suggested caveat: "except for coarse pick-and-place; contact-rich tasks still require fine-tuning"
```

---

## Use Case 3: Overconfidence Automatic Trigger

**Scenario**: The daily calibration check (`calibration-check-{date}.json`) reports that the assumption "tactile sensing will be standard in VLA systems by 2027" has drifted above confidence 0.85 — the watchdog flags this as an overconfidence risk.

**What happens**: Watchdog (f0b3b711) detects `confidence > 0.85` for any assumption and queues a devil's advocate run as a self-healing action. The report is appended to the calibration check output and delivered via Telegram (`--account original --target 1898430254`) as a follow-up message to the daily calibration alert.

**Example**:
```
[CALIBRATION ALERT] Assumption #4 confidence=0.87 > threshold
[DEVIL'S ADVOCATE] 2 contrary signals found (last 30d):
  - VisionOnly-Dex (2026-02-10, ⚡): matches human performance on 8/10 manipulation
    tasks using vision only, no tactile sensors.
Confidence adjusted: 0.87 → 0.79
```

---

## Use Case 4: Pre-Publication Sanity Check

**Scenario**: The researcher has drafted a research memo summarising Pulsar's findings on "sim-to-real transfer for contact-rich manipulation" and is about to share it in a group chat. They want a critique pass before publishing.

**What happens**: The memo text is passed to the devil's advocate tool, which identifies each factual claim, cross-references them against the archive, and returns an annotated version with inline challenge notes and an overall credibility score.

**Example**:
```
Claim: "IsaacLab has become the de-facto simulator for VLA pretraining."
Challenge: Only 4/17 ⚡ papers in the last 60 days used IsaacLab; MuJoCo (6) and
Genesis (4) remain competitive. Rephrase as "a leading option" not "de-facto".
Credibility score: 6.5/10 — revise 3 claims before sharing.
```

---

*See also: [Prediction Score API](prediction-score-api.md), [Semantic Memory Search](semantic-memory-search.md)*
