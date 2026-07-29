#!/bin/bash
# placement-gate.sh -- the Placement enforcement hook (ADR-028)
#
# Canon:   sutra/os/decisions/ADR-028-mandatory-work-placement.md
#          sutra/os/native/primitives/placement.md (I-P1, I-P3)
#          sutra/os/native/blocks/B19-work-placement.md
# Event:   PreToolUse on Edit|Write|Bash(mutating)
# Schema:  sutra-defaults.json .per_turn_blocks.placement
#
# ENFORCEMENT LADDER (deepseek consult 2026-07-29, P1). This hook ships in WARN
# mode. A new HARD gate delivered fleet-wide would deadlock repos on day zero:
# the model has never been required to emit the PLACEMENT block, so the first
# miss would block the next Edit behind an opaque exit-2. Instead:
#
#   warn  (default)  -> log + stderr notice, exit 0. Never blocks.
#   hard             -> exit 2 on a missing marker, like flow-gate.
#
# Mode lives in .claude/placement-mode. A repo auto-promotes warn->hard once it
# has accumulated `promote_after_compliant_turns` (default 50) turns that DID
# carry the marker. Compliance is measured before it is punished.
#
# WHAT IT CHECKS: presence of the placement marker, nothing else. It does NOT
# parse the block's content (deepseek P2) -- a malformed placement passes here
# and is caught by a separate lint pass, never at the tool-execution boundary.
# A gate that parses is a gate that breaks on formatting.
#
# The gate blocks on a missing DECLARATION, never on a missing domain: B19's
# mint path guarantees a declaration always resolves, so "no domain matched" is
# not a blocking condition anywhere in this feature (I-P3 never-stops).
#
# Markers: delegated to marker-lib.sh (Scheme A, session-scoped). Two sessions
# in one repo previously clobbered each other's per-turn markers -- observed
# live and it deadlocked a build twice. Do NOT invent a second scheme here.
#
# Kill-switches (repo-local preferred; deepseek P2):
#   - .claude/placement-disabled     (per-repo  <- preferred)
#   - $HOME/.placement-disabled      (per-machine, ALL projects)
#   - PLACEMENT_DISABLED=1           (per-shell env)
# Override:
#   - PLACEMENT_ACK=1 PLACEMENT_ACK_REASON='<why>'  (audit-logged)

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

LEDGER="$REPO_ROOT/.enforcement/placement/gate-log.jsonl"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
_log() { mkdir -p "$(dirname "$LEDGER")" 2>/dev/null; printf '%s\n' "$1" >> "$LEDGER" 2>/dev/null; }

# -- Kill-switches (repo-local wins; global disables every project) ----------
[ -n "${PLACEMENT_DISABLED:-}" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0

# -- Override (audit-logged bypass) -----------------------------------------
if [ "${PLACEMENT_ACK:-0}" = "1" ]; then
  REASON=$(printf '%s' "${PLACEMENT_ACK_REASON:-no-reason}" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
  _log "{\"ts\":\"$TS\",\"event\":\"placement-override\",\"reason\":\"$REASON\",\"session\":\"${CLAUDE_SESSION_ID:-unknown}\"}"
  exit 0
fi

PAYLOAD=$(cat 2>/dev/null || true)
command -v jq >/dev/null 2>&1 || exit 0   # no jq: fail-open on infrastructure

TOOL_NAME=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null)
[ -z "$TOOL_NAME" ] && exit 0

# -- Marker lib (Scheme A, session-scoped). Sourced defensively: this script
#    runs under `set -u`, and an aborted PreToolUse hook blocks the user's tool
#    call. A governance gate may block on missing discipline; it must never
#    block because its own infrastructure errored.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$PAYLOAD" || true
  set -u
fi
placement_marker_exists() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    sutra_marker_has placement-registered; return $?
  fi
  [ -f "$REPO_ROOT/.claude/placement-registered" ]
}

# -- Scope: which tool calls does placement gate? ----------------------------
# Edit/Write always. Bash only when the command MUTATES the workspace --
# "bash-mutation" was undefined in the original plan (deepseek P1) and an
# unspecified classifier is either too broad (blocks `ls`) or too narrow
# (misses `git push`). Explicit lists, deny-biased on ambiguity.
is_mutating_bash() {
  local cmd="$1"
  # strip quotes/backslashes so `git   commit` and `git "commit"` both match
  local n; n=$(printf '%s' "$cmd" | tr -s '[:space:]' ' ' | tr -d '"'"'"'\\')

  # (1) REDIRECTION FIRST. This must precede the read-only verb allowlist:
  #     `echo hi > out.txt` starts with a read-only verb but writes a file.
  #     Checking verbs first lets every `<readonly-verb> > path` through — a
  #     hole the F2.13 fixture caught. Discard harmless stream redirections
  #     (/dev/null, fd dups) before deciding.
  local r; r=$(printf '%s' "$n" | sed -e 's/[0-9]*>>*[[:space:]]*\/dev\/null//g' -e 's/[0-9]*>&[0-9-]//g')
  case "$r" in *\>*) return 0 ;; esac

  # (2) explicit read-only verbs -> never gate. Bootstrap safety: markers are
  #     written through these, and gating them deadlocks the first turn.
  case "$n" in
    ls\ *|ls|cat\ *|grep\ *|rg\ *|find\ *|wc\ *|head\ *|tail\ *|jq\ *|stat\ *|echo\ *|printf\ *|which\ *|env|pwd|date*) return 1 ;;
    git\ status*|git\ log*|git\ diff*|git\ show*|git\ rev-parse*|git\ config\ --get*|git\ stash\ list*) return 1 ;;
  esac

  # (3) explicit mutating verbs
  case "$n" in
    rm\ *|mv\ *|cp\ *|mkdir\ *|rmdir\ *|touch\ *|tee\ *|truncate\ *|chmod\ *|chown\ *|ln\ *) return 0 ;;
    sed\ -i*|perl\ -i*|*\ --delete*|find\ *-delete*|find\ *-exec\ rm*) return 0 ;;
    git\ commit*|git\ push*|git\ checkout*|git\ reset*|git\ rebase*|git\ merge*|git\ apply*|git\ am*|git\ mv*|git\ rm*|git\ clean*|git\ stash*|git\ restore*|git\ cherry-pick*|git\ tag*|git\ branch\ -d*) return 0 ;;
    npm\ i*|npm\ install*|npm\ publish*|pip\ install*|brew\ install*|cargo\ publish*) return 0 ;;
  esac
  return 1
}

case "$TOOL_NAME" in
  Edit|Write|MultiEdit|NotebookEdit) ;;
  Bash)
    CMD=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null)
    is_mutating_bash "$CMD" || exit 0
    ;;
  *) exit 0 ;;
esac

# -- Whitelist: governance bookkeeping never needs its own placement ---------
FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$FILE_PATH" in
  */.claude/*|*/.enforcement/*|*/.analytics/*|*/holding/checkpoints/*|*/holding/state/*|*.lock) exit 0 ;;
esac

# -- Compliance accounting + mode -------------------------------------------
MODE_FILE="$REPO_ROOT/.claude/placement-mode"
COUNT_FILE="$REPO_ROOT/.enforcement/placement/compliant-turns"
PROMOTE_AFTER="${PLACEMENT_PROMOTE_AFTER:-50}"
MODE="warn"
[ -f "$MODE_FILE" ] && MODE=$(tr -d '[:space:]' < "$MODE_FILE" 2>/dev/null)
case "$MODE" in hard|warn) ;; *) MODE="warn" ;; esac

if placement_marker_exists; then
  # compliant turn -- count it, and auto-promote once the repo has earned it
  if [ "$MODE" = "warn" ]; then
    mkdir -p "$(dirname "$COUNT_FILE")" 2>/dev/null
    N=0; [ -f "$COUNT_FILE" ] && N=$(tr -cd '0-9' < "$COUNT_FILE" 2>/dev/null)
    [ -z "$N" ] && N=0
    N=$((N + 1)); printf '%s\n' "$N" > "$COUNT_FILE" 2>/dev/null
    if [ "$N" -ge "$PROMOTE_AFTER" ]; then
      printf 'hard\n' > "$MODE_FILE" 2>/dev/null
      _log "{\"ts\":\"$TS\",\"event\":\"placement-mode-promoted\",\"from\":\"warn\",\"to\":\"hard\",\"compliant_turns\":$N}"
      printf '\nPLACEMENT: %s compliant turns reached — enforcement promoted warn -> HARD for this repo.\n  Revert: echo warn > .claude/placement-mode\n\n' "$N" >&2
    fi
  fi
  exit 0
fi

# -- Marker missing ----------------------------------------------------------
_log "{\"ts\":\"$TS\",\"event\":\"placement-miss\",\"tool\":\"$TOOL_NAME\",\"mode\":\"$MODE\",\"session\":\"${CLAUDE_SESSION_ID:-unknown}\"}"

if [ "$MODE" = "hard" ]; then
  {
    printf '\nPLACEMENT-GATE (HARD): this work has no address.\n'
    printf '  Tool: %s\n' "$TOOL_NAME"
    printf '  Every unit of work carries one Domain + one Charter before it runs (ADR-028).\n'
    printf '  Emit the PLACEMENT block, then write .claude/placement-registered via the Write tool.\n'
    printf '  Nothing here blocks on a MISSING DOMAIN — if none matches, mint one and continue.\n'
    printf "  Override: PLACEMENT_ACK=1 PLACEMENT_ACK_REASON='<why>' <tool>\n"
    printf '  Disable for this repo only: touch .claude/placement-disabled\n\n'
  } >&2
  exit 2
fi

{
  printf '\nPLACEMENT (warn): no placement marker for this turn — work has no address.\n'
  printf '  Emit the PLACEMENT block + write .claude/placement-registered.\n'
  printf '  Enforcement is WARN in this repo; it promotes to HARD after %s compliant turns.\n\n' "$PROMOTE_AFTER"
} >&2
exit 0
