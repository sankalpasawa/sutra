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

/* ── B1: the request writer's own words ───────────────────────────────────────
   A card paints an ask's summary VERBATIM -- the screen never rewrites a
   record's words -- so a fixture summary written by hand here proves nothing
   about what the owner reads. These templates are read out of org2_api.py's
   REQUEST_SUMMARIES, the one place the writer chooses those words, and every
   fixture below that stands for a filed ask is composed with them. A template
   that carries the word charter again therefore fails on the card that paints
   it. The other side of the pin is test_org2_api.py's
   test_request_summaries_are_screen_words_and_never_say_charter, which walks
   the live endpoint. */
const apiSrc = fs.readFileSync(path.join(__dirname, "org2_api.py"), "utf8");
const WRITER = (() => {
  const block = /REQUEST_SUMMARIES\s*=\s*\{([\s\S]*?)\n\}/.exec(apiSrc);
  if (!block) throw new Error("org2_api.py no longer holds a REQUEST_SUMMARIES table");
  const out = {};
  const re = /"([a-z.]+)"\s*:\s*"([^"]*)"/g;
  let m;
  while ((m = re.exec(block[1]))) out[m[1]] = m[2];
  if (!Object.keys(out).length) throw new Error("REQUEST_SUMMARIES parsed empty");
  return out;
})();
function writerSummary(key, ...names){
  const t = WRITER[key];
  if (!t) throw new Error("the request writer has no " + key + " summary");
  let i = 0;
  const said = t.replace(/%s/g, () => names[i++]);
  if (i !== names.length) throw new Error(key + " takes " + i + " names, not " + names.length);
  return said;
}

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
  /* three for Now, and three the LIST COLUMN itself needs: a state word per
     engine (A18), a version count per filed row (A24) and the people's names
     (A25) are all painted in the column, so the column reads them. The pin
     moved 3 -> 4 in slice D and 4 -> 7 in slice E; dpSelect still costs
     exactly three (S14, S39), which is what opening a department costs.
     The seventh is not this module's: Apps is the ORG screen's own loader,
     called rather than re-asked (A26), and that call is the one the Org
     screen's own column makes for the same department (19-org2.js:639-641). */
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/engines", "/api/dept/r4/filed", "/api/dept/r4/now",
     "/api/dept/r4/people", "/api/dept/r4/running", "/api/dept/r4/waits",
     "/api/modules?subtree=0&department=r4"]);
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

/* Identity was that card until slice B built it, and Adaptation until slice C.
   Every function card is built now, so what this pins is the state BEFORE its
   read lands: a skeleton under the right title, never a guess and never help. */
const FUNCS = [["identity", "Identity"], ["adaptation", "Adaptation"], ["priority", "Priority"],
               ["coordination", "Coordination"], ["audit", "Audit"]];
test("S17: a function card whose read has not landed shows a skeleton under its own title", () => {
  for (const [tab, label] of FUNCS){
    const c2 = fresh();
    const d = c2.o2Data(), n = d.byRef.get("r4");
    c2.dpS().sel = "r4"; c2.dpS().tab.r4 = tab;
    const view = c2.dpViewerHtml(n, d, DEPT_EXP, null);
    assert.ok(view.indexOf("<b>" + label + "</b>") !== -1, label + " names its own card");
    assert.ok(/o2skel/.test(view), label + ": a skeleton, not a guess");
    assert.ok((view.match(/o2quiet dpq/g) || []).length === 0, label + ": nothing quiet yet");
    assert.ok(!/help|Help/.test(view), label + ": A28 no help text");
  }
});

/* ── S18 / A4, A5: the ask card ── */
function nowCard(c, asks, seed){
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "now";
  st.now = { ref: "r4", asks: asks, decidable: true };
  st.running = { ref: "r4", running: [] };
  st.waits = { ref: "r4", waits: [] };
  Object.assign(st, seed || {});
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

/* ── slice B: Identity, its three tabs and the chat every card reuses ── */
const IDENTITY = {
  goal: "Own the operator's experience of Sutra Desktop.",
  done: "Every screen reads its own record.",
  rules: [{ tag: "always", text: "A mock is the app's own markup" },
          { tag: "always", text: "Never a third AI in one task" }],
  budget: { running_at_once: 4, ceiling: 20, turn_budget: { task: 12 } },
  owner: { source: "git", name: "Sankalp Asawa" },
  chats: {
    owner: [
      { who: "Identity", to: "Sankalp Asawa", mode: "say", line: "Write the goal of Org",
        at: "2026-09-21T09:01:04+05:30", row: { id: "p-aa11", kind: "org.charter", status: "pending" } },
      { who: "Identity", to: "", mode: "think", line: "Went ahead without asking: Bash",
        at: "", row: { ts: 100, tool: "Bash", pattern: "/Users/x/**", decision: "allow" } },
    ],
    adaptation: [
      { who: "Adaptation", to: "Identity", mode: "say", line: "Pause the nightly sweep",
        at: "2026-09-21T10:12:00+05:30", row: { id: "p-bb22", kind: "routine.update", status: "rejected" } },
      { who: "Identity", to: "Adaptation", mode: "say", line: "Refused.",
        at: "2026-09-21T10:20:00+05:30", row: { id: "p-bb22", kind: "routine.update", status: "rejected" } },
    ],
  },
};
const BARE_ID = { goal: null, done: null, rules: [],
                  budget: { running_at_once: null, ceiling: 20, turn_budget: {} },
                  owner: { source: "none", name: null }, chats: { owner: [], adaptation: [] } };

function idCard(c, id, pane){
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "identity";
  st.identity = Object.assign({ ref: "r4" }, id);
  if (pane) st.pane["r4:identity"] = pane;
  const d = c.o2Data();
  return c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
}

/* ── S24: the loader ── */
test("S24: Identity is read when its card opens, not when the department does", async () => {
  const c = fresh();
  c.dpSelect("r4");
  await sleep();
  assert.strictEqual(c.calls.apiGet.indexOf("/api/dept/r4/identity"), -1, "opening costs three reads");
  const d = c.o2Data();
  c.dpS().tab.r4 = "identity";
  c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/identity") !== -1, "the card reads it");
  c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  await sleep();
  assert.strictEqual(c.calls.apiGet.filter(p => /identity/.test(p)).length, 1,
    "a repaint is not a second read");
});

test("S24: before the read lands the card shows a skeleton, and a failure says so", () => {
  const c = fresh();
  const d = c.o2Data();
  c.dpS().sel = "r4"; c.dpS().tab.r4 = "identity";
  assert.ok(/o2skel/.test(c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null)));
  c.dpS().error.identity = "Sutra did not answer";
  const html = c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(html.indexOf("Could not read") !== -1);
  assert.ok(!/help|Help/.test(html));
});

/* ── S25 / A10: the card ── */
test("S25/A10: the card carries goal, done line, tagged rules, the budget bar and the owner", () => {
  const c = fresh();
  const html = idCard(c, IDENTITY);
  assert.ok(html.indexOf("<b>Identity</b>") !== -1, "the viewer is Identity");
  assert.ok(html.indexOf("Own the operator&quot;s experience of Sutra Desktop.") !== -1
         || html.indexOf("Own the operator's experience of Sutra Desktop.") !== -1, "the goal");
  assert.ok(html.indexOf("Every screen reads its own record.") !== -1, "the done line");
  assert.ok(html.indexOf("A mock is the app&quot;s own markup") !== -1
         || html.indexOf("A mock is the app's own markup") !== -1, "the first rule");
  assert.strictEqual((html.match(/class="dptag /g) || []).length, 2, "one tag per rule");
  assert.ok(/class="dpbar"><i style="width:20%"/.test(html), "the budget is a bar out of the ceiling");
  assert.ok(html.indexOf("Turns set for task") !== -1, "and names the kinds that carry one");
  assert.ok(html.indexOf(">Sankalp Asawa<") !== -1, "the owner is a name");
  assert.ok(html.indexOf("Rules") !== -1 && html.indexOf("Budget") !== -1 && html.indexOf("Owner") !== -1);
  assert.ok(html.indexOf("/Users/") === -1, "A28: no path");
  assert.ok(!/help|Help|How to|Learn/.test(html), "A28: no help text");
  assert.ok(!/>\s*\d+\s*</.test(html), "A28: no raw count at rest");
});

test("S25: each rule tag paints its own token class, and an unknown tag falls back to always", () => {
  const c = fresh();
  const html = idCard(c, Object.assign({}, IDENTITY, { rules: [
    { tag: "go", text: "one" }, { tag: "ask", text: "two" },
    { tag: "refuse", text: "three" }, { tag: "always", text: "four" },
    { tag: "shout", text: "five" }] }));
  for (const t of ["go", "ask", "refuse", "always"]) {
    assert.ok(html.indexOf(`class="dptag ${t}"`) !== -1, t + " has its own tag");
  }
  assert.strictEqual((html.match(/class="dptag always"/g) || []).length, 2, "an unknown tag reads always");
});

/* DS-1 / A35: the four words are the charter's own, so a refuse reads as a
   refuse. The route decides which record they came from; the card only paints
   the tag it was handed. */
test("S-G/A35: rules that arrive with their own tags are painted with them, never flattened to always", () => {
  const c = fresh();
  const html = idCard(c, Object.assign({}, IDENTITY, { rules: [
    { tag: "refuse", text: "Never a third AI in one task" },
    { tag: "ask", text: "Ask before a push" },
    { tag: "go", text: "Ship a patch without asking" }] }));
  assert.ok(/class="dptag refuse"[^<]*>refuse</.test(html), "refuse wears its own word");
  assert.ok(/class="dptag ask"[^<]*>ask</.test(html) && /class="dptag go"[^<]*>go</.test(html));
  assert.strictEqual((html.match(/class="dptag always"/g) || []).length, 0, "nothing is flattened");
  assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, "A29");
});

test("S25: a department with nothing written says one quiet line per cell, never a zero", () => {
  const c = fresh();
  const html = idCard(c, BARE_ID);
  for (const line of ["No goal yet", "No done line yet", "No rules yet", "No reading yet", "No owner yet"]) {
    assert.ok(html.indexOf(line) !== -1, line);
  }
  assert.ok(html.indexOf("dpbar") === -1, "A11: no reading is not a bar at zero");
});

/* ── S26 / A10: the three tabs ── */
test("S26/A10 + DS-13: two tabs — Identity and Chat, in that order", () => {
  const c = fresh();
  c.localStorage = memStore();
  const html = idCard(c, IDENTITY);
  const panes = (html.match(/data-dppane="([a-z]+)"/g) || []).map(m => /"([a-z]+)"/.exec(m)[1]);
  assert.deepStrictEqual(panes, ["identity", "chat"], "the card, then the chat");
  assert.ok(html.indexOf(">With Sankalp Asawa<") === -1, "no per-person tab any more");
  assert.ok(html.indexOf(">With Adaptation<") === -1);
  assert.ok(html.indexOf(">Log<") === -1, "the Log tab is gone");
  assert.ok(/aria-pressed="true" data-dppane="identity"/.test(html), "Identity is the open one");
  assert.ok(html.indexOf("Write the goal of Org") !== -1, "the owner's turns are on the card, as Recent");
});

test("S26: with no owner the card still opens, and its chat is offered by name", () => {
  const c = fresh();
  c.localStorage = memStore();
  const html = idCard(c, BARE_ID);
  assert.ok(html.indexOf(">Chat<") !== -1, "the chat tab is there");
  const chat = idCard(fresh(), BARE_ID, "chat");
  assert.ok(chat.indexOf("Start the chat with Identity") !== -1);
});

test("S26: a tab click switches the pane, and only inside .dp", () => {
  const c = fresh();
  idCard(c, IDENTITY);
  assert.strictEqual(click(c, elem({ dppane: "owner" })), true);
  assert.strictEqual(c.dpS().pane["r4:identity"], "owner");
  click(c, elem({ dppane: "adaptation" }, ".o2"));
  assert.strictEqual(c.dpS().pane["r4:identity"], "owner", "scoped to .dp");
});

test("S26: opening another department forgets which tab was open", async () => {
  const c = fresh();
  idCard(c, IDENTITY);
  c.dpS().pane["r4:identity"] = "owner"; c.dpS().chatMode["r4:owner"] = "exact";
  c.dpSelect("r5");
  await sleep();
  assert.deepStrictEqual(Object.keys(c.dpS().pane), []);
  assert.deepStrictEqual(Object.keys(c.dpS().chatMode), []);
});

/* ── S27 / A12: no goal yet ── */
test("S27/A12: a department with nothing written says No goal yet and offers one click", () => {
  const c = fresh();
  const html = idCard(c, BARE_ID);
  assert.ok(html.indexOf("No goal yet") !== -1);
  assert.strictEqual((html.match(/data-dpgoal/g) || []).length, 1, "exactly one action");
  assert.ok(html.indexOf(">Write the goal<") !== -1);
  assert.ok(html.toLowerCase().indexOf("charter") === -1, "A12: the word is not on the card");
});

test("S27: the click opens the Org screen's own write-it sheet and posts nothing itself", async () => {
  const opened = [];
  const c = fresh();
  c.o2OpenSheet = (kind) => { opened.push(kind); };
  idCard(c, BARE_ID);
  assert.strictEqual(click(c, elem({ dpgoal: "1" })), true);
  await sleep();
  assert.deepStrictEqual(opened, ["charter"], "the existing ask, not a second one");
  assert.deepStrictEqual(c.calls.apiPost, [], "this screen files no write of its own");
});

test("S27: a card with a goal offers no write-it action", () => {
  const c = fresh();
  assert.ok(idCard(c, IDENTITY).indexOf("data-dpgoal") === -1);
});

/* ── S29 / S31 / A17: the chat component ── */
test("S29/A17: Summary renders one line per row — who, to whom, the line", () => {
  const c = fresh();
  const html = c.dpChatHtml(IDENTITY.chats.adaptation, "summary");
  assert.strictEqual((html.match(/class="dpmsg/g) || []).length, 2, "one line per row");
  assert.ok(html.indexOf("Adaptation to Identity") !== -1, "who, to whom");
  assert.ok(html.indexOf("Pause the nightly sweep") !== -1, "the line");
  assert.ok(html.indexOf(">10:12<") !== -1, "the record's own clock time");
  assert.ok(html.indexOf("dpexact") === -1, "no raw rows in Summary");
});

test("S31/A17: Exact renders each raw row as JSON inside one pre", () => {
  const c = fresh();
  const html = c.dpChatHtml(IDENTITY.chats.adaptation, "exact");
  assert.strictEqual((html.match(/<pre class="dpexact">/g) || []).length, 1);
  assert.ok(html.indexOf("&quot;kind&quot;: &quot;routine.update&quot;") !== -1,
    "the record itself, two-space indented");
  assert.ok(html.indexOf("dpmsg") === -1, "Exact is not the Summary");
});

test("S29: a thinking turn addresses nobody and carries its own class", () => {
  const c = fresh();
  const html = c.dpChatHtml(IDENTITY.chats.owner, "summary");
  assert.ok(/class="dpmsg think"/.test(html), "a judgment taken alone reads differently");
  const think = html.slice(html.indexOf('class="dpmsg think"'));
  assert.ok(/class="dpwho">Identity</.test(think), "it is addressed to nobody");
  assert.ok(html.indexOf("Went ahead without asking: Bash") !== -1);
  assert.ok(html.indexOf("/Users/") === -1, "A28: the matched pattern stays in the raw row");
});

test("S29: an empty chat is one quiet line", () => {
  const c = fresh();
  const html = c.dpChatHtml([], "summary");
  assert.ok(html.indexOf("Nothing yet.") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1);
  assert.ok(c.dpChatHtml(null, "exact").indexOf("Nothing yet.") !== -1, "so is Exact");
  assert.ok(c.dpChatHtml(undefined, "summary").indexOf("Nothing yet.") !== -1);
});

test("S29: a row with no time and no addressee still renders", () => {
  const c = fresh();
  const html = c.dpChatHtml([{ who: "Identity", to: "", mode: "say", line: "A line", at: "", row: {} }], "summary");
  assert.ok(html.indexOf("A line") !== -1);
  assert.ok(html.indexOf('<span class="dpat"></span>') !== -1, "an empty clock, not a guess");
});

/* ── S30: the chat tabs on the Identity card ── */
test("S30/A17 + DS-13: Recent on the Identity card carries both records, in summary only", () => {
  const c = fresh();
  c.localStorage = memStore();
  const html = idCard(c, IDENTITY);
  assert.ok(html.indexOf("<h3>Recent</h3>") !== -1, "the card's own section");
  assert.ok(html.indexOf("Write the goal of Org") !== -1, "the owner's turns");
  assert.ok(html.indexOf("Pause the nightly sweep") !== -1, "and Adaptation's, in one place");
  assert.strictEqual((html.match(/data-dpchatmode=/g) || []).length, 0, "no Summary / Exact control");
  assert.strictEqual(html.indexOf("dpexact"), -1, "and no raw rows on a function card");
});


test("S30 + A33: a department with nothing written shows no Recent at all", () => {
  const c = fresh();
  c.localStorage = memStore();
  const html = idCard(c, BARE_ID);
  assert.strictEqual(html.indexOf("<h3>Recent</h3>"), -1, "an empty Recent is not drawn");
  assert.ok(html.indexOf("dpmsg") === -1);
  assert.ok(html.indexOf("No goal yet") !== -1, "the card's own line is the one quiet line");
});

/* ── S32 / A29, R5: the words on the screen ── */
test("S32/A29: every word on these screens is from the D78 list", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const list = c.dpListHtml(n, d, DEPT_EXP, null);
  const card = idCard(c, IDENTITY);
  const owner = idCard(c, IDENTITY, "log");
  const all = list + card + owner;
  /* "work item" is slice D's, on the engine card; every other word the PRD's
     D78 list names is on screen by the end of slice B. */
  for (const w of ["department", "Now", "Identity", "Adaptation", "Priority", "Coordination",
                   "Audit", "Engines", "Filed work", "People", "Documents", "Apps",
                   "Rules", "Budget", "Owner"]) {
    assert.ok(all.indexOf(w) !== -1, "missing screen word: " + w);
  }
  for (const w of ["cut", "seam", "overlay", "cascade"]) {
    assert.ok(new RegExp("\\b" + w + "\\b", "i").test(all) === false, "off-list word: " + w);
  }
});


/* B1, the bug the acceptance walk found: the fixture is not hand-written. Every
   summary the request writer can compose is put on the Now card the way a filed
   ask reaches it, and read back. A29 as amended: the word reaches a card only
   when a RECORD's own words carry it -- the screen never composes it. */
test("S32/A29/B1: no summary the request writer composes carries the word charter", () => {
  const keys = Object.keys(WRITER);
  assert.ok(keys.length >= 5, "the writer holds its five shapes: " + keys.join(", "));
  const said = keys.map(k => writerSummary.apply(null,
    [k].concat(new Array((WRITER[k].match(/%s/g) || []).length).fill("Doctrine"))));
  for (const s of said) assert.strictEqual(s.toLowerCase().indexOf("charter"), -1, "the writer: " + s);
  const c = fresh();
  const html = nowCard(c, said.map((s, i) => Object.assign({}, ASK, { id: "p-w" + i, summary: s })));
  for (const s of said) assert.ok(html.indexOf(s) !== -1, "painted verbatim: " + s);
  assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, "and none of them says it");
});

/* The other half of the amended A29: a record whose OWN words carry it is still
   painted verbatim -- the screen rewrites nothing. */
test("S32/A29/B1: a record that says it itself is still painted as written", () => {
  const c = fresh();
  const own = "Edit the charter of Doctrine";     /* an old row, filed before B1 */
  const html = nowCard(c, [Object.assign({}, ASK, { summary: own })]);
  assert.ok(html.indexOf(own) !== -1, "the card never rewrites a record's words");
});

/* ── slice C: Adaptation, Priority, Coordination, Audit and their chats ── */
const DAY = 24 * HOUR;
const ADAPTATION = {
  proposals: [
    { id: "p-aa11", change: "Pause the nightly sweep", evidence: "Asked 3 times in seven days",
      state: "Waits.", open: true, created_ms: Date.now() - HOUR, window_ms: 24 * HOUR,
      row: { id: "p-aa11", kind: "routine.update", status: "pending" } },
    /* B1: composed by the request writer, not by hand -- this is the very row
       the acceptance walk read the word charter off (ACCEPTANCE B1) */
    { id: "p-bb22", change: writerSummary("goal.edit", "Org"), evidence: "", state: "Refused.",
      open: false, created_ms: Date.now() - 3 * DAY, window_ms: 24 * HOUR,
      row: { id: "p-bb22", kind: "org.charter", status: "rejected" } },
  ],
  patterns: [{ kind: "routine.update", summary: "Pause the nightly sweep", count: 3,
               since_ms: Date.now() - 5 * DAY }],
  chat: [{ who: "Adaptation", to: "Identity", mode: "say", line: "Pause the nightly sweep",
           at: "2026-09-21T10:12:00+05:30", row: { id: "p-aa11", kind: "routine.update" } }],
};
const PRIORITY = {
  queue: [{ next: "Land the department screen", runs_as: "claude-opus-5",
            when_ms: Date.now() - HOUR, row: { SESSION: "s-1", TOUCHES: "/Users/x/a" } },
          { next: "Land the list column", runs_as: "claude-sonnet-5",
            when_ms: Date.now() - 3 * DAY, row: { SESSION: "s-2" } }],
  class: "3", model: "claude-opus-5",
  budget: { running_at_once: 4, ceiling: 20, turn_budget: { task: 12 } },
  chat: [{ who: "Priority", to: "Coordination", mode: "say",
           line: "Admitted: Land the department screen. Runs as claude-opus-5.",
           at: "2026-09-21T09:00:00+05:30", row: { SESSION: "s-1" } }],
};
const COORD = {
  held: [{ resource: "Nightly sweep", holder: "Its own run", since_ms: Date.now() - HOUR,
           row: { id: "rt-1" } }],
  handoffs: [{ from: "Org", to: "Experience", what: "HLD", ts_ms: Date.now() - 3 * DAY,
               row: { id: "PL-1", supersedes: "PL-0" } }],
  chat: [{ who: "Coordination", to: "Priority", mode: "say",
           line: "Nightly sweep held by its own run.", at: "", row: { id: "rt-1" } }],
};
const AUDIT = {
  findings: [
    { id: "f-2", check: "C17", claim: "sessionstart audit emits on stderr",
      record: "Still open.", dot: "block", first_seen: "2026-09-01", last_seen: "2026-09-20",
      row: { id: "f-2", text: "sutra/marketplace/plugin/hooks/sessionstart-audit.sh emits" } },
    { id: "f-1", check: "C5", claim: "overdue promotion dates in holding hooks",
      record: "judged a measurement artifact", dot: "warn",
      first_seen: "2026-08-04", last_seen: "2026-09-18", row: { id: "f-1" } },
  ],
  unseen: [{ claim: "sessionstart audit emits on stderr", since: "2026-09-01",
             row: { id: "f-2" } }],
  chat: [{ who: "Audit", to: "Priority", mode: "say",
           line: 'Flag: claimed "sessionstart audit emits on stderr"; the record says Still open.',
           at: "2026-09-20",
           row: { id: "f-2", text: "sutra/marketplace/plugin/hooks/sessionstart-audit.sh emits" } }],
};
/* one plain fragment of each function's chat, free of the quotes an Exact row
   escapes, so a Summary can be looked for by eye the way a reader would */
const CHAT_SAYS = { adaptation: "Pause the nightly sweep",
                    priority: "Admitted: Land the department screen",
                    coordination: "held by its own run",
                    audit: "the record says Still open" };
const EMPTY = { adaptation: { proposals: [], patterns: [], chat: [] },
                priority: { queue: [], class: null, model: null,
                            budget: { running_at_once: null, ceiling: 20, turn_budget: {} }, chat: [] },
                coordination: { held: [], handoffs: [], chat: [] },
                audit: { findings: [], unseen: [], chat: [] } };

/* Open one function card with its read already landed. */
function fnCard(c, tab, data, pane, seed){
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = tab;
  st[tab] = Object.assign({ ref: "r4" }, data);
  if (pane) st.pane["r4:" + tab] = pane;
  Object.assign(st, seed || {});
  const d = c.o2Data();
  return c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
}

/* ── S39: the four loaders ── */
test("S39: each function card reads its own route, when it opens and not before", async () => {
  const c = fresh();
  c.dpSelect("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/now", "/api/dept/r4/running", "/api/dept/r4/waits"],
    "opening a department still costs three reads");
  const d = c.o2Data(), n = d.byRef.get("r4");
  for (const [tab] of FUNCS.slice(1)){
    c.dpS().tab.r4 = tab;
    c.dpViewerHtml(n, d, DEPT_EXP, null);
    await sleep();
    assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/" + tab) !== -1, tab + " is read on open");
    c.dpViewerHtml(n, d, DEPT_EXP, null);
    await sleep();
    assert.strictEqual(c.calls.apiGet.filter(p => p === "/api/dept/r4/" + tab).length, 1,
      tab + ": a repaint is not a second read");
  }
});

test("S39: two overlapping reads of one function make exactly one network call", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadAdaptation("r4"); c.dpLoadAdaptation("r4");
  c.dpLoadPriority("r4"); c.dpLoadCoordination("r4"); c.dpLoadAudit("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/adaptation", "/api/dept/r4/audit",
     "/api/dept/r4/coordination", "/api/dept/r4/priority"]);
});

test("S39: a failed read says so under the card's own title, never a guess", () => {
  for (const [tab, label] of FUNCS.slice(1)){
    const c = fresh();
    const d = c.o2Data();
    c.dpS().sel = "r4"; c.dpS().tab.r4 = tab; c.dpS().error[tab] = "Sutra did not answer";
    const html = c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
    assert.ok(html.indexOf("<b>" + label + "</b>") !== -1, label);
    assert.ok(html.indexOf("Could not read") !== -1, label + ": it says so");
  }
});

/* ── S40 / A13: Adaptation ── */
test("S40/A13: Adaptation shows what it wants changed, the asking behind it, and the offer", () => {
  const c = fresh();
  const html = fnCard(c, "adaptation", ADAPTATION);
  assert.ok(html.indexOf("<b>Adaptation</b>") !== -1);
  assert.ok(html.indexOf("Proposals") !== -1 && html.indexOf("Seen in the logbook") !== -1);
  assert.ok(html.indexOf("Pause the nightly sweep") !== -1, "the change");
  assert.ok(html.indexOf("Asked 3 times in seven days · Waits.") !== -1, "evidence and state");
  assert.ok(html.indexOf("Refused.") !== -1, "a decided change says so");
  assert.ok(/class="dpbar"><i style="width:9[0-9.]+%"/.test(html), "an open change carries its window");
  assert.strictEqual((html.match(/class="dpbar"/g) || []).length, 1, "and a decided one does not");
  assert.ok(/Since \d+ [A-Z][a-z]{2}/.test(html), "the pattern says since when");
  assert.strictEqual((html.match(/data-dprule/g) || []).length, 1, "exactly one action");
  assert.ok(html.indexOf(">Change a rule<") !== -1);
  assert.ok(html.toLowerCase().indexOf("charter") === -1, "A29: not the word on the card");
  assert.ok(html.indexOf("/Users/") === -1, "A28: no path");
  assert.ok(!/help|Help|How to|Learn/.test(html), "A28: no help text");
});

test("S40: the offer opens the Org screen's own write-it sheet and posts nothing itself", async () => {
  const opened = [];
  const c = fresh();
  c.o2OpenSheet = (kind) => { opened.push(kind); };
  fnCard(c, "adaptation", ADAPTATION);
  assert.strictEqual(click(c, elem({ dprule: "1" })), true);
  await sleep();
  assert.deepStrictEqual(opened, ["charter"], "the existing ask, not a second one");
  assert.deepStrictEqual(c.calls.apiPost, [], "this screen files no write of its own");
  click(c, elem({ dprule: "1" }, ".o2"));
  await sleep();
  assert.strictEqual(opened.length, 1, "scoped to .dp");
});

/* ── S41 / A14: Priority ── */
test("S41/A14: Priority shows the queue — next, what it runs as, when — and one budget bar", () => {
  const c = fresh();
  const html = fnCard(c, "priority", PRIORITY);
  assert.ok(html.indexOf("<b>Priority</b>") !== -1);
  assert.ok(html.indexOf("Queue") !== -1 && html.indexOf("Budget") !== -1);
  assert.ok(html.indexOf("Land the department screen") !== -1, "next");
  assert.ok(html.indexOf("Runs as claude-opus-5 · ") !== -1, "what it runs as, and when");
  assert.ok(html.indexOf("Land the list column") !== -1, "the row behind it");
  assert.strictEqual((html.match(/class="dpbar"/g) || []).length, 1, "the budget is ONE bar");
  assert.ok(/class="dpbar"><i style="width:20%"/.test(html), "out of the ceiling");
  assert.ok(html.indexOf("Turns set for task") !== -1);
  assert.ok(html.indexOf("/Users/") === -1, "A28: the touches stay in the raw row");
  assert.ok(!/>\s*\d+\s*</.test(html), "A28: no raw count at rest");
});

test("S41/A11: a department with no queue and no budget reading is one quiet line", () => {
  const c = fresh();
  const html = fnCard(c, "priority", EMPTY.priority);
  assert.ok(html.indexOf("Nothing in the queue") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, "one line, not two");
  assert.ok(html.indexOf("dpbar") === -1, "A11: no reading is not a bar at zero");
});

/* ── S42 / A15: Coordination ── */
test("S42/A15: Coordination shows the live board, who holds what since when, and the last hand-off", () => {
  const c = fresh();
  const html = fnCard(c, "coordination", COORD, null,
    { running: { ref: "r4", running: RUNNING } });
  assert.ok(html.indexOf("<b>Coordination</b>") !== -1);
  assert.ok(html.indexOf("Live board") !== -1 && html.indexOf("Locks") !== -1
         && html.indexOf("Hand-offs") !== -1);
  assert.ok(html.indexOf("Land the department screen") !== -1, "the running row");
  assert.ok(html.indexOf("Nightly sweep") !== -1, "what is held");
  assert.ok(/Its own run · since \d/.test(html), "by whom, since when");
  assert.ok(html.indexOf("Org to Experience") !== -1, "the hand-off, from and to");
  assert.ok(html.indexOf(">HLD") !== -1, "and what changed hands");
  assert.ok(html.indexOf("/Users/") === -1, "A28: no path");
});

test("S42: only the LAST hand-off is on the card", () => {
  const c = fresh();
  const two = Object.assign({}, COORD, { handoffs: [
    COORD.handoffs[0],
    { from: "Experience", to: "Org", what: "PRD", ts_ms: Date.now() - 9 * DAY, row: {} }] });
  const html = fnCard(c, "coordination", two);
  assert.ok(html.indexOf(">HLD") !== -1);
  assert.ok(html.indexOf(">PRD") === -1, "the chain behind it belongs to the Chat tab");
});

test("S42: nothing running, nothing held, nothing handed over is one quiet line", () => {
  const c = fresh();
  const html = fnCard(c, "coordination", EMPTY.coordination);
  assert.ok(html.indexOf("Nothing held") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, "one line, not three");
  assert.ok(html.indexOf("dpcard") === -1, "no empty Live board / Locks / Hand-offs cards");
});

/* ── S43 / A16: Audit ── */
test("S43/A16: Audit lists a claim, what the record says, and a dot — never a score", () => {
  const c = fresh();
  const html = fnCard(c, "audit", AUDIT);
  assert.ok(html.indexOf("<b>Audit</b>") !== -1);
  assert.ok(html.indexOf("Checks") !== -1 && html.indexOf("Never looked at") !== -1);
  assert.ok(html.indexOf("sessionstart audit emits on stderr") !== -1, "the claim");
  assert.ok(html.indexOf("judged a measurement artifact") !== -1, "what the record says");
  assert.ok(html.indexOf('class="dpdot block"') !== -1, "severity is a dot");
  assert.ok(html.indexOf('class="dpdot warn"') !== -1);
  assert.ok(html.indexOf("%") === -1, "A16: no share");
  assert.ok(html.indexOf("dpbar") === -1, "A16: no meter on a check");
  assert.ok(!/>\s*\d+\s*</.test(html), "A16: no total");
  assert.ok(html.indexOf("open since 1 Sep") !== -1, "never looked at says since when");
  assert.ok(html.indexOf("/Users/") === -1 && html.indexOf("marketplace/plugin") === -1,
    "A28: the path stays in the raw row");
});

test("S43: the checks arrive in the order the route gave them, newest first", () => {
  const c = fresh();
  const html = fnCard(c, "audit", AUDIT);
  assert.ok(html.indexOf("sessionstart audit emits on stderr")
          < html.indexOf("overdue promotion dates"), "newest first, as read");
});

test("S43/A16: a department no check has named is one quiet line", () => {
  const c = fresh();
  const html = fnCard(c, "audit", EMPTY.audit);
  assert.ok(html.indexOf("No check has run here") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1);
  assert.ok(html.indexOf("dpcard") === -1);
});

/* ── S44 / A17: the Chat tab on all four ── */
test("S44/A17 + DS-13: every function card is two tabs, and its turns are Recent on the card", () => {
  const DATA = { adaptation: ADAPTATION, priority: PRIORITY, coordination: COORD, audit: AUDIT };
  for (const [tab, label] of FUNCS.slice(1)){
    const c = fresh();
    c.localStorage = memStore();
    const card = fnCard(c, tab, DATA[tab]);
    const panes = (card.match(/data-dppane="([a-z]+)"/g) || []).map(m => /"([a-z]+)"/.exec(m)[1]);
    assert.deepStrictEqual(panes, [tab, "chat"], label + ": its own tab, then Chat");
    assert.ok(new RegExp('aria-pressed="true" data-dppane="' + tab + '"').test(card),
      label + " is the open one");
    assert.strictEqual((card.match(/data-dpchatmode=/g) || []).length, 0, label + ": no Summary / Exact");
    assert.ok(card.indexOf(CHAT_SAYS[tab]) !== -1, label + ": the turns its own route wrote, as Recent");
    assert.ok(card.indexOf("<h3>Recent</h3>") !== -1, label + ": under one heading");
  }
});


test("S44: switching one function's chat mode leaves the others alone", () => {
  const c = fresh();
  fnCard(c, "adaptation", ADAPTATION, "log");
  assert.strictEqual(click(c, elem({ dpchatmode: "exact", dpchatkey: "r4:adaptation:chat" })), true);
  assert.strictEqual(c.dpS().chatMode["r4:adaptation:chat"], "exact");
  assert.strictEqual(c.dpS().chatMode["r4:audit:chat"], undefined);
  assert.ok(fnCard(c, "audit", AUDIT, "chat").indexOf("dpexact") === -1);
});

/* ── S45: the empty states, one quiet line each ── */
test("S45: a department with nothing anywhere says one quiet line per function", () => {
  const lines = { adaptation: "Nothing to change yet", priority: "Nothing in the queue",
                  coordination: "Nothing held", audit: "No check has run here" };
  for (const [tab, label] of FUNCS.slice(1)){
    const c = fresh();
    const html = fnCard(c, tab, EMPTY[tab]);
    assert.ok(html.indexOf(lines[tab]) !== -1, label + ": " + lines[tab]);
    assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, label + ": exactly one line");
    assert.ok(!/help|Help|How to|Learn/.test(html), label + ": A28 no help text");
    assert.ok(!/>\s*\d+\s*</.test(html), label + ": A28 no raw count at rest");
    assert.ok(html.toLowerCase().indexOf("charter") === -1, label + ": A29");
  }
});

test("S45: an empty function still offers what it can, and nothing it cannot", () => {
  const c = fresh();
  const adapt = fnCard(c, "adaptation", EMPTY.adaptation);
  assert.strictEqual((adapt.match(/data-dprule/g) || []).length, 1,
    "a rule can still be changed when nothing has been proposed");
  const audit = fnCard(fresh(), "audit", EMPTY.audit);
  assert.strictEqual((audit.match(/data-dp(rule|goal|decide|pause)/g) || []).length, 0,
    "a check nobody ran offers nothing but its own two tabs");
});

test("S45 + A33: an empty function card draws no Recent and keeps its one quiet line", () => {
  for (const [tab] of FUNCS.slice(1)){
    const c = fresh();
    c.localStorage = memStore();
    const html = fnCard(c, tab, EMPTY[tab]);
    assert.strictEqual(html.indexOf("<h3>Recent</h3>"), -1, tab);
    assert.ok(html.indexOf("dpmsg") === -1, tab);
    assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, tab + ": exactly one quiet line");
  }
});

test("S45: opening another department drops what all four answered", async () => {
  const c = fresh();
  fnCard(c, "audit", AUDIT);
  fnCard(c, "priority", PRIORITY);
  c.dpSelect("r5");
  await sleep();
  for (const k of ["adaptation", "priority", "coordination", "audit"]) {
    assert.strictEqual(c.dpS()[k], null, k + " is dropped");
  }
});

/* ── slice D: Engines (S53-S62) ──────────────────────────────────────────── */
const ENG_BORN = Date.parse("2026-08-01T09:00:00+05:30");
const ENGINES = { engines: [
  { id: "nightly", name: "Nightly sweep", state: "idle", enabled: true,
    cwd: "/Users/x/a", runs_as: "haiku", cadence: "Every day at 3:30 AM (local)",
    made_by: { from_ask: true, at: "2026-08-01T09:00:00+05:30", at_ms: ENG_BORN },
    needs: null, makes: ["LATEST"], read_by: null,
    workflow: { id: "W-sweep", title: "Sweep", goal: "sweep it", steps: [
      { id: "S1", name: "read the folder", produces: ["a list"], needs: [], verify: "the list exists" },
      { id: "S2", name: "file what changed", produces: ["LATEST"], needs: [], verify: "the row is filed" }] },
    prompt: "run W-sweep over the department" },
  { id: "hourly", name: "Teamsutra worker", state: "running", enabled: true,
    cwd: "/Users/x/a", runs_as: "sonnet", cadence: "Every hour at :20 (local)",
    made_by: { from_ask: false, at: "", at_ms: 0 },
    needs: null, makes: null, read_by: null, workflow: null,
    prompt: "claim the oldest queued task and return a diff" },
  { id: "off-one", name: "Weekly sweep", state: "paused", enabled: false,
    cwd: "/Users/x/a", runs_as: "", cadence: "",
    made_by: { from_ask: false, at: "", at_ms: 0 },
    needs: null, makes: null, read_by: null, workflow: null, prompt: "" },
] };
const ENG_RUNS = { id: "nightly", total: 3, unreadable: 0, never_run: false, runs: [
  { schema: 1, id: "nightly", trigger: "schedule", started_at: "2026-09-20T03:00:00+05:30",
    ended_at: "2026-09-20T03:04:00+05:30", duration_s: 240, outcome: "ok" },
  { schema: 1, id: "nightly", trigger: "manual", started_at: "2026-09-19T03:00:00+05:30",
    ended_at: "2026-09-19T03:40:00+05:30", duration_s: 2400, outcome: "failed" },
], chat: [{ who: "Nightly sweep", to: "Coordination", mode: "say",
            line: "On the schedule: done.", at: "2026-09-20T03:00:00+05:30",
            row: { id: "nightly", outcome: "ok" } }] };
const ENG_LIVE = { id: "hourly", total: 1, unreadable: 0, never_run: false, runs: [
  { schema: 1, id: "hourly", trigger: "schedule",
    started_at: new Date(Date.now() - 12 * 60000).toISOString(), outcome: "ok", duration_s: 0 },
], chat: [] };
const ENG_NEVER = { id: "off-one", total: 0, unreadable: 0, never_run: true, runs: [], chat: [] };
const ENG_DATA = { filed: [{ id: "PL-1", label: "LATEST", ts_ms: Date.now() - 3 * DAY,
                             row: { id: "PL-1", origin: "nightly" } }] };

/* Open the engine card with the engines read already landed. */
function engCard(c, pane, id, seed){
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "engines";
  st.engines = Object.assign({ ref: "r4" }, ENGINES);
  if (id) st.engineSel = id;
  if (pane) st.pane["r4:engines"] = pane;
  Object.assign(st, seed || {});
  const d = c.o2Data();
  return c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
}
function engList(c){
  const st = c.dpS();
  st.sel = "r4";
  st.engines = Object.assign({ ref: "r4" }, ENGINES);
  const d = c.o2Data();
  return c.dpListHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
}

/* ── S53: the three engine loaders ── */
test("S53: the engines read fires when the list column paints, once", async () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpListHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/engines") !== -1, "the column reads it");
  c.dpListHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.strictEqual(c.calls.apiGet.filter(p => /\/engines$/.test(p)).length, 1,
    "a repaint is not a second read");
});

test("S53: the runs and data reads fire when their pane opens, and not before", async () => {
  const c = fresh();
  engCard(c, null, "nightly");
  await sleep();
  assert.strictEqual(c.calls.apiGet.filter(p => /\/runs$/.test(p)).length, 0,
    "the Engine tab costs neither read");
  assert.strictEqual(c.calls.apiGet.filter(p => /\/data$/.test(p)).length, 0);
  engCard(c, "runs", "nightly");
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/engines/nightly/runs") !== -1);
  engCard(c, "data", "nightly");
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/engines/nightly/data") !== -1);
});

test("S53: each engine keeps its own rows, and two overlapping reads make one call", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadEngineRuns("r4", "nightly"); c.dpLoadEngineRuns("r4", "nightly");
  c.dpLoadEngineRuns("r4", "hourly");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/engines/hourly/runs", "/api/dept/r4/engines/nightly/runs"]);
});

test("S53: an engine answer for a department that is no longer open is dropped", async () => {
  let release;
  const c = fresh({ apiGet: () => new Promise(r => { release = r; }) });
  c.dpS().sel = "r4";
  const p = c.dpLoadEngineRuns("r4", "nightly");
  c.dpS().sel = "r5";
  release(ENG_RUNS);
  await p;
  assert.strictEqual(c.dpS().engineRuns.nightly, undefined, "the late answer is dropped");
});

/* ── S54: the Engines group ── */
test("S54: every engine is a row with its own state word", () => {
  const c = fresh();
  const list = engList(c);
  for (const [name, word] of [["Nightly sweep", "Idle"], ["Teamsutra worker", "Running"],
                              ["Weekly sweep", "Paused"]]) {
    assert.ok(list.indexOf(name) !== -1, name + " is a row");
    assert.ok(list.indexOf(">" + word + "<") !== -1, name + " says " + word);
  }
  assert.ok(/data-dpengine="nightly"/.test(list), "the row opens the engine");
  assert.ok(list.indexOf("/Users/") === -1, "A28: no path on the column");
});

test("S54: a department with no engines says so in one quiet line", () => {
  const c = fresh();
  const st = c.dpS();
  st.sel = "r4"; st.engines = { ref: "r4", engines: [] };
  const d = c.o2Data();
  const list = c.dpListHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(list.indexOf("No engines here") !== -1);
  assert.ok(list.indexOf("data-dpengine") === -1);
});

test("S54: clicking an engine row opens its card on the Engine tab", () => {
  const c = fresh();
  engList(c);
  click(c, elem({ dpengine: "hourly" }));
  assert.strictEqual(c.dpS().engineSel, "hourly");
  assert.strictEqual(c.dpS().tab.r4, "engines");
  c.dpS().pane["r4:engines"] = "runs";
  click(c, elem({ dpengine: "nightly" }));
  assert.strictEqual(c.dpS().pane["r4:engines"], "engines",
    "another engine opens on its own Engine tab");
});

/* ── S55: the five tabs ── */
test("S55: an engine card carries Engine, Workflow, Runs, Data and Chat", () => {
  const c = fresh();
  const view = engCard(c, null, "nightly");
  assert.ok(view.indexOf("<b>Nightly sweep</b>") !== -1, "the card is the engine");
  for (const [v, label] of [["engines", "Engine"], ["workflow", "Workflow"],
                            ["runs", "Runs"], ["data", "Data"], ["chat", "Chat"]]) {
    assert.ok(view.indexOf(`data-dppane="${v}">${label}<`) !== -1, label + " is a tab");
  }
  assert.ok(/aria-pressed="true" data-dppane="engines"/.test(view), "Engine is the open one");
});

test("S55: an engine card whose read has not landed shows a skeleton", () => {
  const c = fresh();
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "engines";
  const d = c.o2Data();
  const view = c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(/o2skel/.test(view), "a skeleton, not a guess");
  assert.ok(view.indexOf("<b>Engines</b>") !== -1, "the card names the group until one is picked");
});

/* ── S56: the Engine table ── */
test("S56: the Engine tab is one table of what the engine is", () => {
  const c = fresh();
  const view = engCard(c, null, "nightly");
  for (const k of ["Made by", "Runs as", "Cadence", "Needs", "Makes", "Read by"]) {
    assert.ok(view.indexOf(">" + k + "<") !== -1, k + " is a cell");
  }
  assert.ok(view.indexOf("From an ask, 1 Aug") !== -1, "A23: the birth line");
  assert.ok(view.indexOf("haiku") !== -1 && view.indexOf("Every day at 3:30 AM (local)") !== -1);
  assert.ok(view.indexOf("LATEST") !== -1, "what it makes");
  assert.strictEqual((view.match(/Not named/g) || []).length, 2,
    "what no record names is a quiet line, twice: needs and read by");
});

test("S56/A23: an engine nobody asked for reads Written", () => {
  const c = fresh();
  const view = engCard(c, null, "hourly");
  assert.ok(view.indexOf("Written") !== -1);
  assert.ok(view.indexOf("From an ask") === -1);
  assert.ok(view.indexOf("Not set") !== -1 || view.indexOf("Every hour") !== -1);
});

/* ── S57: the Workflow tab ── */
test("S57: the Workflow tab is the registered workflow's steps when one exists", () => {
  const c = fresh();
  const view = engCard(c, "workflow", "nightly");
  assert.ok(view.indexOf("read the folder") !== -1 && view.indexOf("file what changed") !== -1);
  assert.ok(view.indexOf("a list · the list exists") !== -1, "what a step makes and how it is checked");
  assert.ok(view.indexOf("dpdot ") === -1 || !/dpdot (ok|warn|block)/.test(view),
    "F-11: no progress is marked, because no run row carries a step");
});

test("S57: an engine with no registered workflow shows what it is told to do", () => {
  const c = fresh();
  const view = engCard(c, "workflow", "hourly");
  assert.ok(view.indexOf("claim the oldest queued task and return a diff") !== -1);
  assert.ok(view.indexOf("What it is told to do") !== -1);
});

test("S57: an engine with neither says so in one quiet line", () => {
  const c = fresh();
  const view = engCard(c, "workflow", "off-one");
  assert.ok(view.indexOf("No steps written yet") !== -1);
});

/* ── S58: the Runs tab ── */
test("S58: Runs is one line per execution row with its dot and its duration bar", () => {
  const c = fresh();
  const view = engCard(c, "runs", "nightly", { engineRuns: { nightly: Object.assign({ ref: "r4" }, ENG_RUNS) } });
  assert.ok(view.indexOf(">Done<") !== -1 && view.indexOf(">Failed<") !== -1);
  assert.ok(view.indexOf("20 Sep") !== -1 && view.indexOf("19 Sep") !== -1,
    "A20: when it started, as the DAY once the day is not today");
  assert.ok(/dpdot ok/.test(view) && /dpdot block/.test(view), "the outcome is a dot");
  assert.strictEqual((view.match(/dpbar/g) || []).length, 2, "one duration bar per run");
  assert.ok(view.indexOf("100%") !== -1, "the longest run fills its bar");
  assert.ok(!/>\s*\d+\s*</.test(view), "A28: no raw count at rest");
});

test("S58/A20: a live run reads Running with the time it has been going", () => {
  const c = fresh();
  const view = engCard(c, "runs", "hourly", { engineRuns: { hourly: Object.assign({ ref: "r4" }, ENG_LIVE) } });
  assert.ok(view.indexOf(">Running") !== -1, "the row says Running");
  assert.ok(/1[12]m so far/.test(view), "and how long it has been going");
  assert.ok(view.indexOf("dpbar") === -1, "a run that has not ended has no duration to draw");
});

test("S58: an engine that never ran says so, and a failed read says so", () => {
  const c = fresh();
  assert.ok(engCard(c, "runs", "off-one",
    { engineRuns: { "off-one": Object.assign({ ref: "r4" }, ENG_NEVER) } }).indexOf("Never run") !== -1);
  const c2 = fresh();
  assert.ok(engCard(c2, "runs", "nightly",
    { error: { "engineRuns:r4:nightly": "boom" } }).indexOf("Could not read") !== -1);
});

test("S58: the Chat tab reads the same run rows, as turns and as the rows themselves", () => {
  const c = fresh();
  const seed = { engineRuns: { nightly: Object.assign({ ref: "r4" }, ENG_RUNS) } };
  const summary = engCard(c, "chat", "nightly", seed);
  assert.ok(summary.indexOf("On the schedule: done.") !== -1, "the turn");
  assert.ok(summary.indexOf("dpmsg") !== -1);
  const c2 = fresh();
  const exact = engCard(c2, "chat", "nightly",
    Object.assign({ chatMode: { "r4:engines:chat": "exact" } }, seed));
  const at = exact.indexOf("&quot;outcome&quot;");
  assert.ok(exact.indexOf("dpexact") !== -1 && at !== -1, "Exact is the run row itself");
  assert.ok(exact.lastIndexOf('<pre class="dpexact">') < at && at < exact.indexOf("</pre>"),
    "and it sits inside the raw block");
  const c3 = fresh();
  assert.ok(engCard(c3, "chat", "off-one",
    { engineRuns: { "off-one": Object.assign({ ref: "r4" }, ENG_NEVER) } }).indexOf("Nothing yet.") !== -1);
});

/* ── S59: the Data tab ── */
test("S59: Data lists what the engine's runs filed, and says Nothing filed when none", () => {
  const c = fresh();
  const view = engCard(c, "data", "nightly",
    { engineData: { nightly: Object.assign({ ref: "r4" }, ENG_DATA) } });
  assert.ok(view.indexOf("LATEST") !== -1 && view.indexOf("Filed work") !== -1);
  const c2 = fresh();
  assert.ok(engCard(c2, "data", "hourly",
    { engineData: { hourly: { ref: "r4", filed: [] } } }).indexOf("Nothing filed") !== -1);
});

/* ── S60: Pause ── */
test("S60/A22: Pause posts the ask and nothing else, and the word does not move", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve(ENGINES); } });
  engCard(c, null, "nightly");
  click(c, elem({ dppause: "nightly" }));
  await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.apiPost.map(x => x.p),
    ["/api/dept/r4/engines/nightly/pause"], "one post, to the one route that writes");
  const list = engList(c);
  assert.ok(list.indexOf(">Idle<") !== -1, "the state word is still what the record says");
  assert.ok(list.indexOf(">Paused<") !== -1, "and the engine that IS paused still reads Paused");
});

test("S60: an engine already waiting on an ask says so instead of asking twice", () => {
  const c = fresh();
  const view = engCard(c, null, "nightly", { now: { ref: "r4", asks: [
    { id: "p-zz99", kind: "routine.update", args: { id: "nightly" }, summary: "Pause Nightly sweep",
      created_ms: Date.now(), window_ms: 24 * HOUR, default: "Nothing happens" }] } });
  assert.ok(view.indexOf("Asked to pause") !== -1);
});

test("S60: a paused engine offers no Pause at all", () => {
  const c = fresh();
  assert.ok(engCard(c, null, "off-one").indexOf("data-dppause") === -1);
});

/* ── A28 / A29 over the engine card ── */
test("S55/A28/A29: no engine pane carries a path, a raw count or the word charter", () => {
  const seed = { engineRuns: { nightly: Object.assign({ ref: "r4" }, ENG_RUNS) },
                 engineData: { nightly: Object.assign({ ref: "r4" }, ENG_DATA) } };
  let all = "";
  for (const pane of ["engines", "workflow", "runs", "data"]){
    const html = engCard(fresh(), pane, "nightly", seed);
    all += html;
    assert.ok(html.indexOf("/Users/") === -1, pane + ": A28 no path");
    assert.ok(!/help|Help/.test(html), pane + ": A28 no help text");
    assert.ok(html.toLowerCase().indexOf("charter") === -1, pane + ": A29");
  }
  for (const w of ["Engine", "Workflow", "Runs", "Data", "Chat", "Made by", "Cadence"]) {
    assert.ok(all.indexOf(w) !== -1, "missing screen word: " + w);
  }
});

test("S53: opening another department drops every engine read", async () => {
  const c = fresh();
  engCard(c, "runs", "nightly", { engineRuns: { nightly: { ref: "r4" } },
                                  engineData: { nightly: { ref: "r4" } } });
  c.dpSelect("r5");
  await sleep();
  assert.strictEqual(c.dpS().engines, null);
  assert.deepStrictEqual(Object.keys(c.dpS().engineRuns), []);
  assert.deepStrictEqual(Object.keys(c.dpS().engineData), []);
  assert.strictEqual(c.dpS().engineSel, null);
});

/* ── S32 / A29 again, now over all five function cards ── */
test("S32/A29: the word charter reaches no function card, and every screen word is on one", () => {
  const DATA = { adaptation: ADAPTATION, priority: PRIORITY, coordination: COORD, audit: AUDIT };
  let all = "";
  for (const [tab] of FUNCS.slice(1)){
    for (const pane of [null, "chat"]) all += fnCard(fresh(), tab, DATA[tab], pane);
    all += fnCard(fresh(), tab, EMPTY[tab]);
  }
  assert.strictEqual(all.toLowerCase().indexOf("charter"), -1, "A29: never on a card");
  for (const w of ["Adaptation", "Priority", "Coordination", "Audit", "Queue", "Budget",
                   "Locks", "Checks", "Chat", "Recent"]) {
    assert.ok(all.indexOf(w) !== -1, "missing screen word: " + w);
  }
  for (const w of ["cut", "seam", "overlay", "cascade", "score"]) {
    assert.ok(new RegExp("\\b" + w + "\\b", "i").test(all) === false, "off-list word: " + w);
  }
});

/* ── slice E fixtures: the filed work, its versions, and the people ──────── */
const FILED = { filed: [
  { id: "holding/plans/department-screen/LLD.md", label: "LLD", kind: "task",
    versions: 3, placement_id: "PL-3", charter_id: "C-1", ts_ms: Date.now() - HOUR,
    history: [
      { id: "PL-3", state: "in use", made_by: "matched", read_by: null,
        charter_id: "C-1", where: "Experience", ts_ms: Date.now() - HOUR, row: { id: "PL-3", charter_id: "C-1" } },
      { id: "PL-2", state: "retired", made_by: "matched", read_by: null,
        charter_id: "C-1", where: "Org", ts_ms: Date.now() - 3 * HOUR, row: { id: "PL-2" } },
      { id: "PL-1", state: "retired", made_by: "backfilled", read_by: null,
        charter_id: "C-1", where: "Org", ts_ms: Date.now() - 9 * HOUR, row: { id: "PL-1" } },
    ] },
  { id: "holding/plans/department-screen/PRD.md", label: "PRD", kind: "task",
    versions: 1, placement_id: "PL-9", charter_id: "C-1", ts_ms: Date.now() - 2 * HOUR,
    history: [{ id: "PL-9", state: "waits", made_by: "hook", read_by: null,
                charter_id: "C-1", where: "Experience", ts_ms: Date.now() - 2 * HOUR, row: { id: "PL-9" } }] },
] };
const PEOPLE = { owner: { source: "charter", name: "Meera", stamps: "Every release of Desktop",
                          /* B1: the writer's words again, on the card that echoed them */
                          seen: [{ id: "p-aa11", summary: writerSummary("goal.edit", "Org"),
                                   answer: "Refused.", at: "2026-09-21T09:01:04+05:30",
                                   at_ms: Date.now() - HOUR, row: { id: "p-aa11" } }] },
                 roles: [{ charter_id: "C-7", title: "Reviewer", name: "Reviewer",
                           stamps: "Stamp the release notes.", seen: [] }] };
const PEOPLE_BARE = { owner: { source: "git", name: "SankalpAsawa", stamps: "", seen: [] }, roles: [] };
const PEOPLE_NONE = { owner: { source: "none", name: null, stamps: "", seen: [] }, roles: [] };
const APPS = [{ id: "m-1", name: "Balance", kind: "page", has_page: true },
              { id: "m-2", name: "Wedding", kind: "page", has_page: true }];

/* The list column with the slice-E reads already landed. */
function listE(c, seed){
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpListHtml(n, d, DEPT_EXP, null);                 /* opens it, fires the reads */
  Object.assign(c.dpS(), seed || {});
  return c.dpListHtml(n, d, DEPT_EXP, null);
}
/* One of the two new cards, with its read landed and its row selected. */
function cardE(c, tab, seed){
  const d = c.o2Data(), n = d.byRef.get("r4");
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = tab;
  Object.assign(st, seed || {});
  return c.dpViewerHtml(n, d, DEPT_EXP, null);
}

/* ── S65: the two loaders ── */
test("S65: dpLoadFiled and dpLoadPeople read their own routes, once each", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadFiled("r4"); c.dpLoadFiled("r4"); c.dpLoadPeople("r4"); c.dpLoadPeople("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/filed", "/api/dept/r4/people"], "the busy guard holds for both");
});

test("S65: a filed answer for a department that is no longer open is dropped", async () => {
  let release;
  const c = fresh({ apiGet: () => new Promise(r => { release = r; }) });
  c.dpS().sel = "r4";
  const p = c.dpLoadFiled("r4");
  c.dpS().sel = "r5";
  release(FILED);
  await p;
  assert.strictEqual(c.dpS().filed, null, "the answer belongs to a department nobody is on");
});

test("S65: opening another department drops the filed work and the people it read", async () => {
  const c = fresh();
  c.dpSelect("r4");
  Object.assign(c.dpS(), { filed: Object.assign({ ref: "r4" }, FILED),
                           people: Object.assign({ ref: "r4" }, PEOPLE),
                           filedSel: "x", personSel: "owner" });
  c.dpSelect("r5");
  await sleep();
  assert.strictEqual(c.dpS().filed, null);
  assert.strictEqual(c.dpS().people, null);
  assert.strictEqual(c.dpS().filedSel, null);
  assert.strictEqual(c.dpS().personSel, null);
});

/* ── S66 / A24: the filed rows and the versions behind one ── */
test("S66/A24: a filed row is a name and its versions are dots, never a count", () => {
  const c = fresh();
  const html = listE(c, { filed: Object.assign({ ref: "r4" }, FILED) });
  assert.ok(html.indexOf(">LLD<") !== -1 && html.indexOf(">PRD<") !== -1, "names, not paths");
  const rows = (html.match(/data-dpfiled="[^"]*"[^]*?<\/button>/g) || []);
  assert.strictEqual(rows.length, 2);
  const dots = r => (r.match(/<i><\/i>/g) || []).length;
  assert.strictEqual(dots(rows[0]), 3, "three versions, three dots");
  assert.strictEqual(dots(rows[1]), 0, "one version carries no mark at all");
  assert.ok(!/>\s*3\s*</.test(html) && !/versions/i.test(html), "A28: no count at rest");
});

test("S66: until the version read lands the rows the Org screen loaded are shown", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const html = c.dpListHtml(n, d, DEPT_EXP, null);
  assert.ok(html.indexOf(">HLD<") !== -1, "the Org payload's own filed row");
  assert.ok(html.indexOf("Nothing filed yet") === -1, "never blank while it reads");
});

test("S66/A24: opening a filed row shows its versions newest first, each with its word", () => {
  const c = fresh();
  const html = cardE(c, "filed", { filed: Object.assign({ ref: "r4" }, FILED), filedSel: FILED.filed[0].id });
  const words = (html.match(/class="dpvw [a-z]+">([^<]*)</g) || []).map(m => /">([^<]*)<$/.exec(m)[1]);
  assert.deepStrictEqual(words, ["in use", "retired", "retired"], "newest first");
  assert.ok(html.indexOf("Filed by matched") !== -1, "the filer's own word");
  assert.ok(html.indexOf("Filed by backfilled") !== -1, "and the older one's");
  assert.ok(html.indexOf("Versions") !== -1 && html.indexOf("The work item") !== -1);
});

test("S66/A24: a work item filed once reads waits and shows its one version", () => {
  const c = fresh();
  const html = cardE(c, "filed", { filed: Object.assign({ ref: "r4" }, FILED), filedSel: FILED.filed[1].id });
  const words = (html.match(/class="dpvw [a-z]+">([^<]*)</g) || []).map(m => /">([^<]*)<$/.exec(m)[1]);
  assert.deepStrictEqual(words, ["waits"]);
});

test("S66: the card names the filer and says nothing where no record names a reader", () => {
  const c = fresh();
  const html = cardE(c, "filed", { filed: Object.assign({ ref: "r4" }, FILED) });
  assert.ok(/Read by<\/div><div class="o2quiet dpq">Not named</.test(html), "no reader is invented");
  assert.ok(html.indexOf("Experience") !== -1, "where it sits now");
});

test("S66: clicking a filed row opens the filed card on that row", () => {
  const c = fresh();
  open(c, "r4", { filed: Object.assign({ ref: "r4" }, FILED) });
  c.dpS().sel = "r4";
  assert.ok(click(c, elem({ dpfiled: FILED.filed[1].id })), "handled");
  assert.strictEqual(c.dpS().filedSel, FILED.filed[1].id);
  assert.strictEqual(c.dpS().tab.r4, "filed");
});

test("S66: a department with nothing filed says so once, and a failed read says so", () => {
  const c = fresh();
  assert.ok(cardE(c, "filed", { filed: { ref: "r4", filed: [] } }).indexOf("Nothing filed yet") !== -1);
  const b = fresh();
  assert.ok(cardE(b, "filed", { error: { filed: "Sutra did not answer" } }).indexOf("Could not read") !== -1);
});

test("S66/A28/A29: the filed card carries no path, no count and not the word charter", () => {
  const c = fresh();
  const html = cardE(c, "filed", { filed: Object.assign({ ref: "r4" }, FILED) });
  assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, "A29");
  assert.strictEqual(html.indexOf("/Users/"), -1, "A28");
  assert.strictEqual(html.indexOf("holding/plans"), -1, "A28: a name, never the path");
});

/* ── S67 / A25: the people ── */
test("S67/A25: People lists the owner first, then the role charters", () => {
  const c = fresh();
  const html = listE(c, { people: Object.assign({ ref: "r4" }, PEOPLE) });
  const rows = (html.match(/data-dpperson="([^"]*)"/g) || []).map(m => /"([^"]*)"/.exec(m)[1]);
  assert.deepStrictEqual(rows, ["owner", "C-7"], "the owner, then the role");
  assert.ok(html.indexOf(">Meera<") !== -1 && html.indexOf(">Reviewer<") !== -1);
});

/* DS-2 / A36: a role charter names a PERSON. The card shows that person, and
   "unfilled" is a name for nobody -- the role exists and is open. */
const PEOPLE_ROLE = { owner: PEOPLE.owner,
                      roles: [{ charter_id: "C-7", title: "Reviewer", name: "Devansh",
                                person: "Devansh", unfilled: false,
                                stamps: "Stamp the release notes.", seen: [] },
                              { charter_id: "C-8", title: "Release manager", name: "unfilled",
                                person: "unfilled", unfilled: true,
                                stamps: "Run the release.", seen: [] }] };
test("S-G/A36: People lists a role charter with its person after the owner", () => {
  const c = fresh();
  const html = listE(c, { people: Object.assign({ ref: "r4" }, PEOPLE_ROLE) });
  const rows = (html.match(/data-dpperson="([^"]*)"/g) || []).map(m => /"([^"]*)"/.exec(m)[1]);
  assert.deepStrictEqual(rows, ["owner", "C-7", "C-8"], "the owner, then the roles");
  assert.ok(html.indexOf(">Devansh<") !== -1, "the person, not the role's title");
  assert.ok(html.indexOf(">unfilled<") !== -1, "a role nobody holds says so");
  const card = cardE(fresh(), "people", { people: Object.assign({ ref: "r4" }, PEOPLE_ROLE), personSel: "C-7" });
  assert.ok(card.indexOf(">Devansh<") !== -1 && card.indexOf("Stamp the release notes.") !== -1,
    "the role opens on its own card: who, and what they run");
  assert.strictEqual(card.toLowerCase().indexOf("charter"), -1, "A29");
});

test("S67/A25: with no role charter the group is the owner alone", () => {
  const c = fresh();
  const html = listE(c, { people: Object.assign({ ref: "r4" }, PEOPLE_BARE) });
  const rows = (html.match(/data-dpperson="([^"]*)"/g) || []).map(m => /"([^"]*)"/.exec(m)[1]);
  assert.deepStrictEqual(rows, ["owner"]);
  assert.ok(html.indexOf(">SankalpAsawa<") !== -1);
});

test("S67: a department with no owner and no roles shows one quiet line", () => {
  const c = fresh();
  const html = listE(c, { people: Object.assign({ ref: "r4" }, PEOPLE_NONE) });
  assert.ok(html.indexOf("No people yet") !== -1);
  assert.strictEqual((html.match(/data-dpperson=/g) || []).length, 0);
});

test("S67: a person opens on their name, what they stamp and the asks they saw", () => {
  const c = fresh();
  const html = cardE(c, "people", { people: Object.assign({ ref: "r4" }, PEOPLE), personSel: "owner" });
  assert.ok(html.indexOf(">Meera<") !== -1, "the name");
  assert.ok(html.indexOf("Every release of Desktop") !== -1, "what they stamp");
  assert.ok(html.indexOf(writerSummary("goal.edit", "Org")) !== -1 && html.indexOf("Refused.") !== -1,
    "the ask they saw and the answer they gave");
  assert.ok(html.indexOf("The person") !== -1 && html.indexOf("Asks they saw") !== -1);
});

test("S67: a person whose record names no scope and no ask says so, twice quietly", () => {
  const c = fresh();
  const html = cardE(c, "people", { people: Object.assign({ ref: "r4" }, PEOPLE_BARE) });
  assert.ok(html.indexOf("Not named") !== -1, "what they stamp is unwritten");
  assert.ok(html.indexOf("No asks yet") !== -1);
});

test("S67: clicking a person opens their card, and a failed read says so", () => {
  const c = fresh();
  open(c, "r4", { people: Object.assign({ ref: "r4" }, PEOPLE) });
  c.dpS().sel = "r4";
  assert.ok(click(c, elem({ dpperson: "C-7" })), "handled");
  assert.strictEqual(c.dpS().personSel, "C-7");
  assert.strictEqual(c.dpS().tab.r4, "people");
  const b = fresh();
  assert.ok(cardE(b, "people", { error: { people: "Sutra did not answer" } }).indexOf("Could not read") !== -1);
});

test("S67/A29: the person card does not say charter, and shows no path", () => {
  const c = fresh();
  for (const seed of [PEOPLE, PEOPLE_BARE, PEOPLE_NONE]){
    const html = cardE(fresh(), "people", { people: Object.assign({ ref: "r4" }, seed) });
    assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, "A29");
    assert.strictEqual(html.indexOf("/Users/"), -1, "A28");
  }
  assert.ok(c);
});

/* ── S68 / A26: Documents is what the Org screen lists ── */
test("S68/A26: Documents carries the same rows the Org screen's own column carries", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  const org = c.o2ListHtml(n, d, DEPT_EXP, null);
  const dp = c.dpListHtml(n, d, DEPT_EXP, null);
  const pick = (html, a, t) => (html.match(new RegExp("data-" + a + '="([^"]*)" data-' + t + '="([^"]*)"', "g")) || []);
  const orgDocs = pick(org, "o2doc", "o2title").map(s => s.replace(/o2/g, ""));
  const dpDocs = pick(dp, "dpdoc", "dptitle").map(s => s.replace(/dp/g, ""));
  assert.ok(orgDocs.length === 1, "the fixture has one document");
  assert.deepStrictEqual(dpDocs, orgDocs, "same path, same title, same order");
});

test("S68/A26: a document opens through the Org screen's own reader", () => {
  const c = fresh();
  open(c, "r4");
  const opened = [];
  c.o2OpenDoc = (p, t) => opened.push([p, t]);
  assert.ok(click(c, elem({ dpdoc: "holding/x.md", dptitle: "X" })), "handled");
  assert.deepStrictEqual(opened, [["holding/x.md", "X"]], "o2OpenDoc, not a second reader");
});

/* ── S69 / A26: Apps is the Org screen's own read ── */
test("S69/A26: Apps calls o2LoadApps and renders exactly what it put in the cache", async () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpListHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/modules?subtree=0&department=r4") !== -1,
    "the Org screen's own URL, unchanged");
  c.o2S().apps.r4 = APPS;
  const html = c.dpListHtml(n, d, DEPT_EXP, null);
  const ids = (html.match(/data-dpapp="([^"]*)"/g) || []).map(m => /"([^"]*)"/.exec(m)[1]);
  assert.deepStrictEqual(ids, ["m-1", "m-2"]);
  assert.ok(html.indexOf(">Balance<") !== -1 && html.indexOf(">Wedding<") !== -1);
  const org = c.o2ListHtml(n, d, DEPT_EXP, null);
  const orgIds = (org.match(/data-o2app="([^"]*)"/g) || []).map(m => /"([^"]*)"/.exec(m)[1]);
  assert.deepStrictEqual(ids, orgIds, "the same apps the Org screen lists, in the same order");
});

test("S69: an unread Apps group says so rather than claiming there are none", () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.o2S().apps.r4 = null;                       /* in flight, the way o2LoadApps marks it */
  assert.ok(c.dpListHtml(n, d, DEPT_EXP, null).indexOf("Not read yet") !== -1);
  c.o2S().apps.r4 = [];
  assert.ok(c.dpListHtml(n, d, DEPT_EXP, null).indexOf("No apps yet") !== -1);
});

test("S69/A26: an app opens through o2OpenApp, over the module that loader cached", () => {
  const c = fresh();
  open(c, "r4");
  c.dpS().sel = "r4";
  c.o2S().apps.r4 = APPS;
  const opened = [];
  c.o2OpenApp = (m) => opened.push(m.id);
  assert.ok(click(c, elem({ dpapp: "m-2" })), "handled");
  assert.deepStrictEqual(opened, ["m-2"]);
  c.o2S().apps.r4 = [];
  click(c, elem({ dpapp: "m-2" }));
  assert.deepStrictEqual(opened, ["m-2"], "an id the cache does not hold opens nothing");
});

/* ── slice F: meters, births, empty and paused states (S73-S82) ──────────── */
const METERS = { month: "2026-09",
  meters: [{ key: "runs", label: "Runs", reading: true, value: 12, of: 30 },
           { key: "asks", label: "Asks", reading: true, value: 4, of: 8 },
           { key: "refuses", label: "Refuses", reading: true, value: 1, of: 4 },
           { key: "spend", label: "Spend", reading: false, value: 0, of: 0 }],
  runs: 12, asks: 4, refuses: 1, spend_usd: null,
  engines: [{ id: "nightly", name: "Nightly sweep", meters: [
               { key: "tick", label: "Tick", dot: "ok" },
               { key: "asks", label: "Asks", dot: "warn" }] },
            { id: "hourly", name: "Teamsutra worker", meters: [] }] };
const METERS_NONE = { month: "2026-09",
  meters: [{ key: "runs", label: "Runs", reading: false, value: 0, of: 0 },
           { key: "asks", label: "Asks", reading: false, value: 0, of: 0 },
           { key: "refuses", label: "Refuses", reading: false, value: 0, of: 0 },
           { key: "spend", label: "Spend", reading: false, value: 0, of: 0 }],
  runs: 0, asks: 0, refuses: 0, spend_usd: null, engines: [] };
const BIRTHS = [{ id: "nightly", name: "Nightly sweep",
                  at: "2026-08-01T09:00:00+05:30", at_ms: ENG_BORN }];

/* ── S74: the meters loader ── */
test("S74: dpLoadMeters reads its own route once, and the busy guard holds", async () => {
  const c = fresh();
  c.dpS().sel = "r4";
  c.dpLoadMeters("r4"); c.dpLoadMeters("r4"); c.dpLoadMeters("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet, ["/api/dept/r4/meters"]);
});

test("S74: a meters answer for a department nobody is on is dropped", async () => {
  let release;
  const c = fresh({ apiGet: () => new Promise(r => { release = r; }) });
  c.dpS().sel = "r4";
  const p = c.dpLoadMeters("r4");
  c.dpS().sel = "r5";
  release(METERS);
  await p;
  assert.strictEqual(c.dpS().meters, null);
});

test("S74: opening another department drops the meters it read", async () => {
  const c = fresh();
  c.dpSelect("r4");
  c.dpS().meters = Object.assign({ ref: "r4" }, METERS);
  c.dpSelect("r5");
  await sleep();
  assert.strictEqual(c.dpS().meters, null);
});

test("S74: opening a department still costs exactly the three Now reads", async () => {
  const c = fresh();
  c.dpSelect("r4");
  await sleep();
  assert.deepStrictEqual(c.calls.apiGet.slice().sort(),
    ["/api/dept/r4/now", "/api/dept/r4/running", "/api/dept/r4/waits"],
    "the meters are not one of them");
});

/* ── S75 / A27: the meters on Now ── */
test("S75: the Now card reads the meters when it opens, once", async () => {
  const c = fresh();
  const d = c.o2Data(), n = d.byRef.get("r4");
  c.dpS().sel = "r4"; c.dpS().tab.r4 = "now";
  c.dpViewerHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/meters") !== -1, "the card reads it");
  c.dpViewerHtml(n, d, DEPT_EXP, null);
  await sleep();
  assert.strictEqual(c.calls.apiGet.filter(p => /\/meters$/.test(p)).length, 1,
    "a repaint is not a second read");
});

test("S75/A27: the month is four bars, drawn against the busiest month on record", () => {
  const c = fresh();
  const html = nowCard(c, [], { meters: Object.assign({ ref: "r4" }, METERS) });
  assert.ok(html.indexOf(">Meters<") !== -1, "the card is on Now");
  for (const w of ["Runs", "Asks", "Refuses", "Spend"]) {
    assert.ok(html.indexOf(">" + w + "<") !== -1, w + " is a meter");
  }
  assert.ok(/class="dpbar"><i style="width:40%"/.test(html), "runs: 12 of 30");
  assert.ok(/class="dpbar"><i style="width:50%"/.test(html), "asks: 4 of 8");
  assert.ok(/class="dpbar"><i style="width:25%"/.test(html), "refuses: 1 of 4");
  assert.strictEqual((html.match(/dpbar/g) || []).length, 3, "the unread meter draws no bar");
  assert.ok(!/>\s*\d+\s*</.test(html), "A28: a bar, never a number");
});

test("S75/A27: a meter with nothing on record reads No reading yet", () => {
  const c = fresh();
  const html = nowCard(c, [], { meters: Object.assign({ ref: "r4" }, METERS) });
  assert.ok(html.indexOf("No reading yet") !== -1, "the spend meter says so");
  assert.strictEqual((html.match(/No reading yet/g) || []).length, 1, "once, for the one");
});

test("S75/A9: with nothing open and nothing on record Now is still one quiet line", () => {
  const c = fresh();
  const html = nowCard(c, [], { meters: Object.assign({ ref: "r4" }, METERS_NONE) });
  assert.ok(html.indexOf("Nothing waiting on you") !== -1);
  assert.strictEqual((html.match(/o2quiet dpq/g) || []).length, 1, "no empty meters card");
  assert.ok(html.indexOf("dpcard") === -1, "and no card at all");
});

test("S75: the meters sit under the asks, and the card keeps both", () => {
  const c = fresh();
  const html = nowCard(c, [ASK], { meters: Object.assign({ ref: "r4" }, METERS) });
  assert.ok(html.indexOf("Pause the nightly sweep") !== -1, "the ask is still there");
  assert.ok(html.indexOf(">Asks<") < html.indexOf(">Meters<"), "the month comes after what waits");
});

/* ── S75 / A23: the births on Adaptation and on Priority ── */
test("S75/A23: Adaptation's Runs says an engine was born of an ask", () => {
  const c = fresh();
  const html = fnCard(c, "adaptation", Object.assign({}, ADAPTATION, { births: BIRTHS }));
  assert.ok(html.indexOf("Engine born: Nightly sweep") !== -1, "the birth line");
  assert.ok(html.indexOf("1 Aug") !== -1, "when it happened");
  assert.ok(html.indexOf(">Runs<") !== -1, "under the card the locked screen names");
});

test("S75/A23: Priority's Runs says the first row that engine was admitted", () => {
  const c = fresh();
  const html = fnCard(c, "priority", Object.assign({}, PRIORITY, { births: BIRTHS }));
  assert.ok(html.indexOf("First row admitted: Nightly sweep") !== -1);
  assert.ok(html.indexOf(">Runs<") !== -1 && html.indexOf(">Budget<") !== -1);
});

test("S75/A23: an engine nobody asked for is on neither card", () => {
  const c = fresh();
  for (const [tab, line] of [["adaptation", "Engine born"], ["priority", "First row admitted"]]) {
    const html = fnCard(fresh(), tab, Object.assign({}, tab === "adaptation" ? ADAPTATION : PRIORITY,
                                                    { births: [] }));
    assert.strictEqual(html.indexOf(line), -1, tab + ": nothing invented");
  }
  assert.ok(c);
});

test("S75/A23: a birth alone is enough to fill a card that is otherwise empty", () => {
  const c = fresh();
  const a = fnCard(c, "adaptation", Object.assign({}, EMPTY.adaptation, { births: BIRTHS }));
  assert.ok(a.indexOf("Engine born: Nightly sweep") !== -1);
  assert.ok(a.indexOf("Nothing to change yet") === -1);
  const p = fnCard(fresh(), "priority", Object.assign({}, EMPTY.priority, { births: BIRTHS }));
  assert.ok(p.indexOf("First row admitted: Nightly sweep") !== -1);
  assert.ok(p.indexOf("Nothing in the queue") === -1);
});

/* ── S76 / A33: the empty department ── */
const BARE_DEPT = { filed: [], docs: [], charter: null, charters: [] };
const EMPTY_READS = {
  now: { ref: "r4", asks: [], decidable: true },
  running: { ref: "r4", running: [] },
  waits: { ref: "r4", waits: [] },
  meters: Object.assign({ ref: "r4" }, METERS_NONE),
  engines: { ref: "r4", engines: [] },
  filed: { ref: "r4", filed: [] },
  people: Object.assign({ ref: "r4" }, PEOPLE_NONE),
  identity: Object.assign({ ref: "r4" }, BARE_ID),
  adaptation: Object.assign({ ref: "r4" }, EMPTY.adaptation),
  priority: Object.assign({ ref: "r4" }, EMPTY.priority),
  coordination: Object.assign({ ref: "r4" }, EMPTY.coordination),
  audit: Object.assign({ ref: "r4" }, EMPTY.audit),
};
function emptyDept(c, tab){
  const st = c.dpS();
  st.sel = "r4";
  Object.assign(st, EMPTY_READS);
  st.tab.r4 = tab || "now";
  if (typeof c.o2S === "function") c.o2S().apps.r4 = [];
  const d = c.o2Data(), n = d.byRef.get("r4");
  return { list: c.dpListHtml(n, d, BARE_DEPT, null),
           card: c.dpViewerHtml(n, d, BARE_DEPT, null) };
}

test("S76/A33: an empty department still shows all seven groups, one quiet line each", () => {
  const c = fresh();
  const { list } = emptyDept(c);
  assert.deepStrictEqual(groupLabels(list), GROUPS, "nothing is hidden because it is empty");
  const quiet = (list.match(/class="o2quiet dpq">([^<]*)</g) || []).map(m => /">([^<]*)<$/.exec(m)[1]);
  assert.deepStrictEqual(quiet, ["No engines here", "Nothing filed yet", "No people yet",
                                 "No documents yet", "No apps yet"],
    "five empty groups, five lines; Now and Functions carry their fixed rows");
  assert.strictEqual((list.match(/data-dptab=/g) || []).length, 6, "Now and the five functions");
});

test("S76/A33: every card of an empty department is exactly one quiet line", () => {
  const want = { now: "Nothing waiting on you", adaptation: "Nothing to change yet",
                 priority: "Nothing in the queue", coordination: "Nothing held",
                 audit: "No check has run here", engines: "No engines here",
                 filed: "Nothing filed yet", people: "No people yet" };
  for (const tab of Object.keys(want)) {
    const { card } = emptyDept(fresh(), tab);
    assert.ok(card.indexOf(want[tab]) !== -1, tab + ' says "' + want[tab] + '"');
    const quiet = (card.match(/o2quiet dpq/g) || []).length;
    assert.strictEqual(quiet, 1, tab + ": one line, not several");
    assert.ok(!/help|Help|How to|Learn/.test(card), tab + ": A28 no help text");
    assert.ok(card.indexOf("/Users/") === -1, tab + ": A28 no path");
  }
});

test("S76/A12: an empty Identity reads No goal yet and never the word behind it", () => {
  const c = fresh();
  const { card } = emptyDept(c, "identity");
  assert.ok(card.indexOf("No goal yet") !== -1, "A12");
  assert.ok(card.indexOf("Write the goal") !== -1, "and the one action beside it");
  assert.strictEqual(card.toLowerCase().indexOf("charter"), -1, "A12: not the word");
  for (const line of ["No done line yet", "No rules yet", "No reading yet", "No owner yet"]) {
    assert.ok(card.indexOf(line) !== -1, "the cell says " + line);
  }
});

/* ── S77 / A34: the paused engine ── */
const ENG_PAUSED_RUNS = { id: "off-one", total: 2, unreadable: 0, never_run: false, runs: [
  { schema: 1, id: "off-one", trigger: "schedule",
    started_at: new Date(Date.now() - 40 * 60000).toISOString(), outcome: "ok", duration_s: 0 },
  { schema: 1, id: "off-one", trigger: "schedule", started_at: "2026-09-14T03:00:00+05:30",
    ended_at: "2026-09-14T03:02:00+05:30", duration_s: 120, outcome: "ok" },
], chat: [] };

test("S77/A34: a paused engine reads Paused in the list and on its card", () => {
  const c = fresh();
  assert.ok(engList(c).indexOf(">Paused<") !== -1, "the row says it");
  const card = engCard(fresh(), null, "off-one");
  assert.ok(card.indexOf(">State<") !== -1 && card.indexOf(">Paused<") !== -1,
    "and so does the card");
  assert.ok(card.indexOf("data-dppause") === -1, "a paused engine is not offered a pause");
});

test("S77/A34: the two engines that are not paused say what they are instead", () => {
  for (const [id, word] of [["nightly", "Idle"], ["hourly", "Running"]]) {
    const card = engCard(fresh(), null, id);
    assert.ok(card.indexOf(">" + word + "<") !== -1, id + " says " + word);
    assert.ok(card.indexOf(">Paused<") === -1, id + " is not paused");
  }
});

test("S77/A34: a paused engine's Runs shows the last run and no live row", () => {
  const c = fresh();
  const view = engCard(c, "runs", "off-one",
    { engineRuns: { "off-one": Object.assign({ ref: "r4" }, ENG_PAUSED_RUNS) } });
  assert.strictEqual((view.match(/>Running/g) || []).length, 0,
    "a switched-off engine has nothing going");
  assert.ok(view.indexOf("so far") === -1, "and no clock on it");
  assert.strictEqual((view.match(/>Done</g) || []).length, 2, "both rows read as they ended");
  const live = engCard(fresh(), "runs", "hourly",
    { engineRuns: { hourly: Object.assign({ ref: "r4" }, ENG_LIVE) } });
  assert.ok(live.indexOf(">Running") !== -1, "a running engine still reads Running");
});

/* ── S77 / A27: the per-engine meters ── */
test("S77/A27: the Engine tab reads the meters and shows the ones a record answers", async () => {
  const c = fresh();
  engCard(c, null, "nightly");
  await sleep();
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/meters") !== -1, "the card reads them");
  const view = engCard(fresh(), null, "nightly", { meters: Object.assign({ ref: "r4" }, METERS) });
  assert.ok(view.indexOf(">Meters<") !== -1, "the card is there");
  assert.ok(/class="dpmet"><i class="dpdot ok"><\/i>Tick/.test(view), "Tick is a dot");
  assert.ok(/class="dpmet"><i class="dpdot warn"><\/i>Asks/.test(view), "so is Asks");
  assert.ok(view.indexOf(">Fit<") === -1, "Fit has no record and is given no dot");
  assert.ok(!/>\s*\d+\s*</.test(view.slice(view.indexOf(">Meters<"))), "A28: dots, never counts");
});

test("S77/A27: an engine whose records answer nothing says No reading yet", () => {
  const c = fresh();
  const view = engCard(c, null, "hourly", { meters: Object.assign({ ref: "r4" }, METERS) });
  assert.ok(view.indexOf(">Meters<") !== -1 && view.indexOf("No reading yet") !== -1);
  assert.ok(view.indexOf("dpmet\"") === -1, "one line, no dots");
});

/* ── B2: the state word after a decision ──────────────────────────────────
   The bug the acceptance walk found (ACCEPTANCE B2): answering an ask re-read
   Now and nothing else, so an approval that changed a routine left the Engines
   list and the engine card saying what the routine used to be until the
   department was opened again. The decide now re-reads the cards that read the
   record it changed -- and only those, and only on a decide: opening a
   department still costs the three reads Now needs. */
test("B2: a stamped routine ask flips the engine's state word without reopening the department", async () => {
  const after = { engines: ENGINES.engines.map(e =>
    Object.assign({}, e, e.id === "nightly" ? { state: "paused" } : {})) };
  const c = fresh({ apiGet: (p) => {
    c.calls.apiGet.push(p);
    if (/\/engines$/.test(p)) return Promise.resolve(after);
    return Promise.resolve({ asks: [], decidable: true });
  } });
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "engines"; st.engineSel = "nightly";
  st.engines = Object.assign({ ref: "r4" }, ENGINES);
  st.now = { ref: "r4", asks: [Object.assign({}, ASK, { args: { id: "nightly" } })], decidable: true };
  st.running = { ref: "r4", running: [] }; st.waits = { ref: "r4", waits: [] };
  const d = c.o2Data(), n = d.byRef.get("r4");
  assert.ok(c.dpListHtml(n, d, DEPT_EXP, null).indexOf(">Idle<") !== -1, "Idle before the decision");
  click(c, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(c.calls.decide, [{ pid: "p-aa11", ok: true }]);
  assert.strictEqual(c.calls.apiGet.filter(p => /\/engines$/.test(p)).length, 1,
    "the decide re-read the engines once, not on every repaint");
  const list = c.dpListHtml(n, d, DEPT_EXP, null);
  assert.ok(list.indexOf("Paused") !== -1 && list.indexOf(">Idle<") === -1, "the row moved in place");
  assert.ok(c.dpViewerHtml(n, d, DEPT_EXP, null).indexOf("Paused") !== -1,
    "and the open engine card's Engine tab says it too");
});

test("B2: a stamped org ask re-reads Identity and People, and a routine ask does not", async () => {
  const seen = [];
  const mk = (kind) => {
    const c = fresh({ apiGet: (p) => { seen.push(p); return Promise.resolve({ asks: [], decidable: true }); } });
    const st = c.dpS();
    st.sel = "r4"; st.tab.r4 = "now";
    st.now = { ref: "r4", asks: [Object.assign({}, ASK, { kind: kind })], decidable: true };
    st.identity = Object.assign({ ref: "r4" }, IDENTITY);
    st.people = Object.assign({ ref: "r4" }, PEOPLE);
    st.engines = Object.assign({ ref: "r4" }, ENGINES);
    return c;
  };
  const c1 = mk("org.charter");
  click(c1, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(seen.sort(), ["/api/dept/r4/identity", "/api/dept/r4/now", "/api/dept/r4/people"]);
  seen.length = 0;
  const c2 = mk("routine.update");
  click(c2, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(seen.sort(), ["/api/dept/r4/engines", "/api/dept/r4/now"]);
});

test("B2: a card this department has not read is not read by a decision", async () => {
  const seen = [];
  const c = fresh({ apiGet: (p) => { seen.push(p); return Promise.resolve({ asks: [], decidable: true }); } });
  const st = c.dpS();
  st.sel = "r4"; st.tab.r4 = "now";
  st.now = { ref: "r4", asks: [Object.assign({}, ASK, { kind: "org.charter" })], decidable: true };
  click(c, elem({ dpdecide: "p-aa11", dpok: "1" }));
  await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(seen, ["/api/dept/r4/now"], "Now, and nothing it never opened");
});

/* ── S78, S79: every card of a full department, swept once ────────────────
   The two sweeps below are the slice's closing gate: one card at a time was
   checked as it was built, and this walks ALL of them with the richest
   fixtures each one has, so a rule that a later slice broke on an earlier
   card is caught here rather than on the screen. The Exact panes are left out
   on purpose -- a raw row is the ONE place a path, a count or the record's own
   word is allowed to appear (A28, A29), and it is checked separately. */
const FULL = {
  now: { ref: "r4", asks: [ASK, HARD_ASK, OLD_ASK], decidable: true },
  running: { ref: "r4", running: RUNNING },
  waits: { ref: "r4", waits: WAITS },
  meters: Object.assign({ ref: "r4" }, METERS),
  identity: Object.assign({ ref: "r4" }, IDENTITY),
  adaptation: Object.assign({ ref: "r4" }, ADAPTATION, { births: BIRTHS }),
  priority: Object.assign({ ref: "r4" }, PRIORITY, { births: BIRTHS }),
  coordination: Object.assign({ ref: "r4" }, COORD),
  audit: Object.assign({ ref: "r4" }, AUDIT),
  engines: Object.assign({ ref: "r4" }, ENGINES),
  engineRuns: { nightly: Object.assign({ ref: "r4" }, ENG_RUNS),
                hourly: Object.assign({ ref: "r4" }, ENG_LIVE),
                "off-one": Object.assign({ ref: "r4" }, ENG_PAUSED_RUNS) },
  engineData: { nightly: Object.assign({ ref: "r4" }, ENG_DATA) },
  filed: Object.assign({ ref: "r4" }, FILED),
  people: Object.assign({ ref: "r4" }, PEOPLE),
};
/* [label, html] for the list column and every card, every pane, every row a
   fixture holds -- Exact excluded. */
function sweep(){
  const out = [];
  const paint = (label, tab, seed) => {
    const c = fresh();
    const st = c.dpS();
    st.sel = "r4";
    Object.assign(st, FULL, seed || {});
    st.tab.r4 = tab;
    c.o2S().apps.r4 = APPS;
    const d = c.o2Data(), n = d.byRef.get("r4");
    out.push([label, c.dpViewerHtml(n, d, DEPT_EXP, null)]);
    if (tab === "now") out.push(["list", c.dpListHtml(n, d, DEPT_EXP, null)]);
  };
  paint("now", "now");
  for (const pane of ["identity", "owner", "adaptation"]) {
    paint("identity/" + pane, "identity", { pane: { "r4:identity": pane } });
  }
  for (const [tab] of FUNCS.slice(1)) {
    for (const pane of [tab, "chat"]) paint(tab + "/" + pane, tab, { pane: { ["r4:" + tab]: pane } });
  }
  for (const id of ["nightly", "hourly", "off-one"]) {
    for (const pane of ["engines", "workflow", "runs", "data", "chat"]) {
      paint("engine " + id + "/" + pane, "engines",
            { engineSel: id, pane: { "r4:engines": pane } });
    }
  }
  for (const f of FILED.filed) paint("filed/" + f.label, "filed", { filedSel: f.id });
  for (const p of ["owner", "C-7"]) paint("people/" + p, "people", { personSel: p });
  return out;
}

test("S78/A28: no card shows help text, a path or a raw count at rest", () => {
  for (const [label, html] of sweep()) {
    /* what a person READS is the text between the tags; a path may ride an
       attribute (it is how a row opens its document), never a label */
    const text = html.replace(/<[^>]*>/g, "\n");
    assert.ok(!/help|Help|How to|Learn more/.test(text), label + ": no help text");
    assert.strictEqual(html.indexOf("/Users/"), -1, label + ": no path, not even in an attribute");
    assert.strictEqual(text.indexOf("holding/plans"), -1, label + ": a name, never the path");
    const counts = (html.match(/>\s*\d+\s*</g) || []);
    assert.deepStrictEqual(counts, [], label + ": counts are bars and dots only");
  }
});

test("S78/A27: every bar on the screen is a share, and every dot is a word", () => {
  for (const [label, html] of sweep()) {
    for (const m of (html.match(/<i style="width:([0-9.]+)%"/g) || [])) {
      const pct = Number(/([0-9.]+)%/.exec(m)[1]);
      assert.ok(pct >= 0 && pct <= 100, label + ": a bar stays inside its track (" + m + ")");
    }
    for (const m of (html.match(/class="dpdot ([a-z]*)"/g) || [])) {
      const dot = /dpdot ([a-z]*)"/.exec(m)[1];
      assert.ok(["", "ok", "warn", "block"].indexOf(dot) !== -1, label + ": " + dot + " is not a dot");
    }
  }
});

test("S79/A29: every screen word is from the D78 list, on every card", () => {
  const all = sweep().map(x => x[1]).join("\n");
  for (const w of ["department", "Now", "Identity", "Adaptation", "Priority", "Coordination",
                   "Audit", "Engines", "Engine", "work item", "Filed work", "People",
                   "Documents", "Apps", "Rules", "Budget", "Owner", "Meters"]) {
    assert.ok(all.indexOf(w) !== -1, "missing screen word: " + w);
  }
  for (const w of ["cut", "seam", "overlay", "cascade", "score"]) {
    assert.ok(new RegExp("\\b" + w + "\\b", "i").test(all) === false, "off-list word: " + w);
  }
});

test("S79/A29: the word charter is on no card at all", () => {
  for (const [label, html] of sweep()) {
    assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, label + ": A29");
  }
});

test("S79/A29: and it reaches the screen only inside an Exact row", () => {
  const c = fresh();
  const st = c.dpS();
  st.sel = "r4";
  Object.assign(st, FULL);
  st.tab.r4 = "engines";
  st.engines = Object.assign({ ref: "r4" }, ENGINES);
  st.engineSel = "nightly";
  st.pane["r4:engines"] = "chat";
  st.chatMode["r4:engines:chat"] = "exact";
  const d = c.o2Data();
  const exact = c.dpViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(exact.indexOf('<pre class="dpexact">') !== -1, "an engine's Exact is the raw row");
  const at = exact.toLowerCase().indexOf("charter");
  if (at !== -1)
    assert.ok(exact.lastIndexOf('<pre class="dpexact">') < at && at < exact.indexOf("</pre>"),
      "and where the word appears at all, it is inside that pre");
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

/* DS-7: Asawa Holding is a root child that carries a working folder. Before the
   domains payload forwarded node_kind the client read it as the machine and the
   department screen never painted for it. */
test("S-G/DS-7: a root child with a working folder and node_kind organisation opens the department screen", () => {
  const rows = TREE.map(x => Object.assign({}, x));
  rows[2].cwd = "/Users/asawa/Claude/asawa-holding";      /* Asawa Inc., a root child WITH a folder */
  const c = fresh({ DOMAINS: rows });
  c.o2EnsureRegistered();
  const st = c.o2S();
  st.loaded = true; st.sel = "r2"; st.dept.r2 = DEPT_EXP;
  const d = c.o2Data();
  assert.strictEqual(c.o2Kind(d.byRef.get("r2"), d), "org", "the stored kind wins over the cwd rule");
  assert.ok(/dplist/.test(c.o2ScreenHtml()), "the .dp column paints");
});

test("S-G/DS-7: a row with no node_kind still follows the old cwd rule", () => {
  const rows = TREE.map(x => Object.assign({}, x));
  delete rows[1].node_kind;                                /* Desktop, carrying a cwd */
  delete rows[2].node_kind;                                /* Asawa Inc., carrying none */
  const c = fresh({ DOMAINS: rows });
  const d = c.o2Data();
  assert.strictEqual(c.o2Kind(d.byRef.get("r1"), d), "machine", "a cwd under the root is still the machine");
  assert.strictEqual(c.o2Kind(d.byRef.get("r2"), d), "org", "and the other root children are organisations");
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

test("S30 + DS-13: the Summary / Exact control lives on an engine card, and only there", () => {
  const c = fresh();
  c.localStorage = memStore();
  const id = idCard(c, IDENTITY);
  const fn = fnCard(fresh(), "audit", AUDIT);
  assert.strictEqual((id + fn).indexOf("data-dpchatmode="), -1, "not on a function card");
  const eng = engCard(fresh(), "chat", "nightly");
  assert.ok(eng.indexOf("data-dpchatmode=") !== -1, "still on an engine's chat");
  assert.strictEqual(click(c, elem({ dpchatmode: "exact", dpchatkey: "r4:engines:chat" })), true);
  assert.strictEqual(c.dpS().chatMode["r4:engines:chat"], "exact", "and the click still switches it");
});

test("S32/A29 + DS-13: with the raw rows gone, the word charter reaches no department card", () => {
  const c = fresh();
  c.localStorage = memStore();
  const d = c.o2Data(), n = d.byRef.get("r4");
  for (const html of [c.dpListHtml(n, d, DEPT_EXP, null),
                      idCard(c, IDENTITY), idCard(c, BARE_ID), idCard(fresh(), IDENTITY, "chat")]) {
    assert.strictEqual(html.toLowerCase().indexOf("charter"), -1, "no charter on a card");
  }
  const eng = engCard(fresh(), "chat", "nightly", { chatMode: { "r4:engines:chat": "exact" } });
  assert.ok(eng.indexOf('data-dpchatmode="exact"') !== -1, "an engine's chat still offers the raw reading");
  assert.ok(/aria-pressed="true" data-dpchatmode="exact"/.test(eng), "and it is the open one here");
});

test("S44/A17 + DS-13: a path may still be read, on an engine's Exact and nowhere else", () => {
  const c = fresh();
  c.localStorage = memStore();
  const fn = fnCard(c, "audit", AUDIT) + fnCard(fresh(), "audit", AUDIT, "chat");
  assert.strictEqual(fn.indexOf("dpexact"), -1, "no raw rows on a function card");
  const eng = engCard(fresh(), "chat", "nightly", { chatMode: { "r4:engines:chat": "exact" } });
  assert.ok(/aria-pressed="true" data-dpchatmode="exact"/.test(eng), "the engine's chat is the one place Exact remains");
});

/* ── slice I: function templates and the live function chat ────────────────
   holding/plans/department-screen/LLD-FUNCTIONS.md, DECISIONS.md DS-8..DS-12. */
const FUNCTIONS_READ = {
  picked: { identity: { id: "identity/default", name: "Default", use_case: "Any department" },
            adaptation: { id: "adaptation/default", name: "Default", use_case: "Any department" },
            priority: { id: "priority/default", name: "Default", use_case: "Any department" },
            coordination: { id: "coordination/default", name: "Default", use_case: "Any department" },
            audit: { id: "audit/money-movement", name: "Money movement", use_case: "A department that moves money" } },
  templates: { audit: [{ id: "audit/default", name: "Default", use_case: "Any department" },
                       { id: "audit/money-movement", name: "Money movement", use_case: "A department that moves money" },
                       { id: "audit/product-build", name: "Product build", use_case: "A department that ships a product" }] },
};
function memStore(seed){
  const m = Object.assign({}, seed || {});
  return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; }, _m: m };
}
/* A document just big enough for the frame manager: one body, elements that
   remember their children, and a placeholder the card painted. */
function frameDoc(key){
  const made = [];
  const mk = (tag) => {
    const el = { tag, children: [], style: {}, hidden: false, isConnected: true, parentNode: null, className: "", src: "", title: "",
      appendChild(ch){ ch.parentNode = el; el.children.push(ch); return ch; },
      removeChild(ch){ el.children = el.children.filter(x => x !== ch); ch.parentNode = null; return ch; } };
    made.push(el);
    return el;
  };
  const ph = { getAttribute: () => key, getBoundingClientRect: () => ({ left: 10, top: 20, width: 600, height: 400 }) };
  const doc = { listeners: {}, made, ph, body: mk("body"),
    addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); },
    createElement: mk,
    querySelector: (sel) => (doc.ph && /data-dpframe/.test(sel) ? doc.ph : null),
    getElementById: () => null };
  return doc;
}

test("slice I + J: a function card's tabs are its own and Chat (live); an engine keeps its record chat", () => {
  const c = fresh();
  c.localStorage = memStore();
  const card = fnCard(c, "audit", AUDIT);
  const panes = (card.match(/data-dppane="([a-z]+)"/g) || []).map(m => /"([a-z]+)"/.exec(m)[1]);
  assert.deepStrictEqual(panes, ["audit", "chat"]);
  const eng = engCard(fresh(), "chat", "nightly");
  assert.ok(eng.indexOf("data-dpchatstart") === -1, "an engine card keeps its record chat, not a live one");
  assert.ok(eng.indexOf("data-dpchatmode") !== -1, "with its two readings");
});

test("slice I: before a chat exists the Chat tab offers one button and sends nothing", () => {
  const c = fresh();
  c.localStorage = memStore();
  const html = fnCard(c, "audit", AUDIT, "chat");
  assert.ok(html.indexOf("No chat with Audit yet") !== -1);
  assert.ok(html.indexOf('data-dpchatstart="audit"') !== -1 && html.indexOf(">Start the chat with Audit<") !== -1);
  assert.ok(html.indexOf("<iframe") === -1 && html.indexOf("data-dpframe") === -1, "no frame until the click");
  assert.strictEqual(c.calls.apiPost.length, 0, "nothing sent");
  assert.strictEqual(click(c, elem({ dpchatstart: "audit" })), true);
  assert.strictEqual(c.dpS().chatStart["r4:audit"], true);
  const after = fnCard(c, "audit", AUDIT, "chat");
  assert.ok(after.indexOf('data-dpframe="r4:audit"') !== -1, "the placeholder the frame is laid over");
  assert.ok(after.indexOf("<iframe") === -1, "the frame never rides in the repainted HTML");
});

test("slice I: a chat this card started before is reopened, not offered again", () => {
  const c = fresh();
  c.localStorage = memStore({ "sutra.fnchat": JSON.stringify({ "r4:priority": { claude_session: "u-1" } }) });
  const html = fnCard(c, "priority", PRIORITY, "chat");
  assert.ok(html.indexOf('data-dpframe="r4:priority"') !== -1);
  assert.ok(html.indexOf("data-dpchatstart") === -1);
  c.localStorage = memStore({ "sutra.fnchat": "{not json" });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.dpFnChatMap())), {}, "a broken map reads as empty");
});

test("slice I + J: Identity's Chat tab is the live chat, and its record turns are Recent on the card", () => {
  const c = fresh();
  c.localStorage = memStore();
  const live = idCard(c, IDENTITY, "chat");
  assert.ok(live.indexOf('data-dpchatstart="identity"') !== -1 && live.indexOf("Start the chat with Identity") !== -1);
  const card = idCard(fresh(), IDENTITY);
  assert.ok(card.indexOf("Write the goal of Org") !== -1, "the owner's own rows, on the card");
});

test("slice I: the frame is made once, kept across paints, and hidden off the screen", () => {
  const c = fresh();
  c.localStorage = memStore();
  const doc = frameDoc("r4:audit");
  c.document = doc; c.window = { addEventListener(){} };
  const st = c.dpS(); st.sel = "r4"; st.selName = "Experience"; st.chatStart["r4:audit"] = true;
  c.dpAfterPaint(null);
  const host = doc.made.find(e => e.className === "dpframehost");
  assert.ok(host, "one host on the body");
  assert.strictEqual(doc.body.children.length, 1);
  assert.strictEqual(host.children.length, 1);
  const fr = host.children[0];
  assert.strictEqual(fr.tag, "iframe");
  assert.strictEqual(fr.src, "/?embed=chat&dept=r4&fn=audit&name=Experience&start=1");
  assert.strictEqual(host.hidden, false);
  assert.strictEqual(host.style.width, "600px");
  c.dpAfterPaint(null); c.dpAfterPaint(null);
  assert.strictEqual(host.children.length, 1);
  assert.strictEqual(host.children[0], fr, "the same element: a repaint never reloads the chat");
  c.S.screen = "chats";
  c.dpAfterPaint(null);
  assert.strictEqual(host.hidden, true, "hidden, not emptied, when the screen changes");
  assert.strictEqual(host.children[0], fr);
  c.S.screen = "org2";
  doc.ph = { getAttribute: () => "r4:priority", getBoundingClientRect: () => ({ left: 0, top: 0, width: 500, height: 300 }) };
  c.dpAfterPaint(null);
  assert.strictEqual(host.children.length, 1, "one live frame");
  assert.notStrictEqual(host.children[0], fr, "another function's chat replaces it");
  assert.ok(/fn=priority/.test(host.children[0].src) && !/start=1/.test(host.children[0].src),
    "resume unless this card asked to start");
  c.dpSelect("r5");
  assert.strictEqual(host.children.length, 0, "a chat belongs to its department");
});

test("slice I: the brief is filled from Identity and stays under 4000 characters", () => {
  const c = fresh();
  const out = c.dpFillBrief("A {department} B {goal} C {done} D {rules} E {owner} F {folder}",
    { department: "Servicing", goal: "Every EMI matched by 8", done: "Zero breaks for a week",
      rules: [{ tag: "ask", text: "Payments over the line" }, { tag: "refuse", text: "Posting after cut-off" }],
      owner: "Meera", folder: "/work/servicing" });
  assert.strictEqual(out, "A Servicing B Every EMI matched by 8 C Zero breaks for a week D ask: Payments over the line; refuse: Posting after cut-off E Meera F /work/servicing");
  const bare = c.dpFillBrief("{department}|{goal}|{done}|{rules}|{owner}|{folder}", {});
  assert.strictEqual(bare, "this department|not written yet|not written yet|none written yet|not named yet|no folder yet");
  const long = c.dpFillBrief("{rules}" + "x".repeat(3900), { rules: Array.from({ length: 200 }, (_, i) => ({ tag: "go", text: "rule " + i })) });
  assert.ok(long.length <= 4000);
});

test("slice I: the template line names the template and Change files an ask, never a write", async () => {
  const c = fresh();
  const st = c.dpS();
  st.functions = Object.assign({ ref: "r4" }, FUNCTIONS_READ);
  const card = fnCard(c, "audit", AUDIT);
  assert.ok(card.indexOf("Runs the Money movement template") !== -1);
  assert.ok(card.indexOf('data-dptplopen="audit"') !== -1);
  assert.strictEqual(click(c, elem({ dptplopen: "audit" })), true);
  const pick = fnCard(c, "audit", AUDIT);
  assert.ok(pick.indexOf(">In use<") !== -1, "the current one says so");
  assert.strictEqual((pick.match(/data-dptpluse=/g) || []).length, 2, "the other two can be asked for");
  assert.ok(pick.indexOf("A department that ships a product") !== -1, "each row carries its use case");
  assert.strictEqual(click(c, elem({ dptpluse: "audit/product-build", dptplfn: "audit" })), true);
  await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0])), { p: "/api/org2/request",
    body: { kind: "org.template", args: { ref: "r4", function: "audit", template: "audit/product-build" } } });
  const after = fnCard(c, "audit", AUDIT);
  assert.ok(after.indexOf("Asked; stamp it in Now") !== -1);
  assert.ok(after.indexOf("data-dptplopen") === -1 && after.indexOf("data-dptpluse") === -1, "one ask at a time");
  c.dpAfterDecide("r4", "org.template");
  assert.strictEqual(c.dpS().fnAsked["r4:audit"], undefined, "a decided ask ends the line");
  assert.ok(c.calls.apiGet.indexOf("/api/dept/r4/functions") !== -1, "and the picks are read again");
});

test("slice I: no word the screen does not say, on the template line, the picker or the chat tab", () => {
  const c = fresh();
  c.localStorage = memStore();
  const st = c.dpS();
  st.functions = Object.assign({ ref: "r4" }, FUNCTIONS_READ);
  st.fnPick = "audit";
  const all = fnCard(c, "audit", AUDIT) + fnCard(c, "audit", AUDIT, "chat") + idCard(c, IDENTITY, "owner");
  assert.strictEqual(all.toLowerCase().indexOf("charter"), -1);
});

test("slice I: the chat-only frame starts the chat from the brief, filed under the department", async () => {
  const c = fresh();
  const got = { newSession: null, submit: null };
  c.URLSearchParams = URLSearchParams;
  c.location = { search: "?embed=chat&dept=r4&fn=audit&name=Experience&start=1" };
  c.S.ui = { dest: "org2" }; c.S.sessions = [];
  c.apiGet = (p) => {
    c.calls.apiGet.push(p);
    if (/brief$/.test(p)) return Promise.resolve({ brief: "Audit for {department}: {goal}", cwd: "/work/exp", template: {} });
    if (/identity$/.test(p)) return Promise.resolve({ goal: "Own the experience", done: null, rules: [], owner: { name: "Sankalp" } });
    return new Promise(() => {});
  };
  c.newSession = (cwd, dept) => { got.newSession = { cwd, dept }; return { id: "s-9" }; };
  c.submitTurn = (seed, sid, opts) => { got.submit = { seed, sid, opts }; };
  const s = await c.dpEmbedOpen();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(got.newSession)), { cwd: "/work/exp", dept: { ref: "r4", name: "Experience" } });
  assert.strictEqual(s.title, "Audit · Experience");
  assert.strictEqual(s.fnKey, "r4:audit");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(got.submit)), { seed: "Audit for Experience: Own the experience", sid: "s-9",
    opts: { pin: { department_ref: "r4" } } });
  assert.strictEqual(c.S.ui.dest, "chats");
  assert.deepStrictEqual(Array.from(c.S.openPanes), ["s-9"], "one chat and nothing else");
});

test("slice I: the chat-only frame reopens the chat it started, and makes no new one", async () => {
  const c = fresh();
  const opened = [];
  c.URLSearchParams = URLSearchParams;
  c.location = { search: "?embed=chat&dept=r4&fn=audit&name=Experience" };
  c.localStorage = memStore({ "sutra.fnchat": JSON.stringify({ "r4:audit": { claude_session: "u-7" } }) });
  c.S.ui = { dest: "org2" };
  c.S.sessions = [{ id: "u-6", claude_session: "u-6" }, { id: "u-7", claude_session: "u-7" }];
  c.S.openPanes = [];
  c.pushPane = (id) => { opened.push(id); c.S.openPanes.push(id); };
  c.ensureTranscript = () => {};
  c.newSession = () => { throw new Error("no new chat on reopen"); };
  const s = await c.dpEmbedOpen();
  assert.strictEqual(s.id, "u-7");
  assert.deepStrictEqual(opened, ["u-7"]);
});

test("slice I: only the chat-only frame records its chat, and only under its own key", () => {
  const c = fresh();
  const written = [];
  c.lsSet = (k, v) => written.push([k, v]);
  c.S.sutraId = { "s-9": "chat-9" };
  c.dpFnChatRemember({ id: "s-9", fnKey: "r4:audit", claude_session: "u-9" });
  assert.strictEqual(written.length, 0, "outside the frame, nothing is written");
  c.EMBED_CHAT = true;
  c.localStorage = memStore();
  c.dpFnChatRemember({ id: "s-9", fnKey: "r4:audit", claude_session: "u-9" });
  assert.strictEqual(written.length, 1);
  assert.strictEqual(written[0][0], "sutra.fnchat");
  assert.strictEqual(written[0][1]["r4:audit"].claude_session, "u-9");
  assert.strictEqual(written[0][1]["r4:audit"].sutra_id, "chat-9");
});

/* ── slice J: the template as a framework, the graph, the added sections ──── */
const FULL_TPL = {
  picked: {
    identity: { id: "identity/default", name: "Default", use_case: "Any department",
      floor: ["Holds the goal, done line, rules, budget and owner"], choices: ["Which effects to raise"],
      reads: ["Every effect recorded"], may_propose: ["A change to the goal"], schedule: "On every effect",
      checks: ["Every effect has a verdict"] },
    adaptation: { id: "adaptation/default", name: "Default", use_case: "Any department",
      floor: ["Reads the record for repeats"], choices: ["Which pattern is worth an engine"],
      reads: ["Asks and their stamps"], may_propose: ["A new engine"], schedule: "Weekly",
      checks: ["Every pattern is proposed or refused with a reason"] },
    priority: { id: "priority/money-movement", name: "Money movement", use_case: "A department that moves money",
      floor: ["Admits each row with its origin"], choices: ["The order of the queue"], reads: ["The queue"],
      may_propose: ["A budget change"], schedule: "Each morning", checks: ["Every row has an origin"] },
    coordination: { id: "coordination/default", name: "Default", use_case: "Any department",
      floor: ["One holder per work item"], choices: ["Who takes it"], reads: ["Open work items"],
      may_propose: ["A hand-off rule"], schedule: "On every hand-off", checks: ["Every hand-off has a row"] },
    audit: { id: "audit/default", name: "Default", use_case: "Any department",
      floor: ["Checks claims against the record"], choices: ["Which claims first"], reads: ["Claims"],
      may_propose: ["A new standing check"], schedule: "Daily", checks: ["Every claim has a result"] },
  },
  templates: { audit: [{ id: "audit/default", name: "Default", use_case: "Any department" }] },
};
function withTpl(c){ c.dpS().functions = Object.assign({ ref: "r4" }, FULL_TPL); return c; }

test("slice J: a function card opens on its template's framework, in the template's own lines", () => {
  const c = withTpl(fresh());
  c.localStorage = memStore();
  const card = fnCard(c, "priority", PRIORITY);
  assert.ok(card.indexOf("The Money movement template") !== -1, "the name of the template it runs");
  assert.ok(card.indexOf("A department that moves money") !== -1, "when it is picked");
  for (const label of ["Always does", "Decides", "Reads", "May propose", "How we know it worked", "Runs"])
    assert.ok(card.indexOf(">" + label + "<") !== -1, "missing part: " + label);
  assert.ok(card.indexOf("Admits each row with its origin") !== -1, "the template's own line");
  assert.ok(card.indexOf("Each morning") !== -1, "and when it runs");
});

test("slice J: Adaptation draws the department and lists every engine's steps", () => {
  const c = withTpl(fresh());
  c.localStorage = memStore();
  const card = fnCard(c, "adaptation", ADAPTATION, null, { engines: Object.assign({ ref: "r4" }, ENGINES) });
  assert.ok(card.indexOf("<svg") !== -1 && card.indexOf("dpgraph") !== -1, "a drawing, not a list");
  for (const w of ["The owner", "Identity", "Priority", "Coordination", "Audit", "Nightly sweep"])
    assert.ok(card.indexOf(w) !== -1, "missing from the graph: " + w);
  assert.ok(card.indexOf("What each engine does, step by step") !== -1);
  assert.ok(card.indexOf("read the folder") !== -1 && card.indexOf("file what changed") !== -1, "its steps");
});

test("slice J: Priority shows when each engine runs next, off the engine's own record", () => {
  const c = withTpl(fresh());
  c.localStorage = memStore();
  const eng = { engines: [Object.assign({}, ENGINES.engines[0], { next_run: "2026-09-23T03:30:00+05:30" }),
                          Object.assign({}, ENGINES.engines[1], { next_run: null })] };
  const card = fnCard(c, "priority", PRIORITY, null, { engines: Object.assign({ ref: "r4" }, eng) });
  assert.ok(card.indexOf("Next runs") !== -1);
  assert.ok(card.indexOf("next 03:30") !== -1, "the clock the record carries");
  assert.ok(card.indexOf("not scheduled") !== -1, "and the one with no next run says so");
});

test("slice J: Coordination says who makes each engine's work and who reads it", () => {
  const c = withTpl(fresh());
  c.localStorage = memStore();
  const card = fnCard(c, "coordination", COORD, null, { engines: Object.assign({ ref: "r4" }, ENGINES) });
  assert.ok(card.indexOf("Who makes it, who reads it") !== -1);
  assert.ok(card.indexOf("from an ask") !== -1, "the engine born from an ask");
  assert.ok(card.indexOf("written by the owner") !== -1, "and the one written by hand");
  assert.ok(card.indexOf("nobody named yet") !== -1, "no reader is invented");
});

test("slice J: a department with no engines still draws its graph and adds no empty section", () => {
  const c = withTpl(fresh());
  c.localStorage = memStore();
  const card = fnCard(c, "adaptation", EMPTY.adaptation);
  assert.ok(card.indexOf("dpgraph") !== -1 && card.indexOf("No engines yet") !== -1);
  assert.ok(card.indexOf("What each engine does") === -1, "no section for engines that do not exist");
  const pri = fnCard(withTpl(fresh()), "priority", EMPTY.priority);
  assert.ok(pri.indexOf("Next runs") === -1);
});

Promise.all(pending).then(() => {
  console.log("\n" + (failed ? failed + " failed" : "all passed") + " (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
