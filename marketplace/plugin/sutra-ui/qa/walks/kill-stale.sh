#!/bin/bash
# Several uvicorns of this app can sit on one port: only the listener serves, but one that lost the port can still
# hold the record's motor lock and tick with OLD code (found 2026-09-28: a front post died unseen). Stop every
# non-listener that is exactly this app's uvicorn on the port, then watch the listener take the motor.
#   usage: qa/walks/kill-stale.sh [record-dir] [port]     (defaults as devserver.sh)
set -u
T="${1:-${TMPDIR:-/tmp}/sutra-walk}"
PORT="${2:-8341}"
M="$T/native/motor.json"
L=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
echo "listener: ${L:-none}"
for P in $(pgrep -f "uvicorn app:app --host 127.0.0.1 --port $PORT"); do
  [ "$P" = "$L" ] && continue
  CMD="$(ps -o command= -p "$P" 2>/dev/null)"
  case "$CMD" in
    *python*uvicorn*app:app*--port\ "$PORT"*) echo "stopping stale $P: $CMD"; kill "$P" 2>/dev/null; /bin/sleep 2
        kill -0 "$P" 2>/dev/null && { echo "  still alive: SIGKILL $P"; kill -9 "$P"; } ;;
    *) echo "NOT MINE, left alone: $P: $CMD" ;;
  esac
done
[ -f "$M" ] || { echo "no motor record at $M"; exit 0; }
for i in $(seq 1 40); do
  /bin/sleep 1
  N=$(sed -nE 's/.*"pid": *([0-9]+).*/\1/p' "$M")
  [ -n "$L" ] && [ "$N" = "$L" ] && { echo "the listener $L holds the motor: $(tr '\n' ' ' < "$M")"; exit 0; }
done
echo "motor record still says: $(tr '\n' ' ' < "$M")"; exit 1
