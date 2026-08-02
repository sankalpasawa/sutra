#!/usr/bin/env bash
# sutra/scripts/sync-h-sutra.sh
#
# Vendor canonical H-Sutra producer artifacts into native@sutra plugin.
#
# Per D49 (Native v1.4 standalone) + codex round-1..5 design review:
#   - shared sourceable lib pattern, function-only (round-2 a-ii fold)
#   - vendored copies (no symlink, no submodule) — standalone install needs
#     self-contained bytes (round-1 P1)
#   - content-addressed lock; rewrite ONLY when hashes differ (round-3 P2-1)
#   - DROPPED sutra-defaults.minimal.json — no consumer at classify.sh:21
#     (round-2 P2 fold)
#
# Idempotent on re-run. Safe to invoke from CI or pre-commit.

set -euo pipefail

# Resolve sutra repo root from script location (works whether sutra is a
# standalone clone or an asawa-holding submodule). Codex review fold P2-A:
# previous implementation used `git rev-parse --show-toplevel` which
# resolves to asawa-holding (outer) under submodule layout — leading to
# `<repo>/sutra/sutra/...` path doubling. Script-relative path is invariant.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SUTRA_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

CANONICAL_CLASSIFY="$SUTRA_ROOT/marketplace/plugin/skills/human-sutra/scripts/classify.sh"
CANONICAL_LIB="$SUTRA_ROOT/marketplace/plugin/lib/h-sutra-classify-and-write.sh"
NATIVE_CLASSIFY="$SUTRA_ROOT/marketplace/native/scripts/classify.sh"
NATIVE_LIB="$SUTRA_ROOT/marketplace/native/lib/h-sutra-classify-and-write.sh"
LOCK_FILE="$SUTRA_ROOT/marketplace/native/.h-sutra-sync.lock"

# Pre-flight: canonical artifacts exist + executable
for f in "$CANONICAL_CLASSIFY" "$CANONICAL_LIB"; do
  if [ ! -r "$f" ]; then
    printf 'sync-h-sutra: canonical missing: %s\n' "$f" >&2
    exit 1
  fi
done

# sha256 of canonicals
sha_classify=$(shasum -a 256 "$CANONICAL_CLASSIFY" | awk '{print $1}')
sha_lib=$(shasum -a 256 "$CANONICAL_LIB" | awk '{print $1}')

# Read existing lock (if any). Skip rewrite if hashes match (round-3 P2-1).
existing_classify=""
existing_lib=""
if [ -r "$LOCK_FILE" ]; then
  existing_classify=$(jq -r '.classify_sh_sha256 // empty' "$LOCK_FILE" 2>/dev/null || true)
  existing_lib=$(jq -r '.lib_sha256 // empty' "$LOCK_FILE" 2>/dev/null || true)
fi

# Always copy artifacts (idempotent) — cp is cheap; lock rewrite is the
# operation we gate on hash equality.
mkdir -p "$(dirname "$NATIVE_CLASSIFY")" "$(dirname "$NATIVE_LIB")"
cp -p "$CANONICAL_CLASSIFY" "$NATIVE_CLASSIFY"
cp -p "$CANONICAL_LIB" "$NATIVE_LIB"

# Verify mirrored hashes match canonical (sanity)
mirror_classify=$(shasum -a 256 "$NATIVE_CLASSIFY" | awk '{print $1}')
mirror_lib=$(shasum -a 256 "$NATIVE_LIB" | awk '{print $1}')
if [ "$mirror_classify" != "$sha_classify" ] || [ "$mirror_lib" != "$sha_lib" ]; then
  printf 'sync-h-sutra: cp produced hash mismatch (FS issue?). Bailing.\n' >&2
  exit 1
fi

# Rewrite lock ONLY if hashes differ from existing
if [ "$existing_classify" = "$sha_classify" ] && [ "$existing_lib" = "$sha_lib" ]; then
  printf 'sync-h-sutra: lock unchanged (hashes match) — no-op.\n'
else
  printf '{"classify_sh_sha256":"%s","lib_sha256":"%s"}\n' "$sha_classify" "$sha_lib" > "$LOCK_FILE"
  printf 'sync-h-sutra: lock updated.\n'
fi

# Echo summary
printf '  classify.sh sha256: %s\n' "$sha_classify"
printf '  lib sha256:         %s\n' "$sha_lib"
printf '  Mirror at:          %s\n' "$NATIVE_CLASSIFY"
printf '                      %s\n' "$NATIVE_LIB"
printf '  Lock:               %s\n' "$LOCK_FILE"

exit 0
