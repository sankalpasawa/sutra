#!/usr/bin/env bash
# test_route_log.sh -- W-BUILD-V1 S4-C4 acceptance: sutra-route-log appender.
# 2 appends (args + stdin) + schema validation + idempotent file growth
# + invalid-row rejection + completeness marker + F-check leak grep.
# Instance data confined to a scratch HOME (never the repo).
set -u

PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="$PLUGIN/bin/sutra-route-log"
VALIDATE="$PLUGIN/bin/sutra-schema-validate"
SCHEMA="$(cd "$PLUGIN/../../os/native/schemas" 2>/dev/null && pwd)/decision-provenance-row.schema.json"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
export HOME="$SCRATCH"
LEDGER="$HOME/.sutra-native/ledger/decision-provenance.jsonl"
MARKER="$LEDGER.complete"

pass=0; fail=0
ok()   { pass=$((pass+1)); echo "PASS: $1"; }
bad()  { fail=$((fail+1)); echo "FAIL: $1"; }
check() { # check <expected-rc> <actual-rc> <label>
  if [ "$2" -eq "$1" ]; then ok "$3"; else bad "$3 (rc=$2, want $1)"; fi
}

# T1: append via args, confidence 0.92 -> mode=match, exit 0
out1="$("$BIN" --turn-id turn-t1 --operator sankalpasawa --intent-type task \
  --confidence 0.92 --confidence-source placement_engine:v1.9.1 \
  --charter-ref 'sutra/os/charters/WORK-DISPATCH.md#authority' \
  --work-ref W-kyc-verify --channel in-band 2>&1)"; rc=$?
check 0 $rc "T1 args append exits 0"
echo "$out1" | grep -q 'mode=match' && ok "T1 mode=match at 0.92" || bad "T1 mode=match missing ($out1)"

# T2: ledger exists with exactly 1 row
[ -f "$LEDGER" ] && [ "$(wc -l < "$LEDGER" | tr -d ' ')" = "1" ] \
  && ok "T2 ledger has 1 row after first append" || bad "T2 ledger row count != 1"

# T3: append via stdin, confidence 0.45 -> mode=floor, exit 0
out3="$(printf '%s' '{"turn_id":"turn-t3","operator_id":"sankalpasawa","decision_seq":1,"intent_type":"question","confidence":0.45,"channels":["in-band"]}' \
  | "$BIN" --stdin 2>&1)"; rc=$?
check 0 $rc "T3 stdin append exits 0"
echo "$out3" | grep -q 'mode=floor' && ok "T3 mode=floor at 0.45" || bad "T3 mode=floor missing ($out3)"

# T4: idempotent file growth -- exactly one row per invocation, now 2
[ "$(wc -l < "$LEDGER" | tr -d ' ')" = "2" ] \
  && ok "T4 ledger grew to exactly 2 rows" || bad "T4 ledger row count != 2"

# T5: every appended row validates against the schema (external validator)
if [ -f "$VALIDATE" ] && [ -f "$SCHEMA" ]; then
  python3 "$VALIDATE" "$SCHEMA" "$LEDGER" >/dev/null 2>&1
  check 0 $? "T5 whole ledger schema-valid via sutra-schema-validate"
else
  bad "T5 validator or schema missing ($VALIDATE / $SCHEMA)"
fi

# T6: recorded factors carry threshold semantics
grep -q '"type":"routing_mode","value":"match"' "$LEDGER" \
  && ok "T6 row1 records routing_mode=match" || bad "T6 routing_mode=match not recorded"
grep -q '"type":"routing_mode","value":"floor"' "$LEDGER" \
  && ok "T6 row2 records routing_mode=floor" || bad "T6 routing_mode=floor not recorded"

# T7: invalid row (authority_verdict outside enum) -> exit 1, nothing written
"$BIN" --turn-id turn-t7 --operator sankalpasawa --authority-verdict approved \
  >/dev/null 2>&1; rc=$?
check 1 $rc "T7 invalid enum rejected with exit 1"
[ "$(wc -l < "$LEDGER" | tr -d ' ')" = "2" ] \
  && ok "T7 ledger unchanged after rejected row" || bad "T7 ledger changed on invalid row"

# T8: usage error (missing turn_id) -> exit 2
"$BIN" --operator sankalpasawa >/dev/null 2>&1; rc=$?
check 2 $rc "T8 missing turn_id exits 2"

# T9: completeness marker present and reports 2 rows
[ -f "$MARKER" ] && grep -q '"rows": 2\|"rows":2' "$MARKER" \
  && ok "T9 completeness marker present, rows=2" || bad "T9 completeness marker wrong/missing"

# T10: F-check -- no queue/assignment/escalation/scheduler/estimation code paths
if grep -nEi 'enqueue|dequeue|def escalate|assign_to|priorit|backoff|scheduler|due_date|due-by|estimat|exactly.once|cross.tenant' "$BIN" >/dev/null; then
  bad "T10 forbidden-dep token found in appender (F1-F10 leak)"
else
  ok "T10 leak grep clean (F1-F10)"
fi

echo "----------------------------------------"
echo "RESULT: PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
