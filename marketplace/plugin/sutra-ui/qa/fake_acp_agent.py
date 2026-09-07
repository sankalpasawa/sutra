#!/usr/bin/env python3
"""A stub ACP agent that records what the panel ACTUALLY sent it.

Exists so claims about the wire can be asserted against the wire. Two
recordings, both written from inside the spawned process:

  $SUTRA_FAKE_ACP_ARGV   the real argv of the real spawn
  $SUTRA_FAKE_ACP_MODES  every session/set_mode this stub ACCEPTED, in order

Neither can be replaced by reading the code under test. The model bug was
precisely that build_acp_args ignored an argument its caller had correctly
computed, validated and announced -- a test asserting on the intended argv
would have passed throughout that bug's entire life. The mode bug below is the
same shape one layer over.

FIDELITY IS THE POINT, NOT CONVENIENCE.

This stub previously answered EVERY unrecognised method with `{}`. That one
line hid a live bug for the whole life of the DeepSeek pane: AcpRuntime called
`session/set_session_mode`, which does not exist on the real CLI (the method is
`session/set_mode`), and the real agent answers it -32601. The stub said yes.
So the panel believed it had set the permission mode, recorded that it had,
and every DeepSeek session ran in `default` -- prompting for approval on work
the operator had put in `plan`.

A stub that is more permissive than the thing it stands in for does not
approximate that thing, it silently deletes a class of test. So:

  - an unrecognised method is answered -32601, exactly as the real agent does
    (`GeminiAgent` implements no `extMethod`, so its dispatcher falls through
    to `RequestError.methodNotFound`)
  - session/new offers the REAL four modes with the REAL ids -- including
    `autoEdit`, whose camelCase is the second half of the same bug: the argv
    flag spells it `auto_edit`, the wire does not
  - session/set_mode VALIDATES modeId against that list and answers -32603
    for anything else, as the real `Session.setMode` does

Verified against @sluisr/deepseek-cli@1.3.2 by read-only probe on 2026-09-07:
initialize, session/new, session/set_mode (valid + invalid), set_model,
set_config_option, set_permissions. Method presence here mirrors that agent's
implemented handler set, not the ACP SDK's dispatcher table -- the two differ,
and the SDK's is the larger.

It never reaches the network and needs no key.
"""
import json
import os
import sys

#: The real CLI's own list, from session/new on the installed build. `plan` is
#: present because that build has it enabled; the ids are what the WIRE uses.
AVAILABLE_MODES = [
    {"id": "default", "name": "Default", "description": "Prompts for approval"},
    {"id": "autoEdit", "name": "Auto Edit", "description": "Auto-approves edit tools"},
    {"id": "yolo", "name": "YOLO", "description": "Auto-approves all tools"},
    {"id": "plan", "name": "Plan", "description": "Read-only mode"},
]
#: Mirrors the installed build, duplicate entry and all -- the real
#: availableModels really does list deepseek-v4-flash twice.
AVAILABLE_MODELS = [
    {"modelId": "auto", "name": "Auto"},
    {"modelId": "deepseek-v4-pro", "name": "deepseek-v4-pro"},
    {"modelId": "deepseek-v4-flash", "name": "deepseek-v4-flash"},
    {"modelId": "deepseek-v4-flash", "name": "deepseek-v4-flash"},
]
CURRENT_MODE = "default"
CURRENT_MODEL = "deepseek-v4-flash"


def _write_argv():
    path = os.environ.get("SUTRA_FAKE_ACP_ARGV")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sys.argv, fh)
    except OSError:
        pass


def _record_mode(mode_id):
    """Append an ACCEPTED mode to the recording. Only accepted ones: a rejected
    set_mode did not change the session, and recording it would let a test
    claiming "the mode was set" pass on a call the agent refused."""
    path = os.environ.get("SUTRA_FAKE_ACP_MODES")
    if not path:
        return
    try:
        modes = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                modes = json.load(fh)
        modes.append(mode_id)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(modes, fh)
    except (OSError, ValueError):
        pass


def _reply(msg_id, result):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def _error(msg_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "error": err}) + "\n")
    sys.stdout.flush()


def _session_state():
    return {"modes": {"availableModes": AVAILABLE_MODES,
                      "currentModeId": CURRENT_MODE},
            "models": {"availableModels": AVAILABLE_MODELS,
                       "currentModelId": CURRENT_MODEL}}


def main():
    global CURRENT_MODE
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
        params = msg.get("params") or {}
        if method == "initialize":
            _reply(msg_id, {"protocolVersion": 1,
                            "agentCapabilities": {"loadSession": True}})
        elif method == "session/new":
            state = _session_state()
            state["sessionId"] = "fake-session"
            _reply(msg_id, state)
        elif method == "session/load":
            # Implemented, because the real agent implements it -- letting this
            # 404 would make a resume test pass for the wrong reason. Carries no
            # sessionId, matching zLoadSessionResponse (unlike session/new, the
            # real one does not echo the id back).
            _reply(msg_id, _session_state())
        elif method == "session/set_mode":
            mode_id = params.get("modeId")
            if any(m["id"] == mode_id for m in AVAILABLE_MODES):
                CURRENT_MODE = mode_id
                _record_mode(mode_id)
                _reply(msg_id, {})
            else:
                # The real Session.setMode raises a plain Error, which the SDK
                # surfaces as -32603 with the message under data.details.
                _error(msg_id, -32603, "Internal error",
                       {"details": "Invalid or unavailable mode: %s" % mode_id})
        elif method == "session/prompt":
            # No text, no tool calls -- the turn is not what is under test.
            _reply(msg_id, {"stopReason": "end_turn"})
        else:
            # NOT `{}`. See the module docstring: the permissive fallback that
            # used to be here is what let the set_session_mode bug ship.
            _error(msg_id, -32601, '"Method not found": %s' % method,
                   {"method": method})


if __name__ == "__main__":
    main()
