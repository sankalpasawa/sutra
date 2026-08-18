#!/usr/bin/env bash
# Balance actionable endpoint contract (PLAN-25 step 12; consult-folded).
# Spins the real FastAPI app on a random port with a temp balance dir and a
# known desktop token, then asserts the full auth/validation/idempotency
# contract including CLI-mode (no env token) and concurrent duplicates.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
UI="$(cd "$HERE/../../sutra-ui" && pwd)"
TMP="$(mktemp -d)"
PORT=$((20000 + RANDOM % 20000))
TOKEN="test-token-$RANDOM"
FAIL=0
die(){ echo "FAIL: $1"; FAIL=1; }

cat > "$TMP/balance-state.json" <<'EOF'
{"schema_version":2,"generated_at":"2026-08-18T00:00:00Z","epoch":0,"cards":[],"signals":{}}
EOF
cat > "$TMP/coach-ledger.jsonl" <<'EOF'
{"ts":1,"event":"born","id":"act-test-one","role":"Test","text":"test actionable","predicate":null}
{"ts":2,"event":"born","id":"act-test-two","role":"Test","text":"second","predicate":null}
{"ts":3,"event":"done","id":"act-test-two","by":"founder"}
EOF
cat > "$TMP/actionables.json" <<'EOF'
{"generated_at":"2026-08-18T00:00:00Z","max_active":3,"profile_warnings":[],
 "actionables":[{"id":"act-test-one","status":"open","active":true,"text":"test actionable","days_open":0}]}
EOF

# Same resolution as run.sh: local venv if present, else any venv beside a
# sibling checkout, else system python3 (skip cleanly if uvicorn is missing).
PY="python3"
for CAND in "$UI/.venv/bin/python" "$UI/../../../sutra/marketplace/plugin/sutra-ui/.venv/bin/python" \
            "$UI/../../../../sutra/marketplace/plugin/sutra-ui/.venv/bin/python" \
            "$UI/../../../../../sutra/marketplace/plugin/sutra-ui/.venv/bin/python"; do
  [ -x "$CAND" ] && PY="$CAND" && break
done
"$PY" -c "import uvicorn, fastapi" 2>/dev/null || { echo "SKIP: no python with uvicorn+fastapi"; exit 0; }

start_server(){ # $1 = token value ("" = unset, CLI mode)
  local tok="$1"
  ( cd "$UI" && \
    /usr/bin/env SUTRA_UI_BALANCE_DIR="$TMP" ${tok:+SUTRA_DESKTOP_TOKEN="$tok"} \
    "$PY" -m uvicorn app:app --host 127.0.0.1 --port "$PORT" --log-level error ) &
  SRV=$!
  for i in $(seq 1 40); do curl -sf -m 1 "http://127.0.0.1:$PORT/api/balance" >/dev/null 2>&1 && return 0; sleep 0.5; done
  die "server did not come up"; return 1
}
stop_server(){ kill "$SRV" 2>/dev/null; pkill -f "uvicorn app:app --host 127.0.0.1 --port $PORT" 2>/dev/null; wait "$SRV" 2>/dev/null; sleep 1; }
trap 'stop_server; rm -rf "$TMP"' EXIT

start_server "$TOKEN" || exit 1
B="http://127.0.0.1:$PORT"
echo "checkpoint: server1 up"

# 1) read model carries actionables
curl -s -m 8 "$B/api/balance" | grep -q '"act-test-one"' || die "read model missing actionables"

# 2) no token -> 403 ; wrong token -> 403
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" \
   -H 'content-type: application/json' -d '{"id":"act-test-one","op":"done"}')" = 403 ] || die "missing token not 403"
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" \
   -H 'content-type: application/json' -H "x-sutra-desktop-token: wrong" \
   -d '{"id":"act-test-one","op":"done"}')" = 403 ] || die "wrong token not 403"

# 3) schema: bad op 422; bad id 422; long note 422
H=(-H 'content-type: application/json' -H "x-sutra-desktop-token: $TOKEN")
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-one","op":"moevment"}')" = 422 ] || die "bad op not 422"
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"../etc","op":"done"}')" = 422 ] || die "bad id not 422"
LONG=$(python3 -c "print('x'*201)")
LCODE=$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d "{\"id\":\"act-test-one\",\"op\":\"movement\",\"note\":\"$LONG\"}")
[ "$LCODE" = 422 ] || die "long note not 422 (got $LCODE, len ${#LONG})"

# 4) unknown id 404
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-nope","op":"done"}')" = 404 ] || die "unknown id not 404"

echo "checkpoint: schema tests done"
# 5) good done -> exactly +1 row; duplicate -> already:true, +0 rows
N0=$(wc -l < "$TMP/coach-ledger.jsonl")
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-one","op":"done"}' | grep -q '"already":false' || die "first done not ok"
N1=$(wc -l < "$TMP/coach-ledger.jsonl")
[ "$((N1-N0))" -eq 1 ] || die "first done appended $((N1-N0)) rows"
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-one","op":"done"}' | grep -q '"already":true' || die "duplicate done not already:true"
[ "$(wc -l < "$TMP/coach-ledger.jsonl")" -eq "$N1" ] || die "duplicate appended rows"

# 6) already-closed id from seed -> already:true
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-two","op":"done"}' | grep -q '"already":true' || die "seed-closed not already:true"

# 7) concurrent duplicates on a fresh id: exactly +1 done row total
printf '%s\n' '{"ts":4,"event":"born","id":"act-test-three","role":"Test","text":"c","predicate":null}' >> "$TMP/coach-ledger.jsonl"
N2=$(wc -l < "$TMP/coach-ledger.jsonl")
CPIDS=()
for i in 1 2 3 4; do
  curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-three","op":"done"}' >/dev/null &
  CPIDS+=($!)
done
wait "${CPIDS[@]}"   # NEVER bare wait: that also waits on the server subshell
DONE3=$(grep -c '"event": "done", "id": "act-test-three"' "$TMP/coach-ledger.jsonl")
[ "$DONE3" -eq 1 ] || die "concurrent duplicates appended $DONE3 done rows (expected 1)"

# 7b) DROP contract (consult fold: drop needs explicit coverage, not "same as done")
printf '%s\n' '{"ts":5,"event":"born","id":"act-test-drop","role":"Test","text":"d","predicate":null}' >> "$TMP/coach-ledger.jsonl"
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-drop","op":"drop"}')" = 422 ] || die "drop without reason not 422"
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-drop","op":"drop","reason":"because-i-said"}')" = 422 ] || die "drop with bad reason not 422"
ND0=$(grep -c '"event": "dropped", "id": "act-test-drop"' "$TMP/coach-ledger.jsonl" || true)
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-drop","op":"drop","reason":"doesnt-matter"}' | grep -q '"already":false' || die "valid drop not ok"
ND1=$(grep -c '"event": "dropped", "id": "act-test-drop"' "$TMP/coach-ledger.jsonl" || true)
[ "$((ND1-ND0))" -eq 1 ] || die "drop appended $((ND1-ND0)) rows, expected 1"
grep -q '"reason": "doesnt-matter"' "$TMP/coach-ledger.jsonl" || die "drop reason not recorded in ledger"
# duplicate drop -> zero rows, closed_as reported
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-drop","op":"drop","reason":"not-now"}' | grep -q '"closed_as":"dropped"' || die "duplicate drop missing closed_as"
[ "$(grep -c '"event": "dropped", "id": "act-test-drop"' "$TMP/coach-ledger.jsonl")" -eq "$ND1" ] || die "duplicate drop appended a row"
# done-after-drop -> already, closed_as=dropped, no append
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-drop","op":"done"}' | grep -q '"closed_as":"dropped"' || die "done-after-drop missing closed_as=dropped"
# drop-after-done -> already, closed_as=done
curl -s -m 8 -X POST "$B/api/balance/actionable" "${H[@]}" -d '{"id":"act-test-one","op":"drop","reason":"doesnt-matter"}' | grep -q '"closed_as":"done"' || die "drop-after-done missing closed_as=done"
echo "checkpoint: drop contract done"

echo "checkpoint: concurrency done"
# 8) CLI mode (env token unset): POST is ALWAYS 403
stop_server
start_server "" || exit 1
[ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' -X POST "$B/api/balance/actionable" \
   -H 'content-type: application/json' -d '{"id":"act-test-one","op":"done"}')" = 403 ] || die "CLI mode POST not 403"
curl -s -m 8 "$B/api/balance" | grep -q '"act-test-one"' || die "CLI mode read model broken"

[ "$FAIL" -eq 0 ] && echo "balance-endpoint: ALL GREEN" || echo "balance-endpoint: FAILURES"
exit "$FAIL"
