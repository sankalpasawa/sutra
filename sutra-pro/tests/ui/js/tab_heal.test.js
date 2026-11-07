"use strict";
// TabHeal (sutra_app/ui/static/js/tab_heal.js) and its rider in sutra_ctx.js: a page that outlives a server restart (welcome-settings, item 5).
// A restart kills the launch token of every open tab (D81). The next write is refused with 401 `bad_token`; the page reads its own boot block again,
// takes the fresh token and repeats that one write, once. Run with: node --test tests/ui/js/tab_heal.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const HEAL_CODE = fs.readFileSync(path.join(JS, "tab_heal.js"), "utf8");
const CTX_CODE = fs.readFileSync(path.join(JS, "sutra_ctx.js"), "utf8");
const TabHeal = require(path.join(JS, "tab_heal.js"));

const OLD = "old-token-0123456789abcdef";
const NEW = "new-token-0123456789abcdef";
const BOOT = {page: "dept", token: OLD, dept: "web", dept_label: "Web", archived: false, note: "", version: "0.1.0"};
const HOME = {page: "home", token: OLD, dept: "", dept_label: "", archived: false, note: "", version: "0.1.0"};

// the page as the server renders it (boot.py render_page): the boot block with every `<` escaped
const pageWith = boot => '<!doctype html><html><head><script type="application/json" id="sutra-boot">' + JSON.stringify(boot).replace(/</g, "\\u003c") +
  "</script></head><body></body></html>";
const reply = (status, body) => ({
  status, ok: status >= 200 && status < 300,
  text: () => Promise.resolve(body === undefined ? "" : (typeof body === "string" ? body : JSON.stringify(body))),
  json: () => Promise.resolve(typeof body === "string" ? JSON.parse(body) : body),
  clone() { return reply(status, body); },
});
const DEAD = () => reply(401, {error: {code: "bad_token", message: "A valid X-Sutra-Token header is required for this request", details: {}}});
const OK = body => reply(200, body === undefined ? {ok: true} : body);

/* ---------------------------------------------------------------- parseBoot */
test("parseBoot reads the block of the same page and the same team", () => {
  assert.deepEqual(TabHeal.parseBoot(pageWith({...BOOT, token: NEW}), {page: "dept", dept: "web"}), {token: NEW, page: "dept", dept: "web"});
  assert.deepEqual(TabHeal.parseBoot(pageWith({...HOME, token: NEW}), {page: "home", dept: ""}), {token: NEW, page: "home", dept: ""});
  assert.deepEqual(TabHeal.parseBoot(pageWith({...HOME, token: NEW}), {page: "home"}), {token: NEW, page: "home", dept: ""});            // no dept is ""
});

test("parseBoot refuses a page of another kind or another team", () => {
  assert.equal(TabHeal.parseBoot(pageWith({...HOME, token: NEW}), {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith({...BOOT, token: NEW, dept: "sales"}), {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith({...BOOT, token: NEW, page: "console", dept: ""}), {page: "home", dept: ""}), null);
});

test("parseBoot refuses an oversized text, a short or missing token, bad JSON, no block, and a bad question", () => {
  const big = pageWith({...BOOT, token: NEW}) + " ".repeat(TabHeal.MAX_CHARS);
  assert.equal(TabHeal.parseBoot(big, {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith({...BOOT, token: "short"}), {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith({page: "dept", dept: "web"}), {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith({...BOOT, token: 12345678901234567890}), {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot('<script id="sutra-boot">{not json</script>', {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot('<script id="sutra-boot">[1,2]</script>', {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot("<html>no block</html>", {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(null, {page: "dept", dept: "web"}), null);
  assert.equal(TabHeal.parseBoot(pageWith(BOOT), null), null);
});

test("isDead is the 401 bad_token and nothing else", () => {
  assert.equal(TabHeal.isDead({status: 401, code: "bad_token"}), true);
  assert.equal(TabHeal.isDead({status: 403, code: "bad_origin"}), false);
  assert.equal(TabHeal.isDead({status: 401, code: "http_401"}), false);
  assert.equal(TabHeal.isDead(null), false);
});

/* ---------------------------------------------------------------- heal */
function healRig(answers, boot) {
  TabHeal.reset();
  const calls = [];
  const fetchFn = (url, init) => { calls.push({url, init}); const a = answers.length > 1 ? answers.shift() : answers[0]; return a instanceof Error ? Promise.reject(a) : Promise.resolve(a); };
  return {ctx: {boot: {...(boot || BOOT)}}, calls, fetchFn};
}

test("heal reads the page's own path and query without the cache and takes the fresh token", async () => {
  const r = healRig([reply(200, pageWith({...BOOT, token: NEW}))]);
  assert.equal(await TabHeal.heal(r.ctx, r.fetchFn, {location: {pathname: "/d/web/", search: "?tab=chat&run=r1"}}), true);
  assert.equal(r.ctx.boot.token, NEW);
  assert.equal(r.calls.length, 1);
  assert.equal(r.calls[0].url, "/d/web/?tab=chat&run=r1");
  assert.equal(r.calls[0].init.method, "GET");
  assert.equal(r.calls[0].init.cache, "no-store");
  assert.equal(JSON.stringify(r.calls[0].init.headers).includes("Token"), false);          // the old token is not sent anywhere
  assert.equal(r.ctx.boot.dept, "web");                                                      // nothing but the token changed
});

test("a heal that fails leaves the old token: a server error, a page of another team, a network error, the same token again", async () => {
  for (const answer of [reply(500, "boom"), reply(200, pageWith({...BOOT, token: NEW, dept: "sales"})), new Error("down"), reply(200, pageWith(BOOT)), reply(200, "<html></html>")]) {
    const r = healRig([answer]);
    assert.equal(await TabHeal.heal(r.ctx, r.fetchFn, {location: {pathname: "/d/web/", search: ""}}), false);
    assert.equal(r.ctx.boot.token, OLD);
  }
});

test("a path that could leave this origin is never fetched", async () => {
  for (const pathname of ["//evil.example/x", "/\\evil.example", ""]) {
    const r = healRig([reply(200, pageWith({...BOOT, token: NEW}))]);
    assert.equal(await TabHeal.heal(r.ctx, r.fetchFn, {location: {pathname, search: ""}}), false);
    assert.equal(r.calls.length, 0);
  }
});

test("callers that arrive while a heal runs share it, and a second heal within 60 s is refused (no loop)", async () => {
  const r = healRig([reply(200, pageWith({...BOOT, token: NEW}))]);
  const where = {location: {pathname: "/", search: ""}};
  let t = 1_000_000;
  const both = await Promise.all([TabHeal.heal(r.ctx, r.fetchFn, {...where, now: () => t}), TabHeal.heal(r.ctx, r.fetchFn, {...where, now: () => t})]);
  assert.deepEqual(both, [true, true]);
  assert.equal(r.calls.length, 1);
  assert.equal(await TabHeal.heal(r.ctx, r.fetchFn, {...where, now: () => t + 59_000}), false);       // the new token was refused too: stop
  assert.equal(r.calls.length, 1);
  const again = healRig([reply(200, pageWith({...BOOT, token: "third-token-0123456789abcdef"}))]);
  assert.equal(await TabHeal.heal(again.ctx, again.fetchFn, {...where, now: () => t + 61_000}), true);          // a minute later it may try again
});

/* ---------------------------------------------------------------- the rider in sutra_ctx.js */
function load(globals) {
  const sandbox = Object.assign({}, globals);
  vm.createContext(sandbox);
  vm.runInContext(HEAL_CODE, sandbox, {filename: "tab_heal.js"});
  vm.runInContext(CTX_CODE, sandbox, {filename: "sutra_ctx.js"});
  return sandbox;
}

// A page at `pathname` whose boot block says `boot`; `fetch` answers from a function (url, init, n) and keeps every call.
function page(boot, pathname, answer) {
  const calls = [];
  const fetch = function (url, init) {
    calls.push({url, init, token: init && init.headers ? (init.headers["X-Sutra-Token"] || null) : null});
    return Promise.resolve(answer(url, init, calls.length));
  };
  const sandbox = load({
    document: {getElementById: id => (id === "sutra-boot" ? {textContent: JSON.stringify(boot)} : null)},
    location: {pathname, search: "?tab=chat"}, URLSearchParams, fetch,
  });
  return {ctx: sandbox.SutraCtx, calls, sandbox};
}

const isPage = url => !String(url).startsWith("/api/");

test("a dead token heals: the write is repeated once with the fresh token, and the next request carries it too", async () => {
  const p = page(BOOT, "/d/web/", (url, init) => (isPage(url) ? reply(200, pageWith({...BOOT, token: NEW})) : (init.headers["X-Sutra-Token"] === NEW ? OK({sent: true}) : DEAD())));
  const got = await p.ctx.api.post("/api/chats/cs_x/messages", {text: "hello"});
  assert.deepEqual(JSON.parse(JSON.stringify(got)), {sent: true});
  assert.deepEqual(p.calls.map(c => [c.url, c.token]), [["/api/chats/cs_x/messages", OLD], ["/d/web/?tab=chat", null], ["/api/chats/cs_x/messages", NEW]]);
  assert.equal(p.calls[2].init.body, JSON.stringify({text: "hello"}));                          // the same words
  await p.ctx.api.put("/api/chats/cs_x/choice", {provider: "claude"});
  assert.equal(p.calls[3].token, NEW);                                                         // the token in a later request header is the new one
  assert.equal(p.ctx.boot.token, NEW);
});

test("the heal works on Home too", async () => {
  const p = page(HOME, "/", (url, init) => (isPage(url) ? reply(200, pageWith({...HOME, token: NEW})) : (init.headers["X-Sutra-Token"] === NEW ? OK() : DEAD())));
  assert.deepEqual(JSON.parse(JSON.stringify(await p.ctx.api.post("/api/ops/welcome/seen", {}))), {ok: true});
  assert.equal(p.calls.length, 3);
});

test("one retry only: a write still refused after the heal is the existing banner's 401, with no third request", async () => {
  const p = page(BOOT, "/d/web/", url => (isPage(url) ? reply(200, pageWith({...BOOT, token: NEW})) : DEAD()));
  let error;
  try { await p.ctx.api.post("/api/x", {a: 1}); } catch (e) { error = e; }
  assert.ok(error && error.status === 401 && error.code === "bad_token");
  assert.equal(p.calls.length, 3);
});

test("a non-401 is never retried, and a 401 with another code is not a dead token", async () => {
  for (const answer of [reply(403, {error: {code: "bad_origin", message: "x"}}), reply(422, {error: {code: "validation", message: "x"}}), reply(500, "boom"),
    reply(401, {error: {code: "unauthorized", message: "x"}}), reply(401, "no json")]) {
    const p = page(BOOT, "/d/web/", () => answer);
    let error;
    try { await p.ctx.api.post("/api/x", {a: 1}); } catch (e) { error = e; }
    assert.ok(error, "it still fails");
    assert.equal(p.calls.length, 1);
  }
});

test("a read is never healed: it carries no token", async () => {
  const p = page(BOOT, "/d/web/", () => DEAD());
  let error;
  try { await p.ctx.api.get("/api/graph"); } catch (e) { error = e; }
  assert.ok(error);
  assert.equal(p.calls.length, 1);
});

test("a heal that fails leaves the old token and the original refusal, so the page keeps its banner", async () => {
  for (const heal of [() => reply(500, "boom"), () => reply(200, pageWith({...BOOT, token: NEW, dept: "sales"})), () => reply(200, "<html></html>")]) {
    const p = page(BOOT, "/d/web/", url => (isPage(url) ? heal() : DEAD()));
    let error;
    try { await p.ctx.api.post("/api/x", {a: 1}); } catch (e) { error = e; }
    assert.ok(error && error.status === 401 && error.code === "bad_token");
    assert.equal(p.ctx.boot.token, OLD);
    assert.equal(p.calls.length, 2);                                                           // the write, the page; no retry
  }
});

test("without tab_heal.js the page behaves as before", async () => {
  const calls = [];
  const sandbox = Object.assign({}, {document: {getElementById: id => (id === "sutra-boot" ? {textContent: JSON.stringify(BOOT)} : null)},
    location: {pathname: "/d/web/", search: ""}, URLSearchParams, fetch: (url, init) => { calls.push(url); return Promise.resolve(DEAD()); }});
  vm.createContext(sandbox);
  vm.runInContext(CTX_CODE, sandbox, {filename: "sutra_ctx.js"});                                // no TabHeal global
  let error;
  try { await sandbox.SutraCtx.api.post("/api/x", {}); } catch (e) { error = e; }
  assert.ok(error && error.code === "bad_token");
  assert.equal(calls.length, 1);
});

/* ---------------------------------------------------------------- J2's own writes on a team page */
function j2Page(answer) {
  const calls = [];
  const fetch = function (url, init) {
    const token = init && init.headers ? (init.headers["X-Sutra-Token"] || (typeof init.headers.get === "function" ? init.headers.get("X-Sutra-Token") : null)) : null;
    calls.push({url, init, token});
    return Promise.resolve(answer(url, token, calls.length));
  };
  const sandbox = load({
    document: {getElementById: id => (id === "sutra-boot" ? {textContent: JSON.stringify(BOOT)} : null)},
    location: {pathname: "/d/web/", search: ""}, URLSearchParams, fetch,
  });
  return {ctx: sandbox.SutraCtx, sandbox, calls};
}

test("J2's wrapped fetch heals a refused write and repeats it once (a string body)", async () => {
  const p = j2Page((url, token) => (url.startsWith("/d/") ? reply(200, pageWith({...BOOT, token: NEW})) : (token === NEW ? OK({said: true}) : DEAD())));
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  const res = await p.sandbox.fetch("/api/say", {method: "POST", body: JSON.stringify({t: "hi"}), headers: {"Content-Type": "application/json"}});
  assert.equal(res.status, 200);
  assert.deepEqual(p.calls.map(c => [c.url, c.token]), [["/api/say?dept=web", OLD], ["/d/web/", null], ["/api/say?dept=web", NEW]]);
  assert.equal(p.calls[2].init.body, JSON.stringify({t: "hi"}));
});

test("J2's wrapped fetch does not repeat a body it cannot send twice, a GET, a non-401 or a failed heal: the caller gets its own response", async () => {
  const stream = {pipe() {}};                                                                   // not a string: it cannot be read again
  let p = j2Page(() => DEAD());
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  assert.equal((await p.sandbox.fetch("/api/say", {method: "POST", body: stream})).status, 401);
  assert.equal(p.calls.length, 1);
  p = j2Page(() => DEAD());
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  assert.equal((await p.sandbox.fetch("/api/state")).status, 401);
  assert.equal(p.calls.length, 1);
  p = j2Page(() => reply(403, {error: {code: "bad_origin", message: "x"}}));
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  assert.equal((await p.sandbox.fetch("/api/say", {method: "POST", body: "{}"})).status, 403);
  assert.equal(p.calls.length, 1);
  p = j2Page(url => (url.startsWith("/d/") ? reply(500, "boom") : DEAD()));
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  const refused = await p.sandbox.fetch("/api/say", {method: "POST", body: "{}"});
  assert.equal(refused.status, 401);
  assert.equal((await refused.json()).error.code, "bad_token");                                // the caller's response is still readable
  assert.equal(p.calls.length, 2);
});

test("J2's wrapped fetch retries once and no more when the fresh token is refused as well", async () => {
  const p = j2Page(url => (url.startsWith("/d/") ? reply(200, pageWith({...BOOT, token: NEW})) : DEAD()));
  p.sandbox.SutraCtx.installFetch(p.sandbox);
  assert.equal((await p.sandbox.fetch("/api/say", {method: "POST", body: "{}"})).status, 401);
  assert.equal(p.calls.length, 3);
});
