#!/usr/bin/env bash
# Sutra OS — Triage Collector (Stop event)
# Scrapes the TRIAGE line from the last assistant message of the current
# transcript and appends a JSONL record to holding/TRIAGE-LOG.jsonl.
#
# CLAUDE.md:32 requires every task to end with:
#   TRIAGE: depth_selected=X, depth_correct=X, class=[correct|overtriage|undertriage]
# Until this hook existed, that line was printed to the transcript and vanished.
#
# Wired from: holding/hooks/dispatcher-stop.sh (section 12)
# Also invokable directly for tests/debugging.
#
# Invocation contract:
#   - Stop hooks receive a JSON payload on stdin containing "transcript_path".
#     (See https://docs.claude.com/en/docs/claude-code/hooks — Stop event.)
#   - If stdin has no JSON we fall back to env vars or a scanner argument.
#   - Env override for tests: TRIAGE_TRANSCRIPT=/path/to/transcript.jsonl
#   - Env override for tests: TRIAGE_LOG_OVERRIDE=/path/to/log.jsonl
#   - Always exits 0 (advisory — never blocks a Stop).
# ───────────────────────────────────────────────────────────────────────────────

set -o pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LOG_FILE="${TRIAGE_LOG_OVERRIDE:-$REPO_ROOT/holding/TRIAGE-LOG.jsonl}"

# ─── 1. Locate transcript ─────────────────────────────────────────────────────
TRANSCRIPT_PATH=""

# 1a. Explicit test override
if [ -n "${TRIAGE_TRANSCRIPT:-}" ] && [ -f "${TRIAGE_TRANSCRIPT}" ]; then
  TRANSCRIPT_PATH="$TRIAGE_TRANSCRIPT"
fi

# 1b. Claude Code hook stdin payload (Stop event)
if [ -z "$TRANSCRIPT_PATH" ] && [ ! -t 0 ]; then
  STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
  if [ -n "$STDIN_PAYLOAD" ]; then
    # Extract transcript_path without requiring jq — tolerant regex.
    CANDIDATE=$(printf '%s' "$STDIN_PAYLOAD" | \
      sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -n "$CANDIDATE" ] && [ -f "$CANDIDATE" ]; then
      TRANSCRIPT_PATH="$CANDIDATE"
    fi
    # Stash the session id from the payload if present — used below.
    STDIN_SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | \
      sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi

# 1c. Common env var spellings
if [ -z "$TRANSCRIPT_PATH" ]; then
  for candidate in "${CLAUDE_TRANSCRIPT_PATH:-}" "${CLAUDE_CODE_TRANSCRIPT_PATH:-}"; do
    if [ -n "$candidate" ] && [ -f "$candidate" ]; then
      TRANSCRIPT_PATH="$candidate"
      break
    fi
  done
fi

# No transcript — silent no-op (advisory).
if [ -z "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# ─── 2. Extract TRIAGE line from last N assistant messages ────────────────────
# Transcripts are JSONL — one event per line. We scan the tail for TRIAGE
# markers. Grep is sufficient: the spec line is unambiguous.
TAIL_LINES="${TRIAGE_TAIL_LINES:-200}"

# The raw match: "TRIAGE: depth_selected=N, depth_correct=N, class=WORD"
MATCH=$(tail -n "$TAIL_LINES" "$TRANSCRIPT_PATH" 2>/dev/null | \
  grep -oE 'TRIAGE:[[:space:]]*depth_selected=[0-9]+,[[:space:]]*depth_correct=[0-9]+,[[:space:]]*class=[a-zA-Z_]+' | \
  tail -1)

# No TRIAGE line — silent no-op.
if [ -z "$MATCH" ]; then
  exit 0
fi

DEPTH_SELECTED=$(printf '%s' "$MATCH" | sed -n 's/.*depth_selected=\([0-9][0-9]*\).*/\1/p')
DEPTH_CORRECT=$(printf '%s' "$MATCH" | sed -n 's/.*depth_correct=\([0-9][0-9]*\).*/\1/p')
CLASS=$(printf '%s' "$MATCH" | sed -n 's/.*class=\([a-zA-Z_][a-zA-Z_]*\).*/\1/p')

# Sanity: if any field missing, bail quietly.
if [ -z "$DEPTH_SELECTED" ] || [ -z "$DEPTH_CORRECT" ] || [ -z "$CLASS" ]; then
  exit 0
fi

# ─── 3. Determine session id ──────────────────────────────────────────────────
SESSION_ID="${STDIN_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
if [ -z "$SESSION_ID" ]; then
  SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
fi

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CWD_ESC=$(pwd | sed 's/"/\\"/g')
RAW_ESC=$(printf '%s' "$MATCH" | sed 's/\\/\\\\/g; s/"/\\"/g')
SESSION_ESC=$(printf '%s' "$SESSION_ID" | sed 's/"/\\"/g')

mkdir -p "$(dirname "$LOG_FILE")"

printf '{"ts":"%s","session_id":"%s","cwd":"%s","depth_selected":%s,"depth_correct":%s,"class":"%s","raw_line":"%s"}\n' \
  "$TS" "$SESSION_ESC" "$CWD_ESC" "$DEPTH_SELECTED" "$DEPTH_CORRECT" "$CLASS" "$RAW_ESC" \
  >> "$LOG_FILE"

exit 0

# ============================================================================
# ## Operationalization
# (Auto-appended on D38 wave-6 plugin promotion — lightweight default; replace
# with concrete metrics when this hook gets attention.)
#
# ### 1. Measurement mechanism
# Hook events emit to .enforcement/build-layer-ledger.jsonl or hook-specific
# log when relevant; no dedicated metric until usage observed.
# ### 2. Adoption mechanism
# Activated via plugin distribution from sutra/marketplace/plugin/hooks/.
# ### 3. Monitoring / escalation
# Surface error/anomaly rate to Asawa CEO weekly until baseline established.
# ### 4. Iteration trigger
# Tighten or loosen after 14 days of fleet observation.
# ### 5. DRI
# Asawa CEO (Sutra Forge per D31).
# ### 6. Decommission criteria
# Retire when capability supersedes via newer hook or absorbed into a
# composite gate. Currently no decommission planned.
# ============================================================================
