#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Weekly Deep Dive - Phase 3: Post-processor.

- Merge LLM output into memory/ai-weekly-digest.json (idempotent per-date upsert)
- Optionally send Telegram update using payload.telegram_text (best-effort)

GitHub push is intentionally skipped here to keep this job robust; deep-dive
articles are handled by the dedicated AI App Deep Dive pipeline.

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
WEEKLY_PATH = os.path.join(MEM_DIR, "ai-weekly-digest.json")
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


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


def _sanitize_entry(day, payload):
    # keep only expected top-level fields; tolerate extra fields
    out = dict(payload) if isinstance(payload, dict) else {}
    out["date"] = day
    # Normalization for lists
    for k in ("tldr", "spotlight", "industry_moves", "workflow_patterns", "developer_picks", "next_week_outlook"):
        v = out.get(k)
        if v is None:
            out[k] = []
        elif not isinstance(v, list):
            out[k] = []
    if not isinstance(out.get("date_range"), str):
        out["date_range"] = out.get("date_range") or ""
    return out


def _upsert_weekly(day, entry, dry_run=False):
    obj = _read_json(WEEKLY_PATH, {"ai_weekly_digest": []})
    rows = obj.get("ai_weekly_digest")
    if not isinstance(rows, list):
        rows = []

    replaced = False
    for i, r in enumerate(rows):
        if isinstance(r, dict) and (r.get("date") or "").strip() == day:
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)

    rows = [r for r in rows if isinstance(r, dict) and (r.get("date") or "").strip()]
    rows.sort(key=lambda x: (x.get("date") or ""))
    rows = rows[-52:]  # keep roughly a year

    out_obj = {"ai_weekly_digest": rows}
    if not dry_run:
        _write_json_atomic(WEEKLY_PATH, out_obj)
    return {"total": len(rows), "replaced": replaced}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--input", required=True)
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="ai_agent_dailybot")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    payload = _read_json(args.input, {})
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "date": day, "error": "invalid_input_json"}, ensure_ascii=False))
        return 2

    entry = _sanitize_entry(day, payload)
    try:
        up = _upsert_weekly(day, entry, dry_run=args.dry_run)
    except Exception as e:
        print(json.dumps({"ok": False, "date": day, "error": "weekly_write_failed", "detail": str(e)[:220]}, ensure_ascii=False))
        return 1

    tg_text = (payload.get("telegram_text") or "").strip()
    if args.dry_run or args.no_telegram or (not tg_text):
        tg = {"ok": True, "skipped": True}
    else:
        tg = _send_telegram(
            tg_text,
            target=(args.target or "").strip() or "1898430254",
            account=(args.account or "").strip(),
        )

    print(json.dumps({
        "ok": True,
        "date": day,
        "weekly": up,
        "telegram": tg,
        "github": {"ok": True, "skipped": True},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

