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
INSTALL_OS=0
INSTALL_GATES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE_ARG="${2:-}"; shift 2 ;;
    --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
    --force) FORCE=1; shift ;;
    --os) INSTALL_OS=1; shift ;;
    --git-gates) INSTALL_GATES=1; shift ;;
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

# Step 3 — depth marker so the next Edit/Write won't trip PreToolUse warn.
# Phase-2 marker-race fix (holding/research/2026-07-30-marker-race-root-cause.md
# §6 phase 2): this bootstrap was sid-blind — it wrote only the legacy global
# .claude/depth-registered, unstamped, which any concurrent session's reset
# could delete as "unowned". Source marker-lib defensively and write via
# sutra_marker_write (session-scoped + SESSION-stamped; dual-write keeps the
# legacy global twin for un-migrated readers). Fail-open fallback stamps
# SESSION= best-effort so the marker is never left unowned.
mkdir -p .claude
MARKER_LIB="$PLUGIN_ROOT/hooks/marker-lib.sh"
if [ -f "$MARKER_LIB" ]; then . "$MARKER_LIB" 2>/dev/null || true; fi
if command -v sutra_marker_write >/dev/null 2>&1; then
  sutra_marker_has depth-registered 2>/dev/null || \
    sutra_marker_write depth-registered "DEPTH=3 TASK=sutra-start" 2>/dev/null || true
elif [ ! -f .claude/depth-registered ]; then
  echo "DEPTH=3 TASK=sutra-start SESSION=${CLAUDE_CODE_SESSION_ID:-} TS=$(date +%s)" > .claude/depth-registered
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

Apply these behaviors in EVERY response in this project. Marker-delimited, managed by the plugin; manual edits inside are overwritten on the next `/core:start`. Enforcement is HARD for Input Routing, Depth, FLOW and BLUEPRINT (D63): those blocks are floored by Stop / PreToolUse hooks — a turn that skips one is blocked and redone once (loop-safe). **The H-Sutra header is convention only** — its Stop hook was removed on 2026-07-28. Enforcement activates only AFTER `/core:start` (which writes this block), so you always have the contract before it is enforced. Per-block kill-switches: see SUTRA-DEFAULTS.md.

## H-Sutra Header — the LITERAL FIRST line of every response

Every response MUST begin with this bracketed header as its first text — before any prose, any other block, or any tool call. **Convention only, not enforced** (2026-07-28): the `h-sutra-enforce` Stop hook was removed. Nothing blocks or redoes a response for a missing or malformed header; the header is still logged for classification by `per-turn-discipline-prompt.sh`.

```
[<DIRECTION>·<VERB> · TIMING:<when> · CHANNEL:<how> · REV:<reversibility> · RISK:<level>]
```

- **DIRECTION** (UPPERCASE): `INBOUND` (from the user) · `INTERNAL` · `OUTBOUND` (to a third party) — or an UPPERCASE actor (e.g. `FOUNDER`, `ASAWA`) or a decision id (e.g. `D48`).
- **VERB** (UPPERCASE): `QUERY` · `ASSERT` · `DIRECT` (add others as needed).
- **TIMING**: `now` · `later` · `scheduled`.  **CHANNEL**: `in-band` · `out-of-band` · `cli`.  **REV**: `reversible` · `irreversible` · `none`.  **RISK**: `low` · `med` · `high`.
- DIRECTION and VERB must be **UPPERCASE** (letters/digits/hyphens). Case errors are the most common cause of a block.

Example: `[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]`

If you must stop and clarify before acting, use: `[STAGE-1-FAIL · CLARIFY · attempt:1/1]`

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

## FLOW — inline block every turn, after Input Routing (HARD)

Emit as literal text (NOT a skill call): the honest resolved spine —
[1] TYPE/cell · [2] FOLLOW <skill> | CONSTRUCT · [3] steps · [4] inner lens/cynefin/factors · [5] mode · [6] close.
Invoke the full core:flow skill only for substantive / multi-step / ambiguous work.
Floor: flow-stop-check.sh (Stop) + flow-gate.sh (PreToolUse Edit|Write|Task).

## BLUEPRINT — before Edit/Write/Bash/Agent when tool calls are planned (HARD)

Doing / Steps (each with a `Verify:` check at Depth >= 3) / Output-looks-like / Verified-by / Scale / Stops-if.
Floor: blueprint-check.sh (PreToolUse; HARD on foundational paths).

## Build-Layer marker — editing plugin / hooks / scripts / skills paths (HARD)

Declare L0 | L1 | L2 + activation scope before the edit. Floor: build-layer-check.sh.

## Codex consult — at Depth >= 3 before Edit/Write (HARD, degrades)

Run a real codex consult (/core:codex-sutra) before the first Depth-3+ Edit/Write; a successful run writes the satisfying marker. On machines without the codex binary the gate degrades to pass (never bricks). Floor: codex-consult-gate.sh (PreToolUse Edit|Write).

## PLACEMENT — one line per unit of work (ADR-028)

```
PLACEMENT: <domain path> | "<charter title>"
```

Every unit of work carries an address. If nothing matches, write exactly: `PLACEMENT: unresolved (no-match)` — never fabricate a path. Floor: placement-gate.sh + placement-stop-check.sh.

## DISPATCH + Work-Atom — before the first mutation of a unit

Open a Work-Atom before the first Edit/Write of a unit and close it through its pre-declared verify when the unit ends: `bin/sutra-atom open --goal <observable outcome> --verify-template <kind> ...`, then `bin/sutra-dispatch resolve` + `bind`. The frozen envelope — not the live intent — is the mutation authority. Floor: atom-floor.sh + dispatch-gate.sh (degrade to pass where the CLIs are absent).

## Marker lifecycle — session-scoped writes

Write marker files via the Write tool to `.claude/sessions/<CLAUDE_CODE_SESSION_ID>/<name>`, always including a `SESSION=<session-id>` line. Markers persist within a turn and reset on the next user prompt. Never write the shared `.claude/<name>` twin directly — dual-write maintains it.

## Readability Gate — apply at output time

- Tables over paragraphs when ≥3 rows of comparable data
- Numbers over adjectives
- Progress bars for scores: `Name ▓▓▓▓▓▓░░░░ 0.6 STATUS`
- Decisions in boxed callouts (impossible to miss)
- Structure-First (D55): when adding anything — survey > reorganize > simplify > surface
- Skill-explain: a 4-line WHAT / WHY / EXPECT / ASKS card before invoking any skill
- Right-effort (Karpathy): think-first, simpler-alt, surgical-scope, verify-loop before Edit

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

# Step 3.7 — company operating scaffold (W2 parity, 2026-08-25).
# Only-if-absent per file: a re-run NEVER overwrites user content.
materialize_company_os() {
  local tdir="$PLUGIN_ROOT/templates/os"
  local dest="$PROJECT_ROOT/os"
  [ -d "$tdir" ] || return 0
  local created=0 rel
  for rel in TODO.md DIRECTIONS.md SYSTEM-MAP.md departments/DEPARTMENT-REGISTRY.md; do
    if [ ! -f "$dest/$rel" ]; then
      mkdir -p "$dest/$(dirname "$rel")"
      cp "$tdir/$rel" "$dest/$rel"
      created=$((created+1))
    fi
  done
  mkdir -p "$dest/state"
  [ -f "$dest/state/.gitkeep" ] || : > "$dest/state/.gitkeep"
  echo "company OS scaffold: $created file(s) created under os/ (existing files untouched)"
}

# Step 3.8 — git test gates via stable shim (W2 parity, 2026-08-25).
# The plugin cache path changes per version, so out-of-repo callers go through
# ~/.sutra/bin/sutra-test-gate which resolves the newest installed plugin.
install_git_gates() {
  [ -e "$PROJECT_ROOT/.git" ] || { echo "git gates: no .git here — skipped"; return 0; }
  mkdir -p "$PROJECT_ROOT/.githooks" "$HOME/.sutra/bin"
  cat > "$HOME/.sutra/bin/sutra-test-gate" <<'SHIMEOF'
#!/usr/bin/env bash
# stable shim -> newest installed Sutra core plugin (managed by /core:start)
latest=$(ls -d "$HOME"/.claude/plugins/cache/sutra/core/*/bin/sutra-test-gate 2>/dev/null | sort -V | tail -1)
[ -n "$latest" ] && exec bash "$latest" "$@"
exit 0
SHIMEOF
  chmod +x "$HOME/.sutra/bin/sutra-test-gate"
  local stage f
  for stage in pre-commit pre-push; do
    f="$PROJECT_ROOT/.githooks/$stage"
    if [ ! -f "$f" ]; then
      printf '#!/usr/bin/env bash\nexec "$HOME/.sutra/bin/sutra-test-gate" %s\n' "$stage" > "$f"
      chmod +x "$f"
    fi
  done
  local current
  current=$(git -C "$PROJECT_ROOT" config core.hooksPath 2>/dev/null || true)
  if [ -z "$current" ]; then
    git -C "$PROJECT_ROOT" config core.hooksPath .githooks
    echo "git gates: core.hooksPath -> .githooks (pre-commit + pre-push; arm by setting test_command in .claude/sutra-project.json)"
  elif [ "$current" = ".githooks" ]; then
    echo "git gates: already installed"
  else
    echo "git gates: core.hooksPath is already \"$current\" — left untouched; call ~/.sutra/bin/sutra-test-gate from your existing hooks to arm the gate"
  fi
}

if [ "$PROFILE" = "company" ] || [ "$INSTALL_OS" = 1 ]; then materialize_company_os; fi
if [ "$PROFILE" = "company" ] || [ "$INSTALL_GATES" = 1 ]; then install_git_gates; fi

# Step 4 — activation banner + next steps. v2.13.0: bash/jq lib.
if [ -f .claude/sutra-project.json ]; then
  bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" banner
else
  echo "onboard failed — check CLAUDE_PROJECT_DIR and plugin install"
  exit 1
fi
