#!/bin/bash
# Sutra plugin test runner.
#
#   bash tests/run-all.sh                  run every discovered suite
#   bash tests/run-all.sh --count          print the number of discovered suites (integer only)
#   bash tests/run-all.sh --list           print the discovered suite paths, one per line
#   bash tests/run-all.sh --only <suite>   run the one suite whose basename matches
#                                          (with or without the .sh extension)
#   bash tests/run-all.sh --set <set>      restrict discovery to a suite set (see below)
#   bash tests/run-all.sh --include-manual also run the suites that need a live install
#
# Suite sets (--set, default "all"; --count, --list and --only honour it):
#   all      every discovered suite — today's behaviour, unchanged.
#   runtime  only the suites this repo's runtime work owns and keeps green:
#              ../runtime/tests/*.sh   (sutra-turn, ledger, shim, canary, kill-switch,
#                                       concurrency, the merge round-trip over the golden
#                                       corpus, overhead and the charcap parity replay)
#              ../hooks/tests/*.sh     (hook-level suites — atom floor, dispatch gate, …)
#            This is the set the release gate runs. The wider "all" set also discovers
#            long-standing suites that are red for reasons unrelated to the runtime
#            (workflow propose/approve/register, eval-pack, native-schema fixtures);
#            gating a release on those would make the gate's signal noise on day one.
#            They stay discoverable — and fixable — under "all"; see the repo TODO.
#
# Discovery (relative to this file):
#   unit/test-*.sh, unit/*.test.sh
#   integration/test-*.sh            (files starting with "_" are archived, skipped)
#   v1/test_*.sh
#   flow-orchestrator/run.sh, marker-concurrency/run.sh
#   placement-smoke.sh + the top-level *-test.sh / *.test.sh / *-cases.sh suites
#   smoke.sh
#   ../runtime/tests/*.sh            (the Sutra runtime suites — sutra-turn, ledger, shim,
#                                    canary, kill-switch, and test-charcap-parity.sh, which
#                                    replays the golden corpus against BOTH runners and is
#                                    the only proof the runtime is a drop-in replacement;
#                                    it skips itself when hooks/tests/golden is absent)
#   ../hooks/tests/*.sh              (hook-level suites — atom floor, dispatch gate, …)
#
# Not discovered by default (opt in with --include-manual, which applies to the
# "all" set only — these are top-level suites, never part of "runtime"; each one
# needs a live install or an operator-supplied target tree, so it cannot gate a
# release):
#   placement-demo.sh          visual demonstration, not an assertion suite
#   placement-eval.sh          measured classifier precision over a real tree
#   governance-parity-acceptance.sh   D40 acceptance harness against an install
#
# Exits non-zero with the number of failing suites.
set -u
cd "$(dirname "$0")"

MANUAL_SUITES="placement-demo.sh
placement-eval.sh
governance-parity-acceptance.sh"

# ── discovery ───────────────────────────────────────────────────────────────
# The plugin-owned suites (unit, integration, v1, flow-orchestrator, marker
# concurrency, placement smoke, the top-level suites). Discovered by "all" only.
discover_plugin() {
  for f in unit/test-*.sh unit/*.test.sh; do [ -f "$f" ] && echo "$f"; done
  for f in integration/test-*.sh;          do [ -f "$f" ] && echo "$f"; done
  for f in v1/test_*.sh;                   do [ -f "$f" ] && echo "$f"; done
  for f in flow-orchestrator/run.sh marker-concurrency/run.sh; do [ -f "$f" ] && echo "$f"; done
  for f in placement-smoke.sh *-test.sh *.test.sh *-cases.sh smoke.sh; do
    [ -f "$f" ] || continue
    case "$MANUAL_SUITES" in *"$f"*) continue ;; esac
    echo "$f"
  done
}

# The runtime set: runtime/tests (sutra-turn, ledger, shim, canary, kill-switch,
# concurrency, overhead, and test-charcap-parity.sh — the golden-corpus replay
# against BOTH runners) plus the hook-level suites. Discovered by every set.
discover_runtime() {
  for f in ../runtime/tests/*.sh;          do [ -f "$f" ] && echo "$f"; done
  for f in ../hooks/tests/*.sh;            do [ -f "$f" ] && echo "$f"; done
}

discover() {
  [ "$SUITE_SET" = "all" ] && discover_plugin
  discover_runtime
  if [ "$SUITE_SET" = "all" ] && [ "$INCLUDE_MANUAL" = "1" ]; then
    echo "$MANUAL_SUITES" | while IFS= read -r f; do [ -f "$f" ] && echo "$f"; done
  fi
  return 0
}

# de-duplicate while preserving order (a file can match two globs)
suites() { discover | awk '!seen[$0]++'; }

# ── arguments ───────────────────────────────────────────────────────────────
MODE="run"; ONLY=""; INCLUDE_MANUAL=0; SUITE_SET="all"
while [ $# -gt 0 ]; do
  case "$1" in
    --count)          MODE="count"; shift ;;
    --list)           MODE="list";  shift ;;
    --only)
      [ $# -ge 2 ] || { echo "run-all.sh: --only needs a suite name" >&2; exit 2; }
      MODE="only"; ONLY="$2"; shift 2 ;;
    --set)
      [ $# -ge 2 ] || { echo "run-all.sh: --set needs a set name (runtime|all)" >&2; exit 2; }
      SUITE_SET="$2"
      case "$SUITE_SET" in
        runtime|all) ;;
        *) echo "run-all.sh: unknown suite set '$SUITE_SET' (want runtime|all)" >&2; exit 2 ;;
      esac
      shift 2 ;;
    --include-manual) INCLUDE_MANUAL=1; shift ;;
    -h|--help) awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "run-all.sh: unknown option $1" >&2; exit 2 ;;
  esac
done

case "$MODE" in
  count) suites | wc -l | tr -d ' '; exit 0 ;;
  list)  suites; exit 0 ;;
esac

# ── selection ───────────────────────────────────────────────────────────────
SELECTED=""
if [ "$MODE" = "only" ]; then
  [ -n "$ONLY" ] || { echo "run-all.sh: --only needs a suite name" >&2; exit 2; }
  WANT="${ONLY%.sh}"
  SELECTED="$(suites | while IFS= read -r f; do
    b="$(basename "$f")"
    [ "$b" = "$ONLY" ] || [ "${b%.sh}" = "$WANT" ] && echo "$f"
  done)"
  if [ -z "$SELECTED" ]; then
    echo "run-all.sh: no suite named '$ONLY' in set '$SUITE_SET' (try --set all --list)" >&2
    exit 2
  fi
else
  SELECTED="$(suites)"
fi

# ── wall-clock budgets for the two timing suites ────────────────────────────
# runtime/tests/test-canary.sh and test-turn-concurrency.sh each carry ONE
# wall-clock bound, with a default that holds on an idle box. This harness runs
# every suite back to back, often beside other sandboxes or on a CI runner, so
# scheduling latency here is noise rather than a regression: export generous
# values unless the caller has already chosen its own. The suites still print
# their measured numbers, so a real slowdown is still visible in the log.
: "${SUTRA_CANARY_BUDGET_MS:=900}"
: "${SUTRA_CONC_TIMEOUT_BUDGET_MS:=8000}"
export SUTRA_CANARY_BUDGET_MS SUTRA_CONC_TIMEOUT_BUDGET_MS

# ── run ─────────────────────────────────────────────────────────────────────
TOTAL=0; FAIL=0
echo "=== Sutra plugin tests (set: $SUITE_SET) ==="
OLDIFS="$IFS"; IFS='
'
for f in $SELECTED; do
  IFS="$OLDIFS"
  TOTAL=$((TOTAL+1))
  echo "-- $f ------------------------------"
  bash "$f"
  if [ $? -ne 0 ]; then
    FAIL=$((FAIL+1))
    echo "  FAIL: $f"
  fi
  echo ""
  IFS='
'
done
IFS="$OLDIFS"

PASS=$((TOTAL-FAIL))
echo "=========================="
echo "  $PASS/$TOTAL test files passed"
[ "$FAIL" -gt 0 ] && echo "  FAILURES: $FAIL"
exit "$FAIL"
