#!/usr/bin/env python3
"""
Pulsar self-check — verify the install is healthy.

Runs three classes of check:
  1. AST parse — every script in scripts/ compiles
  2. Smoke run — every "leaf" no-LLM, no-token script exits 0 against
     a temporary empty PULSAR_MEMORY_DIR
  3. Helper imports — _vla_expert / _domain_loader / _gh_issues_config
     resolve without errors

Usage:
  python3 scripts/check-pipeline.py            # full check
  python3 scripts/check-pipeline.py --parse    # AST only (fast)
  python3 scripts/check-pipeline.py --quiet    # suppress per-file lines

Exit code: 0 = all green, 1 = anything failed.
"""
from __future__ import print_function

import argparse
import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

# Two classes of smoke-runnable script:
#   ALWAYS_OK: must exit 0 even with an empty memory dir (writes empty output)
#   NEEDS_DATA: expected to exit 1 with the message in `expect_err` on day 1;
#               anything else (different exit code or different message) is a fail
SMOKE_ALWAYS_OK = [
    "ai-field-state.py",
    "cross-domain-rule-engine.py",
    "prep-community-context.py",
]

SMOKE_NEEDS_DATA = [
    {"name": "compute-gh-adoption.py", "expect_err": "gh-issues-index.json is empty or missing"},
    {"name": "collect-github-issues.py", "expect_err": "no GITHUB_TOKEN found"},
]

REQUIRED_HELPERS = [
    "_vla_expert.py",
    "_domain_loader.py",
    "_gh_issues_config.py",
]

# Non-Python artifacts to syntax-check
SHELL_SCRIPTS = ["setup.sh"]


def parse_check(quiet=False):
    fails = []
    py_files = sorted(SCRIPTS_DIR.glob("*.py"))
    for f in py_files:
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            if not quiet:
                print("  parse OK   %s" % f.name)
        except SyntaxError as e:
            fails.append((f.name, "%s line %d" % (e.msg, e.lineno or 0)))
            print("  parse FAIL %s  — %s line %d" % (f.name, e.msg, e.lineno or 0))
    return fails


def shell_check(quiet=False):
    """bash -n every shipped shell script."""
    fails = []
    for name in SHELL_SCRIPTS:
        path = SCRIPTS_DIR / name
        if not path.exists():
            fails.append((name, "missing"))
            print("  shell FAIL %s — file not found" % name)
            continue
        try:
            proc = subprocess.run(
                ["bash", "-n", str(path)], timeout=10,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            if proc.returncode != 0:
                fails.append((name, "bash -n exit %d" % proc.returncode))
                print("  shell FAIL %s — %s" % (name, (proc.stderr or '').strip()[:200]))
            elif not quiet:
                print("  shell OK   %s" % name)
        except FileNotFoundError:
            fails.append((name, "bash not installed"))
            print("  shell SKIP %s — bash not available" % name)
        except subprocess.TimeoutExpired:
            fails.append((name, "timeout"))
            print("  shell FAIL %s — timeout" % name)
    return fails


def helper_check(quiet=False):
    fails = []
    for h in REQUIRED_HELPERS:
        path = SCRIPTS_DIR / h
        if not path.exists():
            fails.append((h, "missing"))
            print("  helper FAIL %s — file not found" % h)
        elif not quiet:
            print("  helper OK   %s" % h)
    return fails


def _run(script_path, env):
    return subprocess.run(
        [sys.executable, str(script_path)],
        env=env, timeout=60,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def smoke_check(quiet=False):
    fails = []
    with tempfile.TemporaryDirectory(prefix="pulsar-smoke-") as tmp:
        mem = Path(tmp) / "memory"
        mem.mkdir()
        env = os.environ.copy()
        env["PULSAR_MEMORY_DIR"] = str(mem)
        env["GITHUB_TOKEN"] = ""
        env["DASHSCOPE_API_KEY"] = "fake"

        # 1) ALWAYS_OK leaves: must exit 0
        for name in SMOKE_ALWAYS_OK:
            script = SCRIPTS_DIR / name
            if not script.exists():
                fails.append((name, "missing"))
                print("  smoke FAIL %s — file not found" % name)
                continue
            try:
                proc = _run(script, env)
                if proc.returncode != 0:
                    fails.append((name, "exit %d" % proc.returncode))
                    print("  smoke FAIL %s — expected exit 0, got %d\n    stderr: %s"
                          % (name, proc.returncode, (proc.stderr or "").strip()[:200]))
                elif not quiet:
                    print("  smoke OK   %s  (empty input → empty output)" % name)
            except subprocess.TimeoutExpired:
                fails.append((name, "timeout"))
                print("  smoke FAIL %s — timeout (>60s)" % name)

        # 2) NEEDS_DATA leaves: must exit 1 *with the expected message*
        for entry in SMOKE_NEEDS_DATA:
            name = entry["name"]
            expect = entry["expect_err"]
            script = SCRIPTS_DIR / name
            if not script.exists():
                fails.append((name, "missing"))
                print("  smoke FAIL %s — file not found" % name)
                continue
            try:
                proc = _run(script, env)
                combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                if proc.returncode == 0:
                    fails.append((name, "unexpected exit 0"))
                    print("  smoke FAIL %s — expected exit 1 with '%s'; got exit 0"
                          % (name, expect))
                elif expect not in combined:
                    fails.append((name, "wrong error"))
                    print("  smoke FAIL %s — expected message containing '%s';\n    got: %s"
                          % (name, expect, combined.strip()[:200]))
                elif not quiet:
                    print("  smoke OK   %s  (exit 1 with expected '%s')" % (name, expect))
            except subprocess.TimeoutExpired:
                fails.append((name, "timeout"))
                print("  smoke FAIL %s — timeout (>60s)" % name)
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true", help="AST-parse only")
    ap.add_argument("--quiet", action="store_true", help="suppress OK lines")
    args = ap.parse_args()

    print("[check] parse-check (%d scripts)" % len(list(SCRIPTS_DIR.glob("*.py"))))
    parse_fails = parse_check(args.quiet)

    print("\n[check] shell syntax (bash -n)")
    shell_fails = shell_check(args.quiet)

    if args.parse:
        helper_fails = []
        smoke_fails = []
    else:
        print("\n[check] helper imports")
        helper_fails = helper_check(args.quiet)
        total_smoke = len(SMOKE_ALWAYS_OK) + len(SMOKE_NEEDS_DATA)
        print("\n[check] smoke-run leaves (%d scripts, empty memory dir)" % total_smoke)
        smoke_fails = smoke_check(args.quiet)

    total = len(parse_fails) + len(shell_fails) + len(helper_fails) + len(smoke_fails)
    total_smoke = len(SMOKE_ALWAYS_OK) + len(SMOKE_NEEDS_DATA)
    print("\n[check] summary: parse=%d/%d shell=%d/%d helpers=%d/%d smoke=%d/%d"
          % (len(parse_fails), len(list(SCRIPTS_DIR.glob('*.py'))),
             len(shell_fails), len(SHELL_SCRIPTS),
             len(helper_fails), len(REQUIRED_HELPERS),
             len(smoke_fails), total_smoke))
    if total == 0:
        print("[check] all green ✓")
        return 0
    print("[check] %d failure(s) ✗" % total)
    return 1


if __name__ == "__main__":
    sys.exit(main())
