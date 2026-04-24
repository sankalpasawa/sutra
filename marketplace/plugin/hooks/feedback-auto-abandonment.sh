#!/bin/bash
# sutra/marketplace/plugin/hooks/feedback-auto-abandonment.sh
# Sutra Privacy v2.0 — abandonment-signal auto-capture (Stop).

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || exit 0
source "$LIB" 2>/dev/null || exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
[ -z "$REPO_ROOT" ] && exit 0

DEPTH_MARKER="$REPO_ROOT/.claude/depth-registered"
[ -f "$DEPTH_MARKER" ] || exit 0

NOW=$(date +%s)
MTIME=$(stat -f %m "$DEPTH_MARKER" 2>/dev/null || stat -c %Y "$DEPTH_MARKER" 2>/dev/null)
[ -z "$MTIME" ] && exit 0
AGE=$((NOW - MTIME))
[ "$AGE" -gt 3600 ] && exit 0

SLUG=$(grep -oE 'TASK=[a-zA-Z0-9_-]+' "$DEPTH_MARKER" 2>/dev/null | head -1 | cut -d= -f2)
[ -z "$SLUG" ] && SLUG="unknown"

signal_write abandonment "$SLUG" 1 2>/dev/null || true
exit 0
