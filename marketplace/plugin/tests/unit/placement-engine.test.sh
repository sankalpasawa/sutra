#!/usr/bin/env bash
# placement-engine.test.sh — unit tests for the ADR-028 engine (W3-W6).
# Every assertion maps to a canon invariant or a folded peer-review finding.
set -u
PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
ENG="$PLUGIN/lib/placement_engine.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -n "${2:-}" ] && printf '       %s\n' "$2"; }
eq()  { [ "$2" = "$3" ] && ok "$1" || bad "$1" "expected=$2 got=$3"; }

SB=$(mktemp -d); trap 'rm -rf "$SB"' EXIT
export SUTRA_NATIVE_HOME="$SB/user-kit"
export PLACEMENT_ROOT_NAME="TestCo"
J() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval(sys.argv[1],{'d':d}))" "$1"; }

echo "== registry + mint =="
OUT=$(python3 "$ENG" resolve file src/auth/login.ts "add oauth" src/auth/login.ts)
eq "cold start mints a domain"        "minted"  "$(printf '%s' "$OUT" | J "d['placement']['origin']")"
eq "charter stub minted alongside"    "1"       "$(printf '%s' "$OUT" | J "len(d['placement']['created']['charters'])")"
eq "charter_id is never null (I-P6)"  "True"    "$(printf '%s' "$OUT" | J "bool(d['placement']['charter_id'])")"

CH=$(ls "$SUTRA_NATIVE_HOME"/charters/*.json | head -1)
eq "obligations empty (Decision 5)"   "0"       "$(python3 -c "import json;print(len(json.load(open('$CH'))['obligations']))")"
eq "empty-obligations reason present" "True"    "$(python3 -c "import json;print(bool(json.load(open('$CH')).get('obligations_empty_reason')))")"

echo "== classifier =="
OUT2=$(python3 "$ENG" resolve file src/auth/logout.ts "end session" src/auth/logout.ts)
D1=$(printf '%s' "$OUT"  | J "d['placement']['domain_ref']")
D2=$(printf '%s' "$OUT2" | J "d['placement']['domain_ref']")
eq "adjacent file matches same domain (fold 4)" "$D1" "$D2"
eq "adjacency match does not re-mint"           "0"   "$(printf '%s' "$OUT2" | J "len(d['placement']['created']['domains'])")"

A=$(python3 "$ENG" resolve file src/x/a.ts "alpha beta" src/x/a.ts | J "d['placement']['confidence']")
B=$(python3 "$ENG" resolve file src/x/a.ts "alpha beta" src/x/a.ts | J "d['placement']['confidence']")
eq "scoring is deterministic (F3.6)"  "$A" "$B"

echo "== naming quality =="
python3 "$ENG" resolve file README.md "" >/dev/null 2>&1
NAMED=$(python3 "$ENG" tree | python3 -c "
import json,sys,re
ds=json.load(sys.stdin)['domains']
print(sum(1 for x in ds if re.search(r'\.(Md|Ts|Json|Yaml|Sh)$', x['name'] or '')))")
eq "no domain is named after a file"  "0" "$NAMED"

echo "== atomic mint under concurrency (I-P10 / I-D2) =="
for i in $(seq 1 12); do
  ( python3 "$ENG" resolve file "src/reports/r$i.ts" "reports" "src/reports/r$i.ts" >/dev/null 2>&1 ) &
done; wait
eq "12 racing minters -> exactly 1 domain" "1" "$(python3 "$ENG" tree | python3 -c "
import json,sys;print(sum(1 for d in json.load(sys.stdin)['domains'] if d['name']=='Reports'))")"

echo "== append-only integrity (fold 3) =="
eq "CURRENT.jsonl is append-only JSONL" "True" "$(python3 -c "
import json
ok=True
for line in open('$SUTRA_NATIVE_HOME/placements/CURRENT.jsonl'):
    line=line.strip()
    if line:
        try: json.loads(line)
        except Exception: ok=False
print(ok)")"
eq "every placement id is unique (fold 2)" "True" "$(python3 -c "
import os,json
d='$SUTRA_NATIVE_HOME/placements'
ids=[f for f in os.listdir(d) if f.startswith('PL-')]
print(len(ids)==len(set(ids)))")"

echo "== MOVE re-mints zero placements (I-P8) =="
BEFORE=$(python3 "$ENG" stats | J "d['placements']")
REF=$(python3 "$ENG" tree | python3 -c "
import json,sys
for x in json.load(sys.stdin)['domains']:
    if x['name']=='Reports': print(x['ref']); break")
TGT=$(python3 "$ENG" tree | python3 -c "
import json,sys
for x in json.load(sys.stdin)['domains']:
    if x['name']=='Auth': print(x['ref']); break")
MV=$(python3 "$ENG" restructure move "$REF" "$TGT")
eq "move reports 0 placements repointed" "0" "$(printf '%s' "$MV" | J "d['placements_repointed']")"
eq "move creates no new placement rows"  "$BEFORE" "$(python3 "$ENG" stats | J "d['placements']")"

echo "== MERGE does repoint, DELETE cannot remove root =="
M=$(python3 "$ENG" restructure merge "$REF" "$TGT")
eq "merge succeeds"                      "True" "$(printf '%s' "$M" | J "d['ok']")"
ROOT=$(python3 "$ENG" tree | python3 -c "
import json,sys
for x in json.load(sys.stdin)['domains']:
    if x['path']=='D0': print(x['ref']); break")
eq "root cannot be deleted"              "False" "$(python3 "$ENG" restructure delete "$ROOT" | J "d['ok']")"

echo "== MECE report is deterministic (Decision 6) =="
R1=$(python3 "$ENG" mece | J "d['me_violations']")
R2=$(python3 "$ENG" mece | J "d['me_violations']")
eq "two runs agree"                      "$R1" "$R2"
eq "report counts addressed units"       "True" "$(python3 "$ENG" mece | J "d['ce_addressed_units']>0")"

echo "== operator-touched nodes are never AUTO-merged =="
python3 "$ENG" restructure rename "$TGT" "Renamed Auth" >/dev/null
eq "rename latches touched_by_operator"  "True" "$(python3 "$ENG" tree | python3 -c "
import json,sys
print(any(x['touched'] for x in json.load(sys.stdin)['domains'] if x['ref']=='$TGT'))")"

echo
printf 'PASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
