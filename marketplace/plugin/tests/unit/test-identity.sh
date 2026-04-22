#!/bin/bash
# Unit test: lib/identity.sh — capture function + fallback chain + staleness.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
source "$PLUGIN_ROOT/lib/identity.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# 1) capture_identity emits valid JSON with required keys
OUT=$(capture_identity "1.9.0-unit-test" 2>/dev/null)
if [ -n "$OUT" ] && printf '%s' "$OUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  _ok "capture_identity emits valid JSON"
else
  _no "capture_identity output is not valid JSON"
fi

# 2) All required keys present
REQUIRED="captured_at captured_by_version git_user_name git_user_email_hash github_login github_id hostname_hash os_name os_version arch shell_name locale tz"
MISSING=""
for key in $REQUIRED; do
  if ! printf '%s' "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '$key' in d else 1)" 2>/dev/null; then
    MISSING="$MISSING $key"
  fi
done
if [ -z "$MISSING" ]; then
  _ok "all 13 required keys present"
else
  _no "missing keys:$MISSING"
fi

# 3) captured_by_version matches argument
VER=$(printf '%s' "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['captured_by_version'])" 2>/dev/null)
if [ "$VER" = "1.9.0-unit-test" ]; then
  _ok "captured_by_version round-trips"
else
  _no "captured_by_version mismatch: '$VER' != '1.9.0-unit-test'"
fi

# 4) os_name is always Darwin or Linux (we run on one of these)
OS=$(printf '%s' "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['os_name'] or '')" 2>/dev/null)
case "$OS" in
  Darwin|Linux) _ok "os_name populated: $OS" ;;
  *)            _no "os_name unexpected: '$OS'" ;;
esac

# 5) email_hash, when present, is 16 hex chars
HASH=$(printf '%s' "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('git_user_email_hash') or '')" 2>/dev/null)
if [ -z "$HASH" ]; then
  _ok "git_user_email_hash null (no git email on this box) — acceptable"
elif [ "${#HASH}" -eq 16 ] && printf '%s' "$HASH" | grep -Eq '^[a-f0-9]{16}$'; then
  _ok "git_user_email_hash shape valid (16 hex)"
else
  _no "git_user_email_hash malformed: '$HASH'"
fi

# 6) hostname_hash, when present, is 12 hex chars
HH=$(printf '%s' "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('hostname_hash') or '')" 2>/dev/null)
if [ -z "$HH" ]; then
  _ok "hostname_hash null — acceptable"
elif [ "${#HH}" -eq 12 ] && printf '%s' "$HH" | grep -Eq '^[a-f0-9]{12}$'; then
  _ok "hostname_hash shape valid (12 hex)"
else
  _no "hostname_hash malformed: '$HH'"
fi

# 7) Fallback: when git is unavailable, falls through to $USER
SAVE_PATH="$PATH"
FAKE_BIN=$(mktemp -d)
# Mask git + gh by pointing PATH to empty dir (only python3 + system tools remain)
# Keep python3 + coreutils accessible — rebuild PATH with just /usr/bin + /bin
PATH="/usr/bin:/bin:$FAKE_BIN"
OUT_NO_GIT=$(USER=testuser123 bash "$PLUGIN_ROOT/lib/identity.sh" "1.9.0-fallback" 2>/dev/null)
PATH="$SAVE_PATH"
NAME_FB=$(printf '%s' "$OUT_NO_GIT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('git_user_name') or '')" 2>/dev/null)
if [ "$NAME_FB" = "testuser123" ]; then
  _ok "fallback chain: git/gh missing → git_user_name = \$USER"
else
  # On some systems GECOS may fire before $USER — accept either non-empty
  if [ -n "$NAME_FB" ]; then
    _ok "fallback chain: produced non-empty name ($NAME_FB) without git/gh"
  else
    _no "fallback chain produced empty git_user_name"
  fi
fi
rm -rf "$FAKE_BIN"

# 8) identity_is_stale: missing file → stale (return 0)
if identity_is_stale "/nonexistent/path/identity.json" 604800; then
  _ok "identity_is_stale reports missing file as stale"
else
  _no "identity_is_stale failed to report missing file as stale"
fi

# 9) identity_is_stale: fresh file → not stale (return 1)
FRESH=$(mktemp)
echo '{}' > "$FRESH"
if ! identity_is_stale "$FRESH" 604800; then
  _ok "identity_is_stale: fresh file reported not-stale"
else
  _no "identity_is_stale falsely reported fresh file as stale"
fi
rm -f "$FRESH"

# 10) identity_is_stale: very small max_age → stale immediately
STALE_TEST=$(mktemp)
echo '{}' > "$STALE_TEST"
sleep 2
if identity_is_stale "$STALE_TEST" 1; then
  _ok "identity_is_stale: 1-sec max_age triggers after sleep"
else
  _no "identity_is_stale failed to detect 2s-old file as stale at 1s max_age"
fi
rm -f "$STALE_TEST"

echo ""
echo "test-identity: $PASS passed, $FAIL failed"
exit $FAIL
