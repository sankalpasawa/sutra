#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Pre-commit Test Gate — D1 "verify before commit" enforcement (Sutra-local)
# ═══════════════════════════════════════════════════════════════════════════════
# Ported from holding/hooks/pre-commit-test-gate.sh (commit 31dcaa3 in
# asawa-holding). Same behavior, sutra-local paths.
#
# Called from sutra/hooks/git-wrappers/pre-commit.
#
# Fresh marker requirements:
#   File: .claude/ran-tests (repo-local)
#   Format: key=value lines — ts=<unix>, exit=<code>, cmd=<command>
#   Pass requires: mtime within MARKER_TTL (default 600s) AND exit=0
#
# Enforcement:
#   Docs-only staged set        → exit 0 (skip)
#   Fresh marker + exit=0       → exit 0 (pass)
#   Missing/stale marker / exit≠0 → exit 1 (git pre-commit BLOCK)
#   Override: SKIP_TESTS_ACK=<reason> → exit 0, logged
#
# Kill-switch: TEST_GATE_DISABLED=1 (env) or touch ~/.test-gate-disabled (global).
# Telemetry: .enforcement/test-gate.jsonl (one row per commit attempt).
# ═══════════════════════════════════════════════════════════════════════════════

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
MARKER_FILE="$REPO_ROOT/.claude/ran-tests"
MARKER_TTL="${TEST_GATE_TTL:-600}"
LOG_FILE="$REPO_ROOT/.enforcement/test-gate.jsonl"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null

TS=$(date +%s)

log_row() {
  local status="$1" reason="$2" staged_code="$3" staged_docs="$4"
  printf '{"ts":%s,"event":"pre-commit-test-gate","status":"%s","reason":"%s","staged_code":%s,"staged_docs":%s}\n' \
    "$TS" "$status" "$reason" "$staged_code" "$staged_docs" >> "$LOG_FILE"
}

if [ "${TEST_GATE_DISABLED:-0}" = "1" ] || [ -f "$HOME/.test-gate-disabled" ]; then
  log_row "disabled" "kill-switch" 0 0
  exit 0
fi

STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
if [ -z "$STAGED" ]; then
  log_row "skip" "no-staged-files" 0 0
  exit 0
fi

CODE_COUNT=0
DOCS_COUNT=0
is_doc() {
  case "$1" in
    *.md|*.txt|*.jsonl|*.log|CHANGELOG|LICENSE|CODEOWNERS|.gitignore|TODO.md) return 0 ;;
    */memory/*|*/research/*|*/.planning/*|*/checkpoints/*) return 0 ;;
    */feedback/*|*/feedback-from-companies/*) return 0 ;;
    *) return 1 ;;
  esac
}
is_code() {
  case "$1" in
    *.sh|*.bash|*.zsh) return 0 ;;
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs) return 0 ;;
    *.py|*.rb|*.go|*.rs) return 0 ;;
    *.java|*.kt|*.swift|*.c|*.cpp|*.h|*.hpp) return 0 ;;
    *package.json|*tsconfig.json|*Makefile|*.toml) return 0 ;;
    *) return 1 ;;
  esac
}

while IFS= read -r f; do
  [ -z "$f" ] && continue
  if is_code "$f"; then
    CODE_COUNT=$((CODE_COUNT + 1))
  elif is_doc "$f"; then
    DOCS_COUNT=$((DOCS_COUNT + 1))
  else
    DOCS_COUNT=$((DOCS_COUNT + 1))
  fi
done <<<"$STAGED"

if [ "$CODE_COUNT" -eq 0 ]; then
  log_row "skip" "docs-only" 0 "$DOCS_COUNT"
  exit 0
fi

if [ -n "${SKIP_TESTS_ACK:-}" ]; then
  REASON=$(printf '%s' "$SKIP_TESTS_ACK" | tr -d '"\\' | tr '\n\r' '  ')
  log_row "override" "$REASON" "$CODE_COUNT" "$DOCS_COUNT"
  echo "pre-commit-test-gate: override active (SKIP_TESTS_ACK='$REASON'; $CODE_COUNT code files staged)" >&2
  exit 0
fi

if [ ! -f "$MARKER_FILE" ]; then
  log_row "block" "no-marker" "$CODE_COUNT" "$DOCS_COUNT"
  cat >&2 <<EOF

BLOCKED — pre-commit-test-gate (HARD)
  Code files staged ($CODE_COUNT) but no test-run marker at: .claude/ran-tests

  D1 (verify before commit) requires test evidence. Run:
    bash hooks/mark-tests-ran.sh <your-test-command>

  Override (intentional skip — logged + reviewed):
    SKIP_TESTS_ACK='<why>' git commit ...

  Kill-switch: touch ~/.test-gate-disabled

EOF
  exit 1
fi

if command -v stat >/dev/null 2>&1; then
  MARKER_MTIME=$(stat -f %m "$MARKER_FILE" 2>/dev/null || stat -c %Y "$MARKER_FILE" 2>/dev/null || echo 0)
else
  MARKER_MTIME=0
fi
AGE=$((TS - MARKER_MTIME))

if [ "$AGE" -gt "$MARKER_TTL" ]; then
  log_row "block" "stale-marker" "$CODE_COUNT" "$DOCS_COUNT"
  cat >&2 <<EOF

BLOCKED — pre-commit-test-gate (HARD)
  Marker at .claude/ran-tests is ${AGE}s old (>${MARKER_TTL}s TTL).
  Re-run tests: bash hooks/mark-tests-ran.sh <cmd>

  Override: SKIP_TESTS_ACK='<why>' git commit ...

EOF
  exit 1
fi

MARKER_EXIT=$(grep -E '^exit=' "$MARKER_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')
if [ -z "$MARKER_EXIT" ] || [ "$MARKER_EXIT" != "0" ]; then
  log_row "block" "marker-nonzero-exit" "$CODE_COUNT" "$DOCS_COUNT"
  cat >&2 <<EOF

BLOCKED — pre-commit-test-gate (HARD)
  Last test run failed (exit=${MARKER_EXIT:-unknown}).
  Fix the failing test, then: bash hooks/mark-tests-ran.sh <cmd>

  Override: SKIP_TESTS_ACK='<why>' git commit ...

EOF
  exit 1
fi

log_row "pass" "fresh-marker-exit-0" "$CODE_COUNT" "$DOCS_COUNT"
exit 0

## Operationalization
#
### 1. Measurement mechanism
# .enforcement/test-gate.jsonl in sutra repo — one row per commit attempt.
#
### 2. Adoption mechanism
# Called from sutra/hooks/git-wrappers/pre-commit. Installed via
# `git config core.hooksPath hooks/git-wrappers` inside sutra.
#
### 3. Monitoring / escalation
# Override/block ratio. >20% override rate → review reasons.
#
### 4. Iteration trigger
# Kept in sync with holding/hooks/pre-commit-test-gate.sh until
# Sutra plugin hosts the shared implementation (L2→L1 promotion target).
#
### 5. DRI
# CEO of Sutra (sutra-repo hook).
#
### 6. Decommission criteria
# Retire when CI covers verification AND pre-commit is redundant.
