"""Shadow's own persistent agent session (PLAN-100 S29/S30).

Lazy and flag-gated by construction: importing this module does nothing, and
start() hard-refuses unless providers.shadow_enabled() is True AT CALL TIME.
With the flag off there is no Shadow process, no context read, no state --
the off-state suite (P0 S7) is the contract.

Argv construction is INJECTED by the caller rather than imported from app.py:
app imports session_runtime, and a shadow_session -> app import would close a
cycle the moment app wires Shadow routes in P6.
"""
import os

from session_runtime import SessionRuntime

import providers

HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXT_PATH = os.path.join(HERE, "SHADOW.md")


def load_context():
    """SHADOW.md content, ONLY when the flag is on (S11/S30 contract).

    Returns None with the flag off -- callers treat None as "Shadow does not
    exist", never as an empty persona.
    """
    if not providers.shadow_enabled():
        return None
    try:
        with open(CONTEXT_PATH, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


class ShadowSession:
    """One persistent agent session that IS Shadow.

    Wraps its own SessionRuntime -- same lifecycle, demux and subscriber
    semantics every chat pane gets, so everything pinned by the
    characterization suite holds for Shadow's own session too.
    """

    def __init__(self):
        self.rt = SessionRuntime()
        self.session_id = None
        self.started = False

    async def start(self, build_args, cwd, emit=None):
        """Spawn Shadow's session and inject the SHADOW.md context as the
        first turn. Refuses (returns None) when the flag is off.

        build_args: callable () -> argv list (injected; see module docstring).
        emit: optional frame consumer for the context turn (defaults to a
        sink -- Shadow's own boot chatter is not a client conversation).
        """
        if not providers.shadow_enabled():
            return None
        context = load_context()
        if context is None:
            return None
        args = build_args()
        # Narrow contract (codex fold): the caller supplies argv, but the
        # session refuses one that cannot speak the persistent protocol --
        # a missing stream flag fails here, loudly, not as a hung boot.
        if "--input-format" in args and "stream-json" not in args:
            raise ValueError("build_args() argv lacks stream-json input")
        await self.rt.spawn(args, cwd, tuple(args))

        async def _sink(frame):
            return None

        await self.rt.send_user_frame(
            "[Shadow boot] Read your operating context, then answer READY.\n\n"
            + context)
        (self.session_id, _got_text, got_result,
         _err, _eof) = await self.rt.demux_turn(emit or _sink, None)
        self.started = bool(got_result)
        return self.session_id

    def stop(self):
        """Operator-initiated stop; ordering contract lives in the runtime."""
        self.started = False
        return self.rt.stop()

    @property
    def alive(self):
        return self.rt.alive
