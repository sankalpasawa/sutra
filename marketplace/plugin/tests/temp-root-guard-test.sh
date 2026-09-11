#!/usr/bin/env bash
# temp-root-guard-test.sh — the registry can only be touched under a temp root in tests (Directory Program phase H,
# after the 2026-09-11 reset). Static checks over the plugin tree; no registry is read or written.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; PL="$(cd "$HERE/.." && pwd)"; FAIL=0
die(){ echo "FAIL: $1"; FAIL=1; }; ok(){ echo "ok   $1"; }
# 1 the engine refuses the default home while pytest runs
grep -q '_refuse_default_home_under_test' "$PL/lib/placement_engine.py" && ok "engine refuses default home under pytest" || die "placement_engine.py lacks _refuse_default_home_under_test"
# 2 the pre-test snapshot hook is registered
grep -q 'pytest-isolation-guard.sh' "$PL/hooks/hooks.json" && ok "pytest-isolation-guard registered" || die "pytest-isolation-guard.sh not in hooks.json"
# 3 every sutra-ui test that touches the registry sets a temp SUTRA_NATIVE_HOME
BAD=""
for f in "$PL"/sutra-ui/test_*.py; do
  grep -qE 'placement_engine|org_api|modules_api|E\.DOMAINS|^import app|^from app import' "$f" || continue
  grep -q 'SUTRA_NATIVE_HOME' "$f" || BAD="$BAD $(basename "$f")"
done
if [ -f "$PL/sutra-ui/conftest.py" ] && grep -Eq 'environ\[.SUTRA_NATIVE_HOME.\] *= *' "$PL/sutra-ui/conftest.py" && grep -q 'mkdtemp' "$PL/sutra-ui/conftest.py"; then
  ok "conftest.py assigns a mkdtemp SUTRA_NATIVE_HOME before collection (covers:$BAD )"
else
  [ -z "$BAD" ] && ok "every registry-touching sutra-ui test sets SUTRA_NATIVE_HOME" || die "no conftest temp home and tests touching the registry without SUTRA_NATIVE_HOME:$BAD"
fi
# 4 the paper sync dry run refuses the real registry (only where the holding script exists)
SYNC="$PL/../../../holding/directory/sync-dry-run.py"
if [ -f "$SYNC" ]; then
  out=$(SUTRA_NATIVE_HOME="$HOME/.sutra-native/user-kit" python3 "$SYNC" --apply-to-temp 2>/dev/null | tail -1); rc=$?
  printf '%s' "$out" | grep -q REFUSED && ok "sync-dry-run refuses the real registry" || die "sync-dry-run did not refuse the real registry: $out"
else echo "skip sync-dry-run refusal (holding script not present in this checkout)"; fi
echo "temp-root-guard-test: fail=$FAIL"; exit $FAIL
