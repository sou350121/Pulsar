#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prep community context for weekly/biweekly reports.

Fetches compact summaries from community field notes in your knowledge-base
repo and the latest GitHub adoption snapshot; writes a tmp file that report
scripts can read.

Configuration via env vars:
  PULSAR_MEMORY_DIR              memory root (default: /home/admin/clawd/memory)
  PULSAR_FIELD_NOTES_REPO        target repo (default: sou350121/VLA-Handbook)
  PULSAR_FIELD_NOTES_PATH_*      override per-key field-notes paths

Output: memory/tmp/community-context-latest.json

Python 3.6+ (no external deps).
"""
from __future__ import print_function

import base64
import glob
import json
import os
import sys

MEM_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR = os.path.join(MEM_DIR, "tmp")
OUT_PATH = os.path.join(TMP_DIR, "community-context-latest.json")
GH_REPO = os.environ.get("PULSAR_FIELD_NOTES_REPO", "sou350121/VLA-Handbook")

def _load_token():
    env_paths = os.environ.get("PULSAR_ENV_PATHS", "/home/admin/.clawdbot/.env:/home/admin/.moltbot/.env").split(":")
    for ep in env_paths:
        try:
            with open(ep) as f:
                for line in f:
                    if line.strip().startswith("GITHUB_TOKEN="):
                        return line.strip().split("=", 1)[1].strip().strip("''""" )
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN", "")

def _gh_fetch(path, token):
    """Fetch file from configured knowledge-base repo."""
    try:
        from urllib.request import Request, urlopen
    except ImportError:
        return ""
    url = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    req = Request(url)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return base64.b64decode(data["content"]).decode()
    except Exception:
        return ""

def _extract_summary(content, max_lines=50):
    """Extract headings + key table rows as compact summary."""
    lines = content.split("
")
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            out.append(s)
        elif s.startswith("|") and not s.startswith("|-"):
            if len(out) < max_lines:
                out.append(s)
    return "
".join(out[:max_lines])

def _latest_adoption():
    """Load latest gh-adoption-*.json."""
    pattern = os.path.join(MEM_DIR, "gh-adoption-*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return {}
    try:
        with open(files[-1]) as f:
            data = json.load(f)
        return {
            "date": data.get("date", ""),
            "adoption_phases": data.get("adoption_phases", []),
            "dfi": data.get("dfi", []),
            "convergence": data.get("convergence", [])[:3],
            "tier1_candidates": data.get("tier1_candidates", [])[:5],
            "synthesis": data.get("synthesis", {}).get("text", ""),
        }
    except Exception:
        return {}

def main():
    token = _load_token()
    if not token:
        print("WARN: no GITHUB_TOKEN", file=sys.stderr)

    result = {"github_adoption": _latest_adoption()}

    files = {
        "xiaohongshu": "deployment/community_field_notes_xiaohongshu.md",
        "english": "deployment/community_field_notes_english.md",
        "github": "deployment/community_field_notes_github.md",
    }

    notes = {}
    for key, path in files.items():
        if not token:
            continue
        content = _gh_fetch(path, token)
        if content:
            notes[key] = _extract_summary(content)
            print("%s: %d chars → %d summary lines" % (key, len(content), notes[key].count("
") + 1))

    result["community_notes"] = notes

    os.makedirs(TMP_DIR, exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("
")
    os.rename(tmp, OUT_PATH)
    print("Written: %s" % OUT_PATH)

if __name__ == "__main__":
    main()
