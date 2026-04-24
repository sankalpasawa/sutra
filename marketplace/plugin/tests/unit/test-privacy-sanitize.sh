#!/bin/bash
# sutra/marketplace/plugin/tests/unit/test-privacy-sanitize.sh
# Unit tests for privacy-sanitize.sh (v2.0 privacy model, codex-reviewed).
# NOTE: Test fixtures intentionally contain key-shaped strings to verify the
# scrubber actually works. These are NOT real secrets.

set -u

LIB_DIR="$(cd "$(dirname "$0")/../../lib" && pwd)"
source "$LIB_DIR/privacy-sanitize.sh"

TEST_HOME=$(mktemp -d -t sutra-test-XXXXXX)
export SUTRA_HOME="$TEST_HOME"
export SUTRA_FEEDBACK_AUTO="$TEST_HOME/feedback/auto"
export SUTRA_FEEDBACK_MANUAL="$TEST_HOME/feedback/manual"
export SUTRA_CONSENT_FILE="$TEST_HOME/consent"
export SUTRA_MEM_COUNTER="$TEST_HOME/mem-counter"

cleanup() { rm -rf "$TEST_HOME" 2>/dev/null; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILURES=()

_pass() { PASS=$((PASS + 1)); }
_fail() { FAIL=$((FAIL + 1)); FAILURES+=("$1"); }

assert_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if printf '%s' "$haystack" | grep -qF -- "$needle"; then _pass; else _fail "$desc: missing needle='$needle' in '$haystack'"; fi
}
assert_not_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if ! printf '%s' "$haystack" | grep -qF -- "$needle"; then _pass; else _fail "$desc: found forbidden needle='$needle' in '$haystack'"; fi
}
assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then _pass; else _fail "$desc: expected='$expected' actual='$actual'"; fi
}

reset_state() {
  unset SUTRA_TELEMETRY SUTRA_FEEDBACK_CONSENT SUTRA_LEGACY_TELEMETRY
  rm -rf "$SUTRA_FEEDBACK_AUTO" 2>/dev/null
  rm -f "$SUTRA_MEM_COUNTER" "$SUTRA_CONSENT_FILE" 2>/dev/null
}

# derive_signal
OUT=$(derive_signal override codex-directive 1 2>/dev/null)
assert_contains "derive_signal emits category" '"category":"override"' "$OUT"
assert_contains "derive_signal emits sub" '"sub":"codex-directive"' "$OUT"
assert_contains "derive_signal emits delta" '"delta":1' "$OUT"
assert_contains "derive_signal emits day" "\"day\":\"$(date -u +%Y-%m-%d)\"" "$OUT"

ERR=$(derive_signal not_in_allowlist foo 2>&1 >/dev/null)
assert_contains "derive_signal rejects invalid category" "rejected category" "$ERR"

ERR=$(derive_signal override 'bad;subcat' 2>&1 >/dev/null)
assert_contains "derive_signal rejects non-alphanumeric sub" "rejected subcategory" "$ERR"

ERR=$(derive_signal override foo abc 2>&1 >/dev/null)
assert_contains "derive_signal rejects non-integer delta" "rejected delta" "$ERR"

if command -v python3 >/dev/null 2>&1; then
  OUT=$(derive_signal tool_fail bash-timeout 3)
  if printf '%s' "$OUT" | python3 -c "import sys,json; json.loads(sys.stdin.read())" 2>/dev/null; then
    _pass
  else
    _fail "derive_signal output is valid JSON"
  fi
fi

# scrub_text
OUT=$(scrub_text "see /Users/abhishek/code/secret.py")
assert_contains "scrub_text /Users path" "<HOME>" "$OUT"
assert_not_contains "scrub_text /Users path (neg)" "abhishek" "$OUT"

OUT=$(scrub_text "error at /home/alice/.ssh/id_rsa")
assert_contains "scrub_text /home path" "<HOME>" "$OUT"
assert_not_contains "scrub_text /home (neg)" "alice" "$OUT"

# Test fixture: synthetic KEY=<22+ chars> pattern to exercise scrub regex.
OUT=$(scrub_text 'FAKE_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxx')
assert_contains "scrub_text KEY=value" "<KEY=REDACTED>" "$OUT"

OUT=$(scrub_text "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdefghij")
assert_contains "scrub_text Bearer token" "<REDACTED>" "$OUT"

OUT=$(scrub_text "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijklmnop")
assert_contains "scrub_text JWT" "<JWT>" "$OUT"

OUT=$(scrub_text "git clone https://alice:pass123@github.com/org/repo.git")
assert_contains "scrub_text git creds" "<CREDS>" "$OUT"
assert_not_contains "scrub_text git creds (neg)" "pass123" "$OUT"

OUT=$(scrub_text "Contact alice@example.com")
assert_contains "scrub_text email" "<EMAIL>" "$OUT"
assert_not_contains "scrub_text email (neg)" "alice@example" "$OUT"

OUT=$(scrub_text 'conn: postgres://user:secret@db.host/mydb')
assert_contains "scrub_text DB URI postgres" "<DB-URI>" "$OUT"

OUT=$(scrub_text 'redis://:mypass@cache.local:6379/0')
assert_contains "scrub_text DB URI redis" "<DB-URI>" "$OUT"

OUT=$(scrub_text "-----BEGIN OPENSSH PRIVATE KEY-----")
assert_contains "scrub_text SSH key" "<SSH-KEY>" "$OUT"

OUT=$(scrub_text "-----BEGIN CERTIFICATE-----")
assert_contains "scrub_text PEM begin" "<PEM-BEGIN>" "$OUT"

OUT=$(scrub_text "perfectly benign text with no secrets at all")
assert_contains "scrub_text benign unchanged" "benign text" "$OUT"

# privacy_gate
reset_state

SUTRA_TELEMETRY=0 privacy_gate
assert_eq "privacy_gate SUTRA_TELEMETRY=0 -> 2" "2" "$?"

privacy_gate
assert_eq "privacy_gate no consent -> 1" "1" "$?"

SUTRA_FEEDBACK_CONSENT=granted privacy_gate
assert_eq "privacy_gate env consent -> 0" "0" "$?"

mkdir -p "$SUTRA_HOME"
echo granted > "$SUTRA_CONSENT_FILE"
privacy_gate
assert_eq "privacy_gate file consent -> 0" "0" "$?"
rm -f "$SUTRA_CONSENT_FILE"

SUTRA_LEGACY_TELEMETRY=1 privacy_gate
assert_eq "privacy_gate legacy -> 2" "2" "$?"

# signal_write
reset_state
SUTRA_TELEMETRY=0 signal_write override test-hook 1
if ! find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' 2>/dev/null | grep -q . && [ ! -s "$SUTRA_MEM_COUNTER" ]; then
  _pass
else
  _fail "signal_write opt-out should produce no capture"
fi

reset_state
signal_write override test-hook 1
if [ -s "$SUTRA_MEM_COUNTER" ]; then _pass; else _fail "signal_write no-consent -> mem counter"; fi
if ! find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' 2>/dev/null | grep -q .; then _pass; else _fail "signal_write no-consent -> no disk"; fi

reset_state
SUTRA_FEEDBACK_CONSENT=granted signal_write override test-hook 1
if find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' 2>/dev/null | grep -q .; then _pass; else _fail "signal_write consent -> disk write"; fi

# sutra_safe_write
reset_state
ln -s /tmp/wherever "$SUTRA_HOME/linked" 2>/dev/null
sutra_safe_write "$SUTRA_HOME/linked" "should-fail" 2>/dev/null
assert_eq "sutra_safe_write refuses symlink" "1" "$?"

TARGET="$SUTRA_HOME/normal.txt"
sutra_safe_write "$TARGET" "hello"
assert_eq "sutra_safe_write normal exit" "0" "$?"

if [ -f "$TARGET" ]; then
  CONTENT=$(cat "$TARGET")
  assert_eq "sutra_safe_write content" "hello" "$CONTENT"
  PERMS=$(stat -f %Lp "$TARGET" 2>/dev/null || stat -c %a "$TARGET" 2>/dev/null)
  assert_eq "sutra_safe_write 0600 perms" "600" "$PERMS"
fi

# sutra_grant_consent
reset_state
sutra_grant_consent
if [ -f "$SUTRA_CONSENT_FILE" ] && grep -q "granted" "$SUTRA_CONSENT_FILE"; then _pass; else _fail "sutra_grant_consent writes file"; fi

# Summary
TOTAL=$((PASS + FAIL))
echo ""
echo "-- Privacy Sanitize Lib --"
echo "PASS: $PASS / $TOTAL"
if [ $FAIL -gt 0 ]; then
  echo "FAIL: $FAIL"
  for f in "${FAILURES[@]}"; do echo "  x $f"; done
  exit 1
fi
echo "  OK all green"
exit 0
