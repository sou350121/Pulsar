# Agent Role-Switching — Use Cases

> **Status**: 📋 Planned | **Priority**: P1 | **Issue**: [#5](https://github.com/sou350121/Pulsar/issues/5)

Allows the pipeline's LLM calls (via qwen3.5-plus / DashScope) to adopt different expert personas within a single session, producing analysis from multiple cognitive stances rather than a single "neutral summarizer" voice.

---

## Use Case 1: Analyst to Devil's Advocate — Stress-testing Predictions Before Biweekly

**Scenario**: The researcher has drafted three confident predictions for the next VLA biweekly: "dexterous hand papers will dominate in March", "OpenVLA will release a fine-tuning toolkit", and "tactile sensing will reach billion-parameter scale". Before publishing, she wants to pressure-test them.

**What happens**: The biweekly generation script, after producing the "Analyst" pass, runs a second LLM call with the Devil's Advocate persona prompt. This role is instructed to assume each prediction will fail and argue why — surfacing hidden assumptions, missing evidence, and alternative trajectories. Both versions are included in the final report under separate sections.

**Example**:
```
[Analyst] Prediction: "Dexterous hand papers will surge in March given the RT-2 fine-tuning wave."

[Devil's Advocate] Counter: "The RT-2 wave peaked in hardware-simulation papers, not physical dexterous
hardware. Without sim-to-real transfer breakthroughs (none in past 30 days), physical dexterous
hand results are unlikely to scale. The more probable surge is in soft robotics grippers."

Outcome: researcher revises prediction to cover both dexterous + soft gripper trajectories.
```

---

## Use Case 2: Expert to Teacher — Explaining VLA Concepts to Non-specialists

**Scenario**: The researcher wants to share a VLA Hotspot summary with a collaborator from a software background who is unfamiliar with Vision-Language-Action models, diffusion policies, or robot learning terminology.

**What happens**: The MCP tool `get_vla_signals` accepts a `persona` parameter. When set to `"teacher"`, the downstream LLM call uses a prompt instructing it to explain each concept from first principles, avoid jargon without definition, and use real-world analogies. The Expert mode (default) uses dense technical language suited to a robotics PhD.

**Example**:
```
# Expert mode (default):
"RT-2-X achieved SOTA on OXE benchmark via cross-embodiment co-training with 22 robot morphologies,
improving generalization by 3.2x over single-embodiment baselines."

# Teacher mode (persona="teacher"):
"Imagine teaching a robot to cook by showing it videos from 22 different kitchens with different
stoves and layouts. RT-2-X does something similar — it trained on footage from 22 different robot
bodies, so it learned general 'how to move' principles rather than memorizing one specific arm.
Result: it handles new tasks 3x better than robots trained on just one setup."
```

---

## Use Case 3: Optimist vs Pessimist Dual-pass on a Paper Batch

**Scenario**: After collecting a week's VLA papers, the researcher wants a balanced view: which ones are genuinely exciting vs. which are overhyped. A single neutral summary often ends up blandly positive.

**What happens**: The rating step runs two sequential LLM calls (to stay within the 2 GB RAM constraint — never concurrent). The Optimist pass highlights the strongest claims, novel contributions, and practical impact. The Pessimist pass flags missing ablations, questionable benchmarks, and overclaimed generalization. The final rating reconciles both passes, and the output JSON includes both `optimist_note` and `pessimist_note` fields.

**Example**:
```json
{
  "paper": "UniGrasp-3B: Universal Grasping via VLA Scaling",
  "rating": "🔧",
  "optimist_note": "First VLA to demonstrate zero-shot grasping on 500+ unseen object categories. 3B params is deployable on edge hardware with quantization.",
  "pessimist_note": "All test objects are convex; no evaluation on deformable or transparent objects. Latency numbers measured on A100, not edge device. Real-world demo limited to lab setting.",
  "reconciled": "Solid engineering contribution, not a paradigm shift. Worth tracking for the zero-shot baseline."
}
```

---

## Use Case 4: Domain Specialist Persona — Robotics Hardware Expert for Manipulation Papers

**Scenario**: Most VLA papers evaluate on simulated or simplified manipulation tasks. The researcher wants a hardware-aware perspective: are the proposed methods actually feasible on real robot arms with torque limits, sensor noise, and cable management constraints?

**What happens**: A specialist persona prompt is loaded from `memory/personas/robotics-hardware.txt`. This persona is instructed to evaluate papers specifically through the lens of real-world hardware constraints — actuator bandwidth, payload, repeatability, sensor latency — and flag papers that make physically implausible claims even if their simulation numbers look strong.

**Example**:
```
[Robotics Hardware Expert on "DiffGrasp: 1kHz Diffusion Policy for Reactive Grasping"]

Hardware feasibility: ❌ Implausible as stated.
- 1 kHz control loop requires dedicated RT kernel; standard ROS2 runs at ~125 Hz.
- Authors used Franka Panda (max 1 kHz in FCI mode), but FCI requires Ethernet-only setup —
  not generalizable to wireless or CAN-bus robots.
- Torque noise at 1 kHz not reported; diffusion policy inference latency (~8ms on A100) would
  dominate at that frequency on edge hardware.

Recommendation: treat as simulation result; real deployment needs significant re-engineering.
```

---

*See also: [Quality Drift Detector](quality-drift-detector.md), [Cross-domain Rule Engine](cross-domain-rule-engine.md)*
