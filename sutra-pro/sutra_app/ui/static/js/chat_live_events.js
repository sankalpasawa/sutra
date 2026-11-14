/* chat_live_events.js - the intake of a live chat turn: what a `chat.live` frame means before anything draws it (work package STR-8; streaming design D201, D202,
   D220, D221; docs/design/streaming/architecture.md "Event envelope").

   No DOM, no network, no store. One input (a frame as the page received it), one output (a list of actions for chat_live_store.js).

     createIntake({sid})      the intake of ONE chat; it remembers, per generation, the last `seq` it let through and, per block, how many characters it has seen
         push(raw)            -> Action[]. A frame is checked (envelope, version, conversation, bounds), de-duplicated by (generation_id, seq), and checked
                              for a hole: a `seq` that skips ahead, a text piece whose `offset` is not the length already shown, or a first frame that is not
                              seq 1 gives [{type: "gap", reason}] and the intake buffers every later frame until applySnapshot. A frame that is fine gives
                              [{type: "event", ev}]; an unknown `type` is let through (the store ignores it) so its seq is still counted.
         beginSnapshot()      start buffering (the page is about to read GET /api/chats/{sid}/turn)
         applySnapshot(snap)  -> Action[]. snap is the answer of that route: {live: false, ...} gives [{type: "snapshot.none", ...}]; else [{type: "snapshot", snap}]
                              followed by the buffered frames newer than snap.seq, in order (older ones are dropped: the snapshot holds them). Buffering ends.
         failSnapshot()       the read failed: keep buffering (bounded); the page tries again
         reset()              forget every generation (the page shows another chat)
         state()              {buffering, generations}
     fromPartial(raw, {sid, cumulative})   a `chat.partial` of this chat as [{type: "partial", sid, messageId, delta, cumulative, reset, done}] or [] (D221)
     cpLen(text)              the length of a string in code points, the unit of `offset` on the wire (Python counts characters, not UTF-16 units)
     VERSION, LIMITS

   Every string from the wire is cut to a bound here; the store and the view trust the bounds, and escape what they draw. A classic script with ONE global,
   ChatLiveEvents; in node it is module.exports. */
(function (root) {
  "use strict";

  const VERSION = 1;
  const LIMITS = Object.freeze({delta: 16384, text: 200000, title: 200, short: 500, blocks: 500, buffered: 2000, generations: 8});
  const TYPES = Object.freeze(["turn.accepted", "turn.connecting", "turn.started", "attempt.failed", "attempt.restart", "block.start", "block.update", "block.delta",
    "block.end", "heartbeat", "turn.stopping", "turn.done", "turn.stopped", "turn.failed"]);
  const TERMINAL = Object.freeze({"turn.done": true, "turn.stopped": true, "turn.failed": true});

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const str = (v, max) => (typeof v === "string" ? (v.length > max ? v.slice(0, max) : v) : "");
  const int = v => (Number.isInteger(v) ? v : null);

  // The length in code points: a surrogate pair is ONE character, as it is in the server's count.
  function cpLen(text) {
    const s = typeof text === "string" ? text : "";
    let n = 0;
    for (let i = 0; i < s.length; i += 1) {
      const c = s.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
        const d = s.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) i += 1;
      }
      n += 1;
    }
    return n;
  }

  // The payload of an event, cut and typed. Only the fields the store reads are kept.
  function payloadOf(type, p) {
    const o = isObj(p) ? p : {};
    switch (type) {
      case "turn.accepted": return {clientId: str(o.client_id, 64), attemptNo: int(o.attempt_no) || 1};
      case "turn.connecting": return {provider: str(o.provider, 40), model: str(o.model, 100), streamMode: str(o.stream_mode, 20)};
      case "turn.started": return {provider: str(o.provider, 40), model: str(o.model, 100), streamMode: str(o.stream_mode, 20),
        idleLimitS: Number.isFinite(o.idle_limit_s) ? o.idle_limit_s : null};
      case "attempt.failed": return {provider: str(o.provider, 40), code: str(o.code, 60), reason: str(o.reason, LIMITS.short), action: str(o.action, 40),
        delayS: Number.isFinite(o.delay_s) ? o.delay_s : null, nextProvider: str(o.next_provider, 40)};
      case "attempt.restart": return {attempt: int(o.attempt), provider: str(o.provider, 40), afterSideEffects: o.after_side_effects === true};
      case "block.start": return {blockType: str(o.type, 20), kind: str(o.kind, 20), name: str(o.name, LIMITS.title)};
      case "block.update": return {title: str(o.title, LIMITS.title), target: str(o.target, LIMITS.title)};
      case "block.delta": return {delta: str(o.delta, LIMITS.delta), offset: int(o.offset), size: typeof o.delta === "string" ? o.delta.length : 0};
      case "block.end": return {status: ["ok", "error", "interrupted"].includes(o.status) ? o.status : "ok", isError: o.is_error === true, truncated: o.truncated === true,
        text: typeof o.text === "string" ? str(o.text, LIMITS.text) : null, size: int(o.size)};
      case "heartbeat": return {idleMs: Number.isFinite(o.idle_ms) ? o.idle_ms : 0, idleLimitS: Number.isFinite(o.idle_limit_s) ? o.idle_limit_s : null};
      case "turn.done": return {replyId: int(o.message_id_reply), attemptNo: int(o.attempt_no) || 1, storedOrder: storedOrder(o.stored_order),
        textLen: int(o.text_len), usage: isObj(o.usage) ? o.usage : null, switched: isObj(o.switched) ? o.switched : null};
      case "turn.stopped": return {replyId: int(o.message_id_reply), attemptNo: int(o.attempt_no) || 1, storedOrder: storedOrder(o.stored_order), exit: str(o.exit, 40)};
      case "turn.failed": return {replyId: int(o.message_id_reply), attemptNo: int(o.attempt_no) || 1, storedOrder: storedOrder(o.stored_order),
        message: str(o.message, LIMITS.short * 2), code: str(o.code, 60)};
      default: return {};
    }
  }

  const storedOrder = v => (Array.isArray(v) ? v.slice(0, LIMITS.blocks * 4).filter(x => typeof x === "string").map(x => x.slice(0, 40)) : []);

  // Validate one frame. Returns the event, or {drop: why}: why "other" (not this chat, not an object) is silent, "version" and "oversize" are not.
  function check(raw, sid) {
    if (!isObj(raw)) return {drop: "other"};
    if (!Number.isInteger(raw.v)) return {drop: "other"};
    if (raw.conversation_id !== sid) return {drop: "other"};
    if (raw.v > VERSION) return {drop: "version"};
    if (typeof raw.type !== "string" || typeof raw.generation_id !== "string" || raw.generation_id === "") return {drop: "other"};
    if (!Number.isInteger(raw.seq) || raw.seq < 1) return {drop: "other"};
    const p = isObj(raw.payload) ? raw.payload : {};
    if (raw.type === "block.delta" && typeof p.delta === "string" && p.delta.length > LIMITS.delta) return {drop: "oversize", generation: raw.generation_id};
    const known = TYPES.includes(raw.type);
    return {ev: {gen: raw.generation_id, seq: raw.seq, type: raw.type, known, attempt: int(raw.attempt) || 1, messageId: int(raw.message_id),
      blockId: typeof raw.block_id === "string" ? raw.block_id.slice(0, 40) : null, ts: str(raw.ts, 40), terminal: TERMINAL[raw.type] === true,
      payload: known ? payloadOf(raw.type, p) : {}}};
  }

  function createIntake(options) {
    const o = isObj(options) ? options : {};
    const sid = typeof o.sid === "string" ? o.sid : "";
    const gens = new Map();                    // generation id -> last seq let through
    const seen = new Map();                    // "gen/block" -> characters (code points) shown
    let buffer = null;                         // frames held while a snapshot is read
    let versionNoted = false;

    const remember = gen => {
      gens.delete(gen);                        // re-insert: the map's order is the recency order
      while (gens.size >= LIMITS.generations) gens.delete(gens.keys().next().value);
    };
    const key = ev => ev.gen + "/" + ev.blockId;
    const forgetBlocks = gen => { for (const k of Array.from(seen.keys())) if (k.startsWith(gen + "/")) seen.delete(k); };

    // Judge one checked event against what has been seen: [] (a duplicate), [event action], or [gap action]. Does not advance anything on a gap.
    function admit(ev) {
      const last = gens.get(ev.gen);
      if (last === undefined) {
        if (ev.seq !== 1) return {gap: "first"};
      } else if (ev.seq <= last) {
        return {dup: true};
      } else if (ev.seq !== last + 1) {
        return {gap: "seq"};
      }
      if (ev.type === "block.delta" && ev.blockId !== null) {
        const have = seen.get(key(ev)) || 0;
        if (ev.payload.offset !== null && ev.payload.offset !== have) return {gap: "offset"};
      }
      return {ok: true};
    }

    function advance(ev) {
      remember(ev.gen);
      gens.set(ev.gen, ev.seq);
      if (ev.blockId === null) return;
      if (ev.type === "block.delta") seen.set(key(ev), (seen.get(key(ev)) || 0) + cpLen(ev.payload.delta));
      else if (ev.type === "block.end" && ev.payload.text !== null && !seen.has(key(ev))) seen.set(key(ev), cpLen(ev.payload.text));
    }

    function push(raw) {
      const c = check(raw, sid);
      if (c.drop === "version") {
        if (versionNoted) return [];
        versionNoted = true;
        return [{type: "unsupported", version: isObj(raw) ? raw.v : null}];
      }
      if (c.drop === "oversize") return buffer === null ? (buffering(), [{type: "gap", reason: "oversize"}]) : [];
      if (c.drop) return [];
      if (buffer !== null) {
        if (buffer.length >= LIMITS.buffered) buffer.shift();
        buffer.push(c.ev);
        return [];
      }
      const verdict = admit(c.ev);
      if (verdict.dup) return [];
      if (verdict.gap) { buffering(); buffer.push(c.ev); return [{type: "gap", reason: verdict.gap}]; }
      advance(c.ev);
      return [{type: "event", ev: c.ev}];
    }

    function buffering() { if (buffer === null) buffer = []; }

    function applySnapshot(snap) {
      const held = buffer || [];
      buffer = null;
      if (!isObj(snap)) return [];
      if (snap.live === false) {
        return [{type: "snapshot.none", lastReplyId: int(snap.last_reply_id), lastAttemptNo: int(snap.last_attempt_no)}];
      }
      const gen = str(snap.generation_id, 64);
      const seq = int(snap.seq);
      if (gen === "" || seq === null) return [];
      const blocks = (Array.isArray(snap.blocks) ? snap.blocks.slice(0, LIMITS.blocks) : []).filter(isObj).map(b => ({
        id: str(b.block_id, 40), type: str(b.type, 20), kind: str(b.kind, 20), name: str(b.name, LIMITS.title), status: str(b.status, 20),
        text: str(b.text, LIMITS.text), title: str(b.title, LIMITS.title), target: str(b.target, LIMITS.title), isError: b.is_error === true, truncated: b.truncated === true}));
      const earlier = (Array.isArray(snap.earlier) ? snap.earlier.slice(0, 20) : []).filter(isObj).map(e => ({provider: str(e.provider, 40), reason: str(e.reason, LIMITS.short),
        afterSideEffects: e.after_side_effects === true, lines: (Array.isArray(e.lines) ? e.lines : []).filter(x => typeof x === "string").slice(0, 20).map(x => x.slice(0, LIMITS.title)),
        blocks: (Array.isArray(e.blocks) ? e.blocks.slice(0, LIMITS.blocks) : []).filter(isObj).map(b => ({id: str(b.block_id, 40), type: str(b.type, 20), kind: str(b.kind, 20),
          name: str(b.name, LIMITS.title), status: str(b.status, 20), text: str(b.text, LIMITS.text), title: str(b.title, LIMITS.title), target: str(b.target, LIMITS.title),
          isError: b.is_error === true, truncated: b.truncated === true}))}));
      forgetBlocks(gen);
      remember(gen);
      gens.set(gen, seq);
      blocks.forEach(b => { if (b.type === "text") seen.set(gen + "/" + b.id, cpLen(b.text)); });
      const clean = {generationId: gen, messageId: int(snap.message_id), clientId: str(snap.client_id, 64), attempt: int(snap.attempt) || 1, attemptNo: int(snap.attempt_no) || 1,
        state: str(snap.state, 20), seq, provider: str(snap.provider, 40), model: str(snap.model, 100), streamMode: str(snap.stream_mode, 20),
        elapsedMs: Number.isFinite(snap.elapsed_ms) ? snap.elapsed_ms : 0, idleLimitS: Number.isFinite(snap.idle_limit_s) ? snap.idle_limit_s : null, blocks, earlier};
      const out = [{type: "snapshot", snap: clean}];
      held.filter(ev => ev.gen === gen).sort((a, b) => a.seq - b.seq).forEach(ev => {
        if (ev.seq <= gens.get(gen)) return;                 // the snapshot already holds it
        const verdict = admit(ev);
        if (verdict.dup) return;
        if (verdict.gap) { buffering(); out.push({type: "gap", reason: verdict.gap}); return; }
        advance(ev);
        out.push({type: "event", ev});
      });
      return out;
    }

    return {
      push,
      beginSnapshot: buffering,
      applySnapshot,
      failSnapshot: buffering,
      reset() { gens.clear(); seen.clear(); buffer = null; versionNoted = false; },
      state: () => ({buffering: buffer !== null, generations: gens.size, buffered: buffer === null ? 0 : buffer.length}),
    };
  }

  // chat.partial -> an action. The flag-off direct chat sends pieces ({delta, reset}); an AI worker sends its whole text so far with reset: true (`cumulative`).
  // A piece for another chat, or a frame with no text and no end, is nothing.
  function fromPartial(raw, options) {
    const o = isObj(options) ? options : {};
    const d = isObj(raw) && isObj(raw.data) ? raw.data : raw;
    if (!isObj(d) || typeof o.sid !== "string" || d.session_id !== o.sid) return [];
    const delta = str(d.delta, LIMITS.text);
    const done = d.done === true;
    if (delta === "" && d.reset !== true && !done) return [];
    return [{type: "partial", sid: o.sid, messageId: int(d.message_id), delta, cumulative: o.cumulative === true, reset: d.reset === true, done}];
  }

  const ChatLiveEvents = {createIntake, fromPartial, cpLen, check, VERSION, LIMITS, TYPES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatLiveEvents;
  else root.ChatLiveEvents = ChatLiveEvents;
})(globalThis);
