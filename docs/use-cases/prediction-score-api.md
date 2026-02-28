# Prediction Score API — Use Cases

> **Status**: 📋 Planned | **Priority**: P3 | **Issue**: [#13](https://github.com/sou350121/Pulsar/issues/13)

Scores open predictions against accumulated evidence on a 0–100 scale, maintains a rolling accuracy history, and updates confidence values in `assumptions.json` programmatically.

---

## Use Case 1: Monthly Calibration Scoring Run

**Scenario**: On the 28th of each month, the monthly calibration aggregation job (`monthly-calibration-agg.py`, 062a75be) runs. Currently it adjusts confidence by up to ±0.08 per assumption. The Prediction Score API provides the scoring substrate so the adjustment is evidence-driven rather than heuristic.

**What happens**: For each open prediction in `assumptions.json`, the API gathers all signals from the past 30 days, computes a confirmation score (0–100) based on the number and rating weight of supporting vs. contrary signals (⚡ = 3 points, 🔧 = 1 point, ❌ = -2 points, with diminishing returns), and returns a `delta_confidence` value capped at ±0.08. The monthly job applies this delta and writes the updated `assumptions.json`.

**Example**:
```json
{
  "assumption_id": "vla-04",
  "text": "Diffusion-based policies will outperform transformer-only on contact-rich tasks by Q3 2026",
  "score": 68,
  "supporting_signals": 5,
  "contrary_signals": 2,
  "signal_breakdown": {"⚡_for": 3, "🔧_for": 2, "⚡_against": 1, "🔧_against": 1},
  "current_confidence": 0.71,
  "delta_confidence": +0.06,
  "new_confidence": 0.77
}
```

---

## Use Case 2: Rolling Prediction Accuracy Tracking

**Scenario**: After 6 months of operation, the researcher wants to know Pulsar's track record: what fraction of predictions were eventually confirmed, invalidated, or remain open? And does accuracy differ between VLA and AI App domains?

**What happens**: The API queries `assumptions.json` for all predictions with `status: closed` (either `confirmed` or `invalidated`) and computes accuracy metrics by domain, prediction type (directional trend vs. threshold claim), and confidence-at-creation. Results are written to `memory/prediction-accuracy.json` and included in the monthly Telegram report.

**Example**:
```
Rolling accuracy report — 2026-02 (6-month window)

VLA domain:
  Confirmed: 8/13 closed predictions (61.5%)
  Invalidated: 5/13 (38.5%)
  High-confidence (>0.80) accuracy: 4/5 (80%) — well-calibrated
  Low-confidence (<0.60) accuracy: 2/6 (33%) — expected

AI App domain:
  Confirmed: 6/9 closed predictions (66.7%)
  Invalidated: 3/9 (33.3%)

Overall Brier score: 0.21 (lower = better calibrated; 0.25 = random)
```

---

## Use Case 3: Evidence-Based Confidence Update on ⚡ Signal

**Scenario**: A breakthrough paper — "pi0.5: A Vision-Language-Action Model Trained on 10,000 Robot Hours" — drops and is rated ⚡ by the VLA daily pipeline. It directly addresses prediction vla-07: "A single generalist policy will achieve >80% success on 5+ manipulation task families by end of 2026."

**What happens**: The rating pipeline checks each ⚡ signal against all open predictions using keyword + semantic matching. If a signal's relevance score to a prediction exceeds 0.75, the Prediction Score API is called immediately (not waiting for monthly aggregation) to apply an intra-month confidence update. The update is logged with the signal ID so it is auditable.

**Example**:
```
[INTRA-MONTH UPDATE] Signal: pi0.5 (2026-02-19, ⚡)
Matched prediction: vla-07 — "generalist policy >80% on 5+ task families by 2026"
Relevance score: 0.91

Evidence: pi0.5 reports 84% average success across 7 task families on real hardware.
Prediction score delta: +22 points (was 41 → now 63)
Confidence update: 0.55 → 0.63 (capped at +0.08 per event)
Status: remains OPEN (end-of-2026 deadline not reached)
```

---

## Use Case 4: Monthly Prediction Scorecard Leaderboard

**Scenario**: The researcher shares a monthly scorecard in a research group chat to communicate which hypotheses are solidifying and which should be abandoned. The scorecard needs to be concise, scannable, and ranked.

**What happens**: The Prediction Score API generates a ranked leaderboard of all open predictions sorted by current score descending. Each entry shows the hypothesis, current confidence, monthly score change, and a one-word trend label. The output is formatted as a Telegram-friendly markdown table.

**Example**:
```
PREDICTION SCORECARD — Feb 2026

VLA Domain
#  Score  Conf   Trend    Prediction
1   82    0.83   RISING   pi0.5-class generalist achieves 80%+ success on 5+ tasks
2   71    0.77   RISING   Diffusion policies dominate contact-rich manipulation
3   58    0.61   STABLE   Sim-to-real gap < 15% on LIBERO by Q4 2026
4   34    0.42   FALLING  Tactile sensing standard in VLA by 2027
5   19    0.28   FALLING  Video pretraining alone sufficient (no fine-tuning)

AI App Domain
#  Score  Conf   Trend    Prediction
1   79    0.81   RISING   MoE architectures dominate open-source frontier by mid-2026
2   61    0.65   STABLE   Tool-use agents reach 70% on GAIA benchmark by Q3 2026
```

---

*See also: [Devil's Advocate Report](devils-advocate-report.md), [Semantic Memory Search](semantic-memory-search.md)*
