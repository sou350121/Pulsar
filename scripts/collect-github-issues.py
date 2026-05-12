#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily GitHub Issues collector for VLA adoption monitoring.

Mechanical only — no LLM calls.  ~60s runtime, ~12 API calls/day.
Fetches issues updated since last run, classifies by category,
detects hardware/robot platforms, merges into append-only index.

Output:
  memory/gh-issues-index.json           (append-only, FIFO at 2000)
  memory/tmp/gh-issues-daily-YYYY-MM-DD.json  (daily snapshot)

Python 3.6+ (no external deps).
"""

from __future__ import print_function

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Inline config import (works on server where scripts/ is cwd) ──────────

try:
    from _gh_issues_config import (
        REPOS, TIER1_REPOS, TIER2_REPOS,
        CATEGORY_PATTERNS, HARDWARE_PATTERNS, ROBOT_PATTERNS,
        API_DELAY_SECONDS, MAX_ISSUES_PER_PAGE, MAX_PAGES,
        INDEX_MAX_ISSUES, BODY_SNIPPET_LENGTH,
        MEMORY_DIR, TMP_DIR, INDEX_PATH, ENV_PATHS,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _gh_issues_config import (
        REPOS, TIER1_REPOS, TIER2_REPOS,
        CATEGORY_PATTERNS, HARDWARE_PATTERNS, ROBOT_PATTERNS,
        API_DELAY_SECONDS, MAX_ISSUES_PER_PAGE, MAX_PAGES,
        INDEX_MAX_ISSUES, BODY_SNIPPET_LENGTH,
        MEMORY_DIR, TMP_DIR, INDEX_PATH, ENV_PATHS,
    )

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:
    print("ERROR: urllib not available", file=sys.stderr)
    sys.exit(1)

TZ_CST = timezone(timedelta(hours=8))

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_token():
    """Load GITHUB_TOKEN from env or .env files."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    for p in ENV_PATHS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("GITHUB_TOKEN="):
                        return s.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    return ""


def _read_json(path, default=None):
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def atomic_write(path, data):
    """Atomic JSON write (POSIX rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(str(tmp), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.rename(path)


def _gh_get(url, token):
    """GET request to GitHub API with auth."""
    req = Request(url)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "pulsar-gh-issues/1.0")
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read().decode("utf-8", errors="replace"))


# ── Classification ────────────────────────────────────────────────────────────


def classify_issue(title, body, labels):
    """Classify issue into category.  First regex match wins."""
    text = (title + " " + (body or "")[:500]).lower()
    # Check labels first for strong signals
    label_set = set(l.lower() for l in labels)
    if "bug" in label_set:
        return "bug"
    if label_set & {"enhancement", "feature request", "feature"}:
        return "feature"
    for cat, pat in CATEGORY_PATTERNS:
        if re.search(pat, text):
            return cat
    return "other"


def detect_hardware(text):
    """Detect hardware platforms from text."""
    hits = []
    for hw, pat in HARDWARE_PATTERNS.items():
        if re.search(pat, text):
            hits.append(hw)
    return hits


def detect_robots(text):
    """Detect robot platforms from text."""
    hits = []
    for rb, pat in ROBOT_PATTERNS.items():
        if re.search(pat, text):
            hits.append(rb)
    return hits


# ── Collection ────────────────────────────────────────────────────────────────


def fetch_issues(owner, repo, since, token):
    """Fetch issues updated since `since` (ISO datetime string).
    Returns list of raw API issue objects (PRs excluded).
    """
    all_issues = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            "https://api.github.com/repos/%s/%s/issues"
            "?state=all&since=%s&per_page=%d&sort=updated&direction=desc&page=%d"
            % (owner, repo, since, MAX_ISSUES_PER_PAGE, page)
        )
        try:
            items = _gh_get(url, token)
        except HTTPError as e:
            print("  WARN: HTTP %d fetching %s/%s page %d" % (e.code, owner, repo, page),
                  file=sys.stderr)
            break
        except (URLError, Exception) as e:
            print("  WARN: %s fetching %s/%s page %d" % (e, owner, repo, page),
                  file=sys.stderr)
            break
        # Filter out pull requests
        issues = [i for i in items if "pull_request" not in i]
        all_issues.extend(issues)
        if len(items) < MAX_ISSUES_PER_PAGE:
            break  # last page
        time.sleep(API_DELAY_SECONDS)
    return all_issues


def build_record(raw, repo_short):
    """Transform raw GitHub issue into our index record."""
    title = raw.get("title", "")
    body = raw.get("body", "") or ""
    labels = [l["name"] for l in raw.get("labels", [])]
    text = title + " " + body[:1000]

    return {
        "url": raw["html_url"],
        "repo": repo_short,
        "number": raw["number"],
        "title": title,
        "state": raw["state"],
        "category": classify_issue(title, body, labels),
        "hardware": detect_hardware(text),
        "robots": detect_robots(text),
        "labels": labels,
        "comments_count": raw.get("comments", 0),
        "created_at": raw.get("created_at", ""),
        "updated_at": raw.get("updated_at", ""),
        "closed_at": raw.get("closed_at"),
        "body_snippet": body[:BODY_SNIPPET_LENGTH].replace("\r\n", "\n"),
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    t0 = time.time()
    today = datetime.now(TZ_CST).strftime("%Y-%m-%d")
    api_calls = 0

    # 1. Load token
    token = _load_token()
    if not token:
        print("ERROR: no GITHUB_TOKEN found", file=sys.stderr)
        sys.exit(1)

    # 2. Load existing index
    index = _read_json(INDEX_PATH, {
        "version": 1,
        "last_updated": "",
        "last_fetched": {},
        "total_issues": 0,
        "issues": {},
    })
    issues = index.get("issues", {})
    last_fetched = index.get("last_fetched", {})

    # Stats tracking
    new_count = 0
    updated_count = 0
    new_records = []
    updated_records = []
    by_repo = {}

    # 3. Determine which repos to collect
    #    --all flag or weekday=Saturday → collect all repos
    #    otherwise → tier-1 only (daily)
    collect_all = "--all" in sys.argv or datetime.now(TZ_CST).weekday() == 5  # Saturday
    active_repos = REPOS if collect_all else TIER1_REPOS
    print("Mode: %s (%d repos)" % ("all" if collect_all else "tier-1 daily", len(active_repos)))

    # For each repo, fetch updated issues
    for rc in active_repos:
        owner, repo, short = rc["owner"], rc["repo"], rc["short"]
        since = last_fetched.get(short, "")
        if not since:
            # First run: look back 7 days
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        print("Fetching %s/%s since %s ..." % (owner, repo, since[:10]))
        raw_issues = fetch_issues(owner, repo, since, token)
        api_calls += min(len(raw_issues) // MAX_ISSUES_PER_PAGE + 1, MAX_PAGES)

        repo_new = 0
        repo_updated = 0

        for raw in raw_issues:
            rec = build_record(raw, short)
            url = rec["url"]
            if url in issues:
                # Update existing
                old = issues[url]
                old_comments = old.get("comments_count", 0)
                rec["first_seen"] = old.get("first_seen", today)
                issues[url] = rec
                if rec["comments_count"] != old_comments or rec["state"] != old.get("state"):
                    repo_updated += 1
                    updated_records.append({
                        "url": url, "repo": short, "number": rec["number"],
                        "title": rec["title"], "comments_count": rec["comments_count"],
                        "prev_comments_count": old_comments,
                    })
            else:
                rec["first_seen"] = today
                issues[url] = rec
                repo_new += 1
                new_records.append(rec)

        new_count += repo_new
        updated_count += repo_updated
        by_repo[short] = {"new": repo_new, "updated": repo_updated}

        # Update last_fetched to now
        last_fetched[short] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        print("  %s: +%d new, %d updated (total %d from this repo)" % (
            short, repo_new, repo_updated,
            sum(1 for v in issues.values() if v.get("repo") == short)
        ))
        time.sleep(API_DELAY_SECONDS)

    # 4. FIFO cap
    if len(issues) > INDEX_MAX_ISSUES:
        # Sort by first_seen, drop oldest
        sorted_urls = sorted(issues.keys(), key=lambda u: issues[u].get("first_seen", ""))
        drop = len(issues) - INDEX_MAX_ISSUES
        for url in sorted_urls[:drop]:
            del issues[url]
        print("FIFO: dropped %d oldest issues (cap=%d)" % (drop, INDEX_MAX_ISSUES))

    # 5. Compute category and hardware stats
    cat_counts = {}
    hw_counts = {}
    robot_counts = {}
    for rec in new_records:
        cat_counts[rec["category"]] = cat_counts.get(rec["category"], 0) + 1
        for hw in rec.get("hardware", []):
            hw_counts[hw] = hw_counts.get(hw, 0) + 1
        for rb in rec.get("robots", []):
            robot_counts[rb] = robot_counts.get(rb, 0) + 1

    # 6. Write index
    index["last_updated"] = today
    index["last_fetched"] = last_fetched
    index["total_issues"] = len(issues)
    index["issues"] = issues
    atomic_write(INDEX_PATH, index)

    # 7. Write daily snapshot
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = TMP_DIR / ("gh-issues-daily-%s.json" % today)
    daily = {
        "date": today,
        "stats": {
            "new_issues": new_count,
            "updated_issues": updated_count,
            "by_repo": by_repo,
            "by_category": cat_counts,
            "hardware_mentions": hw_counts,
            "robot_mentions": robot_counts,
            "api_calls": api_calls,
            "runtime_seconds": round(time.time() - t0, 1),
        },
        "new_issues_list": new_records,
        "updated_issues_list": updated_records,
    }
    atomic_write(daily_path, daily)

    # 8. Summary
    elapsed = round(time.time() - t0, 1)
    print("\n=== GitHub Issues Collection Complete ===")
    print("Date: %s | New: %d | Updated: %d | Index: %d | API calls: %d | Time: %ss" % (
        today, new_count, updated_count, len(issues), api_calls, elapsed
    ))
    for short, counts in sorted(by_repo.items()):
        print("  %s: +%d new, %d updated" % (short, counts["new"], counts["updated"]))
    if cat_counts:
        print("  Categories: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(cat_counts.items())))
    if hw_counts:
        print("  Hardware: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(hw_counts.items())))


if __name__ == "__main__":
    main()
