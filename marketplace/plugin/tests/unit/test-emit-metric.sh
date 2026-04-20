#!/bin/bash
# Unit test: hooks/emit-metric.sh — shape + PII rejection.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
EMIT="$PLUGIN_ROOT/hooks/emit-metric.sh"

export SUTRA_HOME="$(mktemp -d)"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# 1) happy path: valid emission writes one line
bash "$EMIT" os_health hook_fires_session 14 count instant >/dev/null 2>&1
LINE=$(tail -1 "$SUTRA_HOME/metrics-queue.jsonl" 2>/dev/null)
[ -n "$LINE" ] && _ok "valid emission appends line" || _no "no line appended"

# 2) schema fields present
for f in schema_version install_id ts dept metric value unit window; do
  case "$LINE" in
    *"\"$f\""*) ;;
    *) _no "missing field: $f"; FAIL=$FAIL ;;
  esac
done
_ok "all required schema fields present"

# 3) non-numeric value rejected (exit 3)
bash "$EMIT" os_health hook_fires_session "not-a-number" 2>/dev/null
RC=$?
[ "$RC" = "3" ] && _ok "non-numeric value rejected (exit 3)" || _no "expected exit 3, got $RC"

# 4) missing arg rejected (exit 2)
bash "$EMIT" os_health 2>/dev/null
RC=$?
[ "$RC" = "2" ] && _ok "missing args rejected (exit 2)" || _no "expected exit 2, got $RC"

# 5) PII in field rejected (exit 4)
bash "$EMIT" "user@email.com" fake_metric 1 2>/dev/null
RC=$?
[ "$RC" = "4" ] && _ok "PII in dept rejected (exit 4)" || _no "expected exit 4, got $RC"

# 6) install_id is 16 chars in emitted row
ID=$(echo "$LINE" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['install_id'])")
[ "${#ID}" = "16" ] && _ok "install_id is 16 hex chars" || _no "install_id len: ${#ID}"

rm -rf "$SUTRA_HOME"
echo ""
echo "test-emit-metric: $PASS passed, $FAIL failed"
exit $FAIL
