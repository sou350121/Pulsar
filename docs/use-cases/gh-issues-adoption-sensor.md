# GitHub Issues Adoption Sensor

> **Why**: star counts lie. They measure attention, not adoption. The issue / PR cadence on an OSS repo is a better signal of who is *actually shipping with it* — and which library is winning a frame war.

## What it does

Watches a curated registry of OSS repos in your domain and turns issue/PR activity into three derived signals:

- **Adoption phase** per repo — `incubation` → `growth` → `mainstream` → `maturity`, inferred from issue cadence, community-question density, and contributor diversity.
- **DFI (Daily Field Index)** — a single per-day number summarizing how busy the tracked ecosystem is. Useful for catching ecosystem-wide spikes that no single repo would surface.
- **Convergence signals** — when ≥3 monitored repos hit the same dependency, method, or benchmark in the same week. Indicates a paradigm crystallizing.

## Pipeline shape

```
collect-github-issues.py   (daily — tier-1 repos)
       ↓
  memory/gh-issues-YYYY-MM-DD.json
       ↓
compute-gh-adoption.py     (Friday 13:00 — tier-1 + tier-2)
       ↓
  memory/gh-adoption-YYYY-MM-DD.json
       ↓
update-gh-field-notes.py   (push to your knowledge-base)
```

## Registry: `scripts/_gh_issues_config.py`

Each entry:

```python
{"owner": "huggingface", "repo": "lerobot", "short": "lerobot", "tier": 1,
 "methods": ["diffusion_policy", "cross_embodiment", "rl_finetuning"]}
```

- `tier`: `1` = daily collection, `2` = weekly-only
- `methods`: which method families this repo is associated with — used by the convergence detector

Replace the shipped VLA registry with repos relevant to your domain. The pipeline logic is domain-agnostic.

## Env overrides

| Variable | Purpose |
|----------|---------|
| `PULSAR_MEMORY_DIR` | Memory root |
| `PULSAR_FIELD_NOTES_REPO` | Target repo for `update-gh-field-notes.py` (default: `sou350121/VLA-Handbook`) |
| `PULSAR_FIELD_NOTES_PATH` | Target path within the repo |
| `GITHUB_TOKEN` | API token with `Contents: Read and Write` on the target repo |

## Cost

Roughly one GitHub API call per tracked repo per day. The default 21-repo registry stays well under the 5000 req/hour authenticated quota.
