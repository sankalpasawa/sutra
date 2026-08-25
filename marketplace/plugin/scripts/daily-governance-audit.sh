#!/usr/bin/env bash
# daily-governance-audit.sh (plugin, fleet-generic) — ported 2026-08-26 from
# asawa-holding staging (atom a-db25e6c4-08; original codex-consulted 2026-08-04).
# Deterministic shell only; LLM triage is governance-triage-headless.sh.
# Ledger mechanism (append-only, id = sha1(check + digit-stripped text)[:12],
# LAST row per id = current state) is verbatim from the staged original.
# Output: $SUTRA_GOV_DIR (default <repo>/.sutra/governance)/YYYY-MM-DD.md
#         + history.jsonl row + findings.jsonl upserts.
# Exit: 0 = no CRITICAL findings; 1 = CRITICAL present.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TODAY=$(date -u +%F)
NOW=$(date +%s)
OUTDIR="${SUTRA_GOV_DIR:-$ROOT/.sutra/governance}"
REPORT="$OUTDIR/$TODAY.md"
mkdir -p "$OUTDIR"

if [ "${FORCE:-0}" != "1" ] && grep -q "\"date\":\"$TODAY\"" "$OUTDIR/history.jsonl" 2>/dev/null; then
  echo "governance-audit: already ran today ($TODAY) — skipping (FORCE=1 to override)"
  exit 0
fi

CRIT=0; WARN=0
CRIT_LINES=""; WARN_LINES=""
FINDINGS_LEDGER="$OUTDIR/findings.jsonl"

ledger() { # $1=check_id $2=severity $3=text
  command -v jq >/dev/null 2>&1 || return 0
  local norm id last status
  norm=$(printf '%s %s' "$1" "$3" | tr -d '0-9' | tr -s ' ' | cut -c1-80)
  id=$(printf '%s' "$norm" | shasum 2>/dev/null | cut -c1-12)
  [ -z "$id" ] && return 0
  last=$(grep "\"id\":\"$id\"" "$FINDINGS_LEDGER" 2>/dev/null | tail -1)
  status=$(printf '%s' "$last" | jq -r '.status // empty' 2>/dev/null)
  case "$status" in
    accepted) return 0 ;;   # accepted never resurrects
    open|"")  ;;             # heartbeat / first sighting
    fixed)    ;;             # re-appearance = genuine recurrence, reopen
  esac
  jq -nc --arg id "$id" --arg c "$1" --arg s "$2" --arg t "$3" --arg d "$TODAY" \
    '{id:$id,check:$c,severity:$s,text:$t,status:"open",date:$d,ts:now|floor}' \
    >> "$FINDINGS_LEDGER" 2>/dev/null || true
}
crit() { CRIT=$((CRIT+1)); CRIT_LINES="${CRIT_LINES}- CRITICAL [$1] $2\n"; ledger "$1" critical "$2"; }
warn() { WARN=$((WARN+1)); WARN_LINES="${WARN_LINES}- WARN [$1] $2\n"; ledger "$1" warn "$2"; }

# C1 — plugin hooks.json parses and every referenced hook file exists
if command -v jq >/dev/null 2>&1 && [ -f "$PLUGIN_ROOT/hooks/hooks.json" ]; then
  if ! jq -e . "$PLUGIN_ROOT/hooks/hooks.json" >/dev/null 2>&1; then
    crit hooks-json "plugin hooks.json does not parse"
  else
    while IFS= read -r h; do
      # a command may be "wrapper.sh real-hook.sh" — validate each path token
      hp="${h//\$\{CLAUDE_PLUGIN_ROOT\}/$PLUGIN_ROOT}"
      hp="${hp//\$CLAUDE_PLUGIN_ROOT/$PLUGIN_ROOT}"
      for tokp in $hp; do
        case "$tokp" in "$PLUGIN_ROOT"/*) [ -f "$tokp" ] || crit hook-missing "wired hook file missing: ${tokp##*/}" ;; esac
      done
    done < <(jq -r '.. | .command? // empty' "$PLUGIN_ROOT/hooks/hooks.json" | grep 'CLAUDE_PLUGIN_ROOT')
  fi
fi

# C2 — .claude/sutra-project.json parses when present
if [ -f "$ROOT/.claude/sutra-project.json" ] && command -v jq >/dev/null 2>&1; then
  jq -e . "$ROOT/.claude/sutra-project.json" >/dev/null 2>&1 \
    || crit project-json ".claude/sutra-project.json does not parse"
fi

# W1 — git gates installed but not armed (no test_command declared)
if [ "$(git -C "$ROOT" config core.hooksPath 2>/dev/null)" = ".githooks" ]; then
  tc=$(jq -r '.test_command // empty' "$ROOT/.claude/sutra-project.json" 2>/dev/null)
  [ -n "$tc" ] || warn gates-unarmed "git test gates installed but test_command not declared in .claude/sutra-project.json"
fi

# W2 — scheduled routines whose LAST run failed
if [ -f "$HOME/.sutra/routines/runs.jsonl" ] && command -v jq >/dev/null 2>&1; then
  while IFS= read -r rid; do
    warn routine-failing "routine $rid: last run exited nonzero"
  done < <(jq -s -r 'group_by(.id) | map(last) | .[] | select(.exit != 0) | .id' "$HOME/.sutra/routines/runs.jsonl" 2>/dev/null)
fi

# W3 — governance block missing from .claude/CLAUDE.md (never onboarded / drifted)
if [ ! -f "$ROOT/.claude/CLAUDE.md" ] || ! grep -q 'SUTRA GOVERNANCE' "$ROOT/.claude/CLAUDE.md" 2>/dev/null; then
  warn govblock-missing "managed governance block absent from .claude/CLAUDE.md — run /core:start"
fi

# W4 — stale session marker dirs (>14 days) under .claude/sessions
if [ -d "$ROOT/.claude/sessions" ]; then
  n=$(find "$ROOT/.claude/sessions" -maxdepth 1 -type d -mtime +14 2>/dev/null | grep -c . || true)
  [ "${n:-0}" -gt 20 ] && warn stale-sessions "$n session marker dirs older than 14 days under .claude/sessions"
fi

{
  echo "# Governance audit — $TODAY"
  echo ""
  echo "**critical**: $CRIT · **warn**: $WARN"
  echo ""
  [ -n "$CRIT_LINES" ] && printf '%b' "$CRIT_LINES"
  [ -n "$WARN_LINES" ] && printf '%b' "$WARN_LINES"
  [ "$CRIT" = 0 ] && [ "$WARN" = 0 ] && echo "- clean"
  echo ""
  echo "provenance: plugin daily-governance-audit.sh (fleet-generic port, 2026-08-26)"
} > "$REPORT"
printf '{"date":"%s","critical":%s,"warn":%s,"ts":%s}\n' "$TODAY" "$CRIT" "$WARN" "$NOW" >> "$OUTDIR/history.jsonl"
echo "governance-audit: critical=$CRIT warn=$WARN report=$REPORT"
[ "$CRIT" -gt 0 ] && exit 1
exit 0
