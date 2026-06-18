#!/usr/bin/env bash
# Launch the Sutra UI dashboard on localhost only.
# Uses the local venv if present (.venv), else the system python3.
set -euo pipefail
cd "$(dirname "$0")"

PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

HOST="${SUTRA_UI_HOST:-127.0.0.1}"
PORT="${SUTRA_UI_PORT:-7000}"

# Localhost-only guard: refuse non-loopback bind unless explicitly forced (logs contain prompts).
if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ] && [ "${SUTRA_UI_ALLOW_EXTERNAL:-0}" != "1" ]; then
  echo "refusing to bind $HOST — set SUTRA_UI_ALLOW_EXTERNAL=1 to override (logs contain prompt text)" >&2
  exit 2
fi

exec "$PY" -m uvicorn app:app --host "$HOST" --port "$PORT"
