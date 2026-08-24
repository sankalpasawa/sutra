"""Process lifecycle for a chat pane\'s persistent agent subprocess.

Extracted VERBATIM from ws_chat (PLAN-100 S17): lifecycle ONLY. Frame
translation, session-id capture, replay/error/stop policy and the socket
reader task all stay at the socket layer -- test_runtime_characterization.py
freezes the behavior this move must not change.
"""
import asyncio
import json
import os
import signal


def _tool_output(content, limit=4000):
    """A tool_result's content, flattened to text for display.

    The block is either a plain string or a list of typed parts. Only text is
    forwarded; an image is NAMED rather than inlined, because a base64 payload
    would be megabytes over a websocket that is rendering a progress view.

    Truncation is EXPLICIT. A silent cut would let someone read half a file and
    believe it was the whole one, which is worse than showing less.
    """
    if content is None:
        return None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                if c.get("type") == "text" and c.get("text"):
                    parts.append(str(c["text"]))
                elif c.get("type"):
                    parts.append("[%s]" % c["type"])
        text = "\n".join(parts)
    else:
        text = str(content)
    text = text.strip()
    if not text:
        return None
    if len(text) > limit:
        return text[:limit] + ("\n… truncated, %d more characters"
                               % (len(text) - limit))
    return text


def _tool_summary(inp, limit=120):
    """One line describing what a tool was asked to do, or "".

    The UI needs to say WHICH file was read or WHICH command ran -- a column of
    identical "Bash" rows tells the operator nothing. The full input is not
    forwarded: a Write's `content` is the whole file, and shipping it to the
    browser on every call is both noise and an accidental data path.

    Key order is deliberate: the most identifying field for the common tools
    (command / file_path / pattern) first, then any short string field, then
    nothing. Never raises -- a tool with an unexpected input shape must not take
    the turn down.
    """
    if not isinstance(inp, dict):
        return ""
    # An Agent/Task input is {description, prompt, subagent_type}. The generic
    # scan below returns on the FIRST hit -- `prompt` -- and in a fan-out every
    # agent's prompt starts with the same preamble, so three parallel agents
    # rendered as three identical rows. subagent_type is the only field that says
    # WHICH agent this is, and it was dropped entirely.
    if inp.get("subagent_type") or inp.get("agent_type"):
        kind = str(inp.get("subagent_type") or inp.get("agent_type") or "agent").strip()
        desc = inp.get("description")
        if isinstance(desc, str) and desc.strip():
            v = "%s: %s" % (kind, " ".join(desc.split()))
            return v[:limit] + ("…" if len(v) > limit else "")
        return kind[:limit]
    for k in ("command", "file_path", "path", "pattern", "url", "query", "prompt",
              "description", "notebook_path"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v[:limit] + ("…" if len(v) > limit else "")
    for v in inp.values():
        if isinstance(v, str) and v.strip() and len(v) <= limit:
            return " ".join(v.split())
    return ""


# A shell command is the one tool input the operator may legitimately want to run
# again by hand, so it is the one forwarded in FULL rather than as the 120-char
# display summary. Deliberately narrow: only tools that take a `command` and
# actually execute a shell. Everything else keeps the summary and nothing more --
# a Write's `content` is a whole file and has no business crossing this wire.
_SHELL_TOOLS = {"bash", "bashoutput", "killshell"}
# Long enough for any real one-liner or short heredoc; past this the paste would
# be unreviewable in a terminal prompt anyway, so it is refused rather than cut
# into something that looks complete but is not.
_COMMAND_MAX = 4000


def _tool_command(name, inp):
    """The verbatim shell command a tool was asked to run, or "".

    Never raises: an unexpected input shape must not take the turn down.
    """
    if not isinstance(inp, dict):
        return ""
    if (name or "").strip().lower() not in _SHELL_TOOLS:
        return ""
    cmd = inp.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    return cmd if len(cmd) <= _COMMAND_MAX else ""


async def _drain_to_newline(reader):
    """Consume bytes up to and including the next newline. Returns False at EOF.

    Naively calling readuntil(b"\n") after an over-limit readline does NOT
    work: the offending bytes are still buffered, so readuntil raises
    LimitOverrunError on the same data and consumes nothing. Swallowing that and
    retrying is an infinite skip that silently drops every later frame -- which
    is exactly what the first version of this fix did, caught by
    test_stream_readline.py.

    LimitOverrunError.consumed is the number of buffered bytes examined without
    finding the separator; readexactly() on that count is what actually removes
    them. Loop until a newline is reached, then the caller is back on a frame
    boundary.
    """
    while True:
        try:
            await reader.readuntil(b"\n")
            return True
        except asyncio.LimitOverrunError as over:
            try:
                await reader.readexactly(over.consumed)
            except asyncio.IncompleteReadError:
                return False
        except asyncio.IncompleteReadError:
            return False
        except ValueError:
            # Defensive: some Python versions surface the limit breach as a
            # bare ValueError from readuntil. Drop the whole buffer and stop.
            return False


class SessionRuntime:
    """Owns exactly one agent subprocess for one chat channel.

    These three fields were a closure dict (`live`) inside ws_chat; the
    meanings are unchanged:

      proc     the persistent subprocess, or None
      key      the RESUME-FREE argv tuple the reuse test compares (storing the
               resume-bearing key made that comparison permanently unequal --
               see the spawn site in ws_chat)
      stopped  the OPERATOR pressed stop. Never set for generic process death:
               conflating the two made an interrupt read as a crash.
    """

    def __init__(self):
        self.proc = None
        self.key = None
        self.stopped = False
        # Turn observers (PLAN-100 S19). The websocket's send_json is NOT in
        # this list -- it is the PRIMARY emit passed to demux_turn, and its
        # exceptions must keep propagating exactly as before (a dead socket
        # ends the turn loop). Subscribers here are additional observers:
        # they see every frame the primary sees, and a broken one is dropped
        # for the turn rather than breaking the operator's answer.
        self.subscribers = []

    def subscribe(self, cb):
        """Register an observer for client frames. cb(frame) may be sync or
        async; it is called AFTER the primary emit for each frame. Returns cb
        so callers can hold it for unsubscribe."""
        self.subscribers.append(cb)
        return cb

    def unsubscribe(self, cb):
        try:
            self.subscribers.remove(cb)
        except ValueError:
            pass

    def _fanout(self, primary):
        """Wrap the primary emit with subscriber fan-out.

        Snapshot semantics: the subscriber list is captured per FRAME (not per
        turn) so an observer attached mid-turn starts seeing frames then --
        the Shadow watcher attaches to already-running panes. Primary
        exceptions propagate (frozen behavior); subscriber exceptions are
        swallowed per-frame -- an observer must never cost the operator a turn.
        """
        import asyncio as _asyncio

        async def emit(frame):
            await primary(frame)
            for cb in list(self.subscribers):
                try:
                    res = cb(frame)
                    if _asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
        return emit

    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    def kill_group(self):
        """Kill the process GROUP, not just the direct child.

        `claude` spawns helpers; signalling only the parent leaves them holding
        the stdout pipe, so the read loop never ends and the turn never actually
        stops. spawn() uses start_new_session=True, which makes the child a
        group leader so this reaches its descendants too. Idempotent: a dead or
        absent process returns False and signals nothing.
        """
        p = self.proc
        if p is None or p.returncode is not None:
            return False
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                p.kill()
            except (ProcessLookupError, OSError):
                return False
        return True

    async def spawn(self, args, cwd, key):
        """Start the persistent process and adopt it as self.proc.

        On OSError nothing is assigned -- the caller keeps whatever stale proc
        was there (the socket layer\'s liveness check already treats a dead one
        as not-alive), and the error policy stays at the socket layer.
        """
        p = await asyncio.create_subprocess_exec(
            *args, cwd=cwd,
            # stdin is a PIPE, not DEVNULL: it is the channel the turns arrive
            # on. (DEVNULL was there because a plain inherited stdin made claude
            # wait 3s for piped input on every message -- with stream-json that
            # wait IS the feature.)
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # 8 MiB, not asyncio\'s 64 KiB default. stream-json is ONE JSON
            # object per line, and a `user` frame carrying a tool_result
            # routinely exceeds 64 KiB -- any Read of a sizeable file, any
            # verbose Bash capture. At the default, StreamReader.readline()
            # raises "Separator is not found, and chunk exceed the limit",
            # which killed the socket and the child mid-answer. Reproduced
            # directly: a 200 KB line raises at the default and reads clean at
            # this limit.
            limit=8 * 1024 * 1024,
            env=dict(os.environ),  # no ANTHROPIC_API_KEY -> subscription auth
            # own process group, so an interrupt can signal the whole tree
            start_new_session=True,
        )
        self.proc = p
        self.key = key
        return p

    async def send_user_frame(self, msg):
        """One turn: one stream-json user frame on stdin.

        Raises what the write raises (BrokenPipeError/ConnectionResetError when
        the process died under us, AttributeError when there is no process) --
        the recovery policy lives at the socket layer.
        """
        self.proc.stdin.write((json.dumps({
            "type": "user",
            "message": {"role": "user",
                        "content": [{"type": "text", "text": msg}]},
        }) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    def clear(self):
        """Forget the process reference after the socket layer has drained and
        reaped it. Deliberately does NOT read or discard pending output --
        hiding unread terminal output here would swallow the very stderr the
        error policy reports."""
        self.proc = None
        self.key = None

    async def demux_turn(self, emit, session_id):
        """Read THIS TURN's events from the persistent process and translate
        them into client frames via `emit` (the websocket's send_json).

        Moved VERBATIM from ws_chat (PLAN-100 S18): the read-until-result
        loop, the stream-json event dispatch, and the frame vocabulary are
        unchanged -- only the send call and the process reference are
        parameterized. Returns (session_id, got_text, got_result,
        result_error, eof); every policy decision on that tuple (stderr
        drain, reap, stop vs error vs replay) stays at the socket layer.
        """
        emit = self._fanout(emit)
        got_text = got_result = False
        result_error = None
        # READ UNTIL THIS TURN'S `result`, not until EOF. The process is
        # persistent now, so EOF only happens when it DIES -- an `async for`
        # over stdout would simply never return.
        eof = False
        while True:
            # readline() is INSIDE the guard. It was outside, so an
            # over-limit line took the whole websocket down instead of
            # costing one dropped frame. The limit above makes this rare;
            # this makes it survivable, because "rare" is not "never" and
            # the failure mode was a dead chat with no error shown.
            try:
                line = await self.proc.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError) as exc:
                await emit({
                    "type": "notice",
                    "text": "one oversized frame from the agent was skipped. "
                            "The answer continues.",
                })
                if not await _drain_to_newline(self.proc.stdout):
                    eof = True
                    break
                continue
            if not line:
                eof = True
                break
            try:
                ev = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            # capture session id from the first event that carries one
            if session_id is None and ev.get("session_id"):
                session_id = ev["session_id"]
                await emit({"type": "session", "id": session_id})
            t = ev.get("type")
            if t == "stream_event":
                delta = (ev.get("event") or {}).get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    got_text = True
                    await emit({"type": "token", "text": delta["text"]})
            elif t == "assistant":
                for blk in (ev.get("message") or {}).get("content", []):
                    # fallback when partial deltas are absent: emit full text blocks
                    if blk.get("type") == "text" and blk.get("text") and not got_text:
                        await emit({"type": "token", "text": blk["text"]})
                    elif blk.get("type") == "thinking":
                        # Presence only. The thinking TEXT is deliberately not
                        # forwarded: it is the model's scratchpad, it is long, and
                        # rendering it as if it were the answer misrepresents both.
                        await emit({"type": "thinking"})
                    elif blk.get("type") == "tool_use":
                        # tool_use blocks never arrive as text deltas, so this must
                        # run regardless of got_text -- gating it behind the text
                        # fallback meant a streaming turn reported zero tool calls.
                        #
                        # phase=start + id: the id is what `tool_result` correlates
                        # against (verified against a real `claude -p` run: tool_use.id
                        # == tool_result.tool_use_id). Without it the UI could show
                        # that a tool was CALLED but never that it finished, so every
                        # tool appeared to run forever.
                        await emit({
                            "type": "tool",
                            "phase": "start",
                            "id": blk.get("id"),
                            "name": blk.get("name", ""),
                            "summary": _tool_summary(blk.get("input")),
                            # Shell commands only, in full -- what "open this in
                            # the terminal" needs. "" for every other tool.
                            "command": _tool_command(blk.get("name", ""),
                                                     blk.get("input")),
                            # Forwarded VERBATIM. Observed {"type":"direct"} for a
                            # main-agent call; other shapes are not guessed at here,
                            # and the client labels whatever actually arrives.
                            "caller": (blk.get("caller") or {}).get("type"),
                        })
            elif t == "user":
                # tool_result lives on USER messages, not assistant ones. This branch
                # did not exist, so every tool result was dropped and completion was
                # unknowable by construction.
                for blk in (ev.get("message") or {}).get("content", []):
                    if isinstance(blk, dict) and blk.get("type") == "tool_result":
                        _out = _tool_output(blk.get("content"))
                        # A BACKGROUND agent's tool_result is a LAUNCH RECEIPT,
                        # not a completion: it arrives immediately, carries the
                        # Agent's tool_use_id, and its content begins "Async
                        # agent launched successfully". Emitting phase:end here
                        # marked the subagent finished the instant it started.
                        # Its REAL completion comes later as a system/
                        # task_notification with the same tool_use_id (handled
                        # in the system branch). Skip the receipt; the tool
                        # stays running until that notification lands. Measured
                        # against claude v2.1.212, stream-json, run_in_background.
                        if _out.strip().startswith("Async agent launched"):
                            continue
                        await emit({
                            "type": "tool",
                            "phase": "end",
                            "id": blk.get("tool_use_id"),
                            "ok": not blk.get("is_error"),
                            # WHAT THE TOOL ACTUALLY RETURNED. This was dropped:
                            # the frame carried {id, ok} and the whole content
                            # array was discarded server-side, so an operator
                            # could see that Read ran and never what it read,
                            # and a failing tool showed a red dot with no reason
                            # attached -- the one thing you need when a turn
                            # goes wrong.
                            "output": _out,
                        })
            elif t == "system":
                # THE FOURTH TYPE THE PARSER NEVER HANDLED. The dispatch knew
                # stream_event / assistant / user / result and silently
                # `continue`d past everything else, so two useful things were
                # invisible:
                #
                #   init      what the session actually resolved -- model,
                #             tool count, mcp servers, plugins. The panel
                #             showed the model it REQUESTED, never the one in
                #             force, and those differ whenever a fallback or
                #             a settings default applies.
                #   api_retry a rate-limit backoff. Claude waits and retries;
                #             with no frame for it the pane sat silent and
                #             the turn read as HUNG. "Waiting, retrying" and
                #             "wedged" look identical when nothing is sent.
                sub = ev.get("subtype")
                if sub == "init":
                    await emit({
                        "type": "sysinit",
                        "model": ev.get("model"),
                        "tools": len(ev.get("tools") or []),
                        "mcp_servers": [
                            {"name": m.get("name"), "status": m.get("status")}
                            for m in (ev.get("mcp_servers") or [])
                            if isinstance(m, dict)],
                        "slash_commands": len(ev.get("slash_commands") or []),
                        "permission_mode": ev.get("permissionMode"),
                        "cwd": ev.get("cwd"),
                    })
                elif sub == "api_retry":
                    await emit({
                        "type": "retrying",
                        "detail": str(ev.get("message") or ev.get("error")
                                      or "the API asked us to retry")[:300],
                        "attempt": ev.get("attempt"),
                    })
                elif sub == "task_notification":
                    # THE REAL completion of a background agent. Its receipt
                    # tool_result was skipped above, so the UI shows the agent
                    # running until THIS frame -- which carries the same
                    # tool_use_id the UI opened the tool with, plus the summary
                    # and usage the receipt never had. task_started/task_progress
                    # fire while it runs and are intentionally not forwarded (the
                    # tool row already reads "running"); only the terminal
                    # notification closes it. Measured shape: {tool_use_id,
                    # status, summary, usage{...}}.
                    status = ev.get("status") or "completed"
                    tuid = ev.get("tool_use_id")
                    if tuid and status in ("completed", "failed", "cancelled"):
                        await emit({
                            "type": "tool",
                            "phase": "end",
                            "id": tuid,
                            "ok": status == "completed",
                            "output": str(ev.get("summary") or "")[:4000],
                        })
            elif t == "result":
                got_result = True
                # A `result` event is NOT proof of success: a failed run (stale
                # --resume, permission abort, API error) emits one with
                # is_error/subtype set and THEN exits non-zero. Sending "done"
                # here painted a failed turn as answered-with-empty-text, and the
                # real error arrived a frame later -- where the client attributed
                # it to whatever turn came next. Hold it and report once, below.
                if ev.get("is_error") or (ev.get("subtype") or "success") != "success":
                    result_error = str(ev.get("result") or ev.get("subtype")
                                       or "claude reported an error")[:600]
                else:
                    # Carry the REAL measurements the result frame already has, so
                    # the UI states duration and cost instead of estimating them.
                    await emit({
                        "type": "done",
                        "session": session_id,
                        "duration_ms": ev.get("duration_ms"),
                        "num_turns": ev.get("num_turns"),
                        "cost_usd": ev.get("total_cost_usd"),
                    })
                # `result` closes THIS TURN. The process stays up for the
                # next one -- that is the whole point of the change.
                break
        return session_id, got_text, got_result, result_error, eof
