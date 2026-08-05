#!/usr/bin/env bash
# verify template: named-test <script-path> [args...] — runs a repo test script; exit code passes through.
# Hash-pinning is enforced by sutra-atom close (sha256 recorded at open, re-checked before run).
set -euo pipefail
[ $# -ge 1 ] || { echo "named-test: needs <script-path>" >&2; exit 2; }
script="$1"; shift
[ -f "$script" ] || { echo "named-test: no such script: $script" >&2; exit 1; }
bash "$script" "$@"
