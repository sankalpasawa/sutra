"""`codex exec --json` transport for a chat pane's agent subprocess -- the third
counterpart to session_runtime.py (Claude, stream-json) and acp_runtime.py
(DeepSeek, ACP).

Everything below was MEASURED against codex-cli 0.153.2 on 2026-09-08, by
running real turns into a throwaway CODEX_HOME so the operator's live
credential was never touched. Where a fact could not be measured it is named as
unmeasured rather than guessed -- the same standard acp_runtime.py holds itself
to, and for the same reason: a convincing wrong answer about a provider's wire
format costs more than an absent one.

WHY A THIRD MODULE AND NOT AN ARM OF ONE OF THE OTHER TWO
---------------------------------------------------------
Neither existing transport fits, and forcing one would mean editing a working
provider's file:

  - session_runtime.SessionRuntime speaks Claude's `--output-format
    stream-json` and keeps ONE PROCESS ACROSS MANY TURNS, fed user frames on a
    persistent stdin.
  - acp_runtime.AcpRuntime speaks JSON-RPC over a persistent stdio pipe, with
    session/new + session/prompt as separate round trips.
  - `codex exec` is ONE PROCESS PER TURN. It reads the prompt, streams JSONL to
    stdout, and EXITS. Continuity comes from re-spawning with `resume <id>`.

The lifecycle members below (alive / kill_group / stop / clear / subscribe /
_fanout / _observe) are duplicated from SessionRuntime rather than shared,
exactly as AcpRuntime.kill_group duplicates it and says so. The duplication is
the point: nothing in this file can change Claude's or DeepSeek's behaviour,
because nothing in those files is edited or subclassed. Only two genuinely
provider-neutral helpers are imported -- `_drain_to_newline` (an asyncio
stream-limit workaround) and `TurnQueue` -- which is precisely what
acp_runtime.py already imports from there.

THE PROCESS IS ONE-SHOT, AND THAT IS WHY THIS FILE LOOKS SIMPLER
----------------------------------------------------------------
There is no session/new to make, no authenticate step, and no permission-mode
round trip: every one of those is spawn-time argv for codex (see
build_codex_args in app.py). `prompt_turn` therefore covers the whole turn --
write the prompt, read to a terminal event, reap -- and returns the SAME
5-tuple as SessionRuntime._demux_turn_inner and AcpRuntime.prompt_turn, so
ws_chat's bookkeeping needs no third code path.

Because the process exits per turn, ws_chat's `if not alive:` arm re-spawns on
every message. That is the loop's existing behaviour for a dead process, not a
new mechanism, and it is why `resume` can be baked into the argv the reuse test
compares: the process is never alive at the top of the next turn, so the
spawn_key comparison cannot mis-fire the way it did for Claude's --resume.

MEASURED WIRE FORMAT (codex-cli 0.153.2, 2026-09-08)
----------------------------------------------------
stdout is PURE JSONL -- 0 unparseable lines across 5 probe runs. Every human
string codex prints (`Reading additional input from stdin...`, and its
`ERROR codex_api::endpoint::responses_websocket:` tracing) goes to STDERR.
So this module parses stdout only and never treats stderr as fatal: stderr
carries retry noise even on turns that SUCCEED.

    {"type":"thread.started","thread_id":"01a08191-7175-7f62-bf84-14f3871ef8a0"}
    {"type":"turn.started"}
    {"type":"item.completed","item":{"id":"item_0","type":"agent_message",
                                     "text":"Running the requested command."}}
    {"type":"item.started","item":{"id":"item_1","type":"command_execution",
        "command":"/bin/zsh -lc 'echo hello'","aggregated_output":"",
        "exit_code":null,"status":"in_progress"}}
    {"type":"item.completed","item":{"id":"item_1","type":"command_execution",
        "command":"/bin/zsh -lc 'echo hello'","aggregated_output":"hello\\n",
        "exit_code":0,"status":"completed"}}
    {"type":"turn.completed","usage":{"input_tokens":29582,
        "cached_input_tokens":25088,"cache_write_input_tokens":0,
        "output_tokens":133,"reasoning_output_tokens":14}}

THERE ARE NO TEXT DELTAS ON THIS SURFACE, and that is a measurement, not an
omission: 0 delta events and 0 `item.updated` across 3 authenticated turns / 18
events, including a 14-second command emitting output throughout. Assistant
text arrives ONLY as `item.completed` / `agent_message`, carrying the COMPLETE
`item.text`.

  => ONE `token` frame per agent_message, holding the whole message.
  => There is no double-render risk to defend against, because there is nothing
     to duplicate. Do NOT add speculative `item.updated` handling for
     agent_message to guard against a delta stream that does not exist; that
     branch would be dead code pretending to be a safeguard.
  => Deltas DO exist on `codex app-server`, which is flagged [experimental] by
     OpenAI. Deliberately not used here.

A pane therefore shows `thinking`, then whole messages. This differs visibly
from Claude's token stream and is the accepted v1 trade.
"""
import asyncio
import json
import os
import signal

from session_runtime import _drain_to_newline, _tool_output, _tool_summary, TurnQueue

#: How long to wait for a one-shot `codex exec` to exit after it emitted a
#: terminal event, before killing its group. It has already answered by this
#: point, so this only bounds teardown -- but it must exist: a process left
#: running per turn is a leak the operator cannot see.
CODEX_EXIT_TIMEOUT = 5

#: What `item.status` means "this command is finished". Read off the measured
#: payloads; `in_progress` is the only other value seen.
_TOOL_DONE_STATUSES = ("completed", "failed")

#: The item types this build TRANSLATES. The full ThreadItem union in the
#: 0.153.2 binary also carries `reasoning`, `file_change`, `mcp_tool_call`,
#: `web_search` and `todo_list`; only the two below plus `error` were ever
#: observed on the wire, so the rest are DROPPED rather than guessed at -- the
#: same policy acp_runtime._translate_update applies to plan /
#: available_commands_update.
#:
#: `reasoning` is the interesting absence. `turn.completed.usage` reported
#: reasoning_output_tokens of 14 and 27 on the two probe turns, and the on-disk
#: rollout DOES carry `response_item/reasoning` records -- but nothing reached
#: stdout, with -c show_raw_agent_reasoning=true, -c
#: model_reasoning_summary=detailed and -c hide_agent_reasoning=false all set.
#: So the model's reasoning is recorded by codex and not published on this
#: surface. `thinking` is emitted from turn.started instead (see prompt_turn).
_TRANSLATED_ITEM_TYPES = ("agent_message", "command_execution")


class CodexRuntime:
    """Owns exactly one `codex exec` subprocess for one turn of one chat pane.

    Field meanings are kept identical to SessionRuntime's so the socket layer
    reads the same on all three transports:

      proc     the subprocess, or None. One-shot: dead once the turn ends.
      key      the argv tuple ws_chat's reuse test compares.
      stopped  the OPERATOR pressed stop. Never set for generic process death.
    """

    def __init__(self):
        self.proc = None
        self.key = None
        self.stopped = False
        self.state = "idle"
        #: The codex thread id, adopted from `thread.started`. Survives across
        #: the per-turn process deaths -- it is what `resume` is built from.
        self.session_id = None
        self.subscribers = []
        self.open_tools = set()
        self.turn_queue = TurnQueue()
        self.queue_event = asyncio.Event()
        self._emit = None            # the CURRENT turn's emit, per prompt_turn
        self._got_text = False
        #: The most recent NON-FATAL warning codex reported as an
        #: `item.type == "error"` item. Kept so a `turn.failed` that arrives
        #: with an empty message has something true to say, and so the reason
        #: is not simply lost. Never emitted as an error frame on its own.
        self.last_warning = None

    # ------------------------------------------------------------ lifecycle --
    # alive / kill_group / clear are IDENTICAL to SessionRuntime's -- the same
    # process-group semantics apply to any subprocess, and AcpRuntime already
    # duplicates them for the same reason. Copied rather than imported so this
    # provider cannot be changed by an edit to Claude's file.

    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    def kill_group(self):
        """Kill the process GROUP, not just the direct child.

        `codex exec` spawns the model's shell commands as children (measured:
        `/bin/zsh -lc '...'`), so signalling only the parent leaves them
        holding the stdout pipe and the read loop never ends. spawn() uses
        start_new_session=True to make the child a group leader. Idempotent.
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

    def stop(self):
        """The OPERATOR pressed stop: record the intent, THEN kill.

        Order matters for the same reason it does in SessionRuntime.stop -- the
        stdout loop can end between the signal and the assignment, and would
        then report the operator's own interrupt as a crash.

        There is no in-band cancel to try first (unlike ACP's session/cancel):
        `codex exec` has no control channel, its stdin is already closed by the
        time a turn is streaming, and killing the group is the only interrupt.
        Measured 2026-09-08: SIGTERM mid-turn ends stdout with NO terminal
        event, which prompt_turn reports as eof -- and ws_chat's existing
        `if rt.stopped:` branch turns that into a `stopped` frame while keeping
        session_id, so the next message resumes the same thread.
        """
        self.stopped = True
        self.state = "stopped"
        if self.turn_queue is not None:
            self.turn_queue.clear_shadow()
        return self.kill_group()

    def clear(self):
        """Forget the process reference. Deliberately does NOT touch
        session_id: the codex thread outlives every process that served it,
        and dropping it here would silently start a new conversation on the
        next message."""
        self.proc = None
        self.key = None

    # ------------------------------------------------------------ observers --
    # Same contract as SessionRuntime: the websocket's send_json is the PRIMARY
    # emit and its exceptions propagate; subscribers are additional observers
    # and a broken one is dropped per frame rather than costing a turn.

    def subscribe(self, cb):
        self.subscribers.append(cb)
        return cb

    def unsubscribe(self, cb):
        try:
            self.subscribers.remove(cb)
        except ValueError:
            pass

    def _observe(self, frame):
        """Update coarse turn state from a frame passing through the fanout.
        Purely mechanical, no policy -- mirrors SessionRuntime._observe so
        Shadow's state machine reads the same on a Codex pane."""
        t = frame.get("type")
        if t == "retrying":
            self.state = "retrying"
        elif t in ("token", "sysinit", "session", "thinking"):
            if self.state != "stopped":
                self.state = "active"
        elif t == "tool":
            if self.state != "stopped":
                self.state = "active"
            if frame.get("phase") == "start" and frame.get("id"):
                self.open_tools.add(frame["id"])
            elif frame.get("phase") == "end" and frame.get("id"):
                self.open_tools.discard(frame["id"])
        elif t == "_turn_boundary":
            if self.state != "stopped":
                self.state = "idle"
            self.open_tools.clear()

    async def _notify_subscribers(self, frame):
        self._observe(frame)
        for cb in list(self.subscribers):
            try:
                res = cb(frame)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def _fanout(self, primary):
        """Wrap the primary emit with subscriber fan-out. Snapshot per FRAME,
        so an observer attaching mid-turn starts seeing frames then."""
        async def emit(frame):
            self._observe(frame)
            await primary(frame)
            for cb in list(self.subscribers):
                try:
                    res = cb(frame)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
        return emit

    # ---------------------------------------------------------------- spawn --

    async def spawn(self, args, cwd, key, env=None):
        """Start the one-shot process and adopt it as self.proc.

        Same signature and same failure policy as SessionRuntime.spawn: on
        OSError nothing is assigned and the error policy stays at the socket
        layer.

        stdin is a PIPE because the PROMPT ARRIVES ON IT. build_codex_args ends
        the argv with `-`, codex's documented "read instructions from stdin"
        form, and send_prompt writes the message there and closes it. The
        prompt is deliberately NOT an argv element: `switch.py` exists because
        a provider-switch payload delivered positionally dies at exec with
        E2BIG (hence ARGV_SAFETY_FRACTION), and stdin has no such ceiling --
        the same reason Claude uses a stdin frame rather than `claude -p <msg>`.

        limit=8 MiB for the same measured reason session_runtime gives: one
        JSON object per line, and a `command_execution` item's
        aggregated_output can carry a whole verbose capture. asyncio's 64 KiB
        default raises "Separator is not found, and chunk exceed the limit",
        which would kill the socket mid-answer.
        """
        p = await asyncio.create_subprocess_exec(
            *args, cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=8 * 1024 * 1024,
            env=dict(os.environ, **(env or {})),
            start_new_session=True,
        )
        self.proc = p
        self.key = key
        return p

    async def send_prompt(self, msg):
        """Deliver the turn's prompt on stdin and CLOSE the stream.

        The close is not optional. `codex exec -` reads instructions until EOF,
        so a stdin left open hangs the turn before the model is ever called --
        the process would sit waiting for input that never comes and the pane
        would look wedged with no error.

        Raises what the write raises (BrokenPipeError / ConnectionResetError
        when the process died under us, AttributeError when there is no
        process); the recovery policy lives at the socket layer, exactly as it
        does for SessionRuntime.send_user_frame.
        """
        self.proc.stdin.write(msg.encode("utf-8"))
        await self.proc.stdin.drain()
        # write_eof() rather than close(): close() on some platforms tears the
        # transport down hard enough to race the drain above.
        try:
            self.proc.stdin.write_eof()
        except (AttributeError, OSError, RuntimeError):
            # A transport that cannot signal EOF is closed outright -- codex
            # needs the EOF far more than we need a graceful shutdown here.
            try:
                self.proc.stdin.close()
            except Exception:
                pass

    # ----------------------------------------------------------- translation --

    async def _emit_agent_message(self, item):
        """One `token` frame carrying the COMPLETE message text.

        Not a simulated stream. There are no deltas on this surface (see the
        module header), and chopping the text up here to imitate Claude would
        invent a progress signal the transport never gave us.
        """
        text = item.get("text")
        if not isinstance(text, str) or not text:
            return
        self._got_text = True
        await self._emit({"type": "token", "text": text})

    async def _emit_tool_start(self, item):
        tool_id = item.get("id")
        if not tool_id or tool_id in self.open_tools:
            return
        command = item.get("command")
        command = command if isinstance(command, str) else ""
        await self._emit({
            "type": "tool",
            "phase": "start",
            "id": tool_id,
            # The item type IS the tool name here. codex has no per-tool names
            # on this surface, so inventing "Bash" would assert a Claude tool
            # identity that nothing sent us.
            "name": item.get("type") or "",
            # Through the SAME helper Claude's tool frames use, so the summary
            # is whitespace-collapsed and capped identically rather than by a
            # second rule that could drift.
            "summary": _tool_summary({"command": command}),
            # In FULL -- this is the one field the operator may legitimately
            # want to re-run by hand, and it is the shell command verbatim.
            "command": command,
            # codex publishes no caller/agent attribution on this surface.
            "caller": None,
        })

    async def _emit_tool_end(self, item):
        tool_id = item.get("id")
        if not tool_id:
            return
        exit_code = item.get("exit_code")
        status = item.get("status")
        # BOTH signals, because either alone is wrong. A `failed` status with
        # exit_code None (a command codex never managed to run) and an
        # exit_code 3 with status `completed` (it ran and the command itself
        # failed) are both failures the operator has to see.
        ok = (status == "completed") and (exit_code == 0 or exit_code is None)
        await self._emit({
            "type": "tool",
            "phase": "end",
            "id": tool_id,
            "ok": ok,
            # BEST-EFFORT DISPLAY DATA, capped through the same helper Claude's
            # tool_result output goes through.
            #
            # MEASURED TO BE LOSSY, 2026-09-08: a command printing
            # line1/line2/line3 came back as "line2\nline3\n" -- line1 was
            # silently dropped. Cause unknown. So this is shown to the
            # operator and must never be treated as authoritative command
            # history, and nothing downstream may parse it for meaning.
            "output": _tool_output(item.get("aggregated_output")),
        })

    async def _translate_item(self, kind, item):
        """One `item.*` event -> zero or more client frames."""
        if not isinstance(item, dict):
            return
        itype = item.get("type")

        if itype == "error":
            # NON-FATAL, and deliberately not an error frame. Measured
            # instances are diagnostics, not turn outcomes: "Model metadata for
            # `x` not found. Defaulting to fallback metadata" and "Falling back
            # from WebSockets to HTTPS transport" -- both arrived on turns that
            # then ran normally. Turning either into result_error would fail a
            # working turn. Retained for a turn.failed that carries no message
            # of its own.
            msg = item.get("message")
            if isinstance(msg, str) and msg.strip():
                self.last_warning = msg.strip()[:600]
            return

        if itype not in _TRANSLATED_ITEM_TYPES:
            # An unmeasured item type is DROPPED, not guessed at. See
            # _TRANSLATED_ITEM_TYPES for the full union and which are absent.
            return

        if itype == "agent_message":
            # `item.completed` ONLY. item.started/updated for a message carry
            # no text on this build and were never observed at all; handling
            # them would be the double-render bug this comment prevents.
            if kind == "item.completed":
                await self._emit_agent_message(item)
            return

        # command_execution
        if kind == "item.started":
            await self._emit_tool_start(item)
        elif kind == "item.completed":
            await self._emit_tool_end(item)
        # item.updated: never observed on this build, including across a
        # 14-second command that emitted output throughout. Dropped rather
        # than handled speculatively.

    # ------------------------------------------------------------------ turn --

    async def prompt_turn(self, msg, emit, session_id=None):
        """The whole turn: write the prompt, translate stdout, reap.

        The Codex analogue of SessionRuntime.send_user_frame() + demux_turn()
        COMBINED -- and of AcpRuntime.prompt_turn, whose signature and 5-tuple
        this matches exactly:

            (session_id, got_text, got_result, result_error, eof)

        so ws_chat's stderr/rc reap, stop handling, chat_store bookkeeping and
        failure/replay policy all run unchanged.

        WHAT THE TUPLE MEANS HERE:
          terminal event seen   -> got_result=True, eof=False. This runtime
                                   reaps the one-shot process itself, because
                                   ws_chat only reaps on eof and a per-turn
                                   process left unwaited is a zombie per
                                   message.
          stdout ended first    -> got_result=False, eof=True. NOT reaped here
                                   on purpose: ws_chat's eof arm drains stderr,
                                   waits for the rc and clears, and that is the
                                   path whose diagnostics an operator needs.
        """
        self._emit = self._fanout(emit)
        self._got_text = False
        self.last_warning = None
        if not self.stopped:
            self.state = "active"

        got_result = False
        result_error = None
        eof = False

        try:
            await self.send_prompt(msg)
        except (BrokenPipeError, ConnectionResetError, AttributeError) as exc:
            # The process died between ws_chat's liveness check and this write.
            # Reported as eof so the socket layer's existing dead-process path
            # (stderr drain, rc, clear) runs and the operator sees the cause.
            await self._notify_subscribers({
                "type": "_turn_boundary", "session": session_id,
                "got_result": False,
                "error": "the codex process closed before the prompt was sent (%s)" % exc,
                "eof": True})
            return session_id, False, False, None, True

        while True:
            # readline() INSIDE the guard, for session_runtime's measured
            # reason: an over-limit line must cost one dropped frame, not the
            # whole websocket.
            try:
                line = await self.proc.stdout.readline()
            except (asyncio.LimitOverrunError, ValueError):
                if not await _drain_to_newline(self.proc.stdout):
                    eof = True
                    break
                continue
            except (AttributeError, ConnectionResetError):
                eof = True
                break
            if not line:
                eof = True
                break
            try:
                ev = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                # stdout measured as pure JSONL across every probe run, so this
                # should not happen -- skipped rather than trusted if it does.
                continue
            if not isinstance(ev, dict):
                continue

            etype = ev.get("type")

            if etype == "thread.started":
                # ALWAYS THE FIRST LINE, on a cold start AND on a resume, and
                # measured to be the SAME id when resuming (probe T2 resumed T1
                # and reported an identical thread_id). So it is adopted
                # unconditionally -- there is no new-vs-resumed case to tell
                # apart, which is a stronger contract than Claude's mid-stream
                # session id.
                tid = ev.get("thread_id")
                if isinstance(tid, str) and tid:
                    session_id = tid
                    self.session_id = tid
                    await self._emit({"type": "session", "id": tid})

            elif etype == "turn.started":
                # No payload at all on this surface -- no turn id, nothing.
                # Used for the one thing it can honestly say: work has begun.
                # This is also the ONLY `thinking` signal a Codex pane gets,
                # because reasoning items never reach stdout (module header),
                # and without it the pane sits blank until the first whole
                # message lands.
                await self._emit({"type": "thinking"})

            elif etype in ("item.started", "item.updated", "item.completed"):
                await self._translate_item(etype, ev.get("item"))

            elif etype == "error":
                # TRANSIENT. Measured: "Reconnecting... 2/5 (...)", emitted up
                # to five times per transport and across two transports
                # (WebSocket then HTTPS) on a single turn that had not yet
                # failed. THE TURN CONTINUES. Mapping this to an error frame
                # would end a turn that codex is still retrying, and would do
                # it up to ten times.
                #
                # `retrying` is the existing frame for exactly this: the client
                # stores the latest on the turn (01-state.js), so repeats
                # overwrite rather than accumulate, and _observe moves the pane
                # to the "retrying" state.
                detail = ev.get("message")
                await self._emit({
                    "type": "retrying",
                    "detail": str(detail or "codex is retrying")[:300],
                    # codex publishes no attempt counter as a field; the count
                    # is inside the message text. Not parsed out of prose.
                    "attempt": None,
                })

            elif etype == "turn.completed":
                got_result = True
                await self._emit({
                    "type": "done",
                    "session": session_id,
                    # codex reports NEITHER on this surface. Sent as None for
                    # the same reason DeepSeek's done frame does: the client
                    # renders an absent figure rather than borrowing another
                    # provider's.
                    "duration_ms": None,
                    "num_turns": None,
                    "cost_usd": None,
                    # Per-turn token counts, forwarded field by field rather
                    # than verbatim -- same policy as acp_runtime._extract_quota
                    # and deepseek_usage.sanitize: a key this build has not been
                    # taught to read must not reach a client frame just because
                    # codex added it.
                    "quota": _extract_usage(ev.get("usage")),
                })
                break

            elif etype == "turn.failed":
                # TERMINAL, and the message is NESTED under .error -- unlike
                # the transient top-level `error` event above, whose message is
                # flat. Confusing the two is the single easiest bug here.
                err = ev.get("error")
                msg_text = err.get("message") if isinstance(err, dict) else None
                if not (isinstance(msg_text, str) and msg_text.strip()):
                    # Nothing usable in the failure itself: fall back to the
                    # last non-fatal warning, which on a bad-credential turn is
                    # the line that actually explains it.
                    msg_text = self.last_warning or "codex reported turn.failed"
                result_error = str(msg_text)[:600]
                got_result = True
                break

            # Any other top-level type is dropped -- same policy as the item
            # union above.

        if got_result:
            await self._reap()

        # Tools cannot outlive the turn that opened them. Cleared here as well
        # as in _observe's _turn_boundary arm, because an interrupted turn may
        # never reach a boundary frame through the fanout.
        self.open_tools.clear()

        await self._notify_subscribers({
            "type": "_turn_boundary",
            "session": session_id,
            "got_result": got_result,
            "error": result_error,
            "eof": eof,
        })
        if not self.stopped:
            self.state = "idle"
        return session_id, self._got_text, got_result, result_error, eof

    async def _reap(self):
        """Wait for the one-shot process to exit, killing it if it will not.

        Only called after a TERMINAL event, where codex has already answered
        and is on its way out. ws_chat reaps only on eof, so without this a
        successful turn would leave an unwaited child per message.
        """
        p = self.proc
        if p is None or p.returncode is not None:
            return
        try:
            await asyncio.wait_for(p.wait(), CODEX_EXIT_TIMEOUT)
        except (asyncio.TimeoutError, Exception):
            self.kill_group()
            try:
                await asyncio.wait_for(p.wait(), 2)
            except Exception:
                pass


def _extract_usage(usage):
    """This turn's token counts, or None.

    Measured shape (0.153.2): {input_tokens, cached_input_tokens,
    cache_write_input_tokens, output_tokens, reasoning_output_tokens}. PER
    TURN, not cumulative, and with NO dollar figure and no duration anywhere in
    it -- which is why the provider declares usage_kind "none" and this rides
    on the done frame only as a detail.

    Field by field, ints only. A string or a nested object arriving under a key
    this build knows would otherwise reach a client frame unvalidated.
    """
    if not isinstance(usage, dict):
        return None
    out = {}
    for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens"):
        val = usage.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, int):
            out[key] = val
    return out or None
