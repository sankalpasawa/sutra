#!/bin/bash
# Unit test: validate the 4 release-critical plugin manifests parse as JSON.
#
# Regression test for the v2.18.1 incident — the description string in
# core/.claude-plugin/plugin.json contained unescaped double-quotes inside the
# value, causing /reload-plugins to fail with "Expected }" on every T4 fleet
# client running /plugin update. The defect shipped because plugin manifests
# weren't part of the test gate. v2.18.2 closes that gap.
#
# Codex consult 2026-05-03 (CHANGES-REQUIRED P3): "Gate the release-critical
# manifests, not every JSON under plugin/. Use jq -e ."
#
# Manifests covered (4):
#   1. sutra/marketplace/plugin/.claude-plugin/plugin.json     (core plugin)
#   2. sutra/marketplace/native/.claude-plugin/plugin.json     (native plugin)
#   3. sutra/.claude-plugin/marketplace.json                   (catalog)
#   4. sutra/marketplace/plugin/hooks/hooks.json               (hook manifest)
#
# Adjacent gate (already shipped v2.10.0): test-validate-hook-paths.sh checks
# that every hook path REFERENCED in hooks.json exists + is git-tracked. This
# test focuses on JSON validity itself (the bug class v2.10.0's gate didn't
# catch).
set -u

PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
SUTRA_ROOT="$(dirname "$(dirname "$PLUGIN_ROOT")")"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Sanity: jq present (the gate itself depends on it; no jq = silent pass = bad).
if ! command -v jq >/dev/null 2>&1; then
  echo "  X   jq not installed — install jq to run this gate (brew/apt/dnf)"
  exit 2
fi

MANIFESTS=(
  "$PLUGIN_ROOT/.claude-plugin/plugin.json"
  "$SUTRA_ROOT/marketplace/native/.claude-plugin/plugin.json"
  "$SUTRA_ROOT/.claude-plugin/marketplace.json"
  "$PLUGIN_ROOT/hooks/hooks.json"
)

# 1) Each manifest exists.
for m in "${MANIFESTS[@]}"; do
  if [ -f "$m" ]; then
    _ok "exists: ${m#$SUTRA_ROOT/}"
  else
    _no "missing: ${m#$SUTRA_ROOT/}"
  fi
done

# 2) Each manifest parses as JSON.
for m in "${MANIFESTS[@]}"; do
  [ -f "$m" ] || continue
  err="$(jq -e . "$m" 2>&1 >/dev/null)"
  if [ -z "$err" ]; then
    _ok "parses: ${m#$SUTRA_ROOT/}"
  else
    _no "INVALID JSON: ${m#$SUTRA_ROOT/} — $err"
  fi
done

# 3) Synthetic scenario: a manifest with the v2.18.1 bug shape (unescaped
#    quote inside a string value) MUST fail jq -e. If this passes, our gate
#    isn't actually catching the bug class.
TMPDIR_BAD=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BAD"' EXIT
cat > "$TMPDIR_BAD/bad.json" <<'EOF'
{"name": "core", "description": "broken because "this" is not escaped"}
EOF
if jq -e . "$TMPDIR_BAD/bad.json" >/dev/null 2>&1; then
  _no "synthetic v2.18.1-shape bad JSON unexpectedly parsed — gate is broken"
else
  _ok "synthetic v2.18.1-shape bad JSON correctly fails jq -e"
fi

# 4) Catalog version sync — the v2.18.1 incident also exposed a drifted
#    catalog (catalog said 2.18.0, source said 2.18.1). Assert catalog core
#    entry matches source plugin.json version.
catalog_core_v=$(jq -r '.plugins[] | select(.name=="core") | .version' "$SUTRA_ROOT/.claude-plugin/marketplace.json" 2>/dev/null || echo "?")
source_core_v=$(jq -r '.version' "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo "?")
if [ "$catalog_core_v" = "$source_core_v" ] && [ "$catalog_core_v" != "?" ]; then
  _ok "core version sync: catalog=$catalog_core_v == source=$source_core_v"
else
  _no "core version DRIFT: catalog=$catalog_core_v != source=$source_core_v"
fi

# 5) Native version sync (same check).
catalog_native_v=$(jq -r '.plugins[] | select(.name=="native") | .version' "$SUTRA_ROOT/.claude-plugin/marketplace.json" 2>/dev/null || echo "?")
source_native_v=$(jq -r '.version' "$SUTRA_ROOT/marketplace/native/.claude-plugin/plugin.json" 2>/dev/null || echo "?")
if [ "$catalog_native_v" = "$source_native_v" ] && [ "$catalog_native_v" != "?" ]; then
  _ok "native version sync: catalog=$catalog_native_v == source=$source_native_v"
else
  _no "native version DRIFT: catalog=$catalog_native_v != source=$source_native_v"
fi

echo ""
echo "  $PASS passed, $FAIL failed"
exit "$FAIL"
