"use strict";
// ModelPick (sutra_app/ui/static/js/model_pick.js): the model list and the effort under a chat's provider buttons (welcome-settings, item 4).
// Run with: node --test tests/ui/js/model_pick.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ModelPick = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/model_pick.js"));
const ChatPill = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_pill.js"));
const {pickHtml, choiceRequest, selectRequest, modelOf} = ModelPick;

const FIVE = ["low", "medium", "high", "xhigh", "max"];
const opt = (slug, label, note, group, efforts) => ({slug, label, note, group: group || "main", efforts: efforts || FIVE});
const CLAUDE = {
  name: "claude", ready: true, why_not: "", model: "sonnet", chat_model: null, chat_effort: null, can_pick: true,
  model_options: [opt("best", "Best available", "the newest model this account can run"), opt("opus", "Opus", "most capable, slowest, highest cost"),
    opt("sonnet", "Sonnet", "balanced default for most work"), opt("haiku", "Haiku", "fastest and cheapest, least capable"),
    opt("claude-opus-4-8", "Opus 4.8", "pinned snapshot", "more"), opt("opus[1m]", "Opus, 1M context", "Opus with the 1M-token window requested explicitly", "more")],
};
const CODEX = {name: "codex", ready: true, why_not: "", model: "gpt-wide", chat_model: null, chat_effort: null, can_pick: true,
  model_options: [opt("gpt-wide", "GPT Wide", "", "main", ["low", "medium", "high"]), opt("gpt-slim", "GPT Slim", "", "main", ["low", "medium"])]};
const clone = v => JSON.parse(JSON.stringify(v));

test("the main rows come first with their note each, and the pinned snapshots and 1M spellings sit under More models", () => {
  const html = pickHtml(CLAUDE);
  assert.match(html, /<select class="cpick-model" data-act="choose-model" data-provider="claude" aria-label="Model for Claude">/);
  const main = html.slice(html.indexOf('<option value="best"'), html.indexOf("<optgroup"));
  assert.deepEqual([...main.matchAll(/<option value="([^"]+)"/g)].map(m => m[1]), ["best", "opus", "sonnet", "haiku"]);
  assert.match(html, /Best available - the newest model this account can run/);
  assert.match(html, /Opus - most capable, slowest, highest cost/);
  assert.match(html, /Haiku - fastest and cheapest, least capable/);
  const more = html.slice(html.indexOf("<optgroup"), html.indexOf("</optgroup>"));
  assert.match(more, /<optgroup label="More models">/);
  assert.deepEqual([...more.matchAll(/<option value="([^"]+)"/g)].map(m => m[1]), ["claude-opus-4-8", "opus[1m]"]);
});

test("the policy's model is the one shown until the chat has its own, and the chat's own wins", () => {
  assert.equal(modelOf(CLAUDE), "sonnet");
  assert.match(pickHtml(CLAUDE), /<option value="sonnet" selected title="balanced default for most work">/);
  const own = pickHtml({...CLAUDE, chat_model: "haiku", chat_effort: "max"});
  assert.match(own, /<option value="haiku" selected/);
  assert.doesNotMatch(own, /<option value="sonnet" selected/);
  assert.match(own, /<option value="max" selected>max<\/option>/);
  assert.doesNotMatch(own, /value="" selected/);
});

test("the note of the chosen model is shown under the selects", () => {
  assert.match(pickHtml({...CLAUDE, chat_model: "opus"}), /<span class="cpick-note">most capable, slowest, highest cost<\/span>/);
});

test("the effort select lists only the values the model accepts, and says Default until the chat has one", () => {
  const codex = pickHtml({...CODEX, chat_model: "gpt-slim", chat_effort: "low"});
  assert.deepEqual([...codex.slice(codex.indexOf("cpick-effort")).matchAll(/<option value="([^"]*)"/g)].map(m => m[1]), ["low", "medium"]);
  assert.match(pickHtml(CLAUDE), /<select class="cpick-effort"[^>]*><option value="" selected>Default<\/option><option value="low">low<\/option>/);
  const stale = pickHtml({...CODEX, chat_model: "gpt-slim", chat_effort: "max"});
  assert.match(stale, /<option value="max" selected>max \(the nearest this model accepts is used\)<\/option>/);
});

test("a model the list does not name is still shown as the chosen one", () => {
  const html = pickHtml({...CLAUDE, model: "claude-legacy-9"});
  assert.match(html, /<option value="claude-legacy-9" selected>claude-legacy-9<\/option>/);
});

test("a chat whose session runs on the other provider says the model waits for the switch and draws no select", () => {
  const html = pickHtml({...CODEX, can_pick: false});
  assert.match(html, /The model and effort of Codex can be chosen after your next message/);
  assert.doesNotMatch(html, /<select/);
});

test("nothing is drawn for a provider that cannot run, or one with no list", () => {
  assert.equal(pickHtml({...CLAUDE, ready: false}), "");
  assert.equal(pickHtml({...CLAUDE, model_options: []}), "");
  assert.equal(pickHtml({name: "claude", ready: true}), "");
  assert.equal(pickHtml(null), "");
});

test("everything from the wire is escaped", () => {
  const evil = '<img src=x onerror="1">';
  const html = pickHtml({name: "claude", ready: true, model: evil, chat_effort: evil, model_options: [opt(evil, evil, evil, "more", ["low"]), opt("a", evil, evil)]});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;1&quot;&gt;/);
});

test("a model change is one PUT with the model and nothing else, an effort change one PUT with the effort", () => {
  assert.deepEqual(choiceRequest("cs_a1b2c3d4e5f6", "claude", {model: "opus"}),
    {method: "PUT", path: "/api/chats/cs_a1b2c3d4e5f6/choice", body: {provider: "claude", model: "opus"}});
  assert.deepEqual(choiceRequest("cs_x", "codex", {effort: "high"}).body, {provider: "codex", effort: "high"});
  assert.deepEqual(choiceRequest("cs_x", "claude", {}).body, {provider: "claude"});
  assert.deepEqual(choiceRequest("cs_x", "gemini", {model: "x"}).body, {provider: null});            // an unknown provider clears, as ChatPill does
  assert.equal(choiceRequest("a/b", "claude", {model: "opus"}).path, "/api/chats/a%2Fb/choice");
});

test("selectRequest sends only a value the list offers and only for a provider that can run", () => {
  const providers = [CLAUDE, CODEX, {...clone(CODEX), name: "codex", ready: false}];
  assert.deepEqual(selectRequest("cs_x", [CLAUDE, CODEX], "choose-model", "claude", "haiku").body, {provider: "claude", model: "haiku"});
  assert.equal(selectRequest("cs_x", [CLAUDE, CODEX], "choose-model", "claude", "opuss"), null);                // a typo is never sent
  assert.equal(selectRequest("cs_x", [CLAUDE, CODEX], "choose-model", "gemini", "x"), null);
  assert.equal(selectRequest("cs_x", [CLAUDE, CODEX], "choose-model", "claude", "gpt-wide"), null);              // another provider's name is not in this list
  assert.deepEqual(selectRequest("cs_x", [CLAUDE, CODEX], "choose-effort", "claude", "xhigh").body, {provider: "claude", effort: "xhigh"});
  assert.equal(selectRequest("cs_x", [CLAUDE, CODEX], "choose-effort", "claude", "ultra"), null);
  const slim = {...CODEX, chat_model: "gpt-slim"};
  assert.equal(selectRequest("cs_x", [slim], "choose-effort", "codex", "high"), null);                        // gpt-slim takes low and medium only
  assert.deepEqual(selectRequest("cs_x", [slim], "choose-effort", "codex", "medium").body, {provider: "codex", effort: "medium"});
  assert.equal(selectRequest("cs_x", [CLAUDE], "oops", "claude", "opus"), null);
  assert.equal(selectRequest("cs_x", providers.slice(2), "choose-model", "codex", "gpt-wide"), null);              // a provider that cannot run
  assert.equal(selectRequest("cs_x", null, "choose-model", "claude", "opus"), null);
});

/* ---------------------------------------------------------------- inside the pill */
test("the pill draws the picker under the buttons of the chosen provider only, and not for the app's own choice", () => {
  const providers = [CLAUDE, CODEX];
  const html = ChatPill.pill(providers, "claude");
  assert.ok(html.indexOf('class="cpill"') < html.indexOf('class="cpick"'));
  assert.equal((html.match(/class="cpick"/g) || []).length, 1);
  assert.match(html, /<div class="cpick" data-provider="claude">/);
  assert.doesNotMatch(ChatPill.pill(providers, ""), /cpick/);                                          // nothing pinned: a model needs its provider
  assert.match(ChatPill.pill(providers, "codex"), /<div class="cpick" data-provider="codex">/);
  assert.doesNotMatch(ChatPill.pill([CLAUDE, {...CODEX, ready: false, why_not: "not signed in"}], "codex"), /cpick/);
});

test("the pill is as it was when the providers carry no model list", () => {
  const html = ChatPill.pill([{name: "claude", ready: true, why_not: ""}], "claude");
  assert.doesNotMatch(html, /cpick/);
  assert.match(html, /class="cpill-opt on"/);
});
