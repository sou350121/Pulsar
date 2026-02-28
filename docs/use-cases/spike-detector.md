# Spike Detector — Use Cases

> **Status**: 📋 Planned | **Priority**: P2 | **Issue**: [#7](https://github.com/sou350121/Pulsar/issues/7)

Detects anomalous surges in signal volume, topic concentration, social traction, or citation velocity, and escalates alerts when the pipeline itself may have missed the spike due to a watchdog failure.

---

## Use Case 1: Sudden Topic Surge — 5+ ⚡ VLA Papers on the Same Subject Within 3 Days

**Scenario**: Without warning, five papers on diffusion-based manipulation policies appear in 72 hours, all rated ⚡. This is a research wave, not normal background noise. The researcher needs to know immediately, not at the next scheduled biweekly.

**What happens**: The spike detector runs as a lightweight post-process after each daily VLA rating pass. It maintains a sliding 3-day topic window, grouping ⚡/🔧 entries by primary keyword cluster. When any cluster accumulates 5+ ⚡ entries in 72 hours, it fires an out-of-schedule Telegram alert on the VLA account and writes a `spike-{topic}-{date}.json` to memory. The alert includes the paper list, cluster keyword, and a one-line qwen3.5-plus synthesis.

**Example**:
```
⚡ SPIKE ALERT — VLA | 2026-02-28

Topic cluster: "diffusion policy / flow matching"
Papers (last 72h):
  1. ⚡ "π0-Fast: 100Hz Diffusion Policy via Flow Matching" (2026-02-26)
  2. ⚡ "DiffVLA: Diffusion-based VLA for Contact-Rich Tasks" (2026-02-26)
  3. ⚡ "ReFlow-Bot: Rectified Flow for Dexterous Manipulation" (2026-02-27)
  4. ⚡ "ConsistencyVLA: Single-step Diffusion Policy Distillation" (2026-02-27)
  5. ⚡ "Diff-Act: Real-time Diffusion Actions for Mobile Robots" (2026-02-28)

Synthesis: Flow matching is replacing DDPM as the default diffusion backbone for VLA inference
speed. Likely triggered by π0-Fast releasing code — watch for implementation comparisons in 7d.
```

---

## Use Case 2: Social Volume Spike — Keyword Trending Across Multiple Sources Simultaneously

**Scenario**: The term "embodied AGI" suddenly appears on Huxiu, 36kr, CSDN, and two tracked Twitter accounts within the same day. No single source would trigger an alert, but the cross-source simultaneity is the signal.

**What happens**: The social spike detector aggregates keyword hit counts across all configured sources (tophub official API nodes: ithome, huxiu, 36kr, geekpark, sspai; tophub AJAX nodes: juejin, oschina; tracked Twitter accounts). When a keyword appears in 4+ distinct sources within 24 hours, it fires a social spike alert separate from the regular `ai-social-intel` report.

**Example**:
```
Social spike — 2026-02-28 | keyword: "embodied AGI"

Sources triggered (5/9):
  - huxiu: "具身AGI的技术路线之争" (3200 views)
  - 36kr: "具身智能会是下一个AGI突破口吗？" (2100 views)
  - sspai: "从VLA到具身AGI：2026年的机器人研究" (890 views)
  - twitter/@karol_hausman: "embodied AGI is closer than people think..."
  - twitter/@chelseafinnjm: "On embodied AGI: the grounding problem..."

Alert: Cross-source social spike detected. Recommend checking VLA pipeline for related ⚡ papers.
```

---

## Use Case 3: Citation Spike — Tracked Paper Accumulates Unusual GitHub Stars in 24 Hours

**Scenario**: A VLA paper that was rated 🔧 two weeks ago (solid but not breakthrough) suddenly gets 800 GitHub stars in a day after being featured in a popular ML newsletter. The researcher missed this because the pipeline does not re-rate old papers.

**What happens**: The spike detector maintains a watchlist of GitHub repos associated with rated papers (extracted from paper URLs/abstracts at rating time). A nightly job polls GitHub API for star/fork counts. A delta exceeding 3x the 7-day rolling average in a single 24-hour window triggers a "late breakout" alert, escalating the original 🔧 to ⚡ in the memory record and sending a Telegram alert with context.

**Example**:
```
Citation spike alert — 2026-02-28

Paper: "OpenVLA-OFT: Fine-tuning Toolkit for OpenVLA" (rated 🔧 on 2026-02-14)
Repo: github.com/openvla/oft

Stars delta (24h): +847 (7-day avg: 23/day → 36x spike)
Forks delta (24h): +134

Trigger: featured in "The Batch" newsletter + tweeted by @AndrewYNg

Action: rating upgraded 🔧 → ⚡ in vla-daily-hotspots-2026-02-28.json
Telegram alert sent to @original
```

---

## Use Case 4: Watchdog Miss + Spike Combo — Pipeline Failure During a Research Wave

**Scenario**: The VLA RSS cron job fails silently overnight (network timeout, no self-heal). On the same day, 4 ⚡ papers on tactile VLA are published. The researcher gets no Telegram message. When the spike detector finally runs the next day, it must surface both the pipeline failure and the missed spike together, with elevated urgency.

**What happens**: The spike detector checks for watchdog failure flags (`_watchdog_lock_{date}` stale, missing signal files) before running its normal analysis. If it detects a pipeline miss coinciding with a spike-eligible topic cluster, it generates an "elevated urgency" combined alert — higher priority than either event alone — and includes recovery instructions alongside the missed signal summary.

**Example**:
```
ELEVATED URGENCY — Pipeline miss + spike coincidence | 2026-02-28

Pipeline status: vla_rss FAILED (2026-02-28 — file missing, watchdog self-heal not triggered)

Retrospective spike (from RSS backfill):
  Topic: "tactile sensing / visuotactile"
  Papers missed on 2026-02-28:
    - ⚡ "Touch-VLA: Visuotactile Foundation Model for Dexterous Grasping"
    - ⚡ "GelSight-RT2: Tactile Integration in Large-Scale VLA"
    - 🔧 "Sim-to-Real Tactile Transfer via Domain Randomization"

Recovery steps:
  1. moltbot cron run <vla-rss-id> --force --timeout 180000 --expect-final
  2. moltbot cron run <vla-rating-id> --force --timeout 180000 --expect-final
  3. Verify: tail -n 50 /tmp/moltbot-gateway.log

Do not ignore: two ⚡ tactile papers missed on the same day is a significant coverage gap.
```

---

*See also: [Quality Drift Detector](quality-drift-detector.md), [Cross-domain Rule Engine](cross-domain-rule-engine.md), [MCP Server](mcp-server.md)*
