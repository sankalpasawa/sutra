#!/bin/bash
# tests/lib.sh — shared assertions for human-sutra tests (TAP-style)
# Source from each test-*.sh

PASS=0
FAIL=0
TESTS=0

assert_field() {
  local input="$1" field="$2" expected="$3"
  local actual
  actual=$(printf '%s' "$input" | bash "$(dirname "${BASH_SOURCE[0]}")/../scripts/classify.sh" 2>/dev/null | jq -r ".$field" 2>/dev/null)
  TESTS=$((TESTS+1))
  if [ "$actual" = "$expected" ]; then
    PASS=$((PASS+1))
    printf 'ok %d - %s=%s\n' "$TESTS" "$field" "$expected"
  else
    FAIL=$((FAIL+1))
    printf 'not ok %d - %s expected %s got %s (input: %.50s)\n' "$TESTS" "$field" "$expected" "$actual" "$input"
  fi
}

assert_equals() {
  local actual="$1" expected="$2" desc="$3"
  TESTS=$((TESTS+1))
  if [ "$actual" = "$expected" ]; then
    PASS=$((PASS+1))
    printf 'ok %d - %s\n' "$TESTS" "$desc"
  else
    FAIL=$((FAIL+1))
    printf 'not ok %d - %s: got %s expected %s\n' "$TESTS" "$desc" "$actual" "$expected"
  fi
}

assert_grep() {
  # Accepts either a regular file path OR a process substitution (FIFO).
  # The prior `[ -f "$file" ]` precondition rejected FIFOs and false-failed
  # tests like `assert_grep <(printf …) …`. grep itself handles both kinds
  # of inputs natively, so we let it decide. (Mid-phase fold R4 2026-05-01,
  # codex consult session 019de1c4-2b41-7931-80b7-b22e797668ff.)
  local file="$1" pattern="$2" desc="$3"
  TESTS=$((TESTS+1))
  if grep -qE "$pattern" "$file" 2>/dev/null; then
    PASS=$((PASS+1))
    printf 'ok %d - %s\n' "$TESTS" "$desc"
  else
    FAIL=$((FAIL+1))
    printf 'not ok %d - %s\n' "$TESTS" "$desc"
  fi
}

summary() {
  printf '1..%d\n' "$TESTS"
  printf '# tests: %d, pass: %d, fail: %d\n' "$TESTS" "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]
}
