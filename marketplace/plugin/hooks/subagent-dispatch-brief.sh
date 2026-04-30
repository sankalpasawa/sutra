#!/usr/bin/env bash
# subagent-dispatch-brief.sh — D40 G4 governance-parity hook
#
# Event: PreToolUse on Task tool
# Behavior: emit a soft hint reminding the model to brief subagent dispatch
#           prompts with the 5-block Sutra discipline + 4-line footer.
#
# Per codex CHANGES-REQUIRED fold (v1.0.1, 2026-04-30): hook now CONSUMES
# sutra-defaults.json at runtime via jq, instead of hardcoding briefing text.
# This makes sutra-defaults.json the actual canonical policy surface (D40 G6).
#
# Per codex caveat (D40 verdict): hook-injects-prompt is SOFT GUIDANCE ONLY.
# G4 fires AFTER top-level discipline (G1) is stable so subagents inherit
# policy rather than invent it (codex execution order G5->G1->G2->G3->G4).
#
# Kill-switches (any one disables):
#   ~/.sutra-defaults-disabled        (all D40 defaults)
#   ~/.subagent-brief-disabled        (this hook only)
#   SUTRA_DEFAULTS_DISABLED=1
#   SUBAGENT_BRIEF_DISABLED=1
#
# Fail-open: exit 0 always (never block the Task tool).

set -u

# Kill-switches
[ -f "$HOME/.sutra-defaults-disabled" ] && exit 0
[ -f "$HOME/.subagent-brief-disabled" ] && exit 0
[ -n "${SUTRA_DEFAULTS_DISABLED:-}" ] && exit 0
[ -n "${SUBAGENT_BRIEF_DISABLED:-}" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
DEFAULTS_DIR="${CLAUDE_PLUGIN_ROOT:-$REPO_ROOT/sutra/marketplace/plugin}"
DEFAULTS_JSON="$DEFAULTS_DIR/sutra-defaults.json"

# Fallback path: json or jq missing → minimal reminder using same contract
# language as primary path (codex re-review #3 fold — fallback parity).
if [ ! -r "$DEFAULTS_JSON" ] || ! command -v jq >/dev/null 2>&1; then
  {
    printf '\n[Sutra defaults · D40 v1.0.4] Subagent dispatch reminder (fallback — sutra-defaults.json or jq unavailable):\n'
    printf '  Prefix dispatched prompt with: §Sutra discipline (mandatory)\n'
    printf '  Then 5 numbered blocks: Input Routing / Depth + Estimation / Build-Layer (if D38) / Operationalization 6-section / Codex review per layer\n'
    printf '  End with 4-line footer (each on own line):\n'
    printf '    TRIAGE: <values>\n    ESTIMATE: <values>\n    ACTUAL: <values>\n    OS TRACE: <one line>\n\n'
  } >&2
  exit 0
fi

# Consume canonical surface (D40 G6 — single source of truth)
# Use briefing_blocks_human (humanized labels) so the harness Q5 regex matches
# the emitted text. Raw briefing_blocks IDs are kept in json for code consumption.
BLOCKS=$(jq -r '.subagent_dispatch.briefing_blocks_human[]' "$DEFAULTS_JSON" 2>/dev/null)
FOOTER=$(jq -r '.subagent_dispatch.footer_lines | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
KILL_FILE=$(jq -r '.kill_switches.subagent_dispatch_brief.file' "$DEFAULTS_JSON" 2>/dev/null)

# Emit derived reminder (changes if json changes).
# Per codex re-review #2 fold (v1.0.4): hook now reminds the model to use
# the EXACT contract language "§Sutra discipline (mandatory)" in the
# dispatched prompt, with 4-line footer each on its own line. This aligns
# what the model is reminded to emit with what the harness Q5 verifies.
{
  printf '\n[Sutra defaults · D40 v1.0.4] Subagent dispatch reminder (sourced from sutra-defaults.json):\n'
  printf '  When invoking the Task tool, prefix the dispatched prompt with this exact line:\n'
  printf '    §Sutra discipline (mandatory)\n'
  printf '  Followed by the 5 numbered blocks:\n'
  N=0
  while IFS= read -r block; do
    [ -z "$block" ] && continue
    N=$((N + 1))
    printf '    %d. %s\n' "$N" "$block"
  done <<< "$BLOCKS"
  printf '  End the dispatched prompt with the 4-line footer (each on its own line):\n'
  printf '    TRIAGE: <values>\n'
  printf '    ESTIMATE: <values>\n'
  printf '    ACTUAL: <values>\n'
  printf '    OS TRACE: <one line>\n'
  printf '  See %s/SUTRA-DEFAULTS.md\n' "$DEFAULTS_DIR"
  printf '  Kill-switch: touch %s\n\n' "${KILL_FILE:-~/.subagent-brief-disabled}"
} >&2

exit 0
