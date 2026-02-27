#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gateway preflight checker.

Run shortly before morning jobs:
- If gateway is healthy: stay silent (stdout empty).
- If unhealthy: try restart + verify, print concise alert only on action/failure.

Changelog:
  2026-02-23 v2: Add _check_memory_configs() — detect missing/corrupt active-config
                 files that cause agent degradation (ENOENT silently swallowed).
                 Add auto-fix root poison — chown -R admin:admin on affected dirs.
                 Add name-pattern job matching — supplemental to UUID matching,
                 survives job rebuilds that change UUIDs.
"""

from __future__ import print_function

import json
import os
import pwd
import subprocess
import sys
import time


MB = "/home/admin/.local/share/pnpm/moltbot"
HOME = "/home/admin"
PORT = "18789"


def _run(cmd, timeout=25):
    env = dict(os.environ)
    env["HOME"] = HOME
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            env=env,
            cwd=HOME,
        )
        return int(p.returncode), (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, (getattr(e, "stdout", "") or ""), (getattr(e, "stderr", "") or "")
    except Exception as e:
        return 125, "", str(e)


def _healthy():
    rc, out, err = _run([MB, "gateway", "health"], timeout=35)
    if rc == 0:
        return True, ""
    msg = (err.strip() or out.strip() or "health_check_failed")
    return False, msg


def _restart_service():
    rc, out, err = _run([MB, "gateway", "restart"], timeout=45)
    msg = (err.strip() or out.strip() or "")
    return rc == 0, msg


def _restart_fallback():
    _run(["pkill", "-f", "moltbot-gateway"], timeout=8)
    time.sleep(2)
    cmd = [MB, "gateway", "--force", "--compact", "run", "--port", PORT, "--bind", "lan"]
    try:
        with open(os.devnull, "w") as devnull:
            subprocess.Popen(
                cmd,
                cwd=HOME,
                env=dict(os.environ, HOME=HOME),
                stdout=devnull,
                stderr=devnull,
                preexec_fn=os.setsid,
            )
        return True, "fallback_started"
    except Exception as e:
        return False, str(e)


def _verify_after_restart(total_wait_seconds=18):
    deadline = time.time() + max(5, int(total_wait_seconds or 18))
    while time.time() < deadline:
        ok, _ = _healthy()
        if ok:
            return True
        time.sleep(3)
    return False


JOBS_JSON = "/home/admin/.moltbot/cron/jobs.json"
JOBS_BACKUP = "/home/admin/.moltbot/cron/jobs.json.preflight-bak"

# Critical job IDs that must always exist in jobs.json.
# NOTE: These UUIDs change if a job is deleted and recreated. Supplemented by
# name-pattern matching in _check_cron_config() for resilience.
CRITICAL_JOB_IDS = {
    "48bb8537-529d-4676-953b-2514c12d6111",  # VLA Weekly Deep Dive
    "b4a7ac85-7915-45cc-bee9-a5a2ae942956",  # AI App Weekly Deep Dive
    "7fe3f14c-911c-49f3-86a7-066b84f6b723",  # VLA Theory Deep Dive (Round 1)
    "6c389b01-a770-4379-8483-a214411471e8",  # VLA Theory Deep Dive (Round 2)
    "8f1d5d41-42fd-4536-89b4-10e5480a8f86",  # VLA Biweekly Reflection
    "09050ca4-6ed2-4b4f-9cf4-9f51d3225132",  # AI App Deep Dive
    "dd10cad8-dd66-44bf-bbbe-b9bd6498792d",  # AI App Biweekly Report
    "a6f10d54-2b67-430a-a199-f296c5c71f49",  # AI App Biweekly Reflection
    "6ad7258d-6ed4-42a5-ab09-de6ba5616907",  # Weekly Output Quality Review
}

# Critical job NAME patterns (substring match, case-insensitive).
# Used as a supplemental check that survives job UUID changes after rebuild.
CRITICAL_JOB_NAME_PATTERNS = [
    "vla weekly",
    "vla theory",
    "vla biweekly",
    "ai app weekly",
    "ai app biweekly",
    "ai app deep dive",
    "quality review",
    "vla daily",
    "vla rss",
    "ai 应用监控",
    "ai 应用开发监控日报",
]


AGENTS_DIR = "/home/admin/.clawdbot/agents"

# Directories to scan and auto-fix for root-poison (non-admin ownership)
ROOT_POISON_DIRS = [
    "/home/admin/.clawdbot",
    "/home/admin/.moltbot",
    "/home/admin/clawd/memory",
    "/home/admin/clawd/scripts",
]

# Critical scripts that must exist for the morning pipeline to succeed.
CRITICAL_SCRIPTS = [
    "/home/admin/clawd/scripts/vla-rss-collect.py",
    "/home/admin/clawd/scripts/run-vla-daily-two-phase.py",
    "/home/admin/clawd/scripts/run-vla-social-two-phase.py",
    "/home/admin/clawd/scripts/prep-vla-social.py",
    "/home/admin/clawd/scripts/post-vla-social.py",
    "/home/admin/clawd/scripts/run-vla-sota-two-phase.py",
    "/home/admin/clawd/scripts/post-vla-sota.py",
    "/home/admin/clawd/scripts/prep-vla-sota.py",
    "/home/admin/clawd/scripts/run-vla-release-two-phase.py",
    "/home/admin/clawd/scripts/prep-vla-release.py",
    "/home/admin/clawd/scripts/post-vla-release.py",
    "/home/admin/clawd/scripts/run-vla-weekly-two-phase.py",
    "/home/admin/clawd/scripts/prep-vla-weekly.py",
    "/home/admin/clawd/scripts/post-vla-weekly.py",
    "/home/admin/clawd/scripts/post-vla-theory.py",
    "/home/admin/clawd/scripts/run-ai-app-workflow-two-phase.py",
    "/home/admin/clawd/scripts/evaluate-shadow-config.py",
    "/home/admin/clawd/scripts/daily-watchdog.py",
    "/home/admin/clawd/scripts/gateway-preflight.py",
    "/home/admin/clawd/scripts/_heartbeat_run.py",
    "/home/admin/clawd/scripts/gh-contents-upload.py",
    "/home/admin/clawd/scripts/gh-paper-index-update.py",
    "/home/admin/clawd/scripts/ai-app-rss-collect.py",
    "/home/admin/clawd/scripts/prep-ai-app-rss-filtered.py",
    "/home/admin/clawd/scripts/prep-ai-app-dedup.py",
    "/home/admin/clawd/scripts/write-ai-app-daily.py",
]

# Critical memory config files that agents load at startup.
# Missing/corrupt configs cause silent degradation (agent runs with empty config).
CRITICAL_MEMORY_CONFIGS = [
    {
        "path": "/home/admin/clawd/memory/active-config.json",
        "required_keys": ["research_directions"],
        "desc": "VLA research directions config (used by VLA Daily, Social, SOTA)",
    },
    {
        "path": "/home/admin/clawd/memory/ai-app-active-config.json",
        "required_keys": ["keywords_A"],
        "desc": "AI App monitor active config (keywords, focus_areas)",
    },
]


def _check_scripts_integrity():
    """Alert if any critical scripts are missing.

    Returns warning lines (empty = ok).
    """
    missing = []
    for path in CRITICAL_SCRIPTS:
        if not os.path.isfile(path):
            missing.append(path)
    if missing:
        lines = ["🚨 %d 个关键脚本丢失（需从备份恢复）:" % len(missing)]
        for p in missing:
            lines.append("  · %s" % p)
        # Attempt auto-restore from .backup/ snapshot
        backup_dir = "/home/admin/clawd/scripts/.backup"
        auto_restored = []
        still_missing = []
        for p in missing:
            bak = os.path.join(backup_dir, os.path.basename(p))
            if os.path.isfile(bak):
                try:
                    import shutil
                    shutil.copy2(bak, p)
                    os.chown(p, admin_uid if "admin_uid" in dir() else 1000, admin_uid if "admin_uid" in dir() else 1000)
                    auto_restored.append(os.path.basename(p))
                except Exception:
                    still_missing.append(p)
            else:
                still_missing.append(p)
        if auto_restored:
            lines.append("✅ 已从 .backup/ 自动恢复: %s" % ", ".join(auto_restored))
        if still_missing:
            lines.append("手动恢复: sudo cp /home/admin/clawd/scripts/.backup/<name> /home/admin/clawd/scripts/")
        return lines
    return []


def _check_memory_configs():
    """Detect missing or corrupt critical memory config files.

    Returns warning lines (empty = ok).
    Reason: active-config.json was missing (confirmed ENOENT in 2026-02-22 logs),
    causing VLA Daily and AI App Daily to run with empty config (no keywords → no items).
    """
    warnings = []
    for cfg in CRITICAL_MEMORY_CONFIGS:
        path = cfg["path"]
        required_keys = cfg.get("required_keys", [])
        desc = cfg.get("desc", path)

        if not os.path.isfile(path):
            warnings.append("🚨 缺失配置文件: %s" % path)
            warnings.append("  说明: %s" % desc)
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            warnings.append("🚨 配置文件损坏 (JSON解析失败): %s — %s" % (path, str(e)[:80]))
            continue

        if not isinstance(data, dict) or not data:
            warnings.append("🚨 配置文件为空对象: %s" % path)
            continue

        missing_keys = [k for k in required_keys if k not in data]
        if missing_keys:
            warnings.append("⚠️ 配置文件缺少必要字段 %s: %s" % (missing_keys, path))

    return warnings


def _check_root_poison():
    """Detect and auto-fix non-admin owned files in critical directories.

    Returns warning lines (empty = ok).

    Why: root-owned files (Root Poison) cause EACCES for all admin cron jobs.
    Auto-fix: attempt `sudo chown -R admin:admin <dir>` for affected dirs.
    Falls back to advisory warning if sudo chown is unavailable.
    """
    warnings = []
    try:
        admin_uid = pwd.getpwnam("admin").pw_uid
        admin_gid = pwd.getpwnam("admin").pw_gid
    except Exception:
        admin_uid = 1000
        admin_gid = 1000

    # Scan all root-poison directories (not just agents dir)
    bad_dirs = set()
    bad_files = []
    for scan_dir in ROOT_POISON_DIRS:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for root, dirs, files in os.walk(scan_dir):
                for fn in files:
                    p = os.path.join(root, fn)
                    try:
                        st = os.lstat(p)
                    except Exception:
                        continue
                    if int(getattr(st, "st_uid", -1)) != int(admin_uid):
                        bad_files.append(p)
                        bad_dirs.add(scan_dir)
        except Exception as e:
            warnings.append("🚨 Root 污染检测失败 (%s): %s" % (scan_dir, str(e)[:80]))

    if not bad_files:
        return warnings

    # Auto-fix: try sudo chown
    fixed_dirs = []
    failed_dirs = []
    for d in sorted(bad_dirs):
        try:
            rc = subprocess.call(
                ["sudo", "chown", "-R", "admin:admin", d],
                timeout=10,
            )
            if rc == 0:
                fixed_dirs.append(d)
            else:
                failed_dirs.append(d)
        except Exception:
            failed_dirs.append(d)

    if fixed_dirs:
        warnings.append(
            "⚠️ Root 污染: 已自动修复 %d 个文件，chown -R admin:admin: %s"
            % (len(bad_files), ", ".join(fixed_dirs))
        )
    if failed_dirs:
        warnings.append(
            "🚨 Root 污染: %d 个文件无法自动修复（需手动执行）: %s"
            % (len([f for f in bad_files if any(f.startswith(d) for d in failed_dirs)]),
               ", ".join(failed_dirs))
        )
        for p in bad_files[:10]:
            warnings.append("  · %s" % p)
        warnings.append("修复: sudo chown -R admin:admin /home/admin/.clawdbot /home/admin/.moltbot /home/admin/clawd")

    return warnings


def _check_cron_config():
    """Validate jobs.json for common misconfigurations.

    Returns a list of warning strings (empty = all good).
    Checks:
    1. isolated jobs must use payload.kind=agentTurn
    2. pipeline jobs (with two-phase scripts) should have timeoutMs set
    3. jobs.json backup & restore if critical jobs are missing
    4. Name-pattern matching as supplemental check (survives UUID changes)
    """
    import shutil

    warnings = []
    try:
        with open(JOBS_JSON) as f:
            data = json.load(f)
    except Exception as e:
        warnings.append("jobs.json 读取失败: %s" % str(e)[:100])
        return warnings

    jobs = data.get("jobs", [])
    # BUG FIX (2026-02-23): empty jobs list must trigger full restore, not early return.
    if not jobs:
        warnings.append("jobs.json 中无任何 job，尝试从备份全量恢复")
        if os.path.isfile(JOBS_BACKUP):
            try:
                with open(JOBS_BACKUP) as fb:
                    bak_data = json.load(fb)
                bak_jobs = bak_data.get("jobs", [])
                if bak_jobs:
                    data["jobs"] = bak_jobs
                    with open(JOBS_JSON, "w") as fw:
                        json.dump(data, fw, ensure_ascii=False, indent=2)
                        fw.write("\n")
                    warnings.append(
                        "✅ 已从备份全量恢复 %d 个 job（将触发 gateway 重启使其生效）" % len(bak_jobs)
                    )
                else:
                    warnings.append("🚨 备份文件也是空的，无法恢复")
            except Exception as e:
                warnings.append("🚨 从备份恢复失败: %s" % str(e)[:100])
        else:
            warnings.append("🚨 备份文件不存在，无法恢复")
        return warnings

    current_ids = {j.get("id") for j in jobs}
    missing_critical = CRITICAL_JOB_IDS - current_ids

    if missing_critical:
        # Try restore from backup
        restored = False
        if os.path.isfile(JOBS_BACKUP):
            try:
                with open(JOBS_BACKUP) as fb:
                    bak_data = json.load(fb)
                bak_jobs = bak_data.get("jobs", [])
                bak_ids = {j.get("id") for j in bak_jobs}
                if CRITICAL_JOB_IDS.issubset(bak_ids):
                    added_names = []
                    for bj in bak_jobs:
                        if bj.get("id") in missing_critical:
                            jobs.append(bj)
                            added_names.append(bj.get("name", bj.get("id", "?")))
                    data["jobs"] = jobs
                    with open(JOBS_JSON, "w") as fw:
                        json.dump(data, fw, ensure_ascii=False, indent=2)
                        fw.write("\n")
                    restored = True
                    warnings.append(
                        "⚠️ jobs.json 丢失 %d 个关键 job，已从备份恢复: %s"
                        % (len(added_names), ", ".join(added_names))
                    )
            except Exception as e:
                warnings.append(
                    "jobs.json 丢失关键 job 且备份恢复失败: %s" % str(e)[:100]
                )
        if not restored:
            names = []
            for cid in missing_critical:
                names.append(cid[:12] + "...")
            warnings.append(
                "🚨 jobs.json 丢失 %d 个关键 job (无可用备份): %s"
                % (len(names), ", ".join(names))
            )
    else:
        # All critical jobs present → update backup
        try:
            shutil.copy2(JOBS_JSON, JOBS_BACKUP)
        except Exception:
            pass

    # Name-pattern check: supplemental to UUID matching
    # Survives job rebuilds that change UUIDs
    enabled_names_lower = [
        (j.get("name", "") or "").lower()
        for j in jobs
        if j.get("enabled", True)
    ]
    for pattern in CRITICAL_JOB_NAME_PATTERNS:
        pat_lower = pattern.lower()
        if not any(pat_lower in n for n in enabled_names_lower):
            warnings.append("⚠️ 未找到匹配 '%s' 的已启用 job（job 可能被禁用或重建）" % pattern)

    for j in jobs:
        if not j.get("enabled", True):
            continue
        name = j.get("name", j.get("id", "?")[:8])
        session = j.get("sessionTarget", "")
        payload = j.get("payload", {})
        pk = payload.get("kind", "")

        # Rule 1: isolated + non-agentTurn
        if session == "isolated" and pk != "agentTurn":
            warnings.append(
                "%s: sessionTarget=isolated 但 payload.kind=%s (应为 agentTurn)" % (name, pk)
            )

        # Rule 2: two-phase jobs should have explicit timeout
        msg = payload.get("message", "")
        if "two-phase" in msg or "run-" in msg:
            has_timeout = ("timeoutMs" in j) or payload.get("timeoutSeconds")
            if not has_timeout:
                warnings.append(
                    "%s: 含 two-phase 流水线但未设 timeoutMs 或 payload.timeoutSeconds" % name
                )

    # Rule 3: auto-fix missing model
    DEFAULT_MODEL = "alibaba-cloud-bailian/qwen3.5-plus"
    model_fixed = []
    for j in jobs:
        if not j.get("enabled", True):
            continue
        payload = j.get("payload", {})
        if not payload.get("model"):
            payload["model"] = DEFAULT_MODEL
            model_fixed.append(j.get("name", j.get("id", "?")[:8]))

    if model_fixed:
        try:
            data["jobs"] = jobs
            with open(JOBS_JSON, "w") as fw:
                json.dump(data, fw, ensure_ascii=False, indent=2)
                fw.write("\n")
            warnings.append(
                "⚠️ 已自动补齐 %d 个 job 的 model: %s"
                % (len(model_fixed), ", ".join(model_fixed))
            )
        except Exception as e:
            warnings.append("🚨 自动补齐 model 失败: %s" % str(e)[:100])

    return warnings


def _check_crontab():
    """Verify admin crontab has expected entries.
    
    Returns warning lines (empty = ok).
    Reason: crontab can be accidentally cleared (crontab -r), causing
    watchdog and memory-snapshot to stop running silently.
    """
    import subprocess as _sp
    warnings = []
    try:
        p = _sp.run(
            ["crontab", "-l"],
            stdout=_sp.PIPE, stderr=_sp.PIPE,
            universal_newlines=True, timeout=5,
        )
        tab = p.stdout or ""
    except Exception as e:
        warnings.append("⚠️ crontab 读取失败: %s" % str(e)[:80])
        return warnings

    required_entries = [
        ("daily-watchdog.py", "daily-watchdog.py"),
        ("memory-snapshot.py", "memory-snapshot.py"),
    ]
    for name, pattern in required_entries:
        if pattern not in tab:
            warnings.append("🚨 crontab 缺少条目: %s（验收和快照不会运行）" % name)
    return warnings


def main():
    ok, reason = _healthy()

    config_warnings = _check_cron_config()
    root_poison_warnings = _check_root_poison()
    scripts_warnings = _check_scripts_integrity()
    memory_config_warnings = _check_memory_configs()
    crontab_warnings = _check_crontab()
    warnings = (list(config_warnings) + list(root_poison_warnings) +
                list(scripts_warnings) + list(memory_config_warnings) + list(crontab_warnings))

    if ok and not warnings:
        return 0

    if ok and warnings:
        needs_restart = any("已从备份全量恢复" in w or "触发 gateway 重启" in w for w in warnings)
        print("⚠️ Gateway 健康，但发现风险项:")
        for w in warnings:
            print("  · %s" % w)
        if needs_restart:
            svc_ok, svc_msg = _restart_service()
            if svc_ok and _verify_after_restart():
                print("✅ Gateway 已重启，jobs 已重新加载")
            else:
                print("🚨 Gateway 重启失败，jobs 可能仍为空: %s" % (svc_msg or ""))
        return 0

    steps = []
    steps.append("初检不健康: %s" % reason[:180])

    svc_ok, svc_msg = _restart_service()
    if svc_ok:
        steps.append("已执行服务重启")
        if _verify_after_restart():
            print("🩺 Gateway 预检: 异常已自动重启并恢复")
            return 0
        steps.append("服务重启后仍未恢复")
    else:
        if svc_msg:
            steps.append("服务重启失败: %s" % svc_msg[:180])

    fb_ok, fb_msg = _restart_fallback()
    if fb_ok:
        steps.append("已执行兜底重启")
        if _verify_after_restart():
            print("🩺 Gateway 预检: 兜底重启后已恢复")
            return 0
        steps.append("兜底重启后仍未恢复")
    else:
        steps.append("兜底重启失败: %s" % (fb_msg[:180] if fb_msg else "unknown"))

    print("🚨 Gateway 预检失败: " + " | ".join(steps))
    if warnings:
        print("⚠️ 另外还发现风险项:")
        for w in warnings:
            print("  · %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
