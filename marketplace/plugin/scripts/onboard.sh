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
# v2.0.3+: preserve existing identity block across re-runs. Prior code rewrote
# .claude/sutra-project.json unconditionally; a re-onboard would silently erase
# a previously stamped identity. Codex caught this at ship — 2026-04-24.
EXISTING_IDENTITY_JSON=""
if [ -f .claude/sutra-project.json ]; then
  FIRST_SEEN=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json')).get('first_seen', ''))" 2>/dev/null)
  [ -z "$FIRST_SEEN" ] && FIRST_SEEN=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  EXISTING_IDENTITY_JSON=$(python3 -c "import json; d=json.load(open('.claude/sutra-project.json')); ident=d.get('identity'); print(json.dumps(ident) if ident else '')" 2>/dev/null || echo "")
fi

# v2.8.11 (vinit#38): moved from python3 stdin-heredoc to file-execution form +
# atomic write (the helper writes via tempfile + os.replace internally, so a
# SIGKILL mid-write leaves the prior valid file content untouched rather than
# producing a 0-byte corrupted .claude/sutra-project.json).
python3 "$PLUGIN_ROOT/scripts/_sutra_project_lib.py" write-onboard \
    "$INSTALL_ID" "$PROJECT_ID" "$NAME" "$FIRST_SEEN" "$VERSION" "$EXISTING_OPTIN" "$EXISTING_IDENTITY_JSON"

queue_init

# v1.9.0+: stamp identity block if telemetry_optin is true. Best-effort.
# v2.0.1+: per PRIVACY.md contract ("local-first, consent-gated, in-memory-until-consent"),
#          local identity writes require SUTRA_LEGACY_TELEMETRY=1 — telemetry_optin alone
#          is insufficient consent for writing github_login/git name to disk. Closes the
#          contract gap codex flagged on 2026-04-24 post-v2.0 privacy rewrite.
if [ "$EXISTING_OPTIN" = "true" ] \
   && [ "${SUTRA_LEGACY_TELEMETRY:-0}" = "1" ] \
   && declare -f capture_identity >/dev/null 2>&1; then
  IDENTITY_JSON=$(capture_identity "$VERSION" 2>/dev/null)
  if [ -n "$IDENTITY_JSON" ]; then
    # v2.8.11 (vinit#38): moved from python3 stdin-heredoc to file-execution
    # form + atomic write. Best-effort per onboard.sh contract — silent failure.
    python3 "$PLUGIN_ROOT/scripts/_sutra_project_lib.py" stamp-identity "$IDENTITY_JSON" 2>/dev/null || true
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
if [ "$EXISTING_OPTIN" = "true" ] && [ "${SUTRA_LEGACY_TELEMETRY:-0}" = "1" ]; then
  echo "  identity:        stamped locally (legacy mode active). See PRIVACY.md."
elif [ "$EXISTING_OPTIN" = "true" ]; then
  echo "  identity:        not stored locally (v2.0 default). See PRIVACY.md for consent options."
fi
echo ""
echo "Next:"
echo "  /sutra-status    — inspect state"
echo "  /sutra-push      — deliver queue to sankalpasawa/sutra-data (needs opt-in=true)"
