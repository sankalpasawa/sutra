#!/bin/bash
# pytest-isolation-guard.sh — a test run never gets to be the last copy of the registry.
#
# Direction:    RCA 2026-09-11 (holding/research/2026-09-11-registry-reset-rca.md):
#               a whole-directory sutra-ui pytest run emptied ~/.sutra-native/user-kit/
#               domains. The engine now refuses the default home under pytest (I-T1,
#               placement_engine._refuse_default_home_under_test). This hook is the
#               second layer: BEFORE any test run that can reach the plugin code, take
#               a snapshot of the registry, and say so.
# Event:        PreToolUse on Bash
# Enforcement:  SOFT by default (backup + one stderr line, exit 0).
#               SUTRA_PYTEST_GUARD=hard  -> exit 2 when the command shows no isolation.
#               Isolation = SUTRA_NATIVE_HOME=<path> or HOME=<path> in the command.
#               `env -u SUTRA_NATIVE_HOME` alone is NOT isolation: it reverts the test
#               to the default home, which is the incident shape (codex P2, 2026-09-11).
# Detection:    pytest / unittest / run-tests.sh / run-all.sh in the command itself, OR
#               inside a script the command runs (bash|sh|source|python <file>) — one
#               level deep, because the 17:11:50 run was `bash .tmp/...sh` with the
#               pytest line inside the script (codex P9, 2026-09-11).
# Scope:        only when the command, the scanned script or the tool cwd names the
#               plugin tree (sutra-ui, marketplace/plugin, placement_engine).
# Backup:       tar.gz of domains/ charters/ placements/ under $SUTRA_NATIVE_HOME
#               (default ~/.sutra-native/user-kit) -> ~/.sutra-native/backups/
#               user-kit-<utc>.tgz, newest 10 kept.
# Parsing:      jq when present, python3 otherwise (macOS ships python3, not jq).
# Ledger:       <repo>/.enforcement/pytest-isolation-guard.jsonl
# Kill-switch:  touch ~/.pytest-isolation-guard-disabled
# Test:         hooks/tests/test-pytest-isolation-guard.sh

set -uo pipefail
[ -e "$HOME/.pytest-isolation-guard-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LEDGER="$REPO_ROOT/.enforcement/pytest-isolation-guard.jsonl"

CMD="${TOOL_INPUT_command:-}"
CWD=""
_JSON=""
if [ ! -t 0 ]; then _JSON=$(cat 2>/dev/null) || _JSON=""; fi
if [ -n "$_JSON" ]; then
  if command -v jq >/dev/null 2>&1; then
    [ -z "$CMD" ] && CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
    CWD=$(printf '%s' "$_JSON" | jq -r '.cwd // empty' 2>/dev/null)
  elif command -v python3 >/dev/null 2>&1; then
    # first line = cwd (never contains a newline), the rest = the command verbatim
    _P=$(printf '%s' "$_JSON" | python3 -c 'import json,sys
try:
    o=json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((o.get("cwd") or "").replace("\n", " "))
sys.stdout.write((o.get("tool_input") or {}).get("command") or "")' 2>/dev/null)
    CWD=$(printf '%s\n' "$_P" | head -1)
    [ -z "$CMD" ] && CMD=$(printf '%s\n' "$_P" | tail -n +2)
  fi
fi
[ -n "$CMD" ] || exit 0

TEST_RE='(^|[^a-zA-Z0-9_])(pytest|unittest|run-tests\.sh|run-all\.sh)([^a-zA-Z0-9_]|$)'
SCOPE_RE='(sutra-ui|marketplace/plugin|placement_engine)'

hit=""
scanned=""
if printf '%s' "$CMD" | grep -Eq "$TEST_RE"; then
  hit="command"
else
  # one level deep: scripts the command runs
  for tok in $(printf '%s' "$CMD" | tr ';&|()' '     ' | grep -oE '[^[:space:]]+\.(sh|py)' | head -8); do
    f="$tok"
    case "$f" in /*) ;; *) f="${CWD:-$REPO_ROOT}/$tok" ;; esac
    [ -f "$f" ] || f="$REPO_ROOT/$tok"
    [ -f "$f" ] || continue
    if head -200 "$f" 2>/dev/null | grep -Eq "$TEST_RE"; then hit="script:$tok"; scanned="$f"; break; fi
  done
fi
[ -n "$hit" ] || exit 0

in_scope=""
printf '%s' "$CMD $CWD" | grep -Eq "$SCOPE_RE" && in_scope=1
[ -z "$in_scope" ] && [ -n "$scanned" ] && head -200 "$scanned" | grep -Eq "$SCOPE_RE" && in_scope=1
[ -n "$in_scope" ] || exit 0

REG="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native/user-kit}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
backup=""
ndom=0
if [ -d "$REG/domains" ]; then
  ndom=$(find "$REG/domains" -maxdepth 1 -name 'dref-*.json' 2>/dev/null | wc -l | tr -d ' ')
  BK="$HOME/.sutra-native/backups"
  mkdir -p "$BK" 2>/dev/null
  parts=()
  for sub in domains charters placements; do [ -d "$REG/$sub" ] && parts+=("$sub"); done
  if [ "${#parts[@]}" -gt 0 ] && tar czf "$BK/user-kit-$TS.tgz" -C "$REG" "${parts[@]}" 2>/dev/null; then
    backup="$BK/user-kit-$TS.tgz"
    ls -1t "$BK" 2>/dev/null | grep -E '^user-kit-.*\.tgz$' | tail -n +11 | while IFS= read -r old; do rm -f "$BK/$old"; done
  fi
fi

isolated=""
printf '%s' "$CMD" | grep -Eq '(SUTRA_NATIVE_HOME=[^[:space:]]|(^|[[:space:]])HOME=[^[:space:]])' && isolated=1

mkdir -p "$(dirname "$LEDGER")" 2>/dev/null
short=$(printf '%s' "$CMD" | head -c 160)
if command -v jq >/dev/null 2>&1; then
  jq -nc --arg ts "$TS" --arg hit "$hit" --arg cmd "$short" --arg backup "$backup" \
    --argjson n "${ndom:-0}" --arg iso "${isolated:-0}" \
    '{ts:$ts,hit:$hit,cmd:$cmd,backup:$backup,domains:$n,isolated:($iso=="1")}' >> "$LEDGER" 2>/dev/null
elif command -v python3 >/dev/null 2>&1; then
  TS="$TS" HIT="$hit" SHORT="$short" BACKUP="$backup" NDOM="${ndom:-0}" ISO="${isolated:-0}" \
  python3 -c 'import json,os;print(json.dumps({"ts":os.environ["TS"],"hit":os.environ["HIT"],"cmd":os.environ["SHORT"],"backup":os.environ["BACKUP"],"domains":int(os.environ["NDOM"]),"isolated":os.environ["ISO"]=="1"}))' >> "$LEDGER" 2>/dev/null
fi

if [ -z "$isolated" ] && [ "${SUTRA_PYTEST_GUARD:-soft}" = "hard" ]; then
  cat >&2 <<EOF
BLOCKED — pytest-isolation-guard (hard): a test run reaches the plugin code and the
command shows no registry isolation. Prefix it with SUTRA_NATIVE_HOME=<tmp dir> or run
it under HOME=<tmp>. Backup of the current registry: ${backup:-none}
EOF
  exit 2
fi

msg="[pytest-isolation-guard] test run detected ($hit); registry snapshot: ${backup:-none} (domains=$ndom)"
[ -z "$isolated" ] && msg="$msg; no SUTRA_NATIVE_HOME= or HOME= in the command, relying on engine guard I-T1"
echo "$msg" >&2
exit 0
