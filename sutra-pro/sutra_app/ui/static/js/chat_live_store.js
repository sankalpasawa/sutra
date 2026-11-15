/* chat_live_store.js - the state of a live chat turn and the rules that move it (work package STR-8; streaming design D201 to D204, D217 to D222; the state
   machine of docs/design/streaming/architecture.md "Message state machine").

   Pure. `reduce(state, action)` returns the next state and never reads the clock (a `now` rides on every action that needs one) or touches the DOM or network.
   The page-side wiring (stream, snapshot, POSTs) is chat_live_client.js; the drawing is chat_live_view.js.

   State of one chat:  {sid, turn, settled, stash, gap, resyncing, unsupported, now}
   Turn:  {phase, source: "live" | "partial", clientId, generationId, messageId, attempt, attemptNo, provider, model, streamMode, idleLimitS, startedAt, lastEventAt, seq,
           heartbeat, blocks, earlier, backoff, stopQueued, stoppingAt, error, replyId, storedOrder, usage, switched, restarts, afterSideEffects, lost}
   Block: {id, type: "text" | "thinking" | "tool_use", kind, name, title, target, status: "open" | "ok" | "error" | "interrupted", text, isError, truncated, startTs, endTs}

   Phases: sending, accepted, connecting, running, backoff, stopping, done, stopped, failed. `resyncing` is a flag beside them, not a phase. A terminal phase never
   changes; a new send replaces the turn. An action that the table does not allow is ignored (`state.ignored` counts them, a dev build can look).

     create(sid)              the empty state
     reduce(state, action)    actions: send, accepted, adopt, send.failed, stop.pressed, stop.failed, event, snapshot, snapshot.none, gap, resync, tick, partial, message, release, clear, unsupported
     LEGAL                    the transition table, {from: [to, ...]}
     holds(state, messageId, attempt)   true while a live generation answers that owner line and has no terminal event (the stored reply is held back, D207, D219)
     activity(state, now)     {kind: "stalled" | "tool" | "writing" | "thinking" | "waiting" | "", label, detail} of a running turn (first match wins)
     label(state, now)        the one line that says where the turn is: "Starting Claude", "Reading src/x.py", "Stopping", "" when there is nothing to say
     canStop(state)           Stop does something now
     active(state)            a turn that has not ended
     elapsed(state, now)      ms since the turn began on this page (a real measurement)
     terminal(phase)

   Honest by construction: every label comes from an event the server sent or a clock this page read; nothing is estimated, no percentage exists.
   A classic script with ONE global, ChatLiveStore; in node it is module.exports. */
(function (root) {
  "use strict";

  const TERMINAL = Object.freeze({done: true, stopped: true, failed: true});
  // from -> to. `running -> connecting` and `connecting -> connecting` are lenient: the router may start a new attempt without saying the old one failed first.
  const LEGAL = Object.freeze({
    sending: ["accepted", "stopping", "failed"],
    accepted: ["connecting", "running", "backoff", "stopping", "done", "stopped", "failed"],
    connecting: ["connecting", "running", "backoff", "stopping", "done", "stopped", "failed"],
    running: ["running", "connecting", "backoff", "stopping", "done", "stopped", "failed"],
    backoff: ["connecting", "running", "stopping", "done", "stopped", "failed"],
    stopping: ["stopping", "stopped", "done", "failed"],
    done: [], stopped: [], failed: [],
  });
  const STALL_CLIENT_MS = 15000;           // no event of any kind for this long: "Live updates paused" (and the page asks for a snapshot)
  const STALL_BEAT_MS = 20000;             // a heartbeat that reports this much silence from the provider: "Still working, no output for N s"
  const STASH_MAX_AGE_MS = 20000;
  const KEEP_BLOCKS = 500;

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const num = v => (Number.isFinite(v) ? v : 0);
  const NAMES = Object.freeze({claude: "Claude", codex: "Codex", stub: "the demo provider"});
  const nameOf = p => (typeof p === "string" && Object.prototype.hasOwnProperty.call(NAMES, p) ? NAMES[p] : (typeof p === "string" && p !== "" ? p : "the model"));
  const terminal = phase => TERMINAL[phase] === true;

  const create = sid => ({sid: typeof sid === "string" ? sid : "", turn: null, settled: null, stash: [], gap: null, resyncing: false, unsupported: false, now: 0, ignored: 0});

  function blank(over) {
    return Object.assign({phase: "sending", source: "live", clientId: "", generationId: "", messageId: null, attempt: 1, attemptNo: 1, provider: "", model: "", streamMode: "",
      idleLimitS: null, startedAt: 0, lastEventAt: 0, seq: 0, heartbeat: null, blocks: [], earlier: [], backoff: null, stopQueued: false, stoppingAt: 0, error: null,
      replyId: null, storedOrder: [], usage: null, switched: null, restarts: 0, afterSideEffects: false, lost: false, endedAt: 0, beforeStop: "", stopSeen: false}, over || {});
  }

  const withTurn = (state, turn, extra) => Object.assign({}, state, {turn}, extra || {});
  const legal = (from, to) => Array.isArray(LEGAL[from]) && LEGAL[from].includes(to);

  // Move the turn's phase if the table allows it; returns the turn (unchanged phase when it does not).
  function go(turn, to) {
    if (turn.phase === to) return turn;
    return legal(turn.phase, to) ? Object.assign({}, turn, {phase: to}) : turn;
  }

  /* ---------------------------------------------------------------- blocks */
  const findBlock = (blocks, id) => blocks.findIndex(b => b.id === id);
  const replaceAt = (blocks, i, block) => { const out = blocks.slice(); out[i] = block; return out; };
  const newBlock = (id, over) => Object.assign({id, type: "text", kind: "other", name: "", title: "", target: "", status: "open", text: "", isError: false, truncated: false,
    startTs: "", endTs: ""}, over || {});

  function applyBlock(turn, ev) {
    const id = ev.blockId;
    if (id === null) return turn;
    const p = ev.payload;
    let blocks = turn.blocks;
    let i = findBlock(blocks, id);
    if (ev.type === "block.start") {
      const fresh = newBlock(id, {type: p.blockType !== "" ? p.blockType : "text", kind: p.kind || "other", name: p.name, startTs: ev.ts});          // a type this page does not know is kept: the view draws it as a plain line
      if (i >= 0) blocks = replaceAt(blocks, i, Object.assign({}, blocks[i], {type: fresh.type, kind: fresh.kind, name: fresh.name || blocks[i].name}));
      else blocks = blocks.length >= KEEP_BLOCKS ? blocks : blocks.concat([fresh]);
      return Object.assign({}, turn, {blocks});
    }
    if (i < 0) {                                           // an event for a block this page never saw start: it is created (a page that joined mid-turn degrades, never throws)
      if (blocks.length >= KEEP_BLOCKS) return turn;
      blocks = blocks.concat([newBlock(id, {type: ev.type === "block.update" ? "tool_use" : "text", startTs: ev.ts})]);
      i = blocks.length - 1;
    }
    const cur = blocks[i];
    if (ev.type === "block.update") return Object.assign({}, turn, {blocks: replaceAt(blocks, i, Object.assign({}, cur, {title: p.title || cur.title, target: p.target || cur.target}))});
    if (ev.type === "block.delta") return Object.assign({}, turn, {blocks: replaceAt(blocks, i, Object.assign({}, cur, {text: cur.text + p.delta}))});
    if (ev.type === "block.end") {
      const next = Object.assign({}, cur, {status: p.status, isError: p.isError, truncated: p.truncated, endTs: ev.ts});
      if (p.text !== null && cur.text === "") next.text = p.text;
      return Object.assign({}, turn, {blocks: replaceAt(blocks, i, next)});
    }
    return turn;
  }

  // What the page kept of the attempt that was replaced: its blocks, who ran it and why it ended.
  function moveToEarlier(turn) {
    if (turn.blocks.length === 0 && !turn.backoff) return turn;
    const entry = {provider: turn.backoff ? turn.backoff.provider : turn.provider, reason: turn.backoff ? turn.backoff.reason : "", blocks: turn.blocks,
      afterSideEffects: turn.blocks.some(b => b.type === "tool_use" && (b.kind === "edit" || b.kind === "run")), lines: []};
    return Object.assign({}, turn, {earlier: turn.earlier.concat([entry]).slice(-5), blocks: []});
  }

  // A turn that ended without finishing: a tool or thinking block that never ended was interrupted; a text block is complete as far as it was shown.
  const interruptOpen = blocks => blocks.map(b => (b.status !== "open" ? b : Object.assign({}, b, {status: b.type === "text" ? "ok" : "interrupted"})));

  /* ---------------------------------------------------------------- one event */
  function applyEvent(state, ev, now) {
    let turn = state.turn;
    if (ev.type === "turn.accepted") {
      if (turn !== null && !terminal(turn.phase) && turn.generationId === "" && (turn.phase === "sending" || turn.phase === "stopping") && turn.clientId !== "" && turn.clientId === ev.payload.clientId) {
        turn = go(Object.assign({}, turn, {generationId: ev.gen, messageId: ev.messageId, attempt: ev.attempt, attemptNo: ev.payload.attemptNo, seq: ev.seq, lastEventAt: now}), "accepted");
        return withTurn(state, turn);
      }
      if (turn !== null && !terminal(turn.phase) && turn.generationId === ev.gen) return withTurn(state, Object.assign({}, turn, {seq: ev.seq, lastEventAt: now}));
      if (turn !== null && !terminal(turn.phase) && turn.phase !== "sending") return state;             // another generation while this one runs: not ours to show
      if (turn !== null && turn.phase === "sending") return state;                                       // another tab's turn while our POST is in flight: the server refuses one of them
      return withTurn(state, blank({phase: "accepted", clientId: ev.payload.clientId, generationId: ev.gen, messageId: ev.messageId, attempt: ev.attempt,
        attemptNo: ev.payload.attemptNo, startedAt: now, lastEventAt: now, seq: ev.seq}), {settled: null});
    }
    if (turn === null || turn.generationId !== ev.gen) return state;
    if (terminal(turn.phase)) return state;
    turn = Object.assign({}, turn, {seq: Math.max(turn.seq, ev.seq), lastEventAt: now, attempt: ev.attempt});
    const p = ev.payload;
    switch (ev.type) {
      case "turn.connecting":
        turn = go(Object.assign({}, turn, {provider: p.provider || turn.provider, model: p.model || turn.model, streamMode: p.streamMode || turn.streamMode}), "connecting");
        break;
      case "turn.started":
        turn = go(Object.assign({}, turn, {provider: p.provider || turn.provider, model: p.model || turn.model, streamMode: p.streamMode || turn.streamMode,
          idleLimitS: p.idleLimitS}), "running");
        break;
      case "attempt.failed":
        turn = go(Object.assign({}, turn, {backoff: {provider: p.provider || turn.provider, reason: p.reason, delayS: p.delayS, nextProvider: p.nextProvider, code: p.code, at: now}}), "backoff");
        break;
      case "attempt.restart":
        turn = moveToEarlier(turn);
        turn = go(Object.assign({}, turn, {attempt: p.attempt || turn.attempt, provider: p.provider || turn.provider, backoff: null, restarts: turn.restarts + 1,
          afterSideEffects: turn.afterSideEffects || p.afterSideEffects}), "running");
        break;
      case "block.start": case "block.update": case "block.delta": case "block.end":
        turn = applyBlock(turn, ev);
        if (turn.phase === "accepted" || turn.phase === "connecting") turn = go(turn, "running");       // a block can arrive before `started` was seen (a resumed stream)
        break;
      case "heartbeat":
        turn = Object.assign({}, turn, {heartbeat: {idleMs: p.idleMs, at: now}, idleLimitS: p.idleLimitS !== null ? p.idleLimitS : turn.idleLimitS});
        break;
      case "turn.stopping":
        turn = go(Object.assign({}, turn, {stoppingAt: turn.stoppingAt || now, stopSeen: true}), "stopping");
        break;
      case "turn.done": case "turn.stopped": case "turn.failed": {
        const to = ev.type === "turn.done" ? "done" : (ev.type === "turn.stopped" ? "stopped" : "failed");
        turn = go(turn, to);
        if (turn.phase !== to) return state;
        turn = Object.assign({}, turn, {replyId: p.replyId, attemptNo: p.attemptNo, storedOrder: p.storedOrder, usage: p.usage || null, switched: p.switched || null,
          error: to === "failed" ? {message: p.message, code: p.code} : null, endedAt: now, backoff: null,
          blocks: to === "done" ? turn.blocks : interruptOpen(turn.blocks)});
        return withTurn(state, turn, {resyncing: false, gap: null});
      }
      default:
        break;                                              // an unknown type: only its seq counts
    }
    return withTurn(state, turn);
  }

  /* ---------------------------------------------------------------- snapshot */
  const PHASE_OF = Object.freeze({accepted: "accepted", connecting: "connecting", running: "running", backoff: "backoff", stopping: "stopping", done: "done", stopped: "stopped", failed: "failed"});

  function fromSnapshot(snap, prev, now) {
    const phase = PHASE_OF[snap.state] || "running";
    const blocks = snap.blocks.map(b => newBlock(b.id, {type: ["text", "thinking", "tool_use"].includes(b.type) ? b.type : "text", kind: b.kind || "other", name: b.name, title: b.title,
      target: b.target, status: ["open", "ok", "error", "interrupted"].includes(b.status) ? b.status : "ok", text: b.text, isError: b.isError, truncated: b.truncated}));
    const earlier = snap.earlier.map(e => ({provider: e.provider, reason: e.reason, afterSideEffects: e.afterSideEffects, lines: e.lines,
      blocks: e.blocks.map(b => newBlock(b.id, {type: ["text", "thinking", "tool_use"].includes(b.type) ? b.type : "text", kind: b.kind || "other", name: b.name, title: b.title, target: b.target,
        status: b.status || "ok", text: b.text, isError: b.isError, truncated: b.truncated}))}));
    // Stop that was pressed (queued, or sent and not yet heard back as turn.stopping) stays Stopping when a snapshot of the same turn still says it runs: the server had not
    // handled the request when it was read, and turn.stopping follows. Only a terminal snapshot ends it.
    const base = prev && prev.generationId === snap.generationId ? prev : blank({startedAt: now - snap.elapsedMs});
    return Object.assign({}, base, {phase: (base.stopQueued || base.phase === "stopping") && !terminal(phase) ? "stopping" : phase, source: "live", clientId: snap.clientId || base.clientId, generationId: snap.generationId,
      messageId: snap.messageId, attempt: snap.attempt, attemptNo: snap.attemptNo, provider: snap.provider || base.provider, model: snap.model || base.model,
      streamMode: snap.streamMode || base.streamMode, idleLimitS: snap.idleLimitS, startedAt: base.startedAt || now - snap.elapsedMs, lastEventAt: now, seq: snap.seq, blocks, earlier,
      heartbeat: null});
  }

  /* ---------------------------------------------------------------- partial (flag off, and a worker: the cumulative or piecewise text of one reply) */
  function applyPartial(state, a, now) {
    let turn = state.turn;
    if (turn === null || terminal(turn.phase)) return state;
    if (a.done) return state;
    if (turn.source === "live" && turn.generationId !== "") return state;            // a live turn is told by its own events
    if (turn.messageId !== null && a.messageId !== null && a.messageId !== turn.messageId) return state;
    const last = turn.blocks[turn.blocks.length - 1];
    let blocks;
    if (last && !a.reset) {
      blocks = replaceAt(turn.blocks, turn.blocks.length - 1, Object.assign({}, last, {text: a.cumulative ? a.delta : last.text + a.delta}));
    } else {
      const n = turn.blocks.length === 0 ? 1 : Number(String(last.id).replace(/\D+/g, "")) + 1;
      blocks = [newBlock("p" + n, {text: a.delta})];                                  // a reset starts a fresh block: what was shown is void (the router tried again)
    }
    turn = Object.assign({}, turn, {source: "partial", streamMode: "snapshot", blocks, lastEventAt: now, messageId: turn.messageId !== null ? turn.messageId : a.messageId});
    turn = go(turn, "running");
    return withTurn(state, turn);
  }

  /* ---------------------------------------------------------------- the reducer */
  function reduce(state, action) {
    const s = isObj(state) ? state : create("");
    const a = isObj(action) ? action : {};
    const now = Number.isFinite(a.now) ? a.now : s.now;
    const base = now !== s.now ? Object.assign({}, s, {now}) : s;
    const ignore = () => Object.assign({}, base, {ignored: base.ignored + 1});
    const turn = base.turn;
    switch (a.type) {
      case "send":
        if (turn !== null && !terminal(turn.phase)) return ignore();
        return Object.assign({}, base, {turn: blank({phase: "sending", clientId: String(a.clientId || ""), startedAt: now, lastEventAt: now, messageId: Number.isInteger(a.messageId) ? a.messageId : null,
          attemptNo: Number.isInteger(a.attemptNo) ? a.attemptNo : 1}), settled: null, stash: [], gap: null, resyncing: false});
      case "accepted": {                                     // the 202 (or a duplicate answer) of the POST
        if (turn === null || terminal(turn.phase) || turn.clientId !== String(a.clientId || "")) return ignore();
        if (turn.generationId !== "" && a.generationId && turn.generationId !== a.generationId) return ignore();
        const next = go(Object.assign({}, turn, {generationId: turn.generationId || String(a.generationId || ""), messageId: Number.isInteger(a.messageId) ? a.messageId : turn.messageId,
          attemptNo: Number.isInteger(a.attemptNo) ? a.attemptNo : turn.attemptNo, lastEventAt: now,
          source: a.generationId || turn.generationId ? "live" : "partial"}), "accepted");
        return withTurn(base, next);
      }
      case "send.failed":
        if (turn === null || turn.clientId !== String(a.clientId || "") || (turn.phase !== "sending" && !(turn.phase === "stopping" && turn.generationId === ""))) return ignore();
        if (turn.stopQueued) return withTurn(base, null);                                 // Stop was pressed and nothing was ever accepted: nothing to stop, the turn is simply gone
        return withTurn(base, Object.assign({}, turn, {phase: "failed", error: {message: String(a.message || "That did not work. Try again."), code: String(a.code || "send")}, endedAt: now}));
      case "stop.pressed": {
        if (turn === null || terminal(turn.phase)) return ignore();
        if (turn.phase === "stopping") return base;
        const next = go(Object.assign({}, turn, {stopQueued: turn.generationId === "" && turn.messageId === null, stoppingAt: now, beforeStop: turn.phase}), "stopping");
        return next === turn ? ignore() : withTurn(base, next);
      }
      case "stop.failed": {                                   // the stop request itself failed (the app did not answer) and no turn.stopping came: Stop is offered again
        if (turn === null || turn.phase !== "stopping" || turn.stopSeen || turn.beforeStop === "") return ignore();
        return withTurn(base, Object.assign({}, turn, {phase: turn.beforeStop, beforeStop: "", stopQueued: false, stoppingAt: 0}));
      }
      case "adopt":                                          // a turn this page did not start and has no live frames for (the flag-off direct chat): shown with its Stop, filled by `partial`
        if (turn !== null && !terminal(turn.phase)) return ignore();
        return withTurn(base, blank({phase: "running", source: "partial", messageId: Number.isInteger(a.messageId) ? a.messageId : null, startedAt: now, lastEventAt: now, streamMode: "snapshot"}), {settled: null});
      case "event":
        return isObj(a.ev) ? applyEvent(base, a.ev, now) : ignore();
      case "snapshot": {
        const snap = a.snap;
        if (!isObj(snap)) return ignore();
        if (turn !== null && !terminal(turn.phase) && turn.generationId === "" && turn.clientId !== "" && snap.clientId !== turn.clientId) return Object.assign({}, base, {resyncing: false});
        if (turn !== null && terminal(turn.phase) && turn.generationId === snap.generationId) return Object.assign({}, base, {resyncing: false, gap: null});
        return withTurn(base, fromSnapshot(snap, turn && turn.generationId === snap.generationId ? turn : (turn && turn.generationId === "" && turn.clientId === snap.clientId ? turn : null), now),
          {resyncing: false, gap: null, settled: null});
      }
      case "snapshot.none": {
        if (turn === null || terminal(turn.phase) || turn.messageId === null || turn.generationId === "") return Object.assign({}, base, {resyncing: false, gap: null});
        // the server runs no turn any more and this page never heard it end: a reply is stored (or the app restarted); the stored line tells which ending it was
        return withTurn(base, Object.assign({}, turn, {phase: "done", lost: true, replyId: a.lastReplyId !== undefined ? a.lastReplyId : null, endedAt: now}), {resyncing: false, gap: null});
      }
      case "gap":
        return Object.assign({}, base, {gap: String(a.reason || "seq"), resyncing: turn !== null && !terminal(turn.phase) ? true : base.resyncing});
      case "resync":
        return Object.assign({}, base, {resyncing: turn !== null && !terminal(turn.phase)});
      case "unsupported":
        return Object.assign({}, base, {unsupported: true});
      case "tick": {
        const next = Object.assign({}, base);
        return next;
      }
      case "partial":
        return applyPartial(base, a, now);
      case "message": {                                       // a stored reply that arrived while its generation still runs: held back, not shown
        const row = a.row;
        if (!isObj(row) || !holds(base, row.turn, row.attempt)) return base;
        if (base.stash.some(r => r.id === row.id)) return base;
        return Object.assign({}, base, {stash: base.stash.concat([row]).slice(-20)});
      }
      case "release":                                         // the hold ends (a terminal event, a snapshot that says nothing runs, or too long a silence): the page takes the rows
        return base.stash.length === 0 ? base : Object.assign({}, base, {stash: []});
      case "clear": {                                         // the stored reply is on the page: the turn is over here; what the view needs to settle in place stays in `settled`
        if (turn === null) return base;
        return Object.assign({}, base, {turn: null, settled: {messageId: turn.messageId, attemptNo: turn.attemptNo, replyId: turn.replyId, storedOrder: turn.storedOrder, phase: turn.phase,
          error: turn.error, usage: turn.usage, switched: turn.switched, blocks: turn.blocks, provider: turn.provider, lost: turn.lost, clientId: turn.clientId}, gap: null, resyncing: false});
      }
      default:
        return ignore();
    }
  }

  /* ---------------------------------------------------------------- selectors */
  const active = state => isObj(state) && state.turn !== null && !terminal(state.turn.phase);

  // True while a live generation answers the owner line `messageId` (and the try `attempt`, when given) and has not ended: the stored reply is held back.
  function holds(state, messageId, attempt) {
    if (!isObj(state) || state.turn === null || terminal(state.turn.phase) || state.turn.source !== "live" || state.turn.generationId === "") return false;
    if (state.turn.messageId === null || state.turn.messageId !== messageId) return false;
    return attempt === undefined || attempt === null || attempt === state.turn.attemptNo;
  }

  const elapsed = (state, now) => (isObj(state) && state.turn !== null ? Math.max(0, num(now) - state.turn.startedAt) : 0);
  const secs = ms => Math.max(0, Math.round(num(ms) / 1000));

  function openBlock(turn, type) {
    for (let i = turn.blocks.length - 1; i >= 0; i -= 1) if (turn.blocks[i].status === "open" && turn.blocks[i].type === type) return turn.blocks[i];
    return null;
  }

  function toolLine(block) {
    const t = (block.title || "").trim();
    if (t !== "") return t;
    return "Using " + (block.name || "a tool");
  }

  // The state of a running turn in one word and one line. Stalled first (the page or the provider has said nothing for long), then a tool, then writing, thinking, waiting.
  function activity(state, now) {
    if (!isObj(state) || state.turn === null) return {kind: "", label: "", detail: ""};
    const turn = state.turn;
    const clock = Number.isFinite(now) ? now : state.now;
    if (terminal(turn.phase)) return {kind: "", label: "", detail: ""};
    const quiet = clock - turn.lastEventAt;
    const beat = turn.heartbeat;
    const silent = beat ? beat.idleMs + Math.max(0, clock - beat.at) : 0;
    if (turn.source === "live" && turn.phase === "running" && state.resyncing) return {kind: "stalled", label: "Catching up", detail: ""};
    if (turn.source === "live" && turn.phase === "running" && quiet >= STALL_CLIENT_MS) {
      return {kind: "stalled", label: "Live updates paused", detail: "Checking where the answer is"};
    }
    if (beat && silent >= STALL_BEAT_MS && turn.phase === "running") {
      const limit = turn.idleLimitS ? " The provider is stopped after " + turn.idleLimitS + " s without output." : "";
      return {kind: "stalled", label: "Still working, no output for " + secs(silent) + " s", detail: limit.trim()};
    }
    const tool = openBlock(turn, "tool_use");
    if (tool) return {kind: "tool", label: toolLine(tool), detail: tool.target && !tool.title.includes(tool.target) ? tool.target : ""};
    if (openBlock(turn, "text")) return {kind: "writing", label: "Writing", detail: ""};
    if (openBlock(turn, "thinking")) return {kind: "thinking", label: "Thinking", detail: ""};
    return {kind: "waiting", label: "Waiting for " + nameOf(turn.provider), detail: ""};
  }

  function label(state, now) {
    if (!isObj(state) || state.turn === null) return "";
    const turn = state.turn;
    const clock = Number.isFinite(now) ? now : state.now;
    switch (turn.phase) {
      case "sending": return "";
      case "accepted": return "Sent";
      case "connecting": return "Starting " + nameOf(turn.provider);
      case "running": return activity(state, clock).label;
      case "backoff": {
        const b = turn.backoff;
        if (!b) return nameOf(turn.provider) + " is being retried";
        const left = Number.isFinite(b.delayS) ? Math.max(0, Math.ceil(b.delayS - (clock - b.at) / 1000)) : null;
        const why = (b.reason || "").replace(/[.\s]+$/, "");
        const head = nameOf(b.provider) + " failed" + (why !== "" ? ": " + why : "");
        if (b.nextProvider && b.nextProvider !== b.provider) return head + ". Trying " + nameOf(b.nextProvider);          // another provider takes over: no wait to count
        return head + (left !== null ? ". Retrying in " + left + " s" : ". Retrying");
      }
      case "stopping": return "Stopping";
      default: return "";
    }
  }

  const canStop = state => isObj(state) && state.turn !== null && !terminal(state.turn.phase) && state.turn.phase !== "stopping";

  // How the page shows the model's own words: "the demo provider" and a provider that sends its answer whole are said so, never dressed up as streaming.
  function streamNote(state) {
    if (!isObj(state) || state.turn === null) return "";
    const t = state.turn;
    if (t.streamMode === "simulated") return "Demo provider, simulated";
    if ((t.streamMode === "activity" || t.streamMode === "final") && t.provider !== "") return nameOf(t.provider) + " sends its answer in one piece";
    return "";
  }

  // The stash is older than the hold is worth: the page releases it (the safety valve of D219).
  function stale(state, now) {
    return isObj(state) && state.stash.length > 0 && state.turn !== null && num(now) - state.turn.lastEventAt > STASH_MAX_AGE_MS;
  }

  const ChatLiveStore = {create, reduce, holds, activity, label, canStop, active, elapsed, streamNote, stale, terminal, nameOf, toolLine, LEGAL, TERMINAL, STALL_CLIENT_MS, STALL_BEAT_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatLiveStore;
  else root.ChatLiveStore = ChatLiveStore;
})(globalThis);
