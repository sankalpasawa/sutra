#!/bin/bash
# f8: flag + docs + bin assertions for flow orchestrator mode (D62 / ADR-029).
# Prints "f8: <why>" per failed assertion. Exit 0 only if all assertions pass.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$HERE/../.." && pwd)"          # sutra/marketplace/plugin
SUTRA_DIR="$(cd "$PLUGIN_DIR/../.." && pwd)"     # sutra
BIN_DIR="$PLUGIN_DIR/bin"
DEFAULTS="$PLUGIN_DIR/sutra-defaults.json"
SKILL="$PLUGIN_DIR/skills/flow/SKILL.md"
ADR="$SUTRA_DIR/os/decisions/ADR-029-flow-orchestrator-mode.md"

RC=0
say() { echo "f8: $1"; RC=1; }

command -v jq >/dev/null 2>&1 || { say "jq not available"; exit "$RC"; }

# Assertion 1: orchestrator flag in sutra-defaults.json is "off".
# Key name is matched by path component containing "orchestrator" (parallel
# build agent owns the exact key); at least one such scalar must equal "off"
# and none may equal "on".
if [ -f "$DEFAULTS" ]; then
  vals="$(jq -r 'paths(scalars) as $p
                 | select(any($p[]; tostring | test("orchestrator")))
                 | getpath($p) | tostring' "$DEFAULTS" 2>/dev/null)"
  if [ -z "$vals" ]; then
    say "no orchestrator-keyed value found in sutra-defaults.json"
  elif printf '%s\n' "$vals" | grep -qx "on"; then
    say "orchestrator flag is 'on' in sutra-defaults.json (expected 'off')"
  elif ! printf '%s\n' "$vals" | grep -qx "off"; then
    say "orchestrator flag not 'off' (values: $(printf '%s' "$vals" | tr '\n' ' '))"
  fi
else
  say "missing $DEFAULTS"
fi

# Assertion 2: flow skill documents the mode.
if [ -f "$SKILL" ]; then
  grep -qF "Orchestrator mode (D62 / ADR-029)" "$SKILL" \
    || say "skills/flow/SKILL.md missing literal 'Orchestrator mode (D62 / ADR-029)'"
else
  say "missing $SKILL"
fi

# Assertion 3: ADR exists.
[ -f "$ADR" ] || say "missing $ADR"

# Assertion 4: the 4 bin scripts exist, are executable, bash -n clean.
# Names resolved by role keyword under bin/flow* (parallel build owns exact names).
resolve_bin() {
  local kw f
  for kw in "$@"; do
    for f in "$BIN_DIR"/*flow*"$kw"* "$BIN_DIR"/*"$kw"*; do
      [ -f "$f" ] && { printf '%s\n' "$f"; return 0; }
    done
  done
  return 1
}

check_bin() {
  local role="$1"; shift
  local b
  if ! b="$(resolve_bin "$@")"; then
    say "bin script for $role not found (looked for bin/*flow*{$*}* then bin/*{$*}*)"
    return
  fi
  [ -x "$b" ] || say "$b not executable"
  bash -n "$b" 2>/dev/null || say "$b fails bash -n"
}

check_bin validator contract valid check
check_bin matcher match resolv
check_bin factors factor
check_bin ledger ledger

exit "$RC"
