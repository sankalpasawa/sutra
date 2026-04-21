#!/bin/bash
# Sutra: update-banner — SessionStart hook
# Compares installed plugin version to last-seen version. If changed, prints
# a one-time banner announcing the update + changelog link. Silent otherwise.
#
# No network, no file writes outside ~/.sutra/.

set -uo pipefail

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
LAST_SEEN_FILE="$SUTRA_HOME/last-seen-version"

[ -z "${CLAUDE_PLUGIN_ROOT:-}" ] && exit 0

MANIFEST="$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json"
[ ! -f "$MANIFEST" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  CURRENT=$(jq -r '.version // empty' "$MANIFEST" 2>/dev/null)
else
  CURRENT=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST" | head -1)
fi

[ -z "$CURRENT" ] && exit 0

LAST_SEEN=""
[ -f "$LAST_SEEN_FILE" ] && LAST_SEEN=$(head -1 "$LAST_SEEN_FILE" 2>/dev/null || echo "")

mkdir -p "$SUTRA_HOME" 2>/dev/null
echo "$CURRENT" > "$LAST_SEEN_FILE"

# First run ever — record, don't nag
[ -z "$LAST_SEEN" ] && exit 0

# Unchanged — silent
[ "$CURRENT" = "$LAST_SEEN" ] && exit 0

# Changed — announce on stderr so Claude sees it without polluting session output
cat >&2 <<EOF

────────────────────────────────────────────────────────────────
Sutra updated: $LAST_SEEN → $CURRENT
Changelog: https://github.com/sankalpasawa/sutra/blob/main/marketplace/plugin/CHANGELOG.md
(If a slash command stopped working, check the changelog — we occasionally rename.)
────────────────────────────────────────────────────────────────

EOF

exit 0
