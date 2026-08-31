"""ACP (Agent Client Protocol) transport for a chat pane's agent subprocess --
the counterpart to session_runtime.py for any ACP-speaking CLI (DeepSeek's
`deepseek --acp` today; any other Gemini-CLI fork tomorrow, since the wire
format is the vendor's, not DeepSeek's).

NOT WIRED INTO ws_chat YET. Nothing imports this module. Wiring means:
  - app.py's provider dispatch branching on active_id ("claude" -> SessionRuntime,
    "deepseek" -> AcpRuntime)
  - a build_acp_args() alongside build_agent_args() (likely just [bin, "--acp"])
  - "deepseek" added to providers.ADAPTERS
  - sourcing DEEPSEEK_API_KEY and refusing cleanly if absent, mirroring the
    ANTHROPIC_API_KEY check already in ws_chat -- that check belongs at the
    call site, not in this transport-agnostic module
All deferred on purpose: this file is the transport + frame-translation logic
only, reviewed before any of the above touches a live code path.

Schema facts below were read directly out of the installed CLI
(@sluisr/deepseek-cli@1.3.2, an unminified esbuild bundle -- identifiers and
source comments survive), not the public ACP spec, and confirmed live: an
empty `{}` permission reply throws Zod validation inside the CLI and comes
back as a failed tool_call_update; the schema below is what actually turns
that into a completed one.
"""
import asyncio
import itertools
import json
import os
import signal

from session_runtime import _drain_to_newline, TurnQueue


# session/new returns {modes: {availableModes: [{id, name}, ...], currentModeId}}.
# These ids are the CLI's own --approval-mode values (verified at the argv
# parser: choices are default/auto_edit/yolo/plan) -- DeepSeek's native
# equivalent of Claude's --permission-mode flag. Setting this at session
# start means plan/acceptEdits/bypassPermissions need ZERO runtime-side
# request_permission handling; only what falls through still asks.
_ACP_MODE_FOR_PERMISSION_MODE = {
    "plan": "plan",
    "acceptEdits": "auto_edit",
    "bypassPermissions": "yolo",
    # dontAsk / auto / manual: no ACP-native equivalent. "default" is what's
    # left, which means the CLI asks about everything -- the fallback below
    # has to actually decide, because nothing upstream already did.
}
_DEFAULT_ACP_MODE = "default"

# Verified PermissionOption.kind values (zPermissionOptionKind) and the
# concrete optionId strings the CLI actually sends (ToolConfirmationOutcome
# enum: proceed_once/proceed_always/proceed_always_and_save/
# proceed_always_server/proceed_always_tool/cancel). We match on `kind`,
# never on the optionId string, because the "always" variant offered differs
# by tool -- picking the first option whose kind is in the wanted set is
# stable across all of them.
_ALLOW_KINDS = ("allow_once", "allow_always")
_REJECT_KINDS = ("reject_once", "reject_always")

# Claude's -p runs pre-allow mcp__sutra__* unconditionally (build_agent_args
# in app.py): a -p run has nobody to answer a permission prompt, so it would
# just stall, and the mutating sutra tools only ever write an inert proposal
# -- safe to wave through regardless of mode. DeepSeek's ACP layer surfaces
# the same prompt instead of swallowing it, so it needs the same carve-out.
#
# What identifies "this tool call is a sutra one" on the wire: NOT much.
# Read directly out of the installed CLI (@sluisr/deepseek-cli@1.3.2,
# bundle/chunk-UNFT3LTQ.js): the `params` object built for
# session/request_permission (bundle/gemini-RIEFLUTB.js ~14350) sets only
# toolCallId/status/title/content/locations/kind -- no server name, no
# rawInput, nothing in `_meta`. The one place server identity leaks through
# is `title`: DiscoveredMCPToolInvocation.getDisplayTitle() returns
# `this.displayName || this.serverToolName` (chunk-UNFT3LTQ.js ~285343),
# and displayName is built as "${serverToolName} (${serverName} MCP
# Server)" -- UNLESS the call's own params carry a "command" key, which
# shadows it entirely (getDisplayTitle special-cases that). None of
# sutra_mcp.py's tool schemas define a "command" parameter, so that
# collision doesn't hit us today, but this is a display string from one
# CLI build, not a protocol-level identifier -- it can silently stop
# matching on a CLI upgrade. serverName here must equal the "name" field
# _sutra_acp_mcp_servers() (app.py) puts in the mcpServers entry.
_SUTRA_MCP_TITLE_SUFFIX = " (sutra MCP Server)"


def _choose_permission_option(effective_permission_mode, tool_kind, options,
                              tool_title=None):
    """One offered option's optionId to answer `session/request_permission`
    with, or None to send `{"outcome":{"outcome":"cancelled"}}` instead.

    Only reached when the CLI decided to ask despite the session mode
    already set (a shell command under auto_edit; anything at all under
    `default`). Mirrors the axis Claude's own CLI already resolves
    invisibly under --permission-mode -- this is that resolution made
    explicit, because DeepSeek's ACP layer surfaces the ask instead of
    swallowing it internally.
    """
    if isinstance(tool_title, str) and tool_title.endswith(_SUTRA_MCP_TITLE_SUFFIX):
        approve = True
    elif effective_permission_mode == "bypassPermissions":
        approve = True
    elif effective_permission_mode == "acceptEdits":
        # PERMISSION_MODE_NOTES already documents acceptEdits as covering
        # create/modify/delete -- "move" tracked alongside since it's the
        # same file-mutation shape and zToolKind lists it separately.
        approve = tool_kind in ("edit", "delete", "move")
    else:
        # plan / dontAsk / auto / manual: declined, not escalated -- the
        # same wording PERMISSION_MODE_NOTES already uses for dontAsk, and
        # for the same reason (no live approval channel to the browser yet).
        approve = False
    wanted = _ALLOW_KINDS if approve else _REJECT_KINDS
    for opt in options:
        if isinstance(opt, dict) and opt.get("kind") in wanted:
            return opt.get("optionId")
    return None


def _content_text(content, limit=4000):
    """Flatten a ToolCallUpdate's `content` array (zToolCallContent: "content"
    wraps a {type:"text",text}; "diff" carries path/oldText/newText; "terminal"
    carries a terminalId) into display text for the `tool` end frame's
    `output` field. Distinct from session_runtime._tool_output: that helper
    flattens Claude's tool_result content shape, which is one level flatter
    than ACP's -- reusing it here would silently drop every ACP item.
    Same truncation policy (explicit, not silent) for consistency.
    """
    if not content:
        return None
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "content":
            inner = item.get("content") or {}
            if inner.get("type") == "text" and inner.get("text"):
                parts.append(str(inner["text"]))
        elif t == "diff":
            parts.append("[diff] %s" % item.get("path", "?"))
        elif t == "terminal":
            parts.append("[terminal output]")
    text = "\n".join(parts).strip()
    if not text:
        return None
    if len(text) > limit:
        return text[:limit] + ("\n… truncated, %d more characters"
                               % (len(text) - limit))
    return text


class AcpRuntime:
    """Owns one ACP agent subprocess for one chat channel.

    Duck-type peer of SessionRuntime -- same .alive / .stop() / .kill_group()
    / .subscribe() / .clear() surface, same _turn_boundary contract via
    _notify_subscribers -- so a future dispatch table in app.py can hold
    either kind of runtime without app.py branching on which one it has.
    Not a subclass: the wire format is different enough (JSON-RPC,
    full-duplex on one stream) that inheriting from SessionRuntime would
    mean overriding every method anyway -- see the design-turn plan.

    CORRECTION (post-wiring): turn_queue/queue_event were NOT optional --
    ws_chat's main loop reads them unconditionally on every pass
    (`len(rt.turn_queue)`, `rt.queue_event.wait()`), for every provider, not
    just when Shadow enqueues something. Missing them crashed every single
    DeepSeek message with AttributeError, not just a Shadow edge case.
    Reused verbatim from session_runtime.TurnQueue rather than
    reimplemented -- it's already the exact class the loop expects.
    """

    def __init__(self):
        self.proc = None
        self.key = None
        self.stopped = False
        self.state = "idle"
        self.session_id = None
        self.effective_permission_mode = None
        self.acp_mode = None
        self.agent_capabilities = {}
        self.subscribers = []
        self._id_seq = itertools.count(1)
        self._pending = {}          # request id -> asyncio.Future
        self._reader_task = None
        self._emit = None           # the CURRENT turn's emit; reassigned per prompt_turn
        self._got_text = False
        self._open_tools = set()
        self.turn_queue = TurnQueue()
        self.queue_event = asyncio.Event()

    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    def kill_group(self):
        """Identical to SessionRuntime.kill_group -- same process-group
        semantics apply to any subprocess, ACP or not."""
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
        """The operator pressed stop. Unlike Claude (no in-band cancel),
        ACP has one: try it first for a clean agent-side abort, then kill
        the group regardless -- a hung or ignored cancel must not leave the
        process running."""
        self.stopped = True
        self.state = "stopped"
        self.turn_queue.clear_shadow()
        if self.session_id:
            asyncio.ensure_future(
                self._notify("session/cancel", {"sessionId": self.session_id}))
        return self.kill_group()

    def clear(self):
        self.proc = None
        self.key = None

    def subscribe(self, cb):
        self.subscribers.append(cb)
        return cb

    def unsubscribe(self, cb):
        try:
            self.subscribers.remove(cb)
        except ValueError:
            pass

    async def _notify_subscribers(self, frame):
        for cb in list(self.subscribers):
            try:
                res = cb(frame)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def _fanout(self, primary):
        """Wrap a turn's primary emit with subscriber fan-out -- mirrors
        SessionRuntime._fanout (session_runtime.py) so Shadow's observer
        (shadow_runner.attach_observer) sees every frame type, not just the
        _turn_boundary ones prompt_turn already pushes via
        _notify_subscribers directly. Without this, subscribers never saw a
        "token" frame: _RECENT_TEXT (mission live-text preview) stayed empty
        for a DeepSeek target, and _LAST_FRAME_TS (stall detection) only
        advanced at turn start/end instead of continuously -- a long single
        ACP turn (session/prompt is one request/response, not Claude's
        multi-frame demux) could false-positive a stall mid-turn.

        No _observe call here (unlike SessionRuntime's version): AcpRuntime
        already sets self.state directly at each transition rather than
        inferring it from frames passing through.
        """
        async def emit(frame):
            await primary(frame)
            for cb in list(self.subscribers):
                try:
                    res = cb(frame)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
        return emit

    # ------------------------------------------------------------- wire --

    async def _call(self, method, params=None):
        """Send a JSON-RPC request, return the raw response dict (carrying
        either `result` or `error`) once _reader_loop resolves its Future.
        Never raises for an `error` response -- callers decide policy per
        call site. Raises ConnectionResetError if the process dies first."""
        req_id = next(self._id_seq)
        fut = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()
        return await fut

    async def _notify(self, method, params=None):
        """Fire-and-forget JSON-RPC notification (no id, no response)."""
        if not self.alive:
            return
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, AttributeError):
            pass

    async def _reader_loop(self):
        """One background task for the process's WHOLE LIFE, not per turn.

        Claude's demux_turn gets away with one read loop per turn because
        stream-json is single-topic -- nothing else talks on that pipe
        while a turn's `result` is pending. ACP is full-duplex on the SAME
        pipe: session/request_permission can arrive *before*
        session/prompt's response. A per-turn loop would have nothing
        reading the pipe between turns, so a permission ask arriving then
        would hang the agent forever.
        """
        while True:
            try:
                line = await self.proc.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError):
                if self._emit is not None:
                    await self._emit({"type": "notice", "text":
                        "one oversized frame from the agent was skipped."})
                if not await _drain_to_newline(self.proc.stdout):
                    self._on_eof()
                    return
                continue
            if not line:
                self._on_eof()
                return
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                fut = self._pending.pop(msg["id"], None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
                continue
            method = msg.get("method")
            if method == "session/request_permission" and "id" in msg:
                asyncio.ensure_future(self._answer_request_permission(msg))
            elif method == "session/update":
                await self._translate_update(msg)
            elif "id" in msg:
                # An agent->client request this skeleton doesn't handle yet
                # (e.g. fs/read_text_file, terminal creation). Answered
                # honestly with a JSON-RPC error -- {} is exactly what
                # silently broke the permission round-trip in testing.
                await self._notify_id_error(msg["id"], method)

    def _on_eof(self):
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionResetError("ACP process closed stdout"))
        self._pending.clear()

    async def _notify_id_error(self, req_id, method):
        payload = {"jsonrpc": "2.0", "id": req_id, "error": {
            "code": -32601, "message": "no client-side handler for %r yet" % method}}
        try:
            self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, AttributeError):
            pass

    async def _answer_request_permission(self, msg):
        req_id = msg["id"]
        params = msg.get("params") or {}
        options = params.get("options") or []
        tool_call = params.get("toolCall") or {}
        option_id = _choose_permission_option(
            self.effective_permission_mode, tool_call.get("kind"), options,
            tool_call.get("title"))
        if option_id is not None:
            result = {"outcome": {"outcome": "selected", "optionId": option_id}}
            approved = True
        else:
            result = {"outcome": {"outcome": "cancelled"}}
            approved = False
        payload = {"jsonrpc": "2.0", "id": req_id, "result": result}
        try:
            self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, AttributeError):
            return
        if self._emit is not None:
            # Auto-resolved without a round trip to the operator -- logged
            # the same way an auto-approved acceptEdits write is auditable,
            # not just silently allowed. `notice` is existing vocabulary
            # (already used for a dropped oversized frame); no new frame type.
            await self._emit({"type": "notice", "text":
                "%s permission request for %r (%s) -- mode %r"
                % ("approved" if approved else "declined",
                   tool_call.get("title") or tool_call.get("toolCallId"),
                   tool_call.get("kind") or "?", self.effective_permission_mode)})

    async def _translate_update(self, msg):
        if self._emit is None:
            return
        update = (msg.get("params") or {}).get("update") or {}
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            text = (update.get("content") or {}).get("text")
            if text:
                self._got_text = True
                await self._emit({"type": "token", "text": text})
        elif kind == "agent_thought_chunk":
            # Presence only -- same policy as Claude's `thinking` block:
            # the model's reasoning is never forwarded as if it were the answer.
            await self._emit({"type": "thinking"})
        elif kind in ("tool_call", "tool_call_update"):
            await self._emit_tool_frame(update)
        # plan / available_commands_update / current_mode_update etc: no
        # Sutra frame covers these yet and nothing downstream reads them --
        # dropped, not guessed at.

    async def _emit_tool_frame(self, update):
        tool_id = update.get("toolCallId")
        if not tool_id:
            return
        status = update.get("status")
        if status in ("completed", "failed"):
            self._open_tools.discard(tool_id)
            await self._emit({
                "type": "tool", "phase": "end", "id": tool_id,
                "ok": status == "completed",
                "output": _content_text(update.get("content")),
            })
        elif tool_id not in self._open_tools:
            self._open_tools.add(tool_id)
            await self._emit({
                "type": "tool", "phase": "start", "id": tool_id,
                "name": update.get("kind") or "",
                "summary": update.get("title") or "",
                "command": "",
                "caller": None,
            })

    # --------------------------------------------------------- lifecycle --

    async def spawn(self, args, cwd, key, env=None):
        """Start the subprocess, the background reader, and the ACP
        handshake. Unlike SessionRuntime.spawn, this is followed
        immediately by `initialize` -- ACP is a stateful connection from
        the first byte; there is no per-turn respawn-with---resume."""
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
        self._reader_task = asyncio.ensure_future(self._reader_loop())
        await self.initialize()
        return p

    async def initialize(self):
        resp = await self._call("initialize", {
            "protocolVersion": 1, "clientCapabilities": {}})
        if "error" in resp:
            raise RuntimeError("ACP initialize failed: %s" % resp["error"])
        self.agent_capabilities = (resp.get("result") or {}).get("agentCapabilities") or {}
        return self.agent_capabilities

    async def new_session(self, cwd, effective_permission_mode, session_id=None,
                          mcp_servers=None):
        """Create or resume the session and set its mode from Sutra's
        permission_mode. Call once per pane, after spawn(), before the
        first prompt_turn().

        `session_id`, when given, is tried via `session/load` first --
        ACP's stable, capability-advertised resume path (agentCapabilities.
        loadSession, confirmed true on this CLI). `session/resume` exists
        too but dispatches to an internal `unstable_resumeSession`, so load
        is the one to use. A dead or unknown id comes back as a JSON-RPC
        error (loadSession's own session lookup throws) -- caught here and
        treated exactly like Claude's dead ``--resume`` id: fall back to a
        fresh session rather than failing the turn.

        KNOWN GAP (follow-up, accepted for now): the fallback is silent.
        There is no channel to tell the client continuity was lost -- this
        runs before self._emit is set (that only happens in prompt_turn),
        so unlike Claude's resume_reset/retry frame, a dropped session id
        here just quietly starts fresh.
        """
        self.effective_permission_mode = effective_permission_mode
        result = None
        if session_id:
            resp = await self._call("session/load", {
                "sessionId": session_id, "cwd": cwd, "mcpServers": mcp_servers or []})
            if "error" not in resp:
                # zLoadSessionResponse carries no sessionId -- unlike
                # session/new, the id isn't echoed back, so it's kept from
                # what was requested.
                self.session_id = session_id
                result = resp.get("result") or {}
            # else: the id is gone (client reconnected with a stale/foreign
            # one, or the CLI's own session store was cleared) -- fall
            # through to session/new below rather than raise, exactly like
            # Claude's dead-seed retry: not the operator's fault, and there
            # is nothing to replay here since no prompt has been sent yet.
        if result is None:
            resp = await self._call("session/new", {
                "cwd": cwd, "mcpServers": mcp_servers or []})
            if "error" in resp:
                raise RuntimeError("session/new failed: %s" % resp["error"])
            result = resp["result"]
            self.session_id = result["sessionId"]

        modes = result.get("modes") or {}
        available = {m.get("id") for m in (modes.get("availableModes") or [])}
        current = modes.get("currentModeId")
        wanted = _ACP_MODE_FOR_PERMISSION_MODE.get(
            effective_permission_mode, _DEFAULT_ACP_MODE)
        if wanted in available and wanted != current:
            await self._call("session/set_session_mode",
                              {"sessionId": self.session_id, "modeId": wanted})
            current = wanted
        self.acp_mode = current
        return self.session_id

    async def prompt_turn(self, msg, emit, session_id=None):
        """The ACP analogue of SessionRuntime.send_user_frame() +
        demux_turn() COMBINED -- session/prompt is a single request/response,
        so there is no separate write-then-read-until-result split. When
        this is wired into ws_chat, that call site's two calls collapse
        into this one.

        Returns the same 5-tuple shape as SessionRuntime._demux_turn_inner
        (session_id, got_text, got_result, result_error, eof) so the
        surrounding loop's bookkeeping doesn't need a second code path.
        """
        self._emit = self._fanout(emit)
        self._got_text = False
        if not self.stopped:
            self.state = "active"
        try:
            resp = await self._call("session/prompt", {
                "sessionId": self.session_id,
                "prompt": [{"type": "text", "text": msg}],
            })
        except ConnectionResetError:
            await self._notify_subscribers({"type": "_turn_boundary",
                "session": self.session_id, "got_result": False,
                "error": "ACP process closed", "eof": True})
            return self.session_id, self._got_text, False, "ACP process closed", True

        result_error = None
        if "error" in resp:
            result_error = str(resp["error"].get("message") or resp["error"])[:600]
        else:
            result = resp.get("result") or {}
            stop_reason = result.get("stopReason")
            if stop_reason in ("refusal", "cancelled"):
                result_error = "stopReason=%s" % stop_reason
            elif stop_reason not in ("end_turn", "max_tokens", "max_turn_requests"):
                # No recognized stopReason at all -- this is the shape that
                # showed up as `[done: None]` when the permission reply was
                # malformed. Surfaced as an error rather than a silent "done".
                result_error = "ACP prompt response had no stopReason: %r" % (resp,)
            else:
                await emit({
                    "type": "done", "session": self.session_id,
                    "duration_ms": None,   # ACP does not report this
                    "num_turns": None,
                    "cost_usd": None,      # DeepSeek's usage block has no dollar figure
                })

        # Single state-reset guard, mirroring the "active" one above -- the
        # duplicate that was here (a second copy of this same block) is gone.
        if not self.stopped:
            self.state = "idle"
        self._open_tools.clear()
        await self._notify_subscribers({"type": "_turn_boundary",
            "session": self.session_id, "got_result": True,
            "error": result_error, "eof": False})
        return self.session_id, self._got_text, True, result_error, False
