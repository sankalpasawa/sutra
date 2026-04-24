#!/usr/bin/env bash
# test-rollback-compositional.sh
set -u
SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/scripts/rollback-compositional.sh"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir -p "$TMPDIR/.claude"
cat > "$TMPDIR/.claude/settings.local.json" <<'JSON'
{
  "permissions": {
    "allow": [
      "Bash(sutra:*)",
      "Bash(compositional-read:ls+grep+tail)",
      "Bash(compositional-read:grep+head)",
      "Write(.claude/depth-registered)"
    ],
    "deny": [],
    "defaultMode": "bypassPermissions"
  }
}
JSON

(cd "$TMPDIR" && bash "$SCRIPT" >/dev/null 2>&1)

remaining=$(jq -r '[.permissions.allow[] | select(startswith("Bash(compositional-read:"))] | length' "$TMPDIR/.claude/settings.local.json")
kept=$(jq -r '.permissions.allow | length' "$TMPDIR/.claude/settings.local.json")

if [ "$remaining" = "0" ] && [ "$kept" = "2" ]; then
  echo "ok: 0 compositional-read remaining, 2 other entries preserved"
  exit 0
else
  echo "FAIL: remaining=$remaining kept=$kept (expected 0 + 2)"
  cat "$TMPDIR/.claude/settings.local.json"
  exit 1
fi
