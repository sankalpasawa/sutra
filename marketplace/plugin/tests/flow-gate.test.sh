#!/bin/bash
# Unit test: hooks/flow-gate.sh  (the Flow PreToolUse enforcement gate)
#
# Contract under test (HARD since v2.39.12, founder direction 2026-06-14;
# ADR-026 + ADR-027; expectations re-pinned 2026-07-30 -- the suite previously
# asserted the retired v1 SOFT contract):
#   The hook is a PreToolUse HARD gate. On an Edit/Write to a path that is NOT
#   whitelisted, if the Flow spine markers (flow-classified + flow-type-resolved;
#   session dir via marker-lib, with transitional adoption of an unstamped or
#   self-stamped legacy global) are missing, the hook EXITS 2 -- blocking the
#   tool call -- writes the nudge to stderr, and appends a "flow-gate-block" row
#   to $REPO_ROOT/.enforcement/flow-gate.jsonl. When both markers ARE present it
#   exits 0 and appends a "flow-gate-pass" row (pass logging added 2026-07-27 so
#   the fire-rate has a denominator). Kill-switches and FLOW_ACK bypass with
#   exit 0 and no block. Registered RAW in hooks.json (NOT stderr-capture
#   wrapped) so exit 2 propagates.
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
#   A  markers present (construct path)         -> exit 0, no nudge, pass row
#   B  markers absent, construct path           -> exit 2 (HARD) + nudge + block row
#   C  whitelisted path (.claude/x)             -> exit 0, no nudge, no row
#   D  FLOW_DISABLED=1                           -> exit 0, no nudge, no row
#   E  $HOME/.flow-disabled present (temp HOME)  -> exit 0, no nudge, no row
#   F  FLOW_ACK=1                                -> exit 0 + flow-gate-ledger.jsonl row
#   CRITICAL: exit 2 is observed ONLY where a block is expected (case B);
#             whitelist, kill-switch, override and defensive paths never exit 2.
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
echo "  flow-gate.sh -- Flow HARD-gate unit test"
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

# Track that exit 2 is NEVER observed where a block is NOT expected. Case B is
# the only expected-block case (HARD contract) and does not call this guard.
SAW_EXIT_2=0
_guard_no_unexpected_2() {
  # $1 = case label, $2 = observed RC
  if [ "$2" = "2" ]; then
    SAW_EXIT_2=1
    _fail "$1 no unexpected exit 2" "hook exited 2 where no block is expected"
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
_guard_no_unexpected_2 "A" "$RC"
ESZ=$(_err_size)
if [ "$RC" = "0" ]; then _pass "A exit 0"; else _fail "A exit 0" "got rc=$RC"; fi
if [ "${ESZ:-0}" -eq 0 ]; then _pass "A no nudge on stderr"; else _fail "A no nudge" "stderr=$ESZ bytes: $(cat "$ERR_FILE")"; fi
# Markers present -> hook appends a "flow-gate-pass" row (pass logging, 2026-07-27).
if grep -q '"event":"flow-gate-pass"' "$REPO_A/.enforcement/flow-gate.jsonl" 2>/dev/null; then
  _pass "A flow-gate-pass row appended"
else
  _fail "A flow-gate-pass row" "no flow-gate-pass row in flow-gate.jsonl"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE B -- markers absent on construct path -> exit 2 HARD + nudge + block row
# ---------------------------------------------------------------------------
echo ""
echo "[B] markers absent, construct path -> exit 2 (HARD) + nudge + block row"
REPO_B=$(_mkrepo)   # .claude/ exists but NO markers seeded
_invoke "$REPO_B/holding/foo.ts" "$REPO_B" ""
# Case B is the one expected-block case: no _guard_no_unexpected_2 call here.
ESZ=$(_err_size)
if [ "$RC" = "2" ]; then _pass "B exit 2 (HARD block)"; else _fail "B exit 2" "got rc=$RC (HARD contract requires 2)"; fi
if [ "${ESZ:-0}" -gt 0 ]; then
  _pass "B nudge written to stderr ($ESZ bytes)"
else
  _fail "B nudge on stderr" "stderr empty -- expected the block nudge"
fi
if grep -q '"event":"flow-gate-block"' "$REPO_B/.enforcement/flow-gate.jsonl" 2>/dev/null; then
  _pass "B flow-gate-block row appended to .enforcement/flow-gate.jsonl"
else
  _fail "B flow-gate-block row" "no flow-gate-block row appended"
fi
_cleanup_invoke

# ---------------------------------------------------------------------------
# CASE C -- whitelisted path (.claude/x) -> exit 0, no nudge
# ---------------------------------------------------------------------------
echo ""
echo "[C] whitelisted path (.claude/x) -> exit 0, silent"
REPO_C=$(_mkrepo)   # no markers; path itself is whitelisted so gate must not fire
_invoke "$REPO_C/.claude/x" "$REPO_C" ""
_guard_no_unexpected_2 "C" "$RC"
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
_guard_no_unexpected_2 "D" "$RC"
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
_guard_no_unexpected_2 "E" "$RC"
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
_guard_no_unexpected_2 "F" "$RC"
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
  _guard_no_unexpected_2 "defensive[${payload:0:12}]" "$drc"
  if [ "$drc" = "0" ]; then
    _pass "defensive exit 0 on input: [${payload:0:20}]"
  else
    _fail "defensive exit 0" "input='${payload:0:20}' rc=$drc"
  fi
  rm -f "$OUT_FILE" "$ERR_FILE"; OUT_FILE=""; ERR_FILE=""
done

# ---------------------------------------------------------------------------
# CRITICAL -- no UNEXPECTED exit 2 across the whole run (case B is the only
# expected-block case and is excluded from the guard)
# ---------------------------------------------------------------------------
echo ""
echo "[CRITICAL] HARD contract: exit 2 only where a block is expected (case B)"
if [ "$SAW_EXIT_2" -eq 0 ]; then
  _pass "no unexpected exit 2 observed across all guarded cases"
else
  _fail "no unexpected exit 2 observed" "hook exited 2 in a guarded (non-block) case"
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