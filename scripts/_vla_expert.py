#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared VLA expert LLM utilities.

Used by:
  - rate-vla-daily.py   (paper rating + cross-pipeline routing)
  - prep-vla-theory.py  (candidate expert scoring)
  - post-vla-theory.py  (article semantic gate)

Python 3.6+ (no external deps)
"""

from __future__ import print_function

import json
import os
import re
import sys
import time

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    Request = urlopen = HTTPError = None

AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
HANDBOOK_BASE = "https://raw.githubusercontent.com/sou350121/VLA-Handbook/main"
THEORY_ARTICLES_PATH = "/home/admin/clawd/memory/vla-theory-articles.json"
DEFAULT_CACHE_DIR = "/home/admin/clawd/memory/tmp"

# Use qwen3.5-plus for all expert tasks
EXPERT_MODEL = "qwen3.5-plus"

_HANDBOOK_CACHE = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_json_safe(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── API key ───────────────────────────────────────────────────────────────────

def get_api_key():
    """Return DashScope API key from env var or auth-profiles.json."""
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    cfg = _read_json_safe(AUTH_PATH, {})
    for k in ("alibaba-cloud:default", "alibaba-cloud"):
        v = (cfg.get("profiles", {}).get(k, {}) or {}).get("key", "").strip()
        if v:
            return v
    return ""


# ── LLM call ─────────────────────────────────────────────────────────────────

def call_qwen(system_prompt, user_prompt, model=None, timeout=150, temperature=0.1):
    """
    Call DashScope chat completions (OpenAI-compatible endpoint).

    Returns:
        {"ok": bool, "content": str, "error": str, "usage": dict}
    """
    if not (Request and urlopen):
        return {"ok": False, "error": "urllib_unavailable", "content": ""}
    api_key = get_api_key()
    if not api_key:
        return {"ok": False, "error": "no_api_key", "content": ""}
    if model is None:
        model = EXPERT_MODEL

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 4096,
    }
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(3):
        req = Request(DASHSCOPE_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Authorization", "Bearer " + api_key)
        try:
            resp = urlopen(req, timeout=timeout)
            raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            content = (
                obj.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {
                "ok": True,
                "content": content,
                "usage": obj.get("usage", {}),
                "error": "",
            }
        except HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(6 * (attempt + 1))
                continue
            return {
                "ok": False,
                "error": "http_%d" % e.code,
                "detail": err_body,
                "content": "",
            }
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return {"ok": False, "error": str(e)[:200], "content": ""}
    return {"ok": False, "error": "max_retries", "content": ""}


# ── VLA-Handbook context ──────────────────────────────────────────────────────

def fetch_handbook_context(day, cache_dir=None):
    """
    Fetch VLA-Handbook key files from GitHub and build a compact context string.
    Cached to disk per day to avoid repeated network calls.

    Returns: str — ready to inject into LLM system prompt.
    """
    global _HANDBOOK_CACHE
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    if day in _HANDBOOK_CACHE:
        return _HANDBOOK_CACHE[day]

    cache_path = os.path.join(cache_dir, "vla-handbook-ctx-%s.txt" % day)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ctx = f.read()
            _HANDBOOK_CACHE[day] = ctx
            return ctx
        except Exception:
            pass

    parts = []

    def _fetch_url(path, timeout=20):
        try:
            resp = urlopen("%s/%s" % (HANDBOOK_BASE, path), timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    # 1. paper_index.md — already-tracked papers (title dedup + overlap detection)
    pi = _fetch_url("theory/paper_index.md")
    if pi:
        titles = []
        for line in pi.splitlines():
            m = re.match(r"\|\s*([^|]{10,120})\s*\|\s*\[", line)
            if m:
                t = m.group(1).strip()
                if t and not t.lower().startswith(
                    ("论文", "paper", "---", "===", "title", "名称")
                ):
                    titles.append(t)
        parts.append(
            "### 已追踪论文（paper_index.md，共 %d 篇）\n"
            "（与这些论文高度重叠 → 降一级；填补未覆盖方向 → 升一级）\n"
            "%s" % (
                len(titles),
                "\n".join("- " + t[:90] for t in titles[:120]),
            )
        )

    # 2. theory/README.md — research directions already covered
    readme = _fetch_url("theory/README.md")
    if readme:
        sections = [
            line.lstrip("#").strip()
            for line in readme.splitlines()
            if (line.startswith("## ") or line.startswith("### "))
            and len(line.lstrip("#").strip()) > 2
        ]
        parts.append(
            "### 已覆盖研究方向（theory/README.md）\n"
            "%s" % "\n".join("- " + s for s in sections[:40])
        )

    # 3. benchmark_tracker.md — current SOTA baseline for upgrade/downgrade
    bt = _fetch_url("theory/benchmark_tracker.md")
    if bt:
        parts.append(
            "### Benchmark SOTA 基准线（benchmark_tracker.md）\n"
            "（超越这些基准 → 强烈考虑 ⚡）\n"
            "%s" % bt[:1000]
        )

    ctx = (
        "\n\n".join(parts)
        if parts
        else "（VLA-Handbook 获取失败，按通用标准评级）"
    )

    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(ctx)
    except Exception:
        pass

    _HANDBOOK_CACHE[day] = ctx
    return ctx


# ── Theory article dedup ──────────────────────────────────────────────────────

def load_theory_titles(path=None):
    """Return set of lowercase titles already published in vla-theory-articles.json."""
    if path is None:
        path = THEORY_ARTICLES_PATH
    data = _read_json_safe(path, {"theory_articles": []})
    return set(
        (a.get("title") or "").strip().lower()
        for a in (data.get("theory_articles") or [])
        if isinstance(a, dict)
    )
