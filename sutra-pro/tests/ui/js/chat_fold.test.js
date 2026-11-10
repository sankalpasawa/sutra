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

// ---- a long TEXT folded (D135): the finished report in the team's chat ------------------------------------------------------------------------------
const {longText, headings} = ChatFold;
const SECTIONS = "## Findings\n\nx\n\n## Changes\n\ny\n\n## Findings\n\nagain\n\n### not a section\n\n## Outcome ##\n\nz\n";

test("a short text is returned as it is and a long one is folded into one details row", () => {
  assert.equal(longText("short", "<p>short</p>"), "<p>short</p>");
  assert.equal(longText("x".repeat(ChatFold.TEXT_FOLD_AT), "<p>x</p>"), "<p>x</p>");                           // the limit itself is still short
  const folded = longText("x".repeat(ChatFold.TEXT_FOLD_AT + 1), "<p>x</p>");
  assert.equal(folded, '<details class="cfold cfold-text"><summary>Read the full text</summary><p>x</p></details>');
  assert.equal(ChatFold.TEXT_FOLD_AT, 1400);
});

test("the summary names the text's headings once each, in order, and the label and limit can be chosen", () => {
  assert.deepEqual(headings(SECTIONS), ["Findings", "Changes", "Outcome"]);
  const html = longText(SECTIONS + "z".repeat(50), "<div>body</div>", {limit: 40, label: "Read the report"});
  assert.equal(html, '<details class="cfold cfold-text"><summary>Read the report (Findings, Changes, Outcome)</summary><div>body</div></details>');
  assert.equal(longText(SECTIONS, "<div>b</div>", {limit: 10_000}), "<div>b</div>");
});

test("a text with many headings names the first eight and says there are more", () => {
  const many = Array.from({length: 11}, (_, i) => "## Part " + (i + 1) + "\n\ntext\n").join("\n");
  const html = longText(many, "<p>x</p>", {limit: 10});
  assert.match(html, /<summary>Read the full text \(Part 1, Part 2, Part 3, Part 4, Part 5, Part 6, Part 7, Part 8, …\)<\/summary>/);
});

test("a heading is escaped in the summary and an odd call is harmless", () => {
  const html = longText("## <script>x</script> & \"q\"\n" + "z".repeat(60), "<p>x</p>", {limit: 10, label: "<b>Read</b>"});
  assert.doesNotMatch(html, /<script|<b>Read/);
  assert.match(html, /&lt;script&gt;x&lt;\/script&gt; &amp; &quot;q&quot;/);
  assert.equal(longText("z".repeat(5000), ""), "");
  assert.equal(longText(null, "<p>x</p>"), "<p>x</p>");
  assert.equal(longText("z".repeat(5000), "<p>x</p>", "limit").startsWith("<details"), true);                 // opts that are not an object are the defaults
  assert.equal(longText("z".repeat(50), "<p>x</p>", {limit: -1}), "<p>x</p>");                                  // a bad limit is the default one
  assert.deepEqual(headings(undefined), []);
});
