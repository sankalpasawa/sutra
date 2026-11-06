"use strict";
// AttentionPill (sutra_app/ui/static/js/attention_pill.js): the org-wide "N need you" pill of a team page and the console (gap package attention).
// The old app's corner card rule (15-shadow-overlay.js applyDotState): quiet stands the alarm down, it never hides the count.
// Run with: node --test tests/ui/js/attention_pill.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const AP = require(path.join(JS, "attention_pill.js"));
const HV = require(path.join(JS, "heads_up_view.js"));
const CA = require(path.join(JS, "chat_attention.js"));

const T1 = "tsk_aaaaaaaaaaaa";
const Q = id => ({message_id: id, session_id: "cs_5e0a77b19c3d", kind: "question", dept_name: "Web", text: "Which?", asked_at: "2026-11-04T10:00:00Z"});
const P = (id, extra = {}) => Object.assign({kind: "problem", tone: "err", task_id: id, dept_id: "web", dept_name: "Web", title: "Menu", status: "crashed",
  text: 'Web ran into a problem on "Menu"', outcome: "", at: "2026-11-04T10:00:00Z", since_s: 60, retry: true}, extra);

test("nothing is drawn at zero; one and twelve read in words; problems ride a quieter line; the aria-label says both", () => {
  assert.equal(AP.pillHtml({count: 0}), "");
  assert.equal(AP.pillHtml({}), "");
  assert.equal(AP.pillHtml(null), "");
  assert.equal(AP.pillHtml({count: -3}), "");
  assert.equal(AP.pillHtml({count: 1}), '<a class="apill quiet" href="/" aria-label="1 needs you">1 needs you</a>');
  assert.equal(AP.pillHtml({count: 12, problems: 2, fresh: true}),
    '<a class="apill fresh" href="/" aria-label="12 need you, 2 to try again">12 need you <small>2 to try again</small></a>');
  assert.match(AP.pillHtml({count: 1, problems: 9}), /1 to try again/);                // never more problems than the count
});

test("a quiet pill keeps its count: quiet calms the pulse, it never hides the news", () => {
  const quiet = AP.pillHtml({count: 3, fresh: false});
  assert.match(quiet, /class="apill quiet"/);
  assert.match(quiet, />3 need you</);
});

function fakeTimers() {
  const t = {intervals: [], timeouts: []};
  return Object.assign(t, {
    setTimeout: (f, ms) => { const h = {f, ms}; t.timeouts.push(h); return h; }, clearTimeout: h => { t.timeouts = t.timeouts.filter(x => x !== h); },
    setInterval: (f, ms) => { const h = {f, ms}; t.intervals.push(h); return h; }, clearInterval: h => { t.intervals = t.intervals.filter(x => x !== h); },
    flush() { const due = t.timeouts; t.timeouts = []; due.forEach(h => h.f()); },
  });
}

function fakeApi(data) {
  const calls = [];
  return {calls, get: async path => { calls.push(path); if (data.fail && data.fail.includes(path)) throw new Error("down"); return path === "/api/needs-you" ? data.needs : data.heads; }};
}

const tick = () => new Promise(r => setImmediate(r));

function fakeDoc(state = "visible") {
  const listeners = {};
  return {visibilityState: state, listeners, addEventListener: (t, f) => { listeners[t] = f; }, removeEventListener: (t, f) => { if (listeners[t] === f) delete listeners[t]; }};
}

test("mount reads both lists, counts asks plus problems, and reads again on its own clock: 5 s in front, 15 s behind", async () => {
  const data = {needs: [Q(7)], heads: [P(T1), {kind: "finished", task_id: "tsk_bbbbbbbbbbbb", text: "done"}]};
  const api = fakeApi(data);
  const host = {innerHTML: "", hidden: true};
  const timers = fakeTimers();
  const doc = fakeDoc();
  const handle = AP.mount(host, {api, view: HV, timers, storage: null, doc});
  await handle.first;
  assert.deepEqual(api.calls.slice().sort(), ["/api/heads-up", "/api/needs-you"]);
  assert.equal(host.hidden, false);
  assert.match(host.innerHTML, /^<a class="apill quiet" href="\/" aria-label="2 need you, 1 to try again">/);     // first paint is not news
  assert.deepEqual(timers.timeouts.map(t => t.ms), [AP.POLL_MS]);                     // one read waits, never a pile of them
  data.needs = [Q(7), Q(8)];
  timers.flush();
  await tick();
  assert.match(host.innerHTML, /class="apill fresh"[^>]*>3 need you/);
  doc.visibilityState = "hidden";
  data.needs = [];
  data.heads = [];
  timers.flush();
  await tick();
  assert.equal(host.innerHTML, "");
  assert.equal(host.hidden, true);
  assert.deepEqual(timers.timeouts.map(t => t.ms), [AP.HIDDEN_POLL_MS]);
  data.needs = [Q(9)];
  doc.visibilityState = "visible";
  doc.listeners.visibilitychange();                                                   // back in front: read at once
  await tick();
  assert.match(host.innerHTML, />1 needs you</);
  assert.equal(timers.timeouts.length, 1);
  handle.destroy();
  assert.equal(timers.timeouts.length, 0);
  assert.equal(doc.listeners.visibilitychange, undefined);
});

test("a list that cannot be read keeps what the pill had, and a problem marked Got it does not count", async () => {
  const data = {needs: [Q(7)], heads: [P(T1)]};
  const api = fakeApi(data);
  const host = {innerHTML: "", hidden: true};
  const store = {getItem: k => (k === HV.SEEN_KEY ? JSON.stringify([T1]) : null), setItem() {}};
  const handle = AP.mount(host, {api, view: HV, timers: fakeTimers(), storage: store, doc: null});
  await handle.first;
  assert.match(host.innerHTML, />1 needs you</);
  data.fail = ["/api/heads-up"];
  data.needs = [Q(7), Q(9)];
  assert.equal(await handle.refresh(), false);
  assert.match(host.innerHTML, />2 need you</);
  handle.destroy();
});

test("with ChatAttention it keeps the count in the tab title too", async () => {
  const doc = {title: "Web · Sutra", hasFocus: () => true};
  const attention = CA.create({doc, Notification: null, storage: null, timers: fakeTimers(), now: () => 1});
  const saved = globalThis.ChatAttention;
  globalThis.ChatAttention = CA;
  try {
    const handle = AP.mount({innerHTML: "", hidden: true}, {api: fakeApi({needs: [Q(1), Q(2)], heads: []}), view: HV, timers: fakeTimers(), storage: null, attention, doc: null});
    await handle.first;
    assert.equal(doc.title, "(2) Web · Sutra");
    handle.destroy();
  } finally {
    globalThis.ChatAttention = saved;
  }
});

test("the page file wiring: the team page gets the three scripts from dept_ext.js in order, the console loads them, Home never mounts the pill", () => {
  const ext = fs.readFileSync(path.join(JS, "dept_ext.js"), "utf8");
  assert.match(ext, /\["heads_up_view", "chat_attention", "attention_pill"\]/);
  assert.match(ext, /tag\.async = false/);
  const pages = path.resolve(__dirname, "../../../sutra_app/ui/pages");
  const consolePage = fs.readFileSync(path.join(pages, "console.html"), "utf8");
  const order = ["heads_up_view.js", "chat_attention.js", "attention_pill.js"].map(n => consolePage.indexOf('src="/ui/js/' + n + '"'));
  assert.ok(order.every(i => i > 0) && order[0] < order[1] && order[1] < order[2]);
  assert.doesNotMatch(fs.readFileSync(path.join(pages, "home.html"), "utf8"), /attention_pill\.js/);
  assert.doesNotMatch(fs.readFileSync(path.join(pages, "j2_ui.html"), "utf8"), /attention_pill|heads_up_view|chat_attention/);    // J2's page is not edited
  const src = fs.readFileSync(path.join(JS, "attention_pill.js"), "utf8");
  assert.match(src, /page === "dept" \|\| page === "console"/);
});
