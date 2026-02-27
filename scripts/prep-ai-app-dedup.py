#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Daily - Dedup Exclusion List Generator

Runs BEFORE the LLM daily report task.
Reads ai-app-daily.json (last 7 days) and generates a simple exclusion file
that the LLM MUST read and respect.

Output: /home/admin/clawd/memory/tmp/ai-app-exclusion-{today}.json
"""

import datetime as _dt
import json
import os
import re
import sys

MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")


def _today_shanghai():
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _norm(s):
    """Normalize title for fuzzy matching."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    # Remove version suffixes for broader matching (e.g., "v0.4" -> "")
    # but keep the base name
    return s


def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    today = _today_shanghai()
    out_path = os.path.join(TMP_DIR, f"ai-app-exclusion-{today}.json")

    # Load recent daily entries
    titles = []
    urls = []
    title_set = set()

    if os.path.exists(DAILY_PATH):
        try:
            with open(DAILY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        entries = data.get("ai_app_daily", [])
        if not isinstance(entries, list):
            entries = [data] if isinstance(data, dict) and data.get("date") else []

        # Last 7 days window
        try:
            d0 = _dt.datetime.strptime(today, "%Y-%m-%d").date()
        except Exception:
            d0 = _dt.date.today()

        allowed_dates = set()
        for i in range(7):
            allowed_dates.add((d0 - _dt.timedelta(days=i)).strftime("%Y-%m-%d"))

        for entry in entries:
            date = (entry or {}).get("date", "")
            if date not in allowed_dates:
                continue
            items = (entry or {}).get("items", [])
            if not isinstance(items, list):
                continue
            for it in items:
                title = (it.get("title") or it.get("name") or "").strip()
                url = (it.get("url") or "").strip()
                norm_title = _norm(title)

                if title and norm_title not in title_set:
                    title_set.add(norm_title)
                    titles.append({
                        "title": title,
                        "date": date,
                        "source": it.get("source", ""),
                    })
                if url:
                    urls.append(url)

    # Also load social intel for cross-dedup
    social_path = os.path.join(MEM_DIR, "ai-app-social-intel.json")
    if os.path.exists(social_path):
        try:
            with open(social_path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            social_items = sdata.get("social_intel", [])  # actual key in ai-app-social-intel.json
            if isinstance(social_items, list):
                for sit in social_items[-50:]:  # last 50
                    st = (sit.get("title") or "").strip()
                    su = (sit.get("url") or "").strip()
                    norm_st = _norm(st)
                    if st and norm_st not in title_set:
                        title_set.add(norm_st)
                        titles.append({
                            "title": st,
                            "date": sit.get("date", "?"),
                            "source": "social-intel",
                        })
                    if su:
                        urls.append(su)
        except Exception:
            pass

    # Deduplicate URLs
    urls = list(dict.fromkeys(urls))  # preserve order, remove dups

    payload = {
        "generated": today,
        "description": "AI App Daily exclusion list. LLM MUST skip any item whose title substantially matches one below.",
        "excluded_titles_count": len(titles),
        "excluded_urls_count": len(urls),
        "titles": titles,
        "urls": urls[:300],  # cap to avoid huge files
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Print summary to stdout (for logging)
    print(json.dumps({
        "ok": True,
        "date": today,
        "excluded_titles": len(titles),
        "excluded_urls": len(urls),
        "output": out_path,
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
