#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory-upsert.py — 通用 memory 文件累积写入器

功能：
  1. 从 stdin 读取 JSON 对象（必须含 "date" 字段）
  2. 读取目标 memory 文件（不存在则创建）
  3. 按 date 做 upsert（同日替换，异日追加）
  4. 自动清理超过 --max-days 天的旧条目
  5. 写回文件，输出 JSON 摘要到 stdout

用法：
  echo '{"date":"2026-02-15","items":[...]}' | \\
    python3 memory-upsert.py --file ai-app-daily.json --key ai_app_daily

  echo '{"date":"2026-02-15","items":[...]}' | \\
    python3 memory-upsert.py --file ai-daily-pick.json --key daily_picks

参数：
  --file    memory 文件名（相对于 MEM_DIR）
  --key     顶层 JSON key（列表容器名）
  --max-days  保留天数（默认 30）
  --dry-run   不实际写入
"""

import argparse
import datetime as _dt
import json
import os
import sys

MEM_DIR = "/home/admin/clawd/memory"


def _today_shanghai():
    utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return utc.astimezone(sh).strftime("%Y-%m-%d")


def _parse_date(s):
    """Parse YYYY-MM-DD string to date object, return None on failure."""
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser(description="Memory file upsert with accumulation and auto-prune")
    ap.add_argument("--file", required=True, help="Memory filename (relative to MEM_DIR)")
    ap.add_argument("--key", required=True, help="Top-level JSON key for the list")
    ap.add_argument("--max-days", type=int, default=30, help="Keep entries within N days (default: 30)")
    ap.add_argument("--dry-run", action="store_true", help="Don't write, just show what would happen")
    args = ap.parse_args()

    # 1. Read new entry from stdin
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            print(json.dumps({"ok": False, "error": "empty stdin"}))
            return 1
        new_entry = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"invalid JSON from stdin: {e}"}))
        return 1

    if not isinstance(new_entry, dict) or "date" not in new_entry:
        print(json.dumps({"ok": False, "error": "stdin JSON must be an object with 'date' field"}))
        return 1

    new_date = new_entry["date"]

    # 2. Read existing file
    filepath = os.path.join(MEM_DIR, args.file)
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    if not isinstance(existing, dict):
        existing = {}

    # 3. Get or create the list
    entries = existing.get(args.key, [])
    if not isinstance(entries, list):
        entries = []

    # 4. Upsert: replace same date, append otherwise
    replaced = False
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("date") == new_date:
            entries[i] = new_entry
            replaced = True
            break
    if not replaced:
        entries.append(new_entry)

    # 5. Sort by date (newest first for easy reading)
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)

    # 6. Prune old entries
    today = _parse_date(_today_shanghai())
    cutoff = today - _dt.timedelta(days=args.max_days) if today else None
    before_prune = len(entries)
    if cutoff:
        entries = [e for e in entries if _parse_date(e.get("date", "")) is None or _parse_date(e.get("date", "")) >= cutoff]
    pruned = before_prune - len(entries)

    # 7. Write back
    existing[args.key] = entries
    if not args.dry_run:
        tmp_path = filepath + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    # 8. Output summary
    result = {
        "ok": True,
        "file": args.file,
        "key": args.key,
        "date": new_date,
        "action": "replaced" if replaced else "appended",
        "total_entries": len(entries),
        "pruned": pruned,
        "dry_run": args.dry_run,
        "dates": [e.get("date", "?") for e in entries[:5]],
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
