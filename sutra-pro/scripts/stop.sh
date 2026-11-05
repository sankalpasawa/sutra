#!/bin/sh
# Stop the Sutra Pro server of this checkout's data folder (GAP-OPS-1): SIGTERM, then wait up to 20 s for it to end. It never kills.
# Extra arguments go to `sutra-pro stop` (for example --data-dir D or --json).
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
PY=""
if [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
else
  prefix=$(git -C "$HERE" rev-parse --show-prefix 2>/dev/null || true)
  common=$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  if [ -n "$common" ] && [ -x "$(dirname "$common")/${prefix%/}/.venv/bin/python" ]; then
    PY="$(dirname "$common")/${prefix%/}/.venv/bin/python"
  fi
fi
if [ -z "$PY" ]; then
  echo "stop.sh: there is no .venv; nothing of this checkout can be running. (Run scripts/run.sh first.)" >&2
  exit 1
fi
PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec "$PY" -m sutra_app stop "$@"
