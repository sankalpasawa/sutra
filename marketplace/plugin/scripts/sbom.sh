#!/bin/bash
# sutra/marketplace/plugin/scripts/sbom.sh
# Sutra v2.1 — Software Bill of Materials generator.
# Emits SHA256 hash per shipped file in the plugin tree.
# SECURITY charter primitive #13 — supply-chain integrity.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
OUT="${1:-$SUTRA_HOME/sbom.txt}"

VERSION="unknown"
if command -v jq >/dev/null 2>&1 && [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
  VERSION=$(jq -r '.version' "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo unknown)
fi

mkdir -p "$(dirname "$OUT")" 2>/dev/null

# Hash function fallback
_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    echo "NO-HASHER"
  fi
}

{
  echo "# Sutra Plugin SBOM"
  echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# Version:   $VERSION"
  echo "# Root:      $PLUGIN_ROOT"
  echo "#"
  echo "# Verify integrity: sutra sbom --verify"
  echo "# Format: <sha256>  <relative-path>"
  echo ""
  # Include shipped files only; skip .claude/, .analytics/, tests/, .gitignore
  cd "$PLUGIN_ROOT" && find . \
    -type f \
    -not -path './.claude/*' \
    -not -path './.analytics/*' \
    -not -path './.enforcement/*' \
    -not -name '.gitignore' \
    -not -path './tests/*' \
    | sort | while IFS= read -r f; do
    printf '%s  %s\n' "$(_hash "$f")" "${f#./}"
  done
} > "$OUT"

echo "SBOM written to $OUT"
echo "  entries: $(grep -cv '^#\|^$' "$OUT")"
echo "  version: $VERSION"
echo ""
echo "To verify integrity on a future install:"
echo "  sutra sbom /tmp/current.sbom"
echo "  diff $OUT /tmp/current.sbom   # empty = no tampering"

exit 0
