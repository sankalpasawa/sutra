"""Goal <-> Mission binding (V5 slice 3).

The goal holds the OUTCOME and outlives its attempts. A mission is ONE
attempt. This module is the only place that knows how one maps onto the
other, so the mission engine keeps owning execution and the goal store keeps
owning persistence -- neither learns about the other.

    goal draft ──start_first_attempt()──► mission brief_confirm
                                              │ scheduler admits
                        on_attempt_start()    ▼
    goal working ◄──────────────────────  mission running
        │                                     │
        │  on_attempt_end() reads the mission's own final state:
        │     done                      ──►  goal done      (verified)
        │     blocked                   ──►  goal blocked   (ask the founder)
        │     paused/founder_confirm    ──►  goal verifying  (binding kept)
        │     paused/floor|intervened   ──►  no goal change  (binding kept)
        │     failed|stopped, machine   ──►  goal blocked
        │     failed|stopped, founder   ──►  goal stopped
        ▼
    goal blocked ──resume_goal()───────►  a NEW attempt, SAME chat

WHAT THIS SLICE DELIBERATELY DOES NOT DO: no fresh-chat retry, no goal
retargeting, no second goal for a retry, no change to clone_for_retry (a
retried clone carries no goal_id, so it stays a standalone mission with the
historical terminal behaviour). Resume is same-chat only.

Nothing in production calls this module yet -- there are no goal routes. It
is reached from shadow_runner's two hooks, which no-op for every mission
without a goal_id.
"""
import goal_store
import mission_engine

#: How an attempt's own final state maps onto its goal. `None` means the
#: goal is not moved at all.
_RELEASE_STATES = ("done", "blocked", "failed", "stopped")


def _load_pair(goal_id, gstore=None):
    gs = gstore or goal_store.GoalStore()
    g = gs.load(goal_id)
    if g is None:
        raise ValueError("no goal %s" % goal_id)
    return gs, g


# ------------------------------------------------------------- attempts --
def _new_attempt(goal_id, template, extra_turns, manifest):
    """Create + bind one attempt at `goal_id`, in the goal's OWN chat.

    Budget carries forward, it never resets: V5 is explicit that extending
    adds turns, because a reset lets a runaway goal loop forever behind a
    friendly button. So a resumed attempt starts at the turns already spent,
    with `extra_turns` added to the ceiling. Resuming a budget-exhausted
    goal with no extension therefore re-blocks on the first check -- which
    is the honest outcome, not a bug.

    Founder confirmations carry forward too: a founder_confirm check that
    was met in the previous attempt is a fact about the world, not about the
    attempt, so the new attempt inherits the previous mission's done_when
    (with its `met` stamps) rather than the goal's pristine copy.
    """
    gs, g = _load_pair(goal_id)
    if g.get("current_mission_id"):
        raise ValueError(
            "goal %s already has a live attempt (%s) -- end it before "
            "starting another" % (goal_id, g["current_mission_id"]))
    ms = mission_engine.MissionStore()
    prev = None
    if g["attempts"]:
        prev = ms.load(g["attempts"][-1]["mission_id"])
    checks = (prev or {}).get("done_when") or g.get("done_when") or []
    # the new attempt inherits what the goal already knows, unless the
    # caller supplied its own briefing
    if manifest is None:
        manifest = goal_context(goal_id)
    m = ms.create(g["outcome"], template,
                  target_mode="existing",          # never a fresh chat
                  target_session=g["target_session"],
                  done_when=[dict(c) for c in checks],
                  manifest=manifest,
                  goal_id=g["id"])
    if prev:
        m = ms.load(m["id"])
        m["turns_used"] = int(prev.get("turns_used") or 0)
        m["max_turns"] = int(prev.get("max_turns") or 0) + int(extra_turns)
        ms.save(m)
    elif extra_turns:
        m = ms.load(m["id"])
        m["max_turns"] = int(m["max_turns"]) + int(extra_turns)
        ms.save(m)
    m = ms.transition(m["id"], "brief_confirm",
                      "attempt %d of goal %s" % (len(g["attempts"]) + 1,
                                                 g["id"]))
    gs.bind_mission(g["id"], m["id"],
                    "attempt %d" % (len(g["attempts"]) + 1))
    # snapshot the budget NOW, so an extended ceiling is visible before the
    # resumed attempt has run a single turn. Check results are untouched --
    # a resumed goal keeps what it had already proven.
    gs.record_budget(g["id"], turns_used=m.get("turns_used"),
                     max_turns=m.get("max_turns"))
    return m


def start_first_attempt(goal_id, template="fix", extra_turns=0,
                        manifest=None):
    """The first attempt at a `draft` goal. Returns the mission, awaiting
    the founder's Start (brief_confirm) exactly like any other mission."""
    _gs, g = _load_pair(goal_id)
    if g["state"] != "draft":
        raise ValueError("start_first_attempt needs a draft goal, not %s"
                         % g["state"])
    return _new_attempt(goal_id, template, extra_turns, manifest)


def resume_goal(goal_id, extra_turns=0, template="fix", manifest=None):
    """Resume a BLOCKED goal in the SAME chat as a fresh attempt.

    A new mission, not a revived one: the blocked attempt stays on the
    record with how it ended, and the attempt number advances. The target
    chat is the goal's own and is never changed -- no fresh chat is created
    here, and no goal is ever retargeted.
    """
    _gs, g = _load_pair(goal_id)
    if g["state"] != "blocked":
        raise ValueError("resume_goal needs a blocked goal, not %s"
                         % g["state"])
    return _new_attempt(goal_id, template, extra_turns, manifest)


# -------------------------------------------------------------- the hooks --
def record_evaluation(mission, results, done=None):
    """Mirror ONE evaluation's per-check results onto the goal.

    Called from the engine's `on_evaluated` observer, so the goal's progress
    tracks the same evaluation the loop already ran -- same evaluator, same
    tiers, same evidence (Shadow-authored text already excluded upstream by
    shadow_runner.evidence_text). Nothing is re-evaluated here.

    A no-op for a mission with no goal_id.
    """
    gid = (mission or {}).get("goal_id")
    if not gid:
        return None
    gs = goal_store.GoalStore()
    if gs.load(gid) is None:
        raise ValueError("no goal %s" % gid)
    attempt = None
    g = gs.load(gid)
    for row in g.get("attempts") or []:
        if row.get("mission_id") == mission.get("id"):
            attempt = row.get("attempt")
    return gs.record_check_results(
        gid, results, mission_id=mission.get("id"), attempt=attempt,
        turns_used=mission.get("turns_used"),
        max_turns=mission.get("max_turns"))


def record_founder_confirmation(mission):
    """Reflect a founder's check confirmation on the goal IMMEDIATELY.

    MissionStore.confirm_check stays the ONLY writer of a founder_confirm
    `met` flag, and nothing here re-verifies or invents a tier. It merges
    two facts that already exist -- the mission's persisted `met` stamps
    (which only a founder action can set) and the goal's last evaluated
    results -- so a goal in `verifying` stops reporting a check the founder
    has already signed off, instead of waiting for the attempt to resume.

    Idempotent, and a no-op for a mission with no goal_id.
    """
    gid = (mission or {}).get("goal_id")
    if not gid:
        return None
    gs, g = _load_pair(gid)
    definitions = mission.get("done_when") or g.get("done_when") or []
    stored = {r.get("index"): r for r in g.get("check_results") or []}
    results = []
    for i, d in enumerate(definitions):
        prev = stored.get(i) or {}
        results.append({
            "tier": d.get("tier"),
            "check": d.get("check"),
            # last evaluated OR confirmed on the mission: never a downgrade
            "met": bool(prev.get("met")) or bool(d.get("met")),
        })
    attempt = None
    for row in g.get("attempts") or []:
        if row.get("mission_id") == mission.get("id"):
            attempt = row.get("attempt")
    return gs.record_check_results(
        gid, results, mission_id=mission.get("id"), attempt=attempt,
        turns_used=mission.get("turns_used"),
        max_turns=mission.get("max_turns"))


def on_attempt_start(mission):
    """An attempt reached `running`; the goal is now working.

    Idempotent, and a no-op for a mission with no goal_id.
    """
    gid = (mission or {}).get("goal_id")
    if not gid:
        return None
    gs, g = _load_pair(gid)
    if g["state"] == "working":
        return g
    if "working" not in goal_store.TRANSITIONS.get(g["state"], ()):
        raise ValueError("goal %s cannot start working from %s"
                         % (gid, g["state"]))
    return gs.transition(gid, "working",
                         "attempt %s running" % mission.get("id"))


def on_attempt_end(mission):
    """Reconcile the goal with the state its attempt actually finished in.

    Reads the mission record only -- it never re-evaluates checks, so a
    goal can reach `done` only because the engine's own done_when
    evaluation put the mission in `done`. Exhausting turns or being stopped
    can never complete a goal.
    """
    gid = (mission or {}).get("goal_id")
    if not gid:
        return None
    gs, g = _load_pair(gid)
    state = mission.get("state")
    target = None

    if state == "paused":
        # V5's `verifying`: every other tier is met and a founder_confirm
        # check is outstanding. The attempt is NOT over -- the same mission
        # resumes on confirmation -- so the binding is kept.
        if mission.get("pause_reason") == "founder_confirm":
            target = "verifying"
        # floor_confirm / founder_intervened leave the goal alone: Shadow is
        # paused in that chat and the founder is already present. Unchanged
        # safety behaviour, unchanged takeover behaviour.
    elif state == "done":
        target = "done"
    elif state == "blocked":
        target = "blocked"
    elif state in mission_engine.TERMINAL:
        # machine trouble asks the founder; only an explicit founder stop
        # abandons the goal (V5: a goal cannot die without being asked)
        target = "stopped" if mission.get("ended_by") == "founder" \
            else "blocked"

    # a draft goal whose attempt already ran was never marked working (the
    # start hook was skipped); normalise so the real transition is legal
    if target and target != "working" and g["state"] == "draft" \
            and "working" in goal_store.TRANSITIONS["draft"]:
        g = gs.transition(gid, "working", "attempt ran")

    if target and g["state"] != target:
        if target not in goal_store.TRANSITIONS.get(g["state"], ()):
            raise ValueError("goal %s cannot go %s -> %s"
                             % (gid, g["state"], target))
        note = mission.get("block_reason") or mission.get("pause_reason") \
            or ("attempt %s %s" % (mission.get("id"), state))
        if target == "blocked":
            # stamp the blocker on the goal too, so a blocked goal can say
            # what stopped it without loading the attempt that stopped
            g = gs.block(gid, mission.get("block_reason") or note, note)
        else:
            g = gs.transition(gid, target, note)

    # close the attempt row once the mission can no longer continue from
    # where it stopped. Idempotent: a second call finds nothing bound.
    if state in _RELEASE_STATES \
            and g.get("current_mission_id") == mission.get("id"):
        g = gs.release_mission(
            gid, state,
            mission.get("block_reason") or ("ended %s" % state))
    # an attempt that can no longer continue leaves what it learned behind,
    # so the NEXT attempt is not a blank slate. Deduped, so the idempotent
    # second call to this function records nothing new.
    if state in _RELEASE_STATES:
        g = _record_attempt_memory(gs, gid, mission) or g
    return g


# -------------------------------------------------------------- memory ---
def _record_attempt_memory(gs, gid, mission):
    """Turn ONE finished attempt into reusable facts. Deterministic.

    Every value comes from state that already exists on the mission or the
    goal -- no transcript is read, no model is asked, nothing is inferred.
    That is deliberate: the transcript is the chat's and Shadow's talk, and
    promoting arbitrary text from it into durable memory is exactly what
    this slice must not do.
    """
    g = gs.load(gid)
    if g is None:
        return None
    attempt = None
    for row in g.get("attempts") or []:
        if row.get("mission_id") == mission.get("id"):
            attempt = row.get("attempt")
    mid = mission.get("id")
    state = mission.get("state")
    turns = "%s/%s" % (mission.get("turns_used"), mission.get("max_turns"))

    results = g.get("check_results") or []
    proven = [r.get("check") for r in results if r.get("met")]
    outstanding = [r.get("check") for r in results if not r.get("met")]

    gs.record_learned(
        gid, "attempt_outcome",
        "attempt %s tried \"%s\" and ended %s after %s turns"
        % (attempt, (mission.get("objective") or "")[:160], state, turns),
        attempt=attempt, mission_id=mid)

    if mission.get("block_reason"):
        gs.record_learned(
            gid, "blocker",
            "attempt %s stopped on %s at %s turns%s"
            % (attempt, mission["block_reason"], turns,
               ("; still outstanding: " + "; ".join(
                   c for c in outstanding if c)) if outstanding else ""),
            attempt=attempt, mission_id=mid)

    if proven:
        gs.record_learned(
            gid, "checks_proven",
            "already satisfied: " + "; ".join(c for c in proven if c),
            attempt=attempt, mission_id=mid)

    if mission.get("result_excerpt"):
        gs.record_learned(gid, "result",
                          str(mission["result_excerpt"])[:800],
                          attempt=attempt, mission_id=mid)
    return gs.load(gid)


def record_founder_guidance(goal_id, text, attempt=None):
    """Keep something the founder EXPLICITLY said about this goal.

    Explicit is the whole point: this is only ever reached by a founder
    action (answering a blocked goal, adding an instruction to it), never by
    scraping the chat. It is scoped to this goal and its chat -- it is not
    written to the Shadow instruction ledger, so global memory, confirmation
    and precedence behaviour are all unchanged.
    """
    gs, _g = _load_pair(goal_id)
    if not str(text or "").strip():
        raise ValueError("founder guidance needs text")
    return gs.record_learned(goal_id, "founder_guidance", text,
                             attempt=attempt, source="founder")


def goal_context(goal_id):
    """The briefing a resumed attempt starts from, or None if nothing known.

    Deterministically composed from the goal's own stored facts, so a second
    attempt is not a blank slate: what was tried, what stopped it, what is
    already proven, what is still outstanding, and what the founder said.

    It is delivered as the new mission's MANIFEST, which means it rides
    turn 0 through the ordinary say path -- tagged as Shadow-authored, and
    therefore excluded from verification evidence by
    shadow_runner.evidence_text. Naming a satisfied check in here can never
    satisfy that check.
    """
    gs, g = _load_pair(goal_id)
    learned = g.get("learned") or []
    # ONLY finished attempts are history. The live attempt (if any) is the
    # one being briefed, so counting it would announce the wrong number.
    ended = [row for row in (g.get("attempts") or [])
             if row.get("ended_at") is not None]

    lines = []
    if ended:
        lines.append("This is attempt %d. Previous attempts:"
                     % (len(ended) + 1))
        for row in ended:
            lines.append("- attempt %s ended %s%s"
                         % (row.get("attempt"), row.get("ended_state"),
                            (" (%s)" % row["note"]) if row.get("note")
                            else ""))

    results = g.get("check_results") or []
    proven = [r.get("check") for r in results if r.get("met")]
    outstanding = [r.get("check") for r in results if not r.get("met")]
    if proven:
        lines.append("Already satisfied (do not redo): "
                     + "; ".join(c for c in proven if c))
    if outstanding:
        lines.append("Still outstanding: "
                     + "; ".join(c for c in outstanding if c))

    blockers = [r for r in learned if r.get("kind") == "blocker"]
    if blockers:
        lines.append("What has blocked this before:")
        lines.extend("- " + r["text"] for r in blockers[-3:])

    guidance = [r for r in learned if r.get("kind") == "founder_guidance"]
    if guidance:
        lines.append("What the founder told me about this goal:")
        lines.extend("- " + r["text"] for r in guidance)

    # nothing worth saying -> say nothing. A context with a header and no
    # content would be noise in the prompt and a lie in the UI.
    if not lines:
        return None
    return "\n".join(
        ["[Goal context] Outcome: %s" % g.get("outcome")]
        + lines
        + ["Continue toward the outcome. Do not start over."])


# ------------------------------------------------------------- founder ---
def abandon(goal_id, note="founder abandoned the goal"):
    """The founder gives up on the outcome: the goal is stopped.

    Stops the live attempt through the existing founder path, so the
    mission's own stop semantics and its `ended_by` stamp are reused rather
    than duplicated.
    """
    gs, g = _load_pair(goal_id)
    if g["state"] in goal_store.TERMINAL:
        return g                                   # already finished
    mid = g.get("current_mission_id")
    if mid:
        ms = mission_engine.MissionStore()
        m = ms.load(mid)
        if m and m["state"] not in mission_engine.TERMINAL:
            mission_engine.MissionEngine(ms, None, None, None).founder_stop(
                mid)
    g = gs.transition(goal_id, "stopped", note)
    if g.get("current_mission_id") == mid and mid:
        g = gs.release_mission(goal_id, "stopped", note)
    return g
