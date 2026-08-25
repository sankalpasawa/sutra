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


def standing_context():
    """U3 "applied thereafter" + grounded undo: founder-confirmed standing
    instructions and recent actions, rebuilt fresh at every boot. Failure
    yields "" -- a broken ledger must never stop Shadow from booting."""
    try:
        import shadow_ledger
        import shadow_precedence
        latest = {}
        for row in shadow_ledger.read("instructions", 200):
            latest[row.get("id")] = row
        block = shadow_precedence.replay_context(list(latest.values()))
        acts = shadow_ledger.read("actions", 10)
        lines = ["- %s: %s" % (a.get("kind"), (a.get("summary") or "")[:120])
                 for a in acts]
        out = ("\n\nSTANDING INSTRUCTIONS (founder-confirmed; apply to "
               "every reply):\n" + block)
        if lines:
            out += ("\n\nRECENT SHADOW ACTIONS (ground undo requests in "
                    "these; if something cannot be undone, say so "
                    "honestly):\n" + "\n".join(lines))
        return out
    except Exception as exc:
        # deepseek fold: a broken ledger must not stop the boot, but it
        # must not be SILENT either -- Shadow itself tells the founder
        return ("\n\n(standing instructions unavailable this boot: %s -- "
                "the memory ledger needs attention)" % str(exc)[:120])


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

    async def start(self, build_args, cwd, emit=None, extra_env=None):
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
        context = context + standing_context()
        args = build_args()
        # Narrow contract (codex fold): the caller supplies argv, but the
        # session refuses one that cannot speak the persistent protocol --
        # a missing stream flag fails here, loudly, not as a hung boot.
        if "--input-format" in args and "stream-json" not in args:
            raise ValueError("build_args() argv lacks stream-json input")
        env = {"SUTRA_MCP_SHADOW": "1"}
        env.update(extra_env or {})
        await self.rt.spawn(args, cwd, tuple(args), env=env)

        async def _sink(frame):
            return None

        try:
            await self.rt.send_user_frame(
                "[Shadow boot] Read your operating context, then answer "
                "READY.\n\n" + context)
            (self.session_id, _got_text, got_result,
             _err, _eof) = await self.rt.demux_turn(emit or _sink, None)
        except Exception:
            # partial boot must not leak a live process (codex P2 fold)
            self.rt.kill_group()
            self.rt.clear()
            raise
        self.started = bool(got_result)
        if not self.started:
            self.rt.kill_group()
            self.rt.clear()
            return None
        return self.session_id

    def stop(self):
        """Operator-initiated stop; ordering contract lives in the runtime."""
        self.started = False
        return self.rt.stop()

    @property
    def alive(self):
        return self.rt.alive
