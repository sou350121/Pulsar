#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VLA RSS Collector (low-token pipeline)

Outputs:
- Writes /home/admin/clawd/memory/vla-rss-YYYY-MM-DD.json
- Stdout is EMPTY on success (silent).
- Stdout prints ONE warning line only when ALL feeds fail.

Python: 3.6+ (no external dependencies)
"""

from __future__ import print_function

import base64
import datetime
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


MEM_DIR = "/home/admin/clawd/memory"

FEEDS = [
    # arXiv
    ("cs.RO", "https://rss.arxiv.org/rss/cs.RO"),
    ("cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("cs.CV", "https://rss.arxiv.org/rss/cs.CV"),
    ("cs.LG", "https://rss.arxiv.org/rss/cs.LG"),
    ("hf-papers", "https://papers.takara.ai/api/feed"),
    # Nature
    ("Nature", "https://www.nature.com/nature.rss"),
    ("Nature-MI", "https://www.nature.com/natmachintell.rss"),
    ("npj-Robotics", "https://www.nature.com/npjrobot.rss"),
    ("Nature-Comms", "https://www.nature.com/ncomms.rss"),
    # Science
    ("Science-Robotics", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=scirobotics"),
    ("Science-Advances", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv"),
    ("Science", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science"),
    # Cell
    ("Cell", "https://www.cell.com/cell/current.rss"),
    ("Cell-InPress", "https://www.cell.com/cell/inpress.rss"),
]

# Journal feeds ranked before arXiv (peer-reviewed > preprint)
SOURCE_PRIORITY = [
    "hf-papers",
    "npj-Robotics", "Nature-MI", "Science-Robotics",
    "Nature", "Nature-Comms", "Science-Advances", "Science", "Cell", "Cell-InPress",
    "cs.RO", "cs.AI", "cs.CV", "cs.LG",
]

A_KEYWORDS_DEFAULT = [
    "VLA",
    "vision-language-action",
    "OpenVLA",
    "embodied AI",
    "robot manipulation",
    "robot learning",
    "visuomotor",
    "action chunking",
    "diffusion policy",
    "sim-to-real",
    "imitation learning",
    "robot policy",
    "foundation model robot",
    "vision language action",
    "embodied intelligence",
    "robotic manipulation",
]

B_KEYWORDS_DEFAULT = [
    "robot grasping",
    "dexterous",
    "humanoid control",
    "locomotion",
    "world model",
    "reinforcement learning robot",
    "MuJoCo",
    "Isaac Sim",
    "behavior cloning",
    "language-conditioned",
    "cross-embodiment",
    "Open X-Embodiment",
    "action tokenization",
    "robot foundation model",
    "embodied agent",
    "tactile",
    "bimanual",
    "mobile manipulation",
]


def _load_keywords_from_config(config_path=None):
    """Load keywords_A and keywords_B from active-config.json.
    Falls back to hardcoded defaults if file is missing or malformed.
    Closes the loop: self-reflection → active-config → RSS filtering.
    """
    if config_path is None:
        config_path = os.path.join(MEM_DIR, "active-config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        a = cfg.get("keywords_A") or []
        b = cfg.get("keywords_B") or []
        if isinstance(a, list) and len(a) >= 3 and isinstance(b, list) and len(b) >= 3:
            return a, b
    except Exception:
        pass
    return A_KEYWORDS_DEFAULT, B_KEYWORDS_DEFAULT



def _now_shanghai():
    # Asia/Shanghai is UTC+8, no DST.
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def _today_str():
    return _now_shanghai().strftime("%Y-%m-%d")


def _is_weekend_shanghai():
    # Monday=0..Sunday=6
    return _now_shanghai().weekday() >= 5


def _safe_mkdir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except TypeError:
        # Python 3.6 compat for exist_ok (still supported), keep fallback
        if not os.path.isdir(path):
            os.makedirs(path)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _strip_tags(s):
    if not s:
        return ""
    # Remove CDATA
    s = re.sub(r"<!\\[CDATA\\[(.*?)\\]\\]>", r"\\1", s, flags=re.S)
    # Drop tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Unescape basic entities
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#39;", "'")
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def _extract_arxiv_id(url):
    if not url:
        return ""
    m = re.search(r"arxiv\\.org/(abs|pdf)/([0-9]{4}\\.[0-9]{4,5})(v\\d+)?", url)
    if m:
        return m.group(2)
    m = re.search(r"arxiv\\.org/(abs|pdf)/([a-z\\-]+/[0-9]{7})(v\\d+)?", url)
    if m:
        return m.group(2)
    # takara tldr links sometimes embed arxiv id in path
    m = re.search(r"/p/([0-9]{4}\\.[0-9]{4,5})", url)
    if m:
        return m.group(1)
    return ""


def _norm_title(t):
    t = (t or "").strip().lower()
    t = re.sub(r"\\s+", " ", t)
    return t


def _match_keywords(blob_lc, keywords):
    matched = []
    for kw in keywords:
        k = kw.lower()
        if k and (k in blob_lc):
            matched.append(kw)
    return matched


def _curl_fetch(url, timeout_sec=25):
    # -L follow redirects; -s silent; -S show errors; -f fail on HTTP errors.
    cmd = ["/usr/bin/curl", "-fsSL", "--max-time", str(int(timeout_sec)), url]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except Exception as e:
        return None, "exception: %s" % (str(e),)
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        if not err:
            err = "curl_exit_%s" % p.returncode
        return None, err
    text = p.stdout or ""
    if not text.strip():
        return "", None
    return text, None


# Namespace constants for multi-format RSS support
_NS_RSS1   = "http://purl.org/rss/1.0/"
_NS_ATOM   = "http://www.w3.org/2005/Atom"
_NS_DC     = "http://purl.org/dc/elements/1.1/"
_NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"
_NS_RDF    = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _parse_rss_xml(xml_text, source_name):
    items = []
    if not xml_text or not xml_text.strip():
        return items
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        # Some feeds may have leading whitespace/BOM; try to clean
        try:
            xml_text2 = xml_text.lstrip("\ufeff \t\r\n")
            root = ET.fromstring(xml_text2)
        except Exception:
            return items

    # RSS 2.0: <item>; Atom: <entry>; RSS 1.0 (Nature/RDF): <{RSS1_NS}item>
    nodes = root.findall(".//item")
    if not nodes:
        nodes = (root.findall(".//{%s}entry" % _NS_ATOM)
                 or root.findall(".//entry"))
    if not nodes:
        nodes = root.findall(".//{%s}item" % _NS_RSS1)

    for n in nodes:
        title = ""
        link = ""
        desc = ""
        authors = ""

        # title: plain → Atom → RSS 1.0
        for tag in ["title", "{%s}title" % _NS_ATOM, "{%s}title" % _NS_RSS1]:
            tnode = n.find(tag)
            if tnode is not None and tnode.text:
                title = _strip_tags(tnode.text)
                break

        # link: plain → Atom href → RSS 1.0 → rdf:about fallback
        lnode = n.find("link")
        if lnode is not None:
            href = lnode.attrib.get("href")
            if href:
                link = href.strip()
            elif lnode.text:
                link = lnode.text.strip()
        if not link:
            lnode = n.find("{%s}link" % _NS_ATOM)
            if lnode is not None:
                link = (lnode.attrib.get("href") or lnode.text or "").strip()
        if not link:
            lnode = n.find("{%s}link" % _NS_RSS1)
            if lnode is not None and lnode.text:
                link = lnode.text.strip()
        if not link:
            # RSS 1.0: rdf:about attribute on <item> carries the canonical URL
            link = n.attrib.get("{%s}about" % _NS_RDF, "")

        # description: plain → Atom summary/content → RSS 1.0 → content:encoded
        for tag in [
            "description",
            "{%s}summary" % _NS_ATOM,
            "{%s}content" % _NS_ATOM,
            "{%s}description" % _NS_RSS1,
            "{%s}encoded" % _NS_CONTENT,
        ]:
            dnode = n.find(tag)
            if dnode is not None:
                raw = dnode.text or ET.tostring(dnode, encoding="unicode")
                desc = _strip_tags(raw)
                if desc:
                    break

        # authors: dc:creator (Nature journals emit multiple; take all, "et al." normalize)
        creators = n.findall("{%s}creator" % _NS_DC)
        if creators:
            names = [c.text for c in creators if c.text]
            if names:
                authors = names[0] + (" et al." if len(names) > 1 else "")
        if not authors:
            anode = n.find("{%s}author" % _NS_ATOM)
            if anode is not None:
                name_node = anode.find("{%s}name" % _NS_ATOM)
                if name_node is not None and name_node.text:
                    authors = _strip_tags(name_node.text)

        # arXiv RSS description often contains "Authors:" line
        if (not authors) and desc:
            m = re.search(r"\\bAuthors?:\\s*([^\\.]+)", desc)
            if m:
                authors = m.group(1).strip()

        # Normalize authors to "First et al."
        authors_out = ""
        if authors:
            parts = [p.strip() for p in re.split(r",|;| and ", authors) if p.strip()]
            if parts:
                authors_out = parts[0]
                if len(parts) > 1:
                    authors_out += " et al."

        if not title or not link:
            continue

        abstract_snippet = (desc or "")[:120].strip()

        items.append({
            "title": title,
            "authors": authors_out,
            "url": link,
            "source": source_name,
            "abstract": desc or "",
            "abstract_snippet": abstract_snippet,
        })

    return items


def _load_hotspots_covered(max_days=7):
    path = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
    if not os.path.exists(path):
        return set(), set()
    try:
        obj = _read_json(path)
    except Exception:
        return set(), set()
    items = obj.get("reported_papers") or []
    today = _now_shanghai().date()
    titles = set()
    arxiv_ids = set()
    for it in items:
        d = (it.get("date") or "").strip()
        if not d:
            continue
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if (today - dt).days > max_days:
            continue
        t = _norm_title(it.get("title") or "")
        if t:
            titles.add(t)
        aid = _extract_arxiv_id(it.get("url") or "")
        if aid:
            arxiv_ids.add(aid)
    return titles, arxiv_ids


def main():
    _safe_mkdir(MEM_DIR)
    today = _today_str()
    out_path = os.path.join(MEM_DIR, "vla-rss-%s.json" % today)
    if os.path.exists(out_path):
        # Idempotent: already collected today.
        return 0

    weekend = _is_weekend_shanghai()

    feed_status = {}
    fail_reasons = {}
    all_items = []
    fetched_total = 0
    ok_any = False

    for name, url in FEEDS:
        if weekend and name.startswith("cs."):
            feed_status[name] = "empty"
            continue

        txt, err = _curl_fetch(url, timeout_sec=25)
        if err is not None:
            feed_status[name] = "failed"
            fail_reasons[name] = err
            continue
        if txt is None:
            feed_status[name] = "failed"
            fail_reasons[name] = "unknown"
            continue
        if not txt.strip():
            feed_status[name] = "empty"
            continue

        parsed = _parse_rss_xml(txt, name)
        if parsed:
            feed_status[name] = "ok"
            ok_any = True
            fetched_total += len(parsed)
            all_items.extend(parsed)
        else:
            # xml exists but parse produced nothing: treat as empty
            feed_status[name] = "empty"

    # If all feeds failed (not empty): alert
    failed_all = True
    for name, _ in FEEDS:
        st = feed_status.get(name, "failed")
        if st != "failed":
            failed_all = False
            break
    if failed_all:
        reasons = []
        for name, _ in FEEDS:
            reasons.append("%s=%s" % (name, fail_reasons.get(name, "failed")))
        print("⚠️ RSS 全部抓取失敗，日報可能缺少論文數據。失敗原因：%s" % ("; ".join(reasons),))
        return 0

    # Filtering
    a_kw, b_kw = _load_keywords_from_config()  # reads active-config.json, falls back to defaults

    covered_titles, covered_arxiv_ids = _load_hotspots_covered(max_days=7)

    matched_A = []
    matched_B = []
    for it in all_items:
        title = it.get("title") or ""
        abstract = it.get("abstract") or ""
        blob = (title + " " + abstract).lower()
        title_lc = title.lower()

        hitA = _match_keywords(blob, a_kw)
        if hitA:
            lvl = "A"
            kws = hitA
        else:
            hitB = _match_keywords(title_lc, b_kw)
            if not hitB:
                continue
            lvl = "B"
            kws = hitB

        aid = _extract_arxiv_id(it.get("url") or "")
        already = False
        if aid and aid in covered_arxiv_ids:
            already = True
        if _norm_title(title) in covered_titles:
            already = True

        out_it = {
            "title": title,
            "authors": it.get("authors") or "",
            "url": it.get("url") or "",
            "source": it.get("source") or "",
            "match_level": lvl,
            "keywords_matched": kws,
            "already_covered": bool(already),
            "abstract_snippet": (it.get("abstract_snippet") or "")[:120],
        }

        if lvl == "A":
            matched_A.append(out_it)
        else:
            matched_B.append(out_it)

    def prio(src):
        try:
            return SOURCE_PRIORITY.index(src)
        except Exception:
            return len(SOURCE_PRIORITY)

    matched_A.sort(key=lambda x: prio(x.get("source") or ""))
    matched_B.sort(key=lambda x: prio(x.get("source") or ""))

    if len(matched_A) > 30:
        papers = matched_A[:30]
    else:
        papers = matched_A + matched_B

    out = {
        "date": today,
        "feed_status": feed_status,
        "total_fetched": int(fetched_total),
        "after_filter": int(len(papers)),
        "papers": papers,
        "generated_at": _now_shanghai().isoformat(),
    }

    _write_json(out_path, out)

    # Silent success: print nothing.
    return 0


if __name__ == "__main__":
    sys.exit(main())

