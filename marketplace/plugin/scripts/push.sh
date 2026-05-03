#!/bin/bash
# Sutra plugin — /sutra-push logic as standalone script.
# Delivers local queue to sankalpasawa/sutra-data (private). Respects opt-in.
#
# v2.18.0 (2026-05-03): opt-in transport restored.
#   - Removes v2.0 hard gate that blocked push regardless of consent.
#   - SUTRA_TELEMETRY=0 short-circuits BEFORE the telemetry_optin gate
#     so the kill-switch works uniformly across capture and push.
#   - Replaces all python3 JSON probes + manifest writer with jq
#     (matches start.sh v2.13.0 EDR-killed-python3 fix).
#   - SUTRA_DATA_REMOTE env override for testability and self-host paths.
#
# Codex review chain: R1-R5 → PASS. Verdict file:
#   .enforcement/codex-reviews/2026-05-03-v2.18.0-opt-in-push.md

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

source "$PLUGIN_ROOT/lib/queue.sh"
# v1.9.0+: identity capture (best-effort; never fails push)
if [ -f "$PLUGIN_ROOT/lib/identity.sh" ]; then
  source "$PLUGIN_ROOT/lib/identity.sh"
fi

# Kill-switch — uniform with capture path. PRIVACY.md v2.18 amendment
# documents this as the single off-switch for both capture and transport.
if [ "${SUTRA_TELEMETRY:-1}" = "0" ]; then
  echo "telemetry off (SUTRA_TELEMETRY=0) — push skipped"
  exit 0
fi

# jq is required (matching start.sh v2.13.0 — EDR-kills-python3 fix)
if ! command -v jq >/dev/null 2>&1; then
  cat >&2 <<'EOF'
sutra push: jq is required but not found on PATH.

Install:
  macOS:    brew install jq
  Debian:   sudo apt-get install jq
  RHEL:     sudo dnf install jq
  Other:    https://jqlang.org/download/

Then re-run.
EOF
  exit 127
fi

cd "$PROJECT_ROOT"

if [ ! -f .claude/sutra-project.json ]; then
  echo "no .claude/sutra-project.json — run /sutra-onboard first"
  exit 0
fi

OPTIN=$(jq -r '.telemetry_optin // false' .claude/sutra-project.json 2>/dev/null)
if [ "$OPTIN" != "true" ]; then
  echo "telemetry_optin is false — push skipped"
  echo "(to enable: re-run /core:start --telemetry on)"
  exit 0
fi

INSTALL_ID=$(jq -r '.install_id // empty' .claude/sutra-project.json)
PROJECT_ID=$(jq -r '.project_id // empty' .claude/sutra-project.json)
PROJECT_NAME=$(jq -r '.project_name // ""' .claude/sutra-project.json)
VERSION=$(jq -r '.sutra_version // empty' .claude/sutra-project.json)

if [ -z "$INSTALL_ID" ] || [ -z "$PROJECT_ID" ] || [ -z "$VERSION" ]; then
  echo "✗ .claude/sutra-project.json missing required fields (install_id/project_id/sutra_version) — re-run /core:start"
  exit 1
fi

COUNT=$(queue_count)

if [ "$COUNT" -eq 0 ]; then
  echo "queue empty — nothing to push"
  exit 0
fi

echo "pushing $COUNT metrics for install_id $INSTALL_ID..."

REMOTE="${SUTRA_DATA_REMOTE:-git@github.com:sankalpasawa/sutra-data.git}"
CACHE="$SUTRA_HOME/sutra-data-cache"
if [ ! -d "$CACHE/.git" ]; then
  git clone --depth 1 --single-branch --quiet "$REMOTE" "$CACHE" 2>&1 | tail -2
else
  git -C "$CACHE" pull --quiet 2>&1 | tail -2
fi

if [ ! -d "$CACHE/.git" ]; then
  echo "✗ could not clone sutra-data (check gh auth + network) — queue preserved"
  exit 1
fi

TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
DEST="$CACHE/clients/$INSTALL_ID"
mkdir -p "$DEST"
cp "$(queue_file)" "$DEST/telemetry-$TS.jsonl"

# v2.2.0 (PROTO-024 H2 fix): identity capture REMOVED from push path. The
# legacy block stamped github_login/github_id/git_user_name into remote
# manifest.json, which leaked PII for any T4 stranger that pushed. Identity
# is now captured local-only (lib/identity.sh callers other than push) and
# never crosses the D33 boundary on this rail. Future versions may join
# identity server-side via a different transport (see PROTO-024 V2 plan).
#
# v2.18.0: manifest fields written are install_id, project_id,
# project_name_optional, sutra_version, push_count, first_seen, last_seen.
# PRIVACY.md v2.18 amendment discloses these on the opt-in path.

MANIFEST="$DEST/manifest.json"
NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMP=$(mktemp "${DEST}/.manifest-XXXXXX.tmp") || { echo "✗ mktemp failed"; exit 1; }
if [ -f "$MANIFEST" ] && jq -e . "$MANIFEST" >/dev/null 2>&1; then
  jq --arg install_id "$INSTALL_ID" \
     --arg project_id "$PROJECT_ID" \
     --arg project_name "$PROJECT_NAME" \
     --arg version "$VERSION" \
     --arg now "$NOW_ISO" \
     '.install_id = (.install_id // $install_id)
      | .first_seen = (.first_seen // $now)
      | .last_seen = $now
      | .push_count = ((.push_count // 0) + 1)
      | .project_id = $project_id
      | .project_name_optional = $project_name
      | .sutra_version = $version' \
     "$MANIFEST" > "$TMP"
else
  jq -n --arg install_id "$INSTALL_ID" \
        --arg project_id "$PROJECT_ID" \
        --arg project_name "$PROJECT_NAME" \
        --arg version "$VERSION" \
        --arg now "$NOW_ISO" \
        '{install_id:$install_id, first_seen:$now, last_seen:$now, push_count:1,
          project_id:$project_id, project_name_optional:$project_name,
          sutra_version:$version}' > "$TMP"
fi
mv -f "$TMP" "$MANIFEST" || { rm -f "$TMP"; echo "✗ manifest atomic-mv failed"; exit 1; }

if (cd "$CACHE" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" add "clients/$INSTALL_ID" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" commit --quiet -m "telemetry: $INSTALL_ID $TS ($COUNT rows)" && git push --quiet); then
  queue_clear
  echo "✓ pushed $COUNT metrics; queue cleared"
else
  echo "✗ push failed — queue preserved for next attempt"
  exit 1
fi
