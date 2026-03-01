#!/usr/bin/env python3.11
"""
Semantic Memory Search — P2 #11

CLI and programmatic interface for querying Pulsar's semantic memory index.

Usage:
  python3 semantic-search.py --query "flow matching in robot policy"
  python3 semantic-search.py --query "Karpathy intent-driven development" --days 30 --top 5
  python3 semantic-search.py --query "assumption calibration VLA" --source-type calibration
  python3 semantic-search.py --stats
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

MEM_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
INDEX_PATH = os.path.join(MEM_DIR, "semantic-index.json")
AUTH_PATH = "/home/admin/.openclaw/agents/reports/agent/auth-profiles.json"
DASHSCOPE_EMBED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
EMBED_MODEL = "text-embedding-v3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("alibaba-cloud:default", "alibaba-cloud"):
            v = (d.get("profiles", {}).get(k, {}) or {}).get("key", "").strip()
            if v:
                return v
    except Exception:
        pass
    return ""


def _embed_query(text: str, api_key: str) -> list[float] | None:
    payload = json.dumps({
        "model": EMBED_MODEL,
        "input": [text],
        "encoding_format": "float",
    }).encode("utf-8")
    req = Request(DASHSCOPE_EMBED_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        resp = urlopen(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        return result["data"][0]["embedding"]
    except Exception as e:
        print(f"[error] embed query failed: {e}", file=sys.stderr)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure Python cosine similarity."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb + 1e-9)


def _cutoff_date(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(
    query: str,
    days: int = 60,
    top: int = 5,
    source_type: str | None = None,
    json_out: bool = False,
) -> list[dict]:
    """
    Search the semantic index.

    Returns list of dicts with: score, date, source, source_type, text, section
    """
    if not os.path.exists(INDEX_PATH):
        print("[error] Index not found. Run semantic-index-builder.py first.", file=sys.stderr)
        return []

    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)

    chunks = index.get("chunks", [])
    if not chunks:
        print("[warn] Index is empty.", file=sys.stderr)
        return []

    # Filter by date and source_type
    cutoff = _cutoff_date(days)
    candidates = [
        c for c in chunks
        if c.get("date", "") >= cutoff
        and "embedding" in c
        and (not source_type or c.get("source_type") == source_type)
    ]

    if not candidates:
        print(f"[warn] No candidates matching days={days}, source_type={source_type}", file=sys.stderr)
        return []

    # Embed query
    api_key = _get_api_key()
    if not api_key:
        print("[error] No DashScope API key found", file=sys.stderr)
        return []

    q_vec = _embed_query(query, api_key)
    if q_vec is None:
        return []

    # Score all candidates
    scored = []
    for c in candidates:
        score = _cosine(q_vec, c["embedding"])
        scored.append({
            "score": round(score, 4),
            "date": c.get("date", ""),
            "source": c.get("source", ""),
            "source_type": c.get("source_type", ""),
            "section": c.get("section", ""),
            "text": c.get("text", "")[:400],  # truncate for display
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_search(args) -> int:
    results = search(
        query=args.query,
        days=args.days,
        top=args.top,
        source_type=args.source_type or None,
        json_out=args.json,
    )

    if not results:
        print("No results found.")
        return 0

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🔍 Semantic search: \"{args.query}\" (top {len(results)}, last {args.days}d)\n")
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['score']:.3f}] [{r['source_type']}] {r['date']} — {r['source']}")
        if r.get("section"):
            print(f"     § {r['section']}")
        # Show first 2 lines of text
        lines = r["text"].strip().splitlines()
        preview = " ".join(lines[:2])[:160]
        print(f"     {preview}")
        print()
    return 0


def _cmd_stats() -> int:
    if not os.path.exists(INDEX_PATH):
        print("Index not found. Run semantic-index-builder.py first.")
        return 1
    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)
    chunks = index.get("chunks", [])
    by_type: dict[str, int] = {}
    for c in chunks:
        t = c.get("source_type", "?")
        by_type[t] = by_type.get(t, 0) + 1
    size_kb = os.path.getsize(INDEX_PATH) // 1024
    print(f"Semantic index — built: {index.get('built_at', '?')[:16]}")
    print(f"  Model: {index.get('model', '?')}, dim={index.get('dim', '?')}")
    print(f"  Chunks: {len(chunks)}, file: {size_kb} KB")
    print("  By source type:")
    for t, n in sorted(by_type.items()):
        print(f"    {t:25}: {n}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic Memory Search — P2 #11")
    sub = parser.add_subparsers(dest="cmd")

    # search subcommand (also default)
    s = sub.add_parser("search", help="Search the index")
    s.add_argument("--query", "-q", required=True)
    s.add_argument("--days", type=int, default=60)
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--source-type", help="Filter: ai_daily_pick|ai_social|vla_social|calibration|upstream|...")
    s.add_argument("--json", action="store_true")

    sub.add_parser("stats", help="Show index statistics")

    # Allow --query at top level (shorthand: semantic-search.py --query "...")
    parser.add_argument("--query", "-q", help="Query string (top-level shorthand)")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--source-type")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--stats", action="store_true")

    args = parser.parse_args()

    if args.stats or args.cmd == "stats":
        return _cmd_stats()

    if args.cmd == "search" or args.query:
        return _cmd_search(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
