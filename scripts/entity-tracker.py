#!/usr/bin/env python3.11
"""
Entity Tracker — P2 #9

Extracts {lab, method, benchmark} entities from every ⚡/🔧-rated VLA signal
and high-relevance AI App picks, building a rolling 90-day structured index.

Sources:
  VLA:    tmp/vla-daily-rating-out-{date}.json  (⚡/🔧 papers)
  AI App: memory/ai-daily-pick.json             (daily picks)

Output:
  memory/entity-index.json  — rolling 90-day entity index

CLI query:
  python3 entity-tracker.py --query "DeepMind" --days 90
  python3 entity-tracker.py --list labs --days 30
  python3 entity-tracker.py --stats
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ---------------------------------------------------------------------------
MEM_DIR  = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR  = os.path.join(MEM_DIR, "tmp")
INDEX    = os.path.join(MEM_DIR, "entity-index.json")
KEEP_DAYS = 90
# ---------------------------------------------------------------------------

# Known benchmarks (VLA domain)
BENCHMARKS = [
    "SIMPLER", "LIBERO", "OXE", "BridgeData", "RLBench", "MetaWorld",
    "FurnitureBench", "ManiSkill", "AnyManip", "CALVIN", "OpenX",
    "HumanoidBench", "LEROBOT", "BiGym", "INSERT", "DROID",
]

# Known AI orgs / labs for AI App entity extraction
AI_ORGS = [
    "OpenAI", "Anthropic", "Google", "DeepMind", "Google DeepMind",
    "Microsoft", "Meta", "Apple", "Amazon", "NVIDIA", "Alibaba",
    "Baidu", "Tencent", "ByteDance", "Mistral", "Cohere", "AI21",
    "Hugging Face", "Stability AI", "xAI", "Perplexity", "Cursor",
    "Replit", "Cognition", "Devin", "LangChain", "LlamaIndex",
    "Qwen", "DeepSeek", "Moonshot", "Zhipu", "MiniMax",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=days)).strftime("%Y-%m-%d")


def _read_json(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, obj: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ---------------------------------------------------------------------------
# Entity extraction — VLA
# ---------------------------------------------------------------------------

def _extract_labs_vla(paper: dict) -> list[str]:
    """Parse [Lab1|Lab2] from affiliation field."""
    affil = paper.get("affiliation", "")
    labs = []
    # Match [...] blocks (possibly multiple)
    for block in re.findall(r"\[([^\]]+)\]", affil):
        for part in block.split("|"):
            name = part.strip()
            if name:
                labs.append(name)
    return labs


def _extract_method_vla(paper: dict) -> str | None:
    """
    Extract method name from title.
    Pattern: first hyphenated/CamelCase term before ':' or end.
    e.g. 'Fast-ThinkAct: ...' → 'Fast-ThinkAct'
         'GeCo-SRT: ...'     → 'GeCo-SRT'
    """
    title = paper.get("title", "")
    # Remove leading punctuation
    title = title.strip()
    # If title has ':', take the part before ':'
    before_colon = title.split(":")[0].strip() if ":" in title else title

    # Look for a token that is: hyphenated, CamelCase abbreviation, or ALL-CAPS acronym
    # Heuristic: first 1-3 tokens that look like a method name
    tokens = before_colon.split()
    if not tokens:
        return None

    # Case 1: starts with CamelCase acronym with digits or hyphens (e.g. Fast-ThinkAct, GeCo-SRT)
    first = tokens[0]
    if re.match(r"^[A-Z][A-Za-z0-9]*[-][A-Za-z0-9]+", first):
        return first
    # Case 2: ALL-CAPS abbreviation (≥2 chars) e.g. "HALO", "DeLTa"
    if re.match(r"^[A-Z]{2,}$", first):
        return first
    # Case 3: CamelCase starting with uppercase, at least 2 uppercase chars, no spaces
    if re.match(r"^[A-Z][a-z]+[A-Z]", first):
        return first

    # Fallback: check second token with same patterns
    if len(tokens) > 1:
        second = tokens[1]
        if re.match(r"^[A-Z][A-Za-z0-9]*[-][A-Za-z0-9]+", second):
            return second
        if re.match(r"^[A-Z]{2,}$", second):
            return second

    return None


def _extract_benchmarks_vla(paper: dict) -> list[str]:
    """Check title + abstract for known benchmark names."""
    text = f"{paper.get('title','')} {paper.get('abstract_snippet','')}"
    found = []
    for bm in BENCHMARKS:
        if bm.lower() in text.lower():
            found.append(bm)
    return found


def _extract_entities_from_vla_paper(paper: dict) -> list[dict]:
    """Return list of entity dicts extracted from one paper."""
    entities = []
    signal = {
        "date":   paper.get("date", _today()),
        "title":  paper.get("title", ""),
        "url":    paper.get("url", ""),
        "rating": paper.get("rating", ""),
        "domain": "vla",
    }

    for lab in _extract_labs_vla(paper):
        entities.append({"type": "lab", "name": lab, "signal": signal})

    method = _extract_method_vla(paper)
    if method:
        entities.append({"type": "method", "name": method, "signal": signal})

    for bm in _extract_benchmarks_vla(paper):
        entities.append({"type": "benchmark", "name": bm, "signal": signal})

    return entities

# ---------------------------------------------------------------------------
# Entity extraction — AI App
# ---------------------------------------------------------------------------

def _extract_entities_from_aiapp_pick(item: dict, date: str) -> list[dict]:
    """Extract org/product entities from an AI App daily pick item."""
    entities = []
    text  = f"{item.get('title','')} {item.get('why_picked','')}"
    signal = {
        "date":   date,
        "title":  item.get("title", ""),
        "url":    item.get("url", ""),
        "rating": None,
        "domain": "ai_app",
    }
    for org in AI_ORGS:
        if org.lower() in text.lower():
            entities.append({"type": "lab", "name": org, "signal": signal})
    return entities

# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    if not os.path.exists(INDEX):
        return {"entities": {}, "last_updated": ""}
    return _read_json(INDEX)


def _entity_key(etype: str, name: str) -> str:
    return f"{etype}:{name.lower()}"


def _upsert(index: dict, etype: str, name: str, signal: dict) -> bool:
    """Add signal to entity. Returns True if new signal added."""
    key = _entity_key(etype, name)
    if key not in index["entities"]:
        index["entities"][key] = {
            "type":    etype,
            "name":    name,
            "signals": [],
        }
    entity = index["entities"][key]
    # Dedup: skip if same (date, url) already present
    existing = {(s["date"], s["url"]) for s in entity["signals"]}
    if (signal["date"], signal["url"]) in existing:
        return False
    entity["signals"].append(signal)
    return True


def _trim_index(index: dict, keep_days: int) -> int:
    """Remove signals older than keep_days; remove empty entities."""
    cutoff = _cutoff(keep_days)
    removed = 0
    empty_keys = []
    for key, entity in index["entities"].items():
        before = len(entity["signals"])
        entity["signals"] = [s for s in entity["signals"] if s.get("date", "") >= cutoff]
        removed += before - len(entity["signals"])
        if not entity["signals"]:
            empty_keys.append(key)
    for k in empty_keys:
        del index["entities"][k]
    return removed

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_vla_papers_today(today: str) -> list:
    """Load today's rated VLA papers; fallback to yesterday."""
    for date in [today, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")]:
        path = os.path.join(TMP_DIR, f"vla-daily-rating-out-{date}.json")
        if os.path.exists(path):
            data = _read_json(path)
            papers = data.get("papers", [])
            hot = [p for p in papers if p.get("rating") in ("⚡", "🔧")]
            if hot:
                return hot, date
    return [], today


def _load_aiapp_picks_today(today: str) -> list[tuple[str, dict]]:
    """Load today's AI App picks; return (date, item) tuples."""
    path = os.path.join(MEM_DIR, "ai-daily-pick.json")
    if not os.path.exists(path):
        return []
    data = _read_json(path)
    picks = data.get("daily_picks", [])
    results = []
    for entry in picks:
        date = entry.get("date", "")
        if date == today or date == (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"):
            for item in entry.get("items", []):
                results.append((date, item))
    return results

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_query(args):
    index = _load_index()
    query = args.query.lower()
    cutoff_date = _cutoff(args.days)
    matches = []
    for key, entity in index["entities"].items():
        if query in entity["name"].lower():
            recent = [s for s in entity["signals"] if s.get("date", "") >= cutoff_date]
            if recent:
                matches.append((entity["type"], entity["name"], recent))

    if not matches:
        print(f"No entities matching '{args.query}' in last {args.days} days.")
        return

    matches.sort(key=lambda x: (-len(x[2]), x[1]))
    for etype, name, signals in matches:
        print(f"\n[{etype}] {name}  ({len(signals)} signal(s))")
        for s in sorted(signals, key=lambda x: x["date"], reverse=True):
            rating = f" {s['rating']}" if s.get("rating") else ""
            print(f"  {s['date']}{rating} {s['title'][:70]}")
            print(f"    {s['url']}")


def _cmd_list(args):
    index = _load_index()
    cutoff_date = _cutoff(args.days)
    etype_filter = args.list

    rows = []
    for key, entity in index["entities"].items():
        if etype_filter and entity["type"] != etype_filter:
            continue
        recent = [s for s in entity["signals"] if s.get("date", "") >= cutoff_date]
        if recent:
            rows.append((entity["type"], entity["name"], len(recent),
                         max(s["date"] for s in recent)))

    rows.sort(key=lambda x: (-x[2], x[3]), reverse=False)
    rows.sort(key=lambda x: -x[2])
    print(f"{'Type':12} {'Name':30} {'Signals':>7}  {'Last seen'}")
    print("-" * 65)
    for etype, name, count, last in rows:
        print(f"{etype:12} {name:30} {count:>7}  {last}")


def _cmd_stats(args):
    index = _load_index()
    cutoff_date = _cutoff(90)
    by_type = defaultdict(int)
    total_signals = 0
    for entity in index["entities"].values():
        recent = [s for s in entity["signals"] if s.get("date", "") >= cutoff_date]
        if recent:
            by_type[entity["type"]] += 1
            total_signals += len(recent)
    print(f"Entity index — last updated: {index.get('last_updated','?')}")
    print(f"Total signals (90d): {total_signals}")
    for t, count in sorted(by_type.items()):
        print(f"  {t:12}: {count} entities")

# ---------------------------------------------------------------------------
# Main update loop
# ---------------------------------------------------------------------------

def main_update() -> int:
    today = _today()
    print(f"[entity] date={today}")

    index = _load_index()
    added = 0

    # VLA papers
    papers, paper_date = _load_vla_papers_today(today)
    print(f"[entity] VLA ⚡/🔧 papers: {len(papers)} (from {paper_date})")
    for paper in papers:
        for e in _extract_entities_from_vla_paper(paper):
            if _upsert(index, e["type"], e["name"], e["signal"]):
                added += 1

    # AI App picks
    picks = _load_aiapp_picks_today(today)
    print(f"[entity] AI App picks: {len(picks)}")
    for date, item in picks:
        for e in _extract_entities_from_aiapp_pick(item, date):
            if _upsert(index, e["type"], e["name"], e["signal"]):
                added += 1

    # Trim + save
    removed = _trim_index(index, KEEP_DAYS)
    index["last_updated"] = today
    _write_json_atomic(INDEX, index)

    total = len(index["entities"])
    print(f"[entity] added={added}, trimmed={removed}, total_entities={total}")
    return 0


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Entity Tracker — P2 #9")
    sub = parser.add_subparsers(dest="cmd")

    p_query = sub.add_parser("query", aliases=["--query"])
    p_query.add_argument("query", nargs="?")
    p_query.add_argument("--days", type=int, default=90)

    p_list = sub.add_parser("list", aliases=["--list"])
    p_list.add_argument("list", nargs="?", choices=["lab", "method", "benchmark"])
    p_list.add_argument("--days", type=int, default=90)

    p_stats = sub.add_parser("stats", aliases=["--stats"])

    # Direct flags (for easier CLI use)
    parser.add_argument("--query", "-q", metavar="TERM", help="Query entity by name")
    parser.add_argument("--list", "-l", metavar="TYPE", choices=["lab", "method", "benchmark"],
                        help="List all entities of type")
    parser.add_argument("--stats", "-s", action="store_true", help="Show index stats")
    parser.add_argument("--days", type=int, default=90)

    args = parser.parse_args()

    if args.query:
        _cmd_query(args)
    elif args.list:
        _cmd_list(args)
    elif args.stats:
        _cmd_stats(args)
    else:
        # Default: update index
        sys.exit(main_update())


if __name__ == "__main__":
    main()
