#!/usr/bin/env bash
# Sutra Native — one-line installer
#
# Usage:
#   curl -fsSL https://sutra-os.vercel.app/native/install | bash
#   curl -fsSL https://sutra-os.vercel.app/native/install | bash -s -- -y   # non-interactive
#
# What this does:
#   1. Verifies prerequisites (git, node ≥20)
#   2. Creates ./sutra/native/ in your current directory
#   3. Downloads the Sutra Native source preview (~5 MB)
#   4. Installs npm dependencies
#   5. Registers Sutra marketplace with Claude Code if present
#
# Native v1.0.2 ships as a SOURCE PREVIEW — the engine source tree
# (V2.4 architecture: 4 primitives + 6 laws + Skill Engine R4 + 6 terminal
# checks). Functional usage today is via tsx/bun. Hook activation +
# npm-style entrypoint land in v1.x.
#
# Source: github.com/sankalpasawa/sutra/blob/main/website/native/install.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUTRA_REPO="https://github.com/sankalpasawa/sutra.git"
TARGET_DIR="${SUTRA_NATIVE_TARGET:-$PWD/sutra/native}"
NON_INTERACTIVE=0
NATIVE_VERSION="v1.0.2"

while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes) NON_INTERACTIVE=1 ;;
    -h|--help)
      sed -n '1,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Display helpers (no unicode box-drawing — ASCII + ANSI only)
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'
  C_DIM=$'\033[2m'
  C_BOLD=$'\033[1m'
  C_GOLD=$'\033[38;5;179m'
  C_BLUE=$'\033[38;5;75m'
  C_GREEN=$'\033[38;5;78m'
  C_RED=$'\033[38;5;203m'
  C_GREY=$'\033[38;5;245m'
else
  C_RESET= C_DIM= C_BOLD= C_GOLD= C_BLUE= C_GREEN= C_RED= C_GREY=
fi

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s  ok%s  %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_GOLD" "$C_RESET" "$*"; }
fail() { printf '%sfail%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }
step() { printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"; }
hr()   { printf '%s%s%s\n' "$C_GREY" "------------------------------------------------------------" "$C_RESET"; }

banner() {
  printf '%s' "$C_GOLD"
  cat <<'BANNER'
   _   _      _   _
  | \ | |__ _| |_(_)_ _____
  |  \| / _` |  _| \ V / -_)
  |_|\__\__,_|\__|_|\_/\___|
BANNER
  printf '%s\n' "$C_RESET"
  printf '  %sSutra Native %s%s — one founder, one LLM, a whole company.%s\n' \
    "$C_BOLD" "$NATIVE_VERSION" "$C_RESET" ""
  printf '  %ssource preview · V2.4 architecture · 412 tests · ADVISORY-cleared%s\n' "$C_GREY" "$C_RESET"
  echo
}

# ---------------------------------------------------------------------------
# Onboarding — show what installs, get consent
# ---------------------------------------------------------------------------
banner

cat <<EOF
${C_BOLD}What is Native?${C_RESET}
The deployable Sutra plugin. The runtime that lets one founder + one LLM
operate a whole company autonomously — built on commodity infra (Anthropic
Claude SDK + Temporal + OPA + OpenTelemetry) with ~1700 LOC of Sutra glue
providing governance, composition, and decision provenance.

${C_BOLD}What this script will install${C_RESET}
  ${C_GOLD}*${C_RESET} ${C_BOLD}Location:${C_RESET}        ${TARGET_DIR}
  ${C_GOLD}*${C_RESET} ${C_BOLD}Source:${C_RESET}          sutra/marketplace/native (sparse clone)
  ${C_GOLD}*${C_RESET} ${C_BOLD}Footprint:${C_RESET}       ~5 MB engine source + ~80 MB node_modules
  ${C_GOLD}*${C_RESET} ${C_BOLD}Network:${C_RESET}         git clone github.com/sankalpasawa/sutra · npm registry
  ${C_GOLD}*${C_RESET} ${C_BOLD}Claude Code:${C_RESET}     marketplace add (skipped if claude CLI absent)

${C_BOLD}What Native gives you${C_RESET}
  ${C_BLUE}-${C_RESET} 4 primitives    Domain · Charter · Workflow · Execution
  ${C_BLUE}-${C_RESET} 6 laws          DATA · BOUNDARY · ACTIVATION · COMMITMENT · META · REFLEXIVITY
  ${C_BLUE}-${C_RESET} 9 capabilities  Identity · Authority · Workflow durability · Coordination
                  Tool invocation · Telemetry · Skills · Repo conv · LLM
  ${C_BLUE}-${C_RESET} Decision provenance  every governance decision logged + queryable
  ${C_BLUE}-${C_RESET} Time-to-value        ≤30 min from install to first Workflow execution
  ${C_BLUE}-${C_RESET} Governance overhead  ≤15% of session tokens

${C_BOLD}What it does NOT do (yet, v1.0.2)${C_RESET}
  ${C_GREY}-${C_RESET} Hook activation is deferred to v1.x — engine runs via tsx today
  ${C_GREY}-${C_RESET} npm-style entrypoint deferred — sources ship as .ts
  ${C_GREY}-${C_RESET} Cutover from Core plugin: see MIGRATION.md after install

EOF

if [ "$NON_INTERACTIVE" -ne 1 ]; then
  printf '%sInstall to %s%s%s? [Y/n] %s' "$C_BOLD" "$C_GOLD" "$TARGET_DIR" "$C_RESET" "$C_RESET"
  read -r reply </dev/tty || reply="y"
  case "${reply:-y}" in
    [Nn]*) say "${C_GREY}aborted by user.${C_RESET}"; exit 0 ;;
  esac
fi

# ---------------------------------------------------------------------------
# Step 1 — prerequisites
# ---------------------------------------------------------------------------
step "1/5  Checking prerequisites"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required tool: $1 — please install and re-run"
  fi
  ok "$1 — $(command -v "$1")"
}

require git

if command -v node >/dev/null 2>&1; then
  node_version="$(node -v 2>/dev/null | sed 's/^v//')"
  node_major="${node_version%%.*}"
  if [ -z "$node_major" ] || [ "$node_major" -lt 20 ] 2>/dev/null; then
    fail "node ≥20 required (found v${node_version}) — upgrade and re-run"
  fi
  ok "node — v${node_version}"
else
  fail "missing required tool: node ≥20 — install from nodejs.org and re-run"
fi

require npm

CLAUDE_CLI=0
if command -v claude >/dev/null 2>&1; then
  ok "claude — $(command -v claude) (Sutra marketplace will be registered)"
  CLAUDE_CLI=1
else
  warn "claude CLI not found — skipping marketplace step (Native source still installs)"
  warn "       install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
fi

# ---------------------------------------------------------------------------
# Step 2 — target directory
# ---------------------------------------------------------------------------
step "2/5  Preparing target directory"

if [ -e "$TARGET_DIR" ]; then
  if [ -d "$TARGET_DIR/.git" ] || [ -f "$TARGET_DIR/package.json" ]; then
    warn "$TARGET_DIR already populated — refusing to overwrite"
    say  "       remove it (rm -rf $TARGET_DIR) or set SUTRA_NATIVE_TARGET to install elsewhere"
    exit 2
  fi
fi

mkdir -p "$(dirname "$TARGET_DIR")"
ok "parent ready — $(dirname "$TARGET_DIR")"

# ---------------------------------------------------------------------------
# Step 3 — sparse clone of sutra/marketplace/native
# ---------------------------------------------------------------------------
step "3/5  Downloading Native source preview"

TMP_DIR="$(mktemp -d -t sutra-native-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

# Sparse + shallow clone keeps download tiny
git clone \
  --filter=blob:none \
  --depth 1 \
  --sparse \
  --quiet \
  "$SUTRA_REPO" \
  "$TMP_DIR/sutra"

(
  cd "$TMP_DIR/sutra"
  # --quiet is not supported by older git sparse-checkout (pre-2.43)
  # so we suppress its progress output explicitly instead.
  git sparse-checkout set marketplace/native >/dev/null
)

if [ ! -d "$TMP_DIR/sutra/marketplace/native" ]; then
  fail "sparse-clone returned no marketplace/native — repo layout drift?"
fi

mv "$TMP_DIR/sutra/marketplace/native" "$TARGET_DIR"
ok "source installed — $TARGET_DIR"

# ---------------------------------------------------------------------------
# Step 4 — npm install
# ---------------------------------------------------------------------------
step "4/5  Installing npm dependencies"

(
  cd "$TARGET_DIR"
  npm install --silent --no-audit --no-fund --loglevel=error
)
ok "node_modules ready"

# ---------------------------------------------------------------------------
# Step 5 — register Sutra marketplace with Claude Code (optional)
# ---------------------------------------------------------------------------
step "5/5  Registering Sutra marketplace with Claude Code"

if [ "$CLAUDE_CLI" -eq 1 ]; then
  if claude plugin marketplace list 2>/dev/null | grep -q "sankalpasawa/sutra"; then
    ok "marketplace already registered"
  else
    if claude plugin marketplace add sankalpasawa/sutra >/dev/null 2>&1; then
      ok "marketplace added — sankalpasawa/sutra"
    else
      warn "marketplace add failed — register manually:"
      say  "       claude plugin marketplace add sankalpasawa/sutra"
    fi
  fi
else
  say "${C_GREY}skipped (no claude CLI)${C_RESET}"
fi

# ---------------------------------------------------------------------------
# Done — next steps
# ---------------------------------------------------------------------------
echo
hr
printf '%s  Sutra Native installed%s\n' "$C_GREEN$C_BOLD" "$C_RESET"
hr

cat <<EOF

  ${C_BOLD}Native lives at:${C_RESET}  ${C_GOLD}${TARGET_DIR}${C_RESET}

  ${C_BOLD}Try it now${C_RESET}

    ${C_BLUE}# 1. Run the time-to-value dogfood (≤30 min target)${C_RESET}
    cd "$TARGET_DIR"
    npx tsx scripts/dogfood-time-to-value.ts

    ${C_BLUE}# 2. Install the plugin in Claude Code${C_RESET}
    claude
    /plugin install native@sutra

  ${C_BOLD}Read next${C_RESET}
    README           ${TARGET_DIR}/README.md
    Migration        ${TARGET_DIR}/MIGRATION.md         (Core → Native cutover)
    Sutra OS         https://sutra-os.vercel.app

  ${C_BOLD}Feedback${C_RESET}
    gh issues        github.com/sankalpasawa/sutra/issues
    discord          run /core:start in Claude Code, then /core:join-discord

EOF

exit 0
