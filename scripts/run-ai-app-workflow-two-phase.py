#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for AI App Workflow Inspiration.

Flow:
1) prep-ai-app-workflow.py -> Perplexity search for workflow patterns
2) call LLM agent           -> generate structured workflow digest
3) Post: memory write + Telegram

Print: post result (single JSON line on success/failure)
Exit: non-zero on hard failure
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from _heartbeat_run import run_with_heartbeat


PREP = "/home/admin/clawd/scripts/prep-ai-app-workflow.py"
NODE = "/opt/moltbot/dist/index.js"
MOLTBOT_BIN = "/home/admin/.local/share/pnpm/moltbot"
WORKDIR = "/home/admin"
TMP_DIR = "/home/admin/clawd/memory/tmp"
MEM_DIR = "/home/admin/clawd/memory"
WORKFLOW_PATH = os.path.join(MEM_DIR, "ai-app-workflow-digest.json")

DASHSCOPE_AUTH_PATH = "/home/admin/.moltbot/agents/reports/agent/auth-profiles.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def _get_api_key():
    """Read DashScope API key from env or auth-profiles."""
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if key:
        return key
    try:
        with open(DASHSCOPE_AUTH_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return (cfg.get("profiles", {})
                   .get("alibaba-cloud:default", {})
                   .get("key", "")) or ""
    except Exception:
        return ""


def _call_qwen_max(system_prompt, user_prompt, timeout=60):
    """Call qwen-max for expert curation. Returns text or None on failure."""
    try:
        from urllib.request import Request, urlopen
    except ImportError:
        return None
    key = _get_api_key()
    if not key:
        return None
    payload = {
        "model": "qwen3.5-plus",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(DASHSCOPE_URL, data=body, headers={
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
    })
    for attempt in range(2):
        try:
            rsp = urlopen(req, timeout=timeout)
            raw = rsp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            return (obj.get("choices", [{}])[0]
                       .get("message", {})
                       .get("content", ""))
        except Exception:
            if attempt == 1:
                return None
    return None


def _expert_curate_cards(cards, day):
    """Use qwen-max to score inspiration value (0-5) and filter to >=4 only.
    Keeps at least 1 card. Skips gracefully if API call fails."""
    if not cards or len(cards) <= 1:
        return cards
    cards_text = json.dumps(cards, ensure_ascii=False, indent=2)
    system = (
        "你是「AI 工作流灵感」质量把控专家。"
        "评估每张灵感卡片的「启发价值」，标准如下：\n"
        "5 = 读者立刻想试，步骤清晰，解决真实痛点，工具具体\n"
        "4 = 很有价值，稍需补充，但核心灵感清晰\n"
        "3 = 一般，过于通用或太obvious（如\"用ChatGPT写邮件\"）\n"
        "2 = 只是工具公告/新闻，无具体工作流\n"
        "1 = 无实质内容、纯营销或first_step仅是'访问官网/注册'\n\n"
        "保留评分 >= 4 的卡片（最少保留 1 张，最多 5 张）。"
        "按评分从高到低排序。"
    )
    user = (
        "今天日期: %s\n\n"
        "待评估的灵感卡片（JSON）:\n%s\n\n"
        "请对每张卡片评分，然后返回筛选后的卡片。\n"
        "输出纯 JSON，格式：\n"
        "{\"curated_cards\": [...保留的完整卡片原样，按评分降序...], "
        "\"scores\": {\"卡片title\": 分数}}"
    ) % (day, cards_text)

    result = _call_qwen_max(system, user, timeout=60)
    if not result:
        return cards
    js = _extract_json_text(result)
    if not js:
        return cards
    try:
        obj = json.loads(js)
        curated = obj.get("curated_cards") or []
        if curated:
            scores = obj.get("scores") or {}
            print("[expert] Curated %d/%d cards. Scores: %s" % (
                len(curated), len(cards),
                ", ".join("%s=%s" % (k[:15], v) for k, v in list(scores.items())[:5])
            ), flush=True)
            return curated
    except Exception as e:
        print("[expert] Parse error: %s" % e, flush=True)
    return cards




_EXEC_FAIL_PATTERNS = [
    'FileNotFoundError', 'No such file or directory', 'ENOENT', 'EACCES',
    'Permission denied', 'Unknown model', 'ModuleNotFoundError',
    'ImportError:', 'SyntaxError:', 'Traceback (most recent call last)',
]

def _detect_exec_failure(text):
    for pat in _EXEC_FAIL_PATTERNS:
        if pat in (text or ''):
            return True, pat
    return False, None

def _today():
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def _run_heartbeat(cmd, timeout=120, label="subprocess"):
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


def _run_simple(cmd, timeout=60, cwd="/home/admin"):
    env = dict(os.environ)
    env["HOME"] = "/home/admin"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return int(p.returncode), (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 125, "", str(e)


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


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _send_telegram(text, target="1898430254", account="ai_agent_dailybot"):
    if not text:
        return {"ok": True, "skipped": True}
    cmd = [MOLTBOT_BIN, "message", "send", "--channel", "telegram"]
    if account:
        cmd.extend(["--account", account])
    cmd.extend(["--target", target, "--message", text])
    rc, out, err = _run_simple(cmd, timeout=45)
    return {"ok": (rc == 0), "rc": rc, "out": (out or "")[:200]}


def _build_llm_message(day, candidates_obj):
    results = candidates_obj.get("search_results") or []
    parts = []
    for idx, r in enumerate(results):
        if not r.get("ok") or r.get("filtered_reason"):
            continue
        content = (r.get("content") or "").strip()
        urls_ann = r.get("urls_annotated") or []
        urls = [u.get("url", "") for u in urls_ann
                if u.get("url_valid", True)][:5]
        if not urls:
            urls = (r.get("urls") or [])[:5]
        query = r.get("query", r.get("search_name", "?"))[:80]
        if content:
            parts.append("--- 搜索 %d [%s] ---\n%s" % (idx + 1, query, content))
            if urls:
                parts.append("链接: " + " | ".join(urls))

    context = "\n\n".join(parts) if parts else "(无搜索结果)"

    msg = (
        "你是「AI 工作流灵感」专栏编辑，面向工程师、PM、分析师、创作者、创业者。\n\n"
        "【核心使命】找出「让读者立刻打开新标签页试着做」的具体工作流。\n"
        "不是报道新工具发布，而是「用工具解决了什么问题、怎么做的」。\n\n"
        "【灵感判定标准（必须同时满足）】\n"
        "1. 可在 30 分钟内尝试第一步（不是\"了解\"或\"注册官网\"）\n"
        "2. 解决了一个真实痛点（有 before/after 的对比感）\n"
        "3. 工具 + 场景 + 步骤三要素齐全\n"
        "4. 非纯粹工具发布公告（工具本身不是灵感，用工具做成的事才是）\n\n"
        "【拒绝标准（命中任一 → 跳过）】\n"
        "- first_step 仅为\"访问官网 / 注册账户 / 阅读文档\"\n"
        "- 只有工具名，没有具体工作场景\n"
        "- 新工具发布公告（无使用案例）\n"
        "- 人尽皆知的通用建议（如\"用 ChatGPT 写邮件\"）\n\n"
        "⚠️ 禁止编造 URL。只报告有可验证来源的内容。\n"
        "⚠️ 禁止 web_search / web_fetch / 任何网络调用。只基于提供的数据生成。\n"
        "⚠️ 若无合格内容，宁可只输出 1-2 张卡片，绝不凑数。\n\n"
        "今天日期: %s\n\n"
        "字段说明:\n"
        "- title: 动词开头，描述做成了什么（10字内，如\"用 n8n 自动归档邮件附件\"）\n"
        "- problem_solved: 解决了什么痛点（1句话，有 before/after 感）\n"
        "- target_roles: 最多 3 个，从：工程师/产品经理/分析师/内容创作者/创业者/研究者\n"
        "- difficulty: 1-5（1=无代码拖拉即用，5=需编程部署）\n"
        "- first_step: 具体可操作（包含工具名+动词+对象，如'打开 n8n → 搜索 RSS template → 连接 Notion'）\n"
        "- inspiration_score: 自评 1-5（5=读者立刻想试）\n\n"
        "输出必须是纯 JSON 对象，不要 markdown fence，不要解释。\n\n"
        "{\n"
        '  "date": "%s",\n'
        '  "telegram_text": "Telegram 正文（见格式）",\n'
        '  "inspiration_cards": [\n'
        "    {\n"
        '      "title": "动词开头描述做成了什么（10字内）",\n'
        '      "problem_solved": "解决了什么痛点（before/after感）",\n'
        '      "target_roles": ["产品经理", "创业者"],\n'
        '      "workflow_steps": ["第一步（工具+操作）", "第二步", "第三步"],\n'
        '      "difficulty": 2,\n'
        '      "key_tools": ["n8n", "Claude API"],\n'
        '      "first_step": "打开 n8n → 搜索 Gmail template → 连接 Notion 数据库",\n'
        '      "inspiration_score": 4,\n'
        '      "url": "一手来源链接（无来源则留空）",\n'
        '      "category": "no-code|orchestration|content|research|data|other"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "telegram_text 格式（严格按此模板）:\n"
        "🌟 AI 工作流灵感 | {date}\n\n"
        "（每张卡片格式：\n"
        "💡 #{n} 适合：{角色1} / {角色2}\n"
        "{标题}\n\n"
        "{problem_solved}\n\n"
        "{2-3句具体做法，包含工具名和步骤}\n\n"
        "🔧 {工具列表}  难度：{difficulty}/5\n"
        "📌 第一步：{first_step}\n"
        "🔗 {url}（无来源则省略此行）\n"
        "━━━━━━━━━━━━━━）\n\n"
        "搜索结果原文:\n\n%s"
    ) % (day, day, context)
    return msg

def _upsert_workflow_digest(day, cards, dry_run=False):
    obj = _load_json(WORKFLOW_PATH) if os.path.exists(WORKFLOW_PATH) else {"workflow_digest": []}
    rows = obj.get("workflow_digest")
    if not isinstance(rows, list):
        rows = []
    # Store as inspiration_cards (new schema); old entries keep their patterns key
    entry = {"date": day, "inspiration_cards": cards}
    replaced = False
    for i, r in enumerate(rows):
        if isinstance(r, dict) and (r.get("date") or "").strip() == day:
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)
    rows = [r for r in rows if isinstance(r, dict) and r.get("date")]
    rows.sort(key=lambda x: x.get("date", ""))
    rows = rows[-90:]
    if not dry_run:
        _write_json_atomic(WORKFLOW_PATH, {"workflow_digest": rows})
    return {"total": len(rows), "replaced": replaced}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--target", default="1898430254")
    ap.add_argument("--account", default="ai_agent_dailybot")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)
    run_id = "%s-%s" % (os.getpid(), int(_dt.datetime.utcnow().timestamp()))
    cands_path = os.path.join(
        TMP_DIR, "ai-workflow-candidates-%s-%s.json" % (day, run_id))
    llm_out_path = os.path.join(
        TMP_DIR, "ai-workflow-llm-output-%s-%s.json" % (day, run_id))

    # Phase 1: Prep (Perplexity search for workflow patterns)
    print("[progress] Phase 1/3: Prep (search for workflow patterns, ~60s)...", flush=True)
    prep_cmd = ["python3", PREP, "--date", day, "--out", cands_path, "--max-queries", "2"]
    if args.no_web:
        prep_cmd.append("--no-web")
    rc, out, err = _run_heartbeat(prep_cmd, timeout=300, label="ai-workflow/prep")
    print("[progress] Phase 1/3: step finished (rc=%d)." % rc, flush=True)
    if rc != 0:
        print(json.dumps(
            {"ok": False, "error": "prep_failed", "rc": rc, "stderr": err[:300]},
            ensure_ascii=False))
        return 1
    if not os.path.exists(cands_path):
        print(json.dumps(
            {"ok": False, "error": "candidates_missing", "path": cands_path},
            ensure_ascii=False))
        return 1

    candidates_obj = _load_json(cands_path)

    # Phase 2: LLM generation
    print("[progress] Phase 2/3: LLM generation (workflow patterns, ~60s)...", flush=True)
    msg = _build_llm_message(day, candidates_obj)
    cmd = [
        "node", NODE, "agent",
        "--agent", "reports",
        "--session-id", "ai-workflow-%s" % day,
        "--message", msg,
        "--json",
        "--timeout", "90",
    ]
    rc, out, err = _run_heartbeat(cmd, timeout=120, label="ai-workflow/agent")
    print("[progress] Phase 2/3: step finished (rc=%d)." % rc, flush=True)
    if rc != 0:
        print(json.dumps(
            {"ok": False, "error": "agent_failed", "rc": rc, "stderr": err[:300]},
            ensure_ascii=False))
        return 1

    js = _extract_json_text(out)
    if not js:
        print(json.dumps(
            {"ok": False, "error": "agent_json_not_found", "stdout": out[:400]},
            ensure_ascii=False))
        return 1
    try:
        agent_obj = json.loads(js)
    except Exception as e:
        print(json.dumps(
            {"ok": False, "error": "agent_json_parse_failed", "detail": str(e)},
            ensure_ascii=False))
        return 1

    text = ""
    try:
        text = (
            (((agent_obj.get("result") or {}).get("payloads") or [{}])[0]
             .get("text")) or ""
        )
    except Exception:
        text = ""
    if not text.strip():
        print(json.dumps({"ok": False, "error": "agent_empty_text"}, ensure_ascii=False))
        return 1

    if text:
        _exec_fail, _exec_pat = _detect_exec_failure(text)
        if _exec_fail:
            print(json.dumps({'ok': False, 'error': 'agent_exec_failure_detected',
                              'pattern': _exec_pat, 'text_head': text[:300]}, ensure_ascii=False))
            return 2
    model_js = _extract_json_text(text)
    if not model_js:
        print(json.dumps(
            {"ok": False, "error": "model_output_not_json", "text_head": text[:300]},
            ensure_ascii=False))
        return 1
    try:
        payload = json.loads(model_js)
    except Exception as e:
        print(json.dumps(
            {"ok": False, "error": "model_json_parse_failed", "detail": str(e)},
            ensure_ascii=False))
        return 1

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "model_payload_not_dict"}, ensure_ascii=False))
        return 1

    payload["date"] = day
    with open(llm_out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Expert curation: qwen-max scores inspiration value, filters >=4/5
    print("[progress] Expert curation: scoring inspiration value (~30s)...", flush=True)
    raw_cards = payload.get("inspiration_cards") or payload.get("patterns") or payload.get("items") or []
    curated_cards = _expert_curate_cards(raw_cards, day)
    if curated_cards != raw_cards:
        payload["inspiration_cards"] = curated_cards
        # Rebuild telegram_text is skipped; use expert-curated cards for memory
        # TG text from model is kept as-is (expert just filters, not rewrites)
    print("[progress] Expert curation finished (%d cards)." % len(curated_cards), flush=True)

    # Phase 3: Post (memory + Telegram)
    print("[progress] Phase 3/3: Post (memory + Telegram)...", flush=True)
    # New schema uses inspiration_cards; fall back to patterns/items for old prompts
    patterns = payload.get("inspiration_cards") or payload.get("patterns") or payload.get("items") or []
    tg_text = (payload.get("telegram_text") or "").strip()

    mem_result = {"ok": True, "skipped": True}
    if not args.dry_run:
        try:
            mem = _upsert_workflow_digest(day, patterns)
            mem_result = {"ok": True, **mem}
        except Exception as e:
            mem_result = {"ok": False, "error": str(e)[:200]}

    tg = {"ok": True, "skipped": True}
    if not args.dry_run and not args.no_telegram and tg_text:
        tg = _send_telegram(
            tg_text,
            target=(args.target or "").strip() or "1898430254",
            account=(args.account or "").strip(),
        )

    print("[progress] Phase 3/3: step finished.", flush=True)
    print(json.dumps({
        "ok": True,
        "date": day,
        "cards": len(patterns),  # inspiration_cards count
        "memory": mem_result,
        "telegram": tg,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
