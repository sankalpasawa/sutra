#!/usr/bin/env bash
# PreToolUse hook: blocks Write/Edit until input has been classified.
# Fires on: Write, Edit
# Speed-critical — no subshells, no external commands beyond test/grep.

TOOL_NAME="$1"
FILE_PATH="$2"

# Only gate Write and Edit
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

# Whitelist: system-maintenance paths skip classification
if echo "$FILE_PATH" | grep -qE '(memory/|checkpoints/|\.lock|TODO\.md)'; then
  exit 0
fi

# Check for classification marker (per-turn; wiped by reset-turn-markers.sh on
# UserPromptSubmit). Convention aligned with .claude/depth-registered and
# .claude/blueprint-registered. Prior path /tmp/asawa-input-classified-${SID}
# was broken — no writer existed in any skill or hook (2026-05-10 root-cause fix
# during SOFT-to-HARD blanket flip; founder direction Option A).
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
MARKER="$REPO_ROOT/.claude/input-routed"

if [[ -f "$MARKER" ]]; then
  exit 0
fi

# Override path (honor-system; audit-logged)
if [[ "${INPUT_ROUTING_ACK:-0}" == "1" ]]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  REASON=$(printf '%s' "${INPUT_ROUTING_ACK_REASON:-no-reason}" | tr -d '"\\' | tr '\n\r' '  ')
  printf '{"ts":%s,"event":"input-routing-override","reason":"%s"}\n' "$(date +%s)" "$REASON" \
    >> "$REPO_ROOT/.enforcement/input-routing-overrides.jsonl"
  exit 0
fi

cat >&2 <<EOF
BLOCKED: emit Input Routing block before Edit/Write (CLAUDE.md Mandatory Blocks).
Required: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION lines.
Then write marker via Bash (Write tool is itself blocked by this hook):
  printf "TS=%s TASK=<slug>\n" "\$(date +%s)" > .claude/input-routed
Override (one call): INPUT_ROUTING_ACK=1 INPUT_ROUTING_ACK_REASON='<why>' <tool>
EOF
exit 2

# ============================================================================
# ## Operationalization
# (Auto-appended on D38 wave-6 plugin promotion — lightweight default; replace
# with concrete metrics when this hook gets attention.)
#
# ### 1. Measurement mechanism
# Hook events emit to .enforcement/build-layer-ledger.jsonl or hook-specific
# log when relevant; no dedicated metric until usage observed.
# ### 2. Adoption mechanism
# Activated via plugin distribution from sutra/marketplace/plugin/hooks/.
# ### 3. Monitoring / escalation
# Surface error/anomaly rate to Asawa CEO weekly until baseline established.
# ### 4. Iteration trigger
# Tighten or loosen after 14 days of fleet observation.
# ### 5. DRI
# Asawa CEO (Sutra Forge per D31).
# ### 6. Decommission criteria
# Retire when capability supersedes via newer hook or absorbed into a
# composite gate. Currently no decommission planned.
# ============================================================================
