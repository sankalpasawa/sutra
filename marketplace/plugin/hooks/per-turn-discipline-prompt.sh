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

exit 0
