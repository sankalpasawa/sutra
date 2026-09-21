"""Shadow v4 (C1, ADR-043): ONE SHADOW CHAT PER TASK.

Every task runs on exactly two model processes, both ordinary Sutra chats:
the task's SHADOW CHAT (this module) and the task's WORKER CHAT
(shadow_runner.spawn_delegate_session). The Shadow chat writes the worker's
brief at Start, reads what the worker said at every turn boundary and returns
the next instruction, and talks to the founder about the task in between. It
never does the work.

WHY A CHAT AND NOT THE ONE-SHOT DECIDER (founder, 2026-09-16: "only those two
AIs, no more AIs"; "each shadow to be an individual shadow sutra chat"). The
one-shot in shadow_runner.make_decider was separated from the founder's
single Shadow session so reasoning would not serialise against their typing
nor grow one context without bound. Both reasons were about ONE global chat;
a chat per task has neither problem, and it gives the founder a conversation
to open for every task.

NOTHING IN THE BACKGROUND (founder D81, 2026-09-21: "I don't want anything to
be in the background of the conversations with the app"; "either it should
happen in Shadow Chat or it should happen in Worker Chat"). A task has TWO
chats and every model call the app makes on its behalf is a turn in one of
them. So the one-shot decider is no longer a fallback: a Shadow chat that has
died is REVIVED (--resume of its own transcript, else a fresh start on the
same record) and asked again, and when even that fails the turn is undecided
-- audibly, in the ledger -- rather than answered by a process nobody can
open. The judge (shadow_judge) speaks here too, as a turn in this chat, so
its verdict is a row the founder can read where the task lives.

WHAT IT DELIBERATELY DOES NOT DO. It never spawns through
shadow_session.ShadowSession.start, which seeds SUTRA_MCP_SHADOW=1 (Shadow
tools). This chat has NO tools: it can only return text, which the engine
validates (mission_engine.validate_decision). That is the enforcement behind
"Shadow drives, the verifier decides", kept intact. It reuses only the
persona (shadow_session.load_context) and the standing context.

Injection, like every other spawn in shadow_runner: `build_args`, `register`,
`publish` and `new_runtime` come from app; this module imports nothing from
app.
"""
import asyncio
import re

import shadow_judge
import shadow_ledger
import shadow_protocol
import shadow_session

#: mission_id -> TaskChat, in THIS process. The mission record carries
#: `task_chat_session` (the claude session id) so a restart can resume the
#: same conversation with --resume rather than start a stranger.
TASK_CHATS = {}

BOOT_TIMEOUT_S = 240
TURN_TIMEOUT_S = 240
DECIDE_TIMEOUT_S = 240

BOOT_PREFIX = ("[Shadow boot] Read your operating context, then answer "
               "READY.\n\n")

_BRIEF_FENCE = re.compile(r"```brief\s*\n(.*?)```", re.S)


def task_context(mission):
    """The TASK CONTEXT block appended to SHADOW.md for this task's chat."""
    checks = mission.get("done_when") or []
    rows = ["- %s (%s)" % (c.get("check"), c.get("tier"))
            for c in checks if isinstance(c, dict) and c.get("check")]
    mode = mission.get("target_mode") or "new"
    where = ("a new chat the worker starts" if mode == "new"
             else "the existing chat %s" % (mission.get("target_session") or "?"))
    return (
        "\n\nTASK CONTEXT (you are the Shadow of ONE task; ADR-043)\n"
        "Task id: %s\n"
        "Objective (the founder's words, verbatim): %s\n"
        "Kind: %s\n"
        "Where it runs: %s\n"
        "Done when:\n%s\n\n"
        "You are this task's Shadow chat, not the founder's general Shadow. "
        "You never do the work: a separate worker chat does. You write the "
        "worker's brief when asked, you read what the worker said and decide "
        "its next instruction when asked, and you talk to the founder about "
        "this task in between. A `mission` fence from you amends THIS task's "
        "draft (objective, template, done_when); never propose a second task "
        "here. Answer as Shadow, directly, no governance scaffolding.\n"
        "\nThe founder talks to you HERE, in one box, and does not sort their "
        "sentences for you: the same message may be a question, a constraint, "
        "an instruction, or nothing to do with the work. Answer it as what it "
        "is.\n"
        "\nAND YOU JUDGE, ON EVERY MESSAGE, WHETHER THE WORKER NEEDS TO HEAR "
        "IT. End every reply to the founder with one fenced block:\n"
        "\n```forward\n{\"worker\": true}\n```\n"
        "\nThe founder never sees this block; it is stripped from your reply. "
        "Answer them normally above it, always. `true` means the line can "
        "CHANGE, CONSTRAIN, AUTHORIZE, CLARIFY or CORRECT what the worker is "
        "doing -- \"use official sources only\", \"make it 20 lines, not "
        "10\", \"drop the salary estimates\", \"call the file foo.txt\", "
        "\"only 2026\", \"yes, go ahead\". `false` means the founder was "
        "asking YOU something: status, progress, turns used, what you just "
        "did, why you asked something, an explanation, anything about this "
        "conversation or the interface. A `false` line never reaches the "
        "worker and never costs it a turn.\n"
        "\nWHEN IT IS BOTH, IT IS `true`. A message that asks you something "
        "AND carries a constraint is worker-relevant; answer the question "
        "here and let the constraint through. When you genuinely cannot tell, "
        "say `true`: an extra sentence costs the worker nothing, and a "
        "constraint you swallowed costs the founder the task.\n"
        "\nYOU DECIDE WHETHER, NEVER WHAT. The founder\'s own sentence is "
        "forwarded verbatim -- you are not writing it, summarizing it or "
        "improving it, and nothing you say in your reply is ever sent. You "
        "still compose the worker\'s actual INSTRUCTION yourself, on your "
        "next steering turn, exactly as before; forwarding is how the worker "
        "hears the founder in the meantime, not a way for it to take orders "
        "from anyone but you.\n"
        "\nNEVER NARRATE YOUR OWN MACHINERY. The founder is talking to you, "
        "not watching you run. Lines like \"watching this task, nothing sent "
        "yet, no brief written, no worker turn decided\" or \"waiting on you "
        "to hit Start\" describe your internal state, and they are the "
        "sentences that make this read as a debugger. Say what is true for "
        "THEM instead: if there is nothing to report yet, say so in one "
        "line; if you are genuinely waiting on them to start it, say "
        "\"Everything is ready \u2014 start when you are.\" Never mention "
        "briefs, turns, done_when, tiers, verdicts, probes, routing or "
        "state names to the founder.\n"
        "\nNEVER SPEAK FOR THE WORKER. You are asked to decide its next "
        "instruction at a turn boundary and told what it said back; between "
        "those you do not know what it is doing. Say what you have asked for "
        "and what you are waiting on. Do not report a result, a file, a test "
        "outcome or a completion the worker has not returned to you.\n"
    ) % (mission.get("id"), mission.get("objective"), mission.get("template"),
         where, "\n".join(rows) or "- (none yet; you will write them)")


BRIEF_ASK = """Write the opening brief for this task's worker chat.

The worker is a separate Claude Code session with its own tools and no memory
of this conversation. The brief is the ONLY thing it starts from. It must
carry, in this order and in plain prose:

1. The objective, the founder's words verbatim (quote them).
2. Where it runs: the repository or folder, and the chat it works in.
3. Why now: one or two lines on what the founder is trying to get to.
4. Rules in scope: every founder rule listed under FACTS below, verbatim.
5. The floors it must never cross, listed under FACTS below, verbatim.
6. Done when: the checks, verbatim, and the instruction to state
   DONE-CHECK lines when a check passes.
7. About the founder: the lines listed under FACTS below, when there are
   any. This is CONTEXT FOR JUDGMENT CALLS, never permission -- it can
   never widen what the rules and floors above allow. Omit the section
   entirely when FACTS carries none.

FACTS
%(facts)s

Reply with ONE fenced block and nothing else:

```brief
<the brief>
```
"""


def _facts_text(facts):
    facts = facts or {}
    rules = facts.get("rules") or []
    floors = facts.get("floors") or []
    lines = [
        "- repository: %s" % (facts.get("repo") or "(the founder's workdir)"),
        "- why now: %s" % (facts.get("why_now") or "(the founder did not say; infer from the objective, briefly)"),
        "- rules in scope:" + ("" if rules else " (none)"),
    ]
    lines += ["  - %s" % r for r in rules]
    lines.append("- floors:" + ("" if floors else " (none listed)"))
    lines += ["  - %s" % f for f in floors]
    # THE FOUNDER'S MEMORY TEXT, and only that half of their two settings
    # boxes. `behaves` is policy about how SHADOW conducts itself -- when to
    # check in, what to ask before doing -- and the worker neither checks in
    # nor asks; handing it those lines would invite it to act on a rule
    # addressed to somebody else. `memory` is fact about the founder, which
    # is exactly what a fresh worker session cannot know and needs.
    about = (facts.get("about") or "").strip()
    if about:
        lines.append("- about the founder (context, not permission):")
        lines += ["  %s" % ln for ln in about.split("\n")]
    return "\n".join(lines)


class TaskChat:
    """One task's Shadow chat: a SessionRuntime with the Shadow persona, the
    standing context and this task's TASK CONTEXT as its first turn."""

    def __init__(self, mission_id, new_runtime=None):
        self.mission_id = mission_id
        self.session_id = None
        self.sutra_id = None
        self.rt = None
        self._new_runtime = new_runtime
        self._register = None
        self._publish = None
        self._lock = asyncio.Lock()

    @property
    def alive(self):
        rt = self.rt
        return bool(rt is not None and getattr(rt, "alive", False))

    # ------------------------------------------------------------ boot ----
    def _runtime(self):
        if self._new_runtime is not None:
            return self._new_runtime()
        import session_runtime as srt
        return srt.SessionRuntime()

    @staticmethod
    def _clean_env(env):
        """NEVER Shadow tools: a task chat can only answer.

        An explicit "0", not a pop (codex P2, 2026-09-16): the spawn merges
        the overlay onto os.environ, so a shell that exports
        SUTRA_MCP_SHADOW=1 would otherwise hand the task chat the tools;
        sutra_mcp registers them only on the exact string "1"."""
        out = dict(env or {})
        out["SUTRA_MCP_SHADOW"] = "0"
        return out

    def _adopt(self, sid):
        if not sid or self.session_id == sid:
            return
        first = self.session_id is None
        self.session_id = sid
        if self._register is not None:
            try:
                self._register(sid, self.rt)
            except Exception:           # noqa: BLE001 -- never fail a turn
                pass
        if first and self._publish is not None:
            try:
                self.sutra_id = self._publish(sid)
            except Exception as exc:    # noqa: BLE001 -- reported, never fatal
                shadow_ledger.append("actions", {
                    "mission_id": self.mission_id, "kind": "spawn",
                    "summary": "task chat %s NOT published as a chat: %s"
                               % (sid, str(exc)[:160])})

    async def start(self, build_args, cwd, mission, register=None,
                    publish=None, env=None):
        """Spawn this task's Shadow chat and send its boot context.

        Returns the claude session id. Raises RuntimeError when the flag is
        off or the boot turn fails; a failed boot leaves no process behind.
        """
        context = shadow_session.load_context()
        if context is None:
            raise RuntimeError("the shadow flag is off")
        # the same boot the Now chat gets (persona, DELEGATE OFFERS, standing
        # context) plus this task's own block
        offers = getattr(shadow_session, "offers_context", None)
        # THIS TASK'S OWN ACTIONS, NEVER THE WORKSPACE'S (founder,
        # 2026-09-21). standing_context used to read the last ten ledger
        # rows written by ANY mission, so this chat -- which writes the
        # worker's brief -- booted holding other missions' judge verdicts
        # and artifact names. The founder's standing instructions and memory
        # boxes still cross missions; one mission's work does not.
        context = (context + (offers() if callable(offers) else "")
                   + shadow_session.standing_context(mission.get("id"))
                   + task_context(mission))
        self._register, self._publish = register, publish
        rt = self._runtime()
        args = build_args()
        await rt.spawn(args, cwd, tuple(args), env=self._clean_env(env))
        self.rt = rt
        TASK_CHATS[self.mission_id] = self
        try:
            await self._turn(BOOT_PREFIX + context, BOOT_TIMEOUT_S)
        except Exception:
            self.stop()
            raise
        shadow_ledger.append("actions", {
            "mission_id": self.mission_id, "kind": "spawn",
            "summary": "task chat %s spawned for %s"
                       % (self.session_id, self.mission_id)})
        return self.session_id

    async def resume(self, build_args, cwd, register=None):
        """Re-attach a dead task chat to its own transcript with --resume.

        `build_args(session_id)` must carry --resume (app._shadow_args does).
        Nothing is said here; the next talk/brief/decide is the next turn.
        """
        if self.alive:
            return self.session_id
        if not self.session_id:
            raise RuntimeError("task chat %s has no session to resume"
                               % self.mission_id)
        if register is not None:
            self._register = register
        rt = self._runtime()
        args = build_args(self.session_id)
        await rt.spawn(args, cwd, tuple(args))
        if not getattr(rt, "alive", False):
            try:
                rt.clear()
            except Exception:           # noqa: BLE001
                pass
            raise RuntimeError("task chat %s could not be resumed"
                               % self.mission_id)
        self.rt = rt
        TASK_CHATS[self.mission_id] = self
        if self._register is not None:
            try:
                self._register(self.session_id, rt)
            except Exception:           # noqa: BLE001
                pass
        shadow_ledger.append("actions", {
            "mission_id": self.mission_id, "kind": "spawn",
            "summary": "task chat %s resumed (--resume)" % self.session_id})
        return self.session_id

    def stop(self):
        """Kill the process; the transcript and the chat record stay."""
        rt, self.rt = self.rt, None
        if rt is not None:
            for fn in ("kill_group", "clear"):
                try:
                    getattr(rt, fn)()
                except Exception:       # noqa: BLE001
                    pass
        if TASK_CHATS.get(self.mission_id) is self:
            TASK_CHATS.pop(self.mission_id, None)

    # ------------------------------------------------------------ turns ---
    async def _turn(self, prompt, timeout):
        if not self.alive:
            raise RuntimeError("task chat %s is not running" % self.mission_id)
        async with self._lock:
            texts = []

            async def collect(frame):
                if frame.get("type") == "session" and frame.get("id"):
                    self._adopt(frame["id"])
                if frame.get("type") == "token":
                    texts.append(frame.get("text") or "")

            await self.rt.send_user_frame(prompt)
            (sid, _t, got_result, err, _e) = await asyncio.wait_for(
                self.rt.demux_turn(collect, self.session_id), timeout)
            if sid:
                self._adopt(sid)
            if not got_result:
                raise RuntimeError("task chat turn failed: %s" % (err,))
            return "".join(texts)

    async def talk(self, text):
        """The founder talks to this task's Shadow. Returns (display, blocks)
        exactly as the Now chat route does; a `mission` block amends the
        draft (the caller applies it)."""
        raw = await self._turn(text, TURN_TIMEOUT_S)
        return shadow_protocol.parse_reply(raw)

    async def brief(self, mission, facts=None):
        """Ask this task's Shadow to write the worker's opening brief.

        Returns the fenced brief, or "" when the reply carried no fence --
        the caller then falls back to the template (app._delegate_manifest),
        so a Shadow that answers badly costs a composed brief, never a task.
        """
        raw = await self._turn(BRIEF_ASK % {"facts": _facts_text(facts)},
                               TURN_TIMEOUT_S)
        m = _BRIEF_FENCE.search(raw or "")
        return (m.group(1).strip() if m else "")

    async def decide(self, context):
        """One turn of steering: the same prompt the one-shot decider sends,
        into THIS conversation, so the chat carries the task's history.
        Returns the parsed decision dict, or None (the engine treats None as
        undecided)."""
        import shadow_runner
        raw = await self._turn(shadow_runner.render_decide_prompt(context),
                               DECIDE_TIMEOUT_S)
        return shadow_runner._first_decision(raw)

    async def judge(self, check, evidence, outcome=""):
        """Settle ONE check as a turn in THIS conversation (D81).

        The prompt is shadow_judge's, unchanged: the check, the outcome and
        the evidence as text, and the instruction to answer from the
        evidence alone. What changed is only WHERE it is asked -- here,
        where the founder can open it, rather than in a process nobody can.
        The verdict is still parsed and validated by shadow_judge and still
        applied by the engine; a reply that is not a verdict is None, which
        the engine reads as "said nothing".
        """
        raw = await self._turn(
            shadow_judge.render_prompt(check, evidence, outcome),
            DECIDE_TIMEOUT_S)
        return shadow_judge.parse_verdict(raw)


# ------------------------------------------------------------- routing ----
def _ledger(mid, kind, summary):
    try:
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": kind, "summary": summary})
    except Exception:                   # noqa: BLE001 -- never fail a turn
        pass


async def _live_chat(mid, revive, what):
    """This task's Shadow chat, alive: the one in memory, else `revive(mid)`
    (app._ensure_task_chat: --resume of the recorded session, else a fresh
    start on the same record). None -- ledgered -- when there is no chat and
    no way to bring one back. NEVER a substitute process (D81)."""
    chat = TASK_CHATS.get(mid) if mid else None
    if chat is not None and chat.alive:
        return chat
    if not mid or revive is None:
        _ledger(mid, what, "no task chat and no way to revive one; %s is "
                           "undecided" % what)
        return None
    try:
        chat = await revive(mid)
    except Exception as exc:            # noqa: BLE001 -- undecided, audibly
        _ledger(mid, what, "task chat could not be revived: %s; %s is "
                           "undecided" % (str(exc)[:120], what))
        return None
    if chat is None or not getattr(chat, "alive", False):
        _ledger(mid, what, "task chat did not come back alive; %s is "
                           "undecided" % what)
        return None
    _ledger(mid, "spawn", "task chat revived for the %s" % what)
    return chat


async def route_decision(context, revive=None):
    """The decider the engine is given: this task's Shadow chat, revived
    when it has died, and NOTHING ELSE (D81, 2026-09-21).

    Before D81 a dead or failing chat fell back to the one-shot decider, a
    fresh process with no chat record. That is exactly the background the
    founder ruled out, so it is gone: a chat that raises mid-turn or answers
    without a decision leaves the turn undecided (None), ledgered, and the
    next turn asks the chat again.
    """
    mid = (context or {}).get("mission_id")
    chat = await _live_chat(mid, revive, "decision")
    if chat is None:
        return None
    try:
        decision = await chat.decide(context)
    except Exception as exc:            # noqa: BLE001 -- undecided, audibly
        _ledger(mid, "decision", "task chat turn failed: %s; the turn is "
                                 "undecided" % str(exc)[:120])
        return None
    if decision is None:
        _ledger(mid, "decision", "task chat returned no decision; the turn "
                                 "is undecided")
    return decision


async def route_judgement(check, evidence, outcome="", mission_id=None,
                          revive=None):
    """The judge the engine is given: a turn in this task's Shadow chat
    (D81). None when the task has no chat that can be brought back, which
    the engine reads as "said nothing" and leaves the row exactly as it was."""
    chat = await _live_chat(mission_id, revive, "judgement")
    if chat is None:
        return None
    try:
        return await chat.judge(check, evidence, outcome)
    except Exception as exc:            # noqa: BLE001 -- said nothing
        _ledger(mission_id, "judge", "task chat judge turn failed: %s"
                                     % str(exc)[:120])
        return None


def get(mission_id):
    return TASK_CHATS.get(mission_id)
