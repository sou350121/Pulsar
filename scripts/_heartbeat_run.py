#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared subprocess runner with stdout heartbeat.

Python 3.6 compatible.
"""

from __future__ import print_function

import os
import subprocess
import threading


def _normalize_int(value, default_value):
    try:
        iv = int(value)
        if iv <= 0:
            return int(default_value)
        return iv
    except Exception:
        return int(default_value)


def _run_with_heartbeat_core(
    cmd,
    timeout=120,
    heartbeat_sec=20,
    label="",
    cwd="/home/admin",
    extra_env=None,
):
    env = dict(os.environ)
    if isinstance(extra_env, dict):
        env.update(extra_env)

    hb_sec = _normalize_int(heartbeat_sec, 20)
    timeout_sec = _normalize_int(timeout, 120)
    run_label = (label or "").strip() or "subprocess"

    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            cwd=cwd,
            env=env,
        )
    except Exception as e:
        return 125, "", str(e), False

    stop_evt = threading.Event()

    def _heartbeat_loop():
        while not stop_evt.wait(hb_sec):
            try:
                print("[progress] %s still running..." % run_label, flush=True)
            except Exception:
                pass

    hb_thread = threading.Thread(target=_heartbeat_loop)
    hb_thread.daemon = True
    hb_thread.start()

    timed_out = False
    try:
        out, err = p.communicate(timeout=timeout_sec)
        rc = int(p.returncode)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            p.kill()
        except Exception:
            pass
        try:
            out, err = p.communicate()
        except Exception:
            out, err = "", ""
        rc = 124
    except Exception as e:
        out, err = "", str(e)
        rc = 125
    finally:
        stop_evt.set()
        try:
            hb_thread.join(0.2)
        except Exception:
            pass

    return rc, (out or ""), (err or ""), timed_out


def run_with_heartbeat(
    cmd,
    timeout=120,
    heartbeat_sec=20,
    label="",
    cwd="/home/admin",
    extra_env=None,
):
    """
    Run command with periodic stdout heartbeat.
    Returns: (rc, stdout, stderr)
    """
    rc, out, err, _timed_out = _run_with_heartbeat_core(
        cmd=cmd,
        timeout=timeout,
        heartbeat_sec=heartbeat_sec,
        label=label,
        cwd=cwd,
        extra_env=extra_env,
    )
    return rc, out, err


def run_with_heartbeat_ex(
    cmd,
    timeout=120,
    heartbeat_sec=20,
    label="",
    cwd="/home/admin",
    extra_env=None,
):
    """
    Run command with periodic stdout heartbeat.
    Returns: (rc, stdout, stderr, timed_out)
    """
    return _run_with_heartbeat_core(
        cmd=cmd,
        timeout=timeout,
        heartbeat_sec=heartbeat_sec,
        label=label,
        cwd=cwd,
        extra_env=extra_env,
    )
