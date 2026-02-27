#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Daily Hotspots - Phase 2.5: Expert LLM Rating.

Reads today's new papers, calls qwen-max for professional VLA relevance rating.
Each paper receives ⚡/🔧/📖/❌ with a one-line expert reason.

Input:  --papers-file <path>  JSON array of paper dicts
Output: JSON array with "rating" and "reason" fields added

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import json
import os
import sys
import time

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:
    Request = urlopen = HTTPError = URLError = None

AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# Use qwen3.5-plus for expert reasoning
RATING_MODEL = "qwen3.5-plus"

# Expert VLA rating prompt — acts as senior researcher, harsh critic
SYSTEM_PROMPT = """\
你是 VLA（Vision-Language-Action）领域的资深研究员和 embodied AI 架构师，\
具有审阅 CoRL/RSS/ICLR/ICRA 顶会的经验。你的任务是对 arXiv/RSS 每日新论文进行\
专业评级，帮助团队聚焦最重要的进展，过滤噪音。

## 你的背景认知
- 当前 VLA 主流方法：OpenVLA、π0（Physical Intelligence）、RT-2/RT-X（Google）、\
Octo、RoboVLMs、ACT/Diffusion Policy、CrossFormer
- 核心 benchmark：LIBERO、CALVIN、Open-X Embodiment、BridgeData V2、\
FurnitureBench、MetaWorld、DROID
- 主要研究方向：触觉 VLA（primary）、双臂协作、世界模型、Agentic 控制、RL 精调、\
多模态对齐、移动操作
- 重点机构（评级时从摘要/标题中识别，并在 affiliation 字段标注括号内缩写）：
  Physical Intelligence → [π]
  Google DeepMind / Google Brain / Google Research → [DeepMind]
  Stanford IRIS / SAIL / Finn Lab / Levine Lab → [Stanford]
  UC Berkeley BAIR / RLL → [Berkeley]
  CMU Robotics Institute → [CMU]
  MIT CSAIL / Tedrake Lab → [MIT]
  ETH Zurich ASL / RSL → [ETH]
  NVIDIA Research → [NVIDIA]
  Meta AI / FAIR → [Meta]
  Microsoft Research → [MSR]
  清华大学 / Tsinghua / TBSI / AIR → [清华]
  北京大学 / PKU → [北大]
  上海交通大学 / SJTU → [上交]
  浙江大学 / ZJU → [浙大]
  中国科学院 / CAS → [中科院]
  香港科技大学 / HKUST → [科大]
  香港大学 / HKU → [港大]
  北京航空航天大学 / Beihang / BUAA → [北航]
- 重点研究者（可与机构叠加，格式：[机构|姓氏]）：
  Sergey Levine → Levine；Chelsea Finn → Finn；Pieter Abbeel → Abbeel
  Russ Tedrake → Tedrake；Fei-Fei Li → Li；Tony Zhao → Zhao
  Kevin Black → Black；Pete Florence → Florence；Danny Driess → Driess
  Oier Mees → Mees；Homer Walke → Walke；Lerrel Pinto → Pinto
  Marco Hutter → Hutter；Dorsa Sadigh → Sadigh；Animesh Garg → Garg

## 评级标准（严格执行，每级有明确上限）

### ⚡ 战略级（每日最多 1 篇，门槛极高）
必须**同时满足**以下所有条件：
1. 提出 VLA 新架构/新训练范式（不是对现有方法的小改进或工程优化）
2. 在至少 2 个公认 VLA benchmark 上有完整对比实验和消融实验
3. 结果显著优于当前 SOTA（不是边际提升）
4. 解决了领域公认的核心瓶颈：泛化 / 灵巧操作 / 样本效率 / 跨平台迁移

> ⚡ 超过 1 篇/天说明标准已失效，请重新审视全部评级

### 🔧 可操作级（每日最多 5 篇）
满足以下**全部**条件：
1. **VLA 直接相关**：与 VLA 架构/训练/推理/数据/部署直接相关，不是泛泛的机器人论文
2. **本周可复用**：方法/代码/数据集有明确应用路径，VLA 研究者可本周内使用
3. **有实质贡献**：新方法/新能力/新工程洞见，非纯调参或边际改进
4. **reason 具体**：必须说明"贡献点 + 结果/可复用点"；禁用空泛表述

注意：评估基于摘要片段，若论文标题明确含 VLA 且贡献清晰，可给 benefit of the doubt，
无需摘要片段明确列出机器人实验细节。非 VLA 标题论文则要求摘要有明确机器人实验证据。

### 📖 值得了解（不设上限）
以下情形归 📖：
- 方法相邻但无明确 VLA 应用路径
- 仅仿真验证的操作方法（缺真实机器人数据）
- 综述/survey/数据集（重要但不紧急）
- 方法创新一般，仅刷 benchmark
- 不确定时默认归 📖

**灌水论文识别**：若论文存在以下特征，在 reason 末尾加 [💧灌水]：
- 标题宏大但贡献仅是已有方法的简单组合或轻微变体
- 摘要充满"我们提出了…框架/系统/方法"但无具体创新点或量化结果
- 声称"泛化"/"通用"/"统一"但实验只在 1-2 个简单任务上
- 结果提升微小（<2%）且无深度分析

### ❌ 过滤（完全不进 Telegram）
- 语音/音频处理、纯 NLP 任务、纯 2D 视觉（无机器人操作场景）
- 医疗影像、自动驾驶（非机器人操作）
- 图神经网络、量子计算、通信/网络系统
- 摘要内容与机器人操作/embodied AI 无实质关联

## 严格执行原则
- **明确配额**：⚡ ≤ 1/天，🔧 ≤ 5/天；超出必须重审降级
- **禁止空话**：reason 禁止出现"有实际应用潜力/价值"、"相关性高"等
- **标题有 VLA = benefit of the doubt**：VLA 论文的机器人实验细节可能在正文，不凭摘要片段缺失降级
- **重点机构不加分**：π/DeepMind 的论文同样遵守标准，机构只在 affiliation 字段标注
- **宁严勿松**：不确定时降一级
"""

USER_PROMPT_TEMPLATE = """\
以下是今日新论文列表，请逐篇评级、识别重点机构/研究者，并检测灌水论文。

论文列表：
{papers_block}

## 灌水论文识别（高精度，宁缺毋滥）
灌水 ≠ 不相关。不相关的好论文是 📖，不是灌水。
只有满足以下≥2条时才在 reason 末尾加 [💧灌水]：
- 标题极度夸大（"统一/通用/全能"），但摘要无任何具体技术路线
- 贡献明显是 A+B 简单拼接，缺乏理论或实验支撑为何 A+B 有效
- 摘要几乎全是问题描述和目标宣示，无任何方法细节
- 实验设计极弱（只在 1 个玩具任务，无对比基线）
- 同一实验室近期已发表高度相似论文（明显灌水）

严格按以下 JSON 格式输出，只返回 JSON 数组，不要任何说明文字或 markdown 代码块：
[
  {{
    "title": "原始论文标题（完整复制，不要截断）",
    "rating": "⚡" 或 "🔧" 或 "📖" 或 "❌",
    "reason": "一句话（≤40字）：🔧 含贡献+可复用点；真正灌水加 [💧灌水]；❌ 说明误命中原因",
    "affiliation": "识别到的重点机构/研究者如 [DeepMind] 或 [Stanford|Finn]；识别不到填空字符串"
  }},
  ...
]
"""



def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _get_api_key():
    # 1. env var
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    # 2. auth-profiles.json
    cfg = _read_json(AUTH_PATH, {})
    profiles = cfg.get("profiles", {})
    for profile_key in ("alibaba-cloud:default", "alibaba-cloud"):
        p = profiles.get(profile_key, {})
        k = p.get("key", "").strip()
        if k:
            return k
    return ""


def _call_qwen(system_prompt, user_prompt, api_key, timeout=120):
    """Call DashScope chat completions (no web search, pure reasoning)."""
    if not (Request and urlopen):
        return {"ok": False, "error": "urllib_unavailable"}

    payload = {
        "model": RATING_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,   # low temperature for consistent expert judgment
        "max_tokens": 4096,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(DASHSCOPE_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", "Bearer " + api_key)

    for attempt in range(3):
        try:
            resp = urlopen(req, timeout=timeout)
            raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            content = (
                obj.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {"ok": True, "content": content}
        except HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            return {"ok": False, "error": "http_%d" % e.code, "detail": err_body}
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return {"ok": False, "error": str(e)[:200]}
    return {"ok": False, "error": "max_retries"}


def _parse_ratings(content, papers):
    """
    Parse JSON array from LLM response.
    Falls back to assigning 📖 to all papers on parse failure.
    """
    content = content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(
            l for l in lines if not l.strip().startswith("```")
        )

    try:
        rated = json.loads(content)
        if not isinstance(rated, list):
            raise ValueError("not a list")
        # Build title→rating+reason map (fuzzy: strip + lower)
        rating_map = {}
        for item in rated:
            if isinstance(item, dict):
                t = (item.get("title") or "").strip()
                rating_map[t.lower()[:80]] = {
                    "rating": item.get("rating", "📖"),
                    "reason": item.get("reason", ""),
                    "affiliation": item.get("affiliation", ""),
                }
        # Match back to original papers
        result = []
        for p in papers:
            title = (p.get("title") or "").strip()
            key = title.lower()[:80]
            match = rating_map.get(key, {})
            # Also try partial match
            if not match:
                for k, v in rating_map.items():
                    if k[:40] in key or key[:40] in k:
                        match = v
                        break
            p2 = dict(p)
            p2["rating"] = match.get("rating", "📖")
            p2["reason"] = match.get("reason", "")
            p2["affiliation"] = match.get("affiliation", "")
            result.append(p2)
        return result, None
    except Exception as e:
        # Fallback: assign 📖 to all
        result = []
        for p in papers:
            p2 = dict(p)
            p2["rating"] = "📖"
            p2["reason"] = "解析失败，默认存档"
            p2["affiliation"] = ""
            result.append(p2)
        return result, "parse_error: %s" % str(e)[:100]



HANDBOOK_BASE = "https://raw.githubusercontent.com/sou350121/VLA-Handbook/main"
_HANDBOOK_CACHE = {}


def _fetch_handbook_context(day, cache_dir="/home/admin/clawd/memory/tmp"):
    """
    Fetch VLA-Handbook key files from GitHub and build a compact context string
    for injecting into the rating system prompt.
    Caches result for the day to avoid repeated fetches.
    """
    global _HANDBOOK_CACHE
    if day in _HANDBOOK_CACHE:
        return _HANDBOOK_CACHE[day]

    # Try disk cache first
    cache_path = os.path.join(cache_dir, "vla-handbook-ctx-%s.txt" % day)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ctx = f.read()
            _HANDBOOK_CACHE[day] = ctx
            return ctx
        except Exception:
            pass

    import re
    ctx_parts = []

    def _fetch(path, timeout=15):
        try:
            from urllib.request import urlopen as _u
            url = "%s/%s" % (HANDBOOK_BASE, path)
            resp = _u(url, timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return ""

    # 1. paper_index.md — extract already-tracked paper titles
    pi = _fetch("theory/paper_index.md")
    if pi:
        titles = []
        for line in pi.splitlines():
            # Match table rows: | Paper Title | [link](...) | ... |
            m = re.match(r"\|\s*([^|]{10,120})\s*\|\s*\[", line)
            if m:
                t = m.group(1).strip()
                if t and not t.lower().startswith(("论文", "paper", "---", "===", "title")):
                    titles.append(t)
        ctx_parts.append(
            "### 已追踪论文（paper_index.md，共 %d 篇）\n"
            "（与这些论文高度重叠的新论文应降一级）\n"
            "%s" % (len(titles), "\n".join("- " + t[:80] for t in titles[:120]))
        )

    # 2. theory/README.md — extract h2/h3 section names to show coverage
    readme = _fetch("theory/README.md")
    if readme:
        sections = []
        for line in readme.splitlines():
            if line.startswith("## ") or line.startswith("### "):
                s = line.lstrip("#").strip()
                if s and len(s) > 2:
                    sections.append(s)
        ctx_parts.append(
            "### 已有深度分析的研究方向（theory/）\n"
            "（填补以下方向空白的论文优先升级）\n"
            "%s" % "\n".join("- " + s for s in sections[:40])
        )

    # 3. benchmark_tracker.md — current SOTA baseline
    bt = _fetch("theory/benchmark_tracker.md")
    if bt:
        ctx_parts.append(
            "### 当前 Benchmark SOTA 基准线（benchmark_tracker.md）\n"
            "（超越这些基准的方法直接考虑 ⚡）\n"
            "%s" % bt[:800]
        )

    if ctx_parts:
        ctx = "\n\n".join(ctx_parts)
    else:
        ctx = "（VLA-Handbook 获取失败，按通用标准评级）"

    # Cache to disk
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(ctx)
    except Exception:
        pass

    _HANDBOOK_CACHE[day] = ctx
    return ctx


def _fetch_arxiv_authors(papers, timeout=25):
    """
    Batch-fetch author names from arXiv API for all papers with arXiv URLs.
    Returns dict: arxiv_id -> "Author1, Author2, ..."
    One API call for all papers.
    """
    import re as _re

    def _extract_arxiv_id(url):
        m = _re.search(r"arxiv\.org/abs/([\d.v]+)", url or "")
        return m.group(1).split("v")[0] if m else None

    id_map = {}  # arxiv_id -> paper_index
    for p in papers:
        aid = _extract_arxiv_id(p.get("url", ""))
        if aid:
            id_map[aid] = p

    if not id_map:
        return {}

    try:
        ids_str = ",".join(id_map.keys())
        url = ("https://export.arxiv.org/api/query?id_list=%s&max_results=%d"
               % (ids_str, len(id_map) + 5))
        resp = urlopen(url, timeout=timeout)
        xml = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("[arxiv] Metadata fetch failed: %s" % str(e)[:80], file=sys.stderr)
        return {}

    result = {}
    # Parse entries
    for entry in xml.split("<entry>")[1:]:
        # Extract arxiv id
        id_m = _re.search(r"<id>.*?/abs/([\d.v]+)</id>", entry)
        if not id_m:
            continue
        arxiv_id = id_m.group(1).split("v")[0]
        # Extract author names
        authors = _re.findall(r"<name>(.*?)</name>", entry)
        if authors:
            result[arxiv_id] = ", ".join(authors[:6])  # limit to first 6

    return result

def rate_papers(papers):
    """
    Main entry: rate a list of paper dicts.
    Returns (rated_papers, error_or_None).
    """
    if not papers:
        return [], None

    api_key = _get_api_key()
    if not api_key:
        # No API key: assign 📖 to all, note fallback
        result = [dict(p, rating="📖", reason="API key 未配置") for p in papers]
        return result, "no_api_key"

    # Fetch VLA-Handbook context for knowledge-base-aware rating
    import datetime as _dt2
    _today_str = (_dt2.datetime.utcnow() + _dt2.timedelta(hours=8)).strftime("%Y-%m-%d")
    handbook_ctx = _fetch_handbook_context(_today_str)
    system_prompt_with_ctx = (
        SYSTEM_PROMPT
        + "\n\n## VLA-Handbook 知识库状态（评级时请对照）\n"
        + "评级调整规则：\n"
        + "- 与已追踪论文高度重叠（同一方向小改进）→ 降一级\n"
        + "- 填补知识库方向空白 → 升一级\n"
        + "- 超越 benchmark_tracker SOTA → 强烈考虑 ⚡\n\n"
        + handbook_ctx
    )

    # Fetch author names from arXiv API (best-effort, one batch call)
    print("[rating] Fetching arXiv author metadata...", file=sys.stderr)
    author_map = _fetch_arxiv_authors(papers)

    # Build papers block for prompt (include authors for affiliation detection)
    import re as _re_pb

    def _get_arxiv_id(url):
        m = _re_pb.search(r"arxiv\.org/abs/([\d.v]+)", url or "")
        return m.group(1).split("v")[0] if m else None

    lines = []
    for i, p in enumerate(papers, 1):
        title = (p.get("title") or "").strip()
        snippet = (p.get("abstract_snippet") or "").strip()[:300]
        url = (p.get("url") or "").strip()
        arxiv_id = _get_arxiv_id(url)
        authors_str = author_map.get(arxiv_id or "", "")
        line = "%d. 【%s】" % (i, title)
        if authors_str:
            line += "\n   作者：%s" % authors_str
        if snippet:
            line += "\n   摘要：%s" % snippet
        if url:
            line += "\n   链接：%s" % url
        lines.append(line)
    papers_block = "\n\n".join(lines)

    user_prompt = USER_PROMPT_TEMPLATE.format(papers_block=papers_block)
    result = _call_qwen(system_prompt_with_ctx, user_prompt, api_key, timeout=120)

    if not result.get("ok"):
        err = result.get("error", "unknown")
        fallback = [dict(p, rating="📖", reason="LLM 调用失败: %s" % err) for p in papers]
        return fallback, "llm_error: %s" % err

    rated, parse_err = _parse_ratings(result["content"], papers)
    return rated, parse_err



MEM_DIR = "/home/admin/clawd/memory"


def _write_promoted_candidates(day, rated_papers, cache_dir):
    """
    Cross-pipeline routing: write ⚡ and ⚡-candidate 🔧 papers not already
    covered by vla-theory-articles.json to tmp/vla-theory-promoted-{day}.json.
    Called by main() after successful rating.
    """
    import sys as _sys
    _sys.path.insert(0, "/home/admin/clawd/scripts")
    try:
        import _vla_expert as _expert
        theory_titles = _expert.load_theory_titles()
    except Exception:
        theory_titles = set()

    promoted = []
    for p in rated_papers:
        rating = p.get("rating", "")
        if rating not in ("⚡", "🔧"):
            continue
        title = (p.get("title") or "").strip()
        if title.lower() in theory_titles:
            continue
        promoted.append({
            "title": title,
            "url": (p.get("url") or "").strip(),
            "abstract_snippet": (p.get("abstract_snippet") or "").strip(),
            "rating": rating,
            "reason": (p.get("reason") or "").strip(),
            "source": "vla-daily-promoted",
            "date": day,
        })

    out_path = os.path.join(cache_dir, "vla-theory-promoted-%s.json" % day)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            import json as _j
            _j.dump(promoted, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("[routing] %d paper(s) promoted → Theory candidates: %s"
              % (len(promoted), out_path), file=_sys.stderr)
    except Exception as e:
        print("[routing] Write failed: %s" % str(e)[:100], file=_sys.stderr)
    return promoted

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers-file", required=True,
                    help="JSON file with list of paper dicts")
    ap.add_argument("--output-file", default="",
                    help="Write rated JSON to file (default: stdout)")
    ap.add_argument("--date", default="",
                    help="YYYY-MM-DD date override for promoted candidates file")
    args = ap.parse_args()

    try:
        with open(args.papers_file, "r", encoding="utf-8") as f:
            papers = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "input_read_failed: %s" % str(e)},
                         ensure_ascii=False))
        return 1

    if not isinstance(papers, list):
        print(json.dumps({"ok": False, "error": "input must be JSON array"},
                         ensure_ascii=False))
        return 1

    print("[rating] Calling %s to rate %d papers..." % (RATING_MODEL, len(papers)),
          file=sys.stderr)
    rated, err = rate_papers(papers)

    output = {
        "ok": True,
        "model": RATING_MODEL,
        "total": len(rated),
        "counts": {
            r: sum(1 for p in rated if p.get("rating") == r)
            for r in ("⚡", "🔧", "📖", "❌")
        },
        "parse_error": err or "",
        "papers": rated,
    }

    out_str = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(out_str + "\n")
        print("[rating] Written to %s" % args.output_file, file=sys.stderr)
    else:
        print(out_str)

    # Cross-pipeline routing: promote ⚡/🔧 papers to Theory candidate pool
    if rated:
        import datetime as _routing_dt
        _day = args.date.strip() or (_routing_dt.datetime.utcnow() + _routing_dt.timedelta(hours=8)).strftime("%Y-%m-%d")
        _cache_dir = os.path.join(MEM_DIR, "tmp")
        _write_promoted_candidates(_day, rated, _cache_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
