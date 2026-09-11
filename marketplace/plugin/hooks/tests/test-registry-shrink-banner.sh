#!/usr/bin/env bash
# Regression test for marketplace/plugin/hooks/registry-shrink-banner.sh (RCA 2026-09-11).
# PROTO-000: mechanism ships with test.  BUILD-LAYER: L0.
# Usage: bash marketplace/plugin/hooks/tests/test-registry-shrink-banner.sh
# Isolation: mktemp HOME (baseline file, backups, kill-switch), CLAUDE_PROJECT_DIR (ledger),
# SUTRA_NATIVE_HOME (a fake registry). The real registry is never read.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/registry-shrink-banner.sh"
FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }
T=$(mktemp -d -t shrink-banner-test.XXXXXX)
cleanup() { [ -n "${T:-}" ] && [ -d "$T" ] && rm -rf "$T"; }
trap cleanup EXIT
mkdir -p "$T/home" "$T/repo/.enforcement" "$T/kit/domains"
LEDGER="$T/repo/.enforcement/registry-shrink.jsonl"
seed() { local n="$1"; rm -f "$T/kit/domains"/dref-*.json; for i in $(seq 1 "$n"); do printf '{"ref":"dref-%s"}\n' "$i" > "$T/kit/domains/dref-$i.json"; done; }
run() { HOME="$T/home" CLAUDE_PROJECT_DIR="$T/repo" SUTRA_NATIVE_HOME="$T/kit" bash "$HOOK" "$@"; }
# the baseline file is keyed by the registry's realpath; resolve it the way the hook does
BASE="$T/home/.sutra-native/registry-baseline-$(printf '%s' "$(cd "$T/kit" && pwd -P)" | shasum | cut -c1-12).json"

echo "case 1: first run writes the baseline"
seed 68; out=$(run); rc=$?
[ "$rc" = 0 ] && [ "$(jq -r .count "$BASE")" = 68 ] && printf '%s' "$out" | grep -q "departments on disk: 68" && pass "baseline 68" || fail "rc=$rc base=$(cat "$BASE" 2>/dev/null) out=$out"

echo "case 2: growth raises the baseline silently"
seed 80; out=$(run); [ "$(jq -r .count "$BASE")" = 80 ] && pass "baseline 80" || fail "baseline not raised: $(cat "$BASE")"

echo "case 3: a small drop within tolerance does not alarm"
seed 76; out=$(run); rc=$?
[ "$rc" = 0 ] && ! printf '%s' "$out" | grep -q "REGISTRY SHRANK" && [ "$(jq -r .count "$BASE")" = 80 ] && pass "quiet; baseline kept" || fail "false alarm: $out"

echo "case 4: a wipe prints the box, appends the ledger, and --check exits 1"
seed 2; mkdir -p "$T/home/.sutra-native/backups"; touch "$T/home/.sutra-native/backups/user-kit-20260911T114000Z.tgz"
out=$(run); rc=$?
printf '%s' "$out" | grep -q "REGISTRY SHRANK" && printf '%s' "$out" | grep -q "user-kit-20260911T114000Z.tgz" && [ "$rc" = 0 ] && pass "banner names the backup, exit 0 in banner mode" || fail "banner: rc=$rc out=$out"
run --check >/dev/null; rc=$?
[ "$rc" = 1 ] && grep -q '"baseline":80,"live":2' "$LEDGER" && pass "--check exit 1 + ledger row" || fail "--check rc=$rc ledger=$(tail -1 "$LEDGER" 2>/dev/null)"

echo "case 5: --rebase accepts the new count"
out=$(run --rebase); [ "$(jq -r .count "$BASE")" = 2 ] && run --check >/dev/null && pass "rebased to 2, check clean" || fail "rebase failed: $out"

echo "case 5b: another registry home never reuses this baseline"
mkdir -p "$T/kit2/domains"; printf '{"ref":"dref-x"}\n' > "$T/kit2/domains/dref-x.json"
out=$(HOME="$T/home" CLAUDE_PROJECT_DIR="$T/repo" SUTRA_NATIVE_HOME="$T/kit2" bash "$HOOK" --check); rc=$?
[ "$rc" = 0 ] && [ "$(jq -r .count "$BASE")" = 2 ] && pass "second home gets its own baseline; first untouched" || fail "cross-home reuse: rc=$rc base=$(cat "$BASE")"

echo "case 6: kill-switch"
touch "$T/home/.registry-shrink-banner-disabled"; seed 0
out=$(run); rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && pass "disabled" || fail "kill-switch ignored: $out"

[ "$FAIL" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
