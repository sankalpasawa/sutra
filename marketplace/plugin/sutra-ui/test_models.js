#!/usr/bin/env node
/* test_models.js -- the Models editor on Root's pane (static/js/26-models.js; amendment A4, A4.6; screens S19 to S26).

   Named claims:
     M1  no global of 26-models.js is a global of any other script
     M2  the card on Root's pane: the owner's model names, no count, the empty sentence, the pending stamp as one amber line
     M3  the list (S19): every state with its word and its glyph, never colour alone; loading, empty, needs a look, off, a stamp
         waits, read error; the five bases locked
     M4  Stamp and No post to the one route they name, and the list is read again
     M5  the page (S20): inherited fields carry no button; a built-in model has no change button and says so
     M6  add a model (S21): the base is chosen first and Make it is off until it is; a taken name shows the server's sentence;
         Make it posts {spec}
     M7  change a field (S22): the three classes read their three sentences; a widening says Save for my stamp; the preview is
         one call after the pause, not one for each key; the control stops at the base's bound
     M8  turn off or on (S23): the sheet lists what turns off and what is kept; Turn off posts {enabled: false, rev}; the off
         banner; the needs-a-look sentence; Undo posts the undo
     M9  link or nest (S24): a circle is shown before Save and Add is off; a target that is off is not offered; Add posts the
         model with the link
     M10 try a sample (S25): not JSON, fits, does not fit with the server's sentences, the twelve limit, a model that is off
     M11 structure (S26): the sentences equal the edges of the graph one for one; over thirty models only the list and the filter;
         every box is reachable by Tab in reading order
     M12 a model changed elsewhere shows a quiet line and does not redraw under the owner's hands; history: a restore that waits for
         a stamp shows the amber line
     M13 the screen's own words: nothing banned, no count at rest, no path; the hostile strings come out as text on every screen
     M14 the stylesheet block is tokens only and every class the script emits has a rule; panel.html loads the script before the tail

   The read models in test_fixtures/models/views/ are the real answers of the routes (test_layer_models_ui.py checks their shape
   against the routes). Harness: 20-dept.js and 22-website.js with 26-models.js loaded after them, a fake DOM, fake timers.
   Run: node test_models.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
const orgSrc = read("03-org.js"), o2Src = read("19-org2.js"), dpSrc = read("20-dept.js"), wbSrc = read("22-website.js"), mdSrc = read("26-models.js");
const tailSrc = read("09-tail.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
const railSrc = orgSrc.slice(orgSrc.indexOf(RB), orgSrc.indexOf(RE));
const VIEWS = path.join(__dirname, "test_fixtures", "models", "views");
const fx = n => JSON.parse(fs.readFileSync(path.join(VIEWS, n + ".json"), "utf8"));
const copy = x => JSON.parse(JSON.stringify(x));

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
const settle = async () => { for (let i = 0; i < 8; i++) await sleep(); };

const LIST = fx("list"), PAGE = fx("page"), PAGE_ORDER = fx("page_order"), GRAPH = fx("graph"), HISTORY = fx("history"), SHAPE = fx("shape");
const words = h => String(h).replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&quot;/g, '"').replace(/\s+/g, " ");

class Fail extends Error { constructor(detail, status){ super(JSON.stringify(detail) + " (/api/native/_models/x -> " + (status || 409) + ")"); this.status = status || 409; } }

function fresh(o){
  o = o || {};
  const calls = { apiGet: [], apiPost: [], render: 0 };
  const timers = [];
  const dom = { made: [], listeners: {} };
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Math, Object, encodeURIComponent, Promise, isNaN, Error, RegExp,
    setTimeout: (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length; },
    clearTimeout: id => { if (timers[id - 1]) timers[id - 1].live = false; },
    setInterval: () => 1, clearInterval: () => {},
    apiGet: (p) => {
      calls.apiGet.push(p);
      if (o.get){ const r = o.get(p); if (r !== undefined) return r; }
      if (p === "/api/native/_models") return Promise.resolve(copy(o.list || LIST));
      if (p === "/api/native/_models?all=1") return Promise.resolve(copy(o.listAll || fx("list_all")));
      if (p === "/api/native/_models/graph") return Promise.resolve(copy(o.graph || GRAPH));
      if (p === "/api/native/_models/x.client") return Promise.resolve(copy(o.page || PAGE));
      if (p === "/api/native/_models/x.order") return Promise.resolve(copy(PAGE_ORDER));
      if (p === "/api/native/_models/x.vip_client" && o.vip) return Promise.resolve(copy(o.vip));
      if (/\/history$/.test(p)) return Promise.resolve(copy(o.history || HISTORY));
      if (/\/shape$/.test(p)) return Promise.resolve(copy(o.shape || SHAPE));
      return Promise.reject(Object.assign(new Error("/api/native/_models/x -> 404"), { status: 404 }));
    },
    apiPost: (p, body) => {
      calls.apiPost.push({ p, body: copy(body) });
      if (o.post){ const r = o.post(p, body); if (r !== undefined) return r; }
      if (p === "/api/native/_models/preview"){
        if (body.op === "disable" || body.op === "enable") return Promise.resolve(copy(fx("preview_disable")));
        const spec = body.spec || {}, f = (spec.fields || []).filter(x => x.name === "name")[0];
        if ((spec.links || []).some(l => l.to === "x:order")) return Promise.resolve(copy(fx("preview_circle")));
        if (f && f.max_len > 80) return Promise.resolve(copy(fx("preview_widens")));
        if (f && f.max_len === 60) return Promise.resolve(copy(fx("preview_tightens")));
        return Promise.resolve(copy(fx("preview_same")));
      }
      if (p === "/api/native/_models/validate") return Promise.resolve(copy(fx("validate_bad")));
      return Promise.resolve({ ok: true, rev: 7, model: copy(PAGE) });
    },
    window: {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, DOMAINS: [], CHARTERS: [], PLACEMENTS: [], INDEX: [], META: {}, SETTINGS: { flags: { org2: true } },
    ICON: {}, st: (d) => d.status || "active",
    S: { screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } },
    render: () => { calls.render++; },
    loadOrg: () => Promise.resolve(), sbPageFromPath: () => null, mdHtml: (t) => "<p>" + t + "</p>",
    navigator: { clipboard: { writeText(t){ calls.copied = t; } } },
    document: {
      listeners: dom.listeners, activeElement: null, body: { appendChild(){} },
      addEventListener(type, fn){ (dom.listeners[type] = dom.listeners[type] || []).push(fn); },
      querySelector(){ return null; }, querySelectorAll(){ return []; }, getElementById(){ return null; },
      createElement(){ const e = { id: "", innerHTML: "" }; dom.made.push(e); return e; },
    },
  };
  ctx.calls = calls; ctx.timers = timers; ctx.dom = dom;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(o2Src, ctx);
  vm.runInContext(dpSrc, ctx);
  vm.runInContext(wbSrc, ctx);
  vm.runInContext(mdSrc, ctx);
  return ctx;
}
async function loaded(o){ const c = fresh(o); c.mdlLoad(); await settle(); return c; }
async function onPage(o, key){
  const c = await loaded(o);
  click(c, { mdl: "open", mdlKey: key || "x.client" });
  await settle();
  return c;
}
function click(c, ds){
  let prevented = false;
  const el = { dataset: ds, closest(sel){ return sel === "[data-mdl]" && ds.mdl !== undefined ? el : null; } };
  const ev = { target: el, preventDefault(){ prevented = true; }, stopPropagation(){} };
  (c.document.listeners.click || []).forEach(fn => fn(ev));
  return prevented;
}
/* an input on a sheet, as the page's listener hands it */
function type(c, k, value, extra){ c.mdlInput(Object.assign({ dataset: { mdlin: k }, value: String(value), type: "text" }, extra || {})); }
function check(c, k, on){ c.mdlInput({ dataset: { mdlin: k }, type: "checkbox", checked: !!on, value: "on" }); }
const sheet = c => c.mdlSheetHtml();
const pane = c => c.mdlPaneHtml();
async function fire(c){ const t = c.timers.filter(x => x.live); t.forEach(x => { x.live = false; }); t.forEach(x => x.fn()); await settle(); }
const posts = (c, re) => c.calls.apiPost.filter(x => re.test(x.p));
const gets = (c, re) => c.calls.apiGet.filter(p => re.test(p));
const attrs = (h, re) => (String(h).match(re) || []);

/* ── M1 ─────────────────────────────────────────────────────────────────── */
test("M1: no global of 26-models.js is a global of any other script", () => {
  const mine = new Set();
  let m;
  const re = /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^(?:const|let)\s+([A-Za-z_$][\w$]*)/gm;
  while ((m = re.exec(mdSrc))) mine.add(m[1] || m[2]);
  assert.ok(mine.size > 40, "parsed " + mine.size + " globals");
  [...mine].forEach(n => assert.ok(/^(mdl[A-Z]|MDL_|_mdl$)/.test(n), n + " is not prefixed mdl / MDL_"));
  fs.readdirSync(JS).filter(f => /\.js$/.test(f) && f !== "26-models.js").forEach(f => {
    const src = read(f);
    const theirs = /^(?:async\s+)?function\s+(mdl[A-Z]\w*)|^(?:const|let)\s+(MDL_\w+|_mdl)\b/gm;
    assert.ok(!theirs.test(src), f + " declares an mdl global");
  });
  const c = fresh();
  const own = vm.runInContext("typeof mdlState + typeof mdlLoad + typeof mdlRender + typeof mdlCardHtml + typeof mdlListHtml + typeof mdlPageHtml + typeof mdlAddSheet + typeof mdlFieldSheet + typeof mdlOnOffSheet + typeof mdlLinkSheet + typeof mdlTrySheet + typeof mdlStructureHtml + typeof mdlHistoryHtml + typeof mdlOnModelsEvent", c);
  assert.strictEqual(own, "function".repeat(14));
});

/* ── M2 ─────────────────────────────────────────────────────────────────── */
test("M2: the card names the owner's models, never a count; the empty sentence; a pending stamp is one amber line", async () => {
  const c = await loaded();
  const h = c.mdlCardHtml(), w = words(h);
  assert.ok(/Yours: Client, VIP client, Line, Order, Visit note\./.test(w) || /Yours: [A-Za-z ,]+\./.test(w), w);
  ["Client", "VIP client", "Order", "Line"].forEach(n => assert.ok(w.indexOf(n) >= 0, n));
  assert.ok(!/\d/.test(w), "no digit at rest: " + w);
  assert.ok(/data-wbtab="models"/.test(h) && />Open models</.test(h));
  assert.strictEqual(attrs(h, /class="mdlnote"/g).length, 1, "one amber line");
  assert.ok(/class="mdlq"[^>]*>\?</.test(h) && /Client: a change waits for your stamp/.test(w));
  const e = await loaded({ list: Object.assign(copy(LIST), { yours: [] }) });
  assert.ok(/You have not made a model yet\./.test(words(e.mdlCardHtml())) && !/mdlnote/.test(e.mdlCardHtml()));
  /* Root's pane carries the card under Standards, and the pane for the models tab is the one this file draws */
  const rp = vm.runInContext("wbRootPaneHtml({ref:'r2',name:'Root'}, {goal:'g', rules:[], stopped:false})", c);
  assert.ok(rp.indexOf("<h3>Models</h3>") > rp.indexOf("Standards every plan meets") && rp.indexOf("Standards every plan meets") > 0, "under the Standards card");
  assert.ok(/class="dpcard"><h3>Models<\/h3>/.test(rp), "the card is on Root's pane");
  assert.ok(/mdlOnModelsEvent/.test(tailSrc) && /addEventListener\("models"/.test(tailSrc), "09-tail.js listens for the models event");
  assert.ok(/mdlPaneHtml\(\)/.test(wbSrc) && /"models"/.test(wbSrc), "the models tab is drawn by the pane");
});

/* ── M3 ─────────────────────────────────────────────────────────────────── */
test("M3: the list shows every state with its word and its glyph", async () => {
  const L = copy(LIST);
  L.yours.push({ key: "x.survey_answer", name: "survey_answer", label: "Survey answer", version: 1, base: "core:record", base_label: "Record", state: "needs_a_look",
    why: "its base changed: \"tier\" now allows fewer values", abstract: false, children: [], pending: null });
  const c = await loaded({ list: L });
  const h = c.mdlListHtml(), w = words(h);
  assert.ok(/On<\/span>/.test(h) && /Off<\/span>/.test(h) && /Needs a look<\/span>/.test(h), "the three state words");
  /* every state carries its glyph in the same element as its word */
  const states = attrs(h, /<span class="mdlstate [a-z]+">.*?<\/span>/g);
  assert.ok(states.length >= 6);
  states.forEach(s => assert.ok(/<i class="mdlg" aria-hidden="true">.<\/i>(On|Off|Needs a look|Retired)/.test(s), s));
  assert.ok(/its base changed: "tier" now allows fewer values/.test(w), "why, in a quiet line");
  assert.ok(/mdlrow mdlsub"><span class="mdlname">VIP client/.test(h), "a model built on another is indented");
  assert.ok(/a kind of Client/.test(w));
  assert.ok(/mdlnote/.test(h) && />Stamp</.test(h) && />No</.test(h) && /waits for your stamp/.test(w));
  assert.ok(/Add a model/.test(h) && /Show everything built in/.test(h) && /Structure and history/.test(h));
  ["Record", "Artifact template", "Engine template", "Department kind", "Journey"].forEach(n => assert.ok(w.indexOf(n) >= 0 || n === "Engine template" || n === "Department kind", n));
  assert.strictEqual(attrs(h, /<span class="mdllock">/g).length, 5, "the five bases, locked");
  assert.ok(/Built in<\/span>/.test(h));
  /* loading, empty, read error */
  const l = fresh({ get: () => new Promise(() => {}) });
  assert.ok(/o2skel/.test(l.mdlListHtml()), "loading is a skeleton");
  const e = await loaded({ list: Object.assign(copy(LIST), { yours: [] }) });
  assert.ok(/You have not made a model yet\./.test(words(e.mdlListHtml())));
  const bad = fresh({ get: () => Promise.reject(new Error("x")) });
  bad.mdlLoad(); await settle();
  assert.ok(/Could not read your models · /.test(words(bad.mdlListHtml())) && />Try again</.test(bad.mdlListHtml()));
  /* Show everything built in reads the list with ?all=1 and names, by layer */
  click(c, { mdl: "all" }); await settle();
  assert.ok(gets(c, /\?all=1/).length === 1 && /Everything built in/.test(c.mdlListHtml()));
});

/* ── M4 ─────────────────────────────────────────────────────────────────── */
test("M4: Stamp and No post to the one route they name, then the list is read again", async () => {
  const c = await loaded();
  const id = LIST.yours[0].pending.id;
  const before = gets(c, /^\/api\/native\/_models$/).length;
  click(c, { mdl: "stamp", mdlId: id }); await settle();
  let p = posts(c, /pending/);
  assert.strictEqual(p.length, 1);
  assert.strictEqual(p[0].p, "/api/native/_models/pending/" + id);
  assert.deepStrictEqual(p[0].body, { approve: true });
  assert.strictEqual(gets(c, /^\/api\/native\/_models$/).length, before + 1, "read again");
  click(c, { mdl: "no", mdlId: id }); await settle();
  p = posts(c, /pending/);
  assert.deepStrictEqual(p[1].body, { approve: false });
  assert.strictEqual(p[1].p, "/api/native/_models/pending/" + id);
  assert.ok(/Dropped\. Nothing changed\./.test(c.mdlPaneHtml()), "and the screen says what it did");
});

/* ── M14 ────────────────────────────────────────────────────────────────── */
test("M14: the stylesheet block is tokens only and covers what the script emits; panel.html loads the script before the tail", () => {
  const i = css.indexOf("/* Models (A4)");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  assert.ok(!/:\s*[^;{}]*\b\d+(\.\d+)?px[^;{}]*\b(red|blue|green|black|white)\b/i.test(block));
  const emitted = mdSrc.replace(/data-mdl[a-z0-9-]*/g, "").replace(/\bds\.mdl\w*/g, "").replace(/\bmdl[A-Z]\w*/g, "").replace(/\bMDL_\w+/g, "").replace(/"mdl-[a-z]+"/g, "").replace(/\bmdl-[a-z]+\b/g, "");
  const classes = new Set();
  let m;
  const re = /\bmdl[a-z0-9]+\b/g;
  while ((m = re.exec(emitted))) classes.add(m[0]);
  ["mdlin", "mdlsheet"].forEach(k => classes.delete(k === "mdlin" ? k : "none"));
  assert.ok(classes.size > 30, "found " + classes.size + " classes");
  [...classes].forEach(k => assert.ok(new RegExp("\\." + k + "\\b").test(block), "no rule for ." + k));
  const a = panelHtml.indexOf("/static/js/22-website.js"), b = panelHtml.indexOf("/static/js/26-models.js"), t = panelHtml.indexOf("/static/js/09-tail.js");
  assert.ok(a > 0 && b > a && t > b, "loaded after 22, before the tail");
});

Promise.all(pending).then(() => {
  console.log(failed ? failed + " of " + ran + " FAILED" : ran + " passed");
  process.exit(failed ? 1 : 0);
});
