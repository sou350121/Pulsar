#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monthly Calibration Aggregation
- Reads past 30 days of calibration-check-{date}.json
- Per assumption: counts trigger days, scanned days
- Conservatively updates confidence in assumptions.json (max ±0.08/month)
- Generates monthly synthesis report → TG format + JSON output
"""

import json
import os
import sys
import datetime

MEM_DIR = "/home/admin/clawd/memory"
ASSUMPTIONS_PATH = os.path.join(MEM_DIR, "assumptions.json")

def _today_shanghai():
    utc = datetime.datetime.utcnow()
    sh = utc + datetime.timedelta(hours=8)
    return sh.strftime("%Y-%m-%d"), sh.strftime("%Y-%m")

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _progress(msg):
    sys.stdout.write("[progress] %s\n" % msg)
    sys.stdout.flush()

def collect_history(today_str, lookback_days=30):
    """Read all calibration-check files from past N days."""
    today = datetime.datetime.strptime(today_str, "%Y-%m-%d")
    records = []
    for i in range(lookback_days):
        d = today - datetime.timedelta(days=i)
        dstr = d.strftime("%Y-%m-%d")
        path = os.path.join(MEM_DIR, "calibration-check-%s.json" % dstr)
        data = _read_json(path)
        if data:
            records.append(data)
    _progress("found %d calibration records in past %d days" % (len(records), lookback_days))
    return records

def aggregate_per_assumption(records, assumptions):
    """For each assumption, compute: days_scanned, days_triggered, trigger_rate."""
    stats = {}
    for a in assumptions:
        aid = a["id"]
        stats[aid] = {
            "id": aid,
            "domain": a.get("domain", "?"),
            "hypothesis_short": a.get("hypothesis", "")[:80],
            "confidence_before": a.get("confidence", None),
            "days_scanned": 0,
            "days_triggered": 0,
            "triggers": [],  # collect evidence snippets
        }

    for rec in records:
        date = rec.get("date", "?")
        vla_n = rec.get("vla_signals_scanned", 0)
        ai_n = rec.get("ai_signals_scanned", 0)
        triggered_ids = set(t.get("assumption_id") for t in rec.get("triggers", []) if t.get("assumption_id"))

        for a in assumptions:
            aid = a["id"]
            domain = a.get("domain", "system")
            # Count as scanned if relevant signals existed for this domain
            if domain == "vla" and vla_n > 0:
                stats[aid]["days_scanned"] += 1
            elif domain == "ai_agent" and ai_n > 0:
                stats[aid]["days_scanned"] += 1
            elif domain not in ("vla", "ai_agent") and (vla_n + ai_n) > 0:
                stats[aid]["days_scanned"] += 1

            if aid in triggered_ids:
                stats[aid]["days_triggered"] += 1
                # Collect evidence snippet from trigger record
                for t in rec.get("triggers", []):
                    if t.get("assumption_id") == aid:
                        stats[aid]["triggers"].append({
                            "date": date,
                            "signal": t.get("signal_title", "")[:80],
                            "severity": t.get("severity", "medium"),
                        })

    return stats

def compute_confidence_delta(s):
    """
    Conservative Bayesian-ish update.
    - Triggered: confidence goes DOWN (evidence of invalidation)
    - Not triggered + scanned days >= 10: tiny confirmation bonus
    - Max |delta| per month: 0.08
    """
    days_scanned = s["days_scanned"]
    days_triggered = s["days_triggered"]
    if days_scanned == 0:
        return 0.0  # no data, no change

    trigger_rate = days_triggered / days_scanned

    if days_triggered > 0:
        # Each triggered day = moderate confidence reduction
        # trigger_rate 1.0 → delta -0.08, rate 0.1 → delta -0.008
        delta = -0.08 * trigger_rate
    else:
        # No triggers: slight confirmation if well-observed
        if days_scanned >= 10:
            delta = +0.02
        elif days_scanned >= 5:
            delta = +0.01
        else:
            delta = 0.0

    # Clamp
    return max(-0.08, min(+0.04, delta))

def update_assumptions_file(assumptions, stats):
    """Write updated confidence scores back to assumptions.json."""
    data = _read_json(ASSUMPTIONS_PATH)
    if not data:
        return False

    updated = []
    for a in data.get("assumptions", []):
        aid = a.get("id")
        if aid in stats:
            s = stats[aid]
            delta = compute_confidence_delta(s)
            old_conf = a.get("confidence")
            if old_conf is not None and delta != 0.0:
                new_conf = round(max(0.05, min(0.99, old_conf + delta)), 2)
                a["confidence"] = new_conf
                s["confidence_after"] = new_conf
                s["delta"] = round(delta, 3)
            else:
                s["confidence_after"] = old_conf
                s["delta"] = 0.0
        updated.append(a)

    data["assumptions"] = updated
    data["last_calibration_update"] = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    tmp = ASSUMPTIONS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ASSUMPTIONS_PATH)
    _progress("updated assumptions.json")
    return True

def format_tg(stats, month_str, record_count):
    """Format Telegram message."""
    lines = []
    lines.append("📊 *月度假設校準* | %s" % month_str)
    lines.append("")
    lines.append("_基於過去 %d 天校準記錄_" % record_count)
    lines.append("")

    # Sort by |delta| descending
    sorted_stats = sorted(stats.values(), key=lambda s: abs(s.get("delta", 0)), reverse=True)

    # Moved assumptions (delta != 0)
    moved = [s for s in sorted_stats if s.get("delta", 0) != 0]
    stable = [s for s in sorted_stats if s.get("delta", 0) == 0 and s["days_scanned"] > 0]
    no_data = [s for s in sorted_stats if s["days_scanned"] == 0]

    if moved:
        lines.append("━━━ 假設移動 ━━━")
        lines.append("")
        for s in moved:
            aid = s["id"]
            cb = s["confidence_before"]
            ca = s["confidence_after"]
            delta = s["delta"]
            arrow = "↓" if delta < 0 else "↑"
            triggered = s["days_triggered"]
            scanned = s["days_scanned"]
            hyp = s["hypothesis_short"]
            direction = "⚠️ 挑戰" if delta < 0 else "✅ 強化"
            lines.append("%s *%s*: %.2f → %.2f %s" % (direction, aid, cb, ca, arrow))
            lines.append("  _%s..._" % hyp[:60])
            lines.append("  掃描 %d 天 | 觸發 %d 天" % (scanned, triggered))
            if s["triggers"]:
                lines.append("  最近觸發: %s" % s["triggers"][-1]["signal"][:50])
            lines.append("")

    if stable:
        lines.append("━━━ 假設穩定 ━━━")
        lines.append("")
        stable_ids = ", ".join("*%s*" % s["id"] for s in stable[:8])
        lines.append("%s — 本月信號充足但未觸發" % stable_ids)
        lines.append("")

    if no_data:
        nd_ids = ", ".join(s["id"] for s in no_data)
        lines.append("_無數據: %s_" % nd_ids)
        lines.append("")

    lines.append("━━━ 下月觀測點 ━━━")
    lines.append("")
    # Suggest watching the most challenged or borderline assumptions
    watch = [s for s in moved if s.get("delta", 0) < 0][:2]
    if watch:
        for s in watch:
            lines.append("🔭 *%s* (%.2f) — 信號在動搖，留意後續論文" % (s["id"], s["confidence_after"]))
    else:
        lines.append("🔭 本月所有假設穩定，繼續觀察")

    return "\n".join(lines)

def main():
    today_str, month_str = _today_shanghai()
    _progress("monthly calibration agg: %s" % month_str)

    # Load assumptions
    raw = _read_json(ASSUMPTIONS_PATH)
    if not raw:
        print(json.dumps({"ok": False, "error": "cannot_read_assumptions"}))
        sys.exit(1)
    assumptions = [a for a in raw.get("assumptions", []) if a.get("status") == "active"]
    _progress("active assumptions: %d" % len(assumptions))

    # Collect history
    records = collect_history(today_str, lookback_days=30)
    if not records:
        _progress("no calibration records found — too early in the month?")
        print(json.dumps({"ok": True, "month": month_str, "records": 0, "note": "no_data"}))
        return

    # Aggregate
    stats = aggregate_per_assumption(records, assumptions)

    # Update confidence scores
    update_assumptions_file(assumptions, stats)

    # Build output
    out = {
        "ok": True,
        "month": month_str,
        "generated_at": today_str,
        "records_used": len(records),
        "assumptions": list(stats.values()),
    }

    # Save monthly JSON
    out_path = os.path.join(MEM_DIR, "monthly-calibration-%s.json" % month_str)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    _progress("saved %s" % out_path)

    # Format TG message
    tg = format_tg(stats, month_str, len(records))

    # Save TG message
    tg_path = os.path.join(MEM_DIR, "tmp", "monthly-calibration-tg-%s.txt" % month_str)
    os.makedirs(os.path.dirname(tg_path), exist_ok=True)
    with open(tg_path, "w", encoding="utf-8") as f:
        f.write(tg)
    _progress("saved TG draft: %s" % tg_path)


    # Write watch-list.json — shared contract for downstream jobs
    watch_items = []
    for s in stats.values():
        delta = s.get('delta', 0)
        days_triggered = s.get('days_triggered', 0)
        days_scanned = s.get('days_scanned', 0)
        trigger_rate = days_triggered / days_scanned if days_scanned > 0 else 0
        if delta <= -0.03 or trigger_rate >= 0.1:
            watch_items.append({
                'id': s['id'],
                'domain': s['domain'],
                'hypothesis_short': s['hypothesis_short'],
                'confidence': s.get('confidence_after', s.get('confidence_before')),
                'delta': delta,
                'trigger_rate': round(trigger_rate, 3),
                'keywords': next((a.get('keywords', []) for a in assumptions if a.get('id') == s['id']), []),
            })
    watch_path = os.path.join(MEM_DIR, 'watch-list.json')
    with open(watch_path, 'w', encoding='utf-8') as f:
        json.dump({'month': month_str, 'generated_at': today_str, 'watch': watch_items}, f, ensure_ascii=False, indent=2)
    _progress('watch-list: %d items -> %s' % (len(watch_items), watch_path))

    print(json.dumps({
        "ok": True,
        "month": month_str,
        "records": len(records),
        "out_path": out_path,
        "tg_path": tg_path,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
