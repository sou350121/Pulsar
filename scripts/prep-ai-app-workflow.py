#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Workflow Inspiration - Phase 1: Deterministic Search & Candidate Prep.

- Call Perplexity API for workflow/best-practice/case-study content
- Read exclusion sets (daily + social intel + workflow digest history)
- Filter duplicates
- Output candidates JSON for LLM curation

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
WORKFLOW_DIGEST_PATH = os.path.join(MEM_DIR, "ai-app-workflow-digest.json")
SOCIAL_INTEL_PATH = os.path.join(MEM_DIR, "ai-app-social-intel.json")
DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
MOLTBOT_CONFIG = "/home/admin/.moltbot/moltbot.json"
# Switched from OpenRouter/Perplexity to DashScope Qwen 2026-02-23 (OpenRouter 402)
DASHSCOPE_AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3.5-plus"
DEDUP_SCRIPT = "/home/admin/clawd/scripts/prep-ai-app-dedup.py"

DEFAULT_SEARCH_TERMS = [
    # ── 社区真实工作流案例（自然语言查询，避免复杂 site: 语法）──
    # "我是这样自动化的" 真实工作流分享（Reddit/HN/博客）
    "reddit AI workflow automation I automated I built n8n Claude GPT real use case 2026",
    # n8n 社区教程 + 真实操作步骤
    "n8n workflow tutorial real use case step by step reddit community 2026",

    # ── 角色专属可操作工作流 ──
    # PM/创作者/分析师的 AI 工作流实践
    "AI workflow step by step how to automate marketer content creator analyst Claude 2026",
    # 个人/小团队已落地的 AI 自动化案例
    "how I automated daily workflow productivity AI solo founder freelancer 2026",

    # ── 工具整合场景 ──
    # Make/Zapier/n8n 整合 AI 的具体教程
    "Make.com Zapier n8n AI integration tutorial workflow result 2026",
    # MCP 整合进真实工作场景的案例
    "MCP model context protocol workflow integration use case tutorial 2026",

    # ── 深度实战来源 ──
    # Dev.to / 博客中的 AI 自动化实战文章
    "dev.to AI automation workflow implementation experience step by step 2026",
    # 以结果为主的工作流落地：before-after 对比
    "AI workflow automation saves hours per week before after result ROI 2026",
]

# Domains known for low-quality SEO / AI-generated filler content
DOMAIN_BLOCKLIST = {
    "spark`co.ai",
    "analyticsvidhya.com",
    "musketeerstech.com",
    "geeksforgeeks.org",
    "javatpoint.com",
    "tutorialspoint.com",
    "w3schools.com",
    "guru99.com",
    "simplilearn.com",
    "knowledgehut.com",
    "mygreatlearning.com",
}


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
    """Build exclusion set from dedup file + social intel + daily + workflow digest history."""
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
                if s:
                    titles.add(s)
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

    # 4) Workflow digest history (all entries — avoid repeating past picks)
    digest = _read_json(WORKFLOW_DIGEST_PATH, {})
    for entry in (digest.get("workflow_digest") or []):
        if not isinstance(entry, dict):
            continue
        # Support both new schema (inspiration_cards) and old schema (patterns/items)
        items = (entry.get("inspiration_cards") or
                 entry.get("patterns") or
                 entry.get("items") or [])
        for it in items:
            if not isinstance(it, dict):
                continue
            t = _norm(it.get("title", ""))
            u = _norm(it.get("url", ""))
            # Old schema had "insight"; new has "first_step" — dedup on both
            extra = _norm(it.get("insight", "") or it.get("first_step", ""))
            if t:
                titles.add(t)
            if u:
                urls.add(u)
            if extra and len(extra) > 15:
                titles.add(extra)

    titles.discard("")
    urls.discard("")
    return titles, urls


# ------------------------------------------------------------------
# Perplexity API (via OpenRouter)
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


def _two_weeks_ago():
    d = _dt.datetime.utcnow() + _dt.timedelta(hours=8) - _dt.timedelta(days=14)
    return d.strftime("%Y-%m-%d")


def _extract_domain(url):
    """Extract bare domain from a URL."""
    url = (url or "").strip()
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1).lower() if m else ""


def _is_blocked_domain(url):
    """Check if URL belongs to a blocked domain."""
    domain = _extract_domain(url)
    if not domain:
        return False
    for blocked in DOMAIN_BLOCKLIST:
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False


def _validate_url(url, timeout=5):
    """HEAD-request a URL to check if it's reachable (200/301/302)."""
    if not url or not Request or not urlopen:
        return False
    try:
        req = Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (compatible; ClawdBot/1.0)"
        })
        rsp = urlopen(req, timeout=timeout)
        return rsp.getcode() in (200, 301, 302)
    except Exception:
        # Fallback: some servers reject HEAD, try GET with small read
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ClawdBot/1.0)"
            })
            rsp = urlopen(req, timeout=timeout)
            rsp.read(512)  # read minimal bytes
            return rsp.getcode() in (200, 301, 302)
        except Exception:
            return False


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
                           "ai-app-workflow-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    search_terms = list(DEFAULT_SEARCH_TERMS)

    # Build exclusion set
    excl_titles, excl_urls = _build_exclusion_set(day)

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

    # Filter URLs against exclusion set + blocked domains
    for res in search_results:
        if not res.get("ok"):
            continue
        raw_urls = res.get("urls") or []
        clean = [u for u in raw_urls
                 if not _is_excluded("", u, excl_titles, excl_urls)
                 and not _is_blocked_domain(u)]
        res["excluded_url_count"] = len(raw_urls) - len(clean)
        res["urls"] = clean

    # Validate URLs (HEAD request) — mark invalid ones
    all_urls = set()
    for res in search_results:
        if res.get("ok"):
            for u in (res.get("urls") or []):
                all_urls.add(u)
    url_validity = {}
    validated_count = 0
    for u in sorted(all_urls):
        if validated_count >= 30:
            break
        url_validity[u] = _validate_url(u, timeout=5)
        validated_count += 1

    # Annotate each result with url_valid flags
    invalid_urls_found = 0
    for res in search_results:
        if not res.get("ok"):
            continue
        annotated = []
        for u in (res.get("urls") or []):
            valid = url_validity.get(u, True)  # assume valid if not checked
            annotated.append({"url": u, "url_valid": valid})
            if not valid:
                invalid_urls_found += 1
        res["urls_annotated"] = annotated

    out_obj = {
        "ok": True,
        "date": day,
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_type": "workflow_inspiration",
        "search_terms_used": (
            search_terms[:int(args.max_queries)] if not args.no_web else []
        ),
        "exclusion_stats": {
            "titles_in_set": len(excl_titles),
            "urls_in_set": len(excl_urls),
        },
        "url_validation": {
            "checked": validated_count,
            "invalid": invalid_urls_found,
        },
        "search_results": search_results,
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
