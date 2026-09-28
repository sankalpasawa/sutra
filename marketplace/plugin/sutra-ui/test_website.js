#!/usr/bin/env node
/* test_website.js -- the website department on the department screen
   (static/js/22-website.js; the first build, holding/website/native/system/
   first-build.html).

   Named claims:
     W1  no global of 22-website.js is a global of any other script (it once
         took S.ws and ws*() from 13-workspace.js; this is the test that would
         have caught it)
     W2  a department with no website record paints exactly as before
     W3  a website department's list: Map, System status, Motor, the five
         functions, its engines with a state word, its filed work with dots
     W4  before a goal the Map asks for one; Start posts it
     W5  with a goal the Map shows the systems, the line, System status with
         Stamp, Refuse and Stop, Ask, Health, Recent
     W6  Stamp, Stop, Ask and Put back each post the one route they name
     W7  a click on one of 20-dept.js's rows hands the viewer back, and the
         function card carries this department's own state under it
     W8  Preview shows the thing itself in a frame that can run nothing
     W9  the screen prints no count and no path at rest
     W10 the Edit menu carries the command, and panel.html loads the script
         before the tail
     W11 the stylesheet block is tokens only and every class the script emits
         has a rule or is one of 20-dept.js's own
     W12 a department on the engine runtime gains the Board in its list; one
         that is not on it gains nothing and reads neither steps nor board
     W13 an engine opens on its steps: each with its rung, its check, what its
         rows say and Hold; the words carry no step id, rung code or count
     W14 Hold posts the one route it names, and the card that is open stays open
     W15 the Board is a list of threads and the open one as a chat: who spoke
         to whom and with which act; the ideas parked; an empty board is one
         quiet line (amended 2026-09-28: the Board as chats)
     W16 the Map of a runtime department has one way in, shows what the
         department said back, and a function's card carries its steps
     W17 a runtime department has one button, Start when it is off and Stop
         when it is on, at the top of its Map; each posts the one route
     W18 every engine's card says how it starts, on what and unless what, and
         Coordination's card carries its table: who goes first, who may post
     W19 on the screen the five are functions; the word "internal system" is
         the inside word and is printed nowhere
     W25 the chat is the one point of entry: a runtime department opens on it;
         inside a department the same chat scoped, the box carries the
         department as a chip; the words go to Root; a stamp goes where the ask
         lives; on Root the whole chat, the department a chip on the turn
     W26 each function's card has its own Settings tab: its template, its own
         limit, its ladder numbers, how it starts; Identity's carries where the
         site is served from; a department of the first build has none

   Harness: test_dept.js's fresh(), with 22-website.js loaded after 20-dept.js
   (panel.html's order). Run: node test_website.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
const orgSrc = read("03-org.js"), o2Src = read("19-org2.js"), dpSrc = read("20-dept.js"), wbSrc = read("22-website.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
const railSrc = orgSrc.slice(orgSrc.indexOf(RB), orgSrc.indexOf(RE));

let failed = 0, ran = 0;
const pending = [];
function test(name, fn){
  ran++;
  try {
    const r = fn();
    if (r && typeof r.then === "function") pending.push(r.then(() => console.log("ok   " + name), e => { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e)); }));
    else console.log("ok   " + name);
  } catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e)); }
}
const sleep = () => new Promise(r => setTimeout(r, 0));

const ROOT = { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1, node_kind: "root" };
const ORG  = { ref: "r1", path: "D1", name: "City Care Hospital", parent_ref: "r0", status: "active", ts_minted_ms: 2, node_kind: "organisation" };
const RT   = { ref: "r2", path: "D1.D1", name: "Root", parent_ref: "r1", status: "active", ts_minted_ms: 3, node_kind: "department" };
const WEB  = { ref: "r3", path: "D1.D1.D1", name: "Website", parent_ref: "r2", status: "active", ts_minted_ms: 4, node_kind: "department" };
const OTHER = { ref: "r4", path: "D1.D1.D2", name: "Billing", parent_ref: "r2", status: "active", ts_minted_ms: 5, node_kind: "department" };
const TREE = [ROOT, ORG, RT, WEB, OTHER];

const ENGS = [["Plan", "Brief", "Site plan", "model"], ["Write", "Site plan", "Pages", "model"],
              ["Check", "Pages", "Build", "code"], ["Publish", "Build", "Live site", "code"]];
function mapOf(o){
  o = o || {};
  const vers = o.versions || { "Brief": 1, "Site plan": 2, "Pages": 5, "Build": 5, "Live site": 0 };
  return {
    ref: "r3", name: "City Care Hospital Website", goal: "A live website for City Care Hospital", done: "Every page checked and live",
    rules: [], owner: "Sankalp", control: "granted", stopped: !!o.stopped, has_goal: o.has_goal !== false, live: !!o.live,
    runtime: o.runtime || 1,
    systems: ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(n => ({ name: n, state: /Adaptation|Audit/.test(n) && o.runtime !== 2 ? "paused" : "running", last: null })),
    engines: ENGS.map(e => ({ name: e[0], reads: e[1], writes: e[2], runs_as: e[3], slot: "after a new " + e[1],
      state: e[0] === "Publish" && o.ask ? "Waits" : "Idle", envelope: { calls: 30, usd: 6, used_calls: 3, used_usd: 0.4 }, window_min: 15,
      last: { status: "ok", at: "2026-09-27T11:02:00+05:30", what: "" } })),
    artifacts: Object.keys(vers).map(n => ({ name: n, slug: n.toLowerCase().replace(/ /g, "-"), versions: vers[n], latest: null })),
    status: { asks: o.ask ? [{ id: "a-1", kind: "publish", engine: "Publish", text: "Publish: go live for the first time", status: "pending", created: "2026-09-27T11:08:00+05:30" }] : [],
              escalated: [], waits: o.ask ? [{ what: "Publish", why: "for the stamp", since: "2026-09-27T11:08:00+05:30" }] : [], running: [], stopped: !!o.stopped, next: "nothing due" },
    health: { motor: { last_tick: "2026-09-27T11:09:00+05:30", age_s: 2 },
              checks: ["Motor", "Slots", "Versions", "Stuck", "Awake", "Budget", "Done"].map(n => ({ name: n, state: "ok", line: "" })),
              never: [{ name: "A slot run twice", ok: true }],
              timeline: [{ engine: "Plan", system: false, status: "ok", started: "2026-09-27T10:55:00+05:30", ended: "2026-09-27T10:56:00+05:30", slot: "Plan@brief.v1", what: "" }] },
    recent: [{ engine: "Write", system: false, status: "ok", at: "2026-09-27T11:02:00+05:30", what: "Pages from Site plan, check passed" }],
    requests: [], templates: {},
  };
}
/* What the engine runtime's two reads answer (engine_runtime.py: steps_view, board_view). */
const AT = "2026-09-28T10:02:00+05:30";
function stepOf(o){
  return Object.assign({ nature: "transform", mode: "slot", under: null, rung: "C2", rung_name: "Code", form: null, born: "C2", ceiling: "C2",
    soft: false, held: false, pending: null, trial: null, each: false, side_by_side: 1, ran: true,
    last: { at: AT, status: "ok", rung: "C2", miss: false, by: "code", item: null, ok: true, notes: ["every page of the plan is listed"] },
    evidence: { runs: 5, differing: 0, shape_drift: 0, pass: 1, marked: 0, misses: 0, usd: 0 },
    history: [{ at: AT, from: null, to: "C2", by: "born", evidence: null }] }, o);
}
function stepsOf(name, o){
  o = o || {};
  const numbers = { runs: 40, differing: 1, trial: 20, misses: 3 };
  if (name === "Write") return { name, kind: "work", description: "Writes every page the plan names", skills: ["Writing"], reads: "Site plan", writes: "Pages",
    start: { on: ["a new Site plan"], unless: [{ by: "Identity", name: "Say whether it may start" }, { by: "Priority", name: "Keep it inside its envelope" },
                                                { by: "Coordination", name: "Stop a chain at its limit" }] },
    hears: [], numbers, steps: [
      stepOf({ id: "write.list", name: "List the pages", check: "list_has_pages" }),
      stepOf({ id: "write.page", name: "Write a page", nature: "make", rung: o.rung || "C0", rung_name: o.rung_name || "Improvised call", born: "C0", ceiling: "C1",
               soft: true, each: true, side_by_side: 4, check: "page_has_body", held: !!o.held, trial: o.trial || null, pending: o.pending || null,
               last: { at: AT, status: "ok", rung: "C0", miss: false, by: "model", item: "careers", ok: true, notes: ["the page has a body"] },
               evidence: { runs: 10, differing: 0, shape_drift: 0, pass: 0.9, marked: 0, misses: 0, usd: 0.01 },
               history: [{ at: AT, from: null, to: "C0", by: "born", evidence: null }].concat(o.moved ? [{ at: AT, from: "C0", to: "C1", by: "the owner's stamp", evidence: {} }] : []) }),
      stepOf({ id: "write.file", name: "Put the pages together", check: "filed_has_files", ran: false, last: null, evidence: null })] };
  const table = name !== "Coordination" ? undefined : { first: ["A post waiting for its reader", "The line, in its order", "A function woken by new work"],
    line: ["Plan", "Write", "Check", "Publish"], may_post: [{ from: "Audit", act: "inform", to: ["Identity"] }, { from: "Owner", act: "request", to: ["Identity"] }] };
  const limits = name !== "Priority" ? undefined : ENGS.map(e => ({ engine: e[0], calls: 240, usd: 6, used_calls: 3, used_usd: 0.4 }))
    .concat(["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(s => ({ engine: s, calls: 30, usd: 6, used_calls: 0, used_usd: 0 })));
  return { name, kind: "function", description: name === "Priority" ? "grants each engine its budget" : "", skills: [], reads: null, writes: null, numbers, table, limits,
    start: { on: ["a post addressed to it"], unless: [] },
    hears: (table ? ["What engines share"] : []).concat(["Take a request"]), steps: [
    stepOf({ id: name.toLowerCase() + ".gate", name: "Say whether it may start", nature: "decide", mode: "gate", check: "gate_answer_is_known" }),
    stepOf({ id: name.toLowerCase() + ".pick", name: "Say who goes first, when several are ready", nature: "decide", mode: "rule", under: table ? "What engines share" : "Nowhere", check: "names_who_goes_first" }),
    stepOf({ id: name.toLowerCase() + ".read", name: "Read the request", under: "Take a request", check: "brief_is_text" })] };
}
const BOARD = { any: true,
  ideas: [{ id: "i-1", words: "what about a patient portal", reflected: "A place where patients sign in", question: "Who signs in first?",
            shapes: ["A page that links out", "A sign-in of its own"], state: "parked", at: AT }],
  threads: [
    { id: "x-2", topic: "rule", protocol: "request", state: "input-required", decider: "Owner", opened: AT, closed: null, outcome: null,
      bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 0, default: "failure", posts: [
        { n: 3, src: "Identity", dst: ["Owner"], msg_type: "request", at: AT, word: "rule", line: "A rule, as understood: every page names a phone line" }] },
    { id: "x-1", topic: "request", protocol: "request", state: "completed", decider: "Identity", opened: AT, closed: AT, outcome: { by: "inform" },
      bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 0, default: "failure", posts: [
        { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, word: "request", line: "Which page lists the doctors?" },
        { n: 2, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, word: "answer", line: "The Doctors page lists them" }] }] };
/* What the chat read answers (engine_runtime.py: chat_view): on Root the whole
   chat, inside a department the same chat scoped to it. */
const DEPT = "City Care Hospital Website";
const ROOT_CHAT = { root: "r3", about: null, departments: [{ ref: "r5", name: DEPT, stopped: false }], turns: [
    { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, thread: "x-1", word: "front", line: "Start a website department for City Care Hospital", dept: null, name: null },
    { n: 2, src: "Identity", dst: ["Owner"], msg_type: "request", at: AT, thread: "x-1", word: "setup", line: "Set up a department: City Care Hospital Website", dept: null, name: null },
    { n: 3, src: "Owner", dst: ["Identity"], msg_type: "accept-proposal", at: AT, thread: "x-1", word: "setup", line: "", dept: null, name: null },
    { n: 5, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, thread: "x-4", word: "front", line: "Which page lists the doctors?", dept: "r5", name: DEPT },
    { n: 6, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: "x-4", word: "request", line: "handed to City Care Hospital Website", dept: "r5", name: DEPT },
    { n: 7, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "answer", line: "The Doctors page lists them", dept: "r5", name: DEPT }],
  asks: [{ id: "a-1", kind: "publish", engine: "Publish", text: "Publish: go live for the first time", status: "pending", created: AT, ref: "r5", dept: DEPT }] };
const CHAT = { root: "r2", about: "r3", departments: [{ ref: "r3", name: DEPT, stopped: false }],
  turns: ROOT_CHAT.turns.filter(t => t.dept).map(t => Object.assign({}, t, { dept: "r3" })),
  asks: [Object.assign({}, ROOT_CHAT.asks[0], { ref: "r3" })] };

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], render: 0 };
  const map = opts.map === undefined ? mapOf() : opts.map;
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Math, encodeURIComponent, Promise, setTimeout, clearTimeout, isNaN,
    setInterval: () => 1, clearInterval: () => {},
    apiGet: (p) => {
      calls.apiGet.push(p);
      if (p === "/api/native/depts") return Promise.resolve({ depts: opts.none ? [] : [{ ref: "r3", name: "Website", stopped: false }] });
      if (/\/api\/native\/r3\/map$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(map)));
      if (/\/api\/native\/r3\/steps\//.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(stepsOf(decodeURIComponent(p.split("/steps/")[1]), opts.steps))));
      if (/\/api\/native\/r3\/board$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.board || BOARD)));
      if (/\/api\/native\/r3\/chat$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.chat || CHAT)));
      if (/\/api\/native\/r3\/engine\//.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(Object.assign({ runs: [] }, map.engines[1]))));
      if (/\/artifact\//.test(p)) return Promise.resolve({ name: "Live site", slug: "live-site",
        template: { id: "artifact/live-site", name: "Live site", kind: "site", files: ["index.html", "*.html"], checks: ["has_index_html"],
                    written_by: ["Publish"], counts_after: "stamp", put_back: true, operations: ["Adaptation", "Audit"] }, versions: [
        { v: 2, at: "2026-09-27T11:20:00+05:30", made_from: [{ art: "Build", v: 6 }], run: "r-2", check: { ok: true, notes: ["live"] }, note: "" },
        { v: 1, at: "2026-09-27T11:10:00+05:30", made_from: [{ art: "Build", v: 5 }], run: "r-1", check: { ok: true, notes: ["live"] }, note: "" }] });
      if (/^\/api\/dept\//.test(p)) return Promise.resolve({});   /* 20-dept.js's own reads: an empty record */
      return new Promise(() => {});
    },
    apiPost: (p, body) => { calls.apiPost.push({ p, body }); return Promise.resolve({ ref: "r3", org: "r1", root: "r2" }); },
    window: {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { departments: () => "" }, TITLES: { departments: ["Departments", ""] },
    DOMAINS: TREE, CHARTERS: [], PLACEMENTS: [], INDEX: [], META: {},
    SETTINGS: { flags: { org2: true } },
    ICON: { know: "<path d='k'/>", dept: "<path d='d'/>", edit: "<path d='e'/>", plc: "<path d='p'/>" },
    st: (d) => d.status || "active",
    S: { screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } },
    render: () => { calls.render++; },
    loadOrg: () => Promise.resolve(), simulate: () => ({ pending: true }),
    sbPageFromPath: () => null, mdHtml: (t) => "<p>" + t + "</p>",
    decideProposal: () => Promise.resolve({}), loadProposals: () => {},
    document: {
      listeners: {}, activeElement: null, body: { appendChild(){} },
      addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); },
      querySelector(){ return null; }, querySelectorAll(){ return []; }, getElementById(){ return null; },
      createElement(){ return { id: "", innerHTML: "" }; },
    },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(o2Src, ctx);
  vm.runInContext(dpSrc, ctx);
  vm.runInContext(wbSrc, ctx);
  return ctx;
}
function click(c, ds, inside){
  let prevented = false;
  const el = { dataset: ds, closest(sel){
    const keys = Object.keys(ds).map(k => "[data-" + k.toLowerCase() + "]");
    if (sel === ".dp" || sel === ".wb") return inside === false ? null : el;
    return sel.split(",").some(s => keys.indexOf(s.trim()) >= 0) ? el : null;
  } };
  const ev = { target: el, preventDefault(){ prevented = true; }, stopPropagation(){} };
  (c.document.listeners.click || []).forEach(fn => fn(ev));
  return prevented;
}
async function opened(opts){
  const c = fresh(opts);
  vm.runInContext("dpS().sel = 'r3'; dpS().tab['r3'] = 'now';", c);
  c.wbList(WEB);
  await sleep(); await sleep();
  c.wbList(WEB); c.wbViewer(WEB);
  await sleep(); await sleep();
  return c;
}
const list = c => { const l = c.wbList(WEB); return l.top + l.engines + l.filed; };
const view = c => c.wbViewer(WEB);

/* ── W1 ─────────────────────────────────────────────────────────────────── */
test("W1: no global of 22-website.js is a global of any other script", () => {
  const mine = new Set();
  let m;
  const re = /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^const\s+([A-Za-z_$][\w$]*)/gm;
  while ((m = re.exec(wbSrc))) mine.add(m[1] || m[2]);
  assert.ok(mine.size > 30, "parsed " + mine.size + " globals");
  [...mine].forEach(n => assert.ok(/^(wb[A-Z]|WB_)/.test(n), n + " is not prefixed wb / WB_"));
  fs.readdirSync(JS).filter(f => /\.js$/.test(f) && f !== "22-website.js").forEach(f => {
    const src = read(f);
    assert.ok(!/\bS\.wb\b/.test(src), f + " reads S.wb");
    const theirs = /^(?:async\s+)?function\s+(wb[A-Z]\w*)|^const\s+(WB_\w+)/gm;
    assert.ok(!theirs.test(src), f + " declares a wb global");
  });
  assert.ok(!/\bS\.ws\b|\bws[A-Z]\w*\(/.test(wbSrc), "22-website.js still touches the Workspace's names");
});

/* ── W2 ─────────────────────────────────────────────────────────────────── */
test("W2: a department with no website record paints exactly as before", async () => {
  const c = fresh({ none: true });
  c.wbList(OTHER);
  await sleep(); await sleep();
  assert.strictEqual(c.wbList(OTHER), null);
  assert.strictEqual(c.wbViewer(OTHER), null);
  assert.strictEqual(c.wbTileMark("r4"), "");
  const html = c.dpListHtml(OTHER, {}, null, null);
  assert.ok(/data-dptab="now"/.test(html) && !/data-wbtab/.test(html));
  assert.ok(/^<div class="o2viewer dpviewer dp"/.test(c.dpViewerHtml(OTHER, {}, null, null)));
});

/* ── W3 ─────────────────────────────────────────────────────────────────── */
test("W3: the list carries Map, System status, Motor, the engines and the filed work", async () => {
  const c = await opened();
  const html = c.dpListHtml(WEB, {}, null, null);
  ["Map", "System status", "Motor"].forEach(n => assert.ok(html.indexOf("<span>" + n + "</span>") >= 0, n));
  assert.ok(!/data-dptab="now"/.test(html), "Now is replaced by System status");
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(f => assert.ok(html.indexOf('data-dptab="' + f + '"') >= 0, f));
  ENGS.forEach(e => assert.ok(html.indexOf('data-wbengine="' + e[0] + '"') >= 0, e[0]));
  assert.ok(/data-wbart="pages"[^>]*><span>Pages<\/span><span class="dpdots">/.test(html), "Pages carries version dots");
  assert.ok(!/data-wbart="live-site"/.test(html), "nothing filed is not listed");
  assert.ok(/<span>Map<\/span>/.test(html) && /o2li dpli on" data-wbtab="map"/.test(html), "Map opens without a click");
});

/* ── W4 ─────────────────────────────────────────────────────────────────── */
test("W4: before a goal the Map asks for one, and Start posts it", async () => {
  const c = await opened({ map: mapOf({ has_goal: false, versions: { "Brief": 0, "Site plan": 0, "Pages": 0, "Build": 0, "Live site": 0 } }) });
  const html = view(c);
  assert.ok(/<h3>Goal<\/h3>/.test(html) && /data-wbgoal="goal"/.test(html) && />Start</.test(html));
  assert.ok(!/<h3>System status<\/h3>/.test(html));
  assert.ok(/<textarea id="wbd-goal"/.test(html), "the box has an id, so render() keeps its focus and words");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:goal" }, value: "A website for City Care Hospital" } }));
  assert.ok(click(c, { wbgoal: "goal" }));
  await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0])), { p: "/api/native/r3/goal", body: { text: "A website for City Care Hospital" } });
});

/* ── W5 ─────────────────────────────────────────────────────────────────── */
test("W5: with a goal the Map shows the department, System status, Ask, Health and Recent", async () => {
  const c = await opened({ map: mapOf({ ask: true }) });
  const html = view(c);
  ["The department", "System status", "Ask", "Health", "Recent"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].forEach(s => assert.ok(html.indexOf('data-wbfn="' + s.toLowerCase() + '"') >= 0, s));
  assert.strictEqual((html.match(/class="wbflow"/g) || []).length, 2, "two engines to a row");
  assert.ok(/data-wbdecide="a-1" data-wbok="1">Stamp</.test(html) && /data-wbdecide="a-1" data-wbok="0">Refuse</.test(html));
  assert.ok(/data-wbstop="1">Stop</.test(html));
  assert.ok(/data-wbmotor="1"/.test(html), "the motor's dot is on the map");
  const stopped = await opened({ map: mapOf({ stopped: true }) });
  assert.ok(/data-wbresume="1">Resume</.test(view(stopped)));
});

/* ── W6 ─────────────────────────────────────────────────────────────────── */
test("W6: Stamp, Stop, Ask and Put back each post the one route they name", async () => {
  const c = await opened({ map: mapOf({ ask: true }) });
  click(c, { wbdecide: "a-1", wbok: "1" }); await sleep(); await sleep();
  click(c, { wbstop: "1" }); await sleep(); await sleep();
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Add a Careers page" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  click(c, { wbputback: "live-site", wbv: "1" }); await sleep(); await sleep();
  const posts = JSON.parse(JSON.stringify(c.calls.apiPost));
  assert.deepStrictEqual(posts, [
    { p: "/api/native/r3/asks/a-1", body: { approve: true } },
    { p: "/api/native/r3/stop", body: {} },
    { p: "/api/native/r3/ask", body: { text: "Add a Careers page" } },
    { p: "/api/native/r3/putback", body: { slug: "live-site", v: 1 } }]);
});

/* ── W7 ─────────────────────────────────────────────────────────────────── */
test("W7: a click on one of 20-dept.js's rows hands the viewer back, and its card carries this department's state first", async () => {
  const c = await opened();
  const card = async tab => { click(c, { dptab: tab }); c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); return c.dpViewerHtml(WEB, {}, null, null); };
  let html = await card("priority");
  assert.strictEqual(vm.runInContext("S.wb.tab['r3']", c), "");
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority");
  assert.strictEqual(c.wbViewer(WEB), null, "20-dept.js draws its own card");
  assert.ok(/<h3>Envelopes<\/h3>/.test(html) && /<h3>Queue<\/h3>/.test(html), html.slice(0, 400));
  html = await card("coordination");
  ["Timetable", "Hand-offs", "Locks"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  html = await card("identity");
  ["Control", "Autonomy windows", "Stamped by rule"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  html = await card("audit");
  assert.ok(/Paused/.test(html));
  assert.strictEqual(c.wbFnOwn("r4", "priority"), "", "another department's card gains nothing");
  click(c, { wbtab: "motor" });
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "now", "no function row stays lit");
  const motor = view(c);
  ["Motor", "It only reads", "What it does each tick", "Checks", "Timeline", "Never happens"].forEach(h => assert.ok(motor.indexOf("<h3>" + h + "</h3>") >= 0, h));
  const words = motor.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
  assert.ok(!/\d/.test(words), "a number at rest on the Motor: " + (words.match(/.{0,30}\d.{0,30}/) || [""])[0]);
});

/* ── W8 ─────────────────────────────────────────────────────────────────── */
test("W8: Preview shows the thing itself in a frame that can run nothing", async () => {
  const c = await opened({ map: mapOf({ live: true, versions: { "Brief": 1, "Site plan": 1, "Pages": 1, "Build": 1, "Live site": 2 } }) });
  click(c, { wbart: "live-site", wbpane: "preview" });
  view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<iframe class="wbframe" sandbox="" src="\/api\/native\/r3\/site\/index\.html"/.test(html), html.slice(0, 300));
  ["The work item", "Preview", "Versions", "Trace"].forEach(t => assert.ok(html.indexOf(">" + t + "</button>") >= 0, t));
  click(c, { wbpane: "versions", wbpanekey: "r3:live-site" });
  const vs = view(c);
  assert.ok(/<span class="dpk">From<\/span><span class="wbchip">Build/.test(vs), "each version says what it was made from");
  assert.strictEqual((vs.match(/data-wbputback="live-site"/g) || []).length, 1, "only an earlier version can be put back");
});

/* ── W9 ─────────────────────────────────────────────────────────────────── */
test("W9: the screen prints no count and no path at rest", async () => {
  const c = await opened({ map: mapOf({ ask: true, live: true }) });
  const text = h => h.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
  [c.dpListHtml(WEB, {}, null, null), view(c)].forEach(h => {
    const t = text(h);
    assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
    assert.ok(!/\/api\/|\.json|\.html|\bv\d/.test(t), "a path or a version number in the words");
    assert.ok(!/charter/i.test(t), "the word charter on a card");
  });
});

/* ── W10 ────────────────────────────────────────────────────────────────── */
test("W10: the Edit menu carries the command, and panel.html loads the script before the tail", () => {
  const c = fresh();
  assert.ok(/data-wbfound="open">New organisation…<\/button>/.test(c.o2MenuHtml(WEB, c.o2Data())));
  const a = panelHtml.indexOf("/static/js/22-website.js"), b = panelHtml.indexOf("/static/js/09-tail.js"), d = panelHtml.indexOf("/static/js/20-dept.js");
  assert.ok(d >= 0 && a > d && b > a);
});
test("W10b: the command founds the organisation with its Root, hands Root the first department's words, and opens Root", async () => {
  const c = fresh();
  click(c, { wbfound: "open" }, false);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "org" }, value: "City Care Hospital" } }));
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "goal" }, value: "A website for the hospital" } }));
  click(c, { wbfound: "go" }, false);
  for (let i = 0; i < 8; i++) await sleep();
  const posts = JSON.parse(JSON.stringify(c.calls.apiPost));
  assert.deepStrictEqual(posts.slice(0, 1), [
    { p: "/api/native/found", body: { org: "City Care Hospital", first: "A website for the hospital" } }], "one route, nothing founded the old way");
  assert.strictEqual(vm.runInContext("o2S().sel", c), "r2", "Root is where the person goes on");
});

/* ── W11 ────────────────────────────────────────────────────────────────── */
test("W11: the stylesheet block is tokens only and covers what the script emits", () => {
  const i = css.indexOf("/* ── the website department (22-website.js) ");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  const classes = new Set();
  let m;
  const re = /\bwb[a-z0-9]+\b/g;
  const emitted = wbSrc.replace(/data-wb[a-z]+/g, "").replace(/\bds\.wb[a-z]+/g, "").replace(/"wb(found|forg|fgoal)"/g, "");
  while ((m = re.exec(emitted))) classes.add(m[0]);
  classes.delete("wb");
  [...classes].forEach(k => assert.ok(block.indexOf("." + k) >= 0, "no rule for ." + k));
});

/* ── the engine runtime ─────────────────────────────────────────────────── */
const words = h => h.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
const rtMap = o => mapOf(Object.assign({ runtime: 2, live: true }, o || {}));
const readsOf = (c, re) => c.calls.apiGet.filter(p => re.test(p));
async function fnCard(c, tab){
  click(c, { dptab: tab });
  for (let k = 0; k < 3; k++){ c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); }
  return c.dpViewerHtml(WEB, {}, null, null);
}

test("W12: a department on the engine runtime gains the Board; one that is not reads neither steps nor board", async () => {
  const c = await opened({ map: rtMap() });
  assert.ok(/data-wbtab="board"><span>Board<\/span>/.test(list(c)), "the Board is in the list");
  const old = await opened();
  assert.ok(!/data-wbtab="board"/.test(list(old)), "a department of the first build has no Board");
  click(old, { wbengine: "Write" }); view(old); await sleep(); await sleep();
  const html = view(old);
  assert.ok(!/>Steps<\/button>/.test(html) && />Engine<\/button>/.test(html), "its engine card is the one it had");
  click(old, { wbtab: "board" });
  const back = view(old);
  assert.ok(/<div class="o2vh"><b>Map<\/b>/.test(back) && !/class="wbth/.test(back), "and a Board that is asked for falls back to the Map");
  ["identity", "adaptation", "audit"].forEach(f => old.wbFnOwn("r3", f));
  await sleep();
  assert.deepStrictEqual(readsOf(old, /\/steps\/|\/board$/), [], "no read of the runtime's routes");
  assert.ok(/Paused/.test(old.wbFnOwn("r3", "audit")), "Audit says Paused, as before");
});

test("W13: an engine opens on its steps, each with its rung, its check, what its rows say and Hold", async () => {
  const c = await opened({ map: rtMap(), steps: { moved: true } });
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.deepStrictEqual(readsOf(c, /\/steps\//), ["/api/native/r3/steps/Write"]);
  ["Steps", "Engine", "Runs"].forEach(t => assert.ok(html.indexOf(">" + t + "</button>") >= 0, t));
  assert.ok(/aria-pressed="true" data-wbpanekey="r3:Write" data-wbpane="steps"/.test(html), "Steps is the pane it opens on");
  ["List the pages", "Write a page", "Put the pages together"].forEach(s => assert.ok(html.indexOf(s) >= 0, s));
  const row = name => html.slice(html.indexOf(name), html.indexOf("</div></div>", html.indexOf(name)) < 0 ? undefined : html.indexOf(name) + 1400);
  const page = row("Write a page");
  assert.ok(/<span class="wbrung" title="Improvised call"><i class="on"><\/i><i class="on"><\/i><i><\/i><i><\/i><\/span>/.test(page), "two of four pips lit");
  assert.ok(/<span class="wbchip">Improvised call<\/span>/.test(page) && /<span class="wbchip">Side by side<\/span>/.test(page));
  assert.ok(/the page has a body/.test(page), "what its check last said");
  assert.ok(/<span class="dpk">Passing<\/span><div class="dpbar"><i style="width:90%">/.test(page), "its pass rate is a bar");
  assert.ok(/<span class="dpk">To the next rung<\/span><div class="dpbar"><i style="width:25%">/.test(page), "and how far it is from the next rung");
  assert.ok(/data-wbhold="write\.page" data-wbheld="1">Hold</.test(page));
  const code = row("List the pages");
  assert.ok(/<span class="wbchip on">Code<\/span>/.test(code.slice(0, 600)) && !/To the next rung/.test(code.slice(0, html.indexOf("Write a page") - html.indexOf("List the pages"))),
    "a step that is code has nowhere to climb");
  assert.ok(/<span class="dpdot off"><\/span><span>Put the pages together<div class="dpchk">filed has files<\/div>/.test(html), "a step that never ran says which check it names");
  assert.ok(/<h3>Moves<\/h3>/.test(html) && /Improvised call to Checklist · the owner's stamp/.test(html), "a rung that moved says from, to and by whom");
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/write\.(list|page|file)|page_has_body|\bC[0-3]\b|\/api\//.test(t), "a step id, a check id, a rung code or a path in the words");
  const marks = await opened({ map: rtMap(), steps: { held: true, trial: { rung: "C1" }, pending: { to: "C1" } } });
  click(marks, { wbengine: "Write" }); view(marks); await sleep(); await sleep();
  const mh = view(marks);
  ["On trial", "Waits for your stamp", "Held"].forEach(w => assert.ok(mh.indexOf(">" + w + "</span>") >= 0, w));
  assert.ok(/data-wbhold="write\.page" data-wbheld="0">Let go</.test(mh), "a held step can be let go");
});

test("W14: Hold posts the one route it names, and the card that is open stays open", async () => {
  const c = await opened({ map: rtMap() });
  assert.ok(/data-wbhold="identity\.read" data-wbheld="1">Hold</.test(await fnCard(c, "identity")), "Hold is on the function's card");
  assert.ok(click(c, { wbhold: "identity.read", wbheld: "1" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/hold", body: { step: "identity.read", held: true } }]);
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "identity", "the function's card is still the one open");
  click(c, { wbhold: "identity.read", wbheld: "0" });
  await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[1])), { p: "/api/native/r3/hold", body: { step: "identity.read", held: false } });
  assert.ok(readsOf(c, /\/steps\/Identity$/).length >= 2, "and its steps are read again after the post");
});

test("W15: the Board is a list of threads and the open one as a chat: who spoke to whom and with which act; the ideas parked", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbtab: "board" }); view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="o2vh"><b>Board<\/b>/.test(html));
  assert.strictEqual((html.match(/class="wbthr wb/g) || []).length, 2, "one row to a thread");
  assert.ok(html.indexOf("A rule, as understood") < html.indexOf("Which page lists the doctors?"), "newest thread first");
  assert.ok(/class="wbthr wb on" data-wbthread="x-2"><span class="dpdot warn"><\/span><span class="wbwho"><span class="wbchip">Identity<\/span><\/span><span class="dpst">Waits for you<\/span><b>A rule, as understood: every page names a phone line<\/b>/.test(html),
    "the newest is open: its dot, who spoke, its state, its first line");
  assert.ok(/class="wbthr wb" data-wbthread="x-1"><span class="dpdot ok"><\/span>[\s\S]*?<span class="dpst">Done<\/span><b>Which page lists the doctors\?<\/b>/.test(html));
  assert.ok(/<div class="who who-ai">Identity <span class="wbarrow">&rarr;<\/span> Owner<\/div><div class="a">A rule, as understood: every page names a phone line<span class="dpchk">asks · /.test(html),
    "the open thread is turns: who, to whom, the act in a word");
  click(c, { wbthread: "x-1" });
  html = view(c);
  assert.ok(/class="wbthr wb on" data-wbthread="x-1"/.test(html) && !/class="wbthr wb on" data-wbthread="x-2"/.test(html), "another thread opens");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">Which page lists the doctors\?<span class="dpchk">asks · /.test(html), "the owner on the right");
  assert.ok(/<div class="who who-ai">Identity <span class="wbarrow">&rarr;<\/span> Owner<\/div><div class="a">The Doctors page lists them<span class="dpchk">tells · /.test(html), "the department on the left");
  assert.ok(!/A rule, as understood: every page names a phone line<span class="dpchk">/.test(html), "one thread open at a time");
  assert.ok(/<h3>Ideas, parked<\/h3>/.test(html) && /A place where patients sign in/.test(html) && /<span class="wbchip">A sign-in of its own<\/span>/.test(html));
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/accept-proposal|input-required|msg_type|\bx-\d|\/api\//.test(t), "a protocol word or an id in the words");
  const empty = await opened({ map: rtMap(), board: { any: false, threads: [], ideas: [] } });
  click(empty, { wbtab: "board" }); view(empty); await sleep(); await sleep();
  assert.ok(/Nothing has been said yet/.test(view(empty)));
});

test("W16: the Map of a runtime department has one way in, shows what was said back, and a function's card carries its steps", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<h3>Say<\/h3>/.test(html) && /data-wbask="ask"[^>]*>Send</.test(html) && !/<h3>Ask<\/h3>/.test(html), "one box, one button");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "and no second way in");
  assert.ok(/<h3>Replies<\/h3>/.test(html), "what the department said back is on the Map");
  const replies = html.slice(html.indexOf("<h3>Replies</h3>"), html.indexOf("<h3>Health</h3>"));
  assert.ok(replies.indexOf("A rule, as understood") < replies.indexOf("The Doctors page lists them") && replies.indexOf("A rule, as understood") > 0, "newest first");
  assert.ok(!/Which page lists the doctors/.test(replies), "the owner's own words are not a reply");
  assert.ok(!/Paused/.test(html), "no function is paused: " + (html.match(/.{0,60}Paused.{0,20}/) || [""])[0]);
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Which page lists the doctors?" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/ask", body: { text: "Which page lists the doctors?" } }],
    "every kind of words goes through the one route");
  let fn = await fnCard(c, "audit");
  assert.ok(!/Paused/.test(fn) && /<h3>Gates<\/h3>/.test(fn) && /<h3>Take a request<\/h3>/.test(fn), "Audit is an engine: its gate, and its steps under what it hears");
  fn = await fnCard(c, "adaptation");
  assert.ok(/<h3>Ideas, parked<\/h3>/.test(fn), "Adaptation carries the ideas it parked");
  fn = await fnCard(c, "identity");
  ["Control", "Autonomy windows", "Gates", "Take a request"].forEach(h => assert.ok(fn.indexOf("<h3>" + h + "</h3>") >= 0, h));
});

test("W17: a runtime department has one button, Start when it is off and Stop when it is on", async () => {
  const on = await opened({ map: rtMap() });
  click(on, { wbtab: "map" });
  let html = view(on);
  assert.strictEqual((html.match(/data-wbstop="1"/g) || []).length, 1, "one Stop, and only one");
  assert.ok(!/data-wbresume/.test(html) && !/>Resume</.test(html));
  const first = html.slice(0, html.indexOf("<h3>System status</h3>"));
  assert.ok(/<span>On<\/span><button type="button" class="btn wb wbonoff" data-wbstop="1">Stop<\/button>/.test(first), "at the top, beside its state: " + first.slice(0, 400));
  assert.ok(!/>Motor</.test(first) && !/Stopped/.test(first), "its state is one word, On or Off");
  click(on, { wbstop: "1" }); await sleep(); await sleep();
  const off = await opened({ map: rtMap({ stopped: true }) });
  click(off, { wbtab: "map" });
  html = view(off);
  assert.ok(/<span class="dpdot off"><\/span><span>Off<\/span><button type="button" class="btn wb wbonoff dpstamp" data-wbresume="1">Start<\/button>/.test(html), html.slice(0, 500));
  assert.strictEqual((html.match(/data-wbresume="1"/g) || []).length, 1);
  click(off, { wbresume: "1" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify([on.calls.apiPost[0], off.calls.apiPost[0]])),
    [{ p: "/api/native/r3/stop", body: {} }, { p: "/api/native/r3/resume", body: {} }]);
  click(off, { wbtab: "status" });
  assert.ok(/data-wbresume="1">Start</.test(view(off)), "System status carries the same button");
  const old = await opened({ map: mapOf({ stopped: true }) });
  assert.ok(/data-wbresume="1">Resume</.test(view(old)) && !/wbonoff/.test(view(old)), "a department of the first build keeps its own");
});

test("W18: every engine's card says how it starts, and Coordination's card carries its table", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep();
  const html = view(c);
  const starts = html.slice(html.indexOf("<h3>Starts</h3>"), html.indexOf("<h3>Steps</h3>"));
  assert.ok(/<span class="dpk">On<\/span><span class="wbchip on">A new Site plan<\/span>/.test(starts), starts.slice(0, 300));
  assert.ok(/<span class="dpk">Unless<\/span><span class="wbchip ask">Identity: Say whether it may start<\/span><span class="wbchip ask">Priority: Keep it inside its envelope<\/span>/.test(starts));
  assert.ok(!/Who goes first/.test(html), "only Coordination carries the table");
  const fn = await fnCard(c, "identity");
  assert.ok(/<h3>Starts<\/h3>/.test(fn) && /A post addressed to it/.test(fn) && /<span class="wbchip">Nothing holds it<\/span>/.test(fn));
  const co = await fnCard(c, "coordination");
  ["Starts", "Who goes first", "Who may post to whom", "What engines share"].forEach(h => assert.ok(co.indexOf("<h3>" + h + "</h3>") >= 0, h));
  assert.ok(/<span class="dpk">The line<\/span><span class="wbchip">Plan<\/span><span class="wbarrow">&rarr;<\/span><span class="wbchip">Write<\/span>/.test(co));
  assert.ok(/<span class="wbchip">Audit<\/span><span class="dpchk">tells<\/span><span class="wbchip">Identity<\/span>/.test(co), "who, the act in a word, to whom");
  assert.ok(co.indexOf("<h3>What engines share</h3>") < co.indexOf("<h3>Take a request</h3>"), "what engines share comes before what it hears");
  [html, co].forEach(h => {
    const t = words(h);
    assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
    assert.ok(!/coord\.|identity\.|write\.|names_who|\/api\//.test(t), "an id or a path in the words");
  });
});

test("W19: on the screen the five are functions; 'internal system' is printed nowhere", async () => {
  const c = await opened({ map: rtMap() });
  const seen = [c.dpListHtml(WEB, {}, null, null), view(c)];
  click(c, { wbtab: "board" }); view(c); await sleep(); await sleep(); seen.push(view(c));
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep(); seen.push(view(c));
  for (const f of ["identity", "adaptation", "priority", "coordination", "audit"]) seen.push(await fnCard(c, f));
  assert.strictEqual(seen.length, 9);
  seen.forEach((h, i) => assert.ok(!/internal\s+system/i.test(h), "the inside word is on the screen, in view " + i + ": " + (h.match(/.{0,60}internal\s+system.{0,40}/i) || [""])[0]));
  const pr = await fnCard(c, "priority");
  assert.ok(/<h3>The function<\/h3><div class="dpbig">Grants each engine its budget<\/div>/.test(pr), "a function's own card is titled The function");
  assert.ok(/<span>A function woken by new work<\/span>|A function woken by new work/.test(await fnCard(c, "coordination")));
  assert.ok(!/internal\s+system/i.test(wbSrc.replace(/\/\*[\s\S]*?\*\//g, "")), "nor in any string of the script");
});

test("W20: Human Sutra is an app in the list; it shows the department as one conversation in time order, the asks inline, the functions' exchanges folded, one way in", async () => {
  const c = await opened({ map: rtMap({ ask: true }) });
  const lst = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/data-wbtab="conversation"><span>Human Sutra<\/span>/.test(lst), "the app is listed");
  assert.ok(/>Apps<\/div>[\s\S]{0,300}Human Sutra/.test(lst), "under Apps");
  click(c, { wbtab: "conversation" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<div class="o2vh"><b>Human Sutra<\/b>/.test(html), "the app opens");
  const i1 = html.indexOf("Which page lists the doctors?"), i2 = html.indexOf("The Doctors page lists them"), i3 = html.indexOf("A rule, as understood");
  assert.ok(i1 > 0 && i1 < i2 && i2 < i3, "oldest first, newest at the bottom: " + [i1, i2, i3]);
  assert.ok(/class="wbline wb me">/.test(html), "the owner's own line is marked");
  assert.ok(/<h3>Waiting for you<\/h3>/.test(html) && /Publish: go live for the first time/.test(html) &&
    /data-wbdecide="a-1" data-wbok="1"/.test(html) && /data-wbdecide="a-1" data-wbok="0"/.test(html), "an ask is a line with its buttons");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "one way in");
  assert.ok(/<h3>Say<\/h3>/.test(html) && /data-wbask="ask"[^>]*>Send</.test(html), "and it is Say");
  assert.ok(!/internal\s+system/i.test(html));
  const old = await opened();
  assert.ok(!/Human Sutra/.test(old.dpListHtml(WEB, {}, null, null)), "a department of the first build has no app");
  const b2 = JSON.parse(JSON.stringify(BOARD));
  b2.threads.unshift({ id: "x-3", topic: "trial", protocol: "propose", state: "completed", decider: "Priority", opened: AT, closed: AT,
    outcome: { by: "accept-proposal" }, bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 2, default: "failure", posts: [
      { n: 4, src: "Adaptation", dst: ["Priority"], msg_type: "propose", at: AT, word: "trial", line: "one more call a run, for 2 runs" },
      { n: 5, src: "Priority", dst: ["Adaptation"], msg_type: "accept-proposal", at: AT, word: "trial", line: "Room in today's envelope covers it" }] });
  const f = await opened({ map: rtMap(), board: b2 });
  click(f, { wbtab: "conversation" }); view(f); await sleep(); await sleep();
  const h2 = view(f);
  assert.ok(/<details class="wbfold wb"><summary>[\s\S]*?Adaptation[\s\S]*?Priority[\s\S]*?one more call a run[\s\S]*?<\/summary>/.test(h2), "the functions' own exchange folds under the line that started it");
  assert.ok(h2.indexOf("The Doctors page lists them") < h2.indexOf("<details") && h2.indexOf("<details") < h2.indexOf("Room in today"), "and sits in time order");
  assert.ok(/<h3>Say<\/h3>/.test(h2) && !/<h3>Waiting for you<\/h3>/.test(h2), "nothing waits, so no empty card");
});

test("W21: Priority's card carries the limits, born from its template, and Set posts the owner's own for one engine", async () => {
  const c = await opened({ map: rtMap() });
  const pr = await fnCard(c, "priority");
  assert.ok(/<h3>Limits<\/h3>/.test(pr), "the card is there");
  assert.ok(/data-wbdraft="r3:env:Write:calls"[^>]*value="240"/.test(pr) && /data-wbdraft="r3:env:Write:usd"[^>]*value="6"/.test(pr), "each engine's two numbers");
  assert.ok(/data-wbdraft="r3:env:Audit:calls"[^>]*value="30"/.test(pr), "the functions too");
  assert.ok(/data-wbenv="Write"/.test(pr), "and a Set an engine");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:env:Write:usd" }, value: "3" } }));
  click(c, { wbenv: "Write" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/envelope", body: { engine: "Write", usd: 3 } }],
    "only what was typed is sent, for that engine");
  const old = await opened();
  assert.ok(!/<h3>Limits<\/h3>/.test(await fnCard(old, "priority")), "a department of the first build keeps its card");
});

test("W22: a Root is a department on the screen: its one engine, Setup; Say asks Root for a department; no goal box; the app", async () => {
  const m = rtMap();
  m.kind = "root"; m.say = "Ask Root for a department: what it is for"; m.has_goal = true; m.live = false;
  m.engines = [{ name: "Setup", reads: "Request", writes: "Department", runs_as: "model", slot: "after a new Request", state: "Idle",
                 envelope: { calls: 240, usd: 6, used_calls: 0, used_usd: 0 }, window_min: 15, last: null }];
  m.artifacts = [{ name: "Request", slug: "request", versions: 1, latest: null }, { name: "Department", slug: "department", versions: 0, latest: null }];
  const c = await opened({ map: m });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/data-wbengine="Setup"/.test(html) && !/data-wbengine="Plan"/.test(html), "Root's line is Setup alone");
  assert.ok(/placeholder="Ask Root for a department: what it is for"/.test(html), "Say speaks to Root");
  assert.ok(!/What is this website for\?/.test(html), "a Root is born with its goal: no goal box");
  assert.ok(!/Open the live site/.test(html), "nothing to open live");
  const lst = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/data-wbengine="Setup"/.test(lst) && /Human Sutra/.test(lst) && /data-wbart="request"/.test(lst), "the list: Setup, the Request filed, the app");
});

test("W23: a Root that has not been asked for anything says so, and what to say; once asked, the line is gone", async () => {
  const m = rtMap();
  m.kind = "root"; m.say = "Ask Root for a department: what it is for"; m.has_goal = true; m.live = false;
  m.engines = [{ name: "Setup", reads: "Request", writes: "Department", runs_as: "model", slot: "after a new Request", state: "Idle",
                 envelope: { calls: 240, usd: 6, used_calls: 0, used_usd: 0 }, window_min: 15, last: null }];
  m.artifacts = [{ name: "Request", slug: "request", versions: 0, latest: null }, { name: "Department", slug: "department", versions: 0, latest: null }];
  const c = await opened({ map: m });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<h3>Departments<\/h3>[\s\S]{0,80}No department yet\. Say what the first one is for\./.test(html), "the empty state names the action");
  const m2 = JSON.parse(JSON.stringify(m)); m2.artifacts[0].versions = 1;
  const c2 = await opened({ map: m2 });
  click(c2, { wbtab: "map" }); view(c2); await sleep(); await sleep();
  html = view(c2);
  assert.ok(!/No department yet/.test(html), "asked once, the line is gone");
  const w = await opened({ map: rtMap() });
  click(w, { wbtab: "map" }); view(w); await sleep(); await sleep();
  assert.ok(!/No department yet/.test(view(w)), "a website department never says it");
  /* the chat says it too, on a Root with nothing yet, and nowhere else */
  const e = await opened({ map: m, chat: { root: "r3", about: null, turns: [], asks: [], departments: [] } });
  view(e); await sleep(); await sleep();
  assert.ok(/No department yet\. Say what the first one is for\./.test(view(e)), "the chat of an empty Root");
  const f = await opened({ map: rtMap(), chat: { root: "r2", about: "r3", turns: [], asks: [], departments: [] } });
  view(f); await sleep(); await sleep();
  assert.ok(/Nothing has been said yet/.test(view(f)) && !/No department yet/.test(view(f)));
});

test("W24: a filed artifact shows its template: what it holds, its checks, who writes it, when it counts, what runs on a new one", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbart: "live-site", wbpane: "item" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<h3>Template<\/h3>/.test(html), "the template card");
  assert.ok(/index\.html, \*\.html/.test(html) && /has_index_html/.test(html) && /Publish/.test(html), "holds, checks, written by");
  assert.ok(/After your stamp/.test(html), "when it counts");
  assert.ok(/Adaptation, Audit/.test(html), "its operations: the engines that run on a new one");
});

test("W25: the chat is the one point of entry: it opens first; inside a department it is scoped with the department as a chip; the words go to Root; a stamp goes where the ask lives; on Root the whole chat", async () => {
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m });
  assert.ok(/o2li dpli on" data-wbtab="chat"/.test(list(c)) && !/o2li dpli on" data-wbtab="map"/.test(list(c)), "Chat opens without a click");
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="o2vh"><b>Chat<\/b>/.test(html));
  assert.deepStrictEqual(readsOf(c, /\/chat/), ["/api/native/r3/chat"], "one read, of the chat");
  assert.ok(/<div class="turn wbturn"><div class="who who-you">You<\/div><div class="u md">Which page lists the doctors\?<\/div><\/div>/.test(html), "the owner's turn, the chat's own markup");
  assert.ok(/<div class="who who-ai">Root<\/div><div class="a">The Doctors page lists them<span class="dpchk">tells · /.test(html), "the left name is Root");
  assert.ok(!/<span class="wbchip">City Care Hospital Website<\/span>/.test(html), "inside the department, no chip on the turns");
  assert.ok(!/Set up a department/.test(html), "Root's own turns are not here");
  assert.ok(/<button type="button" class="wbchip on wbto wb" data-wbchip="off">to City Care Hospital Website &times;<\/button><textarea id="wbd-ask"/.test(html), "the box carries where you stand as a chip");
  assert.ok(/<h3>Waiting for you<\/h3>/.test(html) && /City Care Hospital Website · Publish/.test(html) && /data-wbdecide="a-1" data-wbok="1" data-wbref="r3"/.test(html), "an ask says where it lives");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "one way in");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Add a Careers page" } }));
  assert.ok(click(c, { wbask: "ask" })); await sleep(); await sleep();
  click(c, { wbchip: "off" });
  assert.ok(/<button type="button" class="wbchip wbto wb" data-wbchip="on">to Root<\/button>/.test(view(c)), "the chip taken off: the words go to Root alone");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Start a department for billing" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  click(c, { wbdecide: "a-1", wbok: "1", wbref: "r3" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r2/ask", body: { text: "Add a Careers page", about: "r3" } },
    { p: "/api/native/r2/ask", body: { text: "Start a department for billing" } },
    { p: "/api/native/r3/asks/a-1", body: { approve: true } }], "to Root, about the department; to Root alone; the stamp where the ask lives");
  assert.ok(readsOf(c, /\/chat/).length >= 2, "and the chat is read again after a post");
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const r = await opened({ map: rm, chat: ROOT_CHAT });
  view(r); await sleep(); await sleep();
  html = view(r);
  assert.ok(/<div class="who who-ai">Root<span class="wbchip">City Care Hospital Website<\/span><\/div><div class="a">The Doctors page lists them/.test(html), "on Root the department is a chip on the turn");
  assert.ok(/<div class="who who-you"><span class="wbchip">City Care Hospital Website<\/span>You<\/div><div class="u md">Which page lists the doctors\?/.test(html), "on the owner's turn too");
  assert.ok(/<div class="who who-ai">Root<\/div><div class="a">Set up a department: City Care Hospital Website<span class="dpchk">asks · /.test(html), "Root's own turns, with no chip");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">Stamped<\/div>/.test(html), "a stamp is a turn with the act as its line, never an empty bubble");
  assert.ok(!/data-wbchip/.test(html) && /placeholder="Ask Root for a department: what it is for"/.test(html), "no chip on the box: Root is where you stand");
  assert.ok(/<span class="dpk">Departments<\/span><span class="wbchip on">City Care Hospital Website<\/span>/.test(html), "the departments under Root");
  assert.ok(/data-wbdecide="a-1" data-wbok="1" data-wbref="r5"/.test(html), "the department's ask, with where it lives");
  (r.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Stop City Care Hospital Website" } }));
  click(r, { wbask: "ask" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(r.calls.apiPost)), [{ p: "/api/native/r3/ask", body: { text: "Stop City Care Hospital Website" } }], "on Root the words go straight in");
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/\bx-\d|\/api\/|\br[0-9]\b/.test(t), "an id or a path in the words");
  const old = await opened();
  assert.ok(!/data-wbtab="chat"/.test(list(old)) && /o2li dpli on" data-wbtab="map"/.test(list(old)), "a department of the first build opens on its Map, as before");
});

test("W26: each function's card has its own Settings tab: its template, its own limit, its ladder numbers, how it starts; Identity's carries where the site is served from", async () => {
  const c = await opened({ map: rtMap() });
  vm.runInContext("dpS().pane['r3:priority'] = 'settings';", c);
  let html = await fnCard(c, "priority");
  assert.ok(/aria-pressed="true" data-dppane="settings">Settings<\/button>/.test(html), "the tab, open");
  ["Template", "Limit", "Ladder", "Starts", "Hears"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  assert.ok(!/<h3>Envelopes<\/h3>/.test(html) && !/<h3>Queue<\/h3>/.test(html), "the card's own rows are on its own tab");
  assert.ok(/data-wbdraft="r3:env:Priority:calls"[^>]*value="30"/.test(html) && /data-wbenv="Priority"/.test(html), "its own limit, and only its own");
  assert.ok(!/data-wbdraft="r3:env:Write:calls"/.test(html), "not another's");
  assert.ok(/<span class="dpk">Runs before a step climbs<\/span><input type="number" min="0" step="1" data-wbdraft="r3:ladder:Priority:runs" value="40"/.test(html), "its ladder numbers");
  assert.ok(/data-wbladder="Priority"/.test(html) && !/<h3>Served from<\/h3>/.test(html));
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ladder:Priority:runs" }, value: "50" } }));
  assert.ok(click(c, { wbladder: "Priority" })); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority", "the card stays open");
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", c);
  html = await fnCard(c, "identity");
  assert.ok(/<h3>Served from<\/h3>/.test(html) && /data-wbhost="1"/.test(html), "Identity's carries the host");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:host" }, value: "https://cityclinic.example" } }));
  click(c, { wbhost: "1" }); await sleep(); await sleep();
  vm.runInContext("dpS().pane['r3:coordination'] = 'settings';", c);
  html = await fnCard(c, "coordination");
  assert.ok(/<h3>Who goes first<\/h3>/.test(html) && /<h3>Who may post to whom<\/h3>/.test(html), "Coordination's carries its table");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r3/ladder", body: { engine: "Priority", runs: 50 } },
    { p: "/api/native/r3/host", body: { host: "https://cityclinic.example" } }], "only what was typed, for that function");
  const t = words(html);
  assert.ok(!/internal\s+system/i.test(t));
  const old = await opened();
  vm.runInContext("dpS().pane['r3:priority'] = 'settings';", old);
  const oh = await fnCard(old, "priority");
  assert.ok(!/>Settings<\/button>/.test(oh) && /<h3>Envelopes<\/h3>/.test(oh), "a department of the first build keeps the tabs it had");
});

Promise.all(pending).then(() => {
  console.log("-".repeat(60));
  console.log(failed ? " " + failed + " failed (" + ran + " tests)" : " all passed (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
