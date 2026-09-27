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
    systems: ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(n => ({ name: n, state: /Adaptation|Audit/.test(n) ? "paused" : "running", last: null })),
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
      if (/\/artifact\//.test(p)) return Promise.resolve({ name: "Live site", slug: "live-site", versions: [
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
  assert.ok(/data-wbfound="open">New website organisation…<\/button>/.test(c.o2MenuHtml(WEB, c.o2Data())));
  const a = panelHtml.indexOf("/static/js/22-website.js"), b = panelHtml.indexOf("/static/js/09-tail.js"), d = panelHtml.indexOf("/static/js/20-dept.js");
  assert.ok(d >= 0 && a > d && b > a);
});
test("W10b: the command founds the organisation, gives the goal, and opens its department", async () => {
  const c = fresh();
  click(c, { wbfound: "open" }, false);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "org" }, value: "City Care Hospital" } }));
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "goal" }, value: "A website for the hospital" } }));
  click(c, { wbfound: "go" }, false);
  for (let i = 0; i < 8; i++) await sleep();
  const posts = JSON.parse(JSON.stringify(c.calls.apiPost));
  assert.deepStrictEqual(posts.slice(0, 2), [
    { p: "/api/native/found", body: { org: "City Care Hospital", dept: "Website" } },
    { p: "/api/native/r3/goal", body: { text: "A website for the hospital" } }]);
  assert.strictEqual(vm.runInContext("o2S().sel", c), "r3");
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

Promise.all(pending).then(() => {
  console.log("-".repeat(60));
  console.log(failed ? " " + failed + " failed (" + ran + " tests)" : " all passed (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
