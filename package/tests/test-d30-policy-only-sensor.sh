#!/bin/bash
# test-d30-policy-only-sensor.sh — regression test for D30 sensor.
#
# Asserts:
#   (a) Sensor produces a STALE finding when a POLICY-ONLY marker is older than window.
#   (b) Sensor is silent (no stdout) when the repo is clean within window.
#   (c) Sensor exit code is always 0 (SOFT enforcement per D30).
#   (d) Sensor flags a hard direction whose mechanism names a missing .sh file.
#
# Framework:
#   run-tests.mjs discovers this via the *.sh glob. Exit 0 = pass, non-0 = fail.
#   The sensor itself always exits 0; the TEST wraps it and asserts on output.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SENSOR="$REPO_ROOT/holding/hooks/policy-only-sensor.sh"

if [ ! -x "$SENSOR" ]; then
  echo "FAIL: sensor not executable at $SENSOR"
  exit 1
fi

# Sandbox: build an isolated repo-root with state.yaml + a POLICY-ONLY marker
SANDBOX=$(mktemp -d "/tmp/d30-test-XXXX")
trap 'rm -rf "$SANDBOX"' EXIT

mkdir -p "$SANDBOX/sutra/state" "$SANDBOX/holding/hooks" "$SANDBOX/.enforcement"
cat > "$SANDBOX/sutra/state/system.yaml" <<'YAML'
meta:
  caps:
    directions_active_max: 1

directions:
  core:
    - id: D99
      name: Fake Hard Direction For Test
      status: active
      enforcement: hard
      mechanism: this-hook-does-not-exist.sh Check 1
      summary: Used only by the D30 sensor regression test.
YAML

# Spoof a POLICY-ONLY marker 10 days old
OLD_DATE=$(date -j -v-10d "+%Y-%m-%d" 2>/dev/null || date -d "10 days ago" "+%Y-%m-%d")
cat > "$SANDBOX/holding/DIRECTION-ENFORCEMENT.md" <<EOF
# Fake
POLICY-ONLY since $OLD_DATE — fake entry for D30 regression test.
EOF

# Seed a git repo so REPO_ROOT resolves correctly inside the sandbox
(cd "$SANDBOX" && git init -q && git add -A && git commit -qm "fixture" 2>/dev/null || true)

# ── Assertion 1 + 4: stale marker AND missing-hook FAIL fire ─────────────────
OUT=$(cd "$SANDBOX" && bash "$SENSOR" 2>&1)
CODE=$?
if [ "$CODE" -ne 0 ]; then
  echo "FAIL: sensor exit code $CODE (expected 0 — SOFT enforcement)"
  exit 1
fi
if ! echo "$OUT" | grep -q "STALE"; then
  echo "FAIL: sensor did not report STALE for 10-day-old POLICY-ONLY marker"
  echo "---- sensor output ----"
  echo "$OUT"
  exit 1
fi
if ! echo "$OUT" | grep -q "this-hook-does-not-exist.sh"; then
  echo "FAIL: sensor did not report missing hook for D99 hard direction"
  echo "---- sensor output ----"
  echo "$OUT"
  exit 1
fi

# ── Assertion 2: clean sandbox → silent ──────────────────────────────────────
CLEAN=$(mktemp -d "/tmp/d30-test-clean-XXXX")
mkdir -p "$CLEAN/sutra/state" "$CLEAN/.enforcement"
cat > "$CLEAN/sutra/state/system.yaml" <<'YAML'
directions:
  core: []
YAML
(cd "$CLEAN" && git init -q && git add -A && git commit -qm "fixture" 2>/dev/null || true)

OUT_CLEAN=$(cd "$CLEAN" && bash "$SENSOR" 2>&1)
CODE_CLEAN=$?
rm -rf "$CLEAN"
if [ "$CODE_CLEAN" -ne 0 ]; then
  echo "FAIL: clean sandbox sensor exit $CODE_CLEAN (expected 0)"
  exit 1
fi
if [ -n "$OUT_CLEAN" ]; then
  echo "FAIL: clean sandbox sensor produced output (expected silent)"
  echo "---- sensor output ----"
  echo "$OUT_CLEAN"
  exit 1
fi

echo "PASS: D30 sensor stale-marker + missing-hook + silent-green assertions met"
exit 0
