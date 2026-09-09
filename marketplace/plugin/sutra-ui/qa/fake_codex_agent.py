#!/usr/bin/env python3
"""A stub `codex exec --json` that records what the panel ACTUALLY sent it.

Exists so claims about the wire can be asserted against the wire. Three
recordings, all written from inside the spawned process:

  $SUTRA_FAKE_CODEX_ARGV    the real argv of the real spawn
  $SUTRA_FAKE_CODEX_STDIN   the prompt bytes the panel actually delivered
  $SUTRA_FAKE_CODEX_SCRIPT  (INPUT) which canned event script to emit

None of these can be replaced by reading the code under test. The bug class
this guards against is the one DeepSeek already paid for: build_acp_args
ignored a model its caller had correctly computed, validated and ANNOUNCED, so
a test asserting on the intended argv would have passed for the whole life of
the bug. The prompt-delivery equivalent here is worse, because a prompt that
silently lands in argv still works for short messages and dies at E2BIG on a
long one.

FIDELITY IS THE POINT, NOT CONVENIENCE.

qa/fake_acp_agent.py's header records what a permissive stub costs: it answered
every unrecognised method `{}`, which hid a live DeepSeek permission-mode bug
for that pane's entire life. "A stub that is more permissive than the thing it
stands in for does not approximate that thing, it silently deletes a class of
test."

So this stub REFUSES what codex-cli 0.153.2 was measured to refuse, on
2026-09-08, with the same output stream and the same shape:

  - `--sandbox <v>` outside {read-only, workspace-write, danger-full-access}
    -> clap usage error on STDERR, exit 2, NO JSON. Measured verbatim:
       "error: invalid value 'nonsense' for '--sandbox <SANDBOX_MODE>'"
  - `-c approval_policy=<v>` outside {untrusted, on-failure, on-request,
    granular, never} -> config load error on STDERR, exit 1, NO JSON. Measured:
       "Error loading config.toml: unknown variant `bogus_value`, expected one
        of `untrusted`, `on-failure`, `on-request`, `granular`, `never`"
  - a `resume` subcommand with exec-level flags AFTER it -> plain-text error,
    NO JSON. This is the ordering trap: `codex exec resume --last --json` was
    measured to print "Not inside a trusted directory and
    --skip-git-repo-check was not specified." and emit no JSONL at all, because
    `resume` does not accept --json/--sandbox/-C/--skip-git-repo-check/-m.
  - no `--skip-git-repo-check` while outside a trusted directory -> the same
    plain-text trust refusal, NO JSON.

STDOUT IS PURE JSONL AND STDERR IS NOISY, because that is what codex does. The
stub writes a "Reading additional input from stdin..." line to stderr on the
stdin-prompt path, mirroring the real CLI, so a parser that ever merges the two
streams fails here instead of in production.
"""
import json
import os
import sys
import uuid

_SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
_APPROVAL_POLICIES = ("untrusted", "on-failure", "on-request", "granular", "never")

#: Flags `codex exec` accepts BEFORE a subcommand and `codex exec resume` does
#: not accept after it. Read off `codex exec resume --help` on 0.153.2, whose
#: whole option list is -c/--last/--all/--enable/--disable/-i/--strict-config.
_EXEC_ONLY_FLAGS = ("--json", "--sandbox", "-C", "--cd", "--skip-git-repo-check",
                    "-m", "--model", "--dangerously-bypass-approvals-and-sandbox")


def _record(env_var, payload, append=False):
    """One recording, from inside the spawned process.

    `append` writes ONE JSON OBJECT PER LINE instead of overwriting, and it is
    used for the argv recording only. A single overwritten argv cannot answer
    the question a switch test has to ask -- "was codex EVER spawned with the
    source provider's session id" -- because it only ever holds the LAST spawn.
    That is not hypothetical: the same overwrite in the Claude stub made two
    provider-switch tests pass while the bug was fully present (see
    qa/fake_claude_agent.py's header).

    The STDIN recording deliberately stays overwrite-and-raw: it is the prompt
    BYTES the panel delivered, and JSON-quoting them would change the thing
    under test.
    """
    path = os.environ.get(env_var)
    if not path:
        return
    try:
        with open(path, "a" if append else "w") as fh:
            if append:
                fh.write(json.dumps(payload) + "\n")
            elif isinstance(payload, str):
                fh.write(payload)
            else:
                json.dump(payload, fh)
    except OSError:
        pass


def _die_plain(message, code=1):
    """A plain-text refusal on stderr with NO JSON on stdout -- the shape the
    real CLI uses for the trust check and the resume-ordering mistake."""
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    sys.exit(code)


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main(argv):
    _record("SUTRA_FAKE_CODEX_ARGV", argv, append=True)

    # ---- parse enough to be as strict as the real thing -----------------
    if "exec" not in argv:
        _die_plain("error: unrecognized subcommand", 2)
    exec_at = argv.index("exec")
    tail = argv[exec_at + 1:]

    sub_at = None
    for name in ("resume", "fork", "review"):
        if name in tail:
            sub_at = min(x for x in (sub_at, tail.index(name)) if x is not None)
    before = tail if sub_at is None else tail[:sub_at]
    after = [] if sub_at is None else tail[sub_at:]

    # THE ORDERING TRAP. An exec-level flag after `resume` is not accepted by
    # the real CLI, which then falls through to the trust check and prints
    # plain text -- no JSONL ever reaches stdout.
    for flag in _EXEC_ONLY_FLAGS:
        if flag in after:
            _die_plain("Not inside a trusted directory and "
                       "--skip-git-repo-check was not specified.")

    if "--skip-git-repo-check" not in before:
        _die_plain("Not inside a trusted directory and "
                   "--skip-git-repo-check was not specified.")

    # --sandbox value validation, clap-style
    if "--sandbox" in before:
        i = before.index("--sandbox")
        val = before[i + 1] if i + 1 < len(before) else ""
        if val not in _SANDBOXES:
            sys.stderr.write(
                "error: invalid value '%s' for '--sandbox <SANDBOX_MODE>'\n"
                "  [possible values: %s]\n\n"
                "For more information, try '--help'.\n"
                % (val, ", ".join(_SANDBOXES)))
            sys.exit(2)

    # -c approval_policy validation, config-load-style
    for i, tok in enumerate(before):
        if tok == "-c" and i + 1 < len(before):
            kv = before[i + 1]
            if kv.startswith("approval_policy="):
                val = kv.split("=", 1)[1]
                if val not in _APPROVAL_POLICIES:
                    sys.stderr.write(
                        "Error loading config.toml: unknown variant `%s`, "
                        "expected one of %s\nin `approval_policy`\n\n"
                        % (val, ", ".join("`%s`" % p for p in _APPROVAL_POLICIES)))
                    sys.exit(1)

    json_mode = "--json" in before

    # ---- the prompt ------------------------------------------------------
    # `-` is codex's documented "read instructions from stdin" form. The real
    # CLI announces the read on STDERR; mirrored so a merged-stream parser
    # breaks here.
    prompt_is_stdin = (tail and tail[-1] == "-")
    prompt = ""
    if prompt_is_stdin:
        sys.stderr.write("Reading additional input from stdin...\n")
        sys.stderr.flush()
        prompt = sys.stdin.read()
    _record("SUTRA_FAKE_CODEX_STDIN", prompt)

    if not json_mode:
        # Nothing under test drives the human renderer; refuse rather than
        # invent output for a mode the panel never uses.
        _die_plain("fake_codex_agent: only --json is implemented", 2)

    # ---- the scripted event stream --------------------------------------
    resumed_id = None
    if after and after[0] == "resume":
        for tok in after[1:]:
            if not tok.startswith("-"):
                resumed_id = tok
                break

    # A resume reports the SAME thread id, which is the measured behaviour and
    # the fact Sutra's session handling depends on.
    thread_id = resumed_id or ("01a08191-7175-7f62-%s" % uuid.uuid4().hex[:16])

    script = (os.environ.get("SUTRA_FAKE_CODEX_SCRIPT") or "ok").strip()

    if script == "no-thread":
        # DIES BEFORE thread.started, which is the one failure shape the other
        # scripts cannot produce: every one of them runs AFTER the emit below,
        # so the panel has already learned a thread id by the time they fail.
        # Here it never learns one -- so `session_id` stays None and
        # switch.confirm is never reached, which is what keeps
        # provider_history free of a segment for a session that does not exist.
        # stderr and a non-zero exit with NO JSON on stdout, the same shape
        # _die_plain already models for the argv refusals.
        _die_plain("codex: could not start a thread", 1)

    _emit({"type": "thread.started", "thread_id": thread_id})
    _emit({"type": "turn.started"})

    if script == "ok":
        _emit({"type": "item.completed",
               "item": {"id": "item_0", "type": "agent_message",
                        "text": "hello from codex"}})
        _emit({"type": "turn.completed",
               "usage": {"input_tokens": 11, "cached_input_tokens": 0,
                         "cache_write_input_tokens": 0, "output_tokens": 3,
                         "reasoning_output_tokens": 1}})

    elif script == "tool":
        cmd = "/bin/zsh -lc 'echo hello'"
        _emit({"type": "item.started",
               "item": {"id": "item_1", "type": "command_execution",
                        "command": cmd, "aggregated_output": "",
                        "exit_code": None, "status": "in_progress"}})
        _emit({"type": "item.completed",
               "item": {"id": "item_1", "type": "command_execution",
                        "command": cmd, "aggregated_output": "hello\n",
                        "exit_code": 0, "status": "completed"}})
        _emit({"type": "item.completed",
               "item": {"id": "item_2", "type": "agent_message",
                        "text": "DONE"}})
        _emit({"type": "turn.completed", "usage": {"output_tokens": 4}})

    elif script == "failed":
        # The transient retries the real CLI interleaves before giving up, then
        # the terminal failure with its message NESTED under .error.
        for n in (2, 3):
            _emit({"type": "error",
                   "message": "Reconnecting... %d/5 (unexpected status 401 "
                              "Unauthorized)" % n})
        _emit({"type": "item.completed",
               "item": {"id": "item_0", "type": "error",
                        "message": "Falling back from WebSockets to HTTPS transport."}})
        _emit({"type": "turn.failed",
               "error": {"message": "unexpected status 401 Unauthorized"}})
        sys.exit(1)

    elif script == "transient":
        # Retries, then SUCCESS. A runtime that treats the top-level `error`
        # event as terminal fails this and only this.
        _emit({"type": "error", "message": "Reconnecting... 2/5 (transport)"})
        _emit({"type": "item.completed",
               "item": {"id": "item_0", "type": "agent_message",
                        "text": "recovered"}})
        _emit({"type": "turn.completed", "usage": {"output_tokens": 2}})

    elif script == "unknown-items":
        # Every measured-but-untranslated member of the ThreadItem union, plus
        # a genuinely unknown top-level type. None may crash the runtime and
        # none may end the turn.
        for itype in ("reasoning", "file_change", "mcp_tool_call",
                      "web_search", "todo_list", "a_type_from_the_future"):
            _emit({"type": "item.completed",
                   "item": {"id": "item_x", "type": itype}})
            _emit({"type": "item.updated",
                   "item": {"id": "item_x", "type": itype}})
        _emit({"type": "some.future.event", "whatever": True})
        _emit({"type": "item.completed",
               "item": {"id": "item_9", "type": "agent_message",
                        "text": "still here"}})
        _emit({"type": "turn.completed", "usage": {"output_tokens": 2}})

    elif script == "eof":
        # Dies mid-turn with NO terminal event -- the measured SIGTERM shape.
        _emit({"type": "item.started",
               "item": {"id": "item_1", "type": "command_execution",
                        "command": "/bin/zsh -lc 'sleep 30'",
                        "aggregated_output": "", "exit_code": None,
                        "status": "in_progress"}})
        sys.exit(0)

    else:
        _die_plain("fake_codex_agent: unknown script %r" % script, 2)

    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv)
