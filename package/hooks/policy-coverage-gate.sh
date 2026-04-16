#!/bin/bash
# PROTO-017: Policy-to-Implementation Coverage Gate
#
# Fires as a Claude Code PreToolUse hook on Edit|Write|Bash.
# If the target file is a Sutra policy/protocol/manifest file, this gate:
#   - surfaces the PROTO-000 5-part reminder to stderr
#   - exits 1 by default (BLOCK with advisory) unless POLICY_ACK=1 is set
#     on the same invocation, or the operator has logged an exemption in
#     POLICY-EXEMPTIONS.md within the past 10 minutes.
#
# Not a shell-injection surface — only reads TOOL_INPUT_file_path and logs
# to a known file. The policy-file match is substring-based on well-known
# sutra/layer2-operating-system/ paths, so files outside the repo that
# happen to share a suffix could trigger the gate; this is conservative
# (false-positive on match) rather than unsafe.
#
# Fixes vs prior revision (post-codex review):
#   - Comments accurately describe behavior; exit code matches policy.
#   - Tracks BASH tool too (previously only Edit|Write — sed/awk bypass).
#   - Exemption path actually implemented + logged.
#
# Bypass for one-off: POLICY_ACK=1 with POLICY_ACK_REASON="..." — both
# appended to .enforcement/policy-acks.log with timestamp.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="$REPO_ROOT/.enforcement"
mkdir -p "$LOG_DIR"

FILE_PATH="${TOOL_INPUT_file_path:-}"
BASH_CMD="${TOOL_INPUT_command:-}"

# Claude Code stdin-JSON fallback (codex P1 fix 2026-04-16) — modern payloads
# deliver tool_input via stdin JSON instead of env vars. Same pattern as
# dispatcher-pretool.sh / cascade-check.sh / process-fix-check.sh.
if [ -z "$FILE_PATH" ] && [ -z "$BASH_CMD" ] && [ ! -t 0 ]; then
  _JSON=$(cat)
  if [ -n "$_JSON" ]; then
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
      BASH_CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
      BASH_CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
  fi
fi

# Use FILE_PATH primarily; fall back to BASH_CMD for the policy-surface check.
[ -z "$FILE_PATH" ] && [ -z "$BASH_CMD" ] && exit 0
# Maintain backward compatibility: policy-file matcher below uses FILE_PATH,
# while Bash-command matcher uses BASH_CMD (already handled below).
if [ -z "$FILE_PATH" ] && [ -n "$BASH_CMD" ]; then
  FILE_PATH="$BASH_CMD"  # legacy behavior — some downstream checks use FILE_PATH
fi

# Normalize paths — scan for the policy surface as substrings of the file path
IS_POLICY=0
case "$FILE_PATH" in
  *sutra/layer2-operating-system/PROTOCOLS.md)               IS_POLICY=1 ;;
  *sutra/layer2-operating-system/MANIFEST-*.md)              IS_POLICY=1 ;;
  *sutra/layer2-operating-system/CLIENT-ONBOARDING.md)       IS_POLICY=1 ;;
  *sutra/layer2-operating-system/ENFORCEMENT.md)             IS_POLICY=1 ;;
  *sutra/layer2-operating-system/templates/SUTRA-CONFIG*.md) IS_POLICY=1 ;;
  *sutra/layer2-operating-system/d-engines/*.md)             IS_POLICY=1 ;;
esac

# Bash tool: detect if the command touches a policy file (sed/awk/tee/rm/mv)
if [ -n "$BASH_CMD" ]; then
  case "$BASH_CMD" in
    *PROTOCOLS.md*|*MANIFEST-*.md*|*CLIENT-ONBOARDING.md*|*ENFORCEMENT.md*|*d-engines/*.md*)
      IS_POLICY=1 ;;
  esac
fi

[ "$IS_POLICY" = "0" ] && exit 0

# Exemption check: explicit ACK on this invocation
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "${POLICY_ACK:-0}" = "1" ]; then
  REASON="${POLICY_ACK_REASON:-no-reason-given}"
  # Strip newlines defensively (prevent log forgery)
  REASON_SAFE=$(printf '%s' "$REASON" | tr -d '\n\r')
  echo "$TS POLICY_ACK=1 file=$FILE_PATH reason=$REASON_SAFE" >> "$LOG_DIR/policy-acks.log"
  exit 0
fi

# Time-boxed exemption: .enforcement/policy-exempt.active younger than 10 min
EXEMPT_FILE="$LOG_DIR/policy-exempt.active"
if [ -f "$EXEMPT_FILE" ]; then
  AGE=$(( $(date +%s) - $(stat -f %m "$EXEMPT_FILE" 2>/dev/null || stat -c %Y "$EXEMPT_FILE" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 600 ]; then
    echo "$TS TIME_EXEMPT age=${AGE}s file=$FILE_PATH" >> "$LOG_DIR/policy-acks.log"
    exit 0
  fi
fi

cat >&2 <<EOF
╭──────────────────────────────────────────────────────────────╮
│  PROTO-017 POLICY GATE — BLOCKING                            │
│                                                              │
│  Target: $FILE_PATH
│                                                              │
│  Sutra policy file. PROTO-000 requires all 5 parts:          │
│    DEFINED → CONNECTED → IMPLEMENTED → TESTED → DEPLOYED     │
│                                                              │
│  Before proceeding, EITHER:                                  │
│    a) Pair this edit with an executable artifact AND a       │
│       deployment in the same change set, OR                  │
│    b) Set POLICY_ACK=1 POLICY_ACK_REASON="..." on the tool   │
│       invocation (logged to .enforcement/policy-acks.log),   │
│       OR                                                     │
│    c) touch .enforcement/policy-exempt.active for a 10-min   │
│       batch edit window.                                     │
│                                                              │
│  After edits: bash holding/hooks/verify-policy-coverage.sh   │
╰──────────────────────────────────────────────────────────────╯
EOF

# Log the block attempt
echo "$TS BLOCK file=$FILE_PATH" >> "$LOG_DIR/policy-acks.log"

exit 1
