#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic two-phase runner for VLA Daily Hotspots.

Flow:
1) vla-rss-collect.py  -> Fetch RSS feeds, filter by keywords, dedup -> vla-rss-YYYY-MM-DD.json
2) Merge new papers into vla-daily-hotspots.json

No LLM generation is used. Pure deterministic pipeline.

Stdout: Progress messages + final summary
"""

from __future__ import print_function

import argparse
import datetime as _dt
import json
import os
import sys

from _heartbeat_run import run_with_heartbeat


RSS_COLLECT = "/home/admin/clawd/scripts/vla-rss-collect.py"
MEM_DIR = "/home/admin/clawd/memory"
WORKDIR = "/home/admin"


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


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _norm_title(title):
    if not title:
        return ""
    t = title.lower().strip()
    t = " ".join(t.split())
    return t


def _extract_arxiv_id(url):
    if not url:
        return None
    import re
    m = re.search(r"arxiv\.org/abs/(\d+\.\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"arxiv\.org/pdf/(\d+\.\d+)", url)
    if m:
        return m.group(1)
    return None


def main():
    parser = argparse.ArgumentParser(description="VLA Daily Hotspots two-phase runner")
    parser.add_argument("--no-web", action="store_true", help="Disable web search (for cron)")
    args = parser.parse_args()

    day = _today()
    print("[progress] VLA Daily Hotspots | day=%s" % day)

    # Phase 1: Run RSS collection
    print("[progress] Phase 1: RSS collection...")
    rss_out_path = os.path.join(MEM_DIR, "vla-rss-%s.json" % day)
    
    # Check if already collected today
    if os.path.exists(rss_out_path):
        print("[progress] RSS already collected for today, skipping collection")
    else:
        rc, out, err = _run(
            ["python3", RSS_COLLECT],
            timeout=180,
            label="vla-daily/rss-collect"
        )
        if rc != 0:
            print("[error] RSS collection failed: rc=%d" % rc)
            if err:
                print("[error] stderr: %s" % (err[:500] if err else ""))
            return 1
        if out and "⚠️" in out:
            # All feeds failed warning
            print("[warn] %s" % out.strip())

    # Load RSS results
    if not os.path.exists(rss_out_path):
        print("[error] RSS output file not found: %s" % rss_out_path)
        return 1

    rss_data = _load_json(rss_out_path)
    papers = rss_data.get("papers") or []
    feed_status = rss_data.get("feed_status") or {}
    total_fetched = rss_data.get("total_fetched", 0)
    after_filter = rss_data.get("after_filter", 0)
    # Compute feed stats early so Phase 3 Telegram message can include them.
    ok_feeds = sum(1 for v in feed_status.values() if v == "ok")
    total_feeds = len(feed_status)

    print("[progress] Phase 1 complete: fetched=%d, filtered=%d" % (total_fetched, after_filter))

    # Phase 2: Merge into hotspots
    print("[progress] Phase 2: Merging into hotspots...")
    hotspots_path = os.path.join(MEM_DIR, "vla-daily-hotspots.json")
    
    # Load existing hotspots
    if os.path.exists(hotspots_path):
        hotspots = _load_json(hotspots_path)
    else:
        hotspots = {"reported_papers": [], "last_updated": None}

    existing_titles = set()
    existing_arxiv_ids = set()
    for p in hotspots.get("reported_papers") or []:
        t = _norm_title(p.get("title"))
        if t:
            existing_titles.add(t)
        aid = _extract_arxiv_id(p.get("url"))
        if aid:
            existing_arxiv_ids.add(aid)

    # Add new papers
    new_count = 0
    for p in papers:
        title = p.get("title") or ""
        url = p.get("url") or ""
        
        # Skip if already covered
        norm_t = _norm_title(title)
        arxiv_id = _extract_arxiv_id(url)
        
        if arxiv_id and arxiv_id in existing_arxiv_ids:
            continue
        if norm_t and norm_t in existing_titles:
            continue

        # Create hotspots entry
        entry = {
            "title": title,
            "date": day,
            "url": url,
            "source": p.get("source", "unknown"),
            "tag": "actionable" if p.get("match_level") == "A" else "read-only",
            "repo_url": "",
            "abstract_snippet": p.get("abstract_snippet", ""),
        }
        hotspots["reported_papers"].insert(0, entry)
        new_count += 1

        if arxiv_id:
            existing_arxiv_ids.add(arxiv_id)
        if norm_t:
            existing_titles.add(norm_t)

    hotspots["last_updated"] = _dt.datetime.now().astimezone().isoformat()

    # Keep only recent papers (last 90 days)
    today_dt = _dt.datetime.now().astimezone().date()
    filtered_papers = []
    for p in hotspots.get("reported_papers") or []:
        p_date = p.get("date", "")
        try:
            dt = _dt.datetime.strptime(p_date, "%Y-%m-%d").date()
            if (today_dt - dt).days <= 90:
                filtered_papers.append(p)
        except Exception:
            filtered_papers.append(p)
    hotspots["reported_papers"] = filtered_papers

    _write_json(hotspots_path, hotspots)
    print("[progress] Phase 2 complete: new_papers=%d, total_in_hotspots=%d" % (new_count, len(hotspots["reported_papers"])))

    # Phase 2.5: Expert LLM rating of today's new papers (qwen-max)
    today_papers = [p for p in hotspots.get("reported_papers", []) if p.get("date") == day][:new_count]
    rated_papers = today_papers  # fallback if rating fails
    rating_meta = {}
    if new_count > 0:
        print("[progress] Phase 2.5: LLM rating %d papers with %s..." % (new_count, "qwen3.5-plus"))
        import tempfile
        tmp_in = os.path.join(MEM_DIR, "tmp", "vla-daily-rating-in-%s.json" % day)
        tmp_out = os.path.join(MEM_DIR, "tmp", "vla-daily-rating-out-%s.json" % day)
        os.makedirs(os.path.dirname(tmp_in), exist_ok=True)
        try:
            with open(tmp_in, "w", encoding="utf-8") as f:
                json.dump(today_papers, f, ensure_ascii=False)
            RATE_SCRIPT = "/home/admin/clawd/scripts/rate-vla-daily.py"
            # Skip re-rating if output already exists (e.g. pipeline re-run same day)
            if os.path.exists(tmp_out):
                print("[progress] Phase 2.5: rating-out already exists, reusing.")
                rc, out, err = 0, "", ""
            else:
                rc, out, err = _run(
                    ["python3", RATE_SCRIPT,
                     "--papers-file", tmp_in,
                     "--output-file", tmp_out],
                    timeout=600,
                    label="vla-daily/rating",
                )
            if rc == 0 and os.path.exists(tmp_out):
                with open(tmp_out, "r", encoding="utf-8") as f:
                    rating_result = json.load(f)
                if rating_result.get("ok"):
                    rated_papers = rating_result.get("papers", today_papers)
                    rating_meta = rating_result.get("counts", {})
                    # Persist ratings back into hotspots memory
                    slug_map = {p.get("title", ""): p for p in rated_papers}
                    for hp in hotspots.get("reported_papers", []):
                        if hp.get("date") == day:
                            rp = slug_map.get(hp.get("title", ""))
                            if rp:
                                hp["rating"] = rp.get("rating", "")
                                hp["reason"] = rp.get("reason", "")
                                hp["affiliation"] = rp.get("affiliation", "")
                    _write_json(hotspots_path, hotspots)
                    print("[progress] Phase 2.5: ratings ⚡=%d 🔧=%d 📖=%d ❌=%d" % (
                        rating_meta.get("⚡", 0), rating_meta.get("🔧", 0),
                        rating_meta.get("📖", 0), rating_meta.get("❌", 0)))
                else:
                    print("[warn] Phase 2.5: rating script returned ok=false")
            else:
                print("[warn] Phase 2.5: rating failed rc=%d, using fallback" % rc)
        except Exception as e:
            print("[warn] Phase 2.5: exception: %s" % str(e)[:150])

    # Phase 3: Deliver rated papers to Telegram (best-effort; failures don't abort).
    tg_ok = False
    tg_msg_id = ""
    if new_count > 0:
        print("[progress] Phase 3: Building Telegram notification...")
        # Partition by rating
        strategic  = [p for p in rated_papers if p.get("rating") == "⚡"]
        actionable = [p for p in rated_papers if p.get("rating") == "🔧"]
        archive    = [p for p in rated_papers if p.get("rating") == "📖"]
        filtered   = [p for p in rated_papers if p.get("rating") == "❌"]
        # If rating didn't run (all papers unrated), fall back to old flat list
        all_unrated = all(not p.get("rating") for p in rated_papers)

        lines = ["📄 VLA 今日精选 | %s" % day, ""]
        if all_unrated:
            # Fallback: keyword-filtered flat list (rating not yet available)
            VLA_KW = ["robot", "vla", "manipulation", "embodied", "visuomotor",
                      "grasping", "grasp", "humanoid", "locomotion", "dexterous",
                      "imitation", "teleoperation", "action chunk", "policy",
                      "end-effector", "sim-to-real", "tactile", "loco",
                      "vision-language", "latent action", "bimanual", "keypoint"]
            def _is_vla(p):
                text = (p.get("title","") + " " + p.get("abstract_snippet","")).lower()
                return any(kw in text for kw in VLA_KW)
            vla_papers = [p for p in rated_papers if _is_vla(p)]
            noise_count = len(rated_papers) - len(vla_papers)
            for i, p in enumerate(vla_papers[:10], 1):
                title = (p.get("title") or "").strip()
                url   = (p.get("url") or "").strip()
                lines.append("📌 %d. %s" % (i, title[:85]))
                if url:
                    lines.append("   %s" % url)
            suffix = "… 等共 %d 篇" % len(vla_papers)
            if noise_count:
                suffix += "（已過濾 %d 篇非VLA）" % noise_count
            if len(vla_papers) > 10 or noise_count:
                lines.append(suffix)
            lines.append("_評分進行中，排版待更新_")
            # Write fallback flag so watchdog can re-push when rating appears
            _fallback_flag = os.path.join(MEM_DIR, "tmp", "_vla_fallback_%s" % day)
            try:
                open(_fallback_flag, "w").write("1")
            except Exception:
                pass
        else:
            def _paper_line(p, idx=None):
                title       = (p.get("title") or "").strip()
                url         = (p.get("url") or "").strip()
                reason      = (p.get("reason") or "").strip()
                affiliation = (p.get("affiliation") or "").strip()
                # Affiliation badge first, then full title (no mid-word cut)
                prefix = (affiliation + " ") if affiliation else ""
                # Trim URL: strip https:// for compactness
                short_url = url.replace("https://", "").replace("http://", "") if url else ""
                num = ("%d. " % idx) if idx is not None else ""
                line = num + prefix + title
                if reason:
                    line += "\n   " + reason
                if short_url:
                    line += "\n   " + short_url
                return line

            if strategic:
                lines.append("⚡ 战略级（%d 篇）" % len(strategic))
                lines.append("")
                for i, p in enumerate(strategic, 1):
                    lines.append(_paper_line(p, i))
                    lines.append("")
                lines.append("")
            if actionable:
                lines.append("🔧 值得跟（%d 篇）" % len(actionable))
                lines.append("")
                for i, p in enumerate(actionable, 1):
                    lines.append(_paper_line(p, i))
                    lines.append("")
                lines.append("")
            # Split archive into clean 📖 and 💧灌水
            shuishui = [p for p in archive if "💧" in (p.get("reason") or "")]
            clean_archive = [p for p in archive if "💧" not in (p.get("reason") or "")]
            if clean_archive:
                titles_str = "、".join(
                    (p.get("title") or "").strip()[:28] for p in clean_archive[:5]
                )
                if len(clean_archive) > 5:
                    titles_str += " 等"
                lines.append("📖 存档（%d 篇）：%s" % (len(clean_archive), titles_str))
            if shuishui:
                sw_titles = "、".join(
                    (p.get("title") or "").strip()[:28] for p in shuishui[:4]
                )
                if len(shuishui) > 4:
                    sw_titles += " 等"
                lines.append("💧 灌水识别（%d 篇）：%s" % (len(shuishui), sw_titles))
            if filtered:
                lines.append("❌ 过滤（%d 篇关键词误命中）" % len(filtered))

            # Filter funnel stats
            lines.append("")
            _shuishui_count = sum(1 for p in rated_papers if "💧" in (p.get("reason") or ""))
            lines.append("📊 漏斗：%d 来源 → %d 相关 → %d 精选%s | Feeds %d/%d ok | 累计 %d 篇" % (
                new_count,
                len(strategic) + len(actionable) + len(archive),
                len(strategic) + len(actionable),
                (" | 💧%d" % _shuishui_count if _shuishui_count else ""),
                ok_feeds, total_feeds,
                len(hotspots["reported_papers"]),
            ))

        if not all_unrated and not (strategic or actionable or archive):
            # All filtered out — still send a brief notice
            lines = [
                "📄 VLA 今日 | %s" % day,
                "今日 %d 篇全部为关键词误命中，已过滤。" % new_count,
                "📊 Feeds %d/%d ok" % (ok_feeds, total_feeds),
            ]

        msg_text = "\n".join(lines)
        tmp_msg = os.path.join(MEM_DIR, "tmp", "vla-daily-tg-%s.txt" % day)
        os.makedirs(os.path.dirname(tmp_msg), exist_ok=True)
        try:
            with open(tmp_msg, "w", encoding="utf-8") as f:
                f.write(msg_text)
            MB = "/home/admin/.local/share/pnpm/moltbot"
            rc, out, err = _run(
                [MB, "message", "send", "--channel", "telegram",
                 "--account", "original", "--target", "1898430254",
                 "--message", msg_text],
                timeout=30,
                label="vla-daily/telegram",
            )
            tg_ok = (rc == 0)
            tg_msg_id = out.strip()[:80] if out else ""
            if tg_ok:
                print("[progress] Phase 3: Telegram sent ok")
            else:
                print("[warn] Phase 3: Telegram send failed rc=%d" % rc)
        except Exception as e:
            print("[warn] Phase 3: Telegram exception: %s" % str(e)[:100])
    else:
        print("[progress] Phase 3: no new papers, skipping Telegram")
        tg_ok = True  # not a failure

    # Summary
    import json as _json
    result = {
        "ok": True,
        "date": day,
        "new_papers": new_count,
        "total_in_hotspots": len(hotspots["reported_papers"]),
        "feeds_ok": "%d/%d" % (ok_feeds, total_feeds),
        "telegram": {"ok": tg_ok, "msg_id": tg_msg_id},
    }
    print("[summary] VLA Daily Hotspots | day=%s | feeds=%d/%d ok | new=%d | total=%d | tg=%s" % (
        day, ok_feeds, total_feeds, new_count, len(hotspots["reported_papers"]),
        "ok" if tg_ok else "fail"
    ))
    print(_json.dumps(result, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
