#!/bin/bash
# sutra/marketplace/plugin/hooks/feedback-auto-override.sh
# Sutra Privacy v2.0 — auto-capture: counts governance overrides.
#
# Signals-only (allowlist-derived, no content captured).
# Privacy-gated via privacy_gate():
#   SUTRA_TELEMETRY=0 → no capture
#   no consent → in-memory only
#   consent granted → disk write
#
# Non-blocking: exits 0 on every path. Never blocks a tool call.
#
# Matches: PreToolUse (all tools)

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || exit 0
source "$LIB" 2>/dev/null || exit 0

# Allowlist of known override ACK env vars (extend as new gates ship)
KNOWN_ACK_VARS="PROTO004_ACK BUILD_LAYER_ACK CODEX_DIRECTIVE_ACK COMPLETION_PROTOCOL_ACK"

# Track which hook-ids we already counted this invocation (dedup env + command scan)
SEEN=""

_capture_if_unseen() {
  local hook_id="$1"
  case " $SEEN " in
    *" $hook_id "*) return 0 ;;  # already counted this invocation
    *) SEEN="$SEEN $hook_id" ;;
  esac
  signal_write override "$hook_id" 1 2>/dev/null || true
}

# Scan environment for known ACK vars set to 1
for var in $KNOWN_ACK_VARS; do
  val="${!var:-}"
  if [ "$val" = "1" ]; then
    hook_id=$(printf '%s' "$var" | sed -E 's|_ACK$||')
    _capture_if_unseen "$hook_id"
  fi
done

# Also scan Bash command string for inline ACK=1 patterns (user sets them inline)
CMD="${TOOL_INPUT_command:-}"
if [ -n "$CMD" ]; then
  # Extract any [A-Z_]+_ACK=1 occurrences
  while IFS= read -r pair; do
    [ -z "$pair" ] && continue
    var="${pair%=1}"
    hook_id=$(printf '%s' "$var" | sed -E 's|_ACK$||')
    _capture_if_unseen "$hook_id"
  done < <(printf '%s\n' "$CMD" | grep -oE '[A-Z_]+_ACK=1' 2>/dev/null)
fi

exit 0
