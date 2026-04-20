---
name: sutra-status
description: Show Sutra plugin state — project IDs, queue depth, last flush, opt-in flag.
disable-model-invocation: true
---

# /sutra-status — Local state

```!
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
source "$PLUGIN_ROOT/lib/queue.sh"

echo "── Sutra plugin status ────────────────────────────────────"

if [ -f .claude/sutra-project.json ]; then
  python3 -c "
import json
d = json.load(open('.claude/sutra-project.json'))
for k,v in d.items(): print(f'  {k:20s} {v}')
"
else
  echo "  (no .claude/sutra-project.json — run /sutra-onboard)"
fi

echo ""
echo "  queue_file           $(queue_file)"
echo "  queue_depth          $(queue_count)"

if [ -f "$HOME/.sutra/last-flush.txt" ]; then
  echo ""
  cat "$HOME/.sutra/last-flush.txt" | sed 's/^/  /'
fi

echo "───────────────────────────────────────────────────────────"
```
