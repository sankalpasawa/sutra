#!/usr/bin/env node
/* test_dept.js -- the department screen (static/js/20-dept.js, holding/plans/
   department-screen/BUILD-PLAN.md slice A onwards): the S.dp state slice, the
   Now loaders and their in-flight guard, the list column's seven groups, the
   default Now selection, the ask card with Stamp / Refuse, the expired and the
   irreversible ask, the empty Now, and the one branch inside 19-org2.js that
   hands a selected department to this module.

   Harness: test_org2.js's own fresh() (the REAL modules under vm with a stub
   context carrying S, apiGet, apiPost, render, document), widened in two ways
   the department screen needs -- 20-dept.js is loaded into the same context
   after 19-org2.js (the load order panel.html uses), and the stub document
   COLLECTS its listeners so a synthetic click can be dispatched at them.
   Run: node test_dept.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const orgSrc = fs.readFileSync(path.join(JS, "03-org.js"), "utf8");
const o2Src = fs.readFileSync(path.join(JS, "19-org2.js"), "utf8");
const dpSrc = fs.readFileSync(path.join(JS, "20-dept.js"), "utf8");
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
    if (r && typeof r.then === "function") pending.push(r.then(() => console.log("ok   " + name), e => { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e && e.message)); }));
    else console.log("ok   " + name);
  } catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e && e.message)); }
}

/* ── the fixture tree (test_org2.js's own rows, plus a second department) ── */
const ROOT = { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1, node_kind: "root" };
const DESK = { ref: "r1", path: "D1", name: "Desktop", parent_ref: "r0", status: "active", ts_minted_ms: 2, cwd: "/Users/x", node_kind: "machine" };
const CO   = { ref: "r2", path: "D2", name: "Asawa Inc.", parent_ref: "r0", status: "active", ts_minted_ms: 3, node_kind: "organisation" };
const HOLD = { ref: "r3", path: "D2.D1", name: "Holding Departments", parent_ref: "r2", status: "active", ts_minted_ms: 4, node_kind: "department" };
const EXP  = { ref: "r4", path: "D2.D1.D1", name: "Experience", parent_ref: "r3", status: "active", ts_minted_ms: 5, node_kind: "department" };
const ORG  = { ref: "r5", path: "D2.D1.D1.D1", name: "Org", parent_ref: "r4", status: "active", ts_minted_ms: 6, node_kind: "department" };
const TREE = [ROOT, DESK, CO, HOLD, EXP, ORG];

const DEPT_EXP = {
  ref: "r4", name: "Experience", kind: "department", status: "active",
  parent: { ref: "r3", name: "Holding Departments" },
  address: ["Sutra", "Asawa Inc.", "Holding Departments", "Experience"],
  children: [{ ref: "r5", name: "Org" }],
  charter: { id: "C-1", title: "Experience Charter", purpose: "Own the operator's experience of Sutra Desktop: screens, journeys and the words on them.", status: "active", kind: "standing", scope_in: [] },
  charters: [],
  filed: [{ id: "holding/departments/experience/org/HLD.md", kind: "task", label: "HLD", charter_id: "C-1", ts_ms: 10 }],
  filed_n: 1,
  docs: [{ path: "holding/departments/experience/org/HLD.md", title: "Org HLD", mtime: 5 }],
  successors: [], ts_minted_ms: 1789000000000, retired_at_ms: null, retire_reason_code: null,
};

const HOUR = 3600 * 1000;
const ASK = { id: "p-aa11", kind: "routine.update", summary: "Pause the nightly sweep",
              args: { id: "rt-1" }, created_ms: Date.now() - HOUR, window_ms: 24 * HOUR,
              default: "Nothing happens", irreversible: false };
const HARD_ASK = { id: "p-bb22", kind: "pr.create", summary: "Open a pull request for the sweep",
                   args: {}, created_ms: Date.now() - HOUR, window_ms: 24 * HOUR,
                   default: "Nothing happens", irreversible: true };
const OLD_ASK = { id: "p-cc33", kind: "routine.update", summary: "Pause the weekly sweep",
                  args: { id: "rt-2" }, created_ms: Date.now() - 25 * HOUR, window_ms: 24 * HOUR,
                  default: "Nothing happens", irreversible: false };
const RUNNING = [{ sid: "s-1", id: "atom-1", goal: "Land the department screen", status: "open", touches: ["/Users/x/a"] }];
const WAITS = [{ id: "m-1", objective: "Write the release note", state: "queued", target_session: "s-2" }];

/* A DOM stub that remembers its listeners, so a synthetic click can be aimed at
   a node the way the browser would aim one (test_org2.js only needs a no-op). */
function elem(attrs, inside){
  const el = {
    dataset: attrs || {},
    _inside: inside === undefined ? ".dp" : inside,
    closest(sel){
      if (sel === el._inside) return el;
      const keys = String(sel).split(",").map(s => s.trim());
      for (const k of keys){
        const m = /^\[data-([a-z0-9-]+)\]$/i.exec(k);
        if (m){
          const camel = m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          if (el.dataset[camel] !== undefined) return el;
        }
      }
      return null;
    },
  };
  return el;
}

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], render: 0, decide: [] };
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Math, encodeURIComponent, Promise, setTimeout, clearTimeout,
    apiGet: opts.apiGet || ((p) => { calls.apiGet.push(p); return new Promise(() => {}); }),
    apiPost: opts.apiPost || ((p, body) => { calls.apiPost.push({ p, body }); return Promise.resolve({}); }),
    window: opts.window || {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { departments: () => "", charters: () => "", placements: () => "", reorg: () => "", history: () => "", health: () => "" },
    TITLES: { departments: ["Departments", ""] },
    DOMAINS: opts.DOMAINS === undefined ? TREE : opts.DOMAINS,
    CHARTERS: [], PLACEMENTS: [], INDEX: [], META: {},
    SETTINGS: opts.SETTINGS === undefined ? { flags: { org2: true } } : opts.SETTINGS,
    ICON: { know: "<path d='k'/>", dept: "<path d='d'/>", edit: "<path d='e'/>", plc: "<path d='p'/>" },
    st: (d) => d.status || "active",
    S: Object.assign({ screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } }, opts.S || {}),
    render: () => { calls.render++; },
    loadOrg: opts.loadOrg || (() => Promise.resolve()),
    simulate: () => ({ pending: true }),
    sbPageFromPath: (p) => (/\.md$/.test(p) ? p : null),
    mdHtml: (t) => "<p>" + t + "</p>",
    decideProposal: opts.decideProposal || ((pid, ok) => { calls.decide.push({ pid, ok }); return Promise.resolve({}); }),
    loadProposals: () => {},
    document: {
      listeners: {},
      addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); },
      querySelector(){ return null; },
      getElementById(){ return null; },
    },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(o2Src, ctx);
  vm.runInContext(dpSrc, ctx);
  return ctx;
}
const sleep = () => new Promise(r => setTimeout(r, 0));

/* Dispatch a synthetic click at `target` through every registered listener. */
function click(c, target){
  let prevented = false;
  const ev = { target, preventDefault(){ prevented = true; }, stopPropagation(){} };
  (c.document.listeners.click || []).forEach(fn => fn(ev));
  return prevented;
}

/* Select a department the way the tree does, without a network read. */
function open(c, ref, seed){
  c.o2EnsureRegistered();
  const st = c.o2S();
  st.loaded = true;
  st.dept[ref || "r4"] = DEPT_EXP;
  st.sel = ref || "r4";
  if (typeof c.dpS === "function") Object.assign(c.dpS(), seed || {});
  return st;
}

/* ── S5: the module loads beside 19-org2.js and changes nothing about it ── */
test("S5: 20-dept.js loads in the same context as 19-org2.js and registers no screen of its own", () => {
  const c = fresh();
  c.o2EnsureRegistered();
  assert.strictEqual(typeof c.SCREENS.org2, "function", "19-org2.js still owns the org2 screen");
  assert.ok(!/SCREENS\.[A-Za-z0-9_]+\s*=/.test(dpSrc), "20-dept.js must not register a SCREENS entry");
  assert.ok(!/TITLES\.[A-Za-z0-9_]+\s*=/.test(dpSrc), "20-dept.js must not register a TITLES row");
  assert.ok(!/\bloadModules\s*\(/.test(dpSrc), "20-dept.js must never call loadModules (it owns another screen's cache)");
});

/* The order is read off the SCRIPT TAGS, not off the raw text: panel.html has
   named 09-tail.js inside a comment since 2.247.0, so a plain indexOf finds the
   prose before the tag (BUILD-PLAN S6's literal verify has that same bug). */
test("S6: panel.html loads 20-dept.js after 19-org2.js and before 09-tail.js", () => {
  const tags = (panelHtml.match(/<script src="\/static\/js\/[^"]+"><\/script>/g) || [])
    .map(t => (/\/static\/js\/([^?"]+)/.exec(t) || [])[1]);
  const i19 = tags.indexOf("19-org2.js"), i20 = tags.indexOf("20-dept.js"), i09 = tags.indexOf("09-tail.js");
  assert.ok(i19 !== -1 && i20 !== -1 && i09 !== -1, "all three tags are present: " + tags.join(" "));
  assert.ok(i19 < i20 && i20 < i09, "boot() must run last, so 20-dept.js sits between them");
  assert.ok(/20-dept\.js\?v=__ASSETVER__/.test(panelHtml), "the tag carries the asset version");
  assert.strictEqual(tags[tags.length - 1], "09-tail.js", "09-tail.js stays the last script tag");
});

/* ── S12: the state slice ── */
test("S12: dpS() initialises S.dp once and hands back the same object", () => {
  const c = fresh();
  assert.strictEqual(c.S.dp, undefined, "nothing is touched before the first call");
  const a = c.dpS(), b = c.dpS();
  assert.strictEqual(a, b, "a second call returns the same slice");
  assert.strictEqual(a, c.S.dp);
  assert.strictEqual(a.sel, null);
  for (const k of ["tab", "chatMode", "loading", "error", "busy", "more", "engineRuns", "engineData"]) {
    assert.strictEqual(typeof a[k], "object", k + " is a map");
  }
  for (const k of ["now", "running", "waits", "identity", "engines", "filed", "people", "meters"]) {
    assert.strictEqual(a[k], null, k + " starts unread");
  }
});

/* ── S13: the three Now loaders ── */
test("S13: each Now loader reads its own route", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadNow("r4"); c.dpLoadRunning("r4"); c.dpLoadWaits("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet, ["/api/dept/r4/now", "/api/dept/r4/running", "/api/dept/r4/waits"]);
});

test("S13: two overlapping calls to one loader make exactly one network read", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadNow("r4"); c.dpLoadNow("r4"); c.dpLoadNow("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet, ["/api/dept/r4/now"], "the busy guard holds");
});

test("S13: a read that lands answers the card, and a second call is a no-op until force", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ asks: [ASK], skipped: 0, decidable: true }); } });
  c.dpS().sel = "r4";
  await c.dpLoadNow("r4");
  assert.strictEqual(c.dpS().now.ref, "r4");
  assert.strictEqual(c.dpS().now.asks.length, 1);
  await c.dpLoadNow("r4");
  assert.strictEqual(c.calls.apiGet.length, 1, "already read");
  await c.dpLoadNow("r4", true);
  assert.strictEqual(c.calls.apiGet.length, 2, "force re-reads");
  assert.strictEqual(c.dpS().busy["now:r4"], undefined, "the flag is cleared");
});

test("S13: an answer for a department that is no longer open is dropped", async () => {
  let release;
  const c = fresh({ apiGet: () => new Promise(r => { release = r; }) });
  c.dpS().sel = "r4";
  const p = c.dpLoadNow("r4");
  c.dpS().sel = "r5";                     /* the operator moved on */
  release({ asks: [ASK] });
  await p;
  assert.strictEqual(c.dpS().now, null, "r4's rows never paint over r5");
});

test("S13: a failed read is kept beside the card, never thrown", async () => {
  const c = fresh({ apiGet: () => Promise.reject(new Error("Sutra did not answer")) });
  c.dpS().sel = "r4";
  await c.dpLoadNow("r4");
  assert.strictEqual(c.dpS().error.now, "Sutra did not answer");
  assert.strictEqual(c.dpS().now, null);
});

/* ── S14: opening a department ── */
test("S14: dpSelect fires the three Now reads and defaults the card to Now", async () => {
  const c = fresh();
  c.dpSelect("r4");
  await sleep();
  assert.strictEqual(c.dpS().sel, "r4");
  assert.strictEqual(c.dpS().tab.r4, "now", "A2: Now is the card on open");
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/now", "/api/dept/r4/running", "/api/dept/r4/waits"]);
});

test("S14: opening another department drops what the first one answered", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ asks: [ASK] }); } });
  c.dpSelect("r4");
  await sleep();
  assert.strictEqual(c.dpS().now.asks.length, 1);
  c.dpS().confirm = "p-aa11"; c.dpS().engineSel = "e-1";
  c.dpSelect("r5");
  assert.strictEqual(c.dpS().now, null, "no stale rows under the new name");
  assert.strictEqual(c.dpS().confirm, null);
  assert.strictEqual(c.dpS().engineSel, null);
  assert.strictEqual(c.dpS().tab.r5, "now");
});

test("S14: re-selecting the same department keeps its card and re-reads nothing", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ asks: [] }); } });
  c.dpSelect("r4");
  await sleep();
  c.dpS().tab.r4 = "identity";
  c.dpSelect("r4");
  await sleep();
  assert.strictEqual(c.dpS().tab.r4, "identity", "the open card survives a repaint");
  assert.strictEqual(c.calls.apiGet.length, 3, "nothing is read twice");
});

/* ── S16 / A1: the seven groups, in order ── */
const GROUPS = ["Now", "Functions", "Engines", "Filed work", "People", "Documents", "Apps"];
function groupLabels(html){
  return (html.match(/class="o2gl dpgl">([^<]*)</g) || []).map(m => /">([^<]*)<$/.exec(m)[1]);
}
test("S16/A1: the list column shows the seven groups in order", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const html = c.dpListHtml(n, d, DEPT_EXP, null);
  assert.deepStrictEqual(groupLabels(html), GROUPS);
});

test("S16/A33: an empty department still shows all seven groups, one quiet line each", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const bare = Object.assign({}, DEPT_EXP, { filed: [], docs: [], charter: null, charters: [] });
  const html = c.dpListHtml(n, d, bare, null);
  assert.deepStrictEqual(groupLabels(html), GROUPS);
  const quiet = (html.match(/class="o2quiet dpq">([^<]*)</g) || []).length;
  assert.strictEqual(quiet, 5, "Engines, Filed work, People, Documents, Apps each say one line");
  assert.ok(!/help|Help/.test(html), "A28: no help text");
  assert.ok(html.indexOf("/Users/") === -1, "A28: no path on screen");
});

test("S16: Functions carries the five function rows in the PRD's order", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const html = c.dpListHtml(n, d, DEPT_EXP, null);
  const rows = (html.match(/data-dptab="([a-z]+)"/g) || []).map(m => /"([a-z]+)"/.exec(m)[1]);
  assert.deepStrictEqual(rows, ["now", "identity", "adaptation", "priority", "coordination", "audit"]);
});

test("S16: Filed work and Documents read the department the Org screen already loaded", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const html = c.dpListHtml(n, d, DEPT_EXP, null);
  assert.ok(html.indexOf(">HLD<") !== -1, "the filed row is a name");
  assert.ok(html.indexOf(">Org HLD<") !== -1, "the document row is a title");
  assert.ok(html.indexOf("holding/departments") === -1 || /data-dp(filed|doc)="holding/.test(html),
    "a path may ride an attribute, never the label");
});

test("S16: the first paint opens the department without a click", async () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpListHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.strictEqual(c.dpS().sel, "r4");
  assert.strictEqual(c.calls.apiGet.length, 3);
});

/* ── S17 / A2: Now is the card on open ── */
test("S17/A2: the Now row is on and its card paints with no click", async () => {
  const c = fresh({ apiGet: (p) => {
    c.calls.apiGet.push(p);
    if (/\/now$/.test(p)) return Promise.resolve({ asks: [ASK], decidable: true });
    if (/\/waits$/.test(p)) return Promise.resolve({ waits: WAITS });
    return Promise.resolve({ running: RUNNING });
  } });
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpListHtml(n, d, DEPT_EXP, null);
  await sleep(); await sleep();
  const list = c.dpListHtml(n, d, DEPT_EXP, null);
  assert.ok(/class="o2li dpli on" data-dptab="now"/.test(list), "the Now row is the selected one");
  const view = c.dpViewerHtml(n, d, DEPT_EXP, null);
  assert.ok(view.indexOf("<b>Now</b>") !== -1, "the card is Now");
  assert.ok(view.indexOf("Pause the nightly sweep") !== -1, "the ask is on it");
  assert.ok(view.indexOf("Write the release note") !== -1, "so is the wait");
  assert.ok(view.indexOf("Land the department screen") !== -1, "and the running work item");
});

test("S17: before the reads land the card shows neither rows nor help text", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpS().sel = "r4"; c.dpS().tab.r4 = "now";
  const view = c.dpViewerHtml(n, d, DEPT_EXP, null);
  assert.ok(/o2skel/.test(view), "a skeleton, not a guess");
  assert.ok(!/help|Help/.test(view));
});

test("S17: a card that has not been built yet says one quiet line", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpS().sel = "r4"; c.dpS().tab.r4 = "identity";
  const view = c.dpViewerHtml(n, d, DEPT_EXP, null);
  assert.ok(view.indexOf("<b>Identity</b>") !== -1);
  assert.strictEqual((view.match(/o2quiet dpq/g) || []).length, 1, "exactly one quiet line");
});

/* ── S18 / A4, A5: the ask card ── */
function nowCard(c, asks){
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "now";
  st.now = { ref: "r4", asks: asks, decidable: true };
  st.running = { ref: "r4", running: [] };
  st.waits = { ref: "r4", waits: [] };
  const d = c.o2Data();
  return c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
}
test("S18/A4: an ask shows the sentence, the default, the window as a bar and two answers", () => {
  const c = fresh();
  const html = nowCard(c, [ASK]);
  assert.ok(html.indexOf("Pause the nightly sweep") !== -1, "the sentence");
  assert.ok(html.indexOf("If nothing is done: Nothing happens") !== -1, "the default");
  assert.ok(/class="dpbar"><i style="width:9[0-9.]+%"/.test(html), "the window is a bar, not a number");
  assert.ok(html.indexOf('data-dpdecide="p-aa11" data-dpok="1">Stamp<') !== -1, "Stamp");
  assert.ok(html.indexOf('data-dpdecide="p-aa11" data-dpok="0">Refuse<') !== -1, "Refuse");
});

test("S18/A5: Stamp and Refuse go through decideProposal, and nothing else is posted", async () => {
  const c = fresh();
  nowCard(c, [ASK]);
  const prevented = click(c, elem({ dpdecide: "p-aa11", dpok: "1" }));
  assert.strictEqual(prevented, true);
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide, [{ pid: "p-aa11", ok: true }]);
  assert.deepStrictEqual(c.calls.apiPost, [], "no write path of its own");
  click(c, elem({ dpdecide: "p-aa11", dpok: "0" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide[1], { pid: "p-aa11", ok: false });
});

test("S18: an answer re-reads Now so the card stops showing a decided ask", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ asks: [] }); } });
  nowCard(c, [ASK]);
  click(c, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep(); await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/now") !== -1, "Now is read again");
});

test("S18: a click outside .dp never reaches a department handler", async () => {
  const c = fresh();
  nowCard(c, [ASK]);
  click(c, elem({ dpdecide: "p-aa11", dpok: "1" }, ".o2"));
  await sleep();
  assert.deepStrictEqual(c.calls.decide, [], "scoped to .dp, the 18-modules.js discipline");
});

test("S18: a tab row switches the card", () => {
  const c = fresh();
  nowCard(c, [ASK]);
  click(c, elem({ dptab: "audit" }));
  assert.strictEqual(c.dpS().tab.r4, "audit");
});

/* ── S19 / A6: the expired ask ── */
test("S19/A6: an ask past its window shows its default as taken and no buttons", () => {
  const c = fresh();
  const html = nowCard(c, [OLD_ASK]);
  assert.ok(html.indexOf("The window closed: Nothing happens") !== -1, "the default is what happened");
  assert.ok(html.indexOf("data-dpdecide") === -1, "no answer is offered on a closed window");
  assert.ok(html.indexOf("dpbar") === -1, "and no window bar either");
  assert.ok(/class="dpask gone"/.test(html));
});

test("S19: a live ask beside an expired one keeps its own buttons", () => {
  const c = fresh();
  const html = nowCard(c, [ASK, OLD_ASK]);
  assert.strictEqual((html.match(/data-dpdecide="p-aa11"/g) || []).length, 2, "Stamp and Refuse on the live one");
  assert.strictEqual((html.match(/data-dpdecide="p-cc33"/g) || []).length, 0, "none on the closed one");
});

/* ── S20 / A9: the empty Now ── */
test("S20/A9: nothing open is exactly one quiet line and no help text", () => {
  const c = fresh();
  const html = nowCard(c, []);
  assert.ok(html.indexOf("Nothing waiting on you") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, "one line, not three");
  assert.ok(html.indexOf("dpcard") === -1, "no empty Asks / Waits / Running cards");
  assert.ok(!/help|Help|How to|Learn/.test(html), "A28: no help text");
  assert.ok(html.indexOf("/Users/") === -1, "A28: no path");
  assert.ok(!/>\s*\d+\s*</.test(html), "A28: no raw count at rest");
});

test("S20: a read that failed says so instead of claiming nothing is waiting", () => {
  const c = fresh();
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "now"; st.error.now = "Sutra did not answer";
  const d = c.o2Data();
  const html = c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(html.indexOf("Could not read") !== -1);
  assert.ok(html.indexOf("Nothing waiting on you") === -1);
});

/* ── S21 / A32: the irreversible ask ── */
test("S21/A32: an ask that leaves this machine carries the warning class on card and bar", () => {
  const c = fresh();
  const html = nowCard(c, [HARD_ASK]);
  assert.ok(/class="dpask hard"/.test(html), "the card takes the warning token");
  assert.ok(/class="dpbar hard"/.test(html), "so does its window bar");
  const plain = nowCard(fresh(), [ASK]);
  assert.ok(!/dpask hard/.test(plain) && !/dpbar hard/.test(plain), "a reversible ask does not");
});

test("S21/A32: Stamp on an irreversible ask needs a second click", async () => {
  const c = fresh();
  nowCard(c, [HARD_ASK]);
  click(c, elem({ dpdecide: "p-bb22", dpok: "1" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide, [], "the first click answers nothing");
  assert.strictEqual(c.dpS().confirm, "p-bb22", "it arms the ask");
  const armed = nowCard(c, [HARD_ASK]);
  assert.ok(armed.indexOf("Stamp, it leaves this machine") !== -1, "and says what it will do");
  click(c, elem({ dpdecide: "p-bb22", dpok: "1" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide, [{ pid: "p-bb22", ok: true }], "the second click answers");
  assert.strictEqual(c.dpS().confirm, null);
});

test("S21: Refuse on an irreversible ask needs one click, and a reversible Stamp needs one", async () => {
  const c = fresh();
  nowCard(c, [HARD_ASK, ASK]);
  click(c, elem({ dpdecide: "p-bb22", dpok: "0" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide, [{ pid: "p-bb22", ok: false }], "refusing is never armed");
  click(c, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide[1], { pid: "p-aa11", ok: true });
});

test("S21: moving to another card disarms an armed ask", () => {
  const c = fresh();
  nowCard(c, [HARD_ASK]);
  c.dpS().confirm = "p-bb22";
  click(c, elem({ dptab: "identity" }));
  assert.strictEqual(c.dpS().confirm, null);
});

/* ── S15 / TEST-PLAN component 39: the one branch inside 19-org2.js ── */
test("S15: a selected department paints the department screen, not the charter view", () => {
  const c = fresh();
  c.o2EnsureRegistered();
  const st = c.o2S();
  st.loaded = true; st.sel = "r4"; st.dept.r4 = DEPT_EXP;
  const html = c.o2ScreenHtml();
  assert.ok(/class="o2list dplist dp"/.test(html), "the department's own list column");
  assert.ok(html.indexOf("o2vb") !== -1 && html.indexOf('class="o2viewer dpviewer dp"') !== -1, "and its viewer");
  assert.ok(html.indexOf("Filed under this charter") === -1, "the charter facets are not painted");
  assert.ok(html.indexOf("o2facets") === -1);
});

test("S15: an organisation paints it too; the root and the machine keep the charter view", () => {
  const c = fresh();
  c.o2EnsureRegistered();
  const st = c.o2S();
  st.loaded = true; st.dept.r2 = DEPT_EXP; st.dept.r0 = DEPT_EXP; st.dept.r1 = DEPT_EXP;
  st.sel = "r2";
  assert.ok(/dplist/.test(c.o2ScreenHtml()), "an organisation is a department screen");
  st.sel = "r0"; st.view = "charter";
  assert.ok(!/dplist/.test(c.o2ScreenHtml()), "the root keeps the charter view");
  st.sel = "r1";
  assert.ok(!/dplist/.test(c.o2ScreenHtml()), "so does the machine");
});

test("S15: the department screen yields to a sheet and to the chart, doc, app and page views", () => {
  const c = fresh();
  c.o2EnsureRegistered();
  const st = c.o2S();
  st.loaded = true; st.sel = "r4"; st.dept.r4 = DEPT_EXP;
  st.view = "chart";
  assert.ok(!/dplist/.test(c.o2ScreenHtml()), "the chart is still the chart");
  st.view = "charter"; st.sheet = { kind: "rename", name: "x" };
  assert.ok(!/dplist/.test(c.o2ScreenHtml()), "a request sheet still opens over it");
});

test("S15: 19-org2.js gains exactly one delegating branch and no other department logic", () => {
  assert.strictEqual((o2Src.match(/dpListHtml/g) || []).length, 2, "named in the guard and in the branch");
  assert.strictEqual((o2Src.match(/dpViewerHtml/g) || []).length, 1);
  assert.ok(!/dpLoad|dpSelect|dpS\(\)|dpAskHtml/.test(o2Src), "no other department code leaks into 19-org2.js");
});

/* ── S22 / A31: tokens only, in the module and in its CSS block ── */
test("A31: 20-dept.js adds no colour literal", () => {
  const hits = dpSrc.split("\n").filter(l => /#[0-9a-fA-F]{3,6}\b/.test(l) && !/^\s*(\/\/|\*|\/\*)/.test(l));
  assert.deepStrictEqual(hits, [], "no literal colour in 20-dept.js");
});

test("S22/A31: the .dp CSS block exists, uses tokens only, and covers what the module emits", () => {
  const at = css.indexOf("/* department screen (20-dept.js");
  assert.ok(at !== -1, "the block is in panel.css");
  const block = css.slice(at);
  assert.deepStrictEqual(block.match(/#[0-9a-fA-F]{3,6}\b/g), null, "no colour literal in the block");
  for (const cls of [".dpg", ".dpli", ".dpq", ".dpcard", ".dprow", ".dpdot", ".dpchk",
                     ".dpask", ".dpask.hard", ".dpask.gone", ".dpasks", ".dpaskd",
                     ".dpbar", ".dpbar.hard", ".dpstamp"]) {
    assert.ok(block.indexOf(cls) !== -1, cls + " has a rule");
  }
  /* every class the module paints is either its own (styled above) or the Org
     screen's, which panel.css already carries */
  const emitted = new Set();
  (dpSrc.match(/class="([^"$]*)/g) || []).forEach(m => m.slice(7).split(/\s+/).forEach(x => { if (x) emitted.add(x); }));
  for (const cls of emitted) {
    if (!/^dp/.test(cls)) continue;
    if (cls === "dp" || cls === "dplist" || cls === "dpviewer" || cls === "dpmore" || cls === "dpgl") continue;
    assert.ok(block.indexOf("." + cls) !== -1, cls + " is painted but has no rule");
  }
});

Promise.all(pending).then(() => {
  console.log("\n" + (failed ? failed + " failed" : "all passed") + " (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
