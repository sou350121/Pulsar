#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for AI App Social Intel.

Flow:
1) prep-ai-app-social.py -> Perplexity search + exclusion -> candidates JSON
2) call LLM agent         -> generate structured signals + telegram text
3) write memory + telegram delivery (no separate post script)

Print: single JSON line (ok/summary)
Exit: non-zero on hard failure

Python 3.6+ (no external deps).
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import sys

from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-ai-app-social.py"
NODE = "/opt/moltbot/dist/index.js"
MEM_UPSERT = "/home/admin/clawd/scripts/memory-upsert.py"
WORKDIR = "/home/admin"
TMP_DIR = "/home/admin/clawd/memory/tmp"
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"
SOCIAL_INTEL_PATH = "/home/admin/clawd/memory/ai-app-social-intel.json"



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


def _existing_nonempty_for_day(day):
    try:
        if not os.path.exists(SOCIAL_INTEL_PATH):
            return False
        obj = _load_json(SOCIAL_INTEL_PATH)
        rows = obj.get("social_intel") or []
        if not isinstance(rows, list):
            return False
        for r in rows:
            if not isinstance(r, dict):
                continue
            if (r.get("date") or "").strip() != day:
                continue
            sig = r.get("signals") or []
            if isinstance(sig, list) and len(sig) > 0:
                return True
        return False
    except Exception:
        return False

def _build_llm_message(day, candidates_obj):
    results = candidates_obj.get("search_results") or []
    parts = []
    for idx, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        if not r.get("ok"):
            continue
        content = (r.get("content") or "").strip()
        urls = r.get("urls") or []
        q = (r.get("query") or "").strip()
        if content:
            parts.append("--- Search %d ---\nQuery: %s\n%s" % (idx + 1, q, content))
            if urls:
                parts.append("Links: " + " | ".join(urls[:6]))
    context = "\n\n".join(parts) if parts else "(No social signals.)"

    msg = (
        "你是『AI 应用开发社交情报』生成器。你的工作是将搜索结果转化为「人们在说什么」的社交情报，而不是工具发布日报。\n"
        "⚠️ 禁止编造 URL / 禁止编造版本号 / 禁止把旧闻当作今日。\n\n"
        "今天日期（Asia/Shanghai）: %s\n\n"
        "「社交情报」内容定义：\n"
        "  - ✅ 要收录：大佬的观点/预测，社区热议/争论，病毒传播的 demo 或帖子，对 AI 工具的真实社区反应，感情趨势，融资/收购大事\n"
        "  - ❌ 不要收录：工具/框架的更新公告、changelog、新版本发布（那是日报的工作）\n\n"
        "硬规则：\n"
        "- 只收录最近 72 小时内的事件/观点；超过 7 天必须标注（旧闻补充，发布于 YYYY-MM-DD）\n"
        "- 不要报纯工具发布/changelog；除非发布引起了重大社区争论\n"
        "- 每条必须有可验证的来源 URL（博客/游记/Reddit/X/GitHub讨论）。做不到就不要写\n"
        "- 宁缺毛滥：没有足够社交信号就输出「今日无重大社交信号」\n\n"
        "输出必须是纯 JSON 对象，不要 markdown fence，不要解释。\n\n"
        "JSON schema:\n"
        "{\n"
        '  \"date\": \"%s\",\n'
        '  \"telegram_text\": \"Telegram 正文\",\n'
        '  \"signals\": [\n'
        "    {\n"
        '      \"type\": \"观点/预测|社区热议|争论/批评|病毒传播|融资/收购|模型发布|安全事件\",\n'
        '      \"source\": \"来源平台（Reddit/X/HN/博客/GitHub）\",\n'
        '      \"person_or_entity\": \"实体或社区\",\n'
        '      \"summary\": \"一句话中文摘要（包含说了什么 + 社区反应或争论要点）\",\n'
        '      \"url\": \"来源链接\",\n'
        '      \"signal_level\": \"一级|二级|三级\"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "telegram_text 格式（条目之间空一行；链接独立成行）：\n"
        "🛰️ AI 社交情报 | %s\n\n"
        "🔥 热议/争论（如有）\n"
        "- {实体：争论要点一句话}\n"
        "  {来源链接}\n\n"
        "💬 观点/预测（2-4 条）\n"
        "- [人名或社区] {摘要}\n"
        "  {来源链接}\n\n"
        "💰 融资/收购/大事（如有）\n"
        "- {实体}: {摘要}\n"
        "  {来源链接}\n\n"
        "（若无信号：telegram_text = '🛰️ 今日 AI 社交面无重大信号'，signals=[]）\n\n"
        "搜索结果原文:\n\n%s"
    ) % (day, day, day, context)
    return msg


def _agent_generate(day, candidates_obj, agent_id="ai_app_monitor", timeout=120):
    msg = _build_llm_message(day, candidates_obj)
    cmd = [
        "node",
        NODE,
        "agent",
        "--agent",
        agent_id,
        "--session-id",
        "ai-app-social-%s" % day,
        "--message",
        msg,
        "--json",
        "--timeout",
        str(int(timeout)),
    ]
    rc, out, err = _run(cmd, timeout=timeout + 60, label="ai-app-social/agent")
    if rc != 0:
        return False, {"error": "agent_cmd_failed", "rc": rc, "stderr": (err or "")[:300]}

    js = _extract_json_text(out)
    if not js:
        return False, {"error": "agent_json_not_found", "stdout": (out or "")[:400]}
    try:
        obj = json.loads(js)
    except Exception as e:
        return False, {"error": "agent_json_parse_failed", "detail": str(e)[:200]}

    text = ""
    try:
        text = (((obj.get("result") or {}).get("payloads") or [{}])[0].get("text")) or ""
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
        return False, {"error": "model_output_not_json", "text_head": text[:300]}
    try:
        payload = json.loads(model_json_txt)
    except Exception as e:
        return False, {"error": "model_json_parse_failed", "detail": str(e)[:200]}

    if not isinstance(payload, dict):
        return False, {"error": "model_payload_not_dict"}
    payload["date"] = day
    if not isinstance(payload.get("signals"), list):
        payload["signals"] = []
    if not isinstance(payload.get("telegram_text"), str):
        payload["telegram_text"] = ""
    return True, payload


def _send_telegram(text, target="1898430254", account="ai_agent_dailybot"):
    if not text:
        return 0, "", ""
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    return _run(cmd, timeout=60, label="ai-app-social/telegram")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="ai_agent_dailybot")
    ap.add_argument("--agent", default="ai_app_monitor")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--best-effort-telegram", action="store_true",
                    help="Do not fail the run when Telegram send fails")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)

    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(TMP_DIR, "ai-app-social-candidates-%s-%s.json" % (day, run_id))
    llm_out_path = os.path.join(TMP_DIR, "ai-app-social-llm-output-%s-%s.json" % (day, run_id))
    upsert_in_path = os.path.join(TMP_DIR, "ai-app-social-entry-%s-%s.json" % (day, run_id))

    # Phase 1: Prep
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path, "--max-queries", "4"]
    if args.no_web:
        prep_cmd.append("--no-web")
    print("[progress] Phase 1/3: running prep script...", flush=True)
    rc, out, err = _run(prep_cmd, timeout=300, label="ai-app-social/prep")
    print("[progress] Phase 1/3: prep finished (rc=%d)." % rc, flush=True)
    if rc != 0 or (not os.path.exists(cands_path)):
        print(json.dumps({"ok": False, "error": "prep_failed", "rc": rc, "stderr": (err or "")[:300]}, ensure_ascii=False))
        return 1
    candidates_obj = _load_json(cands_path)

    # Phase 2: LLM
    print("[progress] Phase 2/3: generating social intel via agent...", flush=True)
    ok, payload = _agent_generate(day, candidates_obj, agent_id=args.agent.strip() or "ai_app_monitor", timeout=180)
    if not ok:
        print(json.dumps({"ok": False, "error": "agent_failed", "detail": payload}, ensure_ascii=False))
        return 1
    try:
        with open(llm_out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except Exception:
        pass

    # Phase 3: Memory upsert
    entry = {"date": day, "signals": payload.get("signals") or [], "telegram_text": payload.get("telegram_text") or ""}

    # Guardrail: never overwrite an existing non-empty day with an empty result
    # (e.g., --no-web fallback or web credits outage). This prevents data loss
    # and avoids sending "no major signals" after we already had signals.
    if (not entry.get("signals")) and _existing_nonempty_for_day(day) and (not args.dry_run):
        print(json.dumps({
            "ok": True,
            "date": day,
            "candidates_path": cands_path,
            "llm_output_path": llm_out_path,
            "memory": {"ok": True, "skipped": True, "reason": "keep_existing_nonempty"},
            "telegram": {"ok": True, "skipped": True, "reason": "keep_existing_nonempty"},
            "signals": 0,
        }, ensure_ascii=False))
        return 0

    try:
        with open(upsert_in_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "write_entry_failed", "detail": str(e)[:200]}, ensure_ascii=False))
        return 1

    up_cmd = ["bash", "-lc", "cat %s | python3 %s --file ai-app-social-intel.json --key social_intel --max-days 30%s" % (
        upsert_in_path,
        MEM_UPSERT,
        " --dry-run" if args.dry_run else "",
    )]
    rc, up_out, up_err = _run(up_cmd, timeout=60, label="ai-app-social/memory-upsert")
    mem = {"ok": (rc == 0), "rc": rc, "out": (up_out or "")[:240], "err": (up_err or "")[:240]}

    # Telegram
    tg = {"ok": True, "skipped": True}
    if not args.no_telegram and not args.dry_run:
        rc, tg_out, tg_err = _send_telegram(
            (payload.get("telegram_text") or "").strip(),
            target=args.target.strip(),
            account=args.account.strip(),
        )
        tg = {"ok": (rc == 0), "rc": rc, "out": (tg_out or "")[:160], "err": (tg_err or "")[:160]}

    overall_ok = bool(mem.get("ok")) and bool(tg.get("ok"))
    print(json.dumps({
        "ok": overall_ok,
        "date": day,
        "candidates_path": cands_path,
        "llm_output_path": llm_out_path,
        "memory": mem,
        "telegram": tg,
        "signals": len(entry.get("signals") or []),
    }, ensure_ascii=False))
    if overall_ok or args.best_effort_telegram or args.no_telegram or args.dry_run:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

