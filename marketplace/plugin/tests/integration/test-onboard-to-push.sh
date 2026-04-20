#!/bin/bash
# Integration test: full loop — emit N metrics, verify queue, simulate push to local bare repo.
# Uses a local bare repo as a stand-in for sutra-data (no live network).
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
CACHE="$SUTRA_HOME/sutra-data-cache"
git clone --quiet "$BARE" "$CACHE"
(cd "$CACHE" && git -c user.name=t -c user.email=t@t commit --allow-empty --quiet -m "init" && git -c user.name=t -c user.email=t@t push --quiet origin HEAD:main)

# Phase A: emit 3 metrics
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 7 count instant
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" estimation entries_session 2 count instant
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" cost tokens_session 44000 tokens instant
source "$PLUGIN_ROOT/lib/queue.sh"
C=$(queue_count)
[ "$C" = "3" ] && _ok "queue has 3 after 3 emits" || _no "queue=$C expected 3"

# Phase B: simulate /sutra-push against local bare repo
INSTALL_ID=$(python3 -c "
import hashlib,os
v=open('$PLUGIN_ROOT/.claude-plugin/plugin.json').read()
import json
v=json.loads(v)['version']
print(hashlib.sha256(f\"{os.environ['HOME']}:{v}\".encode()).hexdigest()[:16])
")
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
DEST="$CACHE/clients/$INSTALL_ID"
mkdir -p "$DEST"
cp "$(queue_file)" "$DEST/telemetry-$TS.jsonl"
(cd "$CACHE" && git -c user.name=t -c user.email=t@t add . && git -c user.name=t -c user.email=t@t commit --quiet -m "push $INSTALL_ID" && git -c user.name=t -c user.email=t@t push --quiet)
queue_clear
C2=$(queue_count)
[ "$C2" = "0" ] && _ok "queue cleared after push" || _no "queue=$C2 expected 0"

# Phase C: verify bare repo received the file
CLONE2=$(mktemp -d)
git clone --quiet "$BARE" "$CLONE2"
FILES=$(find "$CLONE2/clients" -name "telemetry-*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
[ "$FILES" = "1" ] && _ok "bare repo received 1 telemetry file" || _no "bare repo files: $FILES"

# Phase D: verify file schema
LINE=$(head -1 "$CLONE2/clients/$INSTALL_ID"/telemetry-*.jsonl)
for f in schema_version install_id ts dept metric value; do
  case "$LINE" in *"\"$f\""*) ;; *) _no "field $f missing in pushed row"; FAIL=$FAIL;; esac
done
_ok "pushed row has all required fields"

rm -rf "$WORK" "$CLONE2"
echo ""
echo "test-onboard-to-push: $PASS passed, $FAIL failed"
exit $FAIL
