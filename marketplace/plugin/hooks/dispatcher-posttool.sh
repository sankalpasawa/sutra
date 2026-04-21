#!/bin/bash
# Sutra OS — Dispatcher for PostToolUse (D32, ported to marketplace plugin 2026-04-22)
#
# Hot-reloadable hook dispatcher. Reads a declared registry + per-client
# enablement switches on every invocation, fires only the intersection.
#
# Port note: the reference implementation at sutra/package/hooks/dispatcher-posttool.sh
# runs inside a fully-checked-out Sutra tree. In the marketplace plugin, the
# dispatcher is shipped via the plugin bundle and must locate config/registry
# in the CLIENT's working project (CLAUDE_PROJECT_DIR), not the plugin root.
#
# Doctrine (D32):
#   - Registry (Sutra-declared, pushed via PROTO-018):
#       $CLAUDE_PROJECT_DIR/os/hooks/posttool-registry.jsonl
#       One row per declared hook: {"matcher":"Edit|Write|Bash","hook":"foo.sh"}
#   - Enablement (per-client switches):
#       $CLAUDE_PROJECT_DIR/os/SUTRA-CONFIG.md → enabled_hooks: block
#   - Default for every declared hook: OFF. Dispatcher fires it only when
#     BOTH the registry row exists AND enabled_hooks[name] = true.
#   - Clients cannot flip enablement at runtime — Sutra does it via PROTO-018.
#
# Hook lookup order (first match wins):
#   1. ${CLAUDE_PLUGIN_ROOT}/hooks/<hook_name>   (plugin-shipped defaults)
#   2. $CLAUDE_PROJECT_DIR/os/hooks/<hook_name>  (client-local additions)
#
# Because bash re-reads this script on every invocation, and reads registry +
# config fresh each time, adding a new hook reaches LIVE sessions on the next
# tool call — no settings.json change, no restart.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
REGISTRY="$PROJECT_DIR/os/hooks/posttool-registry.jsonl"

# Silent exit when infra absent (new client, pre-deploy, or opt-out)
[ -f "$CONFIG" ]   || exit 0
[ -f "$REGISTRY" ] || exit 0

# Current tool name from env or stdin-JSON
TOOL="${TOOL_NAME:-}"
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

resolve_hook_path() {
  local name="$1"
  if [ -x "$PLUGIN_ROOT/hooks/$name" ]; then
    echo "$PLUGIN_ROOT/hooks/$name"
    return 0
  fi
  if [ -x "$PROJECT_DIR/os/hooks/$name" ]; then
    echo "$PROJECT_DIR/os/hooks/$name"
    return 0
  fi
  return 1
}

while IFS= read -r row; do
  [ -z "$row" ] && continue
  case "$row" in
    \#*|"") continue ;;
  esac
  matcher=$(printf '%s' "$row" | sed -n 's/.*"matcher"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  hook_name=$(printf '%s' "$row" | sed -n 's/.*"hook"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  [ -z "$hook_name" ] && continue

  if [ -n "$matcher" ]; then
    if ! printf '%s' "$TOOL" | grep -qE "^(${matcher})$"; then
      continue
    fi
  fi

  if ! enabled "$hook_name"; then
    continue
  fi

  hook_path=$(resolve_hook_path "$hook_name") || continue

  # Fire — pass through env + stdin; silent on failure (never block)
  if [ -n "$STDIN_JSON" ]; then
    printf '%s' "$STDIN_JSON" | bash "$hook_path" >/dev/null 2>&1 || true
  else
    bash "$hook_path" >/dev/null 2>&1 || true
  fi
done < "$REGISTRY"

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Per-fire log is at the discretion of each enabled hook. Dispatcher itself
# is silent; measurement happens through the enabled_hooks registry and the
# hooks' own telemetry.
#
### 2. Adoption mechanism
# Plugin's hooks.json registers this dispatcher under PostToolUse; on every
# plugin install the dispatcher is present. Clients opt in per-hook via their
# os/SUTRA-CONFIG.md enabled_hooks: block (default OFF).
#
### 3. Monitoring / escalation
# If no hooks fire when expected: verify REGISTRY exists, CONFIG has
# enabled_hooks: true for target, hook script is executable in plugin or
# client os/hooks/.
#
### 4. Iteration trigger
# Revise when: new event type added beyond PostToolUse; registry schema
# extended (e.g., ordering/priority); plugin gains god-mode/bypass fields.
#
### 5. DRI
# Sutra-OS. Ported 2026-04-22 from sutra/package/hooks/dispatcher-posttool.sh.
#
### 6. Decommission criteria
# Retire when: marketplace plugin migrates to a richer hook framework that
# supersedes registry+enablement (e.g., typed contract schema).
