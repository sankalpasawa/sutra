#!/bin/bash
# The app's server from source on a record of its own: engine runtime on, the motor on, the real model. For walks, and
# for the founder's own look in a browser.
#   usage: qa/walks/devserver.sh [record-dir] [port]
#   record-dir  where this walk's registry, department records, proposals and chats live (default: $TMPDIR/sutra-walk);
#               a record kept between runs keeps its departments and their boards
#   port        default 8341
# Nothing here touches the operator's live records (~/.sutra-ui): every home is under record-dir. The server runs in
# the foreground; devserver-detach.sh starts it as its own process, devserver-stop.sh stops it.
set -u
UI="$(cd "$(dirname "$0")/../.." && pwd)"
T="${1:-${TMPDIR:-/tmp}/sutra-walk}"
PORT="${2:-8341}"
mkdir -p "$T/registry" "$T/native" "$T/proposals" "$T/chats"
cd "$UI" || exit 1
export SUTRA_NATIVE_HOME="$T/registry" SUTRA_NATIVE_DEPT_HOME="$T/native" SUTRA_UI_PROPOSALS="$T/proposals" SUTRA_UI_CHATS="$T/chats"
export SUTRA_MOTOR=1 SUTRA_ENGINE_RUNTIME=2
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port "$PORT" --log-level warning
