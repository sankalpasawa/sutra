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
import hashlib
import json
import os
import re
import time
import uuid

import providers
import shadow_egress
import shadow_intervention
import shadow_ledger
import shadow_judge
import shadow_probe
import shadow_protocol

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
#:
#: `brief_confirm -> failed` and `queued -> failed` exist for ONE caller:
#: shadow_runner.start_mission_async's error handler, which is the only place
#: that can know a start never got off the ground. It already guarded on
#: exactly these two states -- they are the two an accepted-but-unlaunched
#: mission can be sitting in -- and then called transition(..., "failed"),
#: which raised ValueError because neither row listed it. The raise was
#: swallowed by that handler's own `except Exception: pass`, so a provisioning
#: failure (a delegate spawn that dies at argv, a full disk, an interpreter
#: without process_group) left the mission frozen in brief_confirm with
#: start_requested_at set -- which the task list renders as QUEUED with no
#: Start button, forever. The failure had nowhere legal to go, so it went
#: nowhere.
#:
#: This adds no state and changes no successful path: `failed` already exists,
#: is already TERMINAL, and is already what `running -> failed` means. It is
#: reachable from two more starting points, so the existing handler can
#: finish its sentence and the row becomes a normal failed task the founder
#: can Retry.
TRANSITIONS = {
    "draft": ("brief_confirm", "stopped"),
    "brief_confirm": ("running", "queued", "draft", "failed", "stopped"),
    "running": ("paused", "blocked", "done", "failed", "stopped"),
    "queued": ("running", "failed", "stopped"),
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

#: SHADOW'S OWN MACHINERY BROKE -- the work did not (founder, 2026-09-16).
#:
#: These reasons name a fault in the SUPERVISOR: the decider subprocess died
#: without answering, or answered with something `validate_decision` cannot
#: read. Measured twice on 2026-09-15 (m-07cbb61906cc, m-5c2fca3f824b): both
#: missions were transitioned `failed` one second after a re-adoption, and on
#: the second one the worker went on to finish successfully 96 seconds LATER
#: and had its result thrown away. Nothing about the delegate, the objective
#: or the checks was consulted -- `evaluate_done_when` is 130 lines further
#: down the loop and the undecided branch returns before reaching it.
#:
#: So an infra fault takes the RECOVERABLE exit rather than the terminal one.
#: `blocked` already means exactly this and already exists: non-terminal, the
#: delegate is deliberately kept alive, the UI reads it as NEEDS YOU, and
#: Resume works. It is what _out_of_road already did for a GOAL attempt --
#: this only stops a standalone mission being the one case that dies of its
#: supervisor's illness.
#:
#: THE SECOND AND THIRD FAULTS OF THE SAME CLASS (founder, 2026-09-16):
#:
#:   no_live_runtime    the say never left the engine. By the sayer's own
#:                      contract a NAMED precondition means nothing was sent
#:                      and nothing was spent -- the opposite of a verdict on
#:                      the work. Measured on m-6b177e1cbdf0 ("Budget per
#:                      task", 2026-09-15): the founder answered Shadow's
#:                      question and CONFIRMED check #2 at 20:50:50Z, the
#:                      loop relaunched, its first say found no runtime for
#:                      the delegate, and the mission was `failed` at
#:                      20:51:01Z -- eleven seconds after the founder had
#:                      signed off, with the work already on disk.
#:   shadow_eval_failed the evidence reader or the evaluator itself raised.
#:                      "I could not tell whether the work is done" is not
#:                      "the work failed"; it is the one question a founder
#:                      can settle in a second.
#:
#: A GOAL attempt already blocked on all three. This is the standalone half.
#: `shadow_crashed` (the runner's own last-resort handler in
#: shadow_runner._launch) is the fourth. It never reaches _out_of_road -- it
#: blocks directly -- but it is listed so the supervisor's faults are one
#: list and a reader looking for "is this Shadow's fault" finds them all.
INFRA_BLOCK_REASONS = frozenset({
    "shadow_undecided",
    "no_live_runtime",
    "shadow_eval_failed",
    "shadow_crashed",
})

#: Stamped beside block_reason so a reader can tell the two apart without
#: parsing prose. "shadow_infra" = the supervisor broke; absent = the ordinary
#: out-of-road reasons (budget, ping-pong, stalled turn, refused say).
INFRA_FAILURE_CLASS = "shadow_infra"

#: how much of the target's latest output the decider is shown. Bounded on
#: purpose: the whole transcript is neither necessary nor affordable, and
#: evidence assembly already excludes Shadow's own turns upstream.
DECISION_TAIL = 2000
DECISION_INSTRUCTION_MAX = 2000


#: The decider prompt shows the shape it wants by EXAMPLE, and the example's
#: fields are angle-bracket placeholders. A model that answers with the
#: example verbatim is not deciding -- it is copying the form.
_TEMPLATE_ECHOES = frozenset({
    "<what to send into the chat next>",
    "<one short line: why this, now>",
    "<what you need from the founder>",
    "<one short line>",
})


def _is_template_echo(instruction):
    """Is this the decider's own placeholder rather than an instruction?

    THE LIVE FAILURE (founder, 2026-09-15, mission m-245777cf1467). After
    resume_after_restart re-adopted a delegate, the decider answered with the
    example straight out of its own prompt:

        {"action": "continue",
         "instruction": "<what to send into the chat next>",
         "reason": "<one short line: why this, now>"}

    `instruction` was a non-empty string, so this validated, and the runner
    said `<what to send into the chat next>` INTO THE DELEGATE CHAT. It did
    it twice, the ping-pong guard saw two identical says, and the mission was
    stopped one second after it had been rescued.

    Why the model echoes: a resumed loop starts with last_response = None, so
    the decider's first turn after any resume is composed with an empty "what
    the target said back". That is a separate weakness and is NOT addressed
    here -- this only stops its output from being mistaken for a decision.

    DELIBERATELY NARROW. An instruction is rejected only when, after
    stripping, it IS one of the prompt's placeholders (case-insensitively).
    A real instruction that merely CONTAINS angle brackets -- "replace <sid>
    in the config", "the <div> is unclosed", quoting a diff -- is untouched,
    because a substring or bracket-shape test would refuse ordinary
    engineering English, which is most of what Shadow says.

    Returning None routes into the caller's EXISTING honest-failure path (R10:
    a malformed decision must not degrade into a generic nudge). No new state
    and no new action.
    """
    s = str(instruction or "").strip()
    return s.lower() in _TEMPLATE_ECHOES


#: Tiers a DECIDER may write. `founder_confirm` (the founder signs it off)
#: and `verify` (a deterministic verifier settles it) only.
#:
#: contains_artifact IS DELIBERATELY NOT HERE. It is evaluated as
#: `check in transcript_text` -- a literal substring search over the worker's
#: words -- so a check describing a STATE can never be satisfied by doing the
#: thing, only by uttering the sentence. The founder-typed path already
#: refused it for exactly that reason (2026-09-15); a Shadow-written check
#: must not reach it either.
#: `judge` ADDED 2026-09-20 (founder D-SH-1). A check that no probe can
#: settle and that is not the founder's taste is read by shadow_judge against
#: the DIFF, not against the worker's account of the diff. See
#: shadow_judge's header for why that is review rather than self-grading, and
#: shadow_protocol.tier_for for the ladder that routes a check here.
DECIDER_TIERS = ("founder_confirm", "verify", "judge")

#: A mission the founder left open should not be handed twenty checks.
MAX_DECIDER_CHECKS = 6


#: How many standing instructions one task may carry, and how long each may
#: be. Small on purpose: this is the set of constraints that governs a task,
#: not a transcript of everything the founder ever said -- that is
#: `founder_says`, which is never trimmed.
MAX_STANDING = 8
STANDING_MAX_CHARS = 300


def validate_standing(raw):
    """The active instruction set a decider wrote, or None for "not sent".

    THREE OUTCOMES, AND THE DIFFERENCE MATTERS:

      None  the key was absent or unusable -> KEEP the set that is already on
            the record. A one-shot fallback decider, an older model, or a
            malformed reply must never be able to silently drop the
            constraints the founder is relying on.
      []    the key was an empty list -> CLEAR the set. That is the founder
            relaxing everything, and it has to be expressible.
      [..]  the new active set, replacing the old one whole. Supersession is
            therefore just "Shadow sends the set that still applies": there
            is no edit language to get wrong, and two contradictory rules
            cannot both survive because only one list exists.

    Lenient per row for the same reason validate_done_when is: one bad entry
    must not cost the instruction that came with it.
    """
    if not isinstance(raw, list):
        return None
    out = []
    for row in raw:
        text = str(row if isinstance(row, str) else
                   (row.get("text") if isinstance(row, dict) else "") or "")
        text = " ".join(text.split())
        if not text or text in out:
            continue
        out.append(text[:STANDING_MAX_CHARS])
        if len(out) >= MAX_STANDING:
            break
    return out


def validate_done_when(raw):
    """The checks a decider wrote, or [] if they are not usable.

    Lenient where the cost of refusing is high and strict where the cost of
    accepting is: a single malformed row is dropped, the rest stand, and a
    payload that is not a list at all yields nothing. Never raises -- the
    caller is mid-decision and a bad criteria list must not cost the
    instruction that came with it.
    """
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        check = str(row.get("check") or "").strip()
        if not check:
            continue
        # ONE LADDER, IN ONE PLACE (D-SH-1). This used to read
        # `str(row.get("tier")) or "founder_confirm"` -- a default that is how
        # all 9 checks on the founder's live install reached their desk, every
        # one carrying `proposed_tier: None`.
        #
        # THE LADDER LIVES IN shadow_protocol.tier_for AND IS NOT RE-DERIVED
        # HERE. An earlier version of this change screened the tier inline and
        # got it wrong in a way a test caught: a TASTE check arriving with no
        # tier at all skipped the founder-only screen entirely, because the
        # screen was written to run only on a row that already said
        # `founder_confirm`. Delegating removes the second opinion that could
        # drift from the proposal path -- which is what the old comment here
        # claimed to be doing and was not.
        tier = str(row.get("tier") or "").strip()
        if tier and tier not in DECIDER_TIERS:
            continue                  # a tier a decider may not write at all
        tier = shadow_protocol.tier_for(check, tier or None, row.get("probe"))
        if tier not in DECIDER_TIERS:
            # `contains_artifact` is reachable from the ladder and is NOT a
            # decider tier: it is `check in transcript_text`, so a check
            # describing a state could be satisfied by the worker uttering the
            # sentence. The founder-typed path refused it for that reason in
            # 2026-09-15 and a Shadow-written check must not reach it either.
            tier = shadow_protocol.FALLBACK_TIER
        # A PROBE IS `verify` ONLY, AND `verify` IS A PROBE ONLY
        # (resolve_verify_tier). founder_confirm is the founder's signature
        # on a judgement ("is this what I wanted?") and a filesystem fact
        # cannot stand in for one, so a probe there is ignored -- a machine
        # must not sign the founder's name. And a `verify` with no probe
        # behind it is demoted rather than dropped: the wording survives, the
        # claim that Shadow checked it does not.
        tier, probe = resolve_verify_tier(tier, row.get("probe"))
        row_out = {"tier": tier, "check": check[:DECISION_INSTRUCTION_MAX]}
        if probe:
            row_out["probe"] = probe
        out.append(row_out)
        if len(out) >= MAX_DECIDER_CHECKS:
            break
    return out


def resolve_verify_tier(tier, raw_probe):
    """THE RULE: a `verify` check without a valid probe is not a verify check.

    Returns `(tier, probe_or_None)` after applying it.

    WHY THIS EXISTS (founder, 2026-09-17). `verify` promises the founder
    "Shadow ran this check and it passed" -- that is HOW_MET's exact wording,
    stamped onto the completion record. Only a probe makes it true. Without
    one the tier falls through to `_shadow_verifier`, which asks whether the
    WORKER emitted a DONE-CHECK line quoting the check: a fact about what was
    said, never about what is. So a probe-less `verify` let Shadow tell the
    founder it had verified something it never looked at. That is the
    loophole this closes, and it is closed deterministically rather than by
    asking the model nicely -- a prompt cannot be audited and this can.

    DEMOTE, NEVER DROP, and never re-word. The check keeps its exact text and
    becomes the founder's to sign. Dropping would lose a requirement the
    founder may need; demoting costs one signature. That is the same choice
    shadow_protocol.tier_for has made on the PROPOSAL path since before
    probes existed -- "an unknown tier, `verify`, or a missing tier all
    resolve deterministically" -> founder_confirm. This is that rule, applied
    to the one path that had exempted itself.

    VALIDATION TIME ONLY. evaluate_done_when is untouched: a probe-less
    `verify` already on disk keeps scoring exactly as it did, and nothing
    re-tiers a persisted mission. The rule binds what is written from here
    on, which is the same shape every other tier decision in this file has.
    """
    if tier != "verify":
        return tier, None
    probe = shadow_probe.validate_probe(raw_probe)
    if probe:
        return "verify", probe
    # DEMOTE TO THE JUDGE, NOT TO A SIGNATURE (D-SH-1). The rule above is
    # unchanged -- a probe-less `verify` is not a verify check and never
    # gets to claim "Shadow ran this check and it passed". What changed is
    # where it lands: the judge reads the diff and can still settle it, and
    # says `cannot_tell` when it cannot, which is the founder's row arriving
    # by the honest route instead of by default.
    return shadow_protocol.FALLBACK_TIER, None


#: How many verification rows one decision may carry. A mission has at most
#: MAX_DECIDER_CHECKS checks, so anything beyond that is noise.
MAX_VERIFICATION = MAX_DECIDER_CHECKS


def validate_verification(raw):
    """Verification metadata a decision may carry: [{index, probe}, ...].

    THE CHECK TEXT IS NOT IN THIS SHAPE, AND THAT IS THE POINT (founder,
    2026-09-17). Shadow is asked HOW an existing condition can be established,
    never WHAT the condition is. A row names a check by INDEX and carries a
    probe; there is no field here through which a model could re-word, replace
    or drop what the founder wrote, because the wording never makes the round
    trip.

    Strict, and a bad row costs only itself: an unusable probe or a
    nonsense index is dropped and the check keeps the tier it already had.
    That direction is safe -- a check with no probe is judged by the founder,
    which is strictly harder to satisfy than a probe is to pass.
    """
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        # bools are ints in python and an index of True is a bug, not a row
        if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0:
            continue
        if idx in seen:
            continue                  # first answer for an index wins
        probe = shadow_probe.validate_probe(row.get("probe"))
        if not probe:
            continue                  # "I cannot verify this" -- say nothing
        seen.add(idx)
        out.append({"index": idx, "probe": probe})
        if len(out) >= MAX_VERIFICATION:
            break
    return out


def _carry_verification(out, raw):
    """ADDITIVE, exactly like `done_when` and `standing`: a decision MAY carry
    verification metadata for checks that already exist. Absent or unusable
    leaves `out` byte-identical to what validate_decision returned before."""
    rows = validate_verification(raw.get("verification"))
    if rows:
        out["verification"] = rows


def _carry_standing(out, raw):
    """ADDITIVE, exactly like `done_when` and `intervention`: a decision MAY
    carry the active instruction set. Absent or unusable leaves `out`
    byte-identical to what validate_decision returned before, so every
    existing decision and every test of one is unaffected."""
    standing = validate_standing(raw.get("standing"))
    if standing is not None:
        out["standing"] = standing


#: The only reasons an `ask_founder` is admitted MID-MISSION (founder
#: D-SH-1, 2026-09-20: "only the absolute absolute essential essential stuff
#: should shadow ask the user ... even in intermediate phases in the chat").
#:
#: The done-when tiering fixed the END of a mission -- what the founder signs
#: off when the work is finished. It did nothing about the MIDDLE, where
#: `ask_founder` could raise anything at all and park the mission on it. The
#: same sentence has to govern both, so it is the same three categories:
#:
#:   floor          the say or the plan trips a confirm-first floor. These
#:                  are unrecoverable and no setting reaches above them.
#:   founder_fact   a fact only the founder holds and no artifact contains:
#:                  a credential, a budget ceiling, which region, which of
#:                  two things they actually want.
#:   taste          a question with no correct answer, only theirs.
#:
#: ANYTHING ELSE IS SHADOW'S OWN WORK. "Do the tests pass", "does this
#: build", "is this the right file", "did the fix land" are all questions
#: with an answer on the machine Shadow is already running on.
ASK_KINDS = ("floor", "founder_fact", "taste")

#: HOW MANY TIMES ONE MISSION MAY HAVE AN ASK REFUSED BEFORE THE NEXT ONE IS
#: ADMITTED WHATEVER IT SAYS.
#:
#: WITHOUT THIS THE GATE EATS THE MISSION. A refused ask becomes a `continue`
#: carrying ASK_REFUSED_INSTRUCTION, which is a FIXED string -- so a decider
#: that asks a refused question twice running produces two identical says and
#: trips the ping-pong guard, which ends the mission `stopped`. The founder
#: would then get a task that quietly died instead of a question, which is
#: strictly worse than the question they did not want.
#:
#: TWO, NOT ONE, AND NOT SIX. One would make the gate advisory -- ask, get
#: told to go and look, ask again, get through. Two means Shadow must
#: actually go and look, come back still stuck, and only then is it believed.
#: Beyond that the founder is better served by a question than by a mission
#: grinding its remaining budget against something it cannot resolve.
ASK_REFUSAL_LIMIT = 2

#: What Shadow is told to do instead, when an ask is refused. Deliberately an
#: INSTRUCTION TO THE WORKER and not a scolding of the decider: the mission
#: keeps driving, which is the entire point of refusing.
ASK_REFUSED_INSTRUCTION = (
    "Establish this yourself rather than asking the founder: %s. "
    "You have full access to the workdir -- read the files, run the "
    "command, check the output. If a command settles it, write the check "
    "as a `verify` row with a `command_succeeds` probe so it settles "
    "itself from now on. Only taste, a credential or a budget the founder "
    "alone holds, or a confirm-first floor may be escalated.")


def screen_ask(decision):
    """May this `ask_founder` reach the founder? -> (admitted, why).

    THE SCREEN IS ON THE QUESTION, NOT ON THE LABEL. A decider that writes
    `ask_kind: "taste"` over "do the tests pass" is not asking about taste,
    and honouring the label would make the whole gate a formality a model can
    walk through by typing a word. So the label says which test to apply and
    the TEXT has to pass it.

    NEVER RAISES, and A SCREENING FAULT FAILS OPEN -- the one place in this
    change that does, and deliberately: a bug in the screen must not silently
    swallow a question about something irreversible. The cost of failing open
    is a question the founder did not need; the cost of failing closed is a
    mission that quietly does something they would have stopped.

    FAILING OPEN IS FOR A FAULT, NOT FOR AN EMPTY ASK. A decision with no
    question in it at all is REFUSED rather than admitted, because there is
    nothing in it to put to anybody -- admitting it would park the mission on
    a blank card. That case does not arise in the loop (it checks `decision is
    not None` first) and is pinned here so the two are not confused.

    A `confirms_check` ask is admitted without further screening. It is
    asking for a signature on a row that shadow_protocol has ALREADY ruled is
    the founder's -- re-screening it here would be a second opinion on a
    question that was settled by the tier ladder, and the two could drift.
    """
    try:
        iv = (decision or {}).get("intervention") or {}
        if iv.get("confirms_check"):
            return True, "confirms a founder_confirm check"
        kind = str((decision or {}).get("ask_kind") or "").strip().lower()
        text = " ".join(str(x) for x in (
            (decision or {}).get("reason") or "",
            iv.get("question") or "", iv.get("context") or "",
            " ".join(str(f.get("label") or "")
                     for f in (iv.get("fields") or [])
                     if isinstance(f, dict)),
        ) if x)
        if kind == "floor":
            floors = shadow_egress.floor_check(text)
            if floors:
                return True, "floor: %s" % ", ".join(floors)
            return False, "declared a floor, but nothing in it trips one"
        if kind in ("founder_fact", "taste"):
            if shadow_protocol.is_founder_only(text):
                return True, kind
            return False, ("declared %s, but this is a question with an "
                           "answer on the machine" % kind)
        # NO LABEL AT ALL is the historical shape, and it is the shape every
        # ask on the founder's live install had. It is screened on the text
        # alone rather than refused outright, so a decider that genuinely
        # needs a credential still gets through without knowing the key
        # exists -- and one that wants to know whether the tests passed
        # does not.
        floors = shadow_egress.floor_check(text)
        if floors:
            return True, "floor: %s" % ", ".join(floors)
        if shadow_protocol.is_founder_only(text):
            return True, "founder-only question"
        return False, "nothing here is taste, a founder-held fact, or a floor"
    except Exception as exc:              # noqa: BLE001 -- see docstring
        return True, "screen unavailable: %s" % str(exc)[:80]


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
        if _is_template_echo(instruction):
            return None               # the PROMPT's own example, not a decision
        out = {"action": action, "reason": reason,
               "instruction": instruction[:DECISION_INSTRUCTION_MAX]}
        # ADDITIVE, exactly like `intervention` below: a continue MAY carry
        # the checks Shadow wrote for a mission the founder left without any.
        # Absent or malformed -> the key is simply not there and `out` is
        # byte-identical to what this returned before, so every existing
        # decision and every test of one is unaffected. A bad list degrades to
        # no criteria rather than failing the decision: the instruction is
        # still worth sending, and Shadow is asked again next turn.
        checks = validate_done_when(raw.get("done_when"))
        if checks:
            out["done_when"] = checks
        # ...and HOW to establish checks that already exist, by index. A
        # separate key from `done_when` because they answer different
        # questions: that one is WHAT must be true, this one is how Shadow
        # will find out. Carrying them separately is what lets the second be
        # accepted for a check the first may not touch.
        _carry_verification(out, raw)
        _carry_standing(out, raw)
        return out
    out = {"action": action, "reason": reason, "instruction": ""}
    # VERIFICATION RIDES EITHER SHAPE. Shadow working out how to check
    # something is not a reason to send the worker a turn, so an
    # `ask_founder` that also settled a verification question must not lose
    # it.
    _carry_verification(out, raw)
    # ...and on THIS shape too: the founder can change what governs the task
    # on a turn Shadow ends by asking them something, and that set must not
    # be lost because the action was not `continue`.
    _carry_standing(out, raw)
    # ADDITIVE, AND ONLY HERE. An ask_founder MAY carry a typed request
    # (shadow_intervention.validate_request). When it does not -- or when the
    # payload is malformed -- `out` is byte-identical to what this function
    # returned before, so every existing ask_founder keeps its prose-only
    # behaviour and every existing test of it is unaffected. A malformed
    # intervention degrades to prose rather than failing the decision: the
    # founder still gets asked, just without the form.
    iv = shadow_intervention.validate_request(raw.get("intervention"))
    if iv is not None:
        out["intervention"] = iv
    # ADDITIVE, AND SHAPE ONLY (D-SH-1). Whether the ask is ADMITTED is
    # `screen_ask`'s question, asked by the loop with the mission in hand;
    # this only carries the label through so the screen has it. An unknown
    # or absent label is simply not carried, which is the historical shape
    # and which screen_ask handles on the text alone.
    kind = str(raw.get("ask_kind") or "").strip().lower()
    if kind in ASK_KINDS:
        out["ask_kind"] = kind
    return out


#: The BUILT-IN kinds, not the whole catalogue. templates() below merges
#: these with every kind the founder has ever minted, and offered_kinds()
#: says which of them Shadow currently presents. This constant stays exported
#: because it is what an unconfigured install offers and what several tests
#: build their fixtures around.
TEMPLATES = {
    "feature": {"max_turns": 30, "invariants": ()},
    "fix": {"max_turns": 20, "invariants": ()},
    "research": {"max_turns": 15, "invariants": ("read_only",)},
    "watch": {"max_turns": 0, "invariants": ("never_say",)},
}

#: The DEFAULT cap, not the cap. Every admission decision now goes through
#: max_running() below, which prefers the founder's setting and falls back to
#: this. The constant stays exported because it is what an unconfigured
#: install runs at and what several tests build their fixtures around.
MAX_RUNNING = 5

#: The band the setting is clamped into. One running task is the floor --
#: zero would be a pause switch wearing a cap's clothes, and Shadow already
#: has stop/pause for that, so a 0 must not silently become "nothing ever
#: starts again". The ceiling is not a taste call: each running mission owns
#: a live worker process and its own turn budget, so the number is bounded by
#: what one machine can actually host, not by what the stepper can reach.
MIN_RUNNING = 1
RUNNING_CEILING = 20


def limits_path():
    """The one file the founder-set task limits live in.

    Beside the ledgers and the mission files, under the SAME resolver
    (shadow_ledger.shadow_home), so a test that redirects the shadow home
    redirects this too and can never write a limit into the live install.

    NOT "settings.json", deliberately: providers.SETTINGS_PATH is already a
    settings.json and several test modules point BOTH at one tmp dir. Two
    unrelated stores sharing a filename is a collision waiting for the run
    order to expose it.
    """
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "task-limits.json")


def _read_limits():
    import json_store
    return json_store.read_json(limits_path(), {})


def clamp_running(n):
    """Coerce anything to a legal cap, or raise ValueError.

    Raises rather than silently clamping on a non-number, because a settings
    write that quietly stores 5 when the founder typed "five" is worse than
    one that says no. Out-of-band NUMBERS do clamp: a stepper held down past
    the ceiling should stop at the ceiling, not error.
    """
    try:
        v = int(n)
    except (TypeError, ValueError):
        raise ValueError("running_at_once must be a whole number")
    return max(MIN_RUNNING, min(RUNNING_CEILING, v))


def max_running():
    """The cap admission ACTUALLY enforces: the founder's setting, else the
    default.

    NEVER RAISES. This is read on every admission path and inside the runner's
    restart sweep; a corrupt settings file, an unreadable home, or the
    shadow_home pytest refusal must degrade to the default rather than take
    down a mission that was otherwise fine. read_json already swallows
    missing/corrupt, so the try here is for the home resolution itself.
    """
    try:
        raw = _read_limits().get("running_at_once")
    except Exception:                     # noqa: BLE001 -- see docstring
        return MAX_RUNNING
    if raw is None:
        return MAX_RUNNING
    try:
        return clamp_running(raw)
    except ValueError:
        return MAX_RUNNING                # a hand-edited junk value


#: "How Shadow behaves" -- the founder's own words (Shadow v4 C7, ADR-043).
#: One verbose text, in the SAME task-limits store as the numbers, read at
#: every Shadow boot (shadow_session.standing_context) and appended under
#: HOW SHADOW BEHAVES. The ceiling keeps the boot context bounded; it is a
#: cut, not a refusal, because a founder who writes at length should keep
#: the first 4000 characters rather than lose the whole text.
BEHAVES_MAX_CHARS = 4000

#: WHAT SHADOW SHOULD REMEMBER, in the founder's own words (founder,
#: 2026-09-17). The `global`/`per_chat` rule list below it is what Shadow has
#: LEARNED and the founder has CONFIRMED -- an append-only record with its own
#: provenance, and not a thing to hand a text cursor to. This field is the
#: other half: what the founder simply wants remembered, typed directly, with
#: no confirmation round-trip. Two different questions, so two different
#: stores; nothing here rewrites a learned rule.
MEMORY_MAX_CHARS = 4000


def behaves():
    """The founder's behaves text, or "". NEVER RAISES: this rides every
    Shadow boot, and a corrupt file must cost the text, never the boot."""
    try:
        raw = _read_limits().get("behaves")
    except Exception:                     # noqa: BLE001 -- see docstring
        return ""
    if not isinstance(raw, str):
        return ""                         # a hand-edited junk value
    return raw[:BEHAVES_MAX_CHARS]


def memory():
    """The founder's memory text, or "". NEVER RAISES, for the same reason
    behaves() never raises: it rides every Shadow boot and a corrupt file
    must cost the text, never the boot."""
    try:
        raw = _read_limits().get("memory")
    except Exception:                     # noqa: BLE001 -- see docstring
        return ""
    if not isinstance(raw, str):
        return ""                         # a hand-edited junk value
    return raw[:MEMORY_MAX_CHARS]


#: THE TWO TEXTS AS ONE BLOCK, and ONE RENDERER so the precedence sentence
#: cannot drift between the readers. Three of them: Shadow's own boot
#: (shadow_session.standing_context), every task chat (which boots on that
#: same context), and the one-shot decider (shadow_runner.render_decide_prompt),
#: which is a fresh process with no persona and therefore reads none of it
#: unless it is handed it here.
#:
#: THE TWO ARE NOT THE SAME KIND OF THING and the block says so. `behaves` is
#: POLICY -- when to check in, what to ask before doing -- and it is ranked
#: explicitly, because a founder rule that outranks nothing is decoration.
#: `memory` is FACT: who the founder is, what matters. It must never read as
#: permission, so the heading says it cannot widen what Shadow may do. A fact
#: that is wrong costs a wrong sentence; a policy that is wrong costs an
#: action nobody asked for, and the two must not be confusable in a prompt.
_BEHAVES_HEAD = (
    "HOW SHADOW BEHAVES (the founder's own words; they rank below the "
    "floors and below what the founder says in a task's own chat, and "
    "above the standing instructions):\n")
_MEMORY_HEAD = (
    "WHAT THE FOUNDER WANTS CARRIED INTO EVERY TASK (the founder's own "
    "words). This is CONTEXT, NOT PERMISSION: it tells you who you work "
    "for and what matters to them, and it can never widen what Shadow is "
    "allowed to do. Nothing here outranks a floor or a standing "
    "instruction:\n")


def carry_block():
    """Both founder texts, each under its heading, or "" when both are empty.

    NEVER RAISES, for the same reason behaves() and memory() never raise:
    this rides every Shadow boot, every task chat boot and every decision,
    and a corrupt limits file must cost the text, never the turn.
    """
    parts = []
    try:
        beh = behaves()
    except Exception:                     # noqa: BLE001 -- see docstring
        beh = ""
    try:
        mem = memory()
    except Exception:                     # noqa: BLE001 -- see docstring
        mem = ""
    if beh:
        parts.append(_BEHAVES_HEAD + beh)
    if mem:
        parts.append(_MEMORY_HEAD + mem)
    return "\n\n".join(parts)


def set_memory(text):
    """Persist it (trimmed, cut at the ceiling). Returns what was stored.
    Refuses non-text rather than coercing, exactly as set_behaves does."""
    if not isinstance(text, str):
        raise ValueError("memory must be text")
    v = text.strip()[:MEMORY_MAX_CHARS]
    import json_store
    cur = _read_limits()
    cur["memory"] = v
    json_store.write_json(limits_path(), cur)
    return v


def set_behaves(text):
    """Persist the text (trimmed, cut at the ceiling). Returns what was
    stored. Refuses non-text rather than coercing it: storing "42" when the
    founder's client sent a number is worse than saying no."""
    if not isinstance(text, str):
        raise ValueError("behaves must be text")
    v = text.strip()[:BEHAVES_MAX_CHARS]
    import json_store
    cur = _read_limits()
    cur["behaves"] = v
    json_store.write_json(limits_path(), cur)
    return v


#: The two boxes on "What Shadow knows", by the name Shadow calls them when
#: it writes one. Each entry is (reader, writer, ceiling).
REMEMBER_KINDS = ("personality", "memory")


def _remember_parts(kind):
    if kind == "personality":
        return behaves, set_behaves, BEHAVES_MAX_CHARS
    if kind == "memory":
        return memory, set_memory, MEMORY_MAX_CHARS
    raise ValueError("kind must be personality|memory")


def remember(kind, line):
    """Add ONE line the founder said in a Shadow chat to one of their boxes.

    THIS IS THE WHOLE FEATURE. The founder should not have to open a settings
    page and type what they already told Shadow in conversation -- "always run
    the suite before you push", "I'm the CEO, Meraki Labs is the holding
    company". Shadow hears it, calls this, and the box fills itself.

    THE TWO BOXES ANSWER DIFFERENT QUESTIONS and the caller picks:
      personality -> HOW to act. When to check in, what to ask before doing,
                     what to leave alone.
      memory      -> WHAT is true. Who the founder is, what matters, what to
                     never forget.

    WRITTEN AS THE FOUNDER'S OWN WORDS, one line each. Newlines are collapsed
    because these boxes read as a list of lines, and a pasted paragraph turns
    that list into prose nobody can revoke a single item of.

    IDEMPOTENT. Shadow hearing the same instruction twice must not write it
    twice -- the founder would be reading their own words back in duplicate
    and wondering which one binds. Matched case-insensitively on the trimmed
    line, which is enough for "the same sentence again" and deliberately not
    enough for "a rephrasing" (that is the founder's call, in the box).

    FULL MEANS THE OLDEST GOES. The box is a running note, and what the
    founder just said is the part they most likely meant; silently refusing
    the new line would be the same failure as silently cutting it in half.
    Returns the full text as stored, so the caller can show it back.
    """
    reader, writer, cap = _remember_parts(kind)
    text = " ".join(str(line or "").split())
    if not text:
        raise ValueError("nothing to remember")
    cur = reader()
    lines = [ln for ln in cur.split("\n") if ln.strip()]
    if any(ln.strip().lower() == text.lower() for ln in lines):
        return cur                      # already there; say nothing new
    lines.append(text)
    while lines and len("\n".join(lines)) > cap:
        lines.pop(0)
    return writer("\n".join(lines))


def forget(kind, line):
    """Drop one line from a box, matched the way remember() dedupes it.

    The other half of a box Shadow can write: an instruction the founder
    takes back has to be removable by saying so, not only by opening the
    settings page and editing text. Returns the full text as stored, and is
    a no-op when the line is not there.
    """
    reader, writer, _cap = _remember_parts(kind)
    text = " ".join(str(line or "").split()).lower()
    if not text:
        raise ValueError("nothing to forget")
    cur = reader()
    kept = [ln for ln in cur.split("\n")
            if ln.strip() and ln.strip().lower() != text]
    if len(kept) == len([ln for ln in cur.split("\n") if ln.strip()]):
        return cur
    return writer("\n".join(kept))


def set_max_running(n):
    """Persist the cap. Returns the value actually stored (post-clamp).

    Deliberately does NOT touch running missions. Lowering the cap below the
    number in flight stops further ADMISSIONS; it does not kill work that is
    already underway, because the founder asked for a queueing rule, not a
    kill switch, and stopping a worker mid-turn abandons a real turn budget.
    The overflow drains naturally as missions finish or are stopped.
    """
    v = clamp_running(n)
    import json_store
    cur = _read_limits()
    cur["running_at_once"] = v
    json_store.write_json(limits_path(), cur)
    return v


#: The band a turn budget is clamped into, and it is clamped HERE -- in the
#: store, under the route -- not in the stepper. The stepper stopping at the
#: ends is a courtesy to the founder; this is the part a hand-written POST
#: cannot get around.
#:
#: ONE, NOT ZERO, is the floor. A zero budget on a kind that actually runs is
#: not a small budget: run_mission's `turns_used >= max_turns` is true before
#: the first turn, so the mission dies immediately as `budget_exhausted`. That
#: is a broken task wearing a setting's clothes, and Shadow already has
#: stop/pause for "do not run this". `watch` keeps its 0 because it never
#: reaches the budget check at all (never_say returns first, :1015 before
#: :1018) -- which is also why `watch` is not settable, below.
#:
#: A HUNDRED is the ceiling: ~3.3x the largest template default, and at the
#: minutes-per-turn this actually runs at, already hours of autonomous work.
#: Past that the founder wants a different mission, not a bigger budget.
MIN_TURNS = 1
TURNS_CEILING = 100

#: Which kinds have a budget worth setting. DERIVED FROM THE INVARIANT, not a
#: hardcoded "everything but watch": the honest rule is "a kind that never
#: speaks never spends a turn", and never_say is the thing that makes that
#: true. run_mission returns on the never_say check (:1015) BEFORE it compares
#: the budget (:1018), so a number stored for such a kind could never bind --
#: and a control that looks kept but is never read is worse than one that says
#: it cannot be set. Deriving it means a future never_say template is excluded
#: automatically rather than by someone remembering to update a list.
SETTABLE_BUDGET_KINDS = tuple(
    k for k, v in TEMPLATES.items() if "never_say" not in v["invariants"])


def settable_budget_kinds():
    """The same rule, over the whole CATALOGUE rather than the built-ins.

    A founder-minted kind has no invariants (DEFAULT_OFFER_INVARIANTS), so it
    speaks, so it spends turns, so its budget is settable -- and the rule that
    decides this is still "a kind that never speaks never spends a turn",
    unchanged. SETTABLE_BUDGET_KINDS stays exported as the built-in answer;
    this is the one the budget paths actually ask.
    """
    return tuple(k for k, v in templates().items()
                 if "never_say" not in v["invariants"])


def clamp_turns(n):
    """Coerce anything to a legal turn budget, or raise ValueError.

    Same asymmetry as clamp_running, for the same reasons: a NON-NUMBER is
    refused, because storing 20 when the founder typed "twenty" is worse than
    saying no; an out-of-band NUMBER clamps, because a stepper held past the
    ceiling should stop at the ceiling rather than error.
    """
    try:
        v = int(n)
    except (TypeError, ValueError):
        raise ValueError("turns must be a whole number")
    return max(MIN_TURNS, min(TURNS_CEILING, v))


def _read_budget_overrides():
    """The founder's per-kind budgets, as stored. Absent kinds are auto.

    SPARSE BY CONSTRUCTION. A kind the founder never touched has no key, so
    an unconfigured install is byte-identical to what shipped before this
    setting existed, and "reset to auto" is a DELETE rather than a second
    sentinel value that every reader would have to know about.
    """
    raw = _read_limits().get("turn_budget")
    return raw if isinstance(raw, dict) else {}


def turn_budget(kind):
    """The budget a NEW mission of this kind is created with: the founder's
    setting, else the template default.

    NEVER RAISES, for the same reason max_running never raises -- this sits on
    the create path, and a corrupt limits file, an unreadable home or the
    shadow_home pytest refusal must degrade to the template rather than take
    down a task the founder just asked for.
    """
    default = (templates().get(kind) or {}).get("max_turns", 0)
    if kind not in settable_budget_kinds():
        return default            # watch: 0, and not negotiable
    try:
        raw = _read_budget_overrides().get(kind)
    except Exception:                     # noqa: BLE001 -- see docstring
        return default
    if raw is None:
        return default
    try:
        return clamp_turns(raw)
    except ValueError:
        return default                    # a hand-edited junk value


def turn_budgets():
    """Every kind's effective budget -- what the settings page states.

    Over the CATALOGUE, not the built-ins: a chip for a founder-minted kind
    has to be able to state its budget too, and a retired kind still needs
    one for the retry path to quote.
    """
    return {k: turn_budget(k) for k in templates()}


def turn_budget_overrides():
    """Just the kinds the founder has actually set. This is what tells the UI
    `auto` from `not auto`; it must never be inferred by comparing the
    effective value against the template, because setting a budget to exactly
    the default is a real choice and would read as auto."""
    try:
        settable = settable_budget_kinds()
        return sorted(k for k in _read_budget_overrides() if k in settable)
    except Exception:                     # noqa: BLE001
        return []


def set_turn_budget(kind, n):
    """Persist one kind's budget. `n is None` clears it back to auto.

    Returns the budget in force for that kind afterwards -- the stored value,
    or the template default after a reset -- so the caller never has to guess
    what a reset landed on.

    DELIBERATELY DOES NOT TOUCH LIVE MISSIONS. max_turns is snapshotted onto
    the mission record at create(), and every reader downstream (the run loop,
    the decider prompt, the restart sweep, clone_for_retry) reads the record.
    So this binds the NEXT task and leaves work already underway on the budget
    it was started with -- which is the only honest reading of a budget: the
    number a worker was given when it began.
    """
    if kind not in settable_budget_kinds():
        raise ValueError("no settable turn budget for %r" % (kind,))
    import json_store
    cur = _read_limits()
    # read-modify-write, like set_max_running: two settings share this file
    budgets = dict(cur.get("turn_budget") or {})
    if n is None:
        budgets.pop(kind, None)
    else:
        budgets[kind] = clamp_turns(n)
    if budgets:
        cur["turn_budget"] = budgets
    else:
        cur.pop("turn_budget", None)      # empty dict would be noise on disk
    json_store.write_json(limits_path(), cur)
    return turn_budget(kind)


# ----------------------------------------------------- autonomy --------
# HOW FAR SHADOW MAY GO ON ITS OWN. Four levels, and each is a real
# difference in what the engine does, not a label:
#
#   L0 Watch    Shadow never speaks. The same silence the `watch` template's
#               never_say invariant gives ONE mission, applied to all of them.
#   L1 Suggest  Shadow composes each instruction and HOLDS it for a founder
#               yes, exactly the way a floor-tripping say is held.
#   L2 Draft    Shadow speaks freely; its WORKER is capped at `plan`, so work
#               is read, planned and written up, but never applied.
#   L3 Act      Shadow speaks freely and the worker runs at the founder's own
#               permission mode. What this build has always done.
#
# THE DEFAULT IS L3 ON PURPOSE. It is what shipped before this setting
# existed -- the client hardcoded `SH_LEVEL_NOW = "L3"` and drew the selector
# inert -- so an unconfigured install behaves exactly as it did. Defaulting to
# L0 would have been "safer" and would have silently stopped every existing
# founder's Shadow on update: that is not safety, it is a regression wearing
# safety's clothes.
#
# THE LEVEL IS A CEILING, NEVER A SOURCE. L2's `plan` cap NARROWS whatever
# providers.effective_permission_mode already resolved to, and can never widen
# it. That is what keeps "Shadow is not a separate trust domain"
# (app._shadow_args) true: there is still exactly one place a permission mode
# comes from, and this only ever lowers it. See app._autonomy_ceiling.
#
# IT IS READ LIVE, NOT STAMPED, and that is the one place it deliberately
# differs from the turn budget. max_turns is snapshotted at create() because a
# budget is "the number a worker was given when it began". A founder dropping
# to L0 is saying STOP, and a stop that waited for the next task would be the
# setting failing in the only direction that actually matters.
AUTONOMY_LEVELS = ("L0", "L1", "L2", "L3")
DEFAULT_AUTONOMY = "L3"

#: What the top-tier switch defaults to. OFF, and this one was got WRONG
#: first: it shipped as True because the reference mock draws the switch on,
#: and eleven existing lanes went red saying so (test_shadow_waiter,
#: test_shadow_run_limit, test_shadow_drives and eight others all watched a
#: mission that used to speak stop at `autonomy_top_tier` instead).
#:
#: They were right and the default was wrong. It is the SAME rule that makes
#: DEFAULT_AUTONOMY L3: an update must not change what an existing install
#: does. A founder who has Shadow running tasks today would have updated into
#: every one of them stopping to ask a question that did not exist before --
#: and "it asks first now" is not a safe default when the thing it breaks is
#: the automation the founder was relying on.
#:
#: The mock draws it on because the mock draws a STATE, not a default. The
#: switch is one click away and the settings page says exactly what it does.
DEFAULT_CONFIRM_TOP = False

#: The levels whose worker may not write. Spelled as a list rather than as
#: "anything below L3" so a future level lands in one place instead of in an
#: inequality someone has to re-derive.
READ_ONLY_LEVELS = ("L0", "L1", "L2")


def clamp_autonomy(v):
    """Coerce to a legal level, or raise ValueError.

    RAISES ON ANYTHING UNKNOWN, and never clamps -- the asymmetry with
    clamp_running is deliberate. A cap is a point on a number line, so an
    out-of-band NUMBER has an obvious nearest legal answer. A level is an
    enum: there is no "nearest" level to "L7" or to "act", and inventing one
    would be granting a permission the founder never chose. Refusing is the
    only honest answer, and here it is the safe one in both directions.
    """
    if v in AUTONOMY_LEVELS:
        return v
    raise ValueError("autonomy must be one of %s" % ", ".join(AUTONOMY_LEVELS))


def autonomy():
    """The level the engine ACTUALLY runs at: the founder's setting, else L3.

    NEVER RAISES, for the same reason max_running never raises: this sits on
    the say path and on every spawn, and a corrupt limits file, an unreadable
    home or the shadow_home pytest refusal must degrade to the default rather
    than take down a mission that was otherwise fine.
    """
    try:
        raw = _read_limits().get("autonomy")
    except Exception:                     # noqa: BLE001 -- see docstring
        return DEFAULT_AUTONOMY
    if raw is None:
        return DEFAULT_AUTONOMY
    try:
        return clamp_autonomy(raw)
    except ValueError:
        return DEFAULT_AUTONOMY           # a hand-edited junk value


def set_autonomy(level):
    """Persist the level. Returns what was stored.

    DELIBERATELY DOES NOT STOP RUNNING WORKERS, for the same reason
    set_max_running does not: killing a worker mid-turn abandons a real turn
    budget. What it DOES do -- and where it differs from the budget -- is bind
    the very NEXT TURN of every running mission, because autonomy() is read
    live at the top of each say rather than snapshotted at create().
    """
    v = clamp_autonomy(level)
    import json_store
    cur = _read_limits()
    cur["autonomy"] = v
    json_store.write_json(limits_path(), cur)
    return v


def confirm_top_tier():
    """Whether L3 must ask before its first write-capable say.

    NEVER RAISES, and degrades to the DEFAULT rather than to False: a settings
    file that cannot be read must not silently drop a confirmation the founder
    asked for.
    """
    try:
        raw = _read_limits().get("confirm_top_tier")
    except Exception:                     # noqa: BLE001 -- see docstring
        return DEFAULT_CONFIRM_TOP
    return DEFAULT_CONFIRM_TOP if raw is None else bool(raw)


def set_confirm_top_tier(on):
    """Persist the top-tier switch. Returns what was stored."""
    v = bool(on)
    import json_store
    cur = _read_limits()
    cur["confirm_top_tier"] = v
    json_store.write_json(limits_path(), cur)
    return v


def worker_may_write(level=None):
    """True when a worker spawned at this level may change anything.

    The ONE place the L2/L3 line is drawn, so the ceiling in app.py and the
    sentence the settings page prints can never disagree about where it is.
    """
    return (level or autonomy()) not in READ_ONLY_LEVELS


# ------------------------------------------------- delegate offers ------
# THE KINDS SHADOW OFFERS, AND THE KINDS A MISSION MAY BE, ARE TWO LISTS.
#
# offered_kinds() is the founder's choice: what the Delegate form presents,
# what the Settings chips state, what Shadow is allowed to name in a mission
# fence. templates() is the CATALOGUE: every kind a mission may legally be,
# which is the built-ins plus every kind the founder has ever minted. The
# catalogue only ever grows.
#
# THAT ASYMMETRY IS THE WHOLE DESIGN, and it exists for one concrete
# failure. clone_for_retry re-creates a finished mission with its ORIGINAL
# template, and create() raises on a template it does not know. If removing
# a kind deleted its definition, then removing "research" would break Retry
# on every research task the founder had ever run -- work already done,
# made un-retryable by a settings click. So a removal UN-OFFERS and never
# UN-DEFINES: the name leaves `offered`, its definition stays under
# `custom`, and re-adding it later restores the budget it always had.
#
# WHY A SEPARATE FILE from task-limits.json. Same home, same json_store, but
# its own inode: a hand-edit that corrupts the offer list must cost the
# default offers and nothing else. Two settings degrading together because
# they happened to share a file is one failure wearing two faces.

#: What a newly minted kind is worth. Settings says AUTO on the budget row --
#: the budget is set by the kind of work, not by taste -- so "+ add" asks for
#: a name and nothing else. Matches `fix`, the middle of the built-in band.
#: The founder can still retune it afterwards through set_turn_budget, which
#: is the control that already exists for exactly that.
DEFAULT_OFFER_TURNS = 20

#: No invariants on a minted kind. read_only and never_say are enforced where
#: the action happens (see the TEMPLATES note above); a founder typing a name
#: into a chip row is not declaring a capability boundary, and inventing one
#: on their behalf would be the wrong kind of guess.
DEFAULT_OFFER_INVARIANTS = ()

#: The band. ONE offer is the floor for the same reason one running task is:
#: zero offers is a "nothing may be delegated" switch wearing a settings
#: row's clothes, and Shadow already has stop/pause for that. The ceiling is
#: a legibility bound rather than an engine one -- the chips wrap inside one
#: settings row, and a founder with thirty kinds has a taxonomy problem no
#: cap can fix.
MIN_OFFERS = 1
MAX_OFFERS = 12

#: What an UNCONFIGURED install offers, in order. Not `list(TEMPLATES)`:
#: offered_kinds() is ordered, default_offer() takes the first, and TEMPLATES
#: happens to start at `feature` while the shipped Delegate form has always
#: opened on `fix`. Deriving the fallback from dict order would have moved
#: the default kind for every install that never touched this setting --
#: a behaviour change smuggled in as a refactor. The membership is still
#: TEMPLATES', asserted by a test, so a fifth built-in cannot go unoffered.
BUILTIN_OFFERS = ("fix", "feature", "research", "watch")

#: A kind name becomes a mission's `template` field, rides the SHADOW.md
#: fence, and is rendered into a data- attribute. Slug-shaped for all three.
_OFFER_NAME = re.compile(r"^[a-z][a-z0-9-]{1,23}$")


def offers_path():
    """The one file the founder's delegate offers live in.

    Beside task-limits.json under the SAME resolver (shadow_ledger
    .shadow_home), so a test that redirects the shadow home redirects this
    too and can never write an offer list into the live install.
    """
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "delegate-offers.json")


def _read_offers():
    import json_store
    return json_store.read_json(offers_path(), {})


def clean_offer_name(name):
    """Coerce anything to a legal kind name, or raise ValueError.

    Raises rather than sanitising, for the same reason clamp_running raises
    on "five": a settings write that quietly stores `codereview` when the
    founder typed `Code Review!` has invented a name they will not recognise
    on the chip. Case and surrounding space ARE forgiven -- those are typing,
    not meaning.
    """
    s = str(name or "").strip().lower()
    if not s:
        raise ValueError("a delegate offer needs a name")
    if not _OFFER_NAME.match(s):
        raise ValueError(
            "%r is not a usable kind name -- 2 to 24 characters, lowercase "
            "letters, digits and hyphens, starting with a letter"
            % (str(name or "").strip(),))
    return s


def _custom_kinds():
    """The founder-minted kind DEFINITIONS, offered or not. Never raises.

    Every field is re-validated on the way out rather than trusted: this file
    is hand-editable, and a junk budget must cost the default for that kind
    rather than a TypeError on the create path.
    """
    try:
        raw = _read_offers().get("custom")
    except Exception:                     # noqa: BLE001 -- see templates()
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        try:
            key = clean_offer_name(name)
        except ValueError:
            continue                      # a hand-edited junk name
        try:
            turns = int(spec.get("max_turns", DEFAULT_OFFER_TURNS))
        except (TypeError, ValueError):
            turns = DEFAULT_OFFER_TURNS
        inv = spec.get("invariants")
        out[key] = {
            "max_turns": max(MIN_TURNS, min(TURNS_CEILING, turns)),
            "invariants": tuple(inv) if isinstance(inv, (list, tuple))
            else DEFAULT_OFFER_INVARIANTS,
        }
    return out


def templates():
    """The CATALOGUE: every kind a mission may legally be.

    NEVER RAISES, and never smaller than TEMPLATES. This is what create()
    validates against and what retry depends on, so a corrupt offers file
    must cost the custom kinds and nothing else -- a mission of a built-in
    kind has to stay creatable whatever is on disk.

    A BUILT-IN ALWAYS WINS A NAME COLLISION. A hand-edited custom "watch"
    can change what Settings shows; it can never change what the engine does
    with the four kinds that ship, and in particular cannot strip never_say
    off `watch` by redefining it.
    """
    out = dict(_custom_kinds())
    out.update(TEMPLATES)
    return out


def offered_kinds():
    """The kinds Shadow ACTUALLY offers: the founder's list, else the
    built-ins.

    NEVER RAISES. This is read at decision time on every path that presents
    or validates a kind -- the fence parser, the settings read, the delegate
    route -- and a corrupt settings file must degrade to the shipped four
    rather than leave the founder unable to delegate anything at all.

    ORDER IS THE FOUNDER'S, not sorted. The first offer is what the Delegate
    form opens on, so the list is a preference and re-sorting it would
    silently move that.
    """
    try:
        raw = _read_offers().get("offered")
    except Exception:                     # noqa: BLE001 -- see docstring
        return list(BUILTIN_OFFERS)
    if not isinstance(raw, list):
        return list(BUILTIN_OFFERS)
    known = templates()
    out = []
    for name in raw:
        try:
            key = clean_offer_name(name)
        except ValueError:
            continue                      # a hand-edited junk entry
        if key in known and key not in out:
            out.append(key)
    # An empty list is not a legal state (MIN_OFFERS is 1) and can only
    # arrive by hand-edit. Nothing offered would mean nothing can be
    # delegated, so it reads as unconfigured rather than as a mute Shadow.
    return out or list(BUILTIN_OFFERS)


def default_offer():
    """The kind a delegation falls back to when nobody named one.

    Never "fix" by constant: the founder may have retired it, and a default
    pointing at a kind they removed is the bug this whole split exists to
    avoid. offered_kinds() never returns empty, so this never IndexErrors.
    """
    return offered_kinds()[0]


def add_offer(name):
    """Offer a kind. Returns the offered list as stored.

    THREE CASES, ONE DOOR. Already offered is a NO-OP returning the same
    list, so a double-click cannot duplicate a chip. A name that is known but
    not offered -- a built-in the founder removed, or a custom kind they
    retired -- is re-offered with the budget it ALWAYS had, never reset to
    the default. Anything else mints a new custom kind.
    """
    key = clean_offer_name(name)
    import json_store
    cur = _read_offers()
    offered = offered_kinds()
    if key in offered:
        return offered
    if len(offered) >= MAX_OFFERS:
        raise ValueError("at most %d delegate offers" % MAX_OFFERS)
    if key not in templates():
        custom = cur.get("custom")
        if not isinstance(custom, dict):
            custom = {}
        custom[key] = {"max_turns": DEFAULT_OFFER_TURNS,
                       "invariants": list(DEFAULT_OFFER_INVARIANTS)}
        cur["custom"] = custom
    cur["offered"] = offered + [key]
    json_store.write_json(offers_path(), cur)
    return list(cur["offered"])


def remove_offer(name):
    """Stop offering a kind. Returns the offered list as stored.

    DOES NOT DELETE THE DEFINITION -- see the section header. A custom kind's
    entry stays under `custom` so clone_for_retry can still rebuild a mission
    that used it, and so re-adding it later restores its budget.

    REFUSES THE LAST ONE. With nothing offered the founder could not delegate
    at all, and a settings row must not be able to turn the feature off by
    attrition.
    """
    key = clean_offer_name(name)
    offered = offered_kinds()
    if key not in offered:
        return offered                    # already gone: nothing to say
    if len(offered) <= MIN_OFFERS:
        raise ValueError(
            "at least %d delegate offer -- Shadow needs something to offer"
            % MIN_OFFERS)
    import json_store
    cur = _read_offers()
    cur["offered"] = [k for k in offered if k != key]
    json_store.write_json(offers_path(), cur)
    return list(cur["offered"])


def _home():
    # one resolver for every Shadow store, with the pytest refusal that keeps
    # a test from writing mission files into the live home (shadow_ledger)
    d = os.path.join(os.path.realpath(shadow_ledger.shadow_home()), "missions")
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
        # THE CATALOGUE, NOT THE OFFERED LIST. A kind the founder has stopped
        # offering must still be CREATABLE, because clone_for_retry rebuilds a
        # finished mission with its original template -- gating create() on
        # what is currently offered would make every past task of a retired
        # kind un-retryable. Refusing a kind the founder no longer offers is
        # the JOB OF THE DOORS (the fence parser, the delegate route), where
        # the intent is "start something new" rather than "run this again".
        known = templates()
        if template not in known:
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
            # SANITISED AT THE DOOR: this route is reached from the API and
            # from a `mission` fence a model wrote, and a probe is the one
            # field on a check that the engine later hands to the filesystem.
            "done_when": sanitise_probes(done_when or []),
            "turns_used": 0,
            # THE BUDGET IS RESOLVED HERE AND NOWHERE ELSE ON THIS PATH.
            # turn_budget() prefers the founder's setting and falls back to
            # the template, and because the answer is SNAPSHOTTED onto the
            # record, every downstream reader (run_mission's budget check,
            # the decider prompt, the restart sweep, clone_for_retry) keeps
            # reading the mission rather than the setting. That is what makes
            # a budget change bind new tasks only, with no re-budgeting of
            # work already in flight and no property indirection.
            "max_turns": turn_budget(template),
            "version": 1,
            "invariants": list(known[template]["invariants"]),
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

    def delete(self, mid):
        """REMOVE one mission record. The only eraser in the store.

        Every other lifecycle verb ENDS a mission (stopped/failed/done) and
        leaves the file, which is why the workspace list is a filter rather
        than a delete -- a concluded mission is still the record a goal's
        attempts[] points at. This is the founder saying they do not want
        the row at all, and it is deliberately narrow:

          - it is NOT a state. Nothing transitions here, so the state
            machine, its transition table and every reader of it are
            untouched.
          - it does NOT end anything. A live mission must already have been
            ended (and its delegate released) by the caller through the
            EXISTING founder paths -- founder_stop / cancel_queued /
            release_delegate -- before its record is removed. This method
            refuses to be that second lifecycle.
          - the ledger keeps the history. missions.jsonl already holds every
            transition this mission ever made and one more row is appended
            here, so deleting the file loses the live record, never the
            audit trail.

        Idempotent: a mission that is already gone returns False rather than
        raising, so a double-click is a no-op and not a 500.
        """
        m = self.load(mid)
        if m is None:
            return False
        state = m.get("state")
        path = os.path.join(_home(), mid + ".json")
        # the lock file the writer uses, and any tmp a crashed write left --
        # otherwise the "deleted" mission leaves its scaffolding behind
        for extra in (path + ".tmp", path + ".lock"):
            try:
                os.remove(extra)
            except OSError:
                pass
        try:
            os.remove(path)
        except OSError:
            return False
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": "deleted",
            "note": "record deleted by the founder (was %s)" % state})
        return True

    def archive(self, mid, note="archived by the founder"):
        """PUT A CONCLUDED MISSION OUT OF THE WAY WITHOUT ERASING IT.

        THE FOUNDER'S X USED TO BE AN ERASER (founder, 2026-09-19: "if we
        delete a shadow task ... should be as a separate section as
        Archived"). Pressing it ended the mission and then removed the
        record, so the one thing a founder might want afterwards -- what the
        task actually did -- existed only in the ledger, which the workspace
        does not read. Archiving keeps the record, the transcript and the
        chat exactly where they are and marks it as something the founder is
        done looking at.

        NOT A STATE, for the same reason delete() is not one: nothing
        transitions here, the state machine and every reader of it are
        untouched. `archived_at` is an ADDITIVE stamp, so an older build
        reading this file sees the mission it always saw.

        It does NOT end anything either -- the caller stops the mission
        through the existing founder path first (shadow_runner
        .founder_force_stop, which carries the stop all the way to the
        worker). Archiving a mission that is still running would leave a live
        worker attached to a row the founder has filed away.

        Idempotent: archiving twice restamps nothing and returns the record.
        delete() remains the eraser, and the workspace's second press is what
        reaches it.
        """
        m = self.load(mid)
        if m is None:
            raise ValueError("no mission %s" % mid)
        if m.get("archived_at"):
            return m
        m["archived_at"] = _now()
        self.save(m)
        shadow_ledger.append("missions", {
            "mission_id": mid, "state": m.get("state"),
            "note": "%s (was %s)" % (note, m.get("state"))})
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
                # same door, same narrowing as create(): a `mission` fence
                # amends done_when with whatever the chat wrote
                m[k] = (sanitise_probes(fields[k]) if k == "done_when"
                        else fields[k])
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


def sanitise_probes(rows):
    """Every `probe` on a done_when list, validated -- and nothing else.

    THE CHOKE POINT. validate_done_when guards the DECIDER's path, but three
    doors write done_when rows raw: the API create route, a `mission` fence
    from a task's own Shadow chat, and that fence's amend. A probe reaching
    disk unvalidated would be a model-authored string the engine later hands
    to the filesystem, so every door is narrowed to one.

    THE PROBE KEY AND THE `verify` TIER, AND NOTHING ELSE. Checks, `met`,
    `confirmed_by`, `contains_artifact`, `founder_confirm` and every other
    field pass through byte-identical -- tier semantics on these paths are
    pre-existing behaviour and not this change's business. The two things
    this function owns are resolve_verify_tier's rule:

      verify + valid probe    -> verify, probe normalised
      verify + no/bad probe   -> founder_confirm, wording kept, probe gone
      any other tier + probe  -> probe dropped; a machine cannot sign for the
                                 founder, and contains_artifact is a literal

    A row that is neither `verify` nor carrying a probe is appended AS IT
    CAME IN -- the same object, not a copy -- so nothing this function does
    not own can be perturbed by it.
    """
    if not isinstance(rows, list):
        return rows
    out = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        if row.get("tier") != "verify" and "probe" not in row:
            out.append(row)               # nothing here is ours
            continue
        clean = dict(row)
        tier, probe = resolve_verify_tier(row.get("tier"), row.get("probe"))
        if row.get("tier") == "verify":
            clean["tier"] = tier          # verify, or demoted
        if probe:
            clean["probe"] = probe
        else:
            clean.pop("probe", None)
        out.append(clean)
    return out


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clone_for_retry(store, mid):
    """Failed/stopped/done -> a FRESH mission with the same brief (retry
    one-tap). Always a new target: a dead delegate is never reused.

    THE BUDGET IS FRESH TOO, and deliberately so: this routes through
    create(), so a retry is stamped with the budget in force NOW rather than
    the one its parent ran on. That is the right reading of a retry -- it is
    a new task with an old brief -- and it is the reason a founder who raises
    the budget after watching a task run out of road gets the bigger number
    on the retry without having to edit anything.
    """
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
    clone = store.create(src["objective"],
                         src.get("template") or default_offer(),
                         target_mode="new", target_session=None,
                         done_when=checks, manifest=src.get("manifest"))
    src = store.load(mid)
    src["retried_to"] = clone["id"]
    store.save(src)
    return store.transition(clone["id"], "brief_confirm",
                            "retry of %s" % mid)


def _call_verifier(verifier, check_text, evidence):
    """Ask a verifier about one check, with or without the evidence.

    TWO SHAPES, ONE CALLER. A production verifier needs the evidence to
    decide anything (it reads what the worker actually said); every verifier
    written before this one -- and every test that injects a lambda -- takes
    the check alone. Preferring the two-argument call and falling back keeps
    both working without a flag day.

    The fallback is narrowed to a TypeError raised by the call itself: a
    TypeError from INSIDE a two-arg verifier must surface as the failure it
    is, not be retried as a one-arg call and silently answered wrong.
    """
    try:
        return bool(verifier(check_text, evidence))
    except TypeError:
        pass
    return bool(verifier(check_text))


def evaluate_done_when(mission, transcript_text, verifier=None,
                       probe_root=None):
    """Tiered evaluation. founder_confirm NEVER auto-passes: it is met only
    when its `met` flag was set by an explicit founder action.

    WORKER CLAIM != DONE (founder, 2026-09-17). A `verify` row that carries a
    `probe` is settled by shadow_probe reading the real filesystem, and the
    transcript is NOT CONSULTED AT ALL for that row -- the verifier is not
    called, the worker's DONE-CHECK line is not read, and a perfect claim
    over a wrong file is unmet. The claim may stay in the transcript as a
    report; the filesystem is what answers.

    Rows without a probe keep the behaviour they have always had, so every
    existing mission, tier and test is unaffected. That is deliberate: this
    change adds a way to be sure, it does not remove the ways to be told.
    """
    results = []
    for check in mission.get("done_when", []):
        tier = check.get("tier")
        probe = check.get("probe") if tier == "verify" else None
        if probe:
            # NEVER RAISES (shadow_probe.run): an unanswerable probe is
            # `met=False`, which leaves the check outstanding and takes the
            # existing escalation path -- another turn, then the ordinary
            # budget and ping-pong exits. It is not a failed mission.
            met = shadow_probe.met(probe, probe_root)
        elif tier == "verify":
            met = (_call_verifier(verifier, check["check"], transcript_text)
                   if verifier else False)
        elif tier == "judge":
            # STAMPED, NOT CALLED. The judge is a model call and this
            # function is synchronous and is called from four places; the
            # loop runs the judges in its own async step (`_run_judges`)
            # immediately before evaluating, and leaves the verdict on the
            # row. A row with no stamp is simply unmet -- the mission has
            # not been judged yet, which is true on the turn a check is
            # written and stops being true on the next one.
            met = (check.get("judged") or {}).get("state") == "met"
        elif tier == "contains_artifact":
            met = check["check"] in (transcript_text or "")
        elif tier == "founder_confirm":
            met = bool(check.get("met"))
        else:
            met = False
        results.append({"tier": tier, "check": check.get("check"),
                        "met": met})
    return all(r["met"] for r in results) if results else False, results


#: how much of the surrounding text a matched artifact is shown inside. A
#: bare substring proves nothing on its own -- the founder needs the run of
#: text it was found in to judge whether the chat really did the thing.
ARTIFACT_CONTEXT = 90

#: WHAT SATISFIED EACH TIER, in the founder's words. The tier IS the answer
#: to "why does Shadow think this is done", so the copy is a fixed map read
#: off the evaluation -- never composed at runtime, never model-written, and
#: never a claim the tier does not support. `founder_confirm` says "you",
#: because confirm_check is the only writer of that flag and only an explicit
#: founder action calls it.
HOW_MET = {
    "verify": "Shadow ran this check and it passed",
    "contains_artifact": "found in the chat",
    "founder_confirm": "you confirmed it",
    # THE WORDING IS A PROMISE AND IT IS EXACTLY THE ONE THE TIER KEEPS.
    # Not "Shadow verified this" -- the judge read a diff and formed a view,
    # which is weaker than a probe and stronger than an attestation, and the
    # founder is entitled to know which of the three they are looking at.
    # The judge's own one-line reason is shown beside it (judged.reason).
    "judge": "Shadow read the change and confirmed it",
}
HOW_UNMET = "still outstanding"


def artifact_context(transcript, needle, window=ARTIFACT_CONTEXT):
    """The matched string INSIDE the run of text it was found in.

    Whitespace is collapsed first, because the evidence blob is streamed
    prose PLUS a json dump (shadow_runner.evidence_text) and a raw slice of
    that reads as machine noise. A cut at either end then drops the partial
    token it landed in -- the same word-boundary rule
    shadow_runner._prose_tail applies, for the same reason: a fragment reads
    as something the worker wrote when it is not.

    Returns "" when there is no match, which is the honest answer: the
    caller shows the check without evidence rather than inventing any.
    """
    text = " ".join(str(transcript or "").split())
    needle = str(needle or "")
    if not needle:
        return ""
    at = text.find(needle)
    if at < 0:
        return ""
    start = max(0, at - window)
    end = min(len(text), at + len(needle) + window)
    out = text[start:end]
    off = at - start                      # where the match sits inside `out`
    if start > 0:
        cut = out.find(" ")
        if 0 <= cut < off:                # never trim INTO the match itself
            out, off = out[cut + 1:], off - (cut + 1)
        out, off = "…" + out, off + 1
    if end < len(text):
        cut = out.rfind(" ")
        if cut > off + len(needle):
            out = out[:cut]
        out += "…"
    return out.strip()


def confirmation_is_due(results):
    """Is the ONLY thing left the founder's signature?

    Lifted verbatim out of the loop's confirmation branch so the infra exit
    below can ask the same question instead of growing a second answer to
    it. Every clause is the loop's, including the one the loop's own comment
    exists to protect: with NO machine-checkable check at all there is
    nothing to have passed, so an all-founder_confirm mission is NOT due --
    it is still being driven.
    """
    results = results or []
    pending_confirm = [r for r in results
                       if r["tier"] == "founder_confirm" and not r["met"]]
    machine = [r for r in results if r["tier"] != "founder_confirm"]
    others_met = bool(machine) and all(r["met"] for r in machine)
    return bool(results and pending_confirm and others_met)


def confirmation_reachable(results, turns_used):
    """Is the founder's SIGNATURE the only thing still standing between this
    attempt and `done`, at the point where the machine has run out of road?

    THE GAP THIS CLOSES (founder, 2026-09-16; measured on m-cd009367d41a,
    and reproduced against the engine on three shapes). `confirmation_is_due`
    deliberately requires a machine-checkable check to exist and to have
    passed -- with no machine check at all there is nothing to have passed,
    so an all-`founder_confirm` mission is NOT due and the loop keeps driving.
    That rule is right INSIDE the loop and is untouched: it is what stops a
    mission pausing on its first evaluation having verified nothing and
    driven nothing (m-b7d534be84d7).

    It is wrong at the END of the road. All-`founder_confirm` is the DEFAULT
    shape, not an edge case -- shadow_protocol.tier_for demotes every check
    that is not a short literal marker -- and such a mission has NO exit to
    `done` inside the loop at all. So it drove until the budget was spent and
    took the budget exit: `failed`, with the worker's finished work never
    shown to the founder and the one party who could sign it off never asked.
    Four of five checks passing on m-cd009367d41a ended exactly that way.

    THE RULE: once the attempt has actually been DRIVEN (turns_used >= 1) and
    every check still outstanding is one only the founder can satisfy, the
    honest ending is "it needs you", never "it failed". Nothing here can
    satisfy a check, `met` is untouched, and `_complete` is still reachable
    only from evaluate_done_when.

    TURN-GATED ON PURPOSE. turns_used == 0 means nothing was driven, so this
    is False and the historical ending stands -- the same first-evaluation
    safety confirmation_is_due exists to protect, stated once more at the
    other end of the loop.

    Strictly WIDER than confirmation_is_due at turns_used >= 1: a mission
    whose machine checks all passed has only founder_confirm outstanding and
    satisfies both. That is why the ending path asks this one.
    """
    if (turns_used or 0) < 1:
        return False
    results = results or []
    unmet = [r for r in results if not r["met"]]
    if not results or not unmet:
        # no checks at all -> there is no bar and nothing to sign; every check
        # met -> `done` is evaluate_done_when's word, not this function's
        return False
    return all(r["tier"] == "founder_confirm" for r in unmet)


def completion_summary(mission, results, transcript="", outcome=""):
    """WHAT WAS DONE, AND WHY SHADOW CALLS IT DONE.

    THE GAP THIS CLOSES (founder, 2026-09-15). A finished mission said two
    things to the founder and neither was legible. The feed row carried
    "mission done", which 14-needs-you.js renders as "done - result inside";
    and `result_excerpt` was that inside -- 150 characters off the HEAD of
    the evidence blob plus 250 off its tail, which cuts through
    `{"role": "assistant", "text": ...}` far more often than it lands on a
    sentence. The one fact the founder actually wanted -- WHICH criteria
    were satisfied, and BY WHAT -- was computed on the way past (it is
    `results`, the loop's own evaluation) and then dropped on the floor.

    DETERMINISTIC, AND NOT A SECOND EVALUATOR. Every value is read off the
    mission record and off the evaluation evaluate_done_when ALREADY ran:
    nothing is re-checked, no model is asked, and this cannot change a
    mission's outcome -- it is called AFTER `done` is decided and only
    describes it. A check it cannot evidence is reported without evidence
    rather than with a guess.

    `transcript` is the same evidence text the evaluation read, and is used
    for exactly one thing: showing a contains_artifact match in context.

    `outcome` IS THE OTHER HALF OF THE ANSWER (founder, 2026-09-15). The
    rows below say why Shadow calls it done -- three boxes ticked, and what
    ticked each. They do not say WHAT WAS DONE, and that is the thing a
    founder opens the pane for. `outcome` is the worker's own closing
    message, read off the transcript by shadow_runner.last_worker_message
    and passed in already trimmed. It is QUOTED, never composed: this
    function does not summarise it, shorten it or reword it, and an absent
    one stays absent so every surface falls back to what it drew before.
    """
    checks = mission.get("done_when") or []
    rows = []
    for i, r in enumerate(results or []):
        # the stored check carries who/when for a founder confirmation;
        # `results` carries the verdict. Index-aligned by construction --
        # evaluate_done_when walks done_when in order and appends one row
        # per check.
        src = checks[i] if i < len(checks) else {}
        tier = r.get("tier")
        met = bool(r.get("met"))
        row = {"check": r.get("check") or "", "tier": tier, "met": met,
               "how": (HOW_MET.get(tier, "Shadow checked this") if met
                       else HOW_UNMET)}
        if met and tier == "contains_artifact":
            found = artifact_context(transcript, r.get("check"))
            if found:
                row["evidence"] = found
        if met and tier == "founder_confirm":
            if src.get("confirmed_by"):
                row["by"] = src["confirmed_by"]
            if src.get("confirmed_at"):
                row["at"] = src["confirmed_at"]
        rows.append(row)
    met_n = sum(1 for r in rows if r["met"])
    return {
        "objective": mission.get("objective") or "",
        "outcome": str(outcome or ""),
        "headline": ("%d of %d checks passed" % (met_n, len(rows))
                     if rows else "no check was set"),
        "checks_met": met_n,
        "checks_total": len(rows),
        "checks": rows,
        "turns_used": mission.get("turns_used") or 0,
        "max_turns": mission.get("max_turns") or 0,
        "chat": mission.get("target_session"),
        "at": _now(),
    }


def completion_text(completion):
    """THE SAME ACCOUNT, AS PLAIN TEXT, for a reader that has no pane.

    THE GAP THIS CLOSES (founder, 2026-09-15). completion_summary made a
    finished mission legible on every surface that renders HTML -- the Now
    card, the Home pane, the Copy button. One surface was left behind:
    goal_lifecycle._record_attempt_memory, which writes the attempt's
    `result` into the goal's durable memory and renders it under "What I
    learned". It was still recording `result_excerpt` -- the same head/tail
    cut of the evidence blob this work exists to stop showing people -- so
    the one place a completed attempt is remembered was the one place it
    still read as machine noise.

    THE TWIN OF shadowCompletionText, DELIBERATELY. 16-shadow-home.js
    renders exactly this text onto the clipboard; the same order, the same
    ✓/✗, the same indented evidence. A founder reading a goal's memory
    should see what the Copy button would have given them, not a second
    dialect of the same fact.

    PURE, AND NOT A SECOND EVALUATOR. It formats the record completion_
    summary already stamped and reads nothing else -- no mission, no
    transcript, no verdict of its own.

    An empty or missing summary returns "", which is what lets the caller
    fall back to the excerpt for a mission completed before the field
    existed. That is the same "empty means absent" rule shadow_runner.
    terminal_why already applies to this field.
    """
    c = completion if isinstance(completion, dict) else None
    if not c:
        return ""
    head = ["Done — %s" % (c.get("headline") or "")]
    if c.get("objective"):
        head.append(str(c["objective"]))
    head.append("%s of %s turns used."
                % (c.get("turns_used") or 0, c.get("max_turns") or 0))
    # the worker's own account, in the same place the pane puts it: under
    # the budget line and above the verdicts. Blank line either side so a
    # paragraph of prose does not read as one more header row.
    if c.get("outcome"):
        head.append("")
        head.append(str(c["outcome"]))
    rows = []
    for k in c.get("checks") or []:
        how = str(k.get("how") or "")
        if k.get("by"):
            how += " · %s" % k["by"]
        # ✓ / ✗ is the pane's tick in text: a plain reader must be able to
        # tell a satisfied check from an outstanding one without the CSS.
        line = ("✓ " if k.get("met") else "✗ ") + str(k.get("check") or "")
        if how:
            line += " — " + how
        if k.get("evidence"):
            line += "\n    " + str(k["evidence"])
        rows.append(line)
    return "\n".join(head) + (("\n\n" + "\n".join(rows)) if rows else "")


def open_first_turn(store, mid):
    """Name the turn a worker has JUST BEGUN. Called at first contact.

    The only writer of `turn_open` outside run_mission, and deliberately the
    same expression the loop uses: the turn in flight is the one after the
    last turn that FINISHED. shadow_runner.spawn_delegate_session calls this
    (through app._delegate_spawn's `on_first_turn`) from the first frame the
    worker emits, so the field is stamped when the turn starts painting and
    not when the app merely decided to spawn something.

    NEVER LOWERS, NEVER RAISES. A record that already names a turn keeps it,
    so a re-adopted or retried spawn cannot walk the count backwards; a
    terminal mission is left alone; and any store trouble leaves the record
    exactly as it was. A turn LABEL is never worth failing a spawn over --
    the same rule every other book-keeping line in that hook follows.

    NOT A BUDGET. max_turns is compared against turns_used and nothing else,
    here as everywhere.
    """
    try:
        m = store.load(mid)
        if m is None or m.get("state") in TERMINAL:
            return None
        want = (m.get("turns_used") or 0) + 1
        if (m.get("turn_open") or 0) >= want:
            return m
        m["turn_open"] = want
        store.save(m)
        return m
    except Exception:                   # noqa: BLE001 -- see docstring
        return None


class MissionEngine:
    """Drives ONE mission's loop. sayer/waiter/reader are injected."""

    def __init__(self, store, sayer, boundary_waiter, transcript_reader,
                 verifier=None, on_evaluated=None, decider=None,
                 outcome_reader=None, response_reader=None,
                 probe_root=None, judge=None):
        """`on_evaluated(mission, results, done)` is an OBSERVER of the one
        evaluation this loop already performs -- it is how the goal layer
        keeps per-check progress without a second evaluator. Optional, and
        never load-bearing: its failure cannot change a mission's outcome.

        `outcome_reader(mission) -> str` is the same shape and the same
        promise: it is asked, once, AFTER `done` is decided, for the
        worker's own closing words, and it is injected rather than imported
        because the transcript lives in shadow_runner and this module
        imports nothing from there. None -- every existing caller and every
        existing test -- stamps a summary with no outcome, which is exactly
        the record shape that shipped before it.
        """
        self.store = store
        self.sayer = sayer
        self.waiter = boundary_waiter
        self.reader = transcript_reader
        self.verifier = verifier
        # WHERE A PROBE IS ALLOWED TO LOOK -- the delegate's own cwd, which
        # is where its work lands. Injected for the same reason `verifier`
        # is: the engine must not reach into app settings itself, and a test
        # must be able to point it at a tmpdir. None means "ask
        # shadow_probe.default_root()", which reads the SAME
        # providers.load_settings()["workdir"] the worker is spawned in, so
        # no production caller has to thread it and none can drift from it.
        self.probe_root = probe_root
        # `judge(check, evidence, outcome) -> shadow_judge.Verdict | None`,
        # async. Injected for exactly the reasons `verifier` and `decider`
        # are: this module must not reach into app's provider stack, and a
        # test must be able to hand it a function. None -- every existing
        # caller and every existing test -- means no judging happens at all,
        # so a `judge` row simply stays unmet and the mission behaves as it
        # did before the tier existed.
        self.judge = judge
        self.on_evaluated = on_evaluated
        # async (context) -> decision dict. None keeps the historical
        # template, which is what leaves every standalone mission and every
        # pre-existing test behaving exactly as before.
        self.decider = decider
        self.outcome_reader = outcome_reader
        # `response_reader(mission) -> str` is WHAT THE DECIDER READS, and it
        # is injected for the same reason outcome_reader is: the transcript
        # lives in shadow_runner and this module imports nothing from there.
        #
        # It replaces a BYTE TAIL with WHOLE MESSAGES. `last_response` used
        # to be the evidence blob sliced to DECISION_TAIL, which kept the end
        # of a message and dropped its beginning -- on mission
        # m-cd009367d41a the decider saw 9% of a 21,060-char reply, lost the
        # "## CHANGE" / "## TESTS" headers that opened it, and spent four
        # turns asking for resends of work that was already finished.
        #
        # None -- every existing caller and every existing test -- keeps the
        # historical byte tail exactly, so nothing that does not inject one
        # changes behaviour by a single character.
        self.response_reader = response_reader

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
        # THE BAR IS SET BEFORE THE WORKER IS EVER SPOKEN TO (founder,
        # 2026-09-15). The spawner sends the manifest and waits out the whole
        # first agentic turn, so by the time it returns Shadow has already
        # supervised a turn it had no criteria for. The order the founder
        # asked for is: objective -> Shadow decides done_when -> persisted and
        # on the card -> first worker interaction. This is that one step, in
        # the one place that runs before the spawner does.
        await self._criteria_before_first_contact(m)
        # THE FIRST TURN IS NAMED WHEN IT STARTS -- NOT ONE MOMENT EARLIER
        # (founder, 2026-09-18, second ruling).
        #
        # The spawner's contract is "send the manifest, WAIT OUT THE WHOLE
        # FIRST AGENTIC TURN, hand back a session id", so turn 1 really is
        # in flight across this await and run_mission never names it: the
        # `briefed` branch skips the say-and-wait block that carries the
        # stamp. That is why every card read "turn 0 of 25" for the whole
        # of turn 1.
        #
        # The first fix stamped `turn_open` HERE, on the line above this
        # await. That was too early by one window: at this point no worker
        # process exists and no frame has been painted, and the founder's
        # ruling is that ZERO is the correct reading for exactly that
        # stretch -- while Shadow is still setting the bar and nothing has
        # been said to anyone. A card reading "turn 1 of 25" over a window
        # in which nothing is happening is the same lie in the other
        # direction.
        #
        # So the stamp moved INTO the spawn, to first contact:
        # shadow_runner.spawn_delegate_session fires `on_first_turn` from
        # its `_adopt` hook -- the first frame that carries a session id,
        # which is the same instant the chat is published and the worker's
        # turn 1 begins painting. app._delegate_spawn passes
        # `open_first_turn` (this module) as that callback, so the writer of
        # the field is still this module and it keeps one meaning.
        #
        # THE CLEANUP BELOW MATTERS MORE NOW, not less: the spawner can
        # stamp at first contact and THEN fail its boot check, and a turn
        # nobody is working must not outlive the spawn.
        try:
            sid = await spawner(m)
        except BaseException:
            # A SPAWN THAT NEVER HAPPENED LEAVES NO TURN IN FLIGHT. The
            # record outlives the failure (the founder sees the mission),
            # so a turn number nobody is working must not outlive it too.
            failed = self.store.load(mid)
            if failed is not None and failed.get("turn_open") is not None:
                failed["turn_open"] = None
                self.store.save(failed)
            raise
        m = self.store.load(mid)
        m["target_session"] = sid
        # THE BRIEF HAS NOW BEEN DELIVERED, and this is the only place that
        # can know it: the spawner's contract (shadow_runner.
        # spawn_delegate_session) is "send the manifest, wait out the turn,
        # hand back a session id". run_mission reads this flag so turn 0 does
        # not say the same thing into the same session a second time.
        # Stamped on the mission rather than inferred from target_mode,
        # because an existing-target mission also has a session and was
        # never briefed -- see _next_say.
        m["manifest_delivered"] = True
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
        # ...AND THE PREVIOUS ITERATION MAY BELONG TO A PREVIOUS PROCESS.
        #
        # THE MEASURED FAILURE (founder dogfood, 2026-09-15, mission
        # m-80893d3f3d18). This loop is re-entered on every resume, and every
        # re-entry started here with nothing. The delegate's transcript held
        # 188 assistant messages, but the decider's FIRST turn after each
        # re-adoption was composed with an empty "what the target said back",
        # so Shadow spent the turn saying "No output from you yet -- keep
        # going". Across sixteen restart/re-adopt cycles that pattern burned
        # the budget and the mission died `failed` on max turns with the work
        # already well advanced. All four empty-response nudges landed within
        # fifteen seconds of a re-adoption; none landed anywhere else.
        #
        # The weakness was already named in _is_template_echo's docstring
        # above ("a resumed loop starts with last_response = None ... that is
        # a separate weakness and is NOT addressed here"). This addresses it.
        #
        # NOTHING NEW IS READ. response_reader is the reader the loop already
        # consults at the END of every iteration, and worker_response behind
        # it reads the DURABLE transcript (read_session), not the in-memory
        # stream -- which is exactly why it survives the restart that cleared
        # everything else. Seeding asks it one turn earlier.
        #
        # STRICTLY A SEED. The per-turn assignment below is untouched, so a
        # loop that runs continuously behaves as it always did: the first
        # iteration overwrites this with its own reading. A caller that
        # injects no response_reader (every existing test, the flag path) is
        # byte-identical -- the branch is not entered.
        #
        # FAILS TO None, NEVER TO A RUN. An unreadable store, a reader that
        # raises, a mission with no transcript yet: all leave the historical
        # value, which is the behaviour that shipped.
        if self.response_reader is not None:
            try:
                seed_m = self.store.load(mid)
                if seed_m is not None:
                    last_response = self.response_reader(seed_m) or None
            except Exception:       # noqa: BLE001 -- a seed must never fail a run
                last_response = None
        # ...AND THE BAR COMES BEFORE THE FIRST WORD, on this path too. An
        # existing-target mission is never provisioned, so its first contact
        # with the worker is turn 0's own say a few lines below. Guarded on
        # turns_used == 0 because a RESUMED loop has long since spoken; there
        # the ordinary decision path is what writes any missing criteria, as
        # it always did. A new-target mission arrives here with the checks
        # already written by provision_target and this is a no-op.
        m0 = self.store.load(mid)
        if m0 is not None and (m0.get("turns_used") or 0) == 0:
            await self._criteria_before_first_contact(m0)
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
            if autonomy() == "L0":
                # L0 WATCH: the same rule as the line above, one level up --
                # that makes ONE mission silent, this makes all of them.
                #
                # IT PAUSES RATHER THAN RETURNING, which is where it parts
                # company with never_say. A `watch` mission is SUPPOSED to sit
                # in `running` and observe forever; silence is its finished
                # state. A feature task held at L0 is not finished, it is
                # waiting for the founder to allow it, and a row reading
                # `running` while nothing will ever be said is the same lie
                # the inert selector used to tell. Pausing also frees the slot
                # (shadow_runner._launch), so a queue cannot stall behind
                # tasks that are forbidden to speak.
                m = self.store.transition(
                    mid, "paused",
                    "autonomy is L0 Watch -- Shadow is watching, not acting")
                m["pause_reason"] = "autonomy_hold"
                self.store.save(m)
                return m
            if m["turns_used"] >= m["max_turns"]:
                return self._out_of_road(
                    m, "failed", "budget_exhausted",
                    "max turns (%d) reached" % m["max_turns"])
            # THE BRIEF IS NEVER DELIVERED TWICE (founder, 2026-09-13).
            #
            # A target_mode="new" delegate is spawned by
            # shadow_runner.spawn_delegate_session, which sends the manifest
            # and waits out the ENTIRE first agentic turn before it hands back
            # a session id. Turn 0 here then sent the SAME manifest into the
            # SAME session: measured at 30s of duplicate model work on top of
            # the 44s spawn (mission m-e14f6acc41aa, 2026-09-12 -- the ledger
            # `say` row and the transcript's second user frame are both there).
            #
            # So the spawn turn IS turn 0. It was said, it was answered, and
            # the only thing that did not happen is the loop saying it. This
            # skips the SAY AND THE WAIT and nothing else: the accounting
            # below -- turns_used, the ledger row, the transcript read, the
            # done_when evaluation -- is the existing code on the existing
            # path, so a task the delegate finished in its first turn now
            # completes at the end of that turn instead of one turn later.
            #
            # provision_target stamps `manifest_delivered` when, and only
            # when, a spawner actually delivered it. An existing-target
            # mission never carries the flag and is byte-identical to before.
            briefed = (m["turns_used"] == 0
                       and bool(m.get("manifest_delivered")))
            # Shadow v4 (C9, ADR-043): A SAY THE FOUNDER APPROVED IS SENT AS
            # IT WAS SHOWN. approve_held_say stamps `approved_say` (the exact
            # string, hash-checked against the one-use approval); this turn
            # sends THAT string, composes nothing, and skips the floor and
            # the autonomy hold that held it -- the founder's yes is the
            # authority for this one say. It is cleared the moment it leaves.
            approved = bool(m.get("approved_say"))
            if approved:
                say_text, decision = m["approved_say"], None
            elif briefed:
                say_text, decision = self._next_say(m), None
                # THE COMPLETION BAR CANNOT WAIT FOR TURN 1 (founder dogfood,
                # 2026-09-15).
                #
                # WHAT WENT WRONG. A target_mode="new" delegate is briefed by
                # the SPAWN, so provision_target stamps manifest_delivered and
                # this branch deliberately sends nothing -- and it also set
                # `decision = None`, which is the only thing that could have
                # carried Shadow's criteria. A mission whose founder left
                # "Done when" blank therefore ran its whole first turn with an
                # empty bar: the card said "Shadow is writing these" while the
                # worker was already exploring, and nothing was written until
                # turn 1 -- if the mission lived that long.
                #
                # So the criteria, and ONLY the criteria, are taken here. The
                # brief already went out at spawn and is not re-sent: say_text
                # above is untouched, `decision` stays None, and every other
                # thing this branch did is byte-identical. What changes is
                # that the bar Shadow supervises against exists before it
                # supervises anything.
                if self.decider is not None and not (m.get("done_when") or []):
                    await self._first_criteria(m, last_response)
            else:
                say_text, decision = await self._instruction(m, last_response)
            self._adopt_criteria(m, decision)
            # ...and HOW, on the same path and for the same reason: a check
            # Shadow has just worked out how to establish must stop needing a
            # signature from the turn it works it out, not from the next
            # mission. Adopting after the criteria pass means a set written
            # one line above can be probed on the same decision.
            self._adopt_verification(m, decision)
            self._adopt_standing(m, decision)
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
                # THE SCREEN, BEFORE THE ESCALATION (D-SH-1, 2026-09-20).
                #
                # The tier ladder fixed what the founder signs off at the END
                # of a mission. This is the MIDDLE, and it was wide open: any
                # question at all could park a mission on the founder's desk,
                # which is the half of "stop asking me things" that the
                # criteria work did not touch.
                #
                # A REFUSED ASK IS NOT AN ERROR AND NOT AN ENDING. The
                # mission KEEPS DRIVING with an instruction to go and find
                # out, which is what Shadow should have done in the first
                # place and what it has full access to do. Falling through to
                # `continue` rather than blocking is the whole behaviour
                # change; nothing below this branch is touched.
                admitted, why = screen_ask(decision)
                refusals = int(m.get("ask_refusals") or 0)
                if not admitted and refusals >= ASK_REFUSAL_LIMIT:
                    # TRIED TWICE, STILL STUCK, SO IT IS BELIEVED. See
                    # ASK_REFUSAL_LIMIT: the alternative is a mission that
                    # ping-pongs itself to death against a fixed refusal
                    # string, and a task that quietly died is worse for the
                    # founder than a question they did not want.
                    admitted, why = True, (
                        "refused %d times already -- admitting rather than "
                        "grinding" % refusals)
                shadow_ledger.append("actions", {
                    "mission_id": mid, "kind": "ask_screen",
                    "summary": "%s: %s" % ("admitted" if admitted
                                           else "refused", why)})
                if not admitted:
                    m["ask_refusals"] = refusals + 1
                    try:
                        self.store.save(m)
                    except Exception:  # noqa: BLE001 -- a count, never a turn
                        pass
                    say_text = ASK_REFUSED_INSTRUCTION % (
                        (decision.get("reason")
                         or "the thing you were about to ask about")[:200])
                    decision = {"action": "continue", "reason":
                                "refused escalation: %s" % why,
                                "instruction": say_text}
                # ADMITTED falls through to the escalation below, which is
                # untouched and still the one writer of that exit.
            if decision is not None and decision["action"] == "ask_founder":
                # ASKING THE FOUNDER IS AN ESCALATION, NOT AN ENDING
                # (founder, 2026-09-14, dogfood m-98f1b3adf69f).
                #
                # This used to route through _out_of_road, which branches on
                # goal_id: a goal attempt blocked and the founder was asked,
                # and a STANDALONE mission was transitioned straight to
                # `stopped`. For the standalone case that made "I cannot make
                # progress, I need the human" indistinguishable from giving
                # up -- terminal, so the delegate was reaped by the runner,
                # and `block_reason` was dropped on the floor because
                # transition() does not stamp it. The founder saw a task that
                # had quietly stopped, with the reason only in a ledger note
                # nothing surfaces. Shadow's one way of speaking to the
                # founder mid-mission could not be heard.
                #
                # It is the SAME escalation either way, so it now takes the
                # same exit either way: store.block, which is what the goal
                # arm already called. Nothing else moves. `blocked` is an
                # existing state, `running -> blocked` was already legal and
                # already reached from here for goals, the UI has read it as
                # NEEDS YOU since it first existed, and the runner already
                # treats it as the one non-terminal stop -- the delegate is
                # deliberately kept ALIVE so the founder can answer in the
                # chat, while the execution slot is freed so the queue moves.
                #
                # _out_of_road is UNTOUCHED and still owns the three exits
                # that really are out of road: budget spent, ping-pong, and
                # the stalled-turn routing. Those keep their historical
                # terminal states for a standalone mission exactly as before.
                # This is only the exit Shadow takes deliberately.
                blocked = self.store.block(
                    mid, "needs_founder",
                    decision["reason"] or "Shadow asked for the founder")
                # THE FORM RIDES BESIDE THE STATE, exactly as pause_reason,
                # block_reason and pending_floor_say already do. store.block
                # is unchanged and still the one writer of block_reason; this
                # only attaches what Shadow wants ASKED. Without an
                # intervention the record is byte-identical to before, which
                # is what keeps every prose-only ask_founder working.
                iv = decision.get("intervention")
                if iv:
                    blocked["intervention"] = iv
                    self.store.save(blocked)
                return blocked
            if decision is not None and decision["action"] == "undecided":
                # R10: never fall back to a generic instruction, never
                # complete. Say honestly that the driver could not decide.
                return self._out_of_road(
                    m, "failed", "shadow_undecided", decision["reason"])
            if briefed and not approved:
                # Nothing is sent and nothing is waited on -- the turn this
                # would have produced already happened, inside the spawn.
                # last_say is still set, so a decider that answers turn 1 with
                # the manifest verbatim trips the SAME ping-pong guard.
                last_say = say_text
                m["last_instruction"] = say_text[:DECISION_INSTRUCTION_MAX]
                self.store.save(m)
            else:
                if say_text == last_say:
                    return self._out_of_road(
                        m, "stopped", "ping_pong",
                        "ping-pong detected (identical consecutive says)")
                floors = ([] if approved
                          else shadow_egress.floor_check(say_text))
                if floors:
                    # S52: the say never leaves the engine; the founder decides
                    # -- through a one-use approval bound to this exact string
                    # (v4 C9), never a bare Resume that recomposes.
                    return self._hold_say(
                        m, "floor_confirm",
                        "floor requires confirmation: %s" % ", ".join(floors),
                        say_text)
                # AUTONOMY COMES AFTER THE FLOOR, AND THAT ORDER IS THE
                # PRECEDENCE RULE ITSELF (SHADOW.md section 3: floors are rank
                # 1, above this session's founder words). A say can trip both
                # -- "push --force to the client repo" at L1 is a floor AND a
                # held suggestion -- and the founder must be told the floor,
                # because that is the fact that does not change no matter what
                # they pick in Settings. Reporting "waiting for your yes" for
                # something that is permanently confirm-first would teach them
                # that raising autonomy would clear it. It would not.
                #
                # NOTHING BELOW CAN REACH THE FLOOR CHECK, either: it returns.
                # So no autonomy level, L3 included, can route around it --
                # which is the property test_shadow_autonomy pins directly
                # rather than leaving to inspection of this comment.
                hold = None if approved else self._autonomy_hold(m, say_text)
                if hold is not None:
                    return hold
                # THE LAST LOOK BEFORE SPEAKING, and the takeover window it
                # closes (founder, 2026-09-14: "clicked Take Over on a
                # running task at turn 3, the task went FAILED").
                #
                # Composing an instruction is a model call and takes seconds
                # -- 9s on mission m-8935e9a46557. Take Over lands inside
                # that gap: it pauses the mission AND reaps the delegate,
                # which is exactly what it is supposed to do (ownership must
                # end or the founder cannot type). The loop was then still
                # holding the pre-takeover snapshot, said into a session that
                # no longer had a runtime, got the "no_live_runtime"
                # precondition back and sent a DELIBERATE disownment down
                # _out_of_road as a failure:
                #
                #   t+206s  say      turn 3
                #   t+214s  paused   "founder typed in the target session"
                #   t+215s  say NOT DELIVERED (no_live_runtime)
                #   t+215s  failed   "say not delivered -- nothing was sent"
                #
                # It even cleared pause_reason on the way, so the record no
                # longer said the founder had taken over at all.
                #
                # THE SAME RELOAD THIS LOOP ALREADY DOES, one step earlier.
                # Step 8 reloads after the boundary wait for precisely this
                # reason ("nothing terminal is decided on a pre-takeover
                # snapshot"); the other side of the decision call was simply
                # never covered. Returning the fresh record preserves the
                # state and pause_reason the founder's action wrote, and the
                # same check closes the founder-stop race for free.
                #
                # No new state, no special case for no_live_runtime, and
                # _out_of_road is untouched: the say that would have failed
                # is never attempted.
                m = self.store.load(mid)
                if m["state"] in TERMINAL or m["state"] in ("paused",
                                                            "blocked"):
                    return m      # the founder took the wheel mid-compose
                ok = await self.sayer(m, say_text)
                # A STRING is a named, retryable precondition -- the say was
                # never delivered, so nothing about the attempt is spent. It
                # goes down _out_of_road, which now reads it as the INFRA
                # fault it always was (INFRA_BLOCK_REASONS): the work is
                # evaluated first, and the mission completes, waits for the
                # founder's signature, or parks as NEEDS YOU -- for a goal
                # attempt and a standalone mission alike. It never `failed`
                # again; that was the "Budget per task" post-mortem.
                # False stays what it always was: the say itself was turned
                # down, which IS a refusal and still fails.
                # non-empty: an EMPTY string is falsy and means nothing, so it
                # stays a plain refusal rather than becoming a nameless blocker
                # (store.block rightly refuses a reasonless block)
                if isinstance(ok, str) and ok:
                    # infra=True on the SHAPE, not on the id: any named
                    # precondition means the say never left, whatever it is
                    # called, so a blocker id added later cannot quietly go
                    # back to failing missions whose work is fine.
                    return self._out_of_road(
                        m, "failed", ok,
                        "say not delivered (%s) -- nothing was sent" % ok,
                        infra=True)
                if not ok:
                    # A REFUSAL IS A VERDICT ON THE SAY, NOT ON THE WORK
                    # (founder, 2026-09-16). False means the sayer itself
                    # turned the turn down -- which IS a refusal and still
                    # fails -- but it says nothing about a worker that may
                    # have finished everything on the previous turn. This was
                    # the last ending that bypassed the funnel entirely, so
                    # it never evaluated, never asked the founder, and (for a
                    # goal attempt) died without the escalation V5 exists to
                    # guarantee. The transition it takes when the work really
                    # is unfinished is the same one, with the same note.
                    return self._out_of_road(m, "failed", "say_refused",
                                             "say refused")
                last_say = say_text
                if approved:
                    # ONE USE: the approved string has left; nothing below can
                    # send it again without a fresh approval
                    m["approved_say"] = None
                    m["pending_say"] = None
                    m["pending_floor_say"] = None
                    m["pending_autonomy_say"] = None
                    approved = False
                # remembered on the record, so a resumed attempt and the ledger
                # both know what Shadow last asked for
                m["last_instruction"] = say_text[:DECISION_INSTRUCTION_MAX]
                # THE TURN THAT IS HAPPENING RIGHT NOW (founder, 2026-09-16).
                #
                # turns_used counts turns that FINISHED -- it is incremented
                # after the boundary arrives, which is correct for a budget
                # and wrong for a display. Between this say and that boundary
                # the worker IS on a turn that no field named, so the card
                # read "TURN 3 of 30" while turn 4 was the one being worked,
                # and a restart in that window lost the fact entirely.
                #
                # `turn_open` is that missing fact and nothing more: the
                # number of the turn currently in flight, written before the
                # wait and cleared when the wait resolves. It never feeds the
                # budget (turns_used is still the only thing max_turns is
                # compared against) and it never feeds evaluation. It is
                # durable on purpose -- surviving the restart is the point.
                m["turn_open"] = m["turns_used"] + 1
                self.store.save(m)
                arrived = await self.waiter(m)
                if isinstance(arrived, str) and arrived:
                    # A NAMED PRECONDITION FROM THE WAITER, read exactly as
                    # the sayer's is a few lines above: the turn boundary
                    # could not be OBSERVED, which is a fault in Shadow's own
                    # plumbing and not a reading of the worker. The live case
                    # is a boundary queue that _forget_session dropped
                    # (a reap-and-reattach race): the wait then returned
                    # False without waiting a single second, and a worker
                    # that was finishing normally was `failed` with its
                    # result never evaluated. infra=True on the SHAPE, for
                    # the same reason it is on the say arm -- any named
                    # precondition means the wait never happened, whatever a
                    # later one is called.
                    return self._out_of_road(
                        m, "failed", arrived,
                        "turn boundary not observable (%s)" % arrived,
                        infra=True)
                if arrived is False:
                    # A STALLED TURN IS OUT OF ROAD, NOT A VERDICT. The wait
                    # ending without a boundary says the worker stopped
                    # producing -- it says nothing about whether the outcome
                    # is reachable. Routing it straight to `failed` was the
                    # one machine-run exit that skipped _out_of_road, so a
                    # GOAL could die on a stall with the founder never asked,
                    # which is exactly what V5 exists to prevent.
                    #
                    # _out_of_road keeps both halves intact: a goal attempt
                    # BLOCKS (founder asked, chat kept alive, Resume works),
                    # a standalone mission takes the same `failed` transition
                    # with the same note it always had.
                    return self._out_of_road(
                        m, "failed", "turn_stalled",
                        "boundary wait timed out")
            m = self.store.load(mid)
            if m["state"] in TERMINAL or m["state"] in ("paused", "blocked"):
                return m          # something terminal happened mid-turn
            m["turns_used"] += 1
            # the in-flight turn just became a finished one; exactly one field
            # describes it at a time
            m["turn_open"] = None
            self.store.save(m)
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "say",
                # the ledger must not claim a say that never left the engine:
                # a briefed turn 0 is the SPAWN's say, counted here
                "summary": (("(brief already delivered at spawn) "
                             if briefed else "") + say_text)[:200]})
            # AN EVALUATION THAT CANNOT ANSWER IS NOT A FAILED MISSION
            # (founder, 2026-09-16). The reader and the verifier are Shadow's
            # machinery, and either can raise on a turn the WORKER finished
            # perfectly well -- an unreadable transcript, a verifier with a
            # bug. That exception used to leave run_mission entirely and land
            # in _launch's crash handler, which wrote `failed`. It now takes
            # the same infra exit every other supervisor fault takes, so the
            # work is evaluated (or the founder asked) instead of buried.
            try:
                transcript = self.reader(m)
            except Exception as exc:      # noqa: BLE001 -- parked, not hidden
                return self._out_of_road(
                    m, "failed", "shadow_eval_failed",
                    "evidence unreadable: %s" % str(exc)[:160])
            # TWO READERS, TWO JOBS, AND THEY MUST NOT BE THE SAME STRING.
            # `transcript` is the EVIDENCE and is untouched: evaluate_done_when
            # below still receives the full evidence_text, so every
            # contains_artifact match that was reachable before still is.
            # `last_response` is only ever read by the DECIDER, and it now
            # carries whole worker messages instead of the blob's last 2000
            # bytes -- no JSON envelope, no message cut off at its head.
            # Falling back to `transcript` keeps the historical value for any
            # caller that injects no response_reader.
            last_response = transcript
            if self.response_reader is not None:
                try:
                    shaped = self.response_reader(m)
                except Exception:       # noqa: BLE001 -- never fail a turn
                    shaped = ""
                if shaped:
                    last_response = shaped
            # THE JUDGES RUN HERE, AND ONLY HERE (D-SH-1). This is the one
            # async point that both owns the record and sits immediately
            # before an evaluation, so a verdict can never be a turn stale by
            # the time it is read. `_run_judges` stamps the row;
            # `evaluate_done_when` -- which is synchronous and has three
            # other callers -- only ever reads the stamp. Never raises.
            try:
                await self._run_judges(m)
            except Exception as exc:      # noqa: BLE001 -- unjudged, not failed
                shadow_ledger.append("actions", {
                    "mission_id": mid, "kind": "judge",
                    "summary": "judging skipped: %s" % str(exc)[:120]})
            try:
                done, results = evaluate_done_when(m, transcript,
                                                   self.verifier,
                                                   self.probe_root)
            except Exception as exc:      # noqa: BLE001 -- parked, not hidden
                return self._out_of_road(
                    m, "failed", "shadow_eval_failed",
                    "evaluation raised: %s" % str(exc)[:160])
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
            # A CONFIRMATION PAUSE MUST BE EARNED, NOT INHERITED FROM AN
            # EMPTY SET (live, missions m-b7d534be84d7 / m-0213b89e5feb /
            # m-d817efbe3aa1 -- three of three).
            #
            # This was `all(r["met"] for r in results if tier != confirm)`.
            # When EVERY check is founder_confirm that generator is empty and
            # all([]) is True, so the mission paused on its FIRST evaluation
            # having verified nothing and driven nothing: m-b7d534be84d7 went
            # running -> paused inside the same second, turn 1 of 20, no
            # decider call, no instruction ever sent. The founder was asked to
            # sign off four criteria the delegate had not begun.
            #
            # And all-founder_confirm is the DEFAULT, not an edge case:
            # shadow_protocol.tier_for demotes every check that is not a
            # short literal marker, so a founder describing an outcome in
            # ordinary words gets exactly this shape.
            #
            # THE RULE: the confirmation boundary is reached only when there
            # was machine-checkable work AND it passed. With no machine check
            # at all there is nothing to have passed, so the loop keeps
            # driving and the founder confirms whenever they are ready --
            # confirm_check + settle_confirmation already work from outside
            # the loop, and are untouched here.
            #
            # This cannot complete a mission: `done` still comes only from
            # evaluate_done_when above, and _complete is still its one writer.
            # the rule itself now lives in confirmation_is_due() -- same
            # clauses, same order, one copy, so the infra exit cannot drift
            # from the loop
            if confirmation_is_due(results):
                return self._await_confirmation(mid)

    def _complete(self, mid, results, transcript):
        """The ONE writer of a `done` mission.

        Lifted verbatim out of the loop so the confirmation path below can
        reach the same completion instead of growing a second one. Same
        transition, same excerpt, same ledger row, in the same order.

        The completion summary is stamped HERE for that same reason; see
        the note under it.
        """
        mm = self.store.transition(
            mid, "done", "done_when met: %s" % json.dumps(results)[:400])
        t = transcript or ""
        mm["result_excerpt"] = (t if len(t) <= 400
                                else t[:150] + " ... " + t[-250:])
        # THE SUMMARY IS STAMPED HERE and nowhere else, for the same reason
        # the transition is: this is the one writer of a done mission, so it
        # is the one place where "what was done and why it counts" can never
        # disagree with the state on disk. `result_excerpt` above is
        # untouched -- every existing reader (goal_lifecycle.
        # _record_attempt_memory, the overlay's shmission card, three tests)
        # keeps the field it reads. This adds a field; it replaces none.
        # THE WORKER'S OWN ACCOUNT, asked for exactly once and here, where
        # the state it describes is already settled. Guarded the same way
        # on_evaluated is and for the same reason: a reader that raises must
        # not be able to lose a mission its completion. A failure costs the
        # outcome line and nothing else -- the summary, the transition and
        # the ledger row below are all already decided.
        outcome = ""
        if self.outcome_reader:
            try:
                outcome = self.outcome_reader(mm) or ""
            except Exception:
                outcome = ""
        mm["completion"] = completion_summary(mm, results, t, outcome)
        self.store.save(mm)
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "result",
            # the headline leads: an audit row that opens with "3 of 3
            # checks passed" is readable, one that opens mid-json is not.
            "summary": ("%s -- %s" % (mm["completion"]["headline"],
                                      mm["result_excerpt"]))[:200]})
        return mm

    def _await_confirmation(self, mid):
        """The machine work passed; only the founder's signature is left.

        Lifted verbatim out of the loop (transition, stamp, save, return) so
        the infra exit can reach the SAME waiting room rather than inventing
        a second one. The founder reads this as NEEDS YOU, `settle` turns
        their Yes into `done`, and nothing here can satisfy a check.
        """
        m = self.store.transition(mid, "paused",
                                  "awaiting founder confirmation")
        m["pause_reason"] = "founder_confirm"
        self.store.save(m)
        return m

    def _autonomy_hold(self, m, say_text):
        """Hold this say for the founder, or None to let it go.

        TWO HOLDS, ONE SHAPE. L1 Suggest holds EVERY say: the founder wanted
        to see each instruction before it lands, so every turn asks. L3 Act
        with the top-tier switch on holds the FIRST say of the mission and
        then never again -- the founder is authorising the tier, not
        proof-reading the work, and asking every turn would make L3
        indistinguishable from L1, which would make the four levels three.
        L2 never holds here: its restraint is the worker's `plan` ceiling, so
        the instruction itself is safe to send.

        ONCE PER MISSION IS RECORDED ON THE MISSION (`top_tier_confirmed`),
        not in memory, because the app restarts and a resumed loop must not
        re-ask something the founder already answered.

        THE PENDING SAY IS STORED THE WAY A FLOORED ONE IS, and carries the
        same known limitation: resuming re-enters run_mission, which composes
        a FRESH instruction from whatever the worker has said since. So the
        founder is approving the tier or the turn, not signing a specific
        string. That is already true of `pending_floor_say` (which has no
        consumer either); fixing it means a one-use approval bound to a hash
        of the text, and it is deliberately not invented here for autonomy
        alone -- one approval mechanism, added once, for both.
        """
        level = autonomy()
        if level == "L1":
            return self._hold_say(
                m, "autonomy_suggest",
                "autonomy is L1 Suggest -- waiting for your yes", say_text)
        if level == "L3" and confirm_top_tier() \
                and not m.get("top_tier_confirmed"):
            return self._hold_say(
                m, "autonomy_top_tier",
                "autonomy is L3 Act -- confirm before the top tier", say_text)
        return None

    def _hold_say(self, m, reason, note, say_text):
        """Park a say for the founder, with a ONE-USE APPROVAL bound to it
        (Shadow v4 C9, ADR-043; the mechanism _autonomy_hold's docstring
        deferred). One shape for the three holds: floor_confirm,
        autonomy_suggest, autonomy_top_tier. The legacy pending_* keys are
        kept so every existing reader of them is unchanged; `pending_say`
        carries the full string the approval hashes."""
        held = self.store.transition(m["id"], "paused", note)
        held["pause_reason"] = reason
        key = ("pending_floor_say" if reason == "floor_confirm"
               else "pending_autonomy_say")
        held[key] = say_text[:1000]
        held["pending_say"] = say_text
        held["approval"] = mint_approval(held, reason, say_text)
        self.store.save(held)
        return held

    def _work_says(self, m):
        """The loop's own evaluation, asked from an ENDING path.

        Lifted verbatim out of _infra_exit so the ordinary endings below can
        ask the same question with the same evidence reader, the same
        verifier and the same evaluator -- one copy, so the two exits cannot
        drift into two different bars.

        NEVER RAISES AND NEVER A VERDICT. An unreadable transcript or a
        verifier with a bug answers "unknown" (False, None), which every
        caller treats as "do not complete", never as "the work failed".
        """
        try:
            transcript = self.reader(m) if self.reader is not None else ""
            done, results = evaluate_done_when(m, transcript, self.verifier,
                                               self.probe_root)
        except Exception:         # noqa: BLE001 -- unknown, never a verdict
            return "", None, False
        return transcript, results, done

    def _work_first(self, m, block_reason):
        """ASK THE WORK BEFORE DECLARING AN ORDINARY ENDING.

        The discipline _infra_exit already applies to a fault in the
        SUPERVISOR, applied to the four endings that are decided by the
        machine running out of road -- budget spent, ping-pong, a stalled
        turn, a refused say. Those exits wrote a terminal state WITHOUT ONCE
        CONSULTING THE WORK, which is the same sentence the supervisor
        post-mortems were, one exit over.

        Returns the settled mission, or None to mean "no reason to stop the
        historical ending":

          1. already settled       -> hand back what is on disk. A `done`
                                      mission is NEVER re-decided; the
                                      completion is the worker's.
          2. the work is done      -> _complete it (DONE).
          3. only the signature is
             left, and the attempt
             was actually driven   -> _await_confirmation (NEEDS YOU).
          4. otherwise             -> None: budget, ping-pong, stall and
                                      refusal keep the exact terminal state
                                      and note they have always had.

        NO SECOND EVALUATOR AND NO WEAKER BAR. Step 2 is evaluate_done_when
        on the same evidence with the same verifier, and step 3 satisfies
        nothing -- it hands the founder a check only they can sign.
        """
        mid = m["id"]
        fresh = self.store.load(mid) or m
        if fresh["state"] in TERMINAL or fresh["state"] in ("paused",
                                                            "blocked"):
            return fresh
        transcript, results, done = self._work_says(fresh)
        if done:
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "decision",
                "summary": "%s, but the work was already done -- completing "
                           "instead of ending it" % block_reason})
            return self._complete(mid, results, transcript)
        if confirmation_reachable(results, fresh.get("turns_used")):
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "decision",
                "summary": "%s, and only your sign-off is outstanding -- "
                           "awaiting founder confirmation" % block_reason})
            return self._await_confirmation(mid)
        return None

    def _infra_exit(self, m, block_reason, note):
        """SHADOW BROKE. ASK THE WORK FIRST, THEN PARK -- NEVER FAIL.

        The one funnel for every fault in the supervisor (INFRA_BLOCK_REASONS
        names them). It exists because the two live post-mortems were the
        same sentence twice: a fault in Shadow decided a mission's fate
        WITHOUT ONCE CONSULTING THE WORK.

          m-5c2fca3f824b  decider unreadable -> failed; the worker finished
                          successfully 96s later and the result was dropped.
          m-6b177e1cbdf0  founder confirmed a check, the next say found no
                          runtime -> failed 11s after the sign-off.

        So this asks, in order:

          1. is the mission already settled?   -> hand back what is on disk.
             A `done` mission is NEVER re-decided by a later Shadow fault:
             the completion is the worker's, not the supervisor's, and
             nothing here may overwrite it.
          2. is the work already done?         -> _complete it (DONE).
          3. is only the signature left?       -> _await_confirmation
                                                  (NEEDS YOU -> DONE on Yes).
          4. otherwise                         -> blocked (NEEDS YOU).

        NO SECOND EVALUATOR AND NO WEAKER BAR. Steps 2 and 3 are the loop's
        own evaluate_done_when, its own evidence reader, its own verifier and
        its own confirmation rule -- the same code the loop runs one screen
        further down and could not reach, because the fault returned first.
        A check Shadow could not verify a second ago is still unmet here.

        AND IF THE EVALUATION ITSELF CANNOT ANSWER -- an unreadable
        transcript, a verifier that raises -- that is not a verdict either:
        the answer is unknown, so the mission parks at step 4 and the founder
        is asked. Never `failed`.
        """
        mid = m["id"]
        fresh = self.store.load(mid) or m
        # 1. the founder (or a finished turn) already settled this
        if fresh["state"] in TERMINAL or fresh["state"] in ("paused",
                                                            "blocked"):
            return fresh
        transcript, results, done = self._work_says(fresh)
        if done:
            # 2. THE WORKER'S RESULT WINS. The supervisor's illness cannot
            # take a finished outcome away from the founder.
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "decision",
                "summary": "%s, but the work was already done -- completing "
                           "instead of failing" % block_reason})
            return self._complete(mid, results, transcript)
        if confirmation_is_due(results):
            # 3. everything machine-checkable passed: this is a signature,
            # not a failure
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "decision",
                "summary": "%s, machine checks all passed -- awaiting "
                           "founder confirmation" % block_reason})
            return self._await_confirmation(mid)
        # 4. genuinely unresolved: park it where Resume works
        blocked = self.store.block(mid, block_reason, note)
        blocked["failure_class"] = INFRA_FAILURE_CLASS
        self.store.save(blocked)
        return blocked

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
        # THE OTHER WAITING ROOM (founder, 2026-09-16). A founder_confirm
        # check is reached two ways, not one: the loop PAUSES on it, and
        # Shadow's own `ask_founder` BLOCKS on it -- and an intervention that
        # declares `confirms_check` is answered in exactly that blocked
        # state. Settling only the pause meant the blocked half went back
        # through the loop to learn something already true: another decider
        # call, another say into the worker chat, another turn spent, and on
        # m-6b177e1cbdf0 that relaunch is the say that died of
        # no_live_runtime. A mission whose last check the founder just
        # signed must not have to take a turn to notice.
        #
        # THE BAR IS UNTOUCHED. `done` still comes only from
        # evaluate_done_when below, on the same evidence with the same
        # verifier, and `not done` still returns the record exactly as it
        # was -- a blocked mission stays blocked, with its block_reason, and
        # the founder's answer resumes it as before.
        settleable = (
            (m["state"] == "paused"
             and m.get("pause_reason") == "founder_confirm")
            or m["state"] == "blocked")
        if not settleable:
            return m            # not a confirmation wait -- untouched
        transcript = self.reader(m) if self.reader is not None else ""
        done, results = evaluate_done_when(m, transcript, self.verifier,
                                           self.probe_root)
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

    def _out_of_road(self, m, terminal_state, block_reason, note,
                     infra=False):
        """The one place that decides how an attempt ends when the machine
        runs out of road (budget spent, or the chat repeating itself).

        An attempt OF A GOAL blocks: V5's core behavioural change is
        "pause -> name the blocker -> ask -> resume the same chat" instead
        of "stop -> report failure -> offer a fresh chat", and a goal must
        never die without the founder having been asked. The target chat is
        left alive and no new chat is created.

        A STANDALONE mission (no goal_id) keeps the historical terminal
        state -- failed on budget, stopped on ping-pong, delegate reaped,
        feed post-mortem -- WHENEVER THE WORK IS GENUINELY UNFINISHED. That
        is what keeps every shipped path, and every existing test, behaving
        as before. `_work_first` below is what decides whether it is: a
        mission whose checks are met completes, and one whose only
        outstanding checks are the founder's to sign waits for that
        signature. Neither is an ending the machine is entitled to call.

        The ledger note is identical either way, so the audit trail reads
        the same for both.
        """
        # A FAULT IN SHADOW IS NEVER A VERDICT ON THE WORK. Checked BEFORE
        # goal_id, because it holds for a standalone mission too -- that is
        # the whole of the change. _infra_exit decides where such a fault
        # lands (done / needs-you / blocked) and is the only thing that runs
        # instead of the two lines below. Everything else about this method is
        # untouched: budget, ping-pong and stalled turns keep their historical
        # terminal states for a standalone mission and their block for a goal.
        #
        # TWO WAYS IN, ONE EXIT. `infra=True` is for a caller that knows the
        # SHAPE is a supervisor fault whatever it is called -- the say-
        # precondition arm, whose blocker ids come from session_runtime and
        # may grow. INFRA_BLOCK_REASONS is for the faults the engine names
        # itself. Neither can reach a terminal state.
        if infra or block_reason in INFRA_BLOCK_REASONS:
            return self._infra_exit(m, block_reason, note)
        # ...AND NEITHER IS RUNNING OUT OF ROAD, UNTIL THE WORK HAS BEEN
        # ASKED (founder, 2026-09-16). The four ordinary endings below are
        # decided by the MACHINE -- the budget is spent, the chat repeated
        # itself, the turn stalled, the say was turned down -- and none of
        # them is a reading of whether the outcome was reached. Each one
        # wrote a terminal state with `evaluate_done_when` sitting one screen
        # away, unasked.
        #
        # _work_first asks it, and returns None for everything it cannot
        # settle -- so budget, ping-pong, stall and refusal keep the exact
        # terminal state, the exact note and the exact block_reason they have
        # always had whenever the work is genuinely unfinished. What changes
        # is the two cases where the ending was a lie: the work was done, or
        # the only thing outstanding was a signature nobody had been asked
        # for.
        settled = self._work_first(m, block_reason)
        if settled is not None:
            return settled
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
        carry = carry_block()          # one limits read, not two
        return {
            # Shadow v4 (ADR-043): the decider router needs to know WHICH
            # task is asking, so it can hand the turn to that task's own
            # Shadow chat. One key, read only by shadow_task_chat.
            "mission_id": m.get("id"),
            # THE FOUNDER'S OWN TWO TEXTS. Every other Shadow-shaped process
            # inherits these from the boot context; the decider is a fresh
            # spawn with no persona turn, so it reads them here or not at
            # all. Omitted entirely when both are empty, so a decider prompt
            # on an unconfigured install is byte-identical to before.
            **({"carry": carry} if carry else {}),
            "outcome": m.get("objective") or "",
            # `probe` is a BOOLEAN, never the probe itself: Shadow is told
            # WHICH checks it has already worked out how to establish, so it
            # does not answer the same question twice -- and is not handed
            # back a payload it could copy instead of composing.
            "checks": [{"tier": c.get("tier"), "check": c.get("check"),
                        "met": bool(c.get("met")),
                        "probe": bool(c.get("probe"))}
                       for c in (m.get("done_when") or [])],
            "turns_used": m.get("turns_used") or 0,
            "max_turns": m.get("max_turns") or 0,
            "last_instruction": m.get("last_instruction") or "",
            "last_response": (last_response or "")[-DECISION_TAIL:],
            # THE ANSWER COMES TO SHADOW, NOT TO THE WORKER. The founder's
            # reply is a LABELLED BLOCK here -- never folded into
            # last_response -- so Shadow can tell what it was told from what
            # the worker said, and so a value can never be mistaken for the
            # worker's own output. Absent on every mission that has not been
            # answered, which is every mission that existed before this.
            **({"founder_response": m["founder_response"]}
               if m.get("founder_response") else {}),
            # WHAT THE FOUNDER VOLUNTEERED, unprompted, since Shadow last
            # decided. A separate block from founder_response for the same
            # reason that one is separate from last_response: an aside the
            # founder chose to send is not an answer to a question Shadow
            # asked, and Shadow must be able to tell them apart. Only the
            # UNSEEN ones -- once a turn has read an aside it is standing
            # context, not news, and repeating it every turn would let one
            # sentence dominate the prompt for the rest of the mission.
            **({"founder_says": [s for s in (m.get("founder_says") or [])
                                 if not s.get("seen")]}
               if any(not s.get("seen")
                      for s in (m.get("founder_says") or [])) else {}),
            # WHAT CURRENTLY GOVERNS THE TASK. Unlike founder_says this is
            # NOT consumed: a standing instruction is standing precisely
            # because it survives the turn that created it, so it is sent on
            # every decision until Shadow replaces the set. It is Shadow's
            # own restatement, kept apart from the founder's raw words above
            # for the same reason those are kept apart from last_response.
            **({"standing": [str(r.get("text") or "").strip()
                             for r in (m.get("standing_instructions") or [])
                             if isinstance(r, dict)
                             and str(r.get("text") or "").strip()]}
               if (m.get("standing_instructions") or []) else {}),
        }

    def _adopt_standing(self, m, decision):
        """Write the ACTIVE instruction set Shadow composed, onto the task.

        WHY A FIELD OF ITS OWN, and it is the only thing step 2.5 adds to the
        record. `founder_says` is an append-only log of the founder's RAW
        words with a per-row consumption flag: it answers "what has the
        founder said", and it must keep answering that, so nothing in it may
        be rewritten when an instruction is superseded. `done_when` is the
        completion contract the verifier reads. The precedence ledger
        (shadow_precedence) is global/chat-scoped, gated on an explicit
        founder Confirm, and is injected into the WORKER'S manifest at spawn
        -- it never reaches a decision. None of the three can hold "what
        currently governs THIS task", so one small named field does.

        THE LINES ARE SHADOW'S, NOT THE FOUNDER'S. Shadow restates each
        constraint in its own words when it composes the set, which is what
        keeps a raw chat line from ever becoming a worker instruction by
        being stored.

        ABSENT MEANS KEEP. Only a decision that actually carried the key
        writes here, so a fallback decider, a malformed reply or an older
        model cannot drop the constraints the founder is relying on. An empty
        list is a deliberate clear and is honoured.

        NOTHING ELSE MOVES: no state, no turn, no budget, no check. Writing
        the set cannot send a turn -- only the instruction the same decision
        carried can, through the path it always took.
        """
        if decision is None or "standing" not in decision:
            return False
        was = [str(r.get("text") or "")
               for r in (m.get("standing_instructions") or [])
               if isinstance(r, dict)]
        now = list(decision["standing"])
        if was == now:
            return False              # nothing changed; no write, no row
        stamp = _now()
        rows = [{"text": t, "at": stamp} for t in now]
        m["standing_instructions"] = rows
        # Same reason as _adopt_criteria: `m` has been held across the decider
        # call, and anything that stamps the record during it would make this
        # a stale write. Write the one field onto what is on disk.
        self._save_field(m, "standing_instructions", rows)
        shadow_ledger.append("actions", {
            "mission_id": m["id"], "kind": "decision",
            "summary": ("standing instructions now %d: %s"
                        % (len(now), " | ".join(now)))[:200]})
        return True

    def _save_field(self, m, field, value, skip_if=None):
        """Persist ONE field onto the record as it stands on disk.

        The engine loads a mission, awaits something slow (a decider, a
        spawner) and then writes -- and anything that stamped the record
        during that await makes the write stale. MissionStore refuses it, by
        design; this obeys that refusal instead of fighting it by re-reading
        first and writing only the field the caller owns.

        `skip_if(fresh)` re-checks the caller's own precondition against the
        fresh record, so a condition that was true before the await but false
        after it does not get overwritten.

        Falls back to saving the held copy when the mission has vanished --
        that is the pre-existing behaviour and the caller's error to see.
        """
        fresh = self.store.load(m["id"])
        if fresh is None:
            self.store.save(m)
            return
        if skip_if is not None and skip_if(fresh):
            return
        fresh[field] = value
        self.store.save(fresh)
        m["seq"] = fresh.get("seq", m.get("seq"))

    def _adopt_criteria(self, m, decision):
        """Write the checks Shadow composed, onto an empty set only.

        ONE WRITER for both callers -- the turn-0 criteria pass and the
        ordinary decision path -- so the founder's own criteria are protected
        by one condition in one place rather than two that can drift apart.
        Returns True when something was written.
        """
        if decision is None or not decision.get("done_when"):
            return False
        if m.get("done_when") or []:
            return False              # the founder said; it is not Shadow's
        checks = [dict(c) for c in decision["done_when"]]
        m["done_when"] = checks
        # WRITE ONTO WHAT IS ON DISK, NOT ONTO A SNAPSHOT HELD ACROSS AN AWAIT
        # (founder, 2026-09-17; mission m-b3eefc51a768). `m` was loaded before
        # the decider was asked, and asking the decider BOOTS THIS TASK'S
        # SHADOW CHAT -- whose publication stamps `task_chat_session` and
        # `task_chat` onto the record, two saves, two sequence bumps. Saving
        # the held copy then hit MissionStore's stale-write guard, the
        # ValueError left provision_target, and start_mission_async's handler
        # turned a bookkeeping collision into a FAILED mission that had never
        # run a worker.
        #
        # THE GUARD IS NOT WEAKENED, IT IS OBEYED: re-read, re-check the one
        # condition this method owns, write only its own field. The in-memory
        # `m` the caller holds keeps the checks either way, so nothing
        # downstream of this call changes.
        self._save_field(m, "done_when", checks,
                         skip_if=lambda fresh: bool(fresh.get("done_when")))
        shadow_ledger.append("actions", {
            "mission_id": m["id"], "kind": "criteria",
            "summary": "Shadow wrote %d check(s) the founder left open: %s"
                       % (len(m["done_when"]),
                          "; ".join(c["check"] for c in m["done_when"])[:160])})
        return True

    def _needs_verification(self, m):
        """Indices of checks Shadow has not yet worked out how to establish.

        A check qualifies when it is `founder_confirm` OR `judge` and carries
        no probe -- which is the shape of "nobody has worked out how yet",
        whoever wrote it. A `verify` row already has its probe
        (resolve_verify_tier guarantees it), and a `contains_artifact` row is
        a literal the work itself must produce.

        `judge` JOINED THE LIST 2026-09-20 (D-SH-1), and the promotion is
        always an UPGRADE. A judge row settled by reading a diff is weaker
        than the same row settled by running a command: the probe is
        deterministic, repeatable and costs no model call. So a judge row
        Shadow later works out how to probe should stop being judged, exactly
        as a founder row that gets a probe stops being signed.
        """
        return [i for i, c in enumerate(m.get("done_when") or [])
                if isinstance(c, dict)
                and c.get("tier") in ("founder_confirm", "judge")
                and not c.get("probe")
                and not c.get("met")]

    def _adopt_verification(self, m, decision):
        """Attach HOW to checks that already say WHAT. Returns True if any
        check changed.

        WHAT THIS MAY DO, AND THE LIST IS THE WHOLE CONTRACT:

          founder_confirm + a valid probe  ->  verify, probe attached

        WHAT IT MAY NEVER DO: change a check's text, drop a check, add one,
        reorder them, touch `met` or `confirmed_by`, or demote anything. The
        decision it reads carries no wording (validate_verification), so the
        first of those is impossible by shape rather than by discipline.

        CREATOR IDENTITY IS NOT CONSULTED (founder, 2026-09-17). There is no
        branch here on who authored a row, because there is no such field and
        there must not be one. A condition written by the founder and a
        condition written by Shadow are the same object: something Shadow is
        responsible for evaluating. `m-c973ff4adef0` ended at NEEDS YOU with a
        correct 18-byte file on disk for exactly one reason -- the row had
        been typed by the founder, so nothing was ever allowed to ask how it
        might be checked.
        """
        rows = (decision or {}).get("verification") or []
        if not rows:
            return False
        checks = [dict(c) if isinstance(c, dict) else c
                  for c in (m.get("done_when") or [])]
        eligible = set(self._needs_verification(m))
        changed = []
        for row in rows:
            i = row["index"]
            if i not in eligible:
                continue          # out of range, already probed, or signed
            tier, probe = resolve_verify_tier("verify", row["probe"])
            if tier != "verify":
                continue          # validate_probe refused it; the founder keeps it
            checks[i]["tier"] = "verify"
            checks[i]["probe"] = probe
            changed.append(i)
        if not changed:
            return False
        m["done_when"] = checks
        # Same stale-write discipline as _adopt_criteria: the decider was
        # awaited, the record may have moved, so re-read and write one field.
        # skip_if re-checks THIS method's own precondition -- if the rows it
        # meant to promote are no longer the rows on disk, it writes nothing
        # rather than stamping a snapshot over them.
        want = [(i, checks[i]["check"]) for i in changed]
        self._save_field(
            m, "done_when", checks,
            skip_if=lambda fresh: any(
                i >= len(fresh.get("done_when") or [])
                or (fresh["done_when"][i] or {}).get("check") != text
                for i, text in want))
        shadow_ledger.append("actions", {
            "mission_id": m["id"], "kind": "criteria",
            "summary": "Shadow can verify %d check(s) itself: %s"
                       % (len(changed),
                          "; ".join("#%d %s" % (i, checks[i]["probe"]["kind"])
                                    for i in changed))[:200]})
        return True

    async def _criteria_before_first_contact(self, m):
        """Every mission has a Done When, and Shadow has decided how it will
        check each one, BEFORE the worker hears anything.

        TWO STEPS, AND THE SECOND IS UNIVERSAL (founder, 2026-09-17):

          1. NO CHECKS -> Shadow writes them, and may answer HOW in the same
             reply. A mission without a Done When does not exist; this is the
             step that guarantees it.
          2. CHECKS THAT STILL HAVE NO MECHANICAL TEST -> Shadow is asked how
             it would establish them, whoever wrote them.

        Step 2 cannot learn who authored a row: there is no such field on a
        check and there must not be one. The old single step returned the
        moment the founder had supplied anything, so a founder-typed condition
        could never acquire a probe however mechanical it was -- and a correct
        18-byte file on disk still ended at NEEDS YOU (m-c973ff4adef0).

        WHY BEFORE THE BRIEF AND NOT AT TURN 1. app._worker_checks_block puts
        verify-tier checks into the worker's manifest. Deciding verification
        after the brief would hand the worker one bar and judge it by another.

        THE COST, STATED: a mission whose checks the founder supplied now
        spends ONE decider call at first contact that it did not before. It is
        bounded, it is not a worker turn, and it buys a turn back whenever the
        worker finishes on the brief.

        ASKED ONCE. Both first-contact callers reach here -- provision_target
        and run_mission's turn 0 -- and `verification_asked` is what stops the
        second from paying for the question again.
        """
        if self.decider is None:
            return False
        wrote = False
        if not (m.get("done_when") or []):
            wrote = await self._first_criteria(m, None)
        fresh = self.store.load(m["id"]) or m
        if not self._needs_verification(fresh) or fresh.get("verification_asked"):
            return wrote
        m["verification_asked"] = True
        self._save_field(m, "verification_asked", True)
        return await self._first_verification(m) or wrote

    async def _first_verification(self, m):
        """Ask the decider HOW, for checks that have no answer yet.

        The same decider, the same context and the same validator the ordinary
        turn uses -- no second decision path. Its `instruction` is discarded
        for the reason _first_criteria discards one: the brief is either still
        to be delivered or was delivered by the spawn, and nothing composed
        here may reach the worker.

        Never raises. A decider that fails or answers badly leaves every check
        exactly as it was -- judged by the founder, the safe direction.
        """
        fresh = self.store.load(m["id"]) or m
        try:
            raw = await self.decider(self._decision_context(fresh, None))
        except Exception:             # noqa: BLE001 -- the checks stand
            return False
        decision = validate_decision(raw)
        if decision is None:
            return False
        if not self._adopt_verification(fresh, decision):
            return False
        m["done_when"] = fresh["done_when"]
        m["seq"] = fresh.get("seq", m.get("seq"))
        return True

    async def _first_criteria(self, m, last_response):
        """Shadow's first decision, consulted for its CRITERIA alone.

        The same decider, the same context and the same validator the normal
        turn uses -- no second decision path and no new state. Its
        `instruction` is deliberately discarded: the brief is either still
        to be delivered (first contact) or was delivered by the spawn, and in
        neither case may an instruction composed here reach the worker -- the
        first would pre-empt the brief, the second would be the double-brief
        the briefed branch exists to prevent. The CRITERIA are the one thing
        taken from this decision.

        Never raises. A decider that fails or answers badly leaves the mission
        exactly where it was, and turn 1 asks again.
        """
        try:
            raw = await self.decider(self._decision_context(m, last_response))
        except Exception:             # noqa: BLE001 -- turn 1 will ask again
            return False
        decision = validate_decision(raw)
        wrote = self._adopt_criteria(m, decision)
        # THE SAME ANSWER, SECOND QUESTION. A decision that wrote the bar may
        # also say how Shadow would check it, so a set written here can be
        # probe-backed without step 2 above spending a second call.
        return self._adopt_verification(m, decision) or wrote

    async def _instruction(self, m, last_response):
        """(say_text, decision) for this iteration.

        Turn 0 is the brief and is never a decision: the manifest (or the
        objective) is what opens the conversation. From turn 1 the decider
        reads what the target actually said and composes the next move.

        NOT REACHED on turn 0 of a mission whose delegate was spawned with
        the manifest -- run_mission takes `_next_say` directly there and
        sends nothing, because that turn already happened inside the spawn.

        Returns say_text None when the attempt must not continue -- the
        caller turns that into the existing founder-facing block rather
        than sending anything.
        """
        if m["turns_used"] == 0 or self.decider is None:
            return self._next_say(m), None
        try:
            ctx = self._decision_context(m, last_response)
            raw = await self.decider(ctx)
            # CONSUMED, AND THE MARK IS WRITTEN HERE (fixed 2026-09-16,
            # step 2). It used to rely on "the save this turn already does" --
            # but the loop RE-LOADS the record from disk before the sayer
            # (`m = self.store.load(mid)`, a few lines below the call to this
            # function), so the mutation landed on a dict that was then
            # thrown away. The mark never reached the file, every aside stayed
            # unseen for the life of the mission, and one sentence the founder
            # said once steered every later turn -- the exact repetition the
            # `seen` flag exists to stop. Pre-dates the talk channel; it made
            # the typed one repeat too.
            #
            # Marking AFTER the decider returns is still deliberate: a turn
            # that dies before this leaves the asides unseen and they go
            # again next turn, which is the safe direction to fail.
            #
            # THE WRITE IS GUARDED FOR THE SAME REASON. A founder line that
            # landed while the decider was thinking makes this a stale write;
            # refusing it costs one repeat of an aside on the next turn, and
            # must never cost the turn itself. Nothing else about the record
            # is being written here.
            if ctx.get("founder_says"):
                for said in (m.get("founder_says") or []):
                    said["seen"] = True
                try:
                    self.store.save(m)
                except Exception:   # noqa: BLE001 -- re-read, never fail
                    pass
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

    async def _run_judges(self, m):
        """Settle every unmet `judge` row against the EVIDENCE, and stamp it.

        RUNS BEFORE EVERY EVALUATION, NOT ONCE. A judgement is a reading of
        the work as it stands this turn; the work changes every turn, so a
        verdict cached from turn 2 would be a statement about code that no
        longer exists. Re-judging is the correct cost and it is bounded by
        the number of unmet judge rows, which MAX_DECIDER_CHECKS caps at 6.

        NEVER RAISES, and a judge that fails leaves the row EXACTLY as it
        found it. That matters more here than anywhere else in this file: a
        failed judgement must not read as `unmet` (which would drive a worker
        at a check that may already hold) and must certainly not read as
        `met`. An unstamped row is unmet-by-absence, the mission keeps
        driving, and the founder is asked at the end of the road exactly as
        they were before this tier existed.

        `cannot_tell` IS THE ROUTE BACK TO THE FOUNDER, and it is the reason
        shadow_protocol could safely stop demoting everything. The row is
        re-tiered to `founder_confirm` on the spot, keeping its wording and
        carrying the judge's reason so the card can say why it came back.
        """
        if self.judge is None:
            return False
        checks = [dict(c) if isinstance(c, dict) else c
                  for c in (m.get("done_when") or [])]
        pending = [i for i, c in enumerate(checks)
                   if isinstance(c, dict) and c.get("tier") == "judge"
                   and not c.get("met")]
        if not pending:
            return False
        evidence = self._judge_evidence(m)
        outcome = m.get("objective") or ""
        changed = False
        for i in pending:
            try:
                verdict = await self.judge(checks[i].get("check") or "",
                                           evidence, outcome)
            except Exception as exc:   # noqa: BLE001 -- row untouched, see doc
                shadow_ledger.append("actions", {
                    "mission_id": m["id"], "kind": "judge",
                    "summary": "#%d judge failed: %s" % (i, str(exc)[:120])})
                continue
            if verdict is None:
                continue               # said nothing; says nothing
            state = getattr(verdict, "state", None)
            reason = getattr(verdict, "reason", "") or ""
            if state not in shadow_judge.VERDICTS:
                continue
            checks[i]["judged"] = {"state": state, "reason": reason[:400],
                                   "at": _now()}
            if state == "met":
                checks[i]["met"] = True
            elif state == "cannot_tell":
                # BACK TO THE FOUNDER, WORDING UNTOUCHED. This is the one
                # place in the new design that re-tiers toward a signature,
                # and it is the honest one: Shadow looked and could not tell.
                checks[i]["tier"] = "founder_confirm"
                checks[i]["met"] = False
            else:
                checks[i]["met"] = False
            changed = True
            shadow_ledger.append("actions", {
                "mission_id": m["id"], "kind": "judge",
                "summary": "#%d %s: %s" % (i, state, reason[:160])})
        if not changed:
            return False
        m["done_when"] = checks
        # Same stale-write discipline as _apply_verification: the judge was
        # awaited, the record may have moved underneath, so re-read and write
        # one field rather than stamping a snapshot over it.
        want = [(i, checks[i].get("check")) for i in pending]
        self._save_field(
            m, "done_when", checks,
            skip_if=lambda fresh: any(
                i >= len(fresh.get("done_when") or [])
                or (fresh["done_when"][i] or {}).get("check") != text
                for i, text in want))
        return True

    def _judge_evidence(self, m):
        """What the judge is shown. THE TRANSCRIPT IS NOT IN IT.

        The diff plus the reason lines of the probes that have already run --
        so a judge asked "did anything else break" can see that the suite was
        run and what it printed. Never the worker's prose; see shadow_judge's
        header for why that exclusion is the design and not an oversight.
        """
        root = self.probe_root
        if root is None:
            root = shadow_probe.default_root()
        lines = []
        for c in (m.get("done_when") or []):
            if not isinstance(c, dict) or c.get("tier") != "verify":
                continue
            probe = c.get("probe")
            if not probe:
                continue
            try:
                res = shadow_probe.run(probe, root)
            except Exception:          # noqa: BLE001 -- no line, not fatal
                continue
            lines.append("%s -> %s (%s)" % (c.get("check"),
                                            "MET" if res.met else "NOT MET",
                                            res.reason))
        try:
            return shadow_judge.evidence_for(root, lines)
        except Exception:              # noqa: BLE001 -- no evidence, not fatal
            return ""

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
    """S55/S56: capped admission with FIFO queue, promotion, and the
    disambiguation helper. One mission per target session is enforced at
    admission -- amend, never spawn a duplicate.

    THE CAP IS READ, NOT CAPTURED. `max_running` is a property that resolves
    to the founder's setting on every read unless a caller passed an explicit
    number (tests do, to build a two-slot world). Binding it in __init__ --
    which is what the old `max_running=MAX_RUNNING` default did -- would mean
    a scheduler built before a settings change kept enforcing the old cap,
    and the runner holds schedulers across promotions.
    """

    def __init__(self, store, max_running=None):
        self.store = store
        #: None means "ask the setting each time"; a number pins it
        self._max_running = max_running

    @property
    def max_running(self):
        return max_running() if self._max_running is None \
            else self._max_running

    @max_running.setter
    def max_running(self, value):
        self._max_running = value

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
        # ALREADY WAITING IS NOT A NEW DECISION, and this return is what
        # stops "Start now" from DESTROYING the task it was pressed on.
        #
        # THE MEASURED FAILURE. A queued row draws a Start now button
        # (shadowPlaneHtml). Pressed while the cap is still full, it reached
        # here in state `queued` and fell through to the transition below --
        # queued -> queued, which is not in TRANSITIONS and so raises. The
        # raise lands in start_mission_async's error handler, whose whole
        # job is to rescue a start that never got off the ground, and that
        # handler guards on exactly `("brief_confirm", "queued")` -> it
        # transitioned the mission to `failed`. So the one control a queued
        # row offers took a task that was waiting its turn and marked it
        # failed, with a note claiming a provisioning error that never
        # happened.
        #
        # IDEMPOTENT, EXACTLY LIKE THE `running` GUARD ABOVE. Nothing is
        # written, the FIFO position (created_ns) is untouched so pressing
        # Start now cannot jump the queue either, and the mission is
        # promoted by the ordinary path when a slot frees.
        if m["state"] == "queued":
            return m
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
            # autonomy_suggest / autonomy_top_tier are founder decisions in
            # exactly the sense this list means: the mission is stopped and
            # only a yes moves it. autonomy_hold (L0) is NOT here -- nothing
            # the founder can say in a disambiguation prompt releases it,
            # because the answer is a settings change, not a yes.
            if m.get("pause_reason") in ("founder_confirm", "floor_confirm",
                                         "autonomy_suggest",
                                         "autonomy_top_tier"):
                out.append({"mission_id": m["id"],
                            "objective": m["objective"][:120],
                            "reason": m["pause_reason"],
                            "version": m["version"]})
        return out


def mint_approval(m, reason, say_text):
    """A one-use approval object for ONE held say: bound to the task, its
    version, its turn and the sha256 of the exact string. Approving it
    releases that string and nothing else; a Retry, an amend or a new turn
    makes it stale by construction."""
    return {
        "id": "ap-" + uuid.uuid4().hex[:12],
        "reason": reason,
        "version": m.get("version"),
        "turn": m.get("turns_used"),
        "say_sha256": hashlib.sha256((say_text or "").encode("utf-8")).hexdigest(),
        "used": False,
        "created_at": _now(),
    }


def approve_held_say(store, mid, approval_id):
    """The founder approves the held say named by `approval_id`.

    Every refusal is a ValueError with the reason: nothing waiting, wrong
    id, already used, stale version, hash mismatch. On success the approval
    is marked used and `approved_say` carries the exact string for the loop
    to send once (run_mission clears it as it leaves). The state is NOT
    moved here: the route owns the cap check and the launch."""
    m = store.load(mid)
    if m is None:
        raise ValueError("no mission %s" % mid)
    ap = m.get("approval")
    if not ap or not m.get("pending_say"):
        raise ValueError("nothing is waiting for approval")
    if m["state"] != "paused":
        raise ValueError("task is %s, not waiting" % m["state"])
    if not approval_id or approval_id != ap.get("id"):
        raise ValueError("approval id does not match")
    if ap.get("used"):
        raise ValueError("approval already used")
    if ap.get("version") != m.get("version"):
        raise ValueError("approval is stale: the task changed since it asked")
    digest = hashlib.sha256(m["pending_say"].encode("utf-8")).hexdigest()
    if digest != ap.get("say_sha256"):
        raise ValueError("approval does not match the pending say")
    ap["used"] = True
    ap["used_at"] = _now()
    m["approved_say"] = m["pending_say"]
    store.save(m)
    shadow_ledger.append("actions", {
        "mission_id": mid, "kind": "approval",
        "summary": "approved %s (%s) at turn %s"
                   % (ap["id"], ap.get("reason"), ap.get("turn"))})
    return m


def emit_mission_feed(mission, kind, why_now):
    """S57: mission events that need the founder become feed items. Dedupe
    key = mission + state + version, so an amend re-surfaces exactly once.
    ONE CARD PER TASK (2026-09-16): an accepted row retires the task's
    earlier open rows, so Now shows the latest state, not the history."""
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
    ok, problems = shadow_feed.emit(item)
    if ok:
        shadow_feed.retire(mission_id=mission["id"],
                           keep_item_id=item["item_id"], producer="shadow")
    return ok, problems
