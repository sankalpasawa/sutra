#!/usr/bin/env bash
# test_run_cost.sh -- sutra-run-cost reads the ledger honestly (B18-8 measurement).
# Same conventions as the other v1 suites: run <cmd>, t <name> <exit> <substrings...>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../../bin/sutra-run-cost"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
OUT=""; RC=0

run() { OUT="$("$@" 2>&1)"; RC=$?; }

t() {
  local name="$1" want_rc="$2"; shift 2
  local ok=1
  [ "$RC" -eq "$want_rc" ] || ok=0
  local s
  for s in "$@"; do
    printf '%s' "$OUT" | grep -qF -- "$s" || ok=0
  done
  if [ "$ok" -eq 1 ]; then echo "PASS $name"; pass=$((pass+1));
  else echo "FAIL $name (rc=$RC want=$want_rc)"; printf '%s\n' "$OUT" | sed 's/^/    /'; fail=$((fail+1)); fi
}

chmod +x "$SRC" 2>/dev/null || true

# --- no ledger dir at all: honest empty report, exit 0 ------------------------
run python3 "$SRC" --ledger-dir "$TMP/nowhere"
t t1-no-ledger-dir 0 "nothing recorded yet"

# --- empty dir (no jsonl): report with closed=0 --------------------------------
mkdir -p "$TMP/led"
run python3 "$SRC" --ledger-dir "$TMP/led"
t t2-empty-dir 0 "closed=0" "not instrumented"

# --- one closed row: duration = ts_close - ts_open (45s) -----------------------
cat > "$TMP/led/run-ledger.jsonl" <<'EOF'
{"schema_version":"1.0.0","run_id":"run-20260818-0001","atom_id":"atom-20260818-0001","ts_open":"2026-08-18T10:00:00Z","ts_close":"2026-08-18T10:00:45Z","goal":"g","verify_template":{"template_id":"file-exists","template_version":"1"},"verify_args":[],"workflow_ref":"W-kyc-verify@1.0.0","thread_id":"t-1","operator_id":"op","outcome":"pass","attempts":1,"evidence_ref":null}
EOF
run python3 "$SRC" --ledger-dir "$TMP/led"
t t3-one-closed-row 0 "run-20260818-0001" "45s" "closed=1" "W-kyc-verify@1.0.0"

# --- clock basis + tokens honesty always printed --------------------------------
t t4-clock-basis 0 "wall-clock UTC" "not instrumented"

# --- open run (.open file) listed without a duration -----------------------------
: > "$TMP/led/run-20260818-0002.open"
run python3 "$SRC" --ledger-dir "$TMP/led"
t t5-open-run-listed 0 "run-20260818-0002" "OPEN (not closed"

# --- malformed line: reported loudly, exit 1 -------------------------------------
echo '{broken json' >> "$TMP/led/run-ledger.jsonl"
run python3 "$SRC" --ledger-dir "$TMP/led"
t t6-malformed-loud 1 "MALFORMED lines" "2"

# --- json mode: parseable, fields present ----------------------------------------
run python3 "$SRC" --ledger-dir "$TMP/led" --json
if [ "$RC" -eq 1 ] && printf '%s' "$OUT" | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r["closed_runs"]==1; assert r["open_runs"]==["run-20260818-0002"]; assert r["malformed_lines"]==[2]; assert r["runs"][0]["wall_seconds"]==45.0; assert "not instrumented" in r["tokens"]'; then
  echo "PASS t7-json-shape"; pass=$((pass+1))
else
  echo "FAIL t7-json-shape (rc=$RC)"; printf '%s\n' "$OUT" | sed 's/^/    /'; fail=$((fail+1))
fi

# --- missing ts_close inside a row (writer bug): duration unavailable, not a guess
mkdir -p "$TMP/led2"
cat > "$TMP/led2/run-ledger.jsonl" <<'EOF'
{"schema_version":"1.0.0","run_id":"run-20260818-0003","ts_open":"2026-08-18T10:00:00Z","outcome":"pass","attempts":1,"workflow_ref":null}
EOF
run python3 "$SRC" --ledger-dir "$TMP/led2"
t t8-no-tsclose-honest 0 "duration unavailable"

# --- usage error ------------------------------------------------------------------
run python3 "$SRC" --bogus
t t9-usage-error 2 "unknown argument"

echo "RESULT: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
