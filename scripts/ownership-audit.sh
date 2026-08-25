#!/usr/bin/env bash
# ownership-audit.sh — D69 (single-repo, single-owner) enforcement.
# Fails if any departed-collaborator identifier appears outside the allowlist.
# Allowlist: .ownership-allowlist at repo root (path-prefix per line, # comments).
set -uo pipefail
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
PAT='tchandrakar|tishant'
ALLOW="$REPO/.ownership-allowlist"
PREFIXES=()
while IFS= read -r p; do PREFIXES+=("$p"); done < <(grep -vE '^\s*(#|$)' "$ALLOW" 2>/dev/null | awk '{print $1}')
FAILS=0
while IFS= read -r line; do
  f="${line%%:*}"
  ok=0
  for p in "${PREFIXES[@]:-}"; do
    case "$f" in "$p"*) ok=1; break ;; esac
  done
  # self-references (this script + allowlist) are structural, not mentions
  case "$f" in scripts/ownership-audit.sh|.ownership-allowlist) ok=1 ;; esac
  if [ "$ok" = 0 ]; then
    echo "D69 VIOLATION: $line"
    FAILS=$((FAILS+1))
  fi
done < <(git grep -rInE -i "$PAT" -- . 2>/dev/null || true)
if [ "$FAILS" -gt 0 ]; then
  echo "ownership-audit: FAIL ($FAILS hits outside .ownership-allowlist)"
  exit 1
fi
echo "ownership-audit: PASS (only allowlisted historical mentions)"
