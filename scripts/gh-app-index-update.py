#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append-only updater for Agent-Playbook `cognition/app_index.md`.

Python 3.6+ (no external deps).
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


def _gh_contents_url(api_base, repo, path, ref=None):
    p = quote(path, safe="/")
    url = api_base.rstrip("/") + "/repos/" + repo + "/contents/" + p
    if ref:
        url += "?ref=" + quote(ref, safe="")
    return url


def _http_json(method, url, token, body_obj=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "moltbot-gh-app-index-update",
    }
    data = None
    if body_obj is not None:
        data = json.dumps(body_obj).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = Request(url, data=data, method=method)
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


def _b64_nolf(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _norm_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    u = u.split("#", 1)[0].split("?", 1)[0]
    m = re.match(r"^(https?://)([^/]+)(/.*)?$", u, flags=re.I)
    if not m:
        return u.rstrip("/")
    scheme = (m.group(1) or "").lower()
    host = (m.group(2) or "").lower()
    path = (m.group(3) or "")
    path = re.sub(r"/{2,}", "/", path).rstrip("/")
    return scheme + host + path


def _importance_emoji(importance):
    imp = (importance or "").strip().lower()
    if imp == "strategic":
        return "⚡"
    if imp == "actionable":
        return "🔧"
    return "📖"


def _category_to_section(category):
    c = (category or "").strip()
    if c == "Agent 框架":
        return "Agent 框架（Frameworks）"
    if c == "UI/UX 工具":
        return "UI/UX 工具（Agent UI / Workflow UI）"
    if c == "RAG 工具链":
        return "RAG 工具链（Vector DB / Retrieval / Indexing）"
    if c == "API 包装器":
        return "API 包装器（Model API / Gateway / SDK）"
    if c == "垂直应用":
        return "垂直应用（Writing / Coding / Data / Sales / Support）"
    if c == "基础设施":
        return "基础设施（Deployment / Observability / Evals / Security）"
    return "其他（Misc）"


def _ensure_table_header_has_direction(lines, start_idx):
    changed = False
    if start_idx < 0 or start_idx + 1 >= len(lines):
        return lines, False
    hdr = lines[start_idx].rstrip("\n")
    if "方向" in hdr:
        return lines, False
    if re.match(r"^\|\s*应用/工具\s*\|\s*开发者\s*\|\s*日期\s*\|\s*标签\s*\|\s*链接\s*\|\s*备注\s*\|\s*$", hdr):
        lines = list(lines)
        lines[start_idx] = "| 应用/工具 | 开发者 | 日期 | 标签 | 链接 | 方向 | 备注 |\n"
        lines[start_idx + 1] = "|---|---:|---:|---|---|---|---|\n"
        changed = True
    return lines, changed


def _append_rows_to_section(md_text, section_title, rows):
    text = (md_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not rows:
        return text, 0, False

    m = re.search(r"^##\s+%s\s*$" % re.escape(section_title), text, flags=re.M)
    if not m:
        return text, 0, False
    after = text[m.end() :]
    mh = re.search(r"^\|\s*应用/工具\s*\|.*\|\s*$", after, flags=re.M)
    if not mh:
        return text, 0, False

    prefix = text[: m.end()]
    full_lines = (prefix + after).splitlines(True)

    hdr_abs = None
    for i, line in enumerate(full_lines):
        if line.strip().startswith("| 应用/工具 |"):
            hdr_abs = i
            break
    if hdr_abs is None:
        return text, 0, False

    new_lines, _ = _ensure_table_header_has_direction(full_lines, hdr_abs)

    i = hdr_abs + 2
    while i < len(new_lines) and new_lines[i].lstrip().startswith("|"):
        i += 1
    insert_at = i

    ins = [r.rstrip() + "\n" for r in rows]
    new_text = "".join(new_lines[:insert_at] + ins + new_lines[insert_at:])
    return new_text, len(rows), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--items-json", required=True, help="items array json path")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--branch", default="")
    ap.add_argument("--path", default="cognition/app_index.md")
    ap.add_argument("--commit-message", default="🤖 update cognition/app_index.md")
    args = ap.parse_args()

    try:
        items = _read_json(args.items_json)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "items_read_failed", "detail": str(e)}, ensure_ascii=False))
        return 0
    if not isinstance(items, list):
        print(json.dumps({"ok": False, "error": "items_not_list"}, ensure_ascii=False))
        return 0

    try:
        cfg = _read_json(args.config)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "config_read_failed", "detail": str(e)}, ensure_ascii=False))
        return 0

    repo = cfg.get("repo")
    api_base = cfg.get("api_base") or "https://api.github.com"
    token_env = cfg.get("token_env") or "GITHUB_TOKEN"
    cfg_branch = (cfg.get("branch") or "").strip() or "main"
    if not repo:
        print(json.dumps({"ok": False, "error": "missing_repo_in_config"}, ensure_ascii=False))
        return 0

    token = _get_token(token_env)
    if not token:
        print(json.dumps({"ok": False, "error": "missing_token", "token_env": token_env}, ensure_ascii=False))
        return 0

    want_branch = (args.branch or "").strip() or cfg_branch
    get_url = _gh_contents_url(api_base, repo, args.path, ref=want_branch)
    code, obj = _http_json("GET", get_url, token)
    used_branch = want_branch
    if code == 404 and want_branch != cfg_branch:
        get_url2 = _gh_contents_url(api_base, repo, args.path, ref=cfg_branch)
        code, obj = _http_json("GET", get_url2, token)
        used_branch = cfg_branch

    if code != 200 or not isinstance(obj, dict) or not obj.get("content") or not obj.get("sha"):
        print(json.dumps({"ok": False, "error": "get_failed", "status": code, "used_branch": used_branch}, ensure_ascii=False))
        return 0

    sha = obj.get("sha")
    try:
        md = base64.b64decode(obj.get("content")).decode("utf-8", errors="replace")
    except Exception:
        md = ""

    existing_urls = set()
    for line in md.splitlines():
        if "http" not in line:
            continue
        for m in re.finditer(r"(https?://[^\\s|)]+)", line):
            existing_urls.add(_norm_url(m.group(1)))

    by_section = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        title = _norm_ws(it.get("title") or it.get("name") or "")
        url = (it.get("url") or "").strip()
        if not title or not url:
            continue
        nu = _norm_url(url)
        if nu and nu in existing_urls:
            continue

        dev = _norm_ws(it.get("developer") or "—")
        tags = it.get("labels") or it.get("tags") or []
        if isinstance(tags, list):
            tag_s = ", ".join([_norm_ws(str(x)) for x in tags if _norm_ws(str(x))])[:80]
        else:
            tag_s = _norm_ws(str(tags))
        direction = _norm_ws(it.get("direction_note_prefix") or "")
        remark = "{emo} daily {d}".format(emo=_importance_emoji(it.get("importance")), d=args.date)
        why = _norm_ws(it.get("why") or "")
        if why:
            remark += " — " + why

        row = "| {t} | {dev} | {d} | {tags} | {url} | {dir} | {remark} |".format(
            t=title,
            dev=dev or "—",
            d=args.date,
            tags=tag_s,
            url=url,
            dir=direction,
            remark=remark,
        )
        sec = _category_to_section(it.get("category"))
        by_section.setdefault(sec, []).append(row)

    added_total = 0
    changed = False
    for sec, rows in by_section.items():
        md2, added, ch = _append_rows_to_section(md, sec, rows)
        md = md2
        added_total += int(added)
        changed = changed or bool(ch)

    if not changed:
        print(json.dumps({"ok": True, "updated": False, "added": 0, "used_branch": used_branch}, ensure_ascii=False))
        return 0

    put_url = _gh_contents_url(api_base, repo, args.path)
    body = {"message": args.commit_message, "content": _b64_nolf(md), "sha": sha, "branch": used_branch}
    put_code, _ = _http_json("PUT", put_url, token, body_obj=body)
    if put_code not in (200, 201):
        print(json.dumps({"ok": False, "error": "put_failed", "status": put_code}, ensure_ascii=False))
        return 0

    print(json.dumps({"ok": True, "updated": True, "added": int(added_total), "used_branch": used_branch}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

