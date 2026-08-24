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
