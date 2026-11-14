"use strict";
// ChatLiveStore (sutra_app/ui/static/js/chat_live_store.js): the reducer, the transition table and the selectors of a live turn (STR-8).
// Run with: node --test tests/ui/js/chat_live_store.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const S = require(path.join(JS, "chat_live_store.js"));
const {createIntake} = require(path.join(JS, "chat_live_events.js"));

const SID = "cs_000000000abc";
const GEN = "gen00001";
const CID = "client-0001";

// Feed raw wire frames through the real intake into the reducer: the two layers as the page runs them.
function rig() {
  const intake = createIntake({sid: SID});
  const r = {state: S.create(SID), intake, seq: 0, now: 1000, gaps: []};
  r.act = a => { r.state = S.reduce(r.state, Object.assign({now: r.now}, a)); return r.state; };
  r.wire = (type, payload, block) => {
    r.seq += 1;
    const raw = {v: 1, id: GEN + ":" + r.seq, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq: r.seq, ts: "2026-11-14T10:00:0" + (r.seq % 10) + ".000Z", type, payload: payload || {}};
    if (block) raw.block_id = block;
    intake.push(raw).forEach(a => { if (a.type === "gap") r.gaps.push(a.reason); r.act(a); });
    return r.state;
  };
  r.at = ms => { r.now += ms; return r; };
  return r;
}
const begin = r => { r.act({type: "send", clientId: CID}); r.act({type: "accepted", clientId: CID, generationId: GEN, messageId: 7, attemptNo: 1}); return r; };
const accept = r => r.wire("turn.accepted", {client_id: CID, attempt_no: 1});
const turn = r => r.state.turn;
const textOf = r => turn(r).blocks.filter(b => b.type === "text").map(b => b.text).join("");

test("the whole happy turn: sending, accepted, connecting, running, tool, text, done", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  assert.equal(turn(r).phase, "sending");
  assert.equal(S.label(r.state), "");
  accept(r);
  assert.equal(turn(r).phase, "accepted");
  assert.equal(turn(r).generationId, GEN);                                         // matched by client_id: no other bubble
  assert.equal(S.label(r.state), "Sent");
  r.wire("turn.connecting", {provider: "claude", model: "sonnet", stream_mode: "tokens"});
  assert.equal(S.label(r.state), "Starting Claude");
  r.wire("turn.started", {provider: "claude", model: "sonnet", stream_mode: "tokens", idle_limit_s: 120});
  assert.equal(turn(r).phase, "running");
  assert.equal(S.label(r.state, r.now), "Waiting for Claude");
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1");
  assert.equal(S.label(r.state, r.now), "Using Read");                             // the name only, until the input is known
  r.wire("block.update", {title: "Reading src/x.py", target: "src/x.py"}, "b1");
  assert.equal(S.label(r.state, r.now), "Reading src/x.py");
  r.wire("block.end", {status: "ok", is_error: false}, "b1");
  r.wire("block.start", {type: "text", kind: "other", name: ""}, "b2");
  r.wire("block.delta", {delta: "Hel", offset: 0}, "b2");
  r.wire("block.delta", {delta: "lo", offset: 3}, "b2");
  assert.equal(textOf(r), "Hello");
  assert.equal(S.label(r.state, r.now), "Writing");
  r.wire("turn.done", {message_id_reply: 8, attempt_no: 1, text_len: 5, stored_order: ["b1", "b1", "b2"]});
  assert.equal(turn(r).phase, "done");
  assert.equal(turn(r).replyId, 8);
  assert.deepEqual(turn(r).storedOrder, ["b1", "b1", "b2"]);
  assert.equal(S.label(r.state), "");
  assert.deepEqual(r.gaps, []);
});

test("another tab's turn (no local send) is created by turn.accepted", () => {
  const r = rig();
  accept(r);
  assert.equal(turn(r).phase, "accepted");
  assert.equal(turn(r).clientId, CID);
});

test("the transition table: every pair not listed is ignored, terminal phases never change", () => {
  const phases = ["sending", "accepted", "connecting", "running", "backoff", "stopping", "done", "stopped", "failed"];
  const events = {accepted: null, connecting: "turn.connecting", running: "turn.started", backoff: "attempt.failed", stopping: "turn.stopping", done: "turn.done", stopped: "turn.stopped", failed: "turn.failed"};
  for (const from of phases) {
    for (const [to, type] of Object.entries(events)) {
      if (type === null) continue;
      const state = Object.assign(S.create(SID), {turn: Object.assign({phase: from, source: "live", generationId: GEN, clientId: CID, messageId: 7, attemptNo: 1, seq: 1, lastEventAt: 0, startedAt: 0,
        blocks: [], earlier: [], storedOrder: [], heartbeat: null, backoff: null, restarts: 0}, {})});
      const raw = {type: "event", ev: {gen: GEN, seq: 2, type, known: true, attempt: 1, messageId: 7, blockId: null, ts: "", payload: {replyId: 8, attemptNo: 1, storedOrder: [], message: "x", code: "c", provider: "claude", reason: "r", delayS: 1, nextProvider: ""}}};
      const out = S.reduce(state, raw).turn.phase;
      const allowed = S.LEGAL[from].includes(to);
      assert.equal(out, allowed ? to : from, from + " -> " + to);
    }
  }
  const finished = Object.assign(S.create(SID), {turn: {phase: "done", source: "live", generationId: GEN, seq: 3, blocks: [], earlier: [], storedOrder: []}});
  const after = S.reduce(finished, {type: "event", ev: {gen: GEN, seq: 4, type: "block.delta", known: true, attempt: 1, blockId: "b1", ts: "", payload: {delta: "late", offset: 0}}});
  assert.equal(after.turn.blocks.length, 0);
});

test("Stop pressed while the POST is in flight: Stopping at once, queued until the 202, never sent before it", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  r.act({type: "stop.pressed"});
  assert.equal(turn(r).phase, "stopping");
  assert.equal(turn(r).stopQueued, true);
  assert.equal(S.label(r.state), "Stopping");
  r.act({type: "accepted", clientId: CID, generationId: GEN, messageId: 7, attemptNo: 1});
  assert.equal(turn(r).phase, "stopping");                                         // stays stopping
  assert.equal(turn(r).generationId, GEN);
  r.wire("turn.stopped", {message_id_reply: 9, attempt_no: 1, exit: "cancelled", stored_order: []});
  assert.equal(turn(r).phase, "stopped");
});

test("Stop pressed while sending and the POST fails: the turn is simply gone, there was nothing to stop", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  r.act({type: "stop.pressed"});
  r.act({type: "send.failed", clientId: CID, message: "The app is not responding."});
  assert.equal(turn(r), null);
});

test("a refused send fails the turn with the words; it can be sent again", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  r.act({type: "send.failed", clientId: CID, message: "This chat is already answering."});
  assert.equal(turn(r).phase, "failed");
  assert.equal(turn(r).error.message, "This chat is already answering.");
  r.act({type: "send", clientId: "client-0002"});
  assert.equal(turn(r).phase, "sending");
});

test("a second send while a turn runs is ignored", () => {
  const r = begin(rig());
  accept(r);
  const before = turn(r);
  r.act({type: "send", clientId: "client-0002"});
  assert.equal(turn(r).clientId, before.clientId);
});

test("Stop from another tab: turn.stopping then turn.stopped; and a finish that beat the signal is done", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  r.wire("turn.stopping", {});
  assert.equal(turn(r).phase, "stopping");
  r.wire("turn.done", {message_id_reply: 5, attempt_no: 1, stored_order: []});
  assert.equal(turn(r).phase, "done");
});

test("a stopped turn ends its open tool as interrupted and keeps what was written", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.delta", {delta: "partial", offset: 0}, "b1");
  r.wire("block.start", {type: "tool_use", kind: "run", name: "Bash"}, "b2");
  r.wire("turn.stopping", {});
  r.wire("turn.stopped", {message_id_reply: 6, attempt_no: 1, exit: "cancelled", stored_order: ["b1", "b2"]});
  assert.equal(turn(r).blocks[0].text, "partial");
  assert.equal(turn(r).blocks[0].status, "ok");
  assert.equal(turn(r).blocks[1].status, "interrupted");
});

test("a failed attempt shows the real reason and the countdown from the server's delay, then the restart moves its blocks under Earlier try", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.connecting", {provider: "claude"});
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "edit", name: "Edit"}, "b1");
  r.wire("block.update", {title: "Editing a.py", target: "a.py"}, "b1");
  r.wire("attempt.failed", {provider: "claude", code: "overloaded", reason: "Claude is overloaded.", action: "retry", delay_s: 10, next_provider: ""});
  assert.equal(turn(r).phase, "backoff");
  assert.equal(S.label(r.state, r.now), "Claude failed: Claude is overloaded. Retrying in 10 s");
  assert.equal(S.label(r.state, r.now + 4000), "Claude failed: Claude is overloaded. Retrying in 6 s");
  r.wire("turn.connecting", {provider: "claude"});
  assert.equal(turn(r).phase, "connecting");
  r.wire("attempt.restart", {attempt: 2, provider: "claude", after_side_effects: true});
  assert.equal(turn(r).phase, "running");
  assert.equal(turn(r).blocks.length, 0);
  assert.equal(turn(r).earlier.length, 1);
  assert.equal(turn(r).earlier[0].reason, "Claude is overloaded.");
  assert.equal(turn(r).earlier[0].afterSideEffects, true);
  assert.equal(turn(r).afterSideEffects, true);
  assert.equal(turn(r).attempt, 2);
});

test("a fallback names the next provider instead of a countdown", () => {
  const r = begin(rig());
  accept(r);
  r.wire("attempt.failed", {provider: "claude", reason: "Not signed in.", delay_s: 0, next_provider: "codex"});
  assert.equal(S.label(r.state, r.now), "Claude failed: Not signed in. Trying Codex");
});

test("a failure ends with the server's words", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.failed", {message: "Claude did not answer within 120 s: it sent no output for that long, so it was stopped", code: "idle_timeout", message_id_reply: 9, attempt_no: 1, stored_order: []});
  assert.equal(turn(r).phase, "failed");
  assert.match(turn(r).error.message, /120 s/);
});

test("activity: stalled shows the real silence and the real idle limit (and none when the limit is unknown)", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude", idle_limit_s: 120});
  r.at(5000).wire("heartbeat", {idle_ms: 22000, idle_limit_s: 120});
  const a = S.activity(r.state, r.now + 3000);
  assert.equal(a.kind, "stalled");
  assert.equal(a.label, "Still working, no output for 25 s");
  assert.match(a.detail, /stopped after 120 s without output/);
  const r2 = begin(rig());
  accept(r2);
  r2.wire("turn.started", {provider: "claude"});
  r2.wire("heartbeat", {idle_ms: 30000, idle_limit_s: null});
  assert.equal(S.activity(r2.state, r2.now).detail, "");
});

test("activity: the page's own silence is 'Live updates paused', and a snapshot in flight is 'Catching up'", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  assert.equal(S.activity(r.state, r.now + 16000).label, "Live updates paused");
  assert.equal(S.activity(r.state, r.now + 5000).kind, "waiting");
  r.act({type: "resync"});
  assert.equal(S.activity(r.state, r.now).label, "Catching up");
});

test("activity precedence: tool, then writing, then thinking", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "thinking"}, "b1");
  assert.equal(S.activity(r.state, r.now).kind, "thinking");
  r.wire("block.start", {type: "text"}, "b2");
  assert.equal(S.activity(r.state, r.now).kind, "writing");
  r.wire("block.start", {type: "tool_use", kind: "run", name: "Bash"}, "b3");
  assert.equal(S.activity(r.state, r.now).kind, "tool");
  r.wire("block.end", {status: "ok"}, "b3");
  assert.equal(S.activity(r.state, r.now).kind, "writing");
});

test("a block event for a block that never started creates it; the turn does not throw", () => {
  const r = begin(rig());
  accept(r);
  r.wire("block.update", {title: "Reading z"}, "b9");
  assert.equal(turn(r).blocks[0].type, "tool_use");
  assert.equal(turn(r).blocks[0].title, "Reading z");
});

test("a block.end with the whole text (a provider that cannot stream) fills a block that has no text", () => {
  const r = begin(rig());
  accept(r);
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.end", {status: "ok", text: "whole answer"}, "b1");
  assert.equal(textOf(r), "whole answer");
});

test("snapshot seeds a turn this page did not start, with its blocks and its place", () => {
  const r = rig();
  const out = r.intake.applySnapshot({generation_id: GEN, message_id: 7, client_id: "other-tab-01", attempt: 1, attempt_no: 1, state: "running", seq: 12, provider: "claude", model: "m",
    stream_mode: "tokens", elapsed_ms: 4000, idle_limit_s: 120, blocks: [{block_id: "b1", type: "text", kind: "other", name: "", status: "open", text: "so far"}], earlier: []});
  out.forEach(a => r.act(a));
  assert.equal(turn(r).phase, "running");
  assert.equal(textOf(r), "so far");
  assert.equal(turn(r).startedAt, r.now - 4000);
  r.seq = 12;
  r.wire("block.delta", {delta: " more", offset: 6}, "b1");
  assert.equal(textOf(r), "so far more");
});

test("snapshot.none ends a turn the page never heard finish: done, lost, with the stored reply's id", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  r.act({type: "snapshot.none", lastReplyId: 11, lastAttemptNo: 1});
  assert.equal(turn(r).phase, "done");
  assert.equal(turn(r).lost, true);
  assert.equal(turn(r).replyId, 11);
});

test("a snapshot of another send never replaces a send still waiting for its 202", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  r.intake.applySnapshot({generation_id: "zzzzzzzz", message_id: 3, client_id: "someone-else", attempt: 1, attempt_no: 1, state: "running", seq: 4, blocks: [], earlier: []}).forEach(a => r.act(a));
  assert.equal(turn(r).phase, "sending");
  assert.equal(turn(r).clientId, CID);
});

test("holds: a stored reply for the line is held back while its generation runs, and let go at the terminal event", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  assert.equal(S.holds(r.state, 7, 1), true);
  assert.equal(S.holds(r.state, 7), true);
  assert.equal(S.holds(r.state, 8, 1), false);
  assert.equal(S.holds(r.state, 7, 2), false);
  const row = {id: 8, role: "agent", turn: 7, attempt: 1, text: "stored"};
  r.act({type: "message", row});
  assert.deepEqual(r.state.stash, [row]);
  r.act({type: "message", row});                                                   // the same row twice is held once
  assert.equal(r.state.stash.length, 1);
  r.wire("turn.done", {message_id_reply: 8, attempt_no: 1, stored_order: []});
  assert.equal(S.holds(r.state, 7, 1), false);
  r.act({type: "release"});
  assert.deepEqual(r.state.stash, []);
});

test("a row of a turn that is not live is never held", () => {
  const r = rig();
  r.act({type: "message", row: {id: 1, role: "agent", turn: 7, attempt: 1}});
  assert.deepEqual(r.state.stash, []);
});

test("clear keeps what settling in place needs, and the next send forgets it", () => {
  const r = begin(rig());
  accept(r);
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.delta", {delta: "x", offset: 0}, "b1");
  r.wire("turn.done", {message_id_reply: 8, attempt_no: 1, stored_order: ["b1"]});
  r.act({type: "clear"});
  assert.equal(turn(r), null);
  assert.deepEqual(r.state.settled.storedOrder, ["b1"]);
  assert.equal(r.state.settled.replyId, 8);
  r.act({type: "send", clientId: "client-0002"});
  assert.equal(r.state.settled, null);
});

test("partial (flag off): pieces append, a reset starts a fresh block, a cumulative frame replaces, another message is ignored", () => {
  const r = rig();
  r.act({type: "send", clientId: CID});
  r.act({type: "accepted", clientId: CID, generationId: "", messageId: 7, attemptNo: 1});
  assert.equal(turn(r).source, "partial");
  r.act({type: "partial", messageId: 7, delta: "Hel", reset: false, cumulative: false});
  r.act({type: "partial", messageId: 7, delta: "lo", reset: false, cumulative: false});
  assert.equal(textOf(r), "Hello");
  assert.equal(turn(r).phase, "running");
  assert.equal(turn(r).streamMode, "snapshot");
  r.act({type: "partial", messageId: 9, delta: "other", reset: false});
  assert.equal(textOf(r), "Hello");
  r.act({type: "partial", messageId: 7, delta: "Again", reset: true});
  assert.equal(textOf(r), "Again");
  assert.equal(turn(r).blocks.length, 1);
  assert.notEqual(turn(r).blocks[0].id, "p1");
  r.act({type: "partial", messageId: 7, delta: "Again, whole", reset: false, cumulative: true});
  assert.equal(textOf(r), "Again, whole");
  assert.equal(S.holds(r.state, 7, 1), false);                                     // no live generation: the old reconcile applies
});

test("no head cap: a 200 KB reply keeps every character", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "text"}, "b1");
  let off = 0;
  for (let i = 0; i < 4000; i += 1) { const piece = "x".repeat(50); r.wire("block.delta", {delta: piece, offset: off}, "b1"); off += 50; }
  assert.equal(textOf(r).length, 200000);
  assert.deepEqual(r.gaps, []);
});

test("streamNote says what a provider that cannot stream is, never dressed up", () => {
  const r = begin(rig());
  accept(r);
  r.wire("turn.connecting", {provider: "codex", stream_mode: "final"});
  assert.equal(S.streamNote(r.state), "Codex sends its answer in one piece");
  r.wire("turn.started", {provider: "stub", stream_mode: "simulated"});
  assert.equal(S.streamNote(r.state), "Demo provider, simulated");
});

test("canStop is true while a turn can still be stopped, false while stopping and after the end", () => {
  const r = begin(rig());
  assert.equal(S.canStop(r.state), true);
  r.act({type: "stop.pressed"});
  assert.equal(S.canStop(r.state), false);
});

test("the reducer is pure: the old state is untouched", () => {
  const r = begin(rig());
  accept(r);
  const before = JSON.stringify(r.state);
  const frozen = r.state;
  S.reduce(frozen, {type: "event", ev: {gen: GEN, seq: 99, type: "block.start", known: true, attempt: 1, blockId: "b1", ts: "", payload: {blockType: "text", kind: "other", name: ""}}, now: 5});
  assert.equal(JSON.stringify(frozen), before);
});
