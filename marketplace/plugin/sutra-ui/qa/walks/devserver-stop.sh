#!/bin/bash
# Stop the source server on a port, and only it: the pid must be the LISTENER and its command must be this app's uvicorn.
#   usage: qa/walks/devserver-stop.sh [port]      (default 8341)
# Prints the holder's command before touching it; a listener that is not this uvicorn is left alone and named.
set -u
PORT="${1:-8341}"
PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | sort -u)"
[ -z "$PIDS" ] && { echo "nothing listens on $PORT"; exit 0; }
for P in $PIDS; do
  CMD="$(ps -o command= -p "$P")"
  case "$CMD" in
    *uvicorn*app:app*--port\ "$PORT"*) echo "stopping $P: $CMD"; kill "$P" ;;
    *) echo "NOT MINE, left alone: $P: $CMD" ;;
  esac
done
for i in $(seq 1 10); do
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1 || { echo "$PORT is free"; exit 0; }
  /bin/sleep 0.5
done
echo "$PORT still held"; exit 1
