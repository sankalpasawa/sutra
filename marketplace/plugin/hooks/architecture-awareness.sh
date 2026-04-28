#!/bin/bash
# Direction: D4 — Architecture Awareness Before Creation
# Event: PreToolUse on Write (new file creation only)
# Enforcement: SOFT (reminder, exit 0 always)
# If creating a new file, remind to check SYSTEM-MAP.md.

FILE_PATH="$TOOL_INPUT_file_path"

# No file path → not relevant
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Only fire if the file doesn't exist yet (new file creation)
if [ ! -f "$FILE_PATH" ]; then
  echo "Warning: Per D4: Creating new file: $FILE_PATH"
  echo "Was SYSTEM-MAP.md consulted? Does this fit existing architecture?"
  echo "Check holding/SYSTEM-MAP.md before proceeding."
fi

exit 0

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
