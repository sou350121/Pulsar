#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate-shadow-config.py: P0 option_b shadow config evaluator.

Enforces safe config changes via a shadow staging workflow:
1. Read proposal JSON (--proposal-json)
2. Low risk: apply changes to shadow config → gate (cold-start, thesis shield) → promote to active config
3. Medium risk: append to pending changes (awaiting_approval), no active config change
4. Print single-line JSON summary and exit

Gates that prevent auto-promotion:
- Cold-start protection: if active-config.version <= 6, no keyword removals
- Thesis shield: keywords in assumptions.json cannot be removed
- Hit-window: keywords with recent hits cannot be removed

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import copy
import datetime as _dt
import json
import os
import sys


MEM_DIR = "/home/admin/clawd/memory"
ASSUMPTIONS_PATH = os.path.join(MEM_DIR, "assumptions.json")

DOMAIN_FILES = {
    "ai_app": {
        "active": os.path.join(MEM_DIR, "ai-app-active-config.json"),
        "shadow": os.path.join(MEM_DIR, "ai-app-shadow-active-config.json"),
        "pending": os.path.join(MEM_DIR, "ai-app-pending-changes.json"),
        "stats": os.path.join(MEM_DIR, "ai-app-daily-stats.json"),
    },
    "vla": {
        "active": os.path.join(MEM_DIR, "active-config.json"),
        "shadow": os.path.join(MEM_DIR, "shadow-active-config.json"),
        "pending": os.path.join(MEM_DIR, "pending-changes.json"),
        "stats": os.path.join(MEM_DIR, "vla-daily-hotspots.json"),
    },
}


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _load_thesis_shield_keywords():
    """Load keywords protected by assumptions (cannot be auto-removed)."""
    obj = _read_json(ASSUMPTIONS_PATH, {})
    shielded = set()
    assumptions = obj.get("assumptions") or []
    if not isinstance(assumptions, list):
        return shielded
    for a in assumptions:
        if not isinstance(a, dict):
            continue
        if a.get("status") not in ("active", None, ""):
            continue
        for kw in (a.get("keywords") or []):
            if isinstance(kw, str) and kw.strip():
                shielded.add(kw.strip().lower())
    return shielded


def _load_stats_recent_hits(stats_path, days=14):
    """Extract keywords that had hits in last N days (from daily stats)."""
    hits = set()
    today_dt = _dt.datetime.utcnow().date()
    cutoff = (today_dt - _dt.timedelta(days=days)).isoformat()
    obj = _read_json(stats_path, {})
    stats = obj.get("daily_stats") or []
    if not isinstance(stats, list):
        return hits
    for entry in stats:
        if not isinstance(entry, dict):
            continue
        date_str = entry.get("date", "")
        if date_str < cutoff:
            continue
        kw_hits = entry.get("keyword_hits") or {}
        if isinstance(kw_hits, dict):
            for kw, count in kw_hits.items():
                if count and count > 0:
                    hits.add(kw.strip().lower())
    return hits


def _apply_changes(config, changes):
    """Apply low-risk changes to config dict. Returns (modified_config, applied_list)."""
    cfg = copy.deepcopy(config)
    applied = []

    # Remove keywords_B
    for kw in (changes.get("remove_keywords_B") or []):
        kws = cfg.get("keywords_B") or []
        if kw in kws:
            kws.remove(kw)
            cfg["keywords_B"] = kws
            applied.append({"op": "remove_keywords_B", "value": kw})

    # Add keywords_B
    for kw in (changes.get("add_keywords_B") or []):
        kws = cfg.get("keywords_B") or []
        if kw not in kws:
            kws.append(kw)
            cfg["keywords_B"] = kws
            applied.append({"op": "add_keywords_B", "value": kw})

    # Add search_terms_social
    for term in (changes.get("add_search_terms_social") or []):
        terms = cfg.get("search_terms_social") or []
        if term not in terms:
            terms.append(term)
            cfg["search_terms_social"] = terms
            applied.append({"op": "add_search_terms_social", "value": term})

    # Remove search_terms_social
    for term in (changes.get("remove_search_terms_social") or []):
        terms = cfg.get("search_terms_social") or []
        if term in terms:
            terms.remove(term)
            cfg["search_terms_social"] = terms
            applied.append({"op": "remove_search_terms_social", "value": term})

    # Update rss_priority
    rss_priority = changes.get("rss_priority")
    if rss_priority and isinstance(rss_priority, dict):
        cfg["rss_priority"] = rss_priority
        applied.append({"op": "set_rss_priority"})

    # Add to learning_focus
    for item in (changes.get("add_learning_focus") or []):
        lf = cfg.get("learning_focus") or []
        if item not in lf:
            lf.append(item)
            cfg["learning_focus"] = lf
            applied.append({"op": "add_learning_focus", "value": item})

    return cfg, applied


def _gate_removal(kw, config_version, thesis_shield, recent_hits, gates_failed):
    """Check if removing kw passes all gates. Populates gates_failed list."""
    kw_lower = kw.strip().lower()

    # Cold-start protection
    if config_version <= 6:
        gates_failed.append(
            "cold_start_protection: version=%d <= 6, cannot remove B-keywords" % config_version)
        return False

    # Thesis shield
    if kw_lower in thesis_shield:
        gates_failed.append(
            "thesis_shield: '%s' is in assumptions.json" % kw)
        return False

    # Hit-window: keyword had hits in last 14 days
    if kw_lower in recent_hits:
        gates_failed.append(
            "hit_window: '%s' had hits in past 14 days" % kw)
        return False

    return True


def _handle_low_risk(proposal, domain_files, day, actor):
    """Apply low-risk changes through shadow → gate → promote."""
    active_path = domain_files["active"]
    shadow_path = domain_files["shadow"]
    stats_path = domain_files["stats"]

    config = _read_json(active_path, {})
    config_version = int(config.get("version") or 0)
    changes = proposal.get("changes") or {}

    # Load gating data
    thesis_shield = _load_thesis_shield_keywords()
    recent_hits = _load_stats_recent_hits(stats_path)

    # Gate each removal operation
    remove_kws = list(changes.get("remove_keywords_B") or [])
    blocked_removals = []
    gates_failed = []

    for kw in remove_kws:
        kw_gates = []
        if not _gate_removal(kw, config_version, thesis_shield, recent_hits, kw_gates):
            blocked_removals.append(kw)
            gates_failed.extend(kw_gates)

    # Remove blocked keywords from changes
    allowed_removals = [kw for kw in remove_kws if kw not in blocked_removals]
    changes_to_apply = dict(changes)
    changes_to_apply["remove_keywords_B"] = allowed_removals

    # Apply to shadow config
    shadow_cfg, applied = _apply_changes(config, changes_to_apply)

    if not applied:
        return {
            "decision": "no_change",
            "applied": [],
            "blocked": blocked_removals,
            "gates_failed": gates_failed,
            "new_version": config_version,
        }

    # Update shadow config metadata
    shadow_cfg["version"] = config_version + 1
    shadow_cfg["last_updated"] = day
    shadow_cfg["updated_by"] = "evaluate-shadow-config/auto/%s" % actor
    shadow_cfg["_shadow_from_version"] = config_version

    # Write shadow config
    _write_json_atomic(shadow_path, shadow_cfg)

    # Promote: copy shadow to active
    promote_cfg = copy.deepcopy(shadow_cfg)
    del promote_cfg["_shadow_from_version"]
    _write_json_atomic(active_path, promote_cfg)

    return {
        "decision": "promoted",
        "applied": applied,
        "blocked": blocked_removals,
        "gates_failed": gates_failed,
        "new_version": shadow_cfg["version"],
    }


def _handle_medium_risk(proposal, domain_files, day, actor):
    """Add medium-risk proposal to pending changes (awaiting_approval)."""
    pending_path = domain_files["pending"]
    obj = _read_json(pending_path, {"pending_changes": []})
    rows = obj.get("pending_changes")
    if not isinstance(rows, list):
        rows = []

    entry = {
        "date": day,
        "actor": actor,
        "risk": "medium",
        "status": "awaiting_approval",
        "rationale": (proposal.get("rationale") or "")[:500],
        "changes": proposal.get("changes") or {},
        "proposals": proposal.get("proposals") or {},
    }
    rows.append(entry)
    rows = rows[-50:]  # keep last 50 pending changes
    _write_json_atomic(pending_path, {"pending_changes": rows})

    return {
        "decision": "awaiting_approval",
        "pending_count": len(rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True,
                    choices=list(DOMAIN_FILES.keys()),
                    help="Config domain (ai_app or vla)")
    ap.add_argument("--actor", default="auto",
                    help="Who is making the change (e.g. J-AI)")
    ap.add_argument("--proposal-json", required=True,
                    help="Path to proposal JSON file")
    args = ap.parse_args()

    day = _today()
    domain_files = DOMAIN_FILES[args.domain]

    # Read proposal
    proposal = _read_json(args.proposal_json, None)
    if not isinstance(proposal, dict):
        print(json.dumps({
            "ok": False,
            "error": "invalid_proposal_json",
            "path": args.proposal_json,
        }, ensure_ascii=False))
        return 1

    risk = (proposal.get("risk") or "low").strip().lower()

    if risk == "low":
        result = _handle_low_risk(proposal, domain_files, day, args.actor)
    else:
        result = _handle_medium_risk(proposal, domain_files, day, args.actor)

    print(json.dumps({
        "ok": True,
        "date": day,
        "domain": args.domain,
        "actor": args.actor,
        "risk": risk,
        **result,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
