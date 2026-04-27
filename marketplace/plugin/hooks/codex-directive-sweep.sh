#!/usr/bin/env bash
# PROTO-019 v3: Codex directive sweep (SessionStart hook)
#
# Scans .claude/codex-directive-pending-* markers and archives any whose
# owning session is stale. "Stale" means the session's heartbeat
# (.claude/heartbeats/<SID>) is either missing or older than the configured
# threshold (default 2h).
#
# Why this exists: prior to v3 the directive marker was a single-slot file.
# Sessions that died without resolving the directive left the marker behind,
# and every new session on the same repo inherited the block. v3 scopes the
# marker to .claude/codex-directive-pending-<SID> and relies on this sweep
# to clean up markers whose session is definitively abandoned.
#
# Live-in-another-tab sessions are PRESERVED: their heartbeat is still fresh,
# so this sweep leaves their markers alone.
#
# Also handles legacy cleanup: archives any bare .claude/codex-directive-pending
# file (no -SID suffix) left over from v2 installs.
#
# Config:
#   SUTRA_HEARTBEAT_STALE_HOURS (default: 2) — session considered dead after this
#   SUTRA_DIRECTIVE_SWEEP_DISABLED=1 — kill switch
#   ~/.codex-directive-disabled — kill switch (file)
#
# Exit: always 0 (housekeeping; never blocks SessionStart)

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

# Kill-switch
[ -n "${SUTRA_DIRECTIVE_SWEEP_DISABLED:-}" ] && exit 0
[ -n "${CODEX_DIRECTIVE_DISABLED:-}" ] && exit 0
[ -f "$HOME/.codex-directive-disabled" ] && exit 0

STALE_HOURS="${SUTRA_HEARTBEAT_STALE_HOURS:-2}"
# Sanitize: integer 1-168 (1h to 1 week)
case "$STALE_HOURS" in
  ''|*[!0-9]*) STALE_HOURS=2 ;;
esac
[ "$STALE_HOURS" -lt 1 ] && STALE_HOURS=1
[ "$STALE_HOURS" -gt 168 ] && STALE_HOURS=168

STALE_MINUTES=$((STALE_HOURS * 60))
ORPHAN_DIR=".enforcement/codex-reviews/orphaned"
LOG_FILE=".enforcement/codex-reviews/gate-log.jsonl"

mkdir -p "$ORPHAN_DIR" .enforcement/codex-reviews 2>/dev/null || true

log_event() {
  [ -z "${1:-}" ] && return
  command -v jq >/dev/null 2>&1 || return
  printf '%s\n' "$1" >> "$LOG_FILE" 2>/dev/null || true
}

archive_marker() {
  local marker="$1"
  local reason="$2"
  local sid="$3"
  [ -f "$marker" ] || return

  local ts dest
  ts=$(date -u +%Y-%m-%dT%H-%M-%SZ)
  dest="$ORPHAN_DIR/$(basename "$marker")-$ts"

  mv "$marker" "$dest" 2>/dev/null || return

  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if command -v jq >/dev/null 2>&1; then
    event=$(jq -nc \
      --arg ts "$now" \
      --arg reason "$reason" \
      --arg sid "$sid" \
      --arg archive "$dest" \
      '{ts:$ts,event:"directive-swept-orphan",reason:$reason,session_id:$sid,archive:$archive}')
    log_event "$event"
  fi
}

# Legacy: archive any bare v2 single-slot marker
if [ -f ".claude/codex-directive-pending" ]; then
  archive_marker ".claude/codex-directive-pending" "v2-legacy-single-slot" "unknown"
fi

# Session-scoped markers: check heartbeat freshness
for marker in .claude/codex-directive-pending-*; do
  [ -f "$marker" ] || continue

  # Extract SID from filename (strip prefix)
  sid="${marker#.claude/codex-directive-pending-}"
  heartbeat=".claude/heartbeats/$sid"

  if [ ! -f "$heartbeat" ]; then
    archive_marker "$marker" "heartbeat-missing" "$sid"
    continue
  fi

  # find returns nonzero if file NOT older than threshold
  if find "$heartbeat" -mmin "+$STALE_MINUTES" -print 2>/dev/null | grep -q .; then
    archive_marker "$marker" "heartbeat-stale-over-${STALE_HOURS}h" "$sid"
  fi
done

# Also prune ancient heartbeats (>7 days old) to keep dir tidy
find .claude/heartbeats -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null || true

exit 0
