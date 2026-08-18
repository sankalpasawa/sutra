#!/usr/bin/env bash
# test_outbox.sh — W-BUILD-V1 S4-C5 acceptance for sutra-outbox.
# Proves: (T1) add appends schema-valid pending rows; (T2) atomic temp+rename
# leaves NO partial rows when writers are kill -9'd mid-add; (T3) double
# replay is an exit-0 no-op that appends nothing; (T4) replay-all clears
# pendings + exit codes match spec (4 = not found, 2 = usage).
# Instance data only under ~/.sutra-native/ (isolated per-run subdir via
# SUTRA_NATIVE_HOME, removed on exit). Never touches the repo.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/../../bin/sutra-outbox"
export SUTRA_NATIVE_HOME="$HOME/.sutra-native/.test-outbox-$$"
STORE="$SUTRA_NATIVE_HOME/outbox/outbox.jsonl"
trap 'rm -rf "$SUTRA_NATIVE_HOME"' EXIT

PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "PASS: $1"; }
no() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

lines() { if [ -f "$STORE" ]; then wc -l < "$STORE" | tr -d ' '; else echo 0; fi; }

# Integrity: every line parses as JSON and carries exactly the 8 required
# keys of outbox-row.schema.json with a legal state. A torn/partial row fails.
check_integrity() {
python3 - "$STORE" <<'PY'
import json, sys
REQ = {"schema_version","outbox_id","ts_queued","ask_text","operator_id","state","ts_resolved","replay_ref"}
bad = 0
with open(sys.argv[1], encoding="utf-8") as f:
    for n, line in enumerate(f, 1):
        line = line.rstrip("\n")
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            print("INTEGRITY: partial/torn row at line %d: %r" % (n, line[:60])); bad += 1; continue
        if set(row) != REQ:
            print("INTEGRITY: line %d key mismatch: %s" % (n, sorted(set(row) ^ REQ))); bad += 1; continue
        if row["state"] not in ("pending", "replayed", "failed"):
            print("INTEGRITY: line %d bad state %r" % (n, row["state"])); bad += 1
sys.exit(1 if bad else 0)
PY
}

replay_ref_of() {
"$BIN" list --state replayed | python3 -c '
import json, sys
oid = sys.argv[1]
for line in sys.stdin:
    r = json.loads(line)
    if r["outbox_id"] == oid and r["ts_resolved"]:
        print(r["replay_ref"]); break
' "$1"
}

echo "== T1: add 2 =="
ID1=$("$BIN" add "APPROVE run of W-emi-reconcile for batch 2026-08-18" --operator sankalpasawa) || no "add #1 nonzero exit"
ID2=$("$BIN" add "APPROVE registration of W-kyc-verify v1" --operator sankalpasawa) || no "add #2 nonzero exit"
if [ -n "${ID1:-}" ] && [ -n "${ID2:-}" ] && [ "$ID1" != "$ID2" ]; then ok "add mints two distinct outbox_ids"; else no "outbox_ids missing or equal"; fi
if [ "$(lines)" = "2" ]; then ok "store holds 2 rows"; else no "store holds $(lines) rows, want 2"; fi
if [ "$("$BIN" list --state pending | wc -l | tr -d ' ')" = "2" ]; then ok "list --state pending shows 2"; else no "pending list wrong"; fi
if check_integrity; then ok "both rows schema-valid (8 keys, legal state)"; else no "schema validity"; fi

echo "== T2: kill -9 mid-add — atomicity (temp+rename => no partial rows) =="
BASE=$(lines)
( for i in $(seq 1 200); do "$BIN" add "kill-nine loop row $i" --operator t >/dev/null 2>&1; done ) &
LOOP=$!
i=0
while [ "$(lines)" -lt $((BASE + 3)) ] && [ "$i" -lt 500 ]; do i=$((i+1)); sleep 0.01; done
kill -9 "$LOOP" 2>/dev/null || true
wait "$LOOP" 2>/dev/null || true
# Direct SIGKILL of in-flight writer processes (interrupts the add itself,
# possibly between temp-write and rename — rename-or-nothing must hold).
KP=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  "$BIN" add "sigkill probe $i" --operator t >/dev/null 2>&1 &
  KP="$KP $!"
done
kill -9 $KP 2>/dev/null || true
wait 2>/dev/null || true
sleep 0.3
AFTER=$(lines)
if [ "$AFTER" -gt "$BASE" ]; then ok "writers made progress before kill ($BASE -> $AFTER rows)"; else no "no rows landed before kill"; fi
if check_integrity; then ok "no partial rows after kill -9 — every line complete + schema-valid"; else no "partial/invalid rows found after kill -9"; fi

echo "== T3: double-replay no-op =="
"$BIN" replay "$ID1" >/dev/null; RC=$?
if [ "$RC" -eq 0 ]; then ok "first replay exits 0"; else no "first replay exit $RC"; fi
REF1=$(replay_ref_of "$ID1")
if [ -n "$REF1" ]; then ok "replayed row carries ts_resolved + replay_ref ($REF1)"; else no "replay_ref/ts_resolved missing"; fi
N1=$(lines)
OUT2=$("$BIN" replay "$ID1"); RC2=$?
N2=$(lines)
if [ "$RC2" -eq 0 ] && [ "$N2" = "$N1" ]; then ok "second replay: exit 0 and no row appended (idempotent no-op)"; else no "second replay rc=$RC2 rows $N1 -> $N2"; fi
if printf '%s' "$OUT2" | grep -q "no-op"; then ok "second replay reports no-op"; else no "no-op message absent: $OUT2"; fi
REF2=$(replay_ref_of "$ID1")
if [ "$REF1" = "$REF2" ]; then ok "replay_ref unchanged by double replay"; else no "replay_ref changed: $REF1 -> $REF2"; fi

echo "== T4: replay-all + exit codes =="
if "$BIN" replay-all >/dev/null; then ok "replay-all exits 0"; else no "replay-all nonzero"; fi
if [ "$("$BIN" list --state pending | wc -l | tr -d ' ')" = "0" ]; then ok "no pendings after replay-all"; else no "pendings remain"; fi
"$BIN" replay does-not-exist >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 4 ]; then ok "replay of unknown outbox_id exits 4"; else no "unknown-id replay exit $RC, want 4"; fi
"$BIN" bogus >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 2 ]; then ok "usage error exits 2"; else no "usage error exit $RC, want 2"; fi
if check_integrity; then ok "final store integrity holds"; else no "final integrity"; fi

echo
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
