#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Theory Deep Dive - Phase 3: Post-processor.

- Quality-gate the article before GitHub push (length, sections, LaTeX)
- Find the theory article markdown written to tmp/ for this date
- Push it to GitHub VLA-Handbook/{target_dir}/{slug}.md
- Upsert entry into memory/vla-theory-articles.json (with extracted URL)
- Send Telegram notification (best-effort)

Called with: python3 post-vla-theory.py --date YYYY-MM-DD [--slug SLUG] [--target-dir DIR]

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import base64
import datetime as _dt
import json
import os
import re
import subprocess
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


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
THEORY_ARTICLES_PATH = os.path.join(MEM_DIR, "vla-theory-articles.json")
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"
GH_CONFIG_PATH = os.path.join(MEM_DIR, "github-config.json")
DEFAULT_ENV_PATHS = [
    "/home/admin/.clawdbot/.env",
    "/home/admin/.moltbot/.env",
]

# Quality gate thresholds
QG_MIN_CHARS = 2000
QG_MIN_H2 = 5


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _run(cmd, timeout=60, cwd="/home/admin"):
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return int(p.returncode), (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 125, "", str(e)


def _send_telegram(text, target="1898430254", account="original"):
    if not text:
        return {"ok": True, "skipped": True}
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    rc, out, err = _run(cmd, timeout=45)
    return {"ok": (rc == 0), "rc": rc, "out": (out or "")[:200]}


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


def _get_gh_token():
    cfg = _read_json(GH_CONFIG_PATH, {})
    token_env = cfg.get("token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env, "")
    if token:
        return token.strip()
    dotenv = _load_dotenv(DEFAULT_ENV_PATHS)
    return (dotenv.get(token_env) or "").strip()


def _gh_api(method, url, token, body=None, max_retries=3):
    """Make GitHub API call with retry on 5xx."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moltbot-vla-theory",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(max_retries):
        try:
            req = Request(url, data=data, method=method)
            for k, v in headers.items():
                req.add_header(k, v)
            resp = urlopen(req, timeout=30)
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.getcode(), json.loads(raw) if raw.strip() else {}
        except HTTPError as e:
            code = e.code
            try:
                raw = e.read().decode("utf-8", errors="replace")
                body_obj = json.loads(raw) if raw.strip() else {}
            except Exception:
                body_obj = {}
            if code in (500, 502, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return code, body_obj
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return -1, {"error": str(e)[:200]}
    return -1, {"error": "max_retries_exceeded"}


def _push_to_github(content_md, target_dir, slug, day, token, repo, api_base):
    """Push markdown article to GitHub via Contents API."""
    if not (Request and urlopen and quote):
        return {"ok": False, "error": "urllib_unavailable"}

    file_path = "%s/%s.md" % (target_dir, slug)
    url = ("%s/repos/%s/contents/%s"
           % (api_base.rstrip("/"), repo, quote(file_path, safe="/")))

    # Check if file exists (to get SHA for update)
    code, existing = _gh_api("GET", url, token)
    sha = None
    if code == 200 and isinstance(existing, dict):
        sha = existing.get("sha")

    encoded = base64.b64encode(content_md.encode("utf-8")).decode("ascii")
    commit_msg = ("theory: add %s (%s)" % (slug, day)
                  if sha is None
                  else "theory: update %s (%s)" % (slug, day))
    body = {
        "message": commit_msg,
        "content": encoded,
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    method = "PUT"
    code, result = _gh_api(method, url, token, body=body)
    if code in (200, 201):
        html_url = ((result.get("content") or {}).get("html_url") or "")
        return {"ok": True, "html_url": html_url, "updated": (sha is not None)}
    return {"ok": False, "code": code, "detail": str(result)[:300]}


def _find_article_file(day, slug=None):
    """Find the theory article markdown file for this day (and optionally slug)."""
    if not os.path.isdir(TMP_DIR):
        return None
    pattern = re.compile(
        r"vla-theory-article-(.+)-(%s)\.md$" % re.escape(day)
    )
    candidates = []
    for fn in os.listdir(TMP_DIR):
        m = pattern.match(fn)
        if m:
            file_slug = m.group(1)
            if slug and file_slug != slug:
                continue
            path = os.path.join(TMP_DIR, fn)
            candidates.append((os.path.getmtime(path), file_slug, path))
    if not candidates:
        return None
    # Return the most recently modified one
    candidates.sort(reverse=True)
    return candidates[0][1], candidates[0][2]  # (slug, path)


def _infer_target_dir(slug, content):
    """Infer target_dir from slug/content if not provided."""
    sl = slug.lower()
    ct = content.lower()
    if any(k in sl or k in ct for k in ("tactile", "touch", "haptic", "force-sens")):
        return "theory/tactile"
    if any(k in sl or k in ct for k in ("foundation", "pretrain", "generalist")):
        return "theory/foundation"
    return "theory"


# ── Step 1: quality gate ──────────────────────────────────────────────────────

def _quality_gate(content_md):
    """
    Programmatic quality check before GitHub push.
    Returns (passed: bool, issues: list[str]).
    Checks:
      - Minimum character count (QG_MIN_CHARS)
      - Minimum ## section count (QG_MIN_H2)
      - Zero LaTeX $$ occurrences (LaTeX breaks GitHub Markdown)
    """
    issues = []
    length = len(content_md.strip())
    if length < QG_MIN_CHARS:
        issues.append("too_short (%d chars, min %d)" % (length, QG_MIN_CHARS))

    h2_count = len(re.findall(r"^##\s+", content_md, re.MULTILINE))
    if h2_count < QG_MIN_H2:
        issues.append("too_few_sections (%d ## sections, min %d)" % (h2_count, QG_MIN_H2))

    # Count $$ occurrences — any presence means LaTeX contamination
    latex_count = len(re.findall(r"\$\$", content_md))
    if latex_count > 0:
        issues.append("latex_contamination (%d '$$' found — banned for GitHub Markdown)" % latex_count)

    passed = (len(issues) == 0)
    return passed, issues


# ── Step 2: extract canonical URL from article header ─────────────────────────

def _extract_article_url(content_md):
    """
    Parse the **链接**: line from the article's metadata block (first 2000 chars).
    Returns the URL string or "" if not found.
    """
    # Match: **链接**: https://... or **链接**：https://...
    m = re.search(
        r"\*\*链接\*\*\s*[:\uff1a]\s*(https?://\S+)",
        content_md[:2000],
    )
    if m:
        url = m.group(1).rstrip(".,;)")
        if len(url) > 10:
            return url
    return ""


# ── Step 3: read candidate JSON for URL fallback ──────────────────────────────

def _read_candidate_url(day):
    """
    Read vla-theory-candidates-{day}.json from tmp/ and return the first
    candidate's url field as a fallback when the article has no **链接** line.
    """
    candidates_path = os.path.join(TMP_DIR, "vla-theory-candidates-%s.json" % day)
    data = _read_json(candidates_path, {})
    candidates = data.get("candidates", [])
    if candidates and isinstance(candidates[0], dict):
        url = candidates[0].get("url", "")
        if url and url.startswith("http"):
            return url
    return ""


def _upsert_theory_articles(day, slug, title, url, target_dir, html_url, dry_run=False):
    obj = _read_json(THEORY_ARTICLES_PATH, {"theory_articles": []})
    rows = obj.get("theory_articles")
    if not isinstance(rows, list):
        rows = []

    entry = {
        "date": day,
        "slug": slug,
        "title": title,
        "url": url,
        "target_dir": target_dir,
        "github_path": "%s/%s.md" % (target_dir, slug),
        "html_url": html_url,
    }
    replaced = False
    for i, r in enumerate(rows):
        if isinstance(r, dict) and r.get("slug") == slug:
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)

    rows = [r for r in rows if isinstance(r, dict) and r.get("slug")]
    rows.sort(key=lambda x: (x.get("date") or ""))
    rows = rows[-200:]  # keep history

    out_obj = {"theory_articles": rows}
    if not dry_run:
        _write_json_atomic(THEORY_ARTICLES_PATH, out_obj)
    return {"total": len(rows), "replaced": replaced}


def _extract_title_from_md(content):
    """Extract first H1 title from markdown content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""



# ── Semantic quality gate (LLM review after structural gate) ──────────────────

_SG_PASS_THRESHOLD = 10  # out of 14 (7 items × 2 pts each)


def _semantic_gate(content_md, title, day):
    """
    Call qwen-max to review the article for X-Ray template quality.
    Returns (passed: bool, score: int, issues: list[str], feedback: str).
    Threshold: score >= _SG_PASS_THRESHOLD (10/14).
    """
    import sys as _sys
    _sys.path.insert(0, "/home/admin/clawd/scripts")
    try:
        import _vla_expert
    except Exception as e:
        return True, -1, [], "semantic_gate_skipped: import failed (%s)" % str(e)[:80]

    api_key = _vla_expert.get_api_key()
    if not api_key:
        return True, -1, [], "semantic_gate_skipped: no_api_key"

    # Truncate to avoid huge token usage while keeping all sections
    article_excerpt = content_md[:8000]

    SYSTEM = """你是 VLA Theory X-Ray 系列的责任编辑。请审核以下深度解析文章，检查 7 项质量标准。

## 评分标准（每项 0-2 分，满分 14）
1. **X-Ray 开场**（0-2）：文章开头 3 句以内是否用非专业语言清晰说明论文解决什么问题？
   - 2分：清晰、生动，外行可读；1分：有但不够清晰；0分：缺失或直接进入技术语言
2. **研究全景时间线**（0-2）：是否有 ASCII 时间线图展示该方向的发展脉络？
   - 2分：有且信息量丰富；1分：有但过于简略；0分：缺失
3. **⚡ Eureka Moment**（0-2）：是否有一句话清晰说出论文最核心的洞见？
   - 2分：精准、令人"原来如此"；1分：有但表述模糊；0分：缺失
4. **📌 Napkin Formula**（0-2）：是否有一行公式、伪代码或方程总结方法本质？
   - 2分：存在且准确；1分：有类似内容但不够精练；0分：缺失
5. **§6.1 隐含假设**（0-2）：是否分析了论文未明说的前提假设？
   - 2分：至少 2 条非显然的隐含假设；1分：仅1条或过于显然；0分：缺失
6. **技术深度**（0-2）：架构分析和实验解读是否言之有物（非简单转述摘要）？
   - 2分：有独到分析；1分：基本够用；0分：流于表面
7. **语言规范**（0-2）：全程简体中文？专业术语后跟英文？无繁体字？
   - 2分：完全符合；1分：小瑕疵；0分：大量繁体或英文混乱

通过门槛：总分 ≥ 10/14

输出格式（严格 JSON，不含 markdown 代码块）：
{
  "scores": {
    "xray_opening": 0,
    "timeline": 0,
    "eureka": 0,
    "napkin": 0,
    "hidden_assumptions": 0,
    "depth": 0,
    "language": 0
  },
  "total": 0,
  "passed": true,
  "issues": ["具体问题1", "具体问题2"],
  "feedback": "总体评语（≤60字）"
}
"""

    USER = """请审核以下 VLA Theory 文章《%s》：

---
%s
---
""" % (title[:80], article_excerpt)

    result = _vla_expert.call_qwen(SYSTEM, USER, timeout=180)
    if not result.get("ok"):
        # If LLM fails, skip semantic gate (don't block the pipeline)
        return True, -1, [], "semantic_gate_skipped: %s" % result.get("error", "?")[:60]

    raw = result["content"].strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))

    try:
        import json as _j
        obj = _j.loads(raw)
        total = int(obj.get("total", 0))
        passed = (total >= _SG_PASS_THRESHOLD)
        issues = obj.get("issues", [])
        feedback = obj.get("feedback", "")
        if not isinstance(issues, list):
            issues = [str(issues)]
        return passed, total, issues, feedback
    except Exception as e:
        return True, -1, [], "semantic_gate_parse_failed: %s" % str(e)[:80]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--slug", default="", help="Article slug (auto-detected if empty)")
    ap.add_argument("--target-dir", default="", help="GitHub target dir (auto-detected if empty)")
    ap.add_argument("--target", default="1898430254", help="Telegram chat ID")
    ap.add_argument("--account", default="original")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--no-github", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    tg_target = (args.target or "").strip() or "1898430254"
    tg_account = (args.account or "").strip()

    # Find the article file
    result = _find_article_file(day, slug=args.slug.strip() or None)
    if result is None:
        print(json.dumps({
            "ok": False, "date": day,
            "error": "article_file_not_found",
            "searched_in": TMP_DIR,
        }, ensure_ascii=False))
        return 1
    slug, article_path = result

    try:
        with open(article_path, "r", encoding="utf-8") as f:
            content_md = f.read()
    except Exception as e:
        print(json.dumps({
            "ok": False, "date": day,
            "error": "article_read_failed", "detail": str(e)[:200],
        }, ensure_ascii=False))
        return 1

    title = _extract_title_from_md(content_md)
    target_dir = (args.target_dir.strip()
                  or _infer_target_dir(slug, content_md))

    # ── Step 1: quality gate (programmatic, before GitHub push) ──────────────
    qg_passed, qg_issues = _quality_gate(content_md)
    if not qg_passed:
        warn_text = (
            "⚠️ VLA Theory | %s — 《%s》质量门未通过，已跳过 GitHub 推送\n"
            "问题：%s\n"
            "请修正文章后重新运行 post-vla-theory.py"
        ) % (day, title[:50] or slug, "; ".join(qg_issues))
        _send_telegram(warn_text, target=tg_target, account=tg_account)
        print(json.dumps({
            "ok": False,
            "date": day,
            "slug": slug,
            "title": title,
            "quality_gate": {"passed": False, "issues": qg_issues},
        }, ensure_ascii=False))
        return 1

    # ── Step 1.5: semantic gate (LLM review of X-Ray template quality) ──────
    sg_passed, sg_score, sg_issues, sg_feedback = _semantic_gate(content_md, title, day)
    if not sg_passed:
        warn_lines = [
            "⚠️ VLA Theory 语义审查未通过 | %s — 《%s》" % (day, title[:50] or slug),
            "评分：%d/14（通过线 %d/14）" % (sg_score, _SG_PASS_THRESHOLD),
        ]
        if sg_issues:
            warn_lines.append("问题：" + "；".join(sg_issues[:4]))
        if sg_feedback:
            warn_lines.append("编辑意见：" + sg_feedback)
        warn_lines.append("请修正后重新运行 post-vla-theory.py")
        _send_telegram("\n".join(warn_lines), target=tg_target, account=tg_account)
        print(json.dumps({
            "ok": False,
            "date": day,
            "slug": slug,
            "title": title,
            "quality_gate": {"passed": True, "issues": []},
            "semantic_gate": {
                "passed": False,
                "score": sg_score,
                "threshold": _SG_PASS_THRESHOLD,
                "issues": sg_issues,
                "feedback": sg_feedback,
            },
        }, ensure_ascii=False))
        return 1

    # ── Step 2+3: resolve canonical URL for memory storage ───────────────────
    # Prefer URL extracted from the article's **链接** line (LLM-written),
    # fall back to the candidate JSON's source URL.
    article_url = _extract_article_url(content_md)
    if not article_url:
        article_url = _read_candidate_url(day)

    # GitHub push
    gh_result = {"ok": True, "skipped": True}
    html_url = ""
    if not args.no_github and not args.dry_run:
        cfg = _read_json(GH_CONFIG_PATH, {})
        repo = cfg.get("repo", "sou350121/VLA-Handbook")
        api_base = cfg.get("api_base", "https://api.github.com")
        token = _get_gh_token()
        if not token:
            gh_result = {"ok": False, "error": "no_github_token"}
        else:
            gh_result = _push_to_github(
                content_md, target_dir, slug, day, token, repo, api_base)
            html_url = gh_result.get("html_url", "")

    # ── Step 4: memory write — pass resolved URL instead of "" ───────────────
    mem_result = {"ok": True, "skipped": True}
    if not args.dry_run:
        try:
            mem = _upsert_theory_articles(day, slug, title, article_url,
                                          target_dir, html_url, dry_run=False)
            mem_result = {"ok": True, **mem}
        except Exception as e:
            mem_result = {"ok": False, "error": str(e)[:200]}

    # Telegram notification
    tg = {"ok": True, "skipped": True}
    if not args.dry_run and not args.no_telegram:
        if html_url:
            tg_text = ("📝 VLA Theory | %s — 《%s》已推送至 GitHub\n%s"
                       % (day, title[:60] or slug, html_url))
        else:
            tg_text = ("📝 VLA Theory | %s — 《%s》已写入（GitHub 推送%s）"
                       % (day, title[:60] or slug,
                          "成功" if gh_result.get("ok") else "失败"))
        tg = _send_telegram(tg_text, target=tg_target, account=tg_account)

    print(json.dumps({
        "ok": True,
        "date": day,
        "slug": slug,
        "title": title,
        "target_dir": target_dir,
        "article_path": article_path,
        "article_url": article_url,
        "quality_gate": {"passed": True, "issues": []},
        "semantic_gate": {
            "passed": sg_passed,
            "score": sg_score,
            "threshold": _SG_PASS_THRESHOLD,
            "feedback": sg_feedback,
        },
        "github": gh_result,
        "memory": mem_result,
        "telegram": tg,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
