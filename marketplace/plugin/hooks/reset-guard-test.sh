#!/usr/bin/env bash
# reset-guard-test.sh — regression test for the per-turn marker reset guards.
#
# WHY THIS EXISTS (2026-07-27): a refactor collapsed reset-turn-markers.sh from
# 90 lines to 17 and silently deleted four guards. With them gone the hook fires
# on every SYNTHETIC UserPromptSubmit — Claude Code injects system-reminders,
# linter notices, READ-BEFORE-EDIT prompts and task-list nudges as synthetic
# prompt events — wiping the per-turn markers between an assistant's own tool
# calls. The next Edit/Write then hard-blocks for "missing" markers that were in
# fact written. That hits SINGLE-session users, not just concurrent ones.
#
# It was caught by reading the file, not by any test. Nothing in the suite would
# have failed. This closes that gap: delete a guard, this test goes red.
#
# Usage:
#   bash reset-guard-test.sh                 # test the hooks next to this script
#   bash reset-guard-test.sh <plugin-root>   # test a specific installed build
#
# Exit 0 = all guards intact. Exit 1 = a guard is missing (regression).

set -u

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
HOOKS="$ROOT/hooks"
RESET="$HOOKS/reset-turn-markers.sh"
GATE="$HOOKS/flow-gate.sh"

FAILED=0
fail() { printf 'GUARD-FAIL: %s\n' "$1" >&2; FAILED=1; }
pass() { printf '  ok  %s\n' "$1"; }

[ -f "$RESET" ] || { echo "GUARD-FAIL: no reset-turn-markers.sh at $HOOKS" >&2; exit 1; }

T=$(mktemp -d) || exit 1
cleanup() { rm -rf "$T"; }
trap cleanup EXIT
mkdir -p "$T/.claude" "$T/.enforcement" "$T/holding"
echo '{"profile":"company"}' > "$T/.claude/sutra-project.json"

# Run a hook with a clean environment. Unsetting the session vars is REQUIRED:
# if the parent shell exports CLAUDE_CODE_SESSION_ID the hook resolves the
# caller's real session dir instead of the fixture's, and every assertion below
# silently tests the wrong directory. (Cost me three false failures.)
run() {
  printf '%s' "$2" | env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID \
    CLAUDE_PROJECT_DIR="$T" CLAUDE_PLUGIN_ROOT="$ROOT" bash "$1" >/dev/null 2>&1
}
# Assertions target the LEGACY GLOBAL marker deliberately. Both the pre- and
# post-migration builds understand that path, so this test is version-agnostic
# and can be pointed at any installed build to answer "are the guards present?".
# Asserting on the session dir instead would make the test pass vacuously on any
# build that predates session scoping.
seed() {
  mkdir -p "$T/.claude/sessions/sT" 2>/dev/null
  printf 'TYPE=direction\nSESSION=sT\n' > "$T/.claude/flow-classified"
  printf 'TYPE=direction\nSESSION=sT\n' > "$T/.claude/sessions/sT/flow-classified"
  rm -f "$T/.claude/.last-reset-ts"
}
# Re-seed WITHOUT clearing the burst timestamp — the burst guard reads
# .last-reset-ts to decide "same turn", so wiping it defeats the very guard
# under test. (This bug made guard 3 red on a build whose guard was fine.)
seed_keep_ts() {
  mkdir -p "$T/.claude/sessions/sT" 2>/dev/null
  printf 'TYPE=direction\nSESSION=sT\n' > "$T/.claude/flow-classified"
  printf 'TYPE=direction\nSESSION=sT\n' > "$T/.claude/sessions/sT/flow-classified"
}
present() { [ -f "$T/.claude/flow-classified" ]; }

echo "reset-guard-test — $ROOT"

# GUARD 1 — synthetic turns must not wipe markers.
for probe in \
  '{"prompt":"<system-reminder>task tools</system-reminder>","session_id":"sT"}' \
  '{"prompt":"file was modified, either by the user or by a linter","session_id":"sT"}' \
  '{"prompt":"READ-BEFORE-EDIT REMINDER","session_id":"sT"}'
do
  seed; run "$RESET" "$probe"
  present || fail "synthetic turn wiped markers: ${probe:0:52}"
done
present && pass "guard 1 — synthetic turns preserve markers"

# GUARD 2 — an empty prompt is not a real turn.
seed; run "$RESET" '{"session_id":"sT"}'
present && pass "guard 2 — empty prompt preserves markers" || fail "empty prompt wiped markers"

# GUARD 3 — burst guard: a second real prompt <3s apart is the same turn.
seed; sleep 3; run "$RESET" '{"prompt":"first real prompt","session_id":"sT"}'
seed_keep_ts; run "$RESET" '{"prompt":"second within 3s","session_id":"sT"}'
present && pass "guard 3 — burst guard holds" || fail "burst guard missing: same-turn reset wiped markers"

# CONTROL — a genuine prompt MUST still clear. Without this the guards could be
# satisfied by a hook that never resets at all, which is equally broken.
seed; sleep 3; run "$RESET" '{"prompt":"a genuine new founder prompt","session_id":"sT"}'
present && fail "control: real prompt did NOT clear markers (reset is dead)" \
        || pass "control — real prompt clears both scopes"

# GUARD 4 — fail-open: broken infrastructure must not hard-fail a user's turn.
# A governance gate may block on missing discipline; it must never block because
# its own library errored.
if [ -f "$GATE" ] && [ -f "$HOOKS/marker-lib.sh" ]; then
  cp "$HOOKS/marker-lib.sh" "$T/lib.bak"
  printf '\necho "$DELIBERATELY_UNSET_VAR"\n' >> "$HOOKS/marker-lib.sh"
  printf '{"tool_name":"Write","session_id":"sT","tool_input":{"file_path":"%s/holding/x.md"}}' "$T" \
    | env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$T" \
      CLAUDE_PLUGIN_ROOT="$ROOT" bash "$GATE" >/dev/null 2>&1
  RC=$?
  cp "$T/lib.bak" "$HOOKS/marker-lib.sh"
  case "$RC" in
    0|2) pass "guard 4 — broken marker-lib degrades (exit $RC), does not crash" ;;
    *)   fail "fail-open violated: broken marker-lib produced exit $RC" ;;
  esac
else
  echo "  --  guard 4 skipped (flow-gate.sh or marker-lib.sh absent)"
fi

if [ "$FAILED" -eq 0 ]; then
  echo "GUARD-PASS: synthetic + empty + burst + control + fail-open"
  exit 0
fi
echo "GUARD-FAIL: reset guards are missing or weakened — see above" >&2
exit 1
