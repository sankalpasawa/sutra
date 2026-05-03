#!/bin/bash
# Integration test: v2.18.0 opt-in telemetry push contract.
# Calls push.sh directly via SUTRA_DATA_REMOTE override against a local
# bare repo. No live network. No python3 in the test path (matches the
# v2.13.0 EDR-killed-python3 fix scope).
#
# Asserts:
#   1. queue accumulates after emit-metric.sh
#   2. push.sh + telemetry_optin=true + bare-repo override -> push succeeds, queue cleared, file received, manifest fields correct
#   3. SUTRA_TELEMETRY=0 short-circuits push BEFORE telemetry_optin check
#   4. jq absent -> push.sh exits 127 with install hint
#   5. telemetry_optin=false -> push.sh skips with structured reason (regression guard)
#   6. SUTRA_TELEMETRY=0 short-circuits emit-metric.sh (capture rail kill-switch)

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

# Isolated env
WORK=$(mktemp -d); cd "$WORK"
export SUTRA_HOME="$WORK/sutra-home"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"
export CLAUDE_PROJECT_DIR="$WORK/project"

mkdir -p "$CLAUDE_PROJECT_DIR/.claude" "$SUTRA_HOME"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Stand-in central repo (bare) + cache clone
BARE="$WORK/sutra-data-bare.git"
git init --bare --quiet "$BARE"
SEED=$(mktemp -d)
git -C "$SEED" init --quiet
git -C "$SEED" -c user.name=t -c user.email=t@t commit --allow-empty --quiet -m "init"
git -C "$SEED" -c user.name=t -c user.email=t@t branch -M main
git -C "$SEED" remote add origin "$BARE"
git -C "$SEED" -c user.name=t -c user.email=t@t push --quiet origin main
rm -rf "$SEED"

export SUTRA_DATA_REMOTE="$BARE"

# Pre-seed sutra-project.json with the fields push.sh requires (mirrors what
# /core:start --telemetry on would have written via _sutra_project_lib.sh)
cat > "$CLAUDE_PROJECT_DIR/.claude/sutra-project.json" <<JSON
{
  "install_id": "testinstall0001",
  "project_id": "testproject0001",
  "project_name": "v218-integration-test",
  "first_seen": "2026-05-03T00:00:00Z",
  "sutra_version": "2.18.0",
  "telemetry_optin": true
}
JSON

source "$PLUGIN_ROOT/lib/queue.sh"

# ─── Phase 1: queue accumulates after emit ─────────────────────────────
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 7 count instant
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" estimation entries_session 2 count instant
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" cost tokens_session 44000 tokens instant
C=$(queue_count)
[ "$C" = "3" ] && _ok "queue=3 after 3 emits" || _no "queue=$C expected 3"

# ─── Phase 2: opt-in + push.sh -> push succeeds, file lands ────────────
PUSH_OUT=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
PUSH_RC=$?
[ "$PUSH_RC" = "0" ] && _ok "push.sh exit 0 on opt-in path" || _no "push.sh exit=$PUSH_RC; out=$PUSH_OUT"

C2=$(queue_count)
[ "$C2" = "0" ] && _ok "queue cleared after push" || _no "queue=$C2 expected 0"

# Verify bare repo received the file
CLONE2=$(mktemp -d)
git clone --quiet "$BARE" "$CLONE2"
FILES=$(find "$CLONE2/clients" -name "telemetry-*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
[ "$FILES" = "1" ] && _ok "bare repo received 1 telemetry file" || _no "bare repo telemetry files: $FILES"

# Verify pushed row schema
LINE=$(head -1 "$CLONE2/clients/testinstall0001"/telemetry-*.jsonl 2>/dev/null)
ROW_OK=1
for f in schema_version install_id ts dept metric value; do
  case "$LINE" in *"\"$f\""*) ;; *) ROW_OK=0; _no "field $f missing in pushed row";; esac
done
[ "$ROW_OK" = "1" ] && _ok "pushed row has all required fields" || true

# Verify manifest schema (v2.18 contract — install_id / project_id / project_name_optional / sutra_version / push_count / first_seen / last_seen)
MAN="$CLONE2/clients/testinstall0001/manifest.json"
if [ -f "$MAN" ]; then
  MAN_OK=1
  for f in install_id project_id project_name_optional sutra_version push_count first_seen last_seen; do
    if ! jq -e ".$f" "$MAN" >/dev/null 2>&1; then
      MAN_OK=0
      _no "manifest missing field: $f"
    fi
  done
  # Identity-stamping must NOT be present (v2.2.0 PII fix preserved)
  if jq -e '.identity' "$MAN" >/dev/null 2>&1; then
    _no "manifest.identity present — v2.2.0 PII fix regressed"
  else
    _ok "manifest has no identity stamp (v2.2.0 fix preserved)"
  fi
  [ "$MAN_OK" = "1" ] && _ok "manifest has all v2.18 fields" || true
else
  _no "manifest.json absent at $MAN"
fi

# ─── Phase 3: SUTRA_TELEMETRY=0 short-circuits push BEFORE optin check ─
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 1 count instant 2>/dev/null || true
PRE=$(queue_count)
SUTRA_TELEMETRY=0 bash "$PLUGIN_ROOT/scripts/push.sh" > "$WORK/kill-switch-out.txt" 2>&1
KS_RC=$?
KS_OUT=$(cat "$WORK/kill-switch-out.txt")
POST=$(queue_count)
[ "$KS_RC" = "0" ] && _ok "SUTRA_TELEMETRY=0 -> push.sh exits 0" || _no "expected exit 0; got $KS_RC"
case "$KS_OUT" in *"SUTRA_TELEMETRY=0"*) _ok "SUTRA_TELEMETRY=0 message surfaced";; *) _no "kill-switch message missing; got: $KS_OUT";; esac
[ "$PRE" = "$POST" ] && _ok "queue unchanged under kill-switch" || _no "queue mutated: $PRE -> $POST"

# ─── Phase 4: SUTRA_TELEMETRY=0 short-circuits emit-metric.sh (capture rail) ──
PRE2=$(queue_count)
SUTRA_TELEMETRY=0 bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 5 count instant 2>/dev/null
POST2=$(queue_count)
[ "$PRE2" = "$POST2" ] && _ok "SUTRA_TELEMETRY=0 -> emit-metric.sh writes nothing" || _no "capture rail leaked under kill-switch: $PRE2 -> $POST2"

# ─── Phase 5: jq absent -> push.sh exits 127 with install hint ─────────
# Strip jq from PATH for this single call. Use a sandbox PATH that excludes
# any jq binary directory.
NOJQ_PATH=""
IFS=':' read -ra PARTS <<< "$PATH"
for d in "${PARTS[@]}"; do
  [ -x "$d/jq" ] && continue
  if [ -z "$NOJQ_PATH" ]; then NOJQ_PATH="$d"; else NOJQ_PATH="$NOJQ_PATH:$d"; fi
done
if [ -z "$NOJQ_PATH" ]; then NOJQ_PATH="/usr/bin:/bin"; fi
NOJQ_OUT=$(env -i HOME="$HOME" PATH="$NOJQ_PATH" SUTRA_HOME="$SUTRA_HOME" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$CLAUDE_PROJECT_DIR" bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
NOJQ_RC=$?
[ "$NOJQ_RC" = "127" ] && _ok "jq absent -> push.sh exits 127" || _no "expected exit 127; got $NOJQ_RC"
case "$NOJQ_OUT" in *"jq is required"*) _ok "missing-jq install hint surfaced";; *) _no "install hint missing; got: $NOJQ_OUT";; esac

# ─── Phase 6: telemetry_optin=false -> push.sh skips (regression guard) ─
TMP=$(mktemp "$CLAUDE_PROJECT_DIR/.claude/.flip-XXXXXX.tmp")
jq '.telemetry_optin = false' "$CLAUDE_PROJECT_DIR/.claude/sutra-project.json" > "$TMP"
mv -f "$TMP" "$CLAUDE_PROJECT_DIR/.claude/sutra-project.json"

# Re-emit (capture path), then verify push skips
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 1 count instant
OPTOUT_OUT=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
OPTOUT_RC=$?
QPRE=$(queue_count)
[ "$OPTOUT_RC" = "0" ] && _ok "opt-out -> push.sh exits 0" || _no "expected exit 0; got $OPTOUT_RC"
case "$OPTOUT_OUT" in *"telemetry_optin is false"*) _ok "opt-out skip message surfaced";; *) _no "opt-out message missing; got: $OPTOUT_OUT";; esac
[ "$QPRE" -gt "0" ] && _ok "queue preserved when opt-in=false (no destructive clear)" || _no "queue cleared on opt-out path"

# ─── Cleanup + report ──────────────────────────────────────────────────
rm -rf "$WORK" "$CLONE2"
echo ""
echo "test-onboard-to-push (v2.18.0): $PASS passed, $FAIL failed"
exit $FAIL
