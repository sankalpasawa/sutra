#!/bin/bash
# flow-gate.sh -- the Flow enforcement hook (ADR-026 + ADR-027; flow.html 0/G/H)
#
# Canon:   sutra/os/decisions/ADR-026-the-flow.md, ADR-027-generic-engine.md
# Skill:   sutra/marketplace/plugin/skills/flow/SKILL.md (core:flow)
# Event:   PreToolUse on Edit|Write + Task/Agent dispatch (BACKSTOP only; Flow
#          FIRES at UserPromptSubmit via per-turn-discipline-prompt.sh, D61)
# Enforcement: HARD (v2.39.12, fleet-wide; founder direction 2026-06-14). EXITS 2
#              -- blocks substantive CONSTRUCT work (Edit/Write to a non-whitelisted
#              path, or Task/Agent dispatch) that skipped classify+resolve. Mirrors
#              input-classification-gate.sh (input-routed) + depth-marker-pretool.sh
#              (depth-registered). Escape hatches preserve fleet survivability:
#              FLOW_ACK=1 (audit-logged override), FLOW_DISABLED=1, ~/.flow-disabled.
#
# What it checks: an Edit/Write to a non-whitelisted path means substantive
#   construct work. The Flow spine wants that work to have been CLASSIFIED
#   (input -> TYPE via Input Routing + H-Sutra 9-cell) and to have RESOLVED a
#   workflow type (FOLLOW a matching child/platform skill, or CONSTRUCT new
#   steps) BEFORE the inner engine shapes each Work-Atom. If either marker is
#   missing, nudge -- do not block.
#
# Composes with (does NOT duplicate) the existing Sutra discipline hooks:
#   core:input-routing  -> .claude/input-routed
#   core:depth-estimation -> .claude/depth-registered
#   core:blueprint      -> .claude/blueprint-registered
# This hook adds ONLY the Flow-spine markers (classify + resolve); it never
# re-checks routing/depth/blueprint state, so it cannot contradict them.
#
# Markers (written by the Flow skills as the spine is walked):
#   .claude/flow-classified      TYPE=<type> CELL=<9cell> TS=<unix>
#   .claude/flow-type-resolved   RESOLUTION=FOLLOW:<skill>|CONSTRUCT SCOPE=... TS=...
#   (.claude/flow-inner, .claude/flow-closed also exist; this hook gates on the
#    first two -- classify + resolve must precede CONSTRUCT.)
#
# Kill-switch (2-level):
#   - FLOW_DISABLED=1                (per-shell env)
#   - $HOME/.flow-disabled           (per-machine fs)
# Override:
#   - FLOW_ACK=1                     (per-call; logs to .enforcement/flow-gate-ledger.jsonl)
#
# Wrapping: the integrator registers this in hooks.json as
#   ${CLAUDE_PLUGIN_ROOT}/hooks/lib/sutra-stderr-capture.sh ${CLAUDE_PLUGIN_ROOT}/hooks/flow-gate.sh
# so this hook only needs to: read stdin JSON, write advisory to stderr, exit 0.

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

# -- Kill-switches (2-level: env + fs; either one bypasses) -----------------
[ -n "${FLOW_DISABLED:-}" ] && exit 0
[ -f "$HOME/.flow-disabled" ] && exit 0

# -- Override path (FLOW_ACK=1 -> audit-log + bypass) -----------------------
if [ "${FLOW_ACK:-0}" = "1" ]; then
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  REASON=$(printf '%s' "${FLOW_ACK_REASON:-no-reason}" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  printf '{"ts":"%s","event":"flow-override","reason":"%s","session":"%s"}\n' \
    "$TS" "$REASON" "${CLAUDE_SESSION_ID:-unknown}" \
    >> "$REPO_ROOT/.enforcement/flow-gate-ledger.jsonl" 2>/dev/null
  exit 0
fi

# -- Parse target file_path from PreToolUse stdin JSON ----------------------
PAYLOAD=$(cat 2>/dev/null || true)

# -- Session-scoped marker resolution (2026-07-27) --------------------------
# Markers used to be single-slot per repo. Two Claude Code sessions in one repo
# overwrote and deleted each other's markers — observed live 2026-07-27, where
# a foreign session's reset wiped this session's marker mid-turn and produced a
# spurious block. Prefer the session-scoped marker (written deterministically
# by per-turn-discipline-prompt.sh), then fall back to the legacy single-slot
# path so model-written markers and un-upgraded installs keep working.
SID=$(printf '%s' "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)
SID=$(printf '%s' "$SID" | tr -cd 'a-zA-Z0-9_-' | head -c 64)
[ -z "$SID" ] && SID="${CLAUDE_SESSION_ID:-}"

# Scheme A (marker-lib) is the single marker authority as of 2026-07-27; the flat
# `.claude/<name>-<sid>` suffix scheme is DELETED. sutra_marker_has reads the
# session dir and, transitionally, adopts a legacy global marker written by a
# not-yet-migrated writer (bounded: reset clears both every turn).
# Sourced defensively (DeepSeek consult 2026-07-27, finding 4): this script runs
# under `set -u`. An unbound var or a stray RETURN trap inside the sourced lib would
# abort THIS hook, and an aborted PreToolUse hook blocks the user's tool call. A
# governance gate may block on missing discipline; it must never block because its
# own infrastructure errored. Degrade to the legacy path instead.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$PAYLOAD" || true
  set -u
fi
flow_marker_exists() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    sutra_marker_has "$1"; return $?
  fi
  # lib missing: legacy global only (fail-open on infrastructure, not on discipline)
  [ -f "$REPO_ROOT/.claude/$1" ]
}

FILE_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="${TOOL_INPUT_file_path:-}"
# -- Widen (v2.39.11): also catch construct-via-delegation (Task/Agent dispatch),
#    not just Edit/Write. Gap fixed: a workflow/subagent dispatch had skipped the gate.
TOOL_NAME=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null)
fi
# flow-gate is a BACKSTOP for construct/dispatch mutations, NOT the firing
# mechanism. Flow FIRES on every input at UserPromptSubmit
# (per-turn-discipline-prompt.sh emits the full-spine activation, D61) — the
# same place Input Routing fires. This hook only catches the case where a
# mutation/dispatch slipped through without classify. Do NOT gate WebSearch/
# WebFetch/Bash here: gating is not how Flow fires (founder D61, 2026-06-14),
# and gating Bash would deadlock the marker bootstrap.
if [ "$TOOL_NAME" = "Task" ] || [ "$TOOL_NAME" = "Agent" ]; then
  if ! flow_marker_exists flow-classified; then
    {
      printf '\nFLOW-GATE (HARD): dispatching work (%s) requires classify first.\n' "$TOOL_NAME"
      printf '  Run core:flow to classify the input + resolve a workflow type,\n'
      printf '  then re-attempt the dispatch.\n'
      printf "  Override: FLOW_ACK=1 FLOW_ACK_REASON='<why>' <tool>\n\n"
    } >&2
    mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
    printf '{"ts":"%s","event":"flow-gate-block","tool":"%s","reason":"dispatch-without-classify","mode":"hard"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TOOL_NAME" >> "$REPO_ROOT/.enforcement/flow-gate.jsonl" 2>/dev/null
    exit 2
  fi
  exit 0
fi
[ -z "$FILE_PATH" ] && exit 0
REL_PATH="${FILE_PATH#"$REPO_ROOT"/}"

# -- Whitelist (skip the nudge regardless of marker state) ------------------
# Read-only / docs context, ephemeral state, ledgers, locks, and memory files
# are NOT substantive construct work -- gating them is noise.
case "$REL_PATH" in
  .claude/*|.enforcement/*|.analytics/*)            exit 0 ;;
  holding/checkpoints/*|holding/state/*)            exit 0 ;;
  holding/TODO.md|*/TODO.md|*/BACKLOG.md)           exit 0 ;;
  */CHANGELOG.md|*/MEMORY.md|MEMORY.md)             exit 0 ;;
  *.lock|*.log|*.jsonl)                             exit 0 ;;
  *.md.bak|*~)                                      exit 0 ;;
esac

# -- Marker check (classify + resolve must precede CONSTRUCT) ----------------
if flow_marker_exists flow-classified && flow_marker_exists flow-type-resolved; then
  # Spine walked: classified + a workflow type resolved. Let the construct
  # proceed. The inner engine + per-Work-Atom verify carry the rest.
  #
  # PASS LOGGING (2026-07-27): this branch used to `exit 0` silently, so the
  # ledger recorded ONLY failures. With no denominator the fire-rate was
  # unmeasurable — 60 recorded blocks could have been 60% or 0.6% of turns,
  # and there was no way to tell a genuine miss from the cross-session marker
  # race. Log the pass so the rate is computable and any future tuning has a
  # denominator. Fail-open: logging never blocks.
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  SAFE_PASS_REL=$(printf '%s' "$REL_PATH" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
  printf '{"ts":"%s","event":"flow-gate-pass","path":"%s","session":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SAFE_PASS_REL" "${SID:-unknown}" \
    >> "$REPO_ROOT/.enforcement/flow-gate.jsonl" 2>/dev/null
  exit 0
fi

# -- Markers missing on a non-whitelisted path: HARD block + log -----------
MISSING=""
flow_marker_exists flow-classified    || MISSING="${MISSING}classify "
flow_marker_exists flow-type-resolved || MISSING="${MISSING}resolve "
MISSING="${MISSING% }"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SAFE_REL=$(printf '%s' "$REL_PATH" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
printf '{"ts":"%s","event":"flow-gate-block","path":"%s","missing":"%s","mode":"hard","session":"%s"}\n' \
  "$TS" "$SAFE_REL" "$MISSING" "${CLAUDE_SESSION_ID:-unknown}" \
  >> "$REPO_ROOT/.enforcement/flow-gate.jsonl" 2>/dev/null

{
  echo "FLOW-GATE (HARD): construct work requires classify + resolve first."
  echo "  File: $REL_PATH"
  echo "  Missing markers: ${MISSING}"
  echo "  Run core:flow to classify the input + resolve a workflow type,"
  echo "  then re-attempt the Edit/Write."
  echo "  Override: FLOW_ACK=1 FLOW_ACK_REASON='<why>' <tool>"
} >&2

# HARD (v2.39.12, fleet-wide per founder direction 2026-06-14): block construct
# work that skipped classify+resolve. core:flow writes its markers via Bash,
# which is NOT gated here (matcher = Edit|Write + Task), so no bootstrap deadlock.
exit 2

# ===========================================================================
# HARD ACTIVATION RECORD (v2.39.12, 2026-06-14)
# ===========================================================================
# The live paths above now EXIT 2 (HARD), fleet-wide, per founder direction
# 2026-06-14 ("hard implementation of Flow, the way Input Routing is" +
# "fleet-wide adoption of the hard gate"). Chosen over the safer company-profile
# -gated sketch by explicit founder decision, with the fleet-disruption risk
# (core:flow is heavier than a routing block) labeled and accepted.
#
# Registration: flow-gate.sh is registered RAW in hooks.json (PreToolUse
# Edit|Write group + Task group) -- NOT wrapped in sutra-stderr-capture.sh --
# so exit 2 propagates and blocks the tool call, same as depth-marker-pretool.sh
# and blueprint-check.sh. (An earlier version of this file warned about a capture
# wrapper swallowing the exit code; that warning was STALE -- the wrapper is not
# applied to this hook. Verified at hooks.json Edit|Write + Task registrations.)
#
# Fleet survivability / rollback:
#   - Per-call override:  FLOW_ACK=1 FLOW_ACK_REASON='<why>' <tool>  (audit-logged)
#   - Per-shell kill:     FLOW_DISABLED=1
#   - Per-machine kill:   touch ~/.flow-disabled
#   - Full rollback:      revert this single commit.
#
# No bootstrap deadlock: core:flow writes its markers (.claude/flow-classified,
# flow-type-resolved) via Bash, and this gate matches only Edit|Write + Task --
# Bash escapes it, so the skill can always write the markers that unlock the gate.
# ===========================================================================