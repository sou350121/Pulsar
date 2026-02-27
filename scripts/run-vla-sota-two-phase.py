#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic runner for VLA SOTA tracker.

Flow:
1) prep-vla-sota.py  -> fetch Evo-SOTA data + detect changes
2) post-vla-sota.py  -> write memory + send Telegram update
   - changed: immediate update
   - no changes: weekly Friday snapshot

No LLM generation is used.
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys
from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-vla-sota.py"
POST = "/home/admin/clawd/scripts/post-vla-sota.py"
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


def _extract_json_obj(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"(\{.*\})", raw, re.S)
    if m:
        try:
            obj = json.loads(m.group(1))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _send_telegram(text, target="1898430254", account=""):
    if not text:
        return {"ok": True, "skipped": True}
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    rc, out, err = _run(cmd, timeout=45, label="vla-sota/telegram-alert")
    return {"ok": (rc == 0), "rc": rc, "out": (out or "")[:160], "err": (err or "")[:160]}


def _build_critical_alert(day, prep_detail):
    missing = prep_detail.get("critical_missing_sources") or []
    warnings = prep_detail.get("warnings")
    if isinstance(warnings, list):
        warn_list = warnings
    elif isinstance(warnings, (int, float)):
        warn_list = ["warnings_count=%s" % int(warnings)]
    elif warnings:
        warn_list = [str(warnings)]
    else:
        warn_list = []
    lines = [
        "🚨 VLA Benchmark SOTA Tracker 异常 | %s" % day,
        "",
        "错误: critical_source_missing",
    ]
    if missing:
        lines.append("缺失数据源: %s" % ", ".join(missing))
    if warn_list:
        # Keep message short but actionable.
        lines.append("详情: %s" % " | ".join([str(x)[:120] for x in warn_list[:4]]))
    lines.append("")
    lines.append("请检查 Evo-SOTA 数据源可用性与网络连通性。")
    return "\n".join(lines).strip()


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
    cands_path = os.path.join(TMP_DIR, "vla-sota-candidates-%s-%s.json" % (day, run_id))
    post_in_path = os.path.join(TMP_DIR, "vla-sota-post-input-%s-%s.json" % (day, run_id))

    print("[progress] Phase 1/2: running prep-vla-sota (fetching Evo-SOTA data + org resolution, ~60-90s)...", flush=True)
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path]
    rc, out, err = _run(prep_cmd, timeout=180, label="vla-sota/prep")
    print("[progress] Phase 1/2: prep-vla-sota finished (rc=%d)." % rc, flush=True)
    if rc != 0:
        prep_detail = _extract_json_obj(out) or {}
        if os.path.exists(cands_path):
            try:
                # Prefer full file payload (contains complete warning list).
                file_detail = _load_json(cands_path)
                if isinstance(file_detail, dict):
                    prep_detail = file_detail
            except Exception:
                pass

        is_critical = (
            prep_detail.get("error") == "critical_source_missing"
            or prep_detail.get("skip_reason") == "critical_source_missing"
            or bool(prep_detail.get("critical_missing_sources"))
        )
        if is_critical:
            alert = {"ok": True, "skipped": True}
            # Force alert when critical source is missing (unless dry-run).
            if not args.dry_run:
                alert_text = _build_critical_alert(day, prep_detail)
                alert = _send_telegram(
                    alert_text,
                    target=args.target.strip(),
                    account=args.account.strip(),
                )
            print(json.dumps({
                "ok": False,
                "error": "critical_source_missing",
                "prep_rc": rc,
                "critical_missing_sources": prep_detail.get("critical_missing_sources") or [],
                "warnings": prep_detail.get("warnings") or [],
                "forced_telegram_alert": alert,
            }, ensure_ascii=False))
            return 1

        print(json.dumps({
            "ok": False,
            "error": "prep_failed",
            "rc": rc,
            "prep_out": (out or "")[:260],
            "stderr": err[:300],
        }, ensure_ascii=False))
        return 1
    if not os.path.exists(cands_path):
        print(json.dumps({
            "ok": False,
            "error": "candidates_missing",
            "path": cands_path,
            "prep_out": out[:200],
        }, ensure_ascii=False))
        return 1

    cands = _load_json(cands_path)
    payload = {
        "date": day,
        "skip_reason": cands.get("skip_reason") or "",
        "items": cands.get("direct_items") or [],
        "snapshot_items": cands.get("snapshot_items") or [],
        "current_records": cands.get("current_records") or [],
        "focus_top5": cands.get("focus_top5") or {},
        "source": cands.get("source") or {},
        "counts": cands.get("counts") or {},
    }
    _write_json(post_in_path, payload)

    print("[progress] Phase 2/2: running post-vla-sota (memory + GitHub + Telegram)...", flush=True)
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

    rc, out, err = _run(post_cmd, timeout=120, label="vla-sota/post")
    print("[progress] Phase 2/2: post-vla-sota finished (rc=%d)." % rc, flush=True)
    if out.strip():
        print(out.strip())
    else:
        print(json.dumps({
            "ok": False,
            "error": "post_no_stdout",
            "rc": rc,
            "stderr": err[:260],
        }, ensure_ascii=False))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

