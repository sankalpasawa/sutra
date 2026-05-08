#!/usr/bin/env bash
# tests/e2e/runner.sh — Verifier Engine v1 E2E driver.
#
# Usage:
#   bash sutra/marketplace/native/tests/e2e/runner.sh pets-site-happy
#   bash sutra/marketplace/native/tests/e2e/runner.sh pets-site-broken
#
# SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7

set -euo pipefail

VARIANT="${1:-}"
if [ -z "$VARIANT" ]; then
  echo "usage: $0 <variant>" >&2
  echo "available variants: pets-site-happy, pets-site-broken" >&2
  exit 2
fi

NATIVE_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_FILE="$NATIVE_ROOT/tests/e2e/verifier-engine-${VARIANT}.test.ts"
if [ ! -f "$TEST_FILE" ]; then
  echo "test file not found: $TEST_FILE" >&2
  exit 2
fi

cd "$NATIVE_ROOT"
echo "=== Verifier Engine v1 E2E — variant: $VARIANT ==="
exec npx vitest run "tests/e2e/verifier-engine-${VARIANT}.test.ts" --reporter=verbose
