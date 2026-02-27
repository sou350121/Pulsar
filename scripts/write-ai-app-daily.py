#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atomic helper: upsert today's entry in ai-app-daily.json,
keeping only the last 30 days (to avoid unbounded growth).

Usage:
    python3 write-ai-app-daily.py --date 2026-02-21 --items-json /tmp/items.json

items-json: a JSON file containing a list of item dicts.
Exits 0 on success, prints JSON result to stdout.
"""
import argparse
import datetime as _dt
import json
import os
import sys

MEM_DIR = "/home/admin/clawd/memory"
DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
KEEP_DAYS = 30


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--items-json", required=True, help="path to JSON file with items list")
    ap.add_argument("--config-version", type=int, default=0)
    args = ap.parse_args()

    today = args.date.strip()
    try:
        _dt.datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        print(json.dumps({"ok": False, "error": "bad_date", "value": today}))
        return 1

    try:
        with open(args.items_json, "r", encoding="utf-8") as f:
            new_items = json.load(f)
        if not isinstance(new_items, list):
            raise ValueError("items must be a list")
    except Exception as e:
        print(json.dumps({"ok": False, "error": "items_load_failed", "detail": str(e)}))
        return 1

    # Load existing
    existing = []
    if os.path.exists(DAILY_PATH):
        try:
            with open(DAILY_PATH, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                existing = obj.get("ai_app_daily", [])
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    # Prune to KEEP_DAYS
    try:
        cutoff = (_dt.datetime.strptime(today, "%Y-%m-%d") - _dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    except Exception:
        cutoff = "2000-01-01"

    kept = [e for e in existing if isinstance(e, dict) and e.get("date", "") >= cutoff and e.get("date", "") != today]

    new_entry = {
        "date": today,
        "config_version": args.config_version,
        "items": new_items,
    }
    kept.append(new_entry)
    kept.sort(key=lambda e: e.get("date", ""))

    payload = {"ai_app_daily": kept}
    # Atomic write: write to .tmp then rename to avoid corrupt file on crash
    tmp_path = DAILY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, DAILY_PATH)

    print(json.dumps({
        "ok": True,
        "date": today,
        "items_written": len(new_items),
        "total_days_in_file": len(kept),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
