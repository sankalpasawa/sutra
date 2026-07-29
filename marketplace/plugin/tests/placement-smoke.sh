#!/usr/bin/env bash
# placement-smoke.sh — operator-runnable check that ADR-028 placement is live.
#
#   bash "$(ls -d ~/.claude/plugins/cache/sutra/core/*/ | tail -1)tests/placement-smoke.sh"
#
# Read-only. Touches nothing in your repo except a throwaway temp dir.
# Exit 0 = working. Exit 1 = something is off (it names the failing check).
set -u

C="$(cd "$(dirname "$0")/.." && pwd)"          # the loaded plugin dir
REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
P=0; F=0
ok()  { P=$((P+1)); printf '  [ok]   %s\n' "$1"; }
no()  { F=$((F+1)); printf '  [FAIL] %s\n' "$1"; [ -n "${2:-}" ] && printf '         %s\n' "$2"; }

printf '\n=== PLACEMENT SMOKE TEST (ADR-028) ===\n'
printf 'plugin: %s\n' "$C"
printf 'repo:   %s\n\n' "$REPO"

printf -- '-- 1. Are the parts installed? --\n'
for f in hooks/placement-gate.sh hooks/placement-stop-check.sh lib/placement-render.sh; do
  [ -f "$C/$f" ] && ok "installed: $f" || no "MISSING: $f" "plugin may be an older version"
done
ok "plugin version: $(basename "$C")"

printf -- '\n-- 2. Is the model told to emit the block? --\n'
CTX=$(printf '{"session_id":"smoke","prompt":"hello"}' | CLAUDE_PROJECT_DIR="$REPO" CLAUDE_PLUGIN_ROOT="$C" bash "$C/hooks/per-turn-discipline-prompt.sh" 2>/dev/null)
printf '%s' "$CTX" | grep -q 'PLACEMENT' \
  && ok "per-turn prompt includes the PLACEMENT block" \
  || no "per-turn prompt does NOT mention PLACEMENT" "wiring missing — bump the plugin version and re-update"

printf -- '\n-- 3. What does the block look like? --\n'
printf '  MATCHED (the common case, 1 line):\n'
printf '{"chain":[{"path":"D0","name":"Asawa Inc."},{"path":"D3","name":"Sutra OS"},{"path":"D3.D2","name":"Native"}],"charter":{"id":"C-9b21","title":"Native Canon Integrity"},"created":{"domains":[],"charters":[]},"units":1}' \
  | bash "$C/lib/placement-render.sh" 2>/dev/null | sed 's/^/    /'
printf '\n  MINTED (only when a domain/charter is created):\n'
printf '{"chain":[{"path":"D0","name":"Asawa Inc."},{"path":"D3","name":"Sutra OS"},{"path":"D3.D9","name":"New Area","is_new":true}],"charter":{"id":"C-new","title":"New Area Charter","promise":"placeholder until you fill it","is_new":true},"created":{"domains":["d9"],"charters":["C-new"]},"units":1}' \
  | bash "$C/lib/placement-render.sh" 2>/dev/null | sed 's/^/    /'

printf -- '\n-- 4. Does the gate behave safely? (temp dir; your repo untouched) --\n'
SB=$(mktemp -d); trap 'rm -rf "$SB"' EXIT; mkdir -p "$SB/.claude"; ( cd "$SB" && git init -q . )
pw='{"tool_name":"Write","tool_input":{"file_path":"'"$SB"'/x.ts"},"session_id":"smoke"}'
rc=$( printf '%s' "$pw" | CLAUDE_PROJECT_DIR="$SB" bash "$C/hooks/placement-gate.sh" >/dev/null 2>&1; echo $? )
[ "$rc" = "0" ] && ok "WARN mode: a missing block does NOT block your work" || no "warn mode blocked (exit $rc)" "this would deadlock a fresh repo"
printf 'hard\n' > "$SB/.claude/placement-mode"
rc=$( printf '%s' "$pw" | CLAUDE_PROJECT_DIR="$SB" bash "$C/hooks/placement-gate.sh" >/dev/null 2>&1; echo $? )
[ "$rc" = "2" ] && ok "HARD mode: a missing block blocks (as designed)" || no "hard mode did not block (exit $rc)"
touch "$SB/.claude/placement-disabled"
rc=$( printf '%s' "$pw" | CLAUDE_PROJECT_DIR="$SB" bash "$C/hooks/placement-gate.sh" >/dev/null 2>&1; echo $? )
[ "$rc" = "0" ] && ok "kill-switch frees a repo instantly" || no "kill-switch ignored (exit $rc)"

printf -- '\n-- 5. Where does YOUR repo stand right now? --\n'
MODE=$( [ -f "$REPO/.claude/placement-mode" ] && tr -d '[:space:]' < "$REPO/.claude/placement-mode" || echo warn )
N=$(tr -cd '0-9' < "$REPO/.enforcement/placement/compliant-turns" 2>/dev/null); [ -z "$N" ] && N=0
printf '  enforcement mode : %s\n' "$MODE"
printf '  compliant turns  : %s / 50 before it promotes to HARD\n' "$N"
printf '  gate-log rows    : %s\n' "$(wc -l < "$REPO/.enforcement/placement/gate-log.jsonl" 2>/dev/null | tr -d ' ' || echo 0)"
[ "$MODE" = "warn" ] && ok "this repo cannot be blocked by placement today" \
                     || ok "this repo is enforcing HARD (revert: echo warn > .claude/placement-mode)"

printf '\n=== RESULT: %s passed, %s failed ===\n\n' "$P" "$F"
[ "$F" -eq 0 ] || exit 1
