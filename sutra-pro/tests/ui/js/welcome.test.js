"use strict";
// Welcome (sutra_app/ui/static/js/welcome.js): the first-run card of Home (gap package welcome-settings, item 1).
// The words come from GET /api/ops/welcome; "Got it" is stored on the server, "Not now" is this page load only and writes nothing.
// Run with: node --test tests/ui/js/welcome.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Welcome = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/welcome.js"));
const {welcomeHtml, humanBytes, load, acknowledge, mount, start} = Welcome;

const READY = {name: "claude", state: "ready", why: "", fix: ""};
const CODEX_OUT = {name: "codex", state: "not_ready", why: "0.9: not signed in", fix: "run `codex login`"};
const FACTS = {
  models: [READY, CODEX_OUT],
  data: {dir: "/data/sutra-pro", db_bytes: 12.5 * 1024 * 1024, free_bytes: 40 * 1024 ** 3, backup: "sutra-pro backup"},
  egress: {scrub: true, api_key_refused: true, only_your_cli: true},
  autonomy: {budget: 30, send_mode: "dry-run", asks: true},
};
const clone = v => JSON.parse(JSON.stringify(v));

/* ---------------------------------------------------------------- the words */
test("the four facts are there, numbered, each with a reading", () => {
  const html = welcomeHtml(FACTS);
  assert.match(html, /role="dialog" aria-modal="true" aria-labelledby="swtitle"/);
  for (const title of ["Which model answers", "Where your files are", "What leaves this computer", "What Sutra does alone, and what it asks"]) assert.ok(html.includes(title), title);
  assert.equal((html.match(/class="swnum"/g) || []).length, 4);
  assert.match(html, /<code class="swdir">\/data\/sutra-pro<\/code>/);
  assert.match(html, /12\.5 MB/);
  assert.match(html, /40\.0 GB is free/);
  assert.match(html, /<code>sutra-pro backup<\/code>/);
  assert.match(html, /budget of 30 work credits/);
  assert.match(html, /drafts only: nothing is sent/);
});

test("a model that cannot answer shows its reason and the fix line, and is not called Ready", () => {
  const html = welcomeHtml({...FACTS, models: [CODEX_OUT, {name: "claude", state: "not_ready", why: "not found on PATH", fix: "install the claude CLI, then run `claude auth login`"}]});
  assert.match(html, /Nothing can answer yet/);
  assert.match(html, /0\.9: not signed in/);
  assert.match(html, /To fix it: <code>run `codex login`<\/code>/);
  assert.match(html, /To fix it: <code>install the claude CLI, then run `claude auth login`<\/code>/);
  assert.doesNotMatch(html, /Ready/);
  assert.doesNotMatch(html, /data-state="ready"/);
});

test("with one model ready the card says so and still lists the other with its fix", () => {
  const html = welcomeHtml(FACTS);
  assert.match(html, /These models can answer on this machine/);
  assert.match(html, /<b>Claude<\/b> <span class="swchip st-ok">Ready<\/span>/);
  assert.match(html, /<b>Codex<\/b> <span class="swchip st-bad">Cannot answer<\/span>/);
  assert.match(html, /run `codex login`/);
});

test("a provider that is cooling down is Waiting, with its reason and no fix", () => {
  const html = welcomeHtml({...FACTS, models: [{name: "claude", state: "blocked", why: "usage limit reached", fix: ""}]});
  assert.match(html, /Waiting/);
  assert.match(html, /usage limit reached/);
  assert.doesNotMatch(html, /To fix it/);
});

test("offline the stub answers and the card says no real model is called", () => {
  const html = welcomeHtml({...FACTS, models: [{name: "stub", state: "stub", why: "Offline mode: a built-in stub answers, no real model is called.", fix: ""}]});
  assert.match(html, /These models can answer on this machine/);
  assert.match(html, /The built-in stub<\/b> <span class="swwhy">Offline mode: a built-in stub answers, no real model is called\./);
  assert.doesNotMatch(html, /Ready/);
});

test("no models at all is said, not hidden", () => {
  assert.match(welcomeHtml({...FACTS, models: []}), /could not read which models are installed/);
  assert.match(welcomeHtml({}), /could not read which models are installed/);
});

test("the copy never claims an API key is used: it says the key is refused", () => {
  const html = welcomeHtml(FACTS);
  assert.match(html, /never uses an API key/);
  assert.match(html, /refuses one/);
  assert.doesNotMatch(html, /uses (your|an|the) API key(?!.*refuses)/);
  assert.match(html, /own subscription/);
  assert.match(html, /key, token or password is removed from a chat message/);
});

test("the copy does not promise a scrub for a team's prompts: they go out as written and only a count-only note is kept (D109)", () => {
  const html = welcomeHtml(FACTS);
  assert.match(html, /team's own prompts go out as written/);
  assert.match(html, /keep keys out of a brief/);
  assert.doesNotMatch(html, /removed before a message leaves/);
});

test("the email line follows the engine's mode and is left out when it is not known", () => {
  assert.match(welcomeHtml({...FACTS, autonomy: {budget: 5, send_mode: "live"}}), /sent for real/);
  const none = welcomeHtml({...FACTS, autonomy: {budget: null, send_mode: null}});
  assert.doesNotMatch(none, /Emails a team writes/);
  assert.match(none, /inside a budget for each run/);
});

test("what leaves the machine mentions the automatic update check: what it asks, how often, that it sends nothing about you, and where to turn it off", () => {
  const on = clone(FACTS);
  on.egress.auto_update = {on: true, desktop: true};
  const html = welcomeHtml(on);
  assert.match(html, /desktop app asks GitHub for the list of Sutra Pro releases about a minute after it opens and every 6 hours/);
  assert.match(html, /one request, and nothing about you or your files is sent/);
  assert.match(html, /installed only when you say so/);
  assert.match(html, /turn this off in Settings, About/);
  assert.match(html, /never check by themselves\.<\/p>/);
  assert.match(html, /never uses an API key/);                                                    // the old sentences stay
  assert.match(html, /No usage data is sent to Sutra\./);
  const browser = welcomeHtml({...on, egress: {...on.egress, auto_update: {on: true, desktop: false}}});
  assert.match(browser, /this copy was not started by the desktop app, so it makes no automatic check/);
  const off = welcomeHtml({...on, egress: {...on.egress, auto_update: {on: false, desktop: true}}});
  assert.match(off, /automatic check for a newer Sutra Pro is switched off \(Settings, About\)/);
  assert.doesNotMatch(off, /about a minute after it opens/);
  assert.doesNotMatch(welcomeHtml(FACTS), /GitHub/);                                              // an older server's answer has no such field: no paragraph, no crash
  assert.doesNotMatch(welcomeHtml({...on, egress: {auto_update: "yes"}}), /GitHub/);
});

test("every word from the wire is escaped", () => {
  const evil = '<img src=x onerror="1">';
  const html = welcomeHtml({models: [{name: evil, state: "not_ready", why: evil, fix: evil}], data: {dir: evil, backup: evil, db_bytes: 1, free_bytes: 1},
    egress: {}, autonomy: {send_mode: evil, budget: evil}});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;1&quot;&gt;/);
});

test("sizes are in words, and a number that is not one is unknown", () => {
  assert.equal(humanBytes(0), "0 B");
  assert.equal(humanBytes(1536), "1.5 KB");
  assert.equal(humanBytes(null), "unknown");
  assert.equal(humanBytes(-1), "unknown");
  assert.equal(humanBytes("12"), "unknown");
});

/* ---------------------------------------------------------------- the server half */
function fakeApi(handlers) {
  const calls = [];
  const run = (method, p, body) => {
    calls.push({method, path: p, body});
    const answer = handlers[method + " " + p];
    if (answer instanceof Error) return Promise.reject(answer);
    return Promise.resolve(answer);
  };
  return {calls, get: p => run("GET", p), post: (p, b) => run("POST", p, b)};
}

test("load reads the welcome route and a failure is null, never a throw", async () => {
  const ok = fakeApi({"GET /api/ops/welcome": {seen: false, facts: FACTS}});
  assert.deepEqual(await load(ok), {seen: false, facts: FACTS});
  assert.equal(await load(fakeApi({"GET /api/ops/welcome": new Error("down")})), null);
  assert.equal(await load(fakeApi({"GET /api/ops/welcome": {oops: 1}})), null);
  assert.deepEqual(await load(fakeApi({"GET /api/ops/welcome": {seen: true, facts: null}})), {seen: true, facts: null});
});

test("acknowledge is one POST and says whether the server stored it", async () => {
  const api = fakeApi({"POST /api/ops/welcome/seen": {seen: true}});
  assert.equal(await acknowledge(api), true);
  assert.deepEqual(api.calls, [{method: "POST", path: "/api/ops/welcome/seen", body: {}}]);
  assert.equal(await acknowledge(fakeApi({"POST /api/ops/welcome/seen": new Error("401")})), false);
});

/* ---------------------------------------------------------------- the card in a page */
function fakeDoc() {
  const buttons = {
    "welcome-gotit": {dataset: {act: "welcome-gotit"}, focused: 0, focus() { this.focused += 1; doc.activeElement = this; }},
    "welcome-later": {dataset: {act: "welcome-later"}, focused: 0, focus() { this.focused += 1; doc.activeElement = this; }},
  };
  const body = {children: [], appendChild(el) { el.parentNode = body; body.children.push(el); }, removeChild(el) { body.children = body.children.filter(c => c !== el); el.parentNode = null; }};
  const opener = {focused: 0, focus() { this.focused += 1; doc.activeElement = this; }};
  const doc = {
    body, activeElement: opener, opener,
    createElement() {
      const el = {listeners: {}, innerHTML: "", id: "", className: "", parentNode: null,
        addEventListener(type, fn) { el.listeners[type] = fn; },
        querySelector(sel) { const m = /data-act="([^"]+)"/.exec(sel); return m ? buttons[m[1]] : null; },
        querySelectorAll() { return [buttons["welcome-gotit"], buttons["welcome-later"]]; }};
      return el;
    },
  };
  return {doc, buttons, click(el, act) { el.listeners.click({target: {closest: () => buttons[act]}}); }, key(el, key, extra) {
    const e = Object.assign({key, shiftKey: false, prevented: false, preventDefault() { this.prevented = true; }}, extra);
    el.listeners.keydown(e);
    return e;
  }};
}

test("the card is mounted on <body> as a dialog, outside the page's own tree, and Got it takes the focus", () => {
  const f = fakeDoc();
  const card = mount(f.doc, FACTS, fakeApi({}));
  assert.equal(f.doc.body.children.length, 1);
  assert.equal(card.el.id, "swelcome");
  assert.match(card.el.innerHTML, /aria-modal="true"/);
  assert.equal(f.buttons["welcome-gotit"].focused, 1);
});

test("Not now removes the card, gives the focus back and writes nothing anywhere", () => {
  const f = fakeDoc();
  const api = fakeApi({});
  const card = mount(f.doc, FACTS, api);
  f.click(card.el, "welcome-later");
  assert.equal(f.doc.body.children.length, 0);
  assert.equal(f.doc.opener.focused, 1);
  assert.deepEqual(api.calls, []);                                  // no server call: this load only
  assert.equal(card.notNow(), false);                               // a second press does nothing
});

test("Esc is Not now: it closes the card and writes nothing", () => {
  const f = fakeDoc();
  const api = fakeApi({});
  const card = mount(f.doc, FACTS, api);
  const e = f.key(card.el, "Escape");
  assert.equal(e.prevented, true);
  assert.equal(card.isOpen(), false);
  assert.deepEqual(api.calls, []);
});

test("Got it asks the server to remember, then closes", async () => {
  const f = fakeDoc();
  const api = fakeApi({"POST /api/ops/welcome/seen": {seen: true}});
  const card = mount(f.doc, FACTS, api);
  assert.equal(await card.gotIt(), true);
  assert.equal(api.calls.length, 1);
  assert.equal(f.doc.body.children.length, 0);
  assert.equal(await card.gotIt(), false);                          // the card is gone: no second POST
  assert.equal(api.calls.length, 1);
});

test("a Got it the server could not store still closes the card", async () => {
  const f = fakeDoc();
  const card = mount(f.doc, FACTS, fakeApi({"POST /api/ops/welcome/seen": new Error("401")}));
  assert.equal(await card.gotIt(), false);
  assert.equal(card.isOpen(), false);
});

test("Tab stays inside the card: from the last button to the first, and Shift+Tab the other way", () => {
  const f = fakeDoc();
  const card = mount(f.doc, FACTS, fakeApi({}));
  f.doc.activeElement = f.buttons["welcome-later"];
  const forward = f.key(card.el, "Tab");
  assert.equal(forward.prevented, true);
  assert.equal(f.doc.activeElement, f.buttons["welcome-gotit"]);
  const back = f.key(card.el, "Tab", {shiftKey: true});
  assert.equal(back.prevented, true);
  assert.equal(f.doc.activeElement, f.buttons["welcome-later"]);
  f.doc.activeElement = f.buttons["welcome-gotit"];
  assert.equal(f.key(card.el, "Tab").prevented, false);             // in the middle the browser moves on by itself
});

test("start shows the card only when the owner has not said Got it and there are facts", async () => {
  const f = fakeDoc();
  assert.equal(await start(f.doc, fakeApi({"GET /api/ops/welcome": {seen: true, facts: null}})), null);
  assert.equal(await start(f.doc, fakeApi({"GET /api/ops/welcome": new Error("404")})), null);
  assert.equal(await start(f.doc, fakeApi({"GET /api/ops/welcome": {seen: false, facts: null}})), null);
  assert.equal(f.doc.body.children.length, 0);
  const card = await start(f.doc, fakeApi({"GET /api/ops/welcome": {seen: false, facts: clone(FACTS)}}));
  assert.ok(card && f.doc.body.children.length === 1);
});
