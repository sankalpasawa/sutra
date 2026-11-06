"use strict";
// ChatComposer (sutra_app/ui/static/js/chat_composer.js): the composer of the direct chat (work package ABS-15): attachments, send, stop, the streaming
// row and the provider rule. Run with: node --test tests/ui/js/chat_composer.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatComposer = require(path.join(JS, "chat_composer.js"));
const ChatView = require(path.join(JS, "chat_view.js"));
globalThis.ChatFold = require(path.join(JS, "chat_fold.js"));          // chat_view draws a settled turn's blocks through the global, as the page does
const {create, bar, chips, streamRow, button, askBlock, providerOf} = ChatComposer;

const SID = "cs_000000000abc";
const ID = "a".repeat(64);
const READY = [{name: "claude", ready: true}, {name: "codex", ready: true}];
const NONE = [{name: "claude", ready: false, why_not: "not signed in"}, {name: "codex", ready: false, why_not: "not installed"}];

function fakeApi(handlers) {
  const calls = [];
  const api = {calls, post: async (p, body) => { calls.push({p, body}); const h = handlers[p] || handlers["*"]; if (!h) throw Object.assign(new Error("no route"), {status: 404}); return h(body); }};
  return api;
}
const file = (name, size) => ({name, size: size === undefined ? 5 : size});
const rig = (handlers, extra) => {
  const api = fakeApi(handlers || {});
  let changes = 0;
  const c = create(Object.assign({api, sid: SID, mode: "direct", readFile: async () => "aGVsbG8=", onChange: () => { changes += 1; }}, extra || {}));
  return {api, c, changes: () => changes};
};
const UP = "/api/chats/" + SID + "/attachments";
const DIRECT = "/api/chats/" + SID + "/direct";
const STOP = DIRECT + "/stop";

test("a file is checked, read, uploaded to the upload route and shown as a chip; Remove drops it", async () => {
  const {api, c} = rig({[UP]: () => ({id: ID, name: "notes.txt", kind: "text", size: 5})});
  await c.addFiles([file("notes.txt")]);
  assert.deepEqual(api.calls[0], {p: UP, body: {name: "notes.txt", content_b64: "aGVsbG8="}});
  const f = c.state().files[0];
  assert.equal(f.status, "ready"); assert.equal(f.id, ID);
  assert.match(chips(c.state().files), /<li class="ccfile ready"><span class="ccname">notes.txt<\/span><small> \(5 B\)<\/small>/);
  c.removeFile(f.key);
  assert.equal(c.state().files.length, 0);
  assert.equal(chips([]), "");
});

test("a file the limits refuse is never read or sent, and the owner is told why", async () => {
  const {api, c} = rig({});
  await c.addFiles([file("tool.exe"), file("empty.txt", 0), file("huge.pdf", 30 * 1024 * 1024)]);
  assert.equal(api.calls.length, 0);
  assert.equal(c.state().files.length, 0);
  assert.match(c.state().note, /over 20 MB/);
  assert.match(bar(c.state()), /class="ccnote"/);
});

test("no more than ten files go with one message", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5})});
  await c.addFiles(Array.from({length: 12}, (_, i) => file("f" + i + ".txt")));
  assert.equal(c.state().files.length, 10);
  assert.match(c.state().note, /Up to 10 files/);
});

test("a failed upload is a chip that says so and is not sent with the message", async () => {
  const {api, c} = rig({[UP]: () => { throw new Error("That file kind is not accepted."); }, [DIRECT]: () => ({message_id: 7, turn: "started"})});
  await c.addFiles([file("a.txt")]);
  assert.equal(c.state().files[0].status, "failed");
  assert.match(chips(c.state().files), /ccfile failed.*not attached: That file kind is not accepted\./);
  await c.send("hello");
  assert.deepEqual(api.calls[api.calls.length - 1].body, {text: "hello"});
});

test("Send posts the text and the uploaded refs to /direct, then the files are cleared and the turn is active", async () => {
  const {api, c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5}), [DIRECT]: () => ({message_id: 41, turn: "started"})});
  await c.addFiles([file("a.txt")]);
  const out = await c.send("  read this  ");
  assert.deepEqual(out, {ok: true, message_id: 41});
  assert.deepEqual(api.calls[api.calls.length - 1], {p: DIRECT, body: {text: "read this", attachments: [ID]}});
  assert.deepEqual(c.state().files, []);
  assert.deepEqual(c.state().turn, {active: true, stopping: false, text: "", messageId: 41});
});

test("a refusal keeps the files and the box's text is the caller's; the turn is not left active", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5}), [DIRECT]: () => { throw Object.assign(new Error("This chat is already answering"), {status: 409}); }});
  await c.addFiles([file("a.txt")]);
  const out = await c.send("again");
  assert.equal(out.ok, false);
  assert.equal(c.state().turn.active, false);
  assert.equal(c.state().files.length, 1);
  assert.equal(c.state().note, "This chat is already answering");
});

test("nothing is sent while a file is uploading, with a blank message, while a turn answers, or in team mode", async () => {
  let release;
  const {api, c} = rig({[UP]: () => new Promise(resolve => { release = () => resolve({id: ID, kind: "text", size: 5}); }), [DIRECT]: () => ({message_id: 1})});
  const pending = c.addFiles([file("a.txt")]);
  assert.match((await c.send("x")).error, /finish uploading/);
  assert.equal(button(c.state(), "x").disabled, true);
  release(); await pending;
  assert.equal((await c.send("   ")).ok, false);
  assert.equal((await c.send("go")).ok, true);
  assert.match((await c.send("again")).error, /already answering/);
  assert.equal(api.calls.filter(x => x.p === DIRECT).length, 1);
  const team = rig({}, {mode: "team"});
  assert.match((await team.c.send("x")).error, /goes to the team/);
});

test("partials of this chat stream into the row, another chat's are ignored, and the row names the chosen provider", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 5})});
  await c.send("hi");
  assert.equal(c.partial({session_id: "cs_other0000000", message_id: 5, delta: "no"}), false);
  c.partial({session_id: SID, message_id: 5, delta: "Hel"});
  c.partial({data: {session_id: SID, message_id: 5, delta: "lo <b>"}});
  assert.equal(c.state().turn.text, "Hello <b>");
  const row = streamRow(c.state(), "codex");
  assert.match(row, /Codex is writing/);
  assert.match(row, /Hello &lt;b&gt;/);
  assert.doesNotMatch(row, /<b>/);
  assert.match(streamRow(c.state(), ""), /The model is writing/);
  assert.equal(streamRow(rig({}).c.state(), "claude"), "");
});

test("the turn ends when an agent message newer than the owner's line is stored, and not before", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 10})});
  await c.send("hi");
  assert.equal(c.reconcile([{id: 10, role: "user"}]), false);
  assert.equal(c.reconcile([{id: 9, role: "agent"}]), false);
  assert.equal(c.state().turn.active, true);
  assert.equal(c.reconcile([{id: 10, role: "user"}, {id: 11, role: "agent", kind: "error"}]), true);
  assert.equal(c.state().turn.active, false);
  assert.equal(streamRow(c.state(), "claude"), "");
});

test("the Send button becomes Stop while a direct turn answers; Stop posts to /direct/stop and then waits for the stored line", async () => {
  const {api, c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: true})});
  assert.deepEqual(button(c.state(), "x"), {label: "Send", act: "send", disabled: false});
  await c.send("long job");
  assert.deepEqual(button(c.state(), ""), {label: "Stop", act: "composer-stop", disabled: false});
  assert.deepEqual(await c.stop(), {ok: true, stopped: true});
  assert.equal(api.calls[api.calls.length - 1].p, STOP);
  assert.deepEqual(button(c.state(), ""), {label: "Stopping…", act: "composer-stop", disabled: true});
  assert.equal(c.state().turn.active, true);              // the stored reply ends it, not the click
});

test("Stop on a turn that had already finished clears the row at once", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: false})});
  await c.send("x");
  assert.deepEqual(await c.stop(), {ok: true, stopped: false});
  assert.equal(c.state().turn.active, false);
});

test("a stop that fails says so and the button comes back", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => { throw new Error("The app is not responding."); }});
  await c.send("x");
  assert.equal((await c.stop()).ok, false);
  assert.equal(c.state().turn.stopping, false);
  assert.equal(button(c.state(), "").act, "composer-stop");
  assert.equal(c.state().note, "The app is not responding.");
});

test("a provider that cannot run is never the one shown, and with none runnable the owner is told", () => {
  assert.equal(providerOf(READY, "codex"), "codex");
  assert.equal(providerOf([{name: "claude", ready: true}, {name: "codex", ready: false}], "codex"), "");
  assert.equal(providerOf(READY, "gemini"), "");
  assert.equal(askBlock(READY), "");
  assert.match(askBlock(NONE), /No model can answer right now/);
  assert.match(askBlock(null), /No model can answer right now/);
  assert.equal(button({mode: "direct", files: [], turn: {active: false}}, "x", {blocked: true}).disabled, true);
});

test("the bar shows the mode toggle always and the attach controls only in direct mode; labels are escaped", () => {
  const team = bar({mode: "team", files: []});
  assert.match(team, /data-mode="team" aria-pressed="true"/);
  assert.doesNotMatch(team, /composer-attach/);
  const direct = bar({mode: "direct", files: [{key: "f1", name: "<img src=x>.png", status: "ready", size: 2048}]}, {labels: {team: "Plan with Sutra", direct: "Ask directly"}});
  assert.match(direct, /Plan with Sutra/);
  assert.match(direct, /data-mode="direct" aria-pressed="true"/);
  assert.match(direct, /composer-attach/);
  assert.match(direct, /Up to 10 files, 20 MB each/);
  assert.match(direct, /&lt;img src=x&gt;\.png/);
  assert.doesNotMatch(direct, /<img/);
  assert.match(direct, /\(2\.0 KB\)/);
  assert.doesNotMatch(bar({mode: "direct", files: []}, {toggle: false}), /ccmode/);
});

test("the stored reply keeps its typed blocks: the settled turn is one fold row, and a streaming one draws none", () => {
  const blocks = [{type: "tool_use", kind: "read", name: "Read", text: "a.md"}, {type: "tool_result", kind: "read", text: "ok"}, {type: "tool_use", kind: "run", name: "Bash", text: "ls"}];
  const session = {kind: "department", title: "Web", writable: true, status: "active"};
  const settled = ChatView.transcript(session, [{id: 2, role: "agent", who: "sutra", kind: "text", text: "Done.", blocks, state: "ok", at: ""}], {live: true});
  assert.match(settled, /2 tool calls: 1 read, 1 run/);
  const pending = ChatView.transcript(session, [{id: 2, role: "agent", who: "sutra", kind: "text", text: "Done.", blocks, state: "pending", at: ""}], {live: true});
  assert.doesNotMatch(pending, /tool calls/);
});
