#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Social Intel - Phase 1: Deterministic Search & Candidate Prep.

- Read active config for search terms
- Read exclusion set (daily + social intel history)
- Call Perplexity API (bounded, deterministic)
- Filter against exclusion set
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
ACTIVE_CONFIG = os.path.join(MEM_DIR, "ai-app-active-config.json")
SOCIAL_INTEL_PATH = os.path.join(MEM_DIR, "ai-app-social-intel.json")
DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
MOLTBOT_CONFIG = "/home/admin/.moltbot/moltbot.json"
# Switched from OpenRouter/Perplexity to DashScope Qwen 2026-02-23 (OpenRouter 402)
DASHSCOPE_AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3.5-plus"
DEDUP_SCRIPT = "/home/admin/clawd/scripts/prep-ai-app-dedup.py"

# Social intel focus: what people are SAYING/DEBATING — NOT what tools launched.
# Tool releases go to 日报 (AI 应用开发监控日报). Social intel = opinions, controversies, viral.
DEFAULT_SEARCH_TERMS = [
    # ── 意見 / 觀點 ──
    "Andrej Karpathy OR Sam Altman OR Dario Amodei OR Yann LeCun AI opinion 2026",
    "AI researcher opinion prediction controversy blog post 2026",
    # ── 社區熱議 / 爭議 ──
    "AI agent limitation failure disappointment reddit hacker news 2026",
    "LLM coding agent criticism OR overhyped OR debate developer community 2026",
    "AI hype AGI controversy skeptic opinion 2026",
    # ── 病毒傳播 / 演示 ──
    "viral AI demo video tweet reddit trending 2026",
    "AI tool community reaction backlash OR praise OR viral 2026",
    # ── 行業動態（社交面）──
    "AI startup funding acquisition major news 2026",
    "AI safety alignment policy regulation debate 2026",
    "open source vs closed model debate community 2026",
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
# Exclusion set
# ------------------------------------------------------------------

def _ensure_exclusion_file(today):
    """Make sure the dedup exclusion file exists (run prep script if needed)."""
    excl_path = os.path.join(TMP_DIR, "ai-app-exclusion-%s.json" % today)
    if os.path.exists(excl_path):
        return excl_path
    # Try running the dedup prep script
    try:
        import subprocess
        subprocess.run(
            [sys.executable, DEDUP_SCRIPT],
            timeout=30,
            capture_output=True,
        )
    except Exception:
        pass
    return excl_path


def _build_exclusion_set(today):
    """Build exclusion set from dedup file + social intel history + daily history."""
    titles = set()
    urls = set()

    # 1) Pre-generated exclusion list
    excl_path = _ensure_exclusion_file(today)
    excl = _read_json(excl_path, {})
    for t in (excl.get("titles") or []):
        if isinstance(t, dict):
            titles.add(_norm(t.get("title", "")))
        elif isinstance(t, str):
            titles.add(_norm(t))
    for u in (excl.get("urls") or []):
        urls.add(_norm(u))

    # 2) Social intel history (all entries)
    social = _read_json(SOCIAL_INTEL_PATH, {})
    entries = social.get("social_intel", [])
    if isinstance(entries, list):
        for entry in entries:
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

    # 3) Daily report history (last 7 days)
    daily = _read_json(DAILY_PATH, {})
    for entry in (daily.get("ai_app_daily") or [])[-7:]:
        if not isinstance(entry, dict):
            continue
        for it in (entry.get("items") or []):
            if not isinstance(it, dict):
                continue
            t = _norm(it.get("title") or it.get("name", ""))
            u = _norm(it.get("url", ""))
            if t:
                titles.add(t)
            if u:
                urls.add(u)

    # Clean empty
    titles.discard("")
    urls.discard("")
    return titles, urls


# ------------------------------------------------------------------
# Perplexity API
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
        "Today is " + day + ". Find the most notable recent events (past 2-3 weeks) "
        "about: " + topic + ". "
        "For each item provide: entity/person, what happened, approximate date, and source URL. "
        "Exclude arXiv preprints." + excl_hint
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
                    help="Max Perplexity queries")
    ap.add_argument("--no-web", action="store_true",
                    help="Skip Perplexity search")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out = (args.out.strip()
           or os.path.join(TMP_DIR,
                           "ai-app-social-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    # Load config
    cfg = _read_json(ACTIVE_CONFIG, {})
    search_terms = cfg.get("search_terms_social") or DEFAULT_SEARCH_TERMS
    if not isinstance(search_terms, list):
        search_terms = DEFAULT_SEARCH_TERMS

    # Build exclusion set
    excl_titles, excl_urls = _build_exclusion_set(day)

    # Today's RSS for cross-reference
    rss_path = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % day)
    rss = _read_json(rss_path, {})
    rss_items = []
    if isinstance(rss, dict):
        for it in (rss.get("items") or rss.get("papers") or []):
            if isinstance(it, dict):
                rss_items.append({
                    "title": (it.get("title") or "").strip(),
                    "url": (it.get("url") or "").strip(),
                    "source": (it.get("source") or "rss").strip(),
                })

    # Perplexity search
    search_results = []
    warnings = []
    if not args.no_web:
        key = _extract_dashscope_key()
        excl_sample = [t for t in excl_titles if len(t) > 15][:20]
        if not key:
            warnings.append("dashscope_api_key_missing")
        else:
            max_q = min(int(args.max_queries), len(search_terms))
            for term in search_terms[:max_q]:
                res = _call_qwen_search(day, term, excl_sample, key)
                search_results.append(res)
                if not res.get("ok"):
                    warnings.append("query_failed:%s" % term[:40])

    # Filter URLs against exclusion set
    for res in search_results:
        if not res.get("ok"):
            continue
        raw_urls = res.get("urls") or []
        clean = [u for u in raw_urls
                 if not _is_excluded("", u, excl_titles, excl_urls)]
        res["excluded_url_count"] = len(raw_urls) - len(clean)
        res["urls"] = clean

    out_obj = {
        "ok": True,
        "date": day,
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_search_terms_used": (
            search_terms[:int(args.max_queries)] if not args.no_web else []
        ),
        "exclusion_stats": {
            "titles_in_set": len(excl_titles),
            "urls_in_set": len(excl_urls),
        },
        "rss_context_items": len(rss_items),
        "search_results": search_results,
        "rss_headlines": [
            {"title": it["title"], "url": it["url"], "source": it["source"]}
            for it in rss_items[:30]
        ],
        "warnings": warnings,
    }
    _write_json(out, out_obj)
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out,
        "search_count": len([r for r in search_results if r.get("ok")]),
        "warnings": len(warnings),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
