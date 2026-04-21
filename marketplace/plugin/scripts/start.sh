#!/bin/bash
# Sutra plugin — /core:start (v1.4.0+, profile-aware v1.6.0+)
# THE one command: onboard + telemetry + activation banner + depth marker.
#
# v1.6.0 — honors `profile` from plugin.json userConfig (or --profile arg):
#   individual — warn-only, telemetry OFF (privacy default)
#   project    — warn-only, telemetry ON (observability default)
#   company    — HARD enforcement, telemetry ON
#
# Profile resolution order (highest → lowest priority):
#   1. --profile <name> argument
#   2. CLAUDE_PLUGIN_OPTION_PROFILE env var (Claude Code passes userConfig this way)
#   3. existing value in .claude/sutra-project.json
#   4. default: "project"

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_ROOT"

# Resolve profile
PROFILE_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE_ARG="${2:-}"; shift 2 ;;
    --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
    *) shift ;;
  esac
done

PROFILE="${PROFILE_ARG:-${CLAUDE_PLUGIN_OPTION_PROFILE:-}}"
if [ -z "$PROFILE" ] && [ -f .claude/sutra-project.json ]; then
  if command -v jq >/dev/null 2>&1; then
    PROFILE=$(jq -r '.profile // empty' .claude/sutra-project.json 2>/dev/null)
  fi
fi
[ -z "$PROFILE" ] && PROFILE="project"

# Validate
case "$PROFILE" in
  individual|project|company) ;;
  *)
    echo "Invalid profile: $PROFILE. Must be one of: individual, project, company." >&2
    exit 2
    ;;
esac

# Profile-dependent telemetry default
case "$PROFILE" in
  individual) TELEMETRY_DEFAULT=0 ;;
  project|company) TELEMETRY_DEFAULT=1 ;;
esac

# Step 1 — onboard (with profile-dependent telemetry default)
SUTRA_AUTO_OPTIN="$TELEMETRY_DEFAULT" bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

# Step 2 — patch .claude/sutra-project.json to persist the profile + telemetry
if [ -f .claude/sutra-project.json ]; then
  python3 - "$PROFILE" "$TELEMETRY_DEFAULT" <<'PY'
import json, sys
p = '.claude/sutra-project.json'
profile = sys.argv[1]
telemetry_default = sys.argv[2] == '1'
d = json.load(open(p))
d['profile'] = profile
d['telemetry_optin'] = telemetry_default
open(p, 'w').write(json.dumps(d, indent=2))
PY
fi

# Step 3 — depth marker so the next Edit/Write won't trip PreToolUse warn
mkdir -p .claude
if [ ! -f .claude/depth-registered ]; then
  echo "DEPTH=3 TASK=sutra-start TS=$(date +%s)" > .claude/depth-registered
fi

# Step 4 — activation banner + next steps
if [ -f .claude/sutra-project.json ]; then
  python3 <<PY
import json
d = json.load(open('.claude/sutra-project.json'))
print("🧭 Sutra active")
print(f"   Version:         {d['sutra_version']}")
print(f"   Project:         {d['project_name']}")
print(f"   Install ID:      {d['install_id']}")
print(f"   Project ID:      {d['project_id']}")
print(f"   Profile:         {d.get('profile','project')}")
print(f"   Telemetry:       {'on' if d['telemetry_optin'] else 'off'}  (edit .claude/sutra-project.json to flip)")
print()
print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace, session-retrieve")
profile = d.get('profile','project')
enforcement = "HARD — missing depth marker blocks Edit/Write" if profile == 'company' else "warn-only"
print(f"   Enforcement:     {enforcement}")
print()
print("You're ready. Ask Claude anything — every task goes through governance.")
print()
print("Other commands:")
print("   /core:status      — show install / queue / telemetry state")
print("   /core:update      — pull the latest plugin version")
print("   /core:uninstall   — remove Sutra from this machine")
print("   /core:depth-check — manual depth marker for the next task")
print("   /core:permissions — paste-ready allowlist snippet")
if profile == 'company':
  print()
  print("Escape hatch (one-shot): prefix any tool call with SUTRA_BYPASS=1")
PY
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
