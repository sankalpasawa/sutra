#!/bin/bash
# flow-orchestrator test suite (D62 / ADR-029).
# Fixtures f1..f8. Prints "PASS <id>" / "FAIL <id> <why>" per fixture,
# then a summary line "flow-orchestrator: N/8 PASS". Exit 0 only on 8/8.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$HERE/../.." && pwd)"
# FLOW_BIN_DIR override exists for harness self-testing with mock bins only.
BIN_DIR="${FLOW_BIN_DIR:-$PLUGIN_DIR/bin}"

PASS_N=0
FAIL_N=0
pass() { echo "PASS $1"; PASS_N=$((PASS_N+1)); }
fail() { echo "FAIL $1 $2"; FAIL_N=$((FAIL_N+1)); }

# Resolve a bin script by role keyword under bin/*flow* (build lands in
# parallel; exact names are owned by the build agents — e.g.
# workflow-type-match.sh, flow-ledger-append.sh).
resolve_bin() {
  local kw f
  for kw in "$@"; do
    for f in "$BIN_DIR"/*flow*"$kw"* "$BIN_DIR"/*"$kw"*; do
      [ -f "$f" ] && [ -x "$f" ] && { printf '%s\n' "$f"; return 0; }
    done
  done
  return 1
}

VALIDATOR="$(resolve_bin contract valid check || true)"
MATCHER="$(resolve_bin match resolv || true)"
FACTORS="$(resolve_bin factor || true)"
LEDGER="$(resolve_bin ledger || true)"

# Run the validator on a fixture file. Tries stdin first; if the exit code
# is outside the {0 VALID, 1 INVALID} contract (i.e. a usage error), retries
# with the file as a positional argument. Sets V_OUT / V_RC.
run_validator() {
  V_OUT="$("$VALIDATOR" < "$1" 2>&1)"; V_RC=$?
  if [ "$V_RC" -ne 0 ] && [ "$V_RC" -ne 1 ]; then
    V_OUT="$("$VALIDATOR" "$1" 2>&1)"; V_RC=$?
  fi
}

# --- f1: valid contract -> VALID / exit 0 -------------------------------
if [ -z "$VALIDATOR" ]; then
  fail f1 "validator bin not found under $BIN_DIR/*flow*"
else
  run_validator "$HERE/f1-good-contract.json"; out="$V_OUT"; rc="$V_RC"
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "VALID" \
     && ! printf '%s' "$out" | grep -q "INVALID"; then
    pass f1
  else
    fail f1 "expected VALID/exit0, got rc=$rc out=${out:0:120}"
  fi
fi

# --- f2/f3/f4: invalid contracts -> INVALID / exit 1 --------------------
for fx in f2-bad-missing-field f3-bad-enum f4-transcript-shaped; do
  id="${fx%%-*}"
  if [ -z "$VALIDATOR" ]; then
    fail "$id" "validator bin not found under $BIN_DIR/*flow*"
    continue
  fi
  run_validator "$HERE/$fx.json"; out="$V_OUT"; rc="$V_RC"
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "INVALID"; then
    pass "$id"
  else
    fail "$id" "expected INVALID/exit1, got rc=$rc out=${out:0:120}"
  fi
done

# --- f5: matcher cases (output must start with expected prefix) ---------
if [ -z "$MATCHER" ]; then
  fail f5 "matcher bin not found under $BIN_DIR/*flow*"
else
  f5_ok=1
  f5_why=""
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    intent="${line%% :: *}"
    prefix="${line##* :: }"
    # Pin scopes so matching is deterministic regardless of caller cwd:
    # child scope = this test dir (empty), platform scope = the plugin.
    out="$(CLAUDE_PROJECT_DIR="$HERE" CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR" \
           "$MATCHER" "$intent" 2>&1)"
    first="$(printf '%s\n' "$out" | head -n1)"
    case "$first" in
      "$prefix"*) : ;;
      *) f5_ok=0
         f5_why="intent '$intent' -> '${first:0:80}' (want prefix '$prefix')"
         break ;;
    esac
  done < "$HERE/f5-matcher-cases.txt"
  if [ "$f5_ok" -eq 1 ]; then pass f5; else fail f5 "$f5_why"; fi
fi

# --- f6: factors -> JSON with integer unit_factors.steps_est, deterministic
if [ -z "$FACTORS" ]; then
  fail f6 "factors bin not found under $BIN_DIR/*flow*"
else
  unit="$(sed -n 's/^unit: //p' "$HERE/f6-factors-case.txt" | head -n1)"
  out1="$("$FACTORS" "$unit" 2>&1)"; rc1=$?
  out2="$("$FACTORS" "$unit" 2>&1)"; rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ]; then
    fail f6 "factors exited rc1=$rc1 rc2=$rc2"
  elif ! printf '%s' "$out1" | jq -e . >/dev/null 2>&1; then
    fail f6 "output is not valid JSON: ${out1:0:120}"
  elif ! printf '%s' "$out1" \
       | jq -e '.unit_factors.steps_est | type == "number" and . == floor' >/dev/null 2>&1; then
    fail f6 "unit_factors.steps_est missing or not an integer"
  elif [ "$out1" != "$out2" ]; then
    fail f6 "double-run output not byte-identical"
  else
    pass f6
  fi
fi

# --- f7: ledger append redacts secrets ----------------------------------
if [ -z "$LEDGER" ]; then
  fail f7 "ledger bin not found under $BIN_DIR/*flow*"
else
  tmp="$(mktemp "${TMPDIR:-/tmp}/flow-ledger.XXXXXX")"
  FLOW_LEDGER_PATH="$tmp" "$LEDGER" \
    < "$HERE/f7-ledger-redaction.json" >/dev/null 2>&1
  if [ ! -s "$tmp" ]; then
    fail f7 "ledger file empty after append"
  elif ! grep -q "REDACTED" "$tmp"; then
    fail f7 "no [REDACTED] marker in ledger row"
  elif grep -q "sk-abcdefghijklmnop" "$tmp"; then
    fail f7 "raw sk- token leaked into ledger"
  elif grep -q "ghp_" "$tmp"; then
    fail f7 "raw ghp_ token leaked into ledger"
  elif grep -q "xoxb-" "$tmp"; then
    fail f7 "raw xoxb- token leaked into ledger"
  else
    pass f7
  fi
  rm -f "$tmp"
fi

# --- f8: flag + docs + bin assertions -----------------------------------
if out="$(bash "$HERE/f8-flag-and-docs.sh" 2>&1)"; then
  pass f8
else
  why="$(printf '%s\n' "$out" | grep -m1 '^f8:' || echo 'f8: assertions failed')"
  fail f8 "$why"
fi

# --- summary ------------------------------------------------------------
echo "flow-orchestrator: $PASS_N/8 PASS"
if [ "$PASS_N" -eq 8 ]; then exit 0; else exit 1; fi
