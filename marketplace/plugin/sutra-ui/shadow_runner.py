"""Mounts the mission engine in the app process (GAP-AUDIT rows 2-3).

The engine (mission_engine.py) was fully tested against mocks; this module
is the missing binding: a per-mission asyncio task whose sayer is the SAME
validated-say function the HTTP endpoint uses, whose waiter listens to the
runtime's internal _turn_boundary frames, and whose reader is the existing
transcript reader. Plus the watcher: one observer per runtime that turns
error signals into rescue feed items and the dot-badge count.
"""
import asyncio

import mission_engine
import session_reader
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
#: session_id -> rolling window of STREAMED text (what the app actually saw;
#: transcript files lag or, for fakes, never exist -- the stream is the truth)
_RECENT_TEXT = {}
_RECENT_CAP = 20000

BOUNDARY_TIMEOUT_S = 300   # delegates in a governance-heavy repo run long turns


def attach_observer(session_id, rt):
    """Idempotent per runtime: pushes boundary frames into the per-session
    queue (for waiters) and emits rescue feed items on errors (watcher)."""
    if id(rt) in _OBSERVED:
        return
    _OBSERVED.add(id(rt))
    q = _BOUNDARIES.setdefault(session_id, asyncio.Queue())

    def observer(frame):
        t = frame.get("type")
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
        # live stream first (authoritative for what the pane showed), disk
        # transcript appended when it exists
        live = _RECENT_TEXT.get(mission["target_session"], "")
        doc = session_reader.read_session(mission["target_session"]) or {}
        import json as _json
        return (live + " " + _json.dumps(doc))[-40000:]

    return sayer, waiter, reader


def start_mission(mid, validated_say, verifier=None):
    """Admit + launch the loop task. Returns the (possibly queued) mission."""
    store = mission_engine.MissionStore()
    sched = mission_engine.MissionScheduler(store)
    m = sched.start(mid)
    if m["state"] != "running":
        return m          # queued: launched later by on_terminal promotion
    _launch(mid, validated_say, verifier)
    return m


def _launch(mid, validated_say, verifier):
    if mid in RUNNING and not RUNNING[mid].done():
        return
    store = mission_engine.MissionStore()
    sayer, waiter, reader = make_bindings(validated_say)
    engine = mission_engine.MissionEngine(store, sayer, waiter, reader,
                                          verifier)

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
            drt = DELEGATES.pop(m.get("target_session"), None)
            if drt is not None:
                drt.kill_group()   # a terminal mission's delegate dies with it
                drt.clear()
            mission_engine.emit_mission_feed(
                m, "info" if m["state"] == "done" else "needs_decision",
                "mission %s" % m["state"])
            promoted = mission_engine.MissionScheduler(store).on_terminal(mid)
            if promoted is not None:
                _launch(promoted["id"], validated_say, verifier)
        elif m and m.get("pause_reason"):
            mission_engine.emit_mission_feed(
                m, "needs_decision", m.get("pause_reason"))
        shadow_ledger.append("actions", {
            "mission_id": mid, "kind": "stop" if not m else m["state"],
            "summary": "runner finished (%s)"
                       % (m["state"] if m else "unknown")})

    RUNNING[mid] = asyncio.get_event_loop().create_task(run())


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
    return hit


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

    # THE PUMP (found by the first real flight): panes have a websocket loop
    # consuming their TurnQueue; a headless delegate has nobody -- says sat
    # queued forever and every boundary wait timed out. This is the delegate's
    # loop: nudge -> dequeue -> send -> demux (which fires _turn_boundary to
    # the waiters).
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

    asyncio.get_event_loop().create_task(_pump())
    shadow_ledger.append("actions", {
        "mission_id": None, "kind": "spawn",
        "summary": "delegate session %s spawned (plan mode)" % sid})
    return sid


def start_mission_async(mid, validated_say, provisioner=None, verifier=None):
    """Second-flight fix: provisioning a delegate takes minutes; holding the
    HTTP request open let client timeouts CANCEL it mid-spawn. Admission and
    provisioning now run as an app task; the endpoint answers immediately and
    the mission file is the progress surface."""
    store = mission_engine.MissionStore()

    async def go():
        try:
            m = store.load(mid)
            if provisioner and m and m.get("target_mode") == "new" \
                    and not m.get("target_session"):
                eng = mission_engine.MissionEngine(store, None, None, None)
                await eng.provision_target(mid, provisioner)
            start_mission(mid, validated_say, verifier)
        except Exception as exc:
            try:
                mm = store.load(mid)
                if mm and mm["state"] not in mission_engine.TERMINAL:
                    store.transition(mid, "failed",
                                     "provision/admit failed: %s"
                                     % str(exc)[:200])
            except Exception:
                pass

    asyncio.get_event_loop().create_task(go())
    return {"accepted": True, "mission_id": mid,
            "note": "provisioning + admission in background; poll the "
                    "missions list"}
