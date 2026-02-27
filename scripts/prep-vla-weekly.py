#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Weekly Deep Dive - Phase 1: Deterministic candidate extraction.

- Read past 7 days from VLA memory files (hotspots, SOTA, release, social)
- Rank and filter candidates
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

HOTSPOTS_PATH = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
SOTA_PATH = os.path.join(MEM_DIR, "vla-sota-tracker.json")
RELEASE_PATH = os.path.join(MEM_DIR, "vla-release-tracker.json")
SOCIAL_PATH = os.path.join(MEM_DIR, "vla-social-intel.json")
WEEKLY_DIGEST_PATH = os.path.join(MEM_DIR, "vla-weekly-digest.json")
THEORY_ARTICLES_PATH = os.path.join(MEM_DIR, "vla-theory-articles.json")

TAG_PRIORITY = {"strategic": 0, "actionable": 1, "read-only": 2}


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
    """Return the date string N days before `day`."""
    try:
        d = _dt.datetime.strptime(day, "%Y-%m-%d")
        c = d - _dt.timedelta(days=days)
        return c.strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


# ------------------------------------------------------------------
# Extract past topics from weekly digest (dedup)
# ------------------------------------------------------------------

def _load_past_topics():
    """Return set of lowercase titles from past weekly digest entries."""
    digest = _read_json(WEEKLY_DIGEST_PATH, {"vla_weekly_digest": []})
    titles = set()
    for entry in (digest.get("vla_weekly_digest") or []):
        if not isinstance(entry, dict):
            continue
        for section in ("paper_highlights", "sota_changes",
                        "releases", "social_signals"):
            for it in (entry.get(section) or []):
                if isinstance(it, dict):
                    t = (it.get("title") or it.get("model") or
                         it.get("event") or it.get("summary") or "")
                    if t:
                        titles.add(t.strip().lower())
    return titles


# ------------------------------------------------------------------
# Extract candidates from memory files
# ------------------------------------------------------------------

def _extract_papers(cutoff, past_titles):
    """Extract papers from vla-daily-hotspots.json within date range."""
    data = _read_json(HOTSPOTS_PATH, {"reported_papers": []})
    papers = []
    for p in (data.get("reported_papers") or []):
        if not isinstance(p, dict):
            continue
        d = p.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        title = (p.get("title") or "").strip()
        if title.lower() in past_titles:
            continue
        papers.append(p)

    # Sort by tag priority, then date (newest first)
    papers.sort(key=lambda x: (
        TAG_PRIORITY.get(x.get("tag", "read-only"), 9),
        x.get("date", "") + "z"  # reverse: negate not possible on str
    ))
    # For newest-first within same priority, reverse the date sort
    papers.sort(key=lambda x: TAG_PRIORITY.get(x.get("tag", "read-only"), 9))
    # Re-sort: priority asc, date desc
    papers.sort(key=lambda x: (
        TAG_PRIORITY.get(x.get("tag", "read-only"), 9),
        "".join(chr(255 - ord(c)) for c in x.get("date", "0000-00-00")),
    ))

    return papers[:15]  # top 15 candidates


def _extract_sota(cutoff, past_titles):
    """Extract SOTA changes within date range."""
    data = _read_json(SOTA_PATH, {})
    items = []
    for entry in (data.get("vla-sota-tracker") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        model = (entry.get("model") or "").strip()
        if model.lower() in past_titles:
            continue
        items.append({
            "benchmark": entry.get("benchmark", ""),
            "split": entry.get("split", ""),
            "metric": entry.get("metric", ""),
            "value": entry.get("value"),
            "model": model,
            "paper_id": entry.get("paper_id", ""),
            "baseline": entry.get("baseline", ""),
            "date": d,
        })
    return items


def _extract_releases(cutoff, past_titles):
    """Extract releases within date range."""
    data = _read_json(RELEASE_PATH, {})
    items = []
    for entry in (data.get("vla-release-tracker") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff):
            continue
        event = (entry.get("event") or "").strip()
        if event.lower() in past_titles:
            continue
        items.append({
            "source": entry.get("source", ""),
            "type": entry.get("type", ""),
            "event": event,
            "detail": entry.get("detail", ""),
            "url": entry.get("url", ""),
            "date": d,
        })
    return items


def _extract_theory_deep_dives(cutoff, day):
    """Extract theory deep dive articles written within date range."""
    data = _read_json(THEORY_ARTICLES_PATH, {"theory_articles": []})
    items = []
    for entry in (data.get("theory_articles") or []):
        if not isinstance(entry, dict):
            continue
        d = entry.get("date", "")
        if not _date_in_range(d, cutoff) or d > day:
            continue
        items.append({
            "title": entry.get("title", ""),
            "url": entry.get("url", ""),
            "github_path": entry.get("github_path", ""),
            "html_url": entry.get("html_url", ""),
            "tag": entry.get("tag", ""),
            "direction": entry.get("direction", ""),
            "date": d,
        })
    return items


def _extract_social(cutoff, past_titles):
    """Extract social signals within date range."""
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
                "source": sig.get("source", ""),
                "person_or_entity": sig.get("person_or_entity", ""),
                "summary": summary,
                "url": sig.get("url", ""),
                "signal_level": sig.get("signal_level", ""),
                "date": d,
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
           or os.path.join(TMP_DIR, "vla-weekly-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    cutoff = _cutoff_date(day, args.days)
    past_titles = _load_past_topics()

    papers = _extract_papers(cutoff, past_titles)
    sota = _extract_sota(cutoff, past_titles)
    releases = _extract_releases(cutoff, past_titles)
    social = _extract_social(cutoff, past_titles)
    theory_deep_dives = _extract_theory_deep_dives(cutoff, day)

    out_obj = {
        "ok": True,
        "date": day,
        "date_range": "%s to %s" % (cutoff, day),
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_type": "vla_weekly_deep_dive",
        "papers": papers,
        "sota_changes": sota,
        "releases": releases,
        "social_signals": social,
        "theory_deep_dives": theory_deep_dives,
        "stats": {
            "papers_count": len(papers),
            "sota_count": len(sota),
            "release_count": len(releases),
            "social_count": len(social),
            "theory_deep_dives_count": len(theory_deep_dives),
            "past_topics_excluded": len(past_titles),
        },
    }
    _write_json(out, out_obj)
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out,
        "papers": len(papers),
        "sota": len(sota),
        "releases": len(releases),
        "social": len(social),
        "theory_deep_dives": len(theory_deep_dives),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
