#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Watchdog (验收与补跑)

原则（见 /root/52-daily-watchdog.md）：
- 只在异常/缺失时输出摘要；全 OK 时 stdout 为空（cron 将静默）。
- 按任务原路补：LLM 型任务只触发对应 cron job；collector 脚本可直接补齐。
- 不死循环：每项最多触发一次，并进入有限回读验收窗口。

Python 3.6+ (no external deps).

Changelog:
  2026-02-27 v6:
    - Add lockfile: prevent duplicate concurrent runs (OOM risk on 2GB server).
    - Add VLA Social Phase 3 orphan recovery: if llm-output tmp exists but
      social-intel missing for today → call post-vla-social.py directly, skip Phase 1+2.
    - Upgrade vla_sota check: was file-exists only; now checks last_checked == today.
    - Upgrade vla_release check: was file-exists only; now checks newest item date == today.
    - Add ai_deep_dive check: WARN if ai-app-deep-dive-articles.json newest entry >4 days old.
    - Add disk_space check: WARN >=85%, FAIL >=95% full.
  2026-02-27 v5:
    - Fix _check_ai_daily_pick: schema is {"daily_picks":[{date,items}]}, not top-level date/items.
    - Fix _check_theory_articles: schema is {"theory_articles":[...]}, not {"articles":[...]}.
  2026-02-27 v4:
    - Add SIGTERM/SIGINT handler: write partial log + summary before dying (fixes silent kill).
  2026-02-27 v3:
    - Fix _cron_run: add --expect-final flag (without it moltbot hangs → TimeoutExpired → crash).
    - Fix _run: catch TimeoutExpired + Exception so crashes don't propagate to main().
    - Add early-hour guard (hour < 9 Shanghai): skip remediation before jobs are scheduled.
  2026-02-23 v2:
    - Add _check_gateway_health(): if Gateway is down, exit immediately
      instead of wasting 12+ minutes triggering jobs that will never run.
    - Add dependency-aware triggering DAG (rss→daily→social):
      if RSS failed, skip downstream daily/social triggers (saves LLM budget).
    - Add structural validation: check item counts, not just date presence.
      Distinguishes FAIL (structure broken) from WARN (0 signals, quality issue).
    - Add per-job timeouts dict (Theory=25min, RSS=5min, Daily=15min).
    - Add WATCHDOG SUMMARY line at end for at-a-glance status.
    - Improve collector success check: verify output file created, not just rc=0.
"""

from __future__ import print_function

import datetime as _dt
import json
import os
import signal
import socket
import subprocess
import sys
import time


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
LOG_PATH = os.path.join(MEM_DIR, "watchdog-log.json")

MOLTBOT = "/home/admin/.local/share/pnpm/moltbot"
GATEWAY_PORT = 18789
POST_VLA_SOCIAL = "/home/admin/clawd/scripts/post-vla-social.py"

# Job IDs (from /root/52-daily-watchdog.md)
JOBS = {
    "vla_rss": "55f14513-f512-43d0-8d54-43275edc6f9a",
    "vla_daily": "a63e051a-5813-4069-b2ae-15967709a7a1",
    "vla_social": "e170613a-61b2-4fb4-9b15-268a4c8d76d8",
    "vla_sota": "3aeb6134-a2c9-42af-9281-38b79bb188e2",
    "vla_release": "2ec9125b-3867-49b0-9f8b-940ad2201350",
    "aiapp_rss": "4ab47b1d-0c40-4c19-bc67-ccfc7fb0306b",
    "aiapp_daily": "63fd9053-136a-4c93-9a6d-ae7ce91b146b",
    "aiapp_social": "1212c84c-e49e-4a49-864c-00b33c3e5aa0",
    "ai_daily_pick": "65669bf4-2383-46b0-9c6f-5a79bce98252",
    "gateway_preflight": "6b71e0af-4d5f-4f9c-9db6-e7e875f86f8b",
}

# Per-job timeout overrides (ms). Default 10 minutes if not specified.
JOB_TIMEOUTS_MS = {
    "vla_rss": 5 * 60 * 1000,
    "aiapp_rss": 5 * 60 * 1000,
    "vla_daily": 15 * 60 * 1000,
    "aiapp_daily": 15 * 60 * 1000,
    "vla_social": 12 * 60 * 1000,
    "aiapp_social": 12 * 60 * 1000,
    "vla_sota": 12 * 60 * 1000,
    "vla_release": 12 * 60 * 1000,
    "ai_daily_pick": 15 * 60 * 1000,
    "gateway_preflight": 3 * 60 * 1000,
}
DEFAULT_JOB_TIMEOUT_MS = 10 * 60 * 1000

# Collector scripts (direct补齐)
SCRIPTS = {
    "vla_rss_collect": "/home/admin/clawd/scripts/vla-rss-collect.py",
    "aiapp_rss_collect": "/home/admin/clawd/scripts/ai-app-rss-collect.py",
}


def _now_shanghai():
    return _dt.datetime.utcnow() + _dt.timedelta(hours=8)


def _today():
    return _now_shanghai().strftime("%Y-%m-%d")


def _progress(msg):
    sys.stdout.write("[progress] %s\n" % msg)
    sys.stdout.flush()


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _append_watchdog_log(entry):
    data = _read_json(LOG_PATH)
    if not isinstance(data, dict):
        data = {"entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    data["entries"].append(entry)
    data["entries"] = data["entries"][-60:]
    _write_json_atomic(LOG_PATH, data)


def _run(cmd, timeout=120):
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
            env=env,
        )
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "", "subprocess timed out after %ds" % timeout
    except Exception as e:
        return -1, "", "subprocess error: %s" % str(e)[:200]


def _check_gateway_health():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        result = s.connect_ex(("127.0.0.1", GATEWAY_PORT))
        s.close()
        if result == 0:
            return True, ""
        return False, "port %d not accepting connections (errno %d)" % (GATEWAY_PORT, result)
    except Exception as e:
        return False, str(e)[:100]


def _cron_run(job_key, timeout_ms=None):
    job_id = JOBS.get(job_key, job_key)
    if timeout_ms is None:
        timeout_ms = JOB_TIMEOUTS_MS.get(job_key, DEFAULT_JOB_TIMEOUT_MS)
    cmd = [
        MOLTBOT, "cron", "run", job_id, "--force",
        "--timeout", str(int(timeout_ms)),
        "--expect-final",
    ]
    wait_sec = max(60, int(timeout_ms / 1000) + 30)
    rc, out, err = _run(cmd, timeout=wait_sec)
    ran_true = ("\"ran\": true" in out) or ("\"ran\": true" in err)
    ok = (rc == 0) and ran_true
    return ok, out, err


def _run_collector(script_key, out_path, timeout=240):
    script = SCRIPTS.get(script_key)
    if not script or not os.path.exists(script):
        return False, "script not found: %s" % script
    before_mtime = None
    try:
        before_mtime = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    except Exception:
        pass
    rc, out, err = _run(["python3", script], timeout=timeout)
    if rc != 0:
        return False, "rc=%d: %s" % (rc, (err or out)[:100])
    try:
        after_mtime = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    except Exception:
        after_mtime = None
    if after_mtime is None:
        return False, "output file not created: %s" % out_path
    if before_mtime is not None and after_mtime <= before_mtime:
        return False, "output file not updated (same mtime): %s" % out_path
    return True, ""


def _file_exists(path):
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        return False


# ── Check functions ──────────────────────────────────────────────────────────

def _check_ai_daily_pick(today):
    p = os.path.join(MEM_DIR, "ai-daily-pick.json")
    obj = _read_json(p)
    if not isinstance(obj, dict):
        return False, "FAIL", "missing or invalid ai-daily-pick.json"
    picks = obj.get("daily_picks", [])
    for entry in picks:
        if isinstance(entry, dict) and (entry.get("date") or "").strip() == today:
            items = entry.get("items", [])
            if not items:
                return False, "WARN", "ai-daily-pick today entry has 0 items"
            return True, "OK", ""
    return False, "FAIL", "ai-daily-pick.json has no entry for today"


def _check_ai_app_daily(today):
    p = os.path.join(MEM_DIR, "ai-app-daily.json")
    obj = _read_json(p)
    if not isinstance(obj, dict):
        return False, "FAIL", "missing or invalid ai-app-daily.json"
    rows = obj.get("ai_app_daily")
    if not isinstance(rows, list):
        return False, "FAIL", "ai-app-daily.json missing ai_app_daily[]"
    for r in rows[::-1]:
        if isinstance(r, dict) and (r.get("date") or "").strip() == today:
            items = r.get("items", [])
            if not items:
                return False, "WARN", "ai-app-daily.json today entry has 0 items"
            return True, "OK", ""
    return False, "FAIL", "ai-app-daily.json has no entry for today"


def _check_social_intel(today, filename):
    p = os.path.join(MEM_DIR, filename)
    obj = _read_json(p)
    if not isinstance(obj, dict):
        return False, "FAIL", "missing or invalid %s" % filename
    reports = obj.get("social_intel")
    if not isinstance(reports, list):
        return False, "FAIL", "%s missing social_intel[]" % filename
    for r in reports[::-1]:
        if isinstance(r, dict) and (r.get("date") or "").strip() == today:
            signals = r.get("signals") or r.get("items") or []
            if isinstance(signals, list) and len(signals) == 0:
                return False, "WARN", "%s today entry has 0 signals" % filename
            return True, "OK", ""
    return False, "FAIL", "%s has no entry for today" % filename


def _check_vla_hotspots(today):
    p = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
    obj = _read_json(p)
    if not isinstance(obj, dict):
        return False, "FAIL", "missing or invalid vla-daily-hotspots.json"
    papers = obj.get("reported_papers")
    if not isinstance(papers, list):
        return False, "FAIL", "vla-daily-hotspots.json missing reported_papers[]"
    today_papers = [x for x in papers if isinstance(x, dict) and (x.get("date") or "").strip() == today]
    if not today_papers:
        return False, "FAIL", "vla-daily-hotspots.json has no papers for today"
    return True, "OK", ""


def _check_vla_sota(today):
    """Check that SOTA tracker was updated today (not just file exists)."""
    p = os.path.join(MEM_DIR, "vla-sota-tracker.json")
    d = _read_json(p)
    if not d:
        return False, "FAIL", "missing vla-sota-tracker.json"
    last = (d.get("last_checked") or "").strip()
    if last != today:
        return False, "WARN", "vla-sota-tracker last_checked=%s (not today)" % (last or "unknown")
    return True, "OK", ""


def _check_vla_release(today):
    """Check that Release tracker ran today (via github-last-seen checked_at).
    The tracker only adds items when new tags are found; on quiet days no items
    are added even though the job ran fine.  Check checked_at instead."""
    p = os.path.join(MEM_DIR, "vla-release-tracker.json")
    d = _read_json(p)
    if not d:
        return False, "FAIL", "missing vla-release-tracker.json"
    # Primary check: at least one repo has checked_at == today (job ran today)
    last_seen = d.get("github-last-seen") or {}
    checked_today = [repo for repo, meta in last_seen.items()
                     if isinstance(meta, dict) and meta.get("checked_at") == today]
    if checked_today:
        return True, "OK", ""
    # Secondary: any release item dated today (new tag found today)
    items = d.get("vla-release-tracker") or []
    if not items:
        return False, "WARN", "vla-release-tracker.json has 0 items"
    dates = sorted([i.get("date", "") for i in items if i.get("date")], reverse=True)
    latest = dates[0] if dates else ""
    if latest != today:
        return False, "WARN", "vla-release job did not run today (last checked=%s)" % (latest or "none")
    return True, "OK", ""


def _check_vla_rating(today):
    """WARN if rating-out missing (rating failed/pending)."""
    p = os.path.join(MEM_DIR, "tmp", "vla-daily-rating-out-%s.json" % today)
    if _file_exists(p):
        return True, "OK", ""
    hour = int((_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%H"))
    if hour >= 10:
        return False, "WARN", "vla-daily-rating-out-%s.json missing after 10:00" % today
    return True, "OK", ""


def _check_calibration(today):
    """WARN if calibration-check output missing after 12:00."""
    p = os.path.join(MEM_DIR, "calibration-check-%s.json" % today)
    if _file_exists(p):
        return True, "OK", ""
    hour = int((_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%H"))
    if hour >= 12:
        return False, "WARN", "calibration-check-%s.json missing after 12:00" % today
    return True, "OK", ""


def _check_theory_articles():
    """WARN if vla-theory-articles.json has no entry in past 4 days."""
    p = os.path.join(MEM_DIR, "vla-theory-articles.json")
    data = _read_json(p)
    if not data:
        return True, "OK", ""
    articles = data if isinstance(data, list) else (data.get("theory_articles") or data.get("articles", []))
    if not articles:
        return True, "OK", ""
    dates = sorted([a.get("date", "") for a in articles if a.get("date")], reverse=True)
    if not dates:
        return True, "OK", ""
    latest = dates[0]
    now_date = (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")
    diff = (_dt.datetime.strptime(now_date, "%Y-%m-%d") -
            _dt.datetime.strptime(latest, "%Y-%m-%d")).days
    if diff > 4:
        return False, "WARN", "vla-theory-articles last entry %s (%d days ago)" % (latest, diff)
    return True, "OK", ""


def _check_ai_deep_dive():
    """WARN if ai-app-deep-dive-articles.json newest entry >4 days old."""
    p = os.path.join(MEM_DIR, "ai-app-deep-dive-articles.json")
    data = _read_json(p)
    if not data:
        return True, "OK", ""
    arts = (data.get("deep_dive_articles") or data.get("articles")
            or (data if isinstance(data, list) else []))
    if not arts:
        return True, "OK", ""
    dates = sorted([a.get("date", "") for a in arts if isinstance(a, dict) and a.get("date")],
                   reverse=True)
    if not dates:
        return True, "OK", ""
    latest = dates[0]
    now_date = (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")
    try:
        diff = (_dt.datetime.strptime(now_date, "%Y-%m-%d") -
                _dt.datetime.strptime(latest, "%Y-%m-%d")).days
    except Exception:
        return True, "OK", ""
    # Deep Dive runs Tue/Thu/Sat; gap <=3 days is normal
    if diff > 4:
        return False, "WARN", "ai-deep-dive last entry %s (%d days ago)" % (latest, diff)
    return True, "OK", ""


def _check_disk_space():
    """WARN >=85% full, FAIL >=95% full."""
    try:
        st = os.statvfs(MEM_DIR)
        total = st.f_blocks * st.f_frsize
        avail = st.f_bavail * st.f_frsize
        pct = int((total - avail) * 100 / total)
        free_gb = round(avail / (1024.0 ** 3), 1)
        if pct >= 95:
            return False, "FAIL", "disk %d%% full (%sGB free)" % (pct, free_gb)
        if pct >= 85:
            return False, "WARN", "disk %d%% full (%sGB free)" % (pct, free_gb)
        return True, "OK", ""
    except Exception:
        return True, "OK", ""


def _check_quality_drift(today: str):
    """WARN if quality-drift-check.py didn't record today's metrics yet (check #16)."""
    drift_state_path = os.path.join(MEM_DIR, "drift-state.json")
    if not os.path.exists(drift_state_path):
        return False, "WARN", "drift-state.json missing — quality-drift-check.py never ran"
    try:
        state = _read_json(drift_state_path)
        last = state.get("last_check", "")
        if last != today:
            return False, "WARN", "drift check last ran %r, expected %r" % (last, today)
        # If drift detected, surface it as a WARN (alert already sent by the script itself)
        metrics = state.get("metrics", {})
        drifting = [k for k, m in metrics.items() if m.get("streak", 0) >= 3]
        if drifting:
            return False, "WARN", "quality drift active: %s" % ", ".join(drifting)
    except Exception as e:
        return False, "WARN", "drift-state.json unreadable: %s" % e
    return True, "OK", ""


def _memory_rw_check():
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
    except Exception:
        pass
    p = os.path.join(TMP_DIR, "_watchdog_rw_probe.json")
    payload = {"ts": int(time.time()), "ok": True}
    _write_json_atomic(p, payload)
    back = _read_json(p)
    try:
        os.remove(p)
    except Exception:
        pass
    return isinstance(back, dict) and back.get("ok") is True


def _find_vla_social_orphan(today):
    """Return path to today's VLA Social Phase 2 llm-output if Phase 3 hasn't run yet.

    Phase 3 orphan: Phase 2 wrote the llm-output tmp file but Phase 3
    (post-vla-social.py) never ran — often due to timeout or gateway restart.
    In this case we can skip Phase 1+2 and run Phase 3 directly.
    """
    try:
        prefix = "vla-social-llm-output-%s-" % today
        matches = [
            os.path.join(TMP_DIR, f)
            for f in os.listdir(TMP_DIR)
            if f.startswith(prefix) and f.endswith(".json")
        ]
        if not matches:
            return None
        matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return matches[0]
    except Exception:
        return None


def _run_rerate(today):
    """Re-push rated TG if fallback was used and rating is now available."""
    fallback_flag = os.path.join(MEM_DIR, "tmp", "_vla_fallback_%s" % today)
    rating_out    = os.path.join(MEM_DIR, "tmp", "vla-daily-rating-out-%s.json" % today)
    rerated_flag  = os.path.join(MEM_DIR, "tmp", "_vla_rerated_%s" % today)
    if not os.path.exists(fallback_flag):
        return None
    if os.path.exists(rerated_flag):
        return None
    if not os.path.exists(rating_out):
        return None
    _progress("vla rerate: fallback flag + rating-out found, re-pushing TG")
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(
            ["python3", "/home/admin/clawd/scripts/vla-daily-rerate-push.py",
             "--date", today],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60,
            cwd="/home/admin", env=env,
        )
        return ("OK" if p.returncode == 0 else "FAIL: rc=%d" % p.returncode)
    except Exception as e:
        return "FAIL: %s" % str(e)[:80]


def _wait_until(check_fn, timeout_sec=720, step_sec=15):
    deadline = time.time() + int(timeout_sec)
    while time.time() < deadline:
        ok, _, _ = check_fn()
        if ok:
            return True
        time.sleep(step_sec)
    return False


def main():
    today = _today()
    start_ts = int(time.time())

    # Shared state for signal handler
    _state = {"actions": [], "issues_initial": [], "lock_path": None}

    def _handle_signal(signum, frame):
        elapsed = int(time.time() - start_ts)
        _progress("watchdog killed by signal %d after %ds — writing partial log" % (signum, elapsed))
        # Delete lockfile so next run isn't blocked
        try:
            lp = _state.get("lock_path")
            if lp and os.path.exists(lp):
                os.remove(lp)
        except Exception:
            pass
        try:
            _append_watchdog_log({
                "date": today, "ts": start_ts, "duration_sec": elapsed,
                "actions": _state["actions"],
                "issues_initial": _state["issues_initial"],
                "issues_final_fail": ["KILLED by signal %d after %ds" % (signum, elapsed)],
                "issues_final_warn": [],
                "killed": True,
            })
        except Exception:
            pass
        sys.stdout.write("Watchdog killed by signal %d after %ds\n" % (signum, elapsed))
        sys.stdout.flush()
        sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _progress("watchdog start: %s" % today)

    # ===== GATE: Lockfile — prevent duplicate concurrent runs =====
    # Two concurrent watchdog processes each ~330MB on a 2GB server = OOM risk.
    # Lock is valid for 30 min; stale locks (process died without cleanup) are ignored.
    lock_path = os.path.join(TMP_DIR, "_watchdog_lock_%s" % today)
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
    except Exception:
        pass
    try:
        if os.path.exists(lock_path):
            lock_age = time.time() - os.path.getmtime(lock_path)
            if lock_age < 1800:
                _progress("watchdog already running (lock %ds old) — aborting duplicate to prevent OOM" % int(lock_age))
                return 0
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))
        _state["lock_path"] = lock_path
    except Exception:
        pass  # lock write failure is non-fatal

    # ===== GATE: Early-hour guard =====
    hour_now = _now_shanghai().hour
    if hour_now < 9:
        _progress("watchdog: too early (hour=%d Shanghai), skipping remediation" % hour_now)
        _append_watchdog_log({
            "date": today, "ts": start_ts, "duration_sec": 0,
            "actions": [], "issues_initial": [],
            "issues_final_fail": [], "issues_final_warn": [],
            "skipped": "too early (hour=%d)" % hour_now,
        })
        try:
            os.remove(lock_path)
        except Exception:
            pass
        return 0

    # ===== GATE: Gateway health check =====
    gw_ok, gw_msg = _check_gateway_health()
    if not gw_ok:
        _progress("ABORT: Gateway not healthy: %s" % gw_msg)
        sys.stdout.write("Watchdog abort: Gateway not responding (port %d) — %s\n" % (GATEWAY_PORT, gw_msg))
        sys.stdout.write("  All cron triggers skipped. Fix Gateway first.\n")
        _append_watchdog_log({
            "date": today, "ts": start_ts, "duration_sec": 1,
            "actions": [], "issues_initial": ["gateway_down: %s" % gw_msg],
            "issues_final": ["gateway_down: %s" % gw_msg], "aborted": True,
        })
        try:
            os.remove(lock_path)
        except Exception:
            pass
        return 1

    rw_ok = _memory_rw_check()

    # Define checks — (key, check_fn)
    checks = [
        ("memory_rw",      lambda: (rw_ok, "FAIL" if not rw_ok else "OK", "" if rw_ok else "memory rw probe failed")),
        ("vla_rss_file",   lambda: (True, "OK", "") if _file_exists(os.path.join(MEM_DIR, "vla-rss-%s.json" % today))
                                   else (False, "FAIL", "missing vla-rss-%s.json" % today)),
        ("vla_hotspots",   lambda: _check_vla_hotspots(today)),
        ("vla_social",     lambda: _check_social_intel(today, "vla-social-intel.json")),
        ("vla_sota",       lambda: _check_vla_sota(today)),
        ("vla_release",    lambda: _check_vla_release(today)),
        ("aiapp_rss_file", lambda: (True, "OK", "") if _file_exists(os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today))
                                   else (False, "FAIL", "missing ai-app-rss-%s.json" % today)),
        ("aiapp_daily",    lambda: _check_ai_app_daily(today)),
        ("aiapp_social",   lambda: _check_social_intel(today, "ai-app-social-intel.json")),
        ("ai_daily_pick",  lambda: _check_ai_daily_pick(today)),
        ("vla_rating",     lambda: _check_vla_rating(today)),
        ("calibration",    lambda: _check_calibration(today)),
        ("theory_articles",lambda: _check_theory_articles()),
        ("ai_deep_dive",   lambda: _check_ai_deep_dive()),
        ("disk_space",     lambda: _check_disk_space()),
        ("quality_drift", lambda: _check_quality_drift(today)),
    ]

    results = {}
    issues_initial = _state["issues_initial"]
    for key, fn in checks:
        ok, level, why = fn()
        results[key] = {"ok": bool(ok), "level": level, "why": why}
        if not ok:
            issues_initial.append("%s[%s]: %s" % (key, level, why))

    actions = _state["actions"]

    # ===== DEPENDENCY-AWARE TRIGGERING =====
    vla_rss_ok   = results.get("vla_rss_file", {}).get("ok", True)
    aiapp_rss_ok = results.get("aiapp_rss_file", {}).get("ok", True)

    # 1) Fix RSS collectors first
    if not vla_rss_ok:
        vla_rss_out = os.path.join(MEM_DIR, "vla-rss-%s.json" % today)
        _progress("running vla-rss-collect.py")
        coll_ok, coll_detail = _run_collector("vla_rss_collect", vla_rss_out)
        actions.append("collect vla_rss: %s %s" % ("OK" if coll_ok else "FAIL", coll_detail))
        vla_rss_ok = coll_ok

    if not aiapp_rss_ok:
        aiapp_rss_out = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today)
        _progress("running ai-app-rss-collect.py")
        coll_ok, coll_detail = _run_collector("aiapp_rss_collect", aiapp_rss_out)
        actions.append("collect aiapp_rss: %s %s" % ("OK" if coll_ok else "FAIL", coll_detail))
        aiapp_rss_ok = coll_ok

    # 2a) VLA Social: Phase 3 orphan recovery before full-pipeline trigger
    # If Phase 2 llm-output file exists for today but social-intel missing →
    # Phase 3 never ran (timeout/restart). Call post-vla-social.py directly.
    if not results.get("vla_social", {}).get("ok") and vla_rss_ok:
        orphan = _find_vla_social_orphan(today)
        if orphan:
            _progress("vla_social: Phase 3 orphan detected (%s) — running post directly" % os.path.basename(orphan))
            rc3, _, _ = _run(
                ["python3", POST_VLA_SOCIAL, "--date", today,
                 "--input", orphan, "--account", "original", "--target", "1898430254"],
                timeout=90,
            )
            if rc3 == 0:
                actions.append("vla_social_phase3_orphan: OK (skipped Phase 1+2)")
                results["vla_social"] = {"ok": True, "level": "OK", "why": ""}
            else:
                actions.append("vla_social_phase3_orphan: FAIL rc=%d — will retry full pipeline" % rc3)

    # 2b) Trigger remaining failed LLM jobs (respects DAG)
    trigger_plan = [
        ("vla_hotspots",  "vla_daily",    vla_rss_ok,   "vla_rss"),
        ("vla_social",    "vla_social",   vla_rss_ok,   "vla_rss"),
        ("vla_sota",      "vla_sota",     True,          None),
        ("vla_release",   "vla_release",  True,          None),
        ("aiapp_daily",   "aiapp_daily",  aiapp_rss_ok,  "aiapp_rss"),
        ("aiapp_social",  "aiapp_social", aiapp_rss_ok,  "aiapp_rss"),
        ("ai_daily_pick", "ai_daily_pick",True,          None),
    ]

    for chk, job_key, upstream_ok, upstream_name in trigger_plan:
        if results.get(chk, {}).get("ok"):
            continue
        if not upstream_ok:
            actions.append("SKIP %s (upstream %s failed)" % (chk, upstream_name))
            _progress("skip %s because %s not available" % (chk, upstream_name))
            continue
        # WARN-only checks (sota/release): still trigger to refresh
        level = results.get(chk, {}).get("level", "FAIL")
        if level == "WARN" and chk not in ("vla_sota", "vla_release"):
            continue  # quality WARNs don't trigger re-runs
        _progress("trigger %s" % chk)
        job_ok, out, err = _cron_run(job_key)
        actions.append("trigger %s: %s" % (chk, "OK" if job_ok else "FAIL"))

    # 2.5) VLA Re-rate push
    rerate_result = _run_rerate(today)
    if rerate_result is not None:
        actions.append("vla_rerate_push: %s" % rerate_result)

    # 3) Re-check deliverables after trigger window (max 12 min)
    _progress("re-validating after triggers")

    def _recheck():
        fails = 0
        for k, fn in [
            ("vla_hotspots",  lambda: _check_vla_hotspots(today)),
            ("vla_social",    lambda: _check_social_intel(today, "vla-social-intel.json")),
            ("aiapp_daily",   lambda: _check_ai_app_daily(today)),
            ("aiapp_social",  lambda: _check_social_intel(today, "ai-app-social-intel.json")),
            ("ai_daily_pick", lambda: _check_ai_daily_pick(today)),
        ]:
            ok, level, _ = fn()
            if not ok and level == "FAIL":
                fails += 1
        return (fails == 0), "OK" if fails == 0 else "FAIL", ""

    _wait_until(_recheck, timeout_sec=12 * 60, step_sec=20)

    # 4) Final evaluation
    final_issues_fail = []
    final_issues_warn = []
    for key, fn in checks:
        ok, level, why = fn()
        if not ok:
            if level == "WARN":
                final_issues_warn.append("%s: %s" % (key, why))
            else:
                final_issues_fail.append("%s: %s" % (key, why))

    entry = {
        "date": today,
        "ts": start_ts,
        "duration_sec": int(time.time() - start_ts),
        "actions": actions,
        "issues_initial": issues_initial,
        "issues_final_fail": final_issues_fail,
        "issues_final_warn": final_issues_warn,
    }
    try:
        _append_watchdog_log(entry)
    except Exception:
        pass

    # Clean up lockfile
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass

    total_checks = len(checks)
    fail_count = len(final_issues_fail)
    warn_count = len(final_issues_warn)
    ok_count = total_checks - fail_count - warn_count

    summary = "WATCHDOG SUMMARY: %d/%d ok, %d warn, %d fail | %s" % (
        ok_count, total_checks, warn_count, fail_count, today
    )

    if not final_issues_fail and not final_issues_warn:
        _progress(summary)
        return 0

    lines = []
    lines.append("Watchdog %s" % today)
    if actions:
        lines.append("")
        lines.append("已执行/触发：")
        for a in actions:
            lines.append("- %s" % a)
    if final_issues_fail:
        lines.append("")
        lines.append("❌ 仍然失败 (需关注)：")
        for it in final_issues_fail:
            lines.append("- %s" % it)
    if final_issues_warn:
        lines.append("")
        lines.append("⚠️ 质量告警：")
        for it in final_issues_warn:
            lines.append("- %s" % it)
    lines.append("")
    lines.append(summary)
    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 1 if final_issues_fail else 0


if __name__ == "__main__":
    sys.exit(main())
