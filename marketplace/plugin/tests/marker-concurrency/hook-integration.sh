#!/usr/bin/env bash
# tests/marker-concurrency/run.sh -- two-session marker concurrency fixture.
#
# Phase 0 acceptance gate of the marker-race migration
# (holding/research/2026-07-30-marker-race-root-cause.md, section 6). Pattern:
# hooks/marker-smoke-test.sh + hooks/reset-guard-test.sh -- a temp repo root,
# two session ids, and direct invocation of the lib + the live hooks.
#
# Pinned contract under test (ADR-029 worker contract, 2026-07-30):
#   - sutra_marker_write/set stamps SESSION=<sid> + TS= and writes the session
#     dir (dual-writing the legacy global twin transitionally).
#   - Read adopts a global twin ONLY when its SESSION= field is absent or equals
#     the reading session's sid. Foreign-stamped globals are IGNORED and logged,
#     never adopted, regardless of SUTRA_MARKER_ADOPT.
#   - Reset (lib AND the live reset-turn-markers.sh hook) NEVER deletes
#     unstamped or foreign-stamped globals; with an empty self sid it deletes
#     no global at all.
#   - No HARD-gate decision is ever keyed to a peer session's marker.
#
# Six named cases; exit 0 = all pass, exit 1 = first failure (named).
#
# Usage: bash sutra/marketplace/plugin/tests/marker-concurrency/run.sh

set -u

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
HOOKS="$ROOT/hooks"
LIB="$HOOKS/marker-lib.sh"
GATE="$HOOKS/flow-gate.sh"
RESET="$HOOKS/reset-turn-markers.sh"

for f in "$LIB" "$GATE" "$RESET"; do
  [ -f "$f" ] || { echo "CONCURRENCY-FAIL: missing $f"; exit 1; }
done
command -v jq >/dev/null 2>&1 || { echo "CONCURRENCY-FAIL: jq required"; exit 1; }

# Unique temp repo root per run (codex 2026-07-30: no stale legacy globals can
# leak between runs) + an empty HOME so a real ~/.flow-disabled cannot
# short-circuit the gate case.
T=$(mktemp -d) || exit 1
H=$(mktemp -d) || exit 1
cleanup() { rm -rf "$T" "$H"; }
trap cleanup EXIT
mkdir -p "$T/.claude" "$T/.enforcement" "$T/holding"

export CLAUDE_PROJECT_DIR="$T"
# shellcheck disable=SC1090
. "$LIB"

SIDA="sid-aaaa-1111"
SIDB="sid-bbbb-2222"
DIRA="$T/.claude/sessions/$SIDA"
DIRB="$T/.claude/sessions/$SIDB"

fail() { echo "CONCURRENCY-FAIL [$CASE]: $1"; exit 1; }
ok()   { echo "  PASS [$CASE] $1"; }

# ---------------------------------------------------------------------------
CASE="1-write-isolation"
# A and B write the SAME marker name; each session dir carries only its own
# SESSION= stamp -- no cross-SESSION= file in either session dir.
# ---------------------------------------------------------------------------
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_write depth-registered "DEPTH=5 from-a"
CLAUDE_CODE_SESSION_ID=$SIDB sutra_marker_write depth-registered "DEPTH=3 from-b"
grep -q "^SESSION=$SIDA\$" "$DIRA/depth-registered" || fail "A's marker not stamped SESSION=$SIDA"
grep -q "^SESSION=$SIDB\$" "$DIRB/depth-registered" || fail "B's marker not stamped SESSION=$SIDB"
grep -rq "SESSION=$SIDB" "$DIRA" && fail "B's SESSION= stamp found inside A's session dir"
grep -rq "SESSION=$SIDA" "$DIRB" && fail "A's SESSION= stamp found inside B's session dir"
[ "$(head -1 "$DIRA/depth-registered")" = "DEPTH=5 from-a" ] || fail "A's body clobbered by B's write"
ok "same-name writes land in separate session dirs, no cross-stamp"

# ---------------------------------------------------------------------------
CASE="2-adopt-self-or-unstamped"
# A global twin IS adopted when unstamped (legacy writer) or stamped with the
# reading session's own sid.
# ---------------------------------------------------------------------------
printf 'LEGACY=1\n' > "$T/.claude/legacy-unstamped"
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_has legacy-unstamped || fail "unstamped legacy global not adopted"
[ -f "$DIRA/legacy-unstamped" ] || fail "adoption did not copy into A's session dir"
printf 'MINE=1\nSESSION=%s\n' "$SIDA" > "$T/.claude/own-stamped"
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_has own-stamped || fail "self-stamped global not adopted"
ok "unstamped + self-stamped globals adopt; land in own session dir"

# ---------------------------------------------------------------------------
CASE="3-refuse-foreign-adoption"
# A global stamped with the PEER's sid is never adopted -- read misses, no file
# appears in the reader's dir, and a contamination row is logged.
# ---------------------------------------------------------------------------
printf 'X=1\nSESSION=%s\n' "$SIDB" > "$T/.claude/foreign-marker"
if CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_has foreign-marker; then
  fail "foreign-stamped global was adopted (the 13:00:46Z contamination class)"
fi
[ ! -f "$DIRA/foreign-marker" ] || fail "foreign marker copied into A's session dir"
CLAUDE_CODE_SESSION_ID=$SIDA SUTRA_MARKER_ADOPT=1 sutra_marker_has foreign-marker \
  && fail "SUTRA_MARKER_ADOPT=1 adopted a foreign-stamped global (flag must not matter)"
grep -q '"marker":"foreign-marker"' "$T/.enforcement/marker-contamination.jsonl" 2>/dev/null \
  || fail "contamination refusal not logged to marker-contamination.jsonl"
ok "foreign-stamped global ignored + logged, never adopted"

# ---------------------------------------------------------------------------
CASE="4-gate-never-keyed-to-peer"
# The HARD flow-gate, run as session A, must NOT pass on session B's markers:
# with ONLY B-stamped flow globals present it blocks (exit 2 + block row), and
# never writes a pass row keyed to the peer's state.
# ---------------------------------------------------------------------------
printf 'TYPE=task CELL=DO-NEW\nSESSION=%s\nTS=1\n' "$SIDB" > "$T/.claude/flow-classified"
printf 'RESOLUTION=CONSTRUCT SCOPE=none\nSESSION=%s\nTS=1\n' "$SIDB" > "$T/.claude/flow-type-resolved"
printf '{"session_id":"%s","tool_name":"Write","tool_input":{"file_path":"%s/holding/x.ts"}}' "$SIDA" "$T" \
  | env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID -u FLOW_DISABLED -u FLOW_ACK \
      HOME="$H" CLAUDE_PROJECT_DIR="$T" bash "$GATE" >/dev/null 2>"$T/gate.err"
rc=$?
[ "$rc" = "2" ] || fail "gate rc=$rc on peer-only markers -- decision keyed to B's marker (expected block, rc=2)"
grep -q '"event":"flow-gate-block"' "$T/.enforcement/flow-gate.jsonl" 2>/dev/null \
  || fail "block row missing from flow-gate.jsonl (rc=2 without the log line is not a real block)"
grep -q '"event":"flow-gate-pass"' "$T/.enforcement/flow-gate.jsonl" 2>/dev/null \
  && fail "pass row written from the peer's markers"
[ -s "$T/gate.err" ] || fail "no stderr nudge on block"
ok "HARD gate blocks honestly instead of passing on the peer's markers"

# ---------------------------------------------------------------------------
CASE="5-lib-reset-ownership-safe"
# sutra_marker_reset_own by A wipes A's dir + ONLY A-stamped globals. B's
# session-dir markers, B-stamped globals, and unstamped globals all survive.
# ---------------------------------------------------------------------------
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_write input-routed "TYPE=task c5-own"
printf 'RAW=1\n' > "$DIRA/never-stamped"
printf 'RAW=1\n' > "$T/.claude/never-stamped"
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_reset_own
[ ! -f "$DIRA/input-routed" ]        || fail "A's own session dir not cleared"
[ ! -f "$T/.claude/input-routed" ]   || fail "A's own stamped global not cleared (adoption loop-back reopened)"
[ ! -f "$T/.claude/own-stamped" ]    || fail "A's self-stamped global not cleared"
[ -f "$DIRB/depth-registered" ]      || fail "reset by A deleted B's session-dir marker"
grep -q "SESSION=$SIDB" "$T/.claude/depth-registered" 2>/dev/null \
  || fail "reset by A deleted or altered B-stamped global depth-registered"
[ -f "$T/.claude/never-stamped" ]    || fail "reset by A deleted an UNSTAMPED global"
[ -f "$T/.claude/flow-classified" ]  || fail "reset by A deleted B-stamped global flow-classified"
ok "lib reset: own dir + own globals only; peer + unstamped globals survive"

# ---------------------------------------------------------------------------
CASE="6-hook-reset-ownership-safe"
# The LIVE per-prompt hook (reset-turn-markers.sh), run as A on a real prompt:
# clears A's dir + A-stamped globals ONLY. B-stamped and unstamped globals
# survive. Second leg: with NO resolvable self sid, it deletes NO global.
# ---------------------------------------------------------------------------
CLAUDE_CODE_SESSION_ID=$SIDA sutra_marker_write depth-registered "DEPTH=5 leg-a"
mkdir -p "$DIRB"
printf 'HAS_OUTPUT=1\nSESSION=%s\n' "$SIDB" > "$DIRB/blueprint-registered"
printf 'HAS_OUTPUT=1\nSESSION=%s\n' "$SIDB" > "$T/.claude/blueprint-registered"
printf 'TYPE=task\n' > "$T/.claude/input-routed"   # unstamped, in the hook's legacy list
rm -f "$T/.claude/.last-reset-ts"
printf '{"prompt":"a genuine new founder prompt","session_id":"%s"}' "$SIDA" \
  | env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$T" \
      CLAUDE_PLUGIN_ROOT="$ROOT" bash "$RESET" >/dev/null 2>&1
[ ! -f "$DIRA/depth-registered" ]       || fail "hook reset did not clear A's session dir"
[ ! -f "$T/.claude/depth-registered" ]  || fail "hook reset did not clear A's own stamped global"
[ -f "$DIRB/blueprint-registered" ]     || fail "hook reset by A deleted B's session-dir marker"
[ -f "$T/.claude/blueprint-registered" ] || fail "hook reset by A deleted B-stamped global (pinned contract violation)"
[ -f "$T/.claude/input-routed" ]        || fail "hook reset by A deleted an UNSTAMPED global (pinned contract violation)"
grep -q '"event":"reset-skipped-unowned-or-foreign-global"' "$T/.enforcement/routing-misses.log" 2>/dev/null \
  || fail "hook did not log the skip rows (loop may not have evaluated)"
# Leg 2: empty self sid -> no global deletion of any kind.
rm -f "$T/.claude/.last-reset-ts"
printf '{"prompt":"another genuine prompt with no session id"}' \
  | env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$T" \
      CLAUDE_PLUGIN_ROOT="$ROOT" bash "$RESET" >/dev/null 2>&1
[ -f "$T/.claude/blueprint-registered" ] || fail "empty-SELF_SID reset deleted a stamped global"
[ -f "$T/.claude/input-routed" ]         || fail "empty-SELF_SID reset deleted an unstamped global"
ok "live hook reset: ownership-safe with a sid; deletes nothing without one"

echo "CONCURRENCY-PASS: 6/6 -- isolation + adoption + refusal + gate + lib-reset + hook-reset"
exit 0
