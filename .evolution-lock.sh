#!/bin/bash
# Sutra Write Lock — prevents concurrent writes during evolution cycles
# Usage: source this before writing to sutra/
#   acquire_lock "agent-name"
#   ... do work ...
#   release_lock

LOCK_FILE="$(git rev-parse --show-toplevel 2>/dev/null)/sutra/.evolution-lock"
LOCK_TIMEOUT=300  # 5 minutes max hold

acquire_lock() {
  local agent="${1:-unknown}"
  local attempts=0
  while [ -f "$LOCK_FILE" ]; do
    # Check if lock is stale (older than timeout)
    if [ -f "$LOCK_FILE" ]; then
      local lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0) ))
      if [ "$lock_age" -gt "$LOCK_TIMEOUT" ]; then
        echo "WARN: Stale lock detected (${lock_age}s old). Breaking it."
        rm -f "$LOCK_FILE"
        break
      fi
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -gt 30 ]; then
      echo "ERROR: Could not acquire sutra write lock after 30 attempts. Another agent is writing."
      return 1
    fi
    sleep 2
  done
  echo "{\"agent\": \"${agent}\", \"acquired\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"pid\": $$}" > "$LOCK_FILE"
  echo "LOCK acquired by ${agent}"
  return 0
}

release_lock() {
  rm -f "$LOCK_FILE"
  echo "LOCK released"
}
