"""The process-lifecycle half every chat runtime shares.

WHY THIS FILE EXISTS. `session_runtime.SessionRuntime` (Claude),
`codex_runtime.CodexRuntime` (Codex) and `acp_runtime.AcpRuntime` (DeepSeek and
any other ACP agent) each carried their OWN copy of `alive`, `kill_group`,
`stop`, `clear`, `subscribe`, `unsubscribe`, `_notify_subscribers`, `_fanout`
and `_observe`. Their own comments said so out loud -- "IDENTICAL to
SessionRuntime's ... Copied rather than imported so this provider cannot be
changed by an edit to Claude's file."

That reason does not survive contact with the facts it was meant to protect.
The two properties the copies exist to guarantee -- `process_group=0` on the
spawn, and `killpg` on the whole group -- are the SAME property for every
provider, and they are the property a regression actually costs us (the
measured `EPERM: uv_cwd` crash under ~/Desktop; a turn that never stops because
the helpers still hold the stdout pipe). Three copies means a fix has to be
applied three times and can be applied twice. One implementation, pinned by
test_provider_spawn_group.py for all three classes, is the honest version of
the same guarantee.

WHAT IS DELIBERATELY *NOT* SHARED, because the three genuinely differ:

  _observe       Claude and Codex INFER coarse turn state from the frames
                 passing through the fanout. AcpRuntime sets `self.state`
                 directly at each transition instead, so its fanout never
                 observed -- `OBSERVES_FRAMES = False` keeps that exact
                 behaviour rather than quietly adding a second state writer.
  _before_kill   ACP has an in-band `session/cancel`; Claude and Codex have no
                 control channel at all, so killing the group is the only
                 interrupt. The hook is a no-op unless a subclass overrides it.
  spawn          AcpRuntime follows the spawn with a background reader, a
                 stderr pump and the ACP `initialize` handshake. The PROCESS
                 creation is shared (`_spawn_process`); what happens after it
                 is not.

No `__init__` here on purpose. Each runtime keeps its own, so the field set of
an existing class is untouched and nothing this file does can reorder or drop a
field a subclass already had.
"""
import asyncio
import os
import signal
import subprocess    # Windows: CREATE_NEW_PROCESS_GROUP flag + taskkill tree-kill


#: 8 MiB, not asyncio's 64 KiB default, on EVERY provider. All three transports
#: are one JSON object per line and all three routinely exceed 64 KiB on a
#: single line (a Claude `user` frame carrying a tool_result, a Codex
#: `command_execution` item's aggregated_output, an ACP tool_call update with a
#: file in it). At the default, StreamReader.readline() raises "Separator is not
#: found, and chunk exceed the limit", which killed the socket and the child
#: mid-answer. Reproduced directly: a 200 KB line raises at the default and
#: reads clean at this limit.
STREAM_LIMIT = 8 * 1024 * 1024


def probe_pid(pid):
    """Liveness probe with the SAME exception contract on every OS.

    Callers guard this with try/except (ProcessLookupError -> the process is
    gone; PermissionError -> it exists but is not ours to signal). On POSIX that
    is exactly `os.kill(pid, 0)`. On Windows `os.kill(pid, 0)` does NOT probe --
    it maps to TerminateProcess and KILLS the target -- so this uses OpenProcess
    and RAISES the matching error instead of signalling anything. Returns None
    (no raise) when the process is alive.
    """
    pid = int(pid)
    if os.name != "nt":
        os.kill(pid, 0)
        return None
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        err = ctypes.get_last_error()
        if err == ERROR_ACCESS_DENIED:
            raise PermissionError(pid)       # exists, not ours to query
        raise ProcessLookupError(pid)        # invalid pid / gone
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            raise ProcessLookupError(pid)    # exited
        return None                          # alive
    finally:
        k.CloseHandle(h)


class ProcRuntime:
    """Process lifecycle + observer fan-out for one chat channel's subprocess.

    Mixed into SessionRuntime, CodexRuntime and AcpRuntime. Provides METHODS
    only -- the subclass still owns `__init__` and therefore its own fields.

    The fields this relies on, all of which every subclass already had:

      proc         the subprocess, or None
      key          the argv tuple ws_chat's reuse test compares
      stopped      the OPERATOR pressed stop. Never set for generic death.
      state        coarse turn state ("idle"/"active"/"retrying"/"stopped")
      subscribers  additional observers; the websocket's send_json is NOT one
      open_tools   ids of tool calls seen started and not yet ended
      turn_queue   the shadow/operator turn queue
    """

    #: True when this runtime infers `state` from frames passing through the
    #: fanout. False for a runtime that sets `state` itself (AcpRuntime).
    OBSERVES_FRAMES = True

    # ------------------------------------------------------------ lifecycle --

    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    def kill_group(self):
        """Kill the process GROUP, not just the direct child.

        Every provider CLI spawns helpers -- `claude` its own, `codex exec` the
        model's shell commands (measured: `/bin/zsh -lc '...'`), an ACP agent
        whatever the fork starts. Signalling only the parent leaves them holding
        the stdout pipe, so the read loop never ends and the turn never actually
        stops. `_spawn_process` uses process_group=0, which makes the child a
        group leader so this reaches its descendants too (a new group, not a new
        session -- see `_spawn_process` for why the session detach was dropped).

        Idempotent: a dead or absent process returns False and signals nothing.
        """
        p = self.proc
        if p is None or p.returncode is not None:
            return False
        if os.name == "nt":
            # No process groups / killpg on Windows. The child was spawned with
            # CREATE_NEW_PROCESS_GROUP (see _spawn_process); taskkill /T reaps it
            # AND its descendants (the model's shell commands, node helpers) --
            # the same tree-kill guarantee killpg gives on POSIX. /F forces it.
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                               check=False, capture_output=True)
                return True
            except Exception:
                try:
                    p.kill()
                except (ProcessLookupError, OSError):
                    return False
                return True
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                p.kill()
            except (ProcessLookupError, OSError):
                return False
        return True

    def _before_kill(self):
        """Hook: the last thing tried before `stop()` kills the group.

        No-op by default. AcpRuntime overrides it to fire `session/cancel` for a
        clean agent-side abort -- and the kill still follows regardless, because
        a hung or ignored cancel must not leave the process running.
        """
        return None

    def stop(self):
        """The OPERATOR pressed stop (S22): record the intent, THEN kill.

        Kept as one method so no caller can get the order wrong -- the flag must
        be set BEFORE the kill, or the stdout loop can end between the signal
        and the assignment and report the operator's own interrupt as a crash.

        Ordering contract (codex fold, 2026-08-25):
        - a turn cut by stop still ends with a `_turn_boundary` to observers
          (eof context) -- watchers always see the turn close;
        - queued SHADOW turns are dropped, queued OPERATOR turns are kept
          (the founder's words outrank automation, even mid-interrupt);
        - the ws handler unregisters from the registry AFTER the kill, in its
          finally -- a lookup during teardown may briefly see a dying runtime,
          which is why sayers must check `alive` before writing.
        """
        self.stopped = True
        self.state = "stopped"
        if getattr(self, "turn_queue", None) is not None:
            self.turn_queue.clear_shadow()
        self._before_kill()
        return self.kill_group()

    def clear(self):
        """Forget the process reference after the socket layer has drained and
        reaped it. Deliberately does NOT read or discard pending output --
        hiding unread terminal output here would swallow the very stderr the
        error policy reports. Deliberately does NOT touch a provider's
        conversation id either (Codex's thread outlives every process that
        served it; dropping it here would silently start a new conversation on
        the next message)."""
        self.proc = None
        self.key = None

    async def _spawn_process(self, args, cwd, key, env=None):
        """Create the subprocess and adopt it as self.proc. Returns it.

        On OSError nothing is assigned -- the caller keeps whatever stale proc
        was there (the socket layer's liveness check already treats a dead one
        as not-alive), and the error policy stays at the socket layer.

        stdin is a PIPE on every provider, because on every provider it is a
        channel we write to: Claude's stream-json user frames, Codex's prompt
        (the argv ends with `-`), ACP's JSON-RPC.

        env: optional environment OVERLAY for this spawn only (Shadow's own
        session carries SUTRA_MCP_SHADOW=1; DeepSeek carries its API key).
        Default None keeps the frozen behaviour byte-identical.

        A new process GROUP, not a new SESSION. kill_group only needs the child
        to be a group leader (killpg reaches its descendants), and that is all
        process_group=0 gives. start_new_session=True ALSO made it a session
        leader -- and on macOS a session leader becomes its own TCC-responsible
        process, so it STOPS inheriting the Sutra app's Files-and-Folders
        grants. A provider spawned into a workdir under ~/Desktop then died at
        startup with `EPERM: uv_cwd` -- process.cwd() denied -- even though the
        Sutra app itself is granted Desktop access (measured 2026-09-13 on the
        DeepSeek child). Staying in Sutra's session keeps the child attributed
        to os.sutra.ui, so the app's grant covers it. Same group-kill, no
        session detach. test_provider_spawn_group.py pins this for all three.
        """
        kw = dict(
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STREAM_LIMIT,
            env=dict(os.environ, **(env or {})),
        )
        if os.name == "nt":
            # Windows has no process groups; CREATE_NEW_PROCESS_GROUP makes the
            # child the root of a new group so taskkill /T (kill_group) can reap
            # its whole tree. There is no macOS TCC concern here, so this is the
            # simple analog of the POSIX process_group=0 below.
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["process_group"] = 0
        p = await asyncio.create_subprocess_exec(*args, **kw)
        self.proc = p
        self.key = key
        return p

    # ------------------------------------------------------------ observers --
    # The websocket's send_json is NOT a subscriber -- it is the PRIMARY emit
    # passed to the turn, and its exceptions must keep propagating exactly as
    # before (a dead socket ends the turn loop). Subscribers here are additional
    # observers: they see every frame the primary sees, and a broken one is
    # dropped for the frame rather than costing the operator their answer.

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

    def _observe(self, frame):
        """Update coarse turn state from a frame passing through the fanout.
        Purely mechanical -- no policy, no timers -- so Shadow's state machine
        reads the same on every provider.

        Not a permission oracle: PERMISSION_WAIT detection is a policy layered
        on open_tools + quiet time, once the real stall shape is characterized.
        """
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
        """Deliver one frame to the observers only (never the primary).
        Snapshot + isolation semantics identical to _fanout."""
        if self.OBSERVES_FRAMES:
            self._observe(frame)
        for cb in list(self.subscribers):
            try:
                res = cb(frame)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def _fanout(self, primary):
        """Wrap the primary emit with subscriber fan-out.

        Snapshot semantics: the subscriber list is captured per FRAME (not per
        turn) so an observer attached mid-turn starts seeing frames then -- the
        Shadow watcher attaches to already-running panes. Primary exceptions
        propagate (frozen behaviour); subscriber exceptions are swallowed
        per-frame -- an observer must never cost the operator a turn.
        """
        async def emit(frame):
            if self.OBSERVES_FRAMES:
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
