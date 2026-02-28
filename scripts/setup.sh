#!/usr/bin/env bash
# Pulsar setup.sh — guided first-time deployment
# Usage: bash setup.sh [--memory-dir PATH] [--non-interactive]
# Supports: Amazon Linux / RHEL / Ubuntu / Debian / macOS
set -euo pipefail

RED='\033[0;31m' YEL='\033[0;33m' GRN='\033[0;32m' BLU='\033[0;34m' NC='\033[0m'
info()  { echo -e "${BLU}[info]${NC}  $*"; }
ok()    { echo -e "${GRN}[ ok ]${NC}  $*"; }
warn()  { echo -e "${YEL}[warn]${NC}  $*"; }
die()   { echo -e "${RED}[fail]${NC}  $*" >&2; exit 1; }
ask()   { echo -e "${YEL}  >>>  ${NC}$*"; }

PULSAR_HOME="${PULSAR_HOME:-$HOME/clawd}"
MEMORY_DIR="${PULSAR_MEMORY_DIR:-$PULSAR_HOME/memory}"
SCRIPTS_DIR="$PULSAR_HOME/scripts"
TEMPLATES_DIR="$SCRIPTS_DIR/templates"
ENV_FILE="$HOME/.clawdbot/.env"
TODAY="$(date +%Y-%m-%d)"
NON_INTERACTIVE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --memory-dir)      MEMORY_DIR="$2"; shift 2 ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    *) die "Unknown option: $1" ;;
  esac
done

prompt() {
  local var="$1" question="$2" default="${3:-}"
  if [[ $NON_INTERACTIVE -eq 1 ]]; then eval "${var}='${default}'"; return; fi
  [[ -n "$default" ]] && ask "$question [$default]: " || ask "$question: "
  read -r input
  if   [[ -z "$input" && -n "$default" ]]; then eval "${var}='${default}'"
  elif [[ -n "$input" ]];                  then eval "${var}='${input}'"
  else die "Required: $question"; fi
}

prompt_secret() {
  local var="$1" question="$2"
  if [[ $NON_INTERACTIVE -eq 1 ]]; then eval "${var}=''"; return; fi
  ask "$question (hidden): "; read -rs input; echo
  [[ -z "$input" ]] && die "Required: $question"
  eval "${var}='${input}'"
}

safe_write() {
  local dest="$1" content="$2"
  if [[ -f "$dest" && $NON_INTERACTIVE -eq 0 ]]; then
    warn "$dest already exists."
    ask "Overwrite? [y/N]: "; read -r ow
    [[ "${ow,,}" != "y" ]] && { info "Skipped $dest"; return; }
  fi
  mkdir -p "$(dirname "$dest")"
  printf '%s\n' "$content" > "$dest"
  ok "Wrote $(basename "$dest")"
}

echo ""
echo -e "${BLU}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLU}║        Pulsar — First-Time Setup         ║${NC}"
echo -e "${BLU}╚══════════════════════════════════════════╝${NC}"
echo ""
info "Memory dir : $MEMORY_DIR"
info "Scripts dir: $SCRIPTS_DIR"
echo ""

# ── Step 1: Python 3.11 ──────────────────────────────────────────────────────
info "Step 1/6 — Checking Python 3.10+ ..."
PYTHON=""
for bin in python3.11 python3.12 python3.10; do
  command -v "$bin" &>/dev/null && PYTHON="$bin" && break
done
if [[ -z "$PYTHON" ]]; then
  info "Not found — attempting install ..."
  if   command -v dnf     &>/dev/null; then sudo dnf install -y python3.11 python3.11-pip 2>&1 | grep -E "Installed|Complete|Error" || true; PYTHON=python3.11
  elif command -v apt-get &>/dev/null; then sudo apt-get update -q && sudo apt-get install -y python3.11 python3.11-pip; PYTHON=python3.11
  elif command -v brew    &>/dev/null; then brew install python@3.11; PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
  else die "Install Python 3.10+ manually and re-run."; fi
fi
ok "$($PYTHON --version)"

# ── Step 2: mcp package ──────────────────────────────────────────────────────
info "Step 2/6 — Checking mcp package ..."
if ! "$PYTHON" -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
  info "Installing mcp ..."; "$PYTHON" -m pip install mcp --quiet; ok "mcp installed"
else
  ok "mcp already installed"
fi

# ── Step 3: collect inputs ───────────────────────────────────────────────────
info "Step 3/6 — Configuration ..."
echo ""; echo "  Answer the prompts. Press Enter to accept [defaults]."; echo ""

prompt       LLM_PROVIDER      "LLM provider (dashscope/openai)" "dashscope"
prompt_secret LLM_API_KEY      "LLM API key"
prompt_secret GITHUB_TOKEN     "GitHub personal access token (repo scope)"
prompt       GITHUB_USER       "GitHub username or org" ""
prompt       GITHUB_REPO       "GitHub archive repo name" "Research-Archive"
prompt       TG_ACCOUNT        "Telegram account name (moltbot)" "default"
prompt       TG_TARGET         "Telegram chat ID" ""
prompt       DOMAIN_KEY        "Domain key slug (e.g. vla, bio, ai_app)" "research"
prompt       DOMAIN_NAME       "Domain display name" "Research"
prompt       DOMAIN_DESC       "Domain description" "My research domain"
prompt       PRIMARY_DIRECTION "Primary research direction" "Core Topic"
prompt       PRIMARY_SLUG      "Direction slug (no spaces)" "core-topic"
prompt       PRIMARY_KW        "Primary keywords (comma-separated)" "keyword1, keyword2"
echo ""

# ── Step 4: write config files ───────────────────────────────────────────────
info "Step 4/6 — Writing config files ..."
mkdir -p "$MEMORY_DIR"

# .env — only write if we have real keys
LLM_ENV_KEY="${LLM_PROVIDER^^}_API_KEY"
if [[ -n "$LLM_API_KEY" && -n "$GITHUB_TOKEN" ]]; then
  safe_write "$ENV_FILE" "# Pulsar env — generated $TODAY
${LLM_ENV_KEY}=${LLM_API_KEY}
GITHUB_TOKEN=${GITHUB_TOKEN}"
  chmod 600 "$ENV_FILE"
else
  [[ -f "$ENV_FILE" ]] && ok ".env already exists, skipping (non-interactive + no keys supplied)" || warn ".env not written: no API keys supplied in non-interactive mode"
fi

# active-config.json
IFS=',' read -ra KWS <<< "$PRIMARY_KW"
KW_ARRAY=$(printf '"%s",' "${KWS[@]}" | sed 's/[[:space:]]//g; s/,$//')
ACTIVE=$(sed \
  -e "s/{{DOMAIN_KEY}}/${DOMAIN_KEY}/g" \
  -e "s/{{TODAY}}/${TODAY}/g" \
  -e "s/{{PRIMARY_DIRECTION}}/${PRIMARY_DIRECTION}/g" \
  -e "s/{{PRIMARY_SLUG}}/${PRIMARY_SLUG}/g" \
  -e "s|\"{{PRIMARY_KEYWORD_1}}\", \"{{PRIMARY_KEYWORD_2}}\"|${KW_ARRAY}|g" \
  -e "s|\"{{KEYWORD_A_1}}\", \"{{KEYWORD_A_2}}\", \"{{KEYWORD_A_3}}\"|${KW_ARRAY}|g" \
  -e "s|\"{{KEYWORD_B_1}}\"|\"general\"|g" \
  "$TEMPLATES_DIR/active-config.template.json")
safe_write "$MEMORY_DIR/${DOMAIN_KEY}-active-config.json" "$ACTIVE"
[[ ! -f "$MEMORY_DIR/active-config.json" ]] && \
  cp "$MEMORY_DIR/${DOMAIN_KEY}-active-config.json" "$MEMORY_DIR/active-config.json" && \
  ok "Linked as active-config.json"

# domains.json
DOMAINS=$(sed \
  -e "s/{{DOMAIN_KEY}}/${DOMAIN_KEY}/g" \
  -e "s/{{DOMAIN_NAME}}/${DOMAIN_NAME}/g" \
  -e "s/{{DOMAIN_DESCRIPTION}}/${DOMAIN_DESC}/g" \
  -e "s/{{TG_ACCOUNT}}/${TG_ACCOUNT}/g" \
  -e "s/{{TG_TARGET}}/${TG_TARGET}/g" \
  "$TEMPLATES_DIR/domains.template.json")
safe_write "$MEMORY_DIR/domains.json" "$DOMAINS"

# github-config.json
GH=$(sed \
  -e "s/{{DOMAIN_KEY}}/${DOMAIN_KEY}/g" \
  -e "s/{{GITHUB_USER}}/${GITHUB_USER}/g" \
  -e "s/{{GITHUB_REPO}}/${GITHUB_REPO}/g" \
  "$TEMPLATES_DIR/github-config.template.json")
safe_write "$MEMORY_DIR/github-config-${DOMAIN_KEY}.json" "$GH"

# assumptions.json (starter — only if absent)
if [[ ! -f "$MEMORY_DIR/assumptions.json" ]]; then
  ASMPS=$(sed -e "s/{{TODAY}}/${TODAY}/g" -e "s/{{DOMAIN_KEY}}/${DOMAIN_KEY}/g" \
    "$TEMPLATES_DIR/assumptions.template.json")
  safe_write "$MEMORY_DIR/assumptions.json" "$ASMPS"
fi

# ── Step 5: path substitution ────────────────────────────────────────────────
info "Step 5/6 — Path substitution (/home/admin → $HOME) ..."
MCP_SERVER="$SCRIPTS_DIR/mcp_server.py"
if [[ "$HOME" == "/home/admin" ]]; then
  info "Home is already /home/admin — skipping path substitution"
  SUBST=0
else
  SUBST=0
  for f in "$SCRIPTS_DIR"/*.py; do
    [[ -f "$f" ]] || continue
    grep -q '/home/admin' "$f" 2>/dev/null && { sed -i "s|/home/admin|$HOME|g" "$f"; SUBST=$((SUBST+1)); }
  done
  ok "$SUBST script(s) path-substituted"
fi
# Patch mcp_server.py only when deploying to a new home (not /home/admin)
if [[ "$HOME" != "/home/admin" && -f "$MCP_SERVER" ]]; then
  sed -i "s|/home/admin/clawd/memory|${MEMORY_DIR}|g; s|/home/admin/clawd/scripts|${SCRIPTS_DIR}|g" "$MCP_SERVER"
  ok "Patched mcp_server.py → MEMORY_DIR=$MEMORY_DIR"
elif [[ -f "$MCP_SERVER" ]]; then
  ok "mcp_server.py uses PULSAR_MEMORY_DIR env var — no patch needed"
fi

# ── Step 6: verify + summary ────────────────────────────────────────────────
info "Step 6/6 — Verification ..."
ERRORS=0
chk() { [[ -f "$2" ]] && ok "$1" || { warn "MISSING $1: $2"; ERRORS=$((ERRORS+1)); }; }
chk ".env"           "$ENV_FILE"
chk "active-config"  "$MEMORY_DIR/${DOMAIN_KEY}-active-config.json"
chk "domains.json"   "$MEMORY_DIR/domains.json"
chk "github-config"  "$MEMORY_DIR/github-config-${DOMAIN_KEY}.json"
chk "mcp_server.py"  "$MCP_SERVER"
[[ $ERRORS -gt 0 ]] && warn "$ERRORS file(s) missing." || ok "All config files present."

echo ""
echo -e "${BLU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GRN}  Setup complete!${NC}"
echo -e "${BLU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Claude Desktop config (~/.config/claude/claude_desktop_config.json):"
printf '\n  {\n    "mcpServers": {\n      "pulsar": {\n        "command": "%s",\n        "args": ["%s"],\n        "env": { "PULSAR_MEMORY_DIR": "%s", "PULSAR_SCRIPTS_DIR": "%s" }\n      }\n    }\n  }\n\n' \
  "$PYTHON" "$MCP_SERVER" "$MEMORY_DIR" "$SCRIPTS_DIR"
echo "  Next steps:"
echo "  1. source $ENV_FILE"
echo "  2. $PYTHON $MCP_SERVER   # test MCP server"
echo "  3. moltbot cron add --name '${DOMAIN_NAME} RSS' --cron '0 9 * * *' \\"
echo "       --command 'python3 $SCRIPTS_DIR/${DOMAIN_KEY}-rss-collect.py'"
echo "  4. Docs: https://github.com/sou350121/Pulsar/blob/main/docs/multi-domain.md"
echo ""
