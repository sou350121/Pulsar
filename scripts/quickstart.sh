#!/usr/bin/env bash
# Pulsar quickstart.sh — non-interactive preset installer.
#
# Usage: bash scripts/quickstart.sh [PRESET=ai-news]
# Env:   PULSAR_HOME (default: $HOME/clawd)
#        PULSAR_MEMORY_DIR (default: $PULSAR_HOME/memory)
#
# What it does:
#   1. Verifies at least one LLM API key (DashScope / OpenAI / Anthropic) is set
#   2. Confirms the preset directory exists
#   3. Creates $PULSAR_MEMORY_DIR if missing
#   4. Copies active-config.json + assumptions.json into $PULSAR_MEMORY_DIR
#   5. Substitutes /home/admin -> $HOME in the preset jobs.json and stages it
#      for ~/.openclaw/cron/jobs.json (warns instead of overwriting if present)
#   6. Runs scripts/check-pipeline.py --quiet and fails loudly if not green
#   7. Prints next-steps (gateway start, manual RSS pull, output location)

set -euo pipefail

RED='\033[0;31m'
YEL='\033[0;33m'
GRN='\033[0;32m'
BLU='\033[0;34m'
NC='\033[0m'
info() { echo -e "${BLU}[info]${NC}  $*"; }
ok()   { echo -e "${GRN}[ ok ]${NC}  $*"; }
warn() { echo -e "${YEL}[warn]${NC}  $*"; }
die()  { echo -e "${RED}[fail]${NC}  $*" >&2; exit 1; }

PRESET="${1:-ai-news}"
PULSAR_HOME="${PULSAR_HOME:-$HOME/clawd}"
PULSAR_MEMORY_DIR="${PULSAR_MEMORY_DIR:-$PULSAR_HOME/memory}"

# Resolve repo root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PRESET_DIR="$REPO_ROOT/config/presets/$PRESET"
CRON_DIR="$HOME/.openclaw/cron"
CRON_JOBS="$CRON_DIR/jobs.json"

echo ""
echo -e "${BLU}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLU}║       Pulsar — Quickstart ($PRESET)      ${NC}"
echo -e "${BLU}╚══════════════════════════════════════════╝${NC}"
echo ""
info "Preset      : $PRESET"
info "Pulsar home : $PULSAR_HOME"
info "Memory dir  : $PULSAR_MEMORY_DIR"
info "Preset dir  : $PRESET_DIR"
echo ""

# ── Step 1: API key check ───────────────────────────────────────────────────
info "Step 1/6 — Checking for an LLM API key ..."
HAVE_KEY=0
for var in DASHSCOPE_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  if [[ -n "${!var:-}" ]]; then
    ok "Found \$$var (length ${#var})"
    HAVE_KEY=1
  fi
done
if [[ $HAVE_KEY -eq 0 ]]; then
  die "No LLM API key found. Set one of: DASHSCOPE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY"
fi

# ── Step 2: Preset directory check ──────────────────────────────────────────
info "Step 2/6 — Verifying preset directory ..."
if [[ ! -d "$PRESET_DIR" ]]; then
  echo ""
  warn "Available presets:"
  if [[ -d "$REPO_ROOT/config/presets" ]]; then
    for d in "$REPO_ROOT/config/presets"/*/; do
      [[ -d "$d" ]] && echo "    - $(basename "$d")"
    done
  fi
  die "Preset '$PRESET' not found at: $PRESET_DIR"
fi
for required in active-config.json assumptions.json jobs.json; do
  [[ -f "$PRESET_DIR/$required" ]] || die "Preset '$PRESET' missing $required"
done
ok "Preset has active-config.json, assumptions.json, jobs.json"

# ── Step 3: Memory dir ──────────────────────────────────────────────────────
info "Step 3/6 — Preparing memory dir ..."
if [[ ! -d "$PULSAR_MEMORY_DIR" ]]; then
  mkdir -p "$PULSAR_MEMORY_DIR"
  ok "Created $PULSAR_MEMORY_DIR"
else
  ok "$PULSAR_MEMORY_DIR exists"
fi

# ── Step 4: Copy active-config + assumptions ────────────────────────────────
info "Step 4/6 — Installing config into memory dir ..."
for f in active-config.json assumptions.json; do
  dest="$PULSAR_MEMORY_DIR/$f"
  if [[ -f "$dest" ]]; then
    warn "$dest already exists — keeping existing file (delete it manually to refresh)"
  else
    cp "$PRESET_DIR/$f" "$dest"
    ok "Wrote $dest"
  fi
done

# Many core scripts (ai-app-rss-collect.py, daily-watchdog.py, etc.) hardcode
# `ACTIVE_CONFIG_PATH = "ai-app-active-config.json"` rather than reading the
# canonical `active-config.json`. Wire the preset through by also writing the
# domain-specific filename so keywords_A/B actually apply at rating time.
for alt in ai-app-active-config.json vla-active-config.json; do
  alt_dest="$PULSAR_MEMORY_DIR/$alt"
  [[ -f "$alt_dest" ]] || cp "$PRESET_DIR/active-config.json" "$alt_dest"
done
ok "Mirrored active-config to ai-app-active-config.json + vla-active-config.json"

# Repo-wide path substitution (idempotent — re-running is a no-op once done).
# 37 scripts hardcode `MEM_DIR = "/home/admin/clawd/memory"` and do not honour
# PULSAR_MEMORY_DIR. Without this step, those scripts try to write to
# /home/admin/... and crash on PermissionError for fresh adopters.
if [[ "$HOME" != "/home/admin" ]]; then
  SUBST_COUNT=0
  for py in "$SCRIPT_DIR"/*.py; do
    [[ -f "$py" ]] || continue
    if grep -q '/home/admin' "$py" 2>/dev/null; then
      sed -i "s|/home/admin|${HOME}|g" "$py"
      SUBST_COUNT=$((SUBST_COUNT+1))
    fi
  done
  if [[ $SUBST_COUNT -gt 0 ]]; then
    ok "Path-substituted /home/admin → $HOME in $SUBST_COUNT script(s)"
  else
    info "No /home/admin references left in scripts/ (already substituted)"
  fi
  # Also patch MEM_DIR to use the user's PULSAR_MEMORY_DIR if it differs from
  # $HOME/clawd/memory (the default after substitution).
  if [[ "$PULSAR_MEMORY_DIR" != "$HOME/clawd/memory" ]]; then
    warn "PULSAR_MEMORY_DIR=$PULSAR_MEMORY_DIR ≠ default $HOME/clawd/memory."
    warn "Scripts reference $HOME/clawd/memory after substitution. To use a"
    warn "custom memory dir, symlink it: ln -s $PULSAR_MEMORY_DIR $HOME/clawd/memory"
  fi
fi

# ── Step 5: Stage jobs.json with path substitution ──────────────────────────
info "Step 5/6 — Preparing cron jobs ..."
mkdir -p "$CRON_DIR"
STAGED_JOBS="$CRON_DIR/jobs.${PRESET}.staged.json"
# Substitute /home/admin -> $HOME so paths in the identity-frame messages resolve
# for the user actually running the install. Use a non-/ delimiter for sed to
# avoid escaping $HOME if it contains slashes.
sed "s|/home/admin|${HOME}|g" "$PRESET_DIR/jobs.json" > "$STAGED_JOBS"
ok "Staged jobs at $STAGED_JOBS"

if [[ -f "$CRON_JOBS" ]]; then
  warn "$CRON_JOBS already exists — NOT overwriting."
  warn "Review the staged file, then merge or replace manually:"
  warn "    diff -u $CRON_JOBS $STAGED_JOBS"
  warn "    # if happy:"
  warn "    cp $STAGED_JOBS $CRON_JOBS"
else
  cp "$STAGED_JOBS" "$CRON_JOBS"
  ok "Installed cron jobs at $CRON_JOBS"
fi

# ── Step 6: Pipeline self-check ─────────────────────────────────────────────
info "Step 6/6 — Running scripts/check-pipeline.py --quiet ..."
if ! python3 "$SCRIPT_DIR/check-pipeline.py" --quiet; then
  die "check-pipeline.py reported failures — fix before continuing."
fi
ok "Pipeline check is green"

# ── Next steps ──────────────────────────────────────────────────────────────
echo ""
echo -e "${GRN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GRN}║   Quickstart complete — next steps:      ${NC}"
echo -e "${GRN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "1) Start (or restart) the moltbot gateway:"
echo "     pkill -f moltbot-gateway || true"
echo "     nohup moltbot gateway run --bind loopback --port 18789 --force \\"
echo "       > /tmp/moltbot-gateway.log 2>&1 &"
echo ""
echo "2) Trigger the first RSS pull manually (optional, otherwise it runs at 07:00):"
echo "     python3 $SCRIPT_DIR/ai-app-rss-collect.py"
echo ""
echo "3) Check output:"
echo "     ls $PULSAR_MEMORY_DIR/ai-app-rss-*.json"
echo "     cat $PULSAR_MEMORY_DIR/daily-stats.json 2>/dev/null || echo '(no stats yet)'"
echo ""
echo "4) Tail the gateway log to confirm cron jobs are picked up:"
echo "     tail -F /tmp/moltbot-gateway.log"
echo ""
ok "Done."
