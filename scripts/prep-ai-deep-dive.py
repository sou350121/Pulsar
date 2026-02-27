#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Deep Dive - Phase 1: Deterministic topic selection + URL prefetch.

- Read past 3 days from ai-app-daily.json, ai-app-social-intel.json, ai-daily-pick.json
- Rank by signal value: product_release > new tool > blog post > funding
- Dedup against ai-app-deep-dive-articles.json (already written)
- Prefetch top candidate URLs (best-effort, 15s timeout each)
- Output top-3 candidates with slug, target_dir, and prefetch results
  → Prefetch-success candidates sort first so the LLM agent has local content

Python 3.6+ (no external deps)

Real memory file structures (2026-02-15 verified):
  ai-app-daily.json:
    {"ai_app_daily": [{"date":"2026-02-14", "items":[{"title","url","source","category","importance","why",...}]}]}
  ai-app-social-intel.json:
    {"social_intel": [{"date":"2026-02-14", "signals":[{"type","source","person_or_entity","summary","url","signal_level"}]}]}
  ai-daily-pick.json:
    {"date":"2026-02-14", "items":[{"title","category","source","url","why_picked"}]}
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
    from urllib.error import HTTPError, URLError
except ImportError:
    Request = urlopen = HTTPError = URLError = None


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")

DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")
SOCIAL_PATH = os.path.join(MEM_DIR, "ai-app-social-intel.json")
PICK_PATH = os.path.join(MEM_DIR, "ai-daily-pick.json")
DEEP_DIVE_PATH = os.path.join(MEM_DIR, "ai-app-deep-dive-articles.json")

# Signal type priority (from social-intel "type" field): lower is better
SIGNAL_PRIORITY = {
    "major_release": 0,
    "product_release": 1,
    "breaking_change": 1,
    "new_tool": 2,
    "significant_update": 2,
    "architecture_change": 3,
    "partnership": 4,
    "blog_post": 4,
    "tutorial": 4,
    "funding": 5,
    "hiring": 6,
    "opinion": 6,
}

# Importance level priority: lower is better
IMPORTANCE_PRIORITY = {
    "actionable": 0,
    "strategic": 1,
    "high": 0,
    "medium": 2,
    "low": 3,
    "read-only": 3,
}

# Prefetch config
PREFETCH_TIMEOUT = 15  # seconds per URL
PREFETCH_MAX_CHARS = 8000  # max chars to store per prefetch
PREFETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; MoltbotPrep/1.0; "
    "+https://github.com/sou350121/Agent-Playbook)"
)


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


def _cutoff_date(day, days=3):
    try:
        d = _dt.datetime.strptime(day, "%Y-%m-%d")
        c = d - _dt.timedelta(days=days)
        return c.strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


def _entity_prefix(slug):
    """Extract the entity identifier from a slug (first 4 meaningful parts).

    Prevents the same product/company from being covered multiple times.
    e.g. "microsoft_agent_framework_rc_deep_dive" -> "microsoft_agent_framework"
    """
    # Strip trailing _deep_dive suffix
    s = (slug or "").rstrip("_")
    if s.endswith("_deep_dive"):
        s = s[:-len("_deep_dive")]
    parts = [p for p in s.split("_") if len(p) > 1]
    # Take first 3 parts as entity ID (e.g. "microsoft_agent_framework")
    return "_".join(parts[:3])


def _load_past_titles_and_urls():
    """Return (titles set, urls set, entity_dates dict) from deep dive articles.

    entity_dates maps entity_prefix -> most recent date covered (YYYY-MM-DD).
    Used to enforce a 14-day cooldown per product/entity.
    """
    data = _read_json(DEEP_DIVE_PATH, {"deep_dive_articles": []})
    titles = set()
    urls = set()
    entity_dates = {}  # entity_prefix -> most recent date string
    for entry in (data.get("deep_dive_articles") or []):
        if isinstance(entry, dict):
            t = (entry.get("title") or "").strip()
            if t:
                titles.add(t.lower())
            u = (entry.get("url") or "").strip()
            if u:
                urls.add(u.lower().rstrip("/"))
            # Track entity cooldown
            slug = entry.get("slug", "")
            date = entry.get("date", "")
            if slug and date:
                ent = _entity_prefix(slug)
                if ent and (ent not in entity_dates or date > entity_dates[ent]):
                    entity_dates[ent] = date
    return titles, urls, entity_dates


def _title_to_slug(title):
    """Convert title to snake_case slug for filename."""
    s = re.sub(r"\(.*?\)", "", title)
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s)
    s = s.strip().lower()
    s = re.sub(r"[\s-]+", "_", s)
    s = s[:60].rstrip("_")
    if not s:
        s = "unnamed_topic"
    return s + "_deep_dive"


def _norm(s):
    return (s or "").strip().lower()


# ------------------------------------------------------------------
# URL Prefetch
# ------------------------------------------------------------------

def _find_best_url(url):
    """Upgrade a generic GitHub repo root URL to its latest release page.

    Calls GitHub API /releases/latest (unauthenticated, 60 req/hr limit — safe
    for our usage: max 3 candidates x 3 runs/day = 9 req/day).
    Returns (best_url, was_upgraded).
    """
    if not url or not Request or not urlopen:
        return url, False

    # Only upgrade bare GitHub repo roots (no /releases/, /blob/, /pull/, /commit/, /tree/)
    gh_root = re.match(
        r'(https?://github\.com/[^/]+/[^/]+)/?$', url.rstrip('/'))
    if not gh_root:
        return url, False

    repo_root = gh_root.group(1)
    # Try /releases/latest via GitHub API
    owner_repo = '/'.join(repo_root.replace('https://github.com/', '').split('/')[:2])
    api_url = 'https://api.github.com/repos/%s/releases/latest' % owner_repo
    try:
        req = Request(api_url, headers={
            'User-Agent': PREFETCH_USER_AGENT,
            'Accept': 'application/vnd.github+json',
        })
        resp = urlopen(req, timeout=8)
        if resp.getcode() == 200:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
            html_url = data.get('html_url', '')
            if html_url and '/releases/tag/' in html_url:
                return html_url, True
    except Exception:
        pass

    # Fallback: try /releases page (still better than root)
    releases_url = repo_root + '/releases'
    try:
        req = Request(releases_url, headers={'User-Agent': PREFETCH_USER_AGENT})
        resp = urlopen(req, timeout=5)
        if resp.getcode() in (200, 301, 302):
            return releases_url, True
    except Exception:
        pass

    return url, False


def _build_alt_urls(url):
    """Generate alternative URLs to try if the primary one fails."""
    alts = []
    if not url:
        return alts

    # GitHub release page → try API endpoint
    # e.g. https://github.com/org/repo/releases → https://api.github.com/repos/org/repo/releases?per_page=5
    gh_match = re.match(
        r'https?://github\.com/([^/]+)/([^/]+)/releases/?$', url)
    if gh_match:
        owner, repo = gh_match.group(1), gh_match.group(2)
        alts.append(
            "https://api.github.com/repos/%s/%s/releases?per_page=3" % (owner, repo))

    # GitHub repo page → try README raw
    gh_repo_match = re.match(
        r'https?://github\.com/([^/]+)/([^/]+)/?$', url)
    if gh_repo_match:
        owner, repo = gh_repo_match.group(1), gh_repo_match.group(2)
        alts.append(
            "https://raw.githubusercontent.com/%s/%s/main/README.md" % (owner, repo))
        alts.append(
            "https://api.github.com/repos/%s/%s" % (owner, repo))

    # ProductHunt → usually JS-rendered, try adding .json or skip
    if "producthunt.com" in url:
        # ProductHunt rarely works with simple fetch; low priority
        pass

    return alts


def _try_fetch(url, timeout=PREFETCH_TIMEOUT):
    """Best-effort URL fetch. Returns (ok, status_code, text_snippet, error_msg)."""
    if not url or urlopen is None:
        return False, 0, "", "no_url_or_urllib"

    headers = {
        "User-Agent": PREFETCH_USER_AGENT,
        "Accept": "text/html,application/json,text/plain,*/*",
    }
    # GitHub API needs Accept header
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github+json"

    try:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=timeout)
        code = resp.getcode()
        raw = resp.read()
        # Try decode
        charset = "utf-8"
        ct = resp.headers.get("Content-Type", "")
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].split(";")[0].strip()
        text = raw.decode(charset, errors="replace")
        # Truncate
        snippet = text[:PREFETCH_MAX_CHARS]
        return True, code, snippet, ""
    except HTTPError as e:
        return False, e.code, "", "HTTP %d" % e.code
    except URLError as e:
        return False, 0, "", str(e.reason)[:120]
    except Exception as e:
        return False, 0, "", str(e)[:120]


def _extract_github_api_content(raw_json):
    """Extract readable content from GitHub API JSON responses.

    Handles:
    - /releases → list of releases with body (markdown)
    - /repos/{owner}/{repo} → description + topics
    """
    try:
        data = json.loads(raw_json)
    except Exception:
        return raw_json  # Fallback: return as-is

    # Release list → concatenate release notes
    if isinstance(data, list):
        parts = []
        for release in data[:3]:
            if not isinstance(release, dict):
                continue
            name = release.get("name") or release.get("tag_name") or ""
            body = release.get("body") or ""
            published = release.get("published_at") or ""
            url = release.get("html_url") or ""
            if name or body:
                parts.append("## %s\n\nPublished: %s\nURL: %s\n\n%s" % (
                    name, published, url, body))
        return "\n\n---\n\n".join(parts) if parts else raw_json

    # Single repo → description + topics + readme info
    if isinstance(data, dict) and data.get("full_name"):
        desc = data.get("description") or ""
        topics = ", ".join(data.get("topics") or [])
        stars = data.get("stargazers_count", 0)
        lang = data.get("language") or ""
        return ("# %s\n\n%s\n\nTopics: %s\nLanguage: %s\nStars: %s\n"
                % (data.get("full_name", ""), desc, topics, lang, stars))

    return raw_json


def _strip_html_tags(html):
    """Rough HTML tag stripping for snippet readability."""
    # Remove script/style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html,
                  flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _prefetch_candidate(candidate):
    """Try to prefetch a candidate's URL. Modifies candidate in-place.

    Adds fields:
      prefetch_ok: bool
      prefetch_status: int
      prefetch_snippet: str (cleaned text, max PREFETCH_MAX_CHARS)
      prefetch_snippet_file: str (path to full snippet file, if saved)
      prefetch_error: str
      prefetch_url_used: str (which URL actually worked)
    """
    url = candidate.get("url", "")
    alt_urls = _build_alt_urls(url)
    # For GitHub URLs, try API first (cleaner content than SSR HTML)
    if alt_urls and ("github.com" in url):
        urls_to_try = alt_urls + [url]
    else:
        urls_to_try = [url] + alt_urls

    for try_url in urls_to_try:
        if not try_url:
            continue
        ok, status, snippet, err = _try_fetch(try_url)
        if ok and snippet and len(snippet.strip()) > 100:
            # GitHub API JSON → extract release notes body
            if "api.github.com" in try_url:
                cleaned = _extract_github_api_content(snippet)
            elif "<html" in snippet.lower() or "<body" in snippet.lower():
                cleaned = _strip_html_tags(snippet)
            else:
                cleaned = snippet

            # Save full snippet to file for the agent to read
            slug = candidate.get("slug", "unknown")
            snippet_path = os.path.join(
                TMP_DIR, "prefetch-%s.txt" % slug)
            try:
                with open(snippet_path, "w", encoding="utf-8") as f:
                    f.write("# Prefetched content for: %s\n" % candidate.get("title", ""))
                    f.write("# URL: %s\n" % try_url)
                    f.write("# Fetched at: %s\n\n" %
                            _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
                    f.write(cleaned[:PREFETCH_MAX_CHARS])
            except Exception:
                snippet_path = ""

            candidate["prefetch_ok"] = True
            candidate["prefetch_status"] = status
            candidate["prefetch_snippet"] = cleaned[:2000]  # short preview in JSON
            candidate["prefetch_snippet_file"] = snippet_path
            candidate["prefetch_error"] = ""
            candidate["prefetch_url_used"] = try_url
            return

    # All URLs failed
    candidate["prefetch_ok"] = False
    candidate["prefetch_status"] = 0
    candidate["prefetch_snippet"] = ""
    candidate["prefetch_snippet_file"] = ""
    candidate["prefetch_error"] = err or "all_urls_failed"
    candidate["prefetch_url_used"] = ""


# ------------------------------------------------------------------
# Data extraction (unchanged from rev.3)
# ------------------------------------------------------------------

def _extract_daily_items(data, cutoff, day):
    """Extract items from ai-app-daily.json.

    Real structure: {"ai_app_daily": [{"date":"...", "items":[...]}]}
    Each daily entry has a "date" and "items" list.
    Items have: title, url, source, category, importance, why, developer, labels
    """
    items = []
    daily_entries = data.get("ai_app_daily") or []
    if not isinstance(daily_entries, list):
        daily_entries = []

    for entry in daily_entries:
        if not isinstance(entry, dict):
            continue
        entry_date = entry.get("date", "")
        if entry_date < cutoff or entry_date > day:
            continue

        for p in (entry.get("items") or []):
            if not isinstance(p, dict):
                continue

            title = (p.get("title") or "").strip()
            url = (p.get("url") or "").strip()
            if not title or not url:
                continue

            importance = p.get("importance", "read-only")
            signal_type = "blog_post"  # default for daily items
            summary = (p.get("why") or p.get("summary") or
                       p.get("description") or "").strip()
            category = (p.get("category") or "").strip()

            items.append({
                "title": title,
                "url": url,
                "source": "daily-%s" % (p.get("source") or "unknown"),
                "signal_type": signal_type,
                "importance": importance,
                "summary": summary,
                "category": category,
                "date": entry_date,
            })
    return items


def _extract_social_items(data, cutoff, day):
    """Extract items from ai-app-social-intel.json.

    Real structure: {"social_intel": [{"date":"...", "signals":[...]}]}
    Signals have: type, source, person_or_entity, summary, url, signal_level
    """
    items = []
    intel_entries = data.get("social_intel") or []
    if not isinstance(intel_entries, list):
        intel_entries = []

    for entry in intel_entries:
        if not isinstance(entry, dict):
            continue
        entry_date = entry.get("date", "")
        if entry_date < cutoff or entry_date > day:
            continue

        for s in (entry.get("signals") or []):
            if not isinstance(s, dict):
                continue

            entity = (s.get("person_or_entity") or s.get("entity") or "").strip()
            summary = (s.get("summary") or "").strip()
            title = entity if entity else summary[:80]
            if not title:
                continue

            url = (s.get("url") or "").strip()
            signal_type = s.get("type", "opinion")
            level = s.get("signal_level", "medium")

            items.append({
                "title": "%s: %s" % (entity, summary[:60]) if entity and summary else title,
                "url": url,
                "source": "social-%s" % (s.get("source") or "unknown"),
                "signal_type": signal_type,
                "importance": level,
                "summary": summary,
                "category": "",
                "date": entry_date,
            })
    return items


def _extract_pick_items(data, cutoff, day):
    """Extract items from ai-daily-pick.json.

    New structure: {"daily_picks":[{"date":"...","items":[...]},...]}
    Legacy structure: {"date":"2026-02-14", "items":[{"title","category","source","url","why_picked"}]}
    """
    items = []

    # Resolve to a list of {date, items} entries
    daily_picks = data.get("daily_picks")
    if isinstance(daily_picks, list):
        entries = daily_picks
    elif data.get("date") and isinstance(data.get("items"), list):
        # Backward compat: old flat single-day structure
        entries = [data]
    else:
        return items

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pick_date = entry.get("date", "")
        if pick_date < cutoff or pick_date > day:
            continue

        pick_items = entry.get("items") or []
        if not isinstance(pick_items, list):
            continue

        for p in pick_items:
            if not isinstance(p, dict):
                continue

            title = (p.get("title") or "").strip()
            url = (p.get("url") or "").strip()
            if not title or not url:
                continue

            summary = (p.get("why_picked") or p.get("summary") or "").strip()
            category = (p.get("category") or "").strip()

            items.append({
                "title": title,
                "url": url,
                "source": "pick-%s" % (p.get("source") or "unknown"),
                "signal_type": "blog_post",
                "importance": "actionable",
                "summary": summary,
                "category": category,
                "date": pick_date,
            })
    return items


def _platform_penalty(item):
    """Penalise .NET/C#-only tools: vibe coder uses Python/JS, not .NET.
    Returns 0 (no penalty) to 3 (strong penalty).
    """
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
        item.get("category", ""),
    ]).lower()
    # .NET-only signals
    dotnet_kw = [".net", "c#", "csharp", "nuget", "blazor", "asp.net", "dotnet", "wpf", "xamarin"]
    dotnet_hits = sum(1 for k in dotnet_kw if k in text)
    # Python/JS/cross-platform signals (vibe coder friendly)
    friendly_kw = ["python", "javascript", "typescript", "node", "api", "open source",
                   "no-code", "claude", "chatgpt", "llm", "mcp", "n8n", "make.com"]
    friendly_hits = sum(1 for k in friendly_kw if k in text)

    if dotnet_hits >= 2 and friendly_hits == 0:
        return 3   # strongly .NET-only → big penalty
    if dotnet_hits >= 1 and friendly_hits == 0:
        return 1   # mildly .NET-specific → small penalty
    return 0


def _arch_bonus(item):
    """Bonus (negative penalty) for tools with architectural depth / production usage.
    Deep dive articles work best when the tool has:
    - Non-trivial architecture (not just an API wrapper)
    - Known failure modes or production gotchas worth discussing
    - Real user community / production deployments
    Returns 0 (no bonus) to -2 (strong bonus = higher priority).
    """
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
        item.get("why", ""),
        item.get("category", ""),
    ]).lower()
    # Signals of architectural depth / production relevance
    arch_kw = ["orchestration", "multi-agent", "distributed", "async", "concurrent",
               "memory", "state", "persistent", "workflow", "pipeline", "queue",
               "gateway", "proxy", "runtime", "execution", "scheduler",
               "breaking change", "migration", "architecture", "rewrite", "v2", "v3"]
    # Signals of API-wrapper / thin tools (less interesting for deep dive)
    thin_kw = ["sdk", "wrapper", "client", "bindings", "connector",
               "plugin", "extension", "integration", "adapter"]
    arch_hits = sum(1 for k in arch_kw if k in text)
    thin_hits = sum(1 for k in thin_kw if k in text)
    if arch_hits >= 3 and thin_hits == 0:
        return -2  # strong architectural depth
    if arch_hits >= 1 and thin_hits == 0:
        return -1  # some depth
    return 0


def _score_item(item):
    """Return a tuple for sorting: lower = better."""
    signal_type = _norm(item.get("signal_type", ""))
    importance = _norm(item.get("importance", ""))
    has_url = 0 if item.get("url") else 1
    platform_pen = _platform_penalty(item)
    arch_bon = _arch_bonus(item)

    return (
        IMPORTANCE_PRIORITY.get(importance, 5) + platform_pen + arch_bon,
        SIGNAL_PRIORITY.get(signal_type, 7),
        has_url,
        # Newer first
        "".join(chr(255 - ord(c)) for c in item.get("date", "0000-00-00")),
    )


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD override")
    ap.add_argument("--out", default="", help="Output path override")
    ap.add_argument("--days", type=int, default=3, help="Lookback days")
    ap.add_argument("--max", type=int, default=3, help="Max candidates (default 3 for fallback)")
    ap.add_argument("--no-prefetch", action="store_true",
                    help="Skip URL prefetch (faster, for testing)")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out_path = (args.out.strip()
                or os.path.join(TMP_DIR,
                                "ai-deep-dive-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    cutoff = _cutoff_date(day, args.days)
    past_titles, past_urls, past_entities = _load_past_titles_and_urls()

    # --- Collect items from all sources ---
    daily_data = _read_json(DAILY_PATH, {})
    social_data = _read_json(SOCIAL_PATH, {})
    pick_data = _read_json(PICK_PATH, {})

    all_items = []
    all_items.extend(_extract_daily_items(daily_data, cutoff, day))
    all_items.extend(_extract_social_items(social_data, cutoff, day))
    all_items.extend(_extract_pick_items(pick_data, cutoff, day))

    # --- Dedup and filter ---
    eligible = []
    seen_titles = set()

    for item in all_items:
        title = item.get("title", "")
        url = item.get("url", "")
        t_lower = _norm(title)
        u_lower = _norm(url).rstrip("/")

        # Skip if already written (exact title or URL match)
        if t_lower in past_titles:
            continue
        if u_lower and u_lower in past_urls:
            continue

        # Skip if same entity covered within the last 14 days
        # Prevents the same product/company from being deep-dived repeatedly.
        item_slug = _title_to_slug(title)
        item_entity = _entity_prefix(item_slug)
        if item_entity and item_entity in past_entities:
            last_covered = past_entities[item_entity]
            try:
                import datetime as _dt2
                delta = (
                    _dt2.datetime.strptime(day, "%Y-%m-%d") -
                    _dt2.datetime.strptime(last_covered, "%Y-%m-%d")
                ).days
                if delta < 14:
                    continue  # entity on cooldown
            except Exception:
                pass  # date parse failure: allow through

        # Skip if already seen in this batch
        if t_lower in seen_titles:
            continue
        seen_titles.add(t_lower)

        # Must have a URL for deep dive (need to web_fetch)
        if not url:
            continue

        eligible.append(item)

    # Rank by score
    eligible.sort(key=_score_item)

    # Take top N
    top = eligible[:args.max]

    # Build candidates
    candidates = []
    for item in top:
        title = item.get("title", "")
        slug = _title_to_slug(title)

        # URL upgrade: try to find specific release URL for generic GitHub roots
        raw_url = item.get("url", "")
        best_url, was_upgraded = _find_best_url(raw_url)

        candidates.append({
            "title": title,
            "url": best_url,
            "url_original": raw_url if was_upgraded else "",
            "url_upgraded": was_upgraded,
            "source": item.get("source", ""),
            "signal_type": item.get("signal_type", ""),
            "importance": item.get("importance", ""),
            "summary": item.get("summary", ""),
            "category": item.get("category", ""),
            "slug": slug,
            "target_dir": "memory/blog/archives/deep-dive",
        })

    # --- Prefetch URLs (best-effort) ---
    prefetch_stats = {"attempted": 0, "success": 0, "failed": 0}
    if not args.no_prefetch and candidates:
        for c in candidates:
            prefetch_stats["attempted"] += 1
            _prefetch_candidate(c)
            if c.get("prefetch_ok"):
                prefetch_stats["success"] += 1
            else:
                prefetch_stats["failed"] += 1

        # Re-sort: prefetch_ok=True first, then by original order
        # (preserve original score ranking within each group)
        ok_candidates = [c for c in candidates if c.get("prefetch_ok")]
        fail_candidates = [c for c in candidates if not c.get("prefetch_ok")]
        candidates = ok_candidates + fail_candidates

    out_obj = {
        "ok": True,
        "date": day,
        "date_range": "%s to %s" % (cutoff, day),
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_type": "ai_app_deep_dive",
        "candidates": candidates,
        "stats": {
            "total_items_in_range": len(all_items),
            "eligible_after_dedup": len(eligible),
            "past_articles_excluded": len(past_titles),
            "selected": len(candidates),
            "prefetch": prefetch_stats,
            "sources": {
                "daily": len([i for i in all_items if i["source"].startswith("daily-")]),
                "social": len([i for i in all_items if i["source"].startswith("social-")]),
                "pick": len([i for i in all_items if i["source"].startswith("pick-")]),
            },
        },
    }

    _write_json(out_path, out_obj)

    # Stdout summary
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out_path,
        "selected": len(candidates),
        "eligible": len(eligible),
        "prefetch_ok": prefetch_stats.get("success", 0),
        "prefetch_fail": prefetch_stats.get("failed", 0),
        "candidate_title": candidates[0]["title"] if candidates else "",
        "candidate_prefetch_ok": candidates[0].get("prefetch_ok", False) if candidates else False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
