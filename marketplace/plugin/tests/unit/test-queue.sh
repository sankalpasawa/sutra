#!/bin/bash
# Unit test: lib/queue.sh — append/read/rotate behavior.
set -u

PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

# Isolate queue from real ~/.sutra
export SUTRA_HOME="$(mktemp -d)"
export SUTRA_QUEUE_CAP=5

source "$PLUGIN_ROOT/lib/queue.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# 1) fresh queue count is 0
queue_init
[ "$(queue_count)" = "0" ] && _ok "fresh queue count 0" || _no "fresh count: $(queue_count)"

# 2) append increases count
queue_append '{"a":1}'
[ "$(queue_count)" = "1" ] && _ok "append increments count" || _no "after append: $(queue_count)"

# 3) read returns what was written
OUT=$(queue_read)
[ "$OUT" = '{"a":1}' ] && _ok "read returns appended line" || _no "read: $OUT"

# 4) clear empties
queue_clear
[ "$(queue_count)" = "0" ] && _ok "clear zeroes count" || _no "after clear: $(queue_count)"

# 5) rotate at cap
for i in 1 2 3 4 5 6; do queue_append "{\"n\":$i}"; done
queue_rotate_if_big
COUNT_AFTER=$(queue_count)
BAK_COUNT=$(ls "$SUTRA_HOME"/metrics-queue.*.bak 2>/dev/null | wc -l | tr -d ' ')
[ "$COUNT_AFTER" = "0" ] && [ "$BAK_COUNT" = "1" ] && \
  _ok "rotate at cap (queue=0, bak=1)" || \
  _no "rotate failed: queue=$COUNT_AFTER bak=$BAK_COUNT"

# 6) queue_file path is under SUTRA_HOME
case "$(queue_file)" in
  "$SUTRA_HOME"/*) _ok "queue path under SUTRA_HOME" ;;
  *) _no "queue path: $(queue_file)" ;;
esac

rm -rf "$SUTRA_HOME"
echo ""
echo "test-queue: $PASS passed, $FAIL failed"
exit $FAIL
