"""The mission engine (PLAN-100 P3, S43-S50).

A mission is the ONLY way Shadow acts. One json file per mission holds the
mutable state; every transition is ALSO appended to the missions ledger, so
the audit trail survives any store edit. The loop is say -> boundary ->
evaluate -> next/terminal, with the sayer and boundary-waiter INJECTED so
unit tests drive a mock session and production binds the TurnQueue + the
runtime's _turn_boundary subscriber.

Flag-gated at every entry: engine methods refuse when shadow_enabled() is
False -- the flag going dark mid-mission stops the loop at the next check.
"""
import fcntl
import json
import os
import time
import uuid

import providers
import shadow_egress
import shadow_ledger

STATES = ("draft", "brief_confirm", "running", "queued", "paused",
          "blocked", "done", "failed", "stopped")
TERMINAL = ("done", "failed", "stopped")

#: The legal-transition table IS the state machine: anything not listed here
#: raises, so an illegal hop is a bug at the call site, never silent drift.
#:
#: `blocked` is deliberately NOT in TERMINAL: it means "Shadow cannot
#: continue autonomously right now", never "the chat is dead". Its exits are
#: the two things a founder can decide -- answer/extend (-> running) or
#: abandon (-> stopped). Nothing in the engine routes INTO it yet; the
#: budget and ping-pong paths still reach failed/stopped unchanged.
TRANSITIONS = {
    "draft": ("brief_confirm", "stopped"),
    "brief_confirm": ("running", "queued", "draft", "stopped"),
    "running": ("paused", "blocked", "done", "failed", "stopped"),
    "queued": ("running", "stopped"),
    "paused": ("running", "stopped", "failed"),
    "blocked": ("running", "stopped"),
    "done": (), "failed": (), "stopped": (),
}

#: Templates are DATA. Invariants are enforced where the action happens:
#: never_say refuses in the loop before any sayer call; read_only is carried
#: on the mission for the say endpoint to enforce once tool-level scoping
#: exists (P5+); both are asserted by tests.
# ------------------------------------------------ the driving contract ---
# SHADOW DRIVES, THE EVALUATOR VERIFIES, AND THE TWO NEVER SWAP JOBS.
#
# _next_say used to be the whole of Shadow's "decision": turn 0 sent the
# objective and every later turn sent "Continue toward: X. Outstanding
# checks: A; B". That string varies ONLY with the unmet set, and the unmet
# set shrinks monotonically -- so two consecutive turns produced identical
# text and the ping-pong guard stopped the attempt. Measured live (goal
# g-d804849d1400, 2026-09-11): blocked on ping_pong at turn 2/20 while the
# target chat had answered correctly. The loop iterated; the INSTRUCTION
# could not.
#
# A decider is now injected, exactly like sayer/waiter/reader/verifier, and
# consulted for turn >= 1. Two actions and no more:
#
#   continue     carry on, with THIS instruction (composed from what the
#                target actually said)
#   ask_founder  I cannot make progress; the founder is needed
#
# THERE IS DELIBERATELY NO `stop`. A stop could only mean "ask the founder"
# -- which is ask_founder -- or "declare the outcome met", which Shadow must
# never do. Leaving it out is what makes "Shadow cannot bypass verification"
# true by construction rather than by a guard that could be edited away:
# _complete stays the only writer of a `done` mission and is reachable only
# from evaluate_done_when.
DECISION_ACTIONS = ("continue", "ask_founder")

#: how much of the target's latest output the decider is shown. Bounded on
#: purpose: the whole transcript is neither necessary nor affordable, and
#: evidence assembly already excludes Shadow's own turns upstream.
DECISION_TAIL = 2000
DECISION_INSTRUCTION_MAX = 2000


def validate_decision(raw):
    """A Shadow decision, or None if it is not one.

    Strict by design (R10): a malformed decision must not degrade into the
    generic nudge this whole change exists to remove, so it returns None and
    the caller blocks honestly instead of guessing.
    """
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or "").strip()
    if action not in DECISION_ACTIONS:
        return None
    reason = str(raw.get("reason") or "").strip()[:300]
    if action == "continue":
        instruction = str(raw.get("instruction") or "").strip()
        if not instruction:
            return None               # "continue" with nothing to say is not
        return {"action": action, "reason": reason,
                "instruction": instruction[:DECISION_INSTRUCTION_MAX]}
    return {"action": action, "reason": reason, "instruction": ""}


TEMPLATES = {
    "feature": {"max_turns": 30, "invariants": ()},
    "fix": {"max_turns": 20, "invariants": ()},
    "research": {"max_turns": 15, "invariants": ("read_only",)},
    "watch": {"max_turns": 0, "invariants": ("never_say",)},
}

MAX_RUNNING = 5


def _home():
    d = os.path.join(os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_SHADOW_HOME", "~/.sutra-ui/shadow"))),
        "missions")
    os.makedirs(d, exist_ok=True)
    return d


class MissionStore:
    """File-per-mission store with ledger-audited transitions."""

    def create(self, objective, template, target_mode="existing",
               target_session=None, done_when=None, manifest=None,
               goal_id=None):
        """`goal_id` marks this mission as ONE ATTEMPT at a durable goal.

        It is the whole switch for the new failure boundary: an attempt of a
        goal BLOCKS when it runs out of road (the founder is asked), while a
        standalone mission keeps its historical terminal behaviour. Absent
        or None means standalone, so every existing caller -- including
        clone_for_retry -- is unchanged by construction.
        """
        if template not in TEMPLATES:
            raise ValueError("unknown template %r" % (template,))
        if target_mode not in ("existing", "new"):
            raise ValueError("target_mode must be existing|new")
        mission = {
            "id": "m-" + uuid.uuid4().hex[:12],
            "objective": objective,
            "template": template,
            "target_mode": target_mode,
            "target_session": target_session,
            "manifest": manifest,
            "goal_id": goal_id,
            "state": "draft",
            "done_when": done_when or [],
            "turns_used": 0,
            "max_turns": TEMPLATES[template]["max_turns"],
            "version": 1,
            "invariants": list(TEMPLATES[template]["invariants"]),
            "created_at": _now(),
            # monotonic tiebreak: created_at is second-granularity and the
            # store lists by filename (random hex) -- FIFO needs a real clock
            "created_ns": __import__("time").time_ns(),
            "updated_at": _now(),
        }
        self.save(mission)
        shadow_ledger.append("missions", {
            "mission_id": mission["id"], "state": "draft",
            "note": "created (%s)" % template})
        return mission

    def save(self, mission):
        # atomic: a crash mid-write must never leave a torn mission file.
        # seq is a monotonic write counter; ledger rows carry it, so the
        # audit trail and the store file can always be re-ordered/replayed
        # against each other after a crash (dual-lane fold).
        #
        # Optimistic stale-write guard (codex P2): store ops are synchronous
        # inside one asyncio process, but a second process (or a future
        # thread) writing the same mission would silently lose updates.
        # A writer holding an older seq than the disk refuses instead.
        path = os.path.join(_home(), mission["id"] + ".json")
        # ONE lock across load-check-increment-write (codex re-review P2):
        # the check and the replace must be a single critical section or two
        # writers can both pass the check and the last replace silently wins.
        with open(path + ".lock", "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            try:
                on_disk = self.load(mission["id"]) \
                    if mission.get("seq") else None
                if on_disk and on_disk.get("seq", 0) > mission.get("seq", 0):
                    raise ValueError(
                        "stale write on %s (disk seq %s > held %s)"
                        % (mission["id"], on_disk["seq"], mission["seq"]))
                mission["seq"] = int(mission.get("seq", 0)) + 1
                tmp = path + ".tmp"
                mission["updated_at"] = _now()
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(mission, handle, indent=1)
                os.replace(tmp, path)
            finally:
                fcntl.flock(lk.fileno(), fcntl.LOCK_UN)

    def load(self, mid):
        try:
            with open(os.path.join(_home(), mid + ".json"),
                      encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def list(self, states=None):
        out = []
        for name in sorted(os.listdir(_home())):
            if not name.endswith(".json"):
                continue
            m = self.load(name[:-5])
            if m and (states is None or m["state"] in states):
                out.append(m)
        return out

    def transition(self, mid, new_state, note=""):
        m = self.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if new_state not in TRANSITIONS.get(m["state"], ()):
            raise ValueError("illegal transition %s -> %s for %s"
                             % (m["state"], new_state, mid))
        m["state"] = new_state
        if new_state != "paused":
            m.pop("pause_reason", None)
        if new_state != "blocked":
            # symmetric with pause_reason: a reason describes the state it
            # belongs to, so leaving the state clears it rather than leaving
            # a stale blocker on a mission that is running again
            m.pop("block_reason", None)
        self.save(m)
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": new_state, "seq": m["seq"],
            "note": note[:500]})
        return m

    def block(self, mid, reason, note=""):
        """running -> blocked, stamping WHY on the record.

        The ONE writer of block_reason, so the reason and the state can
        never disagree on disk. Same two-step shape the loop already uses
        for pause_reason (transition, stamp, save) -- folded into a method
        because a blocked mission that forgot its reason is unanswerable,
        and transition() is the only thing that clears the field.
        """
        if not reason:
            raise ValueError("a blocked mission must carry a reason")
        m = self.transition(mid, "blocked", note or reason)
        m["block_reason"] = str(reason)[:200]
        self.save(m)
        return m

    def confirm_check(self, mid, index, by="founder"):
        """The ONLY writer of a founder_confirm `met` flag (dual-lane fold):
        transcript text, verify callables, and Shadow itself cannot satisfy
        this tier -- an explicit founder action calls this, it stamps who and
        when, and it ledgers the confirmation."""
        m = self.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        checks = m.get("done_when", [])
        if not (0 <= index < len(checks)):
            raise ValueError("no check %d on %s" % (index, mid))
        if checks[index].get("tier") != "founder_confirm":
            raise ValueError("check %d is not founder_confirm" % index)
        checks[index]["met"] = True
        checks[index]["confirmed_by"] = by
        checks[index]["confirmed_at"] = _now()
        self.save(m)
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": m["state"], "seq": m["seq"],
            "note": "founder confirmed check %d" % index})
        return m

    def amend(self, mid, **fields):
        """Amend-not-spawn (S54): a changed brief is a NEW VERSION of the
        same mission -- version bumps, the budget already spent stays spent,
        and the mission returns to brief_confirm for a fresh yes."""
        m = self.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if m["state"] in TERMINAL:
            raise ValueError("cannot amend a terminal mission")
        for k in ("objective", "done_when", "manifest", "max_turns"):
            if k in fields:
                m[k] = fields[k]
        m["version"] += 1
        if m["state"] != "draft":
            if "brief_confirm" not in TRANSITIONS[m["state"]]:
                # running/paused missions detour via their legal edges
                m["state"] = "brief_confirm" if m["state"] == "queued"                     else m["state"]
            else:
                m["state"] = "brief_confirm"
        self.save(m)
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": m["state"],
            "note": "amended to v%d (budget kept: %d turns used)"
                    % (m["version"], m["turns_used"])})
        return m


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clone_for_retry(store, mid):
    """Failed/stopped/done -> a FRESH mission with the same brief (retry
    one-tap). Always a new target: a dead delegate is never reused."""
    src = store.load(mid)
    if not src or src.get("state") not in TERMINAL:
        raise ValueError("retry is only for finished missions")
    prior = src.get("retried_to")
    if prior:
        pm = store.load(prior)
        if pm and pm.get("state") not in TERMINAL:
            raise ValueError("already retried as %s" % prior)
    checks = [{k: v for k, v in c.items()
               if k not in ("met", "confirmed_by", "confirmed_at")}
              for c in src.get("done_when") or []]
    clone = store.create(src["objective"], src.get("template") or "fix",
                         target_mode="new", target_session=None,
                         done_when=checks, manifest=src.get("manifest"))
    src = store.load(mid)
    src["retried_to"] = clone["id"]
    store.save(src)
    return store.transition(clone["id"], "brief_confirm",
                            "retry of %s" % mid)


def evaluate_done_when(mission, transcript_text, verifier=None):
    """Tiered evaluation. founder_confirm NEVER auto-passes: it is met only
    when its `met` flag was set by an explicit founder action."""
    results = []
    for check in mission.get("done_when", []):
        tier = check.get("tier")
        if tier == "verify":
            met = bool(verifier(check["check"])) if verifier else False
        elif tier == "contains_artifact":
            met = check["check"] in (transcript_text or "")
        elif tier == "founder_confirm":
            met = bool(check.get("met"))
        else:
            met = False
        results.append({"tier": tier, "check": check.get("check"),
                        "met": met})
    return all(r["met"] for r in results) if results else False, results


class MissionEngine:
    """Drives ONE mission's loop. sayer/waiter/reader are injected."""

    def __init__(self, store, sayer, boundary_waiter, transcript_reader,
                 verifier=None, on_evaluated=None, decider=None):
        """`on_evaluated(mission, results, done)` is an OBSERVER of the one
        evaluation this loop already performs -- it is how the goal layer
        keeps per-check progress without a second evaluator. Optional, and
        never load-bearing: its failure cannot change a mission's outcome.
        """
        self.store = store
        self.sayer = sayer
        self.waiter = boundary_waiter
        self.reader = transcript_reader
        self.verifier = verifier
        self.on_evaluated = on_evaluated
        # async (context) -> decision dict. None keeps the historical
        # template, which is what leaves every standalone mission and every
        # pre-existing test behaving exactly as before.
        self.decider = decider

    async def provision_target(self, mid, spawner):
        """S53: target_mode=new -- provision the delegate session ONCE via
        the injected spawner (production: session create + manifest prompt),
        then pin the id on the mission. Idempotent: an already-targeted
        mission returns its session untouched."""
        m = self.store.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if m.get("target_session"):
            return m["target_session"]
        if m["target_mode"] != "new":
            raise ValueError("provision_target on an existing-target mission")
        sid = await spawner(m)
        m = self.store.load(mid)
        m["target_session"] = sid
        self.store.save(m)
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "spawn",
            "summary": "delegate session %s provisioned" % sid})
        return sid

    async def run_mission(self, mid):
        """Loop until terminal/paused. Returns the final mission dict.

        DETERMINISTIC CHECK ORDER per iteration (codex fold) -- the same turn
        can trip several conditions, and the terminal state must not depend
        on scheduling: 1 flag dark -> stopped; 2 store state (founder stop /
        intervention / pause) -> honor it; 3 never_say invariant -> return;
        4 max_turns -> failed; 5 ping-pong -> stopped; 6 say; 7 boundary
        wait (timeout -> failed); 8 RELOAD and honor store state again
        (nothing terminal is decided on a pre-takeover snapshot); 9
        done_when (done > founder-confirm pause).

        WAITER CONTRACT: boundary_waiter(mission) resolves when THIS
        mission's say completed a turn on ITS target session -- bound by
        session id and the mission tag, tolerant of a late subscribe, and
        returning False on timeout instead of hanging. The mock in tests and
        the production TurnQueue/_turn_boundary binding both implement this
        contract; the engine treats False as a failed turn.
        """
        last_say = None
        # what the target said on the PREVIOUS iteration, which is the whole
        # point: the next instruction is composed from it
        last_response = None
        while True:
            if not providers.shadow_enabled():
                return self.store.transition(mid, "stopped",
                                             "the shadow flag went dark")
            m = self.store.load(mid)
            if m is None:
                raise ValueError("no mission %s" % mid)
            if m["state"] in TERMINAL or m["state"] == "paused":
                return m          # founder stop / intervention / done
            if m["state"] != "running":
                raise ValueError("run_mission on %s state %s"
                                 % (mid, m["state"]))
            if "never_say" in m.get("invariants", ()):
                # watch missions observe; they do not speak (S46 invariant)
                return m
            if m["turns_used"] >= m["max_turns"]:
                return self._out_of_road(
                    m, "failed", "budget_exhausted",
                    "max turns (%d) reached" % m["max_turns"])
            say_text, decision = await self._instruction(m, last_response)
            if decision is not None:
                # one row per decision, so a mission reads as a conversation
                # in the ledger: decided -> said -> answered -> evaluated
                shadow_ledger.append("actions", {
                    "mission_id": mid, "kind": "decision",
                    "summary": "%s: %s%s" % (
                        decision["action"],
                        (decision.get("instruction") or "")[:120],
                        (" | why: " + decision["reason"][:80])
                        if decision.get("reason") else "")})
            if decision is not None and decision["action"] == "ask_founder":
                # the EXISTING founder-facing exit: a goal attempt blocks and
                # the founder is asked, a standalone mission stays terminal
                return self._out_of_road(
                    m, "stopped", "needs_founder",
                    decision["reason"] or "Shadow asked for the founder")
            if decision is not None and decision["action"] == "undecided":
                # R10: never fall back to a generic instruction, never
                # complete. Say honestly that the driver could not decide.
                return self._out_of_road(
                    m, "failed", "shadow_undecided", decision["reason"])
            if say_text == last_say:
                return self._out_of_road(
                    m, "stopped", "ping_pong",
                    "ping-pong detected (identical consecutive says)")
            floors = shadow_egress.floor_check(say_text)
            if floors:
                # S52: the say never leaves the engine; the founder decides
                m = self.store.transition(
                    mid, "paused", "floor requires confirmation: %s"
                    % ", ".join(floors))
                m["pause_reason"] = "floor_confirm"
                m["pending_floor_say"] = say_text[:1000]
                self.store.save(m)
                return m
            ok = await self.sayer(m, say_text)
            # A STRING is a named, retryable precondition -- the say was never
            # delivered, so nothing about the attempt is spent. It goes down
            # _out_of_road, which blocks a goal attempt (the founder is asked,
            # the chat is kept, Resume works) and leaves a standalone mission
            # terminal exactly as before. False stays what it always was: the
            # say itself was turned down.
            # non-empty: an EMPTY string is falsy and means nothing, so it
            # stays a plain refusal rather than becoming a nameless blocker
            # (store.block rightly refuses a reasonless block)
            if isinstance(ok, str) and ok:
                return self._out_of_road(
                    m, "failed", ok,
                    "say not delivered (%s) -- nothing was sent" % ok)
            if not ok:
                return self.store.transition(mid, "failed", "say refused")
            last_say = say_text
            # remembered on the record, so a resumed attempt and the ledger
            # both know what Shadow last asked for
            m["last_instruction"] = say_text[:DECISION_INSTRUCTION_MAX]
            self.store.save(m)
            arrived = await self.waiter(m)
            if arrived is False:
                return self.store.transition(
                    mid, "failed", "boundary wait timed out")
            m = self.store.load(mid)
            if m["state"] in TERMINAL or m["state"] in ("paused", "blocked"):
                return m          # something terminal happened mid-turn
            m["turns_used"] += 1
            self.store.save(m)
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "say",
                "summary": say_text[:200]})
            transcript = self.reader(m)
            last_response = transcript
            done, results = evaluate_done_when(m, transcript, self.verifier)
            if self.on_evaluated is not None:
                # progress bookkeeping NEVER decides a mission's fate
                try:
                    self.on_evaluated(m, results, done)
                except Exception:
                    pass
            # reload before any terminal decision: a takeover that landed
            # while we evaluated must win (codex fold)
            fresh = self.store.load(mid)
            if fresh["state"] in TERMINAL \
                    or fresh["state"] in ("paused", "blocked"):
                return fresh
            if done:
                return self._complete(mid, results, transcript)
            pending_confirm = [r for r in results
                               if r["tier"] == "founder_confirm"
                               and not r["met"]]
            others_met = all(r["met"] for r in results
                             if r["tier"] != "founder_confirm")
            if results and pending_confirm and others_met:
                m = self.store.transition(
                    mid, "paused", "awaiting founder confirmation")
                m["pause_reason"] = "founder_confirm"
                self.store.save(m)
                return m

    def _complete(self, mid, results, transcript):
        """The ONE writer of a `done` mission.

        Lifted verbatim out of the loop so the confirmation path below can
        reach the same completion instead of growing a second one. Same
        transition, same excerpt, same ledger row, in the same order.
        """
        mm = self.store.transition(
            mid, "done", "done_when met: %s" % json.dumps(results)[:400])
        t = transcript or ""
        mm["result_excerpt"] = (t if len(t) <= 400
                                else t[:150] + " ... " + t[-250:])
        self.store.save(mm)
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "result",
            "summary": mm["result_excerpt"][:200]})
        return mm

    def settle(self, mid):
        """Decide a founder_confirm pause, WITHOUT spending a turn.

        THE DEAD END THIS CLOSES (live, goal g-e59b36c8ae53, 2026-09-11).
        The loop pauses on an outstanding founder_confirm and RETURNS --
        its task ends, RUNNING drops the id, and nothing is driving the
        mission any more. confirm_check then wrote `met`, the goal read
        2 of 2, and there it stayed: `evaluate_done_when` is what turns
        "all checks met" into a done mission, and it only ever ran inside
        the loop that had already exited. The attempt was stuck, not slow.

        NO SECOND EVALUATOR AND NO SECOND COMPLETION. This is the loop's
        own evaluate-and-decide step, reachable from outside the loop:
        same evaluate_done_when, same evidence reader, same _complete.

        NO EXTRA TURN. The loop says BEFORE it evaluates, so resuming the
        loop would have put another Shadow turn in the founder's chat to
        learn something already true. Nothing is said here.

        The mission is only moved off `paused` once the answer is known to
        be terminal: a mission left `running` with no loop behind it would
        be a worse stall than the one being fixed. Still-outstanding checks
        leave it exactly where it was.
        """
        m = self.store.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if m["state"] != "paused" \
                or m.get("pause_reason") != "founder_confirm":
            return m            # not a confirmation pause -- untouched
        transcript = self.reader(m) if self.reader is not None else ""
        done, results = evaluate_done_when(m, transcript, self.verifier)
        if self.on_evaluated is not None:
            # progress bookkeeping NEVER decides a mission's fate
            try:
                self.on_evaluated(m, results, done)
            except Exception:
                pass
        if not done:
            return m            # something is still outstanding: stay paused
        # paused -> done is not a legal edge, and widening the machine for
        # one caller would be the larger change. The mission really did
        # resume to finish, so it says so, in two legal steps and two
        # honest ledger rows.
        self.store.transition(mid, "running",
                              "founder confirmation settles the attempt")
        return self._complete(mid, results, transcript)

    def _out_of_road(self, m, terminal_state, block_reason, note):
        """The one place that decides how an attempt ends when the machine
        runs out of road (budget spent, or the chat repeating itself).

        An attempt OF A GOAL blocks: V5's core behavioural change is
        "pause -> name the blocker -> ask -> resume the same chat" instead
        of "stop -> report failure -> offer a fresh chat", and a goal must
        never die without the founder having been asked. The target chat is
        left alive and no new chat is created.

        A STANDALONE mission (no goal_id) keeps the historical terminal
        state exactly -- failed on budget, stopped on ping-pong, delegate
        reaped, feed post-mortem. That is what keeps every shipped path,
        and every existing test, behaving as before.

        The ledger note is identical either way, so the audit trail reads
        the same for both.
        """
        if m.get("goal_id"):
            return self.store.block(m["id"], block_reason, note)
        return self.store.transition(m["id"], terminal_state, note)

    def _decision_context(self, m, last_response):
        """Everything the decider is shown, and nothing else.

        Deliberately bounded and deliberately structured: the outcome, the
        checks with their CURRENT met/unmet state, the budget, the last
        instruction Shadow gave, and the tail of what the target said back.
        No raw transcript dump -- evidence assembly (which already excludes
        Shadow's own turns) stays the verifier's input, not the driver's.
        """
        return {
            "outcome": m.get("objective") or "",
            "checks": [{"tier": c.get("tier"), "check": c.get("check"),
                        "met": bool(c.get("met"))}
                       for c in (m.get("done_when") or [])],
            "turns_used": m.get("turns_used") or 0,
            "max_turns": m.get("max_turns") or 0,
            "last_instruction": m.get("last_instruction") or "",
            "last_response": (last_response or "")[-DECISION_TAIL:],
        }

    async def _instruction(self, m, last_response):
        """(say_text, decision) for this iteration.

        Turn 0 is the brief and is never a decision: the manifest (or the
        objective) is what opens the conversation. From turn 1 the decider
        reads what the target actually said and composes the next move.

        Returns say_text None when the attempt must not continue -- the
        caller turns that into the existing founder-facing block rather
        than sending anything.
        """
        if m["turns_used"] == 0 or self.decider is None:
            return self._next_say(m), None
        try:
            raw = await self.decider(self._decision_context(m, last_response))
        except Exception as exc:      # noqa: BLE001 -- reported, not hidden
            return None, {"action": "undecided",
                          "reason": "decider failed: %s" % str(exc)[:160]}
        decision = validate_decision(raw)
        if decision is None:
            return None, {"action": "undecided",
                          "reason": "decider returned no usable decision"}
        if decision["action"] == "ask_founder":
            return None, decision
        return decision["instruction"], decision

    def _next_say(self, m):
        if m["turns_used"] == 0:
            return m.get("manifest") or m["objective"]
        unmet = [c.get("check") for c in m.get("done_when", [])
                 if not c.get("met")]
        return ("Continue toward: %s. Outstanding checks: %s"
                % (m["objective"], "; ".join(filter(None, unmet)) or "none"))

    def founder_stop(self, mid, note="founder stop"):
        """Stamps `ended_by` so the goal layer can tell a FOUNDER decision
        from machine trouble: a founder stop abandons the goal (stopped),
        machine trouble asks the founder instead (blocked)."""
        m = self.store.transition(mid, "stopped", note)
        m["ended_by"] = "founder"
        self.store.save(m)
        return m

    def founder_intervened(self, mid):
        m = self.store.transition(mid, "paused", "founder typed in the "
                                                 "target session")
        m["pause_reason"] = "founder_intervened"
        self.store.save(m)
        return m

    def resume(self, mid):
        return self.store.transition(mid, "running", "explicit resume")


class MissionScheduler:
    """S55/S56: cap-5 admission with FIFO queue, promotion, and the
    disambiguation helper. One mission per target session is enforced at
    admission -- amend, never spawn a duplicate."""

    def __init__(self, store, max_running=MAX_RUNNING):
        self.store = store
        self.max_running = max_running

    def start(self, mid):
        m = self.store.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if m["state"] == "running":
            return m                      # idempotent: double-start is a no-op
        running = self.store.list(states=("running",))
        if m.get("target_session") and any(
                r.get("target_session") == m["target_session"]
                and r["id"] != mid          # a mission never blocks ITSELF
                for r in running):
            raise ValueError(
                "session %s already has a running mission -- amend it"
                % m["target_session"])
        if len(running) < self.max_running:
            return self.store.transition(mid, "running", "admitted")
        return self.store.transition(mid, "queued",
                                     "cap %d reached" % self.max_running)

    def on_terminal(self, mid):
        """Promote the oldest queued mission when a slot frees."""
        queued = sorted(self.store.list(states=("queued",)),
                        key=lambda m: m.get("created_ns", 0))
        running = self.store.list(states=("running",))
        if queued and len(running) < self.max_running:
            return self.store.transition(queued[0]["id"], "running",
                                         "promoted from queue")
        return None

    def cancel_queued(self, mid):
        """Founder Drop. Stamps `ended_by` for the same reason founder_stop
        does: a queued attempt the founder dropped abandons its goal, it is
        not machine trouble to ask about."""
        m = self.store.load(mid)
        if m is None or m["state"] != "queued":
            raise ValueError("cancel_queued needs a queued mission")
        m = self.store.transition(mid, "stopped", "cancelled from queue")
        m["ended_by"] = "founder"
        self.store.save(m)
        return m

    def pending_confirmations(self):
        """S56 disambiguation: every paused mission awaiting a founder
        decision. More than one => the UI must ask "Yes to which"."""
        out = []
        for m in self.store.list(states=("paused",)):
            if m.get("pause_reason") in ("founder_confirm", "floor_confirm"):
                out.append({"mission_id": m["id"],
                            "objective": m["objective"][:120],
                            "reason": m["pause_reason"],
                            "version": m["version"]})
        return out


def emit_mission_feed(mission, kind, why_now):
    """S57: mission events that need the founder become feed items. Dedupe
    key = mission + state + version, so an amend re-surfaces exactly once."""
    import shadow_feed
    item = {
        "item_id": "f-%s-%s-v%d" % (mission["id"], mission["state"],
                                    mission["version"]),
        "producer": "shadow",
        "mission_id": mission["id"],
        "kind": kind,
        "severity": "action" if kind == "needs_decision" else "info",
        "why_now": why_now[:200],
        "title": mission["objective"][:120],
        "deep_link": "sutra://shadow/mission/%s" % mission["id"],
        "dedupe_key": "%s:%s:v%d" % (mission["id"], mission["state"],
                                     mission["version"]),
        "state": "new",
    }
    return shadow_feed.emit(item)
