#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic post-processor for AI Agent daily stats.

Purpose:
- Read today's AI daily report and RSS collection outputs
- Compute keyword/source statistics deterministically
- Upsert one entry into ai-app-daily-stats.json (atomic write)

Python 3.6 compatible.
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys


MEM_DIR = "/home/admin/clawd/memory"
AI_ACTIVE_CONFIG = os.path.join(MEM_DIR, "ai-app-active-config.json")
AI_DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
AI_STATS_PATH = os.path.join(MEM_DIR, "ai-app-daily-stats.json")


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _load_daily_items(day):
    obj = _read_json(AI_DAILY_PATH, {})
    rows = obj.get("ai_app_daily") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        if (rec.get("date") or "").strip() != day:
            continue
        items = rec.get("items")
        return items if isinstance(items, list) else []
    return []


def _all_keywords(cfg):
    out = []
    seen = set()
    for key in ("keywords_A", "keywords_B"):
        for kw in (cfg.get(key) or []):
            if not isinstance(kw, str):
                continue
            k = kw.strip()
            nk = _norm(k)
            if (not k) or (not nk) or (nk in seen):
                continue
            seen.add(nk)
            out.append(k)
    return out


def _compute_keywords_stats(day, cfg):
    rss_path = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % day)
    rss = _read_json(rss_path, {})
    rss_items = (rss.get("items") or []) if isinstance(rss, dict) else []
    if not isinstance(rss_items, list):
        rss_items = []

    all_kw = _all_keywords(cfg)
    hit = {}
    for kw in all_kw:
        hit[kw] = 0

    for it in rss_items:
        if not isinstance(it, dict):
            continue
        matched = it.get("keywords_matched")
        if not isinstance(matched, list):
            matched = []
        matched_norm = set()
        for m in matched:
            nm = _norm(str(m))
            if nm:
                matched_norm.add(nm)
        matched_text = " ".join([str(x) for x in matched]).lower()

        for kw in all_kw:
            nkw = _norm(kw)
            if not nkw:
                continue
            if (nkw in matched_norm) or (nkw in matched_text):
                hit[kw] = int(hit.get(kw, 0)) + 1

    miss = []
    for kw in (cfg.get("keywords_B") or []):
        if not isinstance(kw, str):
            continue
        k = kw.strip()
        if not k:
            continue
        if int(hit.get(k, 0)) == 0:
            miss.append(k)

    return hit, miss, rss, rss_items


def _build_blob(item):
    if not isinstance(item, dict):
        return ""
    labels = item.get("labels")
    if not isinstance(labels, list):
        labels = []
    parts = [
        item.get("title") or "",
        item.get("category") or "",
        item.get("developer") or "",
        item.get("why") or "",
        item.get("direction_note_prefix") or "",
        " ".join([str(x) for x in labels]),
    ]
    return _norm(" ".join([str(p) for p in parts if p]))


def _compute_focus_hit(cfg, report_items):
    fa = cfg.get("focus_areas") if isinstance(cfg, dict) else {}
    if not isinstance(fa, dict):
        return []

    blobs = []
    for it in report_items:
        b = _build_blob(it)
        if b:
            blobs.append(b)

    candidates = []
    primary = fa.get("primary")
    if isinstance(primary, dict):
        candidates.append(primary)
    for t in (fa.get("team") or []):
        if isinstance(t, dict):
            candidates.append(t)

    hits = []
    seen = set()
    for c in candidates:
        slug = (c.get("slug") or c.get("name") or "").strip()
        if not slug:
            continue
        keys = c.get("keywords")
        if not isinstance(keys, list):
            keys = []
        matched = False
        for kw in keys:
            nkw = _norm(str(kw))
            if not nkw:
                continue
            for b in blobs:
                if nkw in b:
                    matched = True
                    break
            if matched:
                break
        if matched:
            nslug = _norm(slug)
            if nslug not in seen:
                seen.add(nslug)
                hits.append(slug)
    return hits


def _compute_tags(report_items):
    tags = []
    seen = set()
    for it in report_items:
        if not isinstance(it, dict):
            continue
        labels = it.get("labels")
        if not isinstance(labels, list):
            continue
        for lb in labels:
            if not isinstance(lb, str):
                continue
            s = lb.strip()
            ns = _norm(s)
            if (not s) or (not ns) or (ns in seen):
                continue
            seen.add(ns)
            tags.append(s)
    return tags


def _compute_importance(report_items):
    out = {"read_only": 0, "actionable": 0, "strategic": 0}
    for it in report_items:
        if not isinstance(it, dict):
            continue
        imp = (it.get("importance") or "read-only").strip().lower().replace("-", "_")
        if imp not in out:
            imp = "read_only"
        out[imp] = int(out.get(imp, 0)) + 1
    return out


def _compute_sources_stats(rss, report_items):
    source_status = (rss.get("source_status") or {}) if isinstance(rss, dict) else {}
    if not isinstance(source_status, dict):
        source_status = {}

    sources_hit = {}
    for it in report_items:
        if not isinstance(it, dict):
            continue
        s = (it.get("source") or "unknown").strip() or "unknown"
        sources_hit[s] = int(sources_hit.get(s, 0)) + 1

    all_sources = sorted(set(list(source_status.keys()) + list(sources_hit.keys())))
    sources_zero = [s for s in all_sources if int(sources_hit.get(s, 0)) == 0]
    return sources_hit, sources_zero


def _upsert_stats(day):
    cfg = _read_json(AI_ACTIVE_CONFIG, {})
    report_items = _load_daily_items(day)
    if not report_items:
        raise ValueError("no_ai_app_daily_items_for_%s" % day)

    hit, miss, rss, rss_items = _compute_keywords_stats(day, cfg)
    sources_hit, sources_zero = _compute_sources_stats(rss, report_items)
    tags = _compute_tags(report_items)
    focus_hit = _compute_focus_hit(cfg, report_items)
    importance = _compute_importance(report_items)

    row = {
        "date": day,
        "config_version": int((cfg.get("version") or 0)),
        "total_items_scanned": int(rss.get("total_fetched") or 0),
        "total_after_filter": int(rss.get("after_filter") or len(rss_items)),
        "final_in_report": len(report_items),
        "tags": tags,
        "sources_hit": sources_hit,
        "focus_hit": focus_hit,
        "importance": importance,
        "keywords_hit": hit,
        "keywords_miss": miss,
        "sources_zero": sources_zero,
    }

    obj = _read_json(AI_STATS_PATH, {"daily_stats": []})
    rows = obj.get("daily_stats")
    if not isinstance(rows, list):
        rows = []

    replaced = False
    for i, rec in enumerate(rows):
        if isinstance(rec, dict) and (rec.get("date") or "").strip() == day:
            rows[i] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)

    rows = [x for x in rows if isinstance(x, dict) and (x.get("date") or "").strip()]
    rows.sort(key=lambda x: x.get("date") or "")
    rows = rows[-30:]

    _write_json_atomic(AI_STATS_PATH, {"daily_stats": rows})
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD; default Asia/Shanghai today")
    ap.add_argument("--dry-run", action="store_true", help="Compute only, do not write")
    args = ap.parse_args()

    day = (args.date or "").strip() or _today_shanghai()

    cfg = _read_json(AI_ACTIVE_CONFIG, {})
    report_items = _load_daily_items(day)
    if not report_items:
        print(
            json.dumps(
                {"ok": False, "date": day, "error": "no_ai_app_daily_items"},
                ensure_ascii=False,
            )
        )
        return 2

    try:
        if args.dry_run:
            hit, miss, rss, rss_items = _compute_keywords_stats(day, cfg)
            sources_hit, sources_zero = _compute_sources_stats(rss, report_items)
            row = {
                "date": day,
                "config_version": int((cfg.get("version") or 0)),
                "total_items_scanned": int(rss.get("total_fetched") or 0),
                "total_after_filter": int(rss.get("after_filter") or len(rss_items)),
                "final_in_report": len(report_items),
                "tags": _compute_tags(report_items),
                "sources_hit": sources_hit,
                "focus_hit": _compute_focus_hit(cfg, report_items),
                "importance": _compute_importance(report_items),
                "keywords_hit": hit,
                "keywords_miss": miss,
                "sources_zero": sources_zero,
            }
        else:
            row = _upsert_stats(day)
    except Exception as e:
        print(
            json.dumps(
                {"ok": False, "date": day, "error": "stats_upsert_failed", "detail": str(e)[:220]},
                ensure_ascii=False,
            )
        )
        return 1

    nonzero_kw = 0
    for v in (row.get("keywords_hit") or {}).values():
        try:
            if int(v) > 0:
                nonzero_kw += 1
        except Exception:
            continue

    print(
        json.dumps(
            {
                "ok": True,
                "date": day,
                "final_in_report": int(row.get("final_in_report") or 0),
                "keywords_nonzero": int(nonzero_kw),
                "sources_nonzero": len(row.get("sources_hit") or {}),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
