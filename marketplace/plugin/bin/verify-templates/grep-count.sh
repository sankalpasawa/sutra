#!/usr/bin/env bash
# verify template: grep-count <pattern> <file> <min-count> — exit 0 iff pattern occurs >= min times
set -euo pipefail
[ $# -eq 3 ] || { echo "grep-count: needs <pattern> <file> <min-count>" >&2; exit 2; }
pat="$1"; file="$2"; min="$3"
case "$min" in ''|*[!0-9]*) echo "grep-count: min must be a positive integer" >&2; exit 2 ;; esac
[ "$min" -ge 1 ] || { echo "grep-count: min=0 is vacuous — min must be >= 1" >&2; exit 2; }  # W1-T14 (d5)
[ -f "$file" ] || { echo "grep-count: no such file: $file" >&2; exit 1; }
n=$(grep -cE "$pat" "$file" || true)
[ "$n" -ge "$min" ] || { echo "grep-count: found $n < $min of /$pat/ in $file" >&2; exit 1; }
# evidence on STDOUT (fail/refusal messages stay on stderr; exit codes unchanged)
echo "found $n of >=$min required"
exit 0
