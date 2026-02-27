#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import datetime as _dt
import glob
import json
import os
import sys


MEM_DIR = "/home/admin/clawd/memory"


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _parse_date(s):
    try:
        return _dt.datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj, dry_run):
    if dry_run:
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _cutoff(days, today_s):
    d = _parse_date(today_s)
    if d is None:
        return None
    return d - _dt.timedelta(days=max(1, int(days)) - 1)


def _trim_list_records(path, list_key, keep_days, today_s, dry_run):
    obj = _read_json(path, {})
    rows = obj.get(list_key) if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return {"changed": False, "removed": 0, "kept": 0}

    lo = _cutoff(keep_days, today_s)
    if lo is None:
        return {"changed": False, "removed": 0, "kept": len(rows)}

    kept = []
    removed = 0
    for r in rows:
        if not isinstance(r, dict):
            kept.append(r)
            continue
        d = _parse_date(r.get("date"))
        if (d is not None) and (d < lo):
            removed += 1
            continue
        kept.append(r)

    changed = removed > 0
    if changed:
        obj[list_key] = kept
        _write_json_atomic(path, obj, dry_run)
    return {"changed": changed, "removed": removed, "kept": len(kept)}


def _slim_hotspots(path, keep_full_days, today_s, dry_run):
    obj = _read_json(path, {})
    rows = obj.get("reported_papers") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return {"changed": False, "slimmed": 0}
    lo = _cutoff(keep_full_days, today_s)
    if lo is None:
        return {"changed": False, "slimmed": 0}

    changed = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _parse_date(r.get("date"))
        if (d is None) or (d >= lo):
            continue
        if "abstract_snippet" in r and r.get("abstract_snippet"):
            r["abstract_snippet"] = ""
            changed += 1
        if "summary" in r and r.get("summary"):
            r["summary"] = ""
            changed += 1
        if "content" in r and r.get("content"):
            r["content"] = ""
            changed += 1
    if changed > 0:
        _write_json_atomic(path, obj, dry_run)
    return {"changed": changed > 0, "slimmed": changed}


def _cleanup_rss(pattern, keep_days, today_s, dry_run):
    today = _parse_date(today_s)
    if today is None:
        return {"changed": False, "removed": 0}
    rm = 0
    for p in glob.glob(pattern):
        base = os.path.basename(p)
        # Expect suffix date like xxx-YYYY-MM-DD.json
        d = None
        try:
            s = base[-15:-5]
            d = _dt.datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            d = None
        if d is None:
            continue
        age = (today - d).days
        if age >= int(keep_days):
            rm += 1
            if not dry_run:
                try:
                    os.remove(p)
                except Exception:
                    pass
    return {"changed": rm > 0, "removed": rm}


def main():
    ap = argparse.ArgumentParser(description="Memory lifecycle janitor")
    ap.add_argument("--today", default="", help="YYYY-MM-DD (default: Shanghai today)")
    ap.add_argument("--dry-run", action="store_true", help="Only report, do not write")
    args = ap.parse_args()

    today = (args.today or "").strip() or _today_shanghai()
    dry_run = bool(args.dry_run)

    actions = []
    issues = []

    try:
        ds = _trim_list_records(
            os.path.join(MEM_DIR, "daily-stats.json"),
            "daily_stats",
            keep_days=30,
            today_s=today,
            dry_run=dry_run,
        )
        actions.append("daily-stats: removed=%d kept=%d" % (ds["removed"], ds["kept"]))
    except Exception as e:
        issues.append("daily-stats: %s" % str(e)[:120])

    try:
        wd = _trim_list_records(
            os.path.join(MEM_DIR, "watchdog-log.json"),
            "watchdog_log",
            keep_days=30,
            today_s=today,
            dry_run=dry_run,
        )
        actions.append("watchdog-log: removed=%d kept=%d" % (wd["removed"], wd["kept"]))
    except Exception as e:
        issues.append("watchdog-log: %s" % str(e)[:120])

    try:
        slim = _slim_hotspots(
            os.path.join(MEM_DIR, "vla-daily-hotspots.json"),
            keep_full_days=14,
            today_s=today,
            dry_run=dry_run,
        )
        actions.append("vla-hotspots: slimmed_fields=%d" % slim["slimmed"])
    except Exception as e:
        issues.append("vla-hotspots: %s" % str(e)[:120])

    try:
        vla = _cleanup_rss(
            os.path.join(MEM_DIR, "vla-rss-*.json"),
            keep_days=3,
            today_s=today,
            dry_run=dry_run,
        )
        ai = _cleanup_rss(
            os.path.join(MEM_DIR, "ai-app-rss-*.json"),
            keep_days=3,
            today_s=today,
            dry_run=dry_run,
        )
        actions.append("rss-cleanup: removed=%d" % (int(vla["removed"]) + int(ai["removed"])))
    except Exception as e:
        issues.append("rss-cleanup: %s" % str(e)[:120])

    if issues:
        print("janitor issues:")
        for x in issues:
            print("- %s" % x)
        return 0

    # Silent on success in non-dry mode.
    if dry_run:
        print("dry-run")
        for x in actions:
            print("- %s" % x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
