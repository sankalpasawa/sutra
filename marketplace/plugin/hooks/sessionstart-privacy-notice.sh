#!/bin/bash
# sutra/marketplace/plugin/hooks/sessionstart-privacy-notice.sh
# Sutra Privacy v2.0 — install-time notice + PRIVACY.md refresh + retention sweep.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || exit 0
source "$LIB" 2>/dev/null || exit 0

mkdir -p "$SUTRA_HOME" 2>/dev/null
chmod 0700 "$SUTRA_HOME" 2>/dev/null

PRIVACY_SRC="$PLUGIN_ROOT/PRIVACY.md"
PRIVACY_USER="$SUTRA_HOME/PRIVACY.md"
if [ -f "$PRIVACY_SRC" ]; then
  CONTENT=$(cat "$PRIVACY_SRC" 2>/dev/null)
  sutra_safe_write "$PRIVACY_USER" "$CONTENT" 2>/dev/null
fi

# v2.68.0: marker renamed so every existing install sees the new
# default-on disclosure exactly once after upgrading.
NOTICE_MARKER="$SUTRA_HOME/.privacy-notice-shown-v268"
if [ ! -f "$NOTICE_MARKER" ]; then
  echo "Sutra telemetry is ON by default (v2.68.0): anonymous metric rows push once daily to sankalpasawa/sutra-data. No identity fields without explicit consent (/core:start --telemetry on). Opt out: SUTRA_TELEMETRY=0 or telemetry_optin=false. Details: ~/.sutra/PRIVACY.md"
  (umask 0077; date -u +%Y-%m-%dT%H:%M:%SZ > "$NOTICE_MARKER" 2>/dev/null)
  chmod 0600 "$NOTICE_MARKER" 2>/dev/null
fi

sutra_retention_cleanup 2>/dev/null || true
exit 0
