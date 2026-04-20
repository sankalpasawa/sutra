#!/bin/bash
# Sutra: queue.sh — local metric queue. Layer B rows only.
# Queue file: $SUTRA_HOME/metrics-queue.jsonl (default ~/.sutra/).
# Rotates at 10k lines.

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
QUEUE="$SUTRA_HOME/metrics-queue.jsonl"
QUEUE_CAP="${SUTRA_QUEUE_CAP:-10000}"

queue_dir()   { echo "$SUTRA_HOME"; }
queue_file()  { echo "$QUEUE"; }
queue_init()  { mkdir -p "$SUTRA_HOME"; [ -f "$QUEUE" ] || : > "$QUEUE"; }
queue_append(){ queue_init; printf '%s\n' "$1" >> "$QUEUE"; }
queue_count() { [ -f "$QUEUE" ] || { echo 0; return; }; wc -l < "$QUEUE" | tr -d ' '; }
queue_read()  { [ -f "$QUEUE" ] && cat "$QUEUE" || :; }
queue_clear() { queue_init; : > "$QUEUE"; }

queue_rotate_if_big() {
  local n
  n=$(queue_count)
  if [ "${n:-0}" -gt "$QUEUE_CAP" ]; then
    mv "$QUEUE" "${QUEUE%.jsonl}.$(date +%s).bak"
    queue_init
    return 0
  fi
  return 1
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-}" in
    count)  queue_count ;;
    read)   queue_read ;;
    clear)  queue_clear ;;
    path)   queue_file ;;
    *)      echo "usage: $0 {count|read|clear|path}" ;;
  esac
fi
