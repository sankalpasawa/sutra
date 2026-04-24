#!/usr/bin/env bash
# rollback-compositional.sh — strip Bash(compositional-read:*) entries from
# the current project's .claude/settings.local.json.
# Shipped in plugin v2.2.0. Called by the rollback flow if Tier 1.5 is reverted.
# Idempotent. Creates a one-time .pre-rollback.bak.
#
# Usage: bash rollback-compositional.sh [SETTINGS_PATH]
#        SETTINGS_PATH defaults to .claude/settings.local.json in CWD.
set -u

SETTINGS="${1:-.claude/settings.local.json}"

if [ ! -f "$SETTINGS" ]; then
  echo "no settings.local.json at $(pwd)/$SETTINGS — nothing to do"
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq required — install via brew or apt" >&2
  exit 1
fi

if ! jq empty "$SETTINGS" >/dev/null 2>&1; then
  echo "settings.local.json is not valid JSON" >&2
  exit 1
fi

if [ ! -f "${SETTINGS}.pre-rollback.bak" ]; then
  cp "$SETTINGS" "${SETTINGS}.pre-rollback.bak"
fi

before=$(jq -r '[.permissions.allow[]? | select(startswith("Bash(compositional-read:"))] | length' "$SETTINGS")

tmp=$(mktemp)
jq '
  .permissions.allow = (
    (.permissions.allow // []) |
    map(select(startswith("Bash(compositional-read:") | not))
  )
' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"

after=$(jq -r '[.permissions.allow[]? | select(startswith("Bash(compositional-read:"))] | length' "$SETTINGS")

removed=$((before - after))
echo "rollback-compositional: removed $removed compositional-read entries from $SETTINGS"
echo "  backup: ${SETTINGS}.pre-rollback.bak"
exit 0
