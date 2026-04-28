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

# Check for classification marker
SESSION_ID="${CLAUDE_SESSION_ID:-default}"
MARKER="/tmp/asawa-input-classified-${SESSION_ID}"

if [[ -f "$MARKER" ]]; then
  exit 0
fi

echo "BLOCKED: Classify this input through INPUT-ROUTING protocol before acting. Output the classification block first."
exit 1

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
