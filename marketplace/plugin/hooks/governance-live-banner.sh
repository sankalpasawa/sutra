#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/governance-live-banner.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-05-12
#
# governance-live-banner.sh — SessionStart confirmation that Sutra governance
# is actually loaded in this project (Gap #4 from testlify-deployment-gaps).
#
# WHY: Founder reported "core@sutra already installed globally" + governance
# blocks NOT firing in client session. Cannot tell from /plugin output whether
# governance runtime is live. This banner makes scope handoff visible.
#
# WHAT: One-line stdout banner with plugin version, tier, project_id, and
# routing-table marker. Visible at every SessionStart in every Sutra-enabled
# repo (T2/T3/T4). Silent skip if plugin disabled / kill-switch.
#
# KILL-SWITCH: SUTRA_LIVE_BANNER_DISABLED=1 OR ~/.sutra-live-banner-disabled

set -u
[ "${SUTRA_LIVE_BANNER_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.sutra-live-banner-disabled" ] && exit 0
[ -z "${CLAUDE_PLUGIN_ROOT:-}" ] && exit 0

# Read plugin version
MANIFEST="$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json"
VERSION="?"
if [ -f "$MANIFEST" ]; then
  if command -v jq >/dev/null 2>&1; then
    VERSION=$(jq -r '.version // "?"' "$MANIFEST" 2>/dev/null)
  else
    VERSION=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST" | head -1)
  fi
fi

# Read tier from project SUTRA-CONFIG if present, else "unset"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CONFIG="$REPO_ROOT/os/SUTRA-CONFIG.md"
TIER="unset"
if [ -f "$CONFIG" ]; then
  TIER_LINE=$(grep -i '^tier:' "$CONFIG" 2>/dev/null | head -1 | sed 's/^[Tt]ier:[[:space:]]*//' | tr -d '[:space:]')
  [ -n "$TIER_LINE" ] && TIER="$TIER_LINE"
fi

# Read client_id / project_id
PROJ_FILE="$REPO_ROOT/.claude/sutra-project.json"
PROJECT_ID="?"
if [ -f "$PROJ_FILE" ] && command -v jq >/dev/null 2>&1; then
  PROJECT_ID=$(jq -r '.project_id // .install_id // "?"' "$PROJ_FILE" 2>/dev/null)
fi

# Emit single-line banner
printf '[Sutra·LIVE] plugin=v%s · tier=%s · project=%s · governance=routing+depth+blueprint+output-trace\n' \
  "$VERSION" "$TIER" "$PROJECT_ID"

exit 0
