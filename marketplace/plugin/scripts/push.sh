#!/bin/bash
# Sutra plugin — /sutra-push logic as standalone script.
# Delivers local queue to sankalpasawa/sutra-data (private). Respects opt-in.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

source "$PLUGIN_ROOT/lib/queue.sh"
# v1.9.0+: identity capture (best-effort; never fails push)
if [ -f "$PLUGIN_ROOT/lib/identity.sh" ]; then
  source "$PLUGIN_ROOT/lib/identity.sh"
fi

# v2.0.0: Legacy telemetry gated behind explicit env flag.
# New privacy model (PRIVACY.md): signals captured locally, no auto-push.
# To use legacy push: SUTRA_LEGACY_TELEMETRY=1 bash push.sh
if [ "${SUTRA_LEGACY_TELEMETRY:-0}" != "1" ]; then
  echo "push disabled in v2.0 privacy model — signals stay local"
  echo "to restore legacy behavior: SUTRA_LEGACY_TELEMETRY=1 <cmd>"
  echo "see $PLUGIN_ROOT/PRIVACY.md for new model"
  exit 0
fi

cd "$PROJECT_ROOT"

if [ ! -f .claude/sutra-project.json ]; then
  echo "no .claude/sutra-project.json — run /sutra-onboard first"
  exit 0
fi

OPTIN=$(python3 -c "import json; print('true' if json.load(open('.claude/sutra-project.json')).get('telemetry_optin') else 'false')" 2>/dev/null)
if [ "$OPTIN" != "true" ]; then
  echo "telemetry_optin is false — push skipped"
  echo "(to enable: edit .claude/sutra-project.json → telemetry_optin: true)"
  exit 0
fi

INSTALL_ID=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json'))['install_id'])")
PROJECT_ID=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json'))['project_id'])")
PROJECT_NAME=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json')).get('project_name', ''))")
VERSION=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json'))['sutra_version'])")
COUNT=$(queue_count)

if [ "$COUNT" -eq 0 ]; then
  echo "queue empty — nothing to push"
  exit 0
fi

echo "pushing $COUNT metrics for install_id $INSTALL_ID..."

CACHE="$SUTRA_HOME/sutra-data-cache"
if [ ! -d "$CACHE/.git" ]; then
  git clone --depth 1 --single-branch --quiet git@github.com:sankalpasawa/sutra-data.git "$CACHE" 2>&1 | tail -2
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

# v1.9.0+: refresh identity cache if stale (>7d) or missing. Best-effort.
IDENTITY_CACHE="$SUTRA_HOME/identity.json"
IDENTITY_JSON=""
if declare -f capture_identity >/dev/null 2>&1; then
  if declare -f identity_is_stale >/dev/null 2>&1 && identity_is_stale "$IDENTITY_CACHE" 604800; then
    IDENTITY_JSON=$(capture_identity "$VERSION" 2>/dev/null)
    if [ -n "$IDENTITY_JSON" ]; then
      mkdir -p "$SUTRA_HOME" 2>/dev/null
      printf '%s\n' "$IDENTITY_JSON" > "$IDENTITY_CACHE" 2>/dev/null
      chmod 600 "$IDENTITY_CACHE" 2>/dev/null || true
    fi
  elif [ -f "$IDENTITY_CACHE" ]; then
    IDENTITY_JSON=$(cat "$IDENTITY_CACHE" 2>/dev/null)
  fi
fi

python3 - "$DEST/manifest.json" "$INSTALL_ID" "$PROJECT_ID" "$PROJECT_NAME" "$VERSION" "$IDENTITY_JSON" <<'PY'
import json, os, datetime, sys
m_path, install_id, project_id, project_name, version, identity_json = sys.argv[1:7]
m = {}
if os.path.exists(m_path):
    try: m = json.load(open(m_path))
    except: pass
m.setdefault('install_id', install_id)
m.setdefault('first_seen', datetime.datetime.utcnow().isoformat() + "Z")
m['last_seen'] = datetime.datetime.utcnow().isoformat() + "Z"
m['push_count'] = m.get('push_count', 0) + 1
m['project_id'] = project_id
m['project_name_optional'] = project_name
m['sutra_version'] = version
# v1.9.0: stamp identity block if captured
if identity_json:
    try:
        m['identity'] = json.loads(identity_json)
    except Exception:
        pass
open(m_path, 'w').write(json.dumps(m, indent=2))
PY

if (cd "$CACHE" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" add "clients/$INSTALL_ID" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" commit --quiet -m "telemetry: $INSTALL_ID $TS ($COUNT rows)" && git push --quiet); then
  queue_clear
  echo "✓ pushed $COUNT metrics; queue cleared"
else
  echo "✗ push failed — queue preserved for next attempt"
  exit 1
fi
