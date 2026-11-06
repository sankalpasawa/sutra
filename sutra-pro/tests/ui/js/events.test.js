"use strict";
// SutraEvents (sutra_app/ui/static/js/sutra_events.js): the 15 event names, the hello-resync rule, polling when the stream
// drops, the retry after a hard close, close(), and coalesce.
// Run with: node --test tests/ui/js/events.test.js
//
// The script is a classic browser script: its text runs in a vm context whose timers are a fake clock, so no test waits.
// EventSource is a fake the test drives (open, send, drop, die). Objects made inside the context have that context's
// prototypes, so deep comparisons go through plain().
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.resolve(__dirname, "../../../sutra_app/ui/static/js/sutra_events.js");
const CODE = fs.readFileSync(FILE, "utf8");
const NAMES = ["server.hello", "server.resync", "chat.turn", "chat.message", "chat.partial", "chart.changed", "chart.approval", "graph.updated",
  "task.updated", "atom.updated", "usage.recorded", "needs_you.changed", "connector.health", "connector.switch", "connector.mode"];

const plain = value => JSON.parse(JSON.stringify(value));

// A clock the test advances by hand. Timers run in time order, ties in creation order; an interval re-arms itself.
function makeClock() {
  let now = 0;
  let seq = 0;
  const timers = new Map();
  const add = (fn, ms, every) => { seq += 1; timers.set(seq, {id: seq, fn, at: now + ms, every}); return seq; };
  return {
    setTimeout: (fn, ms) => add(fn, ms, 0),
    setInterval: (fn, ms) => add(fn, ms, ms),
    clearTimeout: id => { timers.delete(id); },
    clearInterval: id => { timers.delete(id); },
    tick(ms) {
      const end = now + ms;
      for (;;) {
        let next = null;
        for (const t of timers.values()) if (t.at <= end && (next === null || t.at < next.at || (t.at === next.at && t.id < next.id))) next = t;
        if (next === null) break;
        now = next.at;
        if (next.every) next.at += next.every; else timers.delete(next.id);
        next.fn();
      }
      now = end;
    },
    pending: () => timers.size,
    now: () => now,
  };
}

// The EventSource of a browser, as far as the client uses it. readyState: 0 connecting, 1 open, 2 closed.
class FakeES {
  constructor(url) { this.url = url; this.readyState = 0; this.listeners = new Map(); this.closes = 0; }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(fn); }
  close() { this.closes += 1; this.readyState = 2; }
  fire(type, event) { for (const fn of this.listeners.get(type) || []) fn(event); }
  open() { this.readyState = 1; this.fire("open", {}); }
  send(type, data, raw) { this.fire(type, {type, data: raw === undefined ? JSON.stringify(data) : raw}); }
  drop() { this.readyState = 0; this.fire("error", {}); }     // the connection broke; the browser will retry by itself
  die() { this.readyState = 2; this.fire("error", {}); }      // the browser gave up on this stream
}

function sandboxWith(clock, logs, extra = {}) {
  const sandbox = vm.createContext({
    setTimeout: clock.setTimeout, setInterval: clock.setInterval, clearTimeout: clock.clearTimeout, clearInterval: clock.clearInterval,
    console: {error: (...args) => logs.push(args.map(String).join(" "))}, ...extra,
  });
  vm.runInContext(CODE, sandbox, {filename: "sutra_events.js"});
  return sandbox;
}

// Connect with a fake clock and a fake EventSource. `options` overrides what connect gets.
function start(options = {}, extra = {}) {
  const clock = makeClock();
  const logs = [];
  const made = [];
  class ES extends FakeES { constructor(url) { super(url); made.push(this); } }
  const sandbox = sandboxWith(clock, logs, extra);
  const events = [];
  const states = [];
  const handle = sandbox.SutraEvents.connect({
    onEvent: (type, data) => events.push([type, plain(data)]),
    onState: state => states.push(state),
    EventSourceCtor: ES,
    ...options,
  });
  return {clock, logs, made, sandbox, events, states, handle, es: () => made[made.length - 1], ES};
}

// ------------------------------------------------------------------------------------------------------------------
// Loading
// ------------------------------------------------------------------------------------------------------------------
test("TYPES is the 15 event names of /api/events, in order, and frozen", () => {
  const { SutraEvents } = sandboxWith(makeClock(), []);
  assert.deepEqual(plain(SutraEvents.TYPES), NAMES);
  assert.equal(SutraEvents.TYPES.length, 15);
  assert.equal(new Set(NAMES).size, 15);
  assert.ok(Object.isFrozen(SutraEvents.TYPES));
});

test("the script adds exactly one global, SutraEvents, and no top-level name J2's page might declare", () => {
  const sandbox = vm.createContext({});
  const before = new Set(Object.getOwnPropertyNames(sandbox));
  vm.runInContext(CODE, sandbox);
  assert.deepEqual(Object.getOwnPropertyNames(sandbox).filter(name => !before.has(name)), ["SutraEvents"]);
  const names = ["TYPES", "connect", "coalesce", "parse", "streamUrl", "report", "ERRORS_BEFORE_POLLING", "DEFAULT_POLL_MS", "RETRY_MS", "CLOSED",
    "SutraEvents", "root", "esc", "paint", "$", "seen", "state", "poll", "open", "close", "live"];
  vm.runInContext(names.map(name => `const ${name} = 1;`).join("\n"), sandbox);
  assert.deepEqual(Object.keys(sandbox.SutraEvents).sort(), ["TYPES", "coalesce", "connect"]);
});

test("in node the file is module.exports and sets no global", () => {
  const sandbox = vm.createContext({module: {exports: {}}});
  vm.runInContext(CODE, sandbox);
  assert.deepEqual(Object.keys(sandbox.module.exports).sort(), ["TYPES", "coalesce", "connect"]);
  assert.equal(sandbox.SutraEvents, undefined);
  const required = require(FILE);
  assert.equal(required.TYPES.length, 15);
  assert.equal(typeof required.connect, "function");
});

// ------------------------------------------------------------------------------------------------------------------
// connect: the stream, its address and its listeners
// ------------------------------------------------------------------------------------------------------------------
test("connect opens one EventSource at /api/events with a listener for each of the 15 names, open and error", () => {
  const { made } = start();
  assert.equal(made.length, 1);
  assert.equal(made[0].url, "/api/events");
  assert.deepEqual([...made[0].listeners.keys()].sort(), [...NAMES, "open", "error"].sort());
  for (const [type, fns] of made[0].listeners) assert.equal(fns.length, 1, type);
});

test("the address: url, topics and an existing query are put together, and there is never an after", () => {
  const cases = [
    [{}, "/api/events"],
    [{url: "/other/stream"}, "/other/stream"],
    [{url: ""}, "/api/events"],
    [{url: 5}, "/api/events"],
    [{topics: ["chat", "graph"]}, "/api/events?topics=chat,graph"],
    [{topics: "chat, graph"}, "/api/events?topics=chat,graph"],
    [{topics: "chat"}, "/api/events?topics=chat"],
    [{topics: ["chat", "", "  ", "graph "]}, "/api/events?topics=chat,graph"],
    [{topics: ["a b", "c&d"]}, "/api/events?topics=a%20b,c%26d"],
    [{topics: []}, "/api/events"],
    [{topics: ""}, "/api/events"],
    [{topics: undefined}, "/api/events"],
    [{topics: 5}, "/api/events"],
    [{url: "/api/events?x=1", topics: ["chat"]}, "/api/events?x=1&topics=chat"],
    [{url: "/api/events?", topics: ["chat"]}, "/api/events?topics=chat"],
    [{url: "/api/events?x=1&", topics: ["chat"]}, "/api/events?x=1&topics=chat"],
    [{url: "/s", topics: ["connector"]}, "/s?topics=connector"],
  ];
  for (const [options, expected] of cases) assert.equal(start(options).made[0].url, expected, JSON.stringify(options));
});

test("onEvent is required", () => {
  const { SutraEvents } = sandboxWith(makeClock(), []);
  for (const options of [undefined, null, {}, {onEvent: 5}, {onEvent: "x"}, {onState() {}}]) {
    assert.throws(() => SutraEvents.connect(options), { name: "TypeError", message: "SutraEvents.connect: onEvent must be a function" }, JSON.stringify(options));
  }
});

// ------------------------------------------------------------------------------------------------------------------
// Events reach onEvent; server.hello and server.resync
// ------------------------------------------------------------------------------------------------------------------
test("every one of the 15 names reaches onEvent: 13 as they are, server.resync forwarded, server.hello as server.resync after the first", () => {
  const { es, events } = start();
  NAMES.filter(name => name !== "server.hello").forEach((name, i) => es().send(name, {n: i, name}));
  assert.deepEqual(events.map(e => e[0]), NAMES.filter(name => name !== "server.hello"));
  events.forEach(([name, data], i) => assert.deepEqual(data, {n: i, name}));
  es().send("server.hello", {version: 1});            // the first one of the handle: the handshake
  assert.equal(events.length, 14);
  es().send("server.hello", {version: 2});
  assert.deepEqual(events[14], ["server.resync", {version: 2}]);
});

test("the first server.hello of a handle is ignored, the second and later act as server.resync with their own body", () => {
  const { es, events, handle } = start();
  es().send("server.hello", {version: 3, chart_version: 2, graph_version: 5});
  assert.deepEqual(events, []);
  assert.equal(handle.state(), "live", "it still proves the stream works");
  es().send("server.hello", {version: 4, chart_version: 2, graph_version: 6});
  es().send("server.hello", {version: 5});
  assert.deepEqual(events, [["server.resync", {version: 4, chart_version: 2, graph_version: 6}], ["server.resync", {version: 5}]]);
  assert.ok(events.every(e => e[0] !== "server.hello"), "server.hello never reaches onEvent under its own name");
});

test("a real server.resync is forwarded with its reason", () => {
  const { es, events } = start();
  es().send("server.hello", {});
  es().send("server.resync", {reason: "restart"});
  es().send("server.resync", {reason: "gap"});
  assert.deepEqual(events, [["server.resync", {reason: "restart"}], ["server.resync", {reason: "gap"}]]);
});

test("the ignored hello is per handle: a new connect ignores its own first hello", () => {
  const first = start();
  first.es().send("server.hello", {});
  first.es().send("server.hello", {});
  assert.equal(first.events.length, 1);
  const second = start();
  second.es().send("server.hello", {});
  assert.equal(second.events.length, 0);
});

test("a first hello that comes after an error is not ignored: events may have been missed", () => {
  for (const fail of ["drop", "die"]) {
    const { es, events } = start();
    es()[fail]();
    es().send("server.hello", {version: 9});
    assert.deepEqual(events, [["server.resync", {version: 9}]], fail);
  }
  const ctorFails = start({EventSourceCtor: class { constructor() { throw new Error("blocked"); } }});
  assert.equal(ctorFails.events.length, 0);
});

test("a hello after polling began is a resync too, even when it is the first hello", () => {
  const { es, events, clock } = start({pollFn() {}});
  es().drop(); es().drop(); es().drop();
  clock.tick(2000);
  es().send("server.hello", {});
  assert.deepEqual(events, [["server.resync", {}]]);
});

test("a body that is empty or not JSON still delivers the event, as {}", () => {
  const { es, events } = start();
  es().send("graph.updated", undefined, "not json");
  es().send("graph.updated", undefined, "");
  es().send("graph.updated", undefined, "   ");
  es().send("graph.updated", undefined, "{");
  es().fire("graph.updated", {});                    // an event with no data at all
  es().fire("graph.updated", undefined);
  es().fire("graph.updated", {data: 5});
  assert.equal(events.length, 7);
  for (const [type, data] of events) {
    assert.equal(type, "graph.updated");
    assert.deepEqual(data, {});
  }
  es().send("graph.updated", undefined, "null");
  es().send("graph.updated", [1, 2]);
  es().send("graph.updated", "text");
  assert.deepEqual(events.slice(7).map(e => e[1]), [null, [1, 2], "text"]);
});

test("a hello with a body that is not JSON is still a hello", () => {
  const { es, events } = start();
  es().send("server.hello", undefined, "oops");
  es().send("server.hello", undefined, "oops");
  assert.deepEqual(events, [["server.resync", {}]]);
});

// ------------------------------------------------------------------------------------------------------------------
// State: live, polling, offline
// ------------------------------------------------------------------------------------------------------------------
test("the handle starts offline and goes live on open; onState is called on a change only", () => {
  const { es, handle, states } = start();
  assert.equal(handle.state(), "offline");
  assert.deepEqual(states, []);
  es().open();
  assert.equal(handle.state(), "live");
  es().open();
  es().send("server.hello", {});
  es().send("graph.updated", {});
  assert.deepEqual(states, ["live"]);
});

test("state() follows the stream with no onState given", () => {
  const made = [];
  const clock = makeClock();
  const sandbox = sandboxWith(clock, []);
  class ES extends FakeES { constructor(url) { super(url); made.push(this); } }
  const handle = sandbox.SutraEvents.connect({onEvent() {}, EventSourceCtor: ES, pollFn() {}});
  assert.equal(handle.state(), "offline");
  made[0].open();
  assert.equal(handle.state(), "live");
  made[0].drop(); made[0].drop(); made[0].drop();
  assert.equal(handle.state(), "polling");
  made[0].send("server.hello", {});
  assert.equal(handle.state(), "live");
});

test("three errors in a row switch to polling; one or two do not", () => {
  const { es, handle, states, clock } = start({pollFn() {}});
  es().open();
  es().drop();
  es().drop();
  assert.equal(handle.state(), "live");
  assert.deepEqual(states, ["live"]);
  assert.equal(clock.pending(), 0, "no timer until the third error");
  es().drop();
  assert.equal(handle.state(), "polling");
  assert.deepEqual(states, ["live", "polling"]);
  assert.equal(clock.pending(), 1);
  es().drop();
  es().drop();
  assert.equal(clock.pending(), 1, "one polling timer, not one per error");
  assert.deepEqual(states, ["live", "polling"]);
});

test("pollFn runs every 2 s while polling, not before, and not on the browser's own retries", () => {
  let polls = 0;
  const { es, clock } = start({pollFn() { polls += 1; }});
  es().drop(); es().drop(); es().drop();
  clock.tick(1999);
  assert.equal(polls, 0);
  clock.tick(1);
  assert.equal(polls, 1);
  clock.tick(2000);
  assert.equal(polls, 2);
  clock.tick(10000);
  assert.equal(polls, 7);
});

test("pollMs sets the period; a value that is not a positive finite number means 2000", () => {
  for (const [pollMs, period] of [[500, 500], [1, 1], [2500.5, 2500.5], [0, 2000], [-5, 2000], [NaN, 2000], [Infinity, 2000], ["500", 2000], [null, 2000], [undefined, 2000]]) {
    let polls = 0;
    const { es, clock } = start({pollFn() { polls += 1; }, pollMs});
    es().drop(); es().drop(); es().drop();
    clock.tick(period - 1);
    assert.equal(polls, 0, String(pollMs));
    clock.tick(1);
    assert.equal(polls, 1, String(pollMs));
  }
});

test("a hello ends the polling, makes the handle live again and is delivered as server.resync", () => {
  let polls = 0;
  const { es, handle, states, events, clock } = start({pollFn() { polls += 1; }});
  es().send("server.hello", {});
  es().drop(); es().drop(); es().drop();
  clock.tick(4000);
  assert.equal(polls, 2);
  es().send("server.hello", {version: 7});
  assert.equal(handle.state(), "live");
  assert.deepEqual(states, ["live", "polling", "live"]);
  assert.deepEqual(events, [["server.resync", {version: 7}]]);
  assert.equal(clock.pending(), 0, "the polling timer is gone");
  clock.tick(10000);
  assert.equal(polls, 2);
});

test("open alone ends polling too", () => {
  let polls = 0;
  const { es, handle, clock } = start({pollFn() { polls += 1; }});
  es().drop(); es().drop(); es().drop();
  es().open();
  assert.equal(handle.state(), "live");
  clock.tick(6000);
  assert.equal(polls, 0);
});

test("errors must be consecutive: an open stream or a hello starts the count again", () => {
  for (const proof of ["open", "hello"]) {
    const { es, handle, clock } = start({pollFn() {}});
    es().open();
    es().drop(); es().drop();
    if (proof === "open") es().open(); else es().send("server.hello", {});
    es().drop(); es().drop();
    assert.equal(handle.state(), "live", proof);
    assert.equal(clock.pending(), 0, proof);
    es().drop();
    assert.equal(handle.state(), "polling", proof);
  }
});

test("after a recovery three new errors poll again", () => {
  let polls = 0;
  const { es, handle, states, clock } = start({pollFn() { polls += 1; }});
  es().drop(); es().drop(); es().drop();
  es().send("server.hello", {});
  es().drop(); es().drop(); es().drop();
  assert.equal(handle.state(), "polling");
  assert.deepEqual(states, ["polling", "live", "polling"]);
  clock.tick(2000);
  assert.equal(polls, 1);
});

test("with no pollFn three errors mean offline, and a hello brings it back", () => {
  const { es, handle, states, events, clock } = start();
  es().open();
  es().drop(); es().drop(); es().drop();
  assert.equal(handle.state(), "offline");
  assert.deepEqual(states, ["live", "offline"]);
  assert.equal(clock.pending(), 0);
  es().send("server.hello", {});
  assert.equal(handle.state(), "live");
  assert.deepEqual(events, [["server.resync", {}]]);
  const never = start();
  never.es().drop(); never.es().drop(); never.es().drop();
  assert.deepEqual(never.states, [], "offline to offline is no change");
});

test("pollFn runs the polling list of X4 until a hello arrives", async () => {
  const gets = [];
  const api = {get: path => { gets.push(path); return Promise.resolve({}); }};
  const state = {lastSeq: 4, sessions: ["cs_org", "cs_77aa10c2e9b4"], lastMessage: {cs_org: 9, cs_77aa10c2e9b4: 3}, node: "web.identity"};
  const list = () => Promise.all([
    api.get("/api/graph"), api.get("/api/chart"), api.get("/api/chart/changes?after=" + state.lastSeq), api.get("/api/needs-you"),
    api.get("/api/departments"), ...state.sessions.map(sid => api.get("/api/chats/" + sid + "/messages?after=" + state.lastMessage[sid])),
    api.get("/api/graph/nodes/" + state.node),
  ]);
  const { es, clock } = start({pollFn: list});
  es().send("server.hello", {});
  es().drop(); es().drop(); es().drop();
  assert.deepEqual(gets, []);
  clock.tick(2000);
  assert.equal(gets.length, 8);
  assert.deepEqual(gets, ["/api/graph", "/api/chart", "/api/chart/changes?after=4", "/api/needs-you", "/api/departments",
    "/api/chats/cs_org/messages?after=9", "/api/chats/cs_77aa10c2e9b4/messages?after=3", "/api/graph/nodes/web.identity"]);
  await new Promise(resolve => setImmediate(resolve));       // the list settled
  clock.tick(2000);
  assert.equal(gets.length, 16);
  await new Promise(resolve => setImmediate(resolve));
  es().send("server.hello", {});
  clock.tick(20000);
  assert.equal(gets.length, 16, "no more polling after the hello");
});

test("only one pollFn is in flight at a time: a slow server does not pile up requests", async () => {
  let calls = 0;
  let release;
  const { es, clock } = start({pollFn() { calls += 1; return new Promise(resolve => { release = resolve; }); }});
  es().drop(); es().drop(); es().drop();
  clock.tick(2000);
  clock.tick(2000);
  clock.tick(2000);
  assert.equal(calls, 1);
  release();
  await new Promise(resolve => setImmediate(resolve));
  clock.tick(2000);
  assert.equal(calls, 2);
});

test("a pollFn that throws or rejects is logged and polling goes on", async () => {
  let calls = 0;
  const { es, clock, logs } = start({pollFn() { calls += 1; if (calls === 1) throw new Error("thrown boom"); return Promise.reject(new Error("rejected boom")); }});
  es().drop(); es().drop(); es().drop();
  clock.tick(2000);
  assert.equal(calls, 1);
  clock.tick(2000);
  assert.equal(calls, 2);
  await new Promise(resolve => setImmediate(resolve));
  clock.tick(2000);
  assert.equal(calls, 3, "the rejected call no longer blocks the next one");
  assert.ok(logs.some(line => line.includes("pollFn") && line.includes("thrown boom")), logs.join("|"));
  assert.ok(logs.some(line => line.includes("pollFn") && line.includes("rejected boom")), logs.join("|"));
});

test("a pollFn that returns a plain value is fine", () => {
  let calls = 0;
  const { es, clock } = start({pollFn() { calls += 1; return 5; }});
  es().drop(); es().drop(); es().drop();
  clock.tick(6000);
  assert.equal(calls, 3);
});

// ------------------------------------------------------------------------------------------------------------------
// A stream the browser closed for good: re-created with a backoff
// ------------------------------------------------------------------------------------------------------------------
test("a soft error leaves the retry to the browser: no timer, no new stream", () => {
  const { es, made, clock } = start();
  es().open();
  es().drop();
  assert.equal(made.length, 1);
  assert.equal(clock.pending(), 0);
});

test("a hard close re-creates the stream after 1 s, on the same address, closing the old one", () => {
  const { es, made, clock } = start({topics: ["chat", "graph"]});
  es().die();
  assert.equal(made.length, 1);
  clock.tick(999);
  assert.equal(made.length, 1);
  clock.tick(1);
  assert.equal(made.length, 2);
  assert.equal(made[1].url, made[0].url);
  assert.equal(made[1].url, "/api/events?topics=chat,graph", "no after: the browser's Last-Event-ID is not ours to send");
  assert.ok(made[0].closes >= 1, "the dead one is closed");
  assert.deepEqual([...made[1].listeners.keys()].sort(), [...NAMES, "open", "error"].sort());
});

test("the wait grows 1, 2, 4, 8, 15 s and stays at 15 s", () => {
  const { es, made, clock } = start();
  const waits = [];
  for (let i = 0; i < 8; i++) {
    const before = made.length;
    es().die();
    let waited = 0;
    while (made.length === before) { clock.tick(1); waited += 1; assert.ok(waited <= 15000, "never created"); }
    waits.push(waited);
  }
  assert.deepEqual(waits, [1000, 2000, 4000, 8000, 15000, 15000, 15000, 15000]);
});

test("a stream that opens resets the wait to 1 s", () => {
  const { es, made, clock } = start();
  es().die();
  clock.tick(1000);
  es().die();
  clock.tick(2000);
  assert.equal(made.length, 3);
  es().open();
  es().die();
  clock.tick(999);
  assert.equal(made.length, 3);
  clock.tick(1);
  assert.equal(made.length, 4);
});

test("a hello also resets the wait", () => {
  const { es, made, clock } = start();
  es().die(); clock.tick(1000);
  es().die(); clock.tick(2000);
  es().send("server.hello", {});
  es().die();
  clock.tick(1000);
  assert.equal(made.length, 4);
});

test("a re-created stream's hello acts as server.resync, and polling runs while the stream is down", () => {
  let polls = 0;
  const { es, made, events, handle, clock } = start({pollFn() { polls += 1; }});
  es().send("server.hello", {});
  es().die();                    // error 1
  clock.tick(1000);              // new stream
  es().die();                    // error 2
  clock.tick(2000);              // new stream
  es().die();                    // error 3: polling starts
  assert.equal(handle.state(), "polling");
  clock.tick(4000);              // third new stream; two polls ran meanwhile
  assert.equal(made.length, 4);
  assert.equal(polls, 2);
  es().send("server.hello", {version: 11});
  assert.equal(handle.state(), "live");
  assert.deepEqual(events, [["server.resync", {version: 11}]]);
  clock.tick(10000);
  assert.equal(polls, 2);
  es().send("graph.updated", {version: 12});
  assert.deepEqual(events[1], ["graph.updated", {version: 12}]);
});

test("a dead stream whose close() throws does not stop the re-creation", () => {
  const { es, made, clock } = start();
  es().close = () => { throw new Error("already closed"); };
  es().die();
  assert.doesNotThrow(() => clock.tick(1000));
  assert.equal(made.length, 2);
});

test("when re-creating fails, the dead stream is forgotten: its late events are ignored", () => {
  let allowed = 1;
  const made = [];
  class Flaky extends FakeES { constructor(url) { if (allowed <= 0) throw new Error("blocked"); allowed -= 1; super(url); made.push(this); } }
  const { events, clock, handle } = start({EventSourceCtor: Flaky});
  made[0].die();
  clock.tick(1000);                        // the constructor throws now
  assert.equal(made.length, 1);
  made[0].send("graph.updated", {late: true});
  made[0].open();
  assert.deepEqual(events, []);
  assert.equal(handle.state(), "offline");
});

test("only one retry is waiting at a time", () => {
  const { es, made, clock } = start();
  const dead = es();
  dead.die();
  dead.die();
  assert.equal(clock.pending(), 1);
  clock.tick(1000);
  assert.equal(made.length, 2, "one new stream, not two");
});

test("events and errors of a stream that was replaced are ignored", () => {
  const { es, made, events, clock, handle } = start({pollFn() {}});
  const old = es();
  old.die();
  clock.tick(1000);
  assert.equal(made.length, 2);
  old.send("graph.updated", {stale: true});
  old.send("server.hello", {});
  old.open();
  old.die();
  old.die();
  old.die();
  assert.deepEqual(events, []);
  assert.equal(handle.state(), "offline", "the old stream's open did not make the handle live");
  assert.equal(clock.pending(), 0, "no retry, no polling from the old stream's errors");
  es().send("graph.updated", {fresh: true});
  assert.deepEqual(events, [["graph.updated", {fresh: true}]]);
});

test("an EventSource constructor that throws counts as an error, is logged, and is retried", () => {
  let tries = 0;
  const { handle, clock, logs, states } = start({
    EventSourceCtor: class { constructor() { tries += 1; throw new Error("blocked by policy"); } },
    pollFn() {},
  });
  assert.equal(tries, 1);
  assert.ok(logs.some(line => line.includes("EventSource") && line.includes("blocked by policy")));
  clock.tick(1000);
  assert.equal(tries, 2);
  clock.tick(2000);
  assert.equal(tries, 3);
  assert.equal(handle.state(), "polling", "three failures");
  assert.deepEqual(states, ["polling"]);
  clock.tick(4000);
  assert.equal(tries, 4);
  handle.close();
  assert.equal(clock.pending(), 0);
});

// ------------------------------------------------------------------------------------------------------------------
// close()
// ------------------------------------------------------------------------------------------------------------------
test("close() stops the polling timer and the retry timer, closes the stream and goes offline without a callback", () => {
  let polls = 0;
  const { es, made, handle, states, events, clock } = start({pollFn() { polls += 1; }});
  es().open();
  es().die(); clock.tick(1000);
  es().die(); clock.tick(2000);
  es().die();                    // polling, and a retry is waiting
  assert.equal(clock.pending(), 2);
  const stream = es();
  handle.close();
  assert.equal(clock.pending(), 0);
  assert.equal(handle.state(), "offline");
  assert.ok(stream.closes >= 1);
  const before = [states.length, events.length, made.length, polls];
  clock.tick(60000);
  stream.send("graph.updated", {});
  stream.open();
  stream.die();
  assert.deepEqual([states.length, events.length, made.length, polls], before);
});

test("close() is safe to call twice and before anything happened", () => {
  const { handle, es, clock } = start();
  handle.close();
  handle.close();
  assert.equal(handle.state(), "offline");
  es().send("graph.updated", {});
  es().open();
  assert.equal(handle.state(), "offline");
  assert.equal(clock.pending(), 0);
});

test("close() with a stream that throws on close does not throw", () => {
  const { handle, es } = start();
  es().close = () => { throw new Error("already closed"); };
  assert.doesNotThrow(() => handle.close());
});

test("a retry that was waiting when close() ran never fires", () => {
  const { es, made, handle, clock } = start();
  es().die();
  handle.close();
  clock.tick(30000);
  assert.equal(made.length, 1);
});

// ------------------------------------------------------------------------------------------------------------------
// No EventSource at all (X9), and which constructor is used
// ------------------------------------------------------------------------------------------------------------------
test("without an EventSource the handle polls at once; with no pollFn it is offline", () => {
  let polls = 0;
  const clock = makeClock();
  const sandbox = sandboxWith(clock, []);
  const states = [];
  const handle = sandbox.SutraEvents.connect({onEvent() {}, onState: s => states.push(s), pollFn() { polls += 1; }});
  assert.equal(handle.state(), "polling");
  assert.deepEqual(states, ["polling"]);
  clock.tick(4000);
  assert.equal(polls, 2);
  handle.close();
  assert.equal(clock.pending(), 0);
  const bare = sandboxWith(makeClock(), []).SutraEvents.connect({onEvent() {}});
  assert.equal(bare.state(), "offline");
});

test("the global EventSource is the default constructor; the EventSourceCtor option wins; a non-function option is ignored", () => {
  const madeGlobal = [];
  class Global extends FakeES { constructor(url) { super(url); madeGlobal.push(this); } }
  const clock = makeClock();
  const sandbox = sandboxWith(clock, [], {EventSource: Global});
  sandbox.SutraEvents.connect({onEvent() {}});
  assert.equal(madeGlobal.length, 1);
  sandbox.SutraEvents.connect({onEvent() {}, EventSourceCtor: "nope"});
  assert.equal(madeGlobal.length, 2);
  const madeOwn = [];
  class Own extends FakeES { constructor(url) { super(url); madeOwn.push(this); } }
  sandbox.SutraEvents.connect({onEvent() {}, EventSourceCtor: Own});
  assert.equal(madeOwn.length, 1);
  assert.equal(madeGlobal.length, 2);
});

// ------------------------------------------------------------------------------------------------------------------
// A consumer that throws never stops the stream
// ------------------------------------------------------------------------------------------------------------------
test("an onEvent that throws is logged and the next event still arrives", () => {
  const seen = [];
  const { es, logs } = start({onEvent(type) { seen.push(type); if (type === "chat.turn") throw new Error("handler bug"); }});
  es().send("chat.turn", {});
  es().send("graph.updated", {});
  assert.deepEqual(seen, ["chat.turn", "graph.updated"]);
  assert.ok(logs.some(line => line.includes("onEvent") && line.includes("handler bug")));
});

test("an onEvent that throws on a resync does not break the hello bookkeeping", () => {
  const seen = [];
  const { es, handle } = start({onEvent(type) { seen.push(type); throw new Error("always"); }});
  es().send("server.hello", {});
  es().send("server.hello", {});
  es().send("server.hello", {});
  assert.deepEqual(seen, ["server.resync", "server.resync"]);
  assert.equal(handle.state(), "live");
});

test("an onState that throws is logged and the stream goes on", () => {
  const { es, handle, logs, events } = start({onState() { throw new Error("chip bug"); }});
  es().open();
  assert.equal(handle.state(), "live");
  es().send("chat.turn", {});
  assert.equal(events.length, 1);
  assert.ok(logs.some(line => line.includes("onState") && line.includes("chip bug")));
});

test("a console that is missing, null or without error() is not a problem", () => {
  for (const console of [undefined, null, {}, {error: 5}]) {      // (a new vm context has V8's own console unless one is given)
    const clock = makeClock();
    const made = [];
    class ES extends FakeES { constructor(url) { super(url); made.push(this); } }
    const sandbox = vm.createContext({setTimeout: clock.setTimeout, setInterval: clock.setInterval, clearTimeout: clock.clearTimeout, clearInterval: clock.clearInterval, console});
    vm.runInContext(CODE, sandbox);
    assert.equal(vm.runInContext("typeof console", sandbox), console === undefined ? "undefined" : typeof console);
    sandbox.SutraEvents.connect({onEvent() { throw new Error("x"); }, EventSourceCtor: ES});
    assert.doesNotThrow(() => made[0].send("chat.turn", {}), String(console));
  }
});

// ------------------------------------------------------------------------------------------------------------------
// A callback that closes the handle: nothing more is called, and no timer is left behind
// ------------------------------------------------------------------------------------------------------------------
test("closing inside onState('polling') leaves no polling timer, no retry timer and no new stream", () => {
  const box = {polls: 0};
  const s = start({pollFn() { box.polls += 1; }, onState: state => { if (state === "polling") box.handle.close(); }});
  box.handle = s.handle;
  s.es().die(); s.clock.tick(1000);        // error 1, a new stream
  s.es().die(); s.clock.tick(2000);        // error 2, a new stream
  s.es().die();                            // error 3: polling, and the callback closes the handle
  assert.equal(s.clock.pending(), 0);
  s.clock.tick(60000);
  assert.equal(s.made.length, 3);
  assert.equal(box.polls, 0);
  assert.equal(s.handle.state(), "offline");
});

test("closing inside onState('live') on a later hello delivers no resync", () => {
  const box = {};
  const s = start({pollFn() {}, onState: state => { if (state === "live" && box.closeOnLive) box.handle.close(); }});
  box.handle = s.handle;
  s.es().send("server.hello", {});
  s.es().drop(); s.es().drop(); s.es().drop();
  assert.equal(s.handle.state(), "polling");
  box.closeOnLive = true;
  s.es().send("server.hello", {});          // live -> the callback closes -> the resync that would follow is not delivered
  assert.deepEqual(s.events, []);
  assert.equal(s.handle.state(), "offline");
  assert.equal(s.clock.pending(), 0);
});

test("closing inside onEvent: the next events of the same stream are not delivered", () => {
  const box = {seen: []};
  const s = start({onEvent: type => { box.seen.push(type); box.handle.close(); }});
  box.handle = s.handle;
  s.es().send("chat.turn", {});
  s.es().send("graph.updated", {});
  assert.deepEqual(box.seen, ["chat.turn"]);
});

test("closing inside pollFn stops the polling for good", () => {
  const box = {polls: 0};
  const s = start({pollFn() { box.polls += 1; box.handle.close(); }});
  box.handle = s.handle;
  s.es().drop(); s.es().drop(); s.es().drop();
  s.clock.tick(2000);
  assert.equal(box.polls, 1);
  assert.equal(s.clock.pending(), 0);
  s.clock.tick(20000);
  assert.equal(box.polls, 1);
});

// ------------------------------------------------------------------------------------------------------------------
// coalesce
// ------------------------------------------------------------------------------------------------------------------
test("coalesce merges a burst into one call at the end of the window, with the last call's arguments", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  const seen = [];
  const refetch = SutraEvents.coalesce((...args) => seen.push(args), 150);
  refetch("a", 1); refetch("b", 2); refetch("c", 3);
  assert.deepEqual(seen, []);
  clock.tick(149);
  assert.deepEqual(seen, []);
  clock.tick(1);
  assert.deepEqual(seen, [["c", 3]]);
  clock.tick(5000);
  assert.equal(seen.length, 1);
});

test("the window is counted from the first call, and the next call after it starts a new window", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  let runs = 0;
  const refetch = SutraEvents.coalesce(() => { runs += 1; }, 150);
  refetch();
  clock.tick(100); refetch();
  clock.tick(49); refetch();
  assert.equal(runs, 0);
  clock.tick(1);
  assert.equal(runs, 1, "fired 150 ms after the first call, not after the last");
  clock.tick(1); refetch();
  clock.tick(149);
  assert.equal(runs, 1);
  clock.tick(1);
  assert.equal(runs, 2);
});

test("a call with no arguments runs fn with none; this is the last call's", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  const seen = [];
  const owner = {run: SutraEvents.coalesce(function (...args) { seen.push([this, args]); }, 10)};
  owner.run(1);
  owner.run();
  clock.tick(10);
  assert.equal(seen.length, 1);
  assert.equal(seen[0][0], owner);
  assert.deepEqual(plain(seen[0][1]), []);
});

test("cancel() drops a pending run, is harmless when nothing is pending, and the function works again afterwards", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  let runs = 0;
  const refetch = SutraEvents.coalesce(() => { runs += 1; }, 150);
  refetch.cancel();
  refetch();
  refetch.cancel();
  assert.equal(clock.pending(), 0);
  clock.tick(1000);
  assert.equal(runs, 0);
  refetch();
  clock.tick(150);
  assert.equal(runs, 1);
  assert.equal(typeof refetch.cancel, "function");
});

test("a zero, negative or missing window still merges calls made in the same turn", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  for (const ms of [0, -5, NaN, undefined, null, "150", Infinity - Infinity]) {
    let runs = 0;
    const refetch = SutraEvents.coalesce(() => { runs += 1; }, ms);
    refetch(); refetch(); refetch();
    assert.equal(runs, 0, String(ms));
    clock.tick(0);
    assert.equal(runs, 1, String(ms));
  }
});

test("a fn that throws does not stop later calls from being scheduled", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  let runs = 0;
  const refetch = SutraEvents.coalesce(() => { runs += 1; if (runs === 1) throw new Error("fn bug"); }, 50);
  refetch();
  assert.throws(() => clock.tick(50), /fn bug/);
  refetch();
  clock.tick(50);
  assert.equal(runs, 2);
});

test("a stream of events every 7 ms for a second becomes about 6 runs at 150 ms", () => {
  const clock = makeClock();
  const { SutraEvents } = sandboxWith(clock, []);
  let runs = 0;
  const refetch = SutraEvents.coalesce(() => { runs += 1; }, 150);
  for (let t = 0; t < 1000; t += 7) { refetch(); clock.tick(7); }
  clock.tick(150);
  assert.ok(runs >= 6 && runs <= 7, "runs: " + runs);
});

// ------------------------------------------------------------------------------------------------------------------
// How a page wires it: connector.* events and one /api/health refetch (Home, UI-7)
// ------------------------------------------------------------------------------------------------------------------
test("on Home a burst of connector.* events triggers one /api/health refetch, and no other event does", () => {
  const gets = [];
  const api = {get: path => { gets.push(path); return Promise.resolve({}); }};
  const { sandbox, clock } = start();
  const refetchHealth = sandbox.SutraEvents.coalesce(() => api.get("/api/health"), 150);
  const streams = [];
  class ES extends FakeES { constructor(url) { super(url); streams.push(this); } }
  const home = sandbox.SutraEvents.connect({
    topics: ["connector", "chat"],
    onEvent: type => { if (type.startsWith("connector.")) refetchHealth(); },
    EventSourceCtor: ES,
  });
  const stream = streams[0];
  stream.send("connector.health", {provider: "claude", state: "ok"});
  stream.send("connector.switch", {from: "claude", to: "codex"});
  stream.send("connector.mode", {mode: "stub"});
  stream.send("chat.message", {});
  stream.send("graph.updated", {});
  assert.deepEqual(gets, []);
  clock.tick(150);
  assert.deepEqual(gets, ["/api/health"]);
  stream.send("connector.mode", {mode: "live"});
  clock.tick(150);
  assert.deepEqual(gets, ["/api/health", "/api/health"]);
  stream.send("graph.updated", {});
  clock.tick(1000);
  assert.equal(gets.length, 2);
  assert.equal(stream.url, "/api/events?topics=connector,chat");
  refetchHealth.cancel();
  home.close();
});

test("a resync refetches everything the page shows, once, however many arrive", () => {
  const refetched = [];
  const { sandbox, clock } = start({onEvent() {}});
  const everything = sandbox.SutraEvents.coalesce(() => refetched.push("all"), 150);
  const stream = [];
  class ES extends FakeES { constructor(url) { super(url); stream.push(this); } }
  const handle = sandbox.SutraEvents.connect({onEvent: type => { if (type === "server.resync") everything(); }, EventSourceCtor: ES});
  stream[0].send("server.hello", {});
  stream[0].send("server.hello", {version: 2});                   // a reconnect
  stream[0].send("server.resync", {reason: "restart"});           // and the real resync that follows it
  stream[0].send("server.resync", {reason: "gap"});
  assert.deepEqual(refetched, []);
  clock.tick(150);
  assert.deepEqual(refetched, ["all"]);
  handle.close();
});
