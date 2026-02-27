#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build a papers JSON payload for gh-paper-index-update.py from vla-daily-hotspots.json.
Python 3.6+.

Output JSON:
  { "papers": [ {title,url,tag,repo_url,why?} ... ] }

Notes:
- 'why' is not available in hotspots memory; this script leaves it empty.
  The cron prompt may optionally post-process or fill it in.
"""

from __future__ import print_function

import argparse
import json
import os
import sys


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_lower(s):
    try:
        return (s or "").lower()
    except Exception:
        return ""


def _match_any_keywords(blob_lc, keywords):
    if not blob_lc or not keywords:
        return False
    for kw in keywords:
        k = _safe_lower(kw).strip()
        if not k:
            continue
        if k in blob_lc:
            return True
    return False


def _load_research_directions(path="/home/admin/clawd/memory/active-config.json"):
    try:
        cfg = _read_json(path)
    except Exception:
        return None
    rd = cfg.get("research_directions") if isinstance(cfg, dict) else None
    return rd if isinstance(rd, dict) else None


def _direction_note_prefix_for(paper, rd):
    """
    Returns (prefix, force_index_bool)
    - primary: "🎯 tactile |"
    - team: "[RL]" / "[VLA后训]" / "[世界模型]"
    """
    if not isinstance(rd, dict):
        return "", False

    title = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract_snippet") or "").strip()
    blob = (title + " " + abstract).strip()
    blob_lc = _safe_lower(blob)

    # primary first
    primary = rd.get("primary") if isinstance(rd.get("primary"), dict) else None
    if primary:
        if _match_any_keywords(blob_lc, primary.get("keywords") or []):
            return "🎯 tactile", True

    # team list
    team = rd.get("team") if isinstance(rd.get("team"), list) else []
    for t in team:
        if not isinstance(t, dict):
            continue
        kws = t.get("keywords") or []
        if not _match_any_keywords(blob_lc, kws):
            continue
        name = (t.get("name") or "").strip()
        if name == "RL 訓練 VLA":
            return "[RL]", True
        if name == "VLA 後訓練":
            return "[VLA后训]", True
        if name == "世界模型 + VLA":
            return "[世界模型]", True
        # fallback: use name as label if provided
        if name:
            return "[{n}]".format(n=name), True

    return "", False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--hotspots", default="/home/admin/clawd/memory/vla-daily-hotspots.json")
    ap.add_argument("--out", required=True, help="Output JSON path")
    args = ap.parse_args()

    today = args.date.strip()
    try:
        obj = _read_json(args.hotspots)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "hotspots_read_failed", "detail": str(e)}))
        return 2

    rd = _load_research_directions()

    papers = []
    for it in (obj.get("reported_papers") or []):
        if not isinstance(it, dict):
            continue
        if (it.get("date") or "").strip() != today:
            continue
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        tag = (it.get("tag") or "read-only").strip()
        repo_url = (it.get("repo_url") or "").strip()
        abstract_snippet = (it.get("abstract_snippet") or "").strip()
        if not title or not url:
            continue
        why = ""
        if tag == "strategic":
            # Best-effort: use abstract_snippet as the "one-line reason" if present.
            why = abstract_snippet
        out_it = {
            "title": title,
            "url": url,
            "tag": tag,
            "repo_url": repo_url if tag == "actionable" else "",
            "why": why,
            "abstract_snippet": abstract_snippet,
        }

        # Optional: direction tag prefix + force_index bypass (>8 rule)
        prefix, force_index = _direction_note_prefix_for(it, rd)
        if prefix:
            out_it["direction_note_prefix"] = prefix
        if force_index:
            out_it["force_index"] = True

        papers.append(out_it)

    out_obj = {"papers": papers}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(json.dumps({"ok": True, "count": len(papers), "out": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

