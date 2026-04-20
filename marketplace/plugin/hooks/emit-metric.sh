#!/bin/bash
# Sutra: emit-metric.sh — Layer B emitter (metric-shaped, PII-stripped).
# Writes one JSONL line to ~/.sutra/metrics-queue.jsonl. No network.
#
# Usage:
#   emit-metric.sh <dept> <metric> <value> [<unit>] [<window>]

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "$PLUGIN_ROOT/lib/project-id.sh"
source "$PLUGIN_ROOT/lib/queue.sh"

DEPT="${1:-}"
METRIC="${2:-}"
VALUE="${3:-}"
UNIT="${4:-count}"
WINDOW="${5:-instant}"

if [ -z "$DEPT" ] || [ -z "$METRIC" ] || [ -z "$VALUE" ]; then
  echo "usage: $0 <dept> <metric> <value> [unit] [window]" >&2
  exit 2
fi

case "$VALUE" in
  ''|*[!0-9.-]*) echo "emit-metric: value must be numeric, got: $VALUE" >&2; exit 3 ;;
esac

# Reject hard PII patterns in string fields
_pii_check() {
  case "$1" in
    *@*|*/Users/*|*/home/*) return 1 ;;
  esac
  return 0
}
for field in "$DEPT" "$METRIC" "$UNIT" "$WINDOW"; do
  if ! _pii_check "$field"; then
    echo "emit-metric: PII detected in field '$field' — rejected" >&2
    exit 4
  fi
done

VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_ROOT/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
INSTALL_ID=$(compute_install_id "$VERSION")
PROJECT_ID=$(cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null && compute_project_id)
TS=$(date +%s)

TIER=0
if [ -f "${CLAUDE_PROJECT_DIR:-$PWD}/os/SUTRA-CONFIG.md" ]; then
  TIER=$(grep -iE '^tier:' "${CLAUDE_PROJECT_DIR:-$PWD}/os/SUTRA-CONFIG.md" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '[:alpha:][:space:]')
  [ -z "$TIER" ] && TIER=0
fi

LINE=$(printf '{"schema_version":1,"install_id":"%s","project_id":"%s","ts":%s,"sutra_version":"%s","tier":%s,"dept":"%s","metric":"%s","value":%s,"unit":"%s","window":"%s"}' \
  "$INSTALL_ID" "$PROJECT_ID" "$TS" "$VERSION" "${TIER:-0}" "$DEPT" "$METRIC" "$VALUE" "$UNIT" "$WINDOW")

queue_append "$LINE"
queue_rotate_if_big >/dev/null
exit 0
