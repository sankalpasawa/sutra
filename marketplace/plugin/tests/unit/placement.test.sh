#!/usr/bin/env bash
# placement.test.sh — unit tests for the ADR-028 placement renderer + gate.
# Run: bash tests/unit/placement.test.sh   (exits non-zero on any failure)
set -u

PLUGIN_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RENDER="$PLUGIN_DIR/lib/placement-render.sh"
GATE="$PLUGIN_DIR/hooks/placement-gate.sh"
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -n "${2:-}" ] && printf '       %s\n' "$2"; }
have() { printf '%s' "$1" | grep -qF -- "$2"; }

SANDBOX=$(mktemp -d)
trap 'rm -rf "$SANDBOX"' EXIT
mkdir -p "$SANDBOX/.claude" "$SANDBOX/.enforcement"
( cd "$SANDBOX" && git init -q . 2>/dev/null )

echo "== renderer =="

CHAIN='[{"path":"D0","name":"Asawa Inc."},{"path":"D3","name":"Sutra OS"},{"path":"D3.D2","name":"Native"}]'

out=$(printf '{"chain":%s,"charter":{"id":"C-1","title":"Native Canon Integrity"},"created":{"domains":[],"charters":[]},"units":1}' "$CHAIN" | bash "$RENDER")
case "$out" in
  "PLACEMENT: D0 Asawa Inc. > D3 Sutra OS > D3.D2 Native | \"Native Canon Integrity\"") ok "compact is one line, exact" ;;
  *) bad "compact is one line, exact" "got: $out" ;;
esac
[ "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" = "1" ] && ok "compact emits exactly 1 line" || bad "compact emits exactly 1 line"

out=$(printf '{"chain":%s,"charter":{"id":"C-1","title":"T","is_new":true},"created":{"domains":["d1"],"charters":["C-1"]},"units":1}' "$CHAIN" | bash "$RENDER")
have "$out" "+-- PLACEMENT" && ok "expanded renders a box" || bad "expanded renders a box"
have "$out" "[NEW]"          && ok "expanded marks new nodes"   || bad "expanded marks new nodes"
have "$out" "CREATED THIS TURN: 1 domain(s), 1 charter(s)" && ok "expanded reports creation counts" || bad "expanded reports creation counts"

out=$(printf '{"chain":%s,"charter":{"id":"C-1","title":"T"},"created":{"domains":["a","b"],"charters":[]},"units":500}' "$CHAIN" | bash "$RENDER")
have "$out" "500 units placed" && ok "summary fires above bulk threshold" || bad "summary fires above bulk threshold"
[ "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" = "1" ] && ok "summary collapses to 1 line" || bad "summary collapses to 1 line"

# ASCII-only (D-UX-1)
out=$(printf '{"chain":%s,"charter":{"id":"C-1","title":"T","is_new":true},"created":{"domains":["d"],"charters":["C-1"]},"units":1}' "$CHAIN" | bash "$RENDER")
if printf '%s' "$out" | LC_ALL=C grep -q '[^[:print:][:space:]]'; then
  bad "expanded is ASCII-only"
else ok "expanded is ASCII-only"; fi

printf '{"chain":[],"created":{"domains":[],"charters":[]},"units":1}' | bash "$RENDER" >/dev/null 2>&1 \
  && bad "empty chain rejected" || ok "empty chain rejected"
printf 'not json' | bash "$RENDER" >/dev/null 2>&1 \
  && bad "invalid JSON rejected" || ok "invalid JSON rejected"

echo "== gate: mode ladder =="

payload() { printf '{"tool_name":"%s","tool_input":{"file_path":"%s","command":"%s"},"session_id":"testsid"}' "$1" "${2:-$SANDBOX/src/x.ts}" "${3:-}"; }
run_gate() { ( cd "$SANDBOX" && printf '%s' "$1" | CLAUDE_PROJECT_DIR="$SANDBOX" bash "$GATE" 2>/dev/null ); echo $?; }

# marker-lib ADOPTS a flat legacy marker into .claude/sessions/<sid>/ on first
# read. Clearing only the flat path leaves the adopted copy behind and every
# later gate call passes on a marker the test thought it had deleted. Clear both.
clear_marker() { rm -f "$SANDBOX/.claude/placement-registered"; rm -rf "$SANDBOX/.claude/sessions"; }
set_marker()   { printf 'DOMAIN_REF=d1\n' > "$SANDBOX/.claude/placement-registered"; }

clear_marker; rm -f "$SANDBOX/.claude/placement-mode"
[ "$(run_gate "$(payload Write)")" = "0" ] && ok "warn mode: missing marker does NOT block (exit 0)" || bad "warn mode: missing marker does NOT block"

printf 'hard\n' > "$SANDBOX/.claude/placement-mode"
[ "$(run_gate "$(payload Write)")" = "2" ] && ok "hard mode: missing marker blocks (exit 2)" || bad "hard mode: missing marker blocks (exit 2)"

set_marker
[ "$(run_gate "$(payload Write)")" = "0" ] && ok "hard mode: marker present passes" || bad "hard mode: marker present passes"

echo "== gate: kill-switches + override =="
clear_marker
touch "$SANDBOX/.claude/placement-disabled"
[ "$(run_gate "$(payload Write)")" = "0" ] && ok "repo-local kill-switch disables" || bad "repo-local kill-switch disables"
rm -f "$SANDBOX/.claude/placement-disabled"

out=$( ( cd "$SANDBOX" && printf '%s' "$(payload Write)" | CLAUDE_PROJECT_DIR="$SANDBOX" PLACEMENT_ACK=1 PLACEMENT_ACK_REASON=test bash "$GATE" 2>/dev/null ); echo $? )
[ "$out" = "0" ] && ok "PLACEMENT_ACK overrides" || bad "PLACEMENT_ACK overrides"
grep -q 'placement-override' "$SANDBOX/.enforcement/placement/gate-log.jsonl" 2>/dev/null \
  && ok "override is audit-logged" || bad "override is audit-logged"

echo "== gate: whitelist + tool scope =="
[ "$(run_gate "$(payload Write "$SANDBOX/.claude/foo")")" = "0" ] && ok ".claude/ path whitelisted" || bad ".claude/ path whitelisted"
[ "$(run_gate "$(payload Read)")" = "0" ]                        && ok "Read is not gated"        || bad "Read is not gated"

echo "== gate: bash-mutation classifier (F2.13) =="
clear_marker   # mode is still 'hard' here; mutating commands must exit 2
# read-only -> must NOT gate (exit 0 even in hard mode with no marker)
for c in "ls -la" "cat file.txt" "grep -r foo ." "git status --short" "git log --oneline -1" "jq . x.json" "wc -l f" "find . -name '*.ts'" "grep foo bar 2>/dev/null" "cat f 2>&1"; do
  [ "$(run_gate "$(payload Bash "" "$c")")" = "0" ] && ok "read-only not gated: $c" || bad "read-only not gated: $c"
done
# mutating -> must gate (exit 2 in hard mode, no marker)
for c in "rm -rf build" "mv a b" "mkdir -p x" "sed -i '' s/a/b/ f" "git commit -m x" "git push origin main" "git checkout ." "echo hi > out.txt" "printf x >> log.txt" "cat a > b"; do
  [ "$(run_gate "$(payload Bash "" "$c")")" = "2" ] && ok "mutating gated: $c" || bad "mutating gated: $c"
done

echo
printf 'PASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
