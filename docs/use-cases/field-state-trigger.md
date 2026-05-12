# Field-State Trigger

> **Why**: deep-dive LLM passes are the most expensive step in the pipeline. Without a gate, you pay for one every day even when nothing interesting happened. Field-state is the gate.

## What it does

`scripts/ai-field-state.py` runs daily, **zero LLM**, and evaluates the day's rated corpus against 6 trigger types:

| Trigger | What it catches |
|---------|----------------|
| `breakthrough_density` | Spike of `⚡` items in a 3-day window |
| `paradigm_shift` | A new method family entering top-5 share of the corpus |
| `consensus_drift` | An assumption (from `memory/assumptions.json`) being repeatedly contradicted |
| `silent_decay` | A previously-hot method family dropping out for 14+ days |
| `cross_domain_pull` | A foreign-domain technique entering the rated signals |
| `release_clustering` | ≥3 model releases targeting the same benchmark within 7 days |

If **no** trigger fires, the deep-dive queue stays empty for the day. If **any** trigger fires, the matching items become deep-dive candidates and enter the FIFO backlog queue.

## Output

`memory/field-state-YYYY-MM-DD.json`:

```json
{
  "date": "2026-05-12",
  "triggers": ["breakthrough_density", "release_clustering"],
  "candidates": [
    {"title": "...", "trigger": "breakthrough_density", "rating": "⚡", ...}
  ],
  "no_trigger_reason": null
}
```

When `triggers` is empty, `no_trigger_reason` explains *why* (e.g. "DFI below baseline; rating distribution stable"). This makes the absence of a deep-dive auditable.

## Cost

Pure JSON I/O + arithmetic. Sub-second on the 2 GB VPS profile.

## Why this matters

A pipeline that always generates a deep-dive eventually generates **noise deep-dives** on slow days. Field-state lets the system stay quiet when there is nothing meaningful to say — and gives you a written reason for the silence.
