#!/bin/bash
# flow-gate.sh -- the Flow enforcement hook (ADR-026 + ADR-027; flow.html 0/G/H)
#
# Canon:   sutra/os/decisions/ADR-026-the-flow.md, ADR-027-generic-engine.md
# Skill:   sutra/marketplace/plugin/skills/flow/SKILL.md (core:flow)
# Event:   PreToolUse on Edit|Write
# Enforcement: SOFT-FIRST -- v1 ALWAYS exits 0. Advisory nudge to stderr +
#              append to .enforcement/flow-gate.jsonl when substantive
#              CONSTRUCT work proceeds without the Flow markers. NEVER exits 2
#              in v1 (must not break any fleet client). A clearly-commented
#              HARD-PROMOTION block below shows the future company-profile path
#              -- it is intentionally NOT wired.
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
FILE_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="${TOOL_INPUT_file_path:-}"
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
CLASSIFIED="$REPO_ROOT/.claude/flow-classified"
RESOLVED="$REPO_ROOT/.claude/flow-type-resolved"

if [ -f "$CLASSIFIED" ] && [ -f "$RESOLVED" ]; then
  # Spine walked: classified + a workflow type resolved. Let the construct
  # proceed silently. The inner engine + per-Work-Atom verify carry the rest.
  exit 0
fi

# -- Markers missing on a non-whitelisted path: advisory nudge + log --------
MISSING=""
[ -f "$CLASSIFIED" ] || MISSING="${MISSING}classify "
[ -f "$RESOLVED" ]   || MISSING="${MISSING}resolve "
MISSING="${MISSING% }"

echo "FLOW: classify + resolve a workflow type before constructing -- run core:flow (missing: ${MISSING})" >&2

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SAFE_REL=$(printf '%s' "$REL_PATH" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
printf '{"ts":"%s","event":"flow-gate-nudge","path":"%s","missing":"%s","mode":"soft","session":"%s"}\n' \
  "$TS" "$SAFE_REL" "$MISSING" "${CLAUDE_SESSION_ID:-unknown}" \
  >> "$REPO_ROOT/.enforcement/flow-gate.jsonl" 2>/dev/null

# SOFT-FIRST: v1 always exits 0. Nudge only -- never break a fleet client.
exit 0

# ===========================================================================
# HARD PROMOTION (FUTURE, DO NOT ENABLE IN V1)
# ===========================================================================
# When the Flow discipline has soaked across the fleet and a client opts into
# the company profile, this hook would HARD-block construct work that skipped
# classify+resolve. The activation is gated on an explicit userConfig profile
# so it can NEVER fire for default fleet installs. The block below is reference
# only -- it is unreachable (after `exit 0` above) and intentionally inert.
#
# Sketch of the future hard path (mirrors blueprint-check.sh exit-2 shape):
#
#   PROFILE=""
#   CFG="$REPO_ROOT/.claude/sutra-project.json"
#   if [ -f "$CFG" ] && command -v jq >/dev/null 2>&1; then
#     PROFILE=$(jq -r '.userConfig.profile // empty' "$CFG" 2>/dev/null)
#   fi
#   if [ "$PROFILE" = "company" ]; then
#     {
#       echo "FLOW-GATE (HARD): construct work requires classify + resolve first."
#       echo "  File: $REL_PATH"
#       echo "  Missing markers: ${MISSING}"
#       echo "  Run core:flow to classify the input + resolve a workflow type,"
#       echo "  then re-attempt the Edit/Write."
#       echo "  Override: FLOW_ACK=1 FLOW_ACK_REASON='<why>' <tool>"
#     } >&2
#     exit 2
#   fi
#
# WRAPPER NOTE for the future integrator: the v1 hooks.json registration wraps
# this hook in hooks/lib/sutra-stderr-capture.sh, which ALWAYS exits 0 and does
# NOT propagate the inner hook's exit code. To activate the HARD path above, the
# wrapper must be changed to forward $RC (or this hook must be registered without
# the capture wrapper). Until then the wrapper would swallow any exit 2 -- which
# is by design for v1 SOFT-first and an extra safety net against accidental hard
# blocks on the fleet.
#
# Promotion criteria (do not flip without founder sign-off):
#   1. >=30d of soft operation with low false-positive nudge rate
#      (audited from .enforcement/flow-gate.jsonl).
#   2. core:flow skill stable across a release cycle (markers written reliably).
#   3. Explicit opt-in via userConfig.profile=company in .claude/sutra-project.json.
# Until all three hold, the live code path above terminates at `exit 0`.
# ===========================================================================