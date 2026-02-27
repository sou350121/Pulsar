#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibration Check - Phase 1: Aggregate today's signals from all memory files.

Reads VLA + AI Agent daily pipeline outputs, extracts compact signal summaries,
and writes a single JSON candidate file for the LLM calibration check agent turn.

Python 3.6+ compatible (no external deps).
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import sys
import time

MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")

ASSUMPTIONS_PATH = os.path.join(MEM_DIR, "assumptions.json")

VLA_MEMORY_FILES = {
    "vla_rss":        "vla-rss-{date}.json",
    "vla_hotspots":   "vla-daily-hotspots.json",
    "vla_social":     "vla-social-intel.json",
    "vla_sota":       "vla-benchmark-sota.json",
    "vla_release":    "vla-release-tracker.json",
}

AI_MEMORY_FILES = {
    "ai_rss":         "ai-app-rss-{date}.json",
    "ai_daily":       "ai-app-daily.json",
    "ai_social":      "ai-app-social-intel.json",
    "ai_pick":        "ai-daily-pick.json",
}


def _today_shanghai():
    """Return today's date string in Asia/Shanghai (UTC+8)."""
    utc_now = _dt.datetime.utcnow()
    sh_now = utc_now + _dt.timedelta(hours=8)
    return sh_now.strftime("%Y-%m-%d")


def _read_json(path):
    """Read JSON file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _progress(msg):
    """Heartbeat to stdout (prevents agent kill)."""
    sys.stdout.write("[progress] %s\n" % msg)
    sys.stdout.flush()


def _extract_vla_rss(data, today):
    """Extract today's items from VLA RSS.
    File structure: {date, papers: [{title, url, abstract_snippet, ...}], total_fetched, ...}
    """
    if not isinstance(data, dict):
        return []
    # Real key is "papers"; fallback to "items"/"entries" for safety
    items = data.get("papers", data.get("items", data.get("entries", [])))
    if not isinstance(items, list):
        return []
    signals = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = it.get("title", "").strip()
        if not title:
            continue
        signals.append({
            "source": "VLA RSS",
            "title": title,
            "url": it.get("url", it.get("link", "")),
            "summary": it.get("summary", it.get("description", ""))[:300],
        })
    return signals[:40]


def _extract_vla_hotspots(data, today):
    """Extract today's papers from VLA Daily Hotspots."""
    if not isinstance(data, dict):
        return []
    papers = data.get("reported_papers", [])
    signals = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        pdate = (p.get("date") or "").strip()
        if pdate != today:
            continue
        if not p.get("in_report", True):
            continue
        signals.append({
            "source": "VLA Daily Hotspots",
            "title": p.get("title", ""),
            "url": p.get("url", ""),
            "summary": p.get("summary", p.get("tldr", ""))[:300],
        })
    return signals


def _extract_vla_social(data, today):
    """Extract today's signals from VLA Social Intelligence.
    File structure: {social_intel: [{date, signals: [{type, source, person_or_entity, summary}], dedup_note}]}
    """
    if not isinstance(data, dict):
        return []
    # Real key is "social_intel"; fallback to "reports" for safety
    reports = data.get("social_intel", data.get("reports", []))
    signals = []
    for r in reports:
        if not isinstance(r, dict):
            continue
        rdate = (r.get("date") or "").strip()
        if rdate != today:
            continue
        # Inner items are in "signals" field (post-vla-social.py writes this key)
        items = r.get("signals", r.get("items", []))
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    signals.append({
                        "source": "VLA Social Intel",
                        "title": it.get("person_or_entity", it.get("title", it.get("headline", ""))),
                        "url": it.get("url", ""),
                        "summary": it.get("summary", it.get("insight", ""))[:300],
                    })
    return signals[:20]


def _extract_vla_sota(data, today):
    """Extract recent SOTA changes.
    File structure: {"vla-sota-tracker": [{benchmark, split, metric, value, model, date, ...}]}
    """
    if not isinstance(data, dict):
        return []
    # Real key is "vla-sota-tracker"; fallback to "benchmarks" for safety
    benchmarks = data.get("vla-sota-tracker", data.get("benchmarks", []))
    signals = []
    for b in benchmarks:
        if not isinstance(b, dict):
            continue
        # Date field is "date" (not "last_updated")
        updated = (b.get("date") or b.get("last_updated") or "").strip()
        if updated != today:
            continue
        signals.append({
            "source": "VLA SOTA Tracker",
            "title": "SOTA change: %s" % b.get("benchmark", "?"),
            "summary": "Leader: %s (value: %s, metric: %s)" % (
                b.get("model", b.get("current_leader", "?")),
                b.get("value", b.get("current_score", "?")),
                b.get("metric", "?")),
        })
    return signals


def _extract_vla_release(data, today):
    """Extract today's release events."""
    if not isinstance(data, dict):
        return []
    seen = data.get("github-last-seen", {})
    signals = []
    for repo, info in seen.items():
        if not isinstance(info, dict):
            continue
        checked = (info.get("checked_at") or "").strip()
        if checked != today:
            continue
        tag = info.get("tag") or info.get("latest_tag") or info.get("latest_release", "")
        if tag:
            signals.append({
                "source": "VLA Release Tracker",
                "title": "Release: %s @ %s" % (repo, tag),
                "summary": info.get("release_notes", "")[:300],
            })
    return signals


def _extract_ai_rss(data, today):
    """Extract today's items from AI App RSS."""
    if not isinstance(data, dict):
        return []
    items = data.get("items", data.get("entries", []))
    if not isinstance(items, list):
        return []
    signals = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = it.get("title", "").strip()
        if not title:
            continue
        signals.append({
            "source": "AI App RSS",
            "title": title,
            "url": it.get("url", it.get("link", "")),
            "summary": it.get("summary", it.get("description", ""))[:300],
        })
    return signals[:40]


def _extract_ai_daily(data, today):
    """Extract today's daily report items.
    File structure: {ai_app_daily: [{date, config_version, items: [{title, category, url, summary}]}]}
    """
    if not isinstance(data, dict):
        return []
    # Real key is "ai_app_daily"; fallback to "daily_reports"/"reports" for safety
    reports = data.get("ai_app_daily", data.get("daily_reports", data.get("reports", [])))
    if not isinstance(reports, list):
        return []
    signals = []
    for r in reports:
        if not isinstance(r, dict):
            continue
        rdate = (r.get("date") or "").strip()
        if rdate != today:
            continue
        items = r.get("items", r.get("entries", []))
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    signals.append({
                        "source": "AI App Daily Report",
                        "title": it.get("title", it.get("name", "")),
                        "category": it.get("category", ""),
                        "url": it.get("url", ""),
                        "summary": it.get("summary", it.get("one_liner", ""))[:300],
                    })
    return signals


def _extract_ai_social(data, today):
    """Extract today's social intel items.
    File structure: {social_intel: [{date, signals: [{...}], dedup_note}]}
    """
    if not isinstance(data, dict):
        return []
    # Real key is "social_intel"; fallback to "reports" for safety
    reports = data.get("social_intel", data.get("reports", []))
    signals = []
    for r in reports:
        if not isinstance(r, dict):
            continue
        rdate = (r.get("date") or "").strip()
        if rdate != today:
            continue
        # Inner items are in "signals" field
        items = r.get("signals", r.get("items", []))
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    signals.append({
                        "source": "AI App Social Intel",
                        "title": it.get("title", it.get("headline", "")),
                        "url": it.get("url", ""),
                        "summary": it.get("summary", it.get("insight", ""))[:300],
                    })
    return signals[:20]


def _extract_ai_pick(data, today):
    """Extract today's daily picks."""
    if not isinstance(data, dict):
        return []
    picks = data.get("daily_picks", [])
    signals = []
    for p in picks:
        if not isinstance(p, dict):
            continue
        pdate = (p.get("date") or "").strip()
        if pdate != today:
            continue
        items = p.get("items", p.get("picks", []))
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    signals.append({
                        "source": "AI Daily Pick",
                        "title": it.get("title", it.get("name", "")),
                        "priority": it.get("priority", it.get("importance", "")),
                        "url": it.get("url", ""),
                        "summary": it.get("summary", it.get("reason", ""))[:300],
                    })
    return signals


EXTRACTORS = {
    "vla_rss":      _extract_vla_rss,
    "vla_hotspots": _extract_vla_hotspots,
    "vla_social":   _extract_vla_social,
    "vla_sota":     _extract_vla_sota,
    "vla_release":  _extract_vla_release,
    "ai_rss":       _extract_ai_rss,
    "ai_daily":     _extract_ai_daily,
    "ai_social":    _extract_ai_social,
    "ai_pick":      _extract_ai_pick,
}



# Signal source → domain mapping
VLA_SOURCE_KEYS = {"vla_rss", "vla_hotspots", "vla_social", "vla_sota", "vla_release"}
AI_SOURCE_KEYS  = {"ai_rss", "ai_daily", "ai_social", "ai_pick"}


def main():
    ap = argparse.ArgumentParser(description="Prep calibration check candidates")
    ap.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    args = ap.parse_args()

    today = args.date or _today_shanghai()
    _progress("calibration-prep start: %s" % today)

    os.makedirs(TMP_DIR, exist_ok=True)

    # Read assumptions
    assumptions_raw = _read_json(ASSUMPTIONS_PATH)
    if not assumptions_raw or not isinstance(assumptions_raw.get("assumptions"), list):
        print(json.dumps({"ok": False, "error": "cannot_read_assumptions"}))
        sys.exit(1)

    active = [a for a in assumptions_raw["assumptions"]
              if isinstance(a, dict) and a.get("status") == "active"]
    _progress("active assumptions: %d" % len(active))

    # Split assumptions by domain
    vla_assumptions    = [a for a in active if a.get("domain") == "vla"]
    ai_assumptions     = [a for a in active if a.get("domain") == "ai_agent"]
    # system + T-series (no domain or domain=="system") apply broadly
    system_assumptions = [a for a in active if a.get("domain") not in ("vla", "ai_agent")]
    _progress("assumptions split: vla=%d ai_agent=%d system=%d" % (
        len(vla_assumptions), len(ai_assumptions), len(system_assumptions)))

    # Collect signals from all memory files, track domain separately
    all_sources = {}
    all_sources.update(VLA_MEMORY_FILES)
    all_sources.update(AI_MEMORY_FILES)

    vla_signals = []
    ai_signals  = []
    source_stats = {}

    for key, filename_tpl in all_sources.items():
        filename = filename_tpl.replace("{date}", today)
        fpath = os.path.join(MEM_DIR, filename)
        data = _read_json(fpath)
        if data is None:
            source_stats[key] = 0
            continue

        extractor = EXTRACTORS.get(key)
        if extractor is None:
            source_stats[key] = 0
            continue

        signals = extractor(data, today)
        source_stats[key] = len(signals)
        if key in VLA_SOURCE_KEYS:
            vla_signals.extend(signals)
        else:
            ai_signals.extend(signals)
        _progress("  %s: %d signals" % (key, len(signals)))

    # Deduplicate within each domain bucket
    def _dedup(lst):
        seen = set()
        out = []
        for s in lst:
            k = (s.get("title") or "").strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(s)
        return out

    vla_signals = _dedup(vla_signals)
    ai_signals  = _dedup(ai_signals)
    all_signals = _dedup(vla_signals + ai_signals)

    _progress("signals: vla=%d ai=%d total=%d" % (
        len(vla_signals), len(ai_signals), len(all_signals)))


    # --- watch-list boost ---
    # If watch-list.json exists and non-empty, keyword-scan broader paper pool
    # and inject matched signals. Zero prompt changes needed.
    WATCH_PATH = os.path.join(MEM_DIR, "watch-list.json")
    watch_data = _read_json(WATCH_PATH)
    watch_items = (watch_data or {}).get("watch", [])
    if watch_items:
        _progress("watch-list: %d watched assumptions, running boost" % len(watch_items))
        # Load broader pools (all hotspot papers + today RSS)
        hs_all = (_read_json(os.path.join(MEM_DIR, "vla-daily-hotspots.json")) or {})
        hs_papers = hs_all.get("reported_papers", [])
        rss_data  = _read_json(os.path.join(MEM_DIR, "vla-rss-%s.json" % today)) or {}
        rss_papers = rss_data.get("papers", [])
        ai_rss_data = _read_json(os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today)) or {}
        ai_rss_items = ai_rss_data.get("items", [])

        existing_titles = set(s.get("title","").strip().lower() for s in vla_signals + ai_signals)

        for wi in watch_items:
            aid = wi.get("id", "?")
            domain = wi.get("domain", "vla")
            kws = [k.lower() for k in wi.get("keywords", []) if k]
            if not kws:
                continue
            injected = 0
            pool = (hs_papers + rss_papers) if domain == "vla" else ai_rss_items
            for p in pool:
                if injected >= 5:
                    break
                title = (p.get("title") or "").strip()
                if not title:
                    continue
                tl = title.lower()
                if tl in existing_titles:
                    continue
                if any(k in tl for k in kws):
                    sig = {
                        "source": "Watch Boost: %s" % aid,
                        "title": title,
                        "url": p.get("url", p.get("link", "")),
                        "summary": p.get("abstract_snippet", p.get("summary", ""))[:200],
                    }
                    if domain == "vla":
                        vla_signals.append(sig)
                    else:
                        ai_signals.append(sig)
                    existing_titles.add(tl)
                    injected += 1
            if injected:
                _progress("  watch boost %s: +%d signals" % (aid, injected))
        # re-dedup after boost
        vla_signals = _dedup(vla_signals)
        ai_signals  = _dedup(ai_signals)
        all_signals = _dedup(vla_signals + ai_signals)
        _progress("signals after boost: vla=%d ai=%d total=%d" % (
            len(vla_signals), len(ai_signals), len(all_signals)))
    # --- end watch-list boost ---

    # Build domain-separated output for richer LLM scanning
    output = {
        "ok": True,
        "date": today,
        "source_stats": source_stats,
        # Domain-separated sections (primary — LLM should scan these)
        "vla_section": {
            "description": "VLA / embodied-AI assumptions vs VLA signals only. Scan strictly within this domain.",
            "assumptions": vla_assumptions,
            "signals": vla_signals,
        },
        "ai_section": {
            "description": "AI Agent assumptions vs AI-App/Agent signals only. Scan strictly within this domain.",
            "assumptions": ai_assumptions,
            "signals": ai_signals,
        },
        "system_section": {
            "description": "System/pipeline assumptions. Cross-check against all signals.",
            "assumptions": system_assumptions,
            "signals": all_signals,
        },
        # Flat view kept for backward compat
        "assumptions_count": len(active),
        "signals_count": len(all_signals),
        "assumptions": active,
        "signals": all_signals,
    }

    out_path = os.path.join(TMP_DIR, "_calibration_candidates_%s.json" % today)
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)

    _progress("wrote %s (%d bytes)" % (out_path, os.path.getsize(out_path)))

    # Print summary to stdout (agent reads this)
    print(json.dumps({
        "ok": True,
        "date": today,
        "assumptions_count": len(active),
        "vla_assumptions": len(vla_assumptions),
        "ai_assumptions": len(ai_assumptions),
        "system_assumptions": len(system_assumptions),
        "vla_signals": len(vla_signals),
        "ai_signals": len(ai_signals),
        "total_signals": len(all_signals),
        "source_stats": source_stats,
        "candidates_path": out_path,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
