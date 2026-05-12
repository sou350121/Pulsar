#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-update deployment/community_field_notes_github.md in VLA-Handbook.

Two update modes (both run from compute-gh-adoption.py post-step):
  1. §7 overwrite (weekly): regenerate adoption snapshot table from latest data
  2. §1-6 append  (monthly): LLM scans new tier-1 issues, appends new knowledge

Output: pushes updated markdown to your knowledge-base repo via GitHub API.
Configure target via env: PULSAR_FIELD_NOTES_REPO, PULSAR_FIELD_NOTES_PATH.

Python 3.6+ (no external deps except _vla_expert for monthly LLM).
"""

from __future__ import print_function

import base64
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _gh_issues_config import REPOS, MEMORY_DIR, ENV_PATHS
    from _vla_expert import call_qwen
except ImportError:
    pass

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    Request = urlopen = HTTPError = None

TZ_CST = timezone(timedelta(hours=8))

GH_REPO = os.environ.get("PULSAR_FIELD_NOTES_REPO", "sou350121/VLA-Handbook")
GH_PATH = os.environ.get("PULSAR_FIELD_NOTES_PATH", "deployment/community_field_notes_github.md")

# §7 markers in the markdown
SECTION7_START = "## 7. 框架采纳度信号"
SECTION7_END = "\n---\n"  # the --- before the footer

# Monthly: only run on 1st and 15th of month
MONTHLY_DAYS = {1, 15}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_token():
    """Load GITHUB_TOKEN from env or .env files."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    for p in ENV_PATHS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("GITHUB_TOKEN="):
                        return s.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    return ""


def _read_json(path, default=None):
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _latest_file(pattern):
    """Find newest file matching glob pattern."""
    files = sorted(glob.glob(str(pattern)))
    return files[-1] if files else None


def _gh_get(path, token):
    url = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    req = Request(url)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github.v3+json")
    resp = urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def _gh_put(path, content, sha, message, token):
    url = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "sha": sha,
        "branch": "main",
    }
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="PUT")
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    resp = urlopen(req, timeout=30)
    result = json.loads(resp.read().decode("utf-8"))
    return result["content"]["sha"]


# ── §7 Weekly Overwrite ───────────────────────────────────────────────────────


def _build_section7(adoption_data):
    """Build §7 table from gh-adoption JSON."""
    date = adoption_data.get("date", "?")
    phases = adoption_data.get("adoption_phases", [])
    dfis = adoption_data.get("dfi", [])
    total = adoption_data.get("total_issues_analyzed", 0)

    # Build DFI lookup
    dfi_map = {d["repo"]: d for d in dfis}

    lines = []
    lines.append("## 7. 框架采纳度信号（%s 快照）" % date)
    lines.append("")
    lines.append("| 框架 | 7d Issues | 采纳阶段 | DFI | 信号 |")
    lines.append("|------|-----------|---------|-----|------|")

    # Sort by sample_size descending
    sorted_phases = sorted(phases, key=lambda p: p.get("sample_size", 0), reverse=True)

    phase_cn = {
        "exploration": "早期探索",
        "integration": "开发整合",
        "production": "生产部署",
        "mixed": "混合",
        "dormant": "**停滞**",
    }

    for p in sorted_phases:
        repo = p["repo"]
        d = dfi_map.get(repo, {})
        phase = phase_cn.get(p.get("phase", "?"), p.get("phase", "?"))
        dfi_val = d.get("dfi", 0)
        dfi_level = d.get("level", "?")
        sample = p.get("sample_size", 0)
        top_friction = d.get("top_friction", "")

        # Build signal description
        signal_parts = []
        if top_friction:
            signal_parts.append("主要摩擦: %s" % top_friction)
        if p.get("phase") == "dormant":
            signal_parts.append("几乎无活动")
        signal = "; ".join(signal_parts) if signal_parts else "—"

        lines.append("| **%s** | %d | %s | %.2f (%s) | %s |" % (
            repo, sample, phase, dfi_val, dfi_level, signal
        ))

    lines.append("")
    lines.append("> 数据来源: Pulsar GitHub Issues Sensor, %d issues analyzed in 7-day window" % total)

    return "\n".join(lines)


# ── §1-6 Monthly LLM Append ──────────────────────────────────────────────────


def _build_monthly_update_prompt(tier1_candidates, current_doc):
    """Build LLM prompt to identify new knowledge from tier-1 issues."""
    if not tier1_candidates:
        return None

    # Filter to candidates not yet in the document
    new_candidates = []
    for c in tier1_candidates:
        url = c.get("url", "")
        # Check if issue URL already appears in the document
        if url and url not in current_doc:
            new_candidates.append(c)

    if not new_candidates:
        return None

    context_lines = ["以下是本月新发现的一级 GitHub Issues（高互动、高价值）:\n"]
    for c in new_candidates[:10]:  # cap at 10
        context_lines.append("- **%s #%d**: %s" % (c["repo"], c["number"], c["title"]))
        context_lines.append("  URL: %s" % c["url"])
        context_lines.append("  类别: %s | 评论数: %d | 原因: %s" % (
            c.get("category", "?"), c.get("comments_count", 0), c.get("reason", "?")
        ))
        context_lines.append("")

    context = "\n".join(context_lines)

    system_prompt = (
        "你是 VLA 部署工程知识库的维护者。以下是本月新发现的一级 GitHub Issues。\n"
        "请判断哪些 Issue 包含值得添加到知识库的新信息，并为每条生成一段追加文本。\n\n"
        "规则：\n"
        "1. 只输出真正有新工程知识的条目（新硬件兼容数据、新训练配方、新 bug 修复）\n"
        "2. 每条格式：`§N.M 追加` + 一段话 + Issue 链接\n"
        "3. §N 对应文档的章节号（1=硬件, 2=训练, 3=推理, 4=模拟器, 5=机器人硬件, 6=跨仓库）\n"
        "4. 如果 Issue 的知识已经在文档中有覆盖，输出 `SKIP: <reason>`\n"
        "5. 保持简体中文，客观语气，含具体数据\n"
        "6. 如果没有任何新知识值得追加，只输出 `NO_NEW_KNOWLEDGE`\n\n"
        "输出纯文本，不要 JSON。"
    )

    return system_prompt, context, new_candidates


def _apply_monthly_updates(doc, llm_output):
    """Parse LLM output and append to appropriate sections."""
    if not llm_output or "NO_NEW_KNOWLEDGE" in llm_output:
        return doc, 0

    # Parse §N.M 追加 blocks
    blocks = re.findall(
        r"§(\d+)\.\d+\s*追加[：:]\s*(.+?)(?=§\d+\.\d+\s*追加|SKIP:|$)",
        llm_output, re.DOTALL
    )

    if not blocks:
        return doc, 0

    section_headers = {
        "1": "## 1. 硬件兼容性矩阵",
        "2": "## 2. 训练配方与陷阱",
        "3": "## 3. 推理与部署",
        "4": "## 4. 模拟器与基准",
        "5": "## 5. 机器人硬件与数据采集",
        "6": "## 6. 跨仓库收敛信号",
    }

    count = 0
    for section_num, content in blocks:
        content = content.strip()
        if not content or len(content) < 20:
            continue

        header = section_headers.get(section_num)
        if not header or header not in doc:
            continue

        # Find the NEXT section header after this one
        next_headers = [h for n, h in sorted(section_headers.items()) if n > section_num]
        next_header = next_headers[0] if next_headers else "---"

        # Insert before the next section
        insert_point = doc.find(next_header)
        if insert_point == -1:
            continue

        # Add the new content with a date tag
        today = datetime.now(TZ_CST).strftime("%Y-%m-%d")
        addition = "\n**[%s 更新]** %s\n" % (today, content)

        doc = doc[:insert_point] + addition + "\n" + doc[insert_point:]
        count += 1

    return doc, count


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    today = datetime.now(TZ_CST)
    today_str = today.strftime("%Y-%m-%d")
    is_monthly = today.day in MONTHLY_DAYS

    print("=== Update GitHub Field Notes ===")
    print("Date: %s | Monthly: %s" % (today_str, is_monthly))

    # 1. Load latest adoption data
    adoption_file = _latest_file(MEMORY_DIR / "gh-adoption-*.json")
    if not adoption_file:
        print("SKIP: no gh-adoption-*.json found")
        return

    adoption = _read_json(adoption_file)
    print("Loaded adoption data: %s (%d issues)" % (
        adoption.get("date", "?"), adoption.get("total_issues_analyzed", 0)
    ))

    # 2. Load GitHub token
    token = _load_token()
    if not token:
        print("ERROR: no GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)

    # 3. Fetch current document from GitHub
    try:
        doc, sha = _gh_get(GH_PATH, token)
        print("Fetched document: %d chars, sha=%s" % (len(doc), sha[:8]))
    except Exception as e:
        print("ERROR fetching document: %s" % e, file=sys.stderr)
        sys.exit(1)

    changed = False

    # 4. §7 weekly overwrite
    new_s7 = _build_section7(adoption)
    if SECTION7_START in doc:
        # Find §7 boundaries
        s7_start = doc.index(SECTION7_START)
        # Find the footer separator after §7
        s7_end_marker = "\n---\n"
        s7_end = doc.find(s7_end_marker, s7_start)
        if s7_end == -1:
            s7_end = len(doc)

        doc = doc[:s7_start] + new_s7 + "\n" + doc[s7_end:]
        changed = True
        print("§7 updated with %s data" % adoption.get("date", "?"))
    else:
        print("WARN: §7 header not found, skipping overwrite")

    # 5. Monthly §1-6 LLM append
    monthly_count = 0
    if is_monthly:
        tier1_path = MEMORY_DIR / "tmp" / "gh-issues-tier1-candidates.json"
        tier1_data = _read_json(tier1_path, {"candidates": []})
        candidates = tier1_data.get("candidates", [])

        # Filter to last 30 days
        cutoff = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        recent = [c for c in candidates if c.get("surfaced_date", "") >= cutoff]

        prompt_result = _build_monthly_update_prompt(recent, doc)
        if prompt_result:
            sys_prompt, user_prompt, new_cands = prompt_result
            print("Monthly LLM: %d new tier-1 candidates to evaluate" % len(new_cands))

            result = call_qwen(sys_prompt, user_prompt, timeout=120, temperature=0.2)
            if result.get("ok"):
                doc, monthly_count = _apply_monthly_updates(doc, result["content"])
                if monthly_count:
                    changed = True
                    print("Monthly: %d new entries appended to §1-6" % monthly_count)
                else:
                    print("Monthly: LLM found no new knowledge to add")
            else:
                print("WARN: Monthly LLM failed: %s" % result.get("error", ""))
        else:
            print("Monthly: no new tier-1 candidates (all already in doc)")
    else:
        print("Monthly update skipped (day=%d, runs on %s)" % (today.day, MONTHLY_DAYS))

    # 6. Update last-updated footer
    footer_pattern = r"\*最后更新: \d{4}-\d{2}-\d{2}\*"
    if re.search(footer_pattern, doc):
        doc = re.sub(footer_pattern, "*最后更新: %s*" % today_str, doc)
        changed = True

    # 7. Push if changed
    if changed:
        parts = ["§7 adoption snapshot"]
        if monthly_count:
            parts.append("%d new §1-6 entries" % monthly_count)
        commit_msg = "Auto-update GitHub field notes: %s (%s)" % (
            " + ".join(parts), today_str
        )

        try:
            new_sha = _gh_put(GH_PATH, doc, sha, commit_msg, token)
            print("Pushed to GitHub: %s → %s" % (GH_PATH, new_sha[:8]))
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            print("ERROR pushing: HTTP %d %s" % (e.code, body), file=sys.stderr)
            sys.exit(1)
    else:
        print("No changes needed")

    print("Done.")


if __name__ == "__main__":
    main()
