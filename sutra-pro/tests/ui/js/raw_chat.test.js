"use strict";
// RawChat (sutra_app/ui/static/js/raw_chat.js): the Raw AI chat debugger's pure parts: the Debug level gate, the /raw path, who made a call,
// the list row and the transcript (every word of the wire escaped, the search marked, SYSTEM folded unless the search is in it).
// Run with: node --test tests/ui/js/raw_chat.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const RawChat = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/raw_chat.js"));
const H = RawChat.helpers;

const store = v => ({getItem: k => (k === "sutra:level" ? v : null)});

test("the button belongs to the Debug level only, and a storage that throws reads as not debug", () => {
  assert.equal(H.isDebug(store("debug")), true);
  assert.equal(H.isDebug(store("manager")), false);
  assert.equal(H.isDebug(store(null)), false);
  assert.equal(H.isDebug({getItem: () => { throw new Error("blocked"); }}), false);
});

test("the full-screen path is /d/<team>/raw and nothing else", () => {
  assert.equal(H.onRawPath("/d/web/raw"), true);
  assert.equal(H.onRawPath("/d/web/raw/"), true);
  assert.equal(H.onRawPath("/d/web/"), false);
  assert.equal(H.onRawPath("/d/web/raw/x"), false);
  assert.equal(H.onRawPath("/d/web/library"), false);
});

test("a call is named after the studio person, a workflow builder or the function", () => {
  assert.equal(H.personOf("identity").name, "Asha");
  assert.equal(H.personOf("audit").name, "Nora");
  assert.equal(H.personOf("W-3").name, "Builder W-3");
  assert.equal(H.personOf("summary").name, "summary");
  assert.equal(H.personOf(undefined).name, "call");
});

test("tokens and cost read short", () => {
  assert.equal(H.fmtTokens({input: 12345, output: 87}), "12k in / 87 out");
  assert.equal(H.fmtTokens(null), "");
  assert.equal(H.fmtUsd(0.0042), "$0.0042");
  assert.equal(H.fmtUsd(0.5), "$0.500");
  assert.equal(H.fmtUsd(null), "");
});

test("a row escapes what the run wrote and shows the step, model and cost", () => {
  const html = H.rowHtml({id: 7, fn: "<b>x</b>", step: 3, cycle: 1, model: "sonnet", usd: 0.02, t: "10:00:01",
    tokens: {input: 10, output: 2}, prompt_preview: "<script>alert(1)</script>"}, true);
  assert.ok(!html.includes("<script>") && !html.includes("<b>x</b>"));
  assert.ok(html.includes("&lt;script&gt;") && html.includes("step 3.1") && html.includes("sonnet") && html.includes("$0.020"));
  assert.ok(html.includes('aria-pressed="true"') && html.includes('data-id="7"'));
});

test("the transcript holds the three turns in order, SYSTEM folded, and marks the search", () => {
  const rec = {id: 2, fn: "identity", system: "be <brief>", prompt: "Write a Plan. plan it.", raw: '{"to":"user"}', reply: {to: "user"}, reason: "why"};
  const html = H.transcriptHtml(rec, "");
  const at = k => html.indexOf(k);
  assert.ok(at("SYSTEM PROMPT") < at(">PROMPT<") && at(">PROMPT<") < at("RAW REPLY"));
  assert.ok(/<details class="rc-turn rc-system">/.test(html), "SYSTEM is folded");
  assert.ok(html.includes("be &lt;brief&gt;") && html.includes("PARSED REPLY") && html.includes("REASON"));
  const found = H.transcriptHtml(rec, "plan");
  assert.equal((found.match(/<mark>/g) || []).length, 2);
  assert.ok(found.includes("2 matches"));
  assert.ok(H.transcriptHtml(rec, "brief").includes('<details class="rc-turn rc-system" open>'), "a search hit in SYSTEM unfolds it");
  assert.ok(H.transcriptHtml(null, "").includes("Pick a call"));
});

test("marking never breaks the escaping", () => {
  assert.equal(H.markHtml("a<b>a", "a"), "<mark>a</mark>&lt;b&gt;<mark>a</mark>");
  assert.equal(H.markHtml("x&y", "&"), "x<mark>&amp;</mark>y");
  assert.equal(H.countOf("AaAa", "a"), 4);
  assert.equal(H.countOf("abc", ""), 0);
});
