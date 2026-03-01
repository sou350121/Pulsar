#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Social Intelligence - Phase 1: Deterministic Search & Candidate Prep.

Rebuilt 2026-02-23: original was deleted in Cursor session on 2026-02-22.
Based on prep-ai-app-social.py pattern, adapted for VLA/embodied-AI domain.
2026-02-23: switched from OpenRouter/Perplexity to DashScope Qwen 3.5 Plus
            (OpenRouter account hit 402 payment limit). Qwen 3.5 Plus has
            knowledge up to 2026 and does not require web search credentials.

- Build exclusion set from VLA memory (hotspots, social intel, RSS)
- Call DashScope Qwen 3.5 Plus for VLA social signals (uses 2026 knowledge)
- Filter candidates against exclusion set
- Output candidates JSON for LLM content generation

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys

try:
    from urllib.request import Request, urlopen
except Exception:  # pragma: no cover
    Request = None
    urlopen = None


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
VLA_HOTSPOTS_PATH = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
VLA_SOCIAL_PATH = os.path.join(MEM_DIR, "vla-social-intel.json")
# DashScope key lives in the reports agent auth-profiles (same agent used in Phase 2)
DASHSCOPE_AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3.5-plus"

# VLA/embodied-AI specific query topics (one per API call, bounded by --max-queries).
# Qwen 3.5 Plus has 2026 knowledge; queries are knowledge-retrieval, not live search.
DEFAULT_QUERY_TOPICS = [
    "VLA or vision-language-action model new release open source",
    "humanoid robot company funding announcement demo launch",
    "embodied AI lab news researcher career move publication",
    "physical intelligence OR 1X technologies OR figure AI news",
    "Boston Dynamics OR Agility Robotics OR Unitree new release",
    "Google DeepMind OR Stanford OR MIT OR CMU robotics lab news",
    "robot manipulation dexterous hand open source project",
    "embodied AI benchmark competition new dataset release",
    "robotics simulation Isaac OR MuJoCo OR Genesis new version",
    "robot foundation model pretrained checkpoint public release",
    "embodied AI researcher funding raise new hire",
    "humanoid OR legged robot hardware announcement",
]


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


# ------------------------------------------------------------------
# Exclusion set (from VLA memory)
# ------------------------------------------------------------------

def _build_exclusion_set(today):
    """Build exclusion set from VLA hotspots, social history, and RSS."""
    titles = set()
    urls = set()

    # 1) VLA daily hotspots (recent 14 days)
    hotspots = _read_json(VLA_HOTSPOTS_PATH, {})
    cutoff = _dt.datetime.utcnow().date() - _dt.timedelta(days=14)
    for p in (hotspots.get("reported_papers") or []):
        if not isinstance(p, dict):
            continue
        try:
            pd = _dt.datetime.strptime(p.get("date", ""), "%Y-%m-%d").date()
            if pd < cutoff:
                continue
        except Exception:
            pass
        t = _norm(p.get("title", ""))
        u = _norm(p.get("url", ""))
        if t:
            titles.add(t)
        if u:
            urls.add(u)

    # 2) VLA social intel history (last 30 days only — avoid dedup exhaustion)
    social = _read_json(VLA_SOCIAL_PATH, {})
    import datetime as _dt2
    _cutoff30 = (_dt2.datetime.utcnow() + _dt2.timedelta(hours=8) - _dt2.timedelta(days=30)).strftime("%Y-%m-%d")
    for entry in [e for e in (social.get("social_intel") or []) if isinstance(e, dict) and (e.get("date") or "") >= _cutoff30]:
        if not isinstance(entry, dict):
            continue
        for sig in (entry.get("signals") or []):
            if not isinstance(sig, dict):
                continue
            s = _norm(sig.get("summary", ""))
            u = _norm(sig.get("url", ""))
            entity = _norm(sig.get("person_or_entity", ""))
            if s:
                titles.add(s)
            if entity and s:
                titles.add(entity + " " + s)
            if u:
                urls.add(u)

    # 3) Today's VLA RSS (avoid duplicating arXiv papers)
    rss_path = os.path.join(MEM_DIR, "vla-rss-%s.json" % today)
    rss = _read_json(rss_path, {})
    for p in (rss.get("papers") or []):
        if not isinstance(p, dict):
            continue
        t = _norm(p.get("title", ""))
        u = _norm(p.get("url", ""))
        if t:
            titles.add(t)
        if u:
            urls.add(u)

    titles.discard("")
    urls.discard("")
    return titles, urls


# ------------------------------------------------------------------
# DashScope Qwen 3.5 Plus (knowledge-retrieval mode, no live search)
# ------------------------------------------------------------------

def _extract_dashscope_key():
    """Read DashScope API key from reports agent auth-profiles or env."""
    key = os.environ.get("DASHSCOPE_API_KEY") or ""
    if key:
        return key
    cfg = _read_json(DASHSCOPE_AUTH_PATH, {})
    try:
        return (cfg.get("profiles", {})
                   .get("alibaba-cloud:default", {})
                   .get("key", "")) or ""
    except Exception:
        return ""


def _call_qwen_search(day, topic, excl_sample, key, timeout=90):
    """
    Call DashScope Responses API with web_search tool for real-time grounded results.
    Uses qwen3.5-plus + built-in web_search -> returns real, verifiable URLs.
    Switched from OpenRouter/Perplexity on 2026-02-23 (OpenRouter 402).
    Per-query ~50s; keep max_queries<=3 to stay within Phase 1 time budget.
    """
    if (not Request) or (not urlopen) or (not key):
        return {"ok": False, "error": "qwen_unavailable", "query": topic}
    excl_hint = ""
    if excl_sample:
        excl_hint = (
            "\nAlready reported (skip these): "
            + "; ".join(list(excl_sample)[:10])
        )
    query_text = (
        "Today is " + day + ". Find notable events from the PAST 3 DAYS ONLY (strict: "
        + day + " minus 3 days) about: " + topic + ". "
        "For each item provide: entity/person, what happened, EXACT date (YYYY-MM-DD), and source URL. "
        "IMPORTANT: Only include events that happened on or after 3 days before today. "
        "Exclude arXiv preprints. Exclude evergreen/intro content with no specific event date." + excl_hint
    )
    payload = {
        "model": "qwen3.5-plus",
        "input": query_text,
        "tools": [{"type": "web_search"}],
        "enable_thinking": False,
    }
    import json as _json
    body = _json.dumps(payload).encode("utf-8")
    url = "https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1/responses"
    req = Request(url, data=body, headers={
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
    })
    try:
        rsp = urlopen(req, timeout=timeout)
        raw = rsp.read().decode("utf-8", errors="replace")
        obj = _json.loads(raw)
        text = ""
        for item in (obj.get("output") or []):
            if item.get("type") == "message":
                for c in (item.get("content") or []):
                    text += c.get("text", "")
        found_urls = re.findall(r"https?://[^\s)\]\"'<>]+", text or "")
        return {"ok": True, "query": topic, "content": text[:3000],
                "urls": list(dict.fromkeys(found_urls))[:15]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "query": topic}



def _is_excluded(text, url, excl_titles, excl_urls):
    n_url = _norm(url)
    if n_url and n_url in excl_urls:
        return True
    n_text = _norm(text)
    if n_text:
        if n_text in excl_titles:
            return True
        for et in excl_titles:
            if len(et) > 10 and (et in n_text or n_text in et):
                return True
    return False


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--out", default="", help="Output path")
    ap.add_argument("--max-queries", type=int, default=3,
                    help="Max Qwen queries (keep bounded; each is ~60s)")
    ap.add_argument("--no-web", action="store_true",
                    help="Skip Qwen queries (offline mode)")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out = (args.out.strip()
           or os.path.join(TMP_DIR, "vla-social-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    excl_titles, excl_urls = _build_exclusion_set(day)

    search_results = []
    warnings = []
    if not args.no_web:
        key = _extract_dashscope_key()
        if not key:
            warnings.append("dashscope_api_key_missing")
            search_results.append({
                "ok": False,
                "search_type": "error",
                "search_name": "no_key",
                "content": "",
                "urls": [],
                "filtered_reason": "api_key_missing",
            })
        else:
            # Pass a sample of exclusion titles to Qwen for dedup guidance
            excl_sample = [t for t in excl_titles if len(t) > 15][:20]
            max_q = min(int(args.max_queries), len(DEFAULT_QUERY_TOPICS))
            for topic in DEFAULT_QUERY_TOPICS[:max_q]:
                res = _call_qwen_search(day, topic, excl_sample, key, timeout=90)
                res["search_type"] = "qwen_knowledge"
                res["search_name"] = topic[:50]
                if not res.get("ok"):
                    warnings.append("query_failed:%s" % topic[:40])
                raw_urls = res.get("urls") or []
                clean = [u for u in raw_urls
                         if not _is_excluded("", u, excl_titles, excl_urls)]
                res["excluded_url_count"] = len(raw_urls) - len(clean)
                res["urls"] = clean
                search_results.append(res)
    else:
        search_results.append({
            "ok": True,
            "search_type": "offline",
            "search_name": "no-web",
            "content": "",
            "urls": [],
            "filtered_reason": "no_web",
        })

    out_obj = {
        "ok": True,
        "date": day,
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exclusion_stats": {
            "titles_in_set": len(excl_titles),
            "urls_in_set": len(excl_urls),
        },
        "search_results": search_results,
        "warnings": warnings,
    }
    _write_json(out, out_obj)
    ok_count = len([r for r in search_results if r.get("ok") and not r.get("filtered_reason")])
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out,
        "search_count": ok_count,
        "exclusion_titles": len(excl_titles),
        "warnings": len(warnings),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

