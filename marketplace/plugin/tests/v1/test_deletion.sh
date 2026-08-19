#!/usr/bin/env bash
# test_deletion.sh -- W-BUILD-V1 S6-38: the deletion test.
# FORBIDDEN-DEPS.md (F1-F10) IS the deletion-set definition. This test:
#   1. Builds a SANDBOXED COPY (mktemp) of the v1 surface: the 8 bin CLIs
#      + verify templates + schemas, mirroring the repo-relative shape so
#      every relative import resolves INSIDE the copy.
#   2. Deletes from the copy every file whose name matches a forbidden
#      module family (engine/contract/shelf/style/horizontal/scheduler).
#      In v1 there is NOTHING to delete -- asserted (deleted count == 0).
#   3. In a clean HOME, PATH restricted to the copy, runs the FULL loop:
#      propose -> approve -> register -> resolve FOLLOW -> run-log
#      open/close (sutra-atom, the M3 runner) -> verify FAIL then RECOVER
#      (grep-count on a file that gains the pattern between attempts).
#   4. Pass = loop completes with later-version code both ABSENT (name
#      sweep still zero, copy inventory byte-identical) and UNREFERENCED
#      (no absolute repo paths / 4-up escapes / non-stdlib imports /
#      forbidden-module imports in the copy's CLIs).
# Instance data ONLY under the sandbox (mktemp HOME + project). stdlib
# python3 + bash only in this harness; jq/perl are runtime deps of the
# shipped sutra-atom CLI, not of this test.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_PLUGIN="$(cd "$SELF_DIR/../.." && pwd)"                 # marketplace/plugin
SRC_SCHEMAS="$(cd "$SRC_PLUGIN/../../os/native/schemas" && pwd)"

SANDBOX="$(mktemp -d /tmp/sutra-deletion-test.XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT
COPY="$SANDBOX/copy"
CPLUGIN="$COPY/marketplace/plugin"
CBIN="$CPLUGIN/bin"
SBHOME="$SANDBOX/home"
PROJ="$SANDBOX/project"
mkdir -p "$CBIN" "$CPLUGIN/templates" "$CPLUGIN/hooks/lib" "$COPY/os/native" \
         "$SBHOME" "$PROJ"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check_rc() { # <label> <want_rc> <got_rc>
  if [ "$3" -eq "$2" ]; then ok "$1 (rc=$3)"; else bad "$1 (want rc=$2 got rc=$3)"; fi
}

# ---- 1. build the sandboxed copy of the v1 surface ------------------------
CLIS="sutra-atom sutra-build-workflow sutra-outbox sutra-registry \
sutra-resolve sutra-route-log sutra-schema-validate sutra-verify"
for c in $CLIS; do cp -p "$SRC_PLUGIN/bin/$c" "$CBIN/$c" || bad "copy $c"; done
cp -pR "$SRC_PLUGIN/bin/verify-templates" "$CBIN/verify-templates"
cp -p  "$SRC_PLUGIN/templates/verify-templates.json" "$CPLUGIN/templates/"
cp -p  "$SRC_PLUGIN/hooks/lib/sutra-paths.sh" "$CPLUGIN/hooks/lib/"
cp -pR "$SRC_SCHEMAS" "$COPY/os/native/schemas"
n_clis=0; for c in $CLIS; do [ -x "$CBIN/$c" ] && n_clis=$((n_clis+1)); done
[ "$n_clis" -eq 8 ] && ok "copy built: 8/8 CLIs executable in sandbox" \
                    || bad "copy built: only $n_clis/8 CLIs present"

# ---- 2. deletion sweep: FORBIDDEN-DEPS.md F1-F10 as code ------------------
# F1 engine slices | F2 typed contracts | F3 shelves | F4 style routing
# F5 horizontals   | F7 scheduler semantics (F6/F8/F9/F10 are behaviors,
# proven absent by the loop below, not separate modules).
FORBIDDEN_RE='(engine|contract|shel[fv]|style|horizontal|schedul)'
matches="$(find "$COPY" -type f | grep -Ei "/[^/]*${FORBIDDEN_RE}[^/]*$" || true)"
deleted=0
if [ -n "$matches" ]; then
  while IFS= read -r f; do rm -f "$f"; deleted=$((deleted+1)); echo "  deleted: $f"; done <<EOF
$matches
EOF
fi
[ "$deleted" -eq 0 ] && ok "deletion sweep: 0 forbidden-module files found (v1 clean by construction)" \
                     || bad "deletion sweep: $deleted forbidden-module files existed in the v1 surface"

find "$COPY" -type f | sort > "$SANDBOX/inventory.pre"

# ---- 3. the full loop, clean HOME, PATH restricted to the copy ------------
JQDIR="$(dirname "$(command -v jq 2>/dev/null || echo /opt/homebrew/bin/jq)")"
SBPATH="$CBIN:/usr/bin:/bin:$JQDIR"
run_sb() { ( cd "$PROJ" && env -i HOME="$SBHOME" PATH="$SBPATH" \
    SUTRA_NATIVE_HOME="$SBHOME/.sutra-native" \
    CLAUDE_PLUGIN_ROOT="$CPLUGIN" CLAUDE_PROJECT_DIR="$PROJ" \
    CLAUDE_CODE_SESSION_ID=deltest "$@" ); }

# fixtures (lending example per standing direction)
printf 'Loan disbursal memo. Borrower: A. Amount: 5L. Clause 1: sanction terms.\n' > "$PROJ/memo.md"
cat > "$SANDBOX/transcript.json" <<EOF
{
  "recorded": "improvised disbursal run 2026-08-19",
  "steps": [
    {"name": "draft-disbursal-memo",
     "how": "Write the loan disbursal memo with borrower, amount, tenure",
     "verify": {"template_id": "file-exists", "template_version": "1",
                "args": [{"name": "path", "value": "$PROJ/memo.md"}]}},
    {"name": "check-sanction-clauses",
     "how": "Confirm the memo carries all mandatory sanction clauses",
     "verify": {"template_id": "grep-count", "template_version": "1",
                "args": [{"name": "pattern", "value": "Clause"},
                         {"name": "file", "value": "$PROJ/memo.md"},
                         {"name": "min", "value": 3}]}}
  ],
  "failure_policy": {"retry_budget": 2, "on_escalate": "credit-ops"},
  "reuse_tag": "lending-disbursal"
}
EOF

# propose
run_sb "$CBIN/sutra-build-workflow" propose \
  --from-transcript "$SANDBOX/transcript.json" \
  --id W-disburse-loan --title "Loan disbursal" \
  --goal "Disburse a sanctioned loan with a verified memo" \
  --version 0.1.0 --proposed-by tester >/dev/null 2>&1
check_rc "loop/propose" 0 $?

# approve (operator action, --i-approve literal -- F8)
run_sb "$CBIN/sutra-build-workflow" approve --id W-disburse-loan@0.1.0 \
  --operator tester --i-approve >/dev/null 2>&1
check_rc "loop/approve" 0 $?

# register: entry landed in the clean HOME's registry + schema-valid
ENTRY="$SBHOME/.sutra-native/registry/workflows/W-disburse-loan@0.1.0.json"
if [ -f "$ENTRY" ] && grep -q '"status": *"registered"' "$ENTRY"; then
  ok "loop/register: entry present with status=registered"
else bad "loop/register: entry missing or not registered"; fi
run_sb "$CBIN/sutra-schema-validate" \
  "$COPY/os/native/schemas/workflow-definition.schema.json" "$ENTRY" >/dev/null 2>&1
check_rc "loop/register schema-valid (copy's schema)" 0 $?

# resolve -> FOLLOW
RES="$(run_sb "$CBIN/sutra-resolve" --ask "disburse the sanctioned loan" \
  --reuse-tag lending-disbursal 2>/dev/null)"
MODE="$(printf '%s' "$RES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("mode"),d.get("workflow_id"))' 2>/dev/null)"
[ "$MODE" = "FOLLOW W-disburse-loan" ] && ok "loop/resolve: FOLLOW W-disburse-loan" \
  || bad "loop/resolve: got '$MODE' (raw: $RES)"

# run-log open (sutra-atom, the M3 runner; ledger under the sandbox project)
run_sb "$CBIN/sutra-atom" open \
  --goal "Disbursal memo carries all three mandatory sanction clauses" \
  --work bash --ref W-disburse-loan@0.1.0 --touches memo.md \
  --verify-template grep-count \
  --verify-arg Clause --verify-arg memo.md --verify-arg 3 >/dev/null 2>&1
check_rc "loop/run-log open" 0 $?
ATOM_JSON="$(find "$PROJ/.sutra/atoms/deltest" -name atom.json 2>/dev/null | head -1)"
ATOM_ID="$(basename "$(dirname "${ATOM_JSON:-/nonexistent}")" 2>/dev/null)"
[ -f "${ATOM_JSON:-/nonexistent}" ] && ok "loop/run-log row open (atom $ATOM_ID)" \
  || bad "loop/run-log: no atom.json written"

# verify FAIL: memo has 1 Clause < 3
run_sb "$CBIN/sutra-atom" close "$ATOM_ID" >/dev/null 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "loop/verify attempt 1 FAILS as declared (rc=$rc, 1 Clause < 3)" \
  || bad "loop/verify attempt 1 should fail but passed"

# RECOVER: the file gains the pattern between attempts
printf 'Clause 2: repayment schedule terms.\nClause 3: default and recovery terms.\n' >> "$PROJ/memo.md"
run_sb "$CBIN/sutra-atom" close "$ATOM_ID" >/dev/null 2>&1
check_rc "loop/verify attempt 2 recovers (memo gained 2 Clause lines)" 0 $?
ATT="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("attempt"), d.get("status"))' "$ATOM_JSON" 2>/dev/null)"
[ "$ATT" = "2 closed" ] && ok "loop/run-log close: attempt=2 status=closed" \
  || bad "loop/run-log close: got '$ATT' (want '2 closed')"
LEDGER="$PROJ/.sutra/atom-ledger.jsonl"
[ -s "$LEDGER" ] && grep -q "$ATOM_ID" "$LEDGER" \
  && ok "loop/run-log ledger row appended for $ATOM_ID" \
  || bad "loop/run-log ledger row missing"

# ---- 4. absent + unreferenced -------------------------------------------
# absent: sweep still zero AND the copy is byte-inventory-identical (the
# loop wrote instance data only to the sandbox HOME/project -- S0 section 3)
post_matches="$(find "$COPY" -type f | grep -Eic "/[^/]*${FORBIDDEN_RE}[^/]*$" || true)"
[ "${post_matches:-0}" -eq 0 ] && ok "absent: forbidden-module sweep still 0 after loop" \
  || bad "absent: $post_matches forbidden-module files appeared"
find "$COPY" -type f | sort > "$SANDBOX/inventory.post"
if diff -q "$SANDBOX/inventory.pre" "$SANDBOX/inventory.post" >/dev/null; then
  ok "absent: copy inventory unchanged (no instance writes into the copy)"
else bad "absent: copy inventory changed during the loop"; fi

# unreferenced (a): no absolute repo paths / no 4-up relative escapes in
# CODE lines (comment lines cannot import; sutra-atom's L1 build-layer
# header is governance metadata, not a reference)
LEAKS="$(cd "$CBIN" && grep -EnH '/Users/asawa|asawa-holding|\.\./\.\./\.\./\.\.' $CLIS \
  | grep -Ev '^[^:]+:[0-9]+:[[:space:]]*#' || true)"
[ -z "$LEAKS" ] && ok "unreferenced: no absolute-repo paths or 4-up escapes in the 8 CLIs" \
  || { bad "unreferenced: path leaks found"; printf '%s\n' "$LEAKS" | sed 's/^/    /'; }

# unreferenced (b): no import/source line names a forbidden module family
IMP_LEAKS="$(cd "$CBIN" && grep -EinH "^[[:space:]]*(import|from|source|\.)[[:space:]].*${FORBIDDEN_RE}" $CLIS || true)"
[ -z "$IMP_LEAKS" ] && ok "unreferenced: no import/source of engine/contract/shelf/style/horizontal/scheduler" \
  || { bad "unreferenced: forbidden imports"; printf '%s\n' "$IMP_LEAKS" | sed 's/^/    /'; }

# unreferenced (c): every python import in the copy's CLIs is stdlib.
# rc-checked so an audit crash is a FAIL, never a silent pass.
PY_AUDIT="$(python3 - "$CBIN" 2>&1 <<'PYEOF'
import ast, importlib.util, pathlib, sys, sysconfig
std = getattr(sys, "stdlib_module_names", None)   # py>=3.10
stdlib_dir = sysconfig.get_paths()["stdlib"]
def is_std(m):
    if std is not None:
        return m in std
    if m in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(m)
    except Exception:
        return False
    o = (spec.origin or "") if spec else ""
    return o in ("built-in", "frozen") or o.startswith(stdlib_dir)
bad = []
for p in sorted(pathlib.Path(sys.argv[1]).iterdir()):
    if not p.is_file(): continue
    first = p.read_bytes().split(b"\n", 1)[0]
    if b"python3" not in first: continue
    tree = ast.parse(p.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += ["%s: import %s" % (p.name, a.name) for a in n.names
                    if not is_std(a.name.split(".")[0])]
        elif isinstance(n, ast.ImportFrom):
            if n.level > 0: bad.append("%s: relative import" % p.name)
            elif not is_std((n.module or "").split(".")[0]):
                bad.append("%s: from %s" % (p.name, n.module))
print("\n".join(bad))
sys.exit(1 if bad else 0)
PYEOF
)"; py_rc=$?
if [ "$py_rc" -eq 0 ]; then ok "unreferenced: all python imports in copy CLIs are stdlib"
else bad "unreferenced: non-stdlib imports or audit crash (rc=$py_rc)"
     printf '%s\n' "$PY_AUDIT" | sed 's/^/    /'; fi

echo "----------------------------------------------------------"
echo "test_deletion: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
