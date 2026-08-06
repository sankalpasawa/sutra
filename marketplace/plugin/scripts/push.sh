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

# v2.68.0 (founder direction 2026-08-06): telemetry is ON by default —
# opt-out model. A missing telemetry_optin key means enabled; only an
# explicit `"telemetry_optin": false` (or SUTRA_TELEMETRY=0, checked above)
# disables. Identity fields remain strictly consent-gated below.
OPTIN=$(jq -r '.telemetry_optin // true' .claude/sutra-project.json 2>/dev/null)
if [ "$OPTIN" = "false" ]; then
  echo "telemetry_optin is false (explicit opt-out) — push skipped"
  echo "(to re-enable: re-run /core:start --telemetry on)"
  exit 0
fi

# v2.33.0 (D50): re-consent gate — codex P1-1 fold. Pre-v2.33 opt-ins consented
# under PRIVACY.md v2.18.0 ("identity NOT pushed"); they must NOT silently
# begin pushing identity on first post-upgrade push. Block when consent_version
# missing or older than 2.33. User re-runs /core:start --telemetry on to write
# consent_version="2.33" and acknowledge the new disclosure.
CONSENT_VERSION=$(jq -r '.consent_version // ""' .claude/sutra-project.json 2>/dev/null)
# Numeric MAJ.MIN compare. Future bumps (2.34, 3.0, ...) work natively.
_consent_ok=0
if [ -n "$CONSENT_VERSION" ]; then
  _cv_maj="${CONSENT_VERSION%%.*}"
  _cv_min="${CONSENT_VERSION#*.}"
  if [ "$_cv_maj" -eq "$_cv_maj" ] 2>/dev/null && [ "$_cv_min" -eq "$_cv_min" ] 2>/dev/null; then
    if [ "$_cv_maj" -gt 2 ] || { [ "$_cv_maj" -eq 2 ] && [ "$_cv_min" -ge 33 ]; }; then
      _consent_ok=1
    fi
  fi
fi
# v2.68.0: without v2.33+ consent the push proceeds ANONYMOUSLY (metric
# rows only, no identity block) instead of blocking entirely. Identity
# still crosses the wire only after explicit /core:start --telemetry on
# re-consent — the v2.33 disclosure contract is unchanged.
PUSH_IDENTITY="$_consent_ok"
if [ "$PUSH_IDENTITY" -eq 0 ]; then
  cat <<'EOF'
telemetry: pushing anonymous metric rows (default-on, v2.68.0).
  Identity fields are NOT included — they require explicit consent:
    /core:start --telemetry on   (acknowledges PRIVACY.md v2.33 disclosure)
  To opt out of telemetry entirely:
    set telemetry_optin=false in .claude/sutra-project.json
    OR set SUTRA_TELEMETRY=0 (kill-switch, both rails)
EOF
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

# v2.33.0 (D50): identity-on-wire with strict 4-field allowlist (codex P1-2
# fold). Reverses v2.2.0 PROTO-024 H2 strip ONLY for the 4 fields founder
# explicitly authorized. capture_identity() emits 14 fields; we extract ONLY
# git_user_name, github_login, github_id, git_user_email_hash. The other 10
# (hostname_hash, os_name, os_version, os_pretty, arch, shell_name, locale,
# tz, captured_at, captured_by_version) stay local. Re-consent gate above
# ensures pre-v2.33 opt-ins re-acknowledge before identity crosses (codex
# P1-1 fold). Log hygiene (codex P2-3 #6): NEVER print IDENTITY_4 to
# stdout/stderr.
IDENTITY_4="{}"
# v2.68.0: identity is captured ONLY on the consented path (PUSH_IDENTITY=1).
# Default-on anonymous pushes carry IDENTITY_4="{}" — nothing to strip later.
if [ "${PUSH_IDENTITY:-0}" -eq 1 ] && declare -f capture_identity >/dev/null 2>&1; then
  _identity_full=$(capture_identity "$VERSION" 2>/dev/null)
  if [ -n "$_identity_full" ] && printf '%s' "$_identity_full" | jq -e . >/dev/null 2>&1; then
    _identity_4=$(printf '%s' "$_identity_full" | jq '{git_user_name, github_login, github_id, git_user_email_hash}' 2>/dev/null)
    [ -n "$_identity_4" ] && IDENTITY_4="$_identity_4"
  fi
fi
# Manifest fields written on opt-in v2.33+ path: install_id, project_id,
# project_name_optional, sutra_version, push_count, first_seen, last_seen,
# identity:{git_user_name, github_login, github_id, git_user_email_hash}.
# PRIVACY.md v2.33.0 amendment discloses these.

MANIFEST="$DEST/manifest.json"
NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMP=$(mktemp "${DEST}/.manifest-XXXXXX.tmp") || { echo "✗ mktemp failed"; exit 1; }
if [ -f "$MANIFEST" ] && jq -e . "$MANIFEST" >/dev/null 2>&1; then
  jq --arg install_id "$INSTALL_ID" \
     --arg project_id "$PROJECT_ID" \
     --arg project_name "$PROJECT_NAME" \
     --arg version "$VERSION" \
     --arg now "$NOW_ISO" \
     --argjson identity "$IDENTITY_4" \
     '.install_id = (.install_id // $install_id)
      | .first_seen = (.first_seen // $now)
      | .last_seen = $now
      | .push_count = ((.push_count // 0) + 1)
      | .project_id = $project_id
      | .project_name_optional = $project_name
      | .sutra_version = $version
      | .identity = $identity' \
     "$MANIFEST" > "$TMP"
else
  jq -n --arg install_id "$INSTALL_ID" \
        --arg project_id "$PROJECT_ID" \
        --arg project_name "$PROJECT_NAME" \
        --arg version "$VERSION" \
        --arg now "$NOW_ISO" \
        --argjson identity "$IDENTITY_4" \
        '{install_id:$install_id, first_seen:$now, last_seen:$now, push_count:1,
          project_id:$project_id, project_name_optional:$project_name,
          sutra_version:$version, identity:$identity}' > "$TMP"
fi
mv -f "$TMP" "$MANIFEST" || { rm -f "$TMP"; echo "✗ manifest atomic-mv failed"; exit 1; }

if (cd "$CACHE" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" add "clients/$INSTALL_ID" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" commit --quiet -m "telemetry: $INSTALL_ID $TS ($COUNT rows)" && git push --quiet); then
  queue_clear
  echo "✓ pushed $COUNT metrics; queue cleared"
else
  echo "✗ push failed — queue preserved for next attempt"
  exit 1
fi
