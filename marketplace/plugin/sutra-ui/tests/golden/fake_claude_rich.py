#!/usr/bin/env python3
"""A scripted `claude -p --output-format stream-json` stub for the golden replay.

WHY THIS EXISTS BESIDE qa/fake_claude_agent.py, WHICH IS NOT REPLACED.

qa/fake_claude_agent.py is deliberately minimal -- "no tools, no MCP, no
thinking, no partial deltas. Those are not what any of this asserts." It is the
right stub for the question it was built for (was the target EVER spawned with
the source provider's session id) and test_provider_golden.py still drives the
real runtime against it for the plain-answer, session-capture and
resume-accepted / resume-refused cases.

But the golden replay has a different job: freeze EVERY client frame
session_runtime._demux_turn_inner can emit, so a rewrite of the dispatch layer
cannot quietly change one. Four of those frames -- `thinking`, `tool` start,
`tool` end and `retrying` -- have no producer in the minimal stub, and the
`result`-with-is_error path has none either. A golden built only on the minimal
stub would record six frame shapes out of ten and call the other four covered.

So this stub emits the measured event shapes for those paths and nothing more.
It is a FIXTURE, owned by the golden test, and it never refuses anything: the
refusal behaviour (a --resume id the CLI cannot resolve) is the minimal stub's
job and the golden uses it for exactly that.

  $SUTRA_GOLDEN_CLAUDE_SCRIPT  (INPUT) which scripted turn to emit
  $SUTRA_GOLDEN_CLAUDE_SESSION (INPUT) the session id to report as its own

ONE PROCESS, MANY TURNS, like the real binary under --input-format stream-json:
read a `user` frame from stdin, emit this script's events, loop until EOF.

THE SCRIPTS, and which frame each exists to produce:

  text          assistant text block                 -> token, done
  thinking      assistant thinking + text blocks     -> thinking, token, done
  tool          tool_use + tool_result (Bash)        -> tool/start, tool/end
  tool_fail     tool_result with is_error            -> tool/end ok=false
  retry         system/api_retry then success        -> retrying, token, done
  error         result with is_error                 -> (no done; result_error)
  subagent      Task tool_use, launch RECEIPT, then
                system/task_notification             -> tool/start, tool/end
                                                        (the receipt must NOT
                                                        close the tool -- see
                                                        session_runtime's
                                                        "Async agent launched"
                                                        branch)
  tools_matrix  one tool_use per tool family named in
                the provider-cleanup spec's kind table, plus an mcp__sutra__*
                call and a tool name this build has never seen. Freezes what
                TODAY's flat `tool` frame carries for each, so the classifier
                added later can be diffed against it rather than guessed at.

Every id, name and text below is fixed -- nothing here is random, so the only
values the golden has to normalise are the ones the RUNTIME or the OS invents.
"""
import json
import os
import sys

SESSION = os.environ.get("SUTRA_GOLDEN_CLAUDE_SESSION") or "golden-session-0001"


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _assistant(blocks):
    _emit({"type": "assistant", "session_id": SESSION,
           "message": {"role": "assistant", "content": blocks}})


def _user(blocks):
    _emit({"type": "user", "session_id": SESSION,
           "message": {"role": "user", "content": blocks}})


def _result_ok(text="ok"):
    _emit({"type": "result", "subtype": "success", "session_id": SESSION,
           "is_error": False, "duration_ms": 1234, "num_turns": 2,
           "total_cost_usd": 0.0042, "result": text})


def _tool_use(tool_id, name, inp, caller=None):
    blk = {"type": "tool_use", "id": tool_id, "name": name, "input": inp}
    if caller is not None:
        blk["caller"] = caller
    return blk


def _tool_result(tool_use_id, content, is_error=False):
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": content, "is_error": is_error}


# --------------------------------------------------------------- the scripts --

def script_text():
    _assistant([{"type": "text", "text": "The answer is 42."}])
    _result_ok("The answer is 42.")


def script_thinking():
    _assistant([{"type": "thinking", "text": "long private scratchpad text"},
                {"type": "text", "text": "Here is the short version."}])
    _result_ok("Here is the short version.")


def script_tool():
    _assistant([_tool_use("toolu_01", "Bash",
                          {"command": "echo hello", "description": "say hello"},
                          caller={"type": "direct"})])
    _user([_tool_result("toolu_01", [{"type": "text", "text": "hello\n"}])])
    _assistant([{"type": "text", "text": "It printed hello."}])
    _result_ok("It printed hello.")


def script_tool_fail():
    _assistant([_tool_use("toolu_02", "Bash", {"command": "false"})])
    _user([_tool_result("toolu_02", "exit status 1", is_error=True)])
    _result_ok("that failed")


def script_retry():
    _emit({"type": "system", "subtype": "api_retry", "session_id": SESSION,
           "message": "overloaded_error, retrying in 2s", "attempt": 2})
    _assistant([{"type": "text", "text": "recovered"}])
    _result_ok("recovered")


def script_error():
    _emit({"type": "result", "subtype": "error_during_execution",
           "session_id": SESSION, "is_error": True, "duration_ms": 99,
           "num_turns": 1, "total_cost_usd": 0.0,
           "result": "Claude Code process exited with code 1"})


def script_subagent():
    _assistant([_tool_use("toolu_03", "Task",
                          {"description": "find the caller",
                           "prompt": "You are a helper. Find the caller of x.",
                           "subagent_type": "Explore"})])
    # THE LAUNCH RECEIPT. Arrives immediately, carries the SAME tool_use_id,
    # and must NOT close the tool -- that is the whole point of this script.
    _user([_tool_result("toolu_03",
                        [{"type": "text",
                          "text": "Async agent launched successfully"}])])
    _emit({"type": "system", "subtype": "task_notification",
           "session_id": SESSION, "tool_use_id": "toolu_03",
           "status": "completed", "summary": "found it in app.py",
           "usage": {"input_tokens": 10, "output_tokens": 4}})
    _result_ok("found it")


def script_tools_matrix():
    calls = [
        ("toolu_10", "Bash", {"command": "ls -la /tmp"}),
        ("toolu_11", "Read", {"file_path": "/etc/hosts"}),
        ("toolu_12", "Edit", {"file_path": "/tmp/a.py", "old_string": "x",
                              "new_string": "y"}),
        ("toolu_13", "Write", {"file_path": "/tmp/b.py",
                               "content": "a whole file body"}),
        ("toolu_14", "Grep", {"pattern": "def run", "path": "/tmp"}),
        ("toolu_15", "Glob", {"pattern": "**/*.py"}),
        ("toolu_16", "WebSearch", {"query": "acp protocol spec"}),
        ("toolu_17", "WebFetch", {"url": "https://example.com/a",
                                  "prompt": "summarise"}),
        ("toolu_18", "TodoWrite", {"todos": [{"content": "one"}]}),
        ("toolu_19", "ExitPlanMode", {"plan": "step one, step two"}),
        ("toolu_20", "NotebookEdit", {"notebook_path": "/tmp/n.ipynb",
                                      "new_source": "print(1)"}),
        ("toolu_21", "mcp__sutra__propose", {"title": "a proposal"}),
        ("toolu_22", "BashOutput", {"bash_id": "sh_1", "command": "tail -f log"}),
        ("toolu_23", "AToolFromTheFuture", {"whatever": "some value"}),
    ]
    _assistant([_tool_use(tid, name, inp) for tid, name, inp in calls])
    _user([_tool_result(tid, [{"type": "text", "text": "result for %s" % tid}])
           for tid, _, _ in calls])
    _result_ok("all fourteen ran")


SCRIPTS = {
    "text": script_text,
    "thinking": script_thinking,
    "tool": script_tool,
    "tool_fail": script_tool_fail,
    "retry": script_retry,
    "error": script_error,
    "subagent": script_subagent,
    "tools_matrix": script_tools_matrix,
}


def main(argv):
    script = (os.environ.get("SUTRA_GOLDEN_CLAUDE_SCRIPT") or "text").strip()
    if script not in SCRIPTS:
        sys.stderr.write("fake_claude_rich: unknown script %r\n" % script)
        return 2

    def _flag(flag):
        try:
            return argv[argv.index(flag) + 1]
        except (ValueError, IndexError):
            return None

    _emit({"type": "system", "subtype": "init", "session_id": SESSION,
           "model": _flag("--model") or "stub-model",
           "tools": ["Bash", "Read", "Edit"],
           "mcp_servers": [{"name": "sutra", "status": "connected"}],
           "slash_commands": ["init", "review"],
           "permissionMode": _flag("--permission-mode") or "plan",
           "cwd": os.getcwd()})

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if frame.get("type") != "user":
            continue
        SCRIPTS[script]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
