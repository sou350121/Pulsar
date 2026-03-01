#!/usr/bin/env python3.11
"""
Semantic Index Builder — P2 #11

Builds/updates a vector index over Pulsar's 60-day memory window.
Uses DashScope text-embedding-v3 (dim=1024) via compatible mode endpoint.

Sources indexed:
  _ai_daily_pick_*.md   — AI App daily curated picks
  _ai_social_*.md       — AI App social intel
  _vla_social_*.md      — VLA social intel
  _biweekly_*.md        — Biweekly reports (VLA + AI App)
  _biweekly_reflection_*.md  — Biweekly reflections
  calibration-check-*.json   — Triggered calibration entries only
  upstream-signals.json — Upstream arxiv signals (last 30 days)

Output:
  memory/semantic-index.json  — Full vector index

Design:
  - Incremental: skips chunks whose source file mtime hasn't changed
  - Batched embedding: up to 25 texts per DashScope request
  - Pure stdlib: no numpy, no sentence-transformers
  - Chunk size: 400 words per chunk (split on section headers first)
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

MEM_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
INDEX_PATH = os.path.join(MEM_DIR, "semantic-index.json")
AUTH_PATH = "/home/admin/.openclaw/agents/reports/agent/auth-profiles.json"
DASHSCOPE_EMBED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
EMBED_MODEL = "text-embedding-v3"
EMBED_DIM = 1024
BATCH_SIZE = 10      # max texts per DashScope request
MAX_WORDS = 400      # max words per chunk before splitting
KEEP_DAYS = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def _cutoff_date(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=days)).strftime("%Y-%m-%d")


def _get_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("alibaba-cloud:default", "alibaba-cloud"):
            v = (d.get("profiles", {}).get(k, {}) or {}).get("key", "").strip()
            if v:
                return v
    except Exception:
        pass
    return ""


def _embed_batch(texts: list[str], api_key: str) -> list[list[float]] | None:
    """Embed a batch of texts. Returns list of embedding vectors or None on failure."""
    payload = json.dumps({
        "model": EMBED_MODEL,
        "input": texts,
        "encoding_format": "float",
    }).encode("utf-8")
    req = Request(DASHSCOPE_EMBED_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        resp = urlopen(req, timeout=60)
        result = json.loads(resp.read().decode("utf-8"))
        items = result.get("data", [])
        # Sort by index to preserve order
        items.sort(key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]
    except Exception as e:
        print(f"[warn] embed batch failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Text extraction and chunking
# ---------------------------------------------------------------------------

def _words(text: str) -> int:
    return len(text.split())


def _chunk_md(text: str, source: str) -> list[dict]:
    """Split markdown by ## headers. Each section → one or more chunks."""
    # Split on ## headers
    sections = re.split(r'\n(?=## )', text.strip())
    chunks = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        # Title from first line
        lines = sec.splitlines()
        title = lines[0].lstrip('#').strip()
        body = '\n'.join(lines[1:]).strip()
        combined = f"{title}\n{body}" if body else title

        if _words(combined) <= MAX_WORDS:
            chunks.append({"text": combined, "section": title})
        else:
            # Split into MAX_WORDS-word blocks
            words = combined.split()
            for i in range(0, len(words), MAX_WORDS):
                block = ' '.join(words[i:i + MAX_WORDS])
                chunks.append({"text": block, "section": f"{title} (part {i//MAX_WORDS + 1})"})
    # Fallback: if no headers found, treat whole file as one/many chunks
    if not chunks:
        words = text.split()
        for i in range(0, len(words), MAX_WORDS):
            block = ' '.join(words[i:i + MAX_WORDS])
            chunks.append({"text": block, "section": f"section_{i//MAX_WORDS}"})
    return chunks


def _extract_date_from_filename(filename: str) -> str:
    """Extract YYYY-MM-DD from filename, or return empty string."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return m.group(1) if m else ""


def _source_type_from_filename(filename: str) -> str:
    name = os.path.basename(filename)
    if "_ai_daily_pick_" in name:     return "ai_daily_pick"
    if "_ai_social_" in name:         return "ai_social"
    if "_vla_social_" in name:        return "vla_social"
    if "_biweekly_reflection_" in name: return "biweekly_reflection"
    if "_biweekly_" in name:          return "vla_biweekly"
    if "calibration-check-" in name:  return "calibration"
    return "other"


def _collect_md_files(cutoff: str) -> list[str]:
    """Return .md files in memory dir within the date cutoff."""
    patterns = [
        "_ai_daily_pick_*.md",
        "_ai_social_*.md",
        "_vla_social_*.md",
        "_biweekly_*.md",
        "_biweekly_reflection_*.md",
    ]
    files = []
    for pat in patterns:
        for path in glob.glob(os.path.join(MEM_DIR, pat)):
            date = _extract_date_from_filename(path)
            if date >= cutoff:
                files.append(path)
    return sorted(set(files))


def _collect_calibration_files(cutoff: str) -> list[str]:
    files = []
    for path in glob.glob(os.path.join(MEM_DIR, "calibration-check-*.json")):
        date = _extract_date_from_filename(path)
        if date >= cutoff:
            files.append(path)
    return sorted(files)


def _chunks_from_md_file(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []
    if not text.strip():
        return []
    date = _extract_date_from_filename(path)
    source_type = _source_type_from_filename(path)
    raw_chunks = _chunk_md(text, path)
    return [
        {
            "id": f"{os.path.basename(path)}_{i}",
            "date": date,
            "source": os.path.basename(path),
            "source_type": source_type,
            "text": c["text"],
            "section": c["section"],
        }
        for i, c in enumerate(raw_chunks)
        if len(c["text"].strip()) > 30  # skip tiny chunks
    ]


def _chunks_from_calibration(path: str) -> list[dict]:
    """Extract triggered calibration entries only."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    date = _extract_date_from_filename(path)
    triggered = d.get("triggers", [])
    if not isinstance(triggered, list):
        triggered = []
    chunks = []
    for i, entry in enumerate(triggered):
        text = (
            f"Calibration {date}: assumption {entry.get('id','')} "
            f"'{entry.get('text','')}' — {entry.get('note','')}"
        )
        if len(text.strip()) > 30:
            chunks.append({
                "id": f"calibration_{date}_{i}",
                "date": date,
                "source": os.path.basename(path),
                "source_type": "calibration",
                "text": text,
                "section": entry.get("id", ""),
            })
    return chunks


def _chunks_from_upstream(cutoff: str) -> list[dict]:
    """Extract upstream signals from upstream-signals.json."""
    path = os.path.join(MEM_DIR, "upstream-signals.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    chunks = []
    for i, sig in enumerate(d.get("signals", [])):
        if sig.get("date", "") < cutoff:
            continue
        kws = ", ".join(sig.get("keywords_matched", [])[:5])
        text = (
            f"Upstream {sig.get('domain','')} signal [{sig.get('source','')}] "
            f"{sig.get('date','')}: {sig.get('title','')}. "
            f"Keywords: {kws}. {sig.get('abstract_snippet','')[:200]}"
        )
        if len(text.strip()) > 30:
            chunks.append({
                "id": f"upstream_{i}_{sig.get('date','')}",
                "date": sig.get("date", ""),
                "source": "upstream-signals.json",
                "source_type": "upstream",
                "text": text,
                "section": sig.get("domain", ""),
            })
    return chunks


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    if not os.path.exists(INDEX_PATH):
        return {"built_at": "", "model": EMBED_MODEL, "dim": EMBED_DIM, "chunks": []}
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"built_at": "", "model": EMBED_MODEL, "dim": EMBED_DIM, "chunks": []}


def _save_index(index: dict) -> None:
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)  # compact — no indent (saves ~40% size)
    os.replace(tmp, INDEX_PATH)


# ---------------------------------------------------------------------------
# Main build logic
# ---------------------------------------------------------------------------

def build(force: bool = False, dry_run: bool = False) -> int:
    api_key = _get_api_key()
    if not api_key:
        print("[error] No DashScope API key found", file=sys.stderr)
        return 1

    cutoff = _cutoff_date(KEEP_DAYS)
    print(f"[builder] date={_today()}, cutoff={cutoff}, force={force}")

    # Load existing index
    index = _load_index()
    existing_ids: set[str] = {c["id"] for c in index.get("chunks", [])}
    # Track source file → mtime for incremental
    existing_sources: dict[str, str] = {}
    for c in index.get("chunks", []):
        src = c.get("source", "")
        if src and src not in existing_sources:
            existing_sources[src] = c.get("_mtime", "")

    # Collect all candidate chunks
    all_chunks: list[dict] = []
    md_files = _collect_md_files(cutoff)
    print(f"[builder] md files: {len(md_files)}")
    for path in md_files:
        mtime = str(os.path.getmtime(path))
        src = os.path.basename(path)
        if not force and existing_sources.get(src) == mtime:
            # Copy existing chunks for this source
            for c in index.get("chunks", []):
                if c.get("source") == src:
                    all_chunks.append(c)
            continue
        chunks = _chunks_from_md_file(path)
        for c in chunks:
            c["_mtime"] = mtime
        all_chunks.extend(chunks)
        print(f"[builder]   {src}: {len(chunks)} chunks (new/updated)")

    cal_files = _collect_calibration_files(cutoff)
    for path in cal_files:
        mtime = str(os.path.getmtime(path))
        src = os.path.basename(path)
        if not force and existing_sources.get(src) == mtime:
            for c in index.get("chunks", []):
                if c.get("source") == src:
                    all_chunks.append(c)
            continue
        chunks = _chunks_from_calibration(path)
        for c in chunks:
            c["_mtime"] = mtime
        all_chunks.extend(chunks)
        if chunks:
            print(f"[builder]   {src}: {len(chunks)} triggered entries")

    upstream_chunks = _chunks_from_upstream(cutoff)
    # Upstream: always refresh (small, no mtime tracking needed)
    all_chunks.extend(upstream_chunks)
    if upstream_chunks:
        print(f"[builder]   upstream-signals.json: {len(upstream_chunks)} signals")

    # Prune chunks outside cutoff
    all_chunks = [c for c in all_chunks if c.get("date", "") >= cutoff]

    # Identify chunks needing embedding (no embedding field or force)
    to_embed = [c for c in all_chunks if force or "embedding" not in c]
    already_embedded = [c for c in all_chunks if not force and "embedding" in c]

    print(f"[builder] total chunks: {len(all_chunks)}, to embed: {len(to_embed)}, cached: {len(already_embedded)}")

    if dry_run:
        print(f"[builder] dry-run: would embed {len(to_embed)} chunks")
        return 0

    # Embed in batches
    embedded: list[dict] = list(already_embedded)
    failed = 0
    for i in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        print(f"[builder] embedding batch {i//BATCH_SIZE + 1}/{(len(to_embed)-1)//BATCH_SIZE + 1} ({len(texts)} texts)...")
        vectors = _embed_batch(texts, api_key)
        if vectors is None:
            # Retry once
            time.sleep(2)
            vectors = _embed_batch(texts, api_key)
        if vectors and len(vectors) == len(batch):
            for chunk, vec in zip(batch, vectors):
                chunk["embedding"] = vec
                embedded.append(chunk)
        else:
            print(f"[warn] batch {i//BATCH_SIZE + 1} failed, skipping {len(batch)} chunks")
            failed += len(batch)
        time.sleep(0.3)  # rate limit courtesy

    print(f"[builder] embedded: {len(embedded)}, failed: {failed}")

    # Save index
    index["built_at"] = datetime.now(timezone.utc).isoformat()
    index["model"] = EMBED_MODEL
    index["dim"] = EMBED_DIM
    index["chunk_count"] = len(embedded)
    index["chunks"] = embedded
    _save_index(index)

    size_kb = os.path.getsize(INDEX_PATH) // 1024
    print(f"[builder] saved: {INDEX_PATH} ({size_kb} KB, {len(embedded)} chunks)")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic Index Builder — P2 #11")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Re-embed all chunks (ignore cache)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be embedded without calling API")
    args = parser.parse_args()
    return build(force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
