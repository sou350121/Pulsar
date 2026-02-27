#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Daily Pick - Stable Source Collector

联动策略（与「AI 应用监控任务群」联动）：
- 优先复用 AI 应用监控 Task 1 的稳定源输出：ai-app-rss-{today}.json（零额外抓取）。
- 并对照 AI 应用监控 Task 2 日报 ai-app-daily.json（today）做去重，减少 Telegram 重复。

输出：
- stdout 输出 JSON
- 同时写入 /home/admin/clawd/memory/ai-daily-pick-sources-{today}.json
- 幂等：若当天文件已存在，直接回读并输出（不重复抓取）

Python：3.6+（无外部依赖）
"""

from __future__ import print_function

import datetime as _dt
import json
import os
import re
import sys


MEM_DIR = "/home/admin/clawd/memory"


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _strip_html(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    # if snippet was truncated mid-tag (e.g. "<a href=..."), drop the tail
    s = re.sub(r"<[^>]*$", " ", s)
    # minimal HTML entity decode
    s = (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_key(s):
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-/.:#@]+", "", s)
    return s.strip()


def _load_ai_app_daily_dedup(today):
    path = os.path.join(MEM_DIR, "ai-app-daily.json")
    dedup = {"titles": set(), "urls": set()}
    if not os.path.exists(path):
        return dedup, 0, False
    try:
        obj = _read_json(path)
    except Exception:
        return dedup, 0, False

    lst = obj.get("ai_app_daily")
    if not isinstance(lst, list):
        return dedup, 0, True

    count = 0
    for e in lst:
        if not isinstance(e, dict):
            continue
        if (e.get("date") or "").strip() != today:
            continue
        items = e.get("items")
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            t = _norm_key(it.get("title") or "")
            u = _norm_key(it.get("url") or "")
            if t:
                dedup["titles"].add(t)
            if u:
                dedup["urls"].add(u)
            count += 1
        break
    return dedup, count, True


def _source_rank(src):
    s = (src or "").strip().lower()
    if s.startswith("ai-app-rss:"):
        s = s[len("ai-app-rss:") :]
    if s.startswith("hf-blog"):
        return 0
    if s.startswith("hn"):
        return 1
    if s.startswith("gh-release:"):
        return 2
    if s.startswith("gh-trending"):
        return 3
    if s.startswith("reddit"):
        return 4
    if s.startswith("producthunt"):
        return 5
    return 9


def _source_group(src):
    s = (src or "").strip().lower()
    if s.startswith("ai-app-rss:"):
        s = s[len("ai-app-rss:") :]
    if s.startswith("gh-release:"):
        return "gh-release"
    if s.startswith("hn"):
        return "hn"
    if s.startswith("gh-trending"):
        return "gh-trending"
    if s.startswith("hf-blog"):
        return "hf-blog"
    if s.startswith("reddit"):
        return "reddit"
    if s.startswith("producthunt"):
        return "producthunt"
    return "other"


def main():
    os.makedirs(MEM_DIR, exist_ok=True)
    today = _today_shanghai()
    out_path = os.path.join(MEM_DIR, "ai-daily-pick-sources-%s.json" % today)

    force = ("--force" in sys.argv)

    # Idempotent: return existing file
    if os.path.exists(out_path) and (not force):
        try:
            obj = _read_json(out_path)
        except Exception:
            obj = {"date": today, "sources": []}
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
        return 0

    dedup, ai_app_daily_count, ai_app_daily_loaded = _load_ai_app_daily_dedup(today)

    sources = []
    ai_app_rss_used = False
    ai_app_rss_path = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today)
    ai_app_rss_filtered_path = os.path.join(MEM_DIR, "ai-app-rss-filtered-%s.json" % today)
    dropped_by_ai_app_daily = 0

    # Prefer filtered RSS (already pub_date-filtered by prep-ai-app-rss-filtered.py)
    # so stale articles (>7 days) are excluded before LLM selection.
    # Fall back to raw RSS + inline 30-day cutoff if filtered file not yet available.
    _MAX_AGE_DAYS = 30  # inline fallback; filtered file uses 7 days

    def _pub_date_ok(it, cutoff_dt):
        """Return True if item is recent enough (or undated from low-volume source)."""
        import datetime as _dt2
        pub = (it.get("pub_date") or "").strip()
        src = (it.get("source") or "").lower()
        high_vol = ("hf-blog" in src or "hf-papers" in src or "blog-hf-papers" in src)
        if pub:
            try:
                item_dt = _dt.date(*[int(x) for x in pub[:10].split("-")])
                return item_dt >= cutoff_dt
            except Exception:
                pass
        # No pub_date: keep unless from high-volume feed
        return not high_vol

    cutoff = (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).date() - _dt.timedelta(days=_MAX_AGE_DAYS)

    rss_source_path = ai_app_rss_filtered_path if os.path.exists(ai_app_rss_filtered_path) else ai_app_rss_path
    if os.path.exists(rss_source_path):
        try:
            rss = _read_json(rss_source_path) or {}
            items = rss.get("items") if isinstance(rss, dict) else None
            if isinstance(items, list):
                ai_app_rss_used = True
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    title = (it.get("title") or "").strip()
                    url = (it.get("url") or "").strip()
                    if not title or not url:
                        continue

                    # Inline pub_date guard (only needed when using raw RSS fallback)
                    if rss_source_path == ai_app_rss_path and not _pub_date_ok(it, cutoff):
                        continue

                    t_n = _norm_key(title)
                    u_n = _norm_key(url)

                    # Dedup vs AI 应用监控日报（Task 2）to avoid TG repeat
                    if u_n and u_n in dedup["urls"]:
                        dropped_by_ai_app_daily += 1
                        continue
                    if t_n and t_n in dedup["titles"]:
                        dropped_by_ai_app_daily += 1
                        continue

                    summary = it.get("summary_snippet") or it.get("summary") or ""
                    summary = _strip_html(summary)
                    if len(summary) > 220:
                        summary = summary[:220].rstrip() + "…"

                    src = (it.get("source") or "").strip()
                    sources.append(
                        {
                            "title": title,
                            "summary": summary,
                            "url": url,
                            "source": "ai-app-rss:%s" % (src or "unknown"),
                            "pub_date": (it.get("pub_date") or ""),
                        }
                    )
        except Exception:
            ai_app_rss_used = False

    # Fallback: return empty sources WITHOUT writing to disk.
    # Not writing prevents the fallback from being cached and returned all day.
    # The next cron run will retry once ai-app-rss-{today}.json becomes available.
    if not sources:
        out = {
            "date": today,
            "sources": [],
            "meta": {
                "linked_ai_app_rss": False,
                "linked_ai_app_rss_path": ai_app_rss_path,
                "ai_app_daily_loaded": bool(ai_app_daily_loaded),
                "ai_app_daily_items_today": int(ai_app_daily_count),
                "dropped_by_ai_app_daily": 0,
                "capped_to": int(max_sources),
                "fallback": True,
                "note": "RSS not available yet; file not cached so next run will retry",
            },
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return 0

    # Dedup within sources + cap (keep order, diversify by source)
    seen_urls = set()
    seen_titles = set()
    uniq = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        t = (s.get("title") or "").strip()
        u = (s.get("url") or "").strip()
        if not t or not u:
            continue
        t_n = _norm_key(t)
        u_n = _norm_key(u)
        if u_n and u_n in seen_urls:
            continue
        if t_n and t_n in seen_titles:
            continue
        seen_urls.add(u_n)
        seen_titles.add(t_n)
        uniq.append(s)

    max_sources = 30
    caps = {
        "gh-release": 10,
        "hn": 8,
        "gh-trending": 6,
        "hf-blog": 6,
        "reddit": 4,
        "producthunt": 4,
        "other": 4,
    }
    taken = {}
    selected = []
    deferred = []
    for s in uniq:
        g = _source_group(s.get("source") or "")
        n = int(taken.get(g, 0))
        cap = int(caps.get(g, 4))
        if (n < cap) and (len(selected) < max_sources):
            selected.append(s)
            taken[g] = n + 1
        else:
            deferred.append(s)

    # Fill remaining slots without per-source caps (still keep order)
    if len(selected) < max_sources:
        for s in deferred:
            selected.append(s)
            if len(selected) >= max_sources:
                break
    uniq = selected

    out = {
        "date": today,
        "sources": uniq,
        "meta": {
            "linked_ai_app_rss": bool(ai_app_rss_used),
            "linked_ai_app_rss_path": ai_app_rss_path if ai_app_rss_used else "",
            "ai_app_daily_loaded": bool(ai_app_daily_loaded),
            "ai_app_daily_items_today": int(ai_app_daily_count),
            "dropped_by_ai_app_daily": int(dropped_by_ai_app_daily),
            "capped_to": int(max_sources),
        },
    }

    try:
        _write_json(out_path, out)
    except Exception:
        pass

    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())