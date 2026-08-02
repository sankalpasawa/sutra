#!/usr/bin/env bash
# tests/marker-concurrency/run.sh -- Phase-0 acceptance gate for the marker-race
# migration (holding/research/2026-07-30-marker-race-root-cause.md section 6,
# Phase 0). Simulates TWO sessions purely via env (CLAUDE_CODE_SESSION_ID=sessA
# / sessB) against a mktemp CLAUDE_PROJECT_DIR sandbox -- never the real .claude/.
#
# Pinned API contract under test (ADR-029 worker contract, 2026-07-30):
#   sutra_marker_write NAME CONTENT -> session-dir write, SESSION=/TS= stamped
#                                      if absent, dual-writes global twin.
#   sutra_marker_read NAME          -> session-dir first; global twin adopted
#                                      ONLY if unstamped or self-stamped.
#                                      Foreign-stamped: ignored + logged, never
#                                      adopted, regardless of SUTRA_MARKER_ADOPT.
#   sutra_marker_reset_own          -> wipes own session dir + only self-stamped
#                                      globals; NEVER unstamped or foreign ones.
#
# Scenarios (per Work-Atom A4 brief):
#   s1 sessA writes depth marker -> sessB read MISSES + contamination log row
#   s2 sessB reset -> sessA marker (session dir AND self-stamped global) survives
#   s3 sessA reset -> sessA own markers gone, sessB untouched
#   s4 unstamped legacy global -> either session may adopt (TRANSITIONAL
#      allowance: an unstamped global has no provable owner, so adoption keeps
#      un-migrated govblock installs working; retired at migration Phase 6)
#   s5 self-stamped global -> self adoption works (crash-recovery path)
#   s6 stale-TS guard -> apply whatever staleness rule marker-lib has (verified
#      2026-07-30: it has NONE for TS= fields -- see s6 note; nothing asserted)
#   s7 strict mode (SUTRA_MARKER_ADOPT=0) -> global path never consulted
#      (marker-lib.sh sutra_marker_has short-circuits on the ADOPT flag BEFORE
#      the owner check): (i) self-stamped global not adopted -- the s5
#      crash-recovery path is LOST in strict; actual lib behavior asserted
#      for consistency + printed; (ii) foreign-stamped global ignored (no
#      contamination row asserted -- the strict short-circuit returns before
#      the logging branch); (iii) fresh session, zero markers -> clean MISS,
#      not a crash; (iv) placement round-trip: placement-resolve.sh writes
#      session-stamped (v2.58.0+), placement-gate.sh (hard mode) reads via
#      sutra_marker_has and must PASS with ADOPT=0 -- THE strict-mode blocker
#      check from the root-cause doc (section 2, placement-registered row:
#      strict mode must not blind the gates now that the writer is sid-aware).
#
# Output: one PASS/FAIL line per scenario + summary "marker-concurrency: N/7 PASS".
# Exit 0 only on full 7/7 pass.
#
# Companion file hook-integration.sh (archived earlier fixture) exercises the
# LIVE hooks (flow-gate, reset-turn-markers) at the same contract; this file is
# the lib-level gate registered in run-all.sh.
#
# Usage: bash sutra/marketplace/plugin/tests/marker-concurrency/run.sh

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
LIB="$PLUGIN_ROOT/hooks/marker-lib.sh"
[ -f "$LIB" ] || { echo "marker-concurrency: FATAL missing $LIB"; echo "marker-concurrency: 0/7 PASS"; exit 1; }

# mktemp sandbox -- the suite never touches the real repo's .claude/.
T=$(mktemp -d) || exit 1
cleanup() { rm -rf "$T"; }
trap cleanup EXIT
mkdir -p "$T/.claude" "$T/.enforcement"

export CLAUDE_PROJECT_DIR="$T"
# Neutralize any real session identity leaking in from the environment.
unset CLAUDE_CODE_SESSION_ID CLAUDE_SESSION_ID CLAUDE_PID 2>/dev/null || true
# shellcheck disable=SC1090
. "$LIB"

SIDA="sessA"
SIDB="sessB"
DIRA="$T/.claude/sessions/$SIDA"
DIRB="$T/.claude/sessions/$SIDB"
GLOBAL="$T/.claude"
CONTAM="$T/.enforcement/marker-contamination.jsonl"

# Session impersonation purely via env, per brief. Subshell keeps the env
# assignment scoped to the one call; filesystem effects + exit code propagate.
as_a() { ( export CLAUDE_CODE_SESSION_ID="$SIDA"; "$@" ); }
as_b() { ( export CLAUDE_CODE_SESSION_ID="$SIDB"; "$@" ); }

PASS_N=0
FAIL_N=0
FAIL_MSG=""

report() { # $1=scenario-id $2=rc $3=one-line description
  if [ "$2" -eq 0 ]; then
    echo "$1 PASS - $3"
    PASS_N=$((PASS_N+1))
  else
    echo "$1 FAIL - $3 :: ${FAIL_MSG:-unspecified}"
    FAIL_N=$((FAIL_N+1))
  fi
  FAIL_MSG=""
}

# ---------------------------------------------------------------------------
s1() { # sessA writes depth marker -> sessB read must MISS + contamination row
  as_a sutra_marker_write depth-registered "DEPTH=5 TASK=concurrency-fixture" \
    || { FAIL_MSG="sessA write failed"; return 1; }
  [ -f "$DIRA/depth-registered" ] \
    || { FAIL_MSG="marker missing from sessA session dir"; return 1; }
  grep -q "SESSION=$SIDA" "$DIRA/depth-registered" \
    || { FAIL_MSG="SESSION=$SIDA stamp missing from session-dir marker"; return 1; }
  grep -q "SESSION=$SIDA" "$GLOBAL/depth-registered" 2>/dev/null \
    || { FAIL_MSG="dual-written global twin missing or unstamped"; return 1; }
  if as_b sutra_marker_read depth-registered >/dev/null 2>&1; then
    FAIL_MSG="sessB READ sessA's marker (foreign adoption -- the 13:00:46Z contamination class)"; return 1
  fi
  [ ! -f "$DIRB/depth-registered" ] \
    || { FAIL_MSG="foreign marker was copied into sessB's session dir"; return 1; }
  grep -q '"marker":"depth-registered"' "$CONTAM" 2>/dev/null \
    || { FAIL_MSG="contamination refusal not logged to marker-contamination.jsonl"; return 1; }
  grep -q "\"foreign_sid\":\"$SIDA\"" "$CONTAM" 2>/dev/null \
    || { FAIL_MSG="contamination row does not name the foreign sid"; return 1; }
  return 0
}
s1; report s1 $? "sessA write invisible to sessB; refusal logged"

# ---------------------------------------------------------------------------
s2() { # sessB reset -> sessA marker (session dir AND self-stamped global) survives
  as_b sutra_marker_write input-routed "TYPE=task FROM=sessB" \
    || { FAIL_MSG="sessB write failed"; return 1; }
  as_b sutra_marker_reset_own \
    || { FAIL_MSG="sessB reset returned nonzero"; return 1; }
  [ ! -f "$DIRB/input-routed" ] \
    || { FAIL_MSG="sessB reset did not clear its own session dir"; return 1; }
  [ ! -f "$GLOBAL/input-routed" ] \
    || { FAIL_MSG="sessB reset left its own self-stamped global (adoption loop-back reopened)"; return 1; }
  [ -f "$DIRA/depth-registered" ] \
    || { FAIL_MSG="sessB reset DELETED sessA's session-dir marker"; return 1; }
  [ -f "$GLOBAL/depth-registered" ] && grep -q "SESSION=$SIDA" "$GLOBAL/depth-registered" \
    || { FAIL_MSG="sessB reset deleted or altered sessA's self-stamped global"; return 1; }
  return 0
}
s2; report s2 $? "sessB reset leaves sessA's session-dir marker + self-stamped global intact"

# ---------------------------------------------------------------------------
s3() { # sessA reset -> sessA own markers gone, sessB untouched
  as_b sutra_marker_write flow-classified "TYPE=task CELL=DO-NEW" \
    || { FAIL_MSG="sessB write failed"; return 1; }
  as_a sutra_marker_reset_own \
    || { FAIL_MSG="sessA reset returned nonzero"; return 1; }
  [ ! -f "$DIRA/depth-registered" ] \
    || { FAIL_MSG="sessA reset did not clear its own session dir"; return 1; }
  [ ! -f "$GLOBAL/depth-registered" ] \
    || { FAIL_MSG="sessA reset did not clear its own self-stamped global"; return 1; }
  [ -f "$DIRB/flow-classified" ] \
    || { FAIL_MSG="sessA reset DELETED sessB's session-dir marker"; return 1; }
  [ -f "$GLOBAL/flow-classified" ] && grep -q "SESSION=$SIDB" "$GLOBAL/flow-classified" \
    || { FAIL_MSG="sessA reset deleted or altered sessB's stamped global"; return 1; }
  return 0
}
s3; report s3 $? "sessA reset wipes only own state; sessB untouched"

# ---------------------------------------------------------------------------
s4() { # unstamped legacy global -> either session may adopt (transitional allowance)
  printf 'LEGACY=1\n' > "$GLOBAL/legacy-unstamped" \
    || { FAIL_MSG="could not plant legacy global"; return 1; }
  as_a sutra_marker_read legacy-unstamped >/dev/null \
    || { FAIL_MSG="sessA could not adopt an unstamped legacy global"; return 1; }
  [ -f "$DIRA/legacy-unstamped" ] \
    || { FAIL_MSG="adoption did not copy into sessA's session dir"; return 1; }
  as_b sutra_marker_read legacy-unstamped >/dev/null \
    || { FAIL_MSG="sessB could not adopt the same unstamped legacy global"; return 1; }
  [ -f "$DIRB/legacy-unstamped" ] \
    || { FAIL_MSG="adoption did not copy into sessB's session dir"; return 1; }
  # TRANSITIONAL: an unstamped global has no provable owner; both sessions
  # adopting it is the documented legacy tolerance (un-migrated govblock
  # installs would otherwise brick). Retired when dual-write/adopt flip off
  # at migration Phase 6.
  return 0
}
s4; report s4 $? "unstamped legacy global adoptable by either session (transitional allowance)"

# ---------------------------------------------------------------------------
s5() { # self-stamped global -> self adoption works (crash-recovery path)
  printf 'RECOVER=1\nSESSION=%s\nTS=%s\n' "$SIDA" "$(date +%s)" > "$GLOBAL/own-recovery" \
    || { FAIL_MSG="could not plant self-stamped global"; return 1; }
  # Simulated crash: session dir has no copy; only the dual-written twin remains.
  as_a sutra_marker_read own-recovery >/dev/null \
    || { FAIL_MSG="sessA could not re-adopt its OWN self-stamped global (crash recovery broken)"; return 1; }
  [ -f "$DIRA/own-recovery" ] \
    || { FAIL_MSG="recovery adoption did not land in sessA's session dir"; return 1; }
  if as_b sutra_marker_read own-recovery >/dev/null 2>&1; then
    FAIL_MSG="sessB adopted sessA's self-stamped global"; return 1
  fi
  return 0
}
s5; report s5 $? "self-stamped global re-adopted by owner only (crash recovery)"

# ---------------------------------------------------------------------------
s6() { # stale-TS guard -- apply whatever staleness rule marker-lib has
  # Lib read 2026-07-30: marker-lib.sh has NO TS-field staleness rule in
  # sutra_marker_has / sutra_marker_read / sutra_marker_reset_own (verified by
  # inspection; the only age logic is sutra_marker_gc, which is mtime-on-
  # session-DIRS, -mmin +1440, and never consults the TS= field). Per brief:
  # assert nothing; observe and note.
  local stale_ts observed
  stale_ts=$(( $(date +%s) - 90000 ))   # 25h old
  printf 'DEPTH=2\nSESSION=%s\nTS=%s\n' "$SIDA" "$stale_ts" > "$GLOBAL/stale-marker" \
    || { FAIL_MSG="could not plant stale marker"; return 1; }
  if as_a sutra_marker_read stale-marker >/dev/null 2>&1; then
    observed="25h-old self-stamped marker still READABLE (no TS staleness rule in lib)"
  else
    observed="25h-old self-stamped marker REJECTED (a TS staleness rule now exists -- update this scenario to assert it)"
  fi
  echo "  s6 NOTE: $observed"
  return 0
}
s6; report s6 $? "stale-TS: lib has no TS staleness rule; behavior observed, nothing asserted"

# ---------------------------------------------------------------------------
# Strict-mode env wrapper: same subshell scoping as as_a/as_b, plus
# SUTRA_MARKER_ADOPT=0. First arg = sid to impersonate.
as_strict() { local sid="$1"; shift; ( export CLAUDE_CODE_SESSION_ID="$sid" SUTRA_MARKER_ADOPT=0; "$@" ); }

s7() { # strict mode (SUTRA_MARKER_ADOPT=0) -> global path never consulted
  local SIDS="sessS" SIDF="sessF" SIDP="sessP"
  local DIRS_="$T/.claude/sessions/$SIDS"
  local rc out err observed

  # (i) self-stamped global under strict. Lib inspection (marker-lib.sh:102):
  # sutra_marker_has short-circuits on the ADOPT flag BEFORE the owner check,
  # so the s5 crash-recovery path is expected LOST. Per brief: assert the
  # ACTUAL behavior for internal consistency (rc must match the filesystem
  # effect) and PRINT it -- do not hard-code the expectation.
  printf 'RECOVER=1\nSESSION=%s\nTS=%s\n' "$SIDS" "$(date +%s)" > "$GLOBAL/strict-own" \
    || { FAIL_MSG="could not plant self-stamped global"; return 1; }
  if as_strict "$SIDS" sutra_marker_read strict-own >/dev/null 2>&1; then rc=0; else rc=1; fi
  if [ "$rc" -eq 0 ]; then
    observed="ADOPT=0 still ADOPTED own self-stamped global (strict short-circuit NOT active -- flag not honored)"
    [ -f "$DIRS_/strict-own" ] \
      || { FAIL_MSG="read hit but no session-dir copy (rc/filesystem inconsistent)"; return 1; }
  else
    observed="ADOPT=0 MISSED own self-stamped global (s5 crash-recovery path LOST in strict; session dir sole authority)"
    [ ! -f "$DIRS_/strict-own" ] \
      || { FAIL_MSG="read missed but global was still copied into session dir (rc/filesystem inconsistent)"; return 1; }
  fi
  echo "  s7 NOTE(i): $observed"

  # (ii) foreign-stamped global under strict: ignored, same outcome as s1.
  # No contamination row asserted -- the strict short-circuit (marker-lib.sh:102)
  # returns before the logging branch.
  printf 'X=1\nSESSION=%s\nTS=%s\n' "$SIDA" "$(date +%s)" > "$GLOBAL/strict-foreign" \
    || { FAIL_MSG="could not plant foreign-stamped global"; return 1; }
  if as_strict "$SIDS" sutra_marker_read strict-foreign >/dev/null 2>&1; then
    FAIL_MSG="strict session READ a foreign-stamped global (ADOPT=0 consulted the global path)"; return 1
  fi
  [ ! -f "$DIRS_/strict-foreign" ] \
    || { FAIL_MSG="foreign global copied into strict session's dir"; return 1; }

  # (iii) fresh session, zero markers anywhere -> clean MISS, not a crash.
  out=$(as_strict "$SIDF" sutra_marker_read never-written-marker 2>/dev/null); rc=$?
  [ "$rc" -ne 0 ] \
    || { FAIL_MSG="fresh strict session HIT a marker that was never written"; return 1; }
  [ -z "$out" ] \
    || { FAIL_MSG="miss produced stdout output: $out"; return 1; }
  err=$(as_strict "$SIDF" sutra_marker_has never-written-marker 2>&1 >/dev/null) || true
  [ -z "$err" ] \
    || { FAIL_MSG="strict miss emitted stderr noise (crash, not clean miss): $err"; return 1; }

  # (iv) placement round-trip under strict -- THE strict-mode blocker check
  # (root-cause doc section 2, placement-registered row): placement-resolve.sh
  # writes session-stamped since v2.58.0, so its own sid-aware gate must PASS
  # with ADOPT=0 and the global twin deleted (session dir alone satisfies it).
  local PLACE_RESOLVE="$PLUGIN_ROOT/hooks/placement-resolve.sh"
  local PLACE_GATE="$PLUGIN_ROOT/hooks/placement-gate.sh"
  [ -f "$PLACE_RESOLVE" ] && [ -f "$PLACE_GATE" ] \
    || { FAIL_MSG="placement hooks missing from plugin root"; return 1; }
  command -v python3 >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 \
    || { FAIL_MSG="python3+jq required for placement round-trip (infrastructure, not lib, missing)"; return 1; }
  printf '{"prompt":"s7 strict placement round-trip probe"}' | (
    export CLAUDE_PROJECT_DIR="$T" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
           CLAUDE_CODE_SESSION_ID="$SIDP" SUTRA_MARKER_ADOPT=0 HOME="$T"
    unset PLACEMENT_DISABLED 2>/dev/null || true
    bash "$PLACE_RESOLVE" >/dev/null 2>&1
  )
  [ -f "$T/.claude/sessions/$SIDP/placement-registered" ] \
    || { FAIL_MSG="placement-resolve did not write a session-scoped marker (sid-blind writer regression)"; return 1; }
  grep -q "SESSION=$SIDP" "$T/.claude/sessions/$SIDP/placement-registered" \
    || { FAIL_MSG="placement marker missing SESSION=$SIDP stamp"; return 1; }
  rm -f "$GLOBAL/placement-registered"      # strict: session dir alone must satisfy
  printf 'hard\n' > "$T/.claude/placement-mode"
  printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"},"session_id":"%s"}' \
      "$T/workfile.txt" "$SIDP" | (
    export CLAUDE_PROJECT_DIR="$T" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
           CLAUDE_CODE_SESSION_ID="$SIDP" SUTRA_MARKER_ADOPT=0 HOME="$T"
    unset PLACEMENT_DISABLED PLACEMENT_ACK 2>/dev/null || true
    bash "$PLACE_GATE" >/dev/null 2>&1
  )
  rc=$?
  rm -f "$T/.claude/placement-mode"
  [ "$rc" -eq 0 ] \
    || { FAIL_MSG="placement-gate (hard) exit $rc with ADOPT=0 despite session-stamped engine marker -- strict-mode flip would hard-block every turn"; return 1; }
  echo "  s7 NOTE(iv): placement round-trip PASSED under ADOPT=0 (gate satisfied by session dir alone, global twin deleted)"
  return 0
}
s7; report s7 $? "strict ADOPT=0: global never consulted; fresh-session clean miss; placement round-trip green"

# ---------------------------------------------------------------------------
echo "marker-concurrency: $PASS_N/7 PASS"
[ "$PASS_N" -eq 7 ] || exit 1
exit 0
