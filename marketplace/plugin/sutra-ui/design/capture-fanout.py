"""Build tests/fixtures/toolruns-fanout.json from a REAL transcript.

Not hand-written: this reads actual Agent tool_use blocks off disk and pushes
them through app.py's own _tool_summary/_tool_command, which is the exact
transform the websocket applies. The result is the shape 01-state.js:904 stores
in turn.toolRuns, so a test that consumes it is testing the real wire.
"""
import glob, json, os, sys

sys.path.insert(0, "/Users/asawa/Claude/asawa-holding/sutra/marketplace/plugin/sutra-ui")
from app import _tool_summary, _tool_command   # the shipped transform, reused

PROJ = os.path.expanduser("~/.claude/projects")

def is_prompt(ev):
    """A real user prompt starts a new turn. A user message that only carries
    tool_result blocks is the transport for a tool ending, not a new turn --
    treating it as one would split a single turn's toolRuns across several."""
    if ev.get("type") != "user":
        return False
    c = (ev.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in c)
    return False


best = None            # (agent_count, path, uses)
for path in glob.glob(os.path.join(PROJ, "*", "*.jsonl")):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        continue
    # A TURN is one user prompt plus every assistant message until the next one.
    # Agent blocks spread across those messages all land in the same
    # turn.toolRuns, which is what the roster reads -- so segment by turn.
    seg = []
    for ln in lines + ["{}"]:                      # sentinel flushes the last turn
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if is_prompt(ev) or ln == "{}":
            agents = [b for b in seg if b.get("name") in ("Agent", "Task")]
            if len(agents) >= 2 and (best is None or len(agents) > best[0]):
                best = (len(agents), path, list(seg))
            seg = []
            continue
        if ev.get("type") == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    seg.append(b)

if not best:
    print("NO_FANOUT_FOUND")
    raise SystemExit(1)

n, path, uses = best
print("source: %s" % path)
print("agent blocks in that message: %d" % n)

# collect tool_results for these ids so the fixture carries real endings too
ids = {b.get("id") for b in uses}
results = {}
for ln in open(path, encoding="utf-8", errors="replace"):
    try:
        ev = json.loads(ln)
    except ValueError:
        continue
    if ev.get("type") != "user":
        continue
    for b in (ev.get("message") or {}).get("content") or []:
        if isinstance(b, dict) and b.get("type") == "tool_result" \
           and b.get("tool_use_id") in ids:
            results[b["tool_use_id"]] = b

runs = []
for i, b in enumerate(uses):
    inp = b.get("input") or {}
    r = {
        "id": b.get("id"),
        "name": b.get("name", ""),
        "summary": _tool_summary(inp),
        "command": _tool_command(b.get("name", ""), inp),
        "caller": (b.get("caller") or {}).get("type"),
        "running": True,
        "ok": None,
        "startedAt": 1_700_000_000_000 + i * 1000,
    }
    res = results.get(b.get("id"))
    if res is not None:
        r["running"] = False
        r["ok"] = not res.get("is_error")
        r["endedAt"] = r["startedAt"] + (i + 1) * 71_000
    runs.append(r)

# leave at least one Agent still running: a roster's hardest state is the live one
live = [r for r in runs if r["name"] in ("Agent", "Task")]
if live and all(not r["running"] for r in live):
    live[-1]["running"] = True
    live[-1]["ok"] = None
    live[-1].pop("endedAt", None)

# Trim to what the unit under test consumes. `command` is dropped (the roster
# never reads it, and for Bash rows it is the whole shell line), and non-Agent
# summaries are capped -- they exist here only to prove the roster EXCLUDES them.
agent_runs = [r for r in runs if r["name"] in ("Agent", "Task")]
other_runs = [r for r in runs if r["name"] not in ("Agent", "Task")][:2]
for r in agent_runs + other_runs:
    r.pop("command", None)
for r in other_runs:
    r["summary"] = r["summary"][:60]
trimmed = other_runs[:1] + agent_runs + other_runs[1:]   # interleave, as the wire does

out = {
    "_source": "captured from a real transcript by scratchpad/capture-fanout.py; "
               "summaries produced by app.py's own _tool_summary()",
    "_shape": "one entry per turn.toolRuns row, exactly as 01-state.js:904 stores it",
    "_trim": "`command` dropped (unread by the roster); non-Agent summaries capped "
             "at 60 chars -- they are here only to prove non-agents are excluded",
    "toolRuns": trimmed,
}
print(json.dumps(out, indent=2)[:1200])
print("...")
print("TOTAL RUNS: %d   AGENT RUNS: %d   STILL RUNNING: %d"
      % (len(runs), len(live), sum(1 for r in runs if r["running"])))
print("SUMMARY SAMPLES:")
for r in live[:4]:
    print("   %r" % r["summary"])

dest = sys.argv[1] if len(sys.argv) > 1 else None
if dest:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print("WROTE %s" % dest)
