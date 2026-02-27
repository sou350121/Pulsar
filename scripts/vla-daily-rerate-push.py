#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Daily Re-rate Push

Called by watchdog when:
  - Morning TG used keyword fallback (_vla_fallback_{day} exists)
  - Rating is now available (vla-daily-rating-out-{day}.json exists)
  - Not yet re-pushed (_vla_rerated_{day} does NOT exist)

Pushes an updated TG message with proper ⚡/🔧/📖 layout.
Python 3.6+
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys

MEM_DIR   = "/home/admin/clawd/memory"
TMP_DIR   = os.path.join(MEM_DIR, "tmp")
MOLTBOT   = "/home/admin/.local/share/pnpm/moltbot"
TG_TARGET = "1898430254"
TG_ACCOUNT= "original"


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _send_tg(text):
    cmd = [MOLTBOT, "message", "send",
           "--channel", "telegram",
           "--account", TG_ACCOUNT,
           "--target", TG_TARGET,
           "--message", text]
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=45, cwd="/home/admin", env=env,
                           universal_newlines=True)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def _paper_line(p, idx=None):
    title  = (p.get("title") or "").strip()
    url    = (p.get("url") or "").strip()
    reason = (p.get("reason") or "").strip()
    affil  = (p.get("affiliation") or "").strip()
    prefix = (affil + " ") if affil else ""
    num    = ("%d. " % idx) if idx is not None else ""
    short_url = url.replace("https://", "").replace("http://", "") if url else ""
    line = num + prefix + title
    parts = [line]
    if reason:
        parts.append("   _%s_" % reason)
    if short_url:
        parts.append("   %s" % short_url)
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    args = ap.parse_args()
    day = (args.date or _today()).strip()

    rating_path  = os.path.join(TMP_DIR, "vla-daily-rating-out-%s.json" % day)
    fallback_flag = os.path.join(TMP_DIR, "_vla_fallback_%s" % day)
    rerated_flag  = os.path.join(TMP_DIR, "_vla_rerated_%s" % day)

    if not os.path.exists(fallback_flag):
        print("[skip] no fallback flag for %s" % day)
        return 0
    if os.path.exists(rerated_flag):
        print("[skip] already re-pushed for %s" % day)
        return 0
    if not os.path.exists(rating_path):
        print("[skip] rating-out not available yet")
        return 0

    rating_result = _read_json(rating_path)
    if not (rating_result and rating_result.get("ok")):
        print("[error] rating-out invalid or ok=false")
        return 1

    rated_papers = rating_result.get("papers", [])
    strategic  = [p for p in rated_papers if p.get("rating") == "⚡"]
    actionable = [p for p in rated_papers if p.get("rating") == "🔧"]
    archive    = [p for p in rated_papers if p.get("rating") == "📖"]

    lines = ["📊 VLA 評分更新 | %s" % day, ""]

    if strategic:
        lines.append("⚡ 突破性進展")
        for i, p in enumerate(strategic, 1):
            lines.append(_paper_line(p, i))
            lines.append("")

    if actionable:
        lines.append("🔧 工程推薦")
        for i, p in enumerate(actionable[:5], 1):
            lines.append(_paper_line(p, i))
            lines.append("")
        if len(actionable) > 5:
            lines.append("… 等 %d 篇" % len(actionable))
            lines.append("")

    if not strategic and not actionable:
        lines.append("_今日無 ⚡/🔧 論文，見各評分_")
        lines.append("")

    counts = rating_result.get("counts", {})
    lines.append("評分：⚡%d 🔧%d 📖%d ❌%d" % (
        counts.get("⚡", 0), counts.get("🔧", 0),
        counts.get("📖", 0), counts.get("❌", 0)))

    text = "\n".join(lines).strip()
    ok, detail = _send_tg(text)
    if ok:
        # Mark as re-pushed
        try:
            open(rerated_flag, "w").write("ok")
        except Exception:
            pass
        print(json.dumps({"ok": True, "day": day,
                          "strategic": len(strategic),
                          "actionable": len(actionable)}))
        return 0
    else:
        print(json.dumps({"ok": False, "error": detail[:200]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
