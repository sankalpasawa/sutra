"use strict";
// ChatLiveEvents (sutra_app/ui/static/js/chat_live_events.js): the intake of a live turn (STR-8): envelope checks, de-duplication, holes, snapshot catch-up,
// code-point offsets and the chat.partial adapter. Run with: node --test tests/ui/js/chat_live_events.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const {createIntake, fromPartial, cpLen} = require(path.join(JS, "chat_live_events.js"));

const SID = "cs_000000000abc";
const GEN = "g".repeat(8);
let n = 0;
function frame(type, seq, payload, extra) {
  return Object.assign({v: 1, id: GEN + ":" + seq, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq, ts: "2026-11-14T10:00:00.000Z", type, payload: payload || {}}, extra || {});
}
const accepted = seq => frame("turn.accepted", seq, {client_id: "client-0001", attempt_no: 1});
const delta = (seq, text, offset, block) => frame("block.delta", seq, {delta: text, offset}, {block_id: block || "b1"});
const types = actions => actions.map(a => a.type + (a.reason ? ":" + a.reason : ""));

test("a valid first frame is an event with typed, bounded fields", () => {
  const i = createIntake({sid: SID});
  const out = i.push(accepted(1));
  assert.deepEqual(types(out), ["event"]);
  assert.equal(out[0].ev.type, "turn.accepted");
  assert.equal(out[0].ev.payload.clientId, "client-0001");
  assert.equal(out[0].ev.gen, GEN);
  assert.equal(out[0].ev.messageId, 7);
});

test("frames of another conversation, not objects, with no seq or an unknown envelope are nothing", () => {
  const i = createIntake({sid: SID});
  assert.deepEqual(i.push(Object.assign(accepted(1), {conversation_id: "cs_other"})), []);
  assert.deepEqual(i.push(null), []);
  assert.deepEqual(i.push("x"), []);
  assert.deepEqual(i.push(Object.assign(accepted(1), {seq: 0})), []);
  assert.deepEqual(i.push(Object.assign(accepted(1), {generation_id: ""})), []);
  assert.deepEqual(i.push(Object.assign(accepted(1), {v: undefined})), []);
});

test("a higher schema version is reported once and never applied", () => {
  const i = createIntake({sid: SID});
  assert.deepEqual(types(i.push(Object.assign(accepted(1), {v: 2}))), ["unsupported"]);
  assert.deepEqual(i.push(Object.assign(accepted(1), {v: 2})), []);
});

test("a duplicate (generation, seq) is dropped and the order is kept", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  assert.deepEqual(types(i.push(frame("turn.connecting", 2, {provider: "claude"}))), ["event"]);
  assert.deepEqual(i.push(frame("turn.connecting", 2, {provider: "claude"})), []);
  assert.deepEqual(i.push(accepted(1)), []);
});

test("a seq that skips ahead is a gap, and everything after it waits for a snapshot", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  assert.deepEqual(types(i.push(frame("turn.started", 4, {provider: "claude"}))), ["gap:seq"]);
  assert.equal(i.state().buffering, true);
  assert.deepEqual(i.push(frame("heartbeat", 5, {idle_ms: 10})), []);
  assert.equal(i.state().buffered, 2);
});

test("a first frame that is not seq 1 is a gap (a page that joined mid-turn)", () => {
  const i = createIntake({sid: SID});
  assert.deepEqual(types(i.push(frame("block.end", 9, {status: "ok"}, {block_id: "b1"}))), ["gap:first"]);
});

test("an offset that is not the length already shown is a gap", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  assert.deepEqual(types(i.push(delta(2, "abc", 0))), ["event"]);
  assert.deepEqual(types(i.push(delta(3, "def", 3))), ["event"]);
  assert.deepEqual(types(i.push(delta(4, "x", 9))), ["gap:offset"]);
});

test("offsets count code points: an emoji is one character, as the server counts it", () => {
  assert.equal(cpLen("a\u{1F600}b"), 3);
  assert.equal("a\u{1F600}b".length, 4);
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  assert.deepEqual(types(i.push(delta(2, "a\u{1F600}b", 0))), ["event"]);
  assert.deepEqual(types(i.push(delta(3, "c", 3))), ["event"]);
});

test("an oversize piece is dropped as a gap, never drawn", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  assert.deepEqual(types(i.push(delta(2, "x".repeat(20000), 0))), ["gap:oversize"]);
});

test("an unknown type passes through so its seq counts; its payload is not kept", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  const out = i.push(frame("brand.new", 2, {secret: "x"}));
  assert.deepEqual(types(out), ["event"]);
  assert.equal(out[0].ev.known, false);
  assert.deepEqual(out[0].ev.payload, {});
  assert.deepEqual(types(i.push(frame("turn.connecting", 3, {provider: "claude"}))), ["event"]);
});

test("a snapshot seeds the intake: older buffered frames drop, newer ones follow in order", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  i.push(frame("turn.started", 5, {provider: "claude"}));                       // gap: the intake now buffers
  i.beginSnapshot();
  i.push(delta(6, "wor", 5, "b1"));
  i.push(delta(7, "ld", 8, "b1"));
  i.push(frame("heartbeat", 4, {idle_ms: 1}));
  const out = i.applySnapshot({generation_id: GEN, message_id: 7, client_id: "client-0001", attempt: 1, attempt_no: 1, state: "running", seq: 5, provider: "claude", model: "m",
    stream_mode: "tokens", elapsed_ms: 900, idle_limit_s: 120, blocks: [{block_id: "b1", type: "text", kind: "other", name: "", status: "open", text: "hello"}], earlier: []});
  assert.deepEqual(types(out), ["snapshot", "event", "event"]);
  assert.deepEqual(out.slice(1).map(a => a.ev.seq), [6, 7]);
  assert.equal(i.state().buffering, false);
  assert.deepEqual(types(i.push(delta(8, "!", 10, "b1"))), ["event"]);          // the snapshot's text is "hello" (5), then 3 and 2 more: 10
});

test("a buffered frame after a second hole gives a gap again", () => {
  const i = createIntake({sid: SID});
  i.beginSnapshot();
  i.push(frame("heartbeat", 9, {idle_ms: 1}));
  const out = i.applySnapshot({generation_id: GEN, message_id: 7, seq: 5, state: "running", blocks: [], earlier: []});
  assert.deepEqual(types(out), ["snapshot", "gap:seq"]);
});

test("a snapshot that says nothing runs is snapshot.none with the stored reply's id", () => {
  const i = createIntake({sid: SID});
  i.beginSnapshot();
  assert.deepEqual(i.applySnapshot({live: false, last_reply_id: 12, last_attempt_no: 1}), [{type: "snapshot.none", lastReplyId: 12, lastAttemptNo: 1}]);
});

test("a failed snapshot keeps buffering, bounded", () => {
  const i = createIntake({sid: SID});
  i.beginSnapshot();
  i.failSnapshot();
  for (let k = 0; k < 2100; k += 1) i.push(frame("heartbeat", k + 1, {idle_ms: 1}));
  assert.equal(i.state().buffered, 2000);
});

test("reset forgets every generation", () => {
  const i = createIntake({sid: SID});
  i.push(accepted(1));
  i.reset();
  assert.deepEqual(types(i.push(accepted(1))), ["event"]);
});

test("fromPartial reads a piece, a reset and an end; other chats and empty frames are nothing", () => {
  assert.deepEqual(fromPartial({session_id: SID, message_id: 4, delta: "hi", reset: false}, {sid: SID}), [{type: "partial", sid: SID, messageId: 4, delta: "hi", cumulative: false, reset: false, done: false}]);
  assert.equal(fromPartial({session_id: SID, delta: "all", reset: true}, {sid: SID, cumulative: true})[0].cumulative, true);
  assert.equal(fromPartial({session_id: SID, delta: "", reset: true, done: true}, {sid: SID})[0].done, true);
  assert.deepEqual(fromPartial({session_id: "cs_other", delta: "x"}, {sid: SID}), []);
  assert.deepEqual(fromPartial({session_id: SID, delta: ""}, {sid: SID}), []);
  assert.deepEqual(fromPartial({data: {session_id: SID, delta: "x"}}, {sid: SID}).length, 1);
});
