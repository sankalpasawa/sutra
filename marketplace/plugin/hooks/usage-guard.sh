#!/usr/bin/env bash
# usage-guard.sh — opt-in rate-limit guard (founder direction 2026-08-07).
#
# Event: PreToolUse (no matcher) — fires on EVERY tool call, but is DORMANT
# unless ~/.sutra-usage-guard/enabled exists (clients opt in on the fly with
# `sutra-usage on`; nothing is auto-deployed behavior-wise).
#
# Behavior (delegates all logic to bin/sutra-usage check):
#   >=70% utilization  -> stderr WARNING, once per 10 min, tool call allowed
#   >=80% utilization  -> exit 2 HARD BLOCK until founder says "continue"
#                         (Claude runs `sutra-usage continue`; override
#                         auto-expires when the breaching limit window resets)
#
# Deadlock guard: a Bash call whose entire command is a bare sutra-usage
# invocation (continue/status/on/off, no chaining) is always allowed so the
# unblock path itself is never blocked.
# Fail-open: missing helper, missing python, fetch/parse errors -> exit 0.
# Kill-switch: ~/.usage-guard-disabled (founder revoke only).
set -u
GUARD_DIR="${SUTRA_USAGE_GUARD_DIR:-$HOME/.sutra-usage-guard}"
[ -f "$GUARD_DIR/enabled" ] || exit 0
[ -f "$HOME/.usage-guard-disabled" ] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="${CLAUDE_PLUGIN_ROOT:-$(dirname "$HOOK_DIR")}/bin/sutra-usage"
[ -f "$BIN" ] || BIN="$(dirname "$HOOK_DIR")/bin/sutra-usage"
[ -f "$BIN" ] || exit 0

# Allow the unblock path through (narrow match: bare sutra-usage command only).
payload="$(cat 2>/dev/null || true)"
if [ -n "$payload" ]; then
  allow="$(printf '%s' "$payload" | python3 -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
    if d.get("tool_name") == "Bash":
        c = ((d.get("tool_input") or {}).get("command") or "").strip()
        if re.match(r"^(bash\s+)?(\S*/)?sutra-usage\s+(continue|status|on|off)$", c):
            print("ALLOW")
except Exception:
    pass' 2>/dev/null || true)"
  [ "$allow" = "ALLOW" ] && exit 0
fi

out="$(bash "$BIN" check 2>/dev/null)"
rc=$?
case "$rc" in
  20) printf '%s\n' "$out" >&2; exit 2 ;;
  10) printf '%s\n' "$out" >&2; exit 0 ;;
  *)  exit 0 ;;
esac
