"""The persistent Goal store (V5 slice 2).

A GOAL is the durable commitment that ONE chat will reach ONE outcome. A
MISSION is one attempt at it. That is the whole distinction: a mission's
terminal states have no exits by design, so today an outcome dies with its
first failed attempt (V5 gap G1). A goal outlives its attempts.

Deliberately store-only. There is no loop, no scheduler binding, no API and
no engine here -- nothing in production reads this module yet, which is what
makes the slice reversible. It is also import-inert: no flag read, no
process state, no side effect beyond creating its own directory on first
write.

PERSISTENCE IS COPIED, NOT REINVENTED. Same idiom as MissionStore, on
purpose (V5: "using the SAME file-per-record, lock, atomic-replace and
seq-guard idiom as missions. Do not invent a second persistence pattern"):

    goals/<goal_id>.json      one record per file, sibling to missions/
    <path>.lock               flock held across load-check-write
    seq                       monotonic write counter; a stale holder refuses
    <path>.tmp + os.replace   a crash mid-write never leaves a torn record

The one difference from missions is the audit trail: mission transitions
append to shadow_ledger's "missions" kind, but goal rows would have no
`mission_id` and would pollute every reader that filters on one. So a goal
carries its OWN append-only `history` list instead, written by the same
methods that change it. Adding a "goals" ledger kind is a deliberate
deferral -- it would edit an existing module and no part of this slice
needs it.
"""
import fcntl
import json
import os
import time
import uuid

#: The V5 lifecycle vocabulary, and nothing beyond it.
#:
#:   draft      the outcome is stated, not yet being pursued
#:   working    a mission is driving the chat toward it
#:   verifying  the chat claims done; the checks are being settled
#:   blocked    Shadow cannot continue autonomously -- the founder is asked.
#:              NOT terminal, and never "the chat is dead" (slice 1 added the
#:              matching mission state)
#:   done       verified
#:   stopped    the founder stopped or abandoned it
STATES = ("draft", "working", "verifying", "blocked", "done", "stopped")

#: A goal reaches a terminal state only by founder decision or verified
#: completion. Machine-detected trouble goes to `blocked` and waits.
TERMINAL = ("done", "stopped")

#: Non-terminal == active == holds its chat. The one-active-goal-per-chat
#: invariant is defined against exactly this set.
ACTIVE = tuple(s for s in STATES if s not in TERMINAL)

#: The legal-transition table IS the state machine -- same contract as
#: missions: anything not listed raises, so an illegal hop is a bug at the
#: call site and never silent drift.
TRANSITIONS = {
    "draft": ("working", "stopped"),
    "working": ("verifying", "blocked", "done", "stopped"),
    # verifying -> blocked because machine trouble ALWAYS asks the founder
    # first, from whichever state it happens in (slice 3)
    "verifying": ("working", "blocked", "done", "stopped"),
    "blocked": ("working", "stopped"),
    "done": (),
    "stopped": (),
}


#: The kinds of reusable knowledge a goal may hold (slice 5). Closed set, so
#: a typo is a failure at the call site rather than a silent new category.
#:
#:   attempt_outcome  what one attempt tried and how it ended
#:   blocker          why an attempt could not continue
#:   checks_proven    which checks an attempt actually satisfied
#:   result           the excerpt captured when the goal verified
#:   founder_guidance something the founder explicitly said about this goal
LEARNED_KINDS = ("attempt_outcome", "blocker", "checks_proven", "result",
                 "founder_guidance")


def _home():
    d = os.path.join(os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_SHADOW_HOME", "~/.sutra-ui/shadow"))),
        "goals")
    os.makedirs(d, exist_ok=True)
    return d


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class GoalStore:
    """File-per-goal store with in-record history."""

    # ------------------------------------------------------------- create --
    def create(self, outcome, target_session, done_when=None):
        """A new goal, in `draft`, bound to one chat.

        `target_session` is REQUIRED and is the key the one-active-per-chat
        invariant is enforced on; a goal with no chat would make that
        invariant unenforceable, and V5 has no unbound-goal concept ("no
        live move", "target is the active tab's chat").

        `done_when` may legitimately be empty here: V5's creation flow has
        Shadow PARSE checks out of natural language, so a draft can exist
        before its checks do. V5's "every goal must carry at least one
        check" rule therefore belongs where a goal leaves draft, not here --
        and its exact shape is still partly founder-pending (trap 5's open
        half: whether a say-less goal is a defined thing). Not decided here.
        """
        if not outcome or not str(outcome).strip():
            raise ValueError("a goal needs an outcome")
        if not target_session or not str(target_session).strip():
            raise ValueError("a goal must be bound to a target session")
        clash = self.active_for_session(target_session)
        if clash:
            raise ValueError(
                "session %s already has an active goal (%s, %s) -- one "
                "active goal per chat" % (target_session, clash["id"],
                                          clash["state"]))
        goal = {
            "id": "g-" + uuid.uuid4().hex[:12],
            "target_session": str(target_session),
            "outcome": str(outcome),
            "done_when": list(done_when or []),
            "state": "draft",
            "current_mission_id": None,
            "attempts": [],
            "history": [],
            # --- progress (slice 4) -------------------------------------
            # done_when above stays the PRISTINE definition; the latest
            # evaluated state of each check lives here, one row per check
            # index, so a blocked/stopped/done goal keeps what it knew.
            "check_results": [],
            "last_evaluated_at": None,
            # snapshot of the live attempt's budget, so turn progress
            # survives the attempt being released
            "turns_used": 0,
            "max_turns": None,
            "block_reason": None,
            # reserved by schema, written by NO code in this slice: memory
            # learning is a later slice and must not be half-implemented here
            "learned": [],
            "created_at": _now(),
            # monotonic tiebreak, same reason as missions: created_at is
            # second-granularity and filenames are random hex
            "created_ns": time.time_ns(),
            "updated_at": _now(),
        }
        self._note(goal, None, "draft", "created")
        self.save(goal)
        return goal

    # --------------------------------------------------------- read/write --
    def load(self, gid):
        try:
            with open(os.path.join(_home(), gid + ".json"),
                      encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def save(self, goal):
        """Atomic write under an exclusive lock, with a stale-write guard.

        Identical shape to MissionStore.save: ONE lock across
        load-check-increment-write, because the check and the replace must
        be a single critical section or two writers both pass the check and
        the last replace silently wins. A writer holding an older `seq` than
        the disk refuses instead of clobbering.
        """
        if not isinstance(goal, dict) or not goal.get("id"):
            raise ValueError("a goal record needs an id")
        path = os.path.join(_home(), goal["id"] + ".json")
        with open(path + ".lock", "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            try:
                on_disk = self.load(goal["id"]) if goal.get("seq") else None
                if on_disk and on_disk.get("seq", 0) > goal.get("seq", 0):
                    raise ValueError(
                        "stale write on %s (disk seq %s > held %s)"
                        % (goal["id"], on_disk["seq"], goal["seq"]))
                goal["seq"] = int(goal.get("seq", 0)) + 1
                goal["updated_at"] = _now()
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(goal, handle, indent=1)
                os.replace(tmp, path)
            finally:
                fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
        return goal

    def list(self, states=None, target_session=None):
        """Every goal, oldest-created first, optionally filtered.

        Ordering is by created_ns rather than filename (random hex), so
        callers get a stable, meaningful order the way the mission
        scheduler's FIFO does.
        """
        out = []
        try:
            names = sorted(os.listdir(_home()))
        except OSError:
            return out
        for name in names:
            if not name.endswith(".json"):
                continue
            g = self.load(name[:-5])
            if g is None:
                continue
            if states is not None and g.get("state") not in states:
                continue
            if target_session is not None \
                    and g.get("target_session") != target_session:
                continue
            out.append(g)
        out.sort(key=lambda g: g.get("created_ns", 0))
        return out

    # ------------------------------------------------------- transitions --
    def transition(self, gid, new_state, note=""):
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        if new_state not in TRANSITIONS.get(g["state"], ()):
            raise ValueError("illegal transition %s -> %s for %s"
                             % (g["state"], new_state, gid))
        self._note(g, g["state"], new_state, note)
        g["state"] = new_state
        if new_state != "blocked":
            # same rule as the mission store: a reason describes the state
            # it belongs to. Check RESULTS are never cleared -- a resumed
            # goal keeps what it had already proven.
            g["block_reason"] = None
        self.save(g)
        return g

    def block(self, gid, reason, note=""):
        """-> blocked, stamping WHY. The one writer of a goal's
        block_reason, mirroring MissionStore.block so the two stores read
        the same way."""
        if not reason:
            raise ValueError("a blocked goal must carry a reason")
        g = self.transition(gid, "blocked", note or reason)
        g["block_reason"] = str(reason)[:200]
        self.save(g)
        return g

    # ---------------------------------------------------------- progress --
    def record_check_results(self, gid, results, mission_id=None,
                             attempt=None, turns_used=None, max_turns=None):
        """Retain the per-check results of ONE evaluation.

        `results` is exactly what mission_engine.evaluate_done_when returns
        -- [{tier, check, met}, ...], positionally aligned with done_when.
        Stored per check index rather than as a prose summary, so progress
        can be counted rather than parsed.

        Replaces the previous results wholesale: this is the LATEST state of
        every check, not an append-only log. The goal's history already
        carries the narrative.
        """
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        now = _now()
        rows = []
        for i, r in enumerate(results or []):
            rows.append({
                "index": i,
                "tier": r.get("tier"),
                "check": r.get("check"),
                "met": bool(r.get("met")),
                "evaluated_at": now,
                "mission_id": mission_id,
                "attempt": attempt,
            })
        g["check_results"] = rows
        g["last_evaluated_at"] = now
        if turns_used is not None:
            g["turns_used"] = int(turns_used)
        if max_turns is not None:
            g["max_turns"] = int(max_turns)
        self.save(g)
        return g

    def record_budget(self, gid, turns_used=None, max_turns=None):
        """Snapshot the live attempt's budget without touching checks --
        used when a resumed attempt raises the ceiling before it has run."""
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        if turns_used is not None:
            g["turns_used"] = int(turns_used)
        if max_turns is not None:
            g["max_turns"] = int(max_turns)
        self.save(g)
        return g

    def progress(self, gid):
        """Honest progress: satisfied checks over total, plus turn usage.

        DERIVED on read from the stored facts, never a stored summary that
        could drift from the results it claims to describe. Two independent
        numbers, deliberately:

          checks_met / checks_total   the only real measure of the outcome
          turns_used / max_turns      cost, NOT progress

        There is no percentage, and there never should be: the checks are
        the only ground truth, and a synthesised number would be the first
        lie in Shadow's UI. `checks_total` comes from the pristine
        done_when, so a goal with three checks and no evaluation yet
        honestly reads 0 of 3.
        """
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        total = len(g.get("done_when") or [])
        by_index = {r.get("index"): r for r in g.get("check_results") or []}
        checks = []
        for i, definition in enumerate(g.get("done_when") or []):
            row = by_index.get(i) or {}
            checks.append({
                "index": i,
                "tier": definition.get("tier"),
                "check": definition.get("check"),
                "met": bool(row.get("met")),
                "evaluated_at": row.get("evaluated_at"),
            })
        met = sum(1 for c in checks if c["met"])
        turns_used = g.get("turns_used") or 0
        max_turns = g.get("max_turns")
        return {
            "goal_id": g["id"],
            "state": g["state"],
            "outcome": g.get("outcome"),
            "target_session": g.get("target_session"),
            "checks": checks,
            "checks_met": met,
            "checks_total": total,
            "checks_label": "%d of %d checks" % (met, total),
            "unmet": [c["check"] for c in checks if not c["met"]],
            "turns_used": turns_used,
            "max_turns": max_turns,
            # None, not a fabricated ceiling, when no attempt has run yet
            "turn_label": (None if max_turns is None
                           else "turn %d/%d" % (turns_used, max_turns)),
            "attempt": len(g.get("attempts") or []),
            "current_mission_id": g.get("current_mission_id"),
            "block_reason": g.get("block_reason"),
            "last_evaluated_at": g.get("last_evaluated_at"),
        }

    # ------------------------------------------------- attempt / mission --
    def bind_mission(self, gid, mission_id, note=""):
        """Point the goal at the mission that is now its live attempt.

        Appends the attempt row as well as setting current_mission_id, so
        the attempt list is the durable record of how many tries an outcome
        took and how each ended -- the thing a mission's forward-only
        `retried_to` pointer cannot answer.
        """
        if not mission_id:
            raise ValueError("bind_mission needs a mission id")
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        if g["state"] in TERMINAL:
            raise ValueError("cannot bind an attempt to a %s goal"
                             % g["state"])
        if g.get("current_mission_id") == mission_id:
            return g                          # idempotent re-bind
        if g.get("current_mission_id"):
            raise ValueError(
                "goal %s already has a live attempt (%s) -- release it first"
                % (gid, g["current_mission_id"]))
        g["current_mission_id"] = str(mission_id)
        g["attempts"].append({
            "mission_id": str(mission_id),
            "attempt": len(g["attempts"]) + 1,
            "started_at": _now(),
            "ended_at": None,
            "ended_state": None,
            "note": str(note)[:200],
        })
        self._note(g, g["state"], g["state"],
                   "attempt %d bound to %s" % (len(g["attempts"]),
                                               mission_id))
        self.save(g)
        return g

    def release_mission(self, gid, ended_state, note=""):
        """Close the live attempt, recording how it ended.

        Does NOT transition the goal: how an attempt ending maps onto the
        goal's own state is lifecycle logic, and lifecycle is not this
        slice. This only stamps the attempt row and clears the binding.
        """
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        mid = g.get("current_mission_id")
        if not mid:
            raise ValueError("goal %s has no live attempt" % gid)
        for row in reversed(g["attempts"]):
            if row.get("mission_id") == mid and row.get("ended_at") is None:
                row["ended_at"] = _now()
                row["ended_state"] = str(ended_state) if ended_state else None
                if note:
                    row["note"] = str(note)[:200]
                break
        g["current_mission_id"] = None
        self._note(g, g["state"], g["state"],
                   "attempt %s ended (%s)" % (mid, ended_state))
        self.save(g)
        return g

    def attempt_count(self, gid):
        g = self.load(gid)
        return len(g["attempts"]) if g else 0

    # ----------------------------------------------------------- memory ---
    def record_learned(self, gid, kind, text, attempt=None, mission_id=None,
                       source="engine"):
        """Append ONE reusable fact. Append-only and de-duplicated.

        The distinction this store keeps:

          history  what happened -- every transition and attempt event, in
                   order, written by the methods that changed the goal
          learned  reusable knowledge a LATER attempt can act on

        Nothing here is inferred: every caller passes a fact that already
        exists in mission or goal state. No transcript is read and no model
        is asked -- arbitrary chat text is never promoted to memory.

        Previous knowledge is never overwritten. A repeat of the same fact
        (same kind, attempt, mission and text) is dropped rather than
        duplicated, so an idempotent lifecycle call cannot inflate memory.
        """
        if kind not in LEARNED_KINDS:
            raise ValueError("unknown learned kind %r" % (kind,))
        text = str(text or "").strip()
        if not text:
            raise ValueError("a learned item needs text")
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        key = "%s|%s|%s|%s" % (kind, attempt, mission_id, text[:200])
        rows = g.setdefault("learned", [])
        for existing in rows:
            if existing.get("dedupe_key") == key:
                return g                       # already known, not a dupe
        rows.append({
            "id": "l-" + uuid.uuid4().hex[:10],
            "kind": kind,
            "text": text[:1000],
            "attempt": attempt,
            "mission_id": mission_id,
            "source": source,
            "ts": _now(),
            "dedupe_key": key,
        })
        self._note(g, g["state"], g["state"],
                   "learned (%s): %s" % (kind, text[:120]))
        self.save(g)
        return g

    def learned(self, gid, kind=None):
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        rows = g.get("learned") or []
        return [r for r in rows if kind is None or r.get("kind") == kind]

    def memory(self, gid):
        """The smallest read surface a later API/UI needs.

        Scoped to THIS goal and its one chat: nothing here is global, and
        nothing is written to the Shadow instruction ledger, so existing
        replay and precedence behaviour is untouched.
        """
        g = self.load(gid)
        if g is None:
            raise ValueError("no goal %s" % gid)
        rows = g.get("learned") or []
        return {
            "goal_id": g["id"],
            "outcome": g.get("outcome"),
            "target_session": g.get("target_session"),
            "attempts": list(g.get("attempts") or []),
            "history": list(g.get("history") or []),
            "learned": list(rows),
            "blockers": [r for r in rows if r.get("kind") == "blocker"],
            "founder_guidance": [r for r in rows
                                 if r.get("kind") == "founder_guidance"],
        }

    # ------------------------------------------------------- invariants ---
    def active_for_session(self, target_session):
        """The one active goal holding this chat, or None.

        `ACTIVE` is every non-terminal state, so a draft holds its chat too:
        V5 allows exactly one active goal per chat and this slice
        deliberately implements no queue -- extra goals are refused, not
        parked. Queueing is a later, founder-pending decision (Q2).
        """
        for g in self.list(states=ACTIVE, target_session=target_session):
            return g
        return None

    # ------------------------------------------------------------ private --
    def _note(self, goal, from_state, to_state, note):
        """Append one row to the goal's own audit trail. Mutates in place;
        the caller saves."""
        goal.setdefault("history", []).append({
            "ts": _now(),
            "from": from_state,
            "to": to_state,
            "note": str(note or "")[:500],
        })
