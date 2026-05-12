#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared configuration for GitHub Issues adoption sensor.

Used by:
  - collect-github-issues.py   (daily collection)
  - compute-gh-adoption.py     (weekly analysis)

No logic — constants only.  Python 3.6+.
"""

# ── Monitored Repos ───────────────────────────────────────────────────────────

# Curated from VLA-Handbook landscape.  Sorted by category then activity.
# "tier" controls collection frequency: 1=daily, 2=weekly-only.
REPOS = [
    # ── VLA Policy Models (core) ──────────────────────────────────────────
    {"owner": "huggingface",           "repo": "lerobot",                    "short": "lerobot",    "tier": 1,
     "methods": ["diffusion_policy", "cross_embodiment", "rl_finetuning"]},
    {"owner": "Physical-Intelligence", "repo": "openpi",                     "short": "openpi",     "tier": 1,
     "methods": ["flow_matching", "cross_embodiment", "language_grounding"]},
    {"owner": "openvla",               "repo": "openvla",                    "short": "openvla",    "tier": 1,
     "methods": ["language_grounding", "instruction_tuning", "multi_task"]},
    {"owner": "NVIDIA",                "repo": "Isaac-GR00T",                "short": "gr00t",      "tier": 1,
     "methods": ["cross_embodiment", "multi_task", "sim_to_real"]},
    {"owner": "thu-ml",                "repo": "RoboticsDiffusionTransformer","short": "rdt",       "tier": 2,
     "methods": ["diffusion_policy", "cross_embodiment"]},
    {"owner": "octo-models",           "repo": "octo",                       "short": "octo",       "tier": 2,
     "methods": ["cross_embodiment", "multi_task"]},
    {"owner": "microsoft",             "repo": "Magma",                      "short": "magma",      "tier": 2,
     "methods": ["language_grounding", "multi_task"]},
    {"owner": "InternRobotics",        "repo": "InternVLA-A1",               "short": "internvla",  "tier": 2,
     "methods": ["language_grounding", "instruction_tuning"]},
    {"owner": "MINT-SJTU",             "repo": "Evo-RL",                     "short": "evo-rl",     "tier": 2,
     "methods": ["rl_finetuning"]},
    # ── Imitation Learning Foundations ─────────────────────────────────────
    {"owner": "tonyzhaozh",            "repo": "act",                        "short": "act",        "tier": 2,
     "methods": ["instruction_tuning"]},
    {"owner": "tonyzhaozh",            "repo": "aloha",                      "short": "aloha",      "tier": 2,
     "methods": ["cross_embodiment"]},
    {"owner": "real-stanford",         "repo": "diffusion_policy",           "short": "diffpol",    "tier": 2,
     "methods": ["diffusion_policy"]},
    # ── Sim / Benchmark Ecosystem ─────────────────────────────────────────
    {"owner": "haosulab",              "repo": "ManiSkill",                  "short": "maniskill",  "tier": 1,
     "methods": ["sim_to_real", "multi_task"]},
    {"owner": "isaac-sim",             "repo": "IsaacLab",                   "short": "isaaclab",   "tier": 1,
     "methods": ["sim_to_real", "rl_finetuning"]},
    {"owner": "Genesis-Embodied-AI",   "repo": "Genesis",                    "short": "genesis",    "tier": 1,
     "methods": ["sim_to_real"]},
    {"owner": "google-deepmind",       "repo": "mujoco",                     "short": "mujoco",     "tier": 2,
     "methods": ["sim_to_real"]},
    {"owner": "Lifelong-Robot-Learning","repo": "LIBERO",                    "short": "libero",     "tier": 2,
     "methods": ["multi_task"]},
    {"owner": "ARISE-Initiative",      "repo": "robosuite",                  "short": "robosuite",  "tier": 2,
     "methods": ["sim_to_real"]},
    {"owner": "simpler-env",           "repo": "SimplerEnv",                 "short": "simplerenv", "tier": 2,
     "methods": ["sim_to_real"]},
    # ── Hardware / Motion Planning ────────────────────────────────────────
    {"owner": "unitreerobotics",       "repo": "unitree_rl_gym",             "short": "unitree-rl", "tier": 2,
     "methods": ["rl_finetuning", "sim_to_real"]},
    {"owner": "wuphilipp",             "repo": "gello_software",             "short": "gello",      "tier": 2,
     "methods": ["cross_embodiment"]},
]

# Convenience: tier-1 repos collected daily, tier-2 only on weekly runs
TIER1_REPOS = [r for r in REPOS if r.get("tier") == 1]
TIER2_REPOS = [r for r in REPOS if r.get("tier") == 2]

# ── Issue Category Classification ─────────────────────────────────────────────
# Regex applied to (title + body[:500]).lower().  First match wins.

CATEGORY_PATTERNS = [
    ("deploy",   r"\b(deploy|inference|latency|real.?time|onnx|tensorrt|quantiz|serving|trt)\b"),
    ("hardware", r"\b(gpu|cuda|oom|out.of.memory|vram|jetson|orin|nano|agx|thor)\b"),
    ("train",    r"\b(train|fine.?tun|overfit|loss|epoch|batch.?size|gradient|lr|learning.rate|checkpoint|resume|lora)\b"),
    ("data",     r"\b(dataset|data.?format|hdf5|lerobot.?dataset|replay|episode|record|teleop|mcap|rosbag)\b"),
    ("install",  r"\b(install|setup|pip|conda|import.?error|module.?not.?found|dependency|version.?mismatch)\b"),
    ("robot",    r"\b(robot|arm|gripper|servo|motor|urdf|action.?space|joint|real.?robot|so.?10[01]|aloha|panda)\b"),
    ("bug",      r"\b(bug|crash|error|exception|traceback|segfault|hang|freeze|deadlock)\b"),
    ("feature",  r"\b(feature.?request|enhancement|proposal|rfc|suggestion|wish)\b"),
]

# ── Hardware Platform Detection ───────────────────────────────────────────────

HARDWARE_PATTERNS = {
    "jetson_orin":    r"(?i)\b(jetson|orin|agx.?orin|nano.?super|orin.?nx|thor)\b",
    "raspberry_pi":   r"(?i)\b(raspberry|rpi|pi[- ]?[345])\b",
    "gpu_consumer":   r"(?i)\b(rtx.?[2345]\d{3}|gtx|geforce|3060|3070|3080|3090|4060|4070|4080|4090|5060|5070|5090)\b",
    "gpu_datacenter": r"(?i)\b(a100|h100|v100|a6000|l40|a40|b100|b200)\b",
    "apple_silicon":  r"(?i)\b(m[1-4]|apple.?silicon|mps)\b",
}

# ── Robot Platform Detection ──────────────────────────────────────────────────

ROBOT_PATTERNS = {
    "so100":   r"(?i)\b(so.?10[01])\b",
    "aloha":   r"(?i)\b(aloha)\b",
    "panda":   r"(?i)\b(panda|franka)\b",
    "ur5":     r"(?i)\b(ur[35]|ur10|universal.?robot)\b",
    "widowx":  r"(?i)\b(widowx|widow.?x)\b",
    "stretch": r"(?i)\b(stretch|hello.?robot)\b",
    "g1":      r"(?i)\b(unitree.?g1|g1.?robot)\b",
}

# ── Adoption Phase Keywords ───────────────────────────────────────────────────

PHASE_KEYWORDS = {
    "exploration": r"(?i)\b(how.?to|tutorial|example|getting.?started|beginner|documentation|question)\b",
    "integration": r"(?i)\b(custom|modify|extend|adapt|port|migration|our.?(robot|setup|data|environment)|fine.?tun)\b",
    "production":  r"(?i)\b(production|scale|fleet|deployment|reliability|uptime|monitoring|ci.?cd|real.?world)\b",
}

# ── DFI (Deployment Friction Index) ───────────────────────────────────────────

DFI_CATEGORY_WEIGHTS = {
    "deploy":   0.30,
    "hardware": 0.25,
    "install":  0.20,
    "train":    0.15,
    "data":     0.10,
}

DFI_LEVELS = {
    "low":      (0.0, 0.3),
    "moderate": (0.3, 0.6),
    "high":     (0.6, 1.0),
}

# ── Signal Level Thresholds ───────────────────────────────────────────────────

TIER1_MIN_COMMENTS = 8
TIER1_MIN_PARTICIPANTS = 3
TIER1_CRITICAL_PATTERN = r"(?i)\b(0%.?success|show.?stopper|major.?bug|regression|broken|does.?not.?work)\b"

TIER2_MIN_COMMENTS = 4
TIER2_MIN_PARTICIPANTS = 2

# ── API / Operational ─────────────────────────────────────────────────────────

API_DELAY_SECONDS = 0.2
MAX_ISSUES_PER_PAGE = 30
MAX_PAGES = 5
INDEX_MAX_ISSUES = 5000  # 21 repos, ~3 issues/day across tier-1
DAILY_SNAPSHOT_RETENTION_DAYS = 60
BODY_SNIPPET_LENGTH = 300
COMMENT_SNIPPET_LENGTH = 500
MAX_COMMENTS_FETCH = 10

# ── Paths ─────────────────────────────────────────────────────────────────────

import os
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = SCRIPT_DIR.parent / "memory"
TMP_DIR = MEMORY_DIR / "tmp"
INDEX_PATH = MEMORY_DIR / "gh-issues-index.json"
ENV_PATHS = [
    str(Path.home() / ".clawdbot" / ".env"),
    str(Path.home() / ".moltbot" / ".env"),
]
