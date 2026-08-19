#!/usr/bin/env bash
# test_eval_pack.sh -- W-BUILD-V1 S6-36/37: EXECUTES the v1-follow eval pack
# (holding/plans/native-sop-program/v1-build/eval-pack-v1-follow.json)
# against the sandbox CLIs and emits eval-receipt rows validated against
# sutra/os/native/schemas/eval-receipt-row.schema.json.
#
# Cases: register / follow / fail-retry / fail-escalate / receipt / counter.
# Instance data ONLY under a throwaway SUTRA_NATIVE_HOME (cleaned on exit).
# python3/bash stdlib only (M1 leak guard).
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$SELF_DIR/../../bin"
SCHEMAS="$(cd "$SELF_DIR/../../../../os/native/schemas" && pwd)"
REPO="$(cd "$SELF_DIR/../../../../.." && pwd)"
PACK_FILE="$REPO/holding/plans/native-sop-program/v1-build/eval-pack-v1-follow.json"
VALID_WF="$SCHEMAS/fixtures/workflow-definition.valid.jsonl"
REGISTRY="$BIN/sutra-registry"
RESOLVE="$BIN/sutra-resolve"
VERIFY="$BIN/sutra-verify"
SVAL="$BIN/sutra-schema-validate"

export SUTRA_NATIVE_HOME="$HOME/.sutra-native/test-eval-pack-$$"
FIX="$SUTRA_NATIVE_HOME/.fixtures"
LEDGER_DIR="$SUTRA_NATIVE_HOME/ledger"
RECEIPTS="$LEDGER_DIR/receipts.jsonl"
RUN_LEDGER="$LEDGER_DIR/run-ledger.jsonl"
trap 'rm -rf "$SUTRA_NATIVE_HOME"' EXIT
mkdir -p "$FIX" "$LEDGER_DIR"

PACK="v1-follow"
RUN_ID="run-$(date -u +%Y%m%d)-eval-pack-$$"
NOW() { date -u +%Y-%m-%dT%H:%M:%SZ; }

PASS=0; FAIL=0
check() { # <name> <expected_rc> <actual_rc>
  if [ "$2" -eq "$3" ]; then PASS=$((PASS+1)); echo "PASS: $1 (rc=$3)"
  else FAIL=$((FAIL+1)); echo "FAIL: $1 (want rc=$2 got rc=$3)"; fi
}
check_ok() { # <name> <0-or-1 from a predicate>
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $1"
  else FAIL=$((FAIL+1)); echo "FAIL: $1"; fi
}
json_field() { # <json> <field>
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]))' "$2" <<<"$1"
}

# receipt helper: build row -> validate SINGLE row against the schema -> append.
receipt_append() { # <case_id> <check> <pass|fail>
  local row tmp
  row="$(python3 - "$RUN_ID" "$PACK" "$1" "$2" "$3" "$(NOW)" <<'PYEOF'
import json, sys
run_id, pack, case_id, chk, result, ts = sys.argv[1:7]
print(json.dumps({
    "schema_version": "1.0.0", "run_id": run_id, "pack": pack,
    "case_id": case_id, "check": chk, "result": result,
    "exclusion_reason": None,
    "receipt_ref": "ledger/receipts/%s/%s.json" % (run_id, case_id),
    "judge": "deterministic", "ts": ts}))
PYEOF
)"
  tmp="$FIX/receipt-row.json"
  printf '%s\n' "$row" > "$tmp"
  "$SVAL" "$SCHEMAS/eval-receipt-row.schema.json" "$tmp" >/dev/null
  check "receipt helper: row for $1/$2 schema-valid" 0 $?
  printf '%s\n' "$row" >> "$RECEIPTS"
}

# ledger helper: build run-ledger row -> validate -> append.
ledger_append() { # <outcome> <attempts> <goal>
  local row tmp
  row="$(python3 - "$RUN_ID" "$1" "$2" "$3" "$(NOW)" <<'PYEOF'
import json, sys
run_id, outcome, attempts, goal, ts = sys.argv[1:6]
print(json.dumps({
    "schema_version": "1.0.0", "run_id": run_id,
    "atom_id": "atom-s6-eval-pack", "ts_open": ts, "ts_close": ts,
    "goal": goal,
    "verify_template": {"template_id": "grep-count", "template_version": "1"},
    "verify_args": [{"name": "pattern", "value": "NO_SUCH_TOKEN_S6_ESCALATE"}],
    "outcome": outcome, "attempts": int(attempts),
    "workflow_ref": None, "thread_id": "thr-s6-eval-pack",
    "operator_id": "sankalpasawa", "evidence_ref": None}))
PYEOF
)"
  tmp="$FIX/ledger-row.json"
  printf '%s\n' "$row" > "$tmp"
  "$SVAL" "$SCHEMAS/run-ledger-row.schema.json" "$tmp" >/dev/null
  check "ledger helper: row (outcome=$1) schema-valid" 0 $?
  printf '%s\n' "$row" >> "$RUN_LEDGER"
}

echo "== pack file present =="
[ -s "$PACK_FILE" ] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$PACK_FILE"
check "pack: eval-pack-v1-follow.json exists + parses" 0 $?

# --- case: register (proposal -> approve -> entry valid) --------------------
echo "== case: register =="
head -1 "$VALID_WF" > "$FIX/base.json"
python3 - "$FIX/base.json" "$FIX/proposed.json" <<'PYEOF'
import json, sys
e = json.load(open(sys.argv[1]))
e.update(workflow_id="W-emi-reconcile", version="0.1.0",
         title="EMI reconciliation", reuse_tag="lending-collections",
         status="proposed", approved_by=None, ts_registered=None)
json.dump(e, open(sys.argv[2], "w"))
PYEOF
"$REGISTRY" add "$FIX/proposed.json" >/dev/null
RC1=$?
check "register: proposed entry adds (schema-valid)" 0 $RC1

# APPROVE is an operator action in the builder gate (registry-cli spec) --
# the operator materializes the registered entry.
python3 - "$FIX/base.json" "$FIX/approved.json" <<'PYEOF'
import json, sys, time
e = json.load(open(sys.argv[1]))
e.update(workflow_id="W-emi-reconcile", version="1.0.0",
         title="EMI reconciliation", reuse_tag="lending-collections",
         status="registered", approved_by="sankalpasawa",
         ts_registered="2026-08-19T00:00:00Z")
json.dump(e, open(sys.argv[2], "w"))
PYEOF
"$REGISTRY" add "$FIX/approved.json" >/dev/null
RC2=$?
check "register: approved entry adds as registered" 0 $RC2
SHOW="$("$REGISTRY" show W-emi-reconcile@1.0.0 2>/dev/null)"
RC3=$?
check "register: show finds registered entry" 0 $RC3
echo "$SHOW" | grep -q '"status": *"registered"'
RC4=$?
check_ok "register: entry status=registered" $RC4
if [ $RC1 -eq 0 ] && [ $RC2 -eq 0 ] && [ $RC3 -eq 0 ] && [ $RC4 -eq 0 ]; then R=pass; else R=fail; fi
receipt_append register registry_add_proposed_entry_valid "$([ $RC1 -eq 0 ] && echo pass || echo fail)"
receipt_append register operator_approve_materializes_registered_entry "$R"

# --- case: follow (FOLLOW for registered, CONSTRUCT for unknown) ------------
echo "== case: follow =="
head -1 "$VALID_WF" > "$FIX/kyc.json"    # W-kyc-verify@1.2.0 registered, reuse_tag=lending-onboarding
"$REGISTRY" add "$FIX/kyc.json" >/dev/null
check "follow: seed registered W-kyc-verify fixture" 0 $?
OUT="$("$RESOLVE" --ask "verify a brand-new borrower" --reuse-tag lending-onboarding)"
RCF=$?
check "follow: resolve exits 0" 0 $RCF
MF=0; [ "$(json_field "$OUT" mode)" = FOLLOW ] && [ "$(json_field "$OUT" workflow_id)" = W-kyc-verify ] || MF=1
check_ok "follow: mode=FOLLOW workflow_id=W-kyc-verify" $MF
receipt_append follow resolve_follow_registered "$([ $RCF -eq 0 ] && [ $MF -eq 0 ] && echo pass || echo fail)"

OUT="$("$RESOLVE" --ask "novel one-off ask with no registered workflow" --reuse-tag no-such-tag-xyz)"
RCC=$?
check "follow: resolve (unknown) exits 0" 0 $RCC
MC=0; [ "$(json_field "$OUT" mode)" = CONSTRUCT ] || MC=1
check_ok "follow: unknown ask -> mode=CONSTRUCT" $MC
receipt_append follow resolve_construct_unknown "$([ $RCC -eq 0 ] && [ $MC -eq 0 ] && echo pass || echo fail)"

# --- case: fail-retry (grep-count fails, fix, passes) -----------------------
echo "== case: fail-retry =="
printf 'ledger line one\nledger line two\n' > "$FIX/data.txt"
O1="$("$VERIFY" --template grep-count --version 1 --arg pattern=EMI-POSTED --arg "file=$FIX/data.txt" --arg min=1)"
A1=$?
check "fail-retry: attempt 1 fails" 1 $A1
G1=0; grep -q "OUTCOME: fail-retry" <<<"$O1" || G1=1
check_ok "fail-retry: attempt 1 OUTCOME: fail-retry" $G1
printf 'EMI-POSTED LN-88213\n' >> "$FIX/data.txt"   # the fix
O2="$("$VERIFY" --template grep-count --version 1 --arg pattern=EMI-POSTED --arg "file=$FIX/data.txt" --arg min=1)"
A2=$?
check "fail-retry: attempt 2 passes after fix" 0 $A2
G2=0; grep -q "OUTCOME: pass" <<<"$O2" || G2=1
check_ok "fail-retry: attempt 2 OUTCOME: pass" $G2
receipt_append fail-retry grep_count_fails_then_passes "$([ $A1 -eq 1 ] && [ $G1 -eq 0 ] && [ $A2 -eq 0 ] && [ $G2 -eq 0 ] && echo pass || echo fail)"

# --- case: fail-escalate (verify fails at max attempts; escalation reported) -
echo "== case: fail-escalate =="
E_FAILS=0
for attempt in 1 2; do
  "$VERIFY" --template grep-count --version 1 --arg pattern=NO_SUCH_TOKEN_S6_ESCALATE --arg "file=$FIX/data.txt" --arg min=1 | grep -q "OUTCOME: fail-retry" && E_FAILS=$((E_FAILS+1))
done
check_ok "fail-escalate: 2/2 attempts fail-retry" "$([ $E_FAILS -eq 2 ]; echo $?)"
if [ $E_FAILS -eq 2 ]; then
  echo "ESCALATE: run_id=$RUN_ID template=grep-count attempts=2 max_attempts=2 -> fail-escalate (harness policy; sutra-verify itself only ever emits pass|fail-retry)"
  ledger_append fail-escalate 2 "S6 eval-pack escalation drill: grep-count cannot pass without a fix"
  ER=pass
else
  ER=fail
fi
receipt_append fail-escalate escalation_reported_after_max_attempts "$ER"

# --- case: receipt (whole receipts file schema-valid) -----------------------
echo "== case: receipt =="
"$SVAL" "$SCHEMAS/eval-receipt-row.schema.json" "$RECEIPTS" >/dev/null
RR=$?
check "receipt: receipts.jsonl validates wholesale" 0 $RR
receipt_append receipt receipts_file_schema_valid "$([ $RR -eq 0 ] && echo pass || echo fail)"

# --- case: counter (run-ledger rows joined to receipts via run_id) ----------
echo "== case: counter =="
COUNT="$(python3 - "$RUN_LEDGER" "$RECEIPTS" <<'PYEOF'
import json, sys, os
def rows(p):
    if not os.path.exists(p): return []
    return [json.loads(l) for l in open(p) if l.strip()]
receipt_ids = {r["run_id"] for r in rows(sys.argv[2])}
print(sum(1 for r in rows(sys.argv[1]) if r["run_id"] in receipt_ids))
PYEOF
)"
echo "counter: run-ledger rows joined to receipts via run_id = $COUNT"
CN=0; [[ "$COUNT" =~ ^[0-9]+$ ]] || CN=1
check_ok "counter: count prints as a bare integer" $CN
CV=0; [ "$COUNT" = 0 ] || [ "$COUNT" = 1 ] || CV=1
check_ok "counter: count is 0 or 1 (currently: $COUNT)" $CV
receipt_append counter ledger_receipt_join_count_prints "$([ $CN -eq 0 ] && [ $CV -eq 0 ] && echo pass || echo fail)"

# --- summary ----------------------------------------------------------------
echo
echo "receipts emitted: $(wc -l < "$RECEIPTS" | tr -d ' ') rows (all schema-validated at append)"
echo "run-ledger rows:  $(wc -l < "$RUN_LEDGER" | tr -d ' ')"
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
