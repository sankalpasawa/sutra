#!/usr/bin/env bash
# Sutra Connectors — check-version-drift.sh (M1.12)
#
# Reads the canonical version from plugin/.claude-plugin/plugin.json and
# compares it to 3 active surfaces (4th deferred to M2). Exits 1 on drift; 0 if synced.
#
# Surfaces compared:
#   1. plugin/.claude-plugin/plugin.json   (CANONICAL)
#   2. plugin/README.md                    (banner: **vX.Y.Z**)
#   3. plugin/connectors/package.json      ("version" field)
#   4. (deferred to M2 step 5: plugin/connectors/QUICKSTART.md banner)
#
# Spec: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.12
set -euo pipefail

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
    exit 2
  fi
done

# Canonical: first "version": "<x>" in plugin.json.
canon=$(grep -E '"version"[[:space:]]*:' "$PLUGIN_JSON" \
        | head -1 \
        | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')
if [ -z "$canon" ]; then
  echo "error: could not extract canonical version from $PLUGIN_JSON" >&2
  exit 2
fi

drift=0

# README banner — tolerate missing match (set -e + pipefail would otherwise abort)
readme_v=$(grep -Eo '\*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*' "$PLUGIN_README" 2>/dev/null \
           | head -1 \
           | sed -E 's/\*\*v([0-9]+\.[0-9]+\.[0-9]+)\*\*/\1/' || true)
if [ "$readme_v" != "$canon" ]; then
  echo "DRIFT: README banner=$readme_v canonical=$canon ($PLUGIN_README)"
  drift=1
fi

# connectors/package.json
pkg_v=$(grep -E '"version"[[:space:]]*:' "$CONN_PKG" 2>/dev/null \
        | head -1 \
        | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/' || true)
if [ "$pkg_v" != "$canon" ]; then
  echo "DRIFT: connectors/package.json=$pkg_v canonical=$canon ($CONN_PKG)"
  drift=1
fi

# QUICKSTART.md — DEFERRED to M2 polish (per spec §M2.5).
# Current banner is "v0 shipped" prose, not a semver; including it here
# would always-fail and obscure real drift. M2 work converts QUICKSTART
# to a versioned banner and re-adds it to this drift check.

if [ "$drift" -eq 1 ]; then
  echo "version-drift: failed (canonical=$canon)"
  exit 1
fi

echo "version-drift: OK (canonical=$canon, 3 M1 surfaces synced; QUICKSTART deferred to M2)"
exit 0
