#!/usr/bin/env bash
# verify template: file-exists <path> [<path>...] — exit 0 iff every path exists and is non-empty
set -euo pipefail
[ $# -ge 1 ] || { echo "file-exists: needs at least one path" >&2; exit 2; }
EVIDENCE=""
for p in "$@"; do
  [ -s "$p" ] || { echo "file-exists: missing or empty: $p" >&2; exit 1; }
  # evidence on STDOUT (stderr + exit codes unchanged): bytes, lines, age
  bytes=$(wc -c < "$p" | tr -d ' ')
  lines=$(wc -l < "$p" | tr -d ' ')
  mt=$(stat -f %m "$p" 2>/dev/null || stat -c %Y "$p" 2>/dev/null || echo 0)
  age=$(( $(date +%s) - mt ))
  EVIDENCE="${EVIDENCE:+$EVIDENCE; }present: $p (${bytes}B, ${lines} lines, ${age}s old)"
done
echo "$EVIDENCE"
exit 0
