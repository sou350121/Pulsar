#!/usr/bin/env python3
"""
Agent Role-Switching module — P1 #5

Defines the four pipeline roles and their model assignments.
On 2GB RAM servers all roles must share the same loaded model
(simultaneous multi-model loading causes OOM). Configure via active-config.json
under the "roles" key. Default: every role uses qwen3.5-plus.

Usage in scripts:
    from _roles import load_role_config, role_model

    roles = load_role_config("vla")        # or "ai_app"
    model = role_model(roles, "analyst")   # "qwen3.5-plus"

⚠️  RAM warning: different model per role requires ≥ 4 GB RAM.
    Keep all roles on the same model until the server is upgraded.
"""

import json
import os

MEM_DIR        = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
DEFAULT_MODEL  = "qwen3.5-plus"

# Canonical role names and their pipeline stage descriptions
ROLE_STAGES = {
    "reader":   "RSS collect + signal filter (deterministic, no LLM)",
    "analyst":  "LLM synthesis — report, rating, social intel",
    "memory":   "Persistent-store writes (deterministic, no LLM)",
    "delivery": "TG / channel send (deterministic, no LLM)",
}

_DOMAIN_CONFIG = {
    "vla":    "active-config.json",
    "ai_app": "ai-app-active-config.json",
}


def load_role_config(domain: str) -> dict:
    """
    Return the roles dict for a domain.
    Falls back to DEFAULT_MODEL for any missing role.

    Returns: {role_name: model_id_or_None}
      - None means "no LLM for this role" (reader, memory, delivery by default).
      - A string means the LLM model ID to use.
    """
    cfg_file = _DOMAIN_CONFIG.get(domain)
    if cfg_file is None:
        raise ValueError(f"Unknown domain {domain!r}. Known: {list(_DOMAIN_CONFIG)}")
    path = os.path.join(MEM_DIR, cfg_file)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    raw = cfg.get("roles", {})
    # Normalise: each role is {model: ...} or just a string
    result = {}
    for role in ROLE_STAGES:
        entry = raw.get(role, {})
        if isinstance(entry, dict):
            result[role] = entry.get("model")  # None means no LLM
        elif isinstance(entry, str):
            result[role] = entry
        else:
            # Default: only analyst uses LLM
            result[role] = DEFAULT_MODEL if role == "analyst" else None
    return result


def role_model(roles: dict, role: str, fallback: str = DEFAULT_MODEL) -> str:
    """
    Return the model for a role, using fallback if the role has None or is missing.
    Call this in LLM scripts to respect role-level model targeting.

    Example:
        roles  = load_role_config("vla")
        model  = role_model(roles, "analyst")   # "qwen3.5-plus" by default
    """
    m = roles.get(role)
    return m if m is not None else fallback


if __name__ == "__main__":
    import sys
    domain = sys.argv[1] if len(sys.argv) > 1 else "vla"
    try:
        roles = load_role_config(domain)
        print(f"Domain: {domain}")
        for r, m in roles.items():
            label = m or "(no LLM)"
            print(f"  {r:10s} → {label}   # {ROLE_STAGES[r]}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
