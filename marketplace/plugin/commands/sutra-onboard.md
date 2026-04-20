---
name: sutra-onboard
description: First-time setup for Sutra in this project. Generates install_id + project_id, writes .claude/sutra-project.json, prompts for opt-in to telemetry, initializes local queue.
disable-model-invocation: true
---

# /sutra-onboard — Project onboarding

One-command project setup. Run once per new project.

## Actions

1. Compute IDs via `lib/project-id.sh`:

```!
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
source "$PLUGIN_ROOT/lib/project-id.sh"
VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_ROOT/.claude-plugin/plugin.json'))['version'])")
INSTALL_ID=$(compute_install_id "$VERSION")
PROJECT_ID=$(compute_project_id)
echo "install_id: $INSTALL_ID"
echo "project_id: $PROJECT_ID"
```

2. Derive project name from git remote basename, with override:

```!
NAME=$(git config --get remote.origin.url 2>/dev/null | sed -E 's|.*/||; s|\.git$||')
[ -z "$NAME" ] && NAME=$(basename "$PWD")
echo "project_name: $NAME"
```

3. Write `.claude/sutra-project.json`:

```!
mkdir -p .claude
cat > .claude/sutra-project.json <<JSON
{
  "install_id": "$INSTALL_ID",
  "project_id": "$PROJECT_ID",
  "project_name": "$NAME",
  "first_seen": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "sutra_version": "$VERSION",
  "telemetry_optin": false
}
JSON
cat .claude/sutra-project.json
```

4. Initialize local queue:

```!
source "$PLUGIN_ROOT/lib/queue.sh"
queue_init
echo "queue at: $(queue_file) — depth: $(queue_count)"
```

5. Print next-step banner:

```
✓ Sutra onboarded for this project
  install_id: <id>
  project_id: <id>
  project_name: <name>

Telemetry is OFF by default. To turn ON (sends metric-only Layer B rows to
sankalpasawa/sutra-data on /sutra-push):
  edit .claude/sutra-project.json → "telemetry_optin": true

Commands:
  /sutra          — show session status
  /sutra-status   — queue depth + last flush
  /sutra-push     — send queue to sutra-data (manual)
```

## Rules

- Idempotent: running twice on same project is a no-op (IDs are deterministic).
- Does NOT enable telemetry; user must flip the flag explicitly.
- Writes only `.claude/sutra-project.json` in the project; everything else is `~/.sutra/`.
