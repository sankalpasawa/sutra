#!/bin/bash
# sutra/marketplace/plugin/scripts/feedback.sh
# Sutra v2.0 — /sutra feedback manual channel. Local-only, never transmits.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || { echo "sutra feedback: privacy lib not found at $LIB" >&2; exit 1; }
source "$LIB"

if [ "${SUTRA_TELEMETRY:-1}" = "0" ]; then
  echo "SUTRA_TELEMETRY=0 -> feedback capture disabled"
  exit 0
fi

PUBLIC=0
if [ "${1:-}" = "--public" ]; then
  PUBLIC=1
  shift
fi

MSG="$*"
if [ -z "$MSG" ] && [ ! -t 0 ]; then
  MSG=$(cat)
fi

if [ -z "$MSG" ]; then
  cat <<'EOF'
Usage: sutra feedback "<your thoughts>"

  Stays on your machine at ~/.sutra/feedback/manual/.
  Granting this also enables local consent for auto-capture signals
  (overrides, corrections, abandonment) to persist on disk — see
  ~/.sutra/PRIVACY.md for what's captured and retention policy.

  Nothing is ever transmitted without your explicit command.

Flags:
  --public   (v2.0: NOT YET IMPLEMENTED) Placeholder for future GitHub
             post. Currently warns and falls back to local-only capture.
EOF
  exit 1
fi

if [ "$PUBLIC" = "1" ]; then
  # v2.1: wire --public to gh CLI with confirmation + scrub.
  if ! command -v gh >/dev/null 2>&1; then
    echo "-- --public requires GitHub CLI (gh). Install: https://cli.github.com/ -- falling back to local capture."
    PUBLIC=0
  else
    if ! gh auth status >/dev/null 2>&1; then
      echo "-- gh CLI installed but not authenticated (gh auth login). Falling back to local capture."
      PUBLIC=0
    fi
  fi
fi

mkdir -p "$SUTRA_HOME/feedback/manual" 2>/dev/null
chmod 0700 "$SUTRA_HOME" "$SUTRA_HOME/feedback" "$SUTRA_HOME/feedback/manual" 2>/dev/null

sutra_grant_consent

SCRUBBED=$(scrub_text "$MSG")
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
FILE="$SUTRA_HOME/feedback/manual/${TS}.md"

PLUGIN_VERSION="unknown"
if command -v jq >/dev/null 2>&1 && [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
  PLUGIN_VERSION=$(jq -r '.version' "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")
fi

CONTENT="---
captured_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
plugin_version: ${PLUGIN_VERSION}
channel: manual
---

${SCRUBBED}
"

if ! sutra_safe_write "$FILE" "$CONTENT"; then
  echo "sutra feedback: write failed" >&2
  exit 1
fi

echo "captured at $FILE"
echo "consent granted -- future auto-capture signals will persist locally"
echo "see ~/.sutra/PRIVACY.md for what's captured and retention policy"

# v2.1: --public opts into GitHub issue post via gh CLI.
if [ "$PUBLIC" = "1" ]; then
  echo ""
  echo "-- --public: about to open a GitHub issue at sankalpasawa/sutra"
  echo "   title:   [feedback] from plugin v${PLUGIN_VERSION}"
  echo "   body:    <scrubbed content above>"
  echo "   labels:  feedback, v${PLUGIN_VERSION}"
  echo "   visible: PUBLIC (this is permanent; GitHub issues are public)"
  echo ""
  printf "   confirm with 'yes' (anything else cancels): "
  read -r CONFIRM
  if [ "$CONFIRM" = "yes" ]; then
    TITLE="[feedback] from plugin v${PLUGIN_VERSION}"
    if gh issue create \
         --repo sankalpasawa/sutra \
         --title "$TITLE" \
         --body "$SCRUBBED" \
         --label "feedback,v${PLUGIN_VERSION}" >/dev/null 2>&1; then
      echo "-- issue opened on sankalpasawa/sutra"
    else
      echo "-- gh issue create failed — feedback remains captured locally at $FILE"
    fi
  else
    echo "-- public post cancelled — feedback kept local only"
  fi
fi

exit 0
