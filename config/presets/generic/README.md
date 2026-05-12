# Generic scaffold preset

This is **not** a ready-to-run preset — it is a starting scaffold for users whose domain doesn't fit `ai-news`. Every value is a `{{PLACEHOLDER}}` you fill in.

## Files

- `active-config.json` — domain keywords, institutions, RSS sources, research directions
- `assumptions.json` — 3 placeholder hypotheses to seed your calibration loop

## How to use

1. Copy this directory to a new name: `cp -r config/presets/generic config/presets/my-domain`
2. Open each `*.json` and replace every `{{PLACEHOLDER}}` with real values
3. Validate: `python3 -c "import json; json.load(open('config/presets/my-domain/active-config.json'))"`
4. Add a `jobs.json` (clone from `config/presets/ai-news/jobs.json`, rename the job IDs, rename "AI News" in the messages)
5. Deploy: `bash scripts/quickstart.sh my-domain`

## Full walkthrough

See [`docs/deployment/your-own-domain.md`](../../../docs/deployment/your-own-domain.md) for the step-by-step guide covering:

- Picking the right `keywords_A` / `keywords_B` split
- Finding stable public RSS feeds for your field
- Seeding good day-1 hypotheses
- Registering the new domain in `memory/domains.json` for multi-domain mode

## If you're tracking AI/ML news

Use [`config/presets/ai-news/`](../ai-news/README.md) — it's a finished, public-feed-only preset that runs in 10 minutes.
