#!/bin/bash
# PROTO-019: External Peer Review (Codex) Gate
#
# Two-phase gate:
#   request : prepare a review packet file and instruct the operator to
#             invoke the /codex skill with it.
#   verify  : check the latest review packet for a non-PENDING verdict.
#             Exit 0 on PASS/ADVISORY, 1 on FAIL/PENDING.
#
# Usage:
#   bash codex-review-gate.sh request [scope]   # scope default: HEAD
#   bash codex-review-gate.sh verify
#
# Fixes vs prior revision (post-codex review):
#   - #6 : Request no longer creates a file on the verify path.
#   - #10: $SCOPE is validated (git rev-parse) before being passed to git.
#          Override reason sanitized (newlines stripped).
#
# Bypass: CODEX_OVERRIDE=1 CODEX_OVERRIDE_REASON="..." — logged.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REVIEW_DIR="$REPO_ROOT/.enforcement/codex-reviews"
mkdir -p "$REVIEW_DIR"

ACTION="${1:-request}"

# ─── Override path (both actions honor it) ───────────────────────────────
if [ "${CODEX_OVERRIDE:-0}" = "1" ]; then
  REASON_RAW="${CODEX_OVERRIDE_REASON:-no-reason-given}"
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # B5 shared-writer: typed audit row + legacy mirror until v1.10 cutover.
  _OA_LIB="$REPO_ROOT/holding/hooks/lib/override-audit.sh"
  [ -f "$_OA_LIB" ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"
  if [ -f "$_OA_LIB" ]; then
    # shellcheck disable=SC1090
    source "$_OA_LIB"
    _OA_MODE="legacy"
    [ -n "${CODEX_OVERRIDE_TOKEN:-}" ] && _OA_MODE="strict"
    if accept_override "CODEX_OVERRIDE" "D29" "codex-review-gate.sh" "$REASON_RAW" 1 "$_OA_MODE" "$ACTION"; then
      REASON_SAFE=$(printf '%s' "$REASON_RAW" | tr -d '\n\r' | head -c 500)
      echo "$TS CODEX_OVERRIDE=1 action=$ACTION reason=$REASON_SAFE" >> "$REVIEW_DIR/overrides.log"
      echo "PROTO-019 OVERRIDE logged. Gate bypassed."
      exit 0
    fi
    # Helper rejected (bad reason or strict-mode token mismatch).
    echo "PROTO-019 override REJECTED by helper (reason malformed or strict-mode token invalid)."
    exit 1
  else
    REASON_SAFE=$(printf '%s' "$REASON_RAW" | tr -d '\n\r' | head -c 500)
    echo "$TS CODEX_OVERRIDE=1 action=$ACTION reason=$REASON_SAFE" >> "$REVIEW_DIR/overrides.log"
    echo "PROTO-019 OVERRIDE logged. Gate bypassed."
    exit 0
  fi
fi

case "$ACTION" in
  request)
    SCOPE_RAW="${2:-HEAD}"
    # Validate SCOPE as a git rev/range to avoid pathspec injection
    if ! (cd "$REPO_ROOT" && git rev-parse --verify "$SCOPE_RAW" >/dev/null 2>&1); then
      # Allow ranges like A..B
      LEFT="${SCOPE_RAW%%..*}"; RIGHT="${SCOPE_RAW##*..}"
      if ! (cd "$REPO_ROOT" && git rev-parse --verify "$LEFT" >/dev/null 2>&1 && git rev-parse --verify "$RIGHT" >/dev/null 2>&1); then
        echo "ERROR: invalid scope '$SCOPE_RAW' — not a git rev or range"
        exit 2
      fi
    fi
    SCOPE="$SCOPE_RAW"
    TS=$(date -u +%Y%m%d-%H%M%S)
    PENDING="$REVIEW_DIR/pending-$TS.md"

    {
      echo "# Codex Review Request — $TS"
      echo
      echo "**Scope**: \`$SCOPE\`"
      echo "**Repo**:  $REPO_ROOT"
      echo
      echo "## Changes (stat)"
      echo
      echo '```'
      # SCOPE is a validated git rev/range; do NOT pass after `--` (that
      # would make git interpret it as pathspec — new bug fix).
      (cd "$REPO_ROOT" && git diff --stat "$SCOPE" 2>/dev/null) || echo "(no diff)"
      echo '```'
      echo
      echo "## Diff (first 500 lines)"
      echo
      echo '```diff'
      (cd "$REPO_ROOT" && git diff "$SCOPE" 2>/dev/null | head -500) || echo "(no diff)"
      echo '```'
      echo
      echo "---"
      echo
      echo "## Codex verdict (operator fills)"
      echo
      echo "<!-- After invoking /codex review, paste verdict below. -->"
      echo "<!-- Required marker: CODEX-VERDICT: PASS | FAIL | ADVISORY -->"
      echo
      echo "CODEX-VERDICT: PENDING"
    } > "$PENDING"

    echo "Codex review request written: $PENDING"
    echo
    echo "Next step:"
    echo "  1. Invoke the /codex skill to review this diff."
    echo "  2. Update $PENDING with CODEX-VERDICT: PASS|FAIL|ADVISORY"
    echo "  3. Run: bash $0 verify"
    exit 0
    ;;

  verify)
    # Find the most recent pending/review file
    LATEST=$(ls -t "$REVIEW_DIR"/pending-*.md "$REVIEW_DIR"/v*-review-*.md 2>/dev/null | head -1)
    if [ -z "$LATEST" ]; then
      echo "ERROR: no review file found. Run: bash $0 request"
      exit 1
    fi
    VERDICT=$(grep -m1 '^CODEX-VERDICT:' "$LATEST" 2>/dev/null || true)
    case "$VERDICT" in
      "CODEX-VERDICT: PASS"|"CODEX-VERDICT: ADVISORY")
        echo "PROTO-019: $VERDICT (file: $LATEST)"
        exit 0
        ;;
      "CODEX-VERDICT: FAIL")
        echo "PROTO-019: FAIL — $LATEST"
        exit 1
        ;;
      *)
        echo "PROTO-019: PENDING — no non-PENDING verdict yet. File: $LATEST"
        exit 1
        ;;
    esac
    ;;

  *)
    echo "Usage: $0 {request [scope]|verify}"
    exit 2
    ;;
esac
