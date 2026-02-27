#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic runner for VLA Release Tracker.

Flow:
1) prep-vla-release.py  -> Layer 1 GitHub Release + Layer 2 Web Search
2) post-vla-release.py  -> write memory + GitHub + Telegram

"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import sys
from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-vla-release.py"
POST = "/home/admin/clawd/scripts/post-vla-release.py"
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"
WORKDIR = "/home/admin"
TMP_DIR = "/home/admin/clawd/memory/tmp"


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _run(cmd, timeout=120, label="subprocess"):
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    return run_with_heartbeat(
        cmd=cmd,
        timeout=timeout,
        heartbeat_sec=20,
        label=label,
        cwd=WORKDIR,
        extra_env=env,
    )


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--target", default="1898430254", help="Telegram target")
    ap.add_argument("--account", default="", help="Telegram account (optional)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)

    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(TMP_DIR, "vla-release-candidates-%s-%s.json" % (day, run_id))
    post_in_path = os.path.join(TMP_DIR, "vla-release-post-input-%s-%s.json" % (day, run_id))

    # ── Phase 1: Prep ──
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path]
    print("[progress] Phase 1/2: prep-vla-release (~5min)...", flush=True)
    rc, out, err = _run(prep_cmd, timeout=300, label="vla-release/prep")  # Layer 2 web search may take time.
    print("[progress] Phase 1/2: step finished (rc=%d)." % rc, flush=True)
    if rc != 0:
        print(json.dumps({
            "ok": False,
            "error": "prep_failed",
            "rc": rc,
            "prep_out": (out or "")[:300],
            "stderr": (err or "")[:300],
        }, ensure_ascii=False))
        return 1

    if not os.path.exists(cands_path):
        print(json.dumps({
            "ok": False,
            "error": "candidates_missing",
            "path": cands_path,
            "prep_out": (out or "")[:200],
        }, ensure_ascii=False))
        return 1

    cands = _load_json(cands_path)
    payload = {
        "date": day,
        "items": cands.get("items") or [],
        "github_last_seen": cands.get("github_last_seen") or {},
        "counts": cands.get("counts") or {},
    }
    _write_json(post_in_path, payload)

    # ── Phase 2: Post ──
    post_cmd = [
        "python3", POST, "--date", day,
        "--input", post_in_path,
        "--target", args.target,
    ]
    if args.account:
        post_cmd.extend(["--account", args.account])
    if args.no_telegram:
        post_cmd.append("--no-telegram")
    if args.dry_run:
        post_cmd.append("--dry-run")

    print("[progress] Phase 2/2: post-vla-release (~2min)...", flush=True)
    rc, out, err = _run(post_cmd, timeout=120, label="vla-release/post")
    print("[progress] Phase 2/2: step finished (rc=%d)." % rc, flush=True)
    if out.strip():
        print(out.strip())
    else:
        print(json.dumps({
            "ok": False,
            "error": "post_no_stdout",
            "rc": rc,
            "stderr": (err or "")[:260],
        }, ensure_ascii=False))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
