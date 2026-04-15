#!/bin/bash
# Sutra OS — PreToolUse Dispatcher (portable bundle, v1.9)
# Single-process execution of PreToolUse checks. Runs checks sequentially;
# exits with first non-zero if any check blocks. Always emits warnings.
#
# Paths use $CLAUDE_PROJECT_DIR or the project root discovered via git.
# Installed to: {project}/.claude/hooks/sutra/dispatcher-pretool.sh

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_DIR="$REPO_ROOT/.claude/hooks/sutra"
HOOK_LOG="$REPO_ROOT/.claude/hooks/sutra/hook-log.jsonl"
ENFORCEMENT_DIR="$REPO_ROOT/.enforcement"
FILE_PATH="$TOOL_INPUT_file_path"
TOOL_NAME="${TOOL_NAME:-}"
BLOCK_CODE=0

# Claude Code ≥ ~1.0 passes tool_input as JSON on stdin instead of env vars.
# Read stdin JSON and extract fields when env vars are missing. 2026-04-15 fix.
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _STDIN_JSON=$(cat)
  if [ -n "$_STDIN_JSON" ]; then
    FILE_PATH=$(printf '%s' "$_STDIN_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$_STDIN_JSON" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi

mkdir -p "$(dirname "$HOOK_LOG")" "$ENFORCEMENT_DIR" 2>/dev/null

log_hook() {
  local _name="$1" _status="$2" _error="$3" _start="$4"
  local _end=$(date +%s)
  local _ms=$(( (_end - _start) * 1000 ))
  if [ "$_status" = "FAIL" ]; then
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"PreToolUse\",\"status\":\"FAIL\",\"error\":\"$_error\",\"ms\":$_ms}" >> "$HOOK_LOG"
  else
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"PreToolUse\",\"status\":\"PASS\",\"ms\":$_ms}" >> "$HOOK_LOG"
  fi
}

# ─── Check 1: Input Routing Verification (D28) ───────────────────────────────
# HARD: require INPUT/TYPE/ROUTE/FIT CHECK/ACTION block before deliverable edits.
# Marker is per-turn — cleared on UserPromptSubmit by reset-turn-markers.sh.
_start1=$(date +%s)
_check1_status="PASS"
_routing_missing=0
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    "$REPO_ROOT/.claude/"*|*/checkpoints/*|*/hook-log*|*TODO.md|*ESTIMATION-LOG*|*.lock)
      ;;
    *)
      ROUTING_MARKER="$REPO_ROOT/.claude/input-routed"
      if [ ! -f "$ROUTING_MARKER" ]; then
        echo ""
        echo "BLOCKED — INPUT ROUTING MISSING (D28)"
        echo "  Emit before any Write/Edit:"
        echo "    INPUT: [founder statement]"
        echo "    TYPE: direction | task | feedback | new concept | question"
        echo "    EXISTING HOME: [where this lives, or 'none']"
        echo "    ROUTE: [which protocol handles this]"
        echo "    FIT CHECK: [what changes in existing architecture]"
        echo "    ACTION: [proposed action]"
        echo "  Then: echo \$(date +%s) > .claude/input-routed"
        echo ""
        echo "{\"ts\":$(date +%s),\"miss\":\"routing\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$ENFORCEMENT_DIR/routing-misses.log"
        _check1_status="FAIL"
        _routing_missing=1
      fi
      ;;
  esac
fi
log_hook "InputRouting-D28" "$_check1_status" "" "$_start1"
[ "$_routing_missing" = "1" ] && [ "$BLOCK_CODE" = "0" ] && BLOCK_CODE=1

# ─── Check 2: Depth Block Verification (D2/D9/D26) ────────────────────────────
_start2=$(date +%s)
_check2_status="PASS"
_depth_missing=0
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    "$REPO_ROOT/.claude/"*|*/checkpoints/*|*/hook-log*|*TODO.md|*ESTIMATION-LOG*|*.lock)
      ;;
    *)
      DEPTH_MARKER="$REPO_ROOT/.claude/depth-registered"
      DEPTH_MARKER_ALT="$REPO_ROOT/.claude/depth-assessed"
      if [ ! -f "$DEPTH_MARKER" ] && [ ! -f "$DEPTH_MARKER_ALT" ]; then
        echo ""
        echo "BLOCKED — DEPTH BLOCK MISSING (D2/D9/D26)"
        echo "  Emit before any Write/Edit:"
        echo "    TASK: \"[what you're about to do]\""
        echo "    DEPTH: X/5"
        echo "    EFFORT: [time], [files]"
        echo "    COST: ~\$X (~Y% of \$200 plan)"
        echo "    IMPACT: [what this changes]"
        echo "  Then: echo \"DEPTH TIMESTAMP TASK\" > .claude/depth-registered"
        echo ""
        echo "{\"ts\":$(date +%s),\"miss\":\"depth\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$ENFORCEMENT_DIR/routing-misses.log"
        _check2_status="FAIL"
        _depth_missing=1
      fi
      ;;
  esac
fi
log_hook "DepthBlock-D2D9D26" "$_check2_status" "" "$_start2"
[ "$_depth_missing" = "1" ] && [ "$BLOCK_CODE" = "0" ] && BLOCK_CODE=1

# ─── Check 3: Sutra→Company Deploy Depth 5 (D27) ─────────────────────────────
# Inside a company session, "Sutra-touching" = edits to os/ tree or SUTRA-* files.
_start3=$(date +%s)
_check3_status="PASS"
_sutra_missing=0
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    */os/*|*SUTRA-CONFIG*|*SUTRA-VERSION*|*sutra-version|*/sutra/*)
      SUTRA_DEPTH5_MARKER="$REPO_ROOT/.claude/sutra-deploy-depth5"
      if [ ! -f "$SUTRA_DEPTH5_MARKER" ]; then
        echo ""
        echo "BLOCKED — SUTRA→COMPANY DEPLOY REQUIRES DEPTH 5 (D27)"
        echo "  File: $FILE_PATH"
        echo "  Sutra-touching edits (os/, SUTRA-*) run at Depth 5. Emit full block:"
        echo "    TASK, DEPTH: 5/5, EFFORT (incl. downstream deps), COST, IMPACT"
        echo "  Then: echo \$(date +%s) > .claude/sutra-deploy-depth5"
        echo ""
        echo "{\"ts\":$(date +%s),\"miss\":\"sutra-depth5\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$ENFORCEMENT_DIR/sutra-deploys.log"
        _check3_status="FAIL"
        _sutra_missing=1
      else
        echo "{\"ts\":$(date +%s),\"event\":\"sutra-deploy\",\"depth\":5,\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$ENFORCEMENT_DIR/sutra-deploys.log"
      fi
      ;;
  esac
fi
log_hook "SutraDeployDepth5-D27" "$_check3_status" "" "$_start3"
[ "$_sutra_missing" = "1" ] && [ "$BLOCK_CODE" = "0" ] && BLOCK_CODE=1

# ─── Check 4: Architecture Awareness (D12) ───────────────────────────────────
# SOFT: reminds when creating a new file to check architecture map.
_start4=$(date +%s)
if [ -n "$FILE_PATH" ] && [ ! -f "$FILE_PATH" ]; then
  SYSMAP=""
  [ -f "$REPO_ROOT/SYSTEM-MAP.md" ] && SYSMAP="$REPO_ROOT/SYSTEM-MAP.md"
  [ -f "$REPO_ROOT/os/SYSTEM-MAP.md" ] && SYSMAP="$REPO_ROOT/os/SYSTEM-MAP.md"
  if [ -n "$SYSMAP" ]; then
    REL="${FILE_PATH#$REPO_ROOT/}"
    DIR="$(dirname "$REL")"
    if ! grep -q "$DIR" "$SYSMAP" 2>/dev/null; then
      echo "PROTO-001: New path outside SYSTEM-MAP — $REL"
    fi
  fi
fi
log_hook "ArchitectureAwareness-D12" "PASS" "" "$_start4"

# ─── Check 5: Hardcoded Secrets (PROTO-004) ──────────────────────────────────
_start5=$(date +%s)
if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
  if grep -qiE '(api_key|secret_key|password|token)\s*[:=]\s*["\x27][A-Za-z0-9_\-]{20,}' "$FILE_PATH" 2>/dev/null; then
    case "$FILE_PATH" in
      *.env|*.env.*) ;;
      *)
        echo "PROTO-004: Possible hardcoded secret in $FILE_PATH — move to env vars"
        ;;
    esac
  fi
fi
log_hook "KeysInEnv-PROTO004" "PASS" "" "$_start5"

# ─── Check 6: Cascade Awareness (D13) ────────────────────────────────────────
# SOFT: reminds to cascade when os/ files change.
_start6=$(date +%s)
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    */os/*|*/.claude/os/*)
      echo "D13: os/ file changed — list downstream impacts and create TODOs for each."
      ;;
  esac
fi
log_hook "Cascade-D13" "PASS" "" "$_start6"

exit $BLOCK_CODE
