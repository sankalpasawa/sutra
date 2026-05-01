#!/usr/bin/env bash
# per-turn-discipline-prompt.sh — D40 G1 governance-parity hook
#
# Event: UserPromptSubmit
# Behavior: emit a soft hint reminding the model to emit Input Routing + Depth
#           on every turn (including pure-question turns where Edit/Write hooks
#           don't fire).
#
# Per codex CHANGES-REQUIRED fold (v1.0.1, 2026-04-30): hook now CONSUMES
# sutra-defaults.json at runtime via jq, instead of hardcoding reminder text.
# This makes sutra-defaults.json the actual canonical policy surface (D40 G6),
# not just documentation.
#
# Per codex caveat (D40 verdict): hook-injects-prompt is SOFT GUIDANCE ONLY.
# Failure modes: prompt dilution, collision, token bloat, cosmetic emission,
# subagent drift. Backed by deterministic Edit/Write hooks elsewhere.
#
# Kill-switches (any one disables):
#   ~/.sutra-defaults-disabled        (all D40 defaults)
#   ~/.per-turn-discipline-disabled   (this hook only)
#   SUTRA_DEFAULTS_DISABLED=1
#
# Fail-open: exit 0 always (never block the user prompt).

set -u

# Kill-switches
[ -f "$HOME/.sutra-defaults-disabled" ] && exit 0
[ -f "$HOME/.per-turn-discipline-disabled" ] && exit 0
[ -n "${SUTRA_DEFAULTS_DISABLED:-}" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

# Fresh-install gate: stay silent until the user has run /core:start (which
# writes .claude/sutra-project.json with their profile). Before that, the
# reminder is non-actionable noise — they don't yet know what Input Routing /
# Depth blocks ARE. After /core:start, the doctrine doc is on their disk and
# the reminder becomes a useful nudge. Kill-switch: SUTRA_DISCIPLINE_PRE_ACTIVATION=1.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$REPO_ROOT/.claude/sutra-project.json" ]; then
  exit 0
fi

DEFAULTS_DIR="${CLAUDE_PLUGIN_ROOT:-$REPO_ROOT/sutra/marketplace/plugin}"
DEFAULTS_JSON="$DEFAULTS_DIR/sutra-defaults.json"

# Fallback path: json or jq missing → minimal reminder
if [ ! -r "$DEFAULTS_JSON" ] || ! command -v jq >/dev/null 2>&1; then
  printf '\n[Sutra defaults · D40] Per-turn discipline: emit Input Routing + Depth blocks. See SUTRA-DEFAULTS.md.\n  (sutra-defaults.json or jq unavailable — using fallback reminder)\n\n' >&2
  exit 0
fi

# Consume canonical surface (D40 G6 — single source of truth)
IR_FIELDS=$(jq -r '.per_turn_blocks.input_routing.fields | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
DEPTH_FIELDS=$(jq -r '.per_turn_blocks.depth_estimation.fields_pre | join(", ")' "$DEFAULTS_JSON" 2>/dev/null)
DEPTH_THRESHOLD=$(jq -r '.consult_policy.depth_threshold' "$DEFAULTS_JSON" 2>/dev/null)
CONSULT_TOOLS=$(jq -r '.consult_policy.applies_to_tools | join("/")' "$DEFAULTS_JSON" 2>/dev/null)
KILL_FILE=$(jq -r '.kill_switches.per_turn_discipline_prompt.file' "$DEFAULTS_JSON" 2>/dev/null)

# Emit derived reminder (changes if json changes)
{
  printf '\n[Sutra defaults · D40 v1.0.1] Per-turn discipline (sourced from sutra-defaults.json):\n'
  printf '  - Input Routing fields: %s\n' "${IR_FIELDS:-INPUT/TYPE/...}"
  printf '  - Depth + Estimation fields: %s\n' "${DEPTH_FIELDS:-TASK/DEPTH/...}"
  printf '  - Depth >= %s with %s planned: consult codex first (core:codex-sutra)\n' "${DEPTH_THRESHOLD:-3}" "${CONSULT_TOOLS:-Edit/Write/MultiEdit}"
  printf '  See %s/SUTRA-DEFAULTS.md (human) / sutra-defaults.json (machine)\n' "$DEFAULTS_DIR"
  printf '  Kill-switch: touch %s\n\n' "${KILL_FILE:-~/.per-turn-discipline-disabled}"
} >&2

# ──────────────────────────────────────────────────────────────────────────
# H-Sutra classification (folded 2026-05-01 per codex consult P2.7).
# Canonical channel: UserPromptSubmit stdin JSON {prompt: "..."} (codex P2 #4).
# Failures stay off stdout to avoid Claude-context pollution (codex P2 #5).
# Concurrency: mkdir-based advisory lock for shared-FS portability (codex P2 #6).
# Per [Never bypass governance]: every turn is logged; fail-open never silent
# (stderr diagnostic on infra failure).
# ──────────────────────────────────────────────────────────────────────────
HSUTRA_INPUT_JSON=""
if [ ! -t 0 ]; then
  HSUTRA_INPUT_JSON=$(cat 2>/dev/null || true)
fi
HSUTRA_PROMPT=""
if [ -n "$HSUTRA_INPUT_JSON" ]; then
  HSUTRA_PROMPT=$(printf '%s' "$HSUTRA_INPUT_JSON" | jq -r '.prompt // empty' 2>/dev/null || true)
fi
[ -z "$HSUTRA_PROMPT" ] && exit 0

HSUTRA_CLASSIFIER="$DEFAULTS_DIR/skills/human-sutra/scripts/classify.sh"
if [ ! -r "$HSUTRA_CLASSIFIER" ]; then
  printf '[h-sutra] classifier missing at %s — row skipped.\n' "$HSUTRA_CLASSIFIER" >&2
  exit 0
fi

# Self-derive IR_TYPE from prompt heuristics (no dependency on input-routing
# cache — codex P1 #1). classify.sh applies its own ADR-001 precedence after.
HSUTRA_LC=$(printf '%s' "$HSUTRA_PROMPT" | tr '[:upper:]' '[:lower:]')
HSUTRA_IR_TYPE="task"
case "$HSUTRA_LC" in
  *"?"*) HSUTRA_IR_TYPE="question" ;;
esac
if printf '%s' "$HSUTRA_LC" | grep -qE '\b(missed|wrong|broken|error|failed|didn.?t|wasn.?t|isn.?t|not yet)\b'; then
  HSUTRA_IR_TYPE="feedback"
fi
if printf '%s' "$HSUTRA_LC" | grep -qE '\b(should|must|always|never|going forward|from now on)\b'; then
  HSUTRA_IR_TYPE="direction"
fi

HSUTRA_JSON=$(IR_TYPE="$HSUTRA_IR_TYPE" bash "$HSUTRA_CLASSIFIER" "$HSUTRA_PROMPT" 2>/dev/null || true)
if [ -z "$HSUTRA_JSON" ]; then
  printf '[h-sutra] classifier returned empty; row skipped.\n' >&2
  exit 0
fi

# Log path: Asawa override > default. mkdir -p the parent on first append.
HSUTRA_LOG="$REPO_ROOT/.sutra/h-sutra.jsonl"
if [ -f "$REPO_ROOT/holding/state/interaction/log.jsonl" ]; then
  HSUTRA_LOG="$REPO_ROOT/holding/state/interaction/log.jsonl"
fi
mkdir -p "$(dirname "$HSUTRA_LOG")" 2>/dev/null || true

HSUTRA_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
HSUTRA_TURN_ID=$(printf '%s' "${HSUTRA_TS}|${HSUTRA_PROMPT}" | shasum -a 256 2>/dev/null | cut -c1-12)
HSUTRA_ROW=$(printf '%s' "$HSUTRA_JSON" | jq -c \
  --arg ts "$HSUTRA_TS" \
  --arg turn_id "$HSUTRA_TURN_ID" \
  --arg ir_type "$HSUTRA_IR_TYPE" \
  '{ts:$ts, turn_id:$turn_id, direction:.direction, verb:.verb, principal_act:.principal_act, mixed_acts:.mixed_acts, tense:.tense, timing:.timing, channel:.channel, reversibility:.reversibility, decision_risk:.decision_risk, stage_1_pass:(.stage_1_fail==false), stage_3_emission_type:.stage_3_emission_type, input_routing_type:$ir_type}' 2>/dev/null || true)
if [ -z "$HSUTRA_ROW" ]; then
  printf '[h-sutra] row build failed; skipped.\n' >&2
  exit 0
fi

# mkdir-based advisory lock (flock not always available on macOS).
HSUTRA_LOCK="$HSUTRA_LOG.lock"
HSUTRA_LOCKED=0
for _ in 1 2 3 4 5; do
  if mkdir "$HSUTRA_LOCK" 2>/dev/null; then HSUTRA_LOCKED=1; break; fi
  sleep 0.2 2>/dev/null || sleep 1
done
if [ "$HSUTRA_LOCKED" = "1" ]; then
  if ! tail -n 10 "$HSUTRA_LOG" 2>/dev/null | grep -qF "\"turn_id\":\"$HSUTRA_TURN_ID\""; then
    printf '%s\n' "$HSUTRA_ROW" >> "$HSUTRA_LOG"
  fi
  rmdir "$HSUTRA_LOCK" 2>/dev/null || true
else
  printf '[h-sutra] log lock contended; row %s skipped.\n' "$HSUTRA_TURN_ID" >&2
fi

exit 0
