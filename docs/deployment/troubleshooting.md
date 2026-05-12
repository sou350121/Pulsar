# Troubleshooting

Organized **by symptom** — what you actually see in the terminal or Telegram.
For each entry: the error message a user would observe, the root cause, and
the exact fix command.

---

## "Cron didn't fire / no output after 24 hours"

**Symptom**: `~/clawd/memory/` has no new dated files; `moltbot cron list`
either fails or shows zero jobs.

**Root cause** (one of two):

1. The moltbot gateway isn't running — nothing schedules the jobs.
2. The job's `message` field is missing the identity-frame pattern
   (`你是…定时任务`), and the runtime silently skips the tool call.

**Fix**:

```bash
# Check the gateway
ps aux | grep moltbot-gateway
ss -ltnp | grep 18789

# If absent, start it (stop first if a stale process is listening)
pkill -f moltbot-gateway || true
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &

# List jobs
moltbot cron list
```

If the gateway is running and `moltbot cron list` shows your jobs but they
still never fire output, open `~/.openclaw/cron/jobs.json` and confirm each
`message` starts with `你是「X」定时任务。严格执行：` (see
[`../../AGENTS.md`](../../AGENTS.md#scheduling-a-new-script)). Reload by
stopping the gateway, editing, and starting it again — the gateway reads
`jobs.json` on startup, not on every tick.

---

## "`memory/ai-app-rss-*.json` is empty or missing"

**Symptom**: `ls memory/ai-app-rss-$(date +%Y-%m-%d).json` shows no file, or
the file's `items[]` array is empty, or `after_filter == 0`.

**Root cause A — wrong filename for keyword config**: `ai-app-rss-collect.py`
reads keywords from `memory/ai-app-active-config.json` (specific filename), not
`memory/active-config.json`. `quickstart.sh` mirrors the preset's
`active-config.json` to that name automatically. If you bypassed the
quickstart, copy it manually:

```bash
cp memory/active-config.json memory/ai-app-active-config.json
```

**Root cause B — path substitution skipped**: scripts hardcode
`MEM_DIR = "/home/admin/clawd/memory"`. A fresh adopter on a different
`$HOME` will get `PermissionError: '/home/admin/clawd'`. Fix:

```bash
# What setup.sh / quickstart.sh do automatically:
find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|$HOME|g"
```

**Root cause C — RSS feed URLs failing**: one or more RSS feed URLs is stale,
behind a redirect, or returning 4xx/5xx.

> Note: `ai-app-rss-collect.py` has its feed list hard-coded in `FEEDS_RSS` at
> the top of the file, not driven by `active-config.json`'s `rss_sources`.
> Editing `rss_sources` won't change which feeds are pulled — you must edit the
> script for now. This is documented in `config/presets/ai-news/README.md`.

**Fix**: probe each feed for a 2xx status. Anything not 200 is suspect:

```bash
python3 - <<'PY'
import json, pathlib, urllib.request
cfg = json.loads((pathlib.Path.home() / "clawd/memory/active-config.json").read_text())
for s in cfg.get("rss_sources", []):
    name, url = s.get("name"), s.get("url")
    try:
        r = urllib.request.urlopen(url, timeout=10)
        print(f"{r.status}  {name:30s}  {url}")
    except Exception as e:
        print(f"ERR  {name:30s}  {url}  -- {e}")
PY
```

Update the failing entries in `memory/active-config.json`. Many sites have
moved their feed URLs; check the source's footer or `<link rel="alternate">`
in the HTML head.

---

## "All papers rated ❌, no ⚡ or 🔧"

**Symptom**: every entry in today's RSS output has `"rating": "❌"`.

**Root cause**: A-list keywords too narrow, wrong language (e.g., English
keywords against Chinese feeds), or unrelated to what the feeds actually
publish.

**Fix**: collect once, inspect the first 10 titles, count A-keyword hits:

```bash
python3 scripts/ai-app-rss-collect.py
python3 - <<'PY'
import json, pathlib, datetime
date = datetime.date.today().isoformat()
mem = pathlib.Path.home() / "clawd/memory"
cfg = json.loads((mem / "active-config.json").read_text())
d = json.loads((mem / f"ai-app-rss-{date}.json").read_text())
keys = [k.lower() for k in cfg.get("keywords_A", [])]
for i, it in enumerate(d.get("items", [])[:10], 1):
    title = it.get("title", "").lower()
    hits = [k for k in keys if k in title]
    print(f"{i:2d}. hits={len(hits)}  {it.get('title','')[:80]}")
PY
```

Aim for **≥3 of your A-keywords** appearing across the top 10 titles. If
fewer, broaden the A-list with synonyms / abbreviations / common framings of
the same concept, then rerun.

---

## "Watchdog reports `MISSING ai-app-daily` etc. on day 1"

**Symptom**: `daily-watchdog.py` or `memory/watchdog-log.json` shows
`status: fail` with `MISSING` on most checks during the first 24 hours.

**Root cause**: **expected behaviour**. Watchdog compares today against
recent history; on day 1 there is no history. The full cycle takes 24 hours
to populate every health check.

**Fix**: wait one full daily cycle, then rerun:

```bash
python3 scripts/daily-watchdog.py
```

After 24 hours, only genuinely failing checks remain `MISSING`. Investigate
those individually.

---

## "Telegram messages not delivered"

**Symptom**: cron jobs complete (you see them in the gateway log) but no
message arrives in your Telegram channel or DM.

**Root cause** (one of two):

1. The bot isn't an admin of the target channel.
2. `TELEGRAM_CHAT_ID` has the wrong sign — **channels are negative**
   (`-1001234567890`), users are positive.

**Fix** — quick API test:

```bash
TG="$TELEGRAM_BOT_TOKEN"
ID="$TELEGRAM_CHAT_ID"
curl -s "https://api.telegram.org/bot$TG/sendMessage?chat_id=$ID&text=test"
```

Inspect the JSON response:

- `"ok": true` → token + chat_id are fine; check whether your cron job's
  `to:` field matches `TELEGRAM_CHAT_ID` exactly.
- `"description": "chat not found"` → ID wrong (often the sign).
- `"description": "Forbidden: bot is not a member of the channel"` → add the
  bot as a channel admin.

---

## "GitHub Contents API returns 403"

**Symptom**: `gh-contents-upload.py` (or any script that pushes to GitHub)
prints `403 Forbidden` and aborts.

**Root cause**: the token has no `Contents: Read and Write` permission on
the target repo, or the fine-grained token's repository allowlist doesn't
include your target.

**Fix**: regenerate the token with the correct scope:

1. GitHub → Settings → Developer Settings → Personal Access Tokens →
   Fine-grained tokens → New token (or edit existing)
2. Repository access: select the target repo(s) explicitly
3. Permissions → Repository permissions → **Contents: Read and Write**
4. Save the new token to `~/.clawdbot/.env` (or whichever env file your shell
   loads) as `GITHUB_TOKEN`
5. Restart the gateway so it picks up the new env

---

## "LLM returns empty content"

**Symptom**: pipeline runs to completion but the LLM-output file is empty,
or contains only whitespace, or the report body is blank.

**Root cause** (in order of likelihood):

1. API key wrong or expired
2. Rate-limited (HTTP 429) by the provider
3. Base URL mismatch — e.g., `OPENAI_API_KEY` set but
   `scripts/_vla_expert.py` still points at the DashScope endpoint

**Fix** — for the third case, edit `scripts/_vla_expert.py`:

```python
# Before (DashScope):
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
EXPERT_MODEL  = "qwen3.5-plus"

# After (OpenAI):
DASHSCOPE_URL = "https://api.openai.com/v1/chat/completions"
EXPERT_MODEL  = "gpt-4o-mini"
```

For rate-limit symptoms, check the gateway log
(`tail -F /tmp/moltbot-gateway.log`) for `429` and back off / lower
concurrency. DashScope's per-hour quota commonly triggers between 11:00–13:00
when several jobs run in succession.

---

## "`check-pipeline.py` says smoke FAIL with 'no GITHUB_TOKEN'"

**Symptom**: `python3 scripts/check-pipeline.py` exits non-zero with an error
mentioning `GITHUB_TOKEN` unset.

**Root cause**: **expected** when `GITHUB_TOKEN` is unset. The smoke test
pins the exact "no GITHUB_TOKEN" error message so the suite stays green
across CI environments without leaking real tokens.

**Fix**: set the token to see the test pass:

```bash
export GITHUB_TOKEN=ghp_...
python3 scripts/check-pipeline.py
```

---

## "`pip install mcp` fails with `requires Python >=3.10`"

**Symptom**: `pip install mcp` aborts with a version-requirement error.

**Root cause**: system Python is older than 3.10.

**Fix**:

```bash
# Amazon Linux 2 / RHEL 8
sudo dnf install -y python3.11
python3.11 -m pip install mcp

# Ubuntu < 22.04
sudo apt update
sudo apt install -y python3.11 python3.11-distutils
python3.11 -m pip install mcp

# macOS (Homebrew)
brew install python@3.11
python3.11 -m pip install mcp
```

Then update your shell so `python3` resolves to the new binary, or invoke
`python3.11` explicitly for Pulsar scripts.

---

## "`moltbot cron add` says 'unknown option: --command'"

**Symptom**: `moltbot cron add --command "..." ...` aborts with
`error: unknown option '--command'`.

**Root cause**: `moltbot cron add` takes `--message`, **not** `--command`.
The runtime expects an LLM-style identity-frame message; a bare command
string won't work even with the right flag.

**Fix**: use the identity-frame pattern from
[`../../AGENTS.md`](../../AGENTS.md#scheduling-a-new-script):

```bash
moltbot cron add \
  --name "Field-State Trigger" \
  --cron "56 9 * * *" \
  --session isolated \
  --timeout 90000 \
  --message $'你是「场态触发器」定时任务。严格执行：\n1) 运行：timeout 60 python3 ~/clawd/scripts/ai-field-state.py\n2) 退出码0=正常，非0=错误\n3) 脚本执行完毕后绝对静默'
```

---

## "`setup.sh` hangs on prompts"

**Symptom**: `bash scripts/setup.sh` stops at a question and you're running
in a CI environment or non-interactive shell.

**Root cause**: interactive mode is the default.

**Fix**: pass `--non-interactive` and set the relevant env vars first:

```bash
export DASHSCOPE_API_KEY=sk-...
bash scripts/setup.sh --non-interactive --memory-dir /path/to/memory
```

For a fully scripted install with the `ai-news` preset, prefer
`bash scripts/quickstart.sh ai-news` — it's non-interactive by design and
won't ask any questions.
