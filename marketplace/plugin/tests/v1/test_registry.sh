#!/usr/bin/env bash
# test_registry.sh -- W-BUILD-V1 S4-C1 fixture round-trip tests for
# sutra-schema-validate + sutra-registry.
# Inputs: workflow-definition schema + fixtures only (v1-build law).
# Instance data ONLY under ~/.sutra-native/ (throwaway subdir, cleaned on exit).
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$SELF_DIR/../../bin"
SCHEMAS="$(cd "$SELF_DIR/../../../../os/native/schemas" && pwd)"
SCHEMA="$SCHEMAS/workflow-definition.schema.json"
VALID="$SCHEMAS/fixtures/workflow-definition.valid.jsonl"
INVALID="$SCHEMAS/fixtures/workflow-definition.invalid.jsonl"
VALIDATE="$BIN/sutra-schema-validate"
REGISTRY="$BIN/sutra-registry"

export SUTRA_NATIVE_HOME="$HOME/.sutra-native/test-registry-$$"
STORE="$SUTRA_NATIVE_HOME/registry/workflows"
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

# --- 1. validator over the workflow-definition acceptance set ---------------
python3 "$VALIDATE" "$SCHEMA" "$VALID" >/dev/null; check "validator: valid fixtures exit 0" 0 $?
python3 "$VALIDATE" "$SCHEMA" "$INVALID" >/dev/null; check "validator: invalid fixtures exit 1" 1 $?

# --- 2. split valid fixtures into per-entry files ---------------------------
python3 - "$VALID" "$FIX" <<'PYEOF'
import json, os, sys
src, out = sys.argv[1], sys.argv[2]
keys = []
with open(src) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        key = "%s@%s" % (row["workflow_id"], row["version"])
        with open(os.path.join(out, key + ".json"), "w") as g:
            json.dump(row, g, indent=2)
        keys.append(key)
with open(os.path.join(out, "KEYS"), "w") as g:
    g.write("\n".join(keys) + "\n")
PYEOF
check "fixture split wrote KEYS" 0 $?

# --- 3. add: every valid fixture round-trips --------------------------------
while IFS= read -r KEY; do
  [ -n "$KEY" ] || continue
  python3 "$REGISTRY" add "$FIX/$KEY.json" >/dev/null
  check "add $KEY" 0 $?
  [ -f "$STORE/$KEY.json" ]; check_ok "store file exists for $KEY" $?
  python3 "$REGISTRY" show "$KEY" > "$FIX/$KEY.shown" 2>/dev/null
  check "show $KEY" 0 $?
  python3 - "$FIX/$KEY.json" "$FIX/$KEY.shown" <<'PYEOF'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
sys.exit(0 if a == b else 1)
PYEOF
  check_ok "round-trip JSON equality for $KEY" $?
done < "$FIX/KEYS"

# --- 4. duplicate add -> 5; invalid entry -> 1, nothing written -------------
FIRST_KEY="$(head -1 "$FIX/KEYS")"
python3 "$REGISTRY" add "$FIX/$FIRST_KEY.json" >/dev/null 2>&1
check "duplicate add rejected" 5 $?
head -1 "$INVALID" > "$FIX/bad-entry.json"
COUNT_BEFORE=$(ls "$STORE" | grep -c '\.json$')
python3 "$REGISTRY" add "$FIX/bad-entry.json" >/dev/null 2>&1
check "invalid entry rejected by add" 1 $?
COUNT_AFTER=$(ls "$STORE" | grep -c '\.json$')
[ "$COUNT_BEFORE" -eq "$COUNT_AFTER" ]; check_ok "nothing written on validation failure" $?

# --- 5. index + list --------------------------------------------------------
[ -f "$STORE/index.json" ]; check_ok "index.json exists" $?
python3 - "$STORE/index.json" <<'PYEOF'
import json, sys
ix = json.load(open(sys.argv[1]))
sys.exit(0 if ix.get("index_complete") is True and "workflows" in ix else 1)
PYEOF
check_ok "index completeness marker present" $?
python3 "$REGISTRY" list | grep -q "W-kyc-verify"; check_ok "list shows W-kyc-verify" $?
python3 "$REGISTRY" list --status registered >/dev/null; check "list --status registered" 0 $?
python3 "$REGISTRY" list --status bogus >/dev/null 2>&1; check "list --status bogus is usage error" 2 $?

# --- 6. show without version picks highest registered -----------------------
python3 "$REGISTRY" show W-kyc-verify > "$FIX/latest.shown" 2>/dev/null
check "show W-kyc-verify (no version)" 0 $?
python3 - "$FIX/latest.shown" <<'PYEOF'
import json, sys
row = json.load(open(sys.argv[1]))
sys.exit(0 if row["status"] == "registered" else 1)
PYEOF
check_ok "versionless show returns a registered entry" $?

# --- 7. supersede + retire transitions --------------------------------------
# successor derived from fixture row 1: version bumped, still schema-valid
python3 - "$FIX/$FIRST_KEY.json" "$FIX/successor.json" <<'PYEOF'
import json, sys
row = json.load(open(sys.argv[1]))
row["version"] = "9.9.9"
json.dump(row, open(sys.argv[2], "w"), indent=2)
PYEOF
SUCC_WID="$(python3 -c "import json,sys;print(json.load(open('$FIX/successor.json'))['workflow_id'])")"
TARGET="$FIRST_KEY"
SUCCESSOR="$SUCC_WID@9.9.9"

python3 "$REGISTRY" supersede "$TARGET" --by "$SUCCESSOR" >/dev/null 2>&1
check "supersede with absent successor rejected" 5 $?
python3 "$REGISTRY" add "$FIX/successor.json" >/dev/null; check "add successor $SUCCESSOR" 0 $?
python3 "$REGISTRY" supersede "$TARGET" --by "$SUCCESSOR" >/dev/null
check "supersede $TARGET by $SUCCESSOR" 0 $?
python3 "$REGISTRY" show "$TARGET" | python3 -c "import json,sys;sys.exit(0 if json.load(sys.stdin)['status']=='superseded' else 1)"
check_ok "target now superseded" $?
python3 - "$STORE/index.json" "$TARGET" "$SUCCESSOR" <<'PYEOF'
import json, sys
ix = json.load(open(sys.argv[1]))
sys.exit(0 if ix.get("successions", {}).get(sys.argv[2]) == sys.argv[3] else 1)
PYEOF
check_ok "succession recorded in index" $?
python3 "$REGISTRY" supersede "$TARGET" --by "$SUCCESSOR" >/dev/null 2>&1
check "supersede non-registered target rejected" 5 $?
python3 "$REGISTRY" supersede "W-ghost@0.0.1" --by "$SUCCESSOR" >/dev/null 2>&1
check "supersede missing target is not-found" 4 $?
python3 "$REGISTRY" retire "$TARGET" >/dev/null
check "retire superseded entry" 0 $?
python3 "$REGISTRY" retire "$TARGET" >/dev/null 2>&1
check "retire retired entry rejected" 5 $?
python3 "$REGISTRY" retire "W-ghost@0.0.1" >/dev/null 2>&1
check "retire missing target is not-found" 4 $?

# --- 8. leak guard: no instance writes inside the repo ----------------------
SUTRA_NATIVE_HOME="$SELF_DIR" python3 "$REGISTRY" list >/dev/null 2>&1
check "store root inside sutra package refused" 3 $?

echo "----------------------------------------"
echo "test_registry.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
