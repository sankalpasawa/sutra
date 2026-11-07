"use strict";
// ChatView's approval card draws the impact lines under its question (gap package chart-insight): what a merge or a split will do, as code-written
// lines (orchestrator/reorg_preview.py), only while the card is open, escaped, capped, and a card without them is byte for byte what it was.
// Run with: node --test tests/ui/js/chat_view_impact.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_view.js"));

const ORG = {id: "cs_org", node_id: "root", kind: "org", title: "Sutra", writable: true, status: "active"};
const QUESTION = "Merge Leads into Quotes? Their chats and history stay available.";
const LINES = ["The chat of Leads (6 messages) becomes read-only history under Quotes.", "The chat of Quotes (14 messages) stays open.", "Nothing is running in Leads."];
const approval = (over = {}) => Object.assign({type: "approval", change_id: "chg-0004", question: QUESTION,
  options: [{id: "yes", label: "Yes"}, {id: "no", label: "No"}]}, over);
const items = html => [...html.matchAll(/<li>(.*?)<\/li>/g)].map(m => m[1]);

test("an open approval card lists what a yes would do between the question and the buttons", () => {
  const html = ChatView.card(approval({impact: LINES}), {});
  assert.deepEqual(items(html), LINES);
  assert.match(html, /<p class="sq">Merge Leads into Quotes\? Their chats and history stay available\.<\/p><ul class="cimpact" aria-label="What a yes would do">/);
  assert.ok(html.indexOf("cimpact") < html.indexOf('data-act="choose"'), "the lines come before the buttons");
});

test("a card without impact, or with an empty one, is byte for byte what it was", () => {
  const plain = ChatView.card(approval(), {});
  assert.doesNotMatch(plain, /cimpact/);
  assert.equal(ChatView.card(approval({impact: []}), {}), plain);
  assert.equal(ChatView.card(approval({impact: "yes"}), {}), plain);
  assert.equal(ChatView.card(approval({impact: [null, "", "  ", {}]}), {}), plain);                   // lines with no words are not lines
});

test("an answered card no longer lists them: the answer is the news", () => {
  assert.doesNotMatch(ChatView.card(approval({impact: LINES}), {answer: "Yes"}), /cimpact/);
  assert.doesNotMatch(ChatView.card(approval({impact: LINES}), {answered: true}), /cimpact/);
});

test("the lines are escaped, kept to 8 of 160 characters, and a choice card never shows any", () => {
  const bad = `<script>alert("x")</script> & 'q'`;
  const html = ChatView.card(approval({impact: [bad]}), {});
  assert.equal(html.includes("<script"), false);
  assert.deepEqual(items(html), ["&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;q&#39;"]);
  const many = ChatView.card(approval({impact: Array.from({length: 12}, (_, i) => "line " + i + "x".repeat(200))}), {});
  assert.equal(items(many).length, 8);
  assert.ok(items(many).every(l => l.length <= 160));
  assert.doesNotMatch(ChatView.card({type: "choice", question: "Which?", options: ["A"], impact: LINES}, {}), /cimpact/);
});

test("the transcript draws the card the same way", () => {
  const msg = {id: 7, session_id: "cs_org", role: "agent", who: "sutra", kind: "card", text: "", state: "ok", at: "2026-11-04T10:00:00Z", card: approval({impact: LINES})};
  assert.deepEqual(items(ChatView.transcript(ORG, [msg], {})), LINES);
  assert.deepEqual(items(ChatView.transcript(ORG, [msg], {answers: {7: "No"}})), []);
});
