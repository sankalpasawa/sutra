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

# v2.13.0 (vinit#38 escalation): jq replaces python3 in the bootstrap path.
# Why: v2.8.11 already moved python3 from heredoc to file form to dodge SIGKILL
# from macOS sandbox/EDR agents, but a 2026-05-01 report (@abhishekshah) showed
# `python3 -c "print('hello')"` itself exits 137 — the python3 binary is killed
# regardless of how it's invoked (quarantine xattr, AV process-name killer, or
# codesign mismatch). File-form vs heredoc is irrelevant when python3 itself
# can't survive exec. jq is widely available, fast, and not subject to these
# heuristics. We fail fast with an install hint if jq is missing rather than
# silently half-bootstrapping.
if ! command -v jq >/dev/null 2>&1; then
  cat >&2 <<'EOF'
sutra start: jq is required but not found on PATH.

Sutra's bootstrap reads/writes .claude/sutra-project.json. We use jq because
python3 is killed by some macOS sandbox/EDR agents (vinit#38), leaving the
project state half-written.

Install:
  macOS:    brew install jq
  Debian:   sudo apt-get install jq
  RHEL:     sudo dnf install jq
  Other:    https://jqlang.org/download/

Then re-run /core:start.
EOF
  exit 127
fi

# Resolve args (profile + force + telemetry)
# v2.9.1+: --telemetry on|off is the explicit opt-in/out switch per founder
# direction 2026-04-30 ("when installing Sutra, give an option to switch on
# the telemetry"). When unset, telemetry defaults OFF (privacy-by-default,
# matches PRIVACY.md v2.0 contract). Profile no longer auto-controls
# telemetry — decoupled.
PROFILE_ARG=""
FORCE=0
TELEMETRY_FLAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE_ARG="${2:-}"; shift 2 ;;
    --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
    --force) FORCE=1; shift ;;
    --telemetry) TELEMETRY_FLAG="${2:-}"; shift 2 ;;
    --telemetry=*) TELEMETRY_FLAG="${1#*=}"; shift ;;
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
       && [ ! -f "$PROJECT_ROOT/go.mod" ] && [ ! -f "$PROJECT_ROOT/CLAUDE.md" ] \
       && [ ! -d "$PROJECT_ROOT/.claude" ]; then
    # v2.8.6 — accept .claude/ as a project marker (vinit#35, 2026-04-28).
    # A directory containing .claude/settings.local.json or .claude/heartbeats
    # is unambiguously a Claude Code project even if it lacks .git/etc.
    REFUSE=1; REASON="no project markers in $PROJECT_ROOT (.git / package.json / pyproject.toml / Cargo.toml / go.mod / CLAUDE.md / .claude/)"
  fi
  if [ "$REFUSE" -eq 1 ]; then
    cat >&2 <<EOF
sutra start: refusing to activate here — $REASON.

Running /core:start in a non-project directory pollutes user-level files
(like ~/.claude/CLAUDE.md) with project-scoped governance, and misnames the
project after your OS username.

Fix: cd into a real project (one with .git/, package.json, pyproject.toml,
Cargo.toml, go.mod, CLAUDE.md, or .claude/), then re-run /core:start.

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

# Telemetry default resolution (v2.9.1+ — decoupled from profile per founder
# direction 2026-04-30):
#   1. --telemetry on|off CLI flag wins
#   2. Else: 0 (off — privacy-by-default, matches PRIVACY.md v2.0 contract)
#   3. Existing .claude/sutra-project.json setting takes precedence over
#      either of the above (handled inside onboard.sh — idempotent preserve)
case "$TELEMETRY_FLAG" in
  on|true|yes|1)  TELEMETRY_DEFAULT=1 ;;
  off|false|no|0|"") TELEMETRY_DEFAULT=0 ;;
  *)
    echo "Invalid --telemetry value: $TELEMETRY_FLAG. Use on|off." >&2
    exit 2
    ;;
esac

# Step 1 — onboard (with explicit-opt-in telemetry default)
SUTRA_AUTO_OPTIN="$TELEMETRY_DEFAULT" bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

# Step 2 — patch .claude/sutra-project.json to persist the profile + telemetry.
# v2.13.0: bash/jq lib (no python3). Atomic writes via mktemp+mv inside the lib.
if [ -f .claude/sutra-project.json ]; then
  bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" patch-profile "$PROFILE" "$TELEMETRY_DEFAULT"
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

# Step 4 — activation banner + next steps. v2.13.0: bash/jq lib.
if [ -f .claude/sutra-project.json ]; then
  bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" banner
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
