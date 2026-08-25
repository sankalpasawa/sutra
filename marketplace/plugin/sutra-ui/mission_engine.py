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
          "done", "failed", "stopped")
TERMINAL = ("done", "failed", "stopped")

#: The legal-transition table IS the state machine: anything not listed here
#: raises, so an illegal hop is a bug at the call site, never silent drift.
TRANSITIONS = {
    "draft": ("brief_confirm", "stopped"),
    "brief_confirm": ("running", "queued", "draft", "stopped"),
    "running": ("paused", "done", "failed", "stopped"),
    "queued": ("running", "stopped"),
    "paused": ("running", "stopped", "failed"),
    "done": (), "failed": (), "stopped": (),
}

#: Templates are DATA. Invariants are enforced where the action happens:
#: never_say refuses in the loop before any sayer call; read_only is carried
#: on the mission for the say endpoint to enforce once tool-level scoping
#: exists (P5+); both are asserted by tests.
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
               target_session=None, done_when=None, manifest=None):
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
        self.save(m)
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": new_state, "seq": m["seq"],
            "note": note[:500]})
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
                 verifier=None):
        self.store = store
        self.sayer = sayer
        self.waiter = boundary_waiter
        self.reader = transcript_reader
        self.verifier = verifier

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
                return self.store.transition(
                    mid, "failed", "max turns (%d) reached" % m["max_turns"])
            say_text = self._next_say(m)
            if say_text == last_say:
                return self.store.transition(
                    mid, "stopped", "ping-pong detected (identical "
                                    "consecutive says)")
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
            if not ok:
                return self.store.transition(mid, "failed", "say refused")
            last_say = say_text
            arrived = await self.waiter(m)
            if arrived is False:
                return self.store.transition(
                    mid, "failed", "boundary wait timed out")
            m = self.store.load(mid)
            if m["state"] in TERMINAL or m["state"] == "paused":
                return m          # something terminal happened mid-turn
            m["turns_used"] += 1
            self.store.save(m)
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "say",
                "summary": say_text[:200]})
            transcript = self.reader(m)
            done, results = evaluate_done_when(m, transcript, self.verifier)
            # reload before any terminal decision: a takeover that landed
            # while we evaluated must win (codex fold)
            fresh = self.store.load(mid)
            if fresh["state"] in TERMINAL or fresh["state"] == "paused":
                return fresh
            if done:
                return self.store.transition(
                    mid, "done", "done_when met: %s"
                    % json.dumps(results)[:400])
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

    def _next_say(self, m):
        if m["turns_used"] == 0:
            return m.get("manifest") or m["objective"]
        unmet = [c.get("check") for c in m.get("done_when", [])
                 if not c.get("met")]
        return ("Continue toward: %s. Outstanding checks: %s"
                % (m["objective"], "; ".join(filter(None, unmet)) or "none"))

    def founder_stop(self, mid):
        return self.store.transition(mid, "stopped", "founder stop")

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
        running = self.store.list(states=("running",))
        if m.get("target_session") and any(
                r.get("target_session") == m["target_session"]
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
        m = self.store.load(mid)
        if m is None or m["state"] != "queued":
            raise ValueError("cancel_queued needs a queued mission")
        return self.store.transition(mid, "stopped", "cancelled from queue")

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
