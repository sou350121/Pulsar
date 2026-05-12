#!/usr/bin/env python3
"""
Cross-domain Rule Engine v2 — Enhanced with built-in rules + LLM significance.

Improvements over v1:
  - Built-in comprehensive rules (not dependent on active-config.json)
  - R002 added: AI tools/frameworks → VLA applications
  - Richer keyword sets with phrase matching
  - LLM generates 1-sentence "cross-domain significance" per batch
  - GitHub Issues cross-repo convergence integrated

Runs daily at 10:20 Shanghai time.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
MEM_DIR   = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR   = os.path.join(MEM_DIR, "tmp")
INSIGHT   = os.path.join(MEM_DIR, "cross-domain-insight.json")
KEEP_DAYS = 60

# ---------------------------------------------------------------------------
# Built-in rules (no longer depends on active-config.json)
# ---------------------------------------------------------------------------

RULES = [
    # ── R001: VLA technique → AI App relevance ──
    {
        "id": "R001", "label": "vla-technique-cross",
        "source_domain": "vla", "target_domain": "ai_app",
        "if_rating": ["⚡", "🔧", "📖"],
        "if_keywords_any": [
            "diffusion", "flow matching", "transformer", "attention",
            "fine-tun", "lora", "rlhf", "grpo", "dpo",
            "context length", "token", "embedding",
            "multimodal", "vision-language", "vlm",
            "quantiz", "distill", "pruning", "onnx", "tensorrt",
            "planning", "reasoning", "chain-of-thought",
            "world model", "video generation", "prediction",
            "foundation model", "pre-train", "scaling",
        ],
        "description": "VLA 技术方法可能影响 AI 应用（模型架构/训练/推理技术迁移）",
    },
    # ── R002: AI App tool/framework → VLA application (NEW) ──
    {
        "id": "R002", "label": "aiapp-tool-to-vla",
        "source_domain": "ai_app", "target_domain": "vla",
        "if_keywords_any": [
            "agent", "tool use", "function call",
            "code generation", "code exec",
            "rag", "retrieval", "knowledge base",
            "sandbox", "safe exec", "guardrail",
            "orchestrat", "workflow", "pipeline",
            "eval", "benchmark", "leaderboard",
            "deploy", "serving", "inference",
            "fine-tun", "lora", "adapt",
            "context engineer", "prompt",
            "vision", "multimodal", "image",
            "edge", "on-device", "mobile",
            "real-time", "streaming", "latency",
            "embodied", "physical", "robot",
            "simulation", "sim2real", "digital twin",
        ],
        "description": "AI 应用工具/框架可能加速 VLA 开发（Agent框架/评估/部署技术迁移）",
    },
    # ── R003: AI App → VLA (embodied AI signals) ──
    {
        "id": "R003", "label": "aiapp-embodied-cross",
        "source_domain": "ai_app", "target_domain": "vla",
        "if_keywords_any": [
            "robot", "embodied", "manipulation",
            "humanoid", "dexterous", "gripper",
            "autonomous", "self-driving",
            "sensor", "lidar", "camera",
            "navigation", "locomotion", "mobility",
            "warehouse", "factory", "industrial",
            "physical ai", "world model",
        ],
        "description": "AI 应用领域的具身智能信号（产业/投资/产品动态影响 VLA 研究方向）",
    },
    # ── R004: VLA foundation → AI App (paradigm influence) ──
    {
        "id": "R004", "label": "vla-foundation-to-aiapp",
        "source_domain": "vla", "target_domain": "ai_app",
        "if_rating": ["⚡", "🔧", "📖"],
        "if_keywords_any": [
            "vla", "vision-language-action",
            "foundation model", "generalist",
            "cross-embodiment", "universal",
            "open-source", "open source",
            "benchmark", "evaluation",
            "scaling law", "emergent",
            "transfer", "zero-shot", "few-shot",
            "world model", "wam",
        ],
        "description": "VLA 基础研究的范式突破可能重塑 AI 应用的方法论",
    },
    # ── R005: Cross-paradigm (VLA vs WAM convergence) ──
    {
        "id": "R005", "label": "paradigm-convergence",
        "source_domain": "vla", "target_domain": "ai_app",
        "if_rating": ["⚡", "🔧", "📖"],
        "if_keywords_any": [
            "world model", "world action",
            "imagination", "dreamer", "planning",
            "video predict", "future predict",
            "latent action", "latent space",
            "model-based", "model predictive",
            "flow", "generative", "diffusion",
        ],
        "description": "VLA 与 WAM 范式融合的信号（论文同时涉及直接动作预测和世界模型）",
    },
]


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _load_vla_papers(today):
    for d in [today, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")]:
        path = os.path.join(TMP_DIR, "vla-daily-rating-out-%s.json" % d)
        if os.path.exists(path):
            return _read_json(path).get("papers", [])
    return []


def _load_aiapp_signals(today):
    for d in [today, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")]:
        path = os.path.join(MEM_DIR, "ai-app-rss-filtered-%s.json" % d)
        if os.path.exists(path):
            return _read_json(path).get("items", [])
    return []


def _load_gh_adoption():
    """Load latest GitHub adoption data for cross-repo convergence."""
    files = sorted(glob.glob(os.path.join(MEM_DIR, "gh-adoption-*.json")))
    if not files:
        return {}
    return _read_json(files[-1])


def _keywords_match(text, keywords):
    """Match keywords/phrases in text (case-insensitive)."""
    text_l = text.lower()
    return [kw for kw in keywords if kw.lower() in text_l]


def _eval_vla_rule(rule, papers, today):
    hits = []
    accepted_ratings = rule.get("if_rating", [])
    keywords = rule.get("if_keywords_any", [])
    for p in papers:
        rating = p.get("rating", "")
        if accepted_ratings and rating not in accepted_ratings:
            continue
        text = "%s %s" % (p.get("title", ""), p.get("abstract_snippet", ""))
        matched = _keywords_match(text, keywords)
        if keywords and not matched:
            continue
        hits.append({
            "date": today,
            "rule_id": rule["id"],
            "label": rule["label"],
            "source_domain": "vla",
            "target_domain": rule["target_domain"],
            "title": p.get("title", ""),
            "url": p.get("url", ""),
            "rating": rating,
            "matched_keywords": matched[:5],
            "abstract": p.get("abstract_snippet", "")[:200],
            "rule_description": rule.get("description", ""),
        })
    return hits


def _eval_aiapp_rule(rule, signals, today):
    hits = []
    keywords = rule.get("if_keywords_any", [])
    for s in signals:
        text = "%s %s" % (s.get("title", ""), s.get("summary_snippet", ""))
        matched = _keywords_match(text, keywords)
        if keywords and not matched:
            continue
        hits.append({
            "date": today,
            "rule_id": rule["id"],
            "label": rule["label"],
            "source_domain": "ai_app",
            "target_domain": rule["target_domain"],
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "rating": None,
            "matched_keywords": matched[:5],
            "abstract": s.get("summary_snippet", "")[:200],
            "rule_description": rule.get("description", ""),
        })
    return hits


def _generate_gh_convergence_insights(adoption, today):
    """Generate cross-domain insights from GitHub Issues convergence patterns."""
    convergence = adoption.get("convergence", [])
    insights = []
    for c in convergence:
        if len(c.get("repos", [])) >= 2:
            insights.append({
                "date": today,
                "rule_id": "R006",
                "label": "github-convergence",
                "source_domain": "github",
                "target_domain": "vla",
                "title": "GitHub: %s" % c.get("pattern", ""),
                "url": c.get("issue_urls", [""])[0] if c.get("issue_urls") else "",
                "rating": None,
                "matched_keywords": c.get("hardware", []),
                "abstract": "%d issues across %s" % (
                    c.get("issue_count", 0), "/".join(c.get("repos", []))
                ),
                "rule_description": "跨仓库收敛：同类问题在多个 VLA 框架出现，代表系统性挑战",
            })
    return insights


def _llm_enrich(insights):
    """Add 1-sentence cross-domain significance to new insights via LLM."""
    if not insights:
        return insights

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _vla_expert import call_qwen
    except ImportError:
        return insights

    # Build compact context
    lines = []
    for i, ins in enumerate(insights[:15]):  # cap at 15
        lines.append("%d. [%s] %s → %s: %s (keywords: %s)" % (
            i + 1, ins["rule_id"], ins["source_domain"], ins["target_domain"],
            ins["title"][:80], ", ".join(ins.get("matched_keywords", [])[:3])
        ))

    prompt = (
        "以下是今日检测到的跨域信号（VLA 具身智能 ↔ AI 应用）。\n"
        "为每条信号写一句「跨域意义」（为什么这个信号对另一个领域重要，15-30字）。\n\n"
        "信号列表：\n%s\n\n"
        "输出纯 JSON 数组，每条一个字符串，顺序对应输入：\n"
        '[\"意义1\", \"意义2\", ...]'
    ) % "\n".join(lines)

    result = call_qwen(
        "你是跨域信号分析师，专注 VLA 具身智能与 AI 应用的交叉点。",
        prompt, timeout=60, temperature=0.2
    )

    if result.get("ok"):
        try:
            import re as _re
            text = result["content"]
            # Extract JSON array
            m = _re.search(r'\[.*\]', text, _re.S)
            if m:
                significances = json.loads(m.group())
                for i, sig in enumerate(significances):
                    if i < len(insights):
                        insights[i]["significance"] = sig
        except Exception:
            pass

    return insights


TRANSFER_HYPOTHESES = """
你掌握以下「AI→VLA 技术转移假设」。每当你看到 AI 应用领域的信号，检查是否能用这些假设生成跨域洞察：

1. Agent tool-use / function calling / MCP → VLA skill library + skill router（机器人调用子技能）
2. Context engineering / system prompt → 结构化任务描述 + 环境 context 注入（VLA 的 language instruction 太原始）
3. RAG / retrieval → Demo retrieval（VLA 检索相似任务的过去轨迹，而非每次从零推理）
4. Eval-driven development / LangSmith / Braintrust → VLA 动作质量评估 + 失败模式分类（不只看成功率）
5. Guardrails / safety → 物理安全约束 + 动作空间限制（机器人撞东西的防护）
6. Multi-agent orchestration → 多机器人协作的任务分解
7. Streaming / real-time inference → VLA 推理延迟优化（KV-cache, speculative decode 迁移）
8. Fine-tune pipeline (LoRA/PEFT) → VLA 自动化微调管线
9. Observability / tracing → 机器人动作 trace + 部署后失败归因
10. Vibe coding / intent→code → Code-as-Policy（自然语言→机器人程序，替代大量示教数据）
"""


def _llm_generate_transfers(vla_papers, aiapp_signals, today):
    """LLM proactively generates cross-domain transfer insights.

    Instead of keyword matching, asks LLM to find non-obvious connections
    between today's AI app signals and VLA research using transfer hypotheses.
    """
    if not aiapp_signals and not vla_papers:
        return []

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _vla_expert import call_qwen
    except ImportError:
        return []

    # Build compact summaries
    ai_lines = []
    for s in aiapp_signals[:10]:
        ai_lines.append("- %s" % s.get("title", "")[:80])

    vla_lines = []
    for p in vla_papers[:10]:
        vla_lines.append("- [%s] %s" % (p.get("rating", "?"), p.get("title", "")[:80]))

    if not ai_lines and not vla_lines:
        return []

    prompt = (
        "今日 AI 应用动态：\n%s\n\n"
        "今日 VLA 论文：\n%s\n\n"
        "基于以上 AI→VLA 技术转移假设，找出 1-3 个**非显而易见的**跨域连接。\n"
        "每条连接必须：\n"
        "- 指出 AI 侧的具体信号和 VLA 侧的具体需求\n"
        "- 说明转移路径（怎么用 AI 的方法解决 VLA 的问题）\n"
        "- 标注对应的假设编号（1-10）\n\n"
        "输出纯 JSON 数组：\n"
        '[{"ai_signal": "AI侧信号标题", "vla_need": "VLA侧需求", '
        '"transfer": "转移路径（1句）", "hypothesis": 3, '
        '"significance": "跨域意义（15-25字）"}]\n\n'
        "如果今天没有值得报告的跨域连接，输出空数组 []。\n"
        "宁缺毋滥——只报告真正有洞察力的连接。"
    ) % ("\n".join(ai_lines) or "(无)", "\n".join(vla_lines) or "(无)")

    result = call_qwen(
        "你是跨域技术迁移分析师。" + TRANSFER_HYPOTHESES,
        prompt, timeout=90, temperature=0.3
    )

    insights = []
    if result.get("ok"):
        try:
            import re as _re
            text = result["content"]
            m = _re.search(r'\[.*\]', text, _re.S)
            if m:
                transfers = json.loads(m.group())
                for t in transfers:
                    if not isinstance(t, dict):
                        continue
                    insights.append({
                        "date": today,
                        "rule_id": "R007",
                        "label": "ai-to-vla-transfer",
                        "source_domain": "ai_app",
                        "target_domain": "vla",
                        "title": t.get("ai_signal", ""),
                        "url": "",
                        "rating": None,
                        "matched_keywords": ["hypothesis-%d" % t.get("hypothesis", 0)],
                        "abstract": t.get("transfer", ""),
                        "significance": t.get("significance", ""),
                        "vla_need": t.get("vla_need", ""),
                        "rule_description": "LLM 主动发现的 AI→VLA 技术转移机会",
                    })
        except Exception:
            pass

    return insights


def main():
    today = _today()
    print("[cross-domain-v2] date=%s" % today)

    vla_papers = _load_vla_papers(today)
    aiapp_sigs = _load_aiapp_signals(today)
    gh_adoption = _load_gh_adoption()
    print("[cross-domain-v2] vla=%d, aiapp=%d, gh_adoption=%s" % (
        len(vla_papers), len(aiapp_sigs), "yes" if gh_adoption else "no"
    ))

    new_entries = []
    for rule in RULES:
        src = rule.get("source_domain")
        if src == "vla":
            hits = _eval_vla_rule(rule, vla_papers, today)
        elif src == "ai_app":
            hits = _eval_aiapp_rule(rule, aiapp_sigs, today)
        else:
            continue
        new_entries.extend(hits)
        if hits:
            print("[cross-domain-v2] %s (%s): %d hit(s)" % (rule["id"], rule["label"], len(hits)))

    # R006: GitHub convergence
    if gh_adoption:
        gh_insights = _generate_gh_convergence_insights(gh_adoption, today)
        new_entries.extend(gh_insights)
        if gh_insights:
            print("[cross-domain-v2] R006 (github-convergence): %d hit(s)" % len(gh_insights))

    # R007: LLM-generated AI→VLA transfer insights
    print("[cross-domain-v2] LLM transfer hypothesis matching...")
    transfer_insights = _llm_generate_transfers(vla_papers, aiapp_sigs, today)
    new_entries.extend(transfer_insights)
    if transfer_insights:
        print("[cross-domain-v2] R007 (ai-to-vla-transfer): %d insight(s)" % len(transfer_insights))

    # LLM enrich with significance (for keyword-matched entries that don't have it yet)
    keyword_entries = [e for e in new_entries if not e.get("significance")]
    if keyword_entries:
        print("[cross-domain-v2] LLM enrichment for %d entries..." % len(keyword_entries))
        keyword_entries = _llm_enrich(keyword_entries)
        # Merge back
        sig_map = {(e["date"], e["url"], e["title"]): e.get("significance") for e in keyword_entries if e.get("significance")}
        for e in new_entries:
            if not e.get("significance"):
                key = (e["date"], e["url"], e["title"])
                if key in sig_map:
                    e["significance"] = sig_map[key]

    # Append + dedup + trim
    log = []
    if os.path.exists(INSIGHT):
        log = _read_json(INSIGHT).get("cross_domain_insights", [])

    existing_keys = {(e.get("date"), e.get("url")) for e in log}
    added = 0
    for e in new_entries:
        key = (e["date"], e["url"])
        if key not in existing_keys:
            log.append(e)
            existing_keys.add(key)
            added += 1

    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    log = [e for e in log if e.get("date", "") >= cutoff]

    _write_json_atomic(INSIGHT, {"cross_domain_insights": log})
    print("[cross-domain-v2] added=%d, total=%d" % (added, len(log)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
