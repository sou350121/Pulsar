# Config Marketplace — Use Cases

> **Status**: 📋 Planned | **Priority**: P4 | **Issue**: [#14](https://github.com/sou350121/Pulsar/issues/14)

A community registry where researchers publish, discover, fork, and rate Pulsar domain configs — reducing the weeks of keyword tuning needed to bootstrap a new research monitoring pipeline.

---

## Use Case 1: Publishing a Tested VLA Keyword Config

**Scenario**: After 3 months of running the VLA pipeline, the researcher has tuned `active-config.json` to produce a high signal-to-noise ratio — consistently 4–6 ⚡ papers per week with few false positives. They want to share this with the robotics research community.

**What happens**: The researcher runs the marketplace publish command with their config file and a metadata block. The marketplace validates the config schema, computes a baseline SNR score from the submitter's reported weekly ⚡ count, and creates a versioned entry in the registry under their GitHub handle. The config is tagged with domain, version, and a description.

**Example**:
```bash
pulsar marketplace publish \
  --config ~/.moltbot/domains/vla/active-config.json \
  --name "vla-manipulation-focused-v1" \
  --domain vla \
  --description "Optimised for dexterous manipulation, sim-to-real, and VLA architecture papers. Filters out pure perception-only robotics." \
  --weekly-sparks 5.2 \
  --github sou350121

# Output:
# Published: marketplace/sou350121/vla-manipulation-focused-v1@1.0.0
# View at: https://marketplace.pulsar.dev/configs/sou350121/vla-manipulation-focused-v1
```

The config includes: keyword lists, rating thresholds, source weights (arxiv vs. tophub vs. GitHub), dedup window, and retention settings.

---

## Use Case 2: Bootstrapping a New Domain from a Community Config

**Scenario**: A new researcher wants to monitor the biomedical AI domain (LLMs for clinical NLP, medical imaging AI, drug discovery). They have no keyword list and do not know which RSS sources are relevant. Starting from scratch would take weeks of false-positive-heavy iteration.

**What happens**: They search the marketplace for biomedical configs, find a community-verified entry with a 4.8/5 rating and 90-day track record, and download it with one command. The config is installed into their Pulsar domain registry as `biomedical-ai`, pre-populated with keywords, source weights, and RSS feeds. They can run a first collection immediately.

**Example**:
```bash
pulsar marketplace install biomedical-lab/biomedical-ai-v2 --domain biomedical-ai

# Output:
# Installed: biomedical-ai-v2@2.1.0 → ~/.moltbot/domains/biomedical-ai/
# Keywords: 147 terms across 8 categories (clinical NLP, imaging, genomics, drug discovery...)
# Sources: pubmed-rss, biorxiv-cs-AI, ithome-biotech, arxiv-cs.LG+q-bio
# Community rating: 4.8/5 (38 ratings) | Avg weekly ⚡: 3.9
# Next step: run `pulsar domain init biomedical-ai` to start first collection
```

---

## Use Case 3: Fork and Customise a Community Config

**Scenario**: The researcher finds a general "AI Agents" config on the marketplace but wants to narrow it to focus specifically on tool-use agents and multi-agent coordination — removing LLM fine-tuning keywords that generate noise for their use case.

**What happens**: They fork the config locally, edit the keyword list and source weights, validate the schema, and re-publish under their own handle as a derived config. The marketplace tracks the fork lineage, so community members can see the parent config and the diff.

**Example**:
```bash
# Fork from community config
pulsar marketplace fork community/ai-agents-general-v3 --as ai-agents-tooluse-v1

# Edit: remove fine-tuning keywords, add tool-use and multi-agent keywords
nano ~/.moltbot/domains/ai-agents-tooluse/active-config.json

# Validate schema before publish
pulsar marketplace validate --config ~/.moltbot/domains/ai-agents-tooluse/active-config.json
# Output: schema OK | 83 keywords | 6 sources | no deprecated fields

# Publish as derived config
pulsar marketplace publish \
  --config ~/.moltbot/domains/ai-agents-tooluse/active-config.json \
  --name "ai-agents-tooluse-v1" \
  --forked-from community/ai-agents-general-v3 \
  --changelog "Removed LLM training keywords; added tool-calling, ReAct, GAIA benchmark, MCP protocol"
```

---

## Use Case 4: Community Quality Rating Based on SNR

**Scenario**: A researcher has been using a downloaded config for 30 days and wants to rate it based on observed signal quality — how many ⚡ papers per week it produced versus the total items ingested (signal-to-noise ratio).

**What happens**: Pulsar automatically tracks per-domain SNR statistics during normal operation. After 14 days of use, the researcher is prompted (via Telegram) to submit their observed rating to the marketplace. The rating is computed from actual pipeline statistics (not self-reported), which prevents gaming. The marketplace aggregates ratings into a quality score visible to all users.

**Example**:
```
[MARKETPLACE RATING REQUEST]
You have used "sou350121/vla-manipulation-focused-v1" for 30 days.
Your observed stats:
  Total items rated: 412
  ⚡ items: 28 (6.8%)   🔧 items: 74 (18.0%)
  📖 items: 187 (45.4%) ❌ items: 123 (29.9%)
  Weekly ⚡ average: 4.7

Compared to publisher claim (5.2/week): within 10% — consistent.
Submit rating? [5 - Exceeds expectations] [4 - Meets expectations] [3 - Adequate] ...

Your rating (4 stars) submitted.
Config new aggregate: 4.6/5 (39 ratings)
```

SNR thresholds for marketplace trust badges: Bronze >= 2 ⚡/week, Silver >= 4, Gold >= 7 with >= 20 community ratings.

---

*See also: [Upstream Signal Monitor](upstream-signal-monitor.md), [Entity Tracker](entity-tracker.md)*
