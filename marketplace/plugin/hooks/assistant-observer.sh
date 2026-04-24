#!/usr/bin/env bash
#
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/hooks/assistant-observer.sh
#   Promotion by: 2026-05-24 (30d L1 stability + P5 plugin promotion)
#   Acceptance (P2): exactly-once event emission per hook-log range;
#     events.jsonl is the SOLE source of truth (cursor derived from tip);
#     stale lock auto-recovered; rewind detected + recorded; P1 tests green.
#   Stale disposition: delete holding copy 30d after plugin-side promotion
#
# Direction: D10 (test in prod), D11 (process not instance), D29 (speed)
# Spec: holding/research/2026-04-24-assistant-layer-design.md §4, §6, §7
# Codex rounds on this file:
#   R1 REJECT  — 5 issues: race, append-failure-advances-cursor, rewind-wedge,
#                silent-mkdir-fail, unsafe-json-fallback.
#   R2 MODIFY  — 1 blocker (append-succeeds/cursor-fails → duplicate on retry)
#                + stale-lock + T6 jq-required. THIS REVISION:
#     • Cursor derived from events.jsonl tip (no separate cursor file;
#       append IS commit — impossible for cursor to drift from events).
#     • Stale-lock auto-recovery when lock dir age > 10s (crash recovery).
#     • Tests updated to require jq (skip removed).
#
# EVENT SHAPES (v1.0 envelope — spec §7 starting shape):
#   turn.observed: {v, ts, client_id, session_id, turn_id, type, payload:
#     {hook_count, evidence_refs: [{source, lines: [from, to]}]}}
#   log.rewound:   {v, ts, client_id, session_id, turn_id, type, payload:
#     {prior_cursor, current_total_lines, reason}}
#
# client_id defaults to "holding" (T1 Asawa per spec §9 + D34); T2/T3/T4
# overrides set $SUTRA_CLIENT_ID externally.
#
# TEST MODE: $ASSISTANT_OBSERVER_PROBE_FILE set → P1-probe behavior only.

set -uo pipefail

# ── P1 back-compat: probe file mode ─────────────────────────────────────
if [ -n "${ASSISTANT_OBSERVER_PROBE_FILE:-}" ]; then
  printf 'observer-called ts=%s pid=%s\n' "$(date +%s)" "$$" \
    >> "$ASSISTANT_OBSERVER_PROBE_FILE" 2>/dev/null || true
  exit 0
fi

# ── jq required ─────────────────────────────────────────────────────────
if ! command -v jq >/dev/null 2>&1; then
  printf 'assistant-observer: jq is required; not found in PATH\n' >&2
  exit 1
fi

# ── Paths (overridable for tests) ───────────────────────────────────────
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
[ -z "$REPO_ROOT" ] && exit 0

CLIENT_ID="${SUTRA_CLIENT_ID:-holding}"
STATE_DIR="${SUTRA_ASSISTANT_STATE_DIR:-$REPO_ROOT/holding/state/assistants/$CLIENT_ID}"
HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/${CLAUDE_PROJECT_DIR}/holding/hooks/hook-log.jsonl}"

EVENTS="$STATE_DIR/events.jsonl"
LOCK="$STATE_DIR/observer.lock"
STALE_LOCK_S=10

if ! mkdir -p "$STATE_DIR" 2>/dev/null; then
  printf 'assistant-observer: cannot create state dir: %s\n' "$STATE_DIR" >&2
  exit 1
fi

[ -f "$HOOK_LOG" ] || exit 0

# ── Timestamp (fail-fast) ───────────────────────────────────────────────
if ! TS=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null); then
  printf 'assistant-observer: cannot produce timestamp\n' >&2
  exit 1
fi

SESSION_ID="${CLAUDE_SESSION_ID:-session-$$}"

# ── Stale-lock check: if lock dir older than STALE_LOCK_S, force-remove ─
if [ -d "$LOCK" ]; then
  # Use find's -mmin: convert seconds to minutes (ceil). For 10s → use mtime
  # comparison via stat where available; fall back to find -mmin.
  LOCK_AGE=""
  if LOCK_MTIME=$(stat -f %m "$LOCK" 2>/dev/null); then
    LOCK_AGE=$(( $(date +%s) - LOCK_MTIME ))
  elif LOCK_MTIME=$(stat -c %Y "$LOCK" 2>/dev/null); then
    LOCK_AGE=$(( $(date +%s) - LOCK_MTIME ))
  fi
  if [ -n "$LOCK_AGE" ] && [ "$LOCK_AGE" -gt "$STALE_LOCK_S" ]; then
    rmdir "$LOCK" 2>/dev/null || true
  fi
fi

# ── Acquire mutex (mkdir-based; waits up to 3s, then fails loudly) ──────
acquire_lock() {
  local max_wait_s=3 waited=0
  while ! mkdir "$LOCK" 2>/dev/null; do
    sleep 0.1
    waited=$((waited + 1))
    if [ "$waited" -ge $((max_wait_s * 10)) ]; then
      printf 'assistant-observer: could not acquire lock after %ss\n' "$max_wait_s" >&2
      return 1
    fi
  done
  return 0
}
release_lock() { rmdir "$LOCK" 2>/dev/null || true; }
trap release_lock EXIT

acquire_lock || exit 1

# ── Cursor derived from events.jsonl tip (sole source of truth) ─────────
# Walk events.jsonl backward for the latest turn.observed; its
# payload.evidence_refs[0].lines[1] is the cursor. If no such event exists
# (fresh install OR all prior events were log.rewound), cursor = 0.
LAST_LINE=0
TURN_ID=0
if [ -f "$EVENTS" ] && [ -s "$EVENTS" ]; then
  TURN_ID=$(wc -l < "$EVENTS" 2>/dev/null | tr -d ' ')
  case "$TURN_ID" in ''|*[!0-9]*) TURN_ID=0 ;; esac
  # Read file in reverse; pick first turn.observed row.
  LAST_LINE=$(tail -r "$EVENTS" 2>/dev/null | awk '
    {
      if (index($0, "\"type\":\"turn.observed\"") > 0) {
        print $0; exit
      }
    }' | jq -r 'try .payload.evidence_refs[0].lines[1] // 0' 2>/dev/null || echo 0)
  case "$LAST_LINE" in ''|*[!0-9]*) LAST_LINE=0 ;; esac
fi

# ── Count hook-log lines ────────────────────────────────────────────────
TOTAL_LINES=$(wc -l < "$HOOK_LOG" 2>/dev/null | tr -d ' ')
case "$TOTAL_LINES" in ''|*[!0-9]*) TOTAL_LINES=0 ;; esac

# ── Rewind detection: cursor > total_lines → log-was-rotated ────────────
if [ "$LAST_LINE" -gt "$TOTAL_LINES" ]; then
  TURN_ID=$((TURN_ID + 1))
  REWIND_EVENT=$(jq -cn \
    --arg v "1.0" --arg ts "$TS" --arg cid "$CLIENT_ID" \
    --arg sid "$SESSION_ID" --argjson tid "$TURN_ID" \
    --argjson pc "$LAST_LINE" --argjson ct "$TOTAL_LINES" \
    '{v:$v, ts:$ts, client_id:$cid, session_id:$sid, turn_id:$tid,
      type:"log.rewound",
      payload:{prior_cursor:$pc, current_total_lines:$ct, reason:"hook-log-rewind-detected"}}')
  if ! printf '%s\n' "$REWIND_EVENT" >> "$EVENTS"; then
    printf 'assistant-observer: failed to append log.rewound event\n' >&2
    exit 1
  fi
  # Rewind event IS the new cursor baseline (it supersedes prior turn.observed).
  # Next iteration derives cursor = 0 naturally since rewind is not turn.observed.
  LAST_LINE=0
fi

# ── Nothing new → no-op ─────────────────────────────────────────────────
if [ "$TOTAL_LINES" -le "$LAST_LINE" ]; then
  exit 0
fi

FROM_LINE=$((LAST_LINE + 1))
HOOK_COUNT=$((TOTAL_LINES - LAST_LINE))
TURN_ID=$((TURN_ID + 1))

# ── Build turn.observed event (jq handles all escaping) ─────────────────
EVENT=$(jq -cn \
  --arg v "1.0" --arg ts "$TS" --arg cid "$CLIENT_ID" \
  --arg sid "$SESSION_ID" --argjson tid "$TURN_ID" \
  --argjson hc "$HOOK_COUNT" --arg src "${CLAUDE_PROJECT_DIR}/holding/hooks/hook-log.jsonl" \
  --argjson f "$FROM_LINE" --argjson t "$TOTAL_LINES" \
  '{v:$v, ts:$ts, client_id:$cid, session_id:$sid, turn_id:$tid, type:"turn.observed",
    payload:{hook_count:$hc, evidence_refs:[{source:$src, lines:[$f,$t]}]}}')

# ── Append = commit (append is atomic; no separate cursor write) ────────
if ! printf '%s\n' "$EVENT" >> "$EVENTS"; then
  printf 'assistant-observer: failed to append event to %s\n' "$EVENTS" >&2
  exit 1
fi

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (D30a / PROTO-000 6-part rule)
#
# ### 1. Measurement mechanism
# events.jsonl line count delta per observer invocation = 1 (growth), 0
# (no-op), 1 (rewind — as log.rewound). Cursor derived from tip; no drift
# possible since there's only one source of truth. Validated by
# test-assistant-observer.sh.
#
# ### 2. Adoption mechanism
# L1 in asawa-holding (P2-P4 dogfood path = holding/state/assistants/).
# Promotes to plugin at P5 → every client on install/update. P5 also moves
# state dir to sutra/os/state/assistants/ (spec §14).
#
# ### 3. Monitoring / escalation
# Any stderr output = bug (captured in hook-log.jsonl stderr). Analytics
# dept 24h cadence. events.jsonl schema-validate failure in production =
# immediate patch per D11.
#
# ### 4. Iteration trigger
# - /assistant explain (P3) surfaces fidelity gaps → richer payload P2.1
# - Schema v1.1 → migrate events + update readers
# - State dir move (P5) → paths shift; tested in P5 promotion
# - Body change > 20 lines → re-run codex
#
# ### 5. DRI
# Sutra-OS owner.
#
# ### 6. Decommission criteria
# Deleted from holding 30d after plugin-side promotion at P5.
# ═══════════════════════════════════════════════════════════════════════════
