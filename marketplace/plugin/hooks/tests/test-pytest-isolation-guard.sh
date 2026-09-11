#!/usr/bin/env bash
# Regression test for marketplace/plugin/hooks/pytest-isolation-guard.sh (RCA 2026-09-11).
# PROTO-000: mechanism ships with test.  BUILD-LAYER: L0.
# Usage: bash marketplace/plugin/hooks/tests/test-pytest-isolation-guard.sh
# Isolation: per-run mktemp HOME (backups, kill-switch), CLAUDE_PROJECT_DIR (ledger) and
# SUTRA_NATIVE_HOME (the registry that gets snapshotted). The real registry is never read.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/pytest-isolation-guard.sh"
FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }
T=$(mktemp -d -t pytest-guard-test.XXXXXX)
cleanup() { [ -n "${T:-}" ] && [ -d "$T" ] && rm -rf "$T"; }
trap cleanup EXIT

mkdir -p "$T/home" "$T/repo/.enforcement" "$T/kit/domains" "$T/kit/charters" "$T/kit/placements" "$T/repo/sutra/marketplace/plugin/sutra-ui"
printf '{"ref":"dref-1","name":"d1"}\n' > "$T/kit/domains/dref-1.json"
printf '{"ref":"dref-2","name":"d2"}\n' > "$T/kit/domains/dref-2.json"
LEDGER="$T/repo/.enforcement/pytest-isolation-guard.jsonl"

run() { # $1=command $2=cwd ; extra env via caller
  printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$(printf '%s' "$1" | jq -Rs .)" "$2" \
    | HOME="$T/home" CLAUDE_PROJECT_DIR="$T/repo" SUTRA_NATIVE_HOME="$T/kit" bash "$HOOK" 2>"$T/err"
}

echo "case 1: an ordinary command is ignored"
run "ls -la" "$T/repo"; rc=$?
[ "$rc" = 0 ] && [ ! -s "$T/err" ] && [ ! -d "$T/home/.sutra-native/backups" ] && pass "no output, no backup, exit 0" || fail "ordinary command touched something (rc=$rc, err=$(cat "$T/err"))"

echo "case 2: pytest inside the plugin tree -> backup + advisory, exit 0"
run ".venv/bin/python -m pytest -q" "$T/repo/sutra/marketplace/plugin/sutra-ui"; rc=$?
n=$(ls "$T/home/.sutra-native/backups"/user-kit-*.tgz 2>/dev/null | wc -l | tr -d ' ')
[ "$rc" = 0 ] && [ "$n" = 1 ] && grep -q "registry snapshot" "$T/err" && grep -q '"isolated":false' "$LEDGER" && pass "backup written, ledger row, advisory" || fail "rc=$rc backups=$n err=$(cat "$T/err")"
tar tzf "$T/home/.sutra-native/backups"/user-kit-*.tgz | grep -q 'domains/dref-1.json' && pass "backup holds the domain files" || fail "backup missing domain files"

echo "case 3: pytest hidden one level down in a script is still detected"
printf '#!/usr/bin/env bash\ncd sutra/marketplace/plugin/sutra-ui && .venv/bin/python -m pytest -q\n' > "$T/repo/run-backend.sh"
run "bash run-backend.sh" "$T/repo"; rc=$?
grep -q '"hit":"script:run-backend.sh"' "$LEDGER" && [ "$rc" = 0 ] && pass "script body scanned" || fail "script not scanned (rc=$rc): $(tail -1 "$LEDGER")"

echo "case 4: pytest outside the plugin tree is out of scope"
: > "$T/err"; before=$(wc -l < "$LEDGER")
run "python -m pytest tests/" "$T/repo/somewhere-else"; rc=$?
[ "$rc" = 0 ] && [ "$(wc -l < "$LEDGER")" = "$before" ] && [ ! -s "$T/err" ] && pass "ignored" || fail "out-of-scope run was handled (rc=$rc)"

echo "case 5: an isolated command is recorded as isolated"
run "SUTRA_NATIVE_HOME=/tmp/x .venv/bin/python -m pytest -q" "$T/repo/sutra/marketplace/plugin/sutra-ui"
tail -1 "$LEDGER" | grep -q '"isolated":true' && pass "isolation token seen" || fail "isolation not detected: $(tail -1 "$LEDGER")"

echo "case 5b: env -u SUTRA_NATIVE_HOME alone is NOT isolation (it is the incident shape)"
run "env -u SUTRA_NATIVE_HOME .venv/bin/python -m pytest -q" "$T/repo/sutra/marketplace/plugin/sutra-ui"
tail -1 "$LEDGER" | grep -q '"isolated":false' && pass "env -u not counted as isolated" || fail "env -u miscounted: $(tail -1 "$LEDGER")"

echo "case 5c: works without jq (python3 fallback for parsing and the ledger)"
NOJQ="$T/nojq"; mkdir -p "$NOJQ"; for b in bash sh find tar grep head tail tr sed awk ls rm mkdir date cat wc git python3 xargs cut; do p=$(command -v $b) && ln -sf "$p" "$NOJQ/$b"; done
before=$(wc -l < "$LEDGER")
printf '{"tool_name":"Bash","tool_input":{"command":".venv/bin/python -m pytest -q"},"cwd":"%s"}' "$T/repo/sutra/marketplace/plugin/sutra-ui" \
  | env -i PATH="$NOJQ" HOME="$T/home" CLAUDE_PROJECT_DIR="$T/repo" SUTRA_NATIVE_HOME="$T/kit" bash "$HOOK" 2>"$T/err"; rc=$?
[ "$rc" = 0 ] && [ "$(wc -l < "$LEDGER")" -gt "$before" ] && grep -q "registry snapshot" "$T/err" && pass "parsed and logged without jq" || fail "no-jq path: rc=$rc err=$(cat "$T/err") ledger_delta=$(( $(wc -l < "$LEDGER") - before ))"

echo "case 6: hard mode blocks an un-isolated run"
printf '{"tool_name":"Bash","tool_input":{"command":".venv/bin/python -m pytest -q"},"cwd":"%s"}' "$T/repo/sutra/marketplace/plugin/sutra-ui" \
  | HOME="$T/home" CLAUDE_PROJECT_DIR="$T/repo" SUTRA_NATIVE_HOME="$T/kit" SUTRA_PYTEST_GUARD=hard bash "$HOOK" 2>"$T/err"; rc=$?
[ "$rc" = 2 ] && grep -q BLOCKED "$T/err" && pass "exit 2 with reason" || fail "hard mode rc=$rc"

echo "case 7: kill-switch"
touch "$T/home/.pytest-isolation-guard-disabled"
before=$(wc -l < "$LEDGER")
run ".venv/bin/python -m pytest -q" "$T/repo/sutra/marketplace/plugin/sutra-ui"; rc=$?
[ "$rc" = 0 ] && [ "$(wc -l < "$LEDGER")" = "$before" ] && pass "disabled" || fail "kill-switch ignored"
rm -f "$T/home/.pytest-isolation-guard-disabled"

echo "case 8: only the newest 10 backups are kept"
for i in $(seq 1 12); do touch "$T/home/.sutra-native/backups/user-kit-2000010${i}T000000Z.tgz"; done
run ".venv/bin/python -m pytest -q" "$T/repo/sutra/marketplace/plugin/sutra-ui"
n=$(ls "$T/home/.sutra-native/backups"/user-kit-*.tgz | wc -l | tr -d ' ')
[ "$n" = 10 ] && pass "pruned to 10" || fail "kept $n backups"

[ "$FAIL" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
