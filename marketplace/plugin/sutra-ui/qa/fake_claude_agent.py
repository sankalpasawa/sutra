#!/usr/bin/env python3
"""A stub `claude -p --output-format stream-json` that records what the panel
ACTUALLY spawned it with.

Exists for the same reason qa/fake_acp_agent.py and qa/fake_codex_agent.py do,
and the reason is stated most sharply in the ACP one: a stub that is more
permissive than the thing it stands in for does not approximate that thing, it
silently deletes a class of test.

  $SUTRA_FAKE_CLAUDE_ARGV     (OUTPUT) JSONL -- one line per spawn, appended
  $SUTRA_FAKE_CLAUDE_SESSION  (INPUT)  the session id to report as its own
  $SUTRA_FAKE_CLAUDE_KNOWN    (INPUT)  comma-separated ids --resume accepts

APPENDED, ONE LINE PER SPAWN, AND THAT IS NOT A DETAIL
A single overwritten recording made this stub useless for the bug it exists to
catch. app.py replays a turn WITHOUT --resume when a resumed id is rejected
(its resume_unverified branch), so the panel spawns twice: once with the bad
id, once clean. A recording that kept only the LAST spawn showed a clean argv
and the assertion passed while the bug was fully present -- measured, on the
first run of test_switch_seed. The question a test has to ask is "was the
target EVER spawned with the source provider's id", so every spawn is kept.

WHAT IT REFUSES, AND WHY THAT IS THE POINT
------------------------------------------
`claude --resume <id>` resolves the id IN THE PROJECT OF ITS WORKING DIRECTORY
and REFUSES an id it cannot find, writing to stderr and exiting non-zero with
no stream-json on stdout at all:

    No conversation found with session ID: <id>

That refusal is the entire behaviour under test. The bug this stub guards
against is the panel handing Claude a session id minted by a DIFFERENT provider
(a Codex thread id), which Claude cannot possibly resolve. A stub that accepted
any --resume value would pass whether or not the fix works, because the wrong
id would be quietly tolerated -- exactly the class of test the ACP stub's
header warns about. So $SUTRA_FAKE_CLAUDE_KNOWN is an allow-list and anything
outside it is refused the way the real binary refuses it.

It is otherwise as small as the interface allows: no tools, no MCP, no
thinking, no partial deltas. Those are not what any of this asserts.

STREAM-JSON, AND ONE PROCESS FOR MANY TURNS
-------------------------------------------
The panel spawns with --input-format stream-json (session_runtime's
stream_input=True), so a turn is one JSON frame on stdin and one process serves
every turn. This mirrors that: read a frame, answer it, loop until EOF. A stub
that exited after one turn would make the reuse path untestable and would look
like the one-shot `codex exec` lifecycle instead of Claude's.

Emits exactly the three event shapes session_runtime._demux_turn_inner reads:

    {"type":"system","subtype":"init","session_id":...}   -> `sysinit` + `session`
    {"type":"assistant","message":{"content":[...]}}      -> `token`
    {"type":"result","subtype":"success",...}             -> `done`, ends the turn
"""
import json
import os
import sys
import uuid


def _record(var, payload):
    """Append one recording, from inside the spawned process. Never fatal: a
    stub that dies on its own bookkeeping fails the test it was meant to
    measure, and for a reason that has nothing to do with the code under
    test.

    Mode "a" and one JSON object per line -- see the header on why keeping only
    the last spawn hid the bug this stub is for."""
    path = os.environ.get(var)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except OSError:
        pass


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _flag_value(argv, flag):
    """The value after `flag`, or None. Not argparse: this has to tolerate the
    real argv verbatim, including flags this stub knows nothing about."""
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def main(argv):
    _record("SUTRA_FAKE_CLAUDE_ARGV", argv)

    resume = _flag_value(argv, "--resume")
    known = [s for s in (os.environ.get("SUTRA_FAKE_CLAUDE_KNOWN") or "").split(",") if s]

    if resume is not None and resume not in known:
        # THE REAL REFUSAL. stderr, non-zero, and NOTHING on stdout -- which is
        # what the panel sees as eof with a stderr body, and is how it learns
        # the id was bad (app.py's resume_unverified branch reads that stderr).
        sys.stderr.write("No conversation found with session ID: %s\n" % resume)
        return 1

    # A resumed session keeps its id; a fresh one mints a new one. Both are what
    # the real binary does, and the difference is what test 2 asserts on.
    session_id = resume or os.environ.get("SUTRA_FAKE_CLAUDE_SESSION") or uuid.uuid4().hex

    _emit({"type": "system", "subtype": "init", "session_id": session_id,
           "model": _flag_value(argv, "--model") or "stub-model",
           "tools": [], "mcp_servers": []})

    # ONE PROCESS, MANY TURNS: a frame per turn until stdin closes.
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if frame.get("type") != "user":
            continue
        _emit({"type": "assistant", "session_id": session_id,
               "message": {"role": "assistant",
                           "content": [{"type": "text", "text": "ack"}]}})
        _emit({"type": "result", "subtype": "success", "session_id": session_id,
               "is_error": False, "duration_ms": 1, "num_turns": 1,
               "total_cost_usd": 0.0, "result": "ack"})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
