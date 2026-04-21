#!/bin/bash
# Sutra plugin — /core:start (v1.4.0+)
# THE one command: onboard + telemetry ON + activation banner + depth marker.
# Replaces /core:onboard, /core:go, /core:sutra from earlier versions.
#
# Philosophy: users run one command and they're done. Simpler > flexible.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_ROOT"

# Step 1 — project onboarding with telemetry ON by default.
SUTRA_AUTO_OPTIN=1 bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

# Step 2 — force telemetry_optin=true even if .claude/sutra-project.json pre-existed.
if [ -f .claude/sutra-project.json ]; then
  python3 -c "
import json
p = '.claude/sutra-project.json'
d = json.load(open(p))
d['telemetry_optin'] = True
open(p, 'w').write(json.dumps(d, indent=2))
" 2>/dev/null
fi

# Step 3 — depth marker so the next Edit/Write won't trip PreToolUse warn
mkdir -p .claude
if [ ! -f .claude/depth-registered ]; then
  echo "DEPTH=3 TASK=sutra-start TS=$(date +%s)" > .claude/depth-registered
fi

# Step 4 — activation banner + next steps
if [ -f .claude/sutra-project.json ]; then
  python3 <<'PY'
import json
d = json.load(open('.claude/sutra-project.json'))
print("🧭 Sutra active")
print(f"   Version:         {d['sutra_version']}")
print(f"   Project:         {d['project_name']}")
print(f"   Install ID:      {d['install_id']}")
print(f"   Project ID:      {d['project_id']}")
print(f"   Telemetry:       on (edit .claude/sutra-project.json to flip)")
print()
print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace")
print("   Hooks active:    depth-marker-pretool (warn), estimation-stop, posttool-counter")
print()
print("You're ready. Ask Claude anything — every task goes through governance.")
print()
print("Other commands:")
print("   /core:status      — show install / queue / telemetry state")
print("   /core:update      — pull the latest plugin version")
print("   /core:uninstall   — remove Sutra from this machine")
print("   /core:depth-check — manual depth marker for the next task")
PY
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
