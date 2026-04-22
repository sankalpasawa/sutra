#!/usr/bin/env bash
# Regression test for D13 — Cascade Downstream Immediately.
# 2026-04-16: HARD lift via I-14 ladder. Hook exits 2 on L0/L2 edit without
# matching downstream TODO evidence; exits 0 with evidence or CASCADE_ACK
# override; exits 0 silently on product files.
# Uses a per-case temp git repo so git diff state is deterministic.

set -u
ORIG_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
HOOK="$ORIG_ROOT/holding/hooks/cascade-check.sh"

FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1  (exit=$2)"; FAIL=1; }

# Build a temp git repo, commit initial target, append edit, optionally seed
# a TODO line into one of the repo's TODO.md files, then invoke the hook.
# Flags on $todo_mode:
#   ""        → write holding/TODO.md and stage it (default)
#   "unstaged"→ commit an empty holding/TODO.md first, then unstaged-append
#   "nonTodo" → write the line to a non-TODO file (should NOT satisfy gate)
# Returns the hook's exit code.
run_case() {
  local target_rel="$1"; local todo_line="$2"; local env_prefix="$3"
  local todo_mode="${4:-}"
  local tmp; tmp=$(mktemp -d)
  (
    cd "$tmp" || exit 99
    git init -q 2>/dev/null
    git config user.email t@t 2>/dev/null
    git config user.name t 2>/dev/null
    mkdir -p "$(dirname "$target_rel")"
    echo "init" > "$target_rel"
    # Pre-commit an empty holding/TODO.md so unstaged edits to it show in diff
    mkdir -p holding
    echo "" > holding/TODO.md
    git add -A 2>/dev/null && git commit -qm init 2>/dev/null
    echo "edit" >> "$target_rel"
    if [ -n "$todo_line" ]; then
      case "$todo_mode" in
        unstaged)
          # modify the tracked TODO.md in working tree only (unstaged)
          printf '%s\n' "$todo_line" >> holding/TODO.md
          ;;
        nonTodo)
          # write to a non-TODO file to verify it does NOT satisfy the gate
          echo "# note" > holding/NOTES.md
          printf '%s\n' "$todo_line" >> holding/NOTES.md
          git add holding/NOTES.md 2>/dev/null
          ;;
        *)
          printf '%s\n' "$todo_line" >> holding/TODO.md
          git add holding/TODO.md 2>/dev/null
          ;;
      esac
    fi
    eval "$env_prefix TOOL_INPUT_file_path=\"$tmp/$target_rel\" bash \"$HOOK\"" </dev/null >/dev/null 2>&1
  )
  local rc=$?
  rm -rf "$tmp"
  return "$rc"
}

echo "=== Case 1 (HARD): L0 (holding/) edit, no TODO in diff → exit 2 ==="
run_case "holding/PRINCIPLES.md" "" ""
rc=$?; [ "$rc" = "2" ] && pass "L0 without evidence exits 2" || fail "L0 without evidence" "$rc"

echo ""
echo "=== Case 2 (HARD): L0 edit WITH matching TODO in diff → exit 0 ==="
run_case "holding/PRINCIPLES.md" "TODO: cascade PRINCIPLES downstream to dayflow" ""
rc=$?; [ "$rc" = "0" ] && pass "L0 with matching TODO exits 0" || fail "L0 with matching TODO" "$rc"

echo ""
echo "=== Case 3 (HARD): L0 edit WITH mismatched TODO → exit 2 ==="
run_case "holding/PRINCIPLES.md" "- [ ] TODO: unrelated thing for someone else" ""
rc=$?; [ "$rc" = "2" ] && pass "L0 with mismatched TODO exits 2" || fail "L0 with mismatched TODO" "$rc"

echo ""
echo "=== Case 4 (HARD): L0 edit with CASCADE_ACK=1 override → exit 0 ==="
run_case "holding/PRINCIPLES.md" "" "CASCADE_ACK=1 CASCADE_ACK_REASON='test-override'"
rc=$?; [ "$rc" = "0" ] && pass "CASCADE_ACK=1 override exits 0" || fail "CASCADE_ACK override" "$rc"

echo ""
echo "=== Case 5 (HARD): Sutra L2 edit, no TODO → exit 2 ==="
run_case "sutra/layer2-operating-system/PROTO-001.md" "" ""
rc=$?; [ "$rc" = "2" ] && pass "L2 sutra without evidence exits 2" || fail "L2 without evidence" "$rc"

echo ""
echo "=== Case 6: product file → silent exit 0 ==="
run_case "dayflow/mobile/src/app.tsx" "" ""
rc=$?; [ "$rc" = "0" ] && pass "product file exits 0 silently" || fail "product file" "$rc"

echo ""
echo "=== Case 7 (HARD): L0 edit WITH matching TODO in UNSTAGED TODO.md → exit 0 ==="
run_case "holding/PRINCIPLES.md" "TODO: unstaged cascade ref to PRINCIPLES" "" "unstaged"
rc=$?; [ "$rc" = "0" ] && pass "L0 with unstaged TODO evidence exits 0" || fail "unstaged evidence" "$rc"

echo ""
echo "=== Case 8 (HARD): TODO line in NON-TODO-file does NOT satisfy gate → exit 2 ==="
run_case "holding/PRINCIPLES.md" "TODO: PRINCIPLES bypass attempt" "" "nonTodo"
rc=$?; [ "$rc" = "2" ] && pass "non-TODO file line does not satisfy gate" || fail "non-TODO bypass succeeded" "$rc"

echo ""
echo "=== Case 9 (HARD): metachar stem 'a+b' — escaped regex, no match on unrelated 'ab' ==="
# Target: holding/a+b.md  (STEM='a+b'). TODO line that would have falsely
# matched the unescaped regex 'a+b' (one-or-more 'a' followed by 'b') was
# 'TODO ab cascade'. Under escaped regex 'a\+b', it should NOT match.
run_case "holding/a+b.md" "TODO ab cascade unrelated" ""
rc=$?; [ "$rc" = "2" ] && pass "metachar stem escaped correctly (no false positive)" || fail "metachar stem false-positive" "$rc"

echo ""
echo "=== Case 10 (HARD): metachar stem 'a+b' — exact match 'a+b' does satisfy ==="
run_case "holding/a+b.md" "TODO a+b cascade ok" ""
rc=$?; [ "$rc" = "0" ] && pass "metachar stem matches when line has exact stem" || fail "metachar exact match failed" "$rc"

echo ""
if [ "$FAIL" = "0" ]; then
  echo "ALL D13 REGRESSION TESTS PASSED"
  exit 0
else
  echo "D13 REGRESSION TESTS FAILED"
  exit 1
fi
