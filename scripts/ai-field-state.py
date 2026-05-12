#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Agent Field State — method family trend tracking for AI applications.

Mirrors compute-field-state.py for VLA, but tracks AI Agent ecosystem trends.
Scans AI daily picks + AI deep dive articles for method family keywords,
computes 7-day rolling counts, acceleration, and adoption phases.

Output: memory/ai-field-state-{date}.json

Python 3.6+, no external deps.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

MEM_DIR = Path(os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory"))
TMP_DIR = MEM_DIR / "tmp"
OUTPUT_DIR = MEM_DIR

TZ_CST = timezone(timedelta(hours=8))

# ── AI Agent Method Families ─────────────────────────────────────────────────

AI_METHOD_FAMILIES = {
    # ── 1. Agentic Coding (最熱賽道) ──
    "agentic_coding": {
        "label": "Agentic Coding",
        "keywords": [
            "claude code", "cursor", "windsurf", "codex", "devin",
            "swe-bench", "swe-agent", "agentic engineering",
            "vibe coding", "coding agent", "code review",
            "copilot", "cline", "aider", "composer",
            "git workflow", "pre-commit", "pull request agent",
        ],
    },
    # ── 2. MCP / Tool Protocol (Agent 的 USB) ──
    "mcp_protocol": {
        "label": "MCP / Tool Protocol",
        "keywords": [
            "mcp", "model context protocol", "function call",
            "tool use", "tool call", "computer use",
            "browser use", "gui agent", "a2a",
            "agent protocol", "api gateway",
        ],
    },
    # ── 3. Multi-Agent 協作 ──
    "multi_agent": {
        "label": "Multi-Agent",
        "keywords": [
            "multi-agent", "multi agent", "swarm",
            "crewai", "autogen", "magentic",
            "agent collaboration", "delegation",
            "orchestrat", "supervisor", "handoff",
        ],
    },
    # ── 4. Context Engineering (Simon Willison 的核心主題) ──
    "context_engineering": {
        "label": "Context Eng.",
        "keywords": [
            "context engineer", "context window", "context management",
            "system prompt", "memory management", "knowledge base",
            "rag", "retrieval", "vector search", "embedding",
            "knowledge graph", "long context", "1m context",
        ],
    },
    # ── 5. Agent Safety / Trust ──
    "agent_safety": {
        "label": "Agent Safety",
        "keywords": [
            "guardrail", "jailbreak", "injection", "red team",
            "sandbox", "safehouse", "rogue agent",
            "prompt attack", "trust tier", "permission",
            "agent identity", "alignment", "misuse",
        ],
    },
    # ── 6. Eval / Benchmark ──
    "agent_eval": {
        "label": "Eval / Bench",
        "keywords": [
            "eval", "benchmark", "leaderboard", "arena",
            "langsmith", "braintrust", "ragas",
            "tracing", "observab", "monitoring",
            "swe-bench", "gaia", "webarena", "tau-bench",
        ],
    },
    # ── 7. Agent Infra (部署/擴展/成本) ──
    "agent_infra": {
        "label": "Agent Infra",
        "keywords": [
            "inference", "latency", "serving", "gateway",
            "streaming", "rate limit", "cost",
            "bedrock", "sagemaker", "vertex",
            "fleet", "scaling", "load balanc",
        ],
    },
    # ── 8. Open-Source Agent (開源 vs 閉源) ──
    "open_source": {
        "label": "Open Source",
        "keywords": [
            "open source", "open-source", "apache",
            "llama", "qwen", "mistral", "deepseek",
            "local llm", "on-device", "ollama",
            "hugging face", "huggingface",
        ],
    },
    # ── 9. Voice / Multimodal Agent ──
    "voice_multimodal": {
        "label": "Voice / Modal",
        "keywords": [
            "voice agent", "real-time voice", "speech",
            "multimodal", "vision", "image", "video",
            "screen agent", "computer vision",
            "audio", "tts", "stt", "whisper",
        ],
    },
    # ── 10. Reasoning / Planning ──
    "reasoning_planning": {
        "label": "Reasoning",
        "keywords": [
            "reasoning", "chain-of-thought", "planning",
            "tree of thought", "reflection", "self-correct",
            "thinking", "step-by-step", "verification",
            "o1", "o3", "o4", "deep thinking",
        ],
    },
    # ── 11. Frontier Models (新模型發布) ──
    "frontier_model": {
        "label": "Frontier Model",
        "keywords": [
            "gpt-5", "gpt-4", "claude 4", "claude 3",
            "gemini", "gemini 3", "sonnet", "opus",
            "fine-tun", "lora", "peft", "distill",
            "moe", "mixture of expert", "scaling law",
        ],
    },
    # ── 12. Vertical Agent (行業垂直) ──
    "vertical_agent": {
        "label": "Vertical Agent",
        "keywords": [
            "legal", "medical", "healthcare", "finance",
            "security ops", "secops", "devops", "sre",
            "customer service", "support agent",
            "compliance", "audit", "enterprise",
        ],
    },
}

# AI Competition Pairs — 每對代表一個策略抉擇
AI_COMPETITION_PAIRS = [
    {"familyA": "agentic_coding",      "familyB": "multi_agent",
     "label": "SINGLE vs SWARM",
     "desc": "Single powerful coding agent vs multi-agent orchestration"},
    {"familyA": "mcp_protocol",        "familyB": "context_engineering",
     "label": "ACT vs THINK",
     "desc": "Tool execution protocol vs context/knowledge retrieval"},
    {"familyA": "open_source",         "familyB": "frontier_model",
     "label": "OPEN vs CLOSED",
     "desc": "Open-source models vs proprietary frontier models"},
    {"familyA": "agent_eval",          "familyB": "agent_safety",
     "label": "MEASURE vs GUARD",
     "desc": "Evaluation-driven development vs safety-first guardrails"},
    {"familyA": "agent_infra",         "familyB": "voice_multimodal",
     "label": "SCALE vs SENSE",
     "desc": "Infrastructure scaling vs multimodal perception"},
]


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path, default=None):
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(str(tmp), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.rename(path)


def _collect_ai_texts(days=14):
    """Collect title+summary texts from AI picks and deep dives for the last N days."""
    cutoff = (datetime.now(TZ_CST) - timedelta(days=days)).strftime("%Y-%m-%d")
    texts_by_date = {}  # date → list of texts

    # 1. AI Daily Picks
    pick_path = MEM_DIR / "ai-daily-pick.json"
    if pick_path.exists():
        data = _read_json(pick_path)
        for p in data.get("daily_picks", []):
            date = p.get("date", "")
            if date < cutoff:
                continue
            for item in p.get("items", []):
                text = "%s %s" % (item.get("title", ""), item.get("why_picked", ""))
                texts_by_date.setdefault(date, []).append(text.lower())

    # 2. AI Deep Dive articles
    dd_path = MEM_DIR / "ai-app-deep-dive-articles.json"
    if dd_path.exists():
        data = _read_json(dd_path)
        for a in data.get("deep_dive_articles", []):
            date = a.get("date", "")
            if date < cutoff:
                continue
            text = "%s %s" % (a.get("title", ""), a.get("signal_type", ""))
            texts_by_date.setdefault(date, []).append(text.lower())

    # 3. AI Social intel
    for f in sorted(glob.glob(str(MEM_DIR / "_ai_social_*.md"))):
        fname = os.path.basename(f)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        if not date_match:
            continue
        date = date_match.group(1)
        if date < cutoff:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read().lower()
            texts_by_date.setdefault(date, []).append(content)
        except Exception:
            pass

    return texts_by_date


def _compute_trends(texts_by_date, today_str):
    """Compute method family trends from collected texts."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    recent_cutoff = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    prior_cutoff = (today - timedelta(days=14)).strftime("%Y-%m-%d")

    trends = []
    for family_id, family in AI_METHOD_FAMILIES.items():
        count_7d = 0
        count_prior_7d = 0

        for date, texts in texts_by_date.items():
            matches = 0
            for text in texts:
                if any(kw in text for kw in family["keywords"]):
                    matches += 1
            if date >= recent_cutoff:
                count_7d += matches
            elif date >= prior_cutoff:
                count_prior_7d += matches

        # Acceleration
        daily_avg_recent = count_7d / 7.0
        daily_avg_prior = count_prior_7d / 7.0
        if daily_avg_prior > 0:
            acceleration = round(daily_avg_recent / daily_avg_prior, 2)
        elif count_7d > 0:
            acceleration = 9.99  # new surge
        else:
            acceleration = 0.0

        # Status
        if count_7d + count_prior_7d < 3:
            status = "insufficient_data"
        elif acceleration >= 3.0:
            status = "surging"
        elif acceleration >= 2.0:
            status = "accelerating"
        elif acceleration <= 0.33:
            status = "declining"
        else:
            status = "stable"

        trends.append({
            "family": family_id,
            "label": family["label"],
            "count_7d": count_7d,
            "count_prior_7d": count_prior_7d,
            "count_14d": count_7d + count_prior_7d,
            "daily_avg_recent": round(daily_avg_recent, 2),
            "daily_avg_prior": round(daily_avg_prior, 2),
            "acceleration": acceleration,
            "status": status,
        })

    trends.sort(key=lambda x: x["count_7d"], reverse=True)
    return trends


def main():
    today = _today()
    print("[ai-field-state] date=%s" % today)

    texts = _collect_ai_texts(14)
    total_texts = sum(len(v) for v in texts.values())
    print("[ai-field-state] collected %d texts from %d days" % (total_texts, len(texts)))

    trends = _compute_trends(texts, today)

    # Summary
    total_7d = sum(t["count_7d"] for t in trends)
    active = [t for t in trends if t["count_7d"] > 0]
    print("[ai-field-state] %d families, %d active, %d mentions in 7d" % (
        len(trends), len(active), total_7d
    ))

    output = {
        "date": today,
        "trend_version": 1,
        "total_mentions_7d": total_7d,
        "method_trends": trends,
        "competition_pairs": AI_COMPETITION_PAIRS,
    }

    out_path = OUTPUT_DIR / ("ai-field-state-%s.json" % today)
    _atomic_write(out_path, output)
    print("[ai-field-state] written: %s" % out_path)

    for t in trends[:5]:
        print("  %s: %d (acc=%.2f, %s)" % (
            t["label"], t["count_7d"], t["acceleration"], t["status"]
        ))

    return 0


if __name__ == "__main__":
    sys.exit(main())
