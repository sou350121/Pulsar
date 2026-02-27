#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Collect last-14-days changes from VLA-Handbook repo via GitHub API and output
compact "reading materials" JSON for the biweekly reasoning task.

Python 3.6+ (no external deps).

Security:
- Never prints tokens.
- Reads token from env var (token_env in github-config.json) or from
  /home/admin/.clawdbot/.env fallback.

Limits:
- Commits: <= 50 (latest first)
- Fetch: commit list + per-commit details JSON (no raw diff)
"""

from __future__ import print_function

import argparse
import base64
import datetime as _dt
import json
import os
import re
import sys

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
except Exception:  # pragma: no cover
    Request = None
    urlopen = None
    HTTPError = Exception
    URLError = Exception
    quote = None


DEFAULT_GITHUB_CONFIG = "/home/admin/clawd/memory/github-config.json"
DEFAULT_ENV_PATHS = [
    "/home/admin/.clawdbot/.env",
    "/home/admin/.moltbot/.env",
]


def _read_text(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_dotenv(paths):
    env = {}
    for p in paths:
        if not p or (not os.path.exists(p)):
            continue
        try:
            raw = _read_text(p)
        except Exception:
            continue
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k:
                continue
            env[k] = v
    return env


def _get_token(token_env):
    token = os.getenv(token_env) if token_env else None
    if token:
        return token.strip()
    dotenv = _load_dotenv(DEFAULT_ENV_PATHS)
    token = dotenv.get(token_env) if token_env else None
    if token:
        return token.strip()
    return None


def _iso_z(dt):
    # Ensure UTC Z-ISO
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    dt = dt.astimezone(_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _gh_url(api_base, repo, path):
    p = quote(path, safe="/")
    return api_base.rstrip("/") + "/repos/" + repo + "/" + p.lstrip("/")


def _http_json(method, url, token, accept=None):
    headers = {
        "User-Agent": "moltbot-gh-handbook-changes-collect",
        "Accept": accept or "application/vnd.github+json",
    }
    req = Request(url, data=None, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    if token:
        req.add_header("Authorization", "token " + token)

    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = getattr(resp, "status", None) or resp.getcode()
            if raw.strip():
                try:
                    return code, json.loads(raw)
                except Exception:
                    return code, {"_raw": raw}
            return code, {}
    except HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        try:
            obj = json.loads(raw) if raw.strip() else {}
        except Exception:
            obj = {"_raw": raw} if raw else {}
        return int(getattr(e, "code", 0) or 0), obj
    except URLError as e:
        return 0, {"error": "urlerror", "detail": str(e)}


def _today_shanghai():
    # Compute YYYY-MM-DD in Asia/Shanghai (UTC+8) without tz database dependency.
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    sh = _dt.timezone(_dt.timedelta(hours=8))
    return now_utc.astimezone(sh).strftime("%Y-%m-%d")


def _period_range(today_str):
    # start = today-13
    d = _dt.datetime.strptime(today_str, "%Y-%m-%d").date()
    start = d - _dt.timedelta(days=13)
    return start.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")


def _normalize_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _is_moltbot_commit(message, files):
    msg = (message or "").lower()
    # Heuristics: our automated commits often contain these prefixes or paths.
    if "moltbot" in msg or "biweekly report" in msg or "update biweekly readme" in msg:
        return True
    for f in files or []:
        name = (f.get("filename") or "").lower()
        if name.endswith("reports/biweekly/readme.md") or name.startswith("reports/biweekly/"):
            return True
        if name.endswith("theory/paper_index.md") and ("daily papers" in msg or "paper_index" in msg):
            return True
    return False


def _extract_added_table_rows_from_patch(patch):
    """
    Extract newly added markdown table rows from a unified diff patch.
    Returns list of raw row strings (without leading '+').
    """
    if not patch:
        return []
    rows = []
    for line in patch.splitlines():
        if not line.startswith("+"):
            continue
        if line.startswith("+++"):
            continue
        # A markdown table row usually begins with '|'
        s = line[1:]
        if s.strip().startswith("|") and s.count("|") >= 3:
            # skip alignment rows
            if re.match(r"^\|\s*:?-{2,}", s.strip()):
                continue
            rows.append(s.rstrip())
    return rows


def _parse_paper_index_row(row):
    """
    Parse row like:
    | Title | [link](url) | 📖 daily 2026-02-10 |
    """
    parts = [p.strip() for p in row.strip().strip("|").split("|")]
    if len(parts) < 3:
        return None
    title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", parts[0]).strip()
    link_cell = parts[1]
    m = re.search(r"\((https?://[^)]+)\)", link_cell)
    url = m.group(1).strip() if m else ""
    note = parts[2].strip()
    tags = []
    for t in ("📖", "🔧", "⚡", "✍️"):
        if t in note or t in parts[0] or t in parts[2]:
            tags.append(t)
    return {
        "title": title,
        "url": url,
        "note": note,
        "tags": tags,
        "raw": row,
    }


def _extract_markdown_headings_from_patch(patch, max_items=30):
    if not patch:
        return []
    out = []
    for line in patch.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        s = line[1:].strip()
        if s.startswith("#"):
            out.append(_normalize_ws(s))
        if len(out) >= max_items:
            break
    return out


def _extract_added_bullets_from_patch(patch, max_items=50):
    if not patch:
        return []
    out = []
    for line in patch.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        s = line[1:].rstrip()
        if s.lstrip().startswith(("-", "*")) and len(s.strip()) > 2:
            out.append(_normalize_ws(s))
        if len(out) >= max_items:
            break
    return out


def _contains_manual_marker(patch):
    return bool(patch and ("✍️" in patch))


def _first_line(msg, limit=160):
    s = (msg or "").strip().splitlines()[0] if (msg or "").strip() else ""
    s = _normalize_ws(s)
    return (s[:limit] + "…") if len(s) > limit else s


def _topic_from_path(path):
    """
    Best-effort topic extraction from file path.
    Examples:
      theory/frontier/foo.md -> frontier
      deployment/perception/bar.md -> perception
    """
    p = (path or "").strip().strip("/")
    parts = p.split("/")
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github-config", default=DEFAULT_GITHUB_CONFIG)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--per-page", type=int, default=50)
    ap.add_argument("--out", default=None, help="Write JSON to this path (optional)")
    ap.add_argument("--max-commits", type=int, default=50)
    args = ap.parse_args()

    # Determine period
    today = _today_shanghai()
    start, end = _period_range(today)
    since_dt = (_dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc) -
                _dt.timedelta(days=max(1, int(args.days))))
    since_iso = _iso_z(since_dt)

    # Load github config
    try:
        cfg = _read_json(args.github_config)
    except Exception as e:
        obj = {"ok": False, "error": "github_config_read_failed", "detail": str(e)}
        print(json.dumps(obj, ensure_ascii=False))
        return 0

    repo = cfg.get("repo")
    api_base = cfg.get("api_base") or "https://api.github.com"
    token_env = cfg.get("token_env") or "GITHUB_TOKEN"
    if not repo:
        print(json.dumps({"ok": False, "error": "missing_repo_in_config"}, ensure_ascii=False))
        return 0

    token = _get_token(token_env)
    if not token:
        print(json.dumps({"ok": False, "error": "missing_token", "token_env": token_env}, ensure_ascii=False))
        return 0

    commits_url = api_base.rstrip("/") + "/repos/" + repo + "/commits?since=" + quote(since_iso, safe="") + "&per_page=" + str(int(args.per_page))
    code, commits_obj = _http_json("GET", commits_url, token)
    if code != 200 or not isinstance(commits_obj, list):
        print(json.dumps({"ok": False, "error": "commits_list_failed", "status": code, "details": commits_obj}, ensure_ascii=False))
        return 0

    commits = commits_obj[: int(args.max_commits)]

    out = {
        "ok": True,
        "repo": repo,
        "period": "{s} to {e}".format(s=start, e=end),
        "since_iso": since_iso,
        "commits_analyzed": 0,
        "moltbot_commits": 0,
        "manual_commits": 0,
        "papers_added": 0,
        "papers_added_moltbot": 0,
        "papers_added_manual": 0,
        "paper_index_additions": [],
        "changed_files": {
            "theory": [],
            "deployment": [],
            "other_md": [],
        },
        "reading_material": [],
        "commit_summaries": [],
        "theory_changed_files_total": 0,
        "theory_changed_files_moltbot": 0,
        "theory_changed_files_manual": 0,
        "topics_suggested": [],
        "manual_topics_suggested": [],
        "manual_markers_found": 0,
        "errors": [],
    }

    seen_files = set()
    theory_files_moltbot = set()
    theory_files_manual = set()
    manual_topics = set()

    for c in commits:
        sha = (c.get("sha") or "").strip()
        if not sha:
            continue
        detail_url = api_base.rstrip("/") + "/repos/" + repo + "/commits/" + sha
        code2, obj2 = _http_json("GET", detail_url, token)
        if code2 != 200 or not isinstance(obj2, dict):
            out["errors"].append({"sha": sha, "error": "commit_detail_failed", "status": code2})
            continue
        out["commits_analyzed"] += 1

        commit_msg = ((obj2.get("commit") or {}).get("message") or "").strip()
        commit_date = ((obj2.get("commit") or {}).get("author") or {}).get("date") or ""
        files = obj2.get("files") or []

        is_moltbot = _is_moltbot_commit(commit_msg, files)
        has_manual = False
        per_commit_paper_rows = []
        per_commit_theory_files = set()
        per_commit_deploy_files = set()
        per_commit_other_md_files = set()
        per_commit_topics = set()

        # Collect file stats + reading material hints
        for f in files:
            fn = (f.get("filename") or "").strip()
            if not fn:
                continue
            if fn in seen_files:
                pass
            else:
                seen_files.add(fn)

            patch = f.get("patch") or ""
            if _contains_manual_marker(patch):
                has_manual = True

            # Track changed files buckets
            if fn.startswith("theory/") and fn.endswith(".md"):
                out["changed_files"]["theory"].append(fn)
                if not fn.endswith("theory/paper_index.md"):
                    per_commit_theory_files.add(fn)
            elif fn.startswith("deployment/") and fn.endswith(".md"):
                out["changed_files"]["deployment"].append(fn)
                per_commit_deploy_files.add(fn)
            elif fn.endswith(".md"):
                out["changed_files"]["other_md"].append(fn)
                per_commit_other_md_files.add(fn)

            # paper_index additions
            if fn.endswith("theory/paper_index.md"):
                rows = _extract_added_table_rows_from_patch(patch)
                for r in rows:
                    parsed = _parse_paper_index_row(r)
                    if parsed:
                        parsed["sha"] = sha[:7]
                        parsed["commit_date"] = commit_date
                        parsed["source"] = "moltbot" if is_moltbot else "manual"
                        out["paper_index_additions"].append(parsed)
                        per_commit_paper_rows.append(parsed)

            # Reading material: headings + bullets (compact)
            headings = _extract_markdown_headings_from_patch(patch, max_items=10)
            bullets = _extract_added_bullets_from_patch(patch, max_items=10)
            if headings or bullets:
                out["reading_material"].append({
                    "file": fn,
                    "headings": headings,
                    "bullets": bullets,
                    "sha": sha[:7],
                    "source": "moltbot" if is_moltbot else "manual",
                })

            # topics (best-effort)
            t = _topic_from_path(fn)
            if t:
                per_commit_topics.add(t)
            for h in headings:
                # strip leading #'s
                hh = re.sub(r"^#+\s*", "", (h or "")).strip()
                if hh:
                    per_commit_topics.add(hh)

        if has_manual:
            out["manual_markers_found"] += 1

        if is_moltbot:
            out["moltbot_commits"] += 1
            for tf in per_commit_theory_files:
                theory_files_moltbot.add(tf)
            out["papers_added_moltbot"] += len(per_commit_paper_rows)
        else:
            out["manual_commits"] += 1
            for tf in per_commit_theory_files:
                theory_files_manual.add(tf)
            out["papers_added_manual"] += len(per_commit_paper_rows)
            for t in per_commit_topics:
                manual_topics.add(t)

        out["commit_summaries"].append({
            "sha": sha[:7],
            "date": commit_date,
            "message": _first_line(commit_msg),
            "source": "moltbot" if is_moltbot else "manual",
            "files_changed": [x.get("filename") for x in (files[:20] if isinstance(files, list) else []) if x.get("filename")],
            "paper_index_rows_added": [
                {"title": r.get("title"), "tags": r.get("tags"), "note": r.get("note")}
                for r in per_commit_paper_rows[:10]
            ],
            "theory_files_changed": sorted(list(per_commit_theory_files))[:30],
            "deployment_files_changed": sorted(list(per_commit_deploy_files))[:30],
            "other_md_files_changed": sorted(list(per_commit_other_md_files))[:30],
            "has_manual_marker": bool(has_manual),
        })

    # Derive papers_added count from paper_index additions (best-effort)
    out["papers_added"] = len(out["paper_index_additions"])
    out["theory_changed_files_total"] = len(set(list(theory_files_moltbot) + list(theory_files_manual)))
    out["theory_changed_files_moltbot"] = len(theory_files_moltbot)
    out["theory_changed_files_manual"] = len(theory_files_manual)

    # De-dup file lists, keep stable order
    for k in ("theory", "deployment", "other_md"):
        lst = out["changed_files"][k]
        seen = set()
        uniq = []
        for x in lst:
            if x in seen:
                continue
            seen.add(x)
            uniq.append(x)
        out["changed_files"][k] = uniq

    # Suggested topics (best-effort)
    # Keep short: prefer manual topics if present
    manual_topics_list = []
    seen_t = set()
    for t in list(manual_topics):
        tt = _normalize_ws(t)
        if not tt or tt in seen_t:
            continue
        seen_t.add(tt)
        manual_topics_list.append(tt)
        if len(manual_topics_list) >= 10:
            break
    out["manual_topics_suggested"] = manual_topics_list
    out["topics_suggested"] = manual_topics_list[:]

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception as e:
            out2 = {"ok": False, "error": "write_failed", "detail": str(e)}
            print(json.dumps(out2, ensure_ascii=False))
            return 0

    # Print compact stdout JSON for agent prompt
    print(json.dumps({
        "ok": True,
        "period": out["period"],
        "commits_analyzed": out["commits_analyzed"],
        "moltbot_commits": out["moltbot_commits"],
        "manual_commits": out["manual_commits"],
        "papers_added": out["papers_added"],
        "papers_added_moltbot": out["papers_added_moltbot"],
        "papers_added_manual": out["papers_added_manual"],
        "theory_changed_files_moltbot": out["theory_changed_files_moltbot"],
        "manual_markers_found": out["manual_markers_found"],
        "manual_topics_suggested": out["manual_topics_suggested"][:8],
        "out": args.out,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

