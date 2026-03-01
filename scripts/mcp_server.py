#!/usr/bin/env python3.11
"""
Pulsar MCP Server — exposes Pulsar's knowledge base as MCP tools.

Install:  pip install mcp
Run:      python3 /home/admin/clawd/scripts/mcp_server.py

Claude Desktop ~/.config/claude/claude_desktop_config.json:
  {
    "mcpServers": {
      "pulsar": {
        "command": "python3",
        "args": ["/home/admin/clawd/scripts/mcp_server.py"]
      }
    }
  }
"""

import glob
import json
import os
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

MEMORY_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
SCRIPTS_DIR = os.environ.get("PULSAR_SCRIPTS_DIR", os.path.dirname(os.path.abspath(__file__)))

import sys as _sys
if SCRIPTS_DIR not in _sys.path:
    _sys.path.insert(0, SCRIPTS_DIR)

mcp = FastMCP("pulsar")


# ── helpers ───────────────────────────────────────────────────────────────────

def _load(filename: str) -> dict:
    with open(os.path.join(MEMORY_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def _date_within(date_str: str, days: int) -> bool:
    """True if date_str (YYYY-MM-DD prefix) falls within the last N days."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return d >= date.today() - timedelta(days=days)
    except (ValueError, TypeError):
        return False


# ⚡ > 🔧 > 📖 > ❌  (lower index = higher priority)
_RATING_RANK = {"⚡": 0, "🔧": 1, "📖": 2, "❌": 3}


def _rating_gte(rating: str, min_rating: str) -> bool:
    """True if `rating` is at least as good as `min_rating`."""
    return _RATING_RANK.get(rating, 99) <= _RATING_RANK.get(min_rating, 99)


def _pick(obj: dict, keys: tuple) -> dict:
    return {k: obj.get(k) for k in keys}


# ── Signal tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def get_vla_signals(days: int = 7, min_rating: str = "🔧") -> str:
    """
    Return recent VLA (Vision-Language-Action) paper signals from Pulsar.

    Args:
        days: How many days back to look (default 7).
        min_rating: Minimum signal quality — ⚡ breakthrough, 🔧 solid,
                    📖 reference, ❌ noise. Default 🔧.

    Returns JSON with count + list of signals (title, date, url, rating, reason, affiliation, tag).
    """
    data = _load("vla-daily-hotspots.json")
    keys = ("title", "date", "url", "rating", "reason", "affiliation", "tag")
    filtered = [
        _pick(p, keys)
        for p in data.get("reported_papers", [])
        if _date_within(p.get("date", ""), days)
        and _rating_gte(p.get("rating", "❌"), min_rating)
    ]
    filtered.sort(key=lambda x: (_RATING_RANK.get(x.get("rating", "❌"), 99), x.get("date", "")))
    return json.dumps({"count": len(filtered), "signals": filtered}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_ai_signals(days: int = 7) -> str:
    """
    Return recent AI App / Agent daily picks from Pulsar.

    Args:
        days: How many days back to look (default 7).

    Returns JSON with count + list of picks (date, title, category, source, url, why_picked).
    """
    data = _load("ai-daily-pick.json")
    result = []
    for day in data.get("daily_picks", []):
        if _date_within(day.get("date", ""), days):
            for item in day.get("items", []):
                result.append({"date": day["date"], **item})
    return json.dumps({"count": len(result), "picks": result}, ensure_ascii=False, indent=2)


@mcp.tool()
def search_signals(keyword: str, days: int = 30) -> str:
    """
    Full-text search across all Pulsar signals (VLA papers + AI picks).

    Args:
        keyword: Search term (case-insensitive).
        days: How many days back to look (default 30).

    Returns JSON with matched VLA papers and AI picks.
    """
    kw = keyword.lower()

    vla_data = _load("vla-daily-hotspots.json")
    vla_hits = [
        _pick(p, ("title", "date", "url", "rating", "reason"))
        for p in vla_data.get("reported_papers", [])
        if _date_within(p.get("date", ""), days)
        and kw in (
            p.get("title", "") + " " +
            p.get("reason", "") + " " +
            p.get("abstract_snippet", "")
        ).lower()
    ]

    ai_data = _load("ai-daily-pick.json")
    ai_hits = []
    for day in ai_data.get("daily_picks", []):
        if _date_within(day.get("date", ""), days):
            for item in day.get("items", []):
                if kw in (item.get("title", "") + " " + item.get("why_picked", "")).lower():
                    ai_hits.append({"date": day["date"], **item})

    return json.dumps({
        "keyword": keyword,
        "vla_hits": len(vla_hits),
        "ai_hits": len(ai_hits),
        "vla": vla_hits,
        "ai": ai_hits,
    }, ensure_ascii=False, indent=2)


# ── Knowledge tools ───────────────────────────────────────────────────────────

@mcp.tool()
def get_assumptions(domain: str = "all") -> str:
    """
    Return active research assumptions/hypotheses tracked by Pulsar.

    Args:
        domain: 'vla', 'ai_app', or 'all' (default).

    Returns JSON list of assumptions (id, status, domain, hypothesis, keywords, created).
    Note: confidence scores may not yet be populated for all entries.
    """
    data = _load("assumptions.json")
    items = data.get("assumptions", [])
    if domain != "all":
        items = [a for a in items if a.get("domain", "").lower() == domain.lower()]
    # Exclude terminated states
    items = [a for a in items if a.get("status") not in ("archived", "invalidated")]
    keys = ("id", "status", "domain", "hypothesis", "keywords", "source", "created")
    result = [_pick(a, keys) for a in items]
    return json.dumps({"count": len(result), "assumptions": result}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_vla_sota(days: int = 30) -> str:
    """
    Return VLA state-of-the-art benchmark records tracked by Pulsar.

    Args:
        days: How many days back to look (default 30). Pass 0 for all records.

    Returns JSON list of SOTA entries (benchmark, split, metric, value, model, paper_id, baseline, date).
    """
    data = _load("vla-sota-tracker.json")
    entries = data.get("vla-sota-tracker", [])
    if days > 0:
        entries = [e for e in entries if _date_within(e.get("date", ""), days)]
    keys = ("benchmark", "split", "metric", "value", "model", "paper_id", "baseline", "date", "source")
    return json.dumps({"count": len(entries), "sota": [_pick(e, keys) for e in entries]},
                      ensure_ascii=False, indent=2)


@mcp.tool()
def get_vla_releases(days: int = 30) -> str:
    """
    Return recent VLA model/library release events tracked by Pulsar.

    Args:
        days: How many days back to look (default 30). Pass 0 for all.

    Returns JSON list (source, type, event, detail, relevance, url, date, layer, repo).
    """
    data = _load("vla-release-tracker.json")
    entries = data.get("vla-release-tracker", [])
    if days > 0:
        entries = [e for e in entries if _date_within(e.get("date", ""), days)]
    keys = ("source", "type", "event", "detail", "relevance", "url", "date", "layer", "repo")
    return json.dumps({"count": len(entries), "releases": [_pick(e, keys) for e in entries]},
                      ensure_ascii=False, indent=2)


@mcp.tool()
def get_social_intel(domain: str = "vla", days: int = 14) -> str:
    """
    Return social intelligence signals (Twitter/community buzz) tracked by Pulsar.

    Args:
        domain: 'vla' (structured JSON) or 'ai' (markdown archives).
        days: How many days back to look (default 14).

    Returns JSON with signals for VLA, or report content list for AI.
    """
    if domain == "vla":
        data = _load("vla-social-intel.json")
        result = []
        for entry in data.get("social_intel", []):
            if _date_within(entry.get("date", ""), days):
                for sig in entry.get("signals", []):
                    result.append({"date": entry["date"], **sig})
        return json.dumps({"domain": "vla", "count": len(result), "signals": result},
                          ensure_ascii=False, indent=2)

    # AI social: dated markdown files  _ai_social_YYYY-MM-DD.md
    pattern = os.path.join(MEMORY_DIR, "_ai_social_*.md")
    cutoff = date.today() - timedelta(days=days)
    reports = []
    for fpath in sorted(glob.glob(pattern), reverse=True):
        fname = os.path.basename(fpath)
        try:
            date_str = fname.removeprefix("_ai_social_").removesuffix(".md")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            break
        with open(fpath, encoding="utf-8") as f:
            reports.append({"date": date_str, "content": f.read()})
    return json.dumps({"domain": "ai", "count": len(reports), "reports": reports},
                      ensure_ascii=False, indent=2)


# ── Meta tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_predictions(domain: str = "all") -> str:
    """
    Return recent predictions and previous-prediction results from Pulsar biweekly reasoning.

    Args:
        domain: 'vla', 'ai', or 'all' (default). Returns up to 3 latest entries each.

    Returns JSON with latest biweekly reasoning summaries per domain.
    """
    keys = ("date", "period", "key_signals", "predictions", "previous_predictions_result")
    result: dict = {}

    if domain in ("vla", "all"):
        try:
            data = _load("biweekly-reasoning.json")
            entries = sorted(data.get("biweekly_reasoning", []),
                             key=lambda x: x.get("date", ""), reverse=True)[:3]
            result["vla"] = [_pick(e, keys) for e in entries]
        except FileNotFoundError:
            result["vla"] = []

    if domain in ("ai", "all"):
        # Try likely filenames for the AI biweekly store
        for fname in ("ai-app-biweekly-reasoning.json", "ai-biweekly-reasoning.json"):
            try:
                data = _load(fname)
                entries = sorted(data.get("biweekly_reasoning", []),
                                 key=lambda x: x.get("date", ""), reverse=True)[:3]
                result["ai"] = [_pick(e, keys) for e in entries]
                break
            except FileNotFoundError:
                continue
        else:
            result["ai"] = []

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_pipeline_health() -> str:
    """
    Return Pulsar pipeline health: last watchdog run + 7-day signal volume stats.

    Returns JSON with last watchdog entry and recent daily stats (total_papers_scanned,
    total_a_matches, total_b_matches per day).
    """
    wdog = _load("watchdog-log.json")
    # New schema uses 'entries', old schema uses 'watchdog_log'
    all_entries = wdog.get("entries") or wdog.get("watchdog_log", [])
    latest = sorted(all_entries,
                    key=lambda x: x.get("ts", x.get("date", "")), reverse=True)[:1]

    stats_data = _load("daily-stats.json")
    recent = sorted(stats_data.get("daily_stats", []),
                    key=lambda x: x.get("date", ""), reverse=True)[:7]

    return json.dumps({
        "last_watchdog": latest[0] if latest else None,
        "recent_stats": recent,
    }, ensure_ascii=False, indent=2)


# ── Domain tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def list_domains() -> str:
    """
    List all configured Pulsar domains with their names and descriptions.

    Returns JSON array of domain keys, names, and descriptions.
    """
    from _domain_loader import list_domains as _list, load_domain as _load
    result = []
    for key in _list():
        d = _load(key)
        result.append({"key": key, "name": d.name, "description": d.description})
    return json.dumps({"count": len(result), "domains": result}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_domain_config(domain: str) -> str:
    """
    Return the active config (keywords, research directions) for a Pulsar domain.

    Args:
        domain: Domain key — 'vla' or 'ai_app'.

    Returns JSON with the full active config for that domain.
    """
    from _domain_loader import load_domain as _load
    d = _load(domain)
    return json.dumps(d.active_config(), ensure_ascii=False, indent=2)



# ── Search tool ──────────────────────────────────────────────────────────────

@mcp.tool()
def search_memory(query: str, days: int = 60, top: int = 5, source_type: str = "") -> str:
    """
    Semantic search over Pulsar's 60-day memory window.

    Uses DashScope text-embedding-v3 to embed the query and returns the most
    relevant memory chunks ranked by cosine similarity.

    Args:
        query: Natural language query string.
        days: Only search within this many past days (default 60).
        top: Number of top results to return (default 5).
        source_type: Optional filter — one of: ai_daily_pick, ai_social,
                     vla_social, vla_biweekly, biweekly_reflection,
                     calibration, upstream. Empty string = no filter.

    Returns JSON with count and results array (score, date, source, source_type, section, text).
    """
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "semantic_search",
        os.path.join(SCRIPTS_DIR, "semantic-search.py"),
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    results = _mod.search(
        query=query,
        days=days,
        top=top,
        source_type=source_type or None,
    )
    return json.dumps({"count": len(results), "results": results}, ensure_ascii=False, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
