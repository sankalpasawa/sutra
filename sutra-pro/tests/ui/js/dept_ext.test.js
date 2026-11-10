"use strict";
// DeptExt (sutra_app/ui/static/js/dept_ext.js): the glue of the team page. Here only what J2 sync 4 changed in it: the team's name in BOTH chips (the icon
// rail's strip and the Simple view's strip, with the name as their title) and the unread dot, which a question to a function and its answer never raise
// (the owner asked for them). The rest of the file is proved on the real page by tests/ui/test_dept_page.py.
// Run with: node --test tests/ui/js/dept_ext.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const DeptExt = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/dept_ext.js"));

const GLOBALS = ["document", "SutraCtx", "SutraEvents", "GraphView"];

// The page, as far as this file looks at it: globals are read when they are used, so a test sets them and puts them back.
function withPage(globals, fn) {
  const saved = Object.fromEntries(GLOBALS.map(k => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
  GLOBALS.forEach(k => { delete globalThis[k]; });
  Object.assign(globalThis, globals);
  const done = () => {
    DeptExt.destroy();
    GLOBALS.forEach(k => { delete globalThis[k]; if (saved[k]) Object.defineProperty(globalThis, k, saved[k]); });
  };
  let result;
  try {
    result = fn();
  } catch (e) {
    done();
    throw e;
  }
  return result && typeof result.then === "function" ? result.finally(done) : (done(), result);
}

const element = id => ({id, textContent: "", attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }});
const pageOf = (ids, boot) => {
  const els = Object.fromEntries(ids.map(id => [id, element(id)]));
  return {els, globals: {document: {getElementById: id => els[id] || null, body: {classList: {add() {}}}}, SutraCtx: {boot: {page: "dept", ...boot}, dept: "web"}}};
};

test("the team's name is in both chips, the rail's and the Simple view's, and is their title", () => {
  const page = pageOf(["deptchip", "deptchip-s"], {dept_label: "  Web\n team "});
  withPage(page.globals, () => assert.equal(DeptExt.chip(), false));                      // false: not an archived team
  for (const id of ["deptchip", "deptchip-s"]) {
    assert.equal(page.els[id].textContent, "Web team", id);
    assert.deepEqual(page.els[id].attrs, {title: "Web team"}, id);                        // a name the chip cuts short is whole on hover
  }
});

test("a page with only one of the chips fills that one, and a team with no name leaves the chips empty and without a title", () => {
  const rail = pageOf(["deptchip"], {dept_label: "Web"});
  withPage(rail.globals, () => DeptExt.chip());
  assert.equal(rail.els.deptchip.textContent, "Web");
  const simple = pageOf(["deptchip-s"], {dept_label: "Web"});
  withPage(simple.globals, () => DeptExt.chip());
  assert.equal(simple.els["deptchip-s"].textContent, "Web");
  const nameless = pageOf(["deptchip", "deptchip-s"], {});
  nameless.els.deptchip.textContent = "stale";
  withPage(nameless.globals, () => DeptExt.chip());
  assert.equal(nameless.els.deptchip.textContent, "");
  assert.deepEqual(nameless.els.deptchip.attrs, {});
  assert.deepEqual(nameless.els["deptchip-s"].attrs, {});
});

test("without a page there is no chip to fill and nothing is thrown", () => {
  withPage({}, () => assert.equal(DeptExt.chip(), false));
});

// A team page with its graph mounted: the unread dot is the graph's, fed by chat.message events.
function withGraph(fn) {
  const noted = [];
  const graph = {setLive() {}, update() {}, fail() {}, select() {}, destroy() {}, markSeen() {}, state: () => ({scope: "this"}), noteMessage: (sid, id) => noted.push([sid, id])};
  let stream = null;
  const events = {coalesce: f => { const g = () => f(); g.cancel = () => {}; return g; }, connect: options => { stream = options; return {close() {}}; }};
  const els = {"pane-graph": {}};
  const globals = {document: {getElementById: id => els[id] || null}, SutraCtx: {boot: {page: "dept"}, dept: "web", api: {get: async () => ({nodes: []})}},
    SutraEvents: events, GraphView: {create: () => graph}};
  return withPage(globals, () => {
    assert.equal(DeptExt.onTab("graph"), true);
    assert.ok(stream, "the graph tab opened the event stream");
    return fn(stream.onEvent, noted);
  });
}

test("a line from the team is news and raises the unread dot of its chat", () => {
  withGraph((onEvent, noted) => {
    onEvent("chat.message", {session_id: "cs_a", message: {id: 5, who: "adaptation"}});
    onEvent("chat.message", {session_id: "cs_b", message: {id: 9, who: "identity", kind: "question"}});
    assert.deepEqual(noted, [["cs_a", 5], ["cs_b", 9]]);
  });
});

test("the owner's own line, a question to a function and its answer are not news: the owner asked for them", () => {
  withGraph((onEvent, noted) => {
    onEvent("chat.message", {session_id: "cs_a", message: {id: 1, who: "user", role: "user"}});
    onEvent("chat.message", {session_id: "cs_a", message: {id: 2, who: "user", role: "user", ask: "q"}});
    onEvent("chat.message", {session_id: "cs_a", message: {id: 3, who: "audit", role: "agent", ask: "records"}});
    onEvent("chat.message", {session_id: "cs_a", message: {id: 4, who: "audit", role: "agent", ask: "model"}});
    assert.deepEqual(noted, []);
    onEvent("chat.message", {session_id: "cs_a", message: {id: 5, who: "audit", role: "agent"}});          // the next line the function writes by itself is news again
    assert.deepEqual(noted, [["cs_a", 5]]);
  });
});

test("an event that names no session or no message raises nothing", () => {
  withGraph((onEvent, noted) => {
    onEvent("chat.message", {message: {id: 1, who: "audit"}});
    onEvent("chat.message", {session_id: "", message: {id: 1, who: "audit"}});
    onEvent("chat.message", {session_id: "cs_a"});
    onEvent("chat.message", null);
    assert.deepEqual(noted, []);
  });
});
