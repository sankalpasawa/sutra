"use strict";
// ChatPill (sutra_app/ui/static/js/chat_pill.js): the provider pill, the streaming indicator and the switch notice (work package ABS-9).
// Ports the intent of the old app's test_chat_pill.js and test_chat_ai_provider.js: a provider that cannot run is never offered.
// Run with: node --test tests/ui/js/chat_pill.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatPill = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_pill.js"));
const {pill, selectable, choiceRequest, partial, settle, indicator, switchNotice} = ChatPill;

const READY = [{name: "claude", ready: true, why_not: ""}, {name: "codex", ready: true, why_not: ""}];
const CODEX_OUT = [{name: "claude", ready: true, why_not: ""}, {name: "codex", ready: false, why_not: "not signed in"}];

test("both ready providers are buttons and the chosen one is pressed", () => {
  const html = pill(READY, "codex");
  assert.match(html, /data-provider="claude" aria-pressed="false"/);
  assert.match(html, /class="cpill-opt on" data-act="choose-provider" data-provider="codex" aria-pressed="true"/);
  assert.match(html, /Let the app choose/);
});

test("a provider that cannot run is never a button: it is a label with its reason", () => {
  const html = pill(CODEX_OUT, "");
  assert.equal((html.match(/data-provider="codex"/g) || []).length, 0);
  assert.match(html, /<span class="cpill-opt off" title="not signed in">Codex <small>not signed in<\/small><\/span>/);
  assert.deepEqual(selectable(CODEX_OUT), ["claude"]);
});

test("with nothing chosen the pill says the app chooses and offers no clear button", () => {
  const html = pill(READY, "");
  assert.match(html, /chosen by the app/);
  assert.doesNotMatch(html, /Let the app choose/);
});

test("nothing is drawn without providers, and unknown providers are dropped", () => {
  assert.equal(pill([], ""), "");
  assert.equal(pill(null, ""), "");
  assert.deepEqual(selectable([{name: "gemini", ready: true}, {name: "claude", ready: true}]), ["claude"]);
});

test("everything from the wire is escaped", () => {
  const html = pill([{name: "claude", ready: true, why_not: ""}, {name: "codex", ready: false, why_not: '<img src=x onerror="1">'}], "");
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;1&quot;&gt;/);
});

test("the choice request is one PUT, null clears, an unknown name clears too", () => {
  assert.deepEqual(choiceRequest("cs_a1b2c3d4e5f6", "codex"), {method: "PUT", path: "/api/chats/cs_a1b2c3d4e5f6/choice", body: {provider: "codex"}});
  assert.deepEqual(choiceRequest("cs_x", null).body, {provider: null});
  assert.deepEqual(choiceRequest("cs_x", "gemini").body, {provider: null});
  assert.equal(choiceRequest("a/b", "claude").path, "/api/chats/a%2Fb/choice");
});

test("partials add up, settle clears, and the indicator is empty when nothing streams", () => {
  let s = ChatPill.idle();
  assert.equal(indicator(s, "claude"), "");
  s = partial(s, {data: {delta: "Hel"}});
  s = partial(s, {delta: "lo\nthere"});
  assert.equal(s.text, "Hello\nthere");
  assert.match(indicator(s, "codex"), /Codex is writing/);
  assert.match(indicator(s, "codex"), /Hello<br\/>there/);
  assert.equal(indicator(settle(s), "codex"), "");
});

test("the streamed text is bounded and escaped", () => {
  let s = partial(ChatPill.idle(), {delta: "x".repeat(9000)});
  assert.equal(s.text.length, 4000);
  s = partial(ChatPill.idle(), {delta: "<script>alert(1)</script>"});
  assert.doesNotMatch(indicator(s, ""), /<script>/);
  assert.match(indicator(s, ""), /The model is writing/);
});

test("the switch notice names both providers and what was carried", () => {
  assert.equal(switchNotice({kind: "switched", data: {from: "claude", to: "codex", plan: {kept_messages: 40, omitted: 0}}}), "Switched Claude to Codex; carried 40 messages");
  assert.equal(switchNotice({from: "codex", to: "claude", plan: {kept_messages: 1}}), "Switched Codex to Claude; carried 1 message");
  assert.equal(switchNotice({from: "claude", to: "codex", plan: {kept_messages: 40, omitted: 20}}), "Switched Claude to Codex; carried 40 messages, 20 earlier shortened");
  assert.equal(switchNotice({from: "claude", to: "codex", plan: {kept_messages: 0}}), "Switched Claude to Codex; nothing to carry");
  assert.equal(switchNotice({}), "");
  assert.equal(switchNotice(null), "");
});
