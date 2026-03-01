#!/usr/bin/env python3.11
"""
Upstream Signal Monitor — P2 #10

Monitors arxiv feeds that are upstream to VLA and AI App domains.
Surfaces foundational papers that may become relevant before they appear
in domain-specific RSS feeds.

VLA upstream:     cs.CL + stat.ML
  → LLM architecture, reasoning, generative model theory
    (techniques that become VLA innovations ~6–18 months later)

AI App upstream:  cs.CL + cs.AI
  → reasoning research, agent theory, benchmark advances
    (cs.AI is already in VLA RSS but not AI App; cs.CL is in neither)

Outputs:
  memory/tmp/upstream-vla-{date}.json    — today's VLA upstream papers
  memory/tmp/upstream-aiapp-{date}.json  — today's AI App upstream papers
  memory/upstream-signals.json           — rolling 30-day index

CLI:
  python3 upstream-signal-monitor.py            # run daily update
  python3 upstream-signal-monitor.py --stats    # show index stats
  python3 upstream-signal-monitor.py --list vla # show recent VLA upstream
"""

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ---------------------------------------------------------------------------
MEM_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR = os.path.join(MEM_DIR, "tmp")
INDEX   = os.path.join(MEM_DIR, "upstream-signals.json")
KEEP_DAYS = 30
FETCH_TIMEOUT = 45  # seconds per feed
# ---------------------------------------------------------------------------

ARXIV_FEEDS = {
    "cs.CL":  "https://rss.arxiv.org/rss/cs.CL",
    "stat.ML": "https://rss.arxiv.org/rss/stat.ML",
    "cs.AI":  "https://rss.arxiv.org/rss/cs.AI",
}

# ---------------------------------------------------------------------------
# VLA upstream keywords — foundational techniques that precede VLA innovations
# ---------------------------------------------------------------------------
VLA_UPSTREAM_KEYWORDS = [
    # Architecture
    "state space model", "SSM", "Mamba", "transformer architecture",
    "attention mechanism", "positional encoding", "tokenizer",
    # Generative models (core to diffusion policy, flow matching)
    "flow matching", "score matching", "diffusion model", "normalizing flow",
    "energy-based model", "variational autoencoder", "consistency model",
    # Training & scaling
    "scaling law", "pre-training strategy", "fine-tuning",
    "data mixture", "curriculum learning",
    # Reasoning — increasingly core to VLA planning
    "chain of thought", "reasoning", "spatial reasoning",
    "visual reasoning", "multimodal reasoning",
    # Multimodal language models
    "vision language model", "visual language model", "multimodal",
    "visual encoder", "image tokenizer",
]

# ---------------------------------------------------------------------------
# AI App upstream keywords — research that becomes product features
# ---------------------------------------------------------------------------
AIAPP_UPSTREAM_KEYWORDS = [
    # Agent capabilities
    "reasoning", "chain-of-thought", "planning", "multi-step reasoning",
    "agent", "agentic", "tool use", "function calling", "code generation",
    # Memory and context
    "long context", "context length", "retrieval augmented",
    "retrieval-augmented generation", "memory", "external knowledge",
    # Alignment and instruction following
    "instruction following", "alignment", "RLHF", "DPO", "preference learning",
    # Evaluation and benchmarks
    "benchmark", "evaluation framework", "MMLU", "HumanEval", "SWE-bench",
    # Efficiency
    "quantization", "speculative decoding", "inference efficiency",
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


def _strip_tags(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Feed fetching
# ---------------------------------------------------------------------------

def _fetch_feed(source: str, url: str) -> tuple[list[dict], str]:
    """Fetch and parse an arxiv RSS feed. Returns (items, status)."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(FETCH_TIMEOUT), url],
            capture_output=True, timeout=FETCH_TIMEOUT + 5
        )
        if result.returncode != 0:
            return [], "failed"
        raw = result.stdout
        if not raw:
            return [], "empty"
        root = ET.fromstring(raw)
        # Handle both RSS 2.0 and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        # RSS 2.0
        for item in root.iter("item"):
            title = _strip_tags(getattr(item.find("title"), "text", "") or "")
            link  = getattr(item.find("link"), "text", "") or ""
            desc  = _strip_tags(getattr(item.find("description"), "text", "") or "")
            # arxiv description contains abstract after the authors line
            abstract = desc[:300] if desc else ""
            if title:
                items.append({"title": title, "url": link, "abstract_snippet": abstract, "source": source})
        return items, "ok" if items else "empty"
    except Exception as e:
        return [], f"error:{e}"


# ---------------------------------------------------------------------------
# Keyword filtering
# ---------------------------------------------------------------------------

def _match_keywords(paper: dict, keywords: list[str]) -> list[str]:
    """Return matched keywords found in title + abstract (case-insensitive)."""
    text = f"{paper.get('title', '')} {paper.get('abstract_snippet', '')}".lower()
    return [kw for kw in keywords if kw.lower() in text]


def _filter_papers(papers: list[dict], keywords: list[str]) -> list[dict]:
    """Return papers matching at least one keyword, with keywords_matched set."""
    result = []
    for p in papers:
        matched = _match_keywords(p, keywords)
        if matched:
            p["keywords_matched"] = matched
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# Daily update
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    if not os.path.exists(INDEX):
        return {"last_updated": "", "signals": []}
    return _read_json(INDEX)


def _trim_index(index: dict, keep_days: int) -> int:
    cutoff = _cutoff(keep_days)
    before = len(index["signals"])
    index["signals"] = [s for s in index["signals"] if s.get("date", "") >= cutoff]
    return before - len(index["signals"])


def main_update() -> int:
    today = _today()
    print(f"[upstream] date={today}")
    os.makedirs(TMP_DIR, exist_ok=True)

    vla_out_path   = os.path.join(TMP_DIR, f"upstream-vla-{today}.json")
    aiapp_out_path = os.path.join(TMP_DIR, f"upstream-aiapp-{today}.json")

    if os.path.exists(vla_out_path) and os.path.exists(aiapp_out_path):
        print("[upstream] already ran today, skip")
        return 0

    # Fetch all needed feeds
    feeds_needed = {
        "cs.CL":   ARXIV_FEEDS["cs.CL"],
        "stat.ML": ARXIV_FEEDS["stat.ML"],
        "cs.AI":   ARXIV_FEEDS["cs.AI"],
    }
    fetched: dict[str, tuple[list, str]] = {}
    for src, url in feeds_needed.items():
        items, status = _fetch_feed(src, url)
        fetched[src] = (items, status)
        print(f"[upstream] {src}: {len(items)} items ({status})")

    # VLA upstream: cs.CL + stat.ML
    vla_raw = fetched["cs.CL"][0] + fetched["stat.ML"][0]
    vla_papers = _filter_papers(vla_raw, VLA_UPSTREAM_KEYWORDS)
    vla_out = {
        "date":          today,
        "domain":        "vla",
        "feed_status":   {s: fetched[s][1] for s in ["cs.CL", "stat.ML"]},
        "total_fetched": len(vla_raw),
        "after_filter":  len(vla_papers),
        "papers":        vla_papers,
    }
    _write_json_atomic(vla_out_path, vla_out)
    print(f"[upstream] VLA upstream: {len(vla_papers)}/{len(vla_raw)} papers")

    # AI App upstream: cs.CL + cs.AI
    aiapp_raw = fetched["cs.CL"][0] + fetched["cs.AI"][0]
    aiapp_papers = _filter_papers(aiapp_raw, AIAPP_UPSTREAM_KEYWORDS)
    aiapp_out = {
        "date":          today,
        "domain":        "ai_app",
        "feed_status":   {s: fetched[s][1] for s in ["cs.CL", "cs.AI"]},
        "total_fetched": len(aiapp_raw),
        "after_filter":  len(aiapp_papers),
        "papers":        aiapp_papers,
    }
    _write_json_atomic(aiapp_out_path, aiapp_out)
    print(f"[upstream] AI App upstream: {len(aiapp_papers)}/{len(aiapp_raw)} papers")

    # Update rolling index
    index = _load_index()
    new_sigs = 0
    existing_keys = {(s["date"], s["url"]) for s in index["signals"]}
    for domain, papers in [("vla", vla_papers), ("ai_app", aiapp_papers)]:
        for p in papers:
            key = (today, p.get("url", ""))
            if key not in existing_keys:
                index["signals"].append({
                    "date":             today,
                    "domain":           domain,
                    "source":           p.get("source", ""),
                    "title":            p.get("title", ""),
                    "url":              p.get("url", ""),
                    "abstract_snippet": p.get("abstract_snippet", "")[:200],
                    "keywords_matched": p.get("keywords_matched", []),
                })
                existing_keys.add(key)
                new_sigs += 1

    trimmed = _trim_index(index, KEEP_DAYS)
    index["last_updated"] = today
    _write_json_atomic(INDEX, index)
    print(f"[upstream] index: +{new_sigs} signals, -{trimmed} trimmed, total={len(index['signals'])}")

    return 0


# ---------------------------------------------------------------------------
# CLI queries
# ---------------------------------------------------------------------------

def _cmd_stats():
    if not os.path.exists(INDEX):
        print("No upstream-signals.json yet.")
        return
    index = _read_json(INDEX)
    sigs = index.get("signals", [])
    by_domain = defaultdict(int)
    by_source = defaultdict(int)
    for s in sigs:
        by_domain[s.get("domain", "?")] += 1
        by_source[s.get("source", "?")] += 1
    print(f"Upstream signals index — last updated: {index.get('last_updated', '?')}")
    print(f"Total signals (30d): {len(sigs)}")
    print("  By domain:")
    for d, n in sorted(by_domain.items()):
        print(f"    {d:10}: {n}")
    print("  By source:")
    for s, n in sorted(by_source.items()):
        print(f"    {s:10}: {n}")


def _cmd_list(domain: str, days: int):
    if not os.path.exists(INDEX):
        print("No upstream-signals.json yet.")
        return
    index = _read_json(INDEX)
    cutoff = _cutoff(days)
    sigs = [s for s in index.get("signals", [])
            if s.get("date", "") >= cutoff and (not domain or s.get("domain") == domain)]
    sigs.sort(key=lambda s: s["date"], reverse=True)
    if not sigs:
        print(f"No upstream signals for domain={domain!r} in last {days} days.")
        return
    for s in sigs:
        kws = ", ".join(s.get("keywords_matched", [])[:3])
        print(f"[{s['date']}] [{s['source']}] {s['title'][:70]}")
        print(f"  kw: {kws}")
        print(f"  {s['url']}")


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Upstream Signal Monitor — P2 #10")
    parser.add_argument("--stats", "-s", action="store_true", help="Show index stats")
    parser.add_argument("--list", "-l", metavar="DOMAIN",
                        choices=["vla", "ai_app", ""], default=None,
                        help="List upstream signals for domain")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    if args.stats:
        _cmd_stats()
    elif args.list is not None:
        _cmd_list(args.list, args.days)
    else:
        sys.exit(main_update())


if __name__ == "__main__":
    main()
