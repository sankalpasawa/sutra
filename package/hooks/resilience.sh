#!/bin/bash
# Sutra OS — Resilience Hook
# Called by SOFT hooks after a warn. Tracks consecutive failures.
# 2 fails: persist state. 3 fails: auto-escalate to founder.
# Usage: bash resilience.sh <hook_name> <status: pass|warn> [project_dir]

HOOK_NAME="${1:?Usage: resilience.sh <hook_name> <pass|warn> [project_dir]}"
STATUS="${2:?Usage: resilience.sh <hook_name> <pass|warn> [project_dir]}"
PROJECT_DIR="${3:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

STATE_DIR="$PROJECT_DIR/.claude/state"
STATE_FILE="$STATE_DIR/hook-failures.json"
mkdir -p "$STATE_DIR"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Initialize state file if missing
if [ ! -f "$STATE_FILE" ]; then
  echo "{}" > "$STATE_FILE"
fi

# Read current count for this hook
COUNT=$(sed -n "s/.*\"$HOOK_NAME\".*\"consecutive_fails\":\([0-9]*\).*/\1/p" "$STATE_FILE")
COUNT="${COUNT:-0}"

if [ "$STATUS" = "pass" ]; then
  # Reset on success — remove this hook's entry
  if [ "$COUNT" -gt 0 ]; then
    sed -i '' "/$HOOK_NAME/d" "$STATE_FILE" 2>/dev/null
  fi
  exit 0
fi

# Status is "warn" — increment
COUNT=$((COUNT + 1))

# Update state: remove old, add new
sed -i '' "/$HOOK_NAME/d" "$STATE_FILE" 2>/dev/null
# Add entry before closing brace
sed -i '' "s/^{/{\"$HOOK_NAME\":{\"consecutive_fails\":$COUNT,\"last_fail\":\"$TS\"},/" "$STATE_FILE" 2>/dev/null

if [ "$COUNT" -eq 2 ]; then
  echo ""
  echo "RESILIENCE: $HOOK_NAME has failed 2 consecutive times. State persisted."
  echo "  Next failure will escalate to founder via feedback-to-sutra."
  echo ""
fi

if [ "$COUNT" -ge 3 ]; then
  echo ""
  echo "RESILIENCE: $HOOK_NAME has failed $COUNT consecutive times. ESCALATING."
  echo ""
  ESCALATION_DIR="$PROJECT_DIR/os/feedback-to-sutra"
  mkdir -p "$ESCALATION_DIR"
  ESCALATION_FILE="$ESCALATION_DIR/auto-escalation-$(date +%Y-%m-%d).md"
  cat >> "$ESCALATION_FILE" << ESCEOF

## Auto-Escalation: $HOOK_NAME ($TS)

**Hook**: $HOOK_NAME
**Consecutive failures**: $COUNT
**Action needed**: Review hook requirements — clarify instructions or adjust enforcement level.
ESCEOF
  echo "  Escalation written to: $ESCALATION_FILE"
fi
