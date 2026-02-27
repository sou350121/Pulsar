#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare deterministic change set for VLA SOTA tracker.

Source:
- https://github.com/MINT-SJTU/Evo-SOTA.io (raw JSON under public/data/)

Output:
- /home/admin/clawd/memory/tmp/vla-sota-candidates-YYYY-MM-DD.json
"""

from __future__ import print_function

import argparse
import datetime as _dt
import html as _html
import json
import os
import re
import subprocess
import sys

try:
    from urllib.error import HTTPError
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
except Exception:  # pragma: no cover
    HTTPError = Exception
    urlparse = None
    Request = None
    urlopen = None


MEM_DIR = "/home/admin/clawd/memory"
TMP_DIR = "/home/admin/clawd/memory/tmp"
TRACKER_PATH = "/home/admin/clawd/memory/vla-sota-tracker.json"
ORG_CACHE_PATH = "/home/admin/clawd/memory/vla-paper-org-cache.json"
NODE = "/opt/moltbot/dist/index.js"
WORKDIR = "/home/admin"
QWEN_AGENT_ID = "reports"
QWEN_SESSION_ID = "vla-sota-org-fill"

SOURCE_REPO = "MINT-SJTU/Evo-SOTA.io"
RAW_BASE = "https://raw.githubusercontent.com/%s/main" % SOURCE_REPO

# Keep this list explicit so behavior is deterministic.
DATA_SOURCES = [
    {
        "slug": "calvin",
        "benchmark": "CALVIN",
        "path": "public/data/calvin.json",
    },
    {
        "slug": "libero",
        "benchmark": "LIBERO",
        "path": "public/data/libero.json",
    },
    {
        "slug": "liberoplus",
        "benchmark": "LIBERO Plus",
        "path": "public/data/liberoPlus.json",
    },
    {
        "slug": "metaworld",
        "benchmark": "MetaWorld",
        "path": "public/data/metaworld.json",
    },
    {
        "slug": "robochallenge",
        "benchmark": "RoboChallenge",
        "path": "public/data/robochallenge.json",
    },
    {
        "slug": "robocasa_gr1_tabletop",
        "benchmark": "RoboCasa-GR1-Tabletop",
        "path": "public/data/robocasa_gr1_tabletop.json",
    },
]

# If these critical sources fail, we fail the prep run to avoid silent blind spots.
CRITICAL_SOURCE_SLUGS = set(["robochallenge"])

SPLIT_MAP = {
    "abcd_d": "ABCD-D",
    "abc_d": "ABC-D",
    "d_d": "D-D",
}

METRIC_PREF = {
    "CALVIN": ["avg_len", "average", "score", "success_rate"],
    "LIBERO": ["average", "libero_90", "avg_success_rate", "success_rate", "score"],
    "LIBERO Plus": ["total", "average", "libero_90", "avg_success_rate", "success_rate", "score"],
    "MetaWorld": ["average", "success_rate", "score"],
    "RoboChallenge": ["score", "success_rate", "average"],
    "RoboCasa-GR1-Tabletop": ["avg_success_rate", "average", "success_rate", "score"],
}

# Focus benchmarks to include richer weekly top-k details in Telegram.
FOCUS_TOPK_BENCHMARKS = set(["LIBERO", "RoboChallenge"])

# Well-known model -> organization mapping (human-curated, high confidence).
# Key: substring to match against model name (lowercased).
# Checked in order; first match wins.
KNOWN_MODEL_ORG = [
    ("pi0.5", "Physical Intelligence"),
    ("pi0", "Physical Intelligence"),
    ("pi-rl", "Physical Intelligence"),
    ("pi_rl", "Physical Intelligence"),
    ("wall-oss", "X Square"),
    ("wall-a", "X Square"),
    ("giga-brain", "Embodied AI Foundation"),
    ("gr-2", "ByteDance Seed"),
    ("gr-3", "ByteDance Seed"),
    ("gr-rl", "ByteDance Seed"),
    ("gr-dexter", "ByteDance Seed"),
    ("spirit", "Spirit AI"),
    ("abot", "AMAP CV Lab"),
    ("mcil", "Universitat Freiburg"),
    ("octo", "UC Berkeley"),
    ("openvla", "Stanford / UC Berkeley"),
    ("rdt-1b", "Tsinghua MARS Lab / ByteDance"),
]
ORG_KEYWORDS = (
    "university", "institute", "school", "laboratory", "lab",
    "inc.", "ltd.", "agibot", "bytedance", "liauto",
    "midea", "shanghai ai lab", "hong kong", "unitree",
    "dexmal", "spirit ai", "amap", "openhelix", "microsoft research",
    "beihang", "peking university", "jiao tong university",
    "大学", "研究院", "字节", "清华",
)
ORG_NOISE_PATTERNS = (
    "fig:", "figure", "table", "appendix", "http://", "https://", "www.",
    "our work", "in order", "this paper", "highlights", "potential",
    "outside of", "vision-language-action", "as shown in",
)
ORG_DOMAIN_HINTS = {
    "github.com/amap-cvlab": "AMAP CV Lab",
    "spirit-ai.com": "Spirit AI",
    "dexmal.com": "DexMal",
    "unifolm-vla.github.io": "Unitree",
    "seed.bytedance.com": "ByteDance Seed",
    "bytedance.com": "ByteDance",
    "agibot.com": "AgiBot",
    "li-auto.com": "Li Auto",
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


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "")
    if not re.match(r"^-?\d+(?:\.\d+)?$", s):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _extract_arxiv_id(url):
    m = re.search(r"(\d{4}\.\d{4,6})", url or "")
    return m.group(1) if m else ""


def _extract_paper_id(url):
    aid = _extract_arxiv_id(url)
    if aid:
        return aid
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    m = re.search(r"/([^/?#]+)(?:[?#].*)?$", u)
    if not m:
        return ""
    tail = m.group(1).strip()
    tail = re.sub(r"\.pdf$", "", tail, flags=re.I)
    tail = re.sub(r"[^a-zA-Z0-9._-]+", "-", tail).strip("-")
    return tail[:80]


def _http_get_json(url, timeout=20):
    if (not Request) or (not urlopen):
        return None, "urllib_unavailable"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ClawdBot/1.0)"})
    try:
        with urlopen(req, timeout=timeout) as rsp:
            raw = rsp.read().decode("utf-8", errors="replace")
        return json.loads(raw), ""
    except HTTPError as e:
        return None, "http_%s" % (getattr(e, "code", "error"))
    except Exception as e:
        return None, str(e)[:200]


def _http_get_text(url, timeout=20):
    if (not Request) or (not urlopen):
        return "", "urllib_unavailable"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ClawdBot/1.0)"})
    try:
        with urlopen(req, timeout=timeout) as rsp:
            raw = rsp.read().decode("utf-8", errors="replace")
        return raw, ""
    except HTTPError as e:
        return "", "http_%s" % (getattr(e, "code", "error"))
    except Exception as e:
        return "", str(e)[:200]


def _run(cmd, timeout=120):
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
            cwd=WORKDIR,
            env=env,
        )
        return int(p.returncode), (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 125, "", str(e)


def _is_nonfatal_moltbot_warning(rc, out, err):
    try:
        rc_i = int(rc or 0)
    except Exception:
        rc_i = 0
    if rc_i == 0:
        return False
    raw = ((err or "") + "\n" + (out or "")).strip()
    if not raw:
        return False
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    if not lines:
        return False
    keep = []
    for ln in lines:
        low = ln.lower()
        if "failed to discover alibaba cloud models" in low:
            continue
        if "alibaba cloud models discovery failed" in low:
            continue
        keep.append(ln)
    return len(keep) == 0


def _extract_json_text(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        json.loads(raw)
        return raw
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.S)
    if m:
        try:
            json.loads(m.group(1))
            return m.group(1)
        except Exception:
            pass
    i = raw.find("{")
    j = raw.rfind("}")
    if i != -1 and j != -1 and j > i:
        cand = raw[i:j + 1]
        try:
            json.loads(cand)
            return cand
        except Exception:
            pass
    i = raw.find("[")
    j = raw.rfind("]")
    if i != -1 and j != -1 and j > i:
        cand = raw[i:j + 1]
        try:
            json.loads(cand)
            return cand
        except Exception:
            pass
    return None


def _load_org_cache():
    obj = _read_json(ORG_CACHE_PATH, {})
    if not isinstance(obj, dict):
        return {}
    if isinstance(obj.get("paper_org_cache"), dict):
        return dict(obj.get("paper_org_cache") or {})
    return dict(obj)


def _save_org_cache(cache):
    if not isinstance(cache, dict):
        return
    _write_json(ORG_CACHE_PATH, {
        "updated_at": _today(),
        "paper_org_cache": cache,
    })


def _paper_cache_key(paper_url):
    aid = _extract_arxiv_id(paper_url)
    if aid:
        return "arxiv:%s" % aid
    u = (paper_url or "").strip()
    if u:
        return "url:%s" % re.sub(r"#.*$", "", u)[:200]
    return ""


def _candidate_dedup_key(item):
    if not isinstance(item, dict):
        return ""
    paper_url = (item.get("paper_url") or "").strip()
    key = _paper_cache_key(paper_url)
    if key:
        return key
    paper_id = (item.get("paper_id") or "").strip()
    if paper_id:
        return "paper:%s" % paper_id
    model = (item.get("model") or "").strip().lower()
    if model:
        return "model:%s" % re.sub(r"\s+", " ", model)
    return ""


def _cache_entry_unpack(raw):
    if isinstance(raw, dict):
        return {
            "org": (raw.get("org") or "").strip(),
            "source": (raw.get("source") or "").strip(),
            "confidence": (raw.get("confidence") or "").strip().lower(),
            "updated_at": (raw.get("updated_at") or "").strip(),
        }
    if isinstance(raw, str):
        return {
            "org": raw.strip(),
            "source": "legacy",
            "confidence": "high" if raw.strip() else "low",
            "updated_at": "",
        }
    return {"org": "", "source": "", "confidence": "", "updated_at": ""}


def _cache_entry_pack(org, source, confidence, day):
    return {
        "org": (org or "").strip(),
        "source": (source or "").strip(),
        "confidence": (confidence or "").strip().lower(),
        "updated_at": (day or "").strip(),
    }


def _clean_org_text(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+\d+\s+", " / ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"^[\d\s,.;:†*#\\-]+", "", s)
    s = s.replace("\\thepa", "").replace("thepa", "").strip(" ,.;:")
    if (not s) or (len(s) < 3):
        return ""
    if len(s) > 140:
        return ""
    return s


def _looks_like_org_text(s):
    t = _clean_org_text(s)
    if not t:
        return False
    low = t.lower()
    if any(x in low for x in ORG_NOISE_PATTERNS):
        return False
    if not any(k in low for k in ORG_KEYWORDS):
        return False
    # Most affiliation lines are short noun phrases.
    if len(t.split()) > 14:
        return False
    if len(t) > 100:
        return False
    return True


def _split_affiliation_parts(s):
    parts = re.split(r"(?:^|[;,])\s*\d+\s*", s or "")
    out = []
    for p in parts:
        if not p:
            continue
        out.extend(re.split(r"\s+\d+\s+", p))
    if not out:
        out = [s or ""]
    return out


def _is_reasonable_org_value(v):
    s = (v or "").strip()
    if not s:
        return True
    parts = [x.strip() for x in s.split("/") if x.strip()]
    if not parts:
        return True
    for p in parts[:3]:
        if _looks_like_org_text(p):
            return True
    return False


def _normalize_org_value(v):
    s = (v or "").strip()
    if not s:
        return ""
    parts = [x.strip() for x in s.split("/") if x.strip()]
    out = []
    seen = set()
    for p in parts:
        t = _clean_org_text(p)
        if not t:
            continue
        if not _looks_like_org_text(t):
            continue
        lt = t.lower()
        if lt in seen:
            continue
        seen.add(lt)
        out.append(t)
    return " / ".join(out[:2])


def _extract_orgs_from_arxiv_html(html_text):
    if not html_text:
        return []
    m = re.search(r"<div class=\"ltx_authors\"[\s\S]*?<div class=\"ltx_abstract\">", html_text, re.I)
    block = m.group(0) if m else html_text[:22000]
    cands = []

    # Template 1: explicit affiliation spans.
    for raw in re.findall(r"ltx_contact\s+ltx_role_affiliation[^>]*>([\s\S]*?)</span>", block, re.I):
        t = re.sub(r"<[^>]+>", " ", raw)
        t = _html.unescape(t)
        if _looks_like_org_text(t):
            t = _clean_org_text(t)
            cands.append(t)

    # Template 2: affiliation lines mixed with superscripts and <br>.
    block_lines = re.sub(r"<br\s*/?>", "\n", block, flags=re.I)
    block_lines = re.sub(r"<[^>]+>", " ", block_lines)
    block_lines = _html.unescape(block_lines).replace("\r", "\n")
    for ln in block_lines.split("\n"):
        s = re.sub(r"\s+", " ", ln).strip()
        if not s:
            continue
        low = s.lower()
        if not any(k in low for k in ORG_KEYWORDS):
            continue
        parts = _split_affiliation_parts(s)
        for p in parts:
            if _looks_like_org_text(p):
                t = _clean_org_text(p)
                cands.append(t)

    # Template 3 fallback: broader prefix scan for rare HTML layouts.
    if not cands:
        abstract_idx = html_text.lower().find("ltx_abstract")
        prefix = html_text[: (abstract_idx + 9000 if abstract_idx > 0 else 26000)]
        prefix = re.sub(r"<br\s*/?>", "\n", prefix, flags=re.I)
        prefix = re.sub(r"<[^>]+>", " ", prefix)
        prefix = _html.unescape(prefix).replace("\r", "\n")
        for ln in prefix.split("\n"):
            s = re.sub(r"\s+", " ", ln).strip()
            if not s:
                continue
            if not any(k in s.lower() for k in ORG_KEYWORDS):
                continue
            parts = _split_affiliation_parts(s)
            for p in parts:
                if _looks_like_org_text(p):
                    t = _clean_org_text(p)
                    cands.append(t)

    out = []
    seen = set()
    for x in cands:
        t = _clean_org_text(x)
        if not t:
            continue
        lt = t.lower()
        if lt in seen:
            continue
        if lt in ("original paper", "paper", "arxiv"):
            continue
        seen.add(lt)
        out.append(t)
    return out[:4]


def _guess_org_from_domain(paper_url):
    u = (paper_url or "").strip()
    if (not u) or (not urlparse):
        return ""
    try:
        p = urlparse(u)
        full = ((p.netloc or "") + (p.path or "")).lower()
    except Exception:
        return ""
    for key, val in ORG_DOMAIN_HINTS.items():
        if key in full:
            return val
    return ""


def _resolve_org(model, paper_url, org_cache, warnings):
    aid = _extract_arxiv_id(paper_url)
    key = _paper_cache_key(paper_url)
    day = _today()

    if key and (key in org_cache):
        cached = _cache_entry_unpack(org_cache.get(key))
        cached_org = _normalize_org_value(cached.get("org"))
        cached_conf = (cached.get("confidence") or "").strip().lower()
        if cached_org and cached_conf == "high":
            org_cache[key] = _cache_entry_pack(
                cached_org,
                cached.get("source") or "cache",
                "high",
                cached.get("updated_at") or day,
            )
            return cached_org
        if cached_org and cached_conf in ("medium", "low"):
            # Strict mode: only high confidence can be used.
            return ""
        if not _is_reasonable_org_value(cached.get("org")):
            try:
                del org_cache[key]
            except Exception:
                pass

    org = ""
    source = ""
    confidence = ""
    if aid:
        html_url = "https://arxiv.org/html/%s" % aid
        html_text, err = _http_get_text(html_url, timeout=16)
        if err:
            warnings.append("org_fetch_failed:%s:%s" % (aid, err))
        else:
            orgs = _extract_orgs_from_arxiv_html(html_text)
            if orgs:
                org = " / ".join(orgs[:2])
                source = "heuristic_arxiv_html"
                confidence = "high"
    if (not org) and paper_url:
        org = _guess_org_from_domain(paper_url)
        if org:
            source = "heuristic_domain"
            confidence = "high"

    # Final fallback: well-known model -> org static mapping.
    if (not org) and model:
        lm = model.lower()
        for pattern, known_org in KNOWN_MODEL_ORG:
            if pattern in lm:
                org = known_org
                source = "known_model_map"
                confidence = "high"
                break

    # Normalize heuristic-extracted orgs, but skip for known_model_map
    # (human-curated values that don't necessarily contain academic keywords).
    if source != "known_model_map":
        org = _normalize_org_value(org)
    if key:
        org_cache[key] = _cache_entry_pack(
            org,
            source or "heuristic",
            confidence or ("high" if org else "low"),
            day,
        )
    if confidence == "high":
        return org
    return ""


def _build_qwen_org_prompt(day, candidates):
    lines = []
    lines.append("你是机构识别助手。请根据给定条目，补全模型对应的团队/机构名称。")
    lines.append("只返回 JSON，不要 markdown，不要解释。")
    lines.append("")
    lines.append("规则:")
    lines.append("1) 不要编造。无法高置信判断时，org 置空且 confidence=low。")
    lines.append("2) confidence 仅可为 high / medium / low。")
    lines.append("3) 仅在你非常确定时给 high。")
    lines.append("4) org 只写机构名，多个机构用 ' / ' 分隔。")
    lines.append("")
    lines.append("输出 schema:")
    lines.append("{\"date\":\"%s\",\"results\":[{\"key\":\"...\",\"org\":\"...\",\"confidence\":\"high|medium|low\",\"evidence\":\"...\"}]}" % day)
    lines.append("")
    lines.append("待补全条目:")
    for c in candidates:
        lines.append("- key: %s" % (c.get("key") or ""))
        lines.append("  benchmark: %s | split: %s | model: %s" % (
            c.get("benchmark") or "",
            c.get("split") or "",
            c.get("model") or "",
        ))
        lines.append("  paper_id: %s" % (c.get("paper_id") or ""))
        lines.append("  paper_url: %s" % (c.get("paper_url") or ""))
    return "\n".join(lines).strip()


def _call_qwen_org_batch(day, candidates, timeout=120):
    msg = _build_qwen_org_prompt(day, candidates)
    cmd = [
        "node", NODE, "agent",
        "--agent", QWEN_AGENT_ID,
        "--session-id", "%s-%s" % (QWEN_SESSION_ID, day),
        "--message", msg,
        "--json",
        "--timeout", str(timeout),
    ]
    rc, out, err = _run(cmd, timeout=timeout + 45)
    if (rc != 0) and (not _is_nonfatal_moltbot_warning(rc, out, err)):
        return False, {"error": "qwen_cmd_failed", "rc": rc, "stderr": (err or "")[:280]}

    js = _extract_json_text(out)
    if not js:
        return False, {"error": "qwen_agent_json_not_found", "stdout": (out or "")[:280], "stderr": (err or "")[:180]}
    try:
        obj = json.loads(js)
    except Exception as e:
        return False, {"error": "qwen_agent_json_parse_failed", "detail": str(e)[:180]}

    text = ""
    try:
        text = ((((obj.get("result") or {}).get("payloads") or [{}])[0].get("text")) or "")
    except Exception:
        text = ""
    if not text.strip():
        return False, {"error": "qwen_empty_payload_text"}

    model_json = _extract_json_text(text)
    if not model_json:
        return False, {"error": "qwen_model_json_not_found", "text_head": text[:260]}
    try:
        payload = json.loads(model_json)
    except Exception as e:
        return False, {"error": "qwen_model_json_parse_failed", "detail": str(e)[:180]}

    if not isinstance(payload, dict):
        return False, {"error": "qwen_payload_not_dict"}
    results = payload.get("results") or []
    if not isinstance(results, list):
        return False, {"error": "qwen_results_not_list"}
    return True, {"results": results}


def _collect_missing_org_targets(current_records, focus_top5):
    targets = {}

    def _add_ref(item):
        if not isinstance(item, dict):
            return
        org = (item.get("org") or "").strip()
        if org:
            return
        key = _candidate_dedup_key(item)
        if not key:
            return
        tgt = targets.get(key)
        if not tgt:
            tgt = {
                "key": key,
                "benchmark": (item.get("benchmark") or "").strip(),
                "split": (item.get("split") or "").strip(),
                "model": (item.get("model") or "").strip(),
                "paper_id": (item.get("paper_id") or "").strip(),
                "paper_url": (item.get("paper_url") or "").strip(),
                "refs": [],
            }
            targets[key] = tgt
        tgt["refs"].append(item)
        if (not tgt.get("paper_id")) and item.get("paper_id"):
            tgt["paper_id"] = (item.get("paper_id") or "").strip()
        if (not tgt.get("paper_url")) and item.get("paper_url"):
            tgt["paper_url"] = (item.get("paper_url") or "").strip()

    for r in (current_records or []):
        _add_ref(r)
    if isinstance(focus_top5, dict):
        for entry in focus_top5.values():
            if not isinstance(entry, dict):
                continue
            for grp in (entry.get("groups") or []):
                if not isinstance(grp, dict):
                    continue
                for r in (grp.get("rows") or []):
                    _add_ref(r)
    return list(targets.values())


def _fill_missing_org_with_qwen(day, current_records, focus_top5, org_cache, warnings):
    stats = {
        "qwen_candidates": 0,
        "qwen_filled_high": 0,
        "qwen_rejected_low_or_medium": 0,
        "qwen_errors": 0,
    }
    targets = _collect_missing_org_targets(current_records, focus_top5)
    stats["qwen_candidates"] = len(targets)
    if not targets:
        return stats

    # Keep prompt size bounded.
    batch = targets[:30]
    ok, data = _call_qwen_org_batch(day, batch, timeout=120)
    if not ok:
        warnings.append("qwen_org_fill_failed:%s" % (data.get("error") or "unknown"))
        stats["qwen_errors"] += 1
        stats["qwen_rejected_low_or_medium"] = len(batch)
        return stats

    result_map = {}
    malformed = 0
    for it in (data.get("results") or []):
        if not isinstance(it, dict):
            malformed += 1
            continue
        key = (it.get("key") or "").strip()
        if not key:
            malformed += 1
            continue
        result_map[key] = it
    if malformed:
        stats["qwen_errors"] += malformed
        warnings.append("qwen_org_fill_malformed_items:%s" % malformed)

    filled = set()
    for t in batch:
        key = t.get("key") or ""
        res = result_map.get(key) or {}
        conf = (res.get("confidence") or "").strip().lower()
        if conf != "high":
            continue
        org = _normalize_org_value(res.get("org") or "")
        if not org:
            continue
        for ref in (t.get("refs") or []):
            ref["org"] = org
        cache_key = _paper_cache_key(t.get("paper_url") or "")
        if cache_key:
            org_cache[cache_key] = _cache_entry_pack(org, "qwen", "high", day)
        filled.add(key)

    stats["qwen_filled_high"] = len(filled)
    stats["qwen_rejected_low_or_medium"] = max(0, len(batch) - len(filled))
    return stats


def _iter_rank_lists(slug, obj):
    # CALVIN shape: {split: {group: [rows]}}
    # Others shape: {group: [rows]}
    if not isinstance(obj, dict):
        return
    if slug == "calvin":
        for split_key, group_obj in obj.items():
            if not isinstance(group_obj, dict):
                continue
            for group_key, rows in group_obj.items():
                if isinstance(rows, list):
                    yield split_key, group_key, rows
        return
    for group_key, rows in obj.items():
        if isinstance(rows, list):
            yield "", group_key, rows


def _format_split(slug, split_key, group_key):
    if slug == "calvin":
        return SPLIT_MAP.get((split_key or "").lower(), split_key or "")
    g = (group_key or "").strip().replace("_", "-")
    return g


def _pick_metric(row, benchmark):
    prefs = METRIC_PREF.get(benchmark) or ["average", "score", "success_rate", "avg_len"]
    for key in prefs:
        val = _to_float(row.get(key))
        if val is not None:
            return key, val
    for key in row.keys():
        if key in ("rank", "is_standard", "is_opensource", "is_rl", "policy_setting"):
            continue
        val = _to_float(row.get(key))
        if val is not None:
            return key, val
    return "", None


def _build_current_records(day, org_cache):
    records = []
    warnings = []
    focus_top5 = {}
    fetched_ok = set()
    for src in DATA_SOURCES:
        url = RAW_BASE + "/" + src["path"]
        obj, err = _http_get_json(url, timeout=20)
        if err:
            warnings.append("source_fetch_failed:%s:%s" % (src["slug"], err))
            continue
        fetched_ok.add(src["slug"])
        for split_key, group_key, rows in _iter_rank_lists(src["slug"], obj):
            ranked = [r for r in rows if isinstance(r, dict)]
            if not ranked:
                continue
            ranked.sort(key=lambda x: int(x.get("rank") or 999999))
            split = _format_split(src["slug"], split_key, group_key)

            if src["benchmark"] in FOCUS_TOPK_BENCHMARKS:
                focus_rows = []
                for i, row in enumerate(ranked[:5]):
                    metric_k, metric_v = _pick_metric(row, src["benchmark"])
                    model_k = (row.get("name") or row.get("base_name") or "").strip()
                    if (not model_k) or (not metric_k) or (metric_v is None):
                        continue
                    try:
                        rank_num = int(row.get("rank") or 0)
                    except Exception:
                        rank_num = 0
                    if rank_num <= 0:
                        rank_num = i + 1
                    paper_url_k = (row.get("paper_url") or "").strip()
                    org_k = _resolve_org(model_k, paper_url_k, org_cache, warnings)
                    focus_rows.append({
                        "rank": rank_num,
                        "model": model_k,
                        "metric": metric_k,
                        "value": float(metric_v),
                        "split": split,
                        "paper_id": _extract_paper_id(paper_url_k),
                        "paper_url": paper_url_k,
                        "org": org_k,
                    })
                if focus_rows:
                    bm_entry = focus_top5.setdefault(src["benchmark"], {
                        "benchmark": src["benchmark"],
                        "slug": src["slug"],
                        "leaderboard_url": "https://sota.evomind-tech.com/benchmarks/%s/" % src["slug"],
                        "groups": [],
                    })
                    bm_entry["groups"].append({
                        "group": split or "overall",
                        "rows": focus_rows,
                    })

            top = ranked[0]
            metric, value = _pick_metric(top, src["benchmark"])
            if (not metric) or (value is None):
                continue

            model = (top.get("name") or top.get("base_name") or "").strip()
            if not model:
                continue
            paper_url = (top.get("paper_url") or "").strip()
            org = _resolve_org(model, paper_url, org_cache, warnings)

            baseline = ""
            if len(ranked) > 1:
                second = ranked[1]
                second_name = (second.get("name") or second.get("base_name") or "").strip()
                second_value = _to_float(second.get(metric))
                if second_name:
                    if second_value is not None:
                        baseline = "%s %+.2f" % (second_name, (value - second_value))
                    else:
                        baseline = second_name

            records.append({
                "benchmark": src["benchmark"],
                "split": split,
                "metric": metric,
                "value": float(value),
                "model": model,
                "org": org,
                "paper_id": _extract_paper_id(paper_url),
                "baseline": baseline,
                "date": day,
                "source": "evosota",
                "source_repo": SOURCE_REPO,
                "source_data_path": src["path"],
                "leaderboard_url": "https://sota.evomind-tech.com/benchmarks/%s/" % src["slug"],
                "paper_url": paper_url,
            })
    critical_missing = []
    for slug in CRITICAL_SOURCE_SLUGS:
        if slug not in fetched_ok:
            critical_missing.append(slug)
    return records, warnings, critical_missing, focus_top5


def _load_tracker_rows():
    obj = _read_json(TRACKER_PATH, {})
    rows = obj.get("vla-sota-tracker") or []
    if not isinstance(rows, list):
        rows = []
    return rows


def _build_latest_index(rows):
    out = {}
    cleaned = [r for r in rows if isinstance(r, dict)]
    cleaned.sort(key=lambda x: (
        x.get("date") or "",
        x.get("benchmark") or "",
        x.get("split") or "",
        x.get("metric") or "",
    ))
    for r in cleaned:
        key = (
            (r.get("benchmark") or "").strip(),
            (r.get("split") or "").strip(),
            (r.get("metric") or "").strip(),
        )
        out[key] = r
    return out


def _build_exact_set(rows):
    out = set()
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        bm = (r.get("benchmark") or "").strip()
        sp = (r.get("split") or "").strip()
        mt = (r.get("metric") or "").strip()
        md = (r.get("model") or "").strip()
        vv = _to_float(r.get("value"))
        if (not bm) or (not mt) or (not md) or (vv is None):
            continue
        out.add((bm, sp, mt, md, round(float(vv), 8)))
    return out


def _is_changed(item, latest_idx, exact_set):
    sig = (
        (item.get("benchmark") or "").strip(),
        (item.get("split") or "").strip(),
        (item.get("metric") or "").strip(),
        (item.get("model") or "").strip(),
        round(float(item.get("value") or 0.0), 8),
    )
    if sig in exact_set:
        return False

    key = (
        (item.get("benchmark") or "").strip(),
        (item.get("split") or "").strip(),
        (item.get("metric") or "").strip(),
    )
    old = latest_idx.get(key)
    if not old:
        return True
    old_model = (old.get("model") or "").strip()
    new_model = (item.get("model") or "").strip()
    if old_model != new_model:
        return True
    old_value = _to_float(old.get("value"))
    new_value = _to_float(item.get("value"))
    if (old_value is None) or (new_value is None):
        return True
    if abs(old_value - new_value) > 1e-9:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--out", default="", help="Output path")
    args = ap.parse_args()

    day = (args.date or _today()).strip()
    out = args.out.strip() or os.path.join(TMP_DIR, "vla-sota-candidates-%s.json" % day)
    os.makedirs(TMP_DIR, exist_ok=True)

    org_cache = _load_org_cache()
    current_records, warnings, critical_missing, focus_top5 = _build_current_records(day, org_cache)
    qwen_stats = _fill_missing_org_with_qwen(day, current_records, focus_top5, org_cache, warnings)
    _save_org_cache(org_cache)
    history_rows = _load_tracker_rows()
    latest_idx = _build_latest_index(history_rows)
    exact_set = _build_exact_set(history_rows)

    skip_reason = ""
    direct_items = []
    snapshot_items = []

    # First run: bootstrap baseline only, no alert.
    if not history_rows:
        skip_reason = "bootstrap"
        snapshot_items = current_records
    else:
        for rec in current_records:
            if _is_changed(rec, latest_idx, exact_set):
                direct_items.append(rec)
        if not direct_items:
            skip_reason = "no_changes"

    out_obj = {
        "ok": True,
        "date": day,
        "source": {
            "repo": SOURCE_REPO,
            "raw_base": RAW_BASE,
            "paths": [x["path"] for x in DATA_SOURCES],
        },
        "counts": {
            "history_rows": len(history_rows),
            "current_records": len(current_records),
            "changes": len(direct_items),
            "qwen_candidates": qwen_stats.get("qwen_candidates") or 0,
            "qwen_filled_high": qwen_stats.get("qwen_filled_high") or 0,
            "qwen_rejected_low_or_medium": qwen_stats.get("qwen_rejected_low_or_medium") or 0,
            "qwen_errors": qwen_stats.get("qwen_errors") or 0,
        },
        "current_records": current_records,
        "focus_top5": focus_top5,
        "snapshot_items": snapshot_items,
        "direct_items": direct_items,
        "candidates": [],
        "skip_reason": skip_reason,
        "critical_missing_sources": critical_missing,
        "warnings": warnings,
    }
    if critical_missing:
        out_obj["ok"] = False
        out_obj["skip_reason"] = "critical_source_missing"
        _write_json(out, out_obj)
        print(json.dumps({
            "ok": False,
            "date": day,
            "out": out,
            "error": "critical_source_missing",
            "critical_missing_sources": critical_missing,
            "warnings": len(warnings),
        }, ensure_ascii=False))
        return 1

    _write_json(out, out_obj)
    print(json.dumps({
        "ok": True,
        "date": day,
        "out": out,
        "current_records": len(current_records),
        "changes": len(direct_items),
        "skip_reason": skip_reason,
        "qwen_candidates": qwen_stats.get("qwen_candidates") or 0,
        "qwen_filled_high": qwen_stats.get("qwen_filled_high") or 0,
        "qwen_rejected_low_or_medium": qwen_stats.get("qwen_rejected_low_or_medium") or 0,
        "qwen_errors": qwen_stats.get("qwen_errors") or 0,
        "warnings": len(warnings),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

