#!/bin/bash
# Integration test: onboard → push → manifest stamped with identity block.
# Uses local bare repo as sutra-data stand-in (no network).
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

WORK=$(mktemp -d); cd "$WORK"
export SUTRA_HOME="$WORK/sutra-home"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"
export CLAUDE_PROJECT_DIR="$WORK/project"

mkdir -p "$CLAUDE_PROJECT_DIR/.claude" "$SUTRA_HOME"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Stand-in sutra-data repo
BARE="$WORK/sutra-data-bare.git"
git init --bare --quiet "$BARE"
CACHE="$SUTRA_HOME/sutra-data-cache"
git clone --quiet "$BARE" "$CACHE"
(cd "$CACHE" && git -c user.name=t -c user.email=t@t commit --allow-empty --quiet -m "init" \
  && git -c user.name=t -c user.email=t@t push --quiet origin HEAD:main)

# Phase 1: onboard with telemetry on — should stamp identity locally
cd "$CLAUDE_PROJECT_DIR"
git init --quiet
git remote add origin git@github.com:fake-user/test-project.git 2>/dev/null || true

SUTRA_AUTO_OPTIN=1 bash "$PLUGIN_ROOT/scripts/onboard.sh" >/dev/null 2>&1

# Check sutra-project.json has identity
if python3 -c "import json; d=json.load(open('.claude/sutra-project.json')); assert 'identity' in d; assert d['identity'].get('git_user_name'); print(d['identity']['git_user_name'])" >/dev/null 2>&1; then
  _ok "onboard stamped identity block into .claude/sutra-project.json"
else
  _no "onboard did NOT stamp identity into .claude/sutra-project.json"
fi

# Check cache file written
if [ -f "$SUTRA_HOME/identity.json" ]; then
  _ok "onboard cached identity at \$SUTRA_HOME/identity.json"
else
  _no "onboard did not cache identity.json"
fi

# Phase 2: emit a metric + simulate push with the real push.sh
source "$PLUGIN_ROOT/lib/queue.sh"
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 1 count instant >/dev/null 2>&1

# Point the cache at the local bare so push.sh hits it instead of sankalpasawa/sutra-data
(cd "$CACHE" && git remote set-url origin "$BARE")

OUTPUT=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
if echo "$OUTPUT" | grep -qE "pushed .* metrics"; then
  _ok "push.sh reported successful push"
else
  _no "push.sh did not report success; output: $OUTPUT"
fi

# Phase 3: verify manifest on bare repo has identity block
CLONE2=$(mktemp -d)
git clone --quiet "$BARE" "$CLONE2"
MANIFEST=$(find "$CLONE2/clients" -name manifest.json 2>/dev/null | head -1)
if [ -z "$MANIFEST" ]; then
  _no "no manifest.json found in pushed bare repo"
else
  if python3 -c "import json; d=json.load(open('$MANIFEST')); assert 'identity' in d; assert d['identity'].get('captured_at'); assert d['identity'].get('os_name'); print('ok')" >/dev/null 2>&1; then
    _ok "manifest.json in bare repo has identity block with captured_at + os_name"
  else
    _no "manifest.json present but missing/malformed identity block"
  fi
fi

# Phase 4: staleness — second push within 7d should NOT recapture
CACHE_MTIME_BEFORE=$(stat -f %m "$SUTRA_HOME/identity.json" 2>/dev/null || stat -c %Y "$SUTRA_HOME/identity.json" 2>/dev/null)
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 2 count instant >/dev/null 2>&1
bash "$PLUGIN_ROOT/scripts/push.sh" >/dev/null 2>&1
CACHE_MTIME_AFTER=$(stat -f %m "$SUTRA_HOME/identity.json" 2>/dev/null || stat -c %Y "$SUTRA_HOME/identity.json" 2>/dev/null)
if [ "$CACHE_MTIME_BEFORE" = "$CACHE_MTIME_AFTER" ]; then
  _ok "second push within 7d did not rewrite identity cache"
else
  _no "second push rewrote cache unexpectedly (before=$CACHE_MTIME_BEFORE after=$CACHE_MTIME_AFTER)"
fi

# Phase 5: forced staleness — move cache mtime 8 days back, push should recapture
EIGHT_DAYS_AGO=$(python3 -c "import time; t=time.time()-8*86400; import time as tt; print(tt.strftime('%Y%m%d%H%M.%S', tt.localtime(t)))")
touch -t "$EIGHT_DAYS_AGO" "$SUTRA_HOME/identity.json" 2>/dev/null || true
CACHE_MTIME_STALE=$(stat -f %m "$SUTRA_HOME/identity.json" 2>/dev/null || stat -c %Y "$SUTRA_HOME/identity.json" 2>/dev/null)
bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 3 count instant >/dev/null 2>&1
bash "$PLUGIN_ROOT/scripts/push.sh" >/dev/null 2>&1
CACHE_MTIME_RECAP=$(stat -f %m "$SUTRA_HOME/identity.json" 2>/dev/null || stat -c %Y "$SUTRA_HOME/identity.json" 2>/dev/null)
if [ "$CACHE_MTIME_STALE" != "$CACHE_MTIME_RECAP" ]; then
  _ok "8-day-old cache triggered recapture on push"
else
  _no "stale cache did NOT trigger recapture"
fi

# Phase 6: emit-metric PII regression — telemetry channel stays PII-free
if ! bash "$PLUGIN_ROOT/hooks/emit-metric.sh" "user@example.com" metric_x 1 count instant >/dev/null 2>&1; then
  _ok "emit-metric still rejects PII in dept field (regression)"
else
  _no "REGRESSION: emit-metric accepted PII in dept field"
fi

rm -rf "$WORK" "$CLONE2"
echo ""
echo "test-identity-stamp: $PASS passed, $FAIL failed"
exit $FAIL
