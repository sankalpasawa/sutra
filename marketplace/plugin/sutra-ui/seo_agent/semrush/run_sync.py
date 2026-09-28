#!/usr/bin/env python3
"""run_sync.py — the CLI entrypoint a scheduled job calls. No LLM anywhere in this path.

    python3 -m seo_agent.semrush.run_sync <daily|weekly|monthly|discover>

Deliberately NOT routed through routines.py. That module's runner spawns a full
`claude -p <prompt>` agent per fire and bills/behaves accordingly -- exactly wrong
for a deterministic data pull that should cost nothing but the Semrush API call
itself. schedule.py installs a launchd job that calls this file directly.

Exit code is 0 on a completed run (even one with per-blog errors recorded inside the
result -- a single blog's 404 is not a run failure) and 1 only when the mode itself
could not run at all (bad mode name, no credentials, an unhandled exception).
"""
import json
import sys
import time


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 -m seo_agent.semrush.run_sync <daily|weekly|monthly|discover>\n")
        return 1
    mode = argv[1]
    from . import sync
    started = time.time()
    try:
        result = sync.run(mode)
    except Exception as e:  # noqa: BLE001 -- a scheduled job must always leave a legible record
        print(json.dumps({"ok": False, "mode": mode, "error": str(e)[:500],
                          "duration_s": round(time.time() - started, 1)}))
        return 1
    result = dict(result or {})
    result.update({"mode": mode, "duration_s": round(time.time() - started, 1)})
    print(json.dumps(result))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
