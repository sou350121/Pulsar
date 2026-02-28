#!/usr/bin/env python3
"""
Pulsar domain registry loader.

Usage in scripts:
    from _domain_loader import load_domain, list_domains

    domain = load_domain("vla")
    cfg    = domain.active_config()        # parsed active-config.json
    gh_cfg = domain.github_config()        # parsed github-config-*.json

CLI:
    python3 _domain_loader.py --list
    python3 _domain_loader.py --show vla
    python3 _domain_loader.py --show ai_app
"""

import json
import os
import sys

MEM_DIR = os.environ.get("PULSAR_MEMORY_DIR", "/home/admin/clawd/memory")
_REGISTRY_FILE = os.path.join(MEM_DIR, "domains.json")


def load_registry() -> dict:
    with open(_REGISTRY_FILE, encoding="utf-8") as f:
        return json.load(f)


def list_domains(enabled_only: bool = True) -> list:
    """Return list of domain keys (default: only enabled ones)."""
    reg = load_registry()
    return [
        k for k, v in reg["domains"].items()
        if not enabled_only or v.get("enabled", True)
    ]


class Domain:
    """Accessor for a single domain's config and metadata."""

    def __init__(self, key: str, meta: dict):
        self.key = key
        self.meta = meta

    # ── config files ──────────────────────────────────────────────────────────

    def config_path(self, which: str = "active") -> str:
        """Return absolute path to a config file.
        which: 'active' | 'shadow' | 'pending'
        """
        field = {"active": "active_config", "shadow": "shadow_config",
                 "pending": "pending_changes"}.get(which, which + "_config")
        return os.path.join(MEM_DIR, self.meta[field])

    def active_config(self) -> dict:
        with open(self.config_path("active"), encoding="utf-8") as f:
            return json.load(f)

    def github_config(self) -> dict:
        path = os.path.join(MEM_DIR, self.meta["github_config"])
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # ── memory files ──────────────────────────────────────────────────────────

    def memory_path(self, key: str, date: str = "") -> str:
        """Return absolute path to a domain memory file.
        For dated files (containing {date}), pass date='YYYY-MM-DD'.
        """
        template = self.meta.get("memory_files", {}).get(key)
        if template is None:
            raise KeyError(f"Memory file key '{key}' not defined for domain '{self.key}'")
        filename = template.replace("{date}", date)
        return os.path.join(MEM_DIR, filename)

    # ── delivery ──────────────────────────────────────────────────────────────

    @property
    def tg_account(self) -> str:
        return self.meta["tg_account"]

    @property
    def tg_target(self) -> str:
        return self.meta["tg_target"]

    # ── metadata ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def description(self) -> str:
        return self.meta.get("description", "")

    def __repr__(self) -> str:
        return f"Domain(key={self.key!r}, name={self.name!r})"


def load_domain(key: str) -> Domain:
    """Load a domain by key. Raises KeyError if not found."""
    reg = load_registry()
    if key not in reg["domains"]:
        available = list(reg["domains"].keys())
        raise KeyError(f"Domain '{key}' not found. Available: {available}")
    return Domain(key, reg["domains"][key])


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pulsar domain registry CLI")
    parser.add_argument("--list", action="store_true", help="List all enabled domains")
    parser.add_argument("--show", metavar="DOMAIN", help="Show full domain metadata")
    parser.add_argument("--all", action="store_true", help="Include disabled domains in --list")
    args = parser.parse_args()

    if args.list or not any([args.list, args.show]):
        enabled_only = not args.all
        for key in list_domains(enabled_only=enabled_only):
            d = load_domain(key)
            print(f"  {key:12s}  {d.name:10s}  {d.description}")
    elif args.show:
        try:
            d = load_domain(args.show)
            print(json.dumps(d.meta, ensure_ascii=False, indent=2))
        except KeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
