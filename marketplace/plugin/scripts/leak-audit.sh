#!/bin/bash
# Sutra: brand-leak audit.
# Greps the plugin tree for the holding-company brand string. Exit 1 if any found.
# Per plugin branding direction: plugin ships as "Sutra" bare.

set -u
PLUGIN_ROOT="${1:-$(dirname "$(dirname "$(realpath "$0")")")}"

echo "Auditing $PLUGIN_ROOT for brand-leak strings..."

# Forbidden string constructed at runtime so the literal doesn't appear in
# this script or in shell history.
FORBIDDEN=$(printf 'a%s' 'sawa')
PATTERN='\b'"$FORBIDDEN"'\b'

if grep -rniE "$PATTERN" "$PLUGIN_ROOT" \
    --exclude-dir=.git \
    --exclude-dir=node_modules \
    --exclude="$(basename "$0")"; then
  echo ""
  echo "FAIL: forbidden brand string detected in plugin tree."
  echo "Remove before publishing per branding direction."
  exit 1
fi

echo "PASS: no brand leaks detected."
exit 0
