#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/loop-budget-guard.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-06-25
#
# Sutra OS — Loop / Tool-Budget Guard (PreToolUse, all tools)
# Implements doc item A6 (agent guardrails: loop budgets, tool budgets, termination).
#
# WHY PreToolUse (not PostToolUse): PostToolUse fires AFTER the tool runs and
# cannot prevent a runaway. To actually STOP an infinite loop or a runaway
# agent the gate must be PreToolUse and block (exit 2).
#
# Behavior (per session_id):
#   - Records a signature (tool_name + sha256(tool_input)) for every tool call.
#   - TOTAL calls > SUTRA_TOOL_BUDGET (default 250)        -> block (exit 2).
#   - Last SUTRA_REPEAT_LIMIT (default 8) signatures all
#     identical (i.e. the same tool+args N times in a row) -> block (exit 2).
#   - Otherwise exit 0.
#
# Fail-open: malformed/empty stdin, missing python3, any error -> exit 0.
#            A guardrail must never break a session by crashing.
#
# Generous defaults: normal sessions never trip. Only genuine runaways do.
#
# Config / overrides:
#   SUTRA_TOOL_BUDGET=<n>          total tool-call ceiling per session (default 250)
#   SUTRA_REPEAT_LIMIT=<n>         identical-call run length that trips (default 8)
#   LOOP_GUARD_ACK=1              one-shot: record but do not block this call
#   LOOP_GUARD_STATE_DIR=<dir>    state dir override (tests); default $SUTRA_HOME/sessions
# Kill-switches (any one):
#   LOOP_BUDGET_GUARD_DISABLED=1 | SUTRA_BYPASS=1 | touch ~/.loop-budget-guard-disabled
#
# Logged on block to .enforcement/loop-guard.jsonl (mirrors keys-in-env-vars.sh).

set -u

# ── Kill-switches ─────────────────────────────────────────────────────────────
[ "${SUTRA_BYPASS:-}" = "1" ] && exit 0
[ "${LOOP_BUDGET_GUARD_DISABLED:-}" = "1" ] && exit 0
[ -e "$HOME/.loop-budget-guard-disabled" ] && exit 0

# ── Read PreToolUse JSON from stdin (fail-open if none) ───────────────────────
[ -t 0 ] && exit 0
JSON=$(cat 2>/dev/null || true)
[ -z "$JSON" ] && exit 0

BUDGET="${SUTRA_TOOL_BUDGET:-250}"
REPEAT="${SUTRA_REPEAT_LIMIT:-8}"
STATE_DIR="${LOOP_GUARD_STATE_DIR:-${SUTRA_HOME:-$HOME/.sutra}/sessions}"

# ── Config validation (fix #2: never silently disable on a typo) ──────────────
# A non-numeric budget/repeat previously slipped through `[ -gt ]` as a shell
# error and the guard fell open — a misconfiguration silently removed the
# guardrail. Validate as non-negative integers; on bad input, warn once on
# stderr and fall back to the documented default. Fail-LOUD, not fail-silent.
valid_int() { case "${1:-}" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
if ! valid_int "$BUDGET"; then
  echo "loop-budget-guard: invalid SUTRA_TOOL_BUDGET='$BUDGET' (need non-negative integer); using default 250" >&2
  BUDGET=250
fi
if ! valid_int "$REPEAT"; then
  echo "loop-budget-guard: invalid SUTRA_REPEAT_LIMIT='$REPEAT' (need non-negative integer); using default 8" >&2
  REPEAT=8
fi
# Detection window for the frequency check (fix #1). Default = 2*REPEAT so a
# strict run of REPEAT identical calls still trips exactly as before, while an
# alternating loop is also caught once a signature recurs REPEAT times in-window.
WINDOW="${SUTRA_REPEAT_WINDOW:-$((REPEAT * 2))}"
if ! valid_int "$WINDOW" || [ "$WINDOW" -lt "$REPEAT" ]; then
  echo "loop-budget-guard: invalid SUTRA_REPEAT_WINDOW='$WINDOW' (need integer >= SUTRA_REPEAT_LIMIT); using $((REPEAT * 2))" >&2
  WINDOW=$((REPEAT * 2))
fi

# ── Parse + compute signature via python3 (fail-open on any error) ────────────
PARSED=$(printf '%s' "$JSON" | python3 -c '
import json, sys, hashlib
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(3)
tool = d.get("tool_name", "")
if not tool:
    sys.exit(3)
sid = d.get("session_id") or "unknown"
ti = d.get("tool_input", {})
try:
    blob = json.dumps(ti, sort_keys=True, default=str)
except Exception:
    blob = str(ti)
h = hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]
print(sid)
print(tool + ":" + h)
' 2>/dev/null) || exit 0
[ -z "$PARSED" ] && exit 0

SID=$(printf '%s\n' "$PARSED" | sed -n '1p')
SIGNATURE=$(printf '%s\n' "$PARSED" | sed -n '2p')
[ -z "$SID" ] && exit 0
[ -z "$SIGNATURE" ] && exit 0

# ── Exempt agent-orchestration tools (A6 multi-agent fix, 2026-06-30) ─────────
# Agent / Task / Workflow dispatches are deliberate BRANCHING, and a fan-out of
# N similar agents is legitimate parallelism — not a runaway loop. Counting them
# toward the per-session tool budget or the repeat detector false-blocks
# multi-agent workflows (the orchestrator's dispatches, and identical parallel
# sub-tasks, look like a "loop" to a tool+args signature that has no per-agent
# dimension). The agents' OWN tool calls (Bash/Read/Write/…) are still recorded,
# so a genuine runaway INSIDE an agent is still caught. Set
# LOOP_GUARD_COUNT_AGENTS=1 to count dispatches too (old behavior).
if [ "${LOOP_GUARD_COUNT_AGENTS:-0}" != "1" ]; then
  case "${SIGNATURE%%:*}" in
    Agent|Task|Workflow) exit 0 ;;
  esac
fi

# Sanitize session id for filesystem use.
SID_SAFE=$(printf '%s' "$SID" | tr -c 'A-Za-z0-9._-' '_')

mkdir -p "$STATE_DIR" 2>/dev/null || exit 0
F="$STATE_DIR/${SID_SAFE}.loopguard"
# Concurrency / durability assumption: state is an APPEND-ONLY log (one
# signature per line). Single-line `>>` appends are atomic on a local POSIX
# filesystem, which is the ONLY supported target. On a shared/networked FS
# (e.g. NFS) concurrent appends from parallel tool calls could interleave or
# be lost; if state ever moves off local disk, switch to O_APPEND+flock or a
# per-call temp-file + atomic rename.
printf '%s\n' "$SIGNATURE" >> "$F" 2>/dev/null || exit 0

TOTAL=$(wc -l < "$F" 2>/dev/null | tr -d ' ')
TOTAL=${TOTAL:-0}

ACK="${LOOP_GUARD_ACK:-0}"

log_block() {  # $1=event $2=detail
  local repo_root ts safe_detail
  repo_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
  ts=$(date +%s)
  safe_detail=$(printf '%s' "$2" | tr -d '"')
  mkdir -p "$repo_root/.enforcement" 2>/dev/null || true
  printf '{"ts":%s,"event":"%s","session":"%s","detail":"%s","total":%s}\n' \
    "$ts" "$1" "$SID_SAFE" "$safe_detail" "$TOTAL" \
    >> "$repo_root/.enforcement/loop-guard.jsonl" 2>/dev/null || true
}

# ── Total tool-budget ceiling ─────────────────────────────────────────────────
if [ "$TOTAL" -gt "$BUDGET" ]; then
  [ "$ACK" = "1" ] && exit 0
  log_block "loopguard-budget" "tool budget $BUDGET exceeded"
  echo "BLOCKED: loop-budget-guard — tool-call budget ($BUDGET) exceeded for this session ($TOTAL calls)." >&2
  echo "  Likely a runaway. Override once: LOOP_GUARD_ACK=1 <retry> · raise: SUTRA_TOOL_BUDGET=<n> · disable: LOOP_BUDGET_GUARD_DISABLED=1" >&2
  exit 2
fi

# ── Repeated-identical-call (loop) detection — frequency-in-window ────────────
# Fix #1: the prior check only caught a strict CONSECUTIVE run of identical
# calls (tail -n REPEAT all-unique==1). An alternating loop (A,B,A,B,…) never
# produces such a run and evaded detection until the total budget — up to 250
# wasted calls. Now we count the most frequent signature within the last WINDOW
# calls; if any signature recurs >= REPEAT times in-window, that is a loop.
# Back-compat: a strict run of REPEAT identical calls still trips at exactly the
# same point (within a WINDOW>=REPEAT, REPEAT consecutive identicals => freq REPEAT).
# REPEAT<1 disables repeat detection entirely (preserves the old "set to 0 to
# turn off" escape hatch — without this guard, REPEAT=0 would block every call).
if [ "$REPEAT" -ge 1 ] && [ "$TOTAL" -ge "$REPEAT" ]; then
  MAXF=$(tail -n "$WINDOW" "$F" 2>/dev/null | sort | uniq -c | sort -rn | awk 'NR==1{print $1}')
  MAXF=${MAXF:-0}
  if [ "$MAXF" -ge "$REPEAT" ]; then
    [ "$ACK" = "1" ] && exit 0
    log_block "loopguard-repeat" "same call x$MAXF in last $WINDOW ($SIGNATURE)"
    echo "BLOCKED: loop-budget-guard — same tool+args repeated $MAXF times within the last $WINDOW calls (possible loop)." >&2
    echo "  Change the call, or override once: LOOP_GUARD_ACK=1 <retry> · raise: SUTRA_REPEAT_LIMIT=<n> / SUTRA_REPEAT_WINDOW=<n> · disable: LOOP_BUDGET_GUARD_DISABLED=1" >&2
    exit 2
  fi
fi

exit 0
