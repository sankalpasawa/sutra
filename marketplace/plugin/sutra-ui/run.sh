#!/usr/bin/env bash
# Launch the Sutra UI dashboard on localhost only.
# Uses the local venv if present (.venv), else a Python 3.11-3.12 found on PATH.
set -euo pipefail
cd "$(dirname "$0")"

# NOT a bare `python3`: on a stock Mac that is Xcode's 3.9, which cannot import
# the pinned deps (cryptography needs 3.11+, numpy 2.0.2 has no 3.13 wheel).
# Same supported range and the same order as install.sh's find_python; keep
# them in step -- test_python_versions.py checks the two agree.
in_range() { "$1" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,12) else 1)' 2>/dev/null; }
PY=""
# The checkout's .venv is range-checked too: one created before 2026-09-13 was
# built on the stock 3.9 and cannot import the current pins, so using it blindly
# just moves the failure from `pip install` to the first import.
if [ -x ".venv/bin/python" ] && in_range ".venv/bin/python"; then
  PY=".venv/bin/python"
else
  [ -x ".venv/bin/python" ] && echo "run.sh: ignoring .venv ($(.venv/bin/python -V 2>&1)); needs 3.11-3.12 -- rebuild it with: python3.12 -m venv --clear .venv" >&2
  for c in ${SUTRA_PYTHON:+"$SUTRA_PYTHON"} python3.12 /opt/homebrew/bin/python3.12 \
           python3.11 /opt/homebrew/bin/python3.11 python3; do
    c="$(command -v "$c" 2>/dev/null || true)"
    if [ -n "$c" ] && in_range "$c"; then
      PY="$c"; break
    fi
  done
fi
[ -n "$PY" ] || { echo "run.sh: no Python 3.11-3.12 found (brew install python@3.12, or set SUTRA_PYTHON)" >&2; exit 2; }

HOST="${SUTRA_UI_HOST:-127.0.0.1}"
PORT="${SUTRA_UI_PORT:-7000}"

# Localhost-only guard: refuse non-loopback bind unless explicitly forced (logs contain prompts).
if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ] && [ "${SUTRA_UI_ALLOW_EXTERNAL:-0}" != "1" ]; then
  echo "refusing to bind $HOST — set SUTRA_UI_ALLOW_EXTERNAL=1 to override (logs contain prompt text)" >&2
  exit 2
fi

exec "$PY" -m uvicorn app:app --host "$HOST" --port "$PORT"
