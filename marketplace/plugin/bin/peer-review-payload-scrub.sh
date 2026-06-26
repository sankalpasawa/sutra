#!/bin/bash
# sutra/marketplace/plugin/bin/peer-review-payload-scrub.sh
# A10 — outbound egress scrubber for the peer-review lanes (codex-sutra, deepseek).
#
# WHY: both lanes send diffs / file contents to a third-party AI API. Secrets or
# PII in that payload would leak. This wraps lib/privacy-sanitize.sh scrub_text()
# and is called by each skill BEFORE the payload is sent.
#
# Contract:
#   peer-review-payload-scrub.sh <file>
#     stdout : scrubbed payload (safe to egress)
#     stderr : "SCRUB redacted=<N> bytes=<B>"  (N = redaction tokens introduced)
#     exit 0 : ok (N >= 0)   — never blocks; auto-redacts + reports
#     exit 2 : usage error (missing arg / unreadable file) — caller must abort
#     exit 3 : oversize (> MAX_BYTES) — caller runs AskUserQuestion (truncate vs abort)
#     exit 4 : binary input (non-text) — refuse; never egress binary
#
# Fail-closed: on any internal error the script exits non-zero rather than
# emitting an unscrubbed payload.
set -uo pipefail

MAX_BYTES="${PEER_REVIEW_SCRUB_MAX_BYTES:-512000}"   # 500 KB

# Locate lib relative to this script (bin/ and lib/ are siblings under plugin/)
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SELF_DIR/../lib/privacy-sanitize.sh"

FILE="${1:-}"

# --- usage / readability guards (exit 2) ---
if [ -z "$FILE" ]; then
  echo "SCRUB error=usage reason=missing_file_arg" >&2
  exit 2
fi
if [ ! -f "$FILE" ] || [ ! -r "$FILE" ]; then
  echo "SCRUB error=usage reason=unreadable_file file=$FILE" >&2
  exit 2
fi
if [ ! -f "$LIB" ] || [ ! -r "$LIB" ]; then
  echo "SCRUB error=internal reason=privacy_lib_missing lib=$LIB" >&2
  exit 2
fi

# --- size cap (exit 3) ---
BYTES=$(wc -c < "$FILE" | tr -d '[:space:]')
if [ "${BYTES:-0}" -gt "$MAX_BYTES" ]; then
  echo "SCRUB error=oversize bytes=$BYTES max=$MAX_BYTES" >&2
  exit 3
fi

# --- binary guard (exit 4) ---
# A text payload is what a code reviewer expects. Refuse anything the OS classifies
# as non-text, and as a fallback refuse any file containing a NUL byte.
MIME=$(file -b --mime-type "$FILE" 2>/dev/null || echo "unknown")
case "$MIME" in
  text/*|application/json|application/xml|application/javascript|inode/x-empty|unknown) ;;
  *) echo "SCRUB error=binary mime=$MIME file=$FILE" >&2; exit 4 ;;
esac
# NOTE: `grep -qU $'\x00'` does NOT work — bash cannot hold a NUL in a string,
# so $'\x00' degrades to an empty pattern that matches EVERY file (flagging all
# text as binary). Use tr+cmp instead: strip NULs and compare to the original;
# if they differ, the file contained a NUL byte. Portable across BSD + GNU.
if ! LC_ALL=C tr -d '\000' < "$FILE" | cmp -s - "$FILE"; then
  echo "SCRUB error=binary reason=nul_byte file=$FILE" >&2
  exit 4
fi

# --- scrub (exit 0) ---
# shellcheck source=../lib/privacy-sanitize.sh
. "$LIB" || { echo "SCRUB error=internal reason=lib_source_failed" >&2; exit 2; }

RAW=$(cat "$FILE")
CLEAN=$(scrub_text "$RAW")

# Count redaction tokens introduced (placeholders the scrubber emits).
# Conservative: count occurrences of each known placeholder in CLEAN.
REDACTED=$(printf '%s' "$CLEAN" | grep -oE '<(HOME|TMP|SSH-KEY|PEM-BEGIN|PEM-END|JWT|GITHUB-TOKEN|OPENAI-KEY|AWS-KEY-ID|SLACK-TOKEN|STRIPE-KEY|SLACK-WEBHOOK|DISCORD-WEBHOOK|SIGNED-URL-PARAMS|CREDS|DB-URI|KEY=REDACTED|PHONE|EMAIL|HIGH-ENTROPY)>' 2>/dev/null | grep -c . || true)
REDACTED="${REDACTED:-0}"

printf '%s' "$CLEAN"
echo "SCRUB redacted=$REDACTED bytes=$BYTES" >&2
exit 0
