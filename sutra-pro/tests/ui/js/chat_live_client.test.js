"use strict";
// ChatLiveClient (sutra_app/ui/static/js/chat_live_client.js): frames to the store, snapshots on a hole and on every reconnect, the held reply, polling, the timer and cleanup (STR-9).
// Run with: node --test tests/ui/js/chat_live_client.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const Client = require(path.join(JS, "chat_live_client.js"));

const SID = "cs_000000000abc";
const GEN = "gen00001";
const CID = "client-0001";

function fakeTimers() {
  const intervals = new Map();
  const timeouts = new Map();
  let id = 0;
  return {intervals, timeouts,
    set: (fn, ms) => { id += 1; timeouts.set(id, {fn, ms}); return id; }, clear: n => timeouts.delete(n),
    setInterval: (fn, ms) => { id += 1; intervals.set(id, {fn, ms}); return id; }, clearInterval: n => intervals.delete(n),
    runIntervals() { Array.from(intervals.values()).forEach(t => t.fn()); },
    runTimeouts() { const all = Array.from(timeouts.entries()); all.forEach(([n]) => timeouts.delete(n)); all.forEach(([, t]) => t.fn()); }};
}

function rig(handlers, extra) {
  const timers = fakeTimers();
  const clock = {t: 10000};
  const log = {changes: 0, released: [], terminals: [], gets: []};
  const api = {get: async p => { log.gets.push(p); const h = handlers && handlers[p]; if (h instanceof Error) throw h; return typeof h === "function" ? h() : h; }};
  const c = Client.create(Object.assign({sid: SID, api, now: () => clock.t, timers, retryMs: 10, onChange: () => { log.changes += 1; }, onRelease: rows => log.released.push(rows),
    onTerminal: t => log.terminals.push(t.phase)}, extra || {}));
  let seq = 0;
  const wire = (type, payload, block) => {
    seq += 1;
    const raw = {v: 1, id: GEN + ":" + seq, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq, ts: "t", type, payload: payload || {}};
    if (block) raw.block_id = block;
    c.frame(raw);
  };
  return {c, timers, clock, log, api, wire, seqTo: n => { seq = n; }};
}
const begin = r => { r.c.dispatch({type: "send", clientId: CID}); r.c.dispatch({type: "accepted", clientId: CID, generationId: GEN, messageId: 7, attemptNo: 1}); };
const tick = async () => { await new Promise(res => setImmediate(res)); await new Promise(res => setImmediate(res)); };
const SNAP = over => Object.assign({generation_id: GEN, message_id: 7, client_id: CID, attempt: 1, attempt_no: 1, state: "running", seq: 3, provider: "claude", model: "m", stream_mode: "tokens",
  elapsed_ms: 2000, idle_limit_s: 120, blocks: [{block_id: "b1", type: "text", kind: "other", name: "", status: "open", text: "abc"}], earlier: []}, over || {});
const textOf = r => r.c.state().turn.blocks.map(b => b.text).join("");

test("frames in order build the turn; a duplicate and another chat's frame change nothing", () => {
  const r = rig({});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.delta", {delta: "Hi", offset: 0}, "b1");
  assert.equal(textOf(r), "Hi");
  r.c.frame({v: 1, conversation_id: "cs_other", generation_id: GEN, seq: 5, type: "block.delta", payload: {delta: "x", offset: 2}, block_id: "b1"});
  r.c.frame({v: 1, conversation_id: SID, generation_id: GEN, seq: 4, type: "block.delta", payload: {delta: "Hi", offset: 0}, block_id: "b1"});         // seq 4 was already used
  assert.equal(textOf(r), "Hi");
});

test("several frames in one go and one frame at a time give the same turn", () => {
  const frames = (() => { const out = []; const mk = (seq, type, payload, block) => out.push({v: 1, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq, ts: "t", type, payload, block_id: block});
    mk(1, "turn.accepted", {client_id: CID, attempt_no: 1}); mk(2, "turn.started", {provider: "claude"}); mk(3, "block.start", {type: "text"}, "b1");
    mk(4, "block.delta", {delta: "ab", offset: 0}, "b1"); mk(5, "block.delta", {delta: "cd", offset: 2}, "b1"); return out; })();
  const one = rig({}); begin(one); frames.forEach(f => one.c.frame(f));
  const many = rig({}); begin(many); frames.slice().forEach(f => many.c.frame(JSON.parse(JSON.stringify(f))));
  assert.deepEqual(one.c.state().turn.blocks, many.c.state().turn.blocks);
  assert.equal(textOf(one), "abcd");
});

test("a hole reads the snapshot, applies it and the frames that waited, and the turn goes on without a repeated word", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: () => SNAP()});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  r.seqTo(3);
  r.wire("block.delta", {delta: "def", offset: 3}, "b1");             // seq 4 arrives, but seq 3 (the block start and its first piece) was lost: a hole
  await tick();
  assert.deepEqual(r.log.gets, ["/api/chats/" + SID + "/turn"]);
  assert.equal(r.c.state().turn.blocks.length, 1);
  assert.equal(textOf(r), "abcdef");                                  // the snapshot holds "abc" at seq 3; the frame that waited (seq 4) follows it exactly
});

test("a snapshot followed by the frames after it continues the text exactly", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: () => SNAP({seq: 5, blocks: [{block_id: "b1", type: "text", kind: "other", name: "", status: "open", text: "abcd"}]})});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.seqTo(5);
  r.wire("block.delta", {delta: "ef", offset: 4}, "b1");              // seq 6: a hole (seq 2 to 5 are missing)
  await tick();
  assert.equal(textOf(r), "abcdef");
  r.wire("block.delta", {delta: "gh", offset: 6}, "b1");              // seq 7 continues
  assert.equal(textOf(r), "abcdefgh");
});

test("reconnect always reads the snapshot (the page's own handle says so on every reconnect)", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: () => SNAP()});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  await r.c.reconnect();
  assert.equal(r.log.gets.length, 1);
  assert.equal(r.c.state().resyncing, false);
});

test("two snapshots asked for at once are one read, then one more", async () => {
  let n = 0;
  const r = rig({["/api/chats/" + SID + "/turn"]: () => { n += 1; return SNAP(); }});
  begin(r);
  const a = r.c.snapshot();
  const b = r.c.snapshot();
  await Promise.all([a, b]);
  assert.equal(n, 2);
});

test("a snapshot that says nothing runs ends a turn the page never heard finish, and releases the held reply", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: {live: false, last_reply_id: 9, last_attempt_no: 1}});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  assert.deepEqual(r.c.offer([{id: 9, role: "agent", turn: 7, attempt: 1, text: "answer"}]), []);
  assert.equal(r.c.state().stash.length, 1);
  await r.c.reconnect();
  assert.equal(r.c.state().turn.phase, "done");
  assert.equal(r.c.state().turn.lost, true);
  assert.equal(r.log.released.length, 1);
  assert.equal(r.log.released[0][0].id, 9);
  assert.deepEqual(r.log.terminals, ["done"]);
});

test("a failed snapshot is retried a bounded number of times while a turn is active, and never after close", async () => {
  const fail = Object.assign(new Error("down"), {code: "network"});
  const r = rig({["/api/chats/" + SID + "/turn"]: fail});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  await r.c.snapshot();
  assert.equal(r.timers.timeouts.size, 1);
  r.timers.runTimeouts();
  await tick();
  assert.equal(r.log.gets.length, 2);
  r.c.close();
  assert.equal(r.timers.timeouts.size, 0);
  assert.equal(await r.c.snapshot(), false);
  assert.equal(r.log.gets.length, 2);
});

test("a stored reply of the live turn is held until its end; the terminal event releases it; other rows pass", () => {
  const r = rig({});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  const rows = [{id: 3, role: "user", text: "hi"}, {id: 9, role: "agent", turn: 7, attempt: 1, text: "answer"}, {id: 2, role: "agent", turn: 1, attempt: 1, text: "old"}];
  assert.deepEqual(r.c.offer(rows).map(m => m.id), [3, 2]);
  assert.equal(r.log.released.length, 0);
  r.wire("turn.done", {message_id_reply: 9, attempt_no: 1, stored_order: []});
  assert.equal(r.log.released.length, 1);
  assert.equal(r.log.released[0][0].id, 9);
  assert.deepEqual(r.c.state().stash, []);
  assert.equal(r.log.terminals.length, 1);
  assert.equal(r.c.offer([{id: 9, role: "agent", turn: 7, attempt: 1}]).length, 1);          // after the end nothing is held
});

test("a retry's reply of attempt 2 is not held by attempt 1 and the first try's stored reply does not end the retry", () => {
  const r = rig({});
  r.c.dispatch({type: "send", clientId: CID, messageId: 7});
  r.c.dispatch({type: "accepted", clientId: CID, generationId: GEN, messageId: 7, attemptNo: 2});
  assert.equal(r.c.holds(7, 2), true);
  assert.equal(r.c.holds(7, 1), false);
  assert.equal(r.c.offer([{id: 8, role: "agent", turn: 7, attempt: 1}]).length, 1);
});

test("the timer runs only while a turn is active, labels get their clock from it, and a long silence asks for a snapshot (at most every 5 s)", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: () => SNAP()});
  assert.equal(r.timers.intervals.size, 0);
  begin(r);
  assert.equal(r.timers.intervals.size, 1);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  r.clock.t += 16000;
  r.timers.runIntervals();
  await tick();
  assert.equal(r.log.gets.length, 1);
  assert.equal(r.c.view().label, "Writing");                          // the snapshot answered: the turn is where the server says
  r.clock.t += 2000;
  r.timers.runIntervals();
  await tick();
  assert.equal(r.log.gets.length, 1);
  r.seqTo(3);                                                         // the snapshot was taken at seq 3
  r.wire("turn.done", {message_id_reply: 9, attempt_no: 1, stored_order: []});
  r.timers.runIntervals();
  assert.equal(r.timers.intervals.size, 0);
});

test("polling mode reads the snapshot every second and says so", async () => {
  const r = rig({["/api/chats/" + SID + "/turn"]: () => SNAP()});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  r.c.setPolling(true);
  assert.equal(r.c.view().label, "Live updates paused, checking every second");
  assert.equal(r.timers.intervals.size, 2);
  r.timers.runIntervals();
  await tick();
  assert.ok(r.log.gets.length >= 1);
  r.c.setPolling(false);
  assert.equal(r.timers.intervals.size, 1);
});

test("close stops every timer and ignores everything after it; a second close is fine", () => {
  const r = rig({});
  begin(r);
  r.c.setPolling(true);
  assert.ok(r.c.timersOpen() > 0);
  r.c.close();
  assert.equal(r.c.timersOpen(), 0);
  assert.equal(r.timers.intervals.size, 0);
  const changes = r.log.changes;
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.c.dispatch({type: "tick"});
  assert.equal(r.log.changes, changes);
  r.c.close();
});

test("partial frames (flag off) fill the turn through the adapter; another chat's and a late one do not", () => {
  const r = rig({});
  r.c.dispatch({type: "send", clientId: CID});
  r.c.dispatch({type: "accepted", clientId: CID, generationId: "", messageId: 7, attemptNo: 1});
  assert.equal(r.c.partial({session_id: SID, message_id: 7, delta: "Hel"}), true);
  r.c.partial({session_id: SID, message_id: 7, delta: "lo"});
  r.c.partial({session_id: "cs_other", message_id: 7, delta: "no"});
  assert.equal(textOf(r), "Hello");
  assert.equal(r.c.view().turn.streamMode, "snapshot");
});

test("view gives the label, the activity, the note and what the buttons need", () => {
  const r = rig({});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.connecting", {provider: "codex", stream_mode: "final"});
  const v = r.c.view();
  assert.equal(v.label, "Starting Codex");
  assert.equal(v.note, "Codex sends its answer in one piece");
  assert.equal(v.canStop, true);
});

test("a turn that failed while a snapshot was being read, and the snapshot says nothing runs, ends failed with its error (not as a quiet success)", async () => {
  let release;
  const r = rig({["/api/chats/" + SID + "/turn"]: () => new Promise(res => { release = res; })});
  begin(r);
  r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
  r.wire("turn.started", {provider: "claude"});
  const reading = r.c.snapshot();
  await tick();
  r.wire("turn.failed", {message: "The model stopped.", code: "crashed", message_id_reply: 9, attempt_no: 1, stored_order: []});
  release({live: false, last_reply_id: 9, last_attempt_no: 1});
  await reading;
  await tick();
  const turn = r.c.state().turn;
  assert.equal(turn.phase, "failed");
  assert.deepEqual(turn.error, {message: "The model stopped.", code: "crashed"});
  assert.equal(turn.lost, false);
  assert.equal(turn.replyId, 9);
  assert.deepEqual(r.log.terminals, ["failed"]);
});
