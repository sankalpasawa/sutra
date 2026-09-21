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
import signal
import subprocess
import time
import weakref

import mission_engine
import session_reader
import session_runtime
import shadow_egress
import shadow_feed
import shadow_home_lock
import shadow_judge
import shadow_ledger
import shadow_forward

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
def _app_process_alive(pid):
    """Is THAT app process still running? Liveness only -- no argv check.

    Narrower than delegate_alive on purpose. This is only ever asked about a
    pid THIS codebase wrote while running as the app, so the recycled-number
    case delegate_alive guards against is not reachable in the same way: a
    lease is claimed and released inside one process lifetime, and an app
    killed mid-mission leaves a pid that is simply gone.

    FAILS OPEN (returns False, "not alive") on a garbage stamp, because the
    cost of the two answers is not symmetric: a wrong "alive" strands a
    mission nothing is driving, a wrong "dead" costs a duplicate loop that
    the in-process RUNNING guard already prevents in the common case.
    """
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False                    # provably gone
    except (PermissionError, OSError):
        return True                     # exists, not ours to signal
    except (TypeError, ValueError):
        return False                    # not a pid at all
    return True


def loop_held_elsewhere(store, mid):
    """Is another LIVE app process already driving this mission?

    THE DUPLICATE THIS CLOSES (founder dogfood, 2026-09-15, m-5c2fca3f824b).
    `RUNNING` is the only thing that stopped two loops on one mission, and it
    is a module global -- per PROCESS. Five app boots in eight seconds each
    re-adopted the same mission and each launched its own loop: four decider
    subprocesses ran CONCURRENTLY against one mission file (transcripts
    a0fad862, c1c5ada7, 8992a0cc, 2cf2a11d, overlapping 19:15:06-19:15:20),
    every one of them entitled to say into the same worker session and to
    decide its terminal state.

    So the lease goes where every other cross-restart fact about this mission
    already lives: the mission record. No new store, no new entity -- the
    same place delegate_pid was put, for the same reason.

    Never raises: an unreadable store answers "no" and the caller proceeds,
    which is the historical behaviour.
    """
    try:
        m = store.load(mid)
        if m is None:
            return False
        pid = m.get("loop_pid")
        if not pid or int(pid) == os.getpid():
            return False                # nobody, or us -- RUNNING decides
        return _app_process_alive(pid)
    except Exception:                   # noqa: BLE001 -- never block a launch
        return False


def _claim_loop(store, mid):
    """Stamp THIS process as the mission's driver. Best-effort, like
    remember_delegate_pid: losing the stamp costs the cross-process guard,
    never the launch."""
    try:
        m = store.load(mid)
        if m is None:
            return
        m["loop_pid"] = os.getpid()
        store.save(m)
    except Exception:                   # noqa: BLE001
        pass


def _release_loop(store, mid):
    """Drop the lease when the loop ends, so the next boot is free to take
    it without waiting on a pid probe. Only ever clears OUR OWN stamp: a
    lease another live process took while we were finishing is not ours to
    remove."""
    try:
        m = store.load(mid)
        if m is None or m.get("loop_pid") != os.getpid():
            return
        m["loop_pid"] = None
        store.save(m)
    except Exception:                   # noqa: BLE001
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
#:
#: RAISED 700 -> 6000 (founder, 2026-09-17). 700 was sized for the ONE-LINE
#: gist that renders above the check list, and for that job it was right: a
#: block that pushes the verdicts off the card defeats the pane it sits in.
#: The Summary block below the checks has the opposite job -- for a RESEARCH
#: task the worker's closing message IS the deliverable, and 700 characters
#: cut it mid-report. Measured against the corpus this module already
#: records (114 assistant messages across 10 Shadow sessions: median 1008,
#: p95 10672, p99 13989, max 21060), 700 truncated even the MEDIAN message.
#:
#: 6000 is a bound, not an absence of one: ~6x the median, still under p95,
#: and under DECIDE_RESPONSE_CHARS (16000) which this module already carries
#: per decision. It is stored per completed mission and returned by
#: GET /api/shadow/missions, so it is deliberately not unbounded -- the
#: payload grows with every finished task on the list.
OUTCOME_CHARS = 6000

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


def _outcome_tidy(text):
    """The worker's own words with the machine noise out AND THE STRUCTURE IN.

    WHAT CHANGED, AND WHY (founder, 2026-09-17). This used to be
    `" ".join(text.split())` -- every run of whitespace, newlines included,
    flattened to one space. That was correct while the only consumer was the
    one-line gist above the check list: a quote carrying raw newlines and
    tabs read as machine noise, which is what test_42 pinned.

    The Summary block renders THE SAME FIELD as markdown, and markdown is
    made of line breaks: flattening them turns a heading into prose, a
    bulleted list into a run-on sentence and a table into rubble. So the
    NOISE is still removed and the STRUCTURE is now kept -- the same intent
    test_42 recorded, applied to a field that is now displayed rather than
    quoted.

    OUT: carriage returns, runs of spaces or tabs INSIDE a line, trailing
    spaces on a line, and runs of three or more newlines.

    IN: single and double line breaks (markdown's block boundaries) and
    LEADING indentation, which is what makes a nested list nested and an
    indented code block code. Interior runs collapse only AFTER a non-space
    character, which is what leaves indentation alone.

    Composes nothing and judges nothing: every character it returns is the
    worker's own.
    """
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(?<=\S)[ \t]+", " ", t)    # interior runs; indentation kept
    t = re.sub(r"[ \t]+\n", "\n", t)         # trailing spaces on a line
    t = re.sub(r"\n{3,}", "\n\n", t)          # at most one blank line
    return t.strip()


def _outcome_trim(text, limit=OUTCOME_CHARS):
    """`text` capped at `limit`, cut at a SENTENCE if one is near the end.

    The same lesson _prose_tail records, applied at the other end of the
    string: a cut at whatever byte lands on `limit` reads as something the
    worker wrote when it is not. A sentence boundary in the last two thirds
    of the window wins outright and needs no ellipsis, because nothing was
    left mid-thought; otherwise the cut falls back to a word boundary and
    SAYS it was cut.
    """
    text = _outcome_tidy(text)
    if len(text) <= limit:
        return text
    head = text[:limit]
    # A LINE BREAK IS A BOUNDARY TOO, now that _outcome_tidy keeps them: a
    # sentence that ends a paragraph ends ".\n", not ". ", and a cap that
    # knew only ". " would walk back past the whole paragraph hunting a
    # space that is not there. Same rule, both spellings.
    stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "),
               head.rfind(".\n"), head.rfind("!\n"), head.rfind("?\n"))
    if stop > limit // 3:
        return head[:stop + 1]
    cut = max(head.rfind(" "), head.rfind("\n"))
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
        text = _outcome_tidy(msg.get("text"))
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

        The return contract: True = this turn ended, False = stop waiting
        (mission_engine treats it as a failed turn, exactly as before), and
        a STRING names a precondition that stopped the wait from happening
        at all -- the sayer's own contract, at the other end of the turn.
        Every bound is an injectable keyword with a production default, the
        same seam check_stalls uses, so tests drive a fake clock instead of
        sleeping.
        """
        sid = mission["target_session"]
        q = _BOUNDARIES.get(sid)
        if q is None:
            # NOT A STALL: THERE WAS NOTHING TO WAIT ON (founder,
            # 2026-09-16). No queue means no observer is attached to this
            # session -- _forget_session drops all three per-session maps
            # when a runtime is reaped, so a reap-and-reattach race leaves
            # the loop waiting on a boundary nobody is pushing. Returning
            # False said "the worker went quiet", which the engine read as
            # the worker's failure and spent a mission on; it had not waited
            # a single second, and the worker may have been finishing
            # normally the whole time.
            #
            # A STRING IS A NAMED PRECONDITION, the same contract the sayer
            # above already uses for NoLiveRuntime: the wait never happened,
            # so nothing about the attempt is spent and the engine parks it
            # as Shadow's own fault (mission_engine.run_mission's
            # isinstance(arrived, str) arm). True/False are untouched.
            return "no_boundary_queue"
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
        # the decider rides along so provision_target can decide the bar
        # before the spawner briefs the worker (see _criteria_before_first_
        # contact). None -- the flag path, a test -- keeps the old behaviour.
        eng2 = mission_engine.MissionEngine(store, None, None, None,
                                            decider=DEFAULT_DECIDER["fn"])
        try:
            await eng2.provision_target(promoted["id"], prov)
            remember_delegate_pid(store, promoted["id"])
        except Exception as exc2:
            store.transition(promoted["id"], "failed",
                             "provision on promote failed: %s"
                             % str(exc2)[:200])
            return None
    # the spawn above takes minutes; a founder stop inside that window must
    # not leave the worker it created running (_ended_during_provision)
    if _ended_during_provision(store, promoted["id"]):
        return None
    _goal_hook("on_attempt_start", promoted)
    _launch(promoted["id"], validated_say, verifier)
    return promoted


async def drain_queue(validated_say, verifier=None, store=None):
    """Fill every free execution slot from the FIFO queue. Returns the ids
    promoted, oldest first.

    THE RAISE-THE-CAP PATH. A mission finishing frees exactly one slot, so
    the terminal/blocked funnel calls _promote_after_slot_freed once and that
    is right. Raising "Running at once" from 2 to 5 frees THREE at once, and
    a single promotion would leave two tasks sitting queued behind a limit
    that no longer exists -- the founder would have to wait for unrelated
    work to end before their own setting took effect.

    Bounded by construction: _promote_after_slot_freed returns None the
    moment the queue is empty or the cap is full again, and the loop also
    carries a hard ceiling in case a promotion fails in a way that leaves the
    row queued (a spawner that throws transitions it to `failed`, but a
    future path that does not must still not spin here).
    """
    store = store or mission_engine.MissionStore()
    promoted = []
    for _ in range(mission_engine.RUNNING_CEILING + 1):
        m = await _promote_after_slot_freed(store, None, validated_say,
                                            verifier)
        if m is None:
            break
        promoted.append(m["id"])
    return promoted


def _launch(mid, validated_say, verifier):
    if mid in RUNNING and not RUNNING[mid].done():
        return
    store = mission_engine.MissionStore()
    # ...AND THE SAME QUESTION ACROSS PROCESSES. RUNNING answers it inside
    # this one; the lease answers it for the app instance that has not
    # finished dying yet. Checked before anything is constructed so a refused
    # launch costs nothing.
    if loop_held_elsewhere(store, mid):
        return
    # EVERY START, RESUME AND RE-ADOPTION PASSES HERE, which is why the
    # restart flush hangs off it rather than off boot recovery alone: a
    # mission resumed by hand hours later gets its pending founder lines
    # too. A no-op when nothing is pending.
    flush_forwards(mid)
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
        # ...and SHADOW JUDGES from turn 1 too (D-SH-1). Same injection shape
        # as the decider and the same None-means-historical-behaviour: an
        # install that never binds one has `judge` rows that never settle,
        # and the founder is asked at the end of the road exactly as before.
        judge=DEFAULT_JUDGE["fn"],
        # what the delegate said it did, quoted into the completion summary
        outcome_reader=lambda m: last_worker_message(m.get("target_session")),
        # what the DECIDER reads: whole worker messages, not a byte tail
        response_reader=lambda m: worker_response(m.get("target_session")))

    async def run():
        try:
            m = await engine.run_mission(mid)
        except Exception as exc:
            # A CRASHED LOOP IS THE SUPERVISOR FAILING, NOT THE WORK
            # (founder, 2026-09-16). This handler catches whatever the engine
            # could not name -- a store that would not write, a binding that
            # raised -- and it wrote `failed`, which is a verdict on the
            # delegate's work that nothing here is entitled to make. It takes
            # the same recoverable exit as every other infra fault now:
            # blocked, labelled, delegate alive, Resume works.
            #
            # FALLS BACK TO THE HISTORICAL LINE. `running -> blocked` is the
            # only legal edge into blocked, so a crash from any other state
            # (and a `done` mission, whose completion must never be
            # overwritten) drops through to exactly what this did before.
            m = None
            try:
                m = store.block(mid, "shadow_crashed",
                                "runner crashed: %s" % exc)
                m["failure_class"] = mission_engine.INFRA_FAILURE_CLASS
                store.save(m)
            except Exception:
                try:
                    m = store.transition(mid, "failed",
                                         "runner crashed: %s" % exc)
                except Exception:
                    m = store.load(mid)
        finally:
            RUNNING.pop(mid, None)
            _release_loop(store, mid)
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
            # A PAUSE FREES THE SLOT TOO, and this branch was the last exit
            # from the loop that did not say so.
            #
            # The accounting is not a judgement call: MissionScheduler
            # counts states=("running",), and `paused` is not one -- so the
            # moment this branch is reached the cap has room the queue
            # cannot see. It is the same argument the blocked branch above
            # makes, and every pause that lands here is a mission the loop
            # has genuinely stopped driving: awaiting founder confirmation,
            # held at a floor, or handed to the founder mid-turn.
            #
            # MEASURED IN THE LIVE APP (run-limit walkthrough, 2026-09-16).
            # It matters most for the SHIPPED completion path: the New Task
            # form writes founder_confirm checks, a mission whose checks are
            # all founder_confirm pauses here for sign-off, and with nothing
            # promoting, a queued task could wait behind a colleague that
            # had stopped working and was waiting on a human.
            await _promote_after_slot_freed(store, mid, validated_say,
                                            verifier)
        # ONE funnel for every way an attempt can end -- terminal, blocked
        # or paused all land here, so the goal can never be left claiming
        # work that stopped.
        _goal_hook("on_attempt_end", m)
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "stop" if not m else m["state"],
            "summary": "runner finished (%s)"
                       % (m["state"] if m else "unknown")})

    _claim_loop(store, mid)
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

    AND ONLY THE RECOVERING PROCESS RUNS IT (founder, 2026-09-16). Everything
    below rewrites missions another live app may be driving right now; a
    second backend on this home must stand down rather than pause work it
    cannot see. See shadow_home_lock for why this is a separate invariant from
    the per-mission loop_pid lease below.
    """
    owned, holder = shadow_home_lock.claim_recovery()
    if not owned:
        shadow_ledger.append("missions", {
            "mission_id": None, "state": "boot",
            "note": "boot recovery skipped: pid %s holds this shadow home"
                    % ((holder or {}).get("pid") or "?")})
        return
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
                               ensure_delegate_async=None, verifier=None):
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

    AND ONLY THE RECOVERING PROCESS RE-ADOPTS. Re-entry to a session is
    `claude --resume <sid>`, which starts a second process on one transcript;
    the whole point of the fence below is that this is safe only when the
    first writer is provably gone. A second backend asking that question about
    a worker the FIRST backend is currently driving would get "dead" for a
    session that is very much alive, because the pid it probes belongs to a
    delegate the live app owns. So it does not get to ask.
    """
    owned, holder = shadow_home_lock.claim_recovery()
    if not owned:
        shadow_ledger.append("missions", {
            "mission_id": None, "state": "boot",
            "note": "restart re-adoption skipped: pid %s holds this shadow "
                    "home" % ((holder or {}).get("pid") or "?")})
        return {"resumed": [], "left": []}
    store = mission_engine.MissionStore()
    running = store.list(states=("running",))
    running_sids = {m.get("target_session") for m in running
                    if m.get("target_session")}
    running_n = len(running)
    # the founder's cap, read ONCE for the whole sweep: this loop counts
    # admissions as it goes, and a mid-sweep settings change that moved the
    # bar under it would make the count and the limit disagree
    cap = mission_engine.max_running()
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
            if running_n >= cap:
                _left_paused(mid, "cap %d reached" % cap)
                left.append(mid)
                continue
            if not session_reader.read_session(sid):
                _left_paused(mid, "target transcript %s not found" % sid)
                left.append(mid)
                continue
            try:
                # THE WORKER KEEPS THE PERMISSIONS IT WAS GIVEN (founder,
                # 2026-09-16). _worker_args rebuilds argv from the CURRENT
                # global settings, so a worker spawned under `acceptEdits`
                # came back on whatever the founder had selected since --
                # `plan`, i.e. read-only -- and silently stopped being able
                # to do the work it was mid-way through. The mode it was
                # spawned with is stamped on the mission; this hands it back.
                # None (a mission from before the stamp existed) resolves to
                # the historical behaviour inside the callee.
                await ensure_delegate_async(
                    sid, m.get("worker_permission_mode"))
            except Exception as exc:  # noqa: BLE001 -- recorded, not hidden
                _left_paused(mid, "could not re-adopt %s: %s"
                                  % (sid, str(exc)[:160]))
                left.append(mid)
                continue
            store.transition(mid, "running",
                             "re-adopted after restart (worker was gone)")
            _launch(mid, validated_say, verifier)
            running_sids.add(sid)
            running_n += 1
            resumed.append(mid)
            continue
        if sid in running_sids:
            _left_paused(mid, "session %s already has a running mission"
                              % sid)
            left.append(mid)
            continue
        if running_n >= cap:
            _left_paused(mid, "cap %d reached" % cap)
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
        _launch(mid, validated_say, verifier)
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
    # and the recovery lease, so a clean restart does not race the kernel's
    # cleanup for its own successor. The kernel releases it on death anyway;
    # this only shrinks the window, exactly like the delegate reaping above.
    shadow_home_lock.stop_rearm()
    shadow_home_lock.release_recovery()


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


def _kill_orphan_delegate(pid, session_id):
    """Kill a delegate THIS PROCESS HAS NO HANDLE ON, by its recorded pid.

    release_delegate is the one reaper and needs a runtime object: it holds
    the pipes, and `rt.kill_group()` is what actually ends the worker. After
    a restart there is no such object -- DELEGATES is empty while the worker
    itself is very much alive, because `_spawn_process` makes it a group
    leader and it outlives the app that started it. A founder who presses
    Stop on that mission has to be able to end it anyway.

    SAME KILL, DIFFERENT HANDLE. proc_group.kill_group signals the process
    GROUP rather than the direct child, because `claude` spawns helpers that
    hold the stdout pipe; this is that call with the pid the mission record
    has carried since S53 instead of a live `Popen`.

    ARGV-GUARDED, because a pid is not an identity. delegate_alive() already
    answers "is that delegate still running", and it answers it by asking
    whether the live pid's command line still mentions this session -- so a
    recycled number reads as dead and is never signalled. It fails CLOSED
    (unknown -> "alive"), which is the wrong direction for a killer, so the
    session id is REQUIRED here: without one there is no way to tell our
    worker from whatever inherited its number, and nothing is signalled.

    Returns True only when a signal was actually delivered.
    """
    if not pid or not session_id:
        return False
    if not delegate_alive(pid, session_id):
        return False                    # already gone, or not ours
    try:
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(int(pid), signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            return False
    except (TypeError, ValueError):
        return False


def _ended_during_provision(store, mid):
    """Did the founder end this mission while its worker was being spawned?

    A DELEGATE SPAWN TAKES MINUTES (the second-flight fix exists because of
    it: `spawn_delegate_session` sends the manifest and waits out the whole
    first agentic turn -- 44s measured on m-e14f6acc41aa). Stop pressed
    inside that window wrote `stopped` correctly, and then the spawn
    finished and handed a LIVE worker to a mission that had already ended.
    Nothing afterwards would reap it: `start_mission` refuses a terminal
    mission, so no loop is launched, and no loop means the runner's own
    terminal branch -- the only thing that calls release_delegate on that
    path -- never runs. The founder's Stop had been obeyed on disk and
    ignored by the process table.

    THE SAME RELOAD THE LOOP ALREADY DOES BEFORE ANY TERMINAL DECISION,
    applied at the other end: after the spawner returns, ask the record
    again. Terminal -> reap what was just created and report it. Returns
    True when the caller must not launch.
    """
    m = store.load(mid)
    if m is None or m["state"] not in mission_engine.TERMINAL:
        return False
    sid = (m or {}).get("target_session")
    reaped = release_delegate(sid) is not None
    if not reaped:
        reaped = _kill_orphan_delegate(m.get("delegate_pid"), sid)
    shadow_ledger.append("actions", {
        "mission_id": mid, "kind": "stop",
        "summary": "mission ended (%s) while its delegate was spawning -- "
                   "worker %s, nothing launched"
                   % (m["state"], "reaped" if reaped else "not found")})
    return True


def founder_force_stop(mid, note="founder stop"):
    """THE FOUNDER'S STOP, CARRIED ALL THE WAY TO THE WORKER.

    WHAT IT WAS (measured live, 2026-09-16: a mission started against a
    worker that hangs mid-turn, Stop pressed from the task row):

        t+0s   POST stop -> state `stopped`, ended_by `founder`, slot freed
        t+10s  the worker process is STILL ALIVE and still mid-turn

    `founder_stop` writes state and nothing else -- it lives in
    mission_engine, which owns no processes. The worker died only when the
    LOOP next reached a checkpoint and returned a terminal record, which the
    runner's own wrapper then reaped: up to STALL_SECS (240s) of silence, or
    MAX_TURN_SECS (3600s) for a worker that keeps emitting. Until then a
    mission the founder had ended still had a claude process appending to
    its transcript, and a paused or queued mission -- no loop at all -- had
    nothing that would ever reap it.

    So the founder action and the process teardown happen in ONE place, here,
    in the module that owns the processes. Every step is an existing
    primitive; nothing new is invented:

      1. already terminal      -> hand it back untouched. IDEMPOTENT, and it
                                  is also what keeps a mission that finished
                                  a second ago DONE: a stop never overwrites
                                  a completion.
      2. founder_stop          -> `stopped` + ended_by="founder", the one
                                  writer of that stamp, so an explicit stop
                                  stays distinguishable from a worker failure
                                  (`failed`) and from a supervisor fault
                                  (`blocked` + failure_class).
      3. cancel the loop task  -> before the kill, so the loop cannot observe
                                  a dying worker and write a verdict about
                                  it. CancelledError is not an Exception, so
                                  the wrapper's handler does not fire; its
                                  `finally` still clears RUNNING and the
                                  lease.
      4. release_delegate      -> THE reaper: kill_group, unregister, clear,
                                  forget the session. A no-op for a chat
                                  Shadow merely ATTACHED to, which is what
                                  keeps the founder's own conversation (and
                                  every continuation in it) untouched.
      5. orphan fallback       -> _kill_orphan_delegate, for the delegate
                                  this process has no handle on.
      6. release the lease     -> so no later boot waits on a pid probe.

    WHAT IT DOES NOT DO. It does not touch ATTACHED runtimes, it does not
    promote the queue (the caller already drains it, and doing it here would
    be a second promotion path), and it is never reached by a machine ending
    -- ping-pong, budget and a stalled turn keep their own exits, with no
    `ended_by` and no kill of their own.
    """
    store = mission_engine.MissionStore()
    m = store.load(mid)
    if m is None:
        raise ValueError("no mission %s" % mid)
    if m["state"] in mission_engine.TERMINAL:
        return m                        # 1. idempotent; a completion stands
    sid = m.get("target_session")
    pid = m.get("delegate_pid")
    m = mission_engine.MissionEngine(store, None, None, None).founder_stop(
        mid, note)                      # 2.
    _STARTING.discard(mid)
    task = RUNNING.pop(mid, None)       # 3.
    if task is not None and not task.done():
        task.cancel()
    reaped = release_delegate(sid) is not None      # 4.
    killed = False
    if not reaped:
        killed = _kill_orphan_delegate(pid, sid)    # 5.
    _release_loop(store, mid)                       # 6.
    shadow_ledger.append("actions", {
        "mission_id": mid, "kind": "stop",
        "summary": "founder force stop: loop cancelled=%s, delegate %s"
                   % (task is not None,
                      "reaped" if reaped else
                      ("killed by pid %s" % pid) if killed else
                      "none to stop")})
    return store.load(mid)


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


#: ASKED ONLY OF A MISSION THAT HAS NO CHECKS (founder, 2026-09-15). The
#: founder may leave "Done when" empty -- the outcome is still required, but
#: what would COUNT as done is Shadow's to write when they did not say. It is
#: rendered into the prompt only in that case, so every mission that already
#: carries criteria sends a byte-identical prompt and cannot be invited to
#: rewrite the founder's own words.
#:
#: Shadow answers it ONCE. After the first turn writes them the mission has
#: checks, this section disappears, and the normal loop resumes.
_CRITERIA_ASK = """
THIS MISSION HAS NO COMPLETION CHECKS, AND YOU MUST WRITE THEM
The founder gave an outcome but did not say what would count as done, which
leaves it to you. With THIS decision only, add a `done_when` key: two to four
checks that, taken together, mean the outcome above is genuinely achieved.

```json
{"action": "continue", "instruction": "<what to send into the chat next>",
 "reason": "<one short line: why this, now>",
 "done_when": [{"tier": "founder_confirm", "check": "<a state, not a task>"}]}
```

  * Write a STATE that is true when the work is done ("the EMI check passes"),
    never an instruction to perform ("run the EMI check").
  * THERE ARE THREE TIERS AND THE FOUNDER'S IS THE RAREST OF THEM. Choose in
    this order, and only fall to the next when the one above genuinely does
    not fit:

      `verify`           you can say HOW to check it: a probe that reads a
                         file, or a COMMAND that is run and whose exit code
                         answers the question. Anything about tests passing,
                         a build succeeding, a script running clean, output
                         being produced -- all of these are `verify`, and
                         they are the most common kind of check there is.
      `judge`            no command settles it, but the CHANGE ITSELF shows
                         it: "the fix addresses the root cause rather than
                         masking it", "nothing unrelated was touched", "the
                         new function handles the empty case". Shadow reads
                         the diff and decides. THIS IS THE DEFAULT -- if you
                         do not name a tier, this is what you get.
      `founder_confirm`  ONLY taste, or a fact that exists nowhere but in
                         the founder's head. "The wording reads well",
                         "this is the design you preferred", "the budget cap
                         is X". If you can imagine settling it by reading
                         the repository or running something, IT IS NOT THIS
                         TIER, and writing it here will simply be ignored --
                         the check is routed to `judge` instead.

    EVERY CHECK YOU MARK `founder_confirm` IS A CLICK YOU ARE ASKING A HUMAN
    FOR. On this install, every check ever written was that tier and the
    founder had to sign off "the tests pass" by hand. Do not do that to them.
  * A `verify` check about a FILE should carry a `probe`, and then Shadow
    reads that file itself instead of believing what the chat says about it:

      {"tier": "verify", "check": "shadow-race-test.txt contains exactly
       shadow-race-pass",
       "probe": {"kind": "file_equals", "path": "shadow-race-test.txt",
                 "text": "shadow-race-pass", "allow_trailing_newline": true}}

    `kind` is one of SIX. Five are a plain read of one file, and the sixth
    RUNS A COMMAND -- which is the one that covers most real checks:

      command_succeeds
                      {"kind":"command_succeeds", "argv":["pytest","-q"]}
                      + optional "expect_exit" (default 0), "contains" (a
                      string the output must also carry), "ignore_case",
                      "timeout_s" (default 180, max 900).

                      `argv` IS A LIST, never one string, and it is run
                      WITHOUT a shell -- so there is no piping, no `&&`, no
                      redirection and no globbing. Invoke the program
                      directly: ["npm","test"], ["./run-tests.sh"],
                      ["git","status","--porcelain"]. A shell invoked with
                      -c is refused, so do not write ["bash","-lc","..."].
                      It runs in the working directory.

                      THIS IS THE ANSWER TO ALMOST EVERY "does it work"
                      CHECK. "The tests pass" is
                      {"kind":"command_succeeds","argv":["./run-tests.sh"]}.
                      Reach for it before you reach for the founder.

      file_exists     {"kind","path"}
      file_equals     {"kind","path","text"} + optional
                      "allow_trailing_newline" -- set it true unless the
                      founder asked for a file with no newline at the end;
                      most editors and shells add one
      line_count      {"kind","path","count"} -- count is a whole number;
                      a single trailing newline is not counted as a line
      lines_distinct  {"kind","path"} -- no two non-blank lines are equal
      file_contains   {"kind","path","text"} + optional "ignore_case" --
                      a SUBSTRING test, never a pattern

    `path` is RELATIVE to the working directory, never absolute and never
    containing "..". Write the
    `check` as the sentence a human would read; the probe is how it is
    settled, not what it says.
  * Only attach a probe to something a file or a command genuinely decides.
    A probe answers "is this mechanically true", never "is this what the
    founder wanted" -- but note that "is this what the founder wanted" is
    usually `judge`, not `founder_confirm`. The founder's tier is for what
    only they can know, not for everything a probe cannot reach.
  * SPLIT A CHECK THAT ASKS FOR SEVERAL THINGS. One check holding a
    mechanical clause AND a judgement clause is settled at the weaker of the
    two, so the mechanical half loses its certainty. Write them as SEPARATE
    checks instead: each mechanical clause becomes its own `verify` with its
    own probe, and what is left becomes `judge` (or, rarely, the founder's).

    "the file has 10 lines, each a distinct line of random text" is three
    claims. Two are mechanical and one is not:

      {"tier": "verify", "check": "notes.txt has 10 lines",
       "probe": {"kind": "line_count", "path": "notes.txt", "count": 10}}
      {"tier": "verify", "check": "no two lines in notes.txt are the same",
       "probe": {"kind": "lines_distinct", "path": "notes.txt"}}
      {"tier": "founder_confirm", "check": "the lines read as random text"}

    Shadow settles the first two itself and keeps driving until they hold;
    the founder is asked only for the third. Splitting is not padding the
    list -- do it when the clauses are genuinely separable, and keep the set
    small.

    THE SAME SPLIT, ON A REAL TASK. "Fix the focus loss in the compose box"
    became three checks, and every one of them reached the founder because
    none of them named a tier:

      {"tier": "verify", "check": "the shell suite passes",
       "probe": {"kind": "command_succeeds",
                 "argv": ["node", "test_shadow_v4_shell.js"]}}
      {"tier": "verify", "check": "nothing else in the suite broke",
       "probe": {"kind": "command_succeeds", "argv": ["./run-tests.sh"]}}
      {"tier": "judge", "check": "the fix addresses the root cause in the
       source rather than masking it with a refocus-on-blur hack"}

    Zero founder clicks. That is the shape to aim for.
  * Derive them from the OUTCOME above and what the chat has said so far.
    Do not invent scope the founder did not ask for, and keep the set small:
    every check is something a human will have to look at.
  * DO NOT ASK THE FOUNDER FOR THEM. An empty "Done when" is not a gap in
    the brief and it is not a question for you to raise: the founder named
    the outcome, which is theirs, and left what would count as done to you,
    which is yours. An `ask_founder` whose reason is that the criteria are
    missing is the one answer this section exists to prevent -- you have the
    outcome and the chat, and that is enough to write them.
  * Omit the key only if you truly cannot tell yet, and then CONTINUE
    anyway; you will be asked again next turn. Never stop for it.
"""


_VERIFY_ASK = """
HOW WILL EACH UNVERIFIED CHECK BE ESTABLISHED?
The checks marked (unverified) above are waiting on the founder. For each one
you can settle by LOOKING AT A FILE or by RUNNING A COMMAND, add it to a
`verification` list on THIS decision and the founder stops being needed for
it -- permanently, from this turn on:

```json
{"verification": [{"index": 0,
                   "probe": {"kind": "file_equals", "path": "out.txt",
                             "text": "ok", "allow_trailing_newline": true}}]}
```

  * `index` is the #N shown above. It is the ONLY way to name a check here.
  * You are answering HOW, never WHAT. The check's wording is not yours to
    send, change or restate -- it is not a field in this shape at all, and
    whatever the founder or you wrote earlier stands exactly as written.
  * `kind` is one of SIX. Five read one file: `file_exists`
    ({"kind","path"}), `file_equals` ({"kind","path","text"} + optional
    "allow_trailing_newline"), `line_count` ({"kind","path","count"}),
    `lines_distinct` ({"kind","path"}), `file_contains`
    ({"kind","path","text"} + optional "ignore_case", a SUBSTRING test and
    never a pattern). Set "allow_trailing_newline" true unless the check asks
    for a file with no newline at the end. `path` is RELATIVE to the working
    directory, never absolute and never containing "..".

    The sixth RUNS SOMETHING, and it is the one most unverified checks want:
    `command_succeeds` ({"kind":"command_succeeds","argv":[...]} + optional
    "expect_exit", "contains", "ignore_case", "timeout_s"). `argv` is a LIST
    run WITHOUT a shell -- no pipes, no `&&`, no redirection, and a shell
    invoked with -c is refused. Run the program directly:
    {"kind":"command_succeeds","argv":["./run-tests.sh"]}.

    LOOK AT THE UNVERIFIED LIST ABOVE AND ASK, FOR EACH ONE: what would I
    type to find this out? If there is an answer, that answer is an argv,
    and that check is yours to settle rather than the founder's.
  * OMIT A CHECK YOU CANNOT SETTLE THIS WAY. Leaving one out is the correct
    and honest answer -- it does not go to the founder by default, it goes to
    a reading of the diff. Do NOT invent a path, guess at a filename you have
    not seen, invent a test command you have not confirmed exists, or attach
    a probe that only approximately tests the check: a probe that tests the
    wrong thing is worse than no probe, because it would let Shadow claim it
    verified something it did not.
  * A check you DO attach a probe to stops needing the founder: Shadow will
    read that file itself, every turn, and the worker's word about it counts
    for nothing.
"""


_DECIDE_PROMPT = """You are Shadow, driving one target chat toward an outcome.

You do NOT do the work. A separate Claude session -- with its own context,
tools and history -- does it. Your job is to read what it just said and
decide the next instruction to send into that same conversation.

You do NOT decide whether the outcome is met. A deterministic verifier owns
that and has already run. Never claim a check is satisfied, never announce
completion, never ask to stop because you think it is done.

WHO YOU WORK FOR (the founder's own words, from their settings)
%(carry)s
These are standing answers. Where they settle a question, they have already
answered it -- decide on them and move, rather than asking the founder
something they have told you once. They never reach the floors, they never
satisfy a founder_confirm check, and they never override what the founder
says in this task's own chat.

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

ACTIVE FOUNDER INSTRUCTIONS (standing constraints on this task)
%(standing)s
These govern the task until the founder changes them, and they outlive the
turn that created them. They are YOUR restatement of what the founder asked
for, not their wording.

WHAT THE FOUNDER HAS SAID SINCE YOUR LAST DECISION (newest last)
%(founder_says)s
Two channels, and the tag says which. [instruction] is the founder typing an
instruction at you deliberately. [conversation] is the founder talking to you
in this task's chat -- a question, a thought, an aside -- which you have
already answered there, and which may have nothing to do with the work.

NEITHER IS A MESSAGE FOR THE WORKER, and you decide which parts are. Read
them for what they CHANGE about the work and carry only that into your
instruction, in your own words. Do not forward the founder's wording, do not
answer a question here, and do not instruct at all when nothing they said
changes what the worker should do next -- an idle remark is not a reason to
send a turn. They confirm no check and resolve no question.

KEEPING THE ACTIVE SET RIGHT. `standing` is OPTIONAL and REPLACES the whole
set when you send it, so send the instructions that STILL govern the task,
all of them, restated in your own words. Leave the key out to keep the set
exactly as it is; send [] only when nothing governs the task any more.
An [instruction] the founder typed is durable unless it plainly applies to
one turn only. A [conversation] line is durable only when the founder clearly
means it to outlive this turn -- "from now on", "don't ... during this task"
-- and a question is never an instruction. Where two conflict the newer
founder intent wins and the older one does not survive into the set.

Creating or changing the set is not itself a reason to send the worker a
turn, and an active instruction is a constraint on what you instruct, not
something to forward.

Decide. Reply with ONE fenced json block and nothing else:

```json
{"action": "continue", "instruction": "<what to send into the chat next>",
 "reason": "<one short line: why this, now>",
 "standing": ["<every instruction that still governs this task>"]}
```

%(criteria_ask)s%(verify_ask)s
or, if you genuinely cannot make progress and the founder is needed:

```json
{"action": "ask_founder", "reason": "<what you need from the founder>",
 "ask_kind": "founder_fact"}
```

`ask_kind` is one of exactly three strings: "floor", "founder_fact", "taste".

THE FOUNDER IS ASKED FOR THREE THINGS AND NOTHING ELSE, AND THIS IS ENFORCED
RATHER THAN REQUESTED. `ask_kind` declares which of the three this is, and
the engine CHECKS THE QUESTION AGAINST THE LABEL -- writing "taste" over a
mechanical question does not get it through. An ask that is none of the three
is REFUSED: the mission keeps running and you are told to go and establish it
yourself, which costs a turn you did not need to spend.

  floor         what you are about to do is unrecoverable: a destructive git
                operation, writing into an external client repository, or an
                irreversible external send (an email, a publish, a charge).
  founder_fact  a fact that exists NOWHERE but in the founder's head -- a
                credential, a budget ceiling, which region, which of two
                things they actually want. Not a fact you could read off
                disk, and not a fact you could find out by running something.
  taste         a question with no correct answer, only theirs: whether the
                wording reads well, whether a design is the one they meant.

EVERYTHING ELSE IS YOUR OWN WORK AND YOU HAVE FULL ACCESS TO DO IT. "Do the
tests pass", "did the fix land", "is this the right file", "does it build",
"did anything else break" -- every one of those has an answer on the machine
you are already running on. Go and get it. If a command settles it, put that
command in a `verify` probe so it settles itself from now on and neither you
nor the founder is ever asked again.

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

Rules for `ask_founder`: try to resolve it YOURSELF first -- read WHO YOU
WORK FOR above, read what the chat said, give it another instruction, tell
it to go and find out. If the founder's own words already answer the
question, that IS the answer: act on it, and do not put the same question to
them a second time. Escalate only when it is one of the three kinds above and
no instruction of yours can settle it. Never ask for something you can work out
yourself or that the chat can be told to establish. Ask the SMALLEST question
that actually unblocks the mission, and choose the field type that matches
the answer you need. The founder's reply comes back to YOU, not to the chat:
you read it, and you decide the next instruction.

Assume the founder is busy, and that any question you send them costs more
than it costs you to go and find the answer yourself. That is the bar.
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


def _standing_text(standing):
    """What currently governs the task, as lines the decider can read.

    Shadow's OWN restatement of the founder's constraints, never the
    founder's raw words -- so this block can be read as "the rules", while
    the block below is read as "what was said". "(none)" for a task nobody
    has constrained, which is every task until Shadow writes a set.
    """
    lines = ["- %s" % str(t).strip()
             for t in (standing or []) if str(t).strip()]
    return "\n".join(lines) or "(none)"


def _founder_says_text(says):
    """Everything the founder has said, as lines the decider can read.

    Same shape and same reasoning as _founder_answer_text below: its own
    labelled section of the prompt, never folded into last_response, so what
    the FOUNDER volunteered can never be read as the target chat's output.
    "(none)" for every mission nobody has said anything to, which is every
    mission that existed before this.

    THE CHANNEL IS PART OF THE LINE (founder, 2026-09-16, step 2). The
    founder has two doors -- an instruction typed at Shadow, and a remark in
    the task's own chat -- and they do not mean the same thing. An
    instruction was composed to change the work; a conversational line may be
    a question, a thought, or nothing to do with the work at all. Shadow
    cannot judge relevance without knowing which it is reading, and the
    founder must never be asked to classify their own sentence, so the tag is
    derived from WHICH ROUTE WROTE THE ROW and nothing else.

    `via` ABSENT MEANS INSTRUCTION, which is every row written before this
    existed: the say endpoint was the only writer, so an untagged aside is a
    typed instruction by construction and reads as one.
    """
    rows = [s for s in (says or []) if isinstance(s, dict)]
    lines = []
    for s in rows:
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        via = "conversation" if s.get("via") == "talk" else "instruction"
        lines.append("- [%s] %s" % (via, text))
    return "\n".join(lines) or "(none)"


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


def render_decide_prompt(context):
    """The steering prompt for one turn, from a _decision_context dict.

    ONE RENDERER, TWO SPEAKERS (Shadow v4, ADR-043): the one-shot decider
    below sends it to a fresh process; a task's Shadow chat
    (shadow_task_chat.TaskChat.decide) sends the same text into its own
    conversation. Lifted verbatim out of make_decider so the two can never
    drift.
    """
    return _DECIDE_PROMPT % {
        # THE DECIDER IS THE ONE READER THAT INHERITS NOTHING. Shadow's own
        # session and every task chat boot on SHADOW.md plus
        # shadow_session.standing_context(), which carries the founder's two
        # settings texts; make_decider spawns a FRESH process with no persona
        # and no context turn, so the process that chooses the next
        # instruction was the only one deciding without them. .get() with a
        # default, like every optional key below, so a hand-built context
        # (the suites build several) cannot KeyError here.
        "carry": context.get("carry") or "(the founder has not written any)",
        "standing": _standing_text(context.get("standing")),
        "outcome": context.get("outcome") or "(none)",
        # THE INDEX IS PART OF THE PROMPT (founder, 2026-09-15). A check
        # rendered without one cannot be CITED: `confirms_check.index`
        # has to be the real done_when position, and a decider that has
        # to count them will eventually miscount. The list is already in
        # done_when order -- _decision_context builds it straight off the
        # record -- so the position IS the index; it just was not shown.
        # (unverified) marks a check with no mechanical test behind it, which
        # is what _VERIFY_ASK below asks Shadow to fix where it honestly can.
        # Rendered off `probe`, which _decision_context carries as a boolean.
        "checks": "\n".join(
            "- #%d [%s] (%s)%s %s" % (i, "x" if c.get("met") else " ",
                                      c.get("tier"),
                                      "" if c.get("probe")
                                      else (" (unverified)"
                                            if c.get("tier") in
                                            ("founder_confirm", "judge")
                                            else ""),
                                      c.get("check"))
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
        "founder_says": _founder_says_text(context.get("founder_says")),
        # DERIVED, NOT A NEW CONTEXT KEY: the mission either has checks or
        # it does not, and _decision_context already carries them. Empty
        # -> Shadow is asked to write them; otherwise this renders to the
        # empty string and the prompt is exactly what it was before.
        "criteria_ask": ("" if (context.get("checks") or [])
                         else _CRITERIA_ASK),
        # DERIVED, exactly like criteria_ask: asked only while some check has
        # no mechanical test behind it, and rendering to the empty string --
        # the prompt Shadow saw before this existed -- the moment none does.
        # `judge` COUNTS AS UNVERIFIED HERE (D-SH-1). A judged row is settled
        # by a model reading a diff; the same row settled by a command is
        # deterministic, repeatable and free. So Shadow is still asked how it
        # might be probed, and _needs_verification lets that promotion land.
        "verify_ask": (_VERIFY_ASK
                       if any(c.get("tier") in ("founder_confirm", "judge")
                              and not c.get("probe")
                              and not c.get("met")
                              for c in (context.get("checks") or []))
                       else ""),
    }


def make_decider(build_args, cwd, timeout_s=DECIDE_TIMEOUT_S, new_runtime=None):
    """Shadow's reasoning step as ONE bounded call per mission turn.

    RETIRED FROM THE APP (founder D81, 2026-09-21): app no longer binds this.
    Every decision is a turn in the task's own Shadow chat
    (shadow_task_chat.route_decision), revived when it has died, never a
    process with no chat record. Kept, unbound, for the lean-lane tests that
    pin its argv and its no-tools property until those lanes are retired
    with it.

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
        prompt = render_decide_prompt(context)
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


def make_judge(build_args, cwd, timeout_s=DECIDE_TIMEOUT_S, new_runtime=None):
    """One bounded call that settles ONE check by reading the evidence.

    RETIRED FROM THE APP (founder D81, 2026-09-21): app no longer binds this.
    The judge is a turn in the task's own Shadow chat
    (shadow_task_chat.route_judgement -> TaskChat.judge), same prompt, same
    parser. Kept, unbound, beside make_decider for the same reason.

    BUILT FROM make_decider'S PRIMITIVES ON PURPOSE, and it inherits every
    property that made the decider safe: a fresh one-shot process, the same
    absent shadow-tool marker (so it cannot say into a session, create a
    mission or write the ledger), no chat record, no resume, killed in the
    `finally`. It can only return text, which shadow_judge then validates
    into one of three verdicts.

    THE MARKER'S NAME IS DELIBERATELY NOT SPELLED OUT IN THIS DOCSTRING.
    test_shadow_drives asserts the reasoning lane's source does not contain
    it, and a comment that named it would fail that test for the one reason
    a test should never fail: prose.

    THE CWD IS SHADOW'S OWN WORKDIR, NOT THE FOUNDER'S REPO. The judge is
    handed the evidence as TEXT in its prompt; it is not given a shell in the
    tree it is judging. That is the difference between a reviewer reading a
    diff and a second worker with opinions, and it is what keeps
    "Shadow supervises, Shadow does not have a shell in the repo" true after
    this module grew a judge.

    A FAILURE RETURNS None, NEVER A VERDICT. Timeout, spawn failure,
    unparseable reply -- all None, which _run_judges reads as "said nothing"
    and leaves the row exactly as it found it. A judge that cannot answer
    must never be mistaken for one that answered "no".
    """
    async def judge(check, evidence, outcome=""):
        import session_runtime as srt
        prompt = shadow_judge.render_prompt(check, evidence, outcome)
        rt = new_runtime() if new_runtime is not None else srt.SessionRuntime()
        texts = []

        async def collect(frame):
            if frame.get("type") == "token":
                texts.append(frame.get("text") or "")

        try:
            await rt.spawn(build_args(), cwd, ("shadow-judge",))
            await rt.send_user_frame(prompt)
            await asyncio.wait_for(rt.demux_turn(collect, None), timeout_s)
        except Exception:                # noqa: BLE001 -- None, never a verdict
            return None
        finally:
            try:
                rt.kill_group()
                rt.clear()
            except Exception:
                pass
        return shadow_judge.parse_verdict("".join(texts))

    return judge


def settle_confirmation(mid, verifier=None):
    """A founder confirmed a check -- decide the attempt, with no turn.

    `verifier` is the SAME callable the loop is launched with. It was the
    one evaluate-and-decide path that never received one, so a `verify`
    check the loop could see satisfied read as unmet here and the founder's
    Yes settled nothing -- the dead end this function exists to close,
    reopened one layer down. Default None keeps every existing caller and
    test byte-identical.

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
        lambda m: evidence_text(m.get("target_session")), verifier,
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


#: app.forward_to_worker, injected at import (app imports this module, so the
#: assignment cannot be an import cycle). None on any install that never
#: loaded the app -- the flag path, a unit test -- and every call site below
#: is guarded, so the lane is simply absent there rather than broken.
FORWARD_FLUSH = {"fn": None}


def _forward_consumed(payload):
    """Mark forwarded rows `consumed` the instant the frame is on the wire.

    BEFORE demux, NOT AFTER, and the ordering is the point. `send_user_frame`
    returning means the founder's words are IN the worker's session; a demux
    that raises afterwards loses the answer, never the delivery. Marking
    after demux would leave the rows `dispatched`, boot recovery would re-
    queue them, and the founder's correction would arrive a second time --
    the duplicate this lane is required not to produce.

    NEVER RAISES. It is called from inside the pump's try, where an exception
    kills the process group: a bookkeeping fault must not take down a worker.
    """
    mid = (payload or {}).get("_mission")
    idx = (payload or {}).get("_fwd_indices")
    if not mid or not idx:
        return
    try:
        store = mission_engine.MissionStore()
        m = store.load(mid)
        if m is not None and shadow_forward.mark(
                m, idx, shadow_forward.FWD_CONSUMED):
            store.save(m)
    except Exception:                   # noqa: BLE001 -- never fail a turn
        pass


def flush_forwards(mid):
    """Re-offer this mission's pending founder lines to a fresh TurnQueue.

    THE RESTART CASE, AND IT IS THE ONLY REASON THIS EXISTS. TurnQueue lives
    in memory. A founder line marked `dispatched` in a process that then died
    was accepted by a queue that no longer exists, so it was never sent and
    nothing else would ever send it. Called from _launch -- which every
    start, resume and post-restart re-adoption goes through -- it re-queues
    exactly those rows against the new runtime. Rows already `consumed` are
    not pending and are never re-offered.

    A NO-OP WITH NOTHING PENDING, so calling it on every launch is free.
    """
    fn = FORWARD_FLUSH.get("fn")
    if fn is None:
        return None
    try:
        return fn(mid)
    except Exception as exc:            # noqa: BLE001 -- audible, never fatal
        try:
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "say",
                "summary": "forward flush failed: %s" % str(exc)[:140]})
        except Exception:
            pass
        return None


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
                    # queued -> dispatched -> CONSUMED. See _forward_consumed
                    # for why this lands between the send and the demux.
                    _forward_consumed(payload)
                    await rt.demux_turn(sink, sid)
                except Exception:
                    rt.kill_group()
                    return

    return asyncio.get_event_loop().create_task(_pump())


async def spawn_delegate_session(build_args, cwd, manifest, register, env=None,
                                 publish=None, on_first_turn=None):
    """S53 in production: a NEW claude session Shadow delegates into.

    Headless twin of a pane: its own SessionRuntime, registered in the same
    registry the say chain uses, observer attached, first turn = the
    enriched manifest. The transcript lands in ~/.claude/projects.

    IT IS NOT SPAWNED IN PLAN MODE, whatever this docstring said until
    2026-09-16. It claimed "spawned in PLAN mode (v1 safety: real turns,
    visible work, no unsupervised writes -- acting delegates need an explicit
    founder grant)", and that stopped being true when the permission-inherit
    change landed: `build_args` is app._worker_args, whose mode comes from
    providers.effective_permission_mode(load_settings()["permission_mode"])
    -- the founder's own setting, clamped, not a literal "plan". A founder in
    acceptEdits gets a delegate that edits. The docstring was describing a
    safety property the code had stopped providing, which is worse than
    describing none: it is the sentence someone would have cited when asking
    whether a worker could write.

    What DOES cap a worker is the autonomy level, and only downward: L0/L1/L2
    clamp it to `plan` through app._autonomy_ceiling, L3 leaves the founder's
    mode alone. See mission_engine's autonomy section.

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
        # THE TURN THE WORKER HAS JUST BEGUN (founder, 2026-09-18). This is
        # the first instant at which a worker provably exists and its turn is
        # painting -- the same frame that publishes the chat, ~1s after the
        # manifest went out. Earlier than this (at admission, or on the line
        # before the spawn) the card would claim a turn while nothing was
        # running, which the founder has ruled must read 0; later than this
        # leaves the card at 0 for the whole of the longest turn of the
        # mission. Best-effort, like every other line in this hook: naming a
        # turn is never worth a failed spawn.
        if on_first_turn is not None:
            try:
                on_first_turn()
            except Exception:           # noqa: BLE001 -- never fail a spawn
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

#: async (check, evidence, outcome) -> shadow_judge.Verdict | None. Injected
#: from app at startup for the same reason as the two above. None means no
#: judging happens and a `judge` row simply stays unmet, which is the
#: behaviour every install had before D-SH-1.
DEFAULT_JUDGE = {"fn": None}


def set_default_provisioner(fn):
    DEFAULT_PROVISIONER["fn"] = fn


def set_default_decider(fn):
    DEFAULT_DECIDER["fn"] = fn


def set_default_judge(fn):
    DEFAULT_JUDGE["fn"] = fn


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
                        >= mission_engine.max_running():
                    mission_engine.MissionScheduler(store).start(mid)
                    return
                prov = provisioner or DEFAULT_PROVISIONER["fn"]
                m = store.load(mid)
                if prov and m and m.get("target_mode") == "new" \
                        and not m.get("target_session"):
                    eng = mission_engine.MissionEngine(
                        store, None, None, None,
                        # same reason as the promote path: the criteria are
                        # decided before the spawner says the first word
                        decider=DEFAULT_DECIDER["fn"])
                    await eng.provision_target(mid, prov)
                    remember_delegate_pid(store, mid)
                # ...and the founder may have ended it while that ran
                if _ended_during_provision(store, mid):
                    return
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
                # ── A FAULT BEFORE THE WORKER EXISTS IS NOT A FAILURE ────
                # (founder, 2026-09-17; mission m-b3eefc51a768.)
                #
                # A pre-launch fault means NO WORKER WAS EVER SPAWNED --
                # target_session is still None and turns_used is 0 -- so there
                # is nothing whose outcome `failed` could be describing. The
                # live case was a stale write: booting the task's Shadow chat
                # stamped the record while provisioning held an older copy, and
                # a bookkeeping collision became a FAILED mission the founder
                # had to explain to themselves. That is the same principle
                # _infra_exit was written for: "a fault in Shadow decided a
                # mission's fate WITHOUT ONCE CONSULTING THE WORK."
                #
                # _infra_exit itself cannot be used here: it parks at `blocked`,
                # and TRANSITIONS lists `blocked` under `running` only -- not
                # under brief_confirm or queued. Rather than widen the state
                # machine for a pre-launch fault, the mission is left in the
                # state it is already in and made STARTABLE again.
                #
                # WHICH IS WHY start_requested_at IS CLEARED, and the reason
                # this is not a return to the bug test_shadow_start_failure.py
                # pins. That bug was a DEAD ROW: brief_confirm with the stamp
                # set, which the list draws as QUEUED with no Start button and
                # no record of why. Clearing the stamp is what makes the row
                # READY again, and the ledger carries the reason. The founder
                # gets a task they can start, not a task that died.
                #
                # THE ORPHANED-RUNNING ARM IS UNTOUCHED: a worker DID exist and
                # is gone, so that mission genuinely has no road left and keeps
                # the terminal state, the note and the behaviour it has always
                # had.
                if orphaned:
                    store.transition(mm["id"], "failed",
                                     "provision/admit failed: %s"
                                     % str(exc)[:200])
                elif mm and mm["state"] in ("brief_confirm", "queued"):
                    try:
                        fresh = store.load(mm["id"])
                        if fresh is not None \
                                and fresh.get("start_requested_at"):
                            fresh["start_requested_at"] = None
                            store.save(fresh)
                    except Exception:   # noqa: BLE001 -- ledger it regardless
                        pass
                    shadow_ledger.append("missions", {
                        "mission_id": mm["id"], "state": mm["state"],
                        "note": "provision/admit failed BEFORE any worker "
                                "existed, so the task is startable again, not "
                                "failed: %s" % str(exc)[:200]})
            except Exception:
                pass

    asyncio.get_event_loop().create_task(go())
    return {"accepted": True, "mission_id": mid,
            "note": "provisioning + admission in background; poll the "
                    "missions list"}
