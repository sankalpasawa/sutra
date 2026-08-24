#!/usr/bin/env bash
# test_daemon.sh -- P1 standalone daemon: gate, router, executor, builder gate,
# fallback-ask, throw-back-always, idempotency, crash sweep, tamper guard.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/../../bin"
DAEMON="$BIN/sutra-daemon"
pass=0; fail=0
OUT=""; RC=0

fresh() {
  TMP="$(mktemp -d)"
  export SUTRA_NATIVE_HOME="$TMP/.sutra-native"
  mkdir -p "$SUTRA_NATIVE_HOME"
}

run() { OUT="$("$@" 2>&1)"; RC=$?; }

t() {
  local name="$1" want_rc="$2"; shift 2
  local ok=1
  [ "$RC" -eq "$want_rc" ] || ok=0
  local s
  for s in "$@"; do printf '%s' "$OUT" | grep -qF -- "$s" || ok=0; done
  if [ "$ok" -eq 1 ]; then echo "PASS $name"; pass=$((pass+1));
  else echo "FAIL $name (rc=$RC want=$want_rc)"; printf '%s\n' "$OUT" | sed 's/^/    /' | head -14; fail=$((fail+1)); fi
}

FAKE_HOST_OK='["/bin/sh","-c","printf \"purpose provenance daemon note\" > \"$SUTRA_NATIVE_HOME/daemon/outputs/$OUT_ID.md\""]'

propose_route() {  # $1 = pattern
  run python3 "$DAEMON" route-propose --pattern "$1" --workflow "W-md-authoring@0.1.0" \
    --host claude-bare --prompt-template "Author a note on: {text}. Write to {out}." \
    --verify-template-id grep-count --verify-version 1 \
    --verify-arg "pattern=provenance" --verify-arg "file={out}" --verify-arg "min=1"
  RID="$(printf '%s' "$OUT" | sed -n 's/^proposed \(r-[a-f0-9]*\).*/\1/p')"
}

# --- t1: ask appends a valid row --------------------------------------------
fresh
run python3 "$DAEMON" ask "write a note on EMI reconciliation"
t t1-ask-queues 0 "queued in-"
run python3 -c "import json,os; [json.loads(l) for l in open(os.environ['SUTRA_NATIVE_HOME']+'/daemon/inbox.jsonl')]; print('rows-ok')"
t t1b-inbox-parseable 0 "rows-ok"

# --- t2: no approved routes -> fallback ask, consumed ------------------------
run python3 "$DAEMON" start --once
t t2-once-runs 0 "handled 1"
run python3 "$BIN/sutra-outbox" list
t t2b-fallback-ask 0 "daemon:fallback" "no approved route matches"
run python3 "$DAEMON" status
t t2c-consumed-fallback 0 '"fallback": 1' "pending: 0"

# --- t3: builder validates regex ---------------------------------------------
run python3 "$DAEMON" route-propose --pattern "([bad" --workflow W --host claude-bare \
  --prompt-template "x" --verify-template-id file-exists --verify-version 1
t t3-bad-regex-refused 2 "does not compile"

# --- t4: approve requires the human flags (F8) -------------------------------
propose_route "^(write|author) "
t t4-propose-ok 0 "proposed r-" "route-approve"
run python3 "$DAEMON" route-approve --route-id "$RID"
t t4b-approve-needs-human 1 "human act"
run python3 "$DAEMON" route-approve --route-id "$RID" --i-approve
t t4c-approve-needs-operator 1 "human act"

# --- t5: approve flips with content hash (tty honor-gate via ack seam) -------
run python3 "$DAEMON" route-approve --route-id "$RID" --i-approve --operator sankalpasawa
t t5a-approve-needs-tty 1 "interactive terminal"
run env SUTRA_DAEMON_APPROVE_ACK=1 python3 "$DAEMON" route-approve --route-id "$RID" --i-approve --operator sankalpasawa
t t5-approved 0 "approved $RID by sankalpasawa hash="
run env SUTRA_DAEMON_APPROVE_ACK=1 python3 "$DAEMON" route-approve --route-id "$RID" --i-approve --operator sankalpasawa
t t5b-no-relaunder 1 "only 'proposed' routes can be approved"
run test -s "$SUTRA_NATIVE_HOME/daemon/route-approvals.jsonl"
t t5c-approval-audit-row 0

# --- t6: matched input runs fake host -> ledger pass + state passed ----------
run python3 "$DAEMON" ask "write a note on KYC verification for W-kyc-verify"
IID="$(printf '%s' "$OUT" | sed 's/^queued //')"
SUTRA_DAEMON_HOST_CMD="[\"/bin/sh\",\"-c\",\"printf 'purpose provenance kyc note' > $SUTRA_NATIVE_HOME/daemon/outputs/$IID.md\"]" \
  run env SUTRA_DAEMON_HOST_CMD="[\"/bin/sh\",\"-c\",\"printf 'purpose provenance kyc note' > $SUTRA_NATIVE_HOME/daemon/outputs/$IID.md\"]" python3 "$DAEMON" start --once
t t6-run-handled 0 "handled 1"
run grep -c '"outcome":"pass"' "$SUTRA_NATIVE_HOME/ledger/run-ledger.jsonl"
t t6b-ledger-pass 0 "1"
run python3 "$DAEMON" status
t t6c-state-passed 0 '"passed": 1'

# --- t7: idempotency -- second pass consumes nothing --------------------------
run python3 "$DAEMON" start --once
if [ "$RC" -eq 0 ] && ! printf '%s' "$OUT" | grep -q "handled"; then
  echo "PASS t7-idempotent"; pass=$((pass+1))
else
  echo "FAIL t7-idempotent (rc=$RC out=$OUT)"; fail=$((fail+1))
fi

# --- t8: host nonzero -> throwback + fail-escalate row ------------------------
run python3 "$DAEMON" ask "write a failing one"
run env SUTRA_DAEMON_HOST_CMD='["/bin/sh","-c","echo boom; exit 3"]' python3 "$DAEMON" start --once
t t8-host-fail-handled 0 "handled 1"
run python3 "$BIN/sutra-outbox" list
t t8b-throwback-ask 0 "daemon:throwback" "host exited 3"
run grep -c '"outcome":"fail-escalate"' "$SUTRA_NATIVE_HOME/ledger/run-ledger.jsonl"
t t8c-ledger-escalate 0 "1"

# --- t9: verify fail -> throwback (host ok but check not satisfied) -----------
run python3 "$DAEMON" ask "write a hollow one"
run env SUTRA_DAEMON_HOST_CMD='["/bin/sh","-c","true"]' python3 "$DAEMON" start --once
t t9-verify-fail-handled 0 "handled 1"
run python3 "$BIN/sutra-outbox" list
t t9b-verify-throwback 0 "pinned check FAILED"

# --- t10: malformed inbox line -> quarantined, daemon continues ---------------
printf 'not json at all\n' >> "$SUTRA_NATIVE_HOME/daemon/inbox.jsonl"
run python3 "$DAEMON" ask "write a good one after garbage"
IID2="$(printf '%s' "$OUT" | sed 's/^queued //')"
run env SUTRA_DAEMON_HOST_CMD="[\"/bin/sh\",\"-c\",\"printf 'purpose provenance ok' > $SUTRA_NATIVE_HOME/daemon/outputs/$IID2.md\"]" python3 "$DAEMON" start --once
t t10-continues-past-garbage 0 "handled 1"
run test -s "$SUTRA_NATIVE_HOME/daemon/quarantine.jsonl"
t t10b-quarantined 0

# --- t11: crash sweep -- 'running' state on restart -> throwback --------------
python3 - <<PYEOF
import json, os
p = os.environ["SUTRA_NATIVE_HOME"] + "/daemon/state.json"
st = json.load(open(p))
st["in-fake-crashed"] = {"state": "running", "ts": "2026-08-20T00:00:00Z", "run_id": "run-fake"}
json.dump(st, open(p, "w"))
PYEOF
run python3 "$DAEMON" start --once
t t11-sweep-runs 0
run python3 "$BIN/sutra-outbox" list
t t11b-interrupted-thrown 0 "interrupted mid-work"

# --- t12: route tamper -> throwback, nothing runs -----------------------------
python3 - <<PYEOF
import json, os
p = os.environ["SUTRA_NATIVE_HOME"] + "/daemon/routes.json"
r = json.load(open(p))
[x for x in r if x["status"] == "approved"][0]["prompt_template"] = "EVIL {text}"
json.dump(r, open(p, "w"))
PYEOF
run python3 "$DAEMON" ask "write one against tampered route"
run python3 "$DAEMON" start --once
t t12-tamper-handled 0 "handled 1"
run python3 "$BIN/sutra-outbox" list
t t12b-tamper-thrown 0 "no longer matches its approved hash"

# --- t13: status renders ------------------------------------------------------
run python3 "$DAEMON" status
t t13-status 0 "daemon:" "routes:" "consumed:"

# --- t14: corrupt state.json -> refuse pass, durable ask, no reprocessing -----
cp "$SUTRA_NATIVE_HOME/daemon/state.json" "$TMP/state.backup"
printf '{torn' > "$SUTRA_NATIVE_HOME/daemon/state.json"
run python3 "$DAEMON" start --once
t t14-corrupt-state-refuses 0
run python3 "$BIN/sutra-outbox" list
t t14b-corrupt-state-ask 0 "state.json" "refusing to process"
cp "$TMP/state.backup" "$SUTRA_NATIVE_HOME/daemon/state.json"

# --- t15: path-traversal input_id -> quarantined, not executed ----------------
printf '{"input_id":"../evil","ts":"2026-08-20T00:00:00Z","text":"write me"}\n' >> "$SUTRA_NATIVE_HOME/daemon/inbox.jsonl"
run python3 "$DAEMON" start --once
t t15-traversal-skipped 0
run grep -c "path-safety" "$SUTRA_NATIVE_HOME/daemon/quarantine.jsonl"
t t15b-traversal-quarantined 0 "1"

# --- t16: crash sweep trusts the ledger (running + closed pass -> passed) -----
python3 - <<PYEOF
import json, os
home = os.environ["SUTRA_NATIVE_HOME"]
led = json.loads(open(home + "/ledger/run-ledger.jsonl").readline())
st = json.load(open(home + "/daemon/state.json"))
st["in-crashed-after-close"] = {"state": "running", "ts": "x", "run_id": led["run_id"]}
json.dump(st, open(home + "/daemon/state.json", "w"))
PYEOF
run python3 "$DAEMON" start --once
t t16-sweep-runs 0
run python3 -c "import json,os; st=json.load(open(os.environ['SUTRA_NATIVE_HOME']+'/daemon/state.json')); print(st['in-crashed-after-close']['state'])"
t t16b-ledger-trusted 0 "passed"

# --- t17: department/charter binding — display metadata, not behavior ---------
run python3 "$DAEMON" route-propose --pattern "^reconcile " --workflow "W-emi-reconcile@1.0.0" \
  --host codex --prompt-template "x {text}" --verify-template-id file-exists --verify-version 1 \
  --department "Finance Ops" --charter "EMI Reconciliation"
RID2="$(printf '%s' "$OUT" | sed -n 's/^proposed \(r-[a-f0-9]*\).*/\1/p')"
t t17-propose-with-binding 0 "proposed r-"
run python3 "$DAEMON" route-list
t t17b-binding-shown 0 "[Finance Ops / EMI Reconciliation]"
run env SUTRA_DAEMON_APPROVE_ACK=1 python3 "$DAEMON" route-approve --route-id "$RID2" --i-approve --operator sankalpasawa
t t17c-binding-approvable 0 "approved $RID2"
python3 - <<PYEOF
import json, os
p = os.environ["SUTRA_NATIVE_HOME"] + "/daemon/routes.json"
r = json.load(open(p))
x = [q for q in r if q["route_id"] == "$RID2"][0]
x["department"] = "Renamed Dept"
json.dump(r, open(p, "w"))
PYEOF
run python3 "$DAEMON" ask "reconcile augusts EMIs"
run env SUTRA_DAEMON_HOST_CMD='["/bin/sh","-c","true"]' python3 "$DAEMON" start --once
if printf '%s' "$OUT" | grep -q "handled 1"; then
  if python3 "$BIN/sutra-outbox" list | grep -q "approved hash.*reconcile augusts"; then
    echo "FAIL t17d-metadata-edit-not-tamper (binding edit disabled the route)"; fail=$((fail+1))
  else
    echo "PASS t17d-metadata-edit-not-tamper"; pass=$((pass+1))
  fi
else
  echo "FAIL t17d-metadata-edit-not-tamper (rc=$RC out=$OUT)"; fail=$((fail+1))
fi

echo "RESULT: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
