#!/bin/bash
# Shared assertion helpers for Sutra outcome tests.
# Source this from each test script: source "$(dirname "$0")/lib/assert.sh"

FAILURES=0
PASSES=0
TEST_NAME="${TEST_NAME:-unnamed}"

_pass() {
  PASSES=$((PASSES + 1))
  echo "  ✓ $1"
}

_fail() {
  FAILURES=$((FAILURES + 1))
  echo "  ✗ $1" >&2
}

# assert_eq <actual> <expected> <message>
assert_eq() {
  if [ "$1" = "$2" ]; then _pass "$3"
  else _fail "$3 (got '$1' wanted '$2')"
  fi
}

# assert_file <path> <message>
assert_file() {
  if [ -f "$1" ]; then _pass "$2"
  else _fail "$2 (missing file: $1)"
  fi
}

# assert_dir <path> <message>
assert_dir() {
  if [ -d "$1" ]; then _pass "$2"
  else _fail "$2 (missing dir: $1)"
  fi
}

# assert_exit <command> <expected-exit-code> <message>
assert_exit() {
  eval "$1" >/dev/null 2>&1
  local actual=$?
  if [ "$actual" -eq "$2" ]; then _pass "$3"
  else _fail "$3 (exit=$actual wanted=$2)"
  fi
}

# assert_count <command> <min> <max> <message>
# Evaluates <command> and asserts its integer output is in [min, max].
assert_count() {
  local n
  n=$(eval "$1")
  if [ -z "$n" ]; then
    _fail "$4 (no output from: $1)"
    return
  fi
  if [ "$n" -ge "$2" ] && [ "$n" -le "$3" ]; then _pass "$4"
  else _fail "$4 (count=$n range=[$2,$3])"
  fi
}

# assert_semver <version-string> <message>
# Loose semver check: N.N.N where N is digits.
assert_semver() {
  if printf '%s' "$1" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then _pass "$2"
  else _fail "$2 (not semver: '$1')"
  fi
}

# assert_nostring <pattern> <file-or-dir> <message>
# Fails if <pattern> is found in <file-or-dir> (case-insensitive).
assert_nostring() {
  local pattern="$1"
  local target="$2"
  local msg="$3"
  if [ -d "$target" ]; then
    if grep -rniE "\\b$pattern\\b" "$target" >/dev/null 2>&1; then
      _fail "$msg (pattern '$pattern' found in $target)"
    else
      _pass "$msg"
    fi
  elif [ -f "$target" ]; then
    if grep -iE "\\b$pattern\\b" "$target" >/dev/null 2>&1; then
      _fail "$msg (pattern '$pattern' found in $target)"
    else
      _pass "$msg"
    fi
  else
    _fail "$msg (target missing: $target)"
  fi
}

# exit_with_summary — print summary, return 0 iff all passed.
exit_with_summary() {
  echo ""
  echo "  — $TEST_NAME: $PASSES passed, $FAILURES failed"
  if [ "$FAILURES" -eq 0 ]; then return 0
  else return 1
  fi
}
