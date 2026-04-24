#!/usr/bin/env bash
#
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/commands/assistant-explain (slash cmd at P5)
#   Acceptance (P3): renders last turn + --turn N + --last K; terse-mechanical
#     narrative per spec §13 fidelity caveat (no causal reconstruction; S3 adds that).
#
# Direction: D1 (simplicity for founder confidence), D29 (speed)
# Spec: holding/research/2026-04-24-assistant-layer-design.md §13, §17
#
# PURPOSE
# Reads events.jsonl for turn.observed / log.rewound events and renders a
# human-readable narrative. S1 fidelity: the "what" is faithful (aggregated
# over evidence_refs source ranges); the "why" is mechanical ("DEPTH 5
# because D27 path") — not causal. Causal narrative ships in S3.
#
# USAGE
#   bash holding/scripts/assistant-explain.sh            # last turn
#   bash holding/scripts/assistant-explain.sh --turn N   # specific turn_id
#   bash holding/scripts/assistant-explain.sh --last K   # last K turns table
#
# Outputs to stdout. Read-only — no file writes.

set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  printf 'assistant-explain: jq is required; not found in PATH\n' >&2
  exit 1
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CLIENT_ID="${SUTRA_CLIENT_ID:-holding}"
STATE_DIR="${SUTRA_ASSISTANT_STATE_DIR:-$REPO_ROOT/holding/state/assistants/$CLIENT_ID}"
HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/holding/hooks/hook-log.jsonl}"
EVENTS="$STATE_DIR/events.jsonl"

MODE="last"
TURN_ARG=""
COUNT_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --turn)
      MODE="turn"
      TURN_ARG="${2:-}"
      shift 2
      ;;
    --last)
      MODE="last_n"
      COUNT_ARG="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '/^# USAGE/,/^# Outputs/p' "$0" | sed 's/^# //; s/^#$//'
      exit 0
      ;;
    *)
      printf 'unknown arg: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$EVENTS" ] || [ ! -s "$EVENTS" ]; then
  printf 'No events yet. Expected: %s\n' "$EVENTS" >&2
  printf '(The observer hook needs to fire at least once. See: assistant-observer.sh)\n' >&2
  exit 1
fi

classify_hook_row() {
  local row="$1"
  printf '%s' "$row" | jq -r '
    if .hook then .hook
    elif .event then .event
    elif .name then .name
    elif .tool_name then "tool:" + .tool_name
    else "unknown"
    end' 2>/dev/null || echo "unknown"
}

render_event() {
  local event="$1"
  local typ ts tid sid hc src from to

  typ=$(printf '%s' "$event" | jq -r '.type // "unknown"')
  ts=$(printf '%s' "$event" | jq -r '.ts // "unknown"')
  tid=$(printf '%s' "$event" | jq -r '.turn_id // "?"')
  sid=$(printf '%s' "$event" | jq -r '.session_id // "?"')

  case "$typ" in
    turn.observed)
      hc=$(printf '%s' "$event" | jq -r '.payload.hook_count // 0')
      src=$(printf '%s' "$event" | jq -r '.payload.evidence_refs[0].source // ""')
      from=$(printf '%s' "$event" | jq -r '.payload.evidence_refs[0].lines[0] // 0')
      to=$(printf '%s' "$event" | jq -r '.payload.evidence_refs[0].lines[1] // 0')

      printf '\n── Turn #%s  (%s) ────────────────────────\n\n' "$tid" "$ts"
      printf '  Session     : %s\n' "$sid"
      printf '  Hook count  : %s  (evidence: %s lines %s-%s)\n' "$hc" "$src" "$from" "$to"

      # Resolve the evidence source to an actual readable path.
      # Codex P3 round-1 blocker: the renderer MUST read from the event's
      # own source, not a hardcoded $HOOK_LOG — otherwise label and data
      # can diverge.
      if [ -n "$src" ]; then
        case "$src" in
          /*) resolved_src="$src" ;;            # absolute
          *)  resolved_src="$REPO_ROOT/$src" ;; # repo-relative
        esac
      else
        resolved_src=""
      fi

      if [ -n "$resolved_src" ] && [ -f "$resolved_src" ] && [ "$from" -gt 0 ] && [ "$to" -ge "$from" ]; then
        local counts
        counts=$(sed -n "${from},${to}p" "$resolved_src" 2>/dev/null | while IFS= read -r row; do
          [ -z "$row" ] && continue
          classify_hook_row "$row"
        done | sort | uniq -c | sort -rn | head -10)

        if [ -n "$counts" ]; then
          printf '\n  What Sutra did (top hook categories):\n'
          printf '%s\n' "$counts" | awk '{printf "    %5d  %s\n", $1, $2}'
        fi
      else
        printf '\n  (evidence source %s unreadable — skipping category breakdown)\n' "${src:-unset}"
      fi

      printf '\n  Why (terse-mechanical):\n'
      printf '    — S1 renders from aggregated counts; causal narrative lands in S3.\n'
      printf '    — See evidence_refs above to inspect raw rows yourself.\n'
      ;;

    log.rewound)
      local pc ct reason
      pc=$(printf '%s' "$event" | jq -r '.payload.prior_cursor // "?"')
      ct=$(printf '%s' "$event" | jq -r '.payload.current_total_lines // "?"')
      reason=$(printf '%s' "$event" | jq -r '.payload.reason // "?"')
      printf '\n── Turn #%s  (%s)  LOG-REWOUND ────────────\n\n' "$tid" "$ts"
      printf '  Session        : %s\n' "$sid"
      printf '  Prior cursor   : %s\n' "$pc"
      printf '  Current lines  : %s\n' "$ct"
      printf '  Reason         : %s\n' "$reason"
      ;;

    *)
      printf '\n── Turn #%s  (%s)  type=%s ─────────────\n' "$tid" "$ts" "$typ"
      printf '  (renderer unknown for this event type — raw follows)\n'
      printf '  %s\n' "$event"
      ;;
  esac
}

case "$MODE" in
  last)
    event=$(tail -1 "$EVENTS")
    render_event "$event"
    ;;

  turn)
    if [ -z "$TURN_ARG" ]; then
      printf 'assistant-explain: --turn requires a number\n' >&2
      exit 2
    fi
    event=$(jq -c --argjson tid "$TURN_ARG" 'select(.turn_id == $tid)' "$EVENTS" 2>/dev/null | head -1)
    if [ -z "$event" ]; then
      printf 'No event with turn_id=%s in %s\n' "$TURN_ARG" "$EVENTS" >&2
      exit 1
    fi
    render_event "$event"
    ;;

  last_n)
    if [ -z "$COUNT_ARG" ]; then
      printf 'assistant-explain: --last requires a number\n' >&2
      exit 2
    fi
    case "$COUNT_ARG" in ''|*[!0-9]*)
      printf 'assistant-explain: --last expects a positive integer, got: %s\n' "$COUNT_ARG" >&2
      exit 2
      ;;
    esac
    printf '\n── Last %s turns ─────────────────────────\n' "$COUNT_ARG"
    printf '  %-8s  %-20s  %-15s  %s\n' "turn_id" "ts" "type" "payload-summary"
    printf '  %s\n' "$(printf '%.0s-' $(seq 1 78))"
    tail -"$COUNT_ARG" "$EVENTS" | while IFS= read -r event; do
      tid=$(printf '%s' "$event" | jq -r '.turn_id // "?"')
      ts=$(printf '%s' "$event" | jq -r '.ts // "?"' | cut -c1-19)
      typ=$(printf '%s' "$event" | jq -r '.type // "?"')
      case "$typ" in
        turn.observed)
          hc=$(printf '%s' "$event" | jq -r '.payload.hook_count // 0')
          summary="hooks=$hc"
          ;;
        log.rewound)
          pc=$(printf '%s' "$event" | jq -r '.payload.prior_cursor // "?"')
          summary="rewind (prior=$pc)"
          ;;
        *)
          summary="—"
          ;;
      esac
      printf '  %-8s  %-20s  %-15s  %s\n' "$tid" "$ts" "$typ" "$summary"
    done
    printf '\n  For details on a specific turn: --turn <id>\n'
    ;;
esac

exit 0
