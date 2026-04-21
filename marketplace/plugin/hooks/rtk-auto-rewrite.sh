#!/usr/bin/env bash
# RTK air-tight enforcement — Tokens charter, Mode A+ (mechanical whitelist)
# PreToolUse(Bash) hook. Blocks unprefixed voluminous git commands; forces
# agent to use `rtk <cmd>` per the measured savings.
#
# Whitelist (v2 — 2026-04-22 extension, part of C3c native-tool track):
#   git status    (measured -68.7% in Asawa repo 2026-04-20)
#   git log       (typical -30-50% on dirty repos)
#   git diff      (typical -40-60% on sizable diffs)
#   git blame     (v2 — large on long files; rtk-shape similar to log)
#   git show      (v2 — commit+diff dumps; rtk-shape similar to log -1 -p)
#
# NOT wrapped (use pipes at call-site instead):
#   grep / rg     → prefer `head -N <pattern>` caps inline; rtk adds no value
#   cat           → for >1KB files, prefer Read tool w/ offset+limit
#   tree / du     → prefer `head -50` or `-d 1` depth caps
#   jq            → prefer `-c` compact output + slicing
#
# Kill-switch (mechanical): ~/.rtk-disabled exists OR env RTK_DISABLED=1 → exit 0.
# Per-command override: prepend `RTK_SKIP=1 ` to your bash command.

set -uo pipefail

if [ -f "$HOME/.rtk-disabled" ] || [ "${RTK_DISABLED:-0}" = "1" ]; then
  exit 0
fi

if ! command -v rtk >/dev/null 2>&1; then
  exit 0
fi

_JSON=""
if [ ! -t 0 ]; then
  _JSON=$(cat)
fi

CMD=""
if [ -n "$_JSON" ]; then
  if command -v jq >/dev/null 2>&1; then
    CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
  else
    CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi

[ -z "$CMD" ] && exit 0

CMD_CLEAN=$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]*([A-Z_][A-Z0-9_]*=[^[:space:]]*[[:space:]]+)*//')

# Per-command override
if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])RTK_SKIP=1[[:space:]]'; then
  exit 0
fi

# Already rtk-prefixed
case "$CMD_CLEAN" in
  rtk*|"rtk "*|*"; rtk"*|*"&& rtk"*|*"| rtk"*) exit 0 ;;
esac

_match_whitelist() {
  local cmd="$1"
  case "$cmd" in
    "git status"|"git status "*|*"; git status"*|*"&& git status"*|*"| git status"*) return 0 ;;
    "git log"|"git log "*|*"; git log"*|*"&& git log"*|*"| git log"*) return 0 ;;
    "git diff"|"git diff "*|*"; git diff"*|*"&& git diff"*|*"| git diff"*) return 0 ;;
    "git blame"|"git blame "*|*"; git blame"*|*"&& git blame"*|*"| git blame"*) return 0 ;;
    "git show"|"git show "*|*"; git show"*|*"&& git show"*|*"| git show"*) return 0 ;;
  esac
  return 1
}

if _match_whitelist "$CMD_CLEAN"; then
  echo ""
  echo "BLOCKED — RTK air-tight gate (Tokens charter, mode A+)"
  echo ""
  echo "  Command: $CMD_CLEAN"
  echo "  Fix:     rtk $CMD_CLEAN"
  echo "  Override: RTK_SKIP=1 $CMD_CLEAN"
  echo "  Kill-switch: touch ~/.rtk-disabled"
  echo ""
  mkdir -p "${CLAUDE_PROJECT_DIR:-.}/.enforcement" 2>/dev/null
  TS=$(date +%s)
  SAFE_CMD=$(printf '%s' "$CMD_CLEAN" | tr -d '"\\' | tr '\n\r' '  ' | head -c 200)
  echo "{\"ts\":$TS,\"event\":\"rtk-gate-block\",\"cmd\":\"$SAFE_CMD\"}" \
    >> "${CLAUDE_PROJECT_DIR:-.}/.enforcement/rtk-gate.jsonl" 2>/dev/null
  exit 2
fi

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Block count per day from .enforcement/rtk-gate.jsonl (one row per block).
# RTK savings from `rtk gain` (cumulative bytes saved + per-command breakdown).
# Null handling: no blocks = agent compliance (good) OR hook not firing (check health).
#
### 2. Adoption mechanism
# Hook registered in .claude/settings.json PreToolUse(Bash). Downstream cross-company
# propagation queued for each company's .claude/ via god-mode deploy.
#
### 3. Monitoring / escalation
# DRI reviews rtk-gate.jsonl + `rtk gain` weekly. Warn: >20 blocks/day (agent drifting).
# Breach: override_rate rise OR quality incident. Escalation: touch ~/.rtk-disabled.
#
### 4. Iteration trigger
# Revise when: whitelist proves too narrow/broad after 2 weeks; new rtk subcommand proves
# lossless; kill-switch used >2×/week; founder direction.
#
### 5. DRI
# Sutra-OS (Tokens charter DRI). Operator: in-session agent, self-served.
#
### 6. Decommission criteria
# Retire when: rtk unmaintained; Claude Code gains native compression; cumulative savings
# <500 tok/day for 30 days; Tokens charter retires.
