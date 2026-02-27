#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append-only updater for VLA-Handbook `theory/paper_index.md`.

Appends new papers from the daily hotspot pipeline into the
"## 📄 Daily Papers (Auto)" section, organized by category subsections.

Python 3.6+ (no external deps).
"""

from __future__ import print_function

import argparse
import base64
import datetime as _dt
import json
import os
import re
import sys
import time

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
except Exception:
    Request = None
    urlopen = None
    HTTPError = Exception
    URLError = Exception
    quote = None


DEFAULT_GH_CONFIG = "/home/admin/clawd/memory/github-config.json"
DEFAULT_ENV_PATHS = [
    "/home/admin/.clawdbot/.env",
    "/home/admin/.moltbot/.env",
]

# Paper index file path in VLA-Handbook repo
PAPER_INDEX_PATH = "theory/paper_index.md"

# Marker for the auto-append section
AUTO_SECTION_HEADER = "## 📄 Daily Papers (Auto)"

# Subsection titles and their category keywords (order matters: first match wins)
CATEGORY_SECTIONS = [
    ("觸覺", ["tactile", "touch", "haptic", "visuotactile", "force sens", "contact-rich",
               "dexterous", "grasp refine", "tactile-force", "force-vision", "fingertip"]),
    ("動作生成", ["diffusion policy", "flow matching", "action token", "action chunk",
                 "imitation learn", "visuomotor", "action model", "action generation",
                 "manipulation policy", "bc policy", "behavior clon", "vla", "vision-language-action"]),
    ("數據", ["dataset", "benchmark", "data collection", "demonstration", "teleoperat",
              "annotation", "scaling data", "synthetic data", "real-to-sim", "simulation data"]),
    ("部署", ["deploy", "edge", "efficient", "compression", "quantiz", "prun", "latency",
              "throughput", "realtime", "real-time", "mobile", "on-device", "hardware"]),
    ("Sim2Real", ["sim-to-real", "sim2real", "transfer", "domain adapt", "domain random",
                  "zero-shot cross", "cross-embodiment", "cross embodiment"]),
]
DEFAULT_SECTION = "其他"


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_dotenv(paths):
    env = {}
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                env[k] = v
    return env


def _get_token(token_env):
    token = os.environ.get(token_env, "")
    if token:
        return token.strip()
    dotenv = _load_dotenv(DEFAULT_ENV_PATHS)
    return (dotenv.get(token_env) or "").strip()


def _gh_api(method, url, token, body=None, retries=3):
    if not (Request and urlopen):
        return -1, {"error": "urllib_unavailable"}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moltbot-vla-paper-index",
    }
    if token:
        headers["Authorization"] = "token " + token
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(retries):
        try:
            req = Request(url, data=data, method=method)
            for k, v in headers.items():
                req.add_header(k, v)
            with urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                code = resp.getcode()
                obj = json.loads(raw) if raw.strip() else {}
                return code, obj
        except HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            try:
                raw = e.read().decode("utf-8", errors="replace")
                obj = json.loads(raw) if raw.strip() else {}
            except Exception:
                obj = {}
            if code in (500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return code, obj
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return -1, {"error": str(e)[:200]}
    return -1, {"error": "max_retries"}


def _norm_url(u):
    u = (u or "").strip()
    u = u.split("#", 1)[0].split("?", 1)[0]
    return re.sub(r"/{2,}", "/", u).rstrip("/").lower()


def _extract_existing_urls(md):
    """Extract all URLs currently in the markdown document."""
    urls = set()
    for m in re.finditer(r"https?://[^\s|)\]\"']+", md):
        urls.add(_norm_url(m.group(0)))
    return urls


def _tag_to_emoji(tag):
    t = (tag or "").lower().strip()
    if t == "strategic":
        return "⚡"
    if t == "actionable":
        return "🔧"
    return "📖"


def _categorize_paper(paper):
    """Return category subsection for a paper based on title + abstract."""
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract_snippet") or "").lower()
    blob = title + " " + abstract

    # Check direction prefix override first
    prefix = (paper.get("direction_note_prefix") or "").lower()
    if "tactile" in prefix:
        return "觸覺"

    for section_name, keywords in CATEGORY_SECTIONS:
        for kw in keywords:
            if kw in blob:
                return section_name
    return DEFAULT_SECTION


def _build_row(paper, date):
    """Build a markdown table row for a paper."""
    title = (paper.get("title") or "").strip()
    url = (paper.get("url") or "").strip()
    tag = paper.get("tag", "read-only")
    repo_url = (paper.get("repo_url") or "").strip()
    why = (paper.get("why") or "").strip()
    direction_prefix = (paper.get("direction_note_prefix") or "").strip()

    emoji = _tag_to_emoji(tag)
    # Embed why with em-dash for strategic papers (AGENTS.md: use — not |)
    date_part = "%s daily %s" % (emoji, date)
    if why and tag == "strategic":
        date_part = date_part + " — " + why[:80]

    # Assemble remark per AGENTS.md note format:
    #   Primary (🎯): direction_prefix \| emoji daily date
    #   Team ([RL]):  direction_prefix emoji daily date  (space, no pipe)
    #   Repo:         ... \| repo: {url}
    remark_parts = []
    if direction_prefix:
        if direction_prefix.startswith("["):
            # Team direction: [RL] emoji daily date
            remark_parts.append(direction_prefix + " " + date_part)
        else:
            # Primary direction: emoji_prefix \| emoji daily date
            remark_parts.append(direction_prefix + " \\| " + date_part)
    else:
        remark_parts.append(date_part)
    if repo_url:
        remark_parts.append("repo: " + repo_url)
    remark = " \\| ".join(remark_parts)

    return "| %s | [link](%s) | %s |" % (title, url, remark)


def _ensure_auto_section(md):
    """If the auto section doesn't exist, append it to the document."""
    if AUTO_SECTION_HEADER in md:
        return md
    new_section = (
        "\n\n---\n\n"
        "%s\n\n"
        "> 本节由日报任务自动追加（只追加，不改动其他内容）。\n"
        "> 若你要手动维护索引，请在上方既有结构中编辑；此处仅作为每日入口与追踪。\n\n"
    ) % AUTO_SECTION_HEADER
    for section_name, _ in CATEGORY_SECTIONS:
        new_section += "\n### %s\n\n| 论文 | 链接 | 备注 |\n|:---|:---|:---|\n" % section_name
    new_section += "\n### %s\n\n| 论文 | 链接 | 备注 |\n|:---|:---|:---|\n" % DEFAULT_SECTION
    return md + new_section


def _ensure_subsection(md, section_name):
    """Ensure a subsection exists within the auto section. Returns updated md."""
    auto_start = md.find(AUTO_SECTION_HEADER)
    if auto_start == -1:
        return md
    after_auto = md[auto_start:]
    if ("### " + section_name) in after_auto:
        return md
    # Append subsection before next H2, or at end
    end_idx = auto_start + len(after_auto)
    insert = "\n### %s\n\n| 论文 | 链接 | 备注 |\n|:---|:---|:---|\n" % section_name
    md = md[:end_idx] + insert
    return md


def _append_to_subsection(md, section_name, rows):
    """Append rows to the named subsection within the auto section."""
    if not rows:
        return md, 0

    auto_start = md.find(AUTO_SECTION_HEADER)
    if auto_start == -1:
        return md, 0

    # Find the subsection within the auto area
    sub_pat = r"###\s+" + re.escape(section_name) + r"\s*\n"
    m = re.search(sub_pat, md[auto_start:])
    if not m:
        return md, 0

    abs_sub_start = auto_start + m.start()
    after_sub = md[auto_start + m.end():]

    # Find the end of the table within this subsection (next ### or ## or end)
    next_section = re.search(r"\n(##|###)", after_sub)
    if next_section:
        table_region = after_sub[:next_section.start()]
        after_table = after_sub[next_section.start():]
    else:
        table_region = after_sub
        after_table = ""

    # Find last table row or header separator
    lines = table_region.splitlines(True)
    insert_at = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            insert_at = i + 1
            break

    new_rows = [r + "\n" for r in rows]
    new_table = "".join(lines[:insert_at] + new_rows + lines[insert_at:])

    abs_after_sub_start = auto_start + m.end()
    return _rebuild_md(md, auto_start, m, after_sub, new_table, next_section, after_table), len(rows)


def _rebuild_md(md, auto_start, sub_match, after_sub, new_table, next_section, after_table):
    """Rebuild the full markdown string after modifying a subsection table."""
    before_auto = md[:auto_start]
    auto_header = md[auto_start: auto_start + sub_match.start()]
    sub_heading = sub_match.group(0)
    if next_section:
        rebuilt_auto = auto_header + sub_heading + new_table + after_table
    else:
        rebuilt_auto = auto_header + sub_heading + new_table
    return before_auto + rebuilt_auto


def _update_header_date(md, date):
    """Update '最后更新' date in the document header."""
    return re.sub(
        r"(\*\*最后更新\*\*[:：]\s*)[\d-]+",
        r"\g<1>" + date,
        md
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--papers-json", required=True,
                    help="JSON with papers array from _paper_index_input_from_hotspots.py")
    ap.add_argument("--config", default=DEFAULT_GH_CONFIG)
    ap.add_argument("--path", default=PAPER_INDEX_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    date = args.date.strip()

    # Read papers
    try:
        data = _read_json(args.papers_json)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "papers_json_read_failed",
                          "detail": str(e)[:200]}, ensure_ascii=False))
        return 1

    papers = data if isinstance(data, list) else (data.get("papers") or [])
    if not papers:
        print(json.dumps({"ok": True, "updated": False, "added": 0,
                          "reason": "no_papers"}, ensure_ascii=False))
        return 0

    # GitHub config
    try:
        cfg = _read_json(args.config)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "config_read_failed",
                          "detail": str(e)[:200]}, ensure_ascii=False))
        return 1

    repo = cfg.get("repo", "sou350121/VLA-Handbook")
    api_base = cfg.get("api_base", "https://api.github.com")
    token_env = cfg.get("token_env", "GITHUB_TOKEN")
    token = _get_token(token_env)

    if not token:
        print(json.dumps({"ok": False, "error": "no_github_token",
                          "token_env": token_env}, ensure_ascii=False))
        return 1

    # Fetch current file
    get_url = ("%s/repos/%s/contents/%s"
               % (api_base.rstrip("/"), repo, quote(args.path, safe="/")))
    code, obj = _gh_api("GET", get_url, token)
    if code != 200 or not isinstance(obj, dict) or not obj.get("sha"):
        print(json.dumps({"ok": False, "error": "fetch_failed", "http_code": code},
                         ensure_ascii=False))
        return 1

    sha = obj["sha"]
    try:
        md = base64.b64decode(obj["content"]).decode("utf-8", errors="replace")
    except Exception as e:
        print(json.dumps({"ok": False, "error": "decode_failed",
                          "detail": str(e)[:200]}, ensure_ascii=False))
        return 1

    # Extract existing URLs for dedup
    existing_urls = _extract_existing_urls(md)

    # Ensure auto section exists
    md = _ensure_auto_section(md)

    # Categorize and dedup papers
    by_category = {}
    skipped = 0
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        url = (paper.get("url") or "").strip()
        if not url:
            continue
        if _norm_url(url) in existing_urls:
            skipped += 1
            continue
        cat = _categorize_paper(paper)
        by_category.setdefault(cat, []).append(paper)

    if not by_category:
        print(json.dumps({
            "ok": True, "updated": False, "added": 0,
            "skipped_dedup": skipped, "reason": "all_deduped",
        }, ensure_ascii=False))
        return 0

    # Build rows and append to subsections
    total_added = 0
    for cat, cat_papers in by_category.items():
        md = _ensure_subsection(md, cat)
        rows = [_build_row(p, date) for p in cat_papers]
        md, added = _append_to_subsection(md, cat, rows)
        total_added += added

    if total_added == 0:
        print(json.dumps({
            "ok": True, "updated": False, "added": 0,
            "skipped_dedup": skipped,
        }, ensure_ascii=False))
        return 0

    # Update header date
    md = _update_header_date(md, date)

    if args.dry_run:
        print(json.dumps({
            "ok": True, "updated": True, "added": total_added,
            "skipped_dedup": skipped, "dry_run": True,
        }, ensure_ascii=False))
        return 0

    # Push updated file
    encoded = base64.b64encode(md.encode("utf-8")).decode("ascii")
    commit_msg = "📄 daily papers: %s (+%d papers)" % (date, total_added)
    body = {"message": commit_msg, "content": encoded, "sha": sha, "branch": "main"}
    put_url = ("%s/repos/%s/contents/%s"
               % (api_base.rstrip("/"), repo, quote(args.path, safe="/")))
    put_code, _ = _gh_api("PUT", put_url, token, body=body)

    if put_code not in (200, 201):
        print(json.dumps({"ok": False, "error": "push_failed", "http_code": put_code},
                         ensure_ascii=False))
        return 1

    print(json.dumps({
        "ok": True, "updated": True, "added": total_added,
        "skipped_dedup": skipped,
        "categories": list(by_category.keys()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
