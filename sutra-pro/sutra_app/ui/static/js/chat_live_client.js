/* chat_live_client.js - the page's side of one chat's live turn: it joins the intake and the store to the network (work package STR-9; streaming design D201,
   D202, D207, D219, D220, D221; docs/design/streaming/architecture.md "Frontend store and layering", "Open the page mid-turn, second tab, reconnect").

   The transport is the page's own SutraEvents handle (an EventSource: the browser frames the byte stream, so a frame that arrives in pieces or several in one read
   reaches here whole and in order). This file does what is left: it feeds each `chat.live` frame to the intake, applies what comes out to the store, reads the turn's
   snapshot (GET /api/chats/{sid}/turn) when the intake says a frame was missed, on every reconnect and while the stream is down, holds back the stored reply of a
   live turn until its terminal event (so the row settles in place), runs one timer while a turn is active, and stops all of it in close().

     create({sid, api, onChange, onRelease, onTerminal, now, timers, retryMs})   -> client
         state()                    the store's state
         dispatch(action)           apply an action (the composer's send, accepted, stop...) and tell onChange
         frame(raw)                 one `chat.live` frame (the page's onEvent): intake, store; a hole starts a snapshot; a terminal event releases the held rows
         partial(raw, opts)         one `chat.partial` frame (the flag-off direct chat, an AI worker): through fromPartial
         snapshot()                 GET /api/chats/{sid}/turn and apply it, with the frames that waited. Single flight; a failure is retried while a turn is active.
                                    Resolves to whether a turn was seeded; never rejects.
         reconnect()                the stream (re)connected, or `server.resync`: the same sequence as a hole, with no wait
         setPolling(on)             the stream is down and the page polls: the snapshot is read every second and the label says so
         offer(rows)                the rows the page may show: a stored reply of a live turn is held back (and kept), the rest is returned as it is
         release()                  let the held rows go: -> rows (onRelease gets them at a terminal event; onTerminal(turn) says an ended turn is waiting for its stored reply)
         tick()                     one second passed (the timer calls it): the clock for labels, stall detection, the stale-hold valve
         holds(messageId, attempt)  see ChatLiveStore.holds
         view()                     {turn, label, activity, note, polling, canStop, elapsedMs} for the view and the buttons
         close()                    stop the timer and every pending retry; later calls are no-ops

   Timers are injectable (`timers` {set, clear, setInterval, clearInterval}) so node tests drive them. A classic script with ONE global, ChatLiveClient; in node it is
   module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const need = (name, file) => {
    if (root[name]) return root[name];
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") return require("./" + file);
    return null;
  };
  const Events = () => need("ChatLiveEvents", "chat_live_events.js");
  const Store = () => need("ChatLiveStore", "chat_live_store.js");

  const RETRY_MS = 1500;
  const MAX_RETRIES = 6;
  const POLL_MS = 1000;
  const RESYNC_GAP_MS = 5000;               // a stalled page asks for a snapshot at most this often

  function create(options) {
    const o = isObj(options) ? options : {};
    const E = Events();
    const S = Store();
    const sid = typeof o.sid === "string" ? o.sid : "";
    const api = o.api;
    const clock = typeof o.now === "function" ? o.now : () => Date.now();
    const timers = isObj(o.timers) ? o.timers : {
      set: (fn, ms) => root.setTimeout(fn, ms), clear: id => root.clearTimeout(id),
      setInterval: (fn, ms) => root.setInterval(fn, ms), clearInterval: id => root.clearInterval(id),
    };
    const retryMs = Number.isFinite(o.retryMs) ? o.retryMs : RETRY_MS;
    const changed = () => { if (typeof o.onChange === "function") o.onChange(); };
    const intake = E.createIntake({sid});
    const base = "/api/chats/" + encodeURIComponent(sid);
    let state = S.create(sid);
    let closed = false;
    let ticker = null;
    let flight = null;                       // the snapshot read in progress (a promise)
    let again = false;                       // another was asked for while one was in flight
    let retryTimer = null;
    let retries = 0;
    let pollTimer = null;
    let polling = false;
    let lastResync = -Infinity;
    let told = "";                           // the ending onTerminal was last called for

    const apply = action => { state = S.reduce(state, Object.assign({now: clock()}, action)); };
    const active = () => S.active(state);

    function ensureTicker() {
      if (closed) return;
      if (active() && ticker === null) ticker = timers.setInterval(() => tick(), 1000);
      else if (!active() && ticker !== null) { timers.clearInterval(ticker); ticker = null; }
    }

    function dispatch(action) {
      if (closed) return state;
      apply(action);
      ensureTicker();
      changed();
      return state;
    }

    // Release the rows held while the turn ran: a terminal event, a snapshot that says nothing runs, or too long a silence.
    function release() {
      const rows = state.stash;
      if (rows.length === 0) return [];
      apply({type: "release"});
      return rows;
    }

    function afterTerminal() {
      const rows = release();
      if (rows.length > 0 && typeof o.onRelease === "function") o.onRelease(rows);
      const t = state.turn;
      if (t !== null && S.terminal(t.phase) && told !== t.generationId + ":" + t.attemptNo + ":" + t.phase) {          // once per ending
        told = t.generationId + ":" + t.attemptNo + ":" + t.phase;
        if (typeof o.onTerminal === "function") o.onTerminal(t);
      }
    }

    function frame(raw) {
      if (closed) return;
      const actions = intake.push(raw);
      if (actions.length === 0) return;
      let hole = false;
      actions.forEach(a => {
        apply(a);
        if (a.type === "gap") hole = true;
      });
      ensureTicker();
      if (state.turn !== null && S.terminal(state.turn.phase)) afterTerminal();
      changed();
      if (hole) snapshot();
    }

    function partial(raw, opts) {
      if (closed) return false;
      const actions = E.fromPartial(raw, {sid, cumulative: isObj(opts) && opts.cumulative === true});
      if (actions.length === 0) return false;
      const before = state;
      actions.forEach(a => apply(a));
      ensureTicker();
      if (state !== before) changed();
      return state !== before;
    }

    function scheduleRetry() {
      if (closed || retryTimer !== null || !active() || retries >= MAX_RETRIES) return;
      retries += 1;
      retryTimer = timers.set(() => { retryTimer = null; snapshot(); }, retryMs * Math.min(retries, 4));
    }

    async function read() {
      if (!api || typeof api.get !== "function") return false;
      apply({type: "resync"});
      intake.beginSnapshot();
      changed();
      let snap;
      try {
        snap = await api.get(base + "/turn");
      } catch (e) {
        intake.failSnapshot();
        scheduleRetry();
        return false;
      }
      if (closed) return false;
      retries = 0;
      const actions = intake.applySnapshot(snap);
      let seeded = false;
      let hole = false;
      actions.forEach(a => {
        apply(a);
        if (a.type === "snapshot") seeded = true;
        if (a.type === "gap") hole = true;
      });
      if (actions.length === 0) apply({type: "snapshot.none"});
      ensureTicker();
      if (state.turn !== null && S.terminal(state.turn.phase)) afterTerminal();
      else if (!active()) afterTerminal();
      changed();
      if (hole) again = true;
      return seeded;
    }

    function snapshot() {
      if (closed) return Promise.resolve(false);
      if (flight !== null) { again = true; return flight; }
      flight = read().then(r => r, () => false).then(r => {
        flight = null;
        if (again && !closed) { again = false; return snapshot(); }
        return r;
      });
      return flight;
    }

    function reconnect() {
      if (closed) return Promise.resolve(false);
      lastResync = clock();
      return snapshot();
    }

    function setPolling(on) {
      if (closed) return;
      const next = on === true;
      if (next === polling) return;
      polling = next;
      if (polling && pollTimer === null) pollTimer = timers.setInterval(() => { if (active()) snapshot(); }, POLL_MS);
      if (!polling && pollTimer !== null) { timers.clearInterval(pollTimer); pollTimer = null; }
      changed();
    }

    function tick() {
      if (closed) return;
      const now = clock();
      apply({type: "tick", now});
      if (active()) {
        const a = S.activity(state, now);
        if (a.kind === "stalled" && a.label === "Live updates paused" && now - lastResync >= RESYNC_GAP_MS) { lastResync = now; snapshot(); }
        if (S.stale(state, now)) { afterTerminal(); snapshot(); }
      } else ensureTicker();
      ensureTicker();
      changed();
    }

    // The rows a page may show now. A stored reply of the live turn is kept back until its terminal event; the page asks again with the released rows.
    function offer(rows) {
      const list = Array.isArray(rows) ? rows : [];
      const show = [];
      list.forEach(row => {
        if (isObj(row) && row.role === "agent" && S.holds(state, row.turn, row.attempt === undefined || row.attempt === null ? undefined : row.attempt)) apply({type: "message", row});
        else show.push(row);
      });
      return show;
    }

    function view() {
      const now = clock();
      const turn = state.turn;
      const act = S.activity(state, now);
      let label = S.label(state, now);
      if (polling && turn !== null && !S.terminal(turn.phase) && turn.phase !== "sending") label = "Live updates paused, checking every second";
      return {turn, settled: state.settled, label, activity: act, note: S.streamNote(state), polling, canStop: S.canStop(state), elapsedMs: S.elapsed(state, now), gap: state.gap,
        unsupported: state.unsupported, resyncing: state.resyncing};
    }

    function close() {
      if (closed) return;
      closed = true;
      if (ticker !== null) { timers.clearInterval(ticker); ticker = null; }
      if (pollTimer !== null) { timers.clearInterval(pollTimer); pollTimer = null; }
      if (retryTimer !== null) { timers.clear(retryTimer); retryTimer = null; }
      intake.reset();
    }

    return {state: () => state, dispatch, frame, partial, snapshot, reconnect, setPolling, offer, release, tick, view, close, holds: (m, a) => S.holds(state, m, a),
      isClosed: () => closed, timersOpen: () => (ticker !== null ? 1 : 0) + (pollTimer !== null ? 1 : 0) + (retryTimer !== null ? 1 : 0)};
  }

  const ChatLiveClient = {create, POLL_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatLiveClient;
  else root.ChatLiveClient = ChatLiveClient;
})(globalThis);
