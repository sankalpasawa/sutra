"use strict";
// ChatView.transcriptItems with `shell: true` (STR-10): a direct reply is a constant shell for chat_live_view.js; every other line is as it was.
// Run with: node --test tests/ui/js/chat_view_shell.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatView = require(path.join(JS, "chat_view.js"));
globalThis.ChatFold = require(path.join(JS, "chat_fold.js"));
globalThis.ChatMarkdown = require(path.join(JS, "chat_markdown.js"));
const LV = require(path.join(JS, "chat_live_view.js"));

const session = {kind: "department", writable: true, status: "active", title: "Web"};
const user = {id: 1, role: "user", who: "user", kind: "text", text: "Hi", state: "ok", at: ""};
const reply = {id: 2, role: "agent", who: "claude", kind: "text", text: "**Hello**", turn: 1, attempt: 1, state: "ok", at: ""};

test("without shell nothing changes; with it only a direct reply becomes a shell, under the key of its turn and try", () => {
  globalThis.ChatLiveView = LV;
  const plain = ChatView.transcriptItems(session, [user, reply], {});
  assert.deepEqual(plain.map(i => i.key), ["m1", "m2"]);
  assert.match(plain[1].html, /<strong>Hello<\/strong>/);
  const shells = ChatView.transcriptItems(session, [user, reply], {shell: true});
  assert.deepEqual(shells.map(i => i.key), ["m1", "turn:1:1"]);
  assert.equal(shells[1].html, LV.shellHtml(1, 1));
  assert.equal(shells[0].html, plain[0].html);
});

test("the shell html of a reply is the same before and after it is stored (a stored id never enters it)", () => {
  globalThis.ChatLiveView = LV;
  const a = ChatView.transcriptItems(session, [user, reply], {shell: true})[1];
  const b = ChatView.transcriptItems(session, [user, Object.assign({}, reply, {id: 99, ordered: true, blocks: [{type: "text", kind: "other", text: "**Hello**"}]})], {shell: true})[1];
  assert.equal(a.html, b.html);
  assert.equal(a.key, b.key);
});

test("a note, an error and a plain agent line are not shells; the error that carries the ended turn's tools is", () => {
  globalThis.ChatLiveView = LV;
  const items = ChatView.transcriptItems(session, [user, {id: 3, role: "agent", who: "sutra", kind: "note", text: "Stopped.", turn: 1, attempt: 1, at: ""},
    {id: 4, role: "agent", who: "claude", kind: "error", text: "boom", turn: 1, attempt: 1, ordered: true, blocks: [{type: "tool_use", kind: "run", name: "Bash", text: "x"}], state: "error", at: ""},
    {id: 5, role: "agent", who: "identity", kind: "text", text: "A team line", at: ""}], {shell: true});
  assert.deepEqual(items.map(i => i.key), ["m1", "m3", "turn:1:1", "m5"]);
});

test("a superseded reply is collapsed under Earlier try", () => {
  globalThis.ChatLiveView = LV;
  const items = ChatView.transcriptItems(session, [user, Object.assign({}, reply, {superseded: true})], {shell: true});
  assert.match(items[1].html, /cl-superseded/);
});

test("without chat_live_view.js on the page the option is ignored", () => {
  delete globalThis.ChatLiveView;
  const items = ChatView.transcriptItems(session, [user, reply], {shell: true});
  assert.deepEqual(items.map(i => i.key), ["m1", "m2"]);
});
