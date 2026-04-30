#!/usr/bin/env bash
# Sutra Connectors — bump-version.sh (M1.12)
#
# Atomic version bump across the four canonical version surfaces. On any
# failure mid-way, restores from .bak files via trap.
#
# Surfaces:
#   1. plugin/.claude-plugin/plugin.json            (canonical "version" field)
#   2. plugin/README.md                             (banner: **vX.Y.Z**)
#   3. plugin/connectors/package.json               ("version" field)
#   4. plugin/connectors/QUICKSTART.md              (test-count banner — version line)
#
# Usage:
#   bash connectors/scripts/bump-version.sh 2.10.0
#
# Spec: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.12
set -euo pipefail

NEW_VERSION="${1:-}"
if [ -z "$NEW_VERSION" ]; then
  echo "usage: bump-version.sh <new-version>" >&2
  exit 1
fi
if ! echo "$NEW_VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "error: version must be semver X.Y.Z (got: $NEW_VERSION)" >&2
  exit 1
fi

# Resolve plugin root from this script location (connectors/scripts/ -> plugin/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="$(cd "$CONN_DIR/.." && pwd)"

PLUGIN_JSON="$PLUGIN_DIR/.claude-plugin/plugin.json"
PLUGIN_README="$PLUGIN_DIR/README.md"
CONN_PKG="$CONN_DIR/package.json"
CONN_QS="$CONN_DIR/QUICKSTART.md"

for f in "$PLUGIN_JSON" "$PLUGIN_README" "$CONN_PKG" "$CONN_QS"; do
  if [ ! -f "$f" ]; then
    echo "error: surface missing: $f" >&2
    exit 1
  fi
done

BACKUPS=()
trap 'restore_on_error' ERR

restore_on_error() {
  echo "bump-version: error encountered, restoring from .bak" >&2
  for b in "${BACKUPS[@]}"; do
    if [ -f "$b" ]; then
      orig="${b%.bak}"
      mv -f "$b" "$orig"
    fi
  done
}

backup() {
  cp "$1" "$1.bak"
  BACKUPS+=("$1.bak")
}

# 1. plugin.json — first "version": "<x>" in JSON
backup "$PLUGIN_JSON"
sed -i.tmp -E "s/(\"version\"[[:space:]]*:[[:space:]]*\")[0-9]+\.[0-9]+\.[0-9]+(\")/\1$NEW_VERSION\2/" "$PLUGIN_JSON"
rm -f "$PLUGIN_JSON.tmp"

# 2. README banner — **vX.Y.Z** on a line near the top
backup "$PLUGIN_README"
sed -i.tmp -E "s/\*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*/\*\*v$NEW_VERSION\*\*/" "$PLUGIN_README"
rm -f "$PLUGIN_README.tmp"

# 3. connectors/package.json — first "version": "<x>"
backup "$CONN_PKG"
sed -i.tmp -E "s/(\"version\"[[:space:]]*:[[:space:]]*\")[0-9]+\.[0-9]+\.[0-9]+(\")/\1$NEW_VERSION\2/" "$CONN_PKG"
rm -f "$CONN_PKG.tmp"

# 4. QUICKSTART.md — DEFERRED to M2 polish (current banner is "v0 shipped",
#    not a semver; doing a sed substitution here is a silent no-op and
#    leaves drift behind. Per spec §M2.5, QUICKSTART rewrite is M2 work.
#    Including it in M1 bump would be cosmetic noise that hides real drift.

# Success — remove .bak files
for b in "${BACKUPS[@]}"; do
  rm -f "$b"
done

echo "bump-version: $NEW_VERSION applied across 3 M1 surfaces (QUICKSTART deferred to M2)"
echo "  $PLUGIN_JSON"
echo "  $PLUGIN_README"
echo "  $CONN_PKG"
