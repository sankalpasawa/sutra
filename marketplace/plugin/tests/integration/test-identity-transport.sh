#!/bin/bash
# Integration test: v2.33.0 (D50) identity-on-wire transport boundary.
#
# Codex P2-3 fold (2026-05-06 consult thread 019dfc2e): 7 transport-boundary
# cases that MUST pass before v2.33.0 ships. Replaces the mixed-concern
# tests/integration/test-identity-stamp.sh (archived as
# _archived-test-identity-stamp-pre-v2.33.sh).
#
# Test cases:
#   1. telemetry_optin=false           → no clone, no remote write, no identity
#   2. SUTRA_TELEMETRY=0 + opt-in true → early exit, queue preserved
#   3. fresh opt-in (consent_version=2.33) → manifest has EXACTLY 4 identity
#      fields (git_user_name, github_login, github_id, git_user_email_hash),
#      NO extras (hostname_hash / os_* / arch / shell_name / locale / tz)
#   4. existing opt-in, consent_version missing → re-consent gate blocks;
#      queue preserved; output contains "re-consent for v2.33+"
#   5. push failure (bogus remote) → queue preserved, exit non-zero
#   6. log hygiene → stdout+stderr never contain any identity field VALUE
#   7. old-name absence → manifest.identity has no key named "email_hash"
#      (only git_user_email_hash); no extras outside the 4-field allowlist

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

WORK=$(mktemp -d)
cd "$WORK"
export SUTRA_HOME="$WORK/sutra-home"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"
export CLAUDE_PROJECT_DIR="$WORK/project"
mkdir -p "$CLAUDE_PROJECT_DIR/.claude" "$SUTRA_HOME"

PASS=0
FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

source "$PLUGIN_ROOT/lib/queue.sh"

# ─── Stand-in sutra-data bare repo ────────────────────────────────────
BARE="$WORK/sutra-data-bare.git"
git init --bare --quiet "$BARE"
SEED="$WORK/sutra-data-seed"
git clone --quiet "$BARE" "$SEED"
(cd "$SEED" && git -c user.name=t -c user.email=t@t commit --allow-empty --quiet -m "init" \
  && git -c user.name=t -c user.email=t@t push --quiet origin HEAD:main) >/dev/null 2>&1
rm -rf "$SEED"

export SUTRA_DATA_REMOTE="$BARE"

# ─── Project repo with deterministic git config ───────────────────────
cd "$CLAUDE_PROJECT_DIR"
git init --quiet
git config user.name "TEST_NAME_TOKEN_X9Z7"
git config user.email "test-x9z7@example.com"
git remote add origin git@github.com:fake-user/test-project.git 2>/dev/null || true

# ─── Helpers ──────────────────────────────────────────────────────────
write_project_json() {
  local optin="$1"
  local consent_version="${2:-}"
  local jq_args
  if [ -n "$consent_version" ]; then
    jq -n --arg id "test-install-id" --arg pid "test-project-id" \
          --arg name "test-project" --arg first "2026-05-06T00:00:00Z" \
          --arg ver "2.33.0" --argjson o "$optin" --arg cv "$consent_version" \
          '{install_id:$id, project_id:$pid, project_name:$name, first_seen:$first, sutra_version:$ver, telemetry_optin:$o, consent_version:$cv}' \
      > "$CLAUDE_PROJECT_DIR/.claude/sutra-project.json"
  else
    jq -n --arg id "test-install-id" --arg pid "test-project-id" \
          --arg name "test-project" --arg first "2026-05-06T00:00:00Z" \
          --arg ver "2.33.0" --argjson o "$optin" \
          '{install_id:$id, project_id:$pid, project_name:$name, first_seen:$first, sutra_version:$ver, telemetry_optin:$o}' \
      > "$CLAUDE_PROJECT_DIR/.claude/sutra-project.json"
  fi
}

reset_cache_and_queue() {
  rm -rf "$SUTRA_HOME/sutra-data-cache"
  rm -f "$SUTRA_HOME/metrics-queue.jsonl"
  queue_init >/dev/null 2>&1
  bash "$PLUGIN_ROOT/hooks/emit-metric.sh" os_health hook_fires_session 1 count instant >/dev/null 2>&1
}

inspect_manifest() {
  local clone_dir
  clone_dir=$(mktemp -d)
  git clone --quiet "$BARE" "$clone_dir" >/dev/null 2>&1
  local manifest
  manifest=$(find "$clone_dir/clients" -name manifest.json 2>/dev/null | head -1)
  if [ -n "$manifest" ] && [ -f "$manifest" ]; then
    cat "$manifest"
  fi
  rm -rf "$clone_dir"
}

# Reset bare so each case starts clean
reset_bare() {
  rm -rf "$BARE"
  git init --bare --quiet "$BARE"
  local seed
  seed=$(mktemp -d)
  git clone --quiet "$BARE" "$seed" >/dev/null 2>&1
  (cd "$seed" && git -c user.name=t -c user.email=t@t commit --allow-empty --quiet -m "init" \
    && git -c user.name=t -c user.email=t@t push --quiet origin HEAD:main) >/dev/null 2>&1
  rm -rf "$seed"
}

# ─── CASE 1: telemetry_optin=false → no clone, no remote write ────────
echo "── CASE 1: opt-out (telemetry_optin=false)"
reset_bare
reset_cache_and_queue
write_project_json "false"
QUEUE_BEFORE=$(queue_count)
OUT1=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
EXIT1=$?
QUEUE_AFTER=$(queue_count)
[ "$EXIT1" -eq 0 ] && _ok "case 1: push exits 0 on opt-out" || _no "case 1: push exit code $EXIT1 (expected 0)"
[ "$QUEUE_BEFORE" = "$QUEUE_AFTER" ] && _ok "case 1: queue preserved" || _no "case 1: queue mutated ($QUEUE_BEFORE → $QUEUE_AFTER)"
[ ! -d "$SUTRA_HOME/sutra-data-cache/.git" ] && _ok "case 1: no clone (cache absent)" || _no "case 1: cache exists despite opt-out"
M1=$(inspect_manifest)
[ -z "$M1" ] && _ok "case 1: no manifest on remote" || _no "case 1: manifest found on remote: $M1"

# ─── CASE 2: SUTRA_TELEMETRY=0 kill-switch + opt-in true ──────────────
echo "── CASE 2: kill-switch (SUTRA_TELEMETRY=0 with opt-in true)"
reset_bare
reset_cache_and_queue
write_project_json "true" "2.33"
QUEUE_BEFORE=$(queue_count)
OUT2=$(SUTRA_TELEMETRY=0 bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
EXIT2=$?
QUEUE_AFTER=$(queue_count)
[ "$EXIT2" -eq 0 ] && _ok "case 2: push exits 0 under kill-switch" || _no "case 2: push exit $EXIT2"
[ "$QUEUE_BEFORE" = "$QUEUE_AFTER" ] && _ok "case 2: queue preserved" || _no "case 2: queue mutated"
echo "$OUT2" | grep -q "telemetry off" && _ok "case 2: 'telemetry off' message present" || _no "case 2: missing kill-switch message"
M2=$(inspect_manifest)
[ -z "$M2" ] && _ok "case 2: no manifest on remote" || _no "case 2: manifest found despite kill-switch"

# ─── CASE 3: fresh opt-in with consent_version=2.33 → 4-field allowlist
echo "── CASE 3: fresh opt-in (consent_version=2.33) → 4-field manifest"
reset_bare
reset_cache_and_queue
write_project_json "true" "2.33"
OUT3=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
EXIT3=$?
[ "$EXIT3" -eq 0 ] && _ok "case 3: push exits 0" || _no "case 3: push exit $EXIT3 — out: $OUT3"
echo "$OUT3" | grep -qE "pushed .* metrics" && _ok "case 3: 'pushed N metrics' reported" || _no "case 3: success line missing"
M3=$(inspect_manifest)
if [ -n "$M3" ]; then
  _ok "case 3: manifest exists on remote"
  # Assert exactly 4 keys in identity
  KEYS=$(printf '%s' "$M3" | jq -r '.identity | keys | sort | join(",")')
  EXPECTED="git_user_email_hash,git_user_name,github_id,github_login"
  [ "$KEYS" = "$EXPECTED" ] && _ok "case 3: identity has exactly 4 allowlisted keys" || _no "case 3: identity keys = '$KEYS' (expected '$EXPECTED')"
  # Assert NO extras at any level of identity object
  for forbidden in hostname_hash os_name os_version os_pretty arch shell_name locale tz captured_at captured_by_version; do
    HAS=$(printf '%s' "$M3" | jq -r ".identity.$forbidden // empty")
    [ -z "$HAS" ] || _no "case 3: forbidden field '$forbidden' = '$HAS' present in identity"
  done
  _ok "case 3: no forbidden identity fields (10 checked)"
  # Assert git_user_name is the deterministic test value
  GUN=$(printf '%s' "$M3" | jq -r '.identity.git_user_name // empty')
  [ "$GUN" = "TEST_NAME_TOKEN_X9Z7" ] && _ok "case 3: git_user_name = TEST_NAME_TOKEN_X9Z7" || _no "case 3: git_user_name = '$GUN'"
else
  _no "case 3: manifest missing"
fi

# ─── CASE 4: opt-in true but consent_version missing → re-consent gate
echo "── CASE 4: re-consent gate (opt-in but consent_version absent)"
reset_bare
reset_cache_and_queue
write_project_json "true"  # no consent_version
QUEUE_BEFORE=$(queue_count)
OUT4=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
EXIT4=$?
QUEUE_AFTER=$(queue_count)
[ "$EXIT4" -eq 0 ] && _ok "case 4: re-consent gate exits 0 (queue preserved)" || _no "case 4: exit $EXIT4"
[ "$QUEUE_BEFORE" = "$QUEUE_AFTER" ] && _ok "case 4: queue preserved" || _no "case 4: queue mutated"
echo "$OUT4" | grep -q "re-consent for v2.33+" && _ok "case 4: re-consent message present" || _no "case 4: re-consent message missing — out: $OUT4"
M4=$(inspect_manifest)
[ -z "$M4" ] && _ok "case 4: no manifest mutation" || _no "case 4: manifest written despite gate"

# ─── CASE 4b: opt-in with consent_version=2.18 (older) → still gated ──
echo "── CASE 4b: re-consent gate (consent_version=2.18 < 2.33)"
reset_bare
reset_cache_and_queue
write_project_json "true" "2.18"
OUT4B=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
echo "$OUT4B" | grep -q "re-consent for v2.33+" && _ok "case 4b: 2.18 still gated" || _no "case 4b: 2.18 not gated — out: $OUT4B"

# ─── CASE 5: push failure (bogus remote) → queue preserved, exit !=0 ──
echo "── CASE 5: push failure (bogus remote, queue preserved)"
reset_cache_and_queue
write_project_json "true" "2.33"
QUEUE_BEFORE=$(queue_count)
OUT5=$(SUTRA_DATA_REMOTE="git@github.com:does-not-exist/never-here-bogus.git" \
       bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
EXIT5=$?
QUEUE_AFTER=$(queue_count)
[ "$EXIT5" -ne 0 ] && _ok "case 5: push exits non-zero on remote failure" || _no "case 5: push exit was 0"
[ "$QUEUE_BEFORE" = "$QUEUE_AFTER" ] && _ok "case 5: queue preserved on failure" || _no "case 5: queue mutated on failure"
# Reset SUTRA_DATA_REMOTE for subsequent cases
export SUTRA_DATA_REMOTE="$BARE"

# ─── CASE 6: log hygiene → identity values never in stdout/stderr ─────
echo "── CASE 6: log hygiene (no identity values in output)"
reset_bare
reset_cache_and_queue
write_project_json "true" "2.33"
OUT6=$(bash "$PLUGIN_ROOT/scripts/push.sh" 2>&1)
echo "$OUT6" | grep -q "TEST_NAME_TOKEN_X9Z7" && _no "case 6: git_user_name leaked to stdout/stderr" || _ok "case 6: git_user_name not in output"
echo "$OUT6" | grep -q "test-x9z7@example.com" && _no "case 6: git_user_email leaked to output" || _ok "case 6: git_user_email not in output"
# Hash form of test-x9z7@example.com (sha256[:16])
EMAIL_HASH_TOKEN=$(printf 'test-x9z7@example.com' | shasum -a 256 2>/dev/null | cut -d' ' -f1 | cut -c1-16)
if [ -n "$EMAIL_HASH_TOKEN" ]; then
  echo "$OUT6" | grep -q "$EMAIL_HASH_TOKEN" && _no "case 6: git_user_email_hash leaked" || _ok "case 6: git_user_email_hash not in output"
else
  _ok "case 6: hash check skipped (shasum unavailable)"
fi

# ─── CASE 7: old-name absence (no 'email_hash' key, only git_user_email_hash)
echo "── CASE 7: old-name absence (rejected schema names not present)"
M7=$(inspect_manifest)
if [ -n "$M7" ]; then
  HAS_OLD=$(printf '%s' "$M7" | jq -r '.identity.email_hash // empty')
  [ -z "$HAS_OLD" ] && _ok "case 7: no 'email_hash' field (only git_user_email_hash)" || _no "case 7: forbidden 'email_hash' present"
  # Top-level identity must not contain any other name we didn't authorize
  EXTRA_KEYS=$(printf '%s' "$M7" | jq -r '.identity | keys[] | select(. != "git_user_name" and . != "github_login" and . != "github_id" and . != "git_user_email_hash")')
  [ -z "$EXTRA_KEYS" ] && _ok "case 7: zero extra keys outside allowlist" || _no "case 7: extra keys = '$EXTRA_KEYS'"
else
  _no "case 7: cannot inspect manifest (case 6 push may have failed)"
fi

# ─── Cleanup ──────────────────────────────────────────────────────────
rm -rf "$WORK"

echo ""
echo "test-identity-transport: $PASS passed, $FAIL failed"
exit "$FAIL"
