#!/bin/bash
# Sutra plugin — /sutra-onboard logic extracted to a script so the slash
# command file can invoke it with a single-line shell block (the Claude Code
# slash-command parser doesn't like multi-line heredoc-style shell).
#
# Writes .claude/sutra-project.json with install_id + project_id + telemetry_optin=false.
# Idempotent — re-running is safe (IDs are deterministic).

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

source "$PLUGIN_ROOT/lib/project-id.sh"
source "$PLUGIN_ROOT/lib/queue.sh"

VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_ROOT/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")

cd "$PROJECT_ROOT"

INSTALL_ID=$(compute_install_id "$VERSION")
PROJECT_ID=$(compute_project_id)

NAME=$(git config --get remote.origin.url 2>/dev/null | sed -E 's|.*/||; s|\.git$||')
[ -z "$NAME" ] && NAME=$(basename "$PROJECT_ROOT")

mkdir -p .claude

# Resolve telemetry_optin default.
#   1) If .claude/sutra-project.json exists → preserve whatever it had.
#   2) Else if $SUTRA_AUTO_OPTIN is 1/true/yes → default to true.
#   3) Else → default to false (privacy-safe default for external users).
EXISTING_OPTIN=false
if [ -f .claude/sutra-project.json ]; then
  EXISTING_OPTIN=$(python3 -c "import json; d=json.load(open('.claude/sutra-project.json')); print('true' if d.get('telemetry_optin') else 'false')" 2>/dev/null || echo false)
else
  case "${SUTRA_AUTO_OPTIN:-}" in
    1|true|TRUE|yes|YES) EXISTING_OPTIN=true ;;
  esac
fi

FIRST_SEEN=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ -f .claude/sutra-project.json ]; then
  FIRST_SEEN=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json')).get('first_seen', ''))" 2>/dev/null)
  [ -z "$FIRST_SEEN" ] && FIRST_SEEN=$(date -u +%Y-%m-%dT%H:%M:%SZ)
fi

cat > .claude/sutra-project.json <<JSON
{
  "install_id": "$INSTALL_ID",
  "project_id": "$PROJECT_ID",
  "project_name": "$NAME",
  "first_seen": "$FIRST_SEEN",
  "sutra_version": "$VERSION",
  "telemetry_optin": $EXISTING_OPTIN
}
JSON

queue_init

echo "✓ Sutra onboarded for this project"
echo "  install_id:      $INSTALL_ID"
echo "  project_id:      $PROJECT_ID"
echo "  project_name:    $NAME"
echo "  sutra_version:   $VERSION"
echo "  telemetry_optin: $EXISTING_OPTIN  (edit .claude/sutra-project.json to flip)"
echo "  queue:           $(queue_file) — depth $(queue_count)"
echo ""
echo "Next:"
echo "  /sutra-status    — inspect state"
echo "  /sutra-push      — deliver queue to sankalpasawa/sutra-data (needs opt-in=true)"
