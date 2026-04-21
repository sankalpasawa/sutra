#!/bin/bash
# Sutra plugin — /sutra:sutra-go — one-shot: onboard + enable telemetry + announce.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

cd "$PROJECT_ROOT"

SUTRA_AUTO_OPTIN=1 bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

if [ -f .claude/sutra-project.json ]; then
  python3 -c "
import json
p = '.claude/sutra-project.json'
d = json.load(open(p))
d['telemetry_optin'] = True
open(p, 'w').write(json.dumps(d, indent=2))
" 2>/dev/null
fi

if [ -f .claude/sutra-project.json ]; then
  python3 -c "
import json
d = json.load(open('.claude/sutra-project.json'))
print('Sutra deployed + telemetry ON')
print(f'  install_id:      {d[\"install_id\"]}')
print(f'  project_id:      {d[\"project_id\"]}')
print(f'  project_name:    {d[\"project_name\"]}')
print(f'  sutra_version:   {d[\"sutra_version\"]}')
print(f'  telemetry_optin: {d[\"telemetry_optin\"]}')
print()
print('Auto-emission is ON. Telemetry auto-pushes on Stop; run `sutra push` manually if needed.')
"
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
