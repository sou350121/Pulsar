#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for AI App Weekly Deep Dive.

Flow:
1) prep-ai-weekly.py   -> read 7 days of AI App memory, build candidates
2) call LLM agent       -> generate structured deep-dive article
3) post-ai-weekly.py   -> memory write + GitHub push + Telegram

Print: post script stdout (single JSON line on success/failure)
Exit: non-zero on hard failure
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import sys
from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-ai-weekly.py"
POST = "/home/admin/clawd/scripts/post-ai-weekly.py"
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
    import re
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
    """Build a high-quality prompt for the LLM to generate an AI App Weekly deep-dive article."""
    date_range = candidates_obj.get("date_range", "past 7 days")

    daily = candidates_obj.get("daily_items") or []
    picks = candidates_obj.get("pick_items") or []
    social = candidates_obj.get("social_signals") or []
    workflow = candidates_obj.get("workflow_items") or []

    daily_json = json.dumps(daily[:20], ensure_ascii=False, indent=1)
    picks_json = json.dumps(picks[:15], ensure_ascii=False, indent=1)
    social_json = json.dumps(social[:15], ensure_ascii=False, indent=1)
    workflow_json = json.dumps(workflow[:15], ensure_ascii=False, indent=1)

    # Quality guidelines for AI Agent domain
    quality_guidelines = (
        "撰写要求（高级 AI 工程师/研究员标准）:\n"
        "角色定位：你是经验丰富的 AI Agent 工程师+研究员，有大规模 LLM 应用部署经验，了解 MCP/agent 框架演进史。\n"
        "\n"
        "spotlight 的 analysis 必须包含 4 个维度：\n"
        "  ① 技术区别（与竞品/前版本的具体差异：接口/性能/架构/使用限制）\n"
        "  ② 量化证据（benchmark 数字、GitHub star 增长、生产案例等可验证数据）\n"
        "  ③ 工程局限（明确不适用的场景，避免过度吹捧）\n"
        "  ④ 行业意义（对 MCP/agent 协议栈/应用层的推进，结合当前发展脉络）\n"
        "\n"
        "信誉规则（必须遵守）：\n"
        "- 对未经验证的数据，用「疑似/据报道/待确认」标注\n"
        "- 不要编造 benchmark 数字或实际部署案例\n"
        "- 如果某工具缺乏实际评测，如实说明「暂无独立评测数据」\n"
        "\n"
        "workflow_patterns 要求：每个模式必须是可操作的具体做法（不是泛泛理念），"
        "包含触发条件、执行步骤、已知效果\n"
        "next_week_outlook 必须是具体信号（如「X 团队的 Y 工具即将发布 v2 beta，关注能否解决 Z 痛点」）\n"
        "语气：有判断力、不客气、像资深 AI 工程师写给同行的周报，敢于说哪些工具不值得用\n"
        "中文撰写，专有名词保留英文\n"
    )

    msg = (
        "你是资深 AI Agent 工程师+研究员，负责撰写 AI Agent Weekly Deep Dive 周报。"
        "基于我提供的本周候选数据，生成高质量深度分析。\n"
        "⚠️ 禁止 web_search / web_fetch / 任何网络调用。只基于提供的数据生成。\n\n"
        "日期: %s\n"
        "周期: %s\n\n"
        "输出必须是纯 JSON 对象，不要 markdown fence，不要解释。\n\n"
        "JSON schema:\n"
        "{\n"
        '  "date": "%s",\n'
        '  "date_range": "%s",\n'
        '  "tldr": ["具体技术要点1", "具体技术要点2", "具体技术要点3"],\n'
        '  "spotlight": [\n'
        "    {\n"
        '      "name": "工具/框架名称",\n'
        '      "url": "链接",\n'
        '      "what": "定位（1-2句：解决什么问题、与谁竞争）",\n'
        '      "analysis": "技术分析（4-6句）：①与竞品区别②量化证据③工程局限④行业意义",\n'
        '      "verdict": "一句话结论（有立场：值得用/观望/跳过 + 理由）",\n'
        '      "confidence": "high|medium|low"\n'
        "    }\n"
        "  ],\n"
        '  "industry_moves": [\n'
        "    {\n"
        '      "event": "事件描述（含具体数值/时间/来源）",\n'
        '      "entity": "公司/人物",\n'
        '      "significance": "①重要性②对 AI Agent 生态的含义",\n'
        '      "url": "链接"\n'
        "    }\n"
        "  ],\n"
        '  "workflow_patterns": [\n'
        "    {\n"
        '      "title": "模式标题（动词+名词，如「用 MCP 实现跨工具状态共享」）",\n'
        '      "description": "具体做法（含触发条件/执行步骤/已知效果，2-3句）",\n'
        '      "use_case": "适用场景（具体，不是泛泛）",\n'
        '      "url": "来源链接"\n'
        "    }\n"
        "  ],\n"
        '  "developer_picks": [\n'
        "    {\n"
        '      "title": "标题",\n'
        '      "url": "链接",\n'
        '      "why_it_matters": "具体说明为什么值得看（不要废话）"\n'
        "    }\n"
        "  ],\n"
        '  "next_week_outlook": ["具体信号1（含团队/工具/预期）", "信号2", "信号3"],\n'
        '  "telegram_text": "Telegram 摘要文本"\n'
        "}\n\n"
        + quality_guidelines +
        "\ntelegram_text 格式:\n"
        "🤖 AI Agent Weekly | %s\n\n"
        "📌 TL;DR\n（3 个具体技术要点）\n\n"
        "🔦 Spotlight\n（每个: 名称 + 有立场的一句话 + 关键数据）\n\n"
        "📊 行业动向（如有）\n\n"
        "🔧 工作流模式（如有，含具体做法）\n\n"
        "👀 下周关注（具体信号）\n\n"
        "候选数据:\n\n"
        "=== Daily Monitored Items ===\n%s\n\n"
        "=== Curated Daily Picks ===\n%s\n\n"
        "=== Social Intelligence ===\n%s\n\n"
        "=== Workflow Inspiration ===\n%s"
    ) % (day, date_range, day, date_range, date_range,
         daily_json, picks_json, social_json, workflow_json)
    return msg


def _agent_generate(day, candidates_obj, timeout=120):
    msg = _build_llm_message(day, candidates_obj)
    cmd = [
        "node", NODE, "agent",
        "--agent", "reports",
        "--session-id", "ai-weekly-%s" % day,
        "--message", msg,
        "--json",
        "--timeout", str(timeout),
    ]
    rc, out, err = _run(cmd, timeout=timeout + 30, label="ai-weekly/agent")
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
    ap.add_argument("--account", default="ai_agent_dailybot")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)
    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(
        TMP_DIR, "ai-weekly-candidates-%s-%s.json" % (day, run_id))
    llm_out_path = os.path.join(
        TMP_DIR, "ai-weekly-llm-output-%s-%s.json" % (day, run_id))

    # -- Phase 1: Prep (read memory, build candidates) -----------------
    print("[progress] Phase 1/3: Prep (read memory, build candidates) (~60s)...", flush=True)
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path]
    rc, out, err = _run(prep_cmd, timeout=60, label="ai-weekly/prep")
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

    # -- Phase 2: LLM generation (article writing) ---------------------
    print("[progress] Phase 2/3: LLM generation (article writing) (~120s)...", flush=True)
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

    # -- Phase 3: Post (memory + GitHub + Telegram) --------------------
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
    print("[progress] Phase 3/3: Post (memory + GitHub + Telegram) (~90s)...", flush=True)
    rc, out, err = _run(post_cmd, timeout=90, label="ai-weekly/post")
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
