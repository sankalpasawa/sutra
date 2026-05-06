#!/usr/bin/env bash
# sutra/marketplace/plugin/lib/h-sutra-classify-and-write.sh
#
# H-Sutra producer helper — function-only library shared by core@sutra
# (per-turn-discipline-prompt.sh) and native@sutra (per-turn-h-sutra.sh).
# Per D49 + codex round-1..5 design review (threads 019dfc31 / 019dfc3b /
# 019dfc41 / 019dfc4c / 019dfc52). Override logged 2026-05-06T08:09:28Z
# (gate-log.jsonl); design converged on a-ii shared-lib + arbitration lock.
#
# Folds applied:
#   - shared sourceable lib (round-1 a-ii)
#   - function-only, no top-level side effects (round-2 a-ii fold)
#   - full ownership of IR_TYPE derive + ts + turn_id + row build + lock +
#     dedupe + parent-dir create + stderr diagnostics (round-3 P1-1 fold)
#   - per-turn arbitration via filesystem lock so co-installed core+native
#     produce ONE row per turn — first mkdir wins (round-3 P1-2 fold)
#   - sanitized session id + bounded length + age-based stale-lock recovery
#     (round-3 P2-2 fold)
#   - row schema explicit; alias `risk` for native predicate.ts:97 (round-4 P2 fold)
#   - same-second same-prompt collision is documented as accepted limitation
#     (round-4 P1 — real-world unhittable; consumer-side dedupe protects)
#
# Sync contract: this file is canonical. Vendored to native via
# sutra/scripts/sync-h-sutra.sh; drift detected by sutra/hooks/h-sutra-drift-check.sh.

set -u

# h_sutra_classify_and_write
#   Args: $1 prompt-text  $2 classifier-path  $3 log-path  $4 session-id (may be empty)
#   Env (optional): SUTRA_HSUTRA_CAPTURE_INPUT=on|1|true|yes -> include input_text (head -c 500)
#   Returns: 0 on row written/deduped/arbitration-loss, 1 on infra failure
#
# Row schema (canonical, 15-16 fields):
#   ts                     ISO8601Z (1s precision)
#   turn_id                sha256(ts|prompt) first-12
#   direction              from classifier (always "INBOUND" today)
#   verb                   from classifier (DIRECT|QUERY|ASSERT|STAGE-1-FAIL)
#   principal_act          same as verb
#   mixed_acts             array of secondary verbs from classifier
#   tense                  past|present|future|null
#   timing                 now|later
#   channel                in-band|...
#   reversibility          reversible|irreversible
#   decision_risk          low|high  (legacy field)
#   risk                   alias of decision_risk (native predicate.ts:97 reads .risk)
#   stage_1_pass           negation of classifier .stage_1_fail
#   stage_3_emission_type  from classifier
#   input_routing_type     helper-derived IR_TYPE (question|task|direction|feedback)
#   input_text             OPTIONAL — env-gated; first 500 chars of prompt
h_sutra_classify_and_write() {
  local prompt="$1"
  local classifier="$2"
  local log_path="$3"
  local session_id="${4:-}"

  local sid_safe
  sid_safe=$(printf '%s' "$session_id" | tr -cd 'a-zA-Z0-9_-' | head -c 64)
  [ -z "$sid_safe" ] && sid_safe="no-sid"

  local lc
  lc=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')
  local ir_type="task"
  case "$lc" in
    *"?"*) ir_type="question" ;;
  esac
  if printf '%s' "$lc" | grep -qE '\b(missed|wrong|broken|error|failed|didn.?t|wasn.?t|isn.?t|not yet)\b'; then
    ir_type="feedback"
  fi
  if printf '%s' "$lc" | grep -qE '\b(should|must|always|never|going forward|from now on)\b'; then
    ir_type="direction"
  fi

  local classifier_json
  classifier_json=$(IR_TYPE="$ir_type" bash "$classifier" "$prompt" 2>/dev/null)
  if [ -z "$classifier_json" ]; then
    printf '[h-sutra] classifier returned empty; row skipped.\n' >&2
    return 1
  fi

  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local turn_id
  turn_id=$(printf '%s' "${ts}|${prompt}" | shasum -a 256 2>/dev/null | cut -c1-12)

  local input_text=""
  case "${SUTRA_HSUTRA_CAPTURE_INPUT:-}" in
    on|1|true|yes)
      input_text=$(printf '%s' "$prompt" | head -c 500)
      ;;
  esac

  local prompt_hash
  prompt_hash=$(printf '%s' "$prompt" | shasum -a 256 2>/dev/null | cut -c1-12)
  local ts_bucket
  ts_bucket=$(date -u +%s)
  local arbiter_lock="/tmp/h-sutra-arbiter-${sid_safe}-${ts_bucket}-${prompt_hash}"
  find /tmp -maxdepth 1 -type d -name 'h-sutra-arbiter-*' -mmin +2 -exec rmdir {} \; 2>/dev/null || true
  if ! mkdir "$arbiter_lock" 2>/dev/null; then
    return 0
  fi
  trap 'rmdir "$arbiter_lock" 2>/dev/null' RETURN

  local row
  row=$(printf '%s' "$classifier_json" | jq -c \
    --arg ts "$ts" \
    --arg turn_id "$turn_id" \
    --arg ir_type "$ir_type" \
    --arg input_text "$input_text" \
    '{ts:$ts,
      turn_id:$turn_id,
      direction:.direction,
      verb:.verb,
      principal_act:.principal_act,
      mixed_acts:.mixed_acts,
      tense:.tense,
      timing:.timing,
      channel:.channel,
      reversibility:.reversibility,
      decision_risk:.decision_risk,
      risk:.decision_risk,
      stage_1_pass:(.stage_1_fail==false),
      stage_3_emission_type:.stage_3_emission_type,
      input_routing_type:$ir_type}
     + (if $input_text == "" then {} else {input_text:$input_text} end)' 2>/dev/null)
  if [ -z "$row" ]; then
    printf '[h-sutra] row build failed; skipped.\n' >&2
    return 1
  fi

  mkdir -p "$(dirname "$log_path")" 2>/dev/null || true
  local log_lock="${log_path}.lock"
  local locked=0
  for _ in 1 2 3 4 5; do
    if mkdir "$log_lock" 2>/dev/null; then locked=1; break; fi
    sleep 0.2 2>/dev/null || sleep 1
  done
  if [ "$locked" = "1" ]; then
    if ! tail -n 10 "$log_path" 2>/dev/null | grep -qF "\"turn_id\":\"$turn_id\""; then
      printf '%s\n' "$row" >> "$log_path"
    fi
    rmdir "$log_lock" 2>/dev/null || true
    return 0
  else
    printf '[h-sutra] log lock contended; row %s skipped.\n' "$turn_id" >&2
    return 1
  fi
}
