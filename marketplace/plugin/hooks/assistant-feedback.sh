#!/usr/bin/env bash
#
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/commands/assistant-feedback
#   Acceptance (P4): --ask writes feedback.prompted + queue entry; --list
#     shows queue; --answer writes feedback.captured + removes queue entry;
#     flock serializes profile.json writes; profile auto-bootstraps.
#
# Direction: D1 (simplicity), D29 (speed)
# Spec: holding/research/2026-04-24-assistant-layer-design.md §8, §13
# Note: spec §8 sketched profile.yaml; P4 uses profile.json (same schema;
#   jq-native manipulation; no PyYAML dependency). Reader accepts both.
#
# PURPOSE
# Capture feedback at decision surfaces. Surface a prompt, log the
# answer, update per-human profile.
#
# USAGE
#   bash holding/scripts/assistant-feedback.sh --ask <surface> "question" <opt1,opt2,opt3>
#   bash holding/scripts/assistant-feedback.sh --list
#   bash holding/scripts/assistant-feedback.sh --answer <prompt_id> <option>
#   bash holding/scripts/assistant-feedback.sh --profile
#
# Writes to profile.json + events.jsonl (profile under flock).

set -uo pipefail

command -v jq >/dev/null 2>&1 || { printf 'jq required\n' >&2; exit 1; }

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CLIENT_ID="${SUTRA_CLIENT_ID:-holding}"
STATE_DIR="${SUTRA_ASSISTANT_STATE_DIR:-$REPO_ROOT/holding/state/assistants/$CLIENT_ID}"
EVENTS="$STATE_DIR/events.jsonl"
PROFILE="$STATE_DIR/profile.json"
LOCK="$STATE_DIR/profile.lock"

mkdir -p "$STATE_DIR" 2>/dev/null || { printf 'cannot create state dir\n' >&2; exit 1; }

bootstrap_profile() {
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  jq -n --arg v "1.0" --arg cid "$CLIENT_ID" --arg created "$TS" --arg repo "$REPO_ROOT" \
    '{
      v: $v, client_id: $cid, created: $created, enabled: true,
      identity: {primary_name: "Billu", tier: "T1", repos: [$repo]},
      preferences: {readability_budget: 25, explanation_verbosity: "terse",
        feedback_tolerance: "low", decision_visualization: "ascii-box"},
      learned_patterns: {depth_drift: {}, rejected_approaches: []},
      energy: {last_reading: null, baseline_cadence_minutes: null},
      unresolved_feedback: []
    }' > "$PROFILE"
}

ensure_profile() { [ -f "$PROFILE" ] || bootstrap_profile; }

acquire_lock() {
  local max_wait=3 waited=0
  if [ -d "$LOCK" ]; then
    local mt age
    if mt=$(stat -f %m "$LOCK" 2>/dev/null); then age=$(( $(date +%s) - mt ))
    elif mt=$(stat -c %Y "$LOCK" 2>/dev/null); then age=$(( $(date +%s) - mt ))
    else age=0; fi
    [ "$age" -gt 10 ] && rmdir "$LOCK" 2>/dev/null
  fi
  while ! mkdir "$LOCK" 2>/dev/null; do
    sleep 0.1; waited=$((waited+1))
    if [ "$waited" -ge $((max_wait * 10)) ]; then
      printf 'could not acquire profile lock\n' >&2; return 1
    fi
  done
}
release_lock() { rmdir "$LOCK" 2>/dev/null || true; }
trap release_lock EXIT

append_event() { printf '%s\n' "$1" >> "$EVENTS"; }

CMD="${1:-}"
case "$CMD" in
  --ask)
    SURFACE="${2:-}"
    QUESTION="${3:-}"
    OPTIONS_CSV="${4:-}"
    if [ -z "$SURFACE" ] || [ -z "$QUESTION" ] || [ -z "$OPTIONS_CSV" ]; then
      printf 'usage: --ask <surface> "question" "opt1,opt2,opt3"\n' >&2; exit 2
    fi

    acquire_lock || exit 1
    ensure_profile

    PROMPT_ID="p$(date +%s)-$$"
    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    SESSION_ID="${CLAUDE_SESSION_ID:-session-$$}"
    OPTIONS_JSON=$(printf '%s' "$OPTIONS_CSV" | jq -Rc 'split(",")')

    # Atomic profile update: read → add entry → write to tmp → rename
    TMP="$PROFILE.$$.tmp"
    jq --arg pid "$PROMPT_ID" --arg surface "$SURFACE" --arg q "$QUESTION" \
       --argjson opts "$OPTIONS_JSON" --arg asked "$TS" \
       '.unresolved_feedback += [{prompt_id: $pid, surface: $surface, question: $q,
         options: $opts, asked_at: $asked}]' "$PROFILE" > "$TMP" || { rm -f "$TMP"; exit 1; }
    mv -f "$TMP" "$PROFILE"

    EVENT=$(jq -cn \
      --arg v "1.0" --arg ts "$TS" --arg cid "$CLIENT_ID" --arg sid "$SESSION_ID" \
      --arg pid "$PROMPT_ID" --arg surface "$SURFACE" --arg q "$QUESTION" \
      --argjson opts "$OPTIONS_JSON" \
      '{v:$v, ts:$ts, client_id:$cid, session_id:$sid, turn_id:0, type:"feedback.prompted",
        payload:{prompt_id:$pid, decision_surface:$surface, question:$q, options:$opts}}')
    append_event "$EVENT"

    printf 'prompt %s queued: "%s" options=[%s]\n' "$PROMPT_ID" "$QUESTION" "$OPTIONS_CSV"
    ;;

  --list)
    ensure_profile
    COUNT=$(jq '.unresolved_feedback | length' "$PROFILE")
    if [ "$COUNT" = "0" ]; then
      echo "No unresolved feedback prompts."
    else
      printf '\n── Unresolved feedback (%s pending) ─────────────────\n\n' "$COUNT"
      jq -r '.unresolved_feedback[] |
        "  [\(.prompt_id)] surface=\(.surface)\n     Q: \(.question)\n     Options: \(.options | join(", "))\n     Asked: \(.asked_at)\n"' "$PROFILE"
      echo "  Answer with: --answer <prompt_id> <option>"
    fi
    ;;

  --answer)
    PID="${2:-}"
    ANSWER="${3:-}"
    if [ -z "$PID" ] || [ -z "$ANSWER" ]; then
      printf 'usage: --answer <prompt_id> <option>\n' >&2; exit 2
    fi

    acquire_lock || exit 1
    ensure_profile

    FOUND=$(jq -c --arg pid "$PID" '.unresolved_feedback[] | select(.prompt_id == $pid)' "$PROFILE")
    if [ -z "$FOUND" ]; then
      printf 'no pending prompt with id %s\n' "$PID" >&2; exit 1
    fi

    VALID=$(printf '%s' "$FOUND" | jq -r --arg a "$ANSWER" '.options | any(. == $a)')
    if [ "$VALID" != "true" ]; then
      printf 'warning: "%s" not in declared options (%s) — recording anyway\n' \
        "$ANSWER" "$(printf '%s' "$FOUND" | jq -r '.options | join(",")')" >&2
    fi

    # Remove from queue
    TMP="$PROFILE.$$.tmp"
    jq --arg pid "$PID" '.unresolved_feedback |= map(select(.prompt_id != $pid))' "$PROFILE" > "$TMP" || { rm -f "$TMP"; exit 1; }
    mv -f "$TMP" "$PROFILE"

    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    SESSION_ID="${CLAUDE_SESSION_ID:-session-$$}"
    SURFACE=$(printf '%s' "$FOUND" | jq -r '.surface')
    OPTIONS=$(printf '%s' "$FOUND" | jq -c '.options')
    ASKED_AT=$(printf '%s' "$FOUND" | jq -r '.asked_at')

    EVENT=$(jq -cn \
      --arg v "1.0" --arg ts "$TS" --arg cid "$CLIENT_ID" --arg sid "$SESSION_ID" \
      --arg pid "$PID" --arg surface "$SURFACE" --argjson opts "$OPTIONS" \
      --arg a "$ANSWER" --arg asked "$ASKED_AT" \
      '{v:$v, ts:$ts, client_id:$cid, session_id:$sid, turn_id:0, type:"feedback.captured",
        payload:{prompt_id:$pid, decision_surface:$surface, options:$opts, answer:$a, asked_at:$asked}}')
    append_event "$EVENT"

    printf 'answer recorded: %s → %s\n' "$PID" "$ANSWER"
    ;;

  --profile)
    ensure_profile
    jq . "$PROFILE"
    ;;

  -h|--help|"")
    sed -n '/^# USAGE/,/^# Writes/p' "$0" | sed 's/^# //; s/^#$//'
    ;;

  *)
    printf 'unknown subcommand: %s (try --help)\n' "$CMD" >&2; exit 2
    ;;
esac

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (D30a)
#
# ### 1. Measurement mechanism
# Count of unresolved_feedback entries; feedback.prompted vs feedback.captured
# event ratio (answer rate). Target: >70% within 7-day window per spec §17.
#
# ### 2. Adoption mechanism
# Promoted with P5 to sutra/marketplace/plugin/commands/. T1 opt-in.
#
# ### 3. Monitoring / escalation
# profile.json schema-validation failure = immediate patch per D11.
#
# ### 4. Iteration trigger
# Answer rate <50% over 14 days → surface-design revision.
#
# ### 5. DRI
# Sutra-OS owner.
#
# ### 6. Decommission criteria
# Deleted from holding 30d after plugin-side promotion at P5.
# ═══════════════════════════════════════════════════════════════════════════
