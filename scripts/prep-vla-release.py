#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLA Release Tracker - Phase 1: Deterministic candidate extraction.

Layer 1 (implemented):
- Query GitHub "latest release" for a curated repo list
- Compare against memory/vla-release-tracker.json -> github-last-seen
- Emit new release items (if any) + updated github_last_seen

Layer 2 (web search) is intentionally skipped here to keep the job deterministic
and robust in restricted environments. This script must never fail the pipeline
just because a subset of repos cannot be fetched.

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except Exception:  # pragma: no cover
    Request = urlopen = HTTPError = URLError = None


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = os.path.join(MEM_DIR, "tmp")
TRACKER_PATH = os.path.join(MEM_DIR, "vla-release-tracker.json")


DEFAULT_REPOS = [
    "google-deepmind/mujoco",
    "haosulab/SAPIEN",
    "Genesis-Embodied-AI/Genesis",
    "huggingface/lerobot",
    "ARISE-Initiative/robosuite",
    "StanfordVL/OmniGibson",
    "haosulab/ManiSkill",
    "octo-models/octo",
    "facebookresearch/habitat-lab",
    "allenai/ai2thor",
]

# Repo -> (source, type)
REPO_META = {
    "google-deepmind/mujoco": ("MuJoCo", "sim"),
    "haosulab/SAPIEN": ("SAPIEN", "sim"),
    "Genesis-Embodied-AI/Genesis": ("Genesis", "sim"),
    "huggingface/lerobot": ("LeRobot", "toolchain"),
    "ARISE-Initiative/robosuite": ("robosuite", "sim"),
    "StanfordVL/OmniGibson": ("OmniGibson", "sim"),
    "haosulab/ManiSkill": ("ManiSkill", "sim"),
    "octo-models/octo": ("Octo", "model"),
    "facebookresearch/habitat-lab": ("Habitat", "sim"),
    "allenai/ai2thor": ("AI2-THOR", "sim"),
}


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
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _load_last_seen():
    obj = _read_json(TRACKER_PATH, {})
    m = obj.get("github-last-seen") if isinstance(obj, dict) else None
    if isinstance(m, dict) and m:
        return m
    # Backward compat: some variants used underscore keys
    m = obj.get("github_last_seen") if isinstance(obj, dict) else None
    return m if isinstance(m, dict) else {}


def _pick_token():
    # Best-effort token loading for higher GitHub rate limits. Do not print it.
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    # Common dotenv paths
    for p in ("/home/admin/.clawdbot/.env", "/home/admin/.moltbot/.env"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("GITHUB_TOKEN="):
                        return s.split("=", 1)[1].strip()
                    if s.startswith("GH_TOKEN="):
                        return s.split("=", 1)[1].strip()
        except Exception:
            continue
    return ""


def _gh_get_latest_release(repo, token=""):
    if not Request or not urlopen:
        return None, "urllib_unavailable"
    url = "https://api.github.com/repos/%s/releases/latest" % repo
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "clawd-vla-release-tracker",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, timeout=20)
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), ""
    except HTTPError as e:
        code = getattr(e, "code", 0)
        return None, "http_%s" % code
    except URLError as e:
        return None, "url_error"
    except Exception as e:
        return None, str(e)[:120]


def _clean_detail(body):
    s = (body or "").strip()
    if not s:
        return ""
    s = re.sub(r"\r", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = s.replace("\n", " ").strip()
    if len(s) > 260:
        s = s[:257].rstrip() + "..."
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--out", default="", help="Output path")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    os.makedirs(TMP_DIR, exist_ok=True)
    out = args.out.strip() or os.path.join(TMP_DIR, "vla-release-candidates-%s.json" % day)

    last_seen = _load_last_seen()
    repos = sorted(set(list(last_seen.keys()) + DEFAULT_REPOS))

    token = _pick_token()

    items = []
    new_last_seen = dict(last_seen) if isinstance(last_seen, dict) else {}
    ok_count = 0
    err_count = 0

    for repo in repos:
        meta = new_last_seen.get(repo) if isinstance(new_last_seen.get(repo), dict) else {}
        prev_tag = (meta.get("tag") or "").strip()

        data, err = _gh_get_latest_release(repo, token=token)
        if err:
            err_count += 1
            # still record that we tried today
            new_last_seen[repo] = {"tag": prev_tag, "checked_at": day}
            continue
        if not isinstance(data, dict):
            err_count += 1
            new_last_seen[repo] = {"tag": prev_tag, "checked_at": day}
            continue

        ok_count += 1

        tag = (data.get("tag_name") or data.get("name") or "").strip()
        html_url = (data.get("html_url") or "").strip()
        published_at = (data.get("published_at") or "").strip()
        body = (data.get("body") or "")

        if not tag:
            # Some repos may have no formal releases.
            new_last_seen[repo] = {"tag": prev_tag, "checked_at": day}
            continue

        new_last_seen[repo] = {"tag": tag, "checked_at": day}

        if prev_tag and (tag == prev_tag):
            continue

        source, typ = REPO_META.get(repo, (repo.split("/", 1)[-1], "toolchain"))
        item_date = day
        if published_at:
            # Use YYYY-MM-DD prefix when available
            item_date = (published_at[:10] or day).strip()

        items.append({
            "source": source,
            "type": typ,
            "event": "%s released" % tag,
            "detail": _clean_detail(body),
            "relevance": "",
            "url": html_url or ("https://github.com/%s/releases/tag/%s" % (repo, tag)),
            "date": item_date,
            "layer": "github_release",
            "repo": repo,
        })

    # deterministic ordering (latest first)
    items = [x for x in items if isinstance(x, dict)]
    items.sort(key=lambda x: (x.get("date") or "", x.get("repo") or "", x.get("event") or ""))
    items = items[-30:]

    out_obj = {
        "ok": True,
        "date": day,
        "items": items,
        "github_last_seen": new_last_seen,
        "counts": {
            "repos_total": len(repos),
            "repos_ok": ok_count,
            "repos_error": err_count,
            "new_releases": len(items),
            "layer2_web_search": 0,
        },
    }
    _write_json(out, out_obj)
    print(json.dumps({"ok": True, "date": day, "out": out, "new_releases": len(items)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

