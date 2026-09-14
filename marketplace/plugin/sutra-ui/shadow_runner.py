"""Mounts the mission engine in the app process (GAP-AUDIT rows 2-3).

The engine (mission_engine.py) was fully tested against mocks; this module
is the missing binding: a per-mission asyncio task whose sayer is the SAME
validated-say function the HTTP endpoint uses, whose waiter listens to the
runtime's internal _turn_boundary frames, and whose reader is the existing
transcript reader. Plus the watcher: one observer per runtime that turns
error signals into rescue feed items and the dot-badge count.
"""
import asyncio
import json
import os
import re
import subprocess
import time
import weakref

import mission_engine
import session_reader
import session_runtime
import shadow_egress
import shadow_feed
import shadow_ledger

#: mission_id -> asyncio.Task (running loops)
RUNNING = {}
#: session_id -> asyncio.Queue of boundary frames (fed by _attach_observer)
_BOUNDARIES = {}
#: Runtimes already carrying our observer.
#:
#: A WeakSet OF THE RUNTIMES, not a set of id(rt). It was the latter, and
#: CPython reuses addresses: 2998 of 3000 freshly allocated SessionRuntime
#: objects landed on a previously-seen id() in a straight measurement. A
#: recycled address made the guard below return EARLY for a brand-new
#: runtime, so nothing was subscribed -- no _turn_boundary reached the
#: waiters, no token reached _RECENT_TEXT, no frame reached _LAST_FRAME_TS.
#: The mission then waited, saw total silence, and died at STALL_SECS
#: blaming the worker for Shadow's own bookkeeping.
#:
#: The set was also never discarded from, so it grew for the life of the
#: process. A WeakSet fixes both at once: membership is identity-based
#: exactly as before (SessionRuntime defines no __eq__/__hash__), an entry
#: disappears when the runtime is collected, and a replacement runtime is
#: therefore always a miss. `.clear()` still works, which is what the
#: existing suites call in setUp.
_OBSERVED = weakref.WeakSet()
#: session ids whose runtime WE spawned (delegates) -- ours to clean up
DELEGATES = {}
#: session ids of FOUNDER-OWNED chats Shadow has attached a runtime to.
#: DELIBERATELY NOT `DELEGATES`, and the distinction is load-bearing twice:
#:   * the terminal-mission branch reaps DELEGATES -- an attached chat is the
#:     founder's, and a finished goal must never kill the process behind it;
#:   * app._shadow_auto_watch() skips ids in DELEGATES ("Shadow's own hands"),
#:     so filing an attached chat there would silently drop the founder's own
#:     conversation out of the Watching list.
#: Its one reaper is reap_attached(), called when the founder takes the wheel.
ATTACHED = {}
#: Session ids Shadow OWNED when a previous process died -- rebuilt at boot by
#: recover_on_boot() from missions on disk, never written anywhere else.
#:
#: NOT a second registry and not a new entity: it holds no runtime, no chat and
#: no state of its own, only ids whose Claude process THIS process cannot see
#: and cannot reap. `spawn()` uses start_new_session=True, so a delegate
#: survives the app that started it; after a restart DELEGATES is empty while
#: that process may still be appending to the transcript. Without this set the
#: send guard would pass, ws_chat would `--resume` the same session, and the
#: two-writer case this slice exists to prevent would be reachable by restart.
#:
#: Fences, does not fix: the orphan is not killed here (see shutdown()).
_ORPHANED = set()

#: session_id -> os pid of the delegate process THIS app spawned for it.
#: In-memory and deliberately so: it is a cache for the stamp below, not the
#: record. The durable copy is `delegate_pid` on the mission file, because
#: that is the only thing that survives the restart it exists to answer.
DELEGATE_PIDS = {}


def delegate_alive(pid, session_id=None):
    """Is THAT delegate process still running?

    THE QUESTION recover_on_boot could not ask (founder, 2026-09-15). A
    delegate is spawned with process_group=0, so its Claude process outlives
    the app; Electron SIGKILLs the uvicorn child on quit, so shutdown() often
    never reaps it. After a restart the runtime handle is gone -- the pipes
    died with the parent and cannot be re-acquired by anyone -- so the only
    way back into that conversation is `claude --resume <sid>`, which starts
    a SECOND process on the same transcript. That is safe if and only if the
    first one is dead, and nothing on disk could say whether it was. The
    fence existed because the answer was unknown, not because it was "yes".

    TWO CHECKS, AND THE SECOND IS WHAT MAKES A PID SAFE TO TRUST. `kill(pid,
    0)` alone is not enough: pids are recycled, so a dead delegate's number
    can belong to something else entirely and read as "alive", which fences
    a mission forever. When the pid IS live we also require its command line
    to mention the session id -- our delegates always carry it in argv. A
    live pid that is not our delegate is a recycled number, and the delegate
    it once named is gone.

    FAILS CLOSED, ALWAYS. Anything unexpected -- no pid recorded, a probe
    that raises, a ps we cannot read -- returns True ("assume alive"), which
    keeps the existing fence. A wrong "alive" costs the founder one Resume
    click; a wrong "dead" puts two writers on one transcript, which is the
    invariant this whole module exists to hold.
    """
    if not pid:
        return True                     # nothing recorded -> assume the worst
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False                    # provably gone
    except (PermissionError, OSError):
        return True                     # exists but not ours to signal
    except (TypeError, ValueError):
        return True
    if not session_id:
        return True
    # live pid: is it OURS, or a recycled number?
    try:
        out = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        cmd = (out.stdout or "")
    except Exception:                   # noqa: BLE001 -- probe failed, fence
        return True
    if not cmd.strip():
        return False                    # ps knows nothing: it died under us
    return str(session_id) in cmd


def remember_delegate_pid(store, mid):
    """Persist the delegate's pid onto the mission that owns it.

    The mission file is already the durable record of delegate identity
    (target_mode + target_session since S53); the pid joins them for the same
    reason and in the same place. No new store and no new entity -- the boot
    path must be able to read this after the process that knew it is gone.

    Best-effort and idempotent: a mission that already carries one is left
    alone, and a failure here must never fail a start.
    """
    try:
        m = store.load(mid)
        if not m or m.get("delegate_pid"):
            return
        pid = DELEGATE_PIDS.get(m.get("target_session"))
        if not pid:
            return
        m["delegate_pid"] = int(pid)
        store.save(m)
    except Exception:                   # noqa: BLE001 -- never fail a start
        pass
#: session_id -> rolling window of STREAMED text (what the app actually saw;
#: transcript files lag or, for fakes, never exist -- the stream is the truth)
_RECENT_TEXT = {}
_RECENT_CAP = 20000

#: how much CLEAN streamed prose evidence_text appends after the evidence
#: blob, so the decider's own tail lands on what the worker actually said
#: rather than on the tail of a json.dumps. Deliberately the same size as
#: mission_engine.DECISION_TAIL (2000) -- that is the window this exists to
#: fill, and a smaller value would leave json in it. Not imported from
#: mission_engine on purpose: mission_engine imports nothing from here, and
#: closing that direction would make the two modules mutually dependent.
DECIDE_PROSE_TAIL = 2000

#: how much of the worker's closing message the completion summary carries.
#: Long enough to be a real account of what was done, short enough that the
#: summary stays a summary -- it renders ABOVE the check list, and a block
#: that pushes the verdicts off the card defeats the pane it sits in.
OUTCOME_CHARS = 700

#: session_id -> unix ts of the LAST frame of any kind (stall detection)
_LAST_FRAME_TS = {}
STALL_SECS = 240

#: a reasoning call is one short turn, not a work turn -- it must not be
#: allowed to stall the mission loop the way a real turn may
DECIDE_TIMEOUT_S = 90

#: how often the boundary wait wakes to re-check liveness. Small relative to
#: STALL_SECS so a worker that goes quiet is caught within one poll of the
#: threshold, and small enough that a cancelled q.get() costs nothing.
POLL_SECS = 15

#: THE ABSOLUTE CEILING ON ONE WORKER TURN. Not a new number: start_pump has
#: always waited 3600s on its queue_event, so this is the outer bound the
#: pump already had, now enforced on the waiting side too. It exists only to
#: bound the runaway case -- a worker that emits frames forever and never
#: finishes a turn keeps the silence clock fresh, so silence alone would
#: never stop it.
MAX_TURN_SECS = 3600


def attach_observer(session_id, rt):
    """Idempotent per runtime: pushes boundary frames into the per-session
    queue (for waiters) and emits rescue feed items on errors (watcher)."""
    # AT MOST ONE LIVE RUNTIME PER SESSION. A pane arriving for a chat Shadow
    # attached to must not leave two `claude --resume <same id>` processes
    # appending to one transcript -- which would corrupt the very evidence
    # done_when is evaluated against. This is the one Shadow-owned function
    # ws_chat already calls with a RESOLVED session id, so the rule holds
    # here without editing ws_chat. founder_takeover() reaps too; it runs
    # earlier but can still see session_id=None on a reconnecting pane's
    # first message, so this is the backstop that always has the id.
    prior = ATTACHED.get(session_id)
    if prior is not None and prior is not rt:
        reap_attached(session_id)
    if rt in _OBSERVED:
        return
    _OBSERVED.add(rt)
    q = _BOUNDARIES.setdefault(session_id, asyncio.Queue())

    def observer(frame):
        t = frame.get("type")
        _LAST_FRAME_TS[session_id] = time.time()
        if t == "token" and frame.get("text"):
            buf = _RECENT_TEXT.get(session_id, "") + frame["text"]
            _RECENT_TEXT[session_id] = buf[-_RECENT_CAP:]
        if t == "_turn_boundary":
            try:
                q.put_nowait(frame)
            except Exception:
                pass
            if frame.get("error"):
                _emit_rescue(session_id, str(frame.get("error"))[:200])
        elif t == "error":
            _emit_rescue(session_id, str(frame.get("detail"))[:200])

    rt.subscribe(observer)


def _forget_session(session_id, rt=None):
    """Drop the PER-SESSION observer bookkeeping when Shadow lets a runtime go.

    The WeakSet above is only half of lifecycle. It guarantees a REPLACEMENT
    runtime is a miss and can therefore always subscribe; it says nothing
    about the three maps keyed by SESSION ID, which outlive the runtime that
    filled them. A replacement attaching to the SAME id inherited all three:

      _LAST_FRAME_TS  a dead runtime's last stamp reads as "silent since
                      then", so the waiter can call a stall on a worker that
                      has not yet been given the chance to say anything;
      _RECENT_TEXT    the previous worker's prose is handed to the decider as
                      what the NEW one just said -- evidence from a process
                      that no longer exists;
      _BOUNDARIES     a queue still holding frames from a turn that is over.

    Called from the two reapers so ownership unwinds in one shape whichever
    way it ends, mirroring release_delegate's own "one reaper" rule. Passing
    `rt` discards the observer entry NOW rather than at the next collection,
    which is what makes the teardown deterministic instead of GC-timed.

    Idempotent, and a no-op for a session that was never observed.
    """
    if rt is not None:
        _OBSERVED.discard(rt)
    _BOUNDARIES.pop(session_id, None)
    _RECENT_TEXT.pop(session_id, None)
    _LAST_FRAME_TS.pop(session_id, None)


def _emit_rescue(session_id, detail):
    shadow_feed.emit({
        "item_id": "rescue-%s" % session_id,
        "producer": "shadow",
        "kind": "needs_decision",
        "severity": "action",
        "why_now": detail,
        "title": "Session %s hit an error" % session_id[:12],
        "deep_link": "sutra://shadow/session/%s" % session_id,
        "dedupe_key": "rescue:%s:%s" % (session_id, detail[:60]),
        "state": "new",
    })


def terminal_why(m):
    """The feed line for a mission that just ended.

    THE ROW NOW SAYS WHAT PASSED (founder, 2026-09-15). Every terminal
    mission emitted "mission <state>", and 14-needs-you.js renders the done
    case as "done - result inside" -- a promise of an inside the founder
    then had to go and find. `_complete` already stamps the inside as one
    line ("3 of 3 checks passed"), so the row carries THAT.

    Failed and stopped are byte-identical to before: a mission that never
    completed has no completion summary, and neither does a done mission
    written before the field existed, so both fall through to the
    historical string.

    Both callers -- the runner's terminal branch and settle_confirmation --
    go through here, because a mission completed by the founder's own
    confirmation is the one most likely to be read.
    """
    if m.get("state") == "done":
        headline = (m.get("completion") or {}).get("headline")
        if headline:
            return headline
    return "mission %s" % m["state"]


def evidence_messages(doc):
    """The transcript messages a check may be verified against.

    Drops the USER-role turns Shadow injected, keeps everything else. The
    asymmetry is the point: Shadow can only ever inject a user turn, so an
    assistant turn that quotes the tag is still the chat's own output and
    stays admissible.
    """
    kept = []
    for msg in (doc or {}).get("messages") or []:
        if msg.get("role") == "user" \
                and shadow_egress.is_shadow_authored(msg.get("text")):
            continue
        kept.append(msg)
    return kept


def evidence_text(session_id):
    """What `done_when` is evaluated against, with Shadow's own words out.

    Two sources, unchanged from before, in the same order and with the same
    40k tail:

      _RECENT_TEXT  the streamed `token` frames -- ASSISTANT text only
                    (session_runtime emits tokens for text deltas and
                    assistant blocks, never for an injected user turn), so
                    this source was already clean.
      read_session  the on-disk transcript, which DOES carry user turns --
                    and Shadow's says land there as user records. That is
                    the leak this function closes.

    Why it matters: `_next_say` names the outstanding checks verbatim, and
    the delegate manifest carries the objective. Left in, either one lets a
    contains_artifact check be satisfied by Shadow having ASKED for the
    thing rather than by the chat having done it. Every other field of the
    doc is passed through exactly as before.

    THE DECIDER READS THE TAIL, AND THE TAIL WAS JSON (measured on the live
    delegate 0423e185, mission m-1e37cbe31708). The blob is built live-first,
    json-last; _decision_context then takes the LAST DECISION_TAIL (2000)
    characters of it. On that session json.dumps(doc) alone was 90,676 chars,
    so the decider's whole 2.2% window landed inside the serialization --
    escaped unicode, `\\n` literals, `{"role": "assistant", "text": ...}` --
    and `live`, the clean streamed prose, was never reachable. It cost a
    real turn: at 05:16:47 the decider reported "Stage 3 didn't land, the
    last thing on the wire is still the Stage 2 tail" and spent turn 6
    re-issuing work the chat had already done.

    So the clean prose is APPENDED after the blob. Nothing is removed and
    nothing is reordered: the 40k blob is byte-identical to what it was, and
    it is still what carries the historical and tool evidence the verifier
    reads. The tail is simply no longer the last thing in the string.

    The appended text is assistant prose that was ALREADY admissible -- the
    same `live` that has always been at the front -- so a contains_artifact
    check can match nothing it could not match before. Shadow's own turns are
    not in _RECENT_TEXT at all (session_runtime emits tokens for assistant
    text only), so the authorship boundary above is untouched.
    """
    live = _RECENT_TEXT.get(session_id, "")
    doc = session_reader.read_session(session_id) or {}
    if doc:
        doc = dict(doc)
        doc["messages"] = evidence_messages(doc)
    blob = (live + " " + json.dumps(doc))[-40000:]
    if not live:
        # nothing streamed for this session: unchanged, byte for byte
        return blob
    return blob + " " + _prose_tail(live)


def _outcome_trim(text, limit=OUTCOME_CHARS):
    """`text` capped at `limit`, cut at a SENTENCE if one is near the end.

    The same lesson _prose_tail records, applied at the other end of the
    string: a cut at whatever byte lands on `limit` reads as something the
    worker wrote when it is not. A sentence boundary in the last two thirds
    of the window wins outright and needs no ellipsis, because nothing was
    left mid-thought; otherwise the cut falls back to a word boundary and
    SAYS it was cut.
    """
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if stop > limit // 3:
        return head[:stop + 1]
    cut = head.rfind(" ")
    return (head[:cut] if cut > 0 else head).rstrip() + "…"


#: the ceiling on the ONE worker message the decider is shown. Not a tail and
#: not a cap on any existing field: DECISION_TAIL (2000), DECIDE_PROSE_TAIL
#: (2000) and _RECENT_CAP (20000) are untouched. Sized above p99 of the
#: corpus measured on this failure (114 assistant messages across 10 Shadow
#: sessions: median 1008, p95 10672, p99 13989, max 21060), so it bites only
#: the pathological single message -- 1 in 114 -- and never the normal case.
DECIDE_RESPONSE_CHARS = 16000


def worker_response(session_id, limit=DECIDE_RESPONSE_CHARS):
    """The worker's LATEST message, whole.

    THE BOTTLENECK THIS REMOVES (founder, 2026-09-15, mission
    m-cd009367d41a). `last_response` was evidence_text -- `(live + " " +
    json.dumps(doc))[-40000:]` -- sliced again to the last DECISION_TAIL
    (2000) characters. The decider therefore read the last 2000 BYTES OF A
    JSON DOCUMENT, not a message. When _RECENT_TEXT was cold (it is
    memory-only, so: after every restart) the real value began

        ':29:09.733Z"}, {"role": "assistant", "text": "## FINAL'

    and when it was warm the window still kept a message's END and dropped
    its START -- where the structure lives ("## CHANGE", "## TESTS",
    "## FINAL"). Shadow spent turns 17-20 asking for resends, describing the
    cut accurately: "`## CHANGE` arrived intact this time". The work was
    already finished. It then hit max turns and died `failed`.

    THE MESSAGE WAS NEVER TOO BIG. The one Shadow needed was 1,811
    characters -- it fitted inside the old window twice over. What consumed
    the window was the ENVELOPE. So this does not widen anything: it returns
    the latest message instead of a byte range.

    LATEST ONLY, AND THAT IS THE POINT. An earlier draft of this accumulated
    messages backwards until a budget filled. Measured on the same mission, a
    24000-char budget pulled in six messages including SUPERSEDED `## CHANGE`
    drafts -- feeding the decider earlier, wrong versions of the very content
    it was trying to read. One message cannot do that.

    THE CAP KEEPS THE HEAD. A single message over `limit` is truncated from
    the END, the opposite of the slice this replaces, because the head is the
    part that was being lost. At or under the limit the text is returned BYTE
    FOR BYTE -- no strip, no whitespace collapse, no join.

    WHAT IT REUSES. read_session, then evidence_messages, then the
    assistant-role check -- the same path last_worker_message walks. Not a
    parser and not a second evaluator: the parsing is session_reader's, the
    admissibility rule is evidence_messages' (Shadow's own turns land as USER
    records and are dropped there; the role check is the independent second
    guard). It returns a string. evaluate_done_when still receives the FULL
    evidence_text, so every contains_artifact match reachable before still is.

    Returns "" when there is nothing to quote, which leaves the caller on the
    value it used before.
    """
    if not session_id:
        return ""
    try:
        doc = session_reader.read_session(session_id) or {}
    except Exception:                   # noqa: BLE001 -- never fail a turn
        return ""
    for msg in reversed(evidence_messages(doc)):
        if msg.get("role") != "assistant":
            continue
        text = str(msg.get("text") or "")
        if not text.strip():
            continue
        return text if len(text) <= limit else text[:limit]
    return ""


def last_worker_message(session_id):
    """WHAT THE WORKER SAID IT DID, in its own last words.

    THE GAP THIS CLOSES (founder, 2026-09-15). completion_summary made a
    finished mission's VERDICT legible -- "3 of 3 checks passed", and which
    criterion was satisfied by what. That is why Shadow calls it done; it
    is not WHAT WAS DONE. A founder reading the pane still learned that
    three boxes were ticked and nothing about the work behind them, and the
    one account of that work -- the delegate's own closing message, which
    says what it built and what it ran -- was on disk the whole time and
    was only ever shown as `result_excerpt`, a byte cut through json.

    NOT A SECOND EVALUATOR, AND NOT A WRITER. This reads the transcript and
    returns a string. It cannot decide a check, cannot change a state, and
    is called only after `done` is settled. Nothing is summarised, nothing
    is asked of a model, and no sentence here is composed: the text is the
    worker's, verbatim, trimmed.

    IT CANNOT QUOTE SHADOW BACK AT THE FOUNDER. evidence_messages is the
    existing admissibility filter and is used for exactly the reason the
    evaluation uses it -- Shadow's says land in the transcript as USER
    records, and an "outcome" that turned out to be Shadow's own
    instruction would be the worst possible version of this field. The
    role check then keeps only assistant turns, so the two guards are
    independent.

    Returns "" for a session with nothing to quote -- no transcript, no
    assistant turn, or an empty one. That is what lets every caller fall
    back to what it rendered before rather than invent a line.
    """
    if not session_id:
        return ""
    try:
        doc = session_reader.read_session(session_id) or {}
    except Exception:
        return ""
    for msg in reversed(evidence_messages(doc)):
        if msg.get("role") != "assistant":
            continue
        text = " ".join(str(msg.get("text") or "").split())
        if text:
            return _outcome_trim(text)
    return ""


def _prose_tail(live, limit=DECIDE_PROSE_TAIL):
    """The last `limit` characters of streamed prose, starting at a WORD.

    THE PHANTOM THIS REMOVES (founder dogfood, 2026-09-14, mission
    m-f83478e90923). The slice was `live[-limit:]`, which cuts at whatever
    byte lands there. Shadow reads the result as literally what the worker
    said, so a cut through "defensi|ble answer in enterprise security" made
    it believe the message BEGAN mid-word. It spent four turns telling the
    delegate to stop emitting a leading fragment that never existed:

        "Close, but the message you just sent did not begin with 'BULKHEAD'
         -- it began mid-word with 'ble answer in enterprise secu'"

    THE CAP IS NOT TOUCHED. The result is a SUFFIX of the same `live[-limit:]`
    slice, so it is never longer than DECIDE_PROSE_TAIL and never reaches
    further back; the only change is dropping a partial leading token. And a
    tail that was never truncated is returned byte for byte, so a short
    message does not lose its first word.

    Nothing about evidence collection, ordering or content moves: `blob` is
    unchanged, `live` is unchanged, and any contains_artifact match that was
    reachable before still is -- `live` is capped at _RECENT_CAP (20000) and
    therefore sits WHOLE inside the 40000-char blob above, which is not
    trimmed here.
    """
    if len(live) <= limit:
        return live                     # nothing was cut
    tail = live[-limit:]
    if live[-limit - 1].isspace() or tail[:1].isspace():
        return tail                     # already starts at a boundary
    cut = 0
    for i, ch in enumerate(tail):
        if ch.isspace():
            cut = i
            break
    else:
        return tail                     # one unbroken token: nothing better
    trimmed = tail[cut:].lstrip()
    return trimmed or tail


def make_bindings(validated_say):
    """The three injectables, bound to the live app."""

    async def sayer(mission, text):
        # TURN CORRELATION (dual-lane fold): drain stale boundary frames
        # BEFORE this say, so the waiter below can only consume the boundary
        # of the turn this say produced. The single-writer runtime + the
        # TurnQueue's inbox-empty rule guarantee one active turn per session;
        # takeover pauses BEFORE an operator turn dispatches, and the engine
        # reloads state after every wait, so a founder turn is never counted
        # as mission progress.
        q = _BOUNDARIES.get(mission["target_session"])
        if q is not None:
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break
        try:
            validated_say(mission["target_session"], mission["id"], text,
                          dedupe_key="%s:t%d:runner"
                          % (mission["id"], mission["turns_used"]))
            return True
        except session_runtime.NoLiveRuntime as exc:
            # NOT a refusal: there was nothing to say THROUGH. Returning the
            # blocker id (a str, never False) is what lets the engine park
            # the attempt as retryable instead of killing it -- see the
            # isinstance(ok, str) arm in MissionEngine.run_mission.
            try:
                shadow_ledger.append("actions", {
                    "mission_id": mission["id"], "kind": "say",
                    "summary": "say NOT DELIVERED (%s): %s"
                               % (exc.reason, str(exc)[:180])})
            except Exception:
                pass
            return exc.reason
        except Exception as exc:
            # the reason must survive (first flight: "say refused", cause lost)
            try:
                shadow_ledger.append("actions", {
                    "mission_id": mission["id"], "kind": "say",
                    "summary": "say REFUSED: %s" % str(exc)[:220]})
            except Exception:
                pass
            return False

    async def waiter(mission, clock=time.time, poll_secs=POLL_SECS,
                     max_turn_secs=MAX_TURN_SECS, stall_secs=STALL_SECS):
        """Wait for THIS turn's boundary, bounded by SILENCE and a ceiling.

        WHY THIS IS NOT A WALL-CLOCK TIMEOUT ANY MORE (live flight, mission
        m-1e37cbe31708, 2026-09-14). This waited a flat BOUNDARY_TIMEOUT_S =
        300s from the say. Measured worker turns on that mission ran 73s,
        138s, 62s, 273s, 209s -- rising as the task deepened -- and turn 7
        was killed at exactly 300s with the delegate still alive and its
        boundary never emitted. The mission died `failed` at 6 of 20 turns
        with five turns of real work in the chat. The only other multi-turn
        mission in the app's history (m-bc6b262cc889, 2026-09-13) died the
        same way, also at exactly 300s. A LONG TURN IS NOT A DEAD TURN, and
        duration was never the signal that told them apart.

        SILENCE IS. `_LAST_FRAME_TS[sid]` is stamped by attach_observer on
        EVERY frame of every type, and STALL_SECS is already this project's
        definition of "that session has gone quiet" (check_stalls). Both
        existed; neither was consulted here. This consults them.

        TWO INDEPENDENT BOUNDS, and both are required:

          silence   no frame for stall_secs  -> False. Catches a hung
                    process, a permission prompt, and a pump that died
                    without emitting a boundary (start_pump kills and
                    returns on exception, so no boundary is ever pushed).
          ceiling   max_turn_secs from the say -> False. Catches the ONE
                    case silence cannot: a runaway worker emitting frames
                    forever without ever finishing a turn.

        A DEAD PROCESS DOES NOT REACH EITHER. demux_turn emits a
        `_turn_boundary` after _demux_turn_inner returns, and that return
        includes the EOF path -- so a worker that exits unblocks this wait
        through the queue, exactly as it always did.

        The return contract is unchanged: True = this turn ended, False =
        stop waiting. mission_engine treats False as a failed turn and is
        untouched. Every bound is an injectable keyword with a production
        default, the same seam check_stalls uses, so tests drive a fake
        clock instead of sleeping.
        """
        sid = mission["target_session"]
        q = _BOUNDARIES.get(sid)
        if q is None:
            return False
        deadline = clock() + max_turn_secs
        while True:
            try:
                await asyncio.wait_for(q.get(), poll_secs)
                return True
            except asyncio.TimeoutError:
                # a boundary that lands while this poll is being cancelled
                # stays in the queue -- asyncio.Queue.get() never consumes an
                # item it does not return -- so the next poll picks it up.
                pass
            now = clock()
            if now >= deadline:
                return False
            last = _LAST_FRAME_TS.get(sid)
            if last is None:
                # never-heard-from target: start its clock HERE, the same
                # grace check_stalls gives a freshly resumed mission, so a
                # stuck-from-birth turn still fails one stall_secs later
                # instead of being treated as infinitely fresh.
                _LAST_FRAME_TS[sid] = now
                continue
            if now - last >= stall_secs:
                return False

    def reader(mission):
        return evidence_text(mission["target_session"])

    return sayer, waiter, reader


def _goal_hook(fn_name, mission, *extra):
    """Goal bookkeeping must NEVER take down a turn that worked (the house
    rule at app.py's chat_store append). No-ops for a mission with no
    goal_id, which today is every mission in production."""
    if not (mission or {}).get("goal_id"):
        return None
    try:
        import goal_lifecycle
        return getattr(goal_lifecycle, fn_name)(mission, *extra)
    except Exception as exc:
        try:
            shadow_ledger.append("actions", {
                "mission_id": mission.get("id"), "kind": "goal_sync",
                "summary": "%s failed: %s" % (fn_name, str(exc)[:200])})
        except Exception:
            pass
        return None


def start_mission(mid, validated_say, verifier=None):
    """Admit + launch the loop task. Returns the (possibly queued) mission."""
    store = mission_engine.MissionStore()
    sched = mission_engine.MissionScheduler(store)
    m = sched.start(mid)
    if m["state"] != "running":
        return m          # queued: launched later by on_terminal promotion
    _goal_hook("on_attempt_start", m)
    _launch(mid, validated_say, verifier)
    return m


async def _promote_after_slot_freed(store, mid, validated_say, verifier):
    """Advance the FIFO queue into an execution slot that just freed.

    Lifted verbatim out of the terminal branch so the blocked branch can
    share it -- two copies of the provision-then-launch dance would drift.

    on_terminal() is the scheduler's only promotion path and it ignores its
    `mid` argument: it promotes the oldest queued row whenever a slot is
    free. That is what makes it correct to call from a NON-terminal
    transition too -- and its running-count query (states=("running",))
    already excludes blocked, so no accounting change is needed.

    Returns the promoted mission, or None when nothing was promoted.
    """
    promoted = mission_engine.MissionScheduler(store).on_terminal(mid)
    if promoted is None:
        return None
    prov = DEFAULT_PROVISIONER["fn"]
    if prov and promoted.get("target_mode") == "new" \
            and not promoted.get("target_session"):
        # a promoted queued mission may still need its delegate
        # (codex P1 fold: queued rows spawn nothing until here)
        eng2 = mission_engine.MissionEngine(store, None, None, None)
        try:
            await eng2.provision_target(promoted["id"], prov)
            remember_delegate_pid(store, promoted["id"])
        except Exception as exc2:
            store.transition(promoted["id"], "failed",
                             "provision on promote failed: %s"
                             % str(exc2)[:200])
            return None
    _goal_hook("on_attempt_start", promoted)
    _launch(promoted["id"], validated_say, verifier)
    return promoted


def _launch(mid, validated_say, verifier):
    if mid in RUNNING and not RUNNING[mid].done():
        return
    store = mission_engine.MissionStore()
    sayer, waiter, reader = make_bindings(validated_say)
    engine = mission_engine.MissionEngine(
        store, sayer, waiter, reader, verifier,
        # observe the evaluation the loop already runs, so a goal's
        # per-check progress is live while it is working
        on_evaluated=lambda mission, results, done: _goal_hook(
            "record_evaluation", mission, results, done),
        # SHADOW DRIVES from turn 1. None (no decider injected, e.g. the
        # flag path or a test) keeps the historical template.
        decider=DEFAULT_DECIDER["fn"],
        # what the delegate said it did, quoted into the completion summary
        outcome_reader=lambda m: last_worker_message(m.get("target_session")),
        # what the DECIDER reads: whole worker messages, not a byte tail
        response_reader=lambda m: worker_response(m.get("target_session")))

    async def run():
        try:
            m = await engine.run_mission(mid)
        except Exception as exc:
            try:
                m = store.transition(mid, "failed",
                                     "runner crashed: %s" % exc)
            except Exception:
                m = store.load(mid)
        finally:
            RUNNING.pop(mid, None)
        if m and m["state"] in mission_engine.TERMINAL:
            # DELEGATES only, and that is the invariant: a delegate is
            # Shadow's own hands and dies with its mission, while an ATTACHED
            # runtime belongs to a chat the founder owns and must outlive
            # every mission that ever drove it. Reaping an attached session
            # here would kill the founder's own conversation.
            #
            # THE PROCESS DIES, THE CHAT DOES NOT. Once a delegate is
            # published as a normal Sutra chat its record, its index row and
            # its transcript are durable and are never touched here -- what
            # ends is Shadow's OWNERSHIP, which is what lets the founder type
            # in it from the next turn on.
            release_delegate(m.get("target_session"))
            mission_engine.emit_mission_feed(
                m, "info" if m["state"] == "done" else "needs_decision",
                terminal_why(m))
            await _promote_after_slot_freed(store, mid, validated_say,
                                            verifier)
        elif m and m["state"] == "blocked":
            # blocked is NOT terminal, so the delegate is deliberately NOT
            # killed: the founder is being asked, and the chat has to be
            # alive to answer in. But the execution SLOT is free the moment
            # the loop stops driving, so the queue must advance on exactly
            # the same path terminal uses -- otherwise a few blocked
            # missions freeze the whole queue at the cap of 5.
            #
            # THE FEED ROW THIS COMMENT WAS WAITING FOR (founder,
            # 2026-09-14). It said the escalation copy belonged to "the slice
            # that actually routes work into blocked" -- that slice is the
            # ask_founder exit, which now blocks for a standalone mission as
            # well as a goal attempt, so the row lands here.
            #
            # The EXISTING emitter, unchanged: emit_mission_feed already
            # keys its dedupe on mission + state + version, which IS the
            # "block reason + attempt" keying V5 R3 asked for -- a mission
            # blocks once per version, and an amend bumps the version and so
            # re-surfaces exactly once. `needs_decision` is the existing kind
            # and is what gives the item severity "action".
            mission_engine.emit_mission_feed(
                m, "needs_decision",
                m.get("block_reason") or "Shadow needs you")
            await _promote_after_slot_freed(store, mid, validated_say,
                                            verifier)
        elif m and m.get("pause_reason"):
            mission_engine.emit_mission_feed(
                m, "needs_decision", m.get("pause_reason"))
        # ONE funnel for every way an attempt can end -- terminal, blocked
        # or paused all land here, so the goal can never be left claiming
        # work that stopped.
        _goal_hook("on_attempt_end", m)
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "stop" if not m else m["state"],
            "summary": "runner finished (%s)"
                       % (m["state"] if m else "unknown")})

    RUNNING[mid] = asyncio.get_event_loop().create_task(run())


def check_stalls(now=None, stall_secs=STALL_SECS):
    """U1 + permission-journey stall detection: a running mission whose
    target session has emitted nothing for stall_secs raises a needs-you
    feed item (deduped one per mission). Pure -- tests pass a fake now."""
    now = time.time() if now is None else now
    store = mission_engine.MissionStore()
    raised = []
    for m in store.list(states=("running",)):
        sid = m.get("target_session")
        last = _LAST_FRAME_TS.get(sid)
        if sid and last is None:
            # never-heard-from target: start its clock at this sweep so a
            # stuck-from-birth delegate still alerts one cycle later, and a
            # freshly resumed mission gets the same grace (deepseek fold)
            _LAST_FRAME_TS[sid] = now
            continue
        if sid and last and (now - last) >= stall_secs:
            ok, _problems = shadow_feed.emit({
                "item_id": "stall-%s" % m["id"],
                "producer": "shadow",
                "kind": "needs_decision",
                "title": "mission may be stalled -- nothing from its "
                         "session for %d min" % max(1, int(now - last) // 60),
                "deep_link": "sutra://shadow/mission/%s" % m["id"],
                "dedupe_key": "stall:%s" % m["id"],
                "state": "new"})
            if ok:
                raised.append(m["id"])
    return raised


_STALL_TASK = {"task": None}


def start_stall_watch(interval=60):
    """Periodic stall sweep. Singleton: repeat startups reuse the live task
    (codex P2 fold); shutdown() cancels it."""
    t = _STALL_TASK.get("task")
    if t is not None and not t.done():
        return t

    async def loop():
        while True:
            await asyncio.sleep(interval)
            try:
                check_stalls()
            except Exception:
                pass

    task = asyncio.get_event_loop().create_task(loop())
    _STALL_TASK["task"] = task
    return task


def active_mission_count():
    store = mission_engine.MissionStore()
    return len(store.list(states=("running", "queued", "paused")))


def recover_on_boot():
    """App restart must not orphan `running` missions (codex fold): anything
    running with no live task pauses honestly; the founder resumes.

    AND it must not orphan their SESSIONS. `SessionRuntime.spawn` passes
    start_new_session=True, so a delegate's Claude process outlives the app
    that started it -- and Electron SIGKILLs the uvicorn child on quit, so
    shutdown() often does not run at all. After a restart DELEGATES is empty
    while that process may still be appending to the transcript. If the send
    guard consulted only DELEGATES, the founder could open the published chat,
    type, and ws_chat would spawn `claude --resume <sid>` against a live
    writer -- two processes on one transcript, which is the case this slice
    exists to prevent.

    So ownership is REBUILT FROM MISSION STATE ALREADY ON DISK. No new
    persistent store and no new entity: a Shadow-created session is exactly a
    non-terminal mission with target_mode == "new" and a target_session, which
    is information the mission file has carried since S53. This is also why
    target_mode is load-bearing for now -- it is the durable discriminator
    between a chat Shadow STARTED and one it merely attached to, and an
    attached chat must stay typeable.

    FENCES, DOES NOT FIX. The orphan process is not killed here: this process
    has no handle on it, and matching it by argv would be a guess. The founder
    Stops or Resumes the mission, and either path releases the fence.
    """
    store = mission_engine.MissionStore()
    for m in store.list(states=("running",)):
        if m["id"] in RUNNING:
            continue
        if "never_say" in m.get("invariants", ()):
            # a watch mission has no loop to orphan: run_mission returns
            # before saying anything and the observers are rebuilt from the
            # watch list, so pausing it only hid it (the one real mission
            # stuck paused since 2026-09-07 was exactly this)
            shadow_ledger.append("missions", {
                "mission_id": m["id"], "state": "running",
                "note": "survived app restart (watch: no loop to lose)"})
            continue
        mm = store.transition(m["id"], "paused",
                              "app restarted -- resume to continue")
        mm["pause_reason"] = "app_restart"
        store.save(mm)
    # after the pauses above, so a just-paused mission is fenced too
    for m in store.list():
        sid = m.get("target_session")
        if (sid and m.get("target_mode") == "new"
                and m.get("state") not in mission_engine.TERMINAL
                and sid not in DELEGATES):
            _ORPHANED.add(sid)


def _left_paused(mid, why):
    shadow_ledger.append("missions", {
        "mission_id": mid, "state": "paused",
        "note": "left paused after restart: %s" % why[:400]})


async def resume_after_restart(ensure_runtime_async, validated_say,
                               ensure_delegate_async=None):
    """Undo the pause the APP itself applied, where that is safe.

    recover_on_boot() pauses honestly; this is the other half, so a restart
    stops being a founder chore for missions nothing was wrong with. Only
    `pause_reason == "app_restart"` is touched: a founder pause, a floor
    pause and a confirmation pause are decisions, not machine trouble.

    THE SAME ADMISSION RULES AS START (codex P1, 2026-09-13): the cap and
    one running mission per target session are what MissionScheduler.start
    enforces, and an automatic resume must not be the one path around them.
    paused -> queued is not a legal edge, so a mission that does not fit
    stays paused with a ledger note instead of being queued.

    Per mission, oldest first:
      watch (never_say)      -> running; no loop to launch
      existing-target say    -> re-attach through ensure_runtime_async (the
                                Resume handler's own step), then the Resume
                                handler's own two lines: running + _launch
      delegate (target new)  -> stays paused: the fence in recover_on_boot
                                exists because the delegate process may
                                still be writing that transcript
    A target whose transcript is gone stays paused with a note and no
    re-attach attempt (34 leaked fixture rows must not spawn 34 claudes).
    No feed items here: emit_mission_feed dedupes on mission+state+version,
    so an app_restart item could collide with an earlier pause (codex P2);
    the ledger note is the record.
    """
    store = mission_engine.MissionStore()
    running = store.list(states=("running",))
    running_sids = {m.get("target_session") for m in running
                    if m.get("target_session")}
    running_n = len(running)
    resumed, left = [], []
    paused = sorted(store.list(states=("paused",)),
                    key=lambda m: m.get("created_ns", 0))
    for m in paused:
        if m.get("pause_reason") != "app_restart":
            continue
        mid = m["id"]
        sid = m.get("target_session")
        if "never_say" in m.get("invariants", ()):
            store.transition(mid, "running",
                             "resumed after restart (watch: no loop to lose)")
            resumed.append(mid)
            continue
        if m.get("target_mode") != "existing" or not sid:
            # A DELEGATE IS ADOPTED ONLY WHEN ITS WORKER IS PROVABLY DEAD
            # (founder, 2026-09-15).
            #
            # THE BUG: a healthy mission driving itself -- four consecutive
            # `continue` decisions on m-55c220d58b1a -- stopped dead because
            # the app restarted under it, and every delegate was fenced here
            # regardless of whether anything was still writing its
            # transcript. A restart became a founder chore for work that had
            # nothing wrong with it. Empirically the worker usually is gone:
            # the delegate behind that mission left no process at all.
            #
            # THE FENCE ITSELF IS RIGHT and is NOT weakened. Re-entry to a
            # session is only ever `claude --resume <sid>` -- the runtime's
            # pipes died with the app and cannot be re-acquired by anyone --
            # so it starts a SECOND process on one transcript. That is the
            # single-writer invariant's whole concern, and it is exactly why
            # this stayed fenced while the answer was UNKNOWN. What changed
            # is that the answer is now knowable: the spawn records its pid
            # on the mission, and delegate_alive() asks about that pid (and
            # checks argv, so a recycled number cannot read as alive).
            #
            # Dead -> the same path an existing-target mission already takes,
            # with the same admission rules below it. Alive, or no pid
            # recorded (a mission from before this shipped), or any probe
            # that failed -> the historical fence, unchanged. delegate_alive
            # fails CLOSED, so every uncertainty keeps the old behaviour.
            if ensure_delegate_async is None:
                _left_paused(mid, "delegate session stays fenced until the "
                                  "founder resumes or stops it")
                left.append(mid)
                continue
            if delegate_alive(m.get("delegate_pid"), sid):
                _left_paused(mid, "delegate worker still alive -- fenced "
                                  "until the founder resumes or stops it")
                left.append(mid)
                continue
            if sid in running_sids:
                _left_paused(mid, "session %s already has a running mission"
                                  % sid)
                left.append(mid)
                continue
            if running_n >= mission_engine.MAX_RUNNING:
                _left_paused(mid, "cap %d reached" % mission_engine.MAX_RUNNING)
                left.append(mid)
                continue
            if not session_reader.read_session(sid):
                _left_paused(mid, "target transcript %s not found" % sid)
                left.append(mid)
                continue
            try:
                await ensure_delegate_async(sid)
            except Exception as exc:  # noqa: BLE001 -- recorded, not hidden
                _left_paused(mid, "could not re-adopt %s: %s"
                                  % (sid, str(exc)[:160]))
                left.append(mid)
                continue
            store.transition(mid, "running",
                             "re-adopted after restart (worker was gone)")
            _launch(mid, validated_say, None)
            running_sids.add(sid)
            running_n += 1
            resumed.append(mid)
            continue
        if sid in running_sids:
            _left_paused(mid, "session %s already has a running mission"
                              % sid)
            left.append(mid)
            continue
        if running_n >= mission_engine.MAX_RUNNING:
            _left_paused(mid, "cap %d reached" % mission_engine.MAX_RUNNING)
            left.append(mid)
            continue
        if not session_reader.read_session(sid):
            _left_paused(mid, "target transcript %s not found" % sid)
            left.append(mid)
            continue
        try:
            await ensure_runtime_async(sid)
        except Exception as exc:      # noqa: BLE001 -- recorded, not hidden
            _left_paused(mid, "could not re-attach to %s: %s"
                              % (sid, str(exc)[:160]))
            left.append(mid)
            continue
        store.transition(mid, "running", "resumed after restart")
        _launch(mid, validated_say, None)
        running_sids.add(sid)
        running_n += 1
        resumed.append(mid)
    return {"resumed": resumed, "left": left}


def shutdown():
    """Cancel loop tasks; missions stay `running` on disk and recover_on_boot
    pauses them at next start (no state is lost, nothing is orphaned).

    AND release the sessions Shadow owns. Cancelling a task does not stop the
    Claude process behind it: spawn() uses start_new_session=True, so an
    un-reaped delegate survives this app and keeps appending to a transcript
    nothing is reading. Killing them here is what makes a CLEAN stop leave no
    second writer behind for the next boot to trip over.

    It does not cover a SIGKILL -- Electron kills the uvicorn child on quit,
    so this hook frequently does not run at all. recover_on_boot() fences what
    survives; this only shrinks how often that is needed.
    """
    for task in list(RUNNING.values()):
        task.cancel()
    RUNNING.clear()
    for sid in list(DELEGATES):
        try:
            release_delegate(sid)
        except Exception:
            pass
    t = _STALL_TASK.get("task")
    if t is not None:
        t.cancel()
        _STALL_TASK["task"] = None


def founder_takeover(session_id):
    """PRD R22 (semantics decided: PAUSE, dual-lane fold): called at payload
    ownership, BEFORE the operator turn dispatches. Queued shadow turns for
    the session are dropped -- the founder took the wheel."""
    store = mission_engine.MissionStore()
    eng = mission_engine.MissionEngine(store, None, None, None)
    hit = None
    for m in store.list(states=("running",)):
        if m.get("target_session") == session_id:
            hit = eng.founder_intervened(m["id"])
            mission_engine.emit_mission_feed(
                hit, "needs_decision", "you took over -- resume when ready")
    # and Shadow's own process for this chat gets out of the way. A no-op
    # unless Shadow had attached one, so every founder turn can call it.
    reap_attached(session_id)
    return hit


async def ensure_runtime(session_id, build_args, register):
    """Make sure Shadow has a runtime to speak through in an EXISTING chat.

    THE GAP THIS CLOSES (first flight, 2026-09-11): `RUNTIMES` is populated
    when a turn COMPLETES on the socket that is open right now, so Shadow
    could only ever drive a chat whose pane the founder was sitting in. That
    contradicts the whole delegation model. This attaches a headless runtime
    to the founder's own session -- same session id, same transcript, one
    continuous conversation -- so the founder never has to keep a pane open.

    MEASURED, NOT ASSUMED (CLI 2.1.268, three live runs):
      * `--resume <sid>` returns the SAME session id, byte for byte;
      * it APPENDS to the existing transcript -- no second .jsonl, one
        `sessionId` inside it, the founder's turns still in order;
      * an unknown id exits 1 with "No conversation found with session ID",
        emitting no `system/init` frame -- which is why the id is checked
        against disk here, BEFORE anything is spawned;
      * a wrong cwd did NOT fail on that version. Irrelevant: the session's
        own cwd is used anyway, because the wrong one gives the runtime the
        wrong project, the wrong memory path and the wrong tool scope.

    Four invariants live in this function:

      1. A LIVE FOUNDER-OWNED RUNTIME ALWAYS WINS. If one is registered and
         alive it is returned untouched -- no spawn, no re-register, no
         second observer. Shadow never displaces the founder's pane.
      2. AT MOST ONE LIVE RUNTIME PER SESSION. Guaranteed by (1) here and by
         attach_observer()'s reap on the way in from a pane.
      3. NO RESUME-FREE FALLBACK. An id that cannot be resumed raises
         NoLiveRuntime; it never degrades into `claude` with no --resume,
         which would start a DIFFERENT conversation.
      4. NOTHING IS SAID HERE. The first turn is the mission's own say,
         through the same queue + pump every other say uses, so evidence
         assembly and the authorship tag are untouched.
    """
    if not session_id:
        raise session_runtime.NoLiveRuntime(session_id)

    rt = session_runtime.lookup_runtime(session_id)
    if rt is not None and rt.alive:
        return rt                      # (1) the founder's pane, untouched

    # (3) refuse a dead id from DISK, before a process exists. resolve_path is
    # the same glob the id resolvers use and opens nothing.
    if session_reader.resolve_path(session_id) is None:
        raise session_runtime.NoLiveRuntime(session_id)

    # the session's OWN working directory -- never the delegate workdir, and
    # never a guess. head_meta reads one file and fails soft to blanks.
    try:
        cwd = (session_reader.head_meta(session_id) or {}).get("cwd") or ""
    except Exception:
        cwd = ""
    if not cwd or not os.path.isdir(cwd):
        raise session_runtime.NoLiveRuntime(session_id)

    rt = session_runtime.SessionRuntime()
    args = build_args(session_id)      # carries --resume <session_id>
    await rt.spawn(args, cwd, tuple(args))
    if not rt.alive:
        # spawn() assigns nothing on OSError, so a failed spawn lands here
        # rather than registering a corpse the say chain would find.
        try:
            rt.clear()
        except Exception:
            pass
        raise session_runtime.NoLiveRuntime(session_id)

    register(session_id, rt)
    attach_observer(session_id, rt)
    ATTACHED[session_id] = rt
    start_pump(rt, session_id)
    shadow_ledger.append("actions", {
        "mission_id": None, "kind": "spawn",
        "summary": "attached to existing session %s (--resume)"
                   % session_id})
    return rt


_DECIDE_PROMPT = """You are Shadow, driving one target chat toward an outcome.

You do NOT do the work. A separate Claude session -- with its own context,
tools and history -- does it. Your job is to read what it just said and
decide the next instruction to send into that same conversation.

You do NOT decide whether the outcome is met. A deterministic verifier owns
that and has already run. Never claim a check is satisfied, never announce
completion, never ask to stop because you think it is done.

OUTCOME
%(outcome)s

COMPLETION CHECKS (verifier-owned; [x] already satisfied)
The number in #N is that check's INDEX. It is the only correct value for
`confirms_check.index` below -- never count positions, never guess.
%(checks)s

BUDGET
turn %(turns_used)s of %(max_turns)s

YOUR PREVIOUS INSTRUCTION
%(last_instruction)s

WHAT THE TARGET CHAT SAID BACK (most recent output)
%(last_response)s

WHAT THE FOUNDER TOLD YOU (their answer to your last question, if any)
%(founder_response)s

Decide. Reply with ONE fenced json block and nothing else:

```json
{"action": "continue", "instruction": "<what to send into the chat next>",
 "reason": "<one short line: why this, now>"}
```

or, if you genuinely cannot make progress and the founder is needed:

```json
{"action": "ask_founder", "reason": "<what you need from the founder>"}
```

An ask_founder MAY also carry a form, when what you need is specific enough
to ask for directly. The `intervention` key is OPTIONAL -- omit it and the
line above behaves exactly as it always has:

```json
{"action": "ask_founder", "reason": "<one short line>",
 "intervention": {
   "question": "<the one thing that has to be decided>",
   "context": "<why you cannot settle it yourself>",
   "fields": [{"key": "region", "type": "choice", "label": "Default region",
               "required": true,
               "options": [{"value": "eu-west-1", "label": "EU West"},
                           {"value": "us-east-1", "label": "US East"}]}]}}
```

WHEN THE QUESTION *IS* A founder_confirm CHECK, SAY SO. A `founder_confirm`
check is met by ONE thing: the founder signing it off. If the intervention
you are raising is asking for exactly that sign-off, mark it, and the
founder's Yes closes the check instead of only answering you:

```json
{"action": "ask_founder", "reason": "<one short line>",
 "intervention": {
   "question": "Do the relevant tests pass?",
   "fields": [{"key": "tests_pass", "type": "boolean",
               "label": "Relevant tests pass."}],
   "confirms_check": {"index": 2, "field": "tests_pass"}}}
```

The rules are strict, and a marker that breaks one is DROPPED -- the
intervention still works, it simply confirms nothing:

  * `index` is the #N of a check in COMPLETION CHECKS above, copied, not
    counted. It must name a `founder_confirm` check -- a machine tier is
    refused, because only the verifier may satisfy those.
  * `field` is the `key` of a field in THIS intervention's own `fields`,
    and that field must have `"type": "boolean"`. Anything else is dropped:
    a choice or a text answer would need a policy for which reply means
    yes, and that judgement is the founder's, not yours to encode.
  * Only True confirms. An answer of False leaves the check open, which is
    correct -- "no, they do not pass" must never sign off that they pass.

OMIT `confirms_check` FOR EVERY OTHER QUESTION. Asking which region to
deploy in, or what the budget cap is, decides nothing about a check. Most
interventions carry no marker at all. Never attach one to make a mission
finish sooner: it is a description of what you are asking, not a lever.

`type` is one of: boolean, choice, multi_choice, text, long_text, number,
currency, percent, date, datetime, url, email, ranking. choice, multi_choice
and ranking need at least two `options`. Use SEVERAL fields when you need
several things at once -- the founder answers them as one form.

Rules for `instruction`: address the target chat directly, build on what it
actually said, and name the specific next thing you want. If it asked you a
question, answer it. If it is stuck or refusing, either unblock it with new
information or use ask_founder. Do not repeat your previous instruction.

Rules for `ask_founder`: try to resolve it YOURSELF first -- read what the
chat said, give it another instruction, tell it to go and find out. Escalate
only when no instruction of yours can settle it and the mission genuinely
cannot proceed without the founder. Never ask for something you can work out
yourself or that the chat can be told to establish. Ask the SMALLEST question
that actually unblocks the mission, and choose the field type that matches
the answer you need. The founder's reply comes back to YOU, not to the chat:
you read it, and you decide the next instruction.
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S)


def _first_decision(text):
    """The first json object in a reply, or None. Never raises."""
    for body in _JSON_FENCE.findall(text or ""):
        try:
            return json.loads(body)
        except ValueError:
            continue
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except ValueError:
            return None
    return None


def _founder_answer_text(answer):
    """The founder's answer, as lines the decider can read.

    LABELLED, NEVER PROSE. It is rendered into its own section of the prompt
    -- never folded into `last_response` -- so Shadow can always tell what
    the FOUNDER told it from what the target chat said, and so a submitted
    value can never be read as the chat's own output. "(none)" for every
    mission that was never asked anything, which is every mission that
    existed before interventions.
    """
    if not isinstance(answer, dict):
        return "(none)"
    rows = answer.get("summary") or []
    lines = ["- %s: %s" % (r.get("label") or r.get("key"), r.get("value"))
             for r in rows if isinstance(r, dict)]
    if not lines:
        return "(none)"
    asked = answer.get("question") or ""
    head = "You asked: %s" % asked if asked else "You asked for input."
    return "\n".join([head] + lines)


def make_decider(build_args, cwd, timeout_s=DECIDE_TIMEOUT_S, new_runtime=None):
    """Shadow's reasoning step as ONE bounded call per mission turn.

    WHY NOT THE FOUNDER'S SHADOW SESSION. app keeps a single persistent
    ShadowSession behind _SHADOW_LOCK. It is the founder's CONVERSATION:
    putting mission reasoning in it would write into the thread they read,
    serialise every decision against their typing (a mission task holding
    that lock while awaiting a 300s boundary is deadlock-shaped), and grow
    one context without bound across every turn of every Assignment.

    So this is a one-shot instead, built from the SAME primitives -- the
    argv `build_args` produces and SessionRuntime's own spawn/send/demux --
    so there is no new provider stack, no new subprocess handling and no
    credential of any kind here (subscription auth rides the environment,
    exactly as it does for every other spawn).

    IT GETS NO SHADOW TOOLS. sutra_mcp registers them only when
    SUTRA_MCP_SHADOW=1 is in the spawn env, and this deliberately does not
    set it. The reasoning process therefore CANNOT say into a session,
    create a mission or write the ledger -- it can only return text, which
    the engine then validates. That is the enforcement behind "Shadow drives,
    the verifier decides".
    """
    async def decide(context):
        import session_runtime as srt
        prompt = _DECIDE_PROMPT % {
            "outcome": context.get("outcome") or "(none)",
            # THE INDEX IS PART OF THE PROMPT (founder, 2026-09-15). A check
            # rendered without one cannot be CITED: `confirms_check.index`
            # has to be the real done_when position, and a decider that has
            # to count them will eventually miscount. The list is already in
            # done_when order -- _decision_context builds it straight off the
            # record -- so the position IS the index; it just was not shown.
            "checks": "\n".join(
                "- #%d [%s] (%s) %s" % (i, "x" if c.get("met") else " ",
                                        c.get("tier"), c.get("check"))
                for i, c in enumerate(context.get("checks") or []))
            or "- (none)",
            "turns_used": context.get("turns_used"),
            "max_turns": context.get("max_turns"),
            "last_instruction": context.get("last_instruction") or "(none)",
            "last_response": context.get("last_response") or "(nothing yet)",
            # .get() like every key above, so a mission that was never asked
            # anything cannot KeyError here -- and _decision_context keeps
            # omitting the key entirely for those, exactly as before.
            "founder_response": _founder_answer_text(
                context.get("founder_response")),
        }
        # THE SAME RUNTIME FACTORY THE CHAT PANES USE, injected the way
        # build_args, register and publish already are -- this module must not
        # import app, and the provider gate (SHADOW_PROVIDERS) belongs on
        # app's side with _shadow_args. None keeps the historical
        # construction, so the flag path and every existing test are
        # byte-identical.
        #
        # What it is NOT: a chat. There is still no chat_store record, no
        # sutra_id, no register_runtime and no resume -- the process answers
        # one prompt and is killed in the finally below. Shadow's reasoning
        # shares Sutra's runtime layer and deliberately not its conversation
        # layer.
        rt = new_runtime() if new_runtime is not None else srt.SessionRuntime()
        texts = []

        async def collect(frame):
            if frame.get("type") == "token":
                texts.append(frame.get("text") or "")

        try:
            await rt.spawn(build_args(), cwd, ("shadow-decide",))
            await rt.send_user_frame(prompt)
            await asyncio.wait_for(rt.demux_turn(collect, None), timeout_s)
        finally:
            # one process per decision, never reused, never leaked
            try:
                rt.kill_group()
                rt.clear()
            except Exception:
                pass
        return _first_decision("".join(texts))

    return decide


def settle_confirmation(mid):
    """A founder confirmed a check -- decide the attempt, with no turn.

    THE ONE thing missing from both confirmation entry points (live, goal
    g-e59b36c8ae53): confirm_check wrote `met` and the goal read 2 of 2,
    but the paused mission was never settled, so `verifying` could never
    reach `done`. Everything below is the runner's EXISTING terminal
    handling, reached for a mission the loop is no longer driving.

    Deliberately NOT a promotion point: a paused mission holds no
    execution slot (MissionScheduler counts states=("running",)), so
    finishing one frees nothing and the queue has nothing to advance.

    Delegate teardown is DELEGATES-only, exactly as the runner's terminal
    branch: an ATTACHED runtime belongs to a chat the founder owns and
    must outlive every mission that ever drove it.
    """
    store = mission_engine.MissionStore()
    engine = mission_engine.MissionEngine(
        store, None, None,
        lambda m: evidence_text(m.get("target_session")),
        on_evaluated=lambda mission, results, done: _goal_hook(
            "record_evaluation", mission, results, done),
        # the SAME completion the loop writes: a mission the founder's own
        # confirmation finishes is the one most likely to be read, so it
        # must not be the one that arrives without the outcome line.
        outcome_reader=lambda m: last_worker_message(m.get("target_session")),
        # what the DECIDER reads: whole worker messages, not a byte tail
        response_reader=lambda m: worker_response(m.get("target_session")))
    m = engine.settle(mid)
    if m and m["state"] in mission_engine.TERMINAL:
        release_delegate(m.get("target_session"))
        mission_engine.emit_mission_feed(
            m, "info" if m["state"] == "done" else "needs_decision",
            terminal_why(m))
    # the same funnel the runner uses: the goal can never be left claiming
    # work that has stopped
    _goal_hook("on_attempt_end", m)
    return m


def reap_attached(session_id):
    """Shadow's process for a FOUNDER-OWNED chat steps aside.

    Founder-takeover policy (founder decision, 2026-09-11): reap, do not hand
    over. Handing the live process to the pane would mean teaching ws_chat to
    adopt a runtime it did not spawn, and ws_chat is the one path this whole
    change refuses to touch. The cost is real and small: the founder's next
    turn cold-starts.

    unregister_runtime is identity-guarded, so when the pane has ALREADY
    registered its own runtime this clears Shadow's process without evicting
    the founder's entry. Idempotent; a no-op for a session Shadow never
    attached to, which is what makes it safe to call on every founder turn.
    """
    rt = ATTACHED.pop(session_id, None)
    if rt is None:
        return None
    try:
        rt.kill_group()
    except Exception:
        pass
    session_runtime.unregister_runtime(session_id, rt)
    try:
        rt.clear()
    except Exception:
        pass
    _forget_session(session_id, rt)
    shadow_ledger.append("actions", {
        "mission_id": None, "kind": "stop",
        "summary": "released attached session %s (founder took the wheel)"
                   % session_id})
    return rt


def driving(session_id):
    """Does Shadow own this Claude session right now?

    THE ONE OWNERSHIP READ. ws_chat asks this before it takes a turn, and the
    answer decides whether a second `claude --resume <sid>` is allowed to
    exist. The invariant it serves:

        FOR ANY CLAUDE SESSION ID, at most one Sutra runtime writes to it.

    Two sources, one concept -- "Shadow owns this session":

      DELEGATES   a runtime THIS process spawned and can still reap
      _ORPHANED   a session a PREVIOUS process owned; the runtime is gone
                  from our view but its Claude process may still be alive

    Deliberately NOT a third map and not a new entity. ATTACHED is excluded on
    purpose: an attached chat is the founder's own, and typing in it is a
    takeover (founder_takeover), not a collision -- that path stays exactly as
    it was.

    Returns the session id (truthy) or None, never a runtime: callers decide
    policy, they do not get a handle to write through.
    """
    if not session_id:
        return None
    if session_id in DELEGATES:
        return session_id
    if session_id in _ORPHANED:
        # A FENCE THAT CAN EXPIRE. The mission behind an orphan can reach a
        # terminal state on a path this process never launched -- the founder
        # stops it from Shadow Home, or abandons its goal -- and neither goes
        # through release_delegate(). Re-checking the store HERE, instead of
        # adding a release call to every such path, is what keeps the fence
        # from outliving the work and leaving a chat permanently un-typeable.
        #
        # Costs a store read only while a fence is actually set, which is
        # empty in the normal case and non-empty only after a restart that
        # left missions in flight. Self-healing: the check runs once, then the
        # id is discarded for good.
        try:
            store = mission_engine.MissionStore()
            live = any(m.get("target_session") == session_id
                       and m.get("state") not in mission_engine.TERMINAL
                       for m in store.list())
        except Exception:
            live = True          # unreadable store: stay closed, never open
        if not live:
            _ORPHANED.discard(session_id)
            return None
        return session_id
    return None


def release_delegate(session_id):
    """Shadow lets go of a session it owned. THE ONE DELEGATE REAPER.

    Was two copies of the same four lines -- the runner's terminal branch and
    settle_confirmation's -- which is one edit away from the two drifting.
    Same body, same order, same effects as both had:

        pop DELEGATES -> kill the group -> drop OUR registry row -> clear

    unregister_runtime is identity-guarded, so when a pane has already taken
    the registry key this clears Shadow's process without evicting the
    founder's entry -- the same rule reap_attached follows, for the same
    reason.

    Also clears any _ORPHANED fence for the id: whichever way ownership ends,
    it ends in one place. Idempotent, and a no-op for a session Shadow never
    owned, which is what makes it safe to call on every terminal transition.
    """
    _ORPHANED.discard(session_id)
    rt = DELEGATES.pop(session_id, None)
    if rt is None:
        return None
    try:
        rt.kill_group()
    except Exception:
        pass
    session_runtime.unregister_runtime(session_id, rt)
    try:
        rt.clear()
    except Exception:
        pass
    _forget_session(session_id, rt)
    return rt


def start_pump(rt, sid):
    """THE PUMP (found by the first real flight): panes have a websocket loop
    consuming their TurnQueue; a headless runtime has nobody -- says sat
    queued forever and every boundary wait timed out. This is that loop:
    nudge -> dequeue -> send -> demux (which fires _turn_boundary to the
    waiters).

    Lifted OUT of spawn_delegate_session verbatim -- same body, same 3600s
    wait, same kill-on-error -- so the attach path below cannot drift from
    the delegate path. It is the only thing extracted in this change.
    """
    async def _pump():
        async def sink(frame):
            return None
        while rt.alive:
            try:
                await asyncio.wait_for(rt.queue_event.wait(), 3600)
            except asyncio.TimeoutError:
                continue
            rt.queue_event.clear()
            while True:
                payload = rt.turn_queue.get()
                if payload is None:
                    break
                try:
                    await rt.send_user_frame(payload.get("message") or "")
                    await rt.demux_turn(sink, sid)
                except Exception:
                    rt.kill_group()
                    return

    return asyncio.get_event_loop().create_task(_pump())


async def spawn_delegate_session(build_args, cwd, manifest, register, env=None,
                                 publish=None):
    """S53 in production: a NEW claude session Shadow delegates into.

    Headless twin of a pane: its own SessionRuntime, spawned in PLAN mode
    (v1 safety: real turns, visible work, no unsupervised writes -- acting
    delegates need an explicit founder grant), registered in the same
    registry the say chain uses, observer attached, first turn = the
    enriched manifest. The transcript lands in ~/.claude/projects.

    `publish` is an INJECTED (sid) -> sutra_id|None hook, supplied the same
    way `build_args` and `register` are and for the same reason: this module
    must not import app, and chat_store lives on app's side of that line.
    It is what turns the delegate into a NORMAL Sutra chat.

    IT IS CALLED AS SOON AS THE SESSION IS IDENTIFIED, not when the first
    turn ends (founder, 2026-09-13). The boundary is the CLI's own
    `session_id` announcement, which is the proof the old `got_result and
    sid` check was standing in for: a provider that dies at its argv parser
    never announces one, so a chat that never started still never appears in
    the rail. The RuntimeError and the mission's failure semantics are
    untouched; only the WAIT is gone, and with it the ~44s during which the
    founder had started a task with nothing to open.

    A publish failure is DELIBERATELY NOT FATAL. The session is live and
    Shadow can drive it; losing the chat record costs discoverability, not
    correctness, and raising here would strand a running Claude process to
    save a rail row. It is ledgered instead, so the gap is visible.
    """
    import session_runtime as srt
    rt = srt.SessionRuntime()
    args = build_args()
    await rt.spawn(args, cwd, tuple(args), env=env)
    texts = []
    #: the id the CLI announced, and whether we have already acted on it
    early = {"sid": None}

    def _adopt(sid):
        """Claim the session and publish its chat. Runs ONCE, at the first
        moment the id exists -- see the `collect` hook below."""
        if early["sid"]:
            return
        early["sid"] = sid
        # OWNERSHIP FIRST, and it is not bookkeeping: driving() reads
        # DELEGATES, and it is what the send guard asks before it lets a pane
        # take a turn. Published-but-unowned would be a chat the founder can
        # open AND type into while this turn is still running -- a second
        # `claude --resume` on the same transcript, which is the one thing
        # the single-writer invariant exists to prevent. A plain dict write,
        # with none of the side effects that keep register/attach/pump below.
        DELEGATES[sid] = rt
        # ...and REMEMBER WHICH PROCESS IT IS. delegate_alive() needs a pid to
        # ask about after the app that spawned it is gone; this is where the
        # process and the session id are both known. In-memory here;
        # remember_delegate_pid puts it on the mission, which is the copy that
        # survives the restart.
        try:
            if getattr(rt, "proc", None) is not None:
                DELEGATE_PIDS[sid] = rt.proc.pid
        except Exception:               # noqa: BLE001 -- never fail a spawn
            pass
        # STILL EXACTLY ONE spawn row per delegate -- it simply lands when the
        # session becomes real rather than when its first turn ends.
        shadow_ledger.append("actions", {
            "mission_id": None, "kind": "spawn",
            "summary": "delegate session %s spawned" % sid})
        if publish is None:
            return
        try:
            publish(sid)
        except Exception as exc:      # noqa: BLE001 -- reported, never fatal
            shadow_ledger.append("actions", {
                "mission_id": None, "kind": "spawn",
                "summary": "delegate %s NOT published as a chat: %s"
                           % (sid, str(exc)[:180])})

    async def collect(frame):
        # THE CHAT APPEARS WHILE THE DELEGATE IS STILL WORKING (founder,
        # 2026-09-13). Publication used to wait for demux_turn to return,
        # which is the END of the whole first agentic turn -- measured at 44s
        # on mission m-e14f6acc41aa. For that entire window the founder had
        # started a task and had nothing to open.
        #
        # session_runtime emits this frame from the first event that carries
        # a session_id, which is ~1s after spawn and long before the turn
        # ends. That frame is also exactly the boundary the old docstring
        # wanted: a CLI that dies at its argv parser (the deepseek case)
        # never emits one, so a session that never started still publishes
        # nothing. What changed is the wait, not the proof.
        if frame.get("type") == "session" and frame.get("id"):
            _adopt(frame["id"])
        if frame.get("type") == "token":
            texts.append(frame.get("text") or "")

    await rt.send_user_frame(manifest)
    (sid, _t, got_result, err, _e) = await rt.demux_turn(collect, None)
    if not got_result or not sid:
        # release_delegate is the ONE reaper and is a no-op for a session we
        # never claimed, so it covers both cases: died before announcing an
        # id (nothing adopted, nothing published) and died after (the chat
        # stays, pointing at a real transcript, and the mission fails around
        # it -- an honest record beats a vanished one).
        if early["sid"]:
            release_delegate(early["sid"])
        else:
            rt.kill_group()
            rt.clear()
        raise RuntimeError("delegate session failed to boot: %s" % (err,))
    # Belt and braces: demux_turn parses the id the same way the frame does,
    # so this only fires if the frame hook was somehow missed. Idempotent.
    _adopt(sid)
    register(sid, rt)
    attach_observer(sid, rt)
    DELEGATES[sid] = rt

    # AFTER the spawn turn, never before: the pump runs its own demux_turn
    # loop on the same stdout, and two demuxers on one process would split
    # the stream. attach_observer is late for the same reason -- the spawn
    # turn's own _turn_boundary must not land in the waiters' queue.
    start_pump(rt, sid)
    return sid


#: missions currently inside the async start path (double-click guard)
_STARTING = set()
#: registered once by the app; promotion of queued new-target missions
#: needs a spawner long after the originating request died (codex P1 fold)
DEFAULT_PROVISIONER = {"fn": None}
#: async (context) -> decision dict. Injected from app at startup, exactly
#: like the provisioner, because shadow_runner must not import app.
DEFAULT_DECIDER = {"fn": None}


def set_default_provisioner(fn):
    DEFAULT_PROVISIONER["fn"] = fn


def set_default_decider(fn):
    DEFAULT_DECIDER["fn"] = fn


def start_mission_async(mid, validated_say, provisioner=None, verifier=None):
    """Second-flight fix: provisioning a delegate takes minutes; holding the
    HTTP request open let client timeouts CANCEL it mid-spawn. Admission and
    provisioning now run as an app task; the endpoint answers immediately and
    the mission file is the progress surface."""
    store = mission_engine.MissionStore()

    async def go():
        try:
            m = store.load(mid)
            if m and m["state"] == "running":
                return                    # double-start no-op (race fix)
            if mid in _STARTING:
                return                    # a second click provisions NOTHING
            _STARTING.add(mid)
            try:
                # cap BEFORE any spawn (codex P1): a full scheduler must
                # queue cheaply, never leak a live delegate for a queued row
                if len(store.list(states=("running",))) \
                        >= mission_engine.MAX_RUNNING:
                    mission_engine.MissionScheduler(store).start(mid)
                    return
                prov = provisioner or DEFAULT_PROVISIONER["fn"]
                m = store.load(mid)
                if prov and m and m.get("target_mode") == "new" \
                        and not m.get("target_session"):
                    eng = mission_engine.MissionEngine(store, None, None,
                                                       None)
                    await eng.provision_target(mid, prov)
                    remember_delegate_pid(store, mid)
                start_mission(mid, validated_say, verifier)
            finally:
                _STARTING.discard(mid)
        except Exception as exc:
            try:
                mm = store.load(mid)
                # NEVER downgrade a healthy running mission (race fix: the
                # duplicate starter's failure is not the mission's failure)
                #
                # `running` JOINED THE LIST, NARROWLY. Admission now happens at
                # session adoption (app._publish_delegate_chat step 1b), so a
                # spawn that dies AFTER announcing its id -- demux_turn coming
                # back without a result -- reaches this handler with the state
                # already `running`. Guarding on the two pre-launch states
                # alone would leave that mission at RUNNING forever with a
                # worker that has already been reaped: the same silent freeze
                # this handler exists to prevent, one state over.
                #
                # The race rule above is kept intact by asking about the
                # DELEGATE, not the state: a healthy running mission always
                # has its session registered here (spawn_delegate_session
                # writes DELEGATES[sid] at adoption and release_delegate is
                # the one reaper). No live delegate means this mission has no
                # worker, whoever started it -- so it is this mission's
                # failure, not a duplicate starter's.
                orphaned = bool(
                    mm and mm["state"] == "running"
                    and mm.get("target_mode") == "new"
                    and mm.get("target_session")
                    and mm["target_session"] not in DELEGATES)
                if mm and (mm["state"] in ("brief_confirm", "queued")
                           or orphaned):
                    store.transition(mm["id"], "failed",
                                     "provision/admit failed: %s"
                                     % str(exc)[:200])
            except Exception:
                pass

    asyncio.get_event_loop().create_task(go())
    return {"accepted": True, "mission_id": mid,
            "note": "provisioning + admission in background; poll the "
                    "missions list"}
