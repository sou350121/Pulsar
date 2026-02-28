# Semantic Memory Search — Use Cases

> **Status**: 📋 Planned | **Priority**: P2 | **Issue**: [#11](https://github.com/sou350121/Pulsar/issues/11)

Enables vector-similarity search across Pulsar's full signal archive, allowing the researcher and downstream agents to retrieve semantically relevant past signals by meaning rather than keyword.

---

## Use Case 1: Abstract Similarity Search

**Scenario**: The researcher reads a new preprint on visuotactile manipulation and wants to know what related work Pulsar has already tracked — not just papers with "tactile" in the title, but papers with similar methodology and framing.

**What happens**: The researcher pastes the abstract into a search query. The semantic search engine encodes it into a vector embedding, queries the archive index (built over all rated signals in `vla-daily-{date}.json` files), and returns the top-N most similar past signals ranked by cosine similarity. Each result includes its original rating, date, and a one-line similarity reason.

**Example**:
```
Query: "We present a visuotactile policy that fuses RGB and GelSight sensor streams
        using cross-attention to enable robust in-hand object rotation."

Results (top 5):
  1. [0.94] "TactileVLA: Multimodal Tactile-Vision Policy" (2026-01-08, ⚡)
             Reason: cross-modal fusion for dexterous in-hand tasks
  2. [0.89] "GelFusion: Contact-Rich Manipulation via Tactile Transformers" (2025-11-22, ⚡)
             Reason: GelSight + attention mechanism for rotation tasks
  3. [0.81] "ViTac: Visual-Tactile Pretraining at Scale" (2025-12-14, 🔧)
             Reason: visuotactile representation learning, similar architecture
```

---

## Use Case 2: Contradiction Finder

**Scenario**: Before the biweekly reflection, the researcher wants to surface all signals that directly challenge the assumption "tactile sensing will dominate dexterous manipulation by 2026" — going beyond keyword search to find semantically contrary claims.

**What happens**: The contradiction finder encodes the assumption as a positive claim, then searches the archive for signals whose embeddings are close to the semantic negation (e.g. "vision-only achieves parity with tactile", "tactile sensing not required for dexterous tasks"). It returns signals ranked by their contradiction score, with the specific contradicting sentence highlighted.

**Example**:
```
Assumption: "Tactile sensing will dominate dexterous manipulation by 2026"

Contradicting signals (top 3):
  1. [score 0.88] VisionOnly-Dex (2026-02-10, ⚡)
     Contradicting claim: "Our vision-only policy matches tactile-equipped baselines
     on 8 of 10 DEXTERITY benchmark tasks."
  2. [score 0.79] SyntheticTouch ablation (2026-01-30, 🔧)
     Contradicting claim: "Removing tactile input reduces success rate by only 4%
     when RGB resolution is doubled."
  3. [score 0.71] Octo-Dex (2025-12-20, 🔧)
     Contradicting claim: "Tactile sensors add latency without improving grasp
     success on smooth objects."
```

---

## Use Case 3: Historical Retrieval Across Sessions

**Scenario**: It is late February 2026 and the researcher cannot remember what Pulsar tracked about diffusion policies in November 2025. The relevant JSON files are archived; keyword grep would miss paraphrased content.

**What happens**: Semantic search queries the persistent archive index which spans all ingested signals since pipeline inception. The query "diffusion policies for robot manipulation" is encoded and matched against the full index, including signals from `vla-daily-2025-11-*.json`. Results are returned with exact dates, enabling the researcher to reconstruct the state of the field at any point in time.

**Example**:
```
Query: "diffusion policies for robot manipulation" | Date filter: 2025-11-01 to 2025-11-30

Results:
  1. [0.93] "Consistency Policy: Diffusion Distillation for Real-Time Robot Control"
             (2025-11-07, ⚡) — fast sampling via consistency models, 10x inference speedup
  2. [0.87] "Diffusion-VLA: Jointly Learning Vision-Language-Action with Diffusion"
             (2025-11-19, ⚡) — first end-to-end VLA with diffusion action head
  3. [0.82] "DPPO: Diffusion Policy Policy Optimization" (2025-11-26, 🔧)
             — RL fine-tuning of diffusion policies, marginal gains on LIBERO
```

---

## Use Case 4: Biweekly Report Prep — Automated Retrieval

**Scenario**: The AI biweekly reflection agent (a6f10d54) runs at 15:45. Before calling qwen3.5-plus to generate the narrative, it needs the top-N most relevant signals from the past 60 days — not just the last 14 — to provide richer context for pattern analysis.

**What happens**: The biweekly script calls the semantic search API internally, passing the current domain focus description ("AI application development tools, agent frameworks, LLM deployment") as the query. It retrieves the top-20 signals by relevance from the full 60-day window, merges them with the standard 14-day signal list (deduped by signal ID), and passes the enriched context to the LLM. This prevents the report from missing a highly relevant signal that happened 5 weeks ago.

**Example**:
```python
# Called inside run-ai-biweekly-reflection.py
extra_context = semantic_search(
    query=domain_config["focus_description"],
    date_from="2025-12-29",
    date_to="2026-02-28",
    top_n=20,
    min_rating=["⚡", "🔧"]
)
# Returns list of signal dicts merged into LLM context before generation
```

---

*See also: [GraphRAG](graphrag.md), [Devil's Advocate Report](devils-advocate-report.md)*
