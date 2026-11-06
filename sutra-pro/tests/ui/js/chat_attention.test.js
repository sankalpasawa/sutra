"use strict";
// ChatAttention (sutra_app/ui/static/js/chat_attention.js): the tab title count and one desktop notice per new thing (gap package attention).
// Re-expresses the old app's test_agents.js FakeNotification cases: focused fires nothing, denied fires nothing, a repeat fires once, first
// sight is not news, a short wait stays silent, permission is asked at most once and never after a No.
// Run with: node --test tests/ui/js/chat_attention.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const CA = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_attention.js"));

const Q = (id, name = "Web") => ({message_id: id, session_id: "cs_5e0a77b19c3d", kind: "question", dept_name: name, text: "Which?", asked_at: "2026-11-04T10:00:00Z"});
const P = (id, text = 'Web ran into a problem on "Menu"') => ({kind: "problem", task_id: id, text});
const T1 = "tsk_aaaaaaaaaaaa";

function memoryStorage() {
  const data = {};
  return {getItem: k => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, data};
}

function fakeNotification(permission) {
  const shown = [];
  function N(title, options) { this.title = title; this.options = options; this.closed = false; shown.push(this); }
  N.prototype.close = function () { this.closed = true; };
  N.permission = permission;
  N.asked = 0;
  N.requestPermission = () => { N.asked += 1; N.permission = "granted"; return Promise.resolve("granted"); };
  N.shown = shown;
  return N;
}

function fakeTimers() {
  const pending = [];
  return {setTimeout: (f, ms) => { const t = {f, ms}; pending.push(t); return t; }, clearTimeout: t => { const i = pending.indexOf(t); if (i >= 0) pending.splice(i, 1); }, pending};
}

function harness({permission = "granted", focused = false, storage = memoryStorage()} = {}) {
  let clock = 1_000_000;
  const doc = {title: "Sutra", focused, hasFocus() { return this.focused; }};
  const win = {focused: 0, focus() { this.focused += 1; }};
  const N = fakeNotification(permission);
  const opened = [];
  const timers = fakeTimers();
  const handle = CA.create({doc, win, Notification: N, storage, timers, now: () => clock, onOpen: item => opened.push(item)});
  return {handle, doc, win, N, opened, timers, storage, tick: ms => { clock += ms; }, get now() { return clock; }};
}

test("the title carries the count, never stacks it and goes back at zero", () => {
  assert.equal(CA.titleFor("Sutra", 2), "(2) Sutra");
  assert.equal(CA.titleFor("(2) Sutra", 5), "(5) Sutra");
  assert.equal(CA.titleFor("(5) Web · Sutra", 0), "Web · Sutra");
  assert.equal(CA.titleFor("Sutra", -1), "Sutra");
  assert.equal(CA.titleFor("Sutra", NaN), "Sutra");
  assert.equal(CA.baseOf("(12) Usage and log - Sutra"), "Usage and log - Sutra");
  const h = harness();
  h.handle.update(CA.itemsOf([Q(7), Q(8)], [], {}));
  assert.equal(h.doc.title, "(2) Sutra");
  h.handle.update([]);
  assert.equal(h.doc.title, "Sutra");
});

test("items: one per question or approval, one per problem not marked seen; quiet and finished rows are not items", () => {
  const items = CA.itemsOf([Q(7, "Web\u0007\nTeam"), {message_id: 9, kind: "approval", text: "Add?"}, {message_id: "x"}],
    [P(T1), {kind: "quiet", task_id: "tsk_bbbbbbbbbbbb", text: "q"}, {kind: "finished", task_id: "tsk_cccccccccccc", text: "f"},
      P("tsk_dddddddddddd"), P("not-a-task")], {tsk_dddddddddddd: true});
  assert.deepEqual(items.map(i => i.key), ["q:7", "q:9", "p:" + T1]);
  assert.equal(items[0].body, "Web Team has a question for you");                     // control characters gone, one line
  assert.equal(items[1].body, "Sutra needs your approval for a change to the org chart");
  assert.equal(items[2].body, 'Web ran into a problem on "Menu"');
  assert.deepEqual(items[2].ref, {kind: "problem", task_id: T1});
});

test("first sight is not news: what is listed on the first update never fires", () => {
  const h = harness();
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  h.tick(60000);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 0);
});

test("a new question fires once, 20 s after it appeared, and a repeat never fires again", () => {
  const h = harness();
  h.handle.update([]);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 0);
  assert.equal(h.timers.pending.length, 1);
  assert.ok(h.timers.pending[0].ms >= CA.MIN_MS);
  h.tick(CA.MIN_MS);
  h.timers.pending.shift().f();
  assert.equal(h.N.shown.length, 1);
  assert.equal(h.N.shown[0].title, "Sutra");
  assert.equal(h.N.shown[0].options.body, "Web has a question for you");
  assert.equal(h.N.shown[0].options.tag, "sutra-q:7");
  h.tick(5000);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 1);
});

test("a question answered within seconds makes no noise", () => {
  const h = harness();
  h.handle.update([]);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  h.tick(5000);
  h.handle.update([]);
  h.tick(30000);
  h.handle.update([]);
  assert.equal(h.N.shown.length, 0);
  assert.equal(h.timers.pending.length, 0);
});

test("a focused window fires nothing, and the question is not announced later when the owner looks away", () => {
  const h = harness({focused: true});
  h.handle.update([]);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  h.tick(CA.MIN_MS);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  h.doc.focused = false;
  h.tick(CA.MIN_MS);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 0);
});

test("denied or unsupported fires nothing", () => {
  for (const permission of ["denied", "default"]) {
    const h = harness({permission});
    h.handle.update([]);
    h.handle.update(CA.itemsOf([Q(7)], [P(T1)], {}));
    h.tick(CA.MIN_MS);
    h.handle.update(CA.itemsOf([Q(7)], [P(T1)], {}));
    assert.equal(h.N.shown.length, 0, permission);
  }
  const doc = {title: "Sutra", hasFocus: () => false};
  const none = CA.create({doc, Notification: null, storage: memoryStorage(), timers: fakeTimers(), now: () => 1});
  none.update([]);
  none.update(CA.itemsOf([Q(1)], [], {}));
  assert.equal(none.state().permission, "unsupported");
  assert.equal(none.offered(), false);
  assert.equal(doc.title, "(1) Sutra");
});

test("a crash is announced like a question, and a click brings the window and the card forward", () => {
  const h = harness();
  h.handle.update([]);
  h.handle.update(CA.itemsOf([], [P(T1)], {}));
  h.tick(CA.MIN_MS);
  h.handle.update(CA.itemsOf([], [P(T1)], {}));
  assert.equal(h.N.shown.length, 1);
  h.N.shown[0].onclick();
  assert.equal(h.win.focused, 1);
  assert.deepEqual(h.opened.map(i => i.key), ["p:" + T1]);
  assert.equal(h.N.shown[0].closed, true);
});

test("two tabs of one browser announce a key once between them", () => {
  const storage = memoryStorage();
  const a = harness({storage});
  const b = harness({storage});
  for (const h of [a, b]) { h.handle.update([]); h.handle.update(CA.itemsOf([Q(7)], [], {})); h.tick(CA.MIN_MS); h.handle.update(CA.itemsOf([Q(7)], [], {})); }
  assert.equal(a.N.shown.length + b.N.shown.length, 1);
});

test("permission is offered only when something waits, asked only from enable(), and never again after No thanks", async () => {
  assert.equal(CA.offer([], "default", false), false);
  assert.equal(CA.offer([{key: "q:1"}], "default", false), true);
  assert.equal(CA.offer([{key: "q:1"}], "denied", false), false);
  assert.equal(CA.offer([{key: "q:1"}], "granted", false), false);
  assert.equal(CA.offer([{key: "q:1"}], "default", true), false);
  const h = harness({permission: "default"});
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.asked, 0);                                       // never on load
  assert.equal(h.handle.offered(), true);
  assert.equal(await h.handle.enable(), "granted");
  assert.equal(h.N.asked, 1);
  assert.equal(h.handle.offered(), false);
  const no = harness({permission: "default"});
  no.handle.update(CA.itemsOf([Q(7)], [], {}));
  no.handle.decline();
  assert.equal(no.handle.offered(), false);
  assert.equal(no.storage.data["sutra:notify"], "off");
});

test("storage that throws never breaks the title or the notice", () => {
  const broken = {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }};
  const h = harness({storage: broken});
  h.handle.update([]);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  h.tick(CA.MIN_MS);
  h.handle.update(CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.doc.title, "(1) Sutra");
  assert.equal(h.N.shown.length, 1);
  h.handle.decline();
  assert.equal(h.handle.offered(), false);                          // granted already
});

test("plan is pure: the same input gives the same answer and the input state is not changed", () => {
  const items = [{key: "q:1"}];
  const s0 = CA.plan(null, [], {now: 0, focused: false, permission: "granted"}).state;
  const frozen = JSON.stringify(s0);
  const a = CA.plan(s0, items, {now: 10, focused: false, permission: "granted"});
  const b = CA.plan(s0, items, {now: 10, focused: false, permission: "granted"});
  assert.deepEqual(a, b);
  assert.equal(JSON.stringify(s0), frozen);
  assert.equal(a.wakeIn, CA.MIN_MS);
  const due = CA.plan(a.state, items, {now: 10 + CA.MIN_MS, focused: false, permission: "granted"});
  assert.deepEqual(due.notify.map(i => i.key), ["q:1"]);
  assert.equal(due.wakeIn, null);
});
