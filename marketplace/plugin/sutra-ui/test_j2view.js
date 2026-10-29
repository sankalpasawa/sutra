#!/usr/bin/env node
/* test_j2view.js -- the department as the J2 prototype's own page (static/js/25-j2view.js; UI-port package j2ui-shell).

   Named claims:
     J1  j2vEnabled is on, `?j2view=off` turns it off and is kept, a stored "off" holds, `?j2view=on` turns it on and is kept
     J2  j2vOn is true only for a website department on the engine runtime whose map is read, on the page's tabs; never
         for a Root, the first build's way, kind default or organic, before the map is read, with the switch off, or in
         records mode, on an engine, filed work or a function's pane
     J3  wbTab folds chat, map, five, board, activity and status (and no tab chosen) into `j2`, answers `records` for the
         records tab, and answers as it always did for every other tab and every other department
     J4  with the page on the screen has no list column and a placeholder for the frame with the department's ref, under
         the `wide` body; with the switch off, or for another kind, it is the classic screen
     J5  the frame: one iframe after two paints, the same element kept, its src /j2ui/<ref>/, no sandbox attribute, the host
         hidden when the placeholder goes or the screen changes and dropped only when the department changes
     J6  the bar carries Stop (data-wbstop) while the department runs and Start (data-wbresume) while it is off, and Settings
         and records; the records tab is a card with a way back
     J7  records mode shows the classic list with one Department view row and none of Chat, Map, Board, Agent activity; a
         function row leaves it for the function's pane, whose Settings tab is there
     J8  j2vHtml reads the department's clock and opens it (wbTick, dpSelect) when the list column does not
     J9  the module is loaded after 24-functions.js and before the tail, owns only j2v / J2V_ names, writes no colour
         literal, sets no sandbox, and every hook in 19-org2.js and 22-website.js is guarded by typeof

   Harness: test_website.js's fresh(), with 25-j2view.js loaded after 24-functions.js (panel.html's order), a fake DOM for
   the frame. Run: node test_j2view.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
const orgSrc = read("03-org.js"), o2Src = read("19-org2.js"), dpSrc = read("20-dept.js"), wbSrc = read("22-website.js");
const sxSrc = read("23-screens.js"), fvSrc = read("24-functions.js"), jvSrc = read("25-j2view.js");
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
const settle = async () => { for (let i = 0; i < 6; i++) await sleep(); };

const ROOT = { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1, node_kind: "root" };
const ORG  = { ref: "r1", path: "D1", name: "City Care Hospital", parent_ref: "r0", status: "active", ts_minted_ms: 2, node_kind: "organisation" };
const RT   = { ref: "r2", path: "D1.D1", name: "Root", parent_ref: "r1", status: "active", ts_minted_ms: 3, node_kind: "department" };
const WEB  = { ref: "r3", path: "D1.D1.D1", name: "Website", parent_ref: "r2", status: "active", ts_minted_ms: 4, node_kind: "department" };
const BILL = { ref: "r4", path: "D1.D1.D2", name: "Billing", parent_ref: "r2", status: "active", ts_minted_ms: 5, node_kind: "department" };
const NOTE = { ref: "r5", path: "D1.D1.D3", name: "Notes", parent_ref: "r2", status: "active", ts_minted_ms: 6, node_kind: "department" };
const OLD  = { ref: "r6", path: "D1.D1.D4", name: "First build", parent_ref: "r2", status: "active", ts_minted_ms: 7, node_kind: "department" };
const TREE = [ROOT, ORG, RT, WEB, BILL, NOTE, OLD];
const DEPTS = [{ ref: "r2", name: "Root", stopped: false, kind: "root", parent: "r1", working: [] },
               { ref: "r3", name: "Website", stopped: false, kind: "website", parent: "r2", working: [] },
               { ref: "r4", name: "Billing", stopped: false, kind: "default", parent: "r2", working: [] },
               { ref: "r5", name: "Notes", stopped: false, kind: "organic", parent: "r2", working: [] },
               { ref: "r6", name: "First build", stopped: false, kind: "website", parent: "r2", working: [] }];

/* What the department's map answers (website_dept.map_view): the record, its engines and what it filed. */
const ENGS = [["Plan", "Brief", "Site plan", "model"], ["Write", "Site plan", "Pages", "model"],
              ["Check", "Pages", "Build", "code"], ["Publish", "Build", "Live site", "code"]];
function mapOf(ref, o){
  o = o || {};
  const names = { r2: "Root", r3: "City Care Hospital Website", r4: "Billing", r5: "Notes", r6: "First build" };
  return {
    ref, name: names[ref], goal: "A live website for City Care Hospital", done: "Every page checked and live",
    rules: [], owner: "Sankalp", control: "granted", stopped: !!o.stopped, has_goal: true, live: false,
    runtime: o.runtime || 2, kind: o.kind || "website", j2: (o.runtime || 2) === 2, root: "r2", planned: true,
    systems: ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(n => ({ name: n, state: "running", last: null })),
    engines: ENGS.map(e => ({ name: e[0], reads: e[1], writes: e[2], runs_as: e[3], slot: "after a new " + e[1], state: "Idle",
      envelope: { calls: 30, usd: 6, used_calls: 3, used_usd: 0.4 }, window_min: 15, last: { status: "ok", at: "2026-09-27T11:02:00+05:30", what: "" } })),
    artifacts: ["Brief", "Site plan", "Pages", "Build", "Live site"].map(n => ({ name: n, slug: n.toLowerCase().replace(/ /g, "-"), versions: n === "Pages" ? 3 : 1, latest: null })),
    status: { asks: [], escalated: [], waits: [], running: [], stopped: !!o.stopped, next: "nothing due" },
    health: { motor: { last_tick: "2026-09-27T11:09:00+05:30", age_s: 2 }, checks: [], never: [], timeline: [] },
    recent: [], requests: [], templates: {},
  };
}
const KINDS = { r2: { kind: "root" }, r3: {}, r4: { kind: "default" }, r5: { kind: "organic" }, r6: { runtime: 1 } };

/* A fake DOM, just enough for the frame: nodes that hold children, a placeholder the page may or may not have painted,
   the listeners the module asks the window for and the observer it starts on #panes. */
function makeDom(){
  const dom = { placeholder: null, win: {}, observers: [], listeners: {}, made: [] };
  const node = tag => {
    const el = { tag, children: [], style: {}, hidden: false, isConnected: true, parentNode: null, attrs: {}, className: "", title: "", src: "", id: "", innerHTML: "",
      appendChild(c){ c.parentNode = el; el.children.push(c); return c; },
      removeChild(c){ const i = el.children.indexOf(c); if (i >= 0) el.children.splice(i, 1); c.parentNode = null; return c; },
      getAttribute(k){ return k in el.attrs ? el.attrs[k] : null; }, setAttribute(k, v){ el.attrs[k] = String(v); } };
    dom.made.push(el);
    return el;
  };
  const body = node("body"), panes = node("div");
  dom.body = body;
  dom.setPlaceholder = (ref, w, h) => {
    dom.placeholder = ref === null ? null : Object.assign(node("div"), { rect: { left: 232, top: 84, width: w === undefined ? 1090 : w, height: h === undefined ? 760 : h } });
    if (dom.placeholder){
      dom.placeholder.attrs["data-j2frame"] = ref;
      dom.placeholder.getBoundingClientRect = () => dom.placeholder.rect;
    }
  };
  dom.scBody = { querySelector: sel => (sel === "[data-j2frame]" && dom.placeholder) ? dom.placeholder : null };
  dom.document = {
    listeners: dom.listeners, activeElement: null, body,
    addEventListener(type, fn){ (dom.listeners[type] = dom.listeners[type] || []).push(fn); },
    querySelector(sel){
      const m = /^\[data-j2frame="([^"]*)"\]$/.exec(sel);
      return m && dom.placeholder && dom.placeholder.attrs["data-j2frame"] === m[1] ? dom.placeholder : null;
    },
    querySelectorAll(){ return []; }, getElementById(id){ return id === "panes" ? panes : null; },
    createElement: node,
  };
  dom.window = { addEventListener(type, fn){ (dom.win[type] = dom.win[type] || []).push(fn); } };
  dom.MutationObserver = class { constructor(cb){ this.cb = cb; this.observed = []; dom.observers.push(this); } observe(target, opts){ this.observed.push([target, opts]); } };
  return dom;
}

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], render: 0, ls: [] };
  const dom = makeDom();
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Math, encodeURIComponent, Promise, setTimeout, clearTimeout, isNaN,
    setInterval: () => 1, clearInterval: () => {},
    apiGet: (p) => {
      calls.apiGet.push(p);
      if (p === "/api/native/depts") return Promise.resolve({ depts: opts.none ? [] : JSON.parse(JSON.stringify(opts.depts || DEPTS)) });
      const m = /^\/api\/native\/(r\d)\/map$/.exec(p);
      if (m) return Promise.resolve(JSON.parse(JSON.stringify(mapOf(m[1], Object.assign({}, KINDS[m[1]], (opts.maps || {})[m[1]])))));
      if (/^\/api\/dept\//.test(p)) return Promise.resolve({});
      return new Promise(() => {});
    },
    apiPost: (p, body) => { calls.apiPost.push({ p, body }); return Promise.resolve({ ref: "r3" }); },
    window: dom.window, MutationObserver: dom.MutationObserver,
    location: { search: opts.search || "" },
    localStorage: { getItem: k => (opts.stored && k in opts.stored ? opts.stored[k] : null), setItem(){} },
    lsSet: (k, v) => { calls.ls.push([k, v]); },
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
    document: dom.document,
  };
  ctx.calls = calls; ctx.dom = dom;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  [o2Src, dpSrc, wbSrc, sxSrc, fvSrc, jvSrc].forEach(src => vm.runInContext(src, ctx));
  vm.runInContext("wbS().v2 = true;", ctx);
  return ctx;
}
const run = (c, code) => vm.runInContext(code, c);
/* the department list and the map of one department read, as the screen has them a moment after it opens */
async function opened(ref, opts){
  const c = fresh(opts);
  run(c, "o2S().loaded = true;");
  c.o2Select(ref);
  for (let k = 0; k < 4; k++){ c.o2ScreenHtml(); await settle(); }
  return c;
}
function click(c, ds){
  let prevented = false;
  const el = { dataset: ds, closest(sel){
    const keys = Object.keys(ds).map(k => "[data-" + k.toLowerCase() + "]");
    if (sel === ".dp" || sel === ".wb" || sel === ".o2") return el;
    return sel.split(",").some(s => keys.indexOf(s.trim()) >= 0) ? el : null;
  } };
  const ev = { target: el, preventDefault(){ prevented = true; }, stopPropagation(){} };
  (c.document.listeners.click || []).forEach(fn => fn(ev));
  return prevented;
}
const node = (c, ref) => c.o2Data().byRef.get(ref);
const only = (ref, o) => ({ maps: { [ref]: o } });

/* ── J1 ────────────────────────────────────────────────────────────────── */
test("J1: the page is on; ?j2view=off turns it off and is kept; a stored off holds; ?j2view=on turns it on and is kept", () => {
  let c = fresh();
  assert.strictEqual(c.j2vEnabled(), true);
  assert.deepStrictEqual(c.calls.ls, [], "nothing written when nothing was said");
  c = fresh({ search: "?x=1&j2view=off" });
  assert.strictEqual(c.j2vEnabled(), false);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.ls)), [["sutra.j2view", "off"]], "kept through lsSet");
  c = fresh({ stored: { "sutra.j2view": '"off"' } });
  assert.strictEqual(c.j2vEnabled(), false);
  assert.deepStrictEqual(c.calls.ls, [], "a stored value is read, not written again");
  c = fresh({ search: "?j2view=on", stored: { "sutra.j2view": '"off"' } });
  assert.strictEqual(c.j2vEnabled(), true);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.ls)), [["sutra.j2view", "on"]]);
  c = fresh({ stored: { "sutra.j2view": "{broken" } });
  assert.strictEqual(c.j2vEnabled(), true, "a stored value that does not parse is no answer");
  c = fresh({ search: "?j2view=off" });
  c.j2vEnabled(); c.location.search = "";
  assert.strictEqual(c.j2vEnabled(), false, "read once for the page's life");
});

test("J1: the module writes storage only through lsSet", () => {
  assert.ok(!/localStorage\.(setItem|removeItem)/.test(jvSrc));
  assert.ok(/lsSet\(J2V_KEY/.test(jvSrc) && /J2V_KEY = "sutra\.j2view"/.test(jvSrc));
});

/* ── J2 ────────────────────────────────────────────────────────────────── */
test("J2: the page is for every department on the engine runtime whose map says j2 and is read, and nothing else", async () => {
  const c = await opened("r3");
  const on = ref => c.j2vOn(ref);
  await settle();
  for (const r of ["r4", "r5"]) c.wbLoadMap(r);
  await settle();
  assert.strictEqual(on("r3"), true, "a website department");
  assert.strictEqual(on("r2"), false, "a Root keeps its chat until it is sent to the page (J2_ROOT_DEFAULT is false)");
  assert.strictEqual(on("r4"), true, "kind default");
  assert.strictEqual(on("r5"), true, "kind organic");
  assert.strictEqual(on("r6"), false, "the first build's way (runtime 1)");
  assert.strictEqual(on("r9"), false, "a ref nobody has");
  assert.strictEqual(on(""), false);
  const early = fresh();
  assert.strictEqual(early.j2vOn("r3"), false, "before the map is read");
  assert.strictEqual(early.j2vEligible("r3"), false);
  const off = await opened("r3", { search: "?j2view=off" });
  assert.strictEqual(off.j2vOn("r3"), false, "the switch off");
  run(c, "S.ui.j2off = { r3: true }");
  assert.strictEqual(c.j2vOn("r3"), false, "the per-department switch (Settings and records) leaves the page for the page's life");
  assert.strictEqual(c.j2vTab("r3"), null);
  c.j2vSetOff("r3", false);
  assert.strictEqual(c.j2vOn("r3"), true);
});

test("J2: parity: j2vEligible is the map's j2 for every kind of the fixture, and the module holds no kind list", async () => {
  const c = fresh();
  run(c, "o2S().loaded = true;");
  for (const r of ["r2", "r3", "r4", "r5", "r6"]) c.wbLoadMap(r);
  await settle();
  const want = { r2: true, r3: true, r4: true, r5: true, r6: false };
  for (const r of Object.keys(want)) assert.strictEqual(c.j2vEligible(r), want[r], r);
  run(c, "wbS().map['r3'] = { runtime: 2, kind: 'website' }");
  assert.strictEqual(c.j2vEligible("r3"), false, "no j2 key, no page");
  run(c, "wbS().map['r3'] = { runtime: 2, kind: 'brand-new-kind', j2: true }");
  assert.strictEqual(c.j2vEligible("r3"), true, "a kind this file has never heard of");
  assert.ok(!/"website"|'website'|"default"|"organic"/.test(jvSrc.replace(/\/\*[^]*?\*\//g, "")), "no kind named in code");
  assert.strictEqual(run(c, "J2_ROOT_DEFAULT"), false);
});

test("J2: Root's page is one click away from its chat, and the bar leads back to the chat", async () => {
  const c = fresh();
  run(c, "o2S().loaded = true;");
  c.wbLoadMap("r2");
  await settle();
  assert.strictEqual(c.j2vOn("r2"), false);
  run(c, "wbS().tab['r2'] = 'j2'");
  assert.strictEqual(c.j2vOn("r2"), true);
  assert.strictEqual(c.wbTab("r2"), "j2");
  const html = c.j2vHtml({ ref: "r2", name: "Root" });
  assert.ok(/data-wbtab="chat"/.test(html) && !/data-wbtab="records"/.test(html), "back to the chat, no records for a Root");
  run(c, "wbS().tab['r2'] = 'chat'");
  assert.strictEqual(c.j2vOn("r2"), false);
  assert.strictEqual(c.wbTab("r2"), "chat");
});

test("J2: the page holds on its own tabs; an engine, a filed work, a function's pane or records mode leave it", async () => {
  const c = await opened("r3");
  const on = () => c.j2vOn("r3");
  for (const t of ["j2", "chat", "map", "five", "board", "activity", "status"]){
    run(c, "wbS().tab['r3'] = " + JSON.stringify(t));
    assert.strictEqual(on(), true, t);
  }
  run(c, "delete wbS().tab['r3']");
  assert.strictEqual(on(), true, "no tab chosen");
  for (const t of ["records", "engine", "art", "conversation", "motor", "root", ""]){
    run(c, "wbS().tab['r3'] = " + JSON.stringify(t));
    assert.strictEqual(on(), false, JSON.stringify(t));
  }
});

/* ── J3 ────────────────────────────────────────────────────────────────── */
test("J3: wbTab folds the six tabs into the page and answers records; every other answer is as it was", async () => {
  const c = await opened("r3");
  for (const t of ["chat", "map", "five", "board", "activity", "status", "j2"]){
    run(c, "wbS().tab['r3'] = " + JSON.stringify(t));
    assert.strictEqual(c.wbTab("r3"), "j2", t + " lands on the page");
  }
  run(c, "delete wbS().tab['r3']");
  assert.strictEqual(c.wbTab("r3"), "j2", "a department opens on the page");
  run(c, "wbS().tab['r3'] = 'records'");
  assert.strictEqual(c.wbTab("r3"), "records");
  for (const t of ["engine", "art", "conversation", ""]){
    run(c, "wbS().tab['r3'] = " + JSON.stringify(t));
    assert.strictEqual(c.wbTab("r3"), t, "the classic answer for " + JSON.stringify(t));
  }
  const other = await opened("r4");
  assert.strictEqual(other.wbTab("r4"), "j2", "a department of another kind opens on the page too");
  run(other, "wbS().tab['r4'] = 'five'");
  assert.strictEqual(other.wbTab("r4"), "j2", "All five is folded into the page for every kind");
  const root = await opened("r2");
  assert.strictEqual(root.wbTab("r2"), "chat", "a Root opens on its chat");
  const first = await opened("r6");
  assert.strictEqual(first.wbTab("r6"), "map", "one of the first build opens on its Map as before");
  const off = await opened("r3", { search: "?j2view=off" });
  assert.strictEqual(off.wbTab("r3"), "chat");
});

/* ── J4 ────────────────────────────────────────────────────────────────── */
test("J4: with the page on the screen has no list column and a placeholder for the frame, under the wide body", async () => {
  const c = await opened("r3");
  const html = c.o2ScreenHtml();
  assert.ok(/<div class="o2body wide">/.test(html), "the wide body");
  assert.ok(!/class="o2list/.test(html) && !/data-dptab=/.test(html), "no list column");
  assert.ok(/<div class="o2viewer j2v wb">/.test(html) && /<div class="j2frame" data-j2frame="r3"><\/div>/.test(html), "the placeholder holds the department's ref");
  assert.strictEqual((html.match(/data-j2frame=/g) || []).length, 1);
  assert.strictEqual(run(c, "dpS().sel"), "r3", "the department is open though its list column is not painted");
});

test("J4: every kind on the engine runtime opens the page, and the frame holds its ref", async () => {
  for (const ref of ["r4", "r5"]){
    const c = await opened(ref);
    const html = c.o2ScreenHtml();
    assert.ok(new RegExp('<div class="j2frame" data-j2frame="' + ref + '"></div>').test(html) && !/class="o2list/.test(html), ref);
  }
});

test("J4: for a department the page is not for, and with the switch off, the screen is the classic one", async () => {
  for (const [ref, opts] of [["r6", {}], ["r3", { search: "?j2view=off" }], ["r4", { search: "?j2view=off" }]]){
    const c = await opened(ref, opts);
    const html = c.o2ScreenHtml();
    assert.ok(/class="o2list dplist dp"/.test(html) && !/data-j2frame/.test(html) && !/j2vbar/.test(html), ref + " " + JSON.stringify(opts));
  }
});

test("J4: the organisation's row is still Root's chat, whatever the switch says", async () => {
  const c = fresh();
  run(c, "o2S().loaded = true;");
  c.o2Select("r1");
  for (let k = 0; k < 4; k++){ c.o2ScreenHtml(); await settle(); }
  const html = c.o2ScreenHtml();
  assert.ok(!/data-j2frame/.test(html) && !/j2vbar/.test(html), "no page on the organisation");
  assert.strictEqual(c.j2vOn("r2"), false);
});

/* ── J5 ────────────────────────────────────────────────────────────────── */
test("J5: one iframe after two paints, the same element, src /j2ui/<ref>/, no sandbox; the host is hidden when the placeholder goes and when the screen changes", async () => {
  const c = fresh(), dom = c.dom;
  dom.setPlaceholder("r3");
  c.j2vAfterPaint(dom.scBody);
  c.j2vAfterPaint(dom.scBody);
  const host = dom.body.children[0];
  assert.strictEqual(dom.body.children.length, 1, "one host on the body");
  assert.strictEqual(host.className, "j2vhost");
  assert.strictEqual(host.children.length, 1, "one iframe");
  const fr = host.children[0];
  assert.strictEqual(fr.tag, "iframe");
  assert.strictEqual(fr.src, "/j2ui/r3/");
  assert.strictEqual(fr.className, "j2v-if");
  assert.strictEqual(fr.title, "Department");
  assert.ok(fr.sandbox === undefined && !("sandbox" in fr.attrs), "no sandbox attribute: a sandbox without allow-same-origin could not fetch");
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.children[0], fr, "the same element kept across paints");
  assert.strictEqual(host.hidden, false);
  assert.deepStrictEqual(JSON.parse(JSON.stringify([host.style.left, host.style.top, host.style.width, host.style.height])), ["232px", "84px", "1090px", "760px"], "laid over the placeholder");
  dom.setPlaceholder("r3", 1000, 500);
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.style.width, "1000px");
  assert.strictEqual(host.style.height, "500px");
  /* the placeholder is gone: hidden, never emptied */
  dom.setPlaceholder(null);
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.hidden, true);
  assert.strictEqual(host.children[0], fr, "the frame is kept");
  dom.setPlaceholder("r3");
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.hidden, false);
  assert.strictEqual(host.children[0], fr, "and back, the same frame (the page keeps its place)");
  /* another screen: hidden */
  c.S.screen = "chat";
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.hidden, true);
  c.S.screen = "org2";
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.hidden, false);
  /* a placeholder of no size: hidden */
  dom.setPlaceholder("r3", 0, 0);
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.hidden, true);
});

test("J5: the frame is dropped only when the department changes", () => {
  const c = fresh(), dom = c.dom;
  dom.setPlaceholder("r3");
  c.j2vAfterPaint(dom.scBody);
  const host = dom.body.children[0], first = host.children[0];
  dom.setPlaceholder("r9");
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(host.children.length, 1, "one live frame");
  assert.notStrictEqual(host.children[0], first);
  assert.strictEqual(first.parentNode, null, "the old one is out of the page");
  assert.strictEqual(host.children[0].src, "/j2ui/r9/");
  assert.strictEqual(dom.body.children.length, 1, "the same host");
});

test("J5: the host keeps its place on resize, scroll and every rebuild of the panes; the listeners are added once", () => {
  const c = fresh(), dom = c.dom;
  dom.setPlaceholder("r3");
  c.j2vAfterPaint(dom.scBody);
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual((dom.win.resize || []).length, 1);
  assert.strictEqual((dom.win.scroll || []).length, 1);
  assert.strictEqual(dom.observers.length, 1);
  assert.strictEqual(dom.observers[0].observed[0][0], dom.document.getElementById("panes"));
  const host = dom.body.children[0];
  dom.placeholder.rect = { left: 10, top: 20, width: 300, height: 200 };
  dom.win.resize[0]();
  assert.strictEqual(host.style.left, "10px");
  dom.setPlaceholder(null);
  dom.observers[0].cb();                       /* the panes were rebuilt with no placeholder: the screen was left */
  assert.strictEqual(host.hidden, true);
});

test("J5: no body, no frame (a page that is not ready draws nothing and does not throw)", () => {
  const c = fresh(), dom = c.dom;
  dom.document.body = null;
  dom.setPlaceholder("r3");
  c.j2vAfterPaint(dom.scBody);
  assert.strictEqual(dom.made.filter(x => x.tag === "iframe").length, 0);
});

/* ── J6 ────────────────────────────────────────────────────────────────── */
test("J6: the bar carries Stop while the department runs, Start while it is off, and Settings and records", async () => {
  const c = await opened("r3");
  let html = c.o2ScreenHtml();
  const bar = /<div class="j2vbar">(.*?)<\/div>/.exec(html)[1];
  assert.ok(/data-wbstop="1">Stop</.test(bar) && !/data-wbresume/.test(bar), bar);
  assert.ok(/data-wbtab="records">Settings and records</.test(bar));
  const off = await opened("r3", only("r3", { stopped: true }));
  const bar2 = /<div class="j2vbar">(.*?)<\/div>/.exec(off.o2ScreenHtml())[1];
  assert.ok(/data-wbresume="1"[^>]*>Start</.test(bar2) && !/data-wbstop/.test(bar2), bar2);
  assert.ok(click(off, { wbresume: "1" }));
  await settle();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(off.calls.apiPost[0])), { p: "/api/native/r3/resume", body: {} }, "the bar's switch is the department's own");
  assert.ok(click(c, { wbstop: "1" }));
  await settle();
  assert.strictEqual(c.calls.apiPost[0].p, "/api/native/r3/stop");
});

test("J6: no title header over the page, no counts and no forbidden word on the bar", async () => {
  const c = await opened("r3");
  const html = c.o2ScreenHtml();
  const viewer = html.slice(html.indexOf('<div class="o2viewer j2v wb">'));
  assert.ok(!/class="o2vh"/.test(viewer), "the page has its own title");
  const text = viewer.replace(/<[^>]+>/g, " ");
  assert.ok(!/\d/.test(text), "a number at rest: " + text);
  assert.ok(!/charter|internal system/i.test(text));
});

test("J6: Settings and records opens a card with a way back; the way back is the page", async () => {
  const c = await opened("r3");
  assert.ok(click(c, { wbtab: "records" }));
  assert.strictEqual(c.wbTab("r3"), "records");
  const html = c.o2ScreenHtml();
  assert.ok(!/data-j2frame/.test(html), "the page leaves the screen");
  assert.ok(/<div class="o2vh"><b>Settings and records<\/b>/.test(html) && /<h3>Settings and records<\/h3>/.test(html));
  assert.ok(html.indexOf("Open a function to change its instructions, or an engine or filed work from the list.") >= 0);
  assert.ok(/data-wbtab="j2">Back to the department</.test(html));
  assert.ok(click(c, { wbtab: "j2" }));
  assert.strictEqual(c.j2vOn("r3"), true);
  assert.ok(/data-j2frame="r3"/.test(c.o2ScreenHtml()));
});

/* ── J7 ────────────────────────────────────────────────────────────────── */
test("J7: records mode shows the classic list with one Department view row and none of Chat, Map, Board, Agent activity", async () => {
  const c = await opened("r3");
  click(c, { wbtab: "records" });
  await settle();
  const html = c.o2ScreenHtml();
  assert.ok(/class="o2list dplist dp"/.test(html), "the classic list column is back");
  assert.ok(/<button type="button" class="o2li dpli" data-wbtab="j2"><span>Department view<\/span><\/button>/.test(html), "the one row");
  ["Chat", "Map", "Board", "Agent activity", "System status", "Motor"].forEach(w => assert.ok(html.indexOf("<span>" + w + "</span>") < 0, w + " is not a row here"));
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(f => assert.ok(html.indexOf('data-dptab="' + f + '"') >= 0, f + " keeps its row"));
  ENGS.forEach(e => assert.ok(html.indexOf('data-wbengine="' + e[0] + '"') >= 0, e[0] + " keeps its row"));
  assert.ok(/data-wbart="pages"/.test(html), "Filed work stays");
  assert.ok(/<span>Human Sutra<\/span>/.test(html), "the Human Sutra app stays");
  assert.ok(/<span>All five<\/span>/.test(html));
  const top = c.j2vTop("r3", c.wbS ? c.wbS().map.r3 : null);
  assert.ok(/^<div class="o2g dpg wb"><button[^>]*data-wbtab="j2"/.test(top));
});

test("J7: outside records mode, and for another department, the list's first group is the classic one", async () => {
  const c = await opened("r3");
  assert.strictEqual(c.j2vTop("r3", null), null, "the page is on: no list at all");
  const bill = await opened("r4");
  assert.strictEqual(bill.j2vTop("r4", null), null);
  const first = await opened("r6");
  assert.strictEqual(first.j2vTop("r6", null), null, "a department of the first build has no page to go back to");
  const html = first.o2ScreenHtml();
  ["Map"].forEach(w => assert.ok(html.indexOf("<span>" + w + "</span>") >= 0, w));
  assert.ok(html.indexOf("Department view") < 0);
});

test("J7: a function row leaves records mode for the function's pane, whose Settings tab is there; an engine row likewise", async () => {
  const c = await opened("r3");
  click(c, { wbtab: "records" });
  await settle();
  assert.ok(c.o2ScreenHtml().indexOf("Department view") >= 0);
  click(c, { dptab: "identity" });                  /* the list's own row: the wb capture handler hands the viewer back first */
  assert.strictEqual(run(c, "wbS().tab['r3']"), "", "hands the viewer back to 20-dept.js");
  run(c, "dpS().tab['r3'] = 'identity'");
  assert.strictEqual(c.j2vOn("r3"), false, "still not the page");
  assert.strictEqual(c.wbTab("r3"), "", "the classic answer");
  await settle();
  const html = c.o2ScreenHtml();
  assert.ok(!/data-j2frame/.test(html) && /class="o2list dplist dp"/.test(html), "the classic screen stays");
  assert.ok(/data-dppane="settings"/.test(html), "the function's Settings tab is reachable: " + html.slice(0, 200));
  assert.ok(html.indexOf("Department view") >= 0, "and the way back stays in the list");
  click(c, { wbengine: "Write" });
  assert.strictEqual(c.wbTab("r3"), "engine");
  assert.strictEqual(c.j2vOn("r3"), false);
  click(c, { wbtab: "j2" });
  assert.strictEqual(c.wbTab("r3"), "j2", "the Department view row goes back to the page");
});

test("J7: every link that used to open Chat, Map, All five, Board, Agent activity or System status lands on the page", async () => {
  const c = await opened("r3");
  click(c, { wbtab: "records" });
  for (const t of ["chat", "map", "five", "board", "activity", "status"]){
    click(c, { wbtab: t });
    assert.strictEqual(c.j2vOn("r3"), true, t);
    assert.ok(/data-j2frame="r3"/.test(c.o2ScreenHtml()), t);
    click(c, { wbtab: "records" });
  }
});

/* ── J8 ────────────────────────────────────────────────────────────────── */
test("J8: j2vHtml reads the department's clock and opens it when the list column has not", async () => {
  const c = await opened("r3");
  const log = [];
  c.wbTick = () => log.push("tick");
  c.dpSelect = ref => log.push("select " + ref);
  run(c, "dpS().sel = 'r2'");
  c.j2vHtml(node(c, "r3"));
  assert.deepStrictEqual(log, ["tick", "select r3"]);
  log.length = 0;
  run(c, "dpS().sel = 'r3'");
  c.j2vHtml(node(c, "r3"));
  assert.deepStrictEqual(log, ["tick"], "already open: not opened again");
});

/* ── J9 ────────────────────────────────────────────────────────────────── */
test("J9: panel.html loads 25-j2view.js after 24-functions.js and before the tail, versioned", () => {
  const tags = [...panelHtml.matchAll(/<script src="\/static\/js\/([^"?]+)(\?[^"]*)?"/g)].map(m => [m[1], m[2] || ""]);
  const at = n => tags.findIndex(t => t[0] === n);
  assert.ok(at("25-j2view.js") > at("24-functions.js") && at("25-j2view.js") < at("09-tail.js"), "24 < 25 < tail");
  assert.ok(/__ASSETVER__/.test(tags[at("25-j2view.js")][1]));
  assert.strictEqual(tags.filter(t => t[0] === "25-j2view.js").length, 1);
});

test("J9: the module owns only j2v / J2V_ names and no other script declares one", () => {
  const mine = new Set();
  let m;
  const re = /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^const\s+([A-Za-z_$][\w$]*)/gm;
  while ((m = re.exec(jvSrc))) mine.add(m[1] || m[2]);
  assert.ok(mine.size >= 14, "parsed " + mine.size);
  [...mine].forEach(n => assert.ok(/^(j2v[A-Z]|J2V_|J2_ROOT_DEFAULT$)/.test(n), n + " is not prefixed j2v / J2V_"));
  fs.readdirSync(JS).filter(f => /\.js$/.test(f) && f !== "25-j2view.js").forEach(f => {
    const src = read(f);
    assert.ok(!/\bS\.j2v\b/.test(src), f + " reads S.j2v");
    assert.ok(!/^(?:async\s+)?function\s+j2v[A-Z]|^const\s+J2V_/m.test(src), f + " declares a j2v global");
  });
});

test("J9: the module sets no sandbox, no colour literal and no counts; the frame is the page's own address", () => {
  const code = jvSrc.replace(/\/\*[^]*?\*\//g, "");
  assert.ok(!/sandbox/i.test(code), "an unsandboxed same-origin frame");
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(code), "a colour literal");
  assert.ok(/"\/j2ui\/" \+ encodeURIComponent\(ref\) \+ "\/"/.test(code));
});

test("J9: every function of the module that 19-org2.js and 22-website.js use is guarded by typeof", () => {
  for (const [name, src] of [["19-org2.js", o2Src], ["22-website.js", wbSrc]]){
    const code = src.replace(/\/\*[^]*?\*\//g, "");
    const used = [...new Set(code.match(/\bj2v[A-Z]\w*/g) || [])];
    assert.ok(used.length >= 1, name + " has a hook");
    used.forEach(fn => assert.ok(new RegExp("typeof " + fn + ' === "function"').test(code), name + " uses " + fn + " with no typeof guard"));
  }
  assert.deepStrictEqual([...new Set(wbSrc.replace(/\/\*[^]*?\*\//g, "").match(/\bj2v[A-Z]\w*/g))].sort(), ["j2vEligible", "j2vHtml", "j2vOn", "j2vRecordsHtml", "j2vTab", "j2vTop"], "22-website.js uses six");
  assert.deepStrictEqual([...new Set(o2Src.replace(/\/\*[^]*?\*\//g, "").match(/\bj2v[A-Z]\w*/g))].sort(), ["j2vAfterPaint", "j2vHtml", "j2vOn"], "19-org2.js uses three");
  assert.ok(!/dpLoad|dpSelect|dpS\(\)|dpAskHtml/.test(o2Src), "19-org2.js gains no department logic");
});

test("J9: the stylesheet block is tokens only and has a rule for every class the module emits", () => {
  const i = css.indexOf("/* ── the J2 view (25-j2view.js)");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  const emitted = new Set();
  (jvSrc.match(/class[Nn]ame = "([^"]+)"|class="([^"$]+)"/g) || []).forEach(s => s.replace(/^[^"]*"/, "").replace(/"$/, "").split(/\s+/).forEach(x => x && emitted.add(x)));
  ["j2v", "j2vbar", "j2frame", "j2vhost", "j2v-if"].forEach(k => assert.ok(emitted.has(k), "emitted " + k));
  [...emitted].filter(k => /^j2v?/.test(k)).forEach(k => assert.ok(block.indexOf("." + k) >= 0, "no rule for ." + k));
  assert.ok(/\.j2vhost\[hidden\]\{display:none\}/.test(block), "a hidden host takes no room");
  assert.ok(/\.j2vhost\{[^}]*position:fixed;[^}]*z-index:4/.test(block), "laid over the placeholder like the chat frame");
});

/* ── J10: j2host.js, the one script the app adds around the page ──────────── */
const hostSrc = fs.readFileSync(path.join(__dirname, "j2ui_assets", "j2host.js"), "utf8");
function hosted(answer){
  const calls = [];
  const win = { fetch: (input, init) => { calls.push({ url: typeof input === "string" ? input : input.url, method: String((init && init.method) || (input && input.method) || "GET").toUpperCase(),
                                                       token: new Headers((init && init.headers) || (input && input.headers) || {}).get("X-Sutra-Panel") });
                                          const call = calls[calls.length - 1];
                                          return Promise.resolve().then(() => answer(call, calls)); } };
  const ctx = { window: win, Request, Headers, Promise, Object, String };
  vm.createContext(ctx);
  vm.runInContext(hostSrc, ctx);
  return { fetch: (...a) => win.fetch(...a), calls };
}
const json = (o, status) => new Response(JSON.stringify(o), { status: status || 200 });

test("J10: a GET or HEAD goes through untouched; no token is asked for", async () => {
  const h = hosted(() => json({}));
  await h.fetch("api/state?since=0");
  await h.fetch("api/map", { method: "HEAD" });
  assert.deepStrictEqual(h.calls.map(c => [c.method, c.url, c.token]), [["GET", "api/state?since=0", null], ["HEAD", "api/map", null]]);
});

test("J10: a write carries X-Sutra-Panel; the token is read once and kept", async () => {
  let n = 0;
  const h = hosted(c => c.url === "/api/panel-token" ? json({ token: "tok-" + (++n) }) : json({ ok: true }));
  await h.fetch("api/say", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await h.fetch("api/say", { method: "POST", body: "{}" });
  assert.deepStrictEqual(h.calls.map(c => [c.method, c.url, c.token]),
    [["GET", "/api/panel-token", null], ["POST", "api/say", "tok-1"], ["POST", "api/say", "tok-1"]], "one read of the token, two writes");
});

test("J10: on a 403 the token is read again once and the write is retried once; a second 403 is the answer", async () => {
  let n = 0, said = 0;
  const h = hosted(c => c.url === "/api/panel-token" ? json({ token: "tok-" + (++n) }) : (c.token === "tok-2" ? json({ ok: true }) : json({}, 403)));
  const r = await h.fetch("api/say", { method: "POST", body: "{}" });
  assert.strictEqual(r.status, 200);
  assert.deepStrictEqual(h.calls.map(c => [c.url, c.token]), [["/api/panel-token", null], ["api/say", "tok-1"], ["/api/panel-token", null], ["api/say", "tok-2"]]);
  const never = hosted(c => c.url === "/api/panel-token" ? json({ token: "t" + (++said) }) : json({}, 403));
  const r2 = await never.fetch("api/say", { method: "POST", body: "{}" });
  assert.strictEqual(r2.status, 403);
  assert.strictEqual(never.calls.filter(c => c.url === "api/say").length, 2, "retried once, not in a loop");
});

test("J10: a Request is written the same way, and a token that cannot be read still lets the call go", async () => {
  const h = hosted(c => c.url === "/api/panel-token" ? json({ token: "tok" }) : json({ ok: true }));
  await h.fetch(new Request("http://127.0.0.1/j2ui/r3/api/say", { method: "POST", body: "{}" }));
  assert.strictEqual(h.calls[1].token, "tok");
  const down = hosted(c => { if (c.url === "/api/panel-token") throw new Error("offline"); return json({ ok: true }); });
  const r = await down.fetch("api/say", { method: "POST", body: "{}" });
  assert.strictEqual(r.status, 200, "the app's guard answers, not this script");
});

test("J10: j2host.js names no URL but the panel token's and writes nothing else", () => {
  const urls = (hostSrc.match(/["'`]\/[A-Za-z][^"'`\s]*["'`]/g) || []).concat(hostSrc.match(/https?:\/\/\S+/g) || []);
  assert.deepStrictEqual(urls, ['"/api/panel-token"']);
  assert.ok(!/localStorage|sessionStorage|document\.cookie|XMLHttpRequest|WebSocket/.test(hostSrc));
});

Promise.all(pending).then(() => {
  console.log("\n" + (failed ? failed + " failed" : "all passed") + " (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
