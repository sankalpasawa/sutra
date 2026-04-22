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
# v1.9.0+: identity capture (best-effort; never fails onboard)
if [ -f "$PLUGIN_ROOT/lib/identity.sh" ]; then
  source "$PLUGIN_ROOT/lib/identity.sh"
fi

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

# v1.9.0+: stamp identity block if telemetry_optin is true. Best-effort.
if [ "$EXISTING_OPTIN" = "true" ] && declare -f capture_identity >/dev/null 2>&1; then
  IDENTITY_JSON=$(capture_identity "$VERSION" 2>/dev/null)
  if [ -n "$IDENTITY_JSON" ]; then
    python3 - "$IDENTITY_JSON" <<'PY' 2>/dev/null || true
import json, sys
p = '.claude/sutra-project.json'
try:
    d = json.load(open(p))
except Exception:
    sys.exit(0)
try:
    d['identity'] = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
open(p, 'w').write(json.dumps(d, indent=2))
PY
    # Also cache for push.sh staleness check. Uses SUTRA_HOME (set by queue.sh).
    SUTRA_HOME_DIR="${SUTRA_HOME:-$HOME/.sutra}"
    mkdir -p "$SUTRA_HOME_DIR" 2>/dev/null
    printf '%s\n' "$IDENTITY_JSON" > "$SUTRA_HOME_DIR/identity.json" 2>/dev/null
    chmod 600 "$SUTRA_HOME_DIR/identity.json" 2>/dev/null || true
  fi
fi

echo "✓ Sutra onboarded for this project"
echo "  install_id:      $INSTALL_ID"
echo "  project_id:      $PROJECT_ID"
echo "  project_name:    $NAME"
echo "  sutra_version:   $VERSION"
echo "  telemetry_optin: $EXISTING_OPTIN  (edit .claude/sutra-project.json to flip)"
echo "  queue:           $(queue_file) — depth $(queue_count)"
if [ "$EXISTING_OPTIN" = "true" ]; then
  echo "  identity:        stamped (git name + gh login + os). See PRIVACY.md or .claude/sutra-project.json"
fi
echo ""
echo "Next:"
echo "  /sutra-status    — inspect state"
echo "  /sutra-push      — deliver queue to sankalpasawa/sutra-data (needs opt-in=true)"
