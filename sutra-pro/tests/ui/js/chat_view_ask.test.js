"use strict";
// ChatView (sutra_app/ui/static/js/chat_view.js): the owner's questions to a function and its answers, as lines of the function's own chat (J2 sync 4, D148).
// The messages route draws them with `ask`: "q" (the owner's question), "records" or "model" (the function's answer). The question is the owner's own line
// labelled "You asked"; the answer is the function's line with a small label that says where it came from.
// Run with: node --test tests/ui/js/chat_view_ask.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const CV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_view.js"));

const msg = (over = {}) => ({id: 1, session_id: "cs_log", role: "agent", who: "adaptation", kind: "text", text: "Hello", card: null, pause: null, answered_by: null, task_id: null,
  state: "ok", at: "2026-11-04T10:00:00Z", ...over});
const asked = (id, text, over = {}) => msg({id, role: "user", who: "user", text, ask: "q", ...over});
const answered = (id, text, from = "records", over = {}) => msg({id, role: "agent", who: "adaptation", text, ask: from, ...over});
const log = (over = {}) => ({id: "cs_log", node_id: "web.adaptation", kind: "function", title: "Adaptation", writable: false, status: "active", connector: "claude", note: "", ...over});
const items = (messages, session = log()) => CV.transcriptItems(session, messages, {deptName: "Web"});

// every tag the markup opens is closed, in order (br is the one void tag the module writes)
function wellFormed(html) {
  const stack = [];
  for (const m of html.matchAll(/<(\/?)([A-Za-z][\w-]*)[^>]*?(\/?)>/g)) {
    if (m[3] === "/" || m[2] === "br") continue;
    if (m[1] === "/") assert.equal(stack.pop(), m[2], "closes " + m[2]);
    else stack.push(m[2]);
  }
  assert.deepEqual(stack, [], "unclosed tags");
}

test("the owner's question is the owner's own line, labelled You asked, and marked as an ask line", () => {
  const html = items([asked(5, "Why was W-3 scored low?")])[0].html;
  assert.match(html, /^<div class="nmsg sb me" data-id="5" data-who="user" data-kind="text" data-state="ok" data-ask="q">/);
  assert.match(html, /<small class="nask">You asked<\/small>Why was W-3 scored low\?<\/div>$/);
  wellFormed(html);
});

test("an answer from the records is the function's line with the label that says no model was called", () => {
  const html = items([answered(6, "It missed the gate.", "records")])[0].html;
  assert.match(html, /^<div class="nmsg sb team" data-id="6" data-who="adaptation" data-kind="text" data-state="ok" data-ask="records">/);
  assert.match(html, /<small>Strategist \(Adaptation\)<\/small>It missed the gate\.<span class="nasksrc">From its records, no AI call<\/span><\/div>$/);
  wellFormed(html);
});

test("an answer a model wrote from the records says so", () => {
  const html = items([answered(7, "Because **W-3** missed the gate.\nIt scored 0.71.", "model")])[0].html;
  assert.match(html, /data-ask="model"/);
  assert.match(html, /Because <b>W-3<\/b> missed the gate\.<br\/>It scored 0\.71\.<span class="nasksrc">AI answer from its records<\/span>/);
  wellFormed(html);
});

test("question and answer keep their place among the function's other lines, each with its own key", () => {
  const got = items([msg({id: 1, text: "Planning W-3."}), asked(2, "Why?"), answered(3, "Because."), msg({id: 4, text: "Back to work."})]);
  assert.deepEqual(got.map(i => i.key), ["m1", "m2", "m3", "m4"]);
  assert.deepEqual(got.map(i => /data-ask="(\w+)"/.exec(i.html) && /data-ask="(\w+)"/.exec(i.html)[1]), [null, "q", "records", null]);
  assert.doesNotMatch(got[0].html, /nask|nasksrc/);
  assert.doesNotMatch(got[3].html, /nask|nasksrc/);
});

test("a line with no ask, an unknown one, or a note to the agent is drawn as it always was", () => {
  const plain = items([msg({id: 1, text: "Hello"})])[0].html;
  for (const over of [{ask: "other"}, {ask: ""}, {ask: null}, {ask: 5}]) assert.equal(items([msg({id: 1, text: "Hello", ...over})])[0].html, plain);
  const note = items([msg({id: 2, role: "user", who: "user", text: "Check the footer.", steer: true})])[0].html;
  assert.doesNotMatch(note, /nask|data-ask/);
  assert.match(note, /^<div class="nmsg sb me"/);
  assert.equal(CV.askOf(msg({ask: "q"})), "q");
  assert.equal(CV.askOf(msg({ask: "records"})), "records");
  assert.equal(CV.askOf(msg({ask: "model"})), "model");
  assert.equal(CV.askOf(msg({ask: "x"})), "");
  assert.equal(CV.askOf(null), "");
  assert.deepEqual(CV.ASK_WORDS, {q: "You asked", records: "From its records, no AI call", model: "AI answer from its records"});
});

test("the words of a question and of an answer are escaped like every other line", () => {
  const evil = '<img src=x onerror="alert(1)"> & <script>';
  for (const html of [items([asked(1, evil)])[0].html, items([answered(2, evil, "model")])[0].html]) {
    assert.doesNotMatch(html, /<img|<script/);
    assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt; &amp; &lt;script&gt;/);
    wellFormed(html);
  }
});

test("an ask line reads the same in a department's chat and in a past run's archived function chat", () => {
  const dept = {id: "cs_x", node_id: "web", kind: "department", title: "Web", writable: true, status: "active", connector: "claude", note: ""};
  const archived = log({status: "archived", writable: false});
  for (const session of [dept, archived]) {
    const html = items([asked(1, "Why?"), answered(2, "Because.")], session).map(i => i.html).join("");
    assert.match(html, /<small class="nask">You asked<\/small>Why\?/);
    assert.match(html, /Because\.<span class="nasksrc">From its records, no AI call<\/span>/);
  }
});

test("the transcript string is the same lines as the items", () => {
  const list = [asked(1, "Why?"), answered(2, "Because.", "model")];
  assert.equal(CV.transcript(log(), list, {deptName: "Web"}), items(list).map(i => i.html).join(""));
});
