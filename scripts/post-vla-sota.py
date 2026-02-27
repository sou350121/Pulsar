#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Benchmark SOTA Tracker - Phase 2: Post-processor.

Responsibilities (deterministic, no LLM):
- Merge new SOTA rows into memory/vla-sota-tracker.json (idempotent per-day upsert)
- Optionally send a Telegram update (best-effort)

Input is produced by run-vla-sota-two-phase.py as JSON:
{
  "date": "YYYY-MM-DD",
  "skip_reason": "bootstrap|no_changes|...",
  "items": [...],           # direct change rows
  "snapshot_items": [...],  # bootstrap baseline
  "current_records": [...], # full current top-1 records
  "focus_top5": {...},      # richer weekly snapshot payload
  "source": {...},
  "counts": {...}
}

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
TRACKER_PATH = os.path.join(MEM_DIR, "vla-sota-tracker.json")
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _parse_date_ymd(s):
    try:
        return _dt.datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _is_friday_shanghai(day):
    d = _parse_date_ymd(day)
    if not d:
        return False
    # Monday=0 ... Sunday=6
    return d.weekday() == 4


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _row_key_for_day(row, day):
    if not isinstance(row, dict):
        return None
    bm = (row.get("benchmark") or "").strip()
    sp = (row.get("split") or "").strip()
    mt = (row.get("metric") or "").strip()
    if not bm or not mt:
        return None
    return (day, bm, sp, mt)


def _coerce_row(row, day):
    if not isinstance(row, dict):
        return None
    out = dict(row)
    out["date"] = day
    # Keep schema stable for downstream tools; don't drop extra fields.
    if "org" in out and out["org"] is None:
        out["org"] = ""
    return out


def _merge_tracker(day, new_rows, dry_run=False):
    obj = _read_json(TRACKER_PATH, {"vla-sota-tracker": [], "last_checked": ""})
    rows = obj.get("vla-sota-tracker")
    if not isinstance(rows, list):
        rows = []

    # Build index for idempotent upsert per-day per (benchmark,split,metric).
    drop_keys = set()
    for r in new_rows:
        k = _row_key_for_day(r, day)
        if k:
            drop_keys.add(k)

    kept = []
    dropped = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        k = _row_key_for_day(r, (r.get("date") or "").strip())
        # drop any existing row with same day+benchmark+split+metric that we're updating
        if k and (k in drop_keys):
            dropped += 1
            continue
        kept.append(r)

    added = 0
    for r in new_rows:
        rr = _coerce_row(r, day)
        if not rr:
            continue
        k = _row_key_for_day(rr, day)
        if not k:
            continue
        kept.append(rr)
        added += 1

    # Keep deterministic order
    def _sort_key(x):
        if not isinstance(x, dict):
            return ("", "", "", "", "")
        return (
            (x.get("date") or ""),
            (x.get("benchmark") or ""),
            (x.get("split") or ""),
            (x.get("metric") or ""),
            (x.get("model") or ""),
        )

    kept = [x for x in kept if isinstance(x, dict) and (x.get("benchmark") or "").strip()]
    kept.sort(key=_sort_key)

    # Bounded growth safety (should be small in practice)
    if len(kept) > 6000:
        kept = kept[-6000:]

    out_obj = {
        "vla-sota-tracker": kept,
        "last_checked": day,
    }
    if (not dry_run):
        _write_json_atomic(TRACKER_PATH, out_obj)
    return {"total": len(kept), "added": added, "replaced": dropped}


def _run(cmd, timeout=60, cwd="/home/admin"):
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return int(p.returncode), (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 125, "", str(e)


def _send_telegram(text, target="1898430254", account=""):
    if not text:
        return {"ok": True, "skipped": True}
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    rc, out, err = _run(cmd, timeout=45)
    msg_id = ""
    m = re.search(r"Message ID:\\s*(\\d+)", (out or "") + "\n" + (err or ""))
    if m:
        msg_id = m.group(1)
    return {
        "ok": (rc == 0),
        "rc": rc,
        "message_id": msg_id,
        "out": (out or "")[:200],
        "err": (err or "")[:200],
    }


def _fmt_row_line(r):
    bm = (r.get("benchmark") or "").strip()
    sp = (r.get("split") or "").strip()
    model = (r.get("model") or "").strip()
    org = (r.get("org") or "").strip()
    metric = (r.get("metric") or "").strip()
    val = r.get("value")
    try:
        v = float(val)
        val_s = ("%.2f" % v).rstrip("0").rstrip(".")
    except Exception:
        val_s = str(val)
    head = "%s%s" % (bm, (" / " + sp) if sp else "")
    tail = "%s=%s" % (metric, val_s) if metric else val_s
    who = model
    if org:
        who = "%s (%s)" % (model, org)
    return "- %s: %s | %s" % (head, who, tail)


def _build_weekly_snapshot_text(day, focus_top5, counts, tracker_total, skip_reason):
    lines = []
    lines.append("🏁 VLA Benchmark SOTA Tracker | %s" % day)
    lines.append("")
    lines.append("- 模式：weekly_snapshot")
    lines.append("- 跳过原因：%s" % (skip_reason or "no_changes"))
    lines.append("- 当前记录总数：%s" % int(tracker_total or 0))
    lines.append("")
    # Keep brief: only include focus benchmarks + top-3 rows each.
    if isinstance(focus_top5, dict) and focus_top5:
        keys = sorted([k for k in focus_top5.keys() if isinstance(k, str)])
        if keys:
            lines.append("🔎 重点榜单（Top）")
            for bm in keys[:3]:
                entry = focus_top5.get(bm) or {}
                if not isinstance(entry, dict):
                    continue
                lines.append("")
                lines.append("**%s**" % bm)
                for grp in (entry.get("groups") or [])[:3]:
                    if not isinstance(grp, dict):
                        continue
                    gname = (grp.get("group") or "overall").strip()
                    rows = grp.get("rows") or []
                    if not isinstance(rows, list) or not rows:
                        continue
                    lines.append("- %s" % gname)
                    for r in rows[:3]:
                        if not isinstance(r, dict):
                            continue
                        model = (r.get("model") or "").strip()
                        org = (r.get("org") or "").strip()
                        metric = (r.get("metric") or "").strip()
                        val = r.get("value")
                        try:
                            vv = float(val)
                            val_s = ("%.2f" % vv).rstrip("0").rstrip(".")
                        except Exception:
                            val_s = str(val)
                        if org:
                            lines.append("  - #%s %s (%s) | %s=%s" % (r.get("rank") or "", model, org, metric, val_s))
                        else:
                            lines.append("  - #%s %s | %s=%s" % (r.get("rank") or "", model, metric, val_s))
    return "\n".join(lines).strip()


def _build_direct_update_text(day, items, tracker_total):
    lines = []
    lines.append("⚡ VLA Benchmark SOTA Tracker 更新 | %s" % day)
    lines.append("")
    lines.append("检测到变更：%d 项" % len(items))
    lines.append("当前记录总数：%d" % int(tracker_total or 0))
    lines.append("")
    for r in items[:10]:
        if isinstance(r, dict):
            lines.append(_fmt_row_line(r))
    if len(items) > 10:
        lines.append("- ...（其余 %d 项略）" % (len(items) - 10))
    return "\n".join(lines).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--input", required=True)
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()

    payload = _read_json(args.input, {})
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "date": day, "error": "invalid_input_json"}, ensure_ascii=False))
        return 2

    skip_reason = (payload.get("skip_reason") or "").strip()
    items = payload.get("items") or []
    snapshot_items = payload.get("snapshot_items") or []
    current_records = payload.get("current_records") or []
    focus_top5 = payload.get("focus_top5") or {}
    counts = payload.get("counts") or {}

    if not isinstance(items, list):
        items = []
    if not isinstance(snapshot_items, list):
        snapshot_items = []
    if not isinstance(current_records, list):
        current_records = []

    mode = "no_changes"
    new_rows = []
    telegram_text = ""

    if items:
        mode = "direct_update"
        new_rows = items
    elif skip_reason == "bootstrap":
        mode = "bootstrap"
        new_rows = snapshot_items or current_records
    elif skip_reason == "no_changes" and _is_friday_shanghai(day):
        mode = "weekly_snapshot"
        new_rows = current_records
    else:
        mode = "no_changes"
        new_rows = []

    try:
        merge = _merge_tracker(day, new_rows, dry_run=args.dry_run)
    except Exception as e:
        print(json.dumps({"ok": False, "date": day, "error": "tracker_write_failed", "detail": str(e)[:220]}, ensure_ascii=False))
        return 1

    tracker_total = merge.get("total") or 0

    # Telegram is best-effort: failure should not fail the job.
    if mode == "direct_update":
        telegram_text = _build_direct_update_text(day, items, tracker_total)
    elif mode == "weekly_snapshot":
        telegram_text = _build_weekly_snapshot_text(day, focus_top5, counts, tracker_total, skip_reason)
    else:
        telegram_text = ""

    if args.dry_run or args.no_telegram or (not telegram_text):
        tg = {"ok": True, "skipped": True}
    else:
        tg = _send_telegram(
            telegram_text,
            target=(args.target or "").strip() or "1898430254",
            account=(args.account or "").strip(),
        )

    out = {
        "ok": True,
        "date": day,
        "mode": mode,
        "skip_reason": skip_reason,
        "tracker": merge,
        "telegram": tg,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

