#!/usr/bin/env python3
"""THE INTERACTIVE FORWARDING LANE (founder, 2026-09-21).

WHAT WAS WRONG. The founder talks to a task's Shadow in one box. Every line
landed on the mission's `founder_says` and stopped there: `_decision_context`
handed it to the decider at the top of run_mission's NEXT iteration, the
decider composed an instruction from it, and only then did the worker hear
anything. So "actually make it 20 lines" waited on a decider LLM call that
had not been scheduled yet, behind a worker turn measured at 62-273s. The
founder experienced this as Shadow receiving a message and the worker never
being told.

WHAT THIS LANE IS. A second cursor over the SAME list, with a classifier in
front of it. Shadow still answers the founder immediately, still records
every line for the decider, and still composes every INSTRUCTION itself. What
changes is that a founder line judged capable of changing the work is also
put on the worker's own queue verbatim, right now, instead of waiting to be
re-authored on a future turn.

THE INVARIANT IT KEEPS. `test_shadow_v4_unified_input` pinned the rule as
"EVERYTHING THE FOUNDER SAID REACHES THE DECIDER, AND ONLY WHAT THE DECIDER
COMPOSES REACHES THE WORKER". The first clause is untouched -- `seen` is not
read or written here, and no row is withheld from `_decision_context`. The
second is narrowed, deliberately and by the founder's direction, to what it
was protecting: only the decider composes an INSTRUCTION. A forwarded line is
not an instruction. It is the founder's own sentence, tagged as the founder's
(shadow_egress.founder_tag), carried verbatim, and the worker is told in as
many words that it is information rather than a new task. Shadow remains the
only thing that can tell the worker what to DO.

WHY THERE IS NO NEW STORE. The mission record is already durable, already
atomic, already recovered on boot, and `founder_says` is already the
append-only log of the founder's raw words in chronological order. A queue
needs exactly two things this list does not already have -- a per-row
lifecycle and an idempotency key -- and both are one field. So `fwd` is added
to the row, `seen` is left alone, and list order IS the FIFO order. No
second store to keep consistent, no cursor that can disagree with the
chronology, and restart recovery is a scan of a file that is already read.

  fwd absent   this row predates the lane, or classification never ran.
               Not delivered: a verdict is reached once, at arrival, and a
               row that never got one is never guessed at later.
  "skip"       Shadow-only. Answered in the chat, never sent to the worker.
  "queued"     worker-relevant, durable, not yet on any TurnQueue.
  "dispatched" accepted by the worker's TurnQueue in THIS process.
  "consumed"   the pump actually sent it into the worker session.

WHY "dispatched" IS RE-DELIVERED ON BOOT AND "consumed" IS NOT. TurnQueue's
dedupe set lives in memory, for the life of one runtime (session_runtime.py
S25). A row that reached `dispatched` and then lost its process was never
sent -- the queue it sat in no longer exists -- so recovery must re-queue it
or the founder's correction is silently lost. A row that reached `consumed`
was written into the transcript, which survives, so re-queueing it would be
the duplicate delivery this lane is required not to produce. That is the
whole difference between the two states, and it is why there are two.

ORDERING IS BY CONSTRUCTION, NOT BY LOCK. Rows are appended in arrival order
and dispatched in list order into the SHADOW lane of TurnQueue, which is FIFO
and which the pump drains single-threaded. The operator lane is deliberately
NOT used: it outranks the shadow lane, so a founder line placed there would
overtake a say already queued for this turn, and the engine's boundary waiter
-- which cannot tell one turn's boundary from another's -- would consume the
founder turn's boundary as if it were its say's, read the wrong response and
spend a turn of budget on it. The founder's own constraint ("do not create an
operator lane where the user's message bypasses Shadow's authority") and the
concurrency requirement happen to have the same answer.
"""
import re

import shadow_egress

#: Row lifecycle. See the module docstring for why these four and not two.
FWD_SKIP = "skip"
FWD_QUEUED = "queued"
FWD_DISPATCHED = "dispatched"
FWD_CONSUMED = "consumed"

#: Rows that recovery must re-offer to a fresh TurnQueue.
FWD_PENDING = (FWD_QUEUED, FWD_DISPATCHED)

#: What the worker is told the forwarded block IS. Carried on every forward,
#: because the worker has no other way to tell a founder line from an
#: instruction: both arrive as user turns in the same transcript. The last
#: sentence is the load-bearing one -- without it a worker reads any founder
#: sentence as a command and abandons what Shadow told it to do.
FORWARD_PREAMBLE = (
    "The founder said this to you directly, while you were working. These "
    "are their own words, verbatim and in the order they sent them. Treat "
    "them as information about the task you already have -- a constraint, a "
    "correction, a clarification or an authorization. This is NOT a new "
    "task, and it does not replace the objective or the last instruction "
    "Shadow gave you. Carry it into the work you are already doing.")

#: A single meta sentence: the founder asking Shadow about Shadow, the task's
#: status, or what just happened. Anchored at the sentence start and matched
#: per sentence, never against the whole message -- see _is_meta_only.
_META_ASK = re.compile(r"""^\s*(?:shadow\s*[,:]?\s*)?(?:
      what(?:\s|'|’|s\b)
    | how\s+(?:many|much|long|far|is|are|was|did|do|does)\b
    | why\b
    | who\b
    | when\s+(?:will|did|do|does|is|are)\b
    | where\s+are\s+we\b
    | which\s+turn\b
    | status\b
    | progress\b
    | explain\b
    | tell\s+me\s+(?:what|how|why|about|more)\b
    | show\s+me\s+(?:what|the\s+status|progress)\b
    | are\s+you\b
    | did\s+you\b
    | do\s+you\b
    | have\s+you\b
    | is\s+(?:it|this|that|the\s+worker)\b
    | any\s+(?:update|progress|news)\b
)""", re.I | re.X)

#: Sentence split for _is_meta_only. Deliberately crude: it only has to be
#: right enough to notice that a message contains something OTHER than a
#: question, and every failure mode of a crude split lands on "forward",
#: which is the safe direction.
_SENTENCE = re.compile(r"[.!?\n]+")


def _sentences(text):
    return [s.strip() for s in _SENTENCE.split(str(text or "")) if s.strip()]


def _is_meta_only(text):
    """True when EVERY sentence is Shadow-meta -- the fallback classifier.

    NOT THE PRIMARY, AND THAT IS THE POINT. Shadow classifies its own turn
    (see classify below); this runs only when that verdict is missing or
    unparseable, which is a model fault rather than a founder one. The
    founder's rule for the ambiguous case is "forward rather than silently
    dropping it", so the default here is FORWARD and the only way to be
    dropped is to be unanimously, recognizably a question about Shadow.

    PER SENTENCE, NEVER WHOLE-MESSAGE. "What's the status? Also use official
    sources only." is two sentences and the second one changes the work. A
    whole-message match would drop both; requiring EVERY sentence to be meta
    forwards the message, which is the conservative answer and the correct
    one. It is also why a crude sentence split is acceptable here: under-
    splitting yields one non-matching blob, and a non-match forwards.
    """
    parts = _sentences(text)
    if not parts:
        return True                     # nothing to forward is not a forward
    return all(_META_ASK.match(p) for p in parts)


def classify(text, blocks=None):
    """Decide ONCE, at arrival, whether this founder line reaches the worker.

    SHADOW DECIDES, NOT THIS FUNCTION. The founder's constraint was explicit:
    integrate with the existing supervisory decision rather than stand up a
    second authority. Shadow already takes one LLM turn on every founder
    message (shadow_task_chat.talk), already returns structured blocks from
    it (shadow_protocol.parse_reply), and is already the supervisor. So the
    verdict rides on that turn as a `forward` fence and costs nothing extra:
    no second model call, no second prompt, and nothing that can disagree
    with Shadow about what Shadow meant.

    THE FALLBACK IS A FLOOR, NOT AN OPINION. When the fence is missing or
    malformed -- an older Shadow, a truncated reply, a model that ignored the
    instruction -- _is_meta_only answers, defaulting to forward. Without it a
    single dropped fence would silently swallow "actually make it 20 lines",
    and silent loss is the exact failure this lane exists to end. With it the
    worst case is one extra forwarded question, which costs part of a turn
    that was being sent anyway and changes nothing about the work.
    """
    spec = (blocks or {}).get("forward")
    if isinstance(spec, dict) and isinstance(spec.get("worker"), bool):
        return spec["worker"]
    return not _is_meta_only(text)


def verdict(text, blocks=None):
    """The `fwd` value a freshly appended row should carry."""
    return FWD_QUEUED if classify(text, blocks) else FWD_SKIP


def pending(mission, revive=False):
    """[(index, row)] awaiting the worker, in FIFO order.

    Ordering is the list's own, which is arrival order. There is no sort key
    here on purpose: a sort key would be a second opinion about chronology,
    and the append-only list already holds the only one that matters.

    `revive` IS THE RESTART SWITCH, AND LEAVING IT OFF IS LOAD-BEARING. A
    `dispatched` row is on a TurnQueue that has not drained yet. Re-offering
    it during ordinary operation coalesces it into the NEXT payload, which
    has different indices, which computes a different dedupe_key, which
    TurnQueue therefore accepts -- and the founder's line is delivered twice.
    (Caught by test_ordering_holds_under_rapid_interleaved_submission, which
    failed with rows 1,2,4,5 riding along inside the payload for row 7.)

    So the live path takes `queued` only. `revive=True` is passed by exactly
    one caller -- shadow_runner.flush_forwards, from _launch -- where the
    queue those rows were accepted by is gone with its process, so the only
    way they are ever sent is to offer them again.
    """
    want = FWD_PENDING if revive else (FWD_QUEUED,)
    rows = (mission or {}).get("founder_says") or []
    return [(i, r) for i, r in enumerate(rows)
            if isinstance(r, dict) and r.get("fwd") in want]


def coalesce(rows):
    """Several founder lines -> ONE worker turn, order and meaning intact.

    A JOIN, NOT A SUMMARY. The lines are concatenated newline-separated in
    list order and nothing else happens to them: no dedupe, no merge, no
    rewrite, and no dropping of a line that a later line contradicts. That
    last one is the whole reason this is not cleverer -- "use official
    sources" followed by "actually, any source" is a CORRECTION, and a
    coalescer that resolved it would be deciding the task. The worker reads
    both, in order, and applies the later one, which is exactly what it would
    have done had they arrived as two separate turns.

    WHY COALESCE AT ALL. Each forward costs a real worker turn: the pump
    sends one frame per payload and demuxes it to completion. Three rapid
    corrections would be three model calls on one thought. One frame carries
    all three for the price of one, and the ordering guarantee is strictly
    easier to keep inside a single frame than across three.
    """
    return "\n".join(str(r.get("text") or "").strip()
                     for _i, r in rows
                     if str(r.get("text") or "").strip())


def compose(mission_id, rows):
    """The exact bytes the worker receives: tag, preamble, founder's lines."""
    body = coalesce(rows)
    if not body:
        return ""
    return "%s %s\n\n%s" % (shadow_egress.founder_tag(mission_id),
                            FORWARD_PREAMBLE, body)


def dedupe_key(mission_id, indices):
    """IDENTITY-SHAPED, per TurnQueue's rule: never the message text.

    The indices ARE the identity -- `founder_says` is append-only, so row 4
    is row 4 for the life of the mission and a retry of the same forward
    computes the same key. Two different coalesces over overlapping rows get
    different keys, which is correct: they are different payloads, and the
    per-row `fwd` state is what stops a row being sent inside both. Text
    would have been wrong for the reason TurnQueue's own docstring gives,
    and doubly so here, where a founder repeating "yes" twice means it twice.
    """
    return "%s:fwd:%s" % (mission_id, ",".join(str(i) for i in indices))


def mark(mission, indices, state):
    """Move rows to `state` in place. Returns True when anything changed."""
    rows = (mission or {}).get("founder_says") or []
    hit = False
    for i in indices:
        if 0 <= i < len(rows) and isinstance(rows[i], dict):
            if rows[i].get("fwd") != state:
                rows[i]["fwd"] = state
                hit = True
    return hit


def deliverable(mission, revive=False):
    """(indices, payload) for the one coalesced turn this mission owes the
    worker, or (None, None) when it owes nothing.

    PURE. It reads a record and returns bytes; it touches no queue, no
    runtime and no store, which is what lets every ordering and coalescing
    guarantee be tested without a live worker anywhere in the picture.
    """
    rows = pending(mission, revive=revive)
    if not rows:
        return None, None
    payload = compose(mission.get("id"), rows)
    if not payload:
        return None, None
    return [i for i, _r in rows], payload
