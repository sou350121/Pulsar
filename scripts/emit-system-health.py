#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import datetime as _dt
import glob
import json
import os
import sys


MEM_DIR = "/home/admin/clawd/memory"
JOBS_PATH = "/home/admin/.clawdbot/cron/jobs.json"
OUT_PATH = os.path.join(MEM_DIR, "system-health.json")


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _parse_date(s):
    try:
        return _dt.datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _last_n_days_records(rows, days, today_s):
    today = _parse_date(today_s)
    if (not isinstance(rows, list)) or (today is None):
        return [], 0
    lo = today - _dt.timedelta(days=max(1, int(days)) - 1)
    picked = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _parse_date(r.get("date"))
        if d is None:
            continue
        if d < lo or d > today:
            continue
        picked.append(r)
        seen.add(d.strftime("%Y-%m-%d"))
    expected = max(1, int(days))
    data_gaps = max(0, expected - len(seen))
    return picked, data_gaps


def _sum_tags(stats_rows):
    final_total = 0
    actionable_total = 0
    for r in stats_rows:
        if not isinstance(r, dict):
            continue
        final_total += int(r.get("final_in_report") or 0)
        tags = r.get("tags") if isinstance(r.get("tags"), dict) else {}
        actionable_total += int(tags.get("actionable") or 0)
    if final_total <= 0:
        return 0.0
    return round(float(actionable_total) / float(final_total), 4)


def _keyword_efficiency(stats_rows):
    ratios = []
    for r in stats_rows:
        if not isinstance(r, dict):
            continue
        hit = r.get("keywords_hit")
        if not isinstance(hit, dict):
            continue
        total = 0
        nonzero = 0
        for _, v in hit.items():
            total += 1
            if int(v or 0) > 0:
                nonzero += 1
        if total > 0:
            ratios.append(float(nonzero) / float(total))
    if not ratios:
        return 0.0
    return round(sum(ratios) / float(len(ratios)), 4)


def _source_diversity(stats_rows):
    vals = []
    for r in stats_rows:
        if not isinstance(r, dict):
            continue
        s = r.get("sources_hit")
        if not isinstance(s, dict):
            continue
        vals.append(len([k for k, v in s.items() if int(v or 0) > 0]))
    if not vals:
        return 0.0
    # Normalize by 6 common source buckets.
    avg = sum(vals) / float(len(vals))
    return round(min(1.0, avg / 6.0), 4)


def _stale_keywords_14d(stats_rows):
    all_hits = {}
    for r in stats_rows:
        if not isinstance(r, dict):
            continue
        hit = r.get("keywords_hit")
        if not isinstance(hit, dict):
            continue
        for kw, v in hit.items():
            if not isinstance(kw, str):
                continue
            all_hits[kw] = int(all_hits.get(kw, 0)) + int(v or 0)
    stale = []
    for kw, total in all_hits.items():
        if total == 0:
            stale.append(kw)
    stale.sort()
    return stale[:30]


def _watchdog_status(today_s):
    path = os.path.join(MEM_DIR, "watchdog-log.json")
    obj = _read_json(path, {})
    rows = obj.get("watchdog_log") if isinstance(obj, dict) else None
    if not isinstance(rows, list) or (not rows):
        return {"last_run": None, "status": "missing"}
    last = rows[-1] if isinstance(rows[-1], dict) else {}
    d = (last.get("date") or "").strip()
    checks = last.get("checks") if isinstance(last.get("checks"), dict) else {}
    all_ok = True
    for _, v in checks.items():
        if not bool(v):
            all_ok = False
            break
    status = "ok" if (d == today_s and all_ok) else "stale_or_degraded"
    return {"last_run": (d or None), "status": status}


def _memory_confirms_success(job_name, today_s):
    # Guard against known "false failure" pattern:
    # job lastStatus=error while memory artifacts are already present.
    if job_name == "VLA Daily Hotspots":
        p = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
        obj = _read_json(p, {})
        rows = obj.get("reported_papers") if isinstance(obj, dict) else None
        if isinstance(rows, list):
            for it in rows:
                if not isinstance(it, dict):
                    continue
                if (it.get("date") or "").strip() != today_s:
                    continue
                if it.get("in_report", True) is False:
                    continue
                return True
        return False
    if job_name == "VLA Release Tracker":
        p = os.path.join(MEM_DIR, "vla-release-tracker.json")
        obj = _read_json(p, {})
        ls = obj.get("github-last-seen") if isinstance(obj, dict) else None
        if isinstance(ls, dict):
            for _, v in ls.items():
                if isinstance(v, dict) and (v.get("checked_at") or "").strip() == today_s:
                    return True
        return False
    return False


def _task_health(today_s):
    obj = _read_json(JOBS_PATH, {})
    jobs = obj if isinstance(obj, list) else obj.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []
    enabled = [j for j in jobs if bool(j.get("enabled", True))]
    total = len(enabled)
    ok = 0
    failed_today = []
    false_failures_filtered = []
    sh = _dt.timezone(_dt.timedelta(hours=8))
    for j in enabled:
        name = j.get("name") or j.get("id") or "unknown"
        st = j.get("state") if isinstance(j.get("state"), dict) else {}
        status = (st.get("lastStatus") or "").strip().lower()
        if status == "ok":
            ok += 1
        last_ms = int(st.get("lastRunAtMs") or 0)
        if last_ms <= 0:
            continue
        d = _dt.datetime.fromtimestamp(last_ms / 1000.0, tz=sh).strftime("%Y-%m-%d")
        if d == today_s and status not in ("", "ok"):
            if _memory_confirms_success(name, today_s):
                false_failures_filtered.append(name)
            else:
                failed_today.append(name)
    rate = round((float(ok) / float(total)), 4) if total > 0 else 0.0
    return {
        "success_rate_enabled": rate,
        "enabled_jobs": total,
        "failed_today": failed_today[:20],
        "false_failures_filtered": false_failures_filtered[:20],
    }


def _cost_snapshot():
    files = sorted(glob.glob(os.path.join(MEM_DIR, "token-usage-weekly-*.json")))
    if not files:
        return {"daily_tokens": 0, "cost_trend_7d": "unknown"}
    latest = _read_json(files[-1], {})
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    trend = latest.get("trend")
    total_tokens = int(summary.get("total_tokens") or 0)
    # Weekly total -> rough daily estimate
    daily_tokens = int(total_tokens / 7) if total_tokens > 0 else 0
    if isinstance(trend, dict):
        direction = trend.get("direction") or "stable"
    elif isinstance(trend, str):
        low = trend.lower()
        if "increase" in low or "up" in low:
            direction = "up"
        elif "decrease" in low or "down" in low:
            direction = "down"
        else:
            direction = "stable"
    else:
        direction = "stable"
    return {
        "daily_tokens": daily_tokens,
        "cost_trend_7d": direction,
    }


def _overall_health(tasks, quality, watchdog):
    if watchdog.get("status") != "ok":
        return "degraded"
    if tasks.get("failed_today"):
        return "degraded"
    if int(quality.get("data_gaps_7d") or 0) >= 2:
        return "degraded"
    return "ok"


def _latest_quality_review():
    path = os.path.join(MEM_DIR, "quality-review.json")
    obj = _read_json(path, {})
    rows = obj.get("quality_reviews") if isinstance(obj, dict) else None
    if not isinstance(rows, list) or (not rows):
        return {"last_date": None, "last_overall": None, "trend_4w": "unknown"}
    # memory-upsert sorts by date desc, but keep defensive sorting.
    rows2 = [r for r in rows if isinstance(r, dict)]
    rows2.sort(key=lambda x: (x.get("date") or ""), reverse=True)
    last = rows2[0]
    vals = []
    for r in rows2[:4]:
        try:
            vals.append(float(r.get("overall")))
        except Exception:
            pass
    trend = "stable"
    if len(vals) >= 2:
        if vals[0] - vals[-1] >= 0.2:
            trend = "up"
        elif vals[-1] - vals[0] >= 0.2:
            trend = "down"
    return {
        "last_date": (last.get("date") or None),
        "last_overall": (last.get("overall") if "overall" in last else None),
        "trend_4w": trend if vals else "unknown",
    }


def main():
    today = _today_shanghai()
    try:
        stats_obj = _read_json(os.path.join(MEM_DIR, "daily-stats.json"), {})
        stats_rows = stats_obj.get("daily_stats") if isinstance(stats_obj, dict) else []
        stats_7d, gaps_7d = _last_n_days_records(stats_rows, 7, today)
        stats_14d, _ = _last_n_days_records(stats_rows, 14, today)

        tasks = _task_health(today)
        quality = {
            "actionable_ratio_7d": _sum_tags(stats_7d),
            "keyword_efficiency_7d": _keyword_efficiency(stats_7d),
            "source_diversity_7d": _source_diversity(stats_7d),
            "stale_keywords_14d": _stale_keywords_14d(stats_14d),
            "data_gaps_7d": int(gaps_7d),
        }
        watchdog = _watchdog_status(today)
        health = {
            "date": today,
            "overall_health": _overall_health(tasks, quality, watchdog),
            "tasks": tasks,
            "quality": quality,
            "quality_review": _latest_quality_review(),
            "cost": _cost_snapshot(),
            "watchdog": watchdog,
        }

        _write_json_atomic(OUT_PATH, health)

        # Silent on success unless degraded.
        if health.get("overall_health") != "ok":
            print("system-health: degraded")
        return 0
    except Exception as e:
        err = {"date": today, "error": str(e)[:240]}
        try:
            _write_json_atomic(OUT_PATH, err)
        except Exception:
            pass
        print("system-health: error %s" % str(e)[:120])
        return 0


if __name__ == "__main__":
    sys.exit(main())
