#!/bin/bash
# Test: blueprint-check.sh out-of-repo guard + per-turn prompt marker visibility.
# Field incident 2026-07-08 (Testlify client): model emitted a correct prose
# BLUEPRINT but nothing in fleet context said to write .claude/blueprint-registered,
# so the hook blocked every Write and the model escaped via Bash+BLUEPRINT_ACK
# (full gate bypass). Two fixes under test:
#
#   [1] absolute path OUTSIDE $CLAUDE_PROJECT_DIR -> exit 0 (out of scope)
#   [2] ~/.claude/** style path outside repo -> exit 0 (was HARD-blocked)
#   [3] inside-repo non-foundational + no marker -> still HARD exit 2 (unchanged)
#   [4] inside-repo foundational + no marker -> still HARD exit 2 (unchanged)
#   [5] per-turn-discipline-prompt.sh output names .claude/blueprint-registered
#   [6] per-turn-discipline-prompt.sh output names HAS_OUTPUT/HAS_VERIFY flags

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$PLUGIN_ROOT/hooks/blueprint-check.sh"
PROMPT_HOOK="$PLUGIN_ROOT/hooks/per-turn-discipline-prompt.sh"

PASS=0
FAIL=0
FAILURES=()

_result() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS+1))
    echo "  PASS: $name"
  else
    FAIL=$((FAIL+1))
    FAILURES+=("$name :: expected=$expected actual=$actual")
    echo "  FAIL: $name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
  fi
}

_TMP=$(mktemp -d)
_OUTSIDE=$(mktemp -d)
trap "rm -rf $_TMP $_OUTSIDE" EXIT
mkdir -p "$_TMP/.claude" "$_TMP/holding"
# Pin depth to 2 so the V2.2 D3+ per-step gate (fail-closed to D5) stays out
# of scope — it has its own coverage.
printf 'DEPTH=2 TASK=test TS=1730000000\n' > "$_TMP/.claude/depth-registered"

_run_capture_exit() {
  local file_path="$1"
  printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$file_path" \
    | CLAUDE_PROJECT_DIR="$_TMP" "$HOOK" >/dev/null 2>&1
  echo $?
}

echo "== blueprint-check.sh marker-visibility tests =="

# --- [1] absolute path outside repo -> exit 0
echo "[1] outside-repo absolute path -> out of scope (exit 0)"
rm -f "$_TMP/.claude/blueprint-registered"
exit_code=$(_run_capture_exit "$_OUTSIDE/some-doc.md")
_result "outside repo exempt" "0" "$exit_code"

# --- [2] ~/.claude-style path outside repo -> exit 0
echo "[2] outside-repo .claude memory path -> out of scope (exit 0)"
exit_code=$(_run_capture_exit "$_OUTSIDE/.claude/projects/x/memory/note.md")
_result "outside .claude exempt" "0" "$exit_code"

# --- [3] inside repo, non-foundational, no marker -> still blocked
echo "[3] inside-repo non-foundational + no marker -> HARD (exit 2)"
exit_code=$(_run_capture_exit "$_TMP/some/random/file.txt")
_result "inside repo still hard" "2" "$exit_code"

# --- [4] inside repo, foundational, no marker -> still blocked
echo "[4] inside-repo foundational + no marker -> HARD (exit 2)"
exit_code=$(_run_capture_exit "$_TMP/holding/FOUNDER-DIRECTIONS.md")
_result "foundational still hard" "2" "$exit_code"

# --- [5]+[6] per-turn prompt teaches the marker contract
# Fresh-install gate: hook is silent without .claude/sutra-project.json.
# CLAUDE_PLUGIN_ROOT points it at the real sutra-defaults.json.
echo "[5] per-turn prompt names the marker file"
printf '{"install_id":"test","project_id":"test"}\n' > "$_TMP/.claude/sutra-project.json"
PROMPT_OUT=$(printf '{"prompt":"do a thing"}' \
  | CLAUDE_PROJECT_DIR="$_TMP" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$PROMPT_HOOK" 2>&1)
case "$PROMPT_OUT" in
  *".claude/blueprint-registered"*) _result "prompt names marker" "yes" "yes" ;;
  *) _result "prompt names marker" "yes" "no" ;;
esac

echo "[6] per-turn prompt names the marker flags"
case "$PROMPT_OUT" in
  *"HAS_OUTPUT=1"*"HAS_VERIFY=1"*) _result "prompt names flags" "yes" "yes" ;;
  *) _result "prompt names flags" "yes" "no" ;;
esac

# --- Report
echo ""
echo "== Results: $PASS passed, $FAIL failed =="
if [ $FAIL -gt 0 ]; then
  echo "Failures:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
exit 0
