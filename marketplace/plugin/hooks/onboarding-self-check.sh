#!/bin/bash
# Phase 6 onboarding self-check — PostToolUse on Write
# Advisory only (exit 0 always). Catches placeholders in company os/ dirs.

FILE_PATH="$TOOL_INPUT_file_path"
[ -z "$FILE_PATH" ] && exit 0

# Only check files inside a company's os/ directory
COMPANY=$(echo "$FILE_PATH" | grep -oE '(dayflow|maze|ppr|jarvis|paisa)/os/' | head -1)
[ -z "$COMPANY" ] && exit 0
COMPANY_NAME=$(echo "$COMPANY" | cut -d/ -f1)

# Patterns to flag
PATTERNS='\{placeholder\}|\{company|\{COMPANY|ExampleCo|TODO:|FIXME:|__REPLACE__|<<.*>>'
# Cross-company name leak: flag "DayFlow" in non-dayflow repos
if [ "$COMPANY_NAME" != "dayflow" ]; then
  PATTERNS="$PATTERNS|DayFlow"
fi

MATCHES=$(grep -noE "$PATTERNS" "$FILE_PATH" 2>/dev/null)
if [ -n "$MATCHES" ]; then
  echo ""
  echo "ONBOARDING QA: Found placeholder in $FILE_PATH:"
  echo "$MATCHES" | head -5
  echo "Fix before proceeding."
  echo ""
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
