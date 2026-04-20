---
name: sutra-push
description: Push queued telemetry metrics to sankalpasawa/sutra-data. Manual, user-initiated. No network work happens in Stop hook per codex v1 architecture.
disable-model-invocation: true
---

# /sutra-push — Manual telemetry push

Transmits the local Layer B queue (`~/.sutra/metrics-queue.jsonl`) to the central store.

## Precondition

`.claude/sutra-project.json` must exist AND `telemetry_optin: true`. Otherwise this is a no-op.

## Actions

```!
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
source "$PLUGIN_ROOT/lib/queue.sh"

if [ ! -f .claude/sutra-project.json ]; then
  echo "no .claude/sutra-project.json — run /sutra-onboard first"
  exit 0
fi

OPTIN=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json')).get('telemetry_optin', False))")
if [ "$OPTIN" != "True" ]; then
  echo "telemetry_optin is false — push skipped (flip in .claude/sutra-project.json to enable)"
  exit 0
fi

INSTALL_ID=$(python3 -c "import json; print(json.load(open('.claude/sutra-project.json'))['install_id'])")
COUNT=$(queue_count)

if [ "$COUNT" -eq 0 ]; then
  echo "queue empty — nothing to push"
  exit 0
fi

echo "pushing $COUNT metrics for install_id $INSTALL_ID..."

# Clone sutra-data (shallow) to cache if missing
CACHE="$HOME/.sutra/sutra-data-cache"
if [ ! -d "$CACHE/.git" ]; then
  git clone --depth 1 --single-branch git@github.com:sankalpasawa/sutra-data.git "$CACHE" 2>&1 | tail -3
else
  git -C "$CACHE" pull --quiet 2>&1 | tail -3
fi

# Write per-push file
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
DEST="$CACHE/clients/$INSTALL_ID"
mkdir -p "$DEST"
cp "$(queue_file)" "$DEST/telemetry-$TS.jsonl"

# Update manifest
python3 <<PY
import json, os, datetime
m_path = "$DEST/manifest.json"
m = {}
if os.path.exists(m_path):
    m = json.load(open(m_path))
m.setdefault('install_id', "$INSTALL_ID")
m.setdefault('first_seen', datetime.datetime.utcnow().isoformat() + "Z")
m['last_seen'] = datetime.datetime.utcnow().isoformat() + "Z"
m['push_count'] = m.get('push_count', 0) + 1
proj = json.load(open(".claude/sutra-project.json"))
m['project_id'] = proj.get('project_id')
m['project_name_optional'] = proj.get('project_name', '')
m['sutra_version'] = proj.get('sutra_version')
open(m_path, 'w').write(json.dumps(m, indent=2))
PY

# Commit + push
(cd "$CACHE" && \
  git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" add "clients/$INSTALL_ID" && \
  git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" commit -m "telemetry: $INSTALL_ID $TS ($COUNT rows)" && \
  git push --quiet)

if [ $? -eq 0 ]; then
  queue_clear
  echo "✓ pushed $COUNT metrics; queue cleared"
else
  echo "✗ push failed — queue preserved for next attempt"
  exit 1
fi
```

## Failure behavior

- Network error → queue kept intact, retry on next `/sutra-push`.
- Git auth error → diagnostic message; user must fix `gh auth status`.
- Never throws on empty queue; always safe to run.
