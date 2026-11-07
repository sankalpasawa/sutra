"use strict";
// Quiet hours and the hourly cap in ChatAttention (gap package routines-limits). The window rule runs the SAME case table as the Python lane
// (tests/fixtures/quiet_hours_cases.json): the page cannot ask the server on every ping, so the rule is written twice and one table keeps it honest.
// Run with: node --test tests/ui/js/attention_prefs.test.js
process.env.TZ = "UTC";                                            // the window is read in the machine's local time: pin it for the test
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const CA = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_attention.js"));
const CASES = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../fixtures/quiet_hours_cases.json"), "utf8"));

const NIGHT = {start: "21:00", end: "08:00"};
const T = n => "tsk_" + String(n).padStart(12, "a");
const Q = id => ({message_id: id, session_id: "cs_5e0a77b19c3d", kind: "question", dept_name: "Web", text: "Which?"});
const P = (n) => ({kind: "problem", task_id: T(n), text: 'Web ran into a problem on "Menu"'});
const F = (n, text = 'Web finished "Menu"') => ({kind: "finished", task_id: T(n), text});
const at = (h, m = 0) => Date.UTC(2026, 10, 4, h, m);              // 4 Nov 2026, UTC (= local here)
const HOUR = 3600000;

function memoryStorage() {
  const data = {};
  return {getItem: k => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, data};
}

function fakeNotification(permission) {
  const shown = [];
  function N(title, options) { this.title = title; this.options = options; shown.push(this); }
  N.permission = permission;
  N.shown = shown;
  return N;
}

function harness({start, prefs, storage = memoryStorage(), permission = "granted"} = {}) {
  let clock = start;
  const doc = {title: "Sutra", hasFocus: () => false};
  const N = fakeNotification(permission);
  const handle = CA.create({doc, Notification: N, storage, now: () => clock, prefs, timers: {setTimeout: () => 0, clearTimeout() {}}});
  return {handle, doc, N, storage, tick: ms => { clock += ms; }, at: t => { clock = t; }, get now() { return clock; }};
}

// first sight is not news: read the lists once, then show them again after the 20 s wait
function arrive(h, make) {
  h.handle.update([]);
  h.handle.update(make());
  h.tick(CA.MIN_MS);
  h.handle.update(make());
}

// ---- the window rule, run against the shared table ----------------------------------------------------------------------------------

test("the window rule runs every case of the shared table", () => {
  assert.ok(CASES.active.length >= 19 && CASES.invalid.length >= 13);
  for (const c of CASES.active) {
    assert.equal(CA.windowActive(CASES.windows[c.window], c.at), c.quiet, `${c.window} ${c.at}: ${c.why}`);
  }
});

test("the same cases with a Date and with minutes after midnight", () => {
  for (const c of CASES.active) {
    const [h, m] = c.at.split(":").map(Number);
    assert.equal(CA.windowActive(CASES.windows[c.window], new Date(Date.UTC(2026, 10, 4, h, m))), c.quiet, `date ${c.window} ${c.at}`);
    assert.equal(CA.windowActive(CASES.windows[c.window], h * 60 + m), c.quiet, `minutes ${c.window} ${c.at}`);
  }
});

test("every invalid window of the shared table is not a window and so is never quiet", () => {
  for (const c of CASES.invalid) {
    assert.equal(CA.cleanQuiet(c.value), null, c.why);
    assert.equal(CA.windowActive(c.value, "03:00"), false, c.why);
  }
  assert.deepEqual(CA.cleanQuiet(NIGHT), NIGHT);
  assert.equal(CA.windowActive(null, "03:00"), false);
  assert.equal(CA.windowActive(NIGHT, "not a time"), false);
  assert.equal(CA.windowActive(NIGHT, NaN), false);
});

// ---- the rolling hour -----------------------------------------------------------------------------------------------------------------

test("an unknown rate suppresses and so does zero; a known rate counts the last 60 minutes", () => {
  const now = at(12);
  for (const rate of [null, undefined, NaN, "3", 2.5, true, -1, 0, Infinity]) assert.equal(CA.nudgeAllowed([], now, rate), false, String(rate));
  assert.equal(CA.nudgeAllowed([], now, 3), true);
  assert.equal(CA.nudgeAllowed([now - 60000, now - 120000], now, 3), true);
  assert.equal(CA.nudgeAllowed([now - 60000, now - 120000, now - 180000], now, 3), false);
  assert.equal(CA.nudgeAllowed([now - HOUR, now - HOUR - 1, now - 120000, now - 180000], now, 3), true);        // an hour ago is out of the hour
  assert.equal(CA.nudgeAllowed([now + 5000, now - 1], now, 2), true);                                           // a ping "from the future" (clock moved back) is not counted
  assert.equal(CA.nudgeAllowed("junk", now, 3), true);
});

// ---- quiet hours: no push, the count stays -----------------------------------------------------------------------------------------------

test("a question at two in the morning inside the window pushes nothing and the count is still in the title", () => {
  const h = harness({start: at(2), prefs: () => ({quiet: NIGHT, nudges: 3})});
  arrive(h, () => CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 0);
  assert.equal(h.doc.title, "(1) Sutra");                                                    // nothing is hidden: the count stays
});

test("the same question at noon is announced", () => {
  const h = harness({start: at(12), prefs: () => ({quiet: NIGHT, nudges: 3})});
  arrive(h, () => CA.itemsOf([Q(7)], [], {}));
  assert.equal(h.N.shown.length, 1);
});

test("a crash obeys quiet hours too, and a window that ends keeps nothing back for later", () => {
  const edge = harness({start: at(7, 59) + 50000, prefs: () => ({quiet: NIGHT, nudges: 3})});     // seen at 07:59:50, due at 08:00:10: the window has just ended
  arrive(edge, () => CA.itemsOf([], [P(1)], {}));
  assert.equal(edge.N.shown.length, 1);
  const q = harness({start: at(7, 30), prefs: () => ({quiet: NIGHT, nudges: 3})});
  arrive(q, () => CA.itemsOf([], [P(2)], {}));
  assert.equal(q.N.shown.length, 0);                                                          // due at 07:30:20: quiet, settled silently
  q.at(at(9));
  q.handle.update(CA.itemsOf([], [P(2)], {}));
  assert.equal(q.N.shown.length, 0);                                                          // no catch-up notice when quiet ends
});

test("quiet hours that cannot be read leave the app speaking", () => {
  for (const prefs of [undefined, () => { throw new Error("no"); }, () => null, () => ({quiet: "21:00-08:00"}), () => ({quiet: {start: "10:00", end: "10:00"}})]) {
    const h = harness({start: at(3), prefs});
    arrive(h, () => CA.itemsOf([Q(7)], [], {}));
    assert.equal(h.N.shown.length, 1);
  }
});

// ---- finished work: the hourly cap -----------------------------------------------------------------------------------------------------------

test("finished work is a notice only when asked for, and never counts in the title", () => {
  const heads = [F(1), P(2)];
  assert.deepEqual(CA.itemsOf([], heads, {}).map(i => i.key), ["p:" + T(2)]);                   // as before: no finished item unless asked
  const items = CA.itemsOf([Q(7)], heads, {}, {finished: true});
  assert.deepEqual(items.map(i => i.key), ["q:7", "p:" + T(2), "f:" + T(1)]);                   // questions first, finished last
  assert.equal(items[2].body, 'Web finished "Menu"');
  assert.deepEqual(items[2].ref, {kind: "finished", task_id: T(1)});
  assert.deepEqual(CA.itemsOf([], [F(1)], {[T(1)]: true}, {finished: true}), []);                // "Got it" is respected
  assert.equal(CA.itemsOf([], [F(1, "")], {}, {finished: true})[0].body, "A team finished its work");
  const h = harness({start: at(12), prefs: () => ({quiet: null, nudges: 3})});
  h.handle.update(items);
  assert.equal(h.doc.title, "(2) Sutra");                                                      // the question and the crash; the finished notice is news, not a debt
  assert.equal(h.handle.state().items, 2);
});

test("a finished notice obeys the hourly cap and a question does not", () => {
  const h = harness({start: at(12), prefs: () => ({quiet: null, nudges: 2})});
  const make = () => CA.itemsOf([Q(7)], [F(1), F(2), F(3)], {}, {finished: true});
  arrive(h, make);
  const keys = h.N.shown.map(n => n.options.tag);
  assert.equal(keys.filter(k => k.startsWith("sutra-f:")).length, 2);                           // two of the three finished rows, the cap
  assert.ok(keys.includes("sutra-q:7"));                                                       // the question is not capped
});

test("a rate of zero or an unknown rate never pushes a finished notice but still pushes a question and a crash", () => {
  for (const nudges of [0, null, undefined]) {
    const h = harness({start: at(12), prefs: () => ({quiet: null, nudges})});
    arrive(h, () => CA.itemsOf([Q(7)], [P(1), F(2)], {}, {finished: true}));
    assert.deepEqual(h.N.shown.map(n => n.options.tag).sort(), ["sutra-p:" + T(1), "sutra-q:7"], String(nudges));
  }
});

test("a finished notice in quiet hours is silent even with budget", () => {
  const h = harness({start: at(23), prefs: () => ({quiet: NIGHT, nudges: 5})});
  arrive(h, () => CA.itemsOf([], [F(1)], {}, {finished: true}));
  assert.equal(h.N.shown.length, 0);
});

test("a reload does not refund the hour's budget, and an hour later it is back", () => {
  const storage = memoryStorage();
  const prefs = () => ({quiet: null, nudges: 1});
  const first = harness({start: at(12), prefs, storage});
  arrive(first, () => CA.itemsOf([], [F(1)], {}, {finished: true}));
  assert.equal(first.N.shown.length, 1);
  assert.equal(JSON.parse(storage.data["sutra:nudges"]).length, 1);
  const reloaded = harness({start: at(12, 10), prefs, storage});                              // a new page over the same storage
  arrive(reloaded, () => CA.itemsOf([], [F(2)], {}, {finished: true}));
  assert.equal(reloaded.N.shown.length, 0);
  const later = harness({start: at(13, 30), prefs, storage});                                 // the first ping is now more than an hour old
  arrive(later, () => CA.itemsOf([], [F(3)], {}, {finished: true}));
  assert.equal(later.N.shown.length, 1);
});

test("a finished notice another tab already announced does not use this tab's budget", () => {
  const storage = memoryStorage();
  const prefs = () => ({quiet: null, nudges: 3});
  const a = harness({start: at(12), prefs, storage});
  const b = harness({start: at(12), prefs, storage});
  for (const h of [a, b]) arrive(h, () => CA.itemsOf([], [F(1)], {}, {finished: true}));
  assert.equal(a.N.shown.length + b.N.shown.length, 1);
  assert.equal(JSON.parse(storage.data["sutra:nudges"]).length, 1);
});

test("a blocked storage never breaks an update", () => {
  const broken = {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }};
  const h = harness({start: at(12), prefs: () => ({quiet: null, nudges: 3}), storage: broken});
  assert.doesNotThrow(() => arrive(h, () => CA.itemsOf([Q(7)], [F(1)], {}, {finished: true})));
});

test("plan() on its own: quiet settles silently, the cap is spent in order, history comes back", () => {
  const items = [{key: "q:1", title: "Sutra", body: "b"}, {key: "f:" + T(1), title: "Sutra", body: "b"}, {key: "f:" + T(2), title: "Sutra", body: "b"}];
  const base = {now: at(12), focused: false, permission: "granted", minMs: 0};
  const started = {started: true, seen: {}, settled: {}};                                    // already past first sight, so everything is due at once (minMs 0)
  const quiet = CA.plan(started, items, {...base, quiet: true, nudgesPerHour: 5, history: []});
  assert.deepEqual(quiet.notify, []);
  assert.equal(quiet.history.length, 0);
  const second = CA.plan(started, items, {...base, nudgesPerHour: 1, history: []});
  assert.deepEqual(second.notify.map(i => i.key), ["q:1", "f:" + T(1)]);
  assert.deepEqual(second.history, [at(12)]);
  const old = CA.plan(started, items, {...base, nudgesPerHour: 1, history: [at(12) - 2 * HOUR, at(12) + 1000, "x"]});
  assert.equal(old.notify.length, 2);                                                        // old and future entries are not counted, junk is dropped
  assert.deepEqual(old.history, [at(12)]);
});
