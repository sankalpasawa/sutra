#!/bin/bash
# blueprint-check.sh — BLUEPRINT block enforcement (codex round-5 narrowed scope)
#
# Charter: sutra/os/engines/BLUEPRINT-ENGINE.md
# Skill:   sutra/marketplace/plugin/skills/blueprint/SKILL.md
# Event:   PreToolUse on Edit|Write
# Enforcement: SOFT — exit 0 with stderr warning unless on FOUNDATIONAL paths.
#              HARD on FOUNDATIONAL paths only.
#
# Why narrower than build-layer-check.sh:
#   build-layer-check.sh already HARD-blocks holding/hooks/**,
#   sutra/marketplace/plugin/**, sutra/os/charters/**, holding/departments/**
#   without .claude/build-layer-registered. A second HARD marker on the same
#   paths is redundant friction. BLUEPRINT fires on a NARROWER set: charters,
#   protocols, design docs, founder directions, plans — places where
#   pre-spend visibility (showing the plan before spending tokens) matters
#   most.
#
# Codex round 5 corrections:
#   - Scope narrowed to foundational doc paths only (no overlap with
#     build-layer-check on code paths).
#   - V1 kill-switch is env + fs ONLY — no fake SUTRA-CONFIG.md flag claim.
#   - Soft mode on BUILD-LAYER-hard paths (avoid double-block UX).
#
# Marker: .claude/blueprint-registered (set when emit-blueprint skill fires)
# Override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool-call>
# Kill-switch (2-level V1):
#   - BLUEPRINT_DISABLED=1 (per-shell)
#   - ~/.blueprint-disabled (per-machine)

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

# ── Kill-switches (2-level, per codex round 5; no fake fleet flag) ──
[ -n "${BLUEPRINT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.blueprint-disabled" ] && exit 0

# ── Override path ──
if [ "${BLUEPRINT_ACK:-0}" = "1" ]; then
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  REASON=$(printf '%s' "${BLUEPRINT_ACK_REASON:-no-reason}" | tr -d '\n\r' | head -c 500)
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  printf '{"ts":"%s","event":"blueprint-override","reason":"%s"}\n' \
    "$TS" "$REASON" >> "$REPO_ROOT/.enforcement/blueprint-ledger.jsonl"
  exit 0
fi

# ── Parse target file_path from PreToolUse stdin JSON ──
PAYLOAD=$(cat 2>/dev/null || true)
FILE_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="$TOOL_INPUT_file_path"
[ -z "$FILE_PATH" ] && exit 0
REL_PATH="${FILE_PATH#$REPO_ROOT/}"

# ── FOUNDATIONAL paths (HARD-block without marker) ──
# Narrower than build-layer-check.sh — only doc artifacts where pre-spend
# blueprint visibility matters most.
case "$REL_PATH" in
  sutra/os/charters/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/protocols/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/PROTOCOLS.md) is_foundational=1 ;;
  holding/FOUNDER-DIRECTIONS.md) is_foundational=1 ;;
  holding/research/*-design.md|holding/research/*-plan.md) is_foundational=1 ;;
  sutra/os/engines/*.md) is_foundational=1 ;;
  *) is_foundational=0 ;;
esac

# ── Whitelist (exempt regardless of foundational class) ──
case "$REL_PATH" in
  *.lock|*.log|*.jsonl) exit 0 ;;
  .claude/*|.enforcement/*|.analytics/*) exit 0 ;;
  */TODO.md|*/BACKLOG.md|*/CHANGELOG.md|*/MEMORY.md) exit 0 ;;
  holding/checkpoints/*) exit 0 ;;
  sutra/archive/*) exit 0 ;;
esac

MARKER="$REPO_ROOT/.claude/blueprint-registered"

if [ "$is_foundational" = "1" ]; then
  # HARD on foundational paths
  if [ ! -f "$MARKER" ]; then
    {
      echo "BLUEPRINT-CHECK: foundational artifact edit requires BLUEPRINT block."
      echo "  File: $REL_PATH"
      echo "  Emit per-task BLUEPRINT block (see CLAUDE.md Mandatory Blocks)."
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
else
  # SOFT elsewhere — advisory only (no blocking; build-layer-check.sh handles HARD)
  if [ ! -f "$MARKER" ]; then
    echo "BLUEPRINT-CHECK (advisory): consider emitting BLUEPRINT block for $REL_PATH" >&2
    # exit 0 — soft, doesn't block
  fi
fi

exit 0

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Logged to .enforcement/blueprint-ledger.jsonl on override events.
# Hook fires counted in holding/hooks/hook-log.jsonl (via standard logger).
#
# ### 2. Adoption mechanism
# Registered in .claude/settings.json under PreToolUse Edit|Write.
# Holding-only at L1 staging; promote to plugin after 30d clean operation.
#
# ### 3. Monitoring / escalation
# Override rate from blueprint-ledger.jsonl reviewed weekly.
# >30% override rate over 7d = soften the rule or narrow paths further.
#
# ### 4. Iteration trigger
# Founder correction on a missed-block fire OR override-rate breach.
#
# ### 5. DRI
# Sutra-OS (Asawa-CEO). Operator: any session running in asawa-holding.
#
# ### 6. Decommission criteria
# Replaced by an in-LLM behavioral discipline that emits the block reliably
# without need for hook enforcement. Or: charter retirement (BLUEPRINT
# subsumed into a different engine).
