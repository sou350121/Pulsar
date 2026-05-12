# Your own domain — concrete adaptation

You've completed [`quickstart.md`](quickstart.md) — the `ai-news` preset is
running and you've verified an RSS pull lands on disk. Now adapt Pulsar to
*your* domain (biomedical AI, climate policy, fintech, materials science,
whatever). This walkthrough is concrete: every step has commands, examples,
and quick sanity checks.

If anything is wrong, see [`troubleshooting.md`](troubleshooting.md).

---

## 1. Pick a starting point

Two options:

- **Closest preset (recommended)** — copy from `config/presets/ai-news/` and
  edit. Keywords + hypotheses get you 60–80% of the way; you'll swap out RSS
  feeds and adjust thresholds. Use this when your domain has any overlap with
  what the preset already does.
- **Generic scaffold (blank slate)** — start from
  `config/active-config.template.json` and write everything from scratch. Use
  this for domains with no overlap (e.g., legal research, climate policy).

```bash
# Option A — clone from the AI-news preset
cp config/presets/ai-news/active-config.json memory/active-config.json
cp config/presets/ai-news/assumptions.json memory/assumptions.json

# Option B — start blank
cp config/active-config.template.json memory/active-config.json
cp config/assumptions.template.json memory/assumptions.json
```

---

## 2. Define keywords (A-list and B-list)

The rating engine filters every raw signal through two keyword lists *before*
any LLM call. Get this calibration right and the rest of the pipeline behaves;
get it wrong and you'll see either no `⚡`/`🔧` ratings at all, or floods of
false positives.

- **A-list (`keywords_A`)** — **must match**. Domain-defining terms; ~5–15
  entries. A signal that hits an A-keyword is a candidate for rating.
- **B-list (`keywords_B`)** — **peripheral / broad net**. ~3–5 entries. A
  B-keyword alone is *not* enough; B-keywords lift confidence only when
  co-occurring with an A-keyword.

How the `ai-news` preset does it: 15 A-keywords like `llm`, `agent`, `rag`,
`mcp`; 4 B-keywords like `inference`, `embedding`. AI papers without any
A-match get dropped.

**Heuristic** (verify empirically in step 6):

- A-list terms should appear in **~5–20%** of your target signals — narrow
  enough to discriminate, broad enough not to filter everything out.
- B-list terms should appear in **~30–50%** — they're a context net, not a
  filter.
- Too narrow (all signals rated `❌`) → broaden A-list or add synonyms.
- Too broad (no rating discrimination) → tighten A-list, raise institution
  weighting.

---

## 3. Find RSS feeds (5–10 sources)

A balanced corpus comes from 5–10 feeds across three categories: primary
research, industry/practitioner blogs, news/aggregators. Three concrete ways
to find them:

**Google search**:
```
site:blog.{your-org}.com rss
{topic} rss feed
{topic} arxiv
```

**arXiv categories** — every arXiv category has an RSS feed. Replace the
category code:
```
https://export.arxiv.org/rss/cs.CL     # NLP
https://export.arxiv.org/rss/cs.RO     # Robotics
https://export.arxiv.org/rss/q-bio.QM  # Quantitative biology
```
Category list: <https://arxiv.org/category_taxonomy>.

**Aggregators for sites without native RSS**:

- [Feedly](https://feedly.com/) — discoverable feed catalog
- [RSSHub](https://docs.rsshub.app/) — self-hostable; generates RSS for sites
  that don't expose one (Twitter handles, GitHub releases, conference sites)

Target **5–10 feeds** for the first iteration. More than 10 is hard to keep
tuned; fewer than 5 risks single-source bias.

---

## 4. Write 3–5 hypotheses

Hypotheses are the testable, falsifiable claims Pulsar tracks across months.
Each one gets a confidence score (0–1) that the calibration loop updates
monthly based on whether incoming signals confirm or contradict it.

Format (in `memory/assumptions.json`):

```json
{
  "id": "BIO-001",
  "text": "Single-cell foundation models will outperform task-specific models on rare-disease classification by Q4",
  "confidence": 0.5,
  "verification": "≥2 papers showing single-cell FM > task-specific F1 on rare-disease benchmark within 6 months",
  "last_updated": "2026-05-12"
}
```

Rules of thumb:

- **3–5 hypotheses** — fewer than 3 and you're under-using calibration; more
  than 5 and you can't keep them maintained.
- **Confidence starts in 0.3–0.7** — leaves room to move both ways.
- **Must be falsifiable** — `verification` must describe what you'd observe if
  the hypothesis turned out to be wrong. Vague claims ("AI will keep
  growing") can't be calibrated.

The `ai-news` preset's five hypotheses (`AI-001` through `AI-005`) are a good
reference for tone and specificity.

---

## 5. Edit `memory/active-config.json`

Open the file and swap in your domain's settings. The four fields that matter:

```jsonc
{
  "domain": "biomedical-ai",                       // free-form label
  "rss_sources": [
    {"name": "arxiv-q-bio.QM", "url": "https://export.arxiv.org/rss/q-bio.QM"},
    {"name": "biorxiv-bioinformatics", "url": "..."}
    // 5–10 entries from step 3
  ],
  "keywords_A": ["foundation model", "single-cell", "scRNA-seq", "..."],  // step 2
  "keywords_B": ["transformer", "fine-tuning", "embedding"],
  "institutions": ["[Stanford]", "[Broad Institute]", "[Memorial Sloan Kettering]"],
  "research_directions": ["disease-specific foundation models", "..."]
}
```

If you want GitHub push too, create a per-domain config:

```bash
cp config/github-config.template.json memory/github-config-primary.json
# Edit "repo": "your-username/your-domain-handbook"
```

---

## 6. Run RSS collect and verify the rating distribution

This is the iteration loop — run, inspect, tune keywords, repeat:

```bash
python3 scripts/ai-app-rss-collect.py
ls ~/clawd/memory/ai-app-rss-$(date +%Y-%m-%d).json
```

Inspect the first 10 titles and how many A-keywords match:

```bash
python3 - <<'PY'
import json, datetime, pathlib
date = datetime.date.today().isoformat()
p = pathlib.Path.home() / "clawd/memory" / f"ai-app-rss-{date}.json"
d = json.loads(p.read_text())
print(f"total_fetched={d.get('total_fetched')} after_filter={d.get('after_filter')}")
for i, it in enumerate(d.get("items", [])[:10], 1):
    print(f"{i:2d}. [{it.get('rating','?')}] {it.get('title','')[:90]}")
PY
```

What to look for:

- `after_filter / total_fetched` ratio of ~5–20% → A-keywords are in the right
  range
- A mix of `⚡`/`🔧`/`📖`/`❌` in the top 10 → rating engine discriminating
- **All `❌`**: A-keywords too narrow or wrong language → broaden, retry
- **All `⚡`/`🔧`**: A-keywords too broad → tighten, retry
- **`after_filter == 0`**: feeds returned nothing in the keyword window → see
  [troubleshooting](troubleshooting.md#memoryai-app-rss-json-is-empty-or-missing)

Iterate keywords until the distribution looks healthy. Two or three rounds is
typical.

---

## 7. Enable cron

The preset's `~/.openclaw/cron/jobs.<preset>.staged.json` is your starting
schedule. Stop the gateway, install the staged file as the active jobs file,
and restart:

```bash
pkill -f moltbot-gateway || true

# If the preset's staged file isn't already in place
cp ~/.openclaw/cron/jobs.ai-news.staged.json ~/.openclaw/cron/jobs.json

nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot cron list
```

You can edit `~/.openclaw/cron/jobs.json` directly while the gateway is
stopped; restart picks up the changes. To add a new job, follow the
identity-frame pattern in
[`../../AGENTS.md`](../../AGENTS.md#scheduling-a-new-script) — bare command
strings don't work.

---

## When to enable advanced capabilities

The P1 / P2 capabilities (cross-domain rule engine, field-state trigger,
quality drift, entity tracker, semantic search) have data dependencies. Run
them too early and they produce empty or misleading output. The full
Day 1 → Day 60 timeline lives at
[`../use-cases/README.md#when-to-enable-what`](../use-cases/README.md#when-to-enable-what).
Short version:

- **Day 1**: MCP server, setup, Devil's Advocate (no data deps)
- **Day 3**: Field-State Trigger, Cross-domain v2 (need a small corpus)
- **Day 7**: Quality Drift Detector (needs 7-day rolling baseline)
- **Day 14**: Entity Tracker, GitHub Adoption analysis
- **Day 28**: Calibration aggregation, Upstream Monitor
- **Day 60**: Semantic Memory Search at full quality

---

If anything is wrong, see [`troubleshooting.md`](troubleshooting.md).
