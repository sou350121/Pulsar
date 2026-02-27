#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Weekly Deep Dive - Phase 1: Deterministic candidate extraction.

- Read past 7 days from AI App memory files (daily, picks, social intel, workflow)
- Filter and rank candidates
- Check past weekly digests for dedup
- Output candidates JSON for LLM article generation

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import sys


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")

DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
PICK_PATH = os.path.join(MEM_DIR, "ai-daily-pick.json")
SOCIAL_PATH = os.path.join(MEM_DIR, "ai-app-social-intel.json")
WORKFLOW_PATH = os.path.join(MEM_DIR, "ai-app-workflow-digest.json")
WEEKLY_DIGEST_PATH = os.path.join(MEM_DIR, "ai-weekly-digest.json")


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _date_in_range(date_str, cutoff):
    """Check if date_str >= cutoff (both YYYY-MM-DD)."""
    try:
        return date_str >= cutoff
    except Exception:
        return False


def _cutoff_date(day, days=7):
    try:
        d = _dt.datetime.strptime(day, "%Y-%m-%d")
        c = d - _dt.timedelta(days=days)
        return c.strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


# ------------------------------------------------------------------
# Dedup from past weekly digests
# ------------------------------------------------------------------

def _load_past_topics():
    """Return set of lowercase titles from past weekly digest entries."""
    digest = _read_json(WEEKLY_DIGEST_PATH, {"ai_weekly_digest": []})
    titles = set()
    for entry in (digest.get("ai_weekly_digest") or []):
        if not isinstance(entry, dict):
            continue
        for section in ("spotlight", "industry_moves",
                        "workflow_patterns", "developer_picks"):
            for it in (entry.get(section) or []):
                if isinstance(it, dict):
                    t = (it.get("title") or it.get("name") or
                         it.get("event") or it.get("summary") or "")
                    if t:
                        titles.add(t.strip().lower())
    return titles


# ------------------------------------------------------------------
# Extract candidates from memory files
# ------------------------------------------------------------------

def _extract_daily(cutoff, past_titles):
    """Extract items from ai-app-daily.json within date range."""
    data = _read_json(DAILY_PATH, {"ai_app_daily": []})
    items = []
    for entry in (data.get("ai_app_daily") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        for it in (entry.get("items") or []):
            if not isinstance(it, dict):
                continue
            title = (it.get("title") or it.get("name") or "").strip()
            if title.lower() in past_titles:
                continue
            items.append({
                "title": title,
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "category": it.get("category", ""),
                "summary": it.get("summary", ""),
                "date": d,
                "origin": "daily",
            })
    return items


def _extract_picks(cutoff, past_titles):
    """Extract items from ai-daily-pick.json within date range."""
    data = _read_json(PICK_PATH, {"daily_picks": []})
    items = []
    # Resolve to list of {date, items} entries; backward compat for old flat structure
    daily_picks = data.get("daily_picks")
    if isinstance(daily_picks, list):
        pick_entries = daily_picks
    elif data.get("date") and isinstance(data.get("items"), list):
        pick_entries = [data]
    else:
        pick_entries = []
    for entry in pick_entries:
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        for it in (entry.get("items") or []):
            if not isinstance(it, dict):
                continue
            title = (it.get("title") or it.get("name") or "").strip()
            if title.lower() in past_titles:
                continue
            items.append({
                "title": title,
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "category": it.get("category", ""),
                "summary": it.get("summary", ""),
                "date": d,
                "origin": "daily_pick",
            })
    return items


def _extract_social(cutoff, past_titles):
    """Extract signals from ai-app-social-intel.json within date range."""
    data = _read_json(SOCIAL_PATH, {"social_intel": []})
    items = []
    for entry in (data.get("social_intel") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        for sig in (entry.get("signals") or []):
            if not isinstance(sig, dict):
                continue
            summary = (sig.get("summary") or "").strip()
            if summary.lower() in past_titles:
                continue
            items.append({
                "type": sig.get("type", ""),
                "person_or_entity": sig.get("person_or_entity", ""),
                "summary": summary,
                "url": sig.get("url", ""),
                "signal_level": sig.get("signal_level", ""),
                "source": sig.get("source", ""),
                "date": d,
                "origin": "social_intel",
            })
    return items


def _extract_workflow(cutoff, past_titles):
    """Extract items from ai-app-workflow-digest.json within date range."""
    data = _read_json(WORKFLOW_PATH, {"workflow_digest": []})
    items = []
    for entry in (data.get("workflow_digest") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        for it in (entry.get("items") or []):
            if not isinstance(it, dict):
                continue
            title = (it.get("title") or "").strip()
            if title.lower() in past_titles:
                continue
            items.append({
                "title": title,
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "insight": it.get("insight", ""),
                "tags": it.get("tags", []),
                "date": d,
                "origin": "workflow",
            })
    return items


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--out", default="", help="Output path")
    ap.add_argument("--days", type=int, default=7, help="Lookback days")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out = (args.out.strip()
           or os.path.join(TMP_DIR, "ai-weekly-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    cutoff = _cutoff_date(day, args.days)
    past_titles = _load_past_topics()

    daily_items = _extract_daily(cutoff, past_titles)
    pick_items = _extract_picks(cutoff, past_titles)
    social_items = _extract_social(cutoff, past_titles)
    workflow_items = _extract_workflow(cutoff, past_titles)

    out_obj = {
        "ok": True,
        "date": day,
        "date_range": "%s to %s" % (cutoff, day),
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_type": "ai_weekly_deep_dive",
        "daily_items": daily_items,
        "pick_items": pick_items,
        "social_signals": social_items,
        "workflow_items": workflow_items,
        "stats": {
            "daily_count": len(daily_items),
            "pick_count": len(pick_items),
            "social_count": len(social_items),
            "workflow_count": len(workflow_items),
            "past_topics_excluded": len(past_titles),
        },
    }
    _write_json(out, out_obj)
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out,
        "daily": len(daily_items),
        "picks": len(pick_items),
        "social": len(social_items),
        "workflow": len(workflow_items),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
