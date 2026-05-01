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

# v2.13.0: jq replaces python3 (vinit#38 escalation — see start.sh for context).
# onboard.sh assumes start.sh's upfront jq health gate has already run, OR that
# this script is being invoked directly (legacy /sutra-onboard slash command).
# Either way, fall back to "unknown" when jq is unavailable so re-onboarding
# from python-broken machines doesn't brick on a missing dep.
if command -v jq >/dev/null 2>&1; then
  VERSION=$(jq -r '.version' "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")
else
  VERSION="unknown"
fi

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
if [ -f .claude/sutra-project.json ] && command -v jq >/dev/null 2>&1; then
  if [ "$(jq -r '.telemetry_optin // false' .claude/sutra-project.json 2>/dev/null)" = "true" ]; then
    EXISTING_OPTIN=true
  fi
elif [ ! -f .claude/sutra-project.json ]; then
  case "${SUTRA_AUTO_OPTIN:-}" in
    1|true|TRUE|yes|YES) EXISTING_OPTIN=true ;;
  esac
fi

FIRST_SEEN=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# v2.0.3+: preserve existing identity block across re-runs. Prior code rewrote
# .claude/sutra-project.json unconditionally; a re-onboard would silently erase
# a previously stamped identity. Codex caught this at ship — 2026-04-24.
EXISTING_IDENTITY_JSON=""
if [ -f .claude/sutra-project.json ] && command -v jq >/dev/null 2>&1; then
  FIRST_SEEN=$(jq -r '.first_seen // ""' .claude/sutra-project.json 2>/dev/null)
  [ -z "$FIRST_SEEN" ] && FIRST_SEEN=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # jq -c outputs nothing for null/missing identity (// empty), so we only
  # propagate a non-empty value. write-onboard treats "" as no identity.
  EXISTING_IDENTITY_JSON=$(jq -c '.identity // empty' .claude/sutra-project.json 2>/dev/null || echo "")
fi

# v2.13.0: bash/jq lib replaces python3 (atomic write via mktemp+mv inside).
bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" write-onboard \
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
    # v2.13.0: bash/jq lib. Best-effort per onboard.sh contract — silent failure.
    bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" stamp-identity "$IDENTITY_JSON" 2>/dev/null || true
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
