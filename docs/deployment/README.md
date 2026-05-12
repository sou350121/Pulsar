# Deploy Pulsar

Start-here guide for new operators. Pulsar is a server-side domain intelligence
pipeline — you define the domain (RSS feeds, keywords, hypotheses), Pulsar runs
the engine (rating, three-stage reasoning, watchdog, calibration).

Three paths through this directory. Pick one:

## A. Quickstart with preset (~10 min) → [`quickstart.md`](quickstart.md)

You want to see Pulsar working *today*, end-to-end, before touching your own
domain config. Use the bundled `ai-news` preset — seven public RSS feeds, four
cron jobs, no Telegram or GitHub credentials required for the first run. Clone,
export one LLM API key, run `bash scripts/quickstart.sh ai-news`, watch the
first RSS pull land in `memory/`. This is the verification loop you want
before adapting anything.

## B. Your own domain (~30–60 min) → [`your-own-domain.md`](your-own-domain.md)

You've finished the quickstart and want to track *your* domain — biomedical AI,
climate policy, fintech, anything. Seven concrete steps: pick a starting
preset, define A-list / B-list keywords, find 5–10 RSS feeds, write 3–5
falsifiable hypotheses, edit `memory/active-config.json`, run RSS collect, tune
the rating distribution, then enable cron. Ends with a pointer at the "Day
1 / 3 / 7 / 14 / 28 / 60" capability-enablement timeline.

## C. Anything wrong? → [`troubleshooting.md`](troubleshooting.md)

Common failure modes organized **by symptom** (what you actually see), each
with the root cause and an exact fix command. Cron not firing, empty RSS
output, all-❌ rating distribution, Telegram delivery silent, GitHub 403,
`pip install mcp` failing on older Python, `moltbot cron add` flag
confusion — all covered here.

## Linkmap

| Doc | When to read |
|---|---|
| [`quickstart.md`](quickstart.md) | First time — verify the engine works |
| [`your-own-domain.md`](your-own-domain.md) | After quickstart — adapt to your domain |
| [`troubleshooting.md`](troubleshooting.md) | Anything broken or unexpected |
| [`../architecture.md`](../architecture.md) | What the 4-layer model and `⚡/🔧/📖/❌` mean |
| [`../use-cases/README.md`](../use-cases/README.md) | When to enable each advanced capability (Day 1 → Day 60 timeline) |
| [`../../AGENTS.md`](../../AGENTS.md) | Path conventions, identity-frame cron pattern, key paths |
| [`../../config/presets/ai-news/README.md`](../../config/presets/ai-news/README.md) | What the `ai-news` preset actually configures |
