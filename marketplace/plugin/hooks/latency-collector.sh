#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Speed Charter W1 — Latency Collector (Stop hook, advisory)
# ═══════════════════════════════════════════════════════════════════════════════
# Spec:  sutra/os/charters/SPEED.md
# Plan:  holding/research/2026-04-20-speed-execution-plan.md
# Phase taxonomy: sutra/os/charters/SPEED-phase-taxonomy.md
#
# What it does:
#   1. Finds the session transcript JSONL at ~/.claude/projects/<project-hash>/
#   2. Parses since the last processed entry (cursor at holding/hooks/.latency-cursor)
#   3. Derives task boundaries (real user prompts — message.content is STRING)
#   4. Per task, computes phase latencies:
#      - wall_ms           first assistant ts in task → last ts before next user prompt
#      - tool_calls[]      each tool_use/tool_result pair with tool_dispatch_ms
#      - llm_think_ms      sum of thinking block durations (proxy: ts delta to next entry)
#      - n_tools           count of tool_use events
#   5. Emits one JSONL row per completed task to holding/LATENCY-LOG.jsonl
#   6. Updates cursor
#
# Non-goals (W1):
#   - hook-pretool / hook-posttool attribution per tool-call (hook-log is time-
#     ordered but joining by tool-call boundary in bash is expensive; deferred
#     to W1.1 if W2 data shows hook overhead is material)
#   - boot-load amortization (needs per-session wall-clock; deferred)
#   - Agent sub-phase breakdown (per taxonomy §4 — deferred unless >15% of wall)
#
# Always exits 0 (advisory). Any failure logs to
# .enforcement/latency-collector-errors.log and returns gracefully.
# ═══════════════════════════════════════════════════════════════════════════════

set -o pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
OUT_LOG="$REPO_ROOT/holding/LATENCY-LOG.jsonl"
CURSOR_FILE="$REPO_ROOT/holding/hooks/.latency-cursor"
ERROR_LOG="$REPO_ROOT/.enforcement/latency-collector-errors.log"
SOURCE_VERSION="v1"

mkdir -p "$(dirname "$OUT_LOG")" "$(dirname "$ERROR_LOG")" 2>/dev/null

_log_err() {
  local _msg="$1"
  local _ts=$(date +%s)
  echo "{\"ts\":$_ts,\"component\":\"latency-collector\",\"error\":\"$(printf '%s' "$_msg" | tr -d '"\\' | tr '\n\r' '  ')\"}" >> "$ERROR_LOG"
}

# jq is required — degrade gracefully without it.
if ! command -v jq >/dev/null 2>&1; then
  _log_err "jq not available; latency-collector skipped"
  exit 0
fi

# ─── 1. Resolve session transcript ────────────────────────────────────────────
# Priority: stdin JSON .transcript_path (Stop event payload) → env var → fallback.
TRANSCRIPT=""
# Read stdin if present (Stop hook passes JSON)
if [ ! -t 0 ]; then
  _STDIN_JSON=$(cat 2>/dev/null)
  if [ -n "$_STDIN_JSON" ]; then
    TRANSCRIPT=$(printf '%s' "$_STDIN_JSON" | jq -r '.transcript_path // empty' 2>/dev/null)
  fi
fi

# Fallback: newest JSONL in the project's session dir
if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  PROJECT_DIR_HASH=$(echo "$REPO_ROOT" | sed 's|/|-|g')
  SESS_DIR="$HOME/.claude/projects/$PROJECT_DIR_HASH"
  if [ -d "$SESS_DIR" ]; then
    TRANSCRIPT=$(ls -t "$SESS_DIR"/*.jsonl 2>/dev/null | head -1)
  fi
fi

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  _log_err "transcript_path missing and no fallback JSONL found"
  exit 0
fi

# ─── 2. Load cursor (last-processed timestamp) ────────────────────────────────
LAST_TS="1970-01-01T00:00:00.000Z"
if [ -f "$CURSOR_FILE" ]; then
  LAST_TS=$(cat "$CURSOR_FILE" 2>/dev/null | head -1 | tr -d '\r\n')
  [ -z "$LAST_TS" ] && LAST_TS="1970-01-01T00:00:00.000Z"
fi

# ─── 3. Identify company from REPO_ROOT ───────────────────────────────────────
COMPANY="asawa"
case "$REPO_ROOT" in
  *asawa-holding*) COMPANY="asawa" ;;
  *dayflow*)       COMPANY="dayflow" ;;
  *billu*)         COMPANY="billu" ;;
  *sutra*)         COMPANY="sutra" ;;
  *)               COMPANY=$(basename "$REPO_ROOT") ;;
esac

# ─── 4. Parse transcript into per-task latency rows ───────────────────────────
# jq pipeline:
#   a) Filter entries newer than LAST_TS
#   b) Chunk into tasks: each real user prompt (content is STRING) starts a chunk
#   c) Per chunk: compute wall_ms, gather tool_use/tool_result pairs, sum think
#   d) Emit LATENCY-LOG rows
#
# To keep bash-jq simple: we do this in two passes.
#   Pass 1: extract task boundaries (promptId + timestamp + content hash)
#   Pass 2: for each task window, aggregate events
#
# Below is the compact jq program. Entries newer than LAST_TS only.

# Pass 1: emit task boundaries. Real user prompt = type=="user" AND message.content is STRING.
TASKS_TSV=$(jq -r --arg since "$LAST_TS" '
  select(.timestamp > $since)
  | select(.type=="user" and (.message.content | type == "string"))
  | [.timestamp, .promptId // .uuid, (.message.content | tostring | .[0:80] | gsub("[\t\n]"; " "))]
  | @tsv
' "$TRANSCRIPT" 2>/dev/null)

if [ -z "$TASKS_TSV" ]; then
  # Nothing new. Advance cursor to newest entry in transcript for next run.
  NEWEST=$(jq -r 'select(.timestamp != null) | .timestamp' "$TRANSCRIPT" 2>/dev/null | sort | tail -1)
  [ -n "$NEWEST" ] && echo "$NEWEST" > "$CURSOR_FILE"
  exit 0
fi

# Pass 2: per task boundary, aggregate events in its window.
#   Task window: [task_start_ts, next_task_start_ts) — or [task_start_ts, newest_ts] for last task.

# Collect all task start timestamps in order
TASK_STARTS=()
TASK_IDS=()
TASK_PREVIEWS=()
while IFS=$'\t' read -r _ts _pid _preview; do
  TASK_STARTS+=("$_ts")
  TASK_IDS+=("$_pid")
  TASK_PREVIEWS+=("$_preview")
done <<< "$TASKS_TSV"

N_TASKS=${#TASK_STARTS[@]}
NEWEST_TS=$(jq -r 'select(.timestamp != null) | .timestamp' "$TRANSCRIPT" 2>/dev/null | sort | tail -1)

# Emit one LATENCY-LOG row per task.
for (( i=0; i<N_TASKS; i++ )); do
  _start="${TASK_STARTS[$i]}"
  if [ $((i+1)) -lt $N_TASKS ]; then
    _end="${TASK_STARTS[$((i+1))]}"
    _closed=true
  else
    _end="$NEWEST_TS"
    _closed=false
  fi
  _task_id="${TASK_IDS[$i]}"
  _preview="${TASK_PREVIEWS[$i]}"

  # Aggregate this task window with jq (-s slurps JSONL into single array).
  # Note: fromdateiso8601 rejects millisecond-precision ISO strings, so we
  # strip .xxxZ and add ms back separately — preserves ms precision.
  _row=$(jq -s -r --arg start "$_start" --arg end "$_end" --arg tid "$_task_id" \
              --arg co "$COMPANY" --arg sv "$SOURCE_VERSION" --arg preview "$_preview" \
              --arg closed "$_closed" '
    def iso_to_ms:
      . as $s
      | ($s | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601) as $secs
      | (try ($s | capture("\\.(?<ms>[0-9]{1,3})Z$") | .ms | tonumber) catch 0) as $ms
      | $secs * 1000 + $ms ;
    map(select(.timestamp != null and .timestamp >= $start and (if $closed == "true" then .timestamp < $end else .timestamp <= $end end)))
    | . as $win
    | (($win | map(select(.type=="assistant" and (.message.content[]? | .type=="tool_use")))) | length) as $n_tool_use_msgs
    | ($win | map(select(.type=="assistant" and (.message.content[]? | .type=="tool_use")))
           | map(.message.content | map(select(.type=="tool_use")) | .[])) as $tool_uses_nested
    | ($win | map(select(.type=="user" and (.message.content | type == "array")))
           | map(.message.content | map(select(.type=="tool_result")) | .[])) as $tool_results_nested
    | ($win | map(select(.type=="assistant" and (.message.content[]? | .type=="thinking")))) as $think_entries
    | ($win | map(select(.type=="assistant" and .message.usage != null)) | map(.message.usage)) as $usages
    | ($win | map(select(.type=="assistant" and (.message.content[]? | .type=="tool_use") and (.message.content[]? | .name? == "Task" or .name? == "Agent"))) | length) as $n_subagent_dispatches
    | ($win | length) as $n_events
    | (($win | map(.timestamp) | sort | last) // $end) as $last_ts
    | (($win | map(.timestamp) | sort | first) // $start) as $first_ts
    | (($last_ts | iso_to_ms) - ($first_ts | iso_to_ms)) as $wall_ms_raw
    | ($wall_ms_raw | floor) as $wall_ms
    | ({
        id: ($tid + "-" + ($start | tostring)),
        ts: $start,
        task_id: $tid,
        company: $co,
        task_preview: $preview,
        wall_ms: $wall_ms,
        closed: ($closed == "true"),
        phases: {
          n_tool_uses: ($tool_uses_nested | length),
          n_tool_results: ($tool_results_nested | length),
          n_thinking_blocks: ($think_entries | length),
          n_subagent_dispatches: $n_subagent_dispatches,
          n_events: $n_events
        },
        tokens: {
          input: ([$usages[].input_tokens // 0] | add // 0),
          output: ([$usages[].output_tokens // 0] | add // 0),
          cache_creation: ([$usages[].cache_creation_input_tokens // 0] | add // 0),
          cache_read: ([$usages[].cache_read_input_tokens // 0] | add // 0),
          total_effective: (
            ([$usages[].input_tokens // 0] | add // 0) +
            ([$usages[].output_tokens // 0] | add // 0) +
            ([$usages[].cache_creation_input_tokens // 0] | add // 0) +
            ([$usages[].cache_read_input_tokens // 0] | add // 0)
          ),
          n_assistant_turns: ($usages | length)
        },
        partial: (($closed != "true") or ($wall_ms <= 0)),
        source_version: $sv
      })
    | tostring
  ' "$TRANSCRIPT" 2>/dev/null)

  if [ -n "$_row" ] && [ "$_row" != "null" ]; then
    echo "$_row" >> "$OUT_LOG"
  else
    _log_err "empty row for task $_task_id window [$_start, $_end)"
  fi
done

# ─── 5. Advance cursor ────────────────────────────────────────────────────────
if [ -n "$NEWEST_TS" ]; then
  echo "$NEWEST_TS" > "$CURSOR_FILE"
fi

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
