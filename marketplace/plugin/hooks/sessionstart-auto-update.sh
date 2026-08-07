#!/bin/bash
# Sutra: sessionstart-auto-update — runs at EVERY session start, acts ONCE PER DAY.
#
# First session of the day: refresh the marketplace, update the plugin, print
# ONE line if the version moved. Every later session that day exits
# immediately with no network. Silent unless something actually changed.
#
# Codex-guided constraints (2026-08-05), all load-bearing:
#  - NO shell timeout wrapper. macOS has no GNU `timeout`; the bound comes from
#    the hook-level "timeout" in hooks.json.
#  - The update does NOT apply to the CURRENT session — Claude Code has already
#    loaded this version. The line says so rather than implying otherwise.
#  - Every failure exits 0 and silent. A broken updater must never be the
#    reason a session cannot start.
#
# Writes exactly one file: $SUTRA_HOME/last-update-check (a date). No logs.

set -uo pipefail

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
STAMP="$SUTRA_HOME/last-update-check"
LOCK="$SUTRA_HOME/.update.lock"
TODAY="$(date +%Y-%m-%d 2>/dev/null)" || exit 0
[ -n "$TODAY" ] || exit 0

# Already ran today -> the common path. No network, no work, no output.
[ -f "$STAMP" ] && [ "$(head -1 "$STAMP" 2>/dev/null)" = "$TODAY" ] && exit 0

[ -n "${CLAUDE_PLUGIN_ROOT:-}" ] || exit 0
command -v claude >/dev/null 2>&1 || exit 0

mkdir -p "$SUTRA_HOME" 2>/dev/null || exit 0

# Concurrent sessions starting together must not both update. mkdir is atomic;
# whoever loses skips. Locks older than an hour are treated as stale.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -d "$LOCK" ]; then
    _age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
    [ "$_age" -lt 3600 ] && exit 0
    rmdir "$LOCK" 2>/dev/null || exit 0
    mkdir "$LOCK" 2>/dev/null || exit 0
  else
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# Stamp BEFORE the network call. If the runner kills us mid-update we must not
# retry on every subsequent session for the rest of the day.
echo "$TODAY" > "$STAMP" 2>/dev/null || true

_cache_root="${SUTRA_CACHE_ROOT:-$HOME/.claude/plugins/cache/sutra/core}"
_before="$(basename "${CLAUDE_PLUGIN_ROOT%/}" 2>/dev/null)"

claude plugin marketplace update sutra >/dev/null 2>&1 || true
claude plugin update core@sutra        >/dev/null 2>&1 || true

# After = the highest version dir present. Comparing directories rather than
# the manifest matters: an update lands as a NEW cache dir, so the manifest
# under the old CLAUDE_PLUGIN_ROOT would still read the old number.
_after="$(ls -1 "$_cache_root" 2>/dev/null | sort -V | tail -1)" || _after=""

[ -n "$_after" ] || exit 0
[ -n "$_before" ] || exit 0
[ "$_after" = "$_before" ] && exit 0

# Only reachable when the version actually moved. One line, on stderr so it
# reaches the operator without becoming session content.
echo "Sutra updated: $_before -> $_after (active next session)" >&2
exit 0
