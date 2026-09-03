"""switch.py -- plan a mid-chat provider switch, then record it.

PLANNER, NOT SPAWNER. Nothing here starts a process or opens a socket, for the
same reason build_agent_args was split out of the socket loop (app.py:319):
the decisions that matter -- is a switch needed, what exactly gets sent, which
tier, does the payload survive its own guards -- must be testable without a
subprocess. ws_chat calls plan() before it spawns and confirm() after the
transport hands back a native session id.

    plan(sutra_id, target)      -> what to send, how, or why not to
    confirm(sutra_id, ..., id)  -> append the segment, once it really exists

WHY confirm() IS SEPARATE
A segment records a session that EXISTS. Appending it at plan time would write
a from_turn pointing at a session the transport may never create (the binary is
missing, session/new errors, the process dies on spawn), and the next reconnect
would resume a thread that was never born. So the record is written only once
the transport has returned an id -- which both transports do, in the same
position of the same tuple: demux_turn for Claude and prompt_turn for DeepSeek
(app.py:2083 and app.py:2090).

THE TWO TRANSPORTS, AND WHAT SEEDING MEANS ON EACH
Neither has "start fresh but behave as though this happened", so seeding is
expressed as the absence of resumption plus a first message that carries the
recording:

    claude    build_agent_args(..., session_id=None, stream_input=True) and
              the replay delivered as a stdin frame. No --resume: resuming
              would attach to the OLD thread, which is the thing being left.
    deepseek  AcpRuntime.new_session(..., session_id=None) -- so it takes the
              session/new branch rather than session/load (acp_runtime.py:488)
              -- then prompt_turn(payload).

STDIN, NOT ARGV, AND THIS IS NOT A STYLE PREFERENCE
ARG_MAX on this machine is 1,048,576 bytes and a 50-turn Claude replay is
~1.09 MB of text (transcript_ir.stats: 21,871 chars per user turn). Passing
that as a positional argument fails with E2BIG at exec time -- for exactly the
scenario this feature was requested for. ws_chat already passes
stream_input=True on both spawn paths, so the live path is safe; but
build_agent_args DEFAULTS to argv delivery, so a future caller that forgets is
one keystroke from an unexplainable exec failure on long chats and a working
one on short chats. plan() therefore states the delivery mode as part of the
plan and argv_would_fail() answers the question directly.

Reads:  the chat store and both providers' transcript trees (via transcript_ir)
Writes: one chat record, in confirm() only.
"""
import os

import budget as budget_mod
import chat_store
import replay
import transcript_ir

#: Passed as `budget_chars` to mean "no ceiling at all". A plain None cannot
#: mean that, because None is what a caller who FORGOT to pass one sends, and
#: unbounded-by-omission is how a payload gets built past the model's window
#: and rejected at the API. So None derives the real budget and this sentinel
#: is the explicit opt-out, used by tests and by callers measuring raw size.
UNBOUNDED = "unbounded"

#: Reason codes. Strings rather than exceptions because every one of these is a
#: thing the UI has to SAY -- "no switch happened, and here is why" is the whole
#: point of the feature's honesty contract, and an exception would push that
#: text into a traceback nobody shows an operator.
NOT_NEEDED = "not-needed"
NO_SOURCE = "no-source-session"
NO_TRANSCRIPT = "source-transcript-unreadable"
FENCE_BROKEN = "fence-integrity-failed"
OVER_BUDGET = "over-context-budget"
UNKNOWN_TARGET = "unknown-target-provider"


def _arg_max():
    try:
        return int(os.sysconf("SC_ARG_MAX"))
    except (ValueError, OSError, AttributeError):
        return 1048576   # POSIX minimum on the platforms this ships to


#: The exec ceiling is shared by argv AND the environment, and the environment
#: on a GUI launch is not small. Two thirds leaves room for it rather than
#: discovering the boundary as an intermittent E2BIG on the longest chats.
ARGV_SAFETY_FRACTION = 0.66


def argv_would_fail(payload_chars):
    """True when delivering this payload as a positional argument is unsafe.

    Answered as a function rather than left implicit because the failure it
    predicts is silent, late, and size-dependent: short chats work, long ones
    die at exec with no frame ever written to the socket.
    """
    return payload_chars > int(_arg_max() * ARGV_SAFETY_FRACTION)


def _transport_for(target):
    """How to seed one provider, in terms the caller already speaks."""
    if target == "claude":
        return {
            "kind": "claude-cli",
            "builder": "build_agent_args",
            "session_id": None,      # NOT --resume: the old thread is what we are leaving
            "stream_input": True,    # see the module header on ARG_MAX
            "delivery": "stdin-frame",
        }
    if target == "deepseek":
        return {
            "kind": "acp",
            "builder": "build_acp_args",
            "new_session_session_id": None,   # forces session/new, not session/load
            "then": "prompt_turn",
            "delivery": "session/prompt",
        }
    return None


def _refuse(code, detail, **extra):
    out = {"switch": False, "reason": code, "detail": detail}
    out.update(extra)
    return out


def plan(sutra_id, target, next_message=None, budget_chars=None,
         include_reasoning=False, ir_loader=None, model=None):
    """What to send to `target` so it can continue this chat, or why not to.

    `budget_chars` is the ceiling for the whole payload. Left unset it is
    DERIVED from the selected model's context window via budget.for_target --
    Haiku 4.5 is 200K where its siblings are 1M, so the ceiling is per-model
    and this module never encodes one itself. Pass switch.UNBOUNDED to opt out
    deliberately; passing nothing must not mean "no limit", because that is
    what a forgetful caller sends and it is how a payload gets built past the
    window and rejected at the API.

    `ir_loader` exists for tests and for the day a transcript comes from
    somewhere other than the two on-disk trees. Defaults to transcript_ir.load.
    """
    if _transport_for(target) is None:
        return _refuse(UNKNOWN_TARGET,
                       "no seeding path for provider %r" % (target,))

    rec = chat_store.load(sutra_id)
    if rec is None:
        return _refuse(NO_SOURCE, "no chat record %r" % (sutra_id,))

    seg = chat_store.active_segment(rec)
    if seg is None:
        # Nothing has been sent yet, so there is no conversation to carry and
        # no switch to perform -- the chat simply starts on `target`.
        return _refuse(NOT_NEEDED, "chat has no provider session yet",
                       start_fresh=True)
    if seg.get("provider") == target:
        return _refuse(NOT_NEEDED, "chat is already running on %r" % (target,))

    # THE WHOLE CHAT, not just the session being left.
    #
    # Reading only the previous session was the original design and it failed
    # two ways in live testing (2026-09-02). Everything older than the last hop
    # existed only INSIDE that session's replay turn, so each hop wrapped the
    # previous recording whole -- 2,936 then 5,644 then 9,928 characters for a
    # four-turn conversation, with 2 then 4 then 6 fence markers, most of them
    # dead. And a provider that resumes its own session (Claude does; two
    # segments shared one native id) received its history twice.
    #
    # So the source is every DISTINCT native session this chat has used, each
    # contributing its own turns with prior replays stripped, merged by
    # timestamp. Distinct by session id because a resumed session appears in
    # more than one segment and must contribute once.
    load = ir_loader or transcript_ir.load
    seen, parts = set(), []
    for h in rec.get("provider_history") or []:
        nid = h.get("native_id")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        parts.append(load(nid))
    ir = transcript_ir.combine(parts, provider=seg.get("provider"))
    if not ir or not (ir.get("turns") or []):
        # The source session's file is gone or unreadable. Refusing beats
        # seeding an empty recording: an empty replay looks to the receiving
        # model like a conversation that never happened, and it would answer
        # turn 51 as if it were turn 1.
        return _refuse(NO_TRANSCRIPT,
                       "cannot read the transcript for %s session %r"
                       % (seg.get("provider"), seg.get("native_id")),
                       source=seg.get("provider"),
                       source_session=seg.get("native_id"))

    if budget_chars is UNBOUNDED:
        budget_info, budget_chars = None, None
    elif budget_chars is None:
        budget_info = budget_mod.for_target(target, model=model)
        budget_chars = budget_info["budget_chars"]
    else:
        budget_info = None

    tier = 1
    out = replay.render(ir, target, next_message=next_message,
                        include_tool_io=True,
                        include_reasoning=include_reasoning)
    if budget_chars and out["chars"] > budget_chars:
        # Tier 2: stop mailing copies of files the target can read itself.
        # Still verbatim -- nothing is condensed, and the prompt says what was
        # left out and that the work was still done.
        tier = 2
        out = replay.render(ir, target, next_message=next_message,
                            include_tool_io=False,
                            include_reasoning=include_reasoning)
        if out["chars"] > budget_chars:
            return _refuse(
                OVER_BUDGET,
                "this chat needs %d characters to carry over even with tool "
                "activity left out, and the budget is %d. Nothing was sent."
                % (out["chars"], budget_chars),
                source=seg.get("provider"), target=target,
                chars=out["chars"], budget_chars=budget_chars, tier=2,
                budget=budget_info)

    if not replay.fence_is_intact(out):
        # The nonce appeared inside the transcript. Astronomically unlikely and
        # therefore exactly the kind of thing that must fail closed rather than
        # be assumed away: a closed fence mid-recording would let quoted text
        # speak with the prompt's authority.
        return _refuse(FENCE_BROKEN,
                       "the transcript contains this payload's own fence "
                       "marker, so the data/instruction boundary cannot be "
                       "guaranteed. Nothing was sent.",
                       source=seg.get("provider"), target=target)

    return {
        "switch": True,
        "sutra_id": rec["sutra_id"],
        "source": seg.get("provider"),
        "source_session": seg.get("native_id"),
        "target": target,
        "from_turn": chat_store.turn_count(rec),
        "tier": tier,
        "payload": out["prompt"],
        "nonce": out["nonce"],
        "transport": _transport_for(target),
        # Audit surface -- piece 6's egress log and the UI's switch marker read
        # these rather than recomputing them from the payload.
        "chars": out["chars"],
        "turns": out["turns"],
        "user_turns": out["user_turns"],
        "included": out["included"],
        "dropped": out["dropped"],
        "dropped_chars": out["dropped_chars"],
        "argv_unsafe": argv_would_fail(out["chars"]),
        "arg_max": _arg_max(),
        "budget_chars": budget_chars,
        # The derivation, when this call computed it. The operator's question
        # after a tier-2 switch is "why did it drop my tool output", and the
        # answer (which window, declared or assumed, and what was reserved) is
        # in here rather than needing to be recomputed by the UI.
        "budget": budget_info,
    }


def confirm(sutra_id, target, native_id):
    """Record the segment now that the target's session actually exists.

    Returns the updated record, or None when the chat is gone. Idempotent for
    the same (target, native_id) because chat_store.begin_segment is -- a
    browser reconnect re-confirming the live session must not split one run
    into two segments.
    """
    rec = chat_store.load(sutra_id)
    if rec is None:
        return None
    return chat_store.begin_segment(rec, target, native_id)


def describe(result):
    """One operator-facing line for a plan result.

    Every refusal path already carries its own `detail`; this exists so the UI
    has a single place to render both outcomes and cannot accidentally show a
    switch as having happened when it did not.
    """
    if not result:
        return "no switch"
    if not result.get("switch"):
        return "no switch (%s): %s" % (result.get("reason"), result.get("detail"))
    return ("switched %s -> %s at turn %d, tier %d, %d characters carried over"
            % (result.get("source"), result.get("target"),
               result.get("from_turn", 0), result.get("tier", 1),
               result.get("chars", 0)))
