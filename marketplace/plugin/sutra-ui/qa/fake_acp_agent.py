#!/usr/bin/env python3
"""A stub ACP agent that records the argv it was spawned with.

Exists for ONE assertion: that the model the panel announces in its `start`
frame is the model the CLI was actually handed. That claim cannot be tested by
reading build_acp_args() -- the bug it guards against was precisely that
build_acp_args ignored an argument the caller correctly computed, validated and
announced. A test that asserts on the intended argv would have passed
throughout the entire life of that bug.

So this records the REAL argv of the REAL spawn, from inside the spawned
process, to $SUTRA_FAKE_ACP_ARGV. The test reads that file and compares it with
the frame the socket sent.

It then speaks just enough ACP (initialize, session/new, session/set_session_mode,
session/prompt) to keep AcpRuntime's handshake from erroring, and no more. It
never reaches the network and needs no key.
"""
import json
import os
import sys


def _write_argv():
    path = os.environ.get("SUTRA_FAKE_ACP_ARGV")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sys.argv, fh)
    except OSError:
        pass


def _reply(msg_id, result):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def main():
    _write_argv()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:
            continue
        if method == "initialize":
            _reply(msg_id, {"protocolVersion": 1,
                            "agentCapabilities": {"loadSession": True}})
        elif method == "session/new":
            _reply(msg_id, {"sessionId": "fake-session",
                            "modes": {"availableModes": [{"id": "default"}],
                                      "currentModeId": "default"}})
        elif method == "session/prompt":
            # No text, no tool calls -- the turn is not what is under test.
            _reply(msg_id, {"stopReason": "end_turn"})
        else:
            _reply(msg_id, {})


if __name__ == "__main__":
    main()
