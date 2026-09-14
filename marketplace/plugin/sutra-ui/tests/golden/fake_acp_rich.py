#!/usr/bin/env python3
"""A scripted ACP agent for the golden replay -- the turn qa/fake_acp_agent.py
does not have.

WHY THIS EXISTS BESIDE qa/fake_acp_agent.py, WHICH IS NOT REPLACED.

qa/fake_acp_agent.py answers `session/prompt` with a bare
{"stopReason": "end_turn"} and says so in its own comment: "No text, no tool
calls -- the turn is not what is under test." That is right for what it guards
(the set_mode name, the auth-before-new refusal, the -32601 fallback), and
test_provider_golden.py drives the real AcpRuntime against it for exactly those:
the handshake, session/new, session/load resume, and mode application.

The golden replay needs the other half -- every client frame
AcpRuntime._translate_update and _answer_request_permission can emit. That is
`token`, `thinking`, `tool` start, `tool` end, `notice` (the permission audit
line) and `done` with a quota block. None of them has a producer in the qa stub,
so a golden built on it alone would freeze one frame type out of six.

FIDELITY, SAME RULE AS THE STUB IT SITS BESIDE. Method set, mode ids, model
list and the unauthenticated refusal are copied from qa/fake_acp_agent.py rather
than loosened, so this stub is never MORE permissive than the thing it stands
in for. An unrecognised method is still -32601.

ORDERING IS DETERMINISTIC ON PURPOSE. AcpRuntime answers
session/request_permission on a task of its own
(asyncio.ensure_future(self._answer_request_permission(msg))) while the reader
loop keeps reading, so a stub that fired the permission ask and then kept
streaming updates would let the `notice` frame land anywhere in the sequence and
the golden would flap. This stub BLOCKS on the permission reply before sending
the next update, which pins the frame order without changing any behaviour
under test.

  $SUTRA_GOLDEN_ACP_ARGV    (OUTPUT) the real argv of the real spawn, as JSON
  $SUTRA_GOLDEN_ACP_SCRIPT  (INPUT)  which prompt turn to run

  plain        message chunk, thought chunk, one tool call, done+quota
  permission   the same, but the tool call asks session/request_permission first
  sutra_mcp    a permission ask whose title carries the sutra MCP suffix (the
               carve-out _choose_permission_option applies before the mode)
  refusal      session/prompt answers stopReason=refusal
  rpc_error    session/prompt answers a JSON-RPC error
"""
import json
import os
import sys

AVAILABLE_MODES = [
    {"id": "default", "name": "Default", "description": "Prompts for approval"},
    {"id": "autoEdit", "name": "Auto Edit", "description": "Auto-approves edit tools"},
    {"id": "yolo", "name": "YOLO", "description": "Auto-approves all tools"},
    {"id": "plan", "name": "Plan", "description": "Read-only mode"},
]
AVAILABLE_MODELS = [
    {"modelId": "auto", "name": "Auto"},
    {"modelId": "deepseek-v4-pro", "name": "deepseek-v4-pro"},
    {"modelId": "deepseek-v4-flash", "name": "deepseek-v4-flash"},
]
DEEPSEEK_AUTH_METHOD = "deepseek-api-key"
UNAUTHED_MESSAGE = "Gemini API key is missing or not configured."
SUTRA_TITLE = "propose (sutra MCP Server)"

CURRENT_MODE = "default"
AUTHENTICATED = False


def _write_argv():
    path = os.environ.get("SUTRA_GOLDEN_ACP_ARGV")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sys.argv, fh)
    except OSError:
        pass


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _reply(msg_id, result):
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _send({"jsonrpc": "2.0", "id": msg_id, "error": err})


def _update(session_id, update):
    _send({"jsonrpc": "2.0", "method": "session/update",
           "params": {"sessionId": session_id, "update": update}})


def _session_state():
    return {"modes": {"availableModes": AVAILABLE_MODES,
                      "currentModeId": CURRENT_MODE},
            "models": {"availableModels": AVAILABLE_MODELS,
                       "currentModelId": "deepseek-v4-flash"}}


def _await_reply(req_id):
    """Block until the client answers request id `req_id`; return its result.

    A plain readline loop, not a queue: nothing else is in flight while a
    permission ask is open, and blocking here is what makes the frame order
    deterministic (see the module header).
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == req_id:
            return msg.get("result"), msg.get("error")
    return None, None


_QUOTA = {"quota": {"token_count": {"input_tokens": 118, "output_tokens": 24},
                    "model_usage": [{"model": "deepseek-v4-flash",
                                     "input_tokens": 118, "output_tokens": 24,
                                     "an_unknown_key": "must not be forwarded"}]}}


def _do_turn(session_id, script):
    if script == "refusal":
        return {"stopReason": "refusal", "_meta": _QUOTA}

    _update(session_id, {"sessionUpdate": "agent_message_chunk",
                         "content": {"type": "text", "text": "Checking the file. "}})
    _update(session_id, {"sessionUpdate": "agent_thought_chunk",
                         "content": {"type": "text",
                                     "text": "private reasoning, never forwarded"}})
    # A sessionUpdate this build drops on purpose -- proof that the golden
    # records the DROP, not a guessed frame.
    _update(session_id, {"sessionUpdate": "plan",
                         "entries": [{"content": "step one", "status": "pending"}]})

    title = SUTRA_TITLE if script == "sutra_mcp" else "Write /tmp/written.txt"
    _update(session_id, {"sessionUpdate": "tool_call", "toolCallId": "tc_1",
                         "kind": "edit", "title": title, "status": "pending"})

    if script in ("permission", "sutra_mcp"):
        _send({"jsonrpc": "2.0", "id": 9001,
               "method": "session/request_permission",
               "params": {"sessionId": session_id,
                          "toolCall": {"toolCallId": "tc_1", "kind": "edit",
                                       "title": title, "status": "pending"},
                          "options": [
                              {"optionId": "proceed_once", "name": "Yes",
                               "kind": "allow_once"},
                              {"optionId": "proceed_always", "name": "Always",
                               "kind": "allow_always"},
                              {"optionId": "cancel", "name": "No",
                               "kind": "reject_once"}]}})
        _await_reply(9001)

    _update(session_id, {"sessionUpdate": "tool_call_update", "toolCallId": "tc_1",
                         "status": "completed",
                         "content": [{"type": "content",
                                      "content": {"type": "text",
                                                  "text": "wrote 1 line"}},
                                     {"type": "diff", "path": "/tmp/written.txt"}]})
    _update(session_id, {"sessionUpdate": "agent_message_chunk",
                         "content": {"type": "text", "text": "Done."}})
    return {"stopReason": "end_turn", "_meta": _QUOTA}


def main():
    global CURRENT_MODE, AUTHENTICATED
    _write_argv()
    script = (os.environ.get("SUTRA_GOLDEN_ACP_SCRIPT") or "plain").strip()
    session_id = "golden-acp-session"

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
                            "agentCapabilities": {"loadSession": True,
                                                  "promptCapabilities": {"image": False}}})
        elif method == "authenticate":
            if params.get("methodId") != DEEPSEEK_AUTH_METHOD:
                _error(msg_id, -32602,
                       "Invalid auth method: %s" % params.get("methodId"))
            else:
                AUTHENTICATED = True
                _reply(msg_id, {})
        elif method == "session/new":
            if not AUTHENTICATED:
                _error(msg_id, -32000, UNAUTHED_MESSAGE)
            else:
                state = _session_state()
                state["sessionId"] = session_id
                _reply(msg_id, state)
        elif method == "session/load":
            if not AUTHENTICATED:
                _error(msg_id, -32000, UNAUTHED_MESSAGE)
            else:
                session_id = params.get("sessionId") or session_id
                _reply(msg_id, _session_state())
        elif method == "session/set_mode":
            mode_id = params.get("modeId")
            if any(m["id"] == mode_id for m in AVAILABLE_MODES):
                CURRENT_MODE = mode_id
                _reply(msg_id, {})
            else:
                _error(msg_id, -32603, "Internal error",
                       {"details": "Invalid or unavailable mode: %s" % mode_id})
        elif method == "session/prompt":
            if script == "rpc_error":
                _error(msg_id, -32000, "DeepSeek API returned 429")
            else:
                _reply(msg_id, _do_turn(params.get("sessionId") or session_id,
                                        script))
        else:
            _error(msg_id, -32601, '"Method not found": %s' % method,
                   {"method": method})


if __name__ == "__main__":
    main()
