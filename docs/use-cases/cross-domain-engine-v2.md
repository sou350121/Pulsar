# Cross-domain Rule Engine v2

> **Why**: LLM-generated cross-domain discovery produces too many false positives ("both domains mention transformers"). Deterministic rules are auditable, predictable, and encode the user's actual cross-domain hypotheses rather than letting the model guess.

## What changed in v2

| | v1 | v2 |
|---|----|----|
| Rules | 2 (R001, R003) | **7 (R001-R007)** |
| Config source | `active-config.json` | Built into the script (no config dependency) |
| LLM significance | none | One sentence per insight batch |
| GitHub-repo convergence | not detected | R006 reads `compute-gh-adoption.py` output |
| Hypothesis-driven transfer | not supported | R007 (LLM generates AI→VLA transfer hypotheses with per-cycle cap) |

## The 7 rules

| ID | Label | Direction | Trigger |
|----|-------|-----------|---------|
| **R001** | `vla-technique-cross` | VLA → AI App | Technique keywords (diffusion, flow matching, transformer, RLHF, quantization, distillation, …) appearing in `⚡` / `🔧` / `📖` VLA items |
| **R002** | `ai-framework-to-vla` | AI App → VLA | New agent / orchestration frameworks (LangGraph, CrewAI, AutoGen, …) being adopted in robotics stacks |
| **R003** | `ai-embodied-to-vla` | AI App → VLA | Embodied-AI papers from generalist labs reaching VLA practitioners |
| **R004** | `vla-foundations-to-ai` | VLA → AI App | Foundation-model and pre-training methods originating in robotics |
| **R005** | `paradigm-fusion` | bidirectional | Both domains converging on the same paradigm in the same week |
| **R006** | `github-repo-convergence` | bidirectional | ≥3 monitored repos touching shared dependency / method / benchmark in the same week |
| **R007** | `hypothesis-driven-transfer` | AI → VLA | LLM generates `N` transfer hypotheses per cycle, capped to avoid spam |

## Output

`memory/cross-domain-insight.json` — append-only, 60-day retention. Each insight:

```json
{
  "date": "2026-05-12",
  "rule_id": "R005",
  "label": "paradigm-fusion",
  "items": [
    {"title": "...", "rating": "⚡", "domain": "vla"},
    {"title": "...", "rating": "🔧", "domain": "ai_app"}
  ],
  "significance": "Both domains converged on diffusion-flow-matching this week — VLA via Pi0.5, AI app via Flux Schnell — suggesting the technique is moving from research to production tooling."
}
```

The `significance` line is the **only** LLM-generated content; rule matching itself is deterministic.

## When to disable a rule

If a rule generates too much noise for your domain, comment it out in `RULES` at the top of `cross-domain-rule-engine.py`. Each rule is self-contained — no cross-dependencies.

## Consumption

- Weekly / biweekly reports read `cross-domain-insight.json` directly.
- The web push step lifts the most-significant items into the public dashboard.
- The MCP `search_signals` tool can grep the file by keyword.
