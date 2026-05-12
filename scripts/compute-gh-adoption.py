#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly GitHub adoption analysis for VLA repos.

Reads gh-issues-index.json, computes 4 mechanical patterns + 1 LLM synthesis.
~120s runtime, 1 LLM call.

Patterns:
  1. Adoption Phase Indicator (exploration/integration/production)
  2. Deployment Friction Index (DFI)
  3. Cross-repo Convergence
  4. Hardware Compatibility Matrix

Also identifies tier-1 candidates for event-driven surfacing.

Output:
  memory/gh-adoption-YYYY-MM-DD.json
  memory/tmp/gh-issues-tier1-candidates.json

Python 3.6+ (no external deps except _vla_expert for LLM).
"""

from __future__ import print_function

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _gh_issues_config import (
        REPOS, PHASE_KEYWORDS, DFI_CATEGORY_WEIGHTS, DFI_LEVELS,
        TIER1_MIN_COMMENTS, TIER1_MIN_PARTICIPANTS, TIER1_CRITICAL_PATTERN,
        TIER2_MIN_COMMENTS, MEMORY_DIR, TMP_DIR, INDEX_PATH,
    )
    from _vla_expert import call_qwen
except ImportError as e:
    print("Import error: %s" % e, file=sys.stderr)
    sys.exit(1)

TZ_CST = timezone(timedelta(hours=8))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_json(path, default=None):
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(str(tmp), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.rename(path)


def _issues_in_window(issues, days, ref_date=None):
    """Filter issues updated within last N days."""
    if ref_date is None:
        ref_date = datetime.now(timezone.utc)
    cutoff = (ref_date - timedelta(days=days)).strftime("%Y-%m-%d")
    return [
        v for v in issues.values()
        if v.get("updated_at", "")[:10] >= cutoff
    ]


def _issues_by_repo(issues_list, repo_short):
    return [i for i in issues_list if i.get("repo") == repo_short]


# ── Pattern 1: Adoption Phase ─────────────────────────────────────────────────


def compute_adoption_phase(issues_list, repo_short):
    """Compute adoption phase for a single repo."""
    repo_issues = _issues_by_repo(issues_list, repo_short)
    if not repo_issues:
        return {
            "repo": repo_short,
            "phase": "dormant",
            "scores": {"exploration": 0, "integration": 0, "production": 0},
            "dominant_ratio": 0,
            "sample_size": 0,
            "trend": "stalling",
        }

    scores = {}
    for phase, pat in PHASE_KEYWORDS.items():
        count = 0
        for iss in repo_issues:
            text = (iss.get("title", "") + " " + iss.get("body_snippet", "")).lower()
            if re.search(pat, text):
                count += 1
        scores[phase] = count

    total = sum(scores.values()) or 1
    ratios = {k: round(v / total, 2) for k, v in scores.items()}
    dominant = max(ratios, key=ratios.get)

    return {
        "repo": repo_short,
        "phase": dominant if ratios[dominant] > 0.1 else "mixed",
        "scores": ratios,
        "dominant_ratio": ratios[dominant],
        "sample_size": len(repo_issues),
        "trend": "stable",  # TODO: compare with 4-week-ago snapshot
    }


# ── Pattern 2: DFI ────────────────────────────────────────────────────────────


def compute_dfi(issues_list, repo_short):
    """Compute Deployment Friction Index for a single repo."""
    repo_issues = _issues_by_repo(issues_list, repo_short)
    if not repo_issues:
        return {
            "repo": repo_short,
            "dfi": 0.0,
            "level": "low",
            "breakdown": {},
            "top_friction": None,
            "trend_4w": 0.0,
            "sample_size": 0,
        }

    cat_counts = Counter(i.get("category", "other") for i in repo_issues)
    total = len(repo_issues) or 1

    breakdown = {}
    weighted_sum = 0.0
    for cat, weight in DFI_CATEGORY_WEIGHTS.items():
        ratio = cat_counts.get(cat, 0) / total
        contribution = ratio * weight
        breakdown[cat] = round(contribution, 3)
        weighted_sum += contribution

    # Normalize so max possible DFI = 1.0
    max_weight = sum(DFI_CATEGORY_WEIGHTS.values())
    dfi = round(min(weighted_sum / max_weight, 1.0), 3) if max_weight else 0.0

    # Determine level
    level = "low"
    for lbl, (lo, hi) in DFI_LEVELS.items():
        if lo <= dfi < hi:
            level = lbl
            break

    # Top friction source
    top_friction = max(breakdown, key=breakdown.get) if breakdown else None

    return {
        "repo": repo_short,
        "dfi": dfi,
        "level": level,
        "breakdown": breakdown,
        "top_friction": top_friction,
        "trend_4w": 0.0,  # TODO: compare with 4-week-ago snapshot
        "sample_size": len(repo_issues),
    }


# ── Pattern 3: Cross-repo Convergence ─────────────────────────────────────────


def _title_bigrams(title):
    """Extract lowercase bigrams from title."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return set(zip(words, words[1:])) if len(words) >= 2 else set()


def compute_convergence(issues_list):
    """Find cross-repo topic convergence via category + hardware overlap."""
    # Group by category
    cat_repos = defaultdict(lambda: defaultdict(list))
    for iss in issues_list:
        cat = iss.get("category", "other")
        repo = iss.get("repo", "")
        cat_repos[cat][repo].append(iss)

    patterns = []
    for cat, repos in cat_repos.items():
        if len(repos) < 2:
            continue
        # Only flag categories with issues in 2+ repos
        repo_names = sorted(repos.keys())
        issue_urls = []
        hw_union = set()
        for rn in repo_names:
            for iss in repos[rn][:3]:  # cap at 3 per repo
                issue_urls.append(iss.get("url", ""))
                hw_union.update(iss.get("hardware", []))

        total_count = sum(len(v) for v in repos.values())
        if total_count < 3:
            continue  # skip sparse convergence

        patterns.append({
            "pattern": "%s issues across %s" % (cat, "/".join(repo_names)),
            "category": cat,
            "repos": repo_names,
            "issue_count": total_count,
            "issue_urls": issue_urls[:6],
            "hardware": sorted(hw_union),
        })

    # Sort by issue count descending
    patterns.sort(key=lambda p: p["issue_count"], reverse=True)
    return patterns[:5]  # top 5


# ── Pattern 4: Hardware Matrix ────────────────────────────────────────────────


def compute_hardware_matrix(issues_list):
    """Build hardware compatibility matrix."""
    matrix = defaultdict(lambda: defaultdict(lambda: {"total": 0, "open": 0, "closed": 0}))

    for iss in issues_list:
        repo = iss.get("repo", "")
        state = iss.get("state", "open")
        for hw in iss.get("hardware", []):
            matrix[hw][repo]["total"] += 1
            matrix[hw][repo][state] += 1

    # Find worst compatibility (highest open rate)
    worst = []
    for hw, repos in matrix.items():
        for repo, counts in repos.items():
            if counts["total"] >= 2:
                open_rate = counts["open"] / counts["total"]
                worst.append({
                    "hardware": hw,
                    "repo": repo,
                    "total": counts["total"],
                    "open": counts["open"],
                    "open_rate": round(open_rate, 2),
                })
    worst.sort(key=lambda x: x["open_rate"], reverse=True)

    # Convert defaultdict to regular dict for JSON
    matrix_dict = {hw: dict(repos) for hw, repos in matrix.items()}
    for hw in matrix_dict:
        for repo in matrix_dict[hw]:
            matrix_dict[hw][repo] = dict(matrix_dict[hw][repo])

    return {
        "matrix": matrix_dict,
        "worst_compatibility": worst[:5],
    }


# ── Tier-1 Identification ────────────────────────────────────────────────────


def identify_tier1(issues_list, prev_surfaced):
    """Identify tier-1 issues for event-driven surfacing."""
    prev_urls = set(c.get("url", "") for c in prev_surfaced)
    candidates = []

    for iss in issues_list:
        url = iss.get("url", "")
        if url in prev_urls:
            continue

        comments = iss.get("comments_count", 0)
        title = iss.get("title", "")
        body = iss.get("body_snippet", "")
        text = title + " " + body

        reason = None
        # Check critical pattern
        if re.search(TIER1_CRITICAL_PATTERN, text) and comments >= 2:
            reason = "critical pattern + %d comments" % comments
        # Check comment threshold (participants estimated as comments/2)
        elif comments >= TIER1_MIN_COMMENTS:
            est_participants = max(2, comments // 3)
            if est_participants >= TIER1_MIN_PARTICIPANTS:
                reason = "%d comments, ~%d participants" % (comments, est_participants)

        if reason:
            # Find method families from repo
            repo_short = iss.get("repo", "")
            methods = []
            for rc in REPOS:
                if rc["short"] == repo_short:
                    methods = rc.get("methods", [])
                    break

            candidates.append({
                "url": url,
                "repo": repo_short,
                "number": iss.get("number", 0),
                "title": title,
                "category": iss.get("category", "other"),
                "comments_count": comments,
                "signal_level": "一级",
                "reason": reason,
                "method_families": methods,
                "surfaced_date": datetime.now(TZ_CST).strftime("%Y-%m-%d"),
                "injected": False,
            })

    return candidates


# ── Method Family Signals ─────────────────────────────────────────────────────


def compute_method_signals(issues_list):
    """Compute per-method-family issue activity."""
    signals = defaultdict(lambda: {"issue_count_7d": 0, "repos": set()})

    for iss in issues_list:
        repo_short = iss.get("repo", "")
        for rc in REPOS:
            if rc["short"] == repo_short:
                for method in rc.get("methods", []):
                    signals[method]["issue_count_7d"] += 1
                    signals[method]["repos"].add(repo_short)
                break

    # Convert sets to sorted lists
    return {
        method: {
            "issue_count_7d": data["issue_count_7d"],
            "repos": sorted(data["repos"]),
        }
        for method, data in signals.items()
    }


# ── LLM Synthesis ────────────────────────────────────────────────────────────


def synthesize_weekly(adoption, dfi, convergence, hardware, tier1):
    """Single LLM call to synthesize weekly GitHub community report."""
    # Build compact context
    lines = ["## 本週 VLA GitHub 社區機械化分析結果\n"]

    lines.append("### 採納階段")
    for a in adoption:
        lines.append("- %s: %s (樣本=%d, 主導比=%.0f%%)" % (
            a["repo"], a["phase"], a["sample_size"], a["dominant_ratio"] * 100
        ))

    lines.append("\n### 部署摩擦 (DFI)")
    for d in dfi:
        lines.append("- %s: DFI=%.2f (%s), 主要摩擦=%s" % (
            d["repo"], d["dfi"], d["level"], d.get("top_friction", "N/A")
        ))

    if convergence:
        lines.append("\n### 跨倉庫收斂")
        for c in convergence[:3]:
            lines.append("- %s: %d issues across %s" % (
                c["pattern"], c["issue_count"], "/".join(c["repos"])
            ))

    if hardware.get("worst_compatibility"):
        lines.append("\n### 硬件兼容性問題")
        for w in hardware["worst_compatibility"][:3]:
            lines.append("- %s × %s: %d issues, %d%% 未解決" % (
                w["hardware"], w["repo"], w["total"], int(w["open_rate"] * 100)
            ))

    if tier1:
        lines.append("\n### 一级發現")
        for t in tier1:
            lines.append("- %s #%d: %s (%s)" % (
                t["repo"], t["number"], t["title"][:60], t["reason"]
            ))

    context = "\n".join(lines)

    system_prompt = (
        "你是 VLA 領域的社區分析師。根據以下 4 個 VLA 開源倉庫的 GitHub Issues "
        "機械化分析結果，撰寫一段 ~600 字的「GitHub 社區脈搏」中文摘要。\n\n"
        "要求：\n"
        "1. 判斷各框架的採納階段和趨勢\n"
        "2. 指出最嚴重的部署摩擦和硬件兼容問題\n"
        "3. 如果有跨倉庫收斂或一级發現，重點標出\n"
        "4. 語氣客觀、數據驅動，避免主觀判斷\n"
        "5. 用「→」標記因果推論"
    )

    result = call_qwen(system_prompt, context, timeout=120, temperature=0.2)
    if result.get("ok"):
        return {
            "text": result["content"],
            "key_finding": "",  # extracted below
            "tokens_used": result.get("usage", {}).get("total_tokens", 0),
        }
    else:
        print("WARN: LLM synthesis failed: %s" % result.get("error", "unknown"),
              file=sys.stderr)
        return {
            "text": "LLM synthesis unavailable: %s" % result.get("error", ""),
            "key_finding": "",
            "tokens_used": 0,
        }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    t0 = time.time()
    today = datetime.now(TZ_CST).strftime("%Y-%m-%d")

    # 1. Load index
    index = _read_json(INDEX_PATH)
    if not index or not index.get("issues"):
        print("ERROR: gh-issues-index.json is empty or missing", file=sys.stderr)
        sys.exit(1)

    issues = index["issues"]
    print("Loaded %d issues from index" % len(issues))

    # 2. Filter windows
    issues_7d = _issues_in_window(issues, 7)
    issues_28d = _issues_in_window(issues, 28)
    print("7-day window: %d issues, 28-day window: %d issues" % (
        len(issues_7d), len(issues_28d)
    ))

    # 3. Compute patterns (7-day window)
    adoption = []
    dfi_results = []
    for rc in REPOS:
        short = rc["short"]
        adoption.append(compute_adoption_phase(issues_7d, short))
        dfi_results.append(compute_dfi(issues_7d, short))

    convergence = compute_convergence(issues_7d)
    hardware = compute_hardware_matrix(issues_7d)
    method_signals = compute_method_signals(issues_7d)

    # 4. Tier-1 identification
    prev_tier1_path = TMP_DIR / "gh-issues-tier1-candidates.json"
    prev_tier1 = _read_json(prev_tier1_path, {"candidates": []})
    tier1 = identify_tier1(issues_7d, prev_tier1.get("candidates", []))

    # Write tier1 candidates
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    tier1_out = {
        "date": today,
        "candidates": prev_tier1.get("candidates", []) + tier1,
    }
    # Keep only last 30 days of candidates
    cutoff = (datetime.now(TZ_CST) - timedelta(days=30)).strftime("%Y-%m-%d")
    tier1_out["candidates"] = [
        c for c in tier1_out["candidates"]
        if c.get("surfaced_date", "") >= cutoff
    ]
    atomic_write(prev_tier1_path, tier1_out)

    # 5. LLM synthesis
    print("Running LLM synthesis...")
    synthesis = synthesize_weekly(adoption, dfi_results, convergence, hardware, tier1)

    # 6. Assemble output
    output = {
        "date": today,
        "version": 1,
        "window_days": 7,
        "total_issues_analyzed": len(issues_7d),
        "adoption_phases": adoption,
        "dfi": dfi_results,
        "convergence": convergence,
        "hardware_matrix": hardware,
        "tier1_candidates": tier1,
        "method_family_signals": method_signals,
        "synthesis": synthesis,
        "runtime_seconds": round(time.time() - t0, 1),
    }

    # 7. Write output
    out_path = MEMORY_DIR / ("gh-adoption-%s.json" % today)
    atomic_write(out_path, output)

    # 8. Auto-update field notes on VLA-Handbook
    try:
        from importlib import import_module as _im
        _updater = _im("update-gh-field-notes")
        print("\nRunning field notes auto-update...")
        _updater.main()
    except Exception as e:
        # Also try direct import for Python 3.6 compat
        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "update_gh_field_notes",
                str(Path(__file__).resolve().parent / "update-gh-field-notes.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print("\nRunning field notes auto-update...")
            mod.main()
        except Exception as e2:
            print("WARN: field notes update skipped: %s" % e2, file=sys.stderr)

    # 9. Summary
    elapsed = round(time.time() - t0, 1)
    print("\n=== GitHub Adoption Analysis Complete ===")
    print("Date: %s | Issues analyzed: %d | Time: %ss" % (today, len(issues_7d), elapsed))
    for a in adoption:
        d = next((x for x in dfi_results if x["repo"] == a["repo"]), {})
        print("  %s: phase=%s DFI=%.2f(%s) sample=%d" % (
            a["repo"], a["phase"], d.get("dfi", 0), d.get("level", "?"), a["sample_size"]
        ))
    if convergence:
        print("  Convergence: %d patterns" % len(convergence))
    if tier1:
        print("  Tier-1: %d new candidates" % len(tier1))
    print("  Synthesis: %d tokens" % synthesis.get("tokens_used", 0))


if __name__ == "__main__":
    main()
