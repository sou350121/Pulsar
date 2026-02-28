#!/usr/bin/env python3.11
"""
Cross-domain Rule Engine — P1 #6

Runs daily at 10:08 Shanghai time (after VLA rating, before watchdog).
Evaluates deterministic rules defined in active-config.json under
`cross_domain_rules` and appends matched signals to
memory/cross-domain-insight.json.

Rule DSL fields:
  source_domain   : "vla" | "ai_app"
  if_rating       : list of accepted VLA ratings (⚡/🔧/📖/❌) — VLA rules only
  if_match_level  : list of accepted AI App match levels (A/B/C) — AI App rules only
  if_keywords_any : signal must contain at least one of these keywords (title+abstract)
  target_domain   : "vla" | "ai_app" — domain this signal is flagged for
  label           : short tag attached to the insight entry

Output schema (cross-domain-insight.json):
  {"cross_domain_insights": [
    {"date", "rule_id", "label", "source_domain", "target_domain",
     "title", "url", "rating", "matched_keywords", "abstract"}
  ]}

Insights are retained for 60 days (cleaned by memory-janitor.py).
"""

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
MEM_DIR  = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
TMP_DIR  = os.path.join(MEM_DIR, "tmp")
VLA_CFG  = os.path.join(MEM_DIR, "active-config.json")
INSIGHT  = os.path.join(MEM_DIR, "cross-domain-insight.json")
KEEP_DAYS = 60
# ---------------------------------------------------------------------------


def _today() -> str:
    utc = datetime.now(timezone.utc)
    return (utc + timedelta(hours=8)).strftime("%Y-%m-%d")


def _read_json(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, obj: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_rules() -> list:
    """Load cross_domain_rules from active-config.json (VLA config holds all rules)."""
    cfg = _read_json(VLA_CFG)
    return [r for r in cfg.get("cross_domain_rules", []) if r.get("enabled", True)]


def _load_vla_papers(today: str) -> list:
    """Load today's rated VLA papers from vla-daily-rating-out-{today}.json."""
    path = os.path.join(TMP_DIR, f"vla-daily-rating-out-{today}.json")
    if not os.path.exists(path):
        # Fallback: yesterday
        yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        path = os.path.join(TMP_DIR, f"vla-daily-rating-out-{yesterday}.json")
        if not os.path.exists(path):
            return []
    data = _read_json(path)
    return data.get("papers", [])


def _load_aiapp_signals(today: str) -> list:
    """Load today's AI App filtered signals from ai-app-rss-filtered-{today}.json."""
    path = os.path.join(MEM_DIR, f"ai-app-rss-filtered-{today}.json")
    if not os.path.exists(path):
        yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        path = os.path.join(MEM_DIR, f"ai-app-rss-filtered-{yesterday}.json")
        if not os.path.exists(path):
            return []
    data = _read_json(path)
    return data.get("items", [])


def _keywords_match(text: str, keywords: list) -> list:
    """Return matched keywords from the list found in text (case-insensitive)."""
    text_l = text.lower()
    return [kw for kw in keywords if kw.lower() in text_l]


def _eval_vla_rule(rule: dict, papers: list) -> list:
    """Evaluate a VLA-source rule against rated papers. Returns insight entries."""
    hits = []
    accepted_ratings  = rule.get("if_rating", [])
    accepted_keywords = rule.get("if_keywords_any", [])
    for p in papers:
        rating = p.get("rating", "")
        if accepted_ratings and rating not in accepted_ratings:
            continue
        text = f"{p.get('title','')} {p.get('abstract_snippet','')}"
        matched = _keywords_match(text, accepted_keywords)
        if accepted_keywords and not matched:
            continue
        hits.append({
            "rule_id":        rule["id"],
            "label":          rule["label"],
            "source_domain":  "vla",
            "target_domain":  rule["target_domain"],
            "title":          p.get("title", ""),
            "url":            p.get("url", ""),
            "rating":         rating,
            "matched_keywords": matched,
            "abstract":       p.get("abstract_snippet", "")[:200],
        })
    return hits


def _eval_aiapp_rule(rule: dict, signals: list) -> list:
    """Evaluate an AI App-source rule against filtered signals. Returns insight entries."""
    hits = []
    accepted_levels   = rule.get("if_match_level", [])
    accepted_keywords = rule.get("if_keywords_any", [])
    for s in signals:
        level = s.get("match_level", "")
        if accepted_levels and level not in accepted_levels:
            continue
        text = f"{s.get('title','')} {s.get('summary_snippet','')}"
        matched = _keywords_match(text, accepted_keywords)
        if accepted_keywords and not matched:
            continue
        hits.append({
            "rule_id":        rule["id"],
            "label":          rule["label"],
            "source_domain":  "ai_app",
            "target_domain":  rule["target_domain"],
            "title":          s.get("title", ""),
            "url":            s.get("url", ""),
            "rating":         None,
            "matched_keywords": matched,
            "abstract":       s.get("summary_snippet", "")[:200],
        })
    return hits


def _load_insight_log() -> list:
    if not os.path.exists(INSIGHT):
        return []
    data = _read_json(INSIGHT)
    return data.get("cross_domain_insights", [])


def _trim_log(log: list, keep_days: int, today: str) -> list:
    """Remove entries older than keep_days."""
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    return [e for e in log if e.get("date", "") >= cutoff]


# ---------------------------------------------------------------------------

def main() -> int:
    today = _today()
    print(f"[cross-domain] date={today}")

    rules = _load_rules()
    if not rules:
        print("[cross-domain] no rules configured, exiting")
        return 0

    vla_papers = _load_vla_papers(today)
    aiapp_sigs = _load_aiapp_signals(today)
    print(f"[cross-domain] vla_papers={len(vla_papers)}, aiapp_signals={len(aiapp_sigs)}")

    new_entries = []
    for rule in rules:
        src = rule.get("source_domain")
        if src == "vla":
            hits = _eval_vla_rule(rule, vla_papers)
        elif src == "ai_app":
            hits = _eval_aiapp_rule(rule, aiapp_sigs)
        else:
            print(f"[cross-domain] unknown source_domain {src!r} in rule {rule['id']}, skip")
            continue
        for h in hits:
            h["date"] = today
        new_entries.extend(hits)
        if hits:
            print(f"[cross-domain] rule {rule['id']} ({rule['label']}): {len(hits)} hit(s)")

    # Append new entries and trim
    log = _load_insight_log()
    # Deduplicate: skip entries with same date + url already present
    existing_keys = {(e.get("date"), e.get("url")) for e in log}
    added = 0
    for e in new_entries:
        key = (e["date"], e["url"])
        if key not in existing_keys:
            log.append(e)
            existing_keys.add(key)
            added += 1

    log = _trim_log(log, KEEP_DAYS, today)
    _write_json_atomic(INSIGHT, {"cross_domain_insights": log})
    print(f"[cross-domain] added {added} new insight(s), total log={len(log)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
