#!/bin/bash
# Sutra plugin — /sutra:sutra-go — one-shot: onboard + enable telemetry + announce.
#
# v2.18.0 (2026-05-03): jq replaces python3 for both telemetry_optin write
# and banner read. Matches start.sh v2.13.0 EDR-killed-python3 fix.
# Without this, /sutra:sutra-go silently failed on EDR-killed-python3 hosts
# (vinit#38 class) — toggle reported success but telemetry_optin stayed false.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

cd "$PROJECT_ROOT"

# jq is required (matching start.sh v2.13.0)
if ! command -v jq >/dev/null 2>&1; then
  cat >&2 <<'EOF'
sutra go: jq is required but not found on PATH.

Install:
  macOS:    brew install jq
  Debian:   sudo apt-get install jq
  RHEL:     sudo dnf install jq
  Other:    https://jqlang.org/download/

Then re-run.
EOF
  exit 127
fi

SUTRA_AUTO_OPTIN=1 bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

if [ -f .claude/sutra-project.json ]; then
  TMP=$(mktemp ".claude/.sutra-go-XXXXXX.tmp") || { echo "✗ mktemp failed" >&2; exit 1; }
  # v2.33.0 (D50): /sutra-go is "one-shot explicit opt-in" — user typed it,
  # consenting to current PRIVACY.md (v2.33.0 identity-on-wire 4-field
  # allowlist). Write consent_version="2.33" alongside telemetry_optin so
  # first push doesn't hit re-consent gate.
  if jq '.telemetry_optin = true | .consent_version = "2.33"' .claude/sutra-project.json > "$TMP" 2>/dev/null; then
    mv -f "$TMP" .claude/sutra-project.json
  else
    rm -f "$TMP"
    echo "✗ jq transform failed — telemetry_optin not patched" >&2
    exit 1
  fi
fi

if [ -f .claude/sutra-project.json ] && jq -e . .claude/sutra-project.json >/dev/null 2>&1; then
  install_id=$(jq -r '.install_id // "<missing>"' .claude/sutra-project.json)
  project_id=$(jq -r '.project_id // "<missing>"' .claude/sutra-project.json)
  project_name=$(jq -r '.project_name // "<unnamed>"' .claude/sutra-project.json)
  sutra_version=$(jq -r '.sutra_version // "unknown"' .claude/sutra-project.json)
  optin=$(jq -r '.telemetry_optin // false' .claude/sutra-project.json)
  echo "Sutra deployed + telemetry ON"
  printf '  install_id:      %s\n' "$install_id"
  printf '  project_id:      %s\n' "$project_id"
  printf '  project_name:    %s\n' "$project_name"
  printf '  sutra_version:   %s\n' "$sutra_version"
  printf '  telemetry_optin: %s\n' "$optin"

  # v2.34.0 (D53 fleet phase, codex P2-1 fold): /sutra-go path also surfaces
  # context7 recommend. Same shape as cmd_banner — read-only probe, opt-in
  # only, no silent install.
  context7_status="recommended — claude plugin install context7@claude-plugins-official"
  if [ -f "$HOME/.claude/plugins/installed_plugins.json" ]; then
    # Codex P2-1 fold (review 2026-05-06): require scope="user" entry.
    if jq -e 'any(.plugins["context7@claude-plugins-official"][]?; .scope=="user")' "$HOME/.claude/plugins/installed_plugins.json" >/dev/null 2>&1; then
      context7_status="enabled — latest library/framework docs available"
    fi
  fi
  printf '  Context7:        %s\n' "$context7_status"

  echo
  echo 'Auto-emission is ON. Telemetry auto-pushes on Stop; run `sutra push` manually if needed.'
  echo 'Kill-switch: SUTRA_TELEMETRY=0 disables both capture and push uniformly.'
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
