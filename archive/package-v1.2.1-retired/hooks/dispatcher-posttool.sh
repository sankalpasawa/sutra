#!/bin/bash
# Sutra OS — Dispatcher for PostToolUse (D32, 2026-04-20)
#
# Hot-reloadable hook dispatcher. Reads a declared registry + per-client
# enablement switches on every invocation, fires only the intersection.
#
# Doctrine (D32):
#   - Registry (Sutra-declared, pushed via PROTO-018):
#       os/hooks/posttool-registry.jsonl
#       One row per declared hook: {"matcher":"Edit|Write|Bash","hook":"foo.sh"}
#   - Enablement (per-client switches in os/SUTRA-CONFIG.md):
#       enabled_hooks:
#         foo.sh: true
#   - Default for every declared hook: OFF. Dispatcher fires it only when
#     BOTH the registry row exists AND enabled_hooks[name] = true.
#   - Clients cannot flip enablement at runtime — Sutra does it via PROTO-018.
#
# Because bash re-reads this script on every invocation, and reads registry +
# config fresh each time, adding a new hook reaches LIVE sessions on the next
# tool call — no settings.json change, no restart.

set -u

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
REGISTRY="$PROJECT_DIR/os/hooks/posttool-registry.jsonl"
HOOK_DIR="$(dirname "$0")"

# Silent exit when infra absent (new client, pre-deploy)
[ -f "$CONFIG" ]   || exit 0
[ -f "$REGISTRY" ] || exit 0

# Current tool name from env or stdin-JSON
TOOL="${TOOL_NAME:-}"
FILE="${TOOL_INPUT_file_path:-}"
CMD="${TOOL_INPUT_command:-}"
STDIN_JSON=""
if [ -z "$TOOL" ] && [ ! -t 0 ]; then
  STDIN_JSON=$(cat 2>/dev/null || true)
  if [ -n "$STDIN_JSON" ]; then
    TOOL=$(printf '%s' "$STDIN_JSON" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi
[ -z "$TOOL" ] && exit 0

# Parse enabled_hooks block from SUTRA-CONFIG.md — same format as enabled_methods
enabled() {
  local name="$1"
  awk -v target="$name" '
    /^enabled_hooks:/ { in_block = 1; next }
    in_block && /^[^[:space:]]/ { in_block = 0 }
    in_block {
      if (match($0, /^[[:space:]]+[^:]+:[[:space:]]*true[[:space:]]*$/)) {
        n = $0
        gsub(/^[[:space:]]+/, "", n)
        sub(/:[[:space:]]*true.*$/, "", n)
        if (n == target) { found = 1; exit }
      }
    }
    END { exit (found ? 0 : 1) }
  ' "$CONFIG"
}

# Iterate registry rows
while IFS= read -r row; do
  [ -z "$row" ] && continue
  # Skip comments
  case "$row" in
    \#*|"") continue ;;
  esac
  # Extract matcher + hook from JSON line (regex, no jq dependency)
  matcher=$(printf '%s' "$row" | sed -n 's/.*"matcher"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  hook_name=$(printf '%s' "$row" | sed -n 's/.*"hook"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  [ -z "$hook_name" ] && continue

  # Matcher check: regex match against TOOL name (simple — | is OR)
  if [ -n "$matcher" ]; then
    if ! printf '%s' "$TOOL" | grep -qE "^(${matcher})$"; then
      continue
    fi
  fi

  # Enablement check (D32 gate)
  if ! enabled "$hook_name"; then
    continue
  fi

  # Hook file must exist + be executable
  hook_path="$HOOK_DIR/$hook_name"
  [ -x "$hook_path" ] || continue

  # Fire — pass through env + stdin; silent on failure (never block)
  if [ -n "$STDIN_JSON" ]; then
    printf '%s' "$STDIN_JSON" | bash "$hook_path" >/dev/null 2>&1 || true
  else
    bash "$hook_path" >/dev/null 2>&1 || true
  fi
done < "$REGISTRY"

exit 0
