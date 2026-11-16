"use strict";
// ChatComposer in live mode (`live: true`, STR-9): the send's client_id, one bubble, frames, the held reply, Stop in every window, Retry, resync and cleanup.
// The older tests of chat_composer.test.js run the composer without `live` and are not touched. Run with: node --test tests/ui/js/chat_composer_live.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatComposer = require(path.join(JS, "chat_composer.js"));

const SID = "cs_000000000abc";
const BASE = "/api/chats/" + SID;
const DIRECT = BASE + "/direct";
const STOP = DIRECT + "/stop";
const RETRY = DIRECT + "/retry";
const TURN = BASE + "/turn";
const GEN = "gen00001";

function timers() {
  const iv = new Map(); const to = new Map(); let id = 0;
  return {iv, to, set: (fn, ms) => { id += 1; to.set(id, fn); return id; }, clear: n => to.delete(n), setInterval: (fn) => { id += 1; iv.set(id, fn); return id; }, clearInterval: n => iv.delete(n)};
}
function rig(handlers, extra) {
  const calls = [];
  const api = {
    calls,
    post: async (p, body) => { calls.push({m: "POST", p, body}); const h = handlers[p] || handlers["*"]; if (!h) throw Object.assign(new Error("no route"), {status: 404}); return typeof h === "function" ? h(body) : h; },
    get: async (p, q) => { calls.push({m: "GET", p, q}); const h = handlers["GET " + p]; if (h === undefined) throw Object.assign(new Error("no route"), {status: 404}); const v = typeof h === "function" ? h(q) : h; if (v instanceof Error) throw v; return v; },
  };
  const t = timers();
  const log = {changes: 0, ended: 0, released: [], settled: 0};
  let n = 0;
  const c = ChatComposer.create(Object.assign({api, sid: SID, mode: "direct", live: true, timers: t, now: () => 1000, newId: () => "client-" + String(++n).padStart(4, "0"),
    onChange: () => { log.changes += 1; }, onTurnEnd: () => { log.ended += 1; }, onRelease: rows => log.released.push(rows), onSettle: () => { log.settled += 1; }}, extra || {}));
  let seq = 0;
  const wire = (type, payload, block) => { seq += 1; const raw = {v: 1, id: GEN + ":" + seq, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq, ts: "t", type, payload: payload || {}}; if (block) raw.block_id = block; c.frame(raw); };
  return {c, api, calls, t, log, wire};
}
const ACCEPT = {message_id: 7, turn: "started", generation_id: GEN, attempt_no: 1, client_id: "client-0001"};
const posts = (r, p) => r.calls.filter(x => x.m === "POST" && x.p === p);
const tick = async () => { await new Promise(res => setImmediate(res)); await new Promise(res => setImmediate(res)); };
const started = async r => { await r.c.send("hello"); r.wire("turn.accepted", {client_id: "client-0001", attempt_no: 1}); r.wire("turn.started", {provider: "claude"}); };

test("the send carries a client_id, shows the owner's line at once, and the stored line with that client_id replaces it (one bubble)", async () => {
  const r = rig({[DIRECT]: ACCEPT});
  const out = await r.c.send("hello");
  assert.deepEqual(out, {ok: true, message_id: 7});
  assert.deepEqual(posts(r, DIRECT)[0].body, {text: "hello", client_id: "client-0001"});
  assert.deepEqual(r.c.pendingLine([]), {clientId: "client-0001", text: "hello"});
  assert.equal(r.c.pendingLine([{id: 7, role: "user", client_id: "client-0001", text: "hello"}]), null);
  assert.equal(r.c.pendingLine([]), null);                                                          // gone for good
});

test("state().turn is the projection of the store with the same four keys", async () => {
  const r = rig({[DIRECT]: ACCEPT});
  assert.deepEqual(r.c.state().turn, {active: false, stopping: false, text: "", messageId: null});
  await started(r);
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.delta", {delta: "Hi ", offset: 0}, "b1");
  r.wire("block.delta", {delta: "there", offset: 3}, "b1");
  assert.deepEqual(r.c.state().turn, {active: true, stopping: false, text: "Hi there", messageId: 7});
  assert.equal(r.c.liveView().label, "Writing");
});

test("a refused send leaves no turn and says why; the owner's line is not left pending", async () => {
  const r = rig({[DIRECT]: () => { throw Object.assign(new Error("This chat is already answering."), {status: 409, code: "busy"}); }});
  const out = await r.c.send("hello");
  assert.equal(out.ok, false);
  assert.equal(r.c.state().turn.active, false);
  assert.equal(r.c.state().note, "This chat is already answering.");
  assert.equal(r.c.pendingLine([]), null);
  assert.equal(r.c.liveView().turn, null);
});

test("the flag-off server (a 202 with no generation) is told by chat.partial and the stored reply, as before", async () => {
  const r = rig({[DIRECT]: {message_id: 7, turn: "started"}});
  await r.c.send("hello");
  assert.equal(r.c.liveView().turn.source, "partial");
  assert.equal(r.c.partial({session_id: SID, message_id: 7, delta: "Hel"}), true);
  r.c.partial({session_id: SID, message_id: 7, delta: "lo"});
  assert.equal(r.c.state().turn.text, "Hello");
  assert.equal(r.c.partial({session_id: "cs_other", message_id: 7, delta: "x"}), false);
  assert.equal(r.c.reconcile([{id: 8, role: "agent", kind: "text", turn: 7}]), true);               // the old rule
  assert.equal(r.c.state().turn.active, false);
  assert.equal(r.log.ended, 1);
});

test("a stored reply of a live turn is held back: reconcile does not end it, the terminal event releases it, then it ends once", async () => {
  const r = rig({[DIRECT]: ACCEPT});
  await started(r);
  const row = {id: 8, role: "agent", kind: "text", turn: 7, attempt: 1, text: "answer"};
  assert.deepEqual(r.c.offer([row]), []);                                                           // chat.message before turn.done: not shown
  assert.equal(r.c.reconcile([row]), false);
  assert.equal(r.c.state().turn.active, true);
  r.wire("turn.done", {message_id_reply: 8, attempt_no: 1, stored_order: []});
  assert.equal(r.c.state().turn.active, false);                                                     // the owner can write again at once
  assert.equal(r.log.released.length, 1);
  assert.equal(r.log.settled, 1);
  assert.equal(r.log.ended, 0);
  assert.equal(r.c.reconcile([row]), true);
  assert.equal(r.log.ended, 1);
  assert.equal(r.c.reconcile([row]), false);
  assert.ok(r.c.liveView().settled);
  assert.equal(r.c.liveView().settled.replyId, 8);
});

test("the first try's stored reply does not end a retry (attempt-scoped)", async () => {
  const r = rig({[RETRY]: {message_id: 7, turn: "started", generation_id: GEN, attempt_no: 2, client_id: "client-0001"}});
  const out = await r.c.retry(7, "hello");
  assert.deepEqual(out, {ok: true, message_id: 7});
  assert.deepEqual(posts(r, RETRY)[0].body, {message_id: 7, client_id: "client-0001"});
  assert.equal(r.c.reconcile([{id: 8, role: "agent", kind: "text", turn: 7, attempt: 1}]), false);
  assert.equal(r.c.state().turn.active, true);
  assert.equal(r.c.pendingLine([]), null);                                                           // a retry adds no owner line
});

test("Retry on a server with no live route sends the words again as it always did", async () => {
  const r = rig({[DIRECT]: {message_id: 30, turn: "started"}});
  const out = await r.c.retry(12, "hello again");
  assert.deepEqual(out, {ok: true, message_id: 30});
  assert.deepEqual(posts(r, DIRECT)[0].body, {text: "hello again", client_id: "client-0002"});
  assert.equal(r.c.state().turn.messageId, 30);
});

test("Retry on a line that was answered says so", async () => {
  const r = rig({[RETRY]: () => { throw Object.assign(new Error("no"), {status: 409, code: "not_retryable"}); }});
  const out = await r.c.retry(7, "hello");
  assert.equal(out.ok, false);
  assert.equal(r.c.state().note, "That message was answered already.");
  assert.equal(r.c.state().turn.active, false);
});

test("Stop: Stopping at once, the stop POST goes out, and the turn ends only with the server's terminal event", async () => {
  const r = rig({[DIRECT]: ACCEPT, [STOP]: {session_id: SID, stopped: true, state: "stopping"}});
  await started(r);
  const out = await r.c.stop();
  assert.deepEqual(out, {ok: true, stopped: true});
  assert.equal(r.c.state().turn.stopping, true);
  assert.equal(r.c.liveView().label, "Stopping");
  r.wire("turn.stopping", {});
  r.wire("turn.stopped", {message_id_reply: 9, attempt_no: 1, exit: "cancelled", stored_order: []});
  assert.equal(r.c.liveView().turn.phase, "stopped");
  assert.equal(r.c.state().turn.active, false);
});

test("Stop pressed while the POST is in flight shows Stopping, waits for the 202 and only then sends the stop", async () => {
  let release;
  const r = rig({[DIRECT]: () => new Promise(res => { release = () => res(ACCEPT); }), [STOP]: {session_id: SID, stopped: true}});
  const sending = r.c.send("hello");
  const out = await r.c.stop();
  assert.deepEqual(out, {ok: true, queued: true});
  assert.equal(r.c.state().turn.stopping, true);
  assert.equal(posts(r, STOP).length, 0);                                                           // never before the turn has an id
  release();
  await sending;
  assert.equal(posts(r, STOP).length, 1);
});

test("Stop pressed while sending, then the POST fails: the turn is gone and no stop was ever sent", async () => {
  let fail;
  const r = rig({[DIRECT]: () => new Promise((res, rej) => { fail = () => rej(Object.assign(new Error("The app is not responding."), {code: "network"})); })});
  const sending = r.c.send("hello");
  await r.c.stop();
  fail();
  const out = await sending;
  assert.equal(out.ok, false);
  assert.equal(r.c.state().turn.active, false);
  assert.equal(posts(r, STOP).length, 0);
});

test("a stop response of stopped:false never clears Stopping by itself: the snapshot decides", async () => {
  const r = rig({[DIRECT]: ACCEPT, [STOP]: {session_id: SID, stopped: false, state: "none"}, ["GET " + TURN]: {live: false, last_reply_id: 8, last_attempt_no: 1}});
  await started(r);
  const out = await r.c.stop();
  assert.deepEqual(out, {ok: true, stopped: false});
  assert.equal(r.calls.filter(x => x.p === TURN).length, 1);
  assert.equal(r.c.liveView().turn.phase, "done");                                                  // the snapshot said nothing runs and a reply is stored
  assert.equal(r.c.liveView().turn.lost, true);
});

test("a stop request that fails brings the Stop button back and says so", async () => {
  const r = rig({[DIRECT]: ACCEPT, [STOP]: () => { throw Object.assign(new Error("The app is not responding."), {code: "network"}); }});
  await started(r);
  const out = await r.c.stop();
  assert.equal(out.ok, false);
  assert.equal(r.c.state().turn.stopping, false);
  assert.equal(r.c.state().note, "The app is not responding.");
});

test("a second tab: resync adopts the live turn from its snapshot and shows the text so far; a later frame continues it", async () => {
  const snap = {generation_id: "other001", message_id: 5, client_id: "tab-two-01", attempt: 1, attempt_no: 1, state: "running", seq: 6, provider: "claude", model: "m", stream_mode: "tokens", elapsed_ms: 3000,
    idle_limit_s: 120, blocks: [{block_id: "b1", type: "text", kind: "other", name: "", status: "open", text: "so far"}], earlier: []};
  const r = rig({["GET " + BASE]: {id: SID, direct_turn: 5, live: {generation_id: "other001", seq: 6, state: "running", attempt_no: 1}}, ["GET " + BASE + "/messages"]: {messages: []}, ["GET " + TURN]: snap}, {mode: "team"});
  assert.equal(await r.c.resync(), true);
  assert.equal(r.c.state().mode, "direct");
  assert.deepEqual(r.c.state().turn, {active: true, stopping: false, text: "so far", messageId: 5});
  r.c.frame({v: 1, id: "x", conversation_id: SID, message_id: 5, generation_id: "other001", attempt: 1, seq: 7, ts: "t", type: "block.delta", payload: {delta: "!", offset: 6}, block_id: "b1"});
  assert.equal(r.c.state().turn.text, "so far!");
});

test("resync without a live generation adopts the turn as before (partial source), and a reply already stored is not adopted", async () => {
  const r = rig({["GET " + BASE]: {id: SID, direct_turn: 5}, ["GET " + BASE + "/messages"]: {messages: []}}, {mode: "team"});
  assert.equal(await r.c.resync(), true);
  assert.deepEqual(r.c.state().turn, {active: true, stopping: false, text: "", messageId: 5});
  const done = rig({["GET " + BASE]: {id: SID, direct_turn: 5}, ["GET " + BASE + "/messages"]: {messages: [{id: 6, role: "agent", turn: 5, attempt: 1}]}}, {mode: "team"});
  assert.equal(await done.c.resync(), false);
  assert.equal(done.c.state().turn.active, false);
});

test("a turn the server no longer runs (the app restarted) is asked about: the snapshot ends it", async () => {
  const r = rig({[DIRECT]: ACCEPT, ["GET " + BASE]: {id: SID, direct_turn: null}, ["GET " + TURN]: {live: false, last_reply_id: 9, last_attempt_no: 1}});
  await started(r);
  assert.equal(await r.c.resync(), true);
  assert.equal(r.c.state().turn.active, false);
});

test("rejoin reads the snapshot of a running turn (the panel was closed meanwhile)", async () => {
  const r = rig({[DIRECT]: ACCEPT, ["GET " + TURN]: {live: false}});
  await started(r);
  assert.equal(r.c.rejoin(), true);
  await tick();
  assert.equal(r.calls.filter(x => x.p === TURN).length, 1);
});

test("reconnect and polling reach the client; close stops every timer", async () => {
  const r = rig({[DIRECT]: ACCEPT, ["GET " + TURN]: {live: false}});
  await started(r);
  r.c.setPolling(true);
  assert.equal(r.t.iv.size, 2);                                                                     // the turn's clock and the poll
  await r.c.reconnect();                                                                            // the server says nothing runs: the turn ends, its clock stops
  assert.equal(r.t.iv.size, 1);
  r.c.close();
  assert.equal(r.t.iv.size, 0);
  assert.equal(r.t.to.size, 0);
});

test("without live: true the composer has no live behaviour at all", async () => {
  const api = {post: async () => ({message_id: 3}), get: async () => ({})};
  const c = ChatComposer.create({api, sid: SID, mode: "direct"});
  assert.equal(c.live(), false);
  assert.equal(c.liveView(), null);
  assert.deepEqual(c.offer([{id: 1}]), [{id: 1}]);
  c.frame({});
  assert.equal(c.pendingLine([]), null);
});
