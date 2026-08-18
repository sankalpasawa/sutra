#!/usr/bin/env bash
# test_resolve.sh -- W-BUILD-V1 S4-C6 tests for sutra-resolve
# (FOLLOW/CONSTRUCT resolution against the real registry).
# Seeds the registry via the C1 CLI (sutra-registry add) with a fixture entry.
# Inputs: workflow-definition fixtures only (v1-build law).
# Instance data ONLY under ~/.sutra-native/ (throwaway subdir, cleaned on exit).
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$SELF_DIR/../../bin"
SCHEMAS="$(cd "$SELF_DIR/../../../../os/native/schemas" && pwd)"
VALID="$SCHEMAS/fixtures/workflow-definition.valid.jsonl"
REGISTRY="$BIN/sutra-registry"
RESOLVE="$BIN/sutra-resolve"

export SUTRA_NATIVE_HOME="$HOME/.sutra-native/test-resolve-$$"
FIX="$SUTRA_NATIVE_HOME/.fixtures"
trap 'rm -rf "$SUTRA_NATIVE_HOME"' EXIT
mkdir -p "$FIX"

PASS=0; FAIL=0
check() { # <name> <expected_rc> <actual_rc>
  if [ "$2" -eq "$3" ]; then PASS=$((PASS+1)); echo "PASS: $1 (rc=$3)"
  else FAIL=$((FAIL+1)); echo "FAIL: $1 (want rc=$2 got rc=$3)"; fi
}
check_ok() { # <name> <0-or-1 from a predicate>
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $1"
  else FAIL=$((FAIL+1)); echo "FAIL: $1"; fi
}

# json_field <json> <field> -> prints value (python3 stdlib only)
json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]))' "$2" <<<"$1"
}

# --- 1. seed registry via C1 CLI with a fixture entry -----------------------
# First valid fixture row: W-kyc-verify@1.2.0, status=registered, 3 steps,
# reuse_tag=lending-onboarding.
head -1 "$VALID" > "$FIX/entry-registered.json"
"$REGISTRY" add "$FIX/entry-registered.json" >/dev/null
check "seed: registry add fixture entry" 0 $?

# A proposed (NOT registered) entry -- resolve must never FOLLOW it.
python3 - "$FIX/entry-registered.json" "$FIX/entry-proposed.json" <<'PYEOF'
import json, sys
e = json.load(open(sys.argv[1]))
e.update(workflow_id="W-emi-reconcile", version="0.1.0",
         title="EMI reconciliation", reuse_tag="lending-collections",
         status="proposed", approved_by=None, ts_registered=None)
json.dump(e, open(sys.argv[2], "w"))
PYEOF
"$REGISTRY" add "$FIX/entry-proposed.json" >/dev/null
check "seed: registry add proposed entry" 0 $?

# --- 2. FOLLOW via --reuse-tag ----------------------------------------------
OUT="$("$RESOLVE" --ask "verify a brand-new borrower" --reuse-tag lending-onboarding)"
check "resolve: reuse-tag match exits 0" 0 $?
check_ok "reuse-tag: mode=FOLLOW"          "$([ "$(json_field "$OUT" mode)" = FOLLOW ]; echo $?)"
check_ok "reuse-tag: workflow_id"          "$([ "$(json_field "$OUT" workflow_id)" = W-kyc-verify ]; echo $?)"
check_ok "reuse-tag: version=1.2.0"        "$([ "$(json_field "$OUT" version)" = 1.2.0 ]; echo $?)"
check_ok "reuse-tag: steps_count=3"        "$([ "$(json_field "$OUT" steps_count)" = 3 ]; echo $?)"
check_ok "reuse-tag: runs=0 (F1: no ledger)" "$([ "$(json_field "$OUT" runs)" = 0 ]; echo $?)"
check_ok "reuse-tag: note verbatim"        "$([ "$(json_field "$OUT" note)" = "following the registered workflow" ]; echo $?)"

# --- 3. FOLLOW via title-token overlap --------------------------------------
OUT="$("$RESOLVE" --ask "run KYC verification for a borrower")"
check "resolve: title-overlap match exits 0" 0 $?
check_ok "title-overlap: mode=FOLLOW"      "$([ "$(json_field "$OUT" mode)" = FOLLOW ]; echo $?)"
check_ok "title-overlap: workflow_id"      "$([ "$(json_field "$OUT" workflow_id)" = W-kyc-verify ]; echo $?)"

# --- 4. no match -> honest CONSTRUCT ----------------------------------------
# Overlaps only the PROPOSED entry's title ("EMI") -- must NOT follow it.
OUT="$("$RESOLVE" --ask "reconcile emi payments")"
check "resolve: no-match exits 0" 0 $?
check_ok "no-match: mode=CONSTRUCT"        "$([ "$(json_field "$OUT" mode)" = CONSTRUCT ]; echo $?)"
check_ok "no-match: note verbatim"         "$([ "$(json_field "$OUT" note)" = "no registered workflow matches" ]; echo $?)"
check_ok "no-match: proposal_offer=true"   "$([ "$(json_field "$OUT" proposal_offer)" = True ]; echo $?)"
check_ok "no-match: no workflow_id key"    "$([ "$(json_field "$OUT" workflow_id)" = None ]; echo $?)"

# --- 5. empty registry -> CONSTRUCT; usage errors ---------------------------
check_ok "empty registry: mode=CONSTRUCT"  "$([ "$(SUTRA_NATIVE_HOME=$SUTRA_NATIVE_HOME/does-not-exist "$RESOLVE" --ask "verify kyc" | python3 -c 'import json,sys; print(json.load(sys.stdin)["mode"])')" = CONSTRUCT ]; echo $?)"
"$RESOLVE" >/dev/null 2>&1; check "usage: missing --ask exits 2" 2 $?
"$RESOLVE" --ask "" >/dev/null 2>&1; check "usage: empty --ask exits 2" 2 $?
"$RESOLVE" --ask x --bogus y >/dev/null 2>&1; check "usage: unknown flag exits 2" 2 $?

echo "----------------------------------------"
echo "test_resolve.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
