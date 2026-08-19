#!/usr/bin/env bash
# test_run_log.sh -- W-BUILD-V1 S5-32/33 acceptance: sutra-run-log lifecycle.
# open+close valid row + schema validation + invalid outcome rejected +
# join test (eval-receipt fixture run_id joins a written row) +
# completeness marker + F-check leak grep.
# Instance data confined to a scratch HOME/SUTRA_NATIVE_HOME (never the repo).
set -u

PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="$PLUGIN/bin/sutra-run-log"
VALIDATE="$PLUGIN/bin/sutra-schema-validate"
SCHEMAS="$(cd "$PLUGIN/../../os/native/schemas" 2>/dev/null && pwd)"
SCHEMA="$SCHEMAS/run-ledger-row.schema.json"
FIXTURE="$SCHEMAS/fixtures/eval-receipt-row.valid.jsonl"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
export HOME="$SCRATCH"
export SUTRA_NATIVE_HOME="$SCRATCH/.sutra-native"
LEDGER="$SUTRA_NATIVE_HOME/ledger/run-ledger.jsonl"
MARKER="$LEDGER.complete"

pass=0; fail=0
ok()   { pass=$((pass+1)); echo "PASS: $1"; }
bad()  { fail=$((fail+1)); echo "FAIL: $1"; }
check() { # check <expected-rc> <actual-rc> <label>
  if [ "$2" -eq "$1" ]; then ok "$3"; else bad "$3 (rc=$2, want $1)"; fi
}

# T1: open mints run_id + atom_id, exit 0
out1="$("$BIN" open --goal 'disburse loan batch 42' \
  --template-id verify-disburse-batch --template-version 1.2.0 \
  --arg batch=42 --arg dry_run=false \
  --workflow-ref W-disburse-loan --thread-id thread-s5-t1 \
  --operator sankalpasawa 2>&1)"; rc=$?
check 0 $rc "T1 open exits 0"
rid="$(printf '%s' "$out1" | tr ' ' '\n' | sed -n 's/^run_id=//p')"
aid="$(printf '%s' "$out1" | tr ' ' '\n' | sed -n 's/^atom_id=//p')"
[ -n "$rid" ] && [ -n "$aid" ] \
  && ok "T1 prints run_id + atom_id" || bad "T1 run_id/atom_id missing ($out1)"

# T2: .open state file held in the ledger dir
[ -f "$SUTRA_NATIVE_HOME/ledger/$rid.open" ] \
  && ok "T2 .open state file in ledger dir" || bad "T2 .open state file missing"

# T3: close with valid outcome appends exactly one row, exit 0
out3="$("$BIN" close --run-id "$rid" --outcome pass --attempts 1 \
  --evidence-ref "~/.sutra-native/ledger/receipts/$rid/evidence.json" 2>&1)"; rc=$?
check 0 $rc "T3 close exits 0"
[ -f "$LEDGER" ] && [ "$(wc -l < "$LEDGER" | tr -d ' ')" = "1" ] \
  && ok "T3 ledger has exactly 1 row" || bad "T3 ledger row count != 1"

# T4: appended row validates against the schema (external validator)
if [ -f "$VALIDATE" ] && [ -f "$SCHEMA" ]; then
  python3 "$VALIDATE" "$SCHEMA" "$LEDGER" >/dev/null 2>&1
  check 0 $? "T4 ledger schema-valid via sutra-schema-validate"
else
  bad "T4 validator or schema missing ($VALIDATE / $SCHEMA)"
fi

# T5: .open state removed after close; completeness marker reports 1 row
[ ! -f "$SUTRA_NATIVE_HOME/ledger/$rid.open" ] \
  && ok "T5 .open state removed after close" || bad "T5 .open state still present"
[ -f "$MARKER" ] && grep -q '"rows": 1\|"rows":1' "$MARKER" \
  && ok "T5 completeness marker present, rows=1" || bad "T5 completeness marker wrong/missing"

# T6: invalid outcome rejected, nothing written
out6="$("$BIN" open --goal 'kyc verify applicant 7' \
  --template-id verify-kyc-pan --template-version 1.0.0 \
  --thread-id thread-s5-t6 --operator sankalpasawa 2>&1)"; rc=$?
check 0 $rc "T6 second open exits 0"
rid6="$(printf '%s' "$out6" | tr ' ' '\n' | sed -n 's/^run_id=//p')"
"$BIN" close --run-id "$rid6" --outcome approved --attempts 1 \
  >/dev/null 2>&1; rc=$?
check 2 $rc "T6 invalid outcome 'approved' rejected with exit 2"
[ "$(wc -l < "$LEDGER" | tr -d ' ')" = "1" ] \
  && ok "T6 ledger unchanged after rejected close" || bad "T6 ledger changed on invalid outcome"

# T7: close of unknown run-id -> exit 2
"$BIN" close --run-id run-never-opened --outcome pass --attempts 1 \
  >/dev/null 2>&1; rc=$?
check 2 $rc "T7 unknown run-id exits 2"

# T8: join test -- eval-receipt fixture run_id joins a written ledger row
JOIN_RID="run-20260818-w-kyc-verify-0042"   # run_id carried by the fixture
"$BIN" open --goal 'kyc verify pan-aadhaar batch' \
  --template-id verify-kyc-pan --template-version 1.0.0 \
  --run-id "$JOIN_RID" --workflow-ref W-kyc-verify \
  --thread-id thread-s5-t8 --operator sankalpasawa >/dev/null 2>&1; rc=$?
check 0 $rc "T8 open with fixture run_id exits 0"
"$BIN" close --run-id "$JOIN_RID" --outcome pass --attempts 2 \
  >/dev/null 2>&1; rc=$?
check 0 $rc "T8 close with fixture run_id exits 0"
if [ -f "$FIXTURE" ]; then
  python3 - "$FIXTURE" "$LEDGER" "$JOIN_RID" <<'PYEOF'
import json, sys
receipts = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
ledger = {json.loads(l)["run_id"] for l in open(sys.argv[2]) if l.strip()}
joined = sorted({r["run_id"] for r in receipts} & ledger)
sys.exit(0 if sys.argv[3] in joined else 1)
PYEOF
  check 0 $? "T8 fixture receipt run_id joins a written ledger row"
else
  bad "T8 eval-receipt fixture missing ($FIXTURE)"
fi

# T9: whole ledger (2 rows) still schema-valid
python3 "$VALIDATE" "$SCHEMA" "$LEDGER" >/dev/null 2>&1
check 0 $? "T9 2-row ledger schema-valid"

# T10: F-check -- row lifecycle only; no runner/queue/scheduler code paths
if grep -nEi 'enqueue|dequeue|def escalate|assign_to|priorit|backoff|scheduler|due_date|due-by|estimat|exactly.once|cross.tenant|run_verify|execute_step' "$BIN" >/dev/null; then
  bad "T10 forbidden-dep token found in lifecycle CLI (F1-F10 / second-runner leak)"
else
  ok "T10 leak grep clean (row lifecycle only)"
fi

echo "----------------------------------------"
echo "RESULT: PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
