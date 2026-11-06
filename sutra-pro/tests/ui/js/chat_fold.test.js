"use strict";
// ChatFold (sutra_app/ui/static/js/chat_fold.js): a settled turn's tool calls fold into ONE row (work package ABS-10). Ports the intent of the old
// app's test_chat_condense.js. Run with: node --test tests/ui/js/chat_fold.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatFold = require(path.join(JS, "chat_fold.js"));
const ChatView = require(path.join(JS, "chat_view.js"));
const {summarize, line, fold} = ChatFold;

const use = (kind, name, text) => ({type: "tool_use", kind, name, text: text || ""});
const result = (kind, text, extra) => Object.assign({type: "tool_result", kind, name: "", text: text || ""}, extra || {});
const TURN = [].concat(
  Array.from({length: 8}, (_, i) => [use("read", "Read", "f" + i + ".md"), result("read", "ok")]).flat(),
  Array.from({length: 3}, () => [use("run", "Bash", "ls"), result("run", "a\nb")]).flat(),
  [use("run", "Bash", "false"), result("run", "boom", {is_error: true})]);

test("a settled turn folds to one counted line", () => {
  assert.equal(line(TURN), "12 tool calls: 8 read, 4 run, 1 failed");
  const s = summarize(TURN);
  assert.equal(s.calls, 12); assert.equal(s.kinds.read, 8); assert.equal(s.kinds.run, 4); assert.equal(s.failed, 1);
});

test("one call is singular, no call is no line, an unknown kind is other", () => {
  assert.equal(line([use("web", "WebFetch")]), "1 tool call: 1 web");
  assert.equal(line([{type: "text", text: "hi"}]), "");
  assert.equal(line([use("telepathy", "Zap")]), "1 tool call: 1 other");
  assert.equal(line(null), "");
});

test("the fold is one <details> row that opens into the cards", () => {
  const html = fold(TURN, {settled: true});
  assert.equal((html.match(/<details/g) || []).length, 1);
  assert.match(html, /<summary>12 tool calls: 8 read, 4 run, 1 failed<\/summary>/);
  assert.equal((html.match(/class="cfold-item kind-/g) || []).length, 12);
  assert.match(html, /class="cfold-item result failed"/);
});

test("while streaming nothing is drawn at the top", () => {
  assert.equal(fold(TURN, {settled: false}), "");
  assert.equal(fold(TURN), "");
  assert.equal(fold([], {settled: true}), "");
});

test("a cut result says it was cut and nothing becomes markup", () => {
  const html = fold([use("run", "Bash", "<b>x</b>"), result("run", "<script>1</script>", {truncated: true})], {settled: true});
  assert.match(html, /\(cut\)/);
  assert.doesNotMatch(html, /<script>|<b>x/);
  assert.match(html, /&lt;script&gt;1&lt;\/script&gt;/);
  const long = fold([use("read", "Read"), result("read", "x".repeat(5000))], {settled: true});
  assert.match(long, /\(cut\)/);
});

test("a very long turn shows the first cards and counts the rest", () => {
  const many = Array.from({length: 300}, () => use("read", "Read", "f"));
  assert.match(fold(many, {settled: true}), /and 100 more/);
});

test("the transcript draws the fold under a settled agent message and not under a pending one", () => {
  const msg = state => ({id: 5, who: "sutra", role: "agent", kind: "text", text: "done", state, blocks: TURN});
  const session = {kind: "department", writable: true, status: "active", title: "Web"};
  global.ChatFold = ChatFold;
  try {
    assert.match(ChatView.transcript(session, [msg("ok")], {}), /<details class="cfold">/);
    assert.doesNotMatch(ChatView.transcript(session, [msg("pending")], {}), /cfold/);
    assert.doesNotMatch(ChatView.transcript(session, [Object.assign(msg("ok"), {blocks: []})], {}), /cfold/);
  } finally {
    delete global.ChatFold;
  }
});
