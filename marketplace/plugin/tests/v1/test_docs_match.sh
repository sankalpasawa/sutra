#!/usr/bin/env bash
# test_docs_match.sh - S7-42 (W-BUILD-V1): docs from artifacts.
# Asserts the work-atom.html "Output looks like" ledger example IS fixture
# row 1 of run-ledger-row.valid.jsonl (checked via its run_id string).
# Stdlib bash + python3 only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../../.." && pwd)"
FIX="$ROOT/sutra/os/native/schemas/fixtures/run-ledger-row.valid.jsonl"
PAGE="$ROOT/holding/website/native/platform/model/work-atom.html"

[ -f "$FIX" ] || { echo "FAIL: fixture missing: $FIX"; exit 1; }
[ -f "$PAGE" ] || { echo "FAIL: page missing: $PAGE"; exit 1; }

RUN_ID="$(python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).readline())["run_id"])' "$FIX")"

if grep -q "\"$RUN_ID\"" "$PAGE"; then
  echo "PASS: work-atom.html contains fixture row 1 run_id \"$RUN_ID\""
  exit 0
else
  echo "FAIL: run_id \"$RUN_ID\" (fixture row 1) not found in work-atom.html"
  exit 1
fi
