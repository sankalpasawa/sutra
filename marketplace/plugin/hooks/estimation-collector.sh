#!/usr/bin/env bash
# Sutra OS — Estimation Collector (Stop event)
# Scrapes the ESTIMATE / ACTUAL lines from the current transcript and appends
# a JSONL record to holding/ESTIMATION-LOG.jsonl matching ESTIMATION-ENGINE.md
# schema v1.
#
# Background: ESTIMATION-ENGINE.md (lines 443-486) specifies a MEASURE-phase
# auto-capture that, until 2026-04-17, existed only as spec. Seed data in
# ESTIMATION-LOG.jsonl was frozen 2026-04-05. This hook wires the actual
# runtime behavior.
#
# Expected assistant output format (CLAUDE.md):
#   ESTIMATE: tokens_est=N, files_est=M, time_min_est=T, category=<slug>
#   ACTUAL: tokens=<observed>, files=<touched>, time_min=<measured>
#
# Rules:
#   - Silent no-op when no ESTIMATE line present in transcript tail.
#   - Idempotent per session_id: rerunning on the same session won't
#     double-append.
#   - If ACTUAL line is missing we fall back to git-diff heuristics and mark
#     the record with accuracy_inferred: true, skipping the per-field actuals
#     we cannot source.
#   - Always exits 0 (advisory — never blocks a Stop).
#
# Wired from: holding/hooks/dispatcher-stop.sh (section 13).
# Also invokable directly for tests/debugging.
#
# Env overrides (test hooks):
#   ESTIMATION_TRANSCRIPT=/path/to/transcript.jsonl
#   ESTIMATION_LOG_OVERRIDE=/path/to/log.jsonl
#   ESTIMATION_TAIL_LINES=200
# ───────────────────────────────────────────────────────────────────────────────

set -o pipefail

# BUILD-LAYER: L0 (plugin-native, promoted from holding 2026-04-23 per
#              PROTO-021 — plugin v1.12.0).
# Default-OFF per D32: set `enabled_hooks.estimation-collector: true` in
#   the instance's os/SUTRA-CONFIG.md to activate.
# Kill-switches: ~/.estimation-collector-disabled OR ESTIMATION_DISABLED=1

[ -f "$HOME/.estimation-collector-disabled" ] && exit 0
[ "${ESTIMATION_DISABLED:-0}" = "1" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# D32 enablement check (default-off)
_CFG="$REPO_ROOT/os/SUTRA-CONFIG.md"
if [ ! -f "$_CFG" ]; then exit 0; fi
if ! grep -qE "^[[:space:]]+estimation-collector:[[:space:]]+true" "$_CFG" 2>/dev/null; then exit 0; fi

# Default log: per-instance .enforcement/estimation-log.jsonl (portable).
# Asawa keeps holding/ESTIMATION-LOG.jsonl via ESTIMATION_LOG_OVERRIDE env.
LOG_FILE="${ESTIMATION_LOG_OVERRIDE:-$REPO_ROOT/.enforcement/estimation-log.jsonl}"

# ─── 1. Locate transcript ─────────────────────────────────────────────────────
TRANSCRIPT_PATH=""
STDIN_SESSION_ID=""

# 1a. Explicit test override
if [ -n "${ESTIMATION_TRANSCRIPT:-}" ] && [ -f "${ESTIMATION_TRANSCRIPT}" ]; then
  TRANSCRIPT_PATH="$ESTIMATION_TRANSCRIPT"
fi

# 1b. Claude Code hook stdin payload (Stop event)
if [ -z "$TRANSCRIPT_PATH" ] && [ ! -t 0 ]; then
  STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
  if [ -n "$STDIN_PAYLOAD" ]; then
    CANDIDATE=$(printf '%s' "$STDIN_PAYLOAD" | \
      sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -n "$CANDIDATE" ] && [ -f "$CANDIDATE" ]; then
      TRANSCRIPT_PATH="$CANDIDATE"
    fi
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

# ─── 2. Extract ESTIMATE line from last N assistant messages ──────────────────
TAIL_LINES="${ESTIMATION_TAIL_LINES:-400}"

# Spec: "ESTIMATE: tokens_est=N, files_est=M, time_min_est=T, category=<slug>"
# Slug allows letters, digits, dot, colon, dash, underscore (e.g. sutra:build).
# Note: transcripts encode real newlines as the two-char escape `\n`. The
# category charset must therefore exclude `\` so the match stops at the
# escape rather than gobbling `holding:ops\nTRIAGE:` into one token.
EST_MATCH=$(tail -n "$TAIL_LINES" "$TRANSCRIPT_PATH" 2>/dev/null | \
  grep -oE 'ESTIMATE:[[:space:]]*tokens_est=[0-9]+,[[:space:]]*files_est=[0-9]+,[[:space:]]*time_min_est=[0-9]+(\.[0-9]+)?,[[:space:]]*category=[A-Za-z0-9_:.-]+(,[[:space:]]*speed_weight=[0-9]+(\.[0-9]+)?)?' | \
  tail -1)

# No ESTIMATE line — silent no-op.
if [ -z "$EST_MATCH" ]; then
  exit 0
fi

TOKENS_EST=$(printf '%s' "$EST_MATCH" | sed -n 's/.*tokens_est=\([0-9][0-9]*\).*/\1/p')
FILES_EST=$(printf '%s' "$EST_MATCH" | sed -n 's/.*files_est=\([0-9][0-9]*\).*/\1/p')
TIME_EST=$(printf '%s' "$EST_MATCH" | sed -n 's/.*time_min_est=\([0-9][0-9]*\(\.[0-9]*\)\{0,1\}\).*/\1/p')
CATEGORY=$(printf '%s' "$EST_MATCH" | sed -n 's/.*category=\([A-Za-z0-9_:.-][A-Za-z0-9_:.-]*\).*/\1/p')
# D21 speed_weight — optional field (2026-04-22). Range 0.0-1.0; default "" → omitted from output.
SPEED_WEIGHT=$(printf '%s' "$EST_MATCH" | sed -n 's/.*speed_weight=\([0-9][0-9]*\(\.[0-9]*\)\{0,1\}\).*/\1/p')

# Sanity check
if [ -z "$TOKENS_EST" ] || [ -z "$FILES_EST" ] || [ -z "$TIME_EST" ] || [ -z "$CATEGORY" ]; then
  exit 0
fi

# ─── 3. Extract ACTUAL line if present ────────────────────────────────────────
ACT_MATCH=$(tail -n "$TAIL_LINES" "$TRANSCRIPT_PATH" 2>/dev/null | \
  grep -oE 'ACTUAL:[[:space:]]*tokens=[0-9]+,[[:space:]]*files=[0-9]+,[[:space:]]*time_min=[0-9]+(\.[0-9]+)?' | \
  tail -1)

TOKENS_ACT=""
FILES_ACT=""
TIME_ACT=""
ACCURACY_INFERRED="false"

if [ -n "$ACT_MATCH" ]; then
  TOKENS_ACT=$(printf '%s' "$ACT_MATCH" | sed -n 's/.*tokens=\([0-9][0-9]*\).*/\1/p')
  FILES_ACT=$(printf '%s' "$ACT_MATCH" | sed -n 's/.*files=\([0-9][0-9]*\).*/\1/p')
  TIME_ACT=$(printf '%s' "$ACT_MATCH" | sed -n 's/.*time_min=\([0-9][0-9]*\(\.[0-9]*\)\{0,1\}\).*/\1/p')
else
  ACCURACY_INFERRED="true"
  # Heuristic: files touched by the last commit via git.
  if command -v git >/dev/null 2>&1; then
    GIT_FILES=$(git -C "$REPO_ROOT" diff --stat HEAD~1 2>/dev/null | tail -1 | grep -oE '[0-9]+ files? changed' | grep -oE '[0-9]+' | head -1)
    if [ -n "$GIT_FILES" ]; then
      FILES_ACT="$GIT_FILES"
    fi
  fi
  # D9 COMPARE wire (2026-04-22): synthesize tokens_actual by summing per-turn
  # usage across the transcript's assistant records. Closes the COMPARE-side
  # coverage gap flagged in ESTIMATION-CONFIDENCE.md first run (11/19 rows had
  # token actuals; this pushes toward 100%).
  # Prefer jq, fall back to python3. Sum = input + output + cache_read + cache_creation.
  if [ -z "$TOKENS_ACT" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    if command -v jq >/dev/null 2>&1; then
      SYNTH_TOKENS=$(jq -s '
        [ .[]
          | select(.type=="assistant" and .message.usage != null)
          | .message.usage
          | (.input_tokens // 0)
            + (.output_tokens // 0)
            + (.cache_read_input_tokens // 0)
            + (.cache_creation_input_tokens // 0)
        ] | add // 0
      ' "$TRANSCRIPT_PATH" 2>/dev/null)
    elif command -v python3 >/dev/null 2>&1; then
      SYNTH_TOKENS=$(python3 - "$TRANSCRIPT_PATH" <<'PYEOF' 2>/dev/null
import json, sys
total = 0
try:
    with open(sys.argv[1], 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "assistant":
                continue
            u = (d.get("message") or {}).get("usage") or {}
            total += (u.get("input_tokens") or 0)
            total += (u.get("output_tokens") or 0)
            total += (u.get("cache_read_input_tokens") or 0)
            total += (u.get("cache_creation_input_tokens") or 0)
except Exception:
    pass
print(total)
PYEOF
)
    fi
    if [ -n "$SYNTH_TOKENS" ] && [ "$SYNTH_TOKENS" -gt 0 ] 2>/dev/null; then
      TOKENS_ACT="$SYNTH_TOKENS"
    fi
  fi
fi

# ─── 4. Determine session id ──────────────────────────────────────────────────
SESSION_ID="${STDIN_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
if [ -z "$SESSION_ID" ]; then
  SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
fi

# ─── 5. Idempotency check — skip if this session_id already logged ────────────
# Look at the tail of the log (last 50 lines is plenty) for a matching
# session_id. Matches ESTIMATION-ENGINE.md:484 (5-line dedupe window) in
# spirit, but keyed on session_id for this auto-capture path since one
# session = one ESTIMATE line by convention.
if [ -f "$LOG_FILE" ]; then
  SESSION_ESC_FOR_MATCH=$(printf '%s' "$SESSION_ID" | sed 's/[.[\*^$(){}+?|/]/\\&/g')
  if tail -n 50 "$LOG_FILE" 2>/dev/null | grep -q "\"session_id\":\"$SESSION_ESC_FOR_MATCH\""; then
    exit 0
  fi
fi

# ─── 6. Emit JSONL record ─────────────────────────────────────────────────────
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CWD_ESC=$(pwd | sed 's/"/\\"/g')
RAW_ESC=$(printf '%s' "$EST_MATCH" | sed 's/\\/\\\\/g; s/"/\\"/g')
SESSION_ESC=$(printf '%s' "$SESSION_ID" | sed 's/"/\\"/g')
CATEGORY_ESC=$(printf '%s' "$CATEGORY" | sed 's/"/\\"/g')

# UUID-ish id — monotonic + session-derived. Matches seed schema's "id" field.
ID="auto-$(date -u +%s)-$(printf '%s' "$SESSION_ID" | cut -c1-8)"

mkdir -p "$(dirname "$LOG_FILE")"

# Build actuals subobject conditionally.
build_actuals() {
  local parts=""
  if [ -n "$TOKENS_ACT" ]; then parts+="\"tokens_total\":$TOKENS_ACT,"; fi
  if [ -n "$FILES_ACT" ]; then  parts+="\"files_touched\":$FILES_ACT,"; fi
  if [ -n "$TIME_ACT" ]; then   parts+="\"duration_min\":$TIME_ACT,"; fi
  # Strip trailing comma
  parts="${parts%,}"
  printf '{%s}' "$parts"
}

ACTUALS_JSON=$(build_actuals)

# Compose the record as a single line.
# Schema matches ESTIMATION-LOG.jsonl seed entries where possible; adds
# accuracy_inferred flag + source marker for the auto-capture origin.
# D21 speed_weight (2026-04-22) — included in estimates subobject when emitted.
if [ -n "$SPEED_WEIGHT" ]; then
  ESTIMATES_JSON=$(printf '{"tokens_total":%s,"files_touched":%s,"duration_min":%s,"speed_weight":%s}' \
    "$TOKENS_EST" "$FILES_EST" "$TIME_EST" "$SPEED_WEIGHT")
else
  ESTIMATES_JSON=$(printf '{"tokens_total":%s,"files_touched":%s,"duration_min":%s}' \
    "$TOKENS_EST" "$FILES_EST" "$TIME_EST")
fi

printf '{"id":"%s","ts":"%s","session_id":"%s","source":"estimation-collector","cwd":"%s","category":"%s","estimates":%s,"actuals":%s,"accuracy_inferred":%s,"raw_line":"%s"}\n' \
  "$ID" "$TS" "$SESSION_ESC" "$CWD_ESC" "$CATEGORY_ESC" \
  "$ESTIMATES_JSON" "$ACTUALS_JSON" "$ACCURACY_INFERRED" "$RAW_ESC" \
  >> "$LOG_FILE"

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Row count in holding/ESTIMATION-LOG.jsonl (wc -l). Coverage: how many rows
# include actuals.tokens_total vs. only estimates (null → model didn't emit
# ACTUAL line). Future: collector synthesizes actuals from Stop stdin usage.
#
### 2. Adoption mechanism
# Called by dispatcher-stop.sh section 13. Collector parses current-turn's
# ESTIMATE/ACTUAL block from transcript + writes JSONL row.
#
### 3. Monitoring / escalation
# DRI reviews ESTIMATION-LOG weekly via estimation-compress.sh accuracy rollup.
# Warn: coverage <50% (model missing ACTUAL lines).
#
### 4. Iteration trigger
# Accuracy <80% for 2 weeks → recalibrate category estimates.
# Coverage drop → investigate actuals-synthesis path.
#
### 5. DRI
# Sutra-OS (ESTIMATION-ENGINE owner).
#
### 6. Decommission criteria
# Retire when: native telemetry stream (Tokens charter Phase 0 Step 3-6)
# subsumes ESTIMATION-LOG; or Estimation charter retires.

## Operationalization
#
### 1. Measurement mechanism
# One JSONL row per session appended to holding/ESTIMATION-LOG.jsonl with
# estimates + actuals + accuracy_inferred flag. Feeds estimation-compress.sh.
#
### 2. Adoption mechanism
# Registered as section 13 of holding/hooks/dispatcher-stop.sh. Runs on every
# Stop event. Silent no-op when no ESTIMATE line emitted in transcript.
#
### 3. Monitoring / escalation
# Row count vs expected growth in ESTIMATION-CONFIDENCE.md (2026-04-22 baseline
# 19 rows / 11 with tokens). Coverage gap resolved via D9 COMPARE synthesis.
#
### 4. Iteration trigger
# Revise when: transcript schema changes (new usage fields), category taxonomy
# grows, or speed_weight aggregation semantics are defined.
#
### 5. DRI
# CEO of Asawa (ESTIMATION-ENGINE owner, D9).
#
### 6. Decommission criteria
# Retire when: Sutra plugin's estimation-stop.sh supersedes with matching
# schema, AND the JSONL log moves to a plugin-owned telemetry path.

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# Per-session JSONL append to <instance>/.enforcement/estimation-log.jsonl
# (or holding/ESTIMATION-LOG.jsonl via ESTIMATION_LOG_OVERRIDE in Asawa).
# Metric: tokens_est vs tokens_actual delta per category; rolling accuracy feeds
# ESTIMATION-CONFIDENCE.md (confident categories compress the pre-task estimate
# block per D9 COMPRESS). Null: no row when ESTIMATE line absent from transcript.
#
# ### 2. Adoption mechanism
# Ships via plugin. Default-OFF per D32 — each instance sets
# enabled_hooks.estimation-collector: true in its own os/SUTRA-CONFIG.md.
# Registered in plugin hooks.json under Stop event. Delivery via
# `claude plugin marketplace update sutra`.
#
# ### 3. Monitoring / escalation
# DRI reviews 7d category accuracy weekly. Warn: <60% accuracy at 7d after
# 10+ samples (estimator drifting). Breach: <40% accuracy (category retune
# required). Fleet-wide: Sutra Analytics Dept surfaces median per category.
#
# ### 4. Iteration trigger
# Add category when novel task class emerges. Retire category when 0 samples
# for 60d. Tune schema when CLAUDE.md ESTIMATE format changes.
#
# ### 5. DRI
# Sutra Forge owns plugin version. Per-instance DRI owns enablement + category
# list curation.
#
# ### 6. Decommission criteria
# Retire when (a) all categories reach confident status for 90d (compression
# makes the collector redundant), OR (b) token telemetry replaces ESTIMATE/
# ACTUAL line-scraping with structured per-tool-call capture.
# ================================================================================
