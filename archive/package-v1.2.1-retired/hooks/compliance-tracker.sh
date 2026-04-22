#!/bin/bash
# Sutra OS — Compliance Tracker
# Called by SOFT hooks to log pass/warn events for graduation tracking.
# Usage: bash compliance-tracker.sh <hook_name> <status: pass|warn> [project_dir]
HOOK_NAME="${1:?Usage: compliance-tracker.sh <hook_name> <pass|warn> [project_dir]}"
STATUS="${2:?Usage: compliance-tracker.sh <hook_name> <pass|warn> [project_dir]}"
PROJECT_DIR="${3:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}}"
LOG_DIR="$PROJECT_DIR/.claude/logs"
LOG_FILE="$LOG_DIR/compliance.jsonl"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "{\"ts\":\"$TS\",\"hook\":\"$HOOK_NAME\",\"status\":\"$STATUS\"}" >> "$LOG_FILE"
