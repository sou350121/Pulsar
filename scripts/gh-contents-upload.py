#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Upload a local Markdown report to GitHub via Contents API (configurable branch),
then update (or create) reports/biweekly/README.md to include a link.

Designed for Python 3.6+ (no external deps).

Security:
- Never prints tokens.
- Reads token from env var (token_env from github-config.json) OR from
  /home/admin/.clawdbot/.env (fallback).
"""

from __future__ import print_function

import argparse
import base64
import datetime as _dt
import json
import os
import random
import re
import sys
import time

try:
    # py3
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
except Exception:  # pragma: no cover
    # should not happen on py3
    Request = None
    urlopen = None
    HTTPError = Exception
    URLError = Exception
    quote = None


DEFAULT_CONFIG_PATH = "/home/admin/clawd/memory/github-config.json"
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


def _get_token(token_env, env_paths):
    token = os.getenv(token_env) if token_env else None
    if token:
        return token.strip()
    dotenv = _load_dotenv(env_paths)
    token = dotenv.get(token_env) if token_env else None
    if token:
        return token.strip()
    return None


def _gh_url(api_base, repo, path, ref=None):
    # path must be URL-escaped but keep slashes
    p = quote(path, safe="/")
    url = api_base.rstrip("/") + "/repos/" + repo + "/contents/" + p
    if ref:
        url += "?ref=" + quote(ref, safe="")
    return url


def _http_json(method, url, token, body_obj=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moltbot-gh-contents-upload",
    }
    data = None
    if body_obj is not None:
        data = json.dumps(body_obj).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
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


def _should_retry(code, obj):
    # Only retry transient transport/service errors.
    if int(code or 0) in (0, 429, 502, 503, 504):
        return True
    return False


def _sleep_backoff(attempt_idx):
    try:
        base = 0.8 * (2 ** int(attempt_idx))
        jitter = random.random() * 0.2
        time.sleep(min(6.0, base + jitter))
    except Exception:
        return


def _http_json_retry(method, url, token, body_obj=None, max_attempts=3):
    last = (0, {"error": "unknown"})
    for i in range(int(max_attempts or 1)):
        code, obj = _http_json(method, url, token, body_obj=body_obj)
        last = (code, obj)
        if _should_retry(code, obj) and i < (max_attempts - 1):
            _sleep_backoff(i)
            continue
        return code, obj
    return last


def _b64_nolf(utf8_text):
    # Contents API expects base64 without newlines
    b = utf8_text.encode("utf-8")
    return base64.b64encode(b).decode("ascii")


def _extract_readme_summary(md_text):
    """
    Try to extract a short one-line summary from the report.
    Preference: first bullet/line under:
    - '## 本期要点' / '## 本期要點'
    - '## 本期信号' / '## 本期信號'
    """
    # Normalize newlines
    text = md_text.replace("\r\n", "\n").replace("\r", "\n")
    m = re.search(r"^##\s+(本期要点|本期要點|本期信号|本期信號)\s*$", text, flags=re.M)
    if m:
        after = text[m.end():]
        # stop at next H2
        parts = re.split(r"^##\s+", after, flags=re.M)
        block = parts[0] if parts else after
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            # bullet or plain
            s = re.sub(r"^[-*]\s+", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            if s:
                return (s[:120] + "…") if len(s) > 120 else s
    # fallback: first non-empty line after title
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            return (s[:120] + "…") if len(s) > 120 else s
    return "Biweekly report"


def _insert_readme_row(readme_md, date_str, filename, summary):
    """
    Insert a row into a markdown table, latest-first.
    If no table exists, create a minimal README with a table.
    """
    row = "| {d} | [本期報告](./{fn}) | {s} |".format(d=date_str, fn=filename, s=summary)

    md = readme_md.replace("\r\n", "\n").replace("\r", "\n")

    lines = md.splitlines()

    # If a row for this date already exists, replace it (and remove duplicates).
    # This prevents multiple rows for the same date (e.g. -v2/-v3).
    date_prefix = "| {d} |".format(d=date_str)
    replaced = False
    changed = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(date_prefix):
            if not replaced:
                if line.strip() == row:
                    new_lines.append(line.rstrip())
                else:
                    new_lines.append(row)
                    changed = True
                replaced = True
            else:
                # Drop duplicate rows for the same date
                changed = True
            continue
        new_lines.append(line)

    if replaced:
        out_md = "\n".join(new_lines).rstrip() + "\n"
        return out_md, changed

    # Find a table header separator line (|---|---|...) or aligned (|:---|:---|)
    sep_idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        # Match separator-looking lines: cells containing only dashes/colons/spaces
        # Handles: |---|---| and |:---|:---| and |:------:|:------:|
        if re.match(r"^\|[-:\s|]{4,}\|$", s) and "-" in s and not any(
            c.isalpha() or c.isdigit() for c in s
        ):
            sep_idx = i
            break

    if sep_idx is not None:
        insert_at = sep_idx + 1
        lines.insert(insert_at, row)
        return "\n".join(lines).rstrip() + "\n", True

    # No table found: create minimal README
    out = []
    out.append("# Biweekly Reports")
    out.append("")
    out.append("| 日期 | 报告 | 摘要 |")
    out.append("|------|------|------|")
    out.append(row)
    out.append("")
    return "\n".join(out), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--report-date", required=True, help="YYYY-MM-DD (for filename)")
    ap.add_argument("--report-local", required=True, help="Local markdown file path")
    ap.add_argument("--report-dir", default="reports/biweekly")
    ap.add_argument("--readme-path", default="reports/biweekly/README.md")
    ap.add_argument("--commit-message", default=None)
    ap.add_argument("--filename", default=None,
                    help="Override output filename (default: {date}.md)")
    args = ap.parse_args()

    cfg = _read_json(args.config)
    repo = cfg.get("repo")
    api_base = cfg.get("api_base") or "https://api.github.com"
    token_env = cfg.get("token_env") or "GITHUB_TOKEN"
    # Branch selection:
    # - If user explicitly passed --branch, respect args.branch.
    # - Otherwise, allow config.branch to override (for repo-specific workflows).
    branch = args.branch
    cfg_branch = (cfg.get("branch") or "").strip() if isinstance(cfg, dict) else ""
    if cfg_branch and ("--branch" not in sys.argv):
        branch = cfg_branch
    if not repo:
        print(json.dumps({"ok": False, "error": "missing_repo_in_config"}))
        return 2

    token = _get_token(token_env, DEFAULT_ENV_PATHS)
    if not token:
        print(json.dumps({"ok": False, "error": "missing_token", "token_env": token_env}))
        return 3

    report_date = args.report_date.strip()
    # basic validation
    try:
        _dt.datetime.strptime(report_date, "%Y-%m-%d")
    except Exception:
        print(json.dumps({"ok": False, "error": "bad_report_date", "value": report_date}))
        return 4

    report_md = _read_text(args.report_local)
    summary = _extract_readme_summary(report_md)

    # Upload report (update in-place if already exists)
    base_name = args.filename if args.filename else (report_date + ".md")
    report_rel_path_base = args.report_dir.strip("/").rstrip("/") + "/" + base_name
    commit_message = args.commit_message or ("📊 biweekly report: " + report_date)

    chosen_path = report_rel_path_base
    chosen_url = "https://github.com/{repo}/blob/{branch}/{path}".format(
        repo=repo, branch=branch, path=report_rel_path_base
    )

    # First, check if file exists to obtain sha for update
    get_url = _gh_url(api_base, repo, report_rel_path_base, ref=branch)
    code, obj = _http_json_retry("GET", get_url, token, body_obj=None)
    existing_sha = None
    if code == 200 and isinstance(obj, dict) and obj.get("sha"):
        existing_sha = obj.get("sha")
    elif code == 404:
        existing_sha = None
    elif code in (401, 403):
        print(json.dumps({"ok": False, "error": "auth_failed", "status": code, "details": obj}))
        return 10
    elif code != 200:
        print(json.dumps({"ok": False, "error": "report_get_failed", "status": code, "details": obj}))
        return 11

    put_url = _gh_url(api_base, repo, report_rel_path_base)
    body = {
        "message": commit_message,
        "content": _b64_nolf(report_md),
        "branch": branch,
    }
    if existing_sha:
        body["sha"] = existing_sha

    code, obj = _http_json_retry("PUT", put_url, token, body_obj=body)
    if code not in (200, 201):
        if code in (401, 403):
            print(json.dumps({"ok": False, "error": "auth_failed", "status": code, "details": obj}))
            return 10
        print(json.dumps({"ok": False, "error": "report_upload_failed", "status": code, "details": obj}))
        return 12

    # Update README
    readme_url = _gh_url(api_base, repo, args.readme_path, ref=branch)
    code, obj = _http_json_retry("GET", readme_url, token, body_obj=None)

    readme_exists = False
    readme_sha = None
    readme_md = ""
    if code == 200 and isinstance(obj, dict) and obj.get("content"):
        readme_exists = True
        readme_sha = obj.get("sha")
        try:
            readme_md = base64.b64decode(obj.get("content")).decode("utf-8", errors="replace")
        except Exception:
            readme_md = ""
    elif code == 404:
        readme_exists = False
        readme_md = ""
    elif code in (401, 403):
        # Report uploaded ok; README failed due to auth -> treat as error but return report info.
        print(json.dumps({
            "ok": True,
            "report": {"path": chosen_path, "url": chosen_url},
            "readme": {"updated": False, "error": "auth_failed", "status": code},
        }))
        return 0
    elif code != 200:
        # Unknown failure; keep report success.
        print(json.dumps({
            "ok": True,
            "report": {"path": chosen_path, "url": chosen_url},
            "readme": {"updated": False, "error": "readme_get_failed", "status": code, "details": obj},
        }))
        return 0

    filename = chosen_path.split("/")[-1]
    new_readme_md, changed = _insert_readme_row(readme_md, report_date, filename, summary)
    if not changed:
        # Already present; no update needed.
        print(json.dumps({
            "ok": True,
            "report": {"path": chosen_path, "url": chosen_url},
            "readme": {"updated": False, "note": "already_present"},
        }))
        return 0

    put_body = {
        "message": "🧾 update biweekly README: " + report_date,
        "content": _b64_nolf(new_readme_md),
        "branch": branch,
    }
    if readme_exists and readme_sha:
        put_body["sha"] = readme_sha

    put_url = _gh_url(api_base, repo, args.readme_path)
    put_code, put_obj = _http_json_retry("PUT", put_url, token, body_obj=put_body)

    if put_code not in (200, 201):
        # Don't fail whole job; return report URL with readme error.
        print(json.dumps({
            "ok": True,
            "report": {"path": chosen_path, "url": chosen_url},
            "readme": {"updated": False, "error": "readme_put_failed", "status": put_code, "details": put_obj},
        }))
        return 0

    readme_blob_url = "https://github.com/{repo}/blob/{branch}/{path}".format(
        repo=repo, branch=branch, path=args.readme_path
    )
    print(json.dumps({
        "ok": True,
        "report": {"path": chosen_path, "url": chosen_url},
        "readme": {"updated": True, "url": readme_blob_url},
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())

