# Cross-domain Rule Engine — Use Cases

> **Status**: 📋 Planned | **Priority**: P1 | **Issue**: [#6](https://github.com/sou350121/Pulsar/issues/6)

Applies declarative rules to signal events across both VLA and AI App domains, automatically routing, promoting, deduplicating, and combining signals when configurable cross-domain conditions are met.

---

## Use Case 1: VLA ⚡ Paper with "Foundation Model" Tag → Auto-flag in AI App Pipeline

**Scenario**: A VLA paper rated ⚡ by the VLA pipeline is also relevant to AI App researchers because it describes a new foundation model architecture. Currently the researcher must notice the paper twice, once in each domain's Telegram message.

**What happens**: A rule is declared in `memory/cross-domain-rules.json`: `IF domain=vla AND rating=⚡ AND any(keywords, ["foundation model", "large-scale pretraining", "generalist policy"]) THEN copy_to(domain=ai_app, rating=🔧, note="cross-domain: VLA foundation model")`. The rule engine runs after each VLA daily rating pass and injects matching entries into the AI App pipeline's next daily summary.

**Example**:
```json
// cross-domain-rules.json:
{
  "rule_id": "vla_fm_to_aiapp",
  "condition": {
    "domain": "vla",
    "min_rating": "⚡",
    "keywords_any": ["foundation model", "generalist policy", "large-scale pretraining"]
  },
  "action": {
    "type": "copy_to",
    "target_domain": "ai_app",
    "target_rating": "🔧",
    "note": "Cross-domain signal: VLA foundation model paper"
  }
}
```
Result: "π0: A Vision-Language-Action Flow Model" appears in both the VLA ⚡ daily and the AI App 🔧 summary the next morning.

---

## Use Case 2: VLA Release That Is an API/SDK → Promote to AI App Pipeline

**Scenario**: A VLA research group releases an SDK or REST API (not just a model checkpoint). This is directly relevant to AI App developers who might integrate VLA capabilities. The VLA pipeline rates it; the AI App pipeline never sees it without manual intervention.

**What happens**: The rule engine monitors `vla-release-{date}.json`. When a release entry contains API/SDK signals (keywords: "API", "SDK", "pip install", "REST endpoint", "Python package"), the engine promotes it to the AI App pipeline with rating ⚡ and a "developer tool" tag, triggering a Telegram alert on the AI App account.

**Example**:
```
VLA Release detected: "OpenVLA-OFT v0.2 — REST API for fine-tuning + inference"
Keywords matched: ["REST API", "pip install openvla-oft", "endpoint"]

→ Rule vla_api_to_aiapp triggered:
  AI App Telegram alert (@ai_agent_dailybot):
  ⚡ [Cross-domain] OpenVLA-OFT now has a REST API — direct VLA inference for app developers.
  pip install openvla-oft | Docs: github.com/openvla/oft
```

---

## Use Case 3: Cross-domain Dedup — Same Paper Cited in Both Pipelines

**Scenario**: A paper on multimodal agent planning is rated 🔧 by the VLA pipeline (as a planning backbone) and independently fetched and rated 📖 by the AI App pipeline (as an agentic reasoning paper). It appears in both daily Telegram messages, confusing the researcher.

**What happens**: The rule engine runs a dedup pass after both daily pipelines complete. It computes title similarity (fuzzy match, threshold 0.85) and arXiv ID match across the day's rated entries from both domains. Duplicates are merged: the higher rating wins, both domain tags are preserved, and only one entry appears in each domain's Telegram message with a "(also in [other domain])" note.

**Example**:
```
Dedup match detected:
  VLA:    🔧 "Chain-of-Thought Planning for Robot Manipulation" (arXiv:2402.12345)
  AI App: 📖 "Chain-of-Thought Planning for Robot Manipulation" (arXiv:2402.12345)

Merged output:
  Rating: 🔧 (higher wins)
  VLA message:    🔧 "Chain-of-Thought Planning..." [also in AI App]
  AI App message: 🔧 "Chain-of-Thought Planning..." [cross-domain: VLA + AI App]
```

---

## Use Case 4: Composite Trigger — VLA SOTA Record + AI App Launch on Same Day → Combined Report

**Scenario**: On the same day, the VLA pipeline detects a new SOTA result on a major benchmark (e.g. LIBERO), and the AI App pipeline detects a major AI agent framework launch (e.g. a new version of a prominent agent SDK). Individually these are notable; together they may signal a convergence moment worth a dedicated combined analysis.

**What happens**: A composite rule fires when both conditions are true within a 24-hour window. The rule engine calls a dedicated LLM prompt (using qwen3.5-plus via DashScope) that synthesizes both events into a "convergence brief" — a 300-word analysis of whether and how the two events are related. This brief is sent to both Telegram accounts and archived in both domain memory files.

**Example**:
```
Composite trigger: vla_sota_record + aiapp_major_launch (2026-02-28)

VLA event: New SOTA on LIBERO-Spatial — "DexVLA achieves 94.3% success, +8.1% vs prior SOTA"
AI App event: "LangGraph 2.0 released — native tool-use DAGs for multi-agent systems"

Convergence brief (qwen3.5-plus):
"DexVLA's SOTA result relies on a hierarchical planning decomposition structurally similar to
LangGraph 2.0's DAG-based agent orchestration. The timing suggests independent convergence on
task decomposition as the key scaling lever — in physical manipulation and software agents alike.
Watch for: VLA papers citing LangGraph-style architectures in Q2 2026."

Sent to: @original (VLA channel) + @ai_agent_dailybot (AI App channel)
```

---

*See also: [Multi-domain Config](multi-domain-config.md), [Spike Detector](spike-detector.md)*
