#!/bin/bash
# Sutra OS — Auto-Coverage Hook (D31 Phase 3 v0, 2026-04-20)
#
# PostToolUse hook. Infers the Sutra method from tool event + file path and
# auto-fires log-coverage.sh so the coverage log captures real phase
# transitions without relying on LLM discipline.
#
# Doctrine (D31):
#   - Mapping is DECLARATIVE (case statement), never runtime judgment.
#   - Silent on no match (exit 0). Never blocks.
#   - Reads task + depth from .claude/depth-registered marker (D28 format).
#   - Coverage: off in SUTRA-CONFIG.md → silent no-op.
#
# Registered: PostToolUse(Edit|Write|Bash) in settings.json.

set -u

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
LOGGER="$(dirname "$0")/log-coverage.sh"

[ -f "$CONFIG" ] || exit 0
[ -x "$LOGGER" ] || exit 0

COVERAGE_SETTING=$(grep '^coverage:' "$CONFIG" | head -1 | awk '{print $2}')
[ "$COVERAGE_SETTING" = "off" ] && exit 0

MARKER="$PROJECT_DIR/.claude/depth-registered"
[ -f "$MARKER" ] || MARKER="${CLAUDE_PROJECT_DIR:-$PROJECT_DIR}/.claude/depth-registered"
[ -f "$MARKER" ] || exit 0

DEPTH=$(grep -oE 'DEPTH=[0-9]+' "$MARKER" | head -1 | cut -d= -f2)
TASK=$(grep -oE 'TASK=[a-zA-Z0-9_.-]+' "$MARKER" | head -1 | cut -d= -f2)
[ -z "${DEPTH:-}" ] && exit 0
[ -z "${TASK:-}" ] && exit 0

TOOL="${TOOL_NAME:-}"
FILE="${TOOL_INPUT_file_path:-}"
CMD="${TOOL_INPUT_command:-}"

# Stdin-JSON fallback
if { [ -z "$FILE" ] && [ -z "$CMD" ]; } && [ ! -t 0 ]; then
  _JSON=$(cat 2>/dev/null || true)
  if [ -n "$_JSON" ]; then
    FILE=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    TOOL=$(printf '%s' "$_JSON" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi

fire() {
  local method="$1" evidence="$2"
  # Per-turn dedupe: if this (task, method) already fired since marker mtime, skip.
  local log="$PROJECT_DIR/os/coverage-log.jsonl"
  if [ -f "$log" ] && [ -f "$MARKER" ]; then
    local marker_mtime turn_start
    marker_mtime=$(stat -f %m "$MARKER" 2>/dev/null || stat -c %Y "$MARKER" 2>/dev/null || echo 0)
    turn_start=$(date -u -r "$marker_mtime" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "1970-01-01T00:00:00Z")
    local last_hit
    last_hit=$(grep "\"task\":\"$TASK\".*\"method\":\"$method\"" "$log" 2>/dev/null | tail -1 | grep -oE '"ts":"[^"]+"' | sed 's/"ts":"//;s/"$//')
    if [ -n "${last_hit:-}" ] && [ "$last_hit" \> "$turn_start" ]; then
      return 0
    fi
  fi
  bash "$LOGGER" "$TASK" "$DEPTH" "$method" "$evidence" >/dev/null 2>&1 || true
}

# DECLARATIVE PATH MAPPINGS — most specific first
case "$FILE" in
  *"/os/specs/"*.md|*-SPEC.md|*/specs/*-SPEC.md)
    fire PHASE-SHAPE "spec edit: ${FILE##*/}"
    ;;
  *-HLD.md|*/HLD-*.md|*"/hld/"*.md)
    fire GATE-HLD "HLD doc: ${FILE##*/}"
    ;;
  *-ADR.md|*/ADR-*.md|*"/adr/"*.md)
    fire GATE-ADR "ADR doc: ${FILE##*/}"
    ;;
  *"/research/"*.md|*-RESEARCH.md|*/RESEARCH-*.md)
    fire GATE-RESEARCH "research doc: ${FILE##*/}"
    ;;
  *"/feedback-to-sutra/"*.md|*"/feedback-from-sutra/"*.md|*-LEARN.md)
    fire PHASE-LEARN "feedback/learn doc: ${FILE##*/}"
    ;;
  *-VERIFY.md|*-TEST-RESULTS.md|*/verify/*.md)
    fire VERIFY-EVIDENCE "verify doc: ${FILE##*/}"
    ;;
  *-MEASURE.md|*/METRICS.md|*/MEASUREMENT.md)
    fire PHASE-MEASURE "measure doc: ${FILE##*/}"
    ;;
  */PLAN-*.md|*-PLAN.md)
    fire PHASE-PLAN "plan doc: ${FILE##*/}"
    ;;
esac

# BASH COMMAND MAPPINGS (conservative — test runners + commits only)
case "$CMD" in
  *"npm test"*|*"npm run test"*|*"jest"*|*"pytest"*|*"go test"*|*"cargo test"*|*"rspec"*)
    fire VERIFY-EVIDENCE "test runner fired"
    ;;
  *"git commit"*)
    fire PHASE-EXECUTE "git commit fired"
    ;;
esac

exit 0
