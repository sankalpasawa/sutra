#!/usr/bin/env bash
# test-atom-floor-scanner.sh — target extraction of the Bash mutation scanner
# in atom-floor.sh, after the 2026-09-10 per-segment rewrite (GATE-2 #2 +
# GATE-1; codex CHANGES-REQUIRED folded).
#
# Drives atom_floor_check directly against a fabricated root with NO open
# atom, and asserts ATOM_FLOOR_BASH_TARGETS + ATOM_FLOOR_MUTATION. Verb
# detection is independent of target extraction, so a dropped command word
# can never hide a mutator — the cases below pin both halves.
set -uo pipefail

PASS=0; FAIL=0
FLOOR="$(cd "$(dirname "$0")/.." && pwd)/atom-floor.sh"
[ -f "$FLOOR" ] || { echo "no floor at $FLOOR"; exit 2; }
T=$(mktemp -d "${TMPDIR:-/tmp}/af-scanner-test.XXXXXX")
trap 'rm -rf "$T"' EXIT

scan() { # $1=command -> prints "MUT=<0|1> T=<targets joined by ,>"
  ( export CLAUDE_PROJECT_DIR="$T" CLAUDE_CODE_SESSION_ID="s-scan" HOME="$T"
    # shellcheck disable=SC1090
    . "$FLOOR" 2>/dev/null
    ATOM_FLOOR_MUTATION=0; ATOM_FLOOR_BASH_TARGETS=""
    atom_floor_check Bash "" "$1" >/dev/null 2>&1
    printf 'MUT=%s T=%s\n' "${ATOM_FLOOR_MUTATION:-0}" "$(printf '%s' "${ATOM_FLOOR_BASH_TARGETS:-}" | tr '\n' ',')" )
}
check() { # $1=label $2=expected $3=command
  local got; got=$(scan "$3")
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); printf '  ok   %s\n' "$1"
  else FAIL=$((FAIL+1)); printf '  FAIL %s\n       cmd:  %s\n       want: %s\n       got:  %s\n' "$1" "$3" "$2" "$got"; fi
}

echo "atom-floor scanner targets"

# --- the two recorded false positives -------------------------------------
check "FP-A: command-word path is not a target"        'MUT=1 T=out/x.txt'         'path/to/scrub.sh "$IN" > out/x.txt'
check "FP-A: interpreter script operand skipped"       'MUT=1 T=holding/out.txt'   'bash holding/scripts/run.sh > holding/out.txt'
check "FP-B: codex -m value is not a target"           'MUT=1 T=holding/state/x.md,holding/state/log.txt' 'codex exec -m gpt-5.5 -o holding/state/x.md hi > holding/state/log.txt'
check "FP-B: codex --model=X is not a target"          'MUT=1 T=holding/state/log.txt' 'codex exec --model=gpt-5.5 hi > holding/state/log.txt'
check "python3 -m module name is not a target"         'MUT=1 T=holding/o.txt'     'python3 -m gpt-5.5 > holding/o.txt'

# --- operands are kept (codex P1) ------------------------------------------
check "tee keeps its operand"                          'MUT=1 T=holding/x.log'     'echo hi | tee holding/x.log'
check "cp keeps both operands"                         'MUT=1 T=a.txt,holding/b.txt' 'cp a.txt holding/b.txt'
check "mv keeps both operands"                         'MUT=1 T=holding/a,holding/b' 'mv holding/a holding/b'
check "sed -i keeps the file operand"                  'MUT=1 T=holding/f.md'      "sed -i 's/x/y/' holding/f.md"
check "git add keeps the file operand"                 'MUT=1 T=holding/f.md'      'git add holding/f.md'
check "sudo env X=1 command cp resolves past wrappers" 'MUT=1 T=a.txt,holding/b.txt' 'sudo env X=1 command cp a.txt holding/b.txt'
check "rm keeps its operand"                           'MUT=1 T=holding/x'         'rm holding/x'
check "bare redirect target kept (: > file)"           'MUT=1 T=holding/x'         ': > holding/x'
check "leading redirect is not a command word"         'MUT=1 T=holding/x'         '>holding/x'
check "-m outside codex is NOT exempt"                 'MUT=1 T=gpt-5.5,holding/o.txt' 'tool -m gpt-5.5 > holding/o.txt'

# --- opaque forms stay opaque (codex P1) -----------------------------------
check "sh -c hides the write -> wrapper, no target"    'MUT=1 T='                  "sh -c 'echo hi > holding/file'"
check "python3 -c is a wrapper, no target"             'MUT=1 T='                  "python3 -c 'open(\"holding/f\",\"w\")'"
check "python3 script.py -> opaque (no target)"        'MUT=1 T='                  'python3 holding/tool.py'

# --- exemption + read-only unchanged -----------------------------------------
check "exempt CLI + mutator: only the mutator's target" 'MUT=1 T=holding/x'        'sutra-atom close a-1; rm holding/x'
check "read-only ls: no mutation, no target"           'MUT=0 T='                  'ls holding/'

echo "  passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
