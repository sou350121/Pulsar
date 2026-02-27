#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for VLA Weekly Deep Dive.

Flow:
1) prep-vla-weekly.py  -> read 7 days of VLA memory (papers, SOTA, releases, social)
2) call LLM agent       -> generate structured weekly deep-dive article
3) post-vla-weekly.py  -> memory write + Telegram

Print: post script stdout (single JSON line on success/failure)
Exit: non-zero on hard failure
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys
from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-vla-weekly.py"
POST = "/home/admin/clawd/scripts/post-vla-weekly.py"
NODE = "/opt/moltbot/dist/index.js"
WORKDIR = "/home/admin"
TMP_DIR = "/home/admin/clawd/memory/tmp"


# ---------------------------------------------------------------------------
# Exec failure detection (added 2026-02-23)
# Reason: agent turns can complete (ok=True) while exec tools fail silently.
# ---------------------------------------------------------------------------
_EXEC_FAIL_PATTERNS = [
    "FileNotFoundError",
    "No such file or directory",
    "ENOENT",
    "EACCES",
    "Permission denied",
    "Unknown model",
    "ModuleNotFoundError",
    "ImportError:",
    "SyntaxError:",
    "ConnectionRefusedError",
    "Traceback (most recent call last)",
]


def _detect_exec_failure(text):
    for pat in _EXEC_FAIL_PATTERNS:
        if pat in (text or ""):
            return True, pat
    return False, None


def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _run(cmd, timeout=120, label="subprocess"):
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    return run_with_heartbeat(
        cmd=cmd,
        timeout=timeout,
        heartbeat_sec=20,
        label=label,
        cwd=WORKDIR,
        extra_env=env,
    )


def _extract_json_text(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        json.loads(raw)
        return raw
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        try:
            json.loads(m.group(1))
            return m.group(1)
        except Exception:
            pass
    i = raw.find("{")
    j = raw.rfind("}")
    if i != -1 and j != -1 and j > i:
        cand = raw[i: j + 1]
        try:
            json.loads(cand)
            return cand
        except Exception:
            pass
    return None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_llm_message(day, candidates_obj):
    date_range = candidates_obj.get("date_range", "past 7 days")

    papers = candidates_obj.get("papers") or []
    sota = candidates_obj.get("sota_changes") or []
    releases = candidates_obj.get("releases") or []
    social = candidates_obj.get("social_signals") or []
    theory = candidates_obj.get("theory_deep_dives") or []

    papers_json = json.dumps(papers[:20], ensure_ascii=False, indent=1)
    sota_json = json.dumps(sota[:10], ensure_ascii=False, indent=1)
    releases_json = json.dumps(releases[:10], ensure_ascii=False, indent=1)
    social_json = json.dumps(social[:15], ensure_ascii=False, indent=1)
    theory_json = json.dumps(theory[:5], ensure_ascii=False, indent=1)

    msg = (
        "你是 VLA/具身智能 Weekly Deep Dive 的文章撰写者。基于我提供的本周候选数据，撰写一篇深度周报文章。\n"
        "⚠️ 禁止 web_search / web_fetch / 任何网络调用。只基于提供的数据生成。\n\n"
        "日期: %s\n"
        "周期: %s\n\n"
        "输出必须是纯 JSON 对象，不要 markdown fence，不要解释。\n\n"
        "JSON schema:\n"
        "{\n"
        '  "date": "%s",\n'
        '  "date_range": "%s",\n'
        '  "tldr": ["bullet1", "bullet2", "bullet3"],\n'
        '  "spotlight": [\n'
        "    {\n"
        '      "title": "论文/项目标题",\n'
        '      "url": "链接",\n'
        '      "what": "这是什么（1-2句）",\n'
        '      "analysis": "深度分析：核心贡献、方法创新、工程落地价值（3-5句）",\n'
        '      "verdict": "一句话结论"\n'
        "    }\n"
        "  ],\n"
        '  "sota_highlights": [\n'
        "    {\n"
        '      "benchmark": "基准名称",\n'
        '      "change": "变化描述",\n'
        '      "significance": "重要性解读（1句）"\n'
        "    }\n"
        "  ],\n"
        '  "release_highlights": [\n'
        "    {\n"
        '      "name": "项目名",\n'
        '      "url": "链接",\n'
        '      "summary": "发布内容（1-2句）"\n'
        "    }\n"
        "  ],\n"
        '  "social_highlights": [\n'
        "    {\n"
        '      "entity": "人/机构",\n'
        '      "event": "事件",\n'
        '      "url": "链接"\n'
        "    }\n"
        "  ],\n"
        '  "next_week_outlook": ["signal_1", "signal_2", "signal_3"],\n'
        '  "telegram_text": "Telegram 发送的摘要文本"\n'
        "}\n\n"
        "撰写要求：\n"
        "- spotlight: 选 1-2 个最重要的论文/项目，深度分析核心贡献\n"
        "- sota_highlights: 从 SOTA 变化中提炼本周排行榜最值得关注的变动\n"
        "- release_highlights: 本周重要开源发布（有 GitHub 链接的优先）\n"
        "- social_highlights: 重要人物动态/行业新闻（来自 social intel）\n"
        "- next_week_outlook: 3-5 个下周值得关注的信号\n"
        "- 如果某类候选数据为空，对应字段输出空数组\n"
        "- 语气: 实用主义，像资深 VLA 研究员写给团队的周报\n"
        "- 中文撰写，专有名词（模型名/方法名/英文缩写）保留英文\n\n"
        "telegram_text 格式:\n"
        "🤖 VLA Weekly | %s\n\n"
        "📌 TL;DR\n"
        "（3 个要点）\n\n"
        "🔦 Spotlight\n"
        "（每个: 标题 + 一句话亮点）\n\n"
        "📊 SOTA 变化（如有）\n\n"
        "🚀 本周发布（如有）\n\n"
        "👀 下周关注\n"
        "（outlook 要点）\n\n"
        "候选数据:\n\n"
        "=== VLA Papers (past %s) ===\n%s\n\n"
        "=== SOTA Changes ===\n%s\n\n"
        "=== New Releases ===\n%s\n\n"
        "=== Social Intelligence ===\n%s\n\n"
        "=== Theory Deep Dives Published ===\n%s"
    ) % (day, date_range, day, date_range, date_range,
         date_range, papers_json, sota_json, releases_json,
         social_json, theory_json)
    return msg


def _agent_generate(day, candidates_obj, timeout=120):
    msg = _build_llm_message(day, candidates_obj)
    cmd = [
        "node", NODE, "agent",
        "--agent", "reports",
        "--session-id", "vla-weekly-%s" % day,
        "--message", msg,
        "--json",
        "--timeout", str(timeout),
    ]
    rc, out, err = _run(cmd, timeout=timeout + 30, label="vla-weekly/agent")
    if rc != 0:
        return False, {"error": "agent_cmd_failed", "rc": rc,
                       "stderr": err[:300]}

    # Scan agent output for exec failures (ok=True but tool actually errored)
    _fail, _pat = _detect_exec_failure(out)
    if _fail:
        return False, {"error": "agent_exec_failure_detected",
                       "pattern": _pat, "stdout_head": out[:300]}

    js = _extract_json_text(out)
    if not js:
        return False, {"error": "agent_json_not_found",
                       "stdout": out[:400]}
    try:
        obj = json.loads(js)
    except Exception as e:
        return False, {"error": "agent_json_parse_failed",
                       "detail": str(e)}

    text = ""
    try:
        text = (
            (((obj.get("result") or {}).get("payloads") or [{}])[0]
             .get("text")) or ""
        )
    except Exception:
        text = ""
    if not text.strip():
        return False, {"error": "agent_empty_text"}

    model_json_txt = _extract_json_text(text)
    if not model_json_txt:
        return False, {"error": "model_output_not_json",
                       "text_head": text[:300]}
    try:
        payload = json.loads(model_json_txt)
    except Exception as e:
        return False, {"error": "model_json_parse_failed",
                       "detail": str(e)}

    if not isinstance(payload, dict):
        return False, {"error": "model_payload_not_dict"}
    payload["date"] = day
    return True, payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="original")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)
    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(
        TMP_DIR, "vla-weekly-candidates-%s-%s.json" % (day, run_id))
    llm_out_path = os.path.join(
        TMP_DIR, "vla-weekly-llm-output-%s-%s.json" % (day, run_id))

    # Phase 1: Prep (read memory, build candidates)
    print("[progress] Phase 1/3: Prep (read VLA memory, build candidates) (~30s)...", flush=True)
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path]
    rc, out, err = _run(prep_cmd, timeout=60, label="vla-weekly/prep")
    print("[progress] Phase 1/3: step finished (rc=%d)." % rc, flush=True)
    if rc != 0:
        print(json.dumps(
            {"ok": False, "error": "prep_failed", "rc": rc,
             "stderr": err[:300]},
            ensure_ascii=False))
        return 1
    if not os.path.exists(cands_path):
        print(json.dumps(
            {"ok": False, "error": "candidates_missing",
             "path": cands_path},
            ensure_ascii=False))
        return 1

    candidates_obj = _load_json(cands_path)

    # Phase 2: LLM generation (weekly article writing)
    print("[progress] Phase 2/3: LLM generation (weekly article) (~120s)...", flush=True)
    ok, data = _agent_generate(day, candidates_obj, timeout=120)
    print("[progress] Phase 2/3: step finished (ok=%s)." % ok, flush=True)
    if not ok:
        print(json.dumps(
            {"ok": False, "error": "agent_generate_failed",
             "detail": data},
            ensure_ascii=False))
        return 1

    with open(llm_out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Phase 3: Post (memory + Telegram)
    post_cmd = [
        "python3", POST, "--date", day,
        "--input", llm_out_path,
        "--target", args.target,
    ]
    if args.account:
        post_cmd.extend(["--account", args.account])
    if args.no_telegram:
        post_cmd.append("--no-telegram")
    if args.dry_run:
        post_cmd.append("--dry-run")
    print("[progress] Phase 3/3: Post (memory + Telegram) (~30s)...", flush=True)
    rc, out, err = _run(post_cmd, timeout=60, label="vla-weekly/post")
    print("[progress] Phase 3/3: step finished (rc=%d)." % rc, flush=True)
    if out.strip():
        print(out.strip())
    else:
        print(json.dumps(
            {"ok": False, "error": "post_no_stdout", "rc": rc,
             "stderr": err[:260]},
            ensure_ascii=False))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
