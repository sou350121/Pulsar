#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Daily - Mechanical RSS pre-filter (dedup + exclusion + date filtering).

Matches `40-ai-app-tasks.md` rev.15:
- Mechanical string matching (exact + substring >= 6 chars + URL-parse compare)
- Output: /home/admin/clawd/memory/ai-app-rss-filtered-{date}.json

Python 3.6+ (no external deps).

Changelog:
  2026-02-23: Add date filtering.
    - Items with pub_date older than 30 days are dropped (too_old).
    - Items without pub_date from high-volume feeds (hf-blog, blog-hf-papers)
      are capped to first 20 per source (RSS returns newest first; cap prevents
      2024 archive articles from entering the pipeline).
    - Root cause: hf-blog RSS returns 180+ articles including 2024 archive;
      agent was picking Gemma 3/Llama 4 (March-April 2025) as "new" content.
"""

from __future__ import print_function

import datetime as _dt
import json
import os
import re
import sys
import subprocess


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
RSS_COLLECT_SCRIPT = "/home/admin/clawd/scripts/ai-app-rss-collect.py"
DEDUP_EXCL_SCRIPT = "/home/admin/clawd/scripts/prep-ai-app-dedup.py"

# Sources that return large archives — cap undated items per source
HIGH_VOLUME_SOURCES = {"hf-blog", "blog-hf-papers"}
HIGH_VOLUME_UNDATED_CAP = 15  # newest-first RSS: first 15 likely within 1 week

MAX_AGE_DAYS = 7  # hard cutoff: daily report only shows last 7 days


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _today_shanghai_date():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).date()


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _norm_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm_title(s):
    s = _norm_ws(s).lower()
    s = re.sub("[\u200b\u200c\u200d]", "", s)
    s = re.sub(r"[()\[\]{}<>\"'`]", "", s)
    s = re.sub(r"[\s\-_/]+", " ", s)
    return s.strip()


def _norm_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    u = u.split("#", 1)[0]
    u = u.split("?", 1)[0]
    m = re.match(r"^(https?://)([^/]+)(/.*)?$", u, flags=re.I)
    if not m:
        return u.rstrip("/")
    scheme = (m.group(1) or "").lower()
    host = (m.group(2) or "").lower()
    path = m.group(3) or ""
    path = re.sub(r"/{2,}", "/", path).rstrip("/")
    return scheme + host + path


def _is_versiony(title_norm):
    return bool(re.search(r"\bv?\d+(?:\.\d+){1,3}\b", title_norm))


def _title_substring_match(a, b):
    if not a or not b:
        return False
    if len(a) < 6 or len(b) < 6:
        return False
    if a in b or b in a:
        short = a if len(a) < len(b) else b
        if len(short) < 6:
            return False
        return True
    return False


def _parse_pub_date(s):
    """Parse pub_date string (YYYY-MM-DD or RFC 822) to date object, or None."""
    if not s:
        return None
    s = s.strip()
    # ISO date
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _apply_date_filter(items, today_dt, dropped):
    """Filter items by pub_date; cap undated high-volume sources."""
    cutoff = today_dt - _dt.timedelta(days=MAX_AGE_DAYS)
    source_undated_count = {}
    result = []
    for it in items:
        source = it.get("source", "")
        pub_date_str = it.get("pub_date", "")
        if pub_date_str:
            item_dt = _parse_pub_date(pub_date_str)
            if item_dt is not None:
                if item_dt < cutoff:
                    dropped["too_old"] = dropped.get("too_old", 0) + 1
                    continue
                # Date OK
                result.append(it)
                continue
        # No parseable pub_date
        if source in HIGH_VOLUME_SOURCES:
            count = source_undated_count.get(source, 0)
            if count >= HIGH_VOLUME_UNDATED_CAP:
                dropped["no_date_capped"] = dropped.get("no_date_capped", 0) + 1
                continue
            source_undated_count[source] = count + 1
        result.append(it)
    return result


def _ensure_inputs(today):
    rss_path = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today)
    if not os.path.exists(rss_path):
        try:
            subprocess.run([sys.executable, RSS_COLLECT_SCRIPT], timeout=240)
        except Exception:
            pass
    excl_path = os.path.join(TMP_DIR, "ai-app-exclusion-%s.json" % today)
    if not os.path.exists(excl_path):
        try:
            subprocess.run([sys.executable, DEDUP_EXCL_SCRIPT], timeout=60)
        except Exception:
            pass
    return rss_path, excl_path


def _load_exclusion(excl_path):
    excl = _read_json(excl_path, {})
    titles = set()
    urls = set()
    for t in (excl.get("titles") or []):
        if isinstance(t, dict):
            titles.add(_norm_title(t.get("title") or ""))
        elif isinstance(t, str):
            titles.add(_norm_title(t))
    for u in (excl.get("urls") or []):
        if isinstance(u, str):
            urls.add(_norm_url(u))
    titles.discard("")
    urls.discard("")
    return titles, urls


def main():
    today = _today_shanghai()
    today_dt = _today_shanghai_date()
    out_path = os.path.join(MEM_DIR, "ai-app-rss-filtered-%s.json" % today)

    rss_path, excl_path = _ensure_inputs(today)
    rss = _read_json(rss_path, {})
    items = rss.get("items") if isinstance(rss, dict) else None
    if not isinstance(items, list):
        items = []

    excl_titles, excl_urls = _load_exclusion(excl_path)
    total_before = len(items)

    dropped = {
        "too_old": 0,
        "no_date_capped": 0,
        "already_covered": 0,
        "excluded_title": 0,
        "excluded_url": 0,
        "bad_row": 0,
        "dedup_title": 0,
        "dedup_url": 0,
        "dedup_substring": 0,
    }

    # 0) Date filter: reject items older than MAX_AGE_DAYS; cap undated high-volume sources
    items = _apply_date_filter(items, today_dt, dropped)

    # 1) Exclude (history + already_covered)
    candidates = []
    for it in items:
        if not isinstance(it, dict):
            dropped["bad_row"] += 1
            continue
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        if not title or not url:
            dropped["bad_row"] += 1
            continue
        if bool(it.get("already_covered")):
            dropped["already_covered"] += 1
            continue

        nt = _norm_title(title)
        nu = _norm_url(url)
        if nu and nu in excl_urls:
            dropped["excluded_url"] += 1
            continue
        if nt and nt in excl_titles:
            dropped["excluded_title"] += 1
            continue

        # substring exclusion vs history
        hit = False
        if nt:
            for et in list(excl_titles)[:800]:
                if _title_substring_match(nt, et):
                    dropped["excluded_title"] += 1
                    hit = True
                    break
        if hit:
            continue

        candidates.append(it)

    # 2) Mechanical dedup within candidates
    out = []
    seen_urls = set()
    seen_titles = set()
    for it in candidates:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        nt = _norm_title(title)
        nu = _norm_url(url)

        if nu and nu in seen_urls:
            dropped["dedup_url"] += 1
            continue
        if nt and nt in seen_titles:
            dropped["dedup_title"] += 1
            continue

        # substring dedup (conservative)
        sub_hit = False
        if nt and (len(nt) >= 6) and (_is_versiony(nt) or len(nt.split()) >= 3):
            for st in list(seen_titles)[-500:]:
                if _title_substring_match(nt, st):
                    dropped["dedup_substring"] += 1
                    sub_hit = True
                    break
        if sub_hit:
            continue

        if nu:
            seen_urls.add(nu)
        if nt:
            seen_titles.add(nt)
        out.append(it)
        if len(out) >= 220:
            break

    payload = {
        "tag": "ai-app-rss-filtered-%s" % today,
        "date": today,
        "source_path": rss_path,
        "exclusion_path": excl_path,
        "total_before_dedup": int(total_before),
        "total_after_dedup": int(len(out)),
        "dropped": dropped,
        "items": out,
    }
    _write_json_atomic(out_path, payload)
    print(json.dumps({"ok": True, "date": today, "output": out_path,
                      "total_before": total_before,
                      "after": len(out),
                      "too_old": dropped.get("too_old", 0),
                      "no_date_capped": dropped.get("no_date_capped", 0)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
