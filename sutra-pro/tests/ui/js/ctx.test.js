"use strict";
// SutraCtx (sutra_app/ui/static/js/sutra_ctx.js): boot, department, J2_PATHS, the fetch wrapper, api, tab, esc, paint.
// Run with: node --test tests/ui/js/ctx.test.js
//
// The script is a classic browser script, so it is loaded the way a browser loads it: its text runs in a fresh vm context
// whose globals are fakes (document, location, fetch, ...). Objects made inside a context have that context's prototypes,
// so deep comparisons go through plain().
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.resolve(__dirname, "../../../sutra_app/ui/static/js/sutra_ctx.js");
const CODE = fs.readFileSync(FILE, "utf8");
const TOKEN = "tok-0123456789abcdef";
const BOOT = {page: "dept", token: TOKEN, dept: "web", dept_label: "Web", archived: false, note: "", version: "0.1.0"};

const plain = value => JSON.parse(JSON.stringify(value));

function load(globals = {}) {
  const sandbox = Object.assign({}, globals);
  vm.createContext(sandbox);
  vm.runInContext(CODE, sandbox, {filename: "sutra_ctx.js"});
  return sandbox;
}

// A document that holds the boot block: `boot` is an object (written as JSON), a string (written as it is), null (the JSON
// null) or false (no block at all).
function documentWith(boot, extra = {}) {
  return Object.assign({
    getElementById: id => (id === "sutra-boot" && boot !== false ? {textContent: typeof boot === "string" ? boot : JSON.stringify(boot)} : null),
  }, extra);
}

function browser(opts = {}) {
  const {boot = BOOT, pathname = "/d/web/", search = "", document, ...rest} = opts;
  return {document: document || documentWith(boot), location: {pathname, search}, URLSearchParams, ...rest};
}

const reply = (status, body) => ({
  status,
  text: () => Promise.resolve(body === undefined ? "" : (typeof body === "string" ? body : JSON.stringify(body))),
});

// A fetch that records its calls and answers from a list (the last answer repeats).
function recorder(...answers) {
  const calls = [];
  const fn = function (url, init) {
    calls.push({url, init, self: this});
    const answer = answers.length > 1 ? answers.shift() : answers[0];
    if (answer instanceof Error) return Promise.reject(answer);
    return Promise.resolve(answer === undefined ? reply(200, {}) : answer);
  };
  fn.calls = calls;
  return fn;
}

async function rejection(promise) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  return assert.fail("expected the promise to reject");
}

const shape = e => ({name: e.name, status: e.status, code: e.code, message: e.message, details: plain(e.details)});

// ------------------------------------------------------------------------------------------------------------------
// Loading: one global, nothing else, and the public surface
// ------------------------------------------------------------------------------------------------------------------
test("the script adds exactly one global, SutraCtx", () => {
  const sandbox = browser();
  vm.createContext(sandbox);
  const before = new Set(Object.getOwnPropertyNames(sandbox));
  vm.runInContext(CODE, sandbox);
  const added = Object.getOwnPropertyNames(sandbox).filter(name => !before.has(name));
  assert.deepEqual(added, ["SutraCtx"]);
});

test("J2's page script can declare its own top-level names after it (no lexical leak)", () => {
  const sandbox = load(browser());
  // every name J2's page uses at its top level, and every name this script uses inside itself
  const names = ["esc", "paint", "$", "md", "dv", "who", "col", "WHO", "isWf", "seen", "state", "versions", "allChat", "viewRun",
    "RUNLIST", "runQ", "EXAMPLES", "OUTS", "examples", "run", "tab", "api", "boot", "dept", "ctx", "root", "TOKEN_HEADER", "ID_RULE",
    "PATH_DEPT", "ROOT_RELATIVE", "isId", "isRootRelative", "J2_EXACT", "J2_PREFIXES", "J2_EXACT_SET", "J2_PATHS", "DEFAULT_MESSAGES",
    "ApiError", "readBoot", "deptFromPath", "pickDept", "tokenOf", "ESCAPES", "cssEscape", "paint", "safeDecode", "hasParam", "withDept",
    "methodOf", "needsToken", "withToken", "installFetch", "queryString", "buildUrl", "failure", "send", "fillFrames", "doc"];
  vm.runInContext([...new Set(names)].map(name => `const ${name} = 1;`).join("\n"), sandbox);
  vm.runInContext("class Later { constructor(){ this.d = SutraCtx.dept; } }; if (new Later().d !== 'web') throw new Error('SutraCtx lost');", sandbox);
});

test("the public surface is exactly the one the design lists", () => {
  const { SutraCtx } = load(browser());
  assert.deepEqual(Object.keys(SutraCtx).sort(),
    ["ApiError", "J2_PATHS", "api", "boot", "currentTab", "dept", "esc", "installFetch", "paint", "run", "tab", "withDept"]);
  assert.deepEqual(Object.keys(SutraCtx.api).sort(), ["del", "get", "post", "put"]);
  for (const name of ["run", "esc", "paint", "tab", "installFetch", "withDept"]) assert.equal(typeof SutraCtx[name], "function", name);
  assert.equal(SutraCtx.currentTab, "");
});

test("in node the file is module.exports and sets no global", () => {
  const sandbox = browser({module: {exports: {}}});
  vm.createContext(sandbox);
  vm.runInContext(CODE, sandbox);
  assert.equal(typeof sandbox.module.exports.api.get, "function");
  assert.equal(sandbox.module.exports.dept, "web");
  assert.equal(sandbox.SutraCtx, undefined);
  const required = require(FILE);        // really through node's loader, on node's own globals (no document, no location)
  assert.equal(typeof required.api.get, "function");
  assert.deepEqual(plain(required.boot), {});
  assert.equal(required.dept, "");
  assert.notEqual(globalThis.fetch && globalThis.fetch.sutraWrapped, true, "a page without a boot block wraps nothing");
});

// ------------------------------------------------------------------------------------------------------------------
// boot and dept
// ------------------------------------------------------------------------------------------------------------------
test("boot is parsed from the JSON block, and dept comes from it", () => {
  const { SutraCtx } = load(browser());
  assert.deepEqual(plain(SutraCtx.boot), BOOT);
  assert.equal(SutraCtx.dept, "web");
});

test("a block written with \\u003c escapes parses back to the text", () => {
  const text = JSON.stringify({...BOOT, dept_label: "A <b>&</b> team"}).replace(/</g, "\\u003c");
  assert.ok(!text.includes("<"));
  const { SutraCtx } = load(browser({boot: text}));
  assert.equal(SutraCtx.boot.dept_label, "A <b>&</b> team");
});

test("the server's block wins over the path", () => {
  assert.equal(load(browser({pathname: "/d/other/"})).SutraCtx.dept, "web");
});

test("with no block the department comes from /d/<id> in the path (the generic id rule)", () => {
  const dept = pathname => load(browser({boot: false, pathname})).SutraCtx.dept;
  assert.equal(dept("/d/web/"), "web");
  assert.equal(dept("/d/web"), "web");
  assert.equal(dept("/d/org_3f9a1c2b7d10/"), "org_3f9a1c2b7d10");
  assert.equal(dept("/d/a.b:c-d/"), "a.b:c-d");
  assert.equal(dept("/d/" + "a".repeat(120) + "/"), "a".repeat(120));
  assert.equal(dept("/d/" + "a".repeat(121) + "/"), "", "121 characters is too long, and the id may not be cut short");
  for (const bad of ["/", "", "/d/", "/d//", "/D/web/", "/x/d/web/", "/d/web%20x/", "/d/we b/", "/d/.", "/d/./", "/d/..", "/d/../", "/dweb/", "/d/web:/x y"]) {
    if (bad === "/d/web:/x y") continue;       // "web:" is a valid id followed by a slash
    assert.equal(dept(bad), "", bad);
  }
  assert.equal(dept("/d/web:/x"), "web:");
});

test("a block with page home has no department, whatever the path says", () => {
  const { SutraCtx } = load(browser({boot: {page: "home", token: TOKEN, dept: "", dept_label: "", version: "0.1.0"}, pathname: "/d/web/"}));
  assert.equal(SutraCtx.dept, "");
  const { SutraCtx: stray } = load(browser({boot: {page: "home", dept: "web", token: TOKEN}, pathname: "/"}));
  assert.equal(stray.dept, "", "home belongs to no team even if the block names one");
});

test("a department in the block that fails the id rule is not used; the path is tried instead", () => {
  for (const dept of ["a b", "..", ".", "", "x".repeat(121), "a/b", 5, null, undefined, ["web"]]) {
    const boot = {page: "dept", token: TOKEN, dept, dept_label: "X", version: "1"};
    assert.equal(load(browser({boot, pathname: "/d/web/"})).SutraCtx.dept, "web", JSON.stringify(dept));
    assert.equal(load(browser({boot, pathname: "/"})).SutraCtx.dept, "", JSON.stringify(dept));
  }
});

test("without a page field a valid dept in the block is still used", () => {
  assert.equal(load(browser({boot: {dept: "web"}, pathname: "/"})).SutraCtx.dept, "web");
});

test("a stub document whose getElementById returns an empty element gives boot {}", () => {
  const empty = () => new Proxy({innerHTML: "", textContent: "", dataset: {}}, {get: (t, k) => (k in t ? t[k] : () => {})});
  const { SutraCtx } = load({document: {getElementById: () => empty()}, location: {search: "", href: "", hash: ""}, URLSearchParams});
  assert.deepEqual(plain(SutraCtx.boot), {});
  assert.equal(SutraCtx.dept, "", "the stub location has no pathname");
});

test("everything that is not a JSON object in the block gives boot {}", () => {
  for (const text of ["", "   \n", "not json", "{", "[]", "[1,2]", "null", "5", '"web"', "true"]) {
    const { SutraCtx } = load(browser({boot: text, pathname: "/"}));
    assert.deepEqual(plain(SutraCtx.boot), {}, JSON.stringify(text));
  }
  // an element whose textContent is not a string (a stub that answers every property with a function)
  const odd = load(browser({document: {getElementById: () => ({textContent: () => "{}"})}, pathname: "/"})).SutraCtx;
  assert.deepEqual(plain(odd.boot), {});
});

test("a missing document, a missing getElementById, a throwing one and a missing location all give boot {} and no department", () => {
  for (const globals of [
    {},
    {document: {}},
    {document: {getElementById: () => { throw new Error("no dom"); }}},
    {document: {getElementById: () => null}, location: undefined},
    {document: {getElementById: () => null}, location: {pathname: 5}},
  ]) {
    const { SutraCtx } = load({URLSearchParams, ...globals});
    assert.deepEqual(plain(SutraCtx.boot), {});
    assert.equal(SutraCtx.dept, "");
  }
});

// ------------------------------------------------------------------------------------------------------------------
// run(), esc(), paint()
// ------------------------------------------------------------------------------------------------------------------
test("run() is the ?run= of the page, read when it is called, or empty", () => {
  const sandbox = load(browser({search: "?x=1&run=j2-20261104-100004-7f3a"}));
  assert.equal(sandbox.SutraCtx.run(), "j2-20261104-100004-7f3a");
  sandbox.location.search = "?run=a%20b";
  assert.equal(sandbox.SutraCtx.run(), "a b");
  for (const search of ["", "?", "?run=", "?x=1", "?runs=2", "?xrun=3"]) {
    sandbox.location.search = search;
    assert.equal(sandbox.SutraCtx.run(), "", JSON.stringify(search));
  }
  sandbox.location = undefined;
  assert.equal(sandbox.SutraCtx.run(), "");
  sandbox.location = {search: 5};
  assert.equal(sandbox.SutraCtx.run(), "");
  const bare = load({document: documentWith(false)});
  assert.equal(bare.SutraCtx.run(), "", "no URLSearchParams");
});

test("esc escapes & < > \" and ' and turns null and undefined into nothing", () => {
  const { SutraCtx } = load(browser());
  assert.equal(SutraCtx.esc(`<a href="x" title='y'>&</a>`), "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
  for (const [raw, entity] of [["&", "&amp;"], ["<", "&lt;"], [">", "&gt;"], ['"', "&quot;"], ["'", "&#39;"]]) assert.equal(SutraCtx.esc(raw), entity);
  assert.equal(SutraCtx.esc("&amp;"), "&amp;amp;", "no double-escape guard: the text is text");
  assert.equal(SutraCtx.esc(""), "");
  assert.equal(SutraCtx.esc(null), "");
  assert.equal(SutraCtx.esc(undefined), "");
  assert.equal(SutraCtx.esc(0), "0");
  assert.equal(SutraCtx.esc(12.5), "12.5");
  assert.equal(SutraCtx.esc(false), "false");
  assert.equal(SutraCtx.esc(["<", 1]), "&lt;,1");
  assert.equal(SutraCtx.esc("plain text / ` ="), "plain text / ` =");
});

function pane(openKeys, presentKeys) {
  const log = [];
  const details = new Map(presentKeys.map(k => [k, {open: false, dataset: {key: k}}]));
  let html = "";
  const el = {
    sets: 0,
    get innerHTML() { return html; },
    set innerHTML(value) { log.push(["html", value]); html = value; this.sets += 1; },
    querySelectorAll(selector) { log.push(["all", selector]); return openKeys.map(k => ({dataset: {key: k}})); },
    querySelector(selector) { log.push(["one", selector]); return details.get(/data-key="(.*)"\]$/.exec(selector)[1].replace(/\\(.)/g, "$1")) || null; },
  };
  return {el, log, details};
}

test("paint writes the HTML once, skips an unchanged pane and says which it did", () => {
  const { SutraCtx } = load(browser());
  const { el } = pane([], []);
  assert.equal(SutraCtx.paint(el, "<p>one</p>"), true);
  assert.equal(el.innerHTML, "<p>one</p>");
  assert.equal(el.__html, "<p>one</p>", "J2's own cache key, so J2's paint and this one agree");
  assert.equal(SutraCtx.paint(el, "<p>one</p>"), false);
  assert.equal(el.sets, 1);
  assert.equal(SutraCtx.paint(el, "<p>two</p>"), true);
  assert.equal(el.sets, 2);
  assert.equal(el.innerHTML, "<p>two</p>");
  assert.equal(SutraCtx.paint(el, ""), true, "an empty pane is a change like any other");
  assert.equal(SutraCtx.paint(el, ""), false);
});

test("paint reopens the <details data-key> that were open and only those", () => {
  const { SutraCtx } = load(browser());
  const { el, log, details } = pane(["shot-1", "log-2"], ["shot-1", "log-2", "other"]);
  assert.equal(SutraCtx.paint(el, "<details data-key=shot-1></details>"), true);
  assert.deepEqual(log.slice(0, 2), [["all", "details[open][data-key]"], ["html", "<details data-key=shot-1></details>"]],
    "the open ones are read BEFORE the HTML is replaced");
  assert.deepEqual(log.slice(2).map(([kind]) => kind), ["one", "one"], "and looked up again only after it");
  assert.equal(details.get("shot-1").open, true);
  assert.equal(details.get("log-2").open, true);
  assert.equal(details.get("other").open, false);
});

test("paint skips a key that is no longer in the new HTML", () => {
  const { SutraCtx } = load(browser());
  const { el, details } = pane(["gone", "kept"], ["kept"]);
  assert.doesNotThrow(() => SutraCtx.paint(el, "x"));
  assert.equal(details.get("kept").open, true);
});

test("paint escapes the key for the selector with CSS.escape, or by hand without it", () => {
  const key = 'a"b\\c';
  const withCss = load(browser({CSS: {escape: s => "<" + s + ">"}}));
  const first = pane([key], []);
  withCss.SutraCtx.paint(first.el, "x");
  assert.deepEqual(first.log[2], ["one", 'details[data-key="<' + key + '>"]']);
  const without = load(browser());
  const second = pane([key], []);
  without.SutraCtx.paint(second.el, "x");
  assert.deepEqual(second.log[2], ["one", 'details[data-key="a\\"b\\\\c"]']);
  const odd = load(browser({CSS: {}}));         // a CSS object without escape
  const third = pane([key], []);
  odd.SutraCtx.paint(third.el, "x");
  assert.deepEqual(third.log[2], second.log[2]);
});

test("paint with no element does nothing", () => {
  const { SutraCtx } = load(browser());
  assert.equal(SutraCtx.paint(null, "x"), false);
  assert.equal(SutraCtx.paint(undefined, "x"), false);
});

// ------------------------------------------------------------------------------------------------------------------
// tab(): currentTab first, then the event when the DOM can
// ------------------------------------------------------------------------------------------------------------------
class FakeCustomEvent {
  constructor(type, init) { this.type = type; this.detail = init && init.detail; this.bubbles = init && init.bubbles; }
}

test("tab(name) sets currentTab and then dispatches sutra:tab with the name", () => {
  const seen = [];
  let sandbox;
  const document = documentWith(BOOT, {dispatchEvent: event => { seen.push({type: event.type, detail: plain(event.detail), bubbles: event.bubbles, current: sandbox.SutraCtx.currentTab}); return true; }});
  sandbox = load(browser({document, CustomEvent: FakeCustomEvent}));
  assert.equal(sandbox.SutraCtx.currentTab, "", "the default is empty");
  assert.equal(sandbox.SutraCtx.tab("graph"), true);
  assert.equal(sandbox.SutraCtx.currentTab, "graph");
  sandbox.SutraCtx.tab("orgchart");
  assert.deepEqual(seen, [
    {type: "sutra:tab", detail: {name: "graph"}, bubbles: true, current: "graph"},
    {type: "sutra:tab", detail: {name: "orgchart"}, bubbles: true, current: "orgchart"},
  ], "a listener already sees the new currentTab");
});

test("tab(name) sets currentTab even without document.dispatchEvent or CustomEvent", () => {
  const cases = [
    ["no dispatchEvent", browser({CustomEvent: FakeCustomEvent})],
    ["no CustomEvent", browser({document: documentWith(BOOT, {dispatchEvent: () => assert.fail("nothing to dispatch without CustomEvent")})})],
    ["neither", browser()],
    ["no document", {location: {pathname: "/", search: ""}, URLSearchParams}],
    ["CustomEvent is not a function", browser({CustomEvent: {}, document: documentWith(BOOT, {dispatchEvent: () => assert.fail("no")})})],
  ];
  for (const [label, globals] of cases) {
    const { SutraCtx } = load(globals);
    assert.doesNotThrow(() => SutraCtx.tab("graph"), label);
    assert.equal(SutraCtx.currentTab, "graph", label);
    assert.equal(SutraCtx.tab("map"), false, label);
    assert.equal(SutraCtx.currentTab, "map", label);
  }
});

test("a dispatchEvent that throws never breaks tab()", () => {
  const document = documentWith(BOOT, {dispatchEvent: () => { throw new Error("listener blew up"); }});
  const { SutraCtx } = load(browser({document, CustomEvent: FakeCustomEvent}));
  assert.equal(SutraCtx.tab("graph"), false);
  assert.equal(SutraCtx.currentTab, "graph");
});

test("tab() turns a name that is not a string into a string", () => {
  const { SutraCtx } = load(browser());
  SutraCtx.tab(undefined);
  assert.equal(SutraCtx.currentTab, "");
  SutraCtx.tab(null);
  assert.equal(SutraCtx.currentTab, "");
  SutraCtx.tab(5);
  assert.equal(SutraCtx.currentTab, "5");
  SutraCtx.tab("preview");
  assert.equal(SutraCtx.currentTab, "preview");
});

// ------------------------------------------------------------------------------------------------------------------
// J2_PATHS
// ------------------------------------------------------------------------------------------------------------------
const J2_EXACT = ["/api/state", "/api/runs", "/api/call", "/api/preview", "/api/docs", "/api/map", "/api/plan", "/api/library",
  "/api/run-templates", "/api/artifacts", "/api/artifacts/tree", "/api/artifact", "/api/agent", "/api/code", "/api/story", "/api/board",
  "/api/audits", "/api/refs", "/api/say", "/api/output", "/api/reset", "/api/playbooks/clear", "/api/lessons/clear"];
const J2_PREFIXES = ["/api/library/", "/site/", "/file/", "/shot/"];
const ORCHESTRATOR = ["/api/chart", "/api/chart/changes", "/api/chart/changes/chg-0002/decision", "/api/graph", "/api/graph/nodes/web.identity",
  "/api/chats", "/api/chats/cs_org", "/api/chats/cs_org/messages", "/api/chats/cs_org/retry", "/api/departments", "/api/departments/web",
  "/api/departments/web/runs", "/api/needs-you", "/api/atoms", "/api/atoms/log", "/api/atoms/a-77aa10c2e9-03", "/api/events", "/api/health",
  "/api/config", "/api/engine/settings", "/api/connectors/claude/test", "/api/connectors/codex/test", "/api/connectors/codex/sign-in",
  "/api/connectors/codex/sign-in/abc", "/api/schemas/atom/1", "/api/schemas/validate", "/api/tasks", "/api/tasks/tsk_a1b2c3d4e5f6",
  "/api/tasks/tsk_a1b2c3d4e5f6/stop", "/api/usage", "/api/usage/summary", "/api/runs/j2-20261104-100004-7f3a", "/openapi.json"];

test("J2_PATHS lists the 23 exact pathnames and the four prefixes of j2_server.py", () => {
  const { J2_PATHS } = load(browser()).SutraCtx;
  assert.equal(J2_EXACT.length, 23);
  assert.deepEqual(plain(J2_PATHS.exact).sort(), [...J2_EXACT].sort());
  assert.deepEqual(plain(J2_PATHS.prefixes), J2_PREFIXES);
  assert.ok(Object.isFrozen(J2_PATHS) && Object.isFrozen(J2_PATHS.exact) && Object.isFrozen(J2_PATHS.prefixes));
});

const PATCHED = ["/api/runlist", "/api/changes"];

test("J2_PATHS.patched lists the two read-only routes of patch P13 and they get dept like J2's own", () => {
  const { J2_PATHS } = load(browser()).SutraCtx;
  assert.deepEqual(plain(J2_PATHS.patched), PATCHED);
  assert.ok(Object.isFrozen(J2_PATHS.patched) && PATCHED.every(p => !J2_PATHS.exact.includes(p)));
  for (const p of PATCHED) {
    assert.equal(J2_PATHS.matches(p), true, p);
    for (const other of [p + "/", p + "x", p.slice(0, -1), p.toUpperCase()]) assert.equal(J2_PATHS.matches(other), false, other);
  }
});

test("J2_PATHS matches whole pathnames exactly for J2's /api/ paths", () => {
  const { J2_PATHS } = load(browser()).SutraCtx;
  for (const p of J2_EXACT) {
    assert.equal(J2_PATHS.matches(p), true, p);
    for (const longer of [p + "/", p + "/x", p + "x", p + "2", p + "?a=1"]) {
      if (J2_PATHS.exact.includes(longer) || J2_PREFIXES.some(prefix => longer.startsWith(prefix))) continue;
      assert.equal(J2_PATHS.matches(longer), false, longer);
    }
    if (!J2_EXACT.includes(p.slice(0, -1))) assert.equal(J2_PATHS.matches(p.slice(0, -1)), false, p.slice(0, -1));
    assert.equal(J2_PATHS.matches(p.toUpperCase()), false, p.toUpperCase());
  }
});

test("J2_PATHS matches by prefix only /api/library/, /site/, /file/ and /shot/", () => {
  const { J2_PATHS } = load(browser()).SutraCtx;
  for (const p of ["/api/library/", "/api/library/x/y/z/v1", "/api/library/website/hero/plain/v3", "/site/", "/site/latest", "/site/v2",
    "/file/prd.md", "/file/prd.docx", "/shot/1", "/shot/site-v1.png"]) assert.equal(J2_PATHS.matches(p), true, p);
  for (const p of ["/api/libraryx", "/api/libraries/", "/sites/x", "/site", "/file", "/files/x", "/shot", "/shots/1", "/x/site/latest",
    "/api/site/latest", "/api/file/x", "/ui/site/x"]) assert.equal(J2_PATHS.matches(p), false, p);
});

test("J2_PATHS matches none of the orchestrator's, the library's or the connectors' routes", () => {
  const { J2_PATHS } = load(browser()).SutraCtx;
  for (const p of ORCHESTRATOR) assert.equal(J2_PATHS.matches(p), false, p);
  for (const p of ["/", "", "/api", "/api/", "/d/web/", "/ui/js/sutra_ctx.js", "/ui/vendor/d3.min.js", "/favicon.ico", "/vendor/d3.min.js"]) {
    assert.equal(J2_PATHS.matches(p), false, JSON.stringify(p));
  }
  for (const v of [undefined, null, 5, {}, ["/api/state"]]) assert.equal(J2_PATHS.matches(v), false);
});

// Optional drift check against the real J2 server: SUTRA_J2_CHECKOUT=/path/to/J2_Prototype node --test tests/ui/js/ctx.test.js
test("J2_PATHS agrees with the routes of the J2 checkout when SUTRA_J2_CHECKOUT is set", t => {
  const checkout = process.env.SUTRA_J2_CHECKOUT;
  const server = checkout && path.join(checkout, "j2_server.py");
  if (!server || !fs.existsSync(server)) return t.skip("set SUTRA_J2_CHECKOUT to a J2 checkout to compare the route list");
  const text = fs.readFileSync(server, "utf8");
  const exact = new Set([...text.matchAll(/(?:u\.path|self\.path) == "(\/api\/[^"]+)"/g)].map(m => m[1]));
  const prefixes = new Set([...text.matchAll(/u\.path\.startswith\("([^"]+)"\)/g)].map(m => m[1]));
  const { J2_PATHS } = load(browser()).SutraCtx;
  assert.deepEqual([...exact].sort(), plain(J2_PATHS.exact).sort());
  assert.deepEqual([...prefixes].sort(), plain(J2_PATHS.prefixes).sort());
});

// ------------------------------------------------------------------------------------------------------------------
// withDept
// ------------------------------------------------------------------------------------------------------------------
test("withDept appends dept to a J2 path once, keeping the query as it is", () => {
  const { withDept } = load(browser()).SutraCtx;
  assert.equal(withDept("/api/state"), "/api/state?dept=web");
  assert.equal(withDept("/api/state?x"), "/api/state?x&dept=web");
  assert.equal(withDept("/api/state?since=3&run=j2-1"), "/api/state?since=3&run=j2-1&dept=web");
  assert.equal(withDept("/api/state?"), "/api/state?dept=web");
  assert.equal(withDept("/api/state?x&"), "/api/state?x&dept=web");
  assert.equal(withDept("/api/artifact?name=a%20b%2Fc&run=r"), "/api/artifact?name=a%20b%2Fc&run=r&dept=web", "no re-encoding");
  assert.equal(withDept("/api/state?x#top"), "/api/state?x&dept=web#top");
  assert.equal(withDept("/api/state#a?b"), "/api/state?dept=web#a?b", "a ? after # belongs to the fragment");
  assert.equal(withDept(withDept("/api/state?x")), "/api/state?x&dept=web", "once");
});

test("withDept leaves a URL that already carries dept alone", () => {
  const { withDept } = load(browser()).SutraCtx;
  for (const url of ["/api/state?dept=web", "/api/state?dept=other", "/api/state?x=1&dept=other", "/api/state?dept=&x=1", "/api/state?dept",
    "/api/state?x=1&dept", "/api/state?%64ept=web", "/api/state?run=r&dept=web#frag"]) {
    assert.equal(withDept(url), url, url);
  }
  for (const [url, expected] of [["/api/state?xdept=1", "/api/state?xdept=1&dept=web"], ["/api/state?dept2=1", "/api/state?dept2=1&dept=web"],
    ["/api/state?x=dept%3Dq", "/api/state?x=dept%3Dq&dept=web"], ["/api/state?y=dept", "/api/state?y=dept&dept=web"],
    ["/api/state?DEPT=1", "/api/state?DEPT=1&dept=web"], ["/api/state?%E0%A4%A=1", "/api/state?%E0%A4%A=1&dept=web"]]) {
    assert.equal(withDept(url), expected, url);
  }
});

test("withDept covers the prefixes and leaves other paths alone", () => {
  const { withDept } = load(browser()).SutraCtx;
  assert.equal(withDept("/api/library/website/hero/plain/v1"), "/api/library/website/hero/plain/v1?dept=web");
  assert.equal(withDept("/site/latest?t=1&run=r"), "/site/latest?t=1&run=r&dept=web");
  assert.equal(withDept("/file/prd.md"), "/file/prd.md?dept=web");
  assert.equal(withDept("/shot/2"), "/shot/2?dept=web");
  for (const url of ["/api/runs/j2-20261104-100004-7f3a", "/api/schemas/atom/1", "/api/tasks", "/api/chart?x=1", "/api/graph?level=chart",
    "/ui/js/sutra_ctx.js", "/ui/vendor/d3.min.js", "/d/web/", "/", "/api/connectors/codex/test"]) {
    assert.equal(withDept(url), url, url);
  }
  assert.equal(withDept("/api/runs"), "/api/runs?dept=web", "the J2 list of saved runs");
  assert.equal(withDept("/api/library/x/y/z/v1"), "/api/library/x/y/z/v1?dept=web");
});

test("withDept leaves absolute, protocol-relative, relative and odd URLs alone", () => {
  const { withDept } = load(browser()).SutraCtx;
  for (const url of ["http://example.com/api/state", "https://example.com/api/state?x=1", "HTTP://example.com/api/state", "//example.com/api/state",
    "/\\example.com/api/state", "/\t/example.com/api/state", "/api/state\n/x", "api/state", "./api/state", "../api/state", "vendor/d3.min.js", "", "?x=1",
    "javascript:alert(1)", "data:text/plain,x", "blob:x"]) {
    assert.equal(withDept(url), url, JSON.stringify(url));
  }
  for (const value of [undefined, null, 5, {}, ["/api/state"]]) assert.equal(withDept(value), value);
});

test("withDept encodes the department", () => {
  const sandbox = load(browser());
  sandbox.SutraCtx.dept = "a.b:c-d";
  assert.equal(sandbox.SutraCtx.withDept("/api/state"), "/api/state?dept=a.b%3Ac-d");
});

test("withDept adds nothing when the department is empty (J2's own page, Home, the harness)", () => {
  for (const globals of [browser({boot: {page: "home", token: TOKEN}, pathname: "/"}), browser({boot: false, pathname: "/"}), {}]) {
    const { withDept } = load({URLSearchParams, ...globals}).SutraCtx;
    for (const url of ["/api/state", "/api/state?x", "/site/latest", "/api/runs"]) assert.equal(withDept(url), url);
  }
});

test("URLs built with runQ survive: the E4 runQ carries dept and the wrapper adds nothing twice", () => {
  const sandbox = load(browser());
  const probe = `
    let viewRun = "";
    const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "") + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");
    const urls = [];
    for (viewRun of ["", "j2-20261104-100004-7f3a", "r 1"]) {
      urls.push(\`/api/state?since=3\${runQ()}\`, \`/api/board?\${runQ().slice(1)}\`, \`/api/library/website/hero/x/v1\${runQ().replace("&", "?")}\`,
        \`/file/prd.md\${runQ().replace("&", "?")}\`, \`/api/call?id=5\${viewRun ? "&run=" + encodeURIComponent(viewRun) : ""}\`);
    }
    urls.map(u => [u, SutraCtx.withDept(u)]);`;
  const pairs = plain(vm.runInContext(probe, sandbox));
  assert.equal(pairs.length, 15);
  for (const [built, wrapped] of pairs) {
    if (built.startsWith("/api/call")) assert.equal(wrapped, built + (built.includes("?") ? "&" : "?") + "dept=web", "J2's /api/call line has no runQ: the wrapper adds dept");
    else assert.equal(wrapped, built, built);
    assert.equal(wrapped.split("dept=").length, 2, "exactly one dept in " + wrapped);
  }
  assert.ok(pairs.some(([built]) => built === "/api/board?dept=web"), "an empty viewRun leaves only dept after slice(1)");
  assert.ok(pairs.some(([built]) => built === "/file/prd.md?run=r%201&dept=web"));
  // J2's own page: dept is empty and runQ is J2's own string
  const own = load(browser({boot: false, pathname: "/"}));
  assert.equal(vm.runInContext(`let viewRun = "r"; const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "") + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : ""); runQ()`, own), "&run=r");
  assert.equal(vm.runInContext(`let viewRun = ""; const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "") + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : ""); runQ()`, load(browser({boot: false, pathname: "/"}))), "");
});

// ------------------------------------------------------------------------------------------------------------------
// installFetch: the wrapper for J2's own fetch calls
// ------------------------------------------------------------------------------------------------------------------
function wrapped(globals = {}) {
  const sandbox = load(browser({...globals}));
  const original = recorder(reply(200, {}));
  const win = {fetch: original};
  assert.equal(sandbox.SutraCtx.installFetch(win), true);
  return {sandbox, win, original, calls: original.calls};
}

test("the wrapper turns /api/state?x into /api/state?x&dept=web, once", async () => {
  const { win, calls } = wrapped();
  await win.fetch("/api/state?x");
  await win.fetch("/api/state?x&dept=web");
  await win.fetch("/api/runs");
  assert.deepEqual(calls.map(c => c.url), ["/api/state?x&dept=web", "/api/state?x&dept=web", "/api/runs?dept=web"]);
});

test("the wrapper leaves /ui/..., other paths, absolute URLs and Request objects alone", async () => {
  const { win, calls } = wrapped();
  const request = {url: "/api/state"};            // not a string: passed through as it is
  const init = {method: "POST", body: "x"};
  await win.fetch("/ui/js/sutra_ctx.js");
  await win.fetch("/api/chart");
  await win.fetch("http://example.com/api/state");
  await win.fetch("https://example.com/api/say", init);
  await win.fetch("//example.com/api/say", init);
  await win.fetch(request, init);
  assert.deepEqual(calls.map(c => c.url), ["/ui/js/sutra_ctx.js", "/api/chart", "http://example.com/api/state", "https://example.com/api/say",
    "//example.com/api/say", request]);
  for (const call of calls.slice(3)) assert.equal(call.init, init, "an init that is not for this origin is passed on untouched, so no token leaves");
  assert.equal(init.headers, undefined);
});

test("the wrapper adds the token on POST, PUT, DELETE and PATCH, and on no read", async () => {
  const { win, calls } = wrapped();
  for (const method of ["POST", "PUT", "DELETE", "PATCH", "post", "Delete"]) await win.fetch("/api/say", {method});
  for (const method of ["GET", "HEAD", "OPTIONS", "get", "head", undefined, ""]) await win.fetch("/api/state", method === undefined ? {} : {method});
  await win.fetch("/api/state");
  const withToken = calls.map(c => (c.init && c.init.headers && c.init.headers["X-Sutra-Token"]) || null);
  assert.deepEqual(withToken, [TOKEN, TOKEN, TOKEN, TOKEN, TOKEN, TOKEN, null, null, null, null, null, null, null, null]);
});

test("the wrapper keeps the caller's headers and body, does not change the caller's init, and adds dept to a POST too", async () => {
  const { win, calls } = wrapped();
  const init = {method: "POST", headers: {"Content-Type": "application/json"}, body: '{"text":"hi"}', cache: "no-store"};
  await win.fetch("/api/say", init);
  assert.equal(calls[0].url, "/api/say?dept=web");
  assert.deepEqual(plain(calls[0].init), {method: "POST", headers: {"Content-Type": "application/json", "X-Sutra-Token": TOKEN}, body: '{"text":"hi"}', cache: "no-store"});
  assert.deepEqual(plain(init), {method: "POST", headers: {"Content-Type": "application/json"}, body: '{"text":"hi"}', cache: "no-store"});
  await win.fetch("/api/reset", {method: "POST"});
  assert.deepEqual(plain(calls[1].init), {method: "POST", headers: {"X-Sutra-Token": TOKEN}});
  assert.equal(calls[1].url, "/api/reset?dept=web");
});

test("the wrapper adds the token to a root-relative POST whatever its path", async () => {
  const { win, calls } = wrapped();
  await win.fetch("/api/chats/cs_org/messages", {method: "POST", body: "{}"});
  await win.fetch("/somewhere/else", {method: "PUT"});
  assert.deepEqual(calls.map(c => c.url), ["/api/chats/cs_org/messages", "/somewhere/else"]);
  assert.deepEqual(calls.map(c => c.init.headers["X-Sutra-Token"]), [TOKEN, TOKEN]);
});

test("a token the caller set (in any case) is kept and not duplicated", async () => {
  const { win, calls } = wrapped();
  await win.fetch("/api/say", {method: "POST", headers: {"x-sutra-token": "mine", Accept: "x"}});
  assert.deepEqual(plain(calls[0].init.headers), {"x-sutra-token": "mine", Accept: "x"});
  await win.fetch("/api/say", {method: "POST", headers: [["Content-Type", "a"], ["X-SUTRA-TOKEN", "mine"]]});
  assert.deepEqual(plain(calls[1].init.headers), [["Content-Type", "a"], ["X-SUTRA-TOKEN", "mine"]]);
});

class FakeHeaders {
  constructor(init) {
    this.map = new Map();
    const pairs = init instanceof FakeHeaders ? [...init.map] : (Array.isArray(init) ? init : Object.entries(init || {}));
    for (const [k, v] of pairs) this.map.set(String(k).toLowerCase(), v);
  }
  has(k) { return this.map.has(k.toLowerCase()); }
  set(k, v) { this.map.set(k.toLowerCase(), v); }
  get(k) { return this.map.get(k.toLowerCase()); }
}

test("headers given as a Headers object or a list of pairs get the token without being changed", async () => {
  const { win, calls } = wrapped({Headers: FakeHeaders});
  const headers = new FakeHeaders({"Content-Type": "text/plain"});
  await win.fetch("/api/say", {method: "POST", headers});
  assert.ok(calls[0].init.headers instanceof FakeHeaders);
  assert.notEqual(calls[0].init.headers, headers, "a copy");
  assert.equal(calls[0].init.headers.get("x-sutra-token"), TOKEN);
  assert.equal(calls[0].init.headers.get("content-type"), "text/plain");
  assert.equal(headers.has("x-sutra-token"), false);
  const own = new FakeHeaders({"X-Sutra-Token": "mine"});
  await win.fetch("/api/say", {method: "POST", headers: own});
  assert.equal(calls[1].init.headers.get("x-sutra-token"), "mine");
  const pairs = [["Content-Type", "a"]];
  await win.fetch("/api/say", {method: "POST", headers: pairs});
  assert.deepEqual(plain(calls[2].init.headers), [["Content-Type", "a"], ["X-Sutra-Token", TOKEN]]);
  assert.deepEqual(pairs, [["Content-Type", "a"]], "the caller's list is not changed");
  await win.fetch("/api/say", {method: "POST", headers: "not headers"});
  assert.deepEqual(plain(calls[3].init.headers), {"X-Sutra-Token": TOKEN});
});

test("without a token in the block the wrapper adds none and passes init on as it is", async () => {
  const { win, calls } = wrapped({boot: {page: "dept", dept: "web", dept_label: "Web", version: "1"}});
  const init = {method: "POST"};
  await win.fetch("/api/say", init);
  assert.equal(calls[0].init, init);
  assert.equal(calls[0].url, "/api/say?dept=web");
  const nonString = wrapped({boot: {page: "dept", dept: "web", token: 12345}});
  const second = {method: "POST"};
  await nonString.win.fetch("/api/say", second);
  assert.equal(nonString.calls[0].init, second, "a token that is not a string is no token");
});

test("with no department the wrapper still adds the token to a root-relative write, and no dept", async () => {
  const { win, calls } = wrapped({boot: {page: "home", token: TOKEN}, pathname: "/"});
  await win.fetch("/api/state");
  await win.fetch("/api/say", {method: "POST"});
  assert.deepEqual(calls.map(c => c.url), ["/api/state", "/api/say"]);
  assert.equal(calls[1].init.headers["X-Sutra-Token"], TOKEN);
});

test("the wrapper calls the original with the window as this and returns what it returns", async () => {
  const sandbox = load(browser());
  const answer = Promise.resolve(reply(200, {ok: true}));
  const original = function () { this.recorded = [...arguments]; return answer; };
  const win = {fetch: original};
  sandbox.SutraCtx.installFetch(win);
  const got = win.fetch("/api/state");
  assert.equal(got, answer);
  assert.equal(win.recorded[0], "/api/state?dept=web");
});

test("wrapping another window's fetch does not change the fetch api uses", async () => {
  const page = recorder(reply(200, {from: "page"}));
  const sandbox = load(browser({fetch: page}));
  const other = recorder(reply(200, {from: "other"}));
  assert.equal(sandbox.SutraCtx.installFetch({fetch: other}), true);
  assert.deepEqual(plain(await sandbox.SutraCtx.api.get("/api/x")), {from: "page"});
  assert.equal(other.calls.length, 0);
});

test("installFetch wraps once, reports what it did and tolerates a window with no fetch", () => {
  const { SutraCtx } = load(browser());
  const original = recorder(reply(200, {}));
  const win = {fetch: original};
  assert.equal(SutraCtx.installFetch(win), true);
  const first = win.fetch;
  assert.notEqual(first, original);
  assert.equal(first.sutraWrapped, true);
  assert.equal(SutraCtx.installFetch(win), false);
  assert.equal(win.fetch, first, "not wrapped twice");
  win.fetch("/api/state");
  assert.equal(original.calls.length, 1);
  assert.equal(original.calls[0].url, "/api/state?dept=web", "one dept, not two");
  for (const bad of [{}, {fetch: 5}, null, undefined, 0]) assert.equal(SutraCtx.installFetch(bad), false);
});

test("a team page wraps its own fetch at load; Home, a page without a block and a page with no fetch do not", async () => {
  const original = recorder(reply(200, {}));
  const team = load(browser({fetch: original}));
  assert.equal(team.fetch.sutraWrapped, true);
  await team.fetch("/api/state?x");
  assert.equal(original.calls[0].url, "/api/state?x&dept=web");
  const home = recorder(reply(200, {}));
  assert.equal(load(browser({boot: {page: "home", token: TOKEN}, pathname: "/", fetch: home})).fetch, home);
  const bare = recorder(reply(200, {}));
  assert.equal(load(browser({boot: false, fetch: bare})).fetch, bare, "a path alone does not install the wrapper");
  assert.doesNotThrow(() => load(browser({})), "no fetch at all");
});

// ------------------------------------------------------------------------------------------------------------------
// api: the orchestrator's routes
// ------------------------------------------------------------------------------------------------------------------
function app(answers, globals = {}) {
  const fetch = recorder(...(Array.isArray(answers) ? answers : [answers]));
  const sandbox = load(browser({fetch, ...globals}));
  return {api: sandbox.SutraCtx.api, calls: fetch.calls, original: fetch, sandbox};
}

test("api.get builds the query, sends no token and returns the JSON", async () => {
  const { api, calls } = app(reply(200, {version: 4, nodes: []}));
  const got = await api.get("/api/graph", {level: "chart", dept: "web"});
  assert.deepEqual(plain(got), {version: 4, nodes: []});
  assert.equal(calls[0].url, "/api/graph?level=chart&dept=web");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.cache, "no-store");
  assert.deepEqual(plain(calls[0].init.headers), {Accept: "application/json"}, "no token on a read");
  assert.equal(calls[0].init.body, undefined);
});

test("api.get query: encoded, null and undefined left out, 0 false and empty kept, a string taken as it is", async () => {
  const { api, calls } = app(reply(200, []));
  await api.get("/api/chart/changes", {limit: 50, after: 0, q: "a b&c=d", none: undefined, nil: null, off: false, empty: ""});
  assert.equal(calls[0].url, "/api/chart/changes?limit=50&after=0&q=a%20b%26c%3Dd&off=false&empty=");
  await api.get("/api/x", {"a b": 1, "c&d": 2});
  assert.equal(calls[calls.length - 1].url, "/api/x?a%20b=1&c%26d=2");
  calls.pop();
  await api.get("/api/x", {});
  await api.get("/api/x", undefined);
  await api.get("/api/x", null);
  await api.get("/api/x", {a: undefined});
  await api.get("/api/x", "");
  assert.deepEqual(calls.slice(1, 6).map(c => c.url), ["/api/x", "/api/x", "/api/x", "/api/x", "/api/x"]);
  await api.get("/api/x", "?a=1&b=2");
  await api.get("/api/x", "a=1");
  await api.get("/api/x?z=0", {a: 1});
  await api.get("/api/x?", {a: 1});
  await api.get("/api/x?z=0&", {a: 1});
  assert.deepEqual(calls.slice(6).map(c => c.url), ["/api/x?a=1&b=2", "/api/x?a=1", "/api/x?z=0&a=1", "/api/x?a=1", "/api/x?z=0&a=1"]);
});

test("api.post sends the JSON body, the token and the content type", async () => {
  const { api, calls } = app(reply(202, {message_id: 7, turn: "started"}));
  const got = await api.post("/api/chats/cs_org/messages", {text: "A website for my cafe"});
  assert.deepEqual(plain(got), {message_id: 7, turn: "started"});
  assert.equal(calls[0].url, "/api/chats/cs_org/messages");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.body, '{"text":"A website for my cafe"}');
  assert.deepEqual(plain(calls[0].init.headers), {Accept: "application/json", "X-Sutra-Token": TOKEN, "Content-Type": "application/json"});
  assert.equal(calls[0].init.cache, "no-store");
});

test("api.post without a body sends none and no content type; a falsy body is still a body", async () => {
  const { api, calls } = app(reply(202, {}));
  await api.post("/api/chats/cs_org/retry");
  assert.equal("body" in calls[0].init, false);
  assert.deepEqual(plain(calls[0].init.headers), {Accept: "application/json", "X-Sutra-Token": TOKEN});
  await api.post("/api/x", 0);
  await api.post("/api/x", false);
  await api.post("/api/x", null);
  assert.deepEqual(calls.slice(1).map(c => c.init.body), ["0", "false", "null"]);
});

test("api.put sends PUT with the body and the token", async () => {
  const { api, calls } = app(reply(200, {schema: "engine-settings/1"}));
  const got = await api.put("/api/engine/settings", {set: {j2_fixes: true}, unset: ["j2_slim"]});
  assert.deepEqual(plain(got), {schema: "engine-settings/1"});
  assert.equal(calls[0].init.method, "PUT");
  assert.equal(calls[0].init.body, '{"set":{"j2_fixes":true},"unset":["j2_slim"]}');
  assert.equal(calls[0].init.headers["X-Sutra-Token"], TOKEN);
  assert.equal(calls[0].url, "/api/engine/settings");
});

test("api.del sends DELETE with the token and no body, and a 204 answers null", async () => {
  const { api, calls } = app(reply(204));
  assert.equal(await api.del("/api/connectors/codex/sign-in/abc"), null);
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].init.headers["X-Sutra-Token"], TOKEN);
  assert.equal("body" in calls[0].init, false);
  assert.equal("Content-Type" in calls[0].init.headers, false);
});

test("api sends no token header when the page has none", async () => {
  const { api, calls } = app(reply(200, {}), {boot: {page: "home", version: "1"}, pathname: "/"});
  await api.post("/api/x", {});
  assert.deepEqual(plain(calls[0].init.headers), {Accept: "application/json", "Content-Type": "application/json"});
});

test("api calls never get dept and never go through the wrapper, even for a path J2 also has", async () => {
  const { api, calls, sandbox } = app(reply(200, {}));
  assert.equal(sandbox.fetch.sutraWrapped, true, "the team page wrapped window.fetch at load");
  await api.get("/api/runs");
  await api.get("/api/state", {x: 1});
  await api.post("/api/reset");
  await api.put("/api/say", {});
  await api.del("/api/library/x/y/z/v1");
  assert.deepEqual(calls.map(c => c.url), ["/api/runs", "/api/state?x=1", "/api/reset", "/api/say", "/api/library/x/y/z/v1"]);
  assert.ok(calls.every(c => c.self === undefined || c.self === null || c.self === sandbox), "the original, called plainly");
  // the wrapper is not what answered: a call through it would carry dept
  await sandbox.fetch("/api/runs");
  assert.equal(calls[calls.length - 1].url, "/api/runs?dept=web");
});

test("api calls the window's fetch as it is when nothing wrapped it, looked up when called", async () => {
  const first = recorder(reply(200, {from: "first"}));
  const sandbox = load(browser({boot: false, pathname: "/", fetch: first}));
  assert.deepEqual(plain(await sandbox.SutraCtx.api.get("/api/x")), {from: "first"});
  const second = recorder(reply(200, {from: "second"}));
  sandbox.fetch = second;
  assert.deepEqual(plain(await sandbox.SutraCtx.api.get("/api/x")), {from: "second"});
});

test("an empty or blank 2xx answer is null; JSON of any kind is returned as it is", async () => {
  for (const [body, expected] of [[undefined, null], ["", null], ["  \n", null], ["null", null], ["[1,2]", [1, 2]], ["0", 0], ['"x"', "x"], ["{}", {}]]) {
    const { api } = app(reply(200, body));
    assert.deepEqual(plain(await api.get("/api/x")), expected, JSON.stringify(body));
  }
  for (const status of [200, 201, 202, 204, 299]) {
    const { api } = app(reply(status, status === 204 ? undefined : { s: status }));
    assert.equal((await api.get("/api/x") || { s: 204 }).s, status);
  }
});

test("a 2xx answer that is not JSON rejects with bad_payload", async () => {
  for (const body of ["<html>proxy</html>", "{", "undefined", "ok"]) {
    const { api } = app(reply(200, body));
    const error = await rejection(api.get("/api/x"));
    assert.deepEqual(shape(error), {name: "ApiError", status: 200, code: "bad_payload", message: "The app sent an answer that could not be read.", details: {}}, body);
  }
});

test("an error answer in the envelope becomes an ApiError with its status, code, message and details", async () => {
  const body = {error: {code: "busy", message: "The team is working. You can write again when it asks you something or is done", details: {task_id: "tsk_1"}}};
  const { api } = app(reply(409, body));
  const error = await rejection(api.post("/api/chats/web/messages", {text: "x"}));
  assert.deepEqual(shape(error), {name: "ApiError", status: 409, code: "busy", message: body.error.message, details: {task_id: "tsk_1"}});
  for (const [status, code] of [[401, "bad_token"], [403, "read_only"], [404, "not_found"], [422, "validation"], [429, "too_many_pending"], [503, "provider_unavailable"], [500, "internal"]]) {
    const one = await rejection(app(reply(status, {error: {code, message: "m " + code, details: {violations: ["f"]}}})).api.get("/api/x"));
    assert.deepEqual(shape(one), {name: "ApiError", status, code, message: "m " + code, details: {violations: ["f"]}});
  }
});

test("an envelope without a message or details gets the code as its message and empty details", async () => {
  const error = await rejection(app(reply(409, {error: {code: "stale_chart"}})).api.get("/api/x"));
  assert.deepEqual(shape(error), {name: "ApiError", status: 409, code: "stale_chart", message: "stale_chart", details: {}});
  const odd = await rejection(app(reply(409, {error: {code: "x", message: 5, details: "d"}})).api.get("/api/x"));
  assert.deepEqual(shape(odd), {name: "ApiError", status: 409, code: "x", message: "x", details: {}});
});

test("an error body that is not the envelope becomes http_<status> with the best sentence it holds", async () => {
  const cases = [
    [404, {error: "no such run"}, "http_404", "no such run"],                       // J2's own body
    [404, {detail: "Not Found"}, "http_404", "Not Found"],                          // FastAPI
    [422, {detail: [{loc: ["query", "x"], msg: "bad"}]}, "http_422", "The app answered 422."],
    [502, "<html>Bad Gateway</html>", "http_502", "The app answered 502."],
    [500, "", "http_500", "The app answered 500."],
    [500, undefined, "http_500", "The app answered 500."],
    [500, "null", "http_500", "The app answered 500."],
    [500, '"oops"', "http_500", "The app answered 500."],
    [500, "[1]", "http_500", "The app answered 500."],
    [418, {error: {code: "", message: "empty code"}}, "http_418", "The app answered 418."],
    [418, {error: {message: "no code"}}, "http_418", "The app answered 418."],
    [418, {error: {code: 5}}, "http_418", "The app answered 418."],
    [418, {error: null}, "http_418", "The app answered 418."],
    [304, undefined, "http_304", "The app answered 304."],
    [199, undefined, "http_199", "The app answered 199."],
    [300, undefined, "http_300", "The app answered 300."],
  ];
  for (const [status, body, code, message] of cases) {
    const error = await rejection(app(reply(status, body)).api.get("/api/x"));
    assert.deepEqual(shape(error), {name: "ApiError", status, code, message, details: {}}, `${status} ${JSON.stringify(body)}`);
  }
});

test("a failed fetch, an unreadable body and a missing fetch reject with network and status 0", async () => {
  const down = await rejection(app(new TypeError("Failed to fetch")).api.get("/api/x"));
  assert.deepEqual(shape(down), {name: "ApiError", status: 0, code: "network", message: "The app is not responding.", details: {reason: "Failed to fetch"}});
  const text = await rejection(app({status: 200, text: () => Promise.reject(new Error("stream cut"))}).api.get("/api/x"));
  assert.deepEqual(shape(text), {name: "ApiError", status: 0, code: "network", message: "The app is not responding.", details: {reason: "stream cut"}});
  const none = await rejection(load(browser({boot: false, pathname: "/"})).SutraCtx.api.get("/api/x"));
  assert.equal(none.code, "network");
  assert.equal(none.status, 0);
  const odd = await rejection(app(Object.assign(new Error(), {message: ""})).api.get("/api/x"));
  assert.equal(odd.code, "network");
  assert.equal(typeof odd.details.reason, "string");
});

test("a path that does not stay on this origin rejects with bad_path before any request", async () => {
  const { api, calls } = app(reply(200, {}));
  for (const bad of ["http://example.com/api/x", "https://example.com/", "//example.com/api/x", "/\\example.com/api/x", "/\t/example.com/api/x",
    "/api/x\n", "api/x", "", "x", undefined, null, 5, {}]) {
    for (const call of [() => api.get(bad), () => api.post(bad, {}), () => api.put(bad, {}), () => api.del(bad)]) {
      const promise = call();
      assert.equal(typeof promise.then, "function", "a rejection, never a synchronous throw: " + String(bad));
      const error = await rejection(promise);
      assert.equal(error.code, "bad_path", String(bad));
      assert.equal(error.status, 0);
      assert.equal(error.message, "An API path starts with a single slash.");
      assert.deepEqual(plain(error.details), {path: typeof bad === "string" ? bad : typeof bad}, String(bad));
    }
  }
  assert.equal(calls.length, 0, "no request, so no token went anywhere");
});

// ------------------------------------------------------------------------------------------------------------------
// ApiError
// ------------------------------------------------------------------------------------------------------------------
test("ApiError carries status, code, message and details and is an Error", () => {
  const sandbox = load(browser());
  const { ApiError } = sandbox.SutraCtx;
  const error = new ApiError({status: 409, code: "busy", message: "The team is working.", details: {task_id: "t"}});
  assert.deepEqual(shape(error), {name: "ApiError", status: 409, code: "busy", message: "The team is working.", details: {task_id: "t"}});
  assert.ok(error instanceof ApiError);
  assert.ok(error instanceof vm.runInContext("Error", sandbox));
  assert.equal(String(error), "ApiError: The team is working.");
  assert.equal(typeof error.stack, "string");
});

test("ApiError takes a bare code as the short form, with a sentence for the codes the client makes", () => {
  const { ApiError } = load(browser()).SutraCtx;
  assert.deepEqual(shape(new ApiError("bad_payload")), {name: "ApiError", status: 0, code: "bad_payload", message: "The app sent an answer that could not be read.", details: {}});
  assert.equal(new ApiError("network").message, "The app is not responding.");
  assert.equal(new ApiError("bad_path").message, "An API path starts with a single slash.");
  assert.equal(new ApiError("busy").message, "busy");
  for (const code of ["constructor", "__proto__", "toString", "hasOwnProperty"]) assert.equal(new ApiError(code).message, code, code);
});

test("ApiError fills what is missing or has the wrong type", () => {
  const { ApiError } = load(browser()).SutraCtx;
  for (const init of [undefined, null, 5, {}, [], {code: 5, status: "404", message: 7, details: "x"}, {code: "", message: ""}]) {
    assert.deepEqual(shape(new ApiError(init)), {name: "ApiError", status: 0, code: "error", message: "error", details: {}}, JSON.stringify(init));
  }
  assert.equal(new ApiError({status: 404.5}).status, 0);
  assert.equal(new ApiError({status: 404}).status, 404);
  assert.equal(new ApiError({status: 0}).status, 0);
  assert.equal(new ApiError({code: "x", details: null}).details.constructor === undefined, false);
  assert.deepEqual(plain(new ApiError({code: "x", details: [1]}).details), [1]);
});

// ------------------------------------------------------------------------------------------------------------------
// The two preview iframes (E2): data-src becomes src, with dept, on DOMContentLoaded
// ------------------------------------------------------------------------------------------------------------------
function frame(attrs) {
  const map = new Map(Object.entries(attrs));
  return {map, getAttribute: name => (map.has(name) ? map.get(name) : null), setAttribute: (name, value) => map.set(name, value)};
}

function pageWithFrames(frames, { readyState = "loading", boot = BOOT } = {}) {
  const listeners = [];
  const document = documentWith(boot, {
    readyState,
    querySelectorAll: selector => (selector === "iframe[data-src]" ? frames : []),
    addEventListener: (type, fn) => listeners.push([type, fn]),
  });
  if (readyState === null) delete document.readyState;
  return {sandbox: load(browser({document, boot})), listeners};
}

test("the preview frames get src from data-src plus dept when the document has loaded", () => {
  const sframe = frame({"data-src": "/site/latest", sandbox: "allow-scripts"});
  const dframe = frame({"data-src": "/site/latest"});
  const { listeners } = pageWithFrames([sframe, dframe]);
  assert.deepEqual(listeners.map(([type]) => type), ["DOMContentLoaded"]);
  assert.equal(sframe.map.get("src"), undefined, "nothing before the document is parsed");
  listeners[0][1]();
  assert.equal(sframe.map.get("src"), "/site/latest?dept=web");
  assert.equal(dframe.map.get("src"), "/site/latest?dept=web");
  assert.equal(sframe.map.get("sandbox"), "allow-scripts");
});

test("a frame that already has a src is left alone (J2 assigned it first)", () => {
  const assigned = frame({"data-src": "/site/latest", src: "/site/v2?t=1&run=r&dept=web"});
  const empty = frame({"data-src": "/site/latest", src: ""});
  const { listeners } = pageWithFrames([assigned, empty]);
  listeners[0][1]();
  assert.equal(assigned.map.get("src"), "/site/v2?t=1&run=r&dept=web");
  assert.equal(empty.map.get("src"), "/site/latest?dept=web", "an empty src is no src");
});

test("a frame with an empty data-src is skipped, and one that is not a J2 path is copied as it is", () => {
  const blank = frame({"data-src": ""});
  const other = frame({"data-src": "/elsewhere/page.html"});
  const { listeners } = pageWithFrames([blank, other]);
  listeners[0][1]();
  assert.equal(blank.map.has("src"), false);
  assert.equal(other.map.get("src"), "/elsewhere/page.html");
});

test("when the document has loaded already the frames are filled at once; without a department the src is plain", () => {
  const ready = frame({"data-src": "/site/latest"});
  const { listeners } = pageWithFrames([ready], {readyState: "interactive"});
  assert.deepEqual(listeners, []);
  assert.equal(ready.map.get("src"), "/site/latest?dept=web");
  const home = frame({"data-src": "/site/latest"});
  pageWithFrames([home], {readyState: "complete", boot: {page: "home", token: TOKEN}});
  assert.equal(home.map.get("src"), "/site/latest");
  const stub = frame({"data-src": "/site/latest"});
  const { listeners: stubListeners } = pageWithFrames([stub], {readyState: null});
  assert.deepEqual(stubListeners, [], "a document with no readyState counts as loaded, like J2's stub");
  assert.equal(stub.map.get("src"), "/site/latest?dept=web");
});

test("frames are skipped quietly where the document cannot be queried", () => {
  for (const document of [undefined, {}, {querySelectorAll: () => { throw new Error("no"); }}, {querySelectorAll: () => [{getAttribute: () => { throw new Error("odd"); }}]}]) {
    assert.doesNotThrow(() => load({URLSearchParams, document, location: {pathname: "/", search: ""}}));
  }
});

// ------------------------------------------------------------------------------------------------------------------
// J2's stub DOM (the harnesses of j2_ui_render.js and j2_graph_layout.js run the page script against it)
// ------------------------------------------------------------------------------------------------------------------
test("the script loads in J2's stub DOM and the page's own names do not clash with it", () => {
  const noop = () => noop;
  const el = () => new Proxy({innerHTML: "", textContent: "", value: "", style: {}, dataset: {}, disabled: false, open: false,
    classList: {toggle: noop, add: noop, remove: noop, contains: () => false}, children: [], scrollHeight: 0},
  {get: (t, k) => (k in t ? t[k] : (k === "querySelectorAll" ? () => [] : noop)), set: (t, k, v) => { t[k] = v; return true; }});
  const els = {};
  const sandbox = vm.createContext({
    document: {getElementById: id => els[id] || (els[id] = el()), querySelector: () => el(), querySelectorAll: () => [], body: el(), addEventListener: noop, createElement: el},
    location: {search: "", href: "", hash: ""}, localStorage: {getItem: () => null, setItem: noop}, CSS: {escape: x => x},
    matchMedia: () => ({matches: true, addEventListener: noop}), fetch: () => Promise.reject(new Error("no network")),
    setTimeout: noop, setInterval: noop, requestAnimationFrame: noop, console, URLSearchParams, Date, JSON, Math, Set, Map, Promise,
  });
  const fetchBefore = sandbox.fetch;
  vm.runInContext(CODE, sandbox);
  assert.equal(sandbox.fetch, fetchBefore, "no block, no wrapper");
  assert.deepEqual(plain(vm.runInContext("SutraCtx.boot", sandbox)), {});
  assert.equal(vm.runInContext("SutraCtx.dept", sandbox), "");
  assert.equal(vm.runInContext("SutraCtx.currentTab", sandbox), "");
  // what E4, E5, E6 and E10 of the port do on that page
  const out = vm.runInContext(`
    let viewRun = "";
    const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "") + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");
    const title = SutraCtx.boot.dept_label || "Your website team";
    SutraCtx.tab("map");
    const pins = "j2pos:" + SutraCtx.dept + ":" + ((typeof viewRun !== "undefined" && viewRun) || "live") + ":tree";
    ({runQ: runQ(), title, tab: SutraCtx.currentTab, pins, href: SutraCtx.withDept("/api/state?since=0")})`, sandbox);
  assert.deepEqual(plain(out), {runQ: "", title: "Your website team", tab: "map", pins: "j2pos::live:tree", href: "/api/state?since=0"});
  assert.equal(vm.runInContext("SutraCtx.esc(\"a<b\")", sandbox), "a&lt;b");
  assert.equal(vm.runInContext("SutraCtx.run()", sandbox), "");
  // J2's page script then declares its own names without a clash
  vm.runInContext(`const esc = s => s, paint = () => {}, $ = id => id, md = 1, who = 2, col = 3, WHO = {}, isWf = 5; function poll(){}`, sandbox);
});
