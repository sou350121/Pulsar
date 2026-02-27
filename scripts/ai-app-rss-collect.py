#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI App RSS Collector (stable-source collector).

Writes:
  /home/admin/clawd/memory/ai-app-rss-YYYY-MM-DD.json

Design goals:
  - Deterministic, low-dependency (Python 3.6+, no external libs)
  - Best-effort: per-source status recorded; partial success is OK
  - Output schema compatible with downstream tasks (keywords_matched/source_status/items)

Changelog:
  2026-02-27: Add tophub.today scraping (/c/developer + /c/tech) via POST API.
              Uses /node-items-by-date endpoint; no external libs (curl POST).
  2026-02-23: Add pub_date parsing (pubDate/published/updated) to all items.
              This enables downstream date-filtering to reject stale articles.
              HuggingFace blog RSS returns 180+ articles including items from 2024;
              without pub_date the agent cannot enforce the 72h/30d recency rule.
"""

from __future__ import print_function

import datetime as _dt
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


MEM_DIR = "/home/admin/clawd/memory"
ACTIVE_CONFIG_PATH = os.path.join(MEM_DIR, "ai-app-active-config.json")
AI_DAILY_PATH = os.path.join(MEM_DIR, "ai-app-daily.json")


# ---- Sources ---------------------------------------------------------------

FEEDS_RSS = [
    ("producthunt", "https://www.producthunt.com/feed"),
    ("hn", "https://hnrss.org/newest?points=50"),
    ("hf-blog", "https://huggingface.co/blog/feed.xml"),

    # Blogs (best-effort; some may redirect or block)
    ("blog-simonwillison", "https://simonwillison.net/atom/everything/"),
    ("blog-minimaxir", "https://minimaxir.com/index.xml"),
    ("blog-lilianweng", "https://lilianweng.github.io/feed.xml"),
    ("blog-karpathy", "https://karpathy.github.io/feed.xml"),
    ("blog-openai", "https://openai.com/blog/rss.xml"),
    ("blog-anthropic-eng", "https://www.anthropic.com/engineering/rss.xml"),
    ("blog-deepmind", "https://deepmind.com/blog/rss.xml"),
    ("blog-google-research", "https://research.google/blog/rss/"),
    ("blog-qwen", "https://qwen.ai/feed.xml"),
    ("blog-together-ai", "https://www.together.ai/blog/rss.xml"),
    ("blog-aws-ai", "https://aws.amazon.com/blogs/machine-learning/feed/"),
    ("blog-bair", "https://bair.berkeley.edu/blog/feed.xml"),
    ("blog-stanford-ai", "https://ai.stanford.edu/blog/rss.xml"),
    ("blog-langchain", "https://blog.langchain.dev/rss/"),
    ("blog-qdrant", "https://qdrant.tech/blog/rss.xml"),
    ("blog-weaviate", "https://weaviate.io/blog/rss.xml"),
    ("blog-replicate", "https://replicate.com/blog.atom"),
    ("blog-vercel", "https://vercel.com/blog/rss.xml"),
    ("blog-supabase", "https://supabase.com/blog/rss.xml"),
    ("blog-cloudflare", "https://blog.cloudflare.com/rss/"),

    # Papers TL;DR feed (as a general AI signal source)
    ("blog-hf-papers", "https://papers.takara.ai/api/feed"),
]

REDDIT_FEEDS = [
    ("reddit-LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA/.rss"),
    ("reddit-ClaudeAI", "https://www.reddit.com/r/ClaudeAI/.rss"),
]

# Tophub nodes: POST /node-items-by-date?p=1&date=YYYY-MM-DD&nodeid=N
# Covers /c/developer (掘金, 开源中国, 人人都是产品经理) and
#         /c/tech     (IT之家, 虎嗅网, 36氪, Readhub)
# Node IDs verified 2026-02-27 via the AJAX API (sitename cross-checked).
TOPHUB_NODES = {
    100: "tophub-juejin",    # 掘金  (/c/developer)
    96:  "tophub-juejin-b",  # 掘金 热榜  (/c/developer)
    310: "tophub-oschina",   # 开源中国  (/c/developer)
    213: "tophub-woshipm",   # 人人都是产品经理  (/c/developer)
    119: "tophub-ithome",    # IT之家  (/c/tech)
    32:  "tophub-huxiu",     # 虎嗅网  (/c/tech)
    345: "tophub-36kr",      # 36氪  (/c/tech)
    209: "tophub-readhub",   # Readhub  (/c/tech)
}

GH_RELEASE_REPOS = [
    "langchain-ai/langchain",
    "run-llama/llama_index",
    "microsoft/autogen",
    "crewAIInc/crewAI",
    "langgenius/dify",
    "open-webui/open-webui",
    "BerriAI/litellm",
    "vercel/ai",
    "langfuse/langfuse",
    "promptfoo/promptfoo",
]

# RFC 822 month abbreviations
_MONTHS_RFC822 = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _now_shanghai():
    return _dt.datetime.utcnow() + _dt.timedelta(hours=8)


def _today():
    return _now_shanghai().strftime("%Y-%m-%d")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path, obj):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_tags(s):
    if not s:
        return ""
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#39;", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_pub_date(s):
    """Normalize RSS/Atom date strings to YYYY-MM-DD, or return '' on failure.

    Handles:
      - ISO 8601:  2026-02-23T07:15:00Z  ->  2026-02-23
      - RFC 822:   Mon, 23 Feb 2026 07:15:00 +0800  ->  2026-02-23
      - Date-only: 2026-02-23  ->  2026-02-23
    """
    if not s:
        return ""
    s = s.strip()
    # ISO 8601 / date-only: starts with YYYY-MM-DD
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    # RFC 822: [Weekday,] DD Mon YYYY ...
    m = re.match(r"(?:\w+,\s+)?(\d{1,2})\s+(\w{3})\s+(\d{4})", s)
    if m:
        day = int(m.group(1))
        mon = _MONTHS_RFC822.get(m.group(2).lower(), "")
        year = m.group(3)
        if mon:
            return "%s-%s-%02d" % (year, mon, day)
    return ""


def _curl_fetch(url, timeout_sec=25):
    cmd = ["/usr/bin/curl", "-fsSL", "--max-time", str(int(timeout_sec)), url]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        if not err:
            err = "curl_exit_%s" % p.returncode
        if "403" in err:
            return None, "http_403"
        if "404" in err:
            return None, "http_404"
        if "308" in err:
            return None, "http_308"
        return None, err[:200]
    text = p.stdout or ""
    if not text.strip():
        return "", None
    return text, None


def _tophub_post(nodeid, date, page=1):
    """POST to tophub /node-items-by-date. Returns (items_list, error_str|None)."""
    body = "p=%d&date=%s&nodeid=%d" % (page, date, int(nodeid))
    cmd = [
        "/usr/bin/curl", "-fsSL", "--max-time", "20",
        "-X", "POST",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-H", "X-Requested-With: XMLHttpRequest",
        "-H", "Referer: https://tophub.today/",
        "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "--data", body,
        "https://tophub.today/node-items-by-date",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode != 0:
        return [], "curl_exit_%d" % p.returncode
    try:
        resp = json.loads(p.stdout)
        items = (resp.get("data") or {}).get("items") or []
        return items, None
    except Exception as e:
        return [], "json_err:%s" % str(e)[:60]


_NS_ATOM = "http://www.w3.org/2005/Atom"


def _parse_feed_xml(xml_text):
    """Parse RSS/Atom feed XML; each item includes pub_date (YYYY-MM-DD or '')."""
    items = []
    if not xml_text or not xml_text.strip():
        return items
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        try:
            root = ET.fromstring(xml_text.lstrip("\ufeff \t\r\n"))
        except Exception:
            return items

    # RSS 2.0: <channel><item>...
    for node in root.findall(".//item"):
        title = _strip_tags((node.findtext("title") or "").strip())
        link = (node.findtext("link") or "").strip()
        desc = _strip_tags(node.findtext("description") or "")
        # Parse pubDate (RSS) or dc:date
        pub_raw = (node.findtext("pubDate") or
                   node.findtext("{http://purl.org/dc/elements/1.1/}date") or "")
        pub_date = _parse_pub_date(pub_raw)
        if not link:
            continue
        items.append({"title": title or link, "url": link, "summary": desc, "pub_date": pub_date})

    # Atom 1.0: <feed><entry>...
    for node in root.findall(".//{%s}entry" % _NS_ATOM):
        title = _strip_tags((node.findtext("{%s}title" % _NS_ATOM) or "").strip())
        link = ""
        for lnk in node.findall("{%s}link" % _NS_ATOM):
            href = (lnk.get("href") or "").strip()
            rel = (lnk.get("rel") or "alternate").strip()
            if href and (rel == "alternate"):
                link = href
                break
            if href and not link:
                link = href
        summary = _strip_tags(node.findtext("{%s}summary" % _NS_ATOM) or "")
        if not summary:
            summary = _strip_tags(node.findtext("{%s}content" % _NS_ATOM) or "")
        # Parse published (prefer) or updated
        pub_raw = (node.findtext("{%s}published" % _NS_ATOM) or
                   node.findtext("{%s}updated" % _NS_ATOM) or "")
        pub_date = _parse_pub_date(pub_raw)
        if not link:
            continue
        items.append({"title": title or link, "url": link, "summary": summary, "pub_date": pub_date})

    return items


def _parse_github_trending(html_text):
    items = []
    if not html_text:
        return items
    rows = re.split(r"<article[^>]*class=\"[^\"]*Box-row[^\"]*\"[^>]*>", html_text)
    for row in rows[1:60]:
        m = re.search(r'href=\"/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\"', row)
        if not m:
            continue
        repo = m.group(1)
        url = "https://github.com/" + repo
        desc = ""
        md = re.search(r"<p[^>]*class=\"[^\"]*col-9[^\"]*\"[^>]*>(.*?)</p>", row, flags=re.S)
        if md:
            desc = _strip_tags(md.group(1))
        # GitHub trending has no publish date; use today as approximation
        items.append({"title": repo, "url": url, "summary": desc, "pub_date": _today()})
    return items


def _load_keywords():
    cfg = _read_json(ACTIVE_CONFIG_PATH, {})
    kw_a = [k for k in (cfg.get("keywords_A") or []) if isinstance(k, str) and k.strip()]
    kw_b = [k for k in (cfg.get("keywords_B") or []) if isinstance(k, str) and k.strip()]
    return kw_a, kw_b


def _load_already_covered_set(today):
    urls = set()
    titles = set()
    obj = _read_json(AI_DAILY_PATH, {})
    rows = obj.get("ai_app_daily") if isinstance(obj, dict) else []
    if not isinstance(rows, list):
        return urls, titles
    recent = rows[-7:]
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        for it in (rec.get("items") or []):
            if not isinstance(it, dict):
                continue
            u = _norm(it.get("url", ""))
            t = _norm(it.get("title") or it.get("name") or "")
            if u:
                urls.add(u)
            if t:
                titles.add(t)
    return urls, titles


def _match_keywords(title, summary, kw_a, kw_b):
    blob = (_norm(title) + " " + _norm(summary)).strip()
    matched_a = []
    matched_b = []
    for kw in kw_a:
        k = _norm(kw)
        if k and (k in blob):
            matched_a.append(kw)
    if matched_a:
        return "A", matched_a
    for kw in kw_b:
        k = _norm(kw)
        if k and (k in blob):
            matched_b.append(kw)
    if matched_b:
        return "B", matched_b
    return None, []


def main():
    today = _today()
    out_path = os.path.join(MEM_DIR, "ai-app-rss-%s.json" % today)

    # Skip if already collected today
    if os.path.exists(out_path):
        print("[progress] ai-app-rss-collect start: %s" % today)
        print("[progress] already collected, skip")
        return 0

    print("[progress] ai-app-rss-collect start: %s" % today)

    kw_a, kw_b = _load_keywords()
    covered_urls, covered_titles = _load_already_covered_set(today)

    source_status = {}
    raw_total = 0
    kept = []

    # 1) RSS/Atom feeds
    for name, url in FEEDS_RSS + REDDIT_FEEDS:
        text, err = _curl_fetch(url, timeout_sec=25)
        if err is not None:
            source_status[name] = "failed:%s" % err
            continue
        items = _parse_feed_xml(text)
        source_status[name] = "ok"
        raw_total += len(items)
        for it in items:
            title = (it.get("title") or "").strip()
            link = (it.get("url") or "").strip()
            summ = (it.get("summary") or "").strip()
            pub_date = it.get("pub_date", "")
            if not link:
                continue
            lvl, matched = _match_keywords(title, summ, kw_a, kw_b)
            if not lvl:
                continue
            nu = _norm(link)
            nt = _norm(title)
            already = (nu in covered_urls) or (nt and (nt in covered_titles))
            kept.append(
                {
                    "title": title or link,
                    "url": link,
                    "source": name,
                    "match_level": lvl,
                    "keywords_matched": matched,
                    "already_covered": bool(already),
                    "pub_date": pub_date,
                    "summary_snippet": (summ[:240] if summ else ""),
                }
            )

    # 2) GitHub trending (HTML scrape)
    html, err = _curl_fetch("https://github.com/trending", timeout_sec=25)
    if err is not None:
        source_status["gh-trending"] = "failed:%s" % err
    else:
        source_status["gh-trending"] = "ok"
        items = _parse_github_trending(html)
        raw_total += len(items)
        for it in items:
            title = (it.get("title") or "").strip()
            link = (it.get("url") or "").strip()
            summ = (it.get("summary") or "").strip()
            pub_date = it.get("pub_date", "")
            if not link:
                continue
            lvl, matched = _match_keywords(title, summ, kw_a, kw_b)
            if not lvl:
                continue
            nu = _norm(link)
            nt = _norm(title)
            already = (nu in covered_urls) or (nt and (nt in covered_titles))
            kept.append(
                {
                    "title": title or link,
                    "url": link,
                    "source": "gh-trending",
                    "match_level": lvl,
                    "keywords_matched": matched,
                    "already_covered": bool(already),
                    "pub_date": pub_date,
                    "summary_snippet": (summ[:240] if summ else ""),
                }
            )

    # 3) GitHub releases (Atom feeds)
    for repo in GH_RELEASE_REPOS:
        src = "gh-release:%s" % repo
        url = "https://github.com/%s/releases.atom" % repo
        text, err = _curl_fetch(url, timeout_sec=25)
        if err is not None:
            source_status[src] = "failed:%s" % err
            continue
        source_status[src] = "ok"
        items = _parse_feed_xml(text)
        raw_total += len(items)
        for it in items:
            title = (it.get("title") or "").strip()
            link = (it.get("url") or "").strip()
            summ = (it.get("summary") or "").strip()
            pub_date = it.get("pub_date", "")
            if not link:
                continue
            lvl, matched = _match_keywords(title, summ, kw_a, kw_b)
            if not lvl:
                continue
            nu = _norm(link)
            nt = _norm(title)
            already = (nu in covered_urls) or (nt and (nt in covered_titles))
            kept.append(
                {
                    "title": title or link,
                    "url": link,
                    "source": src,
                    "match_level": lvl,
                    "keywords_matched": matched,
                    "already_covered": bool(already),
                    "pub_date": pub_date,
                    "summary_snippet": (summ[:240] if summ else ""),
                }
            )

    # 4) Tophub (/c/developer + /c/tech) via POST API
    for nodeid, src_name in TOPHUB_NODES.items():
        items_raw, err = _tophub_post(nodeid, today)
        if err is not None:
            source_status[src_name] = "failed:%s" % err
            continue
        source_status[src_name] = "ok:%d" % len(items_raw)
        raw_total += len(items_raw)
        for it in items_raw:
            title = (it.get("title") or "").strip()
            link = (it.get("url") or "").strip()
            summ = _strip_tags(it.get("description") or "")
            if not link or not title:
                continue
            lvl, matched = _match_keywords(title, summ, kw_a, kw_b)
            if not lvl:
                continue
            nu = _norm(link)
            nt = _norm(title)
            already = (nu in covered_urls) or (nt and (nt in covered_titles))
            kept.append({
                "title": title,
                "url": link,
                "source": src_name,
                "match_level": lvl,
                "keywords_matched": matched,
                "already_covered": bool(already),
                "pub_date": today,
                "summary_snippet": summ[:240] if summ else "",
            })

    # Dedup by URL; two-pass cap so tophub items are never squeezed out by RSS volume.
    # Pass 1: non-tophub sources (RSS, GitHub) — up to 250 items.
    # Pass 2: tophub sources — up to 50 more (total cap 300).
    seen_url = set()
    out_items = []
    for it in kept:
        if "tophub" in (it.get("source") or ""):
            continue
        u = _norm(it.get("url"))
        if not u or (u in seen_url):
            continue
        seen_url.add(u)
        out_items.append(it)
        if len(out_items) >= 250:
            break
    for it in kept:
        if "tophub" not in (it.get("source") or ""):
            continue
        u = _norm(it.get("url"))
        if not u or (u in seen_url):
            continue
        seen_url.add(u)
        out_items.append(it)
        if len(out_items) >= 300:
            break

    payload = {
        "tag": "ai-app-rss-%s" % today,
        "date": today,
        "source_status": source_status,
        "total_fetched": int(raw_total),
        "after_filter": int(len(out_items)),
        "items": out_items,
    }
    _write_json_atomic(out_path, payload)

    ok_any = any((v == "ok") for v in source_status.values())
    if not ok_any:
        sys.stdout.write("WARN: ai-app-rss-collect: all feeds failed\n")
    print("[progress] ai-app-rss-collect done: total_fetched=%d after_filter=%d" % (raw_total, len(out_items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
