#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Release Tracker - Phase 2: Post-processor.

- Merge new release items into memory/vla-release-tracker.json (dedup + bounded)
- Update github-last-seen map
- Optionally send Telegram message (best-effort)

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
TRACKER_PATH = os.path.join(MEM_DIR, "vla-release-tracker.json")
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


def _dedup_key(it):
    if not isinstance(it, dict):
        return ""
    repo = (it.get("repo") or "").strip().lower()
    url = (it.get("url") or "").strip().lower().rstrip("/")
    event = (it.get("event") or "").strip().lower()
    date = (it.get("date") or "").strip()
    if url:
        return "url:%s" % url
    if repo and event:
        return "repo:%s|event:%s|date:%s" % (repo, event, date)
    return ""


def _merge_items(existing, new_items):
    rows = [x for x in (existing or []) if isinstance(x, dict)]
    seen = set()
    out = []
    # keep newest-first by stable sort later; first dedup by key
    for r in rows:
        k = _dedup_key(r)
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        out.append(r)
    added = 0
    for r in (new_items or []):
        if not isinstance(r, dict):
            continue
        k = _dedup_key(r)
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        out.append(r)
        added += 1
    # sort by date asc, then repo/event for determinism; keep last 200
    out.sort(key=lambda x: ((x.get("date") or ""), (x.get("repo") or ""), (x.get("event") or "")))
    if len(out) > 200:
        out = out[-200:]
    return out, added


def _build_telegram(day, items):
    lines = []
    lines.append("🧩 VLA Release Tracker | %s" % day)
    lines.append("")
    if not items:
        return ""
    lines.append("本次新增：%d" % len(items))
    lines.append("")
    for it in items[:8]:
        if not isinstance(it, dict):
            continue
        src = (it.get("source") or it.get("repo") or "").strip()
        ev = (it.get("event") or "").strip()
        url = (it.get("url") or "").strip()
        if src and ev:
            lines.append("- %s: %s" % (src, ev))
        elif ev:
            lines.append("- %s" % ev)
        elif src:
            lines.append("- %s" % src)
        if url:
            lines.append("  %s" % url)
    if len(items) > 8:
        lines.append("")
        lines.append("（其余 %d 条略）" % (len(items) - 8))
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

    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []
    github_last_seen = payload.get("github_last_seen") or payload.get("github-last-seen") or {}
    if not isinstance(github_last_seen, dict):
        github_last_seen = {}

    cur = _read_json(TRACKER_PATH, {"vla-release-tracker": [], "github-last-seen": {}})
    existing_items = cur.get("vla-release-tracker") if isinstance(cur, dict) else []
    merged, added = _merge_items(existing_items, items)

    out_obj = {
        "vla-release-tracker": merged,
        "github-last-seen": github_last_seen,
    }

    if not args.dry_run:
        _write_json_atomic(TRACKER_PATH, out_obj)

    tg_text = _build_telegram(day, items)
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
        "new_items": len(items),
        "added_to_tracker": added,
        "tracker_total": len(merged),
        "telegram": tg,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

