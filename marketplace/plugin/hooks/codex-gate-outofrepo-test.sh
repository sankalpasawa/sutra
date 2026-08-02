#!/usr/bin/env bash
# codex-gate-outofrepo-test.sh -- regression for the 2026-07-31 memory-scope
# carve-out in codex-consult-gate.sh (mirrors the blueprint v2.39.20 incident
# test shape). Cases:
#   1. ~/.claude/** path        -> exit 0 (carve-out)
#   2. in-repo non-whitelisted  -> exit 2 (codex present) / SKIP (absent)
#   3. other out-of-repo (/tmp) -> exit 2 (codex present; pins no-blanket-bypass)
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/codex-consult-gate.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/.claude"
echo '{}' > "$TMP/.claude/sutra-project.json"
printf 'DEPTH=5\n' > "$TMP/.claude/depth-registered"
run_case() {
  printf '{"tool_input":{"file_path":"%s"}}' "$1" \
    | CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" >/dev/null 2>&1
}
fail=0
run_case "$HOME/.claude/projects/x/memory/note.md"; rc=$?
[ "$rc" -eq 0 ] && echo "PASS memory-scope" || { echo "FAIL memory-scope rc=$rc"; fail=1; }
if command -v codex >/dev/null 2>&1; then
  run_case "$TMP/src/app.py"; rc=$?
  [ "$rc" -eq 2 ] && echo "PASS in-repo-blocks" || { echo "FAIL in-repo-blocks rc=$rc"; fail=1; }
  run_case "/tmp/outside-$$.py"; rc=$?
  [ "$rc" -eq 2 ] && echo "PASS no-blanket-bypass" || { echo "FAIL no-blanket-bypass rc=$rc"; fail=1; }
else
  echo "SKIP in-repo-blocks + no-blanket-bypass (codex absent)"
fi
[ "$fail" -eq 0 ] && echo "codex-gate-outofrepo: ALL PASS"
exit $fail
