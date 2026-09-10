#!/usr/bin/env bash
# test-dispatch-gate-runner.sh — hook-shaped contract test for the plugin's
# dispatch-gate.sh ENTRYPOINT (the runner that hooks.json executes directly).
#
# Feeds PreToolUse JSON on stdin exactly as Claude Code does and asserts the
# exit code. Covers the codex CHANGES-REQUIRED fold of 2026-09-10: warn vs
# hard mode, bootstrap escape for the governance CLIs, fail-closed on
# malformed input, delegation to a holding orchestrator, and the shared
# target derivation for Edit / Bash / Task.
set -uo pipefail

PASS=0; FAIL=0
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$HOOKS/dispatch-gate.sh"
FLOOR="$HOOKS/atom-floor.sh"
[ -f "$RUNNER" ] || { echo "no runner at $RUNNER"; exit 2; }

T=$(mktemp -d "${TMPDIR:-/tmp}/dg-runner-test.XXXXXX")
trap 'rm -rf "$T"' EXIT
SID="testsid-runner"
mkdir -p "$T/.claude" "$T/holding" "$T/other"

reset() { # wipe atom + dispatch state, keep mode
  rm -rf "$T/.sutra" "$T/holding/hooks"
}
mode() { printf '%s\n' "$1" > "$T/.claude/dispatch-mode"; }
bind() { # $1=MODEL $2=PLACEMENT $3=TOUCHES
  mkdir -p "$T/.sutra/dispatch/$SID" "$T/.sutra/atoms/$SID/a-test-01"
  printf 'UNIT=t\nCLASS=2\nPROVIDER=claude\nMODEL=%s\nPLACEMENT=%s\nTOUCHES=%s\nWORKROOT=%s\nATOM_ID=a-test-01\nSESSION=%s\n' \
    "$1" "$2" "$3" "$T" "$SID" > "$T/.sutra/dispatch/$SID/dispatch-record"
  echo '{"status":"open"}' > "$T/.sutra/atoms/$SID/a-test-01/atom.json"
}
run() { # $1=json (or "" for empty stdin) -> echoes exit code; stderr to $T/err
  ( export CLAUDE_PROJECT_DIR="$T" CLAUDE_CODE_SESSION_ID="$SID" \
           DISPATCH_GATE_JOURNAL_OVERRIDE="$T/journal.jsonl" HOME="$T"
    printf '%s' "$1" | bash "$RUNNER" >/dev/null 2>"$T/err"; echo $? )
}
j() { # $1=tool $2=key $3=value -> hook JSON
  jq -nc --arg t "$1" --arg k "$2" --arg v "$3" '{tool_name:$t, session_id:"testsid-runner", tool_input:{($k):$v}}'
}
check() { # $1=label $2=expected $3=actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); printf '  ok   %s (exit %s)\n' "$1" "$3"
  else FAIL=$((FAIL+1)); printf '  FAIL %s: expected exit %s got %s\n       stderr: %s\n' "$1" "$2" "$3" "$(head -1 "$T/err")"; fi
}

echo "dispatch-gate runner (hook-shaped stdin)"

# --- mode: default + warn never block --------------------------------------
reset; rm -f "$T/.claude/dispatch-mode"
check "no mode file = warn: Edit w/o atom passes"      0 "$(run "$(j Edit file_path "$T/holding/a.md")")"
grep -q 'ATOM FLOOR (WARN)' "$T/err" && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); echo "  FAIL warn advisory text missing"; }
mode warn
check "warn: Edit w/o atom passes"                     0 "$(run "$(j Edit file_path "$T/holding/a.md")")"
check "warn: empty stdin passes"                       0 "$(run "")"

# --- hard: floor + envelope ------------------------------------------------
mode hard
check "hard: Edit w/o atom blocks"                     2 "$(run "$(j Edit file_path "$T/holding/a.md")")"
check "hard: Edit whitelisted .claude path passes"     0 "$(run "$(j Edit file_path "$T/.claude/x")")"
bind claude-opus-5 INLINE "holding/"
check "hard: bound + Edit inside envelope passes"      0 "$(run "$(j Write file_path "$T/holding/a.md")")"
check "hard: bound + Edit outside envelope blocks"     2 "$(run "$(j Write file_path "$T/other/b.md")")"
grep -q 'outside frozen dispatch envelope' "$T/err" && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); echo "  FAIL envelope reason missing"; }

# --- hard: Bash ---------------------------------------------------------------
reset
check "hard: governance CLI w/o atom passes (bootstrap)" 0 "$(run "$(j Bash command "sutra-atom open --goal 'x; y' --verify-template file-exists --verify-arg z")")"
check "hard: CLI + mutator in one line blocks"         2 "$(run "$(j Bash command "sutra-dispatch show; rm holding/x")")"
check "hard: rm w/o atom blocks"                       2 "$(run "$(j Bash command "rm holding/x")")"
check "hard: read-only ls w/o atom passes"             0 "$(run "$(j Bash command "ls holding/")")"
bind claude-opus-5 INLINE "holding/"
check "hard: bound + rm inside envelope passes"        0 "$(run "$(j Bash command "rm holding/x")")"
check "hard: bound + rm outside envelope blocks"       2 "$(run "$(j Bash command "rm other/x")")"

# --- hard: Task model binding ----------------------------------------------
bind claude-sonnet-5 SPAWN "holding/"
check "hard: SPAWN + unpinned Task blocks"             2 "$(run "$(j Task description "x")")"
check "hard: SPAWN + alias-pinned Task passes"         0 "$(run "$(j Task model sonnet)")"
check "hard: SPAWN + wrong model blocks"               2 "$(run "$(j Task model haiku)")"

# --- hard: fail-closed on malformed input ------------------------------------
check "hard: empty stdin blocks"                       2 "$(run "")"
check "hard: JSON without tool_name blocks"            2 "$(run '{"tool_input":{}}')"
check "hard: unrelated tool passes"                    0 "$(run "$(j Read file_path "$T/other/b.md")")"

# --- delegation ----------------------------------------------------------------
reset; mkdir -p "$T/holding/hooks"; : > "$T/holding/hooks/dispatcher-pretool.sh"
check "holding orchestrator present: runner delegates" 0 "$(run "$(j Edit file_path "$T/holding/a.md")")"
reset
( export CLAUDE_PROJECT_DIR="$T" CLAUDE_CODE_SESSION_ID="$SID" HOME="$T"
  printf '%s' "$(j Edit file_path "$T/holding/a.md")" | bash "$FLOOR" >/dev/null 2>&1; echo $? ) > "$T/floor-exit"
check "atom-floor runner delegates to sibling gate"    0 "$(cat "$T/floor-exit")"

echo "  passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
