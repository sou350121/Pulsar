#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for VLA Social Intelligence.

Flow:
1) prep-vla-social.py   -> Perplexity search + exclusion -> candidates JSON
2) call LLM agent        -> generate structured signals + telegram text
3) post-vla-social.py   -> memory write + telegram delivery

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


PREP = "/home/admin/clawd/scripts/prep-vla-social.py"
POST = "/home/admin/clawd/scripts/post-vla-social.py"
NODE = "/opt/moltbot/dist/index.js"
WORKDIR = "/home/admin"
TMP_DIR = "/home/admin/clawd/memory/tmp"



# ---------------------------------------------------------------------------
# Exec failure detection (2026-02-23)
# Reason: agent turns can complete (ok=True) while exec tools fail silently.
# Scanning the model's text output for error patterns catches this.
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
    """Return (True, pattern) if text contains exec failure indicators."""
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
        cand = raw[i : j + 1]
        try:
            json.loads(cand)
            return cand
        except Exception:
            pass
    return None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# LLM prompt builder
# ------------------------------------------------------------------

def _build_llm_message(day, candidates_obj):
    results = candidates_obj.get("search_results") or []

    parts = []
    for idx, r in enumerate(results):
        if not r.get("ok"):
            continue
        if r.get("filtered_reason"):
            continue  # skip "no recent signal" results
        content_text = (r.get("content") or "").strip()
        urls = r.get("urls") or []
        search_name = r.get("search_name", "?")
        search_type = r.get("search_type", "?")
        if content_text:
            parts.append(
                "--- Search %d [%s] (%s) ---\n%s"
                % (idx + 1, search_type, search_name, content_text)
            )
            if urls:
                parts.append("Links: " + " | ".join(urls[:5]))

    context = "\n\n".join(parts) if parts else "(No recent signals found from any search.)"

    msg = (
        "你是 VLA/具身智能社交情报分析师，有深厚研究背景（了解物理智能/机器人学主要实验室、学者和公司动态）。"
        "基于搜索结果生成结构化社交情报报告。\n"
        "⚠️ 禁止编造 URL。URL 必须从搜索结果中提取（搜索结果已含真实来源链接）。\n"
        "除 URL 核对外，所有推断仅基于搜索结果数据，禁止 web_fetch。\n\n"
        "今天日期: %s\n\n"
        "信号质量标准：\n"
        "- 一级信号：顶级实验室（Physical Intelligence/Google Deepmind Robotics/CMU RI/MIT CSAIL/Stanford HAI）"
        "核心成员的重大动态（发布/招聘/关键合作/融资）；或标志性开源项目的里程碑发布\n"
        "- 二级信号：有具体数据/链接支撑的公司/团队动态；有实际技术内容的行业新闻\n"
        "- 三级信号：趋势性参考，无法独立核实\n"
        "\n"
        "关键规则：\n"
        "- 只收录 5 天内（含今天）的事件；超过 5 天的事件直接丢弃，不得出现在 signals 中\n"
        "- 72 小时内的事件优先；3-5 天内的事件须标注日期（如：2 月 23 日）且须有明确一手来源链接\n"
        "- 不要报告人物简介、实验室介绍、项目概述等 evergreen 内容\n"
        "- 不要报告论文（arXiv/paper），那是 VLA Daily 的职责\n"
        "- 如实报告：若无真正近期信号，说明「无重大信号」\n"
        "- 不要用确定语气叙述无法从搜索结果核实的信息（用「疑似/据报道」）\n"
        "\n"
        "输出必须是纯 JSON 对象，不要 markdown fence，不要解释。\n\n"
        "JSON schema:\n"
        "{\n"
        '  "date": "%s",\n'
        '  "telegram_text": "完整 Telegram 正文",\n'
        '  "signals": [\n'
        "    {\n"
        '      "type": "人物动态|开源项目|社區討论|招聘|融資|会議|benchmark",\n'
        '      "source": "来源平台/媒体",\n'
        '      "person_or_entity": "实体（人名/机构名）",\n'
        '      "summary": "具体事件（含时间/数值/来源，不是简介）",\n'
        '      "url": "一手来源链接（不确定则留空，不要编造）",\n'
        '      "signal_level": "一級|二級|三級",\n'
        '      "field_implication": "对 VLA 研究/工程方向的含义（1句，如无则留空）"\n'
        "    }\n"
        "  ],\n"
        '  "trend_observation": "跨信号的趋势观察（1-2句，只基于今日数据，无数据时留空）"\n'
        "}\n\n"
        "telegram_text 格式:\n"
        "📡 VLA 社交情报 | %s\n\n"
        "🔴 高價值信號（一級，如有）\n"
        "- [类型] 实体：具体做了什麼 + 时间 + 为什麼重要\n"
        "  一手鏈接\n\n"
        "📊 动态摘要（二級，3-5 條）\n"
        "- 实体：做了什麼 + 含義\n"
        "  鏈接\n\n"
        "🔭 趨勢观察（1-2 句，有数据支撐）\n\n"
        "规则:\n"
        "- 每条 signal 的 summary 必须包含具体事件+大致时间，不是简介\n"
        "- 一级信号必须说明「为什么对 VLA 领域重要」\n"
        "- 若无值得报告的信号: telegram_text = '📡 今日 VLA 社交面無重大信號'，signals = []\n"
        "- trend_observation 只在有 2+ 条信号时才有内容，单一信号不作趋势判断\n\n"
        "搜索结果原文:\n\n%s"
    ) % (day, day, day, context)
    return msg


# ------------------------------------------------------------------
# LLM call
# ------------------------------------------------------------------

def _agent_generate(day, candidates_obj, timeout=300):
    msg = _build_llm_message(day, candidates_obj)
    cmd = [
        "node", NODE, "agent",
        "--agent", "reports",
        "--session-id", "vla-social-%s" % day,
        "--message", msg,
        "--json",
        "--timeout", str(timeout),
    ]
    rc, out, err = _run(cmd, timeout=timeout + 30, label="vla-social/agent")
    if rc != 0:
        return False, {"error": "agent_cmd_failed", "rc": rc,
                       "stderr": err[:300]}

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

    if text:
        _exec_fail, _exec_pat = _detect_exec_failure(text)
        if _exec_fail:
            return False, {"error": "agent_exec_failure_detected",
                           "pattern": _exec_pat, "text_head": text[:300]}
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


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="original")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)
    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(
        TMP_DIR, "vla-social-candidates-%s-%s.json" % (day, run_id))
    llm_out_path = os.path.join(
        TMP_DIR, "vla-social-llm-output-%s-%s.json" % (day, run_id))

    # Phase 1: Prep
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path, "--max-queries", "2"]
    if args.no_web:
        prep_cmd.append("--no-web")
    print("[progress] Phase 1/3: running prep script (~30-60s)...", flush=True)
    rc, out, err = _run(prep_cmd, timeout=300, label="vla-social/prep")
    print("[progress] Phase 1/3: prep finished (rc=%d)." % rc, flush=True)
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

    # Phase 2: LLM generation
    print("[progress] Phase 2/3: running LLM agent (~60-90s)...", flush=True)
    ok, data = _agent_generate(day, candidates_obj, timeout=300)
    print("[progress] Phase 2/3: LLM generation finished (ok=%s)." % ok, flush=True)
    if not ok:
        print(json.dumps(
            {"ok": False, "error": "agent_generate_failed",
             "detail": data},
            ensure_ascii=False))
        return 1

    with open(llm_out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Phase 3: Post
    post_cmd = [
        "python3", POST, "--date", day,
        "--input", llm_out_path,
        "--target", args.target,
        "--account", args.account,
    ]
    if args.no_telegram:
        post_cmd.append("--no-telegram")
    if args.dry_run:
        post_cmd.append("--dry-run")
    print("[progress] Phase 3/3: running post script (~30-60s)...", flush=True)
    rc, out, err = _run(post_cmd, timeout=60, label="vla-social/post")
    print("[progress] Phase 3/3: post finished (rc=%d)." % rc, flush=True)
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
