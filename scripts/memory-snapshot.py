#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Daily snapshot for memory and cron config.

- Archive: /home/admin/clawd/memory/*.json + /home/admin/.moltbot/cron/jobs.json
- Output:  /home/admin/clawd/memory/snapshots/YYYY-MM-DD.tar.gz
- Retain:  latest 14 days by default

Python: 3.6+
"""

from __future__ import print_function

import datetime as _dt
import glob
import os
import re
import sys
import tarfile


MEM_DIR = "/home/admin/clawd/memory"
CRON_FILE = "/home/admin/.moltbot/cron/jobs.json"
SNAP_DIR = "/home/admin/clawd/memory/snapshots"
DEFAULT_KEEP_DAYS = 14


def _today():
    # Keep it simple and aligned with server local time.
    return _dt.datetime.now().strftime("%Y-%m-%d")


def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _list_memory_json():
    return sorted(glob.glob(os.path.join(MEM_DIR, "*.json")))


def _archive_path(day):
    return os.path.join(SNAP_DIR, "%s.tar.gz" % day)


def _add_file_safe(tf, path, arcname):
    if os.path.isfile(path):
        tf.add(path, arcname=arcname, recursive=False)
        return True
    return False


def create_snapshot(day=None):
    day = day or _today()
    _ensure_dir(SNAP_DIR)
    out = _archive_path(day)

    mem_files = _list_memory_json()
    # Write to temp file then replace atomically.
    tmp_out = out + ".tmp"
    if os.path.exists(tmp_out):
        os.remove(tmp_out)

    added = 0
    with tarfile.open(tmp_out, "w:gz") as tf:
        for p in mem_files:
            rel = os.path.relpath(p, MEM_DIR)
            if _add_file_safe(tf, p, os.path.join("memory", rel)):
                added += 1
        if _add_file_safe(tf, CRON_FILE, os.path.join("cron", "jobs.json")):
            added += 1

    os.replace(tmp_out, out)
    return out, added


def _snapshot_day_from_name(name):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\.tar\.gz$", name or "")
    return m.group(1) if m else None


def cleanup_old(keep_days=DEFAULT_KEEP_DAYS, today=None):
    today_dt = _dt.datetime.strptime(today or _today(), "%Y-%m-%d").date()
    removed = []
    for p in sorted(glob.glob(os.path.join(SNAP_DIR, "*.tar.gz"))):
        name = os.path.basename(p)
        day = _snapshot_day_from_name(name)
        if not day:
            continue
        d = _dt.datetime.strptime(day, "%Y-%m-%d").date()
        age = (today_dt - d).days
        if age > int(keep_days):
            try:
                os.remove(p)
                removed.append(name)
            except Exception:
                pass
    return removed


def main():
    keep = DEFAULT_KEEP_DAYS
    if len(sys.argv) > 1:
        try:
            keep = int(sys.argv[1])
        except Exception:
            pass

    out, added = create_snapshot()
    removed = cleanup_old(keep_days=keep)
    # One-line summary keeps cron output readable.
    print("snapshot_ok file=%s added=%s removed=%s keep_days=%s" % (out, added, len(removed), keep))
    return 0


if __name__ == "__main__":
    sys.exit(main())

