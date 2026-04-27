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

# Resolve args (profile + force)
PROFILE_ARG=""
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE_ARG="${2:-}"; shift 2 ;;
    --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
    --force) FORCE=1; shift ;;
    *) shift ;;
  esac
done

# Project-root guard (v2.1.1 — fleet feedback 2026-04-25 + codex review):
# Running /core:start from $HOME poisons ~/.claude/CLAUDE.md with project-scoped
# governance and misnames the project after the OS username. Refuse to activate
# in home/non-project dirs unless --force is passed. Idempotent re-runs on an
# already-initialized project are always allowed (presence of .claude/sutra-
# project.json is the "already onboarded" signal).
#
# Path comparison uses canonical (symlink-resolved) paths to prevent bypass
# via trailing slash, /tmp vs /private/tmp, or $HOME symlink tricks.
# .git check uses -e (not -d) so worktrees/submodules — where .git is a FILE
# pointing at the real gitdir — also count as valid project markers.
canon() {
  if [ -d "$1" ]; then
    (cd "$1" 2>/dev/null && pwd -P) || printf '%s' "$1"
  else
    printf '%s' "$1"
  fi
}
if [ "$FORCE" -ne 1 ] && [ ! -f "$PROJECT_ROOT/.claude/sutra-project.json" ]; then
  REFUSE=0; REASON=""
  PR_CANON=$(canon "$PROJECT_ROOT")
  HOME_CANON=$(canon "$HOME")
  if [ "$PR_CANON" = "$HOME_CANON" ]; then
    REFUSE=1; REASON="you're in your home directory ($HOME)"
  elif [ "$PR_CANON" = "/" ] || [ "$PR_CANON" = "/tmp" ] || [ "$PR_CANON" = "/private/tmp" ]; then
    REFUSE=1; REASON="you're at $PROJECT_ROOT — not a project"
  elif [ ! -e "$PROJECT_ROOT/.git" ] && [ ! -f "$PROJECT_ROOT/package.json" ] \
       && [ ! -f "$PROJECT_ROOT/pyproject.toml" ] && [ ! -f "$PROJECT_ROOT/Cargo.toml" ] \
       && [ ! -f "$PROJECT_ROOT/go.mod" ] && [ ! -f "$PROJECT_ROOT/CLAUDE.md" ]; then
    REFUSE=1; REASON="no project markers in $PROJECT_ROOT (.git / package.json / pyproject.toml / Cargo.toml / go.mod / CLAUDE.md)"
  fi
  if [ "$REFUSE" -eq 1 ]; then
    cat >&2 <<EOF
sutra start: refusing to activate here — $REASON.

Running /core:start in a non-project directory pollutes user-level files
(like ~/.claude/CLAUDE.md) with project-scoped governance, and misnames the
project after your OS username.

Fix: cd into a real project (one with .git/, package.json, pyproject.toml,
Cargo.toml, go.mod, or CLAUDE.md), then re-run /core:start.

Override (not recommended): re-run with --force.
EOF
    exit 2
  fi
fi

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

# Step 3.5 — write/update managed governance block in .claude/CLAUDE.md
# (v1.9.2, Finding #22: Claude Code's Skill tool doesn't auto-invoke skills per
#  turn — it fires on semantic match. CLAUDE.md IS loaded as system context on
#  every session, so that's the mechanism that guarantees governance blocks emit
#  on every response. This function is idempotent via marker delimiters.)
ensure_project_claude_md() {
  local claude_md="${PROJECT_ROOT}/.claude/CLAUDE.md"
  local begin_marker='<!-- SUTRA GOVERNANCE (managed by /core:start — do not edit manually) -->'
  local end_marker='<!-- /SUTRA GOVERNANCE -->'

  mkdir -p "$(dirname "$claude_md")"

  # Governance block body (between the markers). Triple-single-quoted heredoc
  # keeps Markdown fences and placeholders verbatim.
  local block
  block=$(cat <<'GOVBLOCK'
# Sutra governance (auto-managed by /core:start)

Apply these behaviors in every response in this project. The block is marker-delimited and managed by the plugin; manual edits inside will be overwritten on the next `/core:start`.

## Input Routing — emit BEFORE any response or tool call

```
INPUT: [paraphrase of what the user said]
TYPE: direction | task | feedback | new concept | question
EXISTING HOME: [where this already lives in the system, or 'none']
ROUTE: [which skill / protocol / tool handles this]
FIT CHECK: [what changes in the existing architecture]
ACTION: [what you're about to do]
```

## Depth Estimation — emit BEFORE any multi-step task

```
TASK: "[what you're about to do]"
DEPTH: X/5  (1=surface · 2=considered · 3=thorough · 4=rigorous · 5=exhaustive)
EFFORT: [time estimate], [files estimate]
COST: ~$X (~Y% of $200 plan)
IMPACT: [what this changes and for whom]
```

## Readability Gate — apply at output time

- Tables over paragraphs when ≥3 rows of comparable data
- Numbers over adjectives
- Progress bars for scores: `Name ▓▓▓▓▓▓░░░░ 0.6 STATUS`
- Decisions in boxed callouts (impossible to miss)

## Output Trace — one line at end of every response

```
OS: [route] > [domain] > [node count] > [terminal] > [output]
```

Example: `OS: Input Routing (task) > Depth 3 > 2 tool calls > Readability gate > 1 file written`
GOVBLOCK
)

  if [ ! -f "$claude_md" ]; then
    # File doesn't exist — create with block between markers.
    {
      printf '%s\n\n' "$begin_marker"
      printf '%s\n\n' "$block"
      printf '%s\n' "$end_marker"
    } > "$claude_md"
    echo "governance block written at $claude_md (new file)"
    return 0
  fi

  if grep -qF "$begin_marker" "$claude_md" && grep -qF "$end_marker" "$claude_md"; then
    # Markers present — replace everything between them (inclusive) with a fresh
    # managed block. awk preserves all content outside the markers exactly.
    local tmp
    tmp=$(mktemp)
    BEGIN_MARKER="$begin_marker" END_MARKER="$end_marker" BLOCK="$block" \
      awk '
        BEGIN {
          begin_m = ENVIRON["BEGIN_MARKER"]
          end_m   = ENVIRON["END_MARKER"]
          block   = ENVIRON["BLOCK"]
          inside  = 0
          emitted = 0
        }
        {
          if (inside == 0) {
            if ($0 == begin_m) {
              inside = 1
              if (emitted == 0) {
                print begin_m
                print ""
                print block
                print ""
                print end_m
                emitted = 1
              }
              next
            }
            print
            next
          } else {
            if ($0 == end_m) {
              inside = 0
              next
            }
            next
          }
        }
      ' "$claude_md" > "$tmp"
    mv "$tmp" "$claude_md"
    echo "governance block updated at $claude_md (markers replaced)"
    return 0
  fi

  # File exists but has no markers — append the managed block at EOF.
  {
    printf '\n%s\n\n' "$begin_marker"
    printf '%s\n\n' "$block"
    printf '%s\n' "$end_marker"
  } >> "$claude_md"
  echo "governance block appended at $claude_md (no prior markers)"
}

ensure_project_claude_md

# Step 4 — activation banner + next steps
if [ -f .claude/sutra-project.json ]; then
  python3 <<PY
import json, os, shutil
d = json.load(open('.claude/sutra-project.json'))
print("🧭 Sutra active")
print(f"   Version:         {d['sutra_version']}")
print(f"   Project:         {d['project_name']}")
print(f"   Install ID:      {d['install_id']}")
print(f"   Project ID:      {d['project_id']}")
print(f"   Profile:         {d.get('profile','project')}")
# v2.7.3 honesty (vinit#9): banner reflects actual v2.0+ privacy model — push is
# disabled regardless of telemetry_optin flag; legacy push only via env opt-in.
if d.get('telemetry_optin') and os.environ.get('SUTRA_LEGACY_TELEMETRY') == '1':
    _tel = "on — legacy push active (SUTRA_LEGACY_TELEMETRY=1)"
elif d.get('telemetry_optin'):
    _tel = "local-only — push disabled in v2.0 privacy model (see PRIVACY.md)"
else:
    _tel = "off"
print(f"   Telemetry:       {_tel}")
# v2.7.3 honesty (vinit#7): RTK rewrite is opt-in external dep, not bundled.
_rtk_active = shutil.which('rtk') is not None and not os.path.exists(os.path.expanduser('~/.rtk-disabled'))
print(f"   RTK rewrite:     {'active' if _rtk_active else 'inactive — rtk binary not installed (opt-in; see README)'}")
print()
print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace")
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
