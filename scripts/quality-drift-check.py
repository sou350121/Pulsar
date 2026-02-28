#!/usr/bin/env python3.11
"""
Quality Drift Checker — P1 #4

Runs daily at 10:05 Shanghai time (after VLA/AI pipelines, before watchdog at 10:15).
Detects systematic pipeline degradation via rolling metric comparison.

Metrics:
  VLA:    papers_scanned, final_in_report, sources_active, tg_msg_len (optional)
  AI App: items_scanned, items_after_filter  (sparse-safe: skip if < 3 days history)

Drift rule: metric < 7-day rolling average × 0.70 for 3+ consecutive days → TG alert.

State:  memory/drift-state.json   (streak tracking, alert dedup)
Log:    memory/drift-metrics.json (30-day daily snapshots)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MEM_DIR  = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR  = os.path.join(MEM_DIR, "tmp")
MOLTBOT  = os.environ.get("MOLTBOT_BIN", "/home/admin/.local/share/pnpm/moltbot")

VLA_STATS_FILE   = os.path.join(MEM_DIR, "daily-stats.json")
AIAPP_STATS_FILE = os.path.join(MEM_DIR, "ai-app-daily-stats.json")
DRIFT_METRICS    = os.path.join(MEM_DIR, "drift-metrics.json")
DRIFT_STATE      = os.path.join(MEM_DIR, "drift-state.json")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WINDOW_DAYS     = 7     # rolling baseline window (days excluding today)
MIN_HISTORY     = 3     # min days of history before drift check runs
DRIFT_THRESHOLD = 0.70  # alert if today < baseline * this (i.e. drop > 30%)
ALERT_STREAK    = 3     # consecutive drift days before firing alert
KEEP_DAYS       = 30    # retention for drift-metrics.json

# TG routing — same target, different accounts per domain
TG_VLA   = {"account": "original",         "target": "1898430254"}
TG_AIAPP = {"account": "ai_agent_dailybot", "target": "1898430254"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shanghai_today() -> str:
    """Return today's date in Shanghai time (UTC+8), formatted YYYY-MM-DD."""
    utc_now = datetime.now(timezone.utc)
    shanghai_now = utc_now + timedelta(hours=8)
    return shanghai_now.strftime("%Y-%m-%d")


def _read_json(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, obj: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _send_tg(account: str, target: str, message: str) -> bool:
    """Send a Telegram message via moltbot CLI. Returns True on success."""
    try:
        result = subprocess.run(
            [MOLTBOT, "message", "send",
             "--account", account, "--target", target, "--message", message],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[drift] TG send error: {e}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# Metric collectors
# ---------------------------------------------------------------------------

def _collect_vla(today: str) -> dict | None:
    """Extract today's VLA metrics from daily-stats.json."""
    if not os.path.exists(VLA_STATS_FILE):
        return None
    rows = _read_json(VLA_STATS_FILE)
    if isinstance(rows, dict):
        rows = rows.get("daily_stats", list(rows.values()))
    for row in reversed(rows):
        if row.get("date") == today:
            scanned = row.get("total_papers_scanned", 0)
            report  = row.get("final_in_report", 0)
            sources_active = len(row.get("sources_hit", []))
            metrics = {
                "vla_papers_scanned": scanned,
                "vla_final_in_report": report,
                "vla_sources_active":  sources_active,
            }
            # Optional: TG message length as output quality proxy
            tg_file = os.path.join(TMP_DIR, f"vla-daily-tg-{today}.txt")
            if os.path.exists(tg_file):
                metrics["vla_tg_msg_len"] = os.path.getsize(tg_file)
            return metrics
    return None


def _collect_aiapp(today: str) -> dict | None:
    """Extract today's AI App metrics from ai-app-daily-stats.json."""
    if not os.path.exists(AIAPP_STATS_FILE):
        return None
    data  = _read_json(AIAPP_STATS_FILE)
    rows  = data.get("daily_stats", []) if isinstance(data, dict) else data
    for row in reversed(rows):
        if row.get("date") == today:
            return {
                "aiapp_items_scanned": row.get("total_items_scanned", 0),
                "aiapp_items_report":  row.get("final_in_report", row.get("total_after_filter", 0)),
            }
    return None

# ---------------------------------------------------------------------------
# Drift metrics log
# ---------------------------------------------------------------------------

def _load_metrics() -> list:
    if not os.path.exists(DRIFT_METRICS):
        return []
    return _read_json(DRIFT_METRICS)


def _append_metrics(metrics_log: list, today: str, snapshot: dict) -> list:
    """Append today's snapshot; keep only last KEEP_DAYS entries."""
    # Remove any existing entry for today (re-run safety)
    metrics_log = [e for e in metrics_log if e.get("date") != today]
    metrics_log.append({"date": today, **snapshot})
    # Trim to retention window
    metrics_log = sorted(metrics_log, key=lambda e: e["date"])
    if len(metrics_log) > KEEP_DAYS:
        metrics_log = metrics_log[-KEEP_DAYS:]
    return metrics_log


def _compute_baseline(metrics_log: list, key: str, today: str) -> float | None:
    """
    Compute 7-day rolling average for `key`, excluding today.
    Returns None if fewer than MIN_HISTORY data points available.
    """
    history = [
        e[key] for e in metrics_log
        if e.get("date") < today and key in e and e[key] is not None
    ]
    history = history[-WINDOW_DAYS:]
    if len(history) < MIN_HISTORY:
        return None
    return sum(history) / len(history)

# ---------------------------------------------------------------------------
# Drift state
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if not os.path.exists(DRIFT_STATE):
        return {"last_check": "", "metrics": {}}
    return _read_json(DRIFT_STATE)


def _update_state(state: dict, key: str, today_val: float,
                  baseline: float, is_drifting: bool) -> None:
    """Update streak counter for a metric in-place."""
    m = state["metrics"].setdefault(key, {"streak": 0, "alerted_at_streak": 0})
    if is_drifting:
        m["streak"] += 1
    else:
        m["streak"] = 0
        m["alerted_at_streak"] = 0
    m["last_value"] = today_val
    m["baseline"]   = round(baseline, 2) if baseline is not None else None
    m["ratio"]      = round(today_val / baseline, 3) if baseline else None

# ---------------------------------------------------------------------------
# Alert formatting
# ---------------------------------------------------------------------------
_METRIC_LABELS = {
    "vla_papers_scanned":  ("VLA", "論文掃描量"),
    "vla_final_in_report": ("VLA", "進入報告量"),
    "vla_sources_active":  ("VLA", "活躍來源數"),
    "vla_tg_msg_len":      ("VLA", "TG 報告長度"),
    "aiapp_items_scanned": ("AI App", "資訊掃描量"),
    "aiapp_items_report":  ("AI App", "進入報告量"),
}


def _format_alert(drifting_keys: list, state: dict) -> dict[str, str]:
    """
    Build per-domain alert messages.
    Returns {"vla": "...", "aiapp": "..."} with only non-empty entries.
    """
    vla_lines   = []
    aiapp_lines = []

    for key in drifting_keys:
        m = state["metrics"].get(key, {})
        domain_label, metric_label = _METRIC_LABELS.get(key, ("?", key))
        streak   = m.get("streak", 0)
        today_v  = m.get("last_value", "?")
        baseline = m.get("baseline", "?")
        ratio    = m.get("ratio", 0)
        pct_drop = round((1 - ratio) * 100) if ratio else "?"
        line = (f"📉 {metric_label}: {today_v:.0f} → 基線 {baseline:.0f} "
                f"(↓{pct_drop}%, 已連續 {streak} 天)")
        if domain_label == "VLA":
            vla_lines.append(line)
        else:
            aiapp_lines.append(line)

    alerts = {}
    if vla_lines:
        alerts["vla"] = (
            "⚠️ Pipeline Drift 警報 — VLA 管道\n\n"
            + "\n".join(vla_lines)
            + "\n\n可能原因：RSS 波動、關鍵詞失效、ArXiv 靜默期\n"
            "建議：檢查 daily-stats.json 和 vla-rss-collect.py"
        )
    if aiapp_lines:
        alerts["aiapp"] = (
            "⚠️ Pipeline Drift 警報 — AI App 管道\n\n"
            + "\n".join(aiapp_lines)
            + "\n\n可能原因：RSS 來源異常、過濾條件過嚴、API 配額耗盡\n"
            "建議：檢查 ai-app-daily-stats.json 和 prep-ai-app-rss-filtered.py"
        )
    return alerts

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    today = _shanghai_today()
    print(f"[drift] date={today}")

    # 1. Collect today's metrics
    snapshot = {}
    vla_metrics   = _collect_vla(today)
    aiapp_metrics = _collect_aiapp(today)

    if vla_metrics is None:
        print("[drift] WARN: no VLA stats for today, skipping VLA metrics", file=sys.stderr)
    else:
        snapshot.update(vla_metrics)

    if aiapp_metrics is None:
        print("[drift] WARN: no AI App stats for today, skipping AI App metrics", file=sys.stderr)
    else:
        snapshot.update(aiapp_metrics)

    if not snapshot:
        print("[drift] ERROR: no metrics collected today", file=sys.stderr)
        # Still write a placeholder so watchdog sees today's entry
        state = _load_state()
        state["last_check"] = today
        _write_json_atomic(DRIFT_STATE, state)
        return 1

    # 2. Append to rolling log
    metrics_log = _load_metrics()
    metrics_log = _append_metrics(metrics_log, today, snapshot)
    _write_json_atomic(DRIFT_METRICS, metrics_log)
    print(f"[drift] snapshot recorded: {list(snapshot.keys())}")

    # 3. Compute baselines + detect drift
    state = _load_state()
    drifting_keys = []

    for key, today_val in snapshot.items():
        baseline = _compute_baseline(metrics_log, key, today)
        if baseline is None:
            print(f"[drift] {key}: insufficient history, skipping")
            continue
        is_drifting = today_val < baseline * DRIFT_THRESHOLD
        _update_state(state, key, today_val, baseline, is_drifting)
        streak = state["metrics"][key]["streak"]
        ratio  = state["metrics"][key]["ratio"]
        print(f"[drift] {key}: {today_val:.0f} vs baseline {baseline:.1f} "
              f"(ratio={ratio:.2f}, streak={streak})")
        if streak >= ALERT_STREAK:
            drifting_keys.append(key)

    state["last_check"] = today
    _write_json_atomic(DRIFT_STATE, state)

    # 4. Send alerts (deduplicated: only alert once per streak milestone)
    if drifting_keys:
        alert_msgs = _format_alert(drifting_keys, state)
        for domain, msg in alert_msgs.items():
            # Dedup: skip if we already alerted at this streak length for ALL keys in domain
            domain_keys = [k for k in drifting_keys
                           if _METRIC_LABELS.get(k, ("?",))[0] == ("VLA" if domain == "vla" else "AI App")]
            already_alerted = all(
                state["metrics"].get(k, {}).get("alerted_at_streak", 0)
                >= state["metrics"].get(k, {}).get("streak", 0)
                for k in domain_keys
            )
            if already_alerted:
                print(f"[drift] {domain}: alert already sent for this streak, skipping")
                continue

            tg = TG_VLA if domain == "vla" else TG_AIAPP
            ok = _send_tg(tg["account"], tg["target"], msg)
            if ok:
                print(f"[drift] {domain}: alert sent via {tg['account']}")
                # Mark as alerted
                for k in domain_keys:
                    if k in state["metrics"]:
                        state["metrics"][k]["alerted_at_streak"] = state["metrics"][k]["streak"]
            else:
                print(f"[drift] {domain}: alert FAILED", file=sys.stderr)

        _write_json_atomic(DRIFT_STATE, state)
    else:
        print("[drift] no drift detected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
