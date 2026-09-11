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
import time

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
#: runtimes already carrying our observer (identity-keyed)
_OBSERVED = set()
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
#: session_id -> rolling window of STREAMED text (what the app actually saw;
#: transcript files lag or, for fakes, never exist -- the stream is the truth)
_RECENT_TEXT = {}
_RECENT_CAP = 20000

#: session_id -> unix ts of the LAST frame of any kind (stall detection)
_LAST_FRAME_TS = {}
STALL_SECS = 240

#: a reasoning call is one short turn, not a work turn -- it must not be
#: allowed to stall the mission loop the way a real turn may
DECIDE_TIMEOUT_S = 90

BOUNDARY_TIMEOUT_S = 300   # delegates in a governance-heavy repo run long turns


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
    if id(rt) in _OBSERVED:
        return
    _OBSERVED.add(id(rt))
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
    """
    live = _RECENT_TEXT.get(session_id, "")
    doc = session_reader.read_session(session_id) or {}
    if doc:
        doc = dict(doc)
        doc["messages"] = evidence_messages(doc)
    return (live + " " + json.dumps(doc))[-40000:]


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

    async def waiter(mission):
        q = _BOUNDARIES.get(mission["target_session"])
        if q is None:
            return False
        try:
            await asyncio.wait_for(q.get(), BOUNDARY_TIMEOUT_S)
            return True
        except asyncio.TimeoutError:
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
        decider=DEFAULT_DECIDER["fn"])

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
            drt = DELEGATES.pop(m.get("target_session"), None)
            if drt is not None:
                drt.kill_group()   # a terminal mission's delegate dies with it
                drt.clear()
            mission_engine.emit_mission_feed(
                m, "info" if m["state"] == "done" else "needs_decision",
                "mission %s" % m["state"])
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
            # No feed item here on purpose: the escalation copy and its
            # dedupe key (which V5 R3 wants keyed on block reason + attempt)
            # belong to the slice that actually routes work into blocked.
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
    running with no live task pauses honestly; the founder resumes."""
    store = mission_engine.MissionStore()
    for m in store.list(states=("running",)):
        if m["id"] not in RUNNING:
            mm = store.transition(m["id"], "paused",
                                  "app restarted -- resume to continue")
            mm["pause_reason"] = "app_restart"
            store.save(mm)


def shutdown():
    """Cancel loop tasks; missions stay `running` on disk and recover_on_boot
    pauses them at next start (no state is lost, nothing is orphaned)."""
    for task in list(RUNNING.values()):
        task.cancel()
    RUNNING.clear()
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
        "summary": "attached to existing session %s (plan mode, --resume)"
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
%(checks)s

BUDGET
turn %(turns_used)s of %(max_turns)s

YOUR PREVIOUS INSTRUCTION
%(last_instruction)s

WHAT THE TARGET CHAT SAID BACK (most recent output)
%(last_response)s

Decide. Reply with ONE fenced json block and nothing else:

```json
{"action": "continue", "instruction": "<what to send into the chat next>",
 "reason": "<one short line: why this, now>"}
```

or, if you genuinely cannot make progress and the founder is needed:

```json
{"action": "ask_founder", "reason": "<what you need from the founder>"}
```

Rules for `instruction`: address the target chat directly, build on what it
actually said, and name the specific next thing you want. If it asked you a
question, answer it. If it is stuck or refusing, either unblock it with new
information or use ask_founder. Do not repeat your previous instruction.
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


def make_decider(build_args, cwd, timeout_s=DECIDE_TIMEOUT_S):
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
            "checks": "\n".join(
                "- [%s] (%s) %s" % ("x" if c.get("met") else " ",
                                    c.get("tier"), c.get("check"))
                for c in (context.get("checks") or [])) or "- (none)",
            "turns_used": context.get("turns_used"),
            "max_turns": context.get("max_turns"),
            "last_instruction": context.get("last_instruction") or "(none)",
            "last_response": context.get("last_response") or "(nothing yet)",
        }
        rt = srt.SessionRuntime()
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
            "record_evaluation", mission, results, done))
    m = engine.settle(mid)
    if m and m["state"] in mission_engine.TERMINAL:
        drt = DELEGATES.pop(m.get("target_session"), None)
        if drt is not None:
            drt.kill_group()
            drt.clear()
        mission_engine.emit_mission_feed(
            m, "info" if m["state"] == "done" else "needs_decision",
            "mission %s" % m["state"])
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
    shadow_ledger.append("actions", {
        "mission_id": None, "kind": "stop",
        "summary": "released attached session %s (founder took the wheel)"
                   % session_id})
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


async def spawn_delegate_session(build_args, cwd, manifest, register, env=None):
    """S53 in production: a NEW claude session Shadow delegates into.

    Headless twin of a pane: its own SessionRuntime, spawned in PLAN mode
    (v1 safety: real turns, visible work, no unsupervised writes -- acting
    delegates need an explicit founder grant), registered in the same
    registry the say chain uses, observer attached, first turn = the
    enriched manifest. The transcript lands in ~/.claude/projects, so the
    session appears in Chats and a pane can resume it.
    """
    import session_runtime as srt
    rt = srt.SessionRuntime()
    args = build_args()
    await rt.spawn(args, cwd, tuple(args), env=env)
    texts = []

    async def collect(frame):
        if frame.get("type") == "token":
            texts.append(frame.get("text") or "")

    await rt.send_user_frame(manifest)
    (sid, _t, got_result, err, _e) = await rt.demux_turn(collect, None)
    if not got_result or not sid:
        rt.kill_group()
        rt.clear()
        raise RuntimeError("delegate session failed to boot: %s" % (err,))
    register(sid, rt)
    attach_observer(sid, rt)
    DELEGATES[sid] = rt

    start_pump(rt, sid)
    shadow_ledger.append("actions", {
        "mission_id": None, "kind": "spawn",
        "summary": "delegate session %s spawned (plan mode)" % sid})
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
                start_mission(mid, validated_say, verifier)
            finally:
                _STARTING.discard(mid)
        except Exception as exc:
            try:
                mm = store.load(mid)
                # NEVER downgrade a healthy running mission (race fix: the
                # duplicate starter's failure is not the mission's failure)
                if mm and mm["state"] in ("brief_confirm", "queued"):
                    store.transition(mm["id"], "failed",
                                     "provision/admit failed: %s"
                                     % str(exc)[:200])
            except Exception:
                pass

    asyncio.get_event_loop().create_task(go())
    return {"accepted": True, "mission_id": mid,
            "note": "provisioning + admission in background; poll the "
                    "missions list"}
