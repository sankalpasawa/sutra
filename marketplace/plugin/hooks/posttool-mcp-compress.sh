#!/usr/bin/env bash
# C3c MCP-tool output compression — Tokens charter, per-turn cost component
# PostToolUse hook matched on mcp__.* tools. Replaces large MCP outputs with
# a compressed summary BEFORE Claude sees them via hookSpecificOutput
# .updatedMCPToolOutput (codex-verified + docs-verified 2026-04-22).
#
# Docs: https://code.claude.com/docs/en/hooks
# Behavior confirmed:
#   - updatedMCPToolOutput REPLACES tool_response content (not appends)
#   - Only applied when exit 0
#   - Works for all mcp__* tools (playwright, context7, github, filesystem, ...)
#   - Parallel hooks don't chain — this must be the sole compressor for a tool
#
# Compression strategy (preserves signal over bytes):
#   - Size threshold: 4000 bytes (below: pass through)
#   - Head (first 40 lines) + tail (last 20 lines) + compression marker
#   - Middle summary: line count, byte count, source tool
#   - Error-bearing lines (error/fail/exception/warning) extracted from middle
#
# Kill-switch: touch ~/.c3c-disabled OR env C3C_DISABLED=1 → exit 0 pass-through

set -uo pipefail

# Kill-switch
if [ -f "$HOME/.c3c-disabled" ] || [ "${C3C_DISABLED:-0}" = "1" ]; then
  exit 0
fi

# Need jq
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

# Read hook input from stdin
INPUT=""
if [ ! -t 0 ]; then
  INPUT=$(cat)
fi
[ -z "$INPUT" ] && exit 0

# Parse tool name; only act on mcp__*
TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
case "$TOOL_NAME" in
  mcp__*) ;;
  *) exit 0 ;;
esac

# Extract tool_response.content — shape varies by MCP, try common paths
OUTPUT=$(printf '%s' "$INPUT" | jq -r '
  .tool_response.content //
  .tool_response.text //
  (.tool_response | if type == "string" then . else tostring end) //
  empty
' 2>/dev/null)

[ -z "$OUTPUT" ] && exit 0

# Size threshold
SIZE=${#OUTPUT}
THRESHOLD=4000
if [ "$SIZE" -lt "$THRESHOLD" ]; then
  exit 0
fi

# Compute compression
TOTAL_LINES=$(printf '%s\n' "$OUTPUT" | wc -l | tr -d ' ')
HEAD_N=40
TAIL_N=20
MIDDLE_LINES=$((TOTAL_LINES - HEAD_N - TAIL_N))

# Bail if not actually big in line count
if [ "$MIDDLE_LINES" -le 0 ] || [ "$TOTAL_LINES" -lt 80 ]; then
  exit 0
fi

HEAD_CONTENT=$(printf '%s' "$OUTPUT" | head -n "$HEAD_N")
TAIL_CONTENT=$(printf '%s' "$OUTPUT" | tail -n "$TAIL_N")

# Extract error/warning lines from middle
MIDDLE_CONTENT=$(printf '%s' "$OUTPUT" | sed -n "$((HEAD_N + 1)),$((TOTAL_LINES - TAIL_N))p")
ERROR_LINES=$(printf '%s' "$MIDDLE_CONTENT" | grep -iE '(error|fail|exception|warning|critical)' | head -10 || true)

# Build compressed output
COMPRESSED="${HEAD_CONTENT}

--- [C3c HOOK] Compressed ${MIDDLE_LINES} lines (${SIZE} bytes total, ${TOTAL_LINES} lines). Tool: ${TOOL_NAME} ---"

if [ -n "$ERROR_LINES" ]; then
  COMPRESSED="${COMPRESSED}

Error/warning lines retained from middle:
${ERROR_LINES}"
fi

COMPRESSED="${COMPRESSED}

--- [end compression, tail ${TAIL_N} lines follow] ---

${TAIL_CONTENT}"

# Emit replacement JSON — MUST exit 0 per docs (JSON only processed on exit 0)
jq -n --arg content "$COMPRESSED" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    updatedMCPToolOutput: $content
  }
}'

# Telemetry
TS=$(date +%s)
BYTES_SAVED=$((SIZE - ${#COMPRESSED}))
REPO_ROOT="${CLAUDE_PROJECT_DIR:-.}"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
printf '{"ts":%s,"event":"c3c-mcp-compress","tool":"%s","bytes_in":%s,"bytes_out":%s,"bytes_saved":%s,"lines_in":%s}\n' \
  "$TS" "$TOOL_NAME" "$SIZE" "${#COMPRESSED}" "$BYTES_SAVED" "$TOTAL_LINES" \
  >> "$REPO_ROOT/.enforcement/c3c-compress.jsonl" 2>/dev/null

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Per-compression telemetry at .enforcement/c3c-compress.jsonl — one row per fire.
# Fields: ts, tool, bytes_in, bytes_out, bytes_saved, lines_in.
# Aggregation example: tail -n 100 .enforcement/c3c-compress.jsonl | jq -s 'map(.bytes_saved) | add'
# Future: wire into ANALYTICS-PULSE via collect.sh §4 Cost as `mcp_bytes_saved_24h`.
#
### 2. Adoption mechanism
# Registered in .claude/settings.json PostToolUse with matcher: "mcp__.*".
# Downstream: vendored into sutra/package/hooks/ so `claude plugin marketplace
# update sutra` propagates to all clients (DayFlow standalone, Billu, Paisa when migrated).
#
### 3. Monitoring / escalation
# DRI (Sutra-OS) reviews .enforcement/c3c-compress.jsonl weekly. Warn: >20 tool
# outputs compressed per session and NO invocation of compressed tool names in
# subsequent messages — may indicate over-compression. Kill-switch: touch ~/.c3c-disabled.
#
### 4. Iteration trigger
# Tune THRESHOLD (default 4000 bytes), HEAD_N (40), TAIL_N (20) based on
# observed tool-output distribution. Add per-tool overrides if some MCPs
# need different preservation strategies (e.g., playwright browser_snapshot
# may need full DOM; context7 query-docs may need aggressive compression).
#
### 5. DRI
# Sutra-OS (Tokens charter DRI).
#
### 6. Decommission criteria
# Retire when: Claude Code ships native MCP output compression; MCP tool usage
# drops to near-zero; Tokens charter retires; or compression causes measurable
# Claude regression in tool-output utilization.
