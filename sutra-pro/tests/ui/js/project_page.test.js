"use strict";
// The project page's client (MAN-13, D326): it reads the snapshot, the audit and the messages (after the last whole number, a gap read again), follows project, node and task events with ONE
// refetch for a burst, polls while the stream is down, answers a question through the right route, says in plain words when something fails and does not trust a card for another project.
// Run with: node --test tests/ui/js/project_page.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ProjectPage = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "project_page.js"));
const ID = "prj_0123456789ab";
const APPROVAL = "ap_0123456789ab";

const snapshot = (over = {}) => Object.assign({project: {id: ID, title: "A page", status: "running", failure_policy: "stop_branch", paused: false, budget_credits: 60, stop_reason: ""},
  nodes: [{id: "nd_0123456789ab", role: "worker", plan_ref: "a1", state: "running", depends_on: [], scope: [], attempt: 1, failure_reason: ""}], edges: [], spend: {calls: 3, usd: null}, cards: [], system_cards: [], last_message_seq: 0}, over);

function world(over = {}) {
  const calls = [];
  const posts = [];
  const answers = Object.assign({snap: snapshot(), audit: [], messages: [], location: {usual: true, note: ""}}, over);
  const api = {
    get: async (url, query) => {
      calls.push([url, query]);
      if (answers.fail && answers.fail(url)) throw answers.fail(url);
      if (url === "/api/projects/" + ID) return typeof answers.snap === "function" ? answers.snap() : answers.snap;
      if (url.endsWith("/audit")) return answers.audit.filter(r => r.seq > query.after);
      if (url.endsWith("/messages")) return (typeof answers.messages === "function" ? answers.messages(query) : answers.messages).filter(r => r.seq > query.after);
      if (url === "/api/nodes/app-location") return answers.location;
      throw new Error("unexpected " + url);
    },
    post: async (url, body) => {
      posts.push([url, body]);
      if (answers.failPost) throw answers.failPost;
      return {};
    },
  };
  const nodes = {};
  const doc = {title: "", activeElement: null, getElementById: name => (nodes[name] = nodes[name] || {id: name, innerHTML: "", textContent: "", contains: () => false})};
  const sources = [];
  class Source {
    constructor(url) { this.url = url; this.listeners = {}; this.closed = false; sources.push(this); }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    close() { this.closed = true; }
    emit(name, data) { this.listeners[name]({data: JSON.stringify(data || {})}); }
  }
  const timers = [];
  const intervals = [];
  const clocks = {
    setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; },
    clearTimeout: n => { if (timers[n - 1]) timers[n - 1].fn = null; },
    setInterval: (fn, ms) => { intervals.push({fn, ms, on: true}); return intervals.length; },
    clearInterval: n => { if (intervals[n - 1]) intervals[n - 1].on = false; },
  };
  const page = ProjectPage.create(Object.assign({doc, api, id: ID, EventSourceCtor: Source}, clocks));
  const fire = async () => { const t = timers.filter(x => x.fn); timers.length = 0; for (const x of t) await x.fn(); };
  const reads = () => calls.filter(c => c[0] === "/api/projects/" + ID).length;
  return {page, calls, posts, nodes, sources, timers, intervals, answers, fire, reads};
}
const button = dataset => ({dataset, disabled: false, closest() { return this; }});
const click = (w, b) => w.page.onClick({target: b, preventDefault() {}});

test("start reads the project, its audit and the note about the app's place, draws them and opens one stream", async () => {
  const w = world({audit: [{seq: 1, at: "2026-11-20T10:00:00Z", action: "project.created", reason: "2 steps"}]});
  assert.equal(await w.page.start(), true);
  assert.match(w.nodes["p-head"].innerHTML, /A page/);
  assert.match(w.nodes["p-body"].innerHTML, /Project started/);
  assert.match(w.nodes["p-body"].innerHTML, /Step a1/);
  assert.equal(w.nodes["p-live"].textContent, "Not connected");
  w.sources[0].listeners.open();
  assert.equal(w.nodes["p-live"].textContent, "Live");
  assert.equal(w.sources.length, 1);
  assert.equal(w.sources[0].url, "/api/events?topics=project,node,task");
  assert.ok(w.calls.some(c => c[0] === "/api/nodes/app-location"));
  assert.equal(w.page.state().auditAfter, 1);
});

test("an app that is not in the usual place shows its note and one that is shows none", async () => {
  const off = world({location: {usual: false, note: "Sutra Pro is not in your Applications folder."}});
  await off.page.start();
  assert.match(off.nodes["p-body"].innerHTML, /not in your Applications folder/);
  const usual = world();
  await usual.page.start();
  assert.equal(usual.nodes["p-body"].innerHTML.includes('role="note"'), false);
  const broken = world({fail: url => (url === "/api/nodes/app-location" ? new Error("x") : null)});
  assert.equal(await broken.page.start(), true, "the note is a courtesy: a failed read changes nothing else");
});

test("a burst of events for this project makes ONE refetch, an event for another project makes none", async () => {
  const w = world();
  await w.page.start();
  const before = w.reads();
  const other = "prj_ffffffffffff";
  w.sources[0].emit("project.updated", {project_id: other});
  w.sources[0].emit("node.updated", {project_id: other});
  assert.equal(w.timers.filter(t => t.fn).length, 0);
  for (let i = 0; i < 5; i += 1) w.sources[0].emit(i % 2 ? "node.updated" : "project.updated", {project_id: ID});
  assert.equal(w.timers.filter(t => t.fn).length, 1);
  assert.equal(w.timers[0].ms, ProjectPage.COALESCE_MS);
  await w.fire();
  assert.equal(w.reads(), before + 1);
});

test("a task event, which carries no project, and a resync make a refetch", async () => {
  const w = world();
  await w.page.start();
  w.sources[0].emit("task.updated", {task_id: "tsk_x"});
  assert.equal(w.timers.filter(t => t.fn).length, 1);
  await w.fire();
  w.sources[0].emit("server.resync", {reason: "gap"});
  assert.equal(w.timers.filter(t => t.fn).length, 1);
});

test("while the stream is down the page asks every few seconds, and when it opens again it stops asking", async () => {
  const w = world();
  await w.page.start();
  const slow = w.intervals.length;
  w.sources[0].listeners.error();
  assert.equal(w.page.state().live, "polling");
  const poll = w.intervals[slow];
  assert.equal(poll.ms, ProjectPage.POLL_MS);
  const before = w.reads();
  await poll.fn();
  assert.equal(w.reads(), before + 1);
  w.sources[0].listeners.open();
  assert.equal(poll.on, false);
  assert.equal(w.page.state().live, "live");
});

test("messages are read after the last whole number and a gap is read again from it", async () => {
  const rows = [1, 2, 3].map(seq => ({seq, from: {node_id: "nd_0123456789ab"}, body: "m" + seq}));
  let served = 0;
  const w = world({snap: () => snapshot({last_message_seq: 3}), messages: query => {
    served += 1;
    return served === 1 ? rows.filter(r => r.seq !== 1) : rows;                // the first answer leaves out number 1: a gap
  }});
  await w.page.start();
  const asked = w.calls.filter(c => c[0].endsWith("/messages")).map(c => c[1].after);
  assert.deepEqual(asked, [0, 0]);
  assert.deepEqual(w.page.state().messages.map(m => m.seq), [1, 2, 3]);
  assert.match(w.nodes["p-body"].innerHTML, /m3/);
  w.answers.snap = () => snapshot({last_message_seq: 3});
  const before = w.calls.length;
  await w.page.refresh();
  assert.equal(w.calls.slice(before).some(c => c[0].endsWith("/messages")), false, "nothing new to read");
});

test("an answer goes to the question's route with the owner's word and the page reads the project again", async () => {
  const w = world({snap: snapshot({cards: [{kind: "tier", approval_id: APPROVAL, question: "Allow?", options: ["allow_once", "deny"], item: ""}]})});
  await w.page.start();
  const reads = w.reads();
  assert.equal(await w.page.act(button({act: "node-answer", project: ID, approval: APPROVAL, item: "", decision: "allow_once"})), true);
  assert.deepEqual(w.posts, [["/api/projects/" + ID + "/approvals/" + APPROVAL, {decision: "allow_once"}]]);
  assert.equal(w.reads(), reads + 1);
});

test("a permission card uses the check and skip routes of its item", async () => {
  const w = world();
  await w.page.start();
  await w.page.act(button({act: "node-answer", project: ID, approval: APPROVAL, item: "files_folders", decision: "check_again"}));
  await w.page.act(button({act: "node-answer", project: ID, approval: APPROVAL, item: "files_folders", decision: "skip"}));
  assert.deepEqual(w.posts, [["/api/projects/" + ID + "/system/files_folders/check", {}], ["/api/projects/" + ID + "/system/files_folders/skip", {}]]);
});

test("stop, pause, continue and stop one step each go to their own route", async () => {
  const w = world();
  await w.page.start();
  await click(w, button({act: "project-stop"}));
  await click(w, button({act: "project-pause", resume: "0"}));
  await click(w, button({act: "project-pause", resume: "1"}));
  await click(w, button({act: "node-stop", node: "nd_0123456789ab"}));
  await new Promise(r => setImmediate(r));
  assert.deepEqual(w.posts, [["/api/projects/" + ID + "/stop", {}], ["/api/projects/" + ID + "/pause", {resume: false}], ["/api/projects/" + ID + "/pause", {resume: true}], ["/api/nodes/nd_0123456789ab/stop", {}]]);
});

test("a button for another project, a word the page does not know or a bad step id posts nothing", async () => {
  const w = world();
  await w.page.start();
  assert.equal(await w.page.act(button({act: "node-answer", project: "prj_ffffffffffff", approval: APPROVAL, item: "", decision: "allow_once"})), false);
  assert.equal(await w.page.act(button({act: "node-stop", node: "../x"})), false);
  assert.equal(await w.page.act(button({act: "launch-missiles"})), false);
  assert.deepEqual(w.posts, []);
});

test("a failed answer says so in plain words and gives the button back", async () => {
  const w = world();
  await w.page.start();
  const failure = Object.assign(new Error("That question was already answered."), {status: 409});
  w.answers.failPost = failure;
  const b = button({act: "node-answer", project: ID, approval: APPROVAL, item: "", decision: "deny"});
  assert.equal(await w.page.act(b), false);
  assert.equal(b.disabled, false);
  assert.match(w.nodes["p-body"].innerHTML, /role="alert">That question was already answered\./);
  w.answers.failPost = Object.assign(new Error("x"), {status: 0});
  await w.page.act(b);
  assert.match(w.nodes["p-body"].innerHTML, /Sutra could not be reached/);
});

test("a project that is not there says so and opens no stream", async () => {
  const w = world({fail: url => (url === "/api/projects/" + ID ? Object.assign(new Error("not found"), {status: 404}) : null)});
  assert.equal(await w.page.start(), false);
  assert.match(w.nodes["p-body"].innerHTML, /That project is not here any more\./);
  assert.equal(w.sources.length, 0);
});

test("a page that could not reach Sutra at first keeps asking and opens the stream once it has the project", async () => {
  let down = true;
  const w = world({fail: url => (down && url === "/api/projects/" + ID ? Object.assign(new Error("x"), {status: 0}) : null)});
  assert.equal(await w.page.start(), false);
  assert.match(w.nodes["p-body"].innerHTML, /Sutra could not be reached/);
  assert.equal(w.sources.length, 0);
  const poll = w.intervals[0];
  assert.equal(poll.ms, ProjectPage.POLL_MS);
  await poll.fn();
  assert.equal(w.sources.length, 0, "still down");
  down = false;
  await poll.fn();
  assert.equal(w.sources.length, 1);
  assert.equal(poll.on, false);
  assert.match(w.nodes["p-body"].innerHTML, /Step a1/);
});

test("a snapshot that cannot be read keeps the last good one on the screen", async () => {
  let next = snapshot();
  const w = world({snap: () => next});
  await w.page.start();
  next = {oops: true};
  await w.page.refresh();
  assert.match(w.nodes["p-body"].innerHTML, /Step a1/);
  assert.match(w.nodes["p-body"].innerHTML, /could not be read/);
});

test("stop closes the stream and every timer, and nothing is refetched afterwards", async () => {
  const w = world();
  await w.page.start();
  w.sources[0].emit("project.updated", {project_id: ID});
  w.page.stop();
  assert.equal(w.sources[0].closed, true);
  assert.equal(w.intervals.every(i => i.on === false), true);
  assert.equal(w.timers.filter(t => t.fn).length, 0);
  const before = w.reads();
  w.page.invalidate();
  assert.equal(w.timers.filter(t => t.fn).length, 0);
  assert.equal(w.reads(), before);
});

test("the project id is read from the path and anything else is no project", () => {
  assert.equal(ProjectPage.idFromPath("/p/" + ID), ID);
  assert.equal(ProjectPage.idFromPath("/p/" + ID + "/"), ID);
  for (const bad of ["/p/", "/p/prj_x", "/d/web/", "/p/" + ID + "/x", "", null]) assert.equal(ProjectPage.idFromPath(bad), "");
});

test("a page for a bad id draws the sentence and reads nothing", async () => {
  const calls = [];
  const nodes = {};
  const doc = {getElementById: n => (nodes[n] = nodes[n] || {innerHTML: "", textContent: "", contains: () => false})};
  const page = ProjectPage.create({doc, api: {get: async u => { calls.push(u); return {}; }}, id: "../x"});
  assert.equal(await page.start(), false);
  assert.match(nodes["p-body"].innerHTML, /That is not a project\./);
  assert.deepEqual(calls, []);
});

test("an answer to a step's engine question goes to that team's chat route, only for a real session and an option word (D401)", async () => {
  const w = world();
  await w.page.start();
  assert.equal(await w.page.act(button({act: "step-answer", session: "cs_0123456789ab", text: "Option 2"})), true);
  assert.deepEqual(w.posts, [["/api/chats/cs_0123456789ab/messages", {text: "Option 2"}]]);
  for (const bad of [{session: "../x", text: "Option 1"}, {session: "cs_0123456789ab", text: "free words"}, {session: "cs_0123456789ab", text: "Option 100"}, {session: "", text: "Option 1"}]) {
    assert.equal(await w.page.act(button(Object.assign({act: "step-answer"}, bad))), false, JSON.stringify(bad));
  }
  assert.equal(w.posts.length, 1);
});
