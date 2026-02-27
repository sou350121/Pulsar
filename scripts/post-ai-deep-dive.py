#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App Deep Dive - Phase 3: Post-processor.

- Read candidate JSON for target path / slug info
- Find the generated article in memory/tmp/
- Push article to Agent-Playbook memory/blog/archives/deep-dive/ via GitHub Contents API
- Merge into ai-app-deep-dive-articles.json (dedup memory)
- Send Telegram notification with article title + GitHub URL

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import base64
import datetime as _dt
import glob
import json
import os
import re as _re
import subprocess
import sys

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
except ImportError:
    Request = urlopen = HTTPError = URLError = quote = None


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
DEEP_DIVE_PATH = os.path.join(MEM_DIR, "ai-app-deep-dive-articles.json")
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"

GH_CONFIG_PATH = os.path.join(MEM_DIR, "github-config-agent-playbook.json")
GH_DOTENV_PATHS = [
    "/home/admin/.clawdbot/.env",
    "/home/admin/.moltbot/.env",
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


def _sanitize_latex(md_content):
    """Strip LaTeX math syntax that breaks GitHub Markdown rendering.
    AI App articles rarely use LaTeX, but this is a safety net.
    Returns (sanitized_content, num_fixes).
    """
    fixes = 0

    def _block_repl(m):
        nonlocal fixes
        fixes += 1
        inner = m.group(1).strip()
        return "\n```\n%s\n```\n" % inner

    md_content = _re.sub(
        r'\$\$\s*(.*?)\s*\$\$',
        _block_repl,
        md_content,
        flags=_re.DOTALL,
    )

    def _inline_repl(m):
        nonlocal fixes
        inner = m.group(1)
        if _re.match(r'^\d', inner):
            return m.group(0)
        fixes += 1
        return "`%s`" % inner

    md_content = _re.sub(
        r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)',
        _inline_repl,
        md_content,
    )

    return md_content, fixes


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


# ------------------------------------------------------------------
# GitHub
# ------------------------------------------------------------------

def _load_github_config():
    """Load Agent-Playbook GitHub config. Returns (repo, branch, token) or None."""
    try:
        with open(GH_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None

    repo = cfg.get("repo", "")
    branch = cfg.get("branch", "main")
    token_env = cfg.get("token_env", "GITHUB_TOKEN")

    token = os.environ.get(token_env, "")
    if not token:
        for p in GH_DOTENV_PATHS:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith(token_env + "="):
                            token = s.split("=", 1)[1].strip()
                            break
            except Exception:
                continue
            if token:
                break

    if not repo or not token:
        return None
    return repo, branch, token


def _gh_api(method, url, token, data=None, timeout=30):
    """Minimal GitHub API helper. Returns (status_code, response_dict)."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer %s" % token,
        "User-Agent": "moltbot-ai-deep-dive-poster",
    }
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=body, headers=headers)
    req.get_method = lambda: method
    try:
        resp = urlopen(req, timeout=timeout)
        code = resp.getcode()
        raw = resp.read().decode("utf-8", errors="replace")
        return code, json.loads(raw) if raw else {}
    except HTTPError as e:
        code = e.code
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        try:
            return code, json.loads(raw)
        except Exception:
            return code, {"message": raw[:300]}
    except Exception as e:
        return 0, {"message": str(e)[:300]}


def _push_article_to_github(candidate, md_content, dry_run=False):
    """Push a single article to GitHub Agent-Playbook. Returns result dict."""
    cfg = _load_github_config()
    if cfg is None:
        return {"ok": False, "error": "github_config_missing"}

    repo, branch, token = cfg
    target_dir = candidate.get("target_dir", "memory/blog/archives/deep-dive")
    slug = candidate.get("slug", "unnamed_topic_deep_dive")
    file_path = "%s/%s.md" % (target_dir, slug)
    api_url = "https://api.github.com/repos/%s/contents/%s" % (
        repo, quote(file_path, safe="/"))

    title = candidate.get("title", "Untitled")

    if dry_run:
        return {"ok": True, "skipped": True, "path": file_path,
                "md_len": len(md_content)}

    # GET existing file for sha (idempotent rerun)
    sha = None
    get_url = api_url
    if branch:
        get_url += "?ref=%s" % quote(branch, safe="")
    code, resp = _gh_api("GET", get_url, token)
    if code == 200:
        sha = resp.get("sha", "")

    # PUT create or update
    commit_msg = "\U0001f50d AI deep dive: %s" % title[:80]
    payload = {
        "message": commit_msg,
        "content": base64.b64encode(md_content.encode("utf-8")).decode("ascii"),
    }
    if branch:
        payload["branch"] = branch
    if sha:
        payload["sha"] = sha

    code, resp = _gh_api("PUT", api_url, token, data=payload)
    if code in (200, 201):
        html_url = resp.get("content", {}).get("html_url", "")
        return {"ok": True, "status": code, "path": file_path,
                "html_url": html_url}
    else:
        msg = resp.get("message", "")[:200]
        return {"ok": False, "status": code, "path": file_path,
                "error": msg}



# ------------------------------------------------------------------
# Article extraction helpers
# ------------------------------------------------------------------

def _extract_summary(article_md):
    import re as _re2
    m = _re2.search(r'\*\*\u4e00\u53e5\u8bdd\u5b9a\u4f4d\*\*[^\n]*\n+(.+?)(?:\n|$)', (article_md or "")[:1500])
    if m:
        text = _re2.sub(r'[*_`>]', '', m.group(1).strip())
        return _re2.sub(r'\s+', ' ', text).strip()[:120]
    m = _re2.search(r'## \u4e00\u53e5\u8bdd\u6458\u8981[^\n]*\n+(.+?)(?:\n\n|\n##)', (article_md or ""), _re2.S)
    if m:
        text = _re2.sub(r'[*_`>]', '', m.group(1).strip())
        return _re2.sub(r'\s+', ' ', text).strip()[:120]
    return ""


def _extract_trap(article_md):
    import re as _re2
    m = _re2.search(r'\*\*\u9677\u9631\s*\d+\s*[\u2014\-]\s*(.+?)\*\*', (article_md or ""))
    if m:
        return m.group(1).strip()[:80]
    return ""


def _extract_action(article_md):
    import re as _re2
    m = _re2.search(r'## \u751f\u5b58\u6307\u5357[^\n]*\n.{0,300}\u2705\s*\*\*\u9002\u5408\u7528\*\*:?\s*([^\n]+)', (article_md or ""), _re2.S)
    if m:
        return m.group(1).strip()[:100]
    return ""


# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------

def _extract_article_url(md_content):
    """Extract the canonical URL from the article header **链接**: field.

    LLM often discovers a more specific URL (release page, blog post) than the
    generic candidate URL.  We prefer that URL for memory storage.
    Returns the extracted URL string, or "" if not found.
    """
    # Match: **链接**: https://...  (anywhere in first 2000 chars)
    # Use \S+ to avoid newline-in-string issues with raw strings
    m = _re.search(
        r'\*\*链接\*\*\s*[::：]\s*(https?://\S+)',
        md_content[:2000],
    )
    if m:
        url = m.group(1).rstrip('.,;)')
        if len(url) > 10:
            return url
    return ""


def _quality_gate(md_content):
    """Check article quality before pushing to GitHub.

    Returns (passed: bool, issues: list[str]).
    Hard failures (passed=False): will cause candidate skip.
    """
    issues = []
    passed = True

    length = len(md_content.strip())
    if length < 1500:
        issues.append("too_short (%d chars, min 1500)" % length)
        passed = False

    # Required sections (hard gate) - using Unicode escapes for Chinese
    arch_section = "\u67b6\u6784\u672c\u8d28"             # 架构本质
    traps_section = "\u7406\u8bba\u597d\u7528"              # 理论好用
    claude_section = "Claude Code"
    concurrency_section = "\u5e76\u53d1"                      # 并发

    for text, issue_key in [
        (arch_section, "missing_section:arch"),
        (traps_section, "missing_section:traps"),
        (claude_section, "missing_section:claude_blind_spots"),
        (concurrency_section, "missing_section:concurrency_security"),
    ]:
        if text not in md_content:
            issues.append(issue_key)
            passed = False

    # Claude Code section must have at least one bad-example marker
    if "\u274c" not in md_content and "xx" not in md_content:
        # soft warn only - don't fail hard on this
        issues.append("warn:missing_claude_blind_spot_example")

    # Warn (non-fatal) if no table found
    if "|---|" not in md_content and "| ---" not in md_content and "|---" not in md_content:
        issues.append("warn:no_table_found")

    return passed, issues


def _merge_deep_dive_articles(day, candidate, github_path, html_url, article_url=""):
    """Append to ai-app-deep-dive-articles.json (dedup tracker)."""
    obj = _read_json(DEEP_DIVE_PATH, {"deep_dive_articles": []})
    entries = obj.get("deep_dive_articles", [])
    if not isinstance(entries, list):
        entries = []

    # Prefer the URL the LLM used in the article (**链接**: field) over the
    # generic candidate URL, as the LLM often discovers a more specific page.
    best_url = article_url or candidate.get("url", "")
    new_entry = {
        "date": day,
        "title": candidate.get("title", ""),
        "url": best_url,
        "slug": candidate.get("slug", ""),
        "github_path": github_path,
        "html_url": html_url,
        "source": candidate.get("source", ""),
        "signal_type": candidate.get("signal_type", ""),
    }

    # Replace same-day + same-slug if exists (idempotent rerun)
    replaced = False
    for i, e in enumerate(entries):
        if (isinstance(e, dict) and e.get("date") == day
                and e.get("slug") == new_entry["slug"]):
            entries[i] = new_entry
            replaced = True
            break
    if not replaced:
        entries.append(new_entry)

    # Keep last 100 entries
    if len(entries) > 100:
        entries = entries[-100:]

    obj["deep_dive_articles"] = entries
    _write_json(DEEP_DIVE_PATH, obj)


# ------------------------------------------------------------------
# Telegram
# ------------------------------------------------------------------

def _send_telegram(text, target="1898430254", account=""):
    if not text:
        return 0, "", ""
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    return _run(cmd, timeout=45)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="ai_agent_dailybot")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()

    # --- Find candidate JSON ---
    cand_path = os.path.join(TMP_DIR,
                             "ai-deep-dive-candidates-%s.json" % day)
    cand_data = _read_json(cand_path, {"candidates": []})
    candidates = cand_data.get("candidates", [])
    if not candidates:
        print(json.dumps({"ok": True, "date": day, "skipped": True,
                          "reason": "no_candidates"},
                         ensure_ascii=False))
        return 0

    # --- Find article file(s) ---
    pattern = os.path.join(TMP_DIR, "ai-deep-dive-article-*-%s.md" % day)
    article_files = sorted(glob.glob(pattern))

    if not article_files:
        print(json.dumps({"ok": False, "date": day,
                          "error": "no_article_files_found",
                          "pattern": pattern},
                         ensure_ascii=False))
        return 0

    results = []
    for candidate in candidates:
        slug = candidate.get("slug", "")
        # Find matching article file
        article_path = None
        for af in article_files:
            if slug in os.path.basename(af):
                article_path = af
                break
        if not article_path:
            results.append({"slug": slug, "ok": False,
                            "error": "article_file_not_found"})
            continue

        try:
            with open(article_path, "r", encoding="utf-8") as f:
                md_content = f.read()
        except Exception as e:
            results.append({"slug": slug, "ok": False,
                            "error": str(e)[:200]})
            continue

        if len(md_content.strip()) < 200:
            results.append({"slug": slug, "ok": False,
                            "error": "article_too_short (%d chars)" %
                            len(md_content)})
            continue

        # --- Inject frontmatter (quality provenance marker) ---
        if not md_content.lstrip().startswith("---"):
            fm_lines = [
                "---",
                "auto_generated: true",
                "generated_at: \"%s\"" % _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_url: \"%s\"" % candidate.get("url", "").replace('"', '\\"'),
                "signal_type: \"%s\"" % candidate.get("signal_type", "").replace('"', '\\"'),
                "---",
                "",
            ]
            md_content = "\n".join(fm_lines) + md_content

        # --- Sanitize LaTeX (safety net) ---
        md_content, latex_fixes = _sanitize_latex(md_content)

        # --- Extract canonical URL from article header ---
        article_url = _extract_article_url(md_content)

        # --- Quality gate (before GitHub push) ---
        qg_passed, qg_issues = _quality_gate(md_content)
        if not qg_passed:
            results.append({
                "slug": slug,
                "title": candidate.get("title", ""),
                "ok": False,
                "skipped": True,
                "reason": "quality_gate_failed",
                "quality_issues": qg_issues,
            })
            continue  # try next candidate

        # --- Update memory FIRST ---
        if not args.dry_run:
            _merge_deep_dive_articles(day, candidate,
                                      "%s/%s.md" % (
                                          candidate.get("target_dir", "memory/blog/archives/deep-dive"),
                                          candidate.get("slug", "")),
                                      "", article_url=article_url)

        # --- Push to GitHub ---
        gh = _push_article_to_github(candidate, md_content,
                                     dry_run=args.dry_run)
        github_path = gh.get("path", "")
        html_url = gh.get("html_url", "")

        # --- Update memory with real html_url + article_url ---
        if not args.dry_run and gh.get("ok") and html_url:
            _merge_deep_dive_articles(day, candidate, github_path, html_url,
                                      article_url=article_url)

        # --- Telegram ---
        tg = {"ok": None}
        title = candidate.get("title", "Untitled")
        # Extract summary + first trap from article for TG hook
        _summary = ""
        _trap = ""
        try:
            with open(article_path, "r", encoding="utf-8") as _af:
                _art = _af.read()
            _summary = _extract_summary(_art)
            _trap = _extract_trap(_art)
        except Exception:
            pass

        if gh.get("ok") and html_url:
            _hook = ("\n\U0001f4a1 %s" % _summary) if _summary else ""
            _trap_line = ("\n\u2620\ufe0f \u9677\u9631: %s" % _trap) if _trap else ""
            tg_text = ("\U0001f50d AI Deep Dive | %s\n\n"
                       "\U0001f4c4 %s%s%s\n\n"
                       "\U0001f517 %s" % (day, title, _hook, _trap_line, html_url))
        elif gh.get("ok"):
            _hook = ("\n\U0001f4a1 %s" % _summary) if _summary else ""
            tg_text = ("\U0001f50d AI Deep Dive | %s\n\n"
                       "\U0001f4c4 %s%s\n"
                       "(GitHub URL not available)" % (day, title, _hook))
        else:
            tg_text = ("\u26a0\ufe0f AI Deep Dive | %s\n\n"
                       "GitHub push failed for: %s\n"
                       "Error: %s" % (day, title,
                                      gh.get("error", "unknown")))


        if args.dry_run or args.no_telegram:
            tg = {"ok": True, "skipped": True}
        else:
            rc, out, err = _send_telegram(
                tg_text,
                target=args.target.strip(),
                account=args.account.strip(),
            )
            tg = {"ok": (rc == 0), "rc": rc,
                  "out": (out or "")[:160], "err": (err or "")[:160]}

        results.append({
            "slug": slug,
            "title": title,
            "latex_fixes": latex_fixes,
            "quality_issues": [i for i in qg_issues if i.startswith("warn:")],
            "article_url": article_url or "",
            "github": gh,
            "telegram": tg,
        })

    print(json.dumps({
        "ok": True,
        "date": day,
        "articles_processed": len(results),
        "results": results,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
