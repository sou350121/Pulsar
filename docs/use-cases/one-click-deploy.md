# One-click Deploy — Use Cases

> **Status**: ✅ Done | **Priority**: P0 | **Issue**: [#3](https://github.com/sou350121/Pulsar/issues/3)

Bootstraps a complete Pulsar instance — Python deps, cron jobs, memory structure, API keys, and Moltbot gateway — from a single script invocation on a fresh server.

---

## Use Case 1: First-time Deployment by a Researcher Cloning Pulsar

**Scenario**: The researcher has a fresh 2 GB RAM VPS running Ubuntu 22.04 and wants to get the full VLA + AI App monitoring pipeline running from zero.

**What happens**: The deploy script installs Python dependencies serially (to respect the 2 GB RAM constraint), creates the memory directory tree, writes `domains.json` from a template, registers all cron jobs via `moltbot cron edit`, and runs a smoke-test to verify the Moltbot gateway is reachable. Interactive prompts collect API keys (DashScope, GitHub token, Telegram account names).

**Example**:
```bash
git clone https://github.com/sou350121/Pulsar-KenVersion.git ~/pulsar
cd ~/pulsar
bash scripts/deploy.sh

# Prompts:
# Enter DashScope API key: sk-...
# Enter GitHub token (for VLA-Handbook + Agent-Playbook): ghp_...
# Enter Telegram account alias for VLA reports [original]: original
# Enter Telegram account alias for AI reports [ai_agent_dailybot]: ai_agent_dailybot

# Output:
# ✓ Python deps installed (serial, low-RAM mode)
# ✓ memory/ structure created
# ✓ domains.json written
# ✓ 15 cron jobs registered
# ✓ Gateway reachable at localhost:18789
# Deploy complete. First run: 06:45 tomorrow.
```

---

## Use Case 2: New Team Member Setting Up on a Different Server

**Scenario**: A collaborator wants their own isolated Pulsar instance (different API keys, different Telegram bot) on a separate server without interfering with the researcher's running instance.

**What happens**: The deploy script detects it is running as a different user/path and scopes all config to that user's home directory (`~/.moltbot/`, `~/clawd/`). Cron jobs are registered under that user's Moltbot gateway. No files from the original instance are read or overwritten.

**Example**:
```bash
# On collaborator's server (user: researcher2):
bash scripts/deploy.sh

# Paths created:
# /home/researcher2/.moltbot/agents/...
# /home/researcher2/clawd/memory/
# /home/researcher2/clawd/scripts/

# Cron jobs registered under researcher2's gateway — isolated from original instance.
```
Both instances can run simultaneously; they share no state.

---

## Use Case 3: CI/CD or Automated Testing with --non-interactive Flag

**Scenario**: A GitHub Actions workflow needs to spin up Pulsar in a Docker container for integration tests, passing all secrets via environment variables without any interactive prompts.

**What happens**: The `--non-interactive` flag suppresses all prompts. The script reads credentials from environment variables (`DASHSCOPE_API_KEY`, `GITHUB_TOKEN`, `TG_ACCOUNT_VLA`, `TG_ACCOUNT_AI`) and writes them to the expected config files. The `--skip-gateway` flag skips Moltbot gateway startup (not needed in CI).

**Example**:
```bash
# In GitHub Actions workflow:
env:
  DASHSCOPE_API_KEY: ${{ secrets.DASHSCOPE_API_KEY }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  TG_ACCOUNT_VLA: original
  TG_ACCOUNT_AI: ai_agent_dailybot

run: |
  bash scripts/deploy.sh --non-interactive --skip-gateway --env-file /dev/null
  python3 scripts/run-vla-hotspots.py --dry-run
```

---

## Use Case 4: Re-deploying After Server Migration — Path Substitution

**Scenario**: The researcher migrates from a server where home was `/home/admin` to a new server where it is `/home/researcher`. All hardcoded paths in cron job commands and config files need updating.

**What happens**: The deploy script accepts `--old-home` and `--new-home` flags. It scans all registered cron job commands and config file path references, performs string substitution, and re-registers the cron jobs. Memory files (JSON) are copied from a backup and path fields inside them are rewritten.

**Example**:
```bash
# After rsync-ing /home/admin/clawd/ → /home/researcher/clawd/:
bash scripts/deploy.sh --migrate \
  --old-home /home/admin \
  --new-home /home/researcher \
  --skip-deps  # Python already installed

# Output:
# ✓ 15 cron job commands updated (/home/admin → /home/researcher)
# ✓ memory/domains.json paths rewritten
# ✓ github-config-*.json paths rewritten
# ✓ Cron jobs re-registered
# Verify: moltbot cron list
```

---

*See also: [Multi-domain Config](multi-domain-config.md)*
