#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Theory Deep Dive - Phase 1: Deterministic paper selection.

- Read past 3 days from vla-daily-hotspots.json
- Keep only strategic / actionable papers
- Rank: strategic > actionable; primary > team > non-direction; repo_url bonus
- Dedup against vla-theory-articles.json (already written)
- Output top-1 candidate with auto-classified target_dir and slug

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")

HOTSPOTS_PATH = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
THEORY_ARTICLES_PATH = os.path.join(MEM_DIR, "vla-theory-articles.json")

# Tag priority: lower is better
TAG_PRIORITY = {"strategic": 0, "actionable": 1}

# Direction priority: lower is better
DIR_PRIORITY = {"primary": 0, "team": 1, "non-direction": 2}

# Keywords for tactile sub-directory classification
TACTILE_KEYWORDS = [
    "tactile", "touch", "force sensing", "haptic",
    "contact-rich", "force control", "tactile sensing",
    "grip force", "deformable", "soft manipulation",
]

# Keyword-based frontier sub-folders.
# Format: (subdir_name, [keywords...])
FRONTIER_SUBDIR_RULES = [
    ("world-model", [
        "world model",
        "agent world model",
        "learned simulator",
        "video prediction",
        "model-based planning",
    ]),
    ("agentic", [
        "agentic",
        "tool-calling agent",
        "tool calling agent",
        "autonomous agent",
        "mcp",
        "multi-step tool use",
    ]),
    ("rl", [
        "reinforcement learning",
        "diffusion policy",
        "policy optimization",
        "policy gradient",
        "offline rl",
        "online rl",
        "reward shaping",
    ]),
]

# Cross-domain but high-value topics that should go to theory/frontier root
# when no sub-folder rule is matched.
FRONTIER_KEYWORDS = [
    "synthetic environment",
    "embodied benchmark",
    "agent benchmark",
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


def _cutoff_date(day, days=3):
    """Return the date string N days before `day`."""
    try:
        d = _dt.datetime.strptime(day, "%Y-%m-%d")
        c = d - _dt.timedelta(days=days)
        return c.strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


def _load_past_titles():
    """Return set of lowercase titles from vla-theory-articles.json (dedup)."""
    data = _read_json(THEORY_ARTICLES_PATH, {"theory_articles": []})
    titles = set()
    for entry in (data.get("theory_articles") or []):
        if isinstance(entry, dict):
            t = (entry.get("title") or "").strip()
            if t:
                titles.add(t.lower())
    return titles


def _title_to_slug(title):
    """Convert paper title to snake_case slug for filename."""
    # Remove parenthetical content, special chars
    s = re.sub(r"\(.*?\)", "", title)
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s)
    s = s.strip().lower()
    # Replace spaces/hyphens with underscore
    s = re.sub(r"[\s-]+", "_", s)
    # Trim to reasonable length
    s = s[:60].rstrip("_")
    if not s:
        s = "unnamed_paper"
    return s + "_dissection"


def _classify_target_dir(title, abstract):
    """Determine theory/ sub-directory based on title/abstract keywords."""
    text = (title + " " + abstract).lower()
    for kw in TACTILE_KEYWORDS:
        if kw in text:
            return "theory/tactile"
    for subdir, keywords in FRONTIER_SUBDIR_RULES:
        for kw in keywords:
            if kw in text:
                return "theory/frontier/%s" % subdir
    for kw in FRONTIER_KEYWORDS:
        if kw in text:
            return "theory/frontier"
    return "theory"


def _score_paper(paper):
    """Return a tuple for sorting: lower = better."""
    tag = paper.get("tag", "read-only")
    direction = paper.get("direction", "non-direction")
    has_repo = 1 if paper.get("repo_url") else 0

    return (
        TAG_PRIORITY.get(tag, 9),
        DIR_PRIORITY.get(direction, 9),
        1 - has_repo,  # 0 = has repo (better), 1 = no repo
        # Newer dates first (reverse sort via complement)
        "".join(chr(255 - ord(c)) for c in paper.get("date", "0000-00-00")),
    )



# ── Expert candidate ranking ──────────────────────────────────────────────────

EXPERT_POOL_SIZE = 5  # Max candidates to send to expert for scoring


def _read_promoted_candidates(day):
    """
    Read papers promoted from VLA Daily pipeline (⚡/🔧) into theory candidate pool.
    Returns list of paper dicts.
    """
    path = os.path.join(TMP_DIR, "vla-theory-promoted-%s.json" % day)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _expert_rank_candidates(candidates, handbook_ctx, api_key):
    """
    Call qwen-max to score and rank theory candidates.
    Returns reordered list (best first), with expert_score + expert_reason added.

    Prompt: VLA Theory 选题编辑，picks the paper most worth a 10,000-word X-Ray analysis.
    """
    import sys as _sys
    sys.path.insert(0, "/home/admin/clawd/scripts")
    try:
        import _vla_expert
        call_qwen = _vla_expert.call_qwen
    except Exception as e:
        print("[prep] _vla_expert import failed: %s" % str(e), file=_sys.stderr)
        return candidates

    SYSTEM = """你是 VLA Theory X-Ray 系列的选题编辑委员会主席，负责从候选论文中挑选最值得完成
一篇 10,000 字 X-Ray 深度解析的论文。评分维度（每项 0-3 分，总分 0-15）：

1. 核心贡献新颖性（0-3）：是否提出新架构/新训练范式/新能力？还是小改进？
2. Eureka Moment 潜力（0-3）：是否有一句话能说清核心洞见？能让读者"原来如此"？
3. VLA-Handbook 空白填补（0-3）：是否覆盖了知识库尚未分析的方向？
4. 技术深度与可挖掘性（0-3）：架构细节/消融实验/工程细节是否足够支撑 10,000 字？
5. 长期影响力（0-3）：是否有可能成为领域里程碑？引用价值？

## VLA-Handbook 知识库状态
{handbook_ctx}
"""

    lines = []
    for i, c in enumerate(candidates, 1):
        title = (c.get("title") or "").strip()
        abstract = (c.get("abstract_snippet") or "").strip()[:400]
        url = (c.get("url") or "").strip()
        source = c.get("source", "")
        rating = c.get("rating", "")
        reason = (c.get("reason") or "").strip()
        line = "%d. 【%s】" % (i, title)
        if rating:
            line += "（Daily评级：%s %s）" % (rating, reason)
        if abstract:
            line += "\n   摘要：%s" % abstract
        if url:
            line += "\n   链接：%s" % url
        lines.append(line)

    USER = """以下是 %d 篇候选论文，请按以上 5 个维度逐篇评分，然后给出综合排名。

%s

严格按以下 JSON 格式输出（只返回 JSON 数组，不含 markdown 代码块）：
[
  {{
    "title": "完整论文标题",
    "scores": {{"novelty": 0, "eureka": 0, "handbook_gap": 0, "depth": 0, "impact": 0}},
    "total": 0,
    "reason": "一句话说明选/不选的核心理由（≤40字）"
  }},
  ...
]
""" % (len(candidates), "\n\n".join(lines))

    system_with_ctx = SYSTEM.format(handbook_ctx=handbook_ctx or "（获取失败）")
    result = call_qwen(system_with_ctx, USER, timeout=180)
    if not result.get("ok"):
        print("[prep] Expert ranking LLM failed: %s" % result.get("error"), file=sys.stderr)
        return candidates

    raw = result["content"].strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
    try:
        import json as _j
        scored = _j.loads(raw)
        if not isinstance(scored, list):
            raise ValueError("not a list")
        # Build score map: title[:80].lower() → {total, reason}
        score_map = {}
        for item in scored:
            t = (item.get("title") or "").strip().lower()[:80]
            score_map[t] = {
                "expert_score": item.get("total", 0),
                "expert_reason": item.get("reason", ""),
            }
        # Attach scores to candidates
        for c in candidates:
            key = (c.get("title") or "").strip().lower()[:80]
            match = score_map.get(key, {})
            if not match:
                # fuzzy: try 40-char prefix match
                for k, v in score_map.items():
                    if k[:40] in key or key[:40] in k:
                        match = v
                        break
            c["expert_score"] = match.get("expert_score", 0)
            c["expert_reason"] = match.get("expert_reason", "")
        # Sort by expert score descending
        candidates.sort(key=lambda x: -x.get("expert_score", 0))
        print("[prep] Expert ranking done. Top: %s (score=%s)"
              % ((candidates[0].get("title") or "")[:60],
                 candidates[0].get("expert_score", "?")), file=sys.stderr)
    except Exception as e:
        print("[prep] Expert ranking parse failed: %s — using keyword score" % str(e)[:80],
              file=sys.stderr)

    return candidates

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD override")
    ap.add_argument("--out", default="", help="Output path override")
    ap.add_argument("--days", type=int, default=3, help="Lookback days")
    ap.add_argument("--max", type=int, default=1, help="Max candidates")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out_path = (args.out.strip()
                or os.path.join(TMP_DIR,
                                "vla-theory-candidates-%s.json" % day))
    os.makedirs(TMP_DIR, exist_ok=True)

    cutoff = _cutoff_date(day, args.days)
    past_titles = _load_past_titles()

    # --- Read and filter papers ---
    data = _read_json(HOTSPOTS_PATH, {"reported_papers": []})
    eligible = []
    seen_titles = set()  # dedup within current batch

    for p in (data.get("reported_papers") or []):
        if not isinstance(p, dict):
            continue

        # Date filter
        d = p.get("date", "")
        if d < cutoff or d > day:
            continue

        # Tag filter: only strategic or actionable
        tag = p.get("tag", "")
        if tag not in TAG_PRIORITY:
            continue

        # Title dedup
        title = (p.get("title") or "").strip()
        if not title:
            continue
        t_lower = title.lower()
        if t_lower in past_titles:
            continue
        if t_lower in seen_titles:
            continue
        seen_titles.add(t_lower)

        # Guardrail:
        # non-direction papers are allowed only when they are classified
        # into a dedicated frontier bucket (e.g., world-model topics).
        direction = p.get("direction", "")
        abstract = (p.get("abstract_snippet") or "").strip()
        target_dir = _classify_target_dir(title, abstract)
        if direction == "non-direction" and target_dir == "theory":
            continue

        eligible.append(p)

    # Rank by keyword score
    eligible.sort(key=_score_paper)

    # Merge promoted candidates from VLA Daily pipeline (⚡/🔧 papers not in theory yet)
    promoted = _read_promoted_candidates(day)
    for pp in promoted:
        t_lower = (pp.get("title") or "").strip().lower()
        if t_lower and t_lower not in past_titles and t_lower not in seen_titles:
            # Mark as promoted so expert knows its origin
            pp.setdefault("tag", "strategic")
            pp.setdefault("direction", "primary")
            eligible.insert(0, pp)
            seen_titles.add(t_lower)

    # Build expert scoring pool (top EXPERT_POOL_SIZE candidates)
    pool = eligible[:EXPERT_POOL_SIZE]

    # Expert LLM ranking when there are multiple candidates
    if len(pool) > 1:
        sys.path.insert(0, "/home/admin/clawd/scripts")
        try:
            import _vla_expert
            day_str = day
            handbook_ctx = _vla_expert.fetch_handbook_context(day_str)
            api_key = _vla_expert.get_api_key()
            if api_key:
                pool = _expert_rank_candidates(pool, handbook_ctx, api_key)
        except Exception as e:
            print("[prep] Expert import/call failed: %s" % str(e)[:100], file=sys.stderr)

    # Take top N after expert ranking
    top = pool[: args.max]

    # Build candidate list
    candidates = []
    for p in top:
        title = (p.get("title") or "").strip()
        abstract = (p.get("abstract_snippet") or "").strip()
        slug = _title_to_slug(title)
        target_dir = _classify_target_dir(title, abstract)

        candidates.append({
            "title": title,
            "url": (p.get("url") or "").strip(),
            "repo_url": (p.get("repo_url") or "").strip(),
            "abstract_snippet": abstract,
            "tag": p.get("tag", ""),
            "direction": p.get("direction", ""),
            "source": p.get("source", ""),
            "reason": (p.get("reason") or "").strip(),
            "expert_score": p.get("expert_score", 0),
            "expert_reason": (p.get("expert_reason") or "").strip(),
            "target_dir": target_dir,
            "slug": slug,
        })

    out_obj = {
        "ok": True,
        "date": day,
        "date_range": "%s to %s" % (cutoff, day),
        "generated_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_type": "vla_theory_deep_dive",
        "candidates": candidates,
        "stats": {
            "total_papers_in_range": len(
                [p for p in (data.get("reported_papers") or [])
                 if isinstance(p, dict)
                 and p.get("date", "") >= cutoff
                 and p.get("date", "") <= day]),
            "eligible_after_tag_filter": len(eligible),
            "past_articles_excluded": len(past_titles),
            "selected": len(candidates),
        },
    }

    _write_json(out_path, out_obj)

    # Stdout summary (single-line JSON for cron agent to read)
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out_path,
        "selected": len(candidates),
        "eligible": len(eligible),
        "candidate_title": candidates[0]["title"] if candidates else "",
        "expert_score": candidates[0].get("expert_score", 0) if candidates else 0,
        "expert_reason": candidates[0].get("expert_reason", "") if candidates else "",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
