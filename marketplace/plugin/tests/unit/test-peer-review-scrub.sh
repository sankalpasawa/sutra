#!/bin/bash
# Unit test: bin/peer-review-payload-scrub.sh — A10 outbound egress scrubber.
# Contract:
#   peer-review-payload-scrub.sh <file>
#   - stdout: scrubbed payload (scrub_text applied from lib/privacy-sanitize.sh)
#   - stderr: "SCRUB redacted=<N> ..." notice (N = redaction tokens introduced)
#   - exit 0 : ok (redacted >= 0)
#   - exit 2 : usage error (missing arg / unreadable file)
#   - exit 3 : oversize (> 500 KB) — caller decides (AskUserQuestion)
#   - exit 4 : binary (non-text mime) — refuse to egress
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
SCRUB="$PLUGIN_ROOT/bin/peer-review-payload-scrub.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# 1) clean text passes through unchanged, exit 0
printf 'Please review this diff: function add(a,b){return a+b}\n' > "$TMP/clean.txt"
OUT=$(bash "$SCRUB" "$TMP/clean.txt" 2>/dev/null); RC=$?
[ "$RC" = "0" ] && _ok "clean text exit 0" || _no "clean text expected exit 0, got $RC"
case "$OUT" in *"function add(a,b)"*) _ok "clean text preserved" ;; *) _no "clean text mangled: $OUT" ;; esac

# 2) AWS access key id redacted
printf 'key is AKIAIOSFODNN7EXAMPLE in the config\n' > "$TMP/aws.txt"
OUT=$(bash "$SCRUB" "$TMP/aws.txt" 2>/dev/null)
case "$OUT" in
  *AKIAIOSFODNN7EXAMPLE*) _no "AWS key LEAKED in output" ;;
  *"<AWS-KEY-ID>"*) _ok "AWS key redacted" ;;
  *) _no "AWS key not handled: $OUT" ;;
esac

# 3) JWT redacted
printf 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N\n' > "$TMP/jwt.txt"
OUT=$(bash "$SCRUB" "$TMP/jwt.txt" 2>/dev/null)
case "$OUT" in *"<JWT>"*) _ok "JWT redacted" ;; *eyJhbGci*) _no "JWT LEAKED" ;; *) _no "JWT not handled" ;; esac

# 4) OpenAI-style key redacted
printf 'export OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz0123\n' > "$TMP/oai.txt"
OUT=$(bash "$SCRUB" "$TMP/oai.txt" 2>/dev/null)
case "$OUT" in
  *"sk-proj-abcdefghijklmnop"*) _no "OpenAI key LEAKED" ;;
  *"<OPENAI-KEY>"*) _ok "OpenAI key redacted" ;;
  *) _no "OpenAI key not handled: $OUT" ;;
esac

# 5) stderr reports a redaction count > 0 when secrets present
ERR=$(bash "$SCRUB" "$TMP/aws.txt" 2>&1 >/dev/null)
case "$ERR" in *redacted=*) _ok "stderr emits redacted= count" ;; *) _no "no redacted= notice on stderr: $ERR" ;; esac
# redacted should be 0 for clean text
ERR0=$(bash "$SCRUB" "$TMP/clean.txt" 2>&1 >/dev/null)
case "$ERR0" in *redacted=0*) _ok "clean text redacted=0" ;; *) _no "clean text not redacted=0: $ERR0" ;; esac

# 6) missing arg -> exit 2
bash "$SCRUB" >/dev/null 2>&1; RC=$?
[ "$RC" = "2" ] && _ok "missing arg exit 2" || _no "missing arg expected 2, got $RC"

# 7) unreadable / nonexistent file -> exit 2
bash "$SCRUB" "$TMP/does-not-exist.txt" >/dev/null 2>&1; RC=$?
[ "$RC" = "2" ] && _ok "missing file exit 2" || _no "missing file expected 2, got $RC"

# 8) oversize (>500KB) -> exit 3
head -c 600000 /dev/zero | tr '\0' 'a' > "$TMP/big.txt"
bash "$SCRUB" "$TMP/big.txt" >/dev/null 2>&1; RC=$?
[ "$RC" = "3" ] && _ok "oversize exit 3" || _no "oversize expected 3, got $RC"

# 9) binary input -> exit 4
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00' > "$TMP/img.bin"
bash "$SCRUB" "$TMP/img.bin" >/dev/null 2>&1; RC=$?
[ "$RC" = "4" ] && _ok "binary input exit 4" || _no "binary expected 4, got $RC"

# 10) multiple secrets -> redacted count >= 2
printf 'AKIAIOSFODNN7EXAMPLE and ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n' > "$TMP/multi.txt"
ERR=$(bash "$SCRUB" "$TMP/multi.txt" 2>&1 >/dev/null)
N=$(printf '%s' "$ERR" | sed -nE 's/.*redacted=([0-9]+).*/\1/p')
[ "${N:-0}" -ge 2 ] && _ok "multiple secrets redacted>=2 (got $N)" || _no "expected redacted>=2, got ${N:-none}"

echo ""
echo "test-peer-review-scrub: $PASS passed, $FAIL failed"
exit "$FAIL"
