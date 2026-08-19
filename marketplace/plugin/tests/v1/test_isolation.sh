#!/usr/bin/env bash
# test_isolation.sh -- W-BUILD-V1 S5-35 instance-store isolation check.
# Proves: (a) a representative command from each of the 8 v1 CLIs, run under a
# throwaway sandbox HOME, writes ONLY under that sandbox (SUTRA_NATIVE_HOME /
# $HOME/.sutra-native / atom ROOT); (b) git status --porcelain at the repo
# root (outer repo + sutra submodule) gains no new/modified entries from the
# runs -- compared before/after, because a live worktree is already dirty;
# lines under .claude/ are excluded (session-runtime state churned by
# concurrent sessions, whitelisted store, not reachable by any v1 CLI);
# (c) the sutra-registry in-package-store refusal still exits 3.
# STDLIB python3/bash only. Instance data only under the sandbox HOME.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$(cd "$SELF_DIR/../../bin" && pwd)"
SCHEMAS="$(cd "$SELF_DIR/../../../../os/native/schemas" && pwd)"
REPO="$(cd "$SELF_DIR/../../../../.." && pwd)"          # asawa-holding root
SUB="$REPO/sutra"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/sutra-iso.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
NH="$SANDBOX/.sutra-native"
mkdir -p "$SANDBOX/tmp"

PASS=0; FAIL=0
ok()    { PASS=$((PASS+1)); echo "PASS: $1"; }
no()    { FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check() { if [ "$2" -eq "$3" ]; then ok "$1 (rc=$3)"; else no "$1 (want rc=$2 got rc=$3)"; fi; }

# Scrubbed environment: nothing leaks in but PATH; HOME + SUTRA_NATIVE_HOME +
# TMPDIR all point inside the sandbox.
RUN() { env -i HOME="$SANDBOX" PATH="$PATH" TMPDIR="$SANDBOX/tmp" \
        SUTRA_NATIVE_HOME="$NH" "$@"; }

snap() { { git -C "$REPO" status --porcelain; echo "--sub--"; \
           git -C "$SUB" status --porcelain; } | grep -vE '^.. \.claude/'; }

BEFORE="$(snap)"

# --- fixtures the commands need, all inside the sandbox ---------------------
python3 -c '
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
json.dump(rows[0], open(sys.argv[2], "w"), indent=2)
' "$SCHEMAS/fixtures/workflow-definition.valid.jsonl" "$SANDBOX/entry.json"
printf 'probe\n' > "$SANDBOX/probe.txt"
cat > "$SANDBOX/transcript.json" <<'EOF'
{
  "recorded": "improvised disbursal run (isolation probe)",
  "steps": [
    {"name": "draft-disbursal-memo",
     "how": "Write the loan disbursal memo with borrower, amount, tenure",
     "verify": {"template_id": "file-exists", "template_version": "1",
                "args": [{"name": "path", "value": "/tmp/memo.md"}]}}
  ],
  "failure_policy": {"retry_budget": 2, "on_escalate": "credit-ops"},
  "reuse_tag": "lending-disbursal-iso"
}
EOF

# --- one representative command per CLI (8 CLIs) ----------------------------
echo "== 1/8 sutra-schema-validate (read-only) =="
RUN python3 "$BIN/sutra-schema-validate" \
  "$SCHEMAS/workflow-definition.schema.json" \
  "$SCHEMAS/fixtures/workflow-definition.valid.jsonl" >/dev/null 2>&1
check "sutra-schema-validate valid fixtures" 0 $?

echo "== 2/8 sutra-registry add =="
RUN python3 "$BIN/sutra-registry" add "$SANDBOX/entry.json" >/dev/null 2>&1
check "sutra-registry add" 0 $?
[ -n "$(find "$NH/registry/workflows" -name '*.json' 2>/dev/null)" ] \
  && ok "registry entry landed under sandbox" || no "registry entry not in sandbox"

echo "== 3/8 sutra-resolve (read-only) =="
RUN python3 "$BIN/sutra-resolve" --ask "verify kyc for the borrower batch" >/dev/null 2>&1
check "sutra-resolve --ask" 0 $?

echo "== 4/8 sutra-verify (stdout-only) =="
RUN python3 "$BIN/sutra-verify" --template file-exists --version 1 \
  --arg "path=$SANDBOX/probe.txt" >/dev/null 2>&1
check "sutra-verify file-exists" 0 $?

echo "== 5/8 sutra-build-workflow propose =="
RUN python3 "$BIN/sutra-build-workflow" propose \
  --from-transcript "$SANDBOX/transcript.json" \
  --id W-disburse-loan-iso --title "Loan disbursal (iso probe)" \
  --goal "Disburse a sanctioned loan with a verified memo" \
  --version 0.1.0 --proposed-by iso-test >/dev/null 2>&1
check "sutra-build-workflow propose" 0 $?
[ -f "$NH/registry/proposals/W-disburse-loan-iso@0.1.0.json" ] \
  && ok "proposal landed under sandbox" || no "proposal not in sandbox"

echo "== 6/8 sutra-route-log append =="
RUN python3 "$BIN/sutra-route-log" --turn-id iso-t1 --operator iso-test \
  --intent-type task --confidence 0.92 \
  --confidence-source placement_engine:v1.9.1 \
  --charter-ref 'sutra/os/charters/WORK-DISPATCH.md#authority' \
  --work-ref W-kyc-verify --channel in-band >/dev/null 2>&1
check "sutra-route-log append" 0 $?
[ -n "$(find "$SANDBOX" -name 'decision-provenance.jsonl' 2>/dev/null)" ] \
  && ok "provenance row landed under sandbox" || no "provenance row not in sandbox"

echo "== 7/8 sutra-outbox add =="
RUN python3 "$BIN/sutra-outbox" add \
  "APPROVE run of W-emi-reconcile for batch 2026-08-19" \
  --operator iso-test >/dev/null 2>&1
check "sutra-outbox add" 0 $?
[ -n "$(find "$SANDBOX" -name 'outbox.jsonl' 2>/dev/null)" ] \
  && ok "outbox row landed under sandbox" || no "outbox row not in sandbox"

echo "== 8/8 sutra-atom open (ROOT pinned to sandbox, plugin-mode assets) =="
# CLAUDE_PLUGIN_ROOT is AUTHORITATIVE for code assets (sutra-paths.sh law);
# state still lands at $ROOT/.sutra with ROOT=CLAUDE_PROJECT_DIR=$SANDBOX.
PLUGIN="$(cd "$SELF_DIR/../.." && pwd)"
( cd "$SANDBOX" && env -i HOME="$SANDBOX" PATH="$PATH" TMPDIR="$SANDBOX/tmp" \
    CLAUDE_PROJECT_DIR="$SANDBOX" CLAUDE_PLUGIN_ROOT="$PLUGIN" \
    CLAUDE_CODE_SESSION_ID=iso-test \
    bash "$BIN/sutra-atom" open --goal "isolation probe atom" \
    --verify-template file-exists --verify-arg "path=$SANDBOX/probe.txt" \
    >/dev/null 2>&1 )
check "sutra-atom open" 0 $?
[ -d "$SANDBOX/.sutra/atoms" ] \
  && ok "atom state landed under sandbox" || no "atom state not in sandbox"

# --- refusal: registry store root inside the sutra package ------------------
echo "== refusal: in-package store root =="
env -i HOME="$SANDBOX" PATH="$PATH" SUTRA_NATIVE_HOME="$SELF_DIR" \
  python3 "$BIN/sutra-registry" list >/dev/null 2>&1
check "sutra-registry refuses in-package store root" 3 $?

# --- repo cleanliness: porcelain gained nothing -----------------------------
echo "== repo porcelain diff (before vs after) =="
AFTER="$(snap)"
if [ "$BEFORE" = "$AFTER" ]; then
  ok "git status --porcelain unchanged (outer repo + sutra submodule)"
else
  no "porcelain changed -- new/modified entries appeared:"
  diff <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER") | sed 's/^/    /'
fi

echo "----------------------------------------"
echo "isolation: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
