#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Patch Agent-Playbook blog/README.md to add AI Daily Pick entry.

Idempotent:
- If section already exists, no change.
- Prefer insert after "## 阅读方式" section.
- Fallback append at end.

Python 3.6+ only, no external deps.
"""

from __future__ import print_function

import argparse
import base64
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


DEFAULT_CONFIG = "/home/admin/clawd/memory/github-config-agent-playbook.json"
DEFAULT_ENV_PATHS = [
    "/home/admin/.clawdbot/.env",
    "/home/admin/.moltbot/.env",
]

SECTION_TITLE = "## AI Agent 每日精選（自動歸檔）"
SECTION_BLOCK = (
    "## AI Agent 每日精選（自動歸檔）\n"
    "- 索引：[`memory/blog/archives/ai-daily-pick/README.md`](./archives/ai-daily-pick/README.md)\n"
    "- 每日歸檔：`memory/blog/archives/ai-daily-pick/YYYY-MM-DD.md`\n"
)


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
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
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


def _gh_url(api_base, repo, path, ref=None):
    p = quote(path, safe="/")
    url = api_base.rstrip("/") + "/repos/" + repo + "/contents/" + p
    if ref:
        url += "?ref=" + quote(ref, safe="")
    return url


def _http_json(method, url, token, body_obj=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moltbot-agent-library-readme-patch",
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


def _b64_nolf(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _insert_block(md):
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    if SECTION_TITLE in text:
        return text, False

    # Preferred: insert after "## 阅读方式" section
    m = re.search(r"^##\s+阅读方式\s*$", text, flags=re.M)
    if m:
        after = text[m.end():]
        m2 = re.search(r"^##\s+", after, flags=re.M)
        if m2:
            pos = m.end() + m2.start()
            block = "\n" + SECTION_BLOCK + "\n"
            return text[:pos] + block + text[pos:], True
        # no next heading => append to end
        return text.rstrip() + "\n\n" + SECTION_BLOCK + "\n", True

    # Fallback append
    return text.rstrip() + "\n\n" + SECTION_BLOCK + "\n", True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--readme-path", default="blog/README.md")
    ap.add_argument("--commit-message", default="🤖 add ai daily pick blog entry")
    args = ap.parse_args()

    try:
        cfg = _read_json(args.config)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "config_read_failed", "detail": str(e)}, ensure_ascii=False))
        return 2

    repo = cfg.get("repo")
    api_base = cfg.get("api_base") or "https://api.github.com"
    token_env = cfg.get("token_env") or "GITHUB_TOKEN"
    if not repo:
        print(json.dumps({"ok": False, "error": "missing_repo_in_config"}, ensure_ascii=False))
        return 3

    token = _get_token(token_env)
    if not token:
        print(json.dumps({"ok": False, "error": "missing_token", "token_env": token_env}, ensure_ascii=False))
        return 4

    get_url = _gh_url(api_base, repo, args.readme_path, ref=args.branch)
    code, obj = _http_json("GET", get_url, token, body_obj=None)
    if code != 200 or not isinstance(obj, dict) or not obj.get("content") or not obj.get("sha"):
        print(json.dumps({"ok": False, "error": "readme_get_failed", "status": code, "details": obj}, ensure_ascii=False))
        return 0

    sha = obj.get("sha")
    try:
        readme_md = base64.b64decode(obj.get("content")).decode("utf-8", errors="replace")
    except Exception:
        readme_md = ""

    new_md, changed = _insert_block(readme_md)
    if not changed:
        print(json.dumps({
            "ok": True,
            "updated": False,
            "note": "already_present",
            "url": "https://github.com/{repo}/blob/{branch}/{path}".format(
                repo=repo, branch=args.branch, path=args.readme_path
            ),
        }, ensure_ascii=False))
        return 0

    put_url = _gh_url(api_base, repo, args.readme_path)
    body = {
        "message": args.commit_message,
        "content": _b64_nolf(new_md),
        "sha": sha,
        "branch": args.branch,
    }
    put_code, put_obj = _http_json("PUT", put_url, token, body_obj=body)
    if put_code not in (200, 201):
        print(json.dumps({"ok": False, "error": "readme_put_failed", "status": put_code, "details": put_obj}, ensure_ascii=False))
        return 0

    print(json.dumps({
        "ok": True,
        "updated": True,
        "url": "https://github.com/{repo}/blob/{branch}/{path}".format(
            repo=repo, branch=args.branch, path=args.readme_path
        ),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
