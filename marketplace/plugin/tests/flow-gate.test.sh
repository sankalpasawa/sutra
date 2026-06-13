#!/bin/bash
# Unit test: hooks/flow-gate.sh  (the Flow PreToolUse soft-enforcement gate)
#
# Contract under test (CURRENT-Sutra "the Flow" spine; ADR-026 + ADR-027):
#   The hook is a PreToolUse advisory gate. On an Edit/Write to a path that is
#   NOT whitelisted, if the Flow spine markers in $REPO_ROOT/.claude/ are
#   missing, the hook nudges (stderr) + appends a row to
#   $REPO_ROOT/.enforcement/flow-gate.jsonl. It is SOFT-FIRST in v1: it must
#   ALWAYS exit 0 and must NEVER exit 2 (breaking exit 2 would break every
#   fleet client). The integrator wraps it as:
#     hooks/lib/sutra-stderr-capture.sh hooks/flow-gate.sh
#   so the hook reads PreToolUse JSON on stdin, writes nudges to stderr, and
#   exits with a code (always 0 in v1).
#
# Markers walked by the spine (written by the flow/resolver/lens/cynefin skills):
#   .claude/flow-classified     TYPE=<type> CELL=<9cell> TS=<unix>
#   .claude/flow-type-resolved  RESOLUTION=FOLLOW:<skill>|CONSTRUCT SCOPE=... TS=<unix>
#   .claude/flow-inner          LENS=<axes> CYNEFIN=<domain> FACTORS=<n> TS=<unix>
#   .claude/flow-closed         MEASURED=<check> LEARNED=<note> TS=<unix>
#
# Kill-switches (both -> exit 0, no nudge): env FLOW_DISABLED, fs $HOME/.flow-disabled
# Override: FLOW_ACK=1 -> append a JSON line to .enforcement/flow-gate-ledger.jsonl, exit 0
#
# Cases:
#   A  markers present (construct path)         -> exit 0, no nudge
#   B  markers absent, construct path           -> exit 0 (SOFT) + nudge + flow-gate.jsonl row
#   C  whitelisted path (.claude/x)             -> exit 0, no nudge
#   D  FLOW_DISABLED=1                           -> exit 0, no nudge
#   E  $HOME/.flow-disabled present (temp HOME)  -> exit 0, no nudge
#   F  FLOW_ACK=1                                -> exit 0 + flow-gate-ledger.jsonl row
#   CRITICAL: across ALL cases the hook NEVER exits 2.
#
# Test isolation note:
#   Every case runs with an ISOLATED $HOME (a fresh temp dir) so that a real
#   $HOME/.flow-disabled file on the machine running the suite cannot
#   short-circuit the hook and make CASE B (which asserts a nudge IS produced)
#   spuriously pass-through. CASE E deliberately plants .flow-disabled inside
#   its isolated HOME to exercise the fs kill-switch.
#
# Usage: bash sutra/marketplace/plugin/tests/flow-gate.test.sh
set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
HOOK="$PLUGIN_ROOT/hooks/flow-gate.sh"

# A clean, EMPTY temp HOME used as the default for every case except E.
# Guarantees no inherited $HOME/.flow-disabled kill-switch corrupts results.
CLEAN_HOME=$(mktemp -d 2>/dev/null)

PASS=0
FAIL=0
FAIL_MSGS=()

# I/O capture targets (declared before the EXIT trap can reference them).
OUT_FILE=""
ERR_FILE=""
RC=""

# Best-effort cleanup of anything we created, even on early exit.
_TRACK_DIRS=()
_track() { _TRACK_DIRS+=("$1"); }
_final_cleanup() {
  rm -f "$OUT_FILE" "$ERR_FILE" /tmp/flow-gate-syntax.err 2>/dev/null
  local d
  for d in "${_TRACK_DIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done
  [ -n "${CLEAN_HOME:-}" ] && rm -rf "$CLEAN_HOME"
}
trap _final_cleanup EXIT

_pass() { PASS=$((PASS+1)); printf '  PASS: %s\n' "$1"; }
_fail() { FAIL=$((FAIL+1)); FAIL_MSGS+=("$1 -- $2"); printf '  FAIL: %s -- %s\n' "$1" "$2"; }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Build a fresh temp REPO_ROOT with an empty .claude/ + .enforcement/ dir.
# Echoes the path. Aborts the suite if mktemp fails (cannot test without it).
_mkrepo() {
  local root
  root=$(mktemp -d 2>/dev/null) || {
    echo "FATAL: mktemp -d failed; cannot create test repo" >&2
    exit 1
  }
  mkdir -p "$root/.claude" "$root/.enforcement"
  _track "$root"
  printf '%s' "$root"
}

# Write all four spine markers into a repo's .claude/ dir.
_seed_markers() {
  local root="$1" ts
  ts=$(date +%s)
  printf 'TYPE=task CELL=DO-NEW TS=%s\n' "$ts"                        > "$root/.claude/flow-classified"
  printf 'RESOLUTION=CONSTRUCT SCOPE=none TS=%s\n' "$ts"              > "$root/.claude/flow-type-resolved"
  printf 'LENS=who,how CYNEFIN=complicated FACTORS=3 TS=%s\n' "$ts"   > "$root/.claude/flow-inner"
  printf 'MEASURED=tests-pass LEARNED=axis-minted TS=%s\n' "$ts"      > "$root/.claude/flow-closed"
}

# Invoke the hook with a PreToolUse JSON payload on stdin.
#   $1 = absolute file_path to embed in {"tool_input":{"file_path":...}}
#   $2 = REPO_ROOT (exported as CLAUDE_PROJECT_DIR)
#   $3 = extra env assignments (whitespace-separated, e.g. "FLOW_DISABLED=1"),
#        may be empty. Tokens are passed to `env` as KEY=VALUE argv so values
#        never undergo a second shell-expansion pass.
#   $4 = HOME override (optional; defaults to the isolated CLEAN_HOME).
# Captures stdout -> $OUT_FILE, stderr -> $ERR_FILE, exit code -> $RC.
_invoke() {
  local file_path="$1" repo="$2" extra="${3:-}" home_override="${4:-$CLEAN_HOME}"
  OUT_FILE=$(mktemp 2>/dev/null)
  ERR_FILE=$(mktemp 2>/dev/null)
  local json
  json=$(printf '{"tool_input":{"file_path":"%s"}}' "$file_path")
  # Split $extra into an argv array (drop empties) rather than relying on
  # unquoted word-splitting at the command site. The ${arr[@]+...} guard is
  # REQUIRED for macOS bash 3.2, where an empty "${arr[@]}" under set -u raises
  # "unbound variable" -- fleet clients run the default system bash.
  local -a extra_env=()
  local tok
  for tok in $extra; do [ -n "$tok" ] && extra_env+=("$tok"); done
  printf '%s' "$json" \
    | env CLAUDE_PROJECT_DIR="$repo" HOME="$home_override" ${extra_env[@]+"${extra_env[@]}"} \
        bash "$HOOK" 1>"$OUT_FILE" 2>"$ERR_FILE"
  RC=$?
}

_err_size() { wc -c < "$ERR_FILE" 2>/dev/null | tr -d ' '; }
_cleanup_invoke() { rm -f "$OUT_FILE" "$ERR_FILE"; OUT_FILE=""; ERR_FILE=""; }

echo "==============================================================="
echo "  flow-gate.sh -- Flow soft-gate unit test"
echo "==============================================================="

# ---------------------------------------------------------------------------
# 0) Pre-flight: hook exists + syntax-checks
# ---------------------------------------------------------------------------
echo ""
echo "[0] pre-flight"
if [ -f "$HOOK" ]; then
  _pass "hook file exists ($HOOK)"
else
  _fail "hook file exists" "missing: $HOOK"
  echo ""
  echo "  Cannot run behavioural cases without the hook. Aborting."
  echo "==============================================================="
  exit 1
fi

if bash -n "$HOOK" 2>/tmp/flow-gate-syntax.err; then
  _pass "bash -n syntax check"
else
  _fail "bash -n syntax check" "$(cat /tmp/flow-gate-syntax.err)"
fi
rm -f /tmp/flow-gate-syntax.err

# Track that exit 2 is NEVER observed across the whole run.
SAW_EXIT_2=0
_guard_never_2() {
  # $1 = case label, $2 = observed RC
  if [ "$2" = "2" ]; then
    SAW_EXIT_2=1
    _fail "$1 NEVER exit 2" "hook exited 2 (SOFT-FIRST violated)"
  fi
}

# ---------------------------------------------------------------------------
# CASE A -- markers present on a construct path -> exit 0, no nudge
# ---------------------------------------------------------------------------
echo ""
echo "[A] markers present -> exit 0, silent"
REPO_A=$(_mkrepo)
_seed_markers "$REPO_A"
_invoke "$REPO_A/holding/foo.ts" "$REPO_A" ""
_guard_never_2 "A" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "A exit 0"; else _fail "A exit 0" "got rc=$RC"; fi
if [ "${ESZ:-0}" -eq 0 ]; then _pass "A no nudge on stderr"; else _fail "A no nudge" "stderr=$ESZ bytes: $(cat "$ERR_FILE")"; fi
# A construct path with markers present must NOT append a flow-gate.jsonl row.
if [ ! -s "$REPO_A/.enforcement/flow-gate.jsonl" ]; then
  _pass "A no flow-gate.jsonl row"
else
  _fail "A no flow-gate.jsonl row" "row appended despite markers present"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE B -- markers absent on construct path -> exit 0 SOFT + nudge + jsonl row
# ---------------------------------------------------------------------------
echo ""
echo "[B] markers absent, construct path -> exit 0 (SOFT) + nudge + jsonl row"
REPO_B=$(_mkrepo)   # .claude/ exists but NO markers seeded
_invoke "$REPO_B/holding/foo.ts" "$REPO_B" ""
_guard_never_2 "B" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "B exit 0 (SOFT, never blocks)"; else _fail "B exit 0" "got rc=$RC (SOFT-FIRST requires 0)"; fi
if [ "${ESZ:-0}" -gt 0 ]; then
  _pass "B nudge written to stderr ($ESZ bytes)"
else
  _fail "B nudge on stderr" "stderr empty -- expected an advisory nudge"
fi
if [ -s "$REPO_B/.enforcement/flow-gate.jsonl" ]; then
  _pass "B row appended to .enforcement/flow-gate.jsonl"
else
  _fail "B flow-gate.jsonl row" "no row appended"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE C -- whitelisted path (.claude/x) -> exit 0, no nudge
# ---------------------------------------------------------------------------
echo ""
echo "[C] whitelisted path (.claude/x) -> exit 0, silent"
REPO_C=$(_mkrepo)   # no markers; path itself is whitelisted so gate must not fire
_invoke "$REPO_C/.claude/x" "$REPO_C" ""
_guard_never_2 "C" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "C exit 0"; else _fail "C exit 0" "got rc=$RC"; fi
if [ "${ESZ:-0}" -eq 0 ]; then _pass "C no nudge on stderr"; else _fail "C no nudge" "stderr=$ESZ bytes: $(cat "$ERR_FILE")"; fi
if [ ! -s "$REPO_C/.enforcement/flow-gate.jsonl" ]; then
  _pass "C no flow-gate.jsonl row (whitelisted)"
else
  _fail "C no flow-gate.jsonl row" "row appended for whitelisted path"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE D -- FLOW_DISABLED=1 -> exit 0, no nudge
# ---------------------------------------------------------------------------
echo ""
echo "[D] FLOW_DISABLED=1 kill-switch -> exit 0, silent"
REPO_D=$(_mkrepo)   # construct path + no markers, but kill-switch must short-circuit
_invoke "$REPO_D/holding/foo.ts" "$REPO_D" "FLOW_DISABLED=1"
_guard_never_2 "D" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "D exit 0"; else _fail "D exit 0" "got rc=$RC"; fi
if [ "${ESZ:-0}" -eq 0 ]; then _pass "D no nudge on stderr"; else _fail "D no nudge" "stderr=$ESZ bytes: $(cat "$ERR_FILE")"; fi
if [ ! -s "$REPO_D/.enforcement/flow-gate.jsonl" ]; then
  _pass "D no flow-gate.jsonl row (kill-switch)"
else
  _fail "D no flow-gate.jsonl row" "row appended despite FLOW_DISABLED=1"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE E -- $HOME/.flow-disabled present (temp HOME) -> exit 0, no nudge
# ---------------------------------------------------------------------------
echo ""
echo "[E] \$HOME/.flow-disabled fs kill-switch (temp HOME) -> exit 0, silent"
REPO_E=$(_mkrepo)
TMP_HOME=$(mktemp -d)
_track "$TMP_HOME"
touch "$TMP_HOME/.flow-disabled"
_invoke "$REPO_E/holding/foo.ts" "$REPO_E" "" "$TMP_HOME"
_guard_never_2 "E" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "E exit 0"; else _fail "E exit 0" "got rc=$RC"; fi
if [ "${ESZ:-0}" -eq 0 ]; then _pass "E no nudge on stderr"; else _fail "E no nudge" "stderr=$ESZ bytes: $(cat "$ERR_FILE")"; fi
if [ ! -s "$REPO_E/.enforcement/flow-gate.jsonl" ]; then
  _pass "E no flow-gate.jsonl row (fs kill-switch)"
else
  _fail "E no flow-gate.jsonl row" "row appended despite \$HOME/.flow-disabled"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE F -- FLOW_ACK=1 override -> exit 0 + ledger row
# ---------------------------------------------------------------------------
echo ""
echo "[F] FLOW_ACK=1 override -> exit 0 + flow-gate-ledger.jsonl row"
REPO_F=$(_mkrepo)   # construct path + no markers; override path engaged
_invoke "$REPO_F/holding/foo.ts" "$REPO_F" "FLOW_ACK=1"
_guard_never_2 "F" "$RC"
if [ "$RC" = "0" ]; then _pass "F exit 0"; else _fail "F exit 0" "got rc=$RC"; fi
if [ -s "$REPO_F/.enforcement/flow-gate-ledger.jsonl" ]; then
  _pass "F row appended to .enforcement/flow-gate-ledger.jsonl"
  # Best-effort: confirm the ledger row is valid JSON if jq is available.
  if command -v jq >/dev/null 2>&1; then
    if tail -n1 "$REPO_F/.enforcement/flow-gate-ledger.jsonl" | jq -e . >/dev/null 2>&1; then
      _pass "F ledger row is valid JSON"
    else
      _fail "F ledger row is valid JSON" "last line not parseable by jq"
    fi
  fi
else
  _fail "F flow-gate-ledger.jsonl row" "no override row appended"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CRITICAL -- defensive inputs must also never exit 2
# ---------------------------------------------------------------------------
echo ""
echo "[*] defensive inputs never exit 2"
REPO_G=$(_mkrepo)
for payload in '' '{}' 'not json' '{"tool_input":{}}'; do
  OUT_FILE=$(mktemp); ERR_FILE=$(mktemp)
  # Isolated HOME here too, so a real ~/.flow-disabled never masks a genuine
  # non-zero exit on malformed input.
  printf '%s' "$payload" \
    | env CLAUDE_PROJECT_DIR="$REPO_G" HOME="$CLEAN_HOME" bash "$HOOK" 1>"$OUT_FILE" 2>"$ERR_FILE"
  drc=$?
  _guard_never_2 "defensive[${payload:0:12}]" "$drc"
  if [ "$drc" = "0" ]; then
    _pass "defensive exit 0 on input: [${payload:0:20}]"
  else
    _fail "defensive exit 0" "input='${payload:0:20}' rc=$drc"
  fi
  rm -f "$OUT_FILE" "$ERR_FILE"; OUT_FILE=""; ERR_FILE=""
done

# ---------------------------------------------------------------------------
# CRITICAL -- global SOFT-FIRST assertion across the whole run
# ---------------------------------------------------------------------------
echo ""
echo "[CRITICAL] SOFT-FIRST: hook never exited 2 in any case"
if [ "$SAW_EXIT_2" -eq 0 ]; then
  _pass "no exit 2 observed across all cases"
else
  _fail "no exit 2 observed" "at least one case exited 2 -- v1 must be soft-only"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS+FAIL))
echo ""
echo "==============================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "  ALL PASS -- $PASS/$TOTAL checks"
  echo "==============================================================="
  exit 0
else
  echo "  FAILED -- $PASS/$TOTAL passed - $FAIL failing"
  echo "==============================================================="
  echo ""
  echo "Failures:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
  echo ""
  exit 1
fi