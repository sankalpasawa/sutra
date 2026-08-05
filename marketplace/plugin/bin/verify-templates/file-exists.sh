#!/usr/bin/env bash
# verify template: file-exists <path> [<path>...] — exit 0 iff every path exists and is non-empty
set -euo pipefail
[ $# -ge 1 ] || { echo "file-exists: needs at least one path" >&2; exit 2; }
for p in "$@"; do
  [ -s "$p" ] || { echo "file-exists: missing or empty: $p" >&2; exit 1; }
done
exit 0
