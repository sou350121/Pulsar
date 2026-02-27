#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Social Intelligence - Phase 3: Post (memory + Telegram).

- Upsert today's entry into memory/vla-social-intel.json (replace same date)
- Best-effort Telegram delivery

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
SOCIAL_PATH = os.path.join(MEM_DIR, "vla-social-intel.json")
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


def _sanitize_signals(signals):
    out = []
    if not isinstance(signals, list):
        return out
    for s in signals:
        if not isinstance(s, dict):
            continue
        out.append({
            "type": (s.get("type") or "").strip(),
            "source": (s.get("source") or "").strip(),
            "person_or_entity": (s.get("person_or_entity") or "").strip(),
            "summary": (s.get("summary") or "").strip(),
            "url": (s.get("url") or "").strip(),
            "signal_level": (s.get("signal_level") or "").strip(),
        })
    return out


def _upsert(day, signals):
    obj = _read_json(SOCIAL_PATH, {"social_intel": []})
    rows = obj.get("social_intel")
    if not isinstance(rows, list):
        rows = []

    # Overwrite protection: if LLM returned 0 signals but today already has signals,
    # skip upsert to avoid erasing good data (e.g., after a Perplexity outage retry).
    if not signals:
        for r in rows:
            if isinstance(r, dict) and (r.get("date") or "").strip() == day:
                existing_signals = r.get("signals") or []
                if isinstance(existing_signals, list) and existing_signals:
                    return {"ok": True, "skipped": True, "reason": "keep_existing_nonempty"}
                break

    entry = {"date": day, "signals": signals, "dedup_note": "two-phase-script"}

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
    rows = rows[-60:]
    _write_json_atomic(SOCIAL_PATH, {"social_intel": rows})
    return {"total": len(rows), "replaced": replaced}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--input", required=True)
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="original")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    payload = _read_json(args.input, {})
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "date": day, "error": "invalid_input_json"}, ensure_ascii=False))
        return 2

    signals = _sanitize_signals(payload.get("signals") or [])
    telegram_text = (payload.get("telegram_text") or "").strip()
    if (not telegram_text) and (not signals):
        telegram_text = "📡 今日 VLA 社交面無重大信號"

    if not args.dry_run:
        mem = _upsert(day, signals)
    else:
        mem = {"ok": True, "skipped": True}

    if args.dry_run or args.no_telegram:
        tg = {"ok": True, "skipped": True}
    else:
        tg = _send_telegram(
            telegram_text,
            target=(args.target or "").strip() or "1898430254",
            account=(args.account or "").strip(),
        )

    print(json.dumps({
        "ok": True,
        "date": day,
        "signals": len(signals),
        "memory": mem,
        "telegram": tg,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

