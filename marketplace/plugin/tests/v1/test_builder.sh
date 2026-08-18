#!/usr/bin/env bash
# test_builder.sh -- W-BUILD-V1 S4-C3 builder gate tests.
# Proves, among other things, F8: a propose immediately followed by approve
# WITHOUT --i-approve exits nonzero and registers NOTHING.
set -u

BIN="$(cd "$(dirname "$0")/../../bin" && pwd)"
BUILD="$BIN/sutra-build-workflow"
REG="$BIN/sutra-registry"

export SUTRA_NATIVE_HOME="$(mktemp -d /tmp/sutra-builder-test.XXXXXX)"
WORK="$(mktemp -d /tmp/sutra-builder-work.XXXXXX)"
trap 'rm -rf "$SUTRA_NATIVE_HOME" "$WORK"' EXIT
PROPOSALS="$SUTRA_NATIVE_HOME/registry/proposals"
STORE="$SUTRA_NATIVE_HOME/registry/workflows"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (want $1, got $2)"; fi; }

# ---- fixtures (lending examples per standing direction) -------------------
cat > "$WORK/transcript-good.json" <<'EOF'
{
  "recorded": "improvised disbursal run 2026-08-19",
  "steps": [
    {"name": "draft-disbursal-memo",
     "how": "Write the loan disbursal memo with borrower, amount, tenure",
     "verify": {"template_id": "file-exists", "template_version": "1",
                "args": [{"name": "path", "value": "/tmp/memo.md"}]}},
    {"name": "check-sanction-clauses",
     "how": "Confirm the memo carries all mandatory sanction clauses",
     "verify": {"template_id": "grep-count", "template_version": "1",
                "args": [{"name": "pattern", "value": "Clause"},
                         {"name": "file", "value": "/tmp/memo.md"},
                         {"name": "min", "value": 3}]}}
  ],
  "failure_policy": {"retry_budget": 2, "on_escalate": "credit-ops"},
  "reuse_tag": "lending-disbursal"
}
EOF
cat > "$WORK/transcript-unpinned.json" <<'EOF'
{"steps": [{"name": "s", "how": "do a thing",
  "verify": {"template_id": "no-such-template", "template_version": "9",
             "args": []}}]}
EOF
cat > "$WORK/transcript-empty.json" <<'EOF'
{"steps": []}
EOF
printf 'not json at all {{{' > "$WORK/transcript-garbage.json"

# ---- T1: propose happy path ----------------------------------------------
"$BUILD" propose --from-transcript "$WORK/transcript-good.json" \
  --id W-disburse-loan --title "Loan disbursal" \
  --goal "Disburse a sanctioned loan with a verified memo" \
  --version 0.1.0 --proposed-by tester >/dev/null 2>&1
check 0 $? "T1 propose (valid transcript) exits 0"
P="$PROPOSALS/W-disburse-loan@0.1.0.json"
[ -f "$P" ] && ok "T1 proposal file written" || bad "T1 proposal file missing"
grep -q '"status": "proposed"' "$P" && ok "T1 status=proposed" \
  || bad "T1 status not proposed"
grep -q '"approved_by": null' "$P" && ok "T1 approved_by null" \
  || bad "T1 approved_by not null"

# ---- T2: F8 -- approve WITHOUT --i-approve must fail, register nothing ---
"$BUILD" approve --id W-disburse-loan@0.1.0 --operator tester \
  >/dev/null 2>"$WORK/t2.err"
rc=$?
[ "$rc" -ne 0 ] && ok "T2 F8: approve without --i-approve exits nonzero ($rc)" \
  || bad "T2 F8 VIOLATION: approve without --i-approve exited 0"
grep -qi "i-approve" "$WORK/t2.err" && ok "T2 refusal names --i-approve" \
  || bad "T2 refusal does not name --i-approve"
[ ! -e "$STORE/W-disburse-loan@0.1.0.json" ] \
  && ok "T2 nothing landed in registry store" \
  || bad "T2 F8 VIOLATION: entry reached registry store"
grep -q '"status": "proposed"' "$P" && ok "T2 proposal still proposed" \
  || bad "T2 proposal state changed without --i-approve"

# ---- T3: approve without --operator must fail ----------------------------
"$BUILD" approve --id W-disburse-loan@0.1.0 --i-approve >/dev/null 2>&1
[ $? -ne 0 ] && ok "T3 approve without --operator exits nonzero" \
  || bad "T3 approve without --operator exited 0"

# ---- T4: approve with --operator AND --i-approve registers ---------------
"$BUILD" approve --id W-disburse-loan@0.1.0 --operator sankalpasawa \
  --i-approve >/dev/null 2>&1
check 0 $? "T4 explicit approve exits 0"
"$REG" show W-disburse-loan@0.1.0 > "$WORK/t4.json" 2>/dev/null
grep -q '"status": *"registered"' "$WORK/t4.json" \
  && ok "T4 registry entry status=registered" \
  || bad "T4 registry entry not registered"
grep -q '"approved_by": *"sankalpasawa"' "$WORK/t4.json" \
  && ok "T4 approved_by recorded" || bad "T4 approved_by missing"
grep -q '"ts_registered": *"20' "$WORK/t4.json" \
  && ok "T4 ts_registered set" || bad "T4 ts_registered missing"
[ -f "$P.approved" ] && ok "T4 proposal archived as .approved" \
  || bad "T4 proposal not archived"

# ---- T5: judge rejects unpinned template ---------------------------------
"$BUILD" propose --from-transcript "$WORK/transcript-unpinned.json" \
  --id W-bad-pin --title t --goal g >/dev/null 2>"$WORK/t5.err"
check 1 $? "T5 unpinned template exits 1"
grep -q "judge" "$WORK/t5.err" && ok "T5 stderr names judge stage" \
  || bad "T5 stderr does not name judge"
[ ! -e "$PROPOSALS/W-bad-pin@0.1.0.json" ] && ok "T5 nothing written" \
  || bad "T5 rejected candidate was written"

# ---- T6: construct rejects empty steps -----------------------------------
"$BUILD" propose --from-transcript "$WORK/transcript-empty.json" \
  --id W-empty --title t --goal g >/dev/null 2>"$WORK/t6.err"
check 1 $? "T6 empty steps exits 1"
grep -q "construct" "$WORK/t6.err" && ok "T6 stderr names construct stage" \
  || bad "T6 stderr does not name construct"

# ---- T7: validate rejects unparseable transcript -------------------------
"$BUILD" propose --from-transcript "$WORK/transcript-garbage.json" \
  --id W-garbage --title t --goal g >/dev/null 2>"$WORK/t7.err"
check 1 $? "T7 garbage transcript exits 1"
grep -q "validate" "$WORK/t7.err" && ok "T7 stderr names validate stage" \
  || bad "T7 stderr does not name validate"

# ---- T8: approve a nonexistent proposal ----------------------------------
"$BUILD" approve --id W-nope --operator tester --i-approve >/dev/null 2>&1
check 4 $? "T8 approve nonexistent exits 4"

# ---- T9: reject flow -----------------------------------------------------
"$BUILD" propose --from-transcript "$WORK/transcript-good.json" \
  --id W-kyc-verify --title "KYC verify" --goal "Verify borrower KYC" \
  >/dev/null 2>&1
check 0 $? "T9 second propose exits 0"
"$BUILD" reject --id W-kyc-verify --reason "steps too coarse" >/dev/null 2>&1
check 0 $? "T9 reject exits 0"
[ -f "$PROPOSALS/W-kyc-verify@0.1.0.json.rejected" ] \
  && ok "T9 proposal archived as .rejected" || bad "T9 no .rejected archive"
"$BUILD" approve --id W-kyc-verify --operator tester --i-approve \
  >/dev/null 2>&1
check 4 $? "T9 approve after reject exits 4"

# ---- summary -------------------------------------------------------------
echo "----------------------------------------"
echo "builder gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
