"use strict";
// FunctionChat (sutra_app/ui/static/js/function_chat.js): J2's chat panel fills its list of questions and answers (`QA`) from the function's own chat
// session (J2 sync 4, D147 and D148). The api is a fake; the list is J2's own shape, changed in place.
// Run with: node --test tests/ui/js/function_chat.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const FC = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/function_chat.js"));

const AUDIT = "cs_e1acceab39f9";
let sidCounter = 0;
const freshSid = () => "cs_" + String(++sidCounter).padStart(12, "0");          // the module remembers what it read per session: every test reads its own

const work = (id, over = {}) => ({id, session_id: AUDIT, role: "agent", who: "audit", kind: "text", text: "Checking item " + id, state: "ok", at: "2026-11-04T10:00:00Z", ...over});
const asked = (id, text, at = "2026-11-04T10:30:05Z") => ({id, session_id: AUDIT, role: "user", who: "user", kind: "text", text, state: "ok", at, ask: "q"});
const answer = (id, text, from = "records", at = "2026-11-04T10:30:09Z") => ({id, session_id: AUDIT, role: "agent", who: "audit", kind: "text", text, state: "ok", at, ask: from});
const clock = iso => new Date(iso).toTimeString().slice(0, 8);          // the time of day J2 writes, in this machine's zone: the test never assumes one
const row = (over = {}) => ({agent: "audit", label: "Audit", kind: "function", session_id: AUDIT, node_id: "web.audit", run_id: "r1", status: "active", ...over});

// A fake api: `agents` is the answer of the team's agents route, `messages` the lines of the session (served by id, `limit` at a time, after a cursor).
function fakeApi({agents = [row()], messages = [], fail = null, hold = null} = {}) {
  const calls = [];
  return {calls, async get(p, query) {
    calls.push({path: p, query});
    if (fail && p.startsWith(fail)) throw Object.assign(new Error("down"), {status: 500});
    if (hold && p.startsWith(hold.path)) await hold.promise;
    if (p.startsWith("/api/teams/")) return agents;
    if (p.startsWith("/api/chats/")) {
      const after = query.after || 0;
      return {messages: messages.filter(m => m.id > after).sort((a, b) => a.id - b.id).slice(0, query.limit || 200)};
    }
    throw Object.assign(new Error("no route " + p), {status: 404});
  }};
}
const ctxOf = api => ({api, dept: "web"});

// ---- pure parts --------------------------------------------------------------------------------------------------------------------------

test("the ask route the node panel posts to names the team", () => {
  assert.equal(FC.askPath("web"), "/api/ask?dept=web");
  assert.equal(FC.askPath("we b/1"), "/api/ask?dept=we%20b%2F1");
});

test("a question is paired with the next answer line, whichever source it came from", () => {
  const got = FC.pairs([work(1), asked(2, "Why?"), work(3), answer(4, "Because.", "model"), asked(5, "And?"), answer(6, "Also.", "records")]);
  assert.deepEqual(got.map(p => [p.q.id, p.a && p.a.id, p.a && p.a.ask]), [[2, 4, "model"], [5, 6, "records"]]);
});

test("a question nothing answered is a pair with no answer, and an answer with no question is not a pair", () => {
  assert.deepEqual(FC.pairs([asked(1, "Why?")]).map(p => [p.q.id, p.a]), [[1, null]]);
  assert.deepEqual(FC.pairs([asked(1, "One?"), asked(2, "Two?"), answer(3, "Two.")]).map(p => [p.q.id, p.a && p.a.id]), [[1, null], [2, 3]]);
  assert.deepEqual(FC.pairs([answer(1, "Orphan.")]), []);
  assert.deepEqual(FC.pairs([work(1), work(2)]), []);
  assert.deepEqual(FC.pairs(null), []);
});

test("lines are paired in id order whatever order they arrive in, and lines that are not ask lines are never part of a pair", () => {
  const got = FC.pairs([answer(4, "Because."), work(3, {ask: "other"}), asked(2, "Why?"), null, "x"]);
  assert.deepEqual(got.map(p => [p.q.id, p.a.id]), [[2, 4]]);
});

test("an entry has J2's fields: the words, where the answer came from, the two times and the place in the feed", () => {
  const e = FC.entryOf({q: asked(2, "Why?", "2026-11-04T10:30:05Z"), a: answer(4, "Because.", "model", "2026-11-04T10:30:09Z")}, "audit", 7);
  assert.deepEqual(e, {who: "audit", q: "Why?", a: "Because.", from: "model", t: clock("2026-11-04T10:30:05Z"), at: clock("2026-11-04T10:30:09Z"), n: 7, id: 2});
  assert.match(e.t, /^\d\d:\d\d:\d\d$/);
  const none = FC.entryOf({q: asked(2, "Why?"), a: null}, "audit", 0);
  assert.equal(none.a, "No answer was stored.");
  assert.equal(none.from, "");
  assert.equal(none.at, "");
  assert.equal(FC.entryOf({q: asked(2, "Why?"), a: answer(4, "")}, "audit", 0).a, "No answer came back.");
  assert.equal(FC.entryOf({q: asked(2, "Why?", "not a time"), a: null}, "audit", -3).t, "");
  assert.equal(FC.entryOf({q: asked(2, "Why?"), a: null}, "audit", -3).n, 0);
});

// ---- hydrate ------------------------------------------------------------------------------------------------------------------------------

test("it reads the function's session of the run and fills the list with the stored questions and answers, in place", async () => {
  const sid = freshSid();
  const api = fakeApi({agents: [row({agent: "identity", session_id: "cs_other"}), row({session_id: sid})],
    messages: [work(1), asked(2, "Why was W-3 scored low?"), answer(3, "It missed the gate.", "model"), asked(4, "And W-4?"), answer(5, "It passed.", "records")]});
  const QA = [{who: "priority", q: "kept", a: "kept", from: "records", t: "", n: 0}, {who: "audit", q: "old", a: "old", from: "records", t: "10:00:00", n: 0}];
  const other = QA[0];
  const same = QA;
  assert.equal(await FC.hydrate(QA, "audit", "r1", {...ctxOf(api), feed: {found: true, events: [1, 2, 3]}}), true);
  assert.equal(QA, same);
  assert.equal(QA[0], other);                                                    // another function's entry is the same object, in its place
  const mine = QA.filter(x => x.who === "audit");
  assert.deepEqual(mine.map(x => [x.q, x.a, x.from, x.n]), [["Why was W-3 scored low?", "It missed the gate.", "model", 3], ["And W-4?", "It passed.", "records", 3]]);
  assert.equal(QA.length, 3);                                                    // the old stored entry of audit was replaced, not kept beside them
  assert.deepEqual(api.calls.map(c => c.path), ["/api/teams/web/agents", "/api/chats/" + sid + "/messages"]);
  assert.deepEqual(api.calls[0].query, {run: "r1"});
  assert.deepEqual(api.calls[1].query, {after: 0, limit: 200});
});

test("the run is named only when the page shows one: the live run takes the team's latest", async () => {
  const api = fakeApi({agents: [row({session_id: freshSid()})]});
  await FC.hydrate([], "audit", "", ctxOf(api));
  await FC.hydrate([], "audit", undefined, ctxOf(api));
  assert.deepEqual(api.calls.filter(c => c.path.startsWith("/api/teams/")).map(c => c.query), [{}, {}]);
});

test("a question with no answer line says so, and the answer of one that came later is its own entry", async () => {
  const api = fakeApi({agents: [row({session_id: freshSid()})], messages: [asked(1, "Why?"), asked(2, "Again?"), answer(3, "Because.")]});
  const QA = [];
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  assert.deepEqual(QA.map(x => [x.q, x.a, x.from]), [["Why?", "No answer was stored.", ""], ["Again?", "Because.", "records"]]);
});

test("a question in flight stays as it is, and its stored question is not added a second time", async () => {
  const waiting = {who: "audit", q: "Why  was W-3\nscored low?", a: null, from: "", t: "10:30:05", n: 2};
  const api = fakeApi({agents: [row({session_id: freshSid()})], messages: [asked(1, "Why was W-3 scored low?"), asked(2, "Earlier?"), answer(3, "Yes.")]});
  const QA = [{who: "audit", q: "stale", a: "stale", from: "records", t: "", n: 0}, waiting];
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  assert.ok(QA.includes(waiting));
  assert.equal(waiting.a, null);                                                 // still "Thinking..." until its own answer arrives
  assert.deepEqual(QA.map(x => x.q), ["Earlier?", waiting.q]);                   // the stale one is gone, the in-flight one comes last and appears once
});

test("an entry that finished while the call was reading is not shown twice", async () => {
  const waiting = {who: "audit", q: "Why?", a: null, from: "", t: "10:30:05", n: 0};
  let release;
  const gate = new Promise(r => { release = r; });
  const api = fakeApi({agents: [row({session_id: freshSid()})], messages: [asked(1, "Why?")], hold: {path: "/api/chats/", promise: gate}});
  const QA = [waiting];
  const done = FC.hydrate(QA, "audit", "r1", ctxOf(api));
  await new Promise(r => setImmediate(r));
  waiting.a = "Because.";                                                        // J2's askFn got its answer while the call waited for the messages
  waiting.from = "records";
  release();
  assert.equal(await done, true);
  assert.deepEqual(QA, [waiting]);                                               // the stored question is the same question: one entry, with J2's own answer
});

test("on any failure the list is left exactly as it was and the answer is false", async () => {
  const QA = [{who: "audit", q: "kept", a: "kept", from: "records", t: "", n: 0}, {who: "audit", q: "waiting", a: null, from: "", t: "", n: 0}];
  const before = QA.slice();
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(fakeApi({fail: "/api/teams/"}))), false);
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(fakeApi({agents: [row({session_id: freshSid()})], fail: "/api/chats/"}))), false);
  assert.deepEqual(QA, before);
  const bad = {get: async p => (p.startsWith("/api/teams/") ? {not: "a list"} : {})};
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(bad)), false);
  const noList = {get: async p => (p.startsWith("/api/teams/") ? [row({session_id: freshSid()})] : {messages: "no"})};
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(noList)), false);
  assert.deepEqual(QA, before);
});

test("a function with no chat of its own in that run changes nothing: the validator, or an agent that did not work in the run", async () => {
  const QA = [{who: "audit", q: "from the records", a: "No record of it.", from: "records", t: "", n: 0}];
  const before = JSON.stringify(QA);
  const api = fakeApi({agents: [row({agent: "identity", session_id: "cs_i"}), row({agent: "audit", kind: "step", session_id: "cs_s"}), row({agent: "audit", session_id: ""})]});
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(api)), false);
  assert.equal(JSON.stringify(QA), before);
  const none = fakeApi();
  assert.equal(await FC.hydrate(QA, "validator", "r1", ctxOf(none)), false);
  assert.equal(await FC.hydrate(QA, "", "r1", ctxOf(none)), false);
  assert.equal(none.calls.length, 0);                                            // the validator is code: nothing is asked for it
});

test("nothing is read without a team, an api or a list", async () => {
  const api = fakeApi();
  assert.equal(await FC.hydrate([], "audit", "r1", {api, dept: ""}), false);
  assert.equal(await FC.hydrate(null, "audit", "r1", ctxOf(api)), false);
  assert.equal(await FC.hydrate([], "audit", "r1", {dept: "web"}), false);
  assert.equal(await FC.hydrate([], "audit", "r1", {api: {}, dept: "web"}), false);
  assert.equal(api.calls.length, 0);
});

test("a long session is read in pages of 200, five at most, and the next call goes on from where this one stopped", async () => {
  const sid = freshSid();
  const lines = [];
  for (let i = 1; i <= 1100; i += 1) lines.push(i === 50 ? asked(i, "Early?") : (i === 51 ? answer(i, "Yes.") : (i === 1050 ? asked(i, "Late?") : (i === 1051 ? answer(i, "No.") : work(i)))));
  const api = fakeApi({agents: [row({session_id: sid})], messages: lines});
  const QA = [];
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  const reads = api.calls.filter(c => c.path.startsWith("/api/chats/")).map(c => c.query);
  assert.deepEqual(reads.map(q => q.after), [0, 200, 400, 600, 800]);
  assert.equal(reads.every(q => q.limit === 200), true);
  assert.deepEqual(QA.map(x => x.q), ["Early?"]);                                // lines 1 to 1000 were read; the late pair waits for the next call
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  const more = api.calls.filter(c => c.path.startsWith("/api/chats/")).map(c => c.query).slice(5);
  assert.deepEqual(more.map(q => q.after), [1000]);                              // only what is new
  assert.deepEqual(QA.map(x => x.q), ["Early?", "Late?"]);
  assert.deepEqual(QA.map(x => x.a), ["Yes.", "No."]);
});

test("a later call asks only for what came after the last line, and still shows every stored question", async () => {
  const sid = freshSid();
  const messages = [work(1), asked(2, "Why?")];
  const api = fakeApi({agents: [row({session_id: sid})], messages});
  const QA = [];
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  assert.deepEqual(QA.map(x => x.a), ["No answer was stored."]);
  messages.push(answer(3, "Because.", "model"), work(4));                        // the answer lands and the agent goes on working
  await FC.hydrate(QA, "audit", "r1", ctxOf(api));
  const reads = api.calls.filter(c => c.path.startsWith("/api/chats/")).map(c => c.query);
  assert.deepEqual(reads, [{after: 0, limit: 200}, {after: 2, limit: 200}]);
  assert.deepEqual(QA.map(x => [x.q, x.a, x.from]), [["Why?", "Because.", "model"]]);
});

test("a call that started earlier and ends later does not undo a newer one", async () => {
  const sid = freshSid();
  let release;
  const gate = new Promise(r => { release = r; });
  const slow = fakeApi({agents: [row({session_id: sid})], messages: [asked(1, "Old view?"), answer(2, "Old.")], hold: {path: "/api/chats/", promise: gate}});
  const fast = fakeApi({agents: [row({session_id: sid})], messages: [asked(1, "New view?"), answer(2, "New.")]});
  const QA = [];
  const first = FC.hydrate(QA, "audit", "r1", ctxOf(slow));
  await new Promise(r => setImmediate(r));
  assert.equal(await FC.hydrate(QA, "audit", "r1", ctxOf(fast)), true);
  release();
  assert.equal(await first, false);
  assert.deepEqual(QA.map(x => x.q), ["New view?"]);
});

test("the place of every stored entry is the feed's length: from the options, else from J2's own FEED, else 0", async () => {
  const api = () => fakeApi({agents: [row({session_id: freshSid()})], messages: [asked(1, "Why?"), answer(2, "Because.")]});
  const a = [];
  await FC.hydrate(a, "audit", "r1", {...ctxOf(api()), feed: {found: true, events: [1, 2, 3, 4]}});
  assert.equal(a[0].n, 4);
  const b = [];
  await FC.hydrate(b, "audit", "r1", {...ctxOf(api()), feed: {found: false, events: [1, 2]}});
  assert.equal(b[0].n, 0);
  assert.equal(typeof globalThis.FEED, "undefined");
  const c = [];
  await FC.hydrate(c, "audit", "r1", ctxOf(api()));
  assert.equal(c[0].n, 0);
  globalThis.FEED = {who: "audit", found: true, events: [1, 2, 3, 4, 5]};       // the page script's top-level const, as another script sees it
  try {
    const d = [];
    await FC.hydrate(d, "audit", "r1", ctxOf(api()));
    assert.equal(d[0].n, 5);
  } finally {
    delete globalThis.FEED;
  }
});

test("without options it uses SutraCtx, read when it is used", async () => {
  const api = fakeApi({agents: [row({session_id: freshSid()})], messages: [asked(1, "Why?"), answer(2, "Because.")]});
  const saved = globalThis.SutraCtx;
  globalThis.SutraCtx = {api, dept: "web"};
  try {
    const QA = [];
    assert.equal(await FC.hydrate(QA, "audit", "r1"), true);
    assert.equal(QA.length, 1);
  } finally {
    if (saved === undefined) delete globalThis.SutraCtx; else globalThis.SutraCtx = saved;
  }
});

test("the page wiring: the module is a classic script with one global and exports for node", () => {
  const source = require("node:fs").readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/js/function_chat.js"), "utf8");
  assert.match(source, /root\.FunctionChat = FunctionChat/);
  assert.doesNotMatch(source, /\beval\(|new Function|document\.cookie|XMLHttpRequest|EventSource|localStorage/);
  assert.deepEqual(FC.FUNCTIONS, ["identity", "adaptation", "priority", "coordination", "audit"]);
});
