#!/usr/bin/env bash
# sutra/hooks/h-sutra-drift-check.sh
#
# Pre-commit + CI drift gate. Blocks commit if canonical H-Sutra artifacts
# changed but native vendored mirrors weren't sync'd (or hash lock is stale).
#
# Per D49 + codex round-3 P1-1 / round-4 P2-2 fold (executable-bit + git-index
# mode check). Per [Never bypass governance]: hook blocks; root cause is run
# `bash sutra/scripts/sync-h-sutra.sh && git add native/`.
#
# Invoked by sutra/.git/hooks/pre-commit (or pre-commit-test-gate.sh chain).
# CI can invoke standalone before tag push.
#
# Exit:
#   0 = no drift OR no canonical/mirror staged (nothing to gate)
#   2 = drift detected; commit blocked
#   1 = infra failure (missing file, jq missing, etc.)

set -uo pipefail

# Resolve sutra repo root from script location (codex review P2-A fold).
# `git rev-parse --show-toplevel` resolves to sutra repo root in standalone
# clone — prefixing every path with another `sutra/` doubled the prefix.
# Script-relative resolution is invariant across standalone + submodule.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SUTRA_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

CANONICAL_CLASSIFY="$SUTRA_ROOT/marketplace/plugin/skills/human-sutra/scripts/classify.sh"
CANONICAL_LIB="$SUTRA_ROOT/marketplace/plugin/lib/h-sutra-classify-and-write.sh"
NATIVE_CLASSIFY="$SUTRA_ROOT/marketplace/native/scripts/classify.sh"
NATIVE_LIB="$SUTRA_ROOT/marketplace/native/lib/h-sutra-classify-and-write.sh"
LOCK_FILE="$SUTRA_ROOT/marketplace/native/.h-sutra-sync.lock"

# Kill-switch
[ -n "${H_SUTRA_DRIFT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.h-sutra-drift-disabled" ] && exit 0

# Resolve canonical/mirror paths relative to sutra repo root (for `git diff --name-only --cached`).
# Codex review P2-A fold: paths now relative to SUTRA_ROOT, not asawa-holding.
canonical_classify_rel="marketplace/plugin/skills/human-sutra/scripts/classify.sh"
canonical_lib_rel="marketplace/plugin/lib/h-sutra-classify-and-write.sh"
native_classify_rel="marketplace/native/scripts/classify.sh"
native_lib_rel="marketplace/native/lib/h-sutra-classify-and-write.sh"
lock_rel="marketplace/native/.h-sutra-sync.lock"

# Are any of the 4 H-Sutra artifacts (or the lock) staged for commit?
staged_files=$(cd "$SUTRA_ROOT" && git diff --name-only --cached 2>/dev/null || true)
relevant_staged=0
for f in "$canonical_classify_rel" "$canonical_lib_rel" "$native_classify_rel" "$native_lib_rel" "$lock_rel"; do
  if printf '%s\n' "$staged_files" | grep -qF "$f"; then
    relevant_staged=1
    break
  fi
done

# Nothing relevant staged → no need to gate
[ "$relevant_staged" = "0" ] && exit 0

# Pre-flight — canonical files exist
for f in "$CANONICAL_CLASSIFY" "$CANONICAL_LIB"; do
  if [ ! -r "$f" ]; then
    printf '[h-sutra-drift] canonical missing: %s\n' "$f" >&2
    exit 1
  fi
done

# Pre-flight — mirror files exist
for f in "$NATIVE_CLASSIFY" "$NATIVE_LIB"; do
  if [ ! -r "$f" ]; then
    printf '[h-sutra-drift] BLOCKED — native mirror missing: %s\n' "$f" >&2
    printf '  Run: bash sutra/scripts/sync-h-sutra.sh && git add %s %s\n' "$native_classify_rel" "$native_lib_rel" >&2
    exit 2
  fi
done

# Compute current canonical sha256
sha_classify=$(shasum -a 256 "$CANONICAL_CLASSIFY" | awk '{print $1}')
sha_lib=$(shasum -a 256 "$CANONICAL_LIB" | awk '{print $1}')

# Compute current mirror sha256
mirror_classify=$(shasum -a 256 "$NATIVE_CLASSIFY" | awk '{print $1}')
mirror_lib=$(shasum -a 256 "$NATIVE_LIB" | awk '{print $1}')

# Mirror must equal canonical
if [ "$mirror_classify" != "$sha_classify" ] || [ "$mirror_lib" != "$sha_lib" ]; then
  printf '[h-sutra-drift] BLOCKED — canonical/mirror sha256 mismatch.\n' >&2
  printf '  classify.sh canonical=%s mirror=%s\n' "$sha_classify" "$mirror_classify" >&2
  printf '  lib         canonical=%s mirror=%s\n' "$sha_lib"      "$mirror_lib"      >&2
  printf '  Run: bash sutra/scripts/sync-h-sutra.sh && git add %s %s %s\n' "$native_classify_rel" "$native_lib_rel" "$lock_rel" >&2
  printf '  Then re-commit.\n' >&2
  exit 2
fi

# Lock must reflect current canonical hashes
if [ ! -r "$LOCK_FILE" ]; then
  printf '[h-sutra-drift] BLOCKED — sync lock missing: %s\n' "$LOCK_FILE" >&2
  printf '  Run: bash sutra/scripts/sync-h-sutra.sh && git add %s\n' "$lock_rel" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  printf '[h-sutra-drift] jq missing — cannot verify lock content.\n' >&2
  exit 1
fi

lock_classify=$(jq -r '.classify_sh_sha256 // empty' "$LOCK_FILE")
lock_lib=$(jq -r '.lib_sha256 // empty' "$LOCK_FILE")

if [ "$lock_classify" != "$sha_classify" ] || [ "$lock_lib" != "$sha_lib" ]; then
  printf '[h-sutra-drift] BLOCKED — lock hashes do not match canonical.\n' >&2
  printf '  classify.sh canonical=%s lock=%s\n' "$sha_classify" "$lock_classify" >&2
  printf '  lib         canonical=%s lock=%s\n' "$sha_lib"      "$lock_lib"      >&2
  printf '  Run: bash sutra/scripts/sync-h-sutra.sh && git add %s\n' "$lock_rel" >&2
  exit 2
fi

# Executable-bit check — git-index mode (round-4 P2-2 fold)
# Only check files actually tracked in git (skip if not yet committed)
for rel in "$canonical_classify_rel" "$canonical_lib_rel" "$native_classify_rel" "$native_lib_rel"; do
  mode=$(cd "$SUTRA_ROOT" && git ls-files -s -- "$rel" 2>/dev/null | awk '{print $1}' | head -1)
  if [ -n "$mode" ] && [ "$mode" != "100755" ]; then
    printf '[h-sutra-drift] BLOCKED — git index mode for %s is %s; expected 100755.\n' "$rel" "$mode" >&2
    printf '  Run: chmod +x %s && git update-index --chmod=+x %s\n' "$rel" "$rel" >&2
    exit 2
  fi
done

# All checks passed
exit 0
