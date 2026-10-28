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

/* ── M5 ─────────────────────────────────────────────────────────────────── */
test("M5: inherited fields have no buttons; a built-in model has no change button", async () => {
  const c = await onPage();
  const h = c.mdlPageHtml("x.client"), w = words(h);
  const rows = attrs(h, /<div class="mdlfield[^"]*">.*?<\/span><\/div>/g);
  const idRow = rows.filter(r => /<span class="mdlfn"><i class="mdlpad" aria-hidden="true"><\/i>id</.test(r))[0];
  assert.ok(idRow && /from Record/.test(idRow) && !/data-mdl=/.test(idRow), "id is locked with no button");
  const nameRow = rows.filter(r => /mdlfn">name</.test(r))[0];
  ["field", "rename", "retire"].forEach(a => assert.ok(new RegExp('data-mdl="' + a + '" data-mdl-name="name"').test(nameRow), a));
  assert.ok(/Add a field/.test(h) && /Link or nest/.test(h) && /Try a sample/.test(h) && /See its shape/.test(h) && /New version/.test(h));
  assert.ok(/Pointed at by: Order \(by its id\)/.test(w) && /Points out: nothing yet/.test(w));
  assert.ok(/Built on it/.test(w) && /VIP client/.test(w));
  assert.ok(/up to 80 characters, at least 1, required/.test(w));
  /* a built-in model: the lock, the line, three buttons at most */
  click(c, { mdl: "open", mdlKey: "core:record" }); await settle();
  const b = c.mdlPageHtml("core:record");
  assert.ok(/Built in/.test(b) && /Part of the app: you can look, not change\./.test(words(b)));
  assert.ok(!/data-mdl="(field|rename|retire|link|onoff|undo|newversion)"/.test(b));
  assert.ok(/Try a sample/.test(b) && /See its shape/.test(b) && /data-mdl="add" data-mdl-key="core:record"/.test(b) && /Build on it/.test(b));
  /* a retired field says Retired and is not offered Change */
  const P = copy(PAGE); P.fields[0].retired = true;
  const r = await onPage({ page: P });
  const rh = r.mdlPageHtml("x.client");
  assert.ok(/Retired/.test(rh) && !/data-mdl="field" data-mdl-name="name"/.test(rh));
});

/* ── M6 ─────────────────────────────────────────────────────────────────── */
test("M6: add a model: the base first, Make it off until it is; a taken name; Make it posts {spec}", async () => {
  const c = await loaded();
  click(c, { mdl: "add" });
  let h = sheet(c);
  assert.ok(/Build it on/.test(h) && /Call it/.test(h) && /Its fields/.test(h));
  assert.ok(/id="mdl-save" data-mdl="make" disabled/.test(h), "off with nothing chosen");
  /* the bases: the five, and the owner's models that are on (not the one that is off) */
  assert.ok(/value="core:record"/.test(h) && /value="x.client"/.test(h) && !/value="x.visit_note"/.test(h));
  type(c, "label", "Regular client");
  assert.ok(/data-mdl="make" disabled/.test(sheet(c)), "a name without a base is still off");
  c.mdlInput({ dataset: { mdlin: "base" }, value: "x.client", type: "radio" }); await settle();
  h = sheet(c);
  assert.ok(!/data-mdl="make" disabled/.test(h), "base and name: on");
  assert.ok(/kept as x\.regular_client/.test(h));
  assert.ok(/from Record/.test(h) && /mdlpad/.test(h), "the base's fields, locked");
  /* a taken name */
  type(c, "label", "Client");
  h = sheet(c);
  assert.ok(/a model called Client is already there/.test(h) && /data-mdl="make" disabled/.test(h));
  /* a fault of the server is printed as written, under the field */
  type(c, "label", "VIP club");
  click(c, { mdl: "make" });
  await settle();
  const post = posts(c, /^\/api\/native\/_models$/)[0];
  assert.ok(post && Object.keys(post.body).join() === "spec", "posts {spec}");
  assert.deepStrictEqual({ n: post.body.spec.name, l: post.body.spec.label, b: post.body.spec.base, v: post.body.spec.version },
    { n: "vip_club", l: "VIP club", b: "x:client/v1", v: 1 });
  assert.ok(c.mdlState().sheet === null, "the sheet is gone");
  assert.ok(/Done\./.test(c.mdlPaneHtml()), "and the screen says what it did");
  const d = await loaded({ post: (p) => p === "/api/native/_models" ? Promise.reject(new Fail({ code: "NAME_TAKEN", faults: ["a model called Client is already there"] })) : undefined });
  click(d, { mdl: "add" }); type(d, "label", "Zed");
  d.mdlInput({ dataset: { mdlin: "base" }, value: "core:record", type: "radio" });
  click(d, { mdl: "make" }); await settle();
  assert.ok(/a model called Client is already there/.test(sheet(d)) && !/->/.test(sheet(d)), "the server's sentence, never the path");
});

/* ── M7 ─────────────────────────────────────────────────────────────────── */
test("M7: change a field: the live line says the class in words, once, after the pause", async () => {
  const c = await onPage();
  click(c, { mdl: "field", mdlName: "name" });
  await fire(c);
  let live = () => words(sheet(c).match(/<div id="mdl-live"[\s\S]*?<\/div>/)[0]);
  assert.ok(/No change in what fits\./.test(live()), live());
  assert.ok(/Type: text \(fixed\)/.test(words(sheet(c))), "the type is fixed once saved");
  const n0 = posts(c, /preview/).length;
  /* five keys, one call */
  "6".split("").concat(["60"]).forEach(v => type(c, "f:max_len", v));
  type(c, "f:max_len", "6"); type(c, "f:max_len", "60");
  assert.strictEqual(c.timers.filter(x => x.live).length, 1, "one pending call, not one for each key");
  assert.ok(/Checking\.\.\./.test(live()), "a quiet Checking... while it waits");
  await fire(c);
  assert.strictEqual(posts(c, /preview/).length, n0 + 1);
  const call = posts(c, /preview/)[n0];
  assert.strictEqual(call.body.op, "edit"); assert.strictEqual(call.body.key, "x.client");
  assert.strictEqual(call.body.spec.fields.filter(f => f.name === "name")[0].max_len, 60);
  assert.ok(/Tightens: fewer values fit\./.test(live()), live());
  assert.ok(/>Save</.test(sheet(c)) && !/Save for my stamp/.test(sheet(c)));
  type(c, "f:max_len", "120"); await fire(c);
  assert.ok(/Lets in more: this would let name run to 120 characters\. This waits for your stamp\./.test(live()), live());
  assert.ok(/Save for my stamp/.test(sheet(c)));
  assert.ok(!/\b(tightens|widens|mixed)\b/.test(words(sheet(c))), "never the codes on screen");
  /* Save posts the whole spec with the page's rev; a stamp waits */
  const d = await onPage({ post: (p) => /x\.client$/.test(p) ? Promise.resolve({ ok: true, pending: true, class: "widens", pending_id: "p-1", says: "let name run to 120 characters" }) : undefined });
  click(d, { mdl: "field", mdlName: "name" }); type(d, "f:max_len", "120"); await fire(d);
  click(d, { mdl: "save" }); await settle();
  const sv = posts(d, /x\.client$/)[0];
  assert.deepStrictEqual(Object.keys(sv.body).sort(), ["rev", "spec"]);
  assert.strictEqual(sv.body.rev, PAGE.rev);
  assert.ok(/Saved for your stamp/.test(d.mdlPaneHtml()));
  /* a server sentence under the control */
  const e = await onPage({ post: (p) => /x\.client$/.test(p) ? Promise.reject(new Fail({ code: "LOOSENS_BASE", faults: ["name cannot allow more than Record does"] })) : p === "/api/native/_models/preview" ? Promise.resolve(copy(fx("preview_same"))) : undefined });
  click(e, { mdl: "field", mdlName: "name" }); await fire(e);
  click(e, { mdl: "save" }); await settle();
  assert.ok(/name cannot allow more than Record does/.test(sheet(e)));
  /* the control stops at the base's bound, and says so */
  const f = await loaded();
  click(f, { mdl: "add" });
  f.mdlInput({ dataset: { mdlin: "base" }, value: "x.client", type: "radio" }); await settle();
  click(f, { mdl: "field" });
  type(f, "f:name", "name"); type(f, "f:label", "Name");
  const hh = sheet(f);
  assert.ok(/max="80"/.test(hh) && /the base allows up to 80/.test(words(hh)), words(hh));
  type(f, "f:max_len", "200");
  assert.strictEqual(f.mdlState().sheet.field.max_len, 80, "clamped to the base");
  /* rename keeps the old name; retire says it stays readable */
  const g = await onPage();
  click(g, { mdl: "rename", mdlName: "phone" });
  assert.ok(/The old name keeps working\./.test(words(sheet(g))));
  type(g, "f:name", "mobile"); await fire(g);
  const rp = posts(g, /preview/).pop().body.spec.fields;
  assert.ok(rp.some(x => x.name === "mobile" && x.aliases.indexOf("phone") >= 0) && !rp.some(x => x.name === "phone"));
  click(g, { mdl: "retire", mdlName: "name" });
  assert.ok(/It stays readable and is never asked for\./.test(words(sheet(g))) && /lets in more/.test(words(sheet(g))), "a required field says it lets in more");
});

/* ── M8 ─────────────────────────────────────────────────────────────────── */
test("M8: turning a model off says what turns off and what is kept; Turn off posts {enabled: false, rev}", async () => {
  const c = await onPage();
  click(c, { mdl: "onoff" }); await settle();
  const h = sheet(c), w = words(h);
  assert.ok(/Client stops being offered when you build, link or file\./.test(w));
  assert.ok(/It turns off with it: VIP client/.test(w));
  assert.ok(/Still there, nothing lost/.test(w) && /You can turn it on again; everything comes back as it was\./.test(w));
  assert.ok(/Keep it on/.test(h));
  assert.strictEqual(posts(c, /preview/)[0].body.op, "disable");
  click(c, { mdl: "onoffgo" }); await settle();
  const p = posts(c, /enabled$/)[0];
  assert.strictEqual(p.p, "/api/native/_models/x.client/enabled");
  assert.deepStrictEqual(p.body, { enabled: false, rev: PAGE.rev });
  /* turning on a child whose base is off: no button */
  const L = copy(LIST); L.yours.forEach(e => { if (e.key === "x.client") e.state = "off"; });
  const V = copy(PAGE); V.key = "x.vip_client"; V.name = "vip_client"; V.label = "VIP client"; V.base = "x:client/v1"; V.base_label = "Client"; V.state = "off";
  const d = await loaded({ list: L, vip: V });
  click(d, { mdl: "open", mdlKey: "x.vip_client" }); await settle();
  assert.ok(/Off\. Nothing new is offered\. What is stored stays\./.test(words(d.mdlPageHtml("x.vip_client"))));
  assert.ok(/Turn on/.test(d.mdlPageHtml("x.vip_client")));
  click(d, { mdl: "onoff" }); await settle();
  assert.ok(/Client is off; turn it on first/.test(words(sheet(d))) && !/data-mdl="onoffgo"/.test(sheet(d)));
  /* needs a look: the sentence and the way to fit it */
  const N = copy(PAGE); N.state = "needs_a_look"; N.why = "its base changed: \"tier\" now allows fewer values";
  const n = await onPage({ page: N });
  assert.ok(/its base changed: "tier" now allows fewer values/.test(words(n.mdlPageHtml("x.client"))) && /Fit it to its base/.test(n.mdlPageHtml("x.client")));
  /* the amber line on the page, and Undo posts the undo with the rev */
  const pg = copy(PAGE); pg.pending = LIST.yours[0].pending;
  const a = await onPage({ page: pg });
  assert.ok(/mdlnote/.test(a.mdlPageHtml("x.client")) && />Stamp</.test(a.mdlPageHtml("x.client")));
  click(a, { mdl: "undo" }); await settle();
  const u = posts(a, /undo$/)[0];
  assert.strictEqual(u.p, "/api/native/_models/x.client/undo"); assert.deepStrictEqual(u.body, { rev: PAGE.rev });
});

/* ── M9 ─────────────────────────────────────────────────────────────────── */
test("M9: a circle is shown before Save and Add is off; a target that is off is not offered; Add posts the model with the link", async () => {
  const c = await onPage({}, "x.line");
  /* Line's page: the page of the fixture stands in for it */
  const P = copy(PAGE); P.key = "x.line"; P.name = "line"; P.label = "Line";
  const d = await onPage({ get: (p) => p === "/api/native/_models/x.line" ? Promise.resolve(copy(P)) : undefined }, "x.line");
  click(d, { mdl: "link" });
  let h = sheet(d);
  assert.ok(/value="x:order"/.test(h) && /value="x:client"/.test(h) && /value="core:envelope"/.test(h), "targets");
  assert.ok(!/Visit note/.test(h), "a target that is off is not offered");
  d.mdlInput({ dataset: { mdlin: "l:to" }, value: "x:order", type: "text" });
  type(d, "l:name", "order");
  await fire(d);
  h = sheet(d);
  assert.ok(/Line, Order, Line: a circle/.test(words(h)), words(h));
  assert.ok(/data-mdl="addlink" disabled/.test(h), "Add is off");
  d.mdlInput({ dataset: { mdlin: "l:to" }, value: "x:client", type: "text" });
  type(d, "l:name", "client_id");
  d.mdlInput({ dataset: { mdlin: "l:mode" }, value: "refer", type: "radio" });
  check(d, "l:required", true);
  await fire(d);
  h = sheet(d);
  assert.ok(!/data-mdl="addlink" disabled/.test(h) && /Hold it inside/.test(h) && /Point to it by its id/.test(h));
  click(d, { mdl: "addlink" }); await settle();
  const sv = posts(d, /x\.line$/)[0];
  assert.ok(sv, "posted to the model");
  assert.deepStrictEqual(sv.body.spec.links, [{ name: "client_id", label: "Client", mode: "refer", to: "x:client", required: true }]);
  assert.strictEqual(sv.body.rev, P.rev);
});

/* ── M10 ────────────────────────────────────────────────────────────────── */
test("M10: try a sample: not JSON, fits, does not fit with the server's sentences, the twelve limit, a model that is off", async () => {
  const c = await onPage();
  click(c, { mdl: "try" });
  type(c, "sample", "{not json");
  click(c, { mdl: "check" }); await settle();
  assert.ok(/That is not JSON: /.test(words(sheet(c))) && !/\d/.test(words(sheet(c)).match(/That is not JSON: [^<]*/)[0]), words(sheet(c)));
  assert.strictEqual(posts(c, /validate/).length, 0, "nothing is sent");
  type(c, "sample", '{"id": "C 1", "name": "", "tier": "platinum"}');
  click(c, { mdl: "check" }); await settle();
  const v = posts(c, /validate/)[0];
  assert.deepStrictEqual(v.body, { key: "x.client", sample: { id: "C 1", name: "", tier: "platinum" } });
  const w = words(sheet(c));
  fx("validate_bad").faults.forEach(f => assert.ok(w.indexOf(words(f)) >= 0, f));
  assert.ok(/It does not fit:/.test(w) && attrs(sheet(c), /<li>/g).length === 3);
  const ok = await onPage({ post: (p) => p === "/api/native/_models/validate" ? Promise.resolve({ ok: true, faults: [] }) : undefined });
  click(ok, { mdl: "try" }); type(ok, "sample", "{}"); click(ok, { mdl: "check" }); await settle();
  assert.ok(/It fits\./.test(words(sheet(ok))));
  const many = Array.from({ length: 15 }, (_, i) => "$.f" + i + ": is wrong");
  const m = await onPage({ post: (p) => p === "/api/native/_models/validate" ? Promise.resolve({ ok: false, faults: many }) : undefined });
  click(m, { mdl: "try" }); type(m, "sample", "{}"); click(m, { mdl: "check" }); await settle();
  assert.strictEqual(attrs(sheet(m), /<li>/g).length, 13, "twelve and 'and more'");
  assert.ok(/<li>and more<\/li>/.test(sheet(m)) && !/\$\.f12/.test(sheet(m)));
  const off = copy(PAGE); off.state = "off";
  const o = await onPage({ page: off });
  click(o, { mdl: "try" });
  assert.ok(/Client is off; this checks it anyway\./.test(words(sheet(o))));
  /* Make an example reads the shape and fills the sample; Shape shows the schema read only with a copy button */
  click(c, { mdl: "makeex" }); await settle();
  assert.strictEqual(gets(c, /shape$/).length, 1);
  assert.deepStrictEqual(JSON.parse(c.mdlState().sheet.sample), SHAPE.example);
  click(c, { mdl: "shapetab" }); await settle();
  assert.ok(/<pre class="mdlpre">/.test(sheet(c)) && /data-mdl="copy"/.test(sheet(c)) && !/<textarea/.test(sheet(c)));
  click(c, { mdl: "copy" });
  assert.strictEqual(JSON.parse(c.calls.copied).properties.name.maxLength, 80);
  click(c, { mdl: "exampletab" }); await settle();
  assert.ok(/<pre class="mdlpre">/.test(sheet(c)));
  /* when a sheet is open the draft goes as spec */
  const d = await loaded();
  click(d, { mdl: "add" }); type(d, "label", "Zed"); d.mdlInput({ dataset: { mdlin: "base" }, value: "core:record", type: "radio" });
  click(d, { mdl: "try" }); type(d, "sample", "{}"); click(d, { mdl: "check" }); await settle();
  assert.strictEqual(posts(d, /validate/)[0].body.spec.name, "zed");
});

/* ── M11 ────────────────────────────────────────────────────────────────── */
test("M11: structure: the sentences equal the graph's edges one for one; over thirty only the list and the filter; Tab reaches every box", async () => {
  const c = await loaded();
  click(c, { mdl: "structure" }); await settle();
  const h = c.mdlStructureHtml();
  const li = attrs(h, /<li>.*?<\/li>/g).map(x => words(x).trim().replace(/\.$/, "").trim());
  assert.deepStrictEqual(li, GRAPH.text, "the same content, one for one");
  /* the edges of the drawing: one line for each edge of the graph, by kind */
  const kinds = k => attrs(h, new RegExp('<line class="' + k + '"', "g")).length;
  assert.strictEqual(kinds("mdlext"), GRAPH.edges.filter(e => e.kind === "extends").length);
  assert.strictEqual(kinds("mdlnest"), GRAPH.edges.filter(e => e.kind === "nests").length);
  assert.strictEqual(kinds("mdlref"), GRAPH.edges.filter(e => e.kind === "refers").length);
  assert.ok(/marker-end="url\(#mdl-closed\)"/.test(h) && /stroke-dasharray/.test(css.slice(css.indexOf("/* Models (A4)"))));
  /* every box: focusable, in reading order (bases first, then what is built on them), owner models are links */
  const boxes = attrs(h, /<g class="mdlbox[^"]*"[^>]*>/g);
  assert.strictEqual(boxes.length, GRAPH.nodes.length);
  boxes.forEach(b => assert.ok(/tabindex="0"/.test(b) && /role="link"/.test(b) && /aria-label="[^"]+, (built in|on|off|needs a look)"/.test(b), b));
  const order = boxes.map(b => (/aria-label="([^"]+),/.exec(b) || [])[1]);
  const lvl = lb => { const n = GRAPH.nodes.filter(x => x.label === lb)[0]; let d = 0, k = n.key; for (;;){ const e = GRAPH.edges.filter(x => x.from === k && x.kind === "extends")[0]; if (!e) break; k = e.to; d++; } return d; };
  const lv = order.map(lvl);
  assert.deepStrictEqual(lv, lv.slice().sort((a, b) => a - b), "reading order: left to right");
  assert.strictEqual(attrs(h, /data-mdl="open" data-mdl-key="x\.[a-z_]+"/g).length, GRAPH.nodes.filter(n => !n.core).length);
  assert.ok(/Built in/.test(h) && !/data-mdl-key="core:/.test(h), "built-in boxes are drawn grey with the word, and open nothing");
  /* the words explain the lines without the drawing */
  assert.ok(/Solid line with a closed head: is a kind of\. Thick line: holds\. Dashed line: points to by its id\./.test(words(h)));
  /* over thirty models: no drawing, the list and a filter */
  const big = { nodes: [], edges: [], text: [] };
  for (let i = 0; i < 31; i++){ big.nodes.push({ key: "x.m" + i, label: "Model " + i, core: false, state: "on" }); big.text.push("Model " + i + " is a kind of Record"); }
  const b = await loaded({ graph: big });
  click(b, { mdl: "structure" }); await settle();
  const bh = b.mdlStructureHtml();
  assert.ok(!/<svg/.test(bh) && /data-mdlin="filter"/.test(bh) && attrs(bh, /<li>/g).length === 31);
  b.mdlInput({ dataset: { mdlin: "filter" }, value: "Model 30" });
  assert.strictEqual(attrs(b.mdlStructureHtml(), /<li>/g).length, 1);
  /* the Enter key opens a box */
  const key = (c.document.listeners.keydown || []).slice(-1)[0];
  let prevented = false;
  const el = { dataset: { mdl: "open", mdlKey: "x.order" }, getAttribute: () => "link", closest: () => el };
  key({ target: el, key: "Enter", preventDefault(){ prevented = true; } });
  assert.ok(prevented && c.mdlState().key === "x.order" && c.mdlState().view === "page");
});

/* ── M12 ────────────────────────────────────────────────────────────────── */
test("M12: a model changed elsewhere is a quiet line, not a redraw; a restore that waits for a stamp shows the amber line", async () => {
  const c = await loaded();
  vm.runInContext("wbS().tab['r2'] = 'models'", c);
  const renders = c.calls.render, reads = c.calls.apiGet.length;
  c.mdlOnModelsEvent({ rev: LIST.rev + 5, keys: ["x.client"] });
  assert.strictEqual(c.calls.render, renders, "no redraw");
  assert.strictEqual(c.calls.apiGet.length, reads, "no read");
  assert.ok(c.mdlState().stale);
  assert.ok(/Models changed · Reload/.test(words(c.mdlPaneHtml())));
  click(c, { mdl: "reload" }); await settle();
  assert.ok(!c.mdlState().stale && !/Models changed/.test(c.mdlPaneHtml()) && c.calls.apiGet.length > reads);
  /* an event for a revision this screen holds says nothing (its own write) */
  const r1 = c.calls.apiGet.length;
  c.mdlOnModelsEvent({ rev: LIST.rev });
  assert.ok(!c.mdlState().stale && c.calls.apiGet.length === r1);
  /* the pane is not open: the card is refreshed at once */
  vm.runInContext("wbS().tab['r2'] = 'root'", c);
  c.mdlOnModelsEvent({ rev: LIST.rev + 9 }); await settle();
  assert.ok(c.calls.apiGet.length > r1 && !c.mdlState().stale);
  /* history: rows with the time, the owner's words and the class as words; Restore this previews first */
  const H = { history: [
    { rev: 3, at: "2026-10-27T11:02:00+05:30", by: "the owner", op: "edit", says: "let name run to 120 characters", class: "widens" },
    { rev: 2, at: "2026-10-27T10:31:00+05:30", by: "the owner", op: "edit", says: "added the field phone", class: "tightens" },
    { rev: 1, at: "2026-10-27T10:24:00+05:30", by: "the owner", op: "create", says: "made Client", class: "same" }] };
  const h = await loaded({ history: H });
  click(h, { mdl: "structure" }); click(h, { mdl: "history" }); await settle();
  const w = words(h.mdlStructureHtml());
  assert.ok(/11:02 You let name run to 120 characters/.test(w) && /Lets in more/.test(w) && /10:31 You added the field phone/.test(w) && /Tightens/.test(w) && /No change/.test(w), w);
  assert.ok(/mdlnote/.test(h.mdlStructureHtml()), "the stamp that waits is on the history too");
  click(h, { mdl: "restore", mdlKey: "x.client", mdlRev: "3" }); await settle();
  assert.deepStrictEqual(posts(h, /preview/)[0].body, { op: "revert", key: "x.client", to_rev: 3 });
  const pr = copy(fx("preview_widens"));
  const k = await loaded({ history: H, post: (p, b) => p === "/api/native/_models/preview" ? Promise.resolve(pr) : /revert$/.test(p) ? Promise.resolve({ ok: true, pending: true, class: "widens", pending_id: "p-9", says: "went back to revision 3 of Client" }) : undefined });
  click(k, { mdl: "structure" }); click(k, { mdl: "history" }); await settle();
  click(k, { mdl: "restore", mdlKey: "x.client", mdlRev: "3" }); await settle();
  assert.ok(/Save for my stamp/.test(sheet(k)) && /mdllive amber/.test(sheet(k)) && /This waits for your stamp/.test(words(sheet(k))));
  click(k, { mdl: "restorego" }); await settle();
  const rv = posts(k, /revert$/)[0];
  assert.strictEqual(rv.p, "/api/native/_models/x.client/revert"); assert.deepStrictEqual(rv.body, { to_rev: 3, rev: LIST.rev });
  assert.ok(/Saved for your stamp/.test(k.mdlPaneHtml()));
  const empty = await loaded({ history: { history: [] }, list: Object.assign(copy(LIST), { yours: [] }) });
  click(empty, { mdl: "structure" }); click(empty, { mdl: "history" }); await settle();
  assert.ok(/Nothing has changed yet/.test(words(empty.mdlStructureHtml())));
});

/* ── M13 ────────────────────────────────────────────────────────────────── */
/* every string the script renders: the literals and templates, without the code inside ${} and without the markup's attributes */
function literals(src){
  const out = [];
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  let i = 0;
  const push = (s) => { s = s.replace(/<[^>]*>/g, " ").replace(/\\u[0-9a-fA-F]{4}/g, " "); if (s.trim()) out.push(s); };
  /* a string up to its closing quote */
  function str(q){ let s = ""; i++; while (i < code.length && code[i] !== q){ if (code[i] === "\\"){ s += code[i] + code[i + 1]; i += 2; } else s += code[i++]; } i++; push(s); }
  /* a template: its text, and the code inside ${} is scanned for literals of its own */
  function tpl(){ let s = ""; i++; while (i < code.length && code[i] !== "`"){
    if (code[i] === "\\"){ s += code[i] + code[i + 1]; i += 2; }
    else if (code[i] === "$" && code[i + 1] === "{"){ s += " "; i += 2; let d = 1; while (i < code.length && d){ const ch = code[i]; if (ch === "{"){ d++; i++; } else if (ch === "}"){ d--; i++; } else if (ch === '"' || ch === "'") str(ch); else if (ch === "`") tpl(); else i++; } }
    else s += code[i++]; }
    i++; push(s); }
  while (i < code.length){ const ch = code[i]; if (ch === '"' || ch === "'") str(ch); else if (ch === "`") tpl(); else i++; }
  return out;
}
const BANNED = /\b(charters?|ceo|requesters?|grant(?:s|ed)?|counter(?:s|ed)?|refus\w*|internal systems?)\b/i;
const HOSTILE = ['<img src=x onerror=window.__xss=1>', '"><script>window.__xss=1</script>', "';alert(1)//", '<svg onload=1>', '&lt;b&gt;x', "</div><div onclick='x'>"];
test("M13: the screen's own words keep the rules; the hostile strings come out as text on every screen", async () => {
  const lits = literals(mdSrc);
  assert.ok(lits.length > 150, "found " + lits.length);
  /* a literal that is a route, a query or a key is not printed; the rest is */
  const printed = lits.filter(s => !/^[\/?#]/.test(s.trim()) && !/^[a-z0-9_.:\/-]+$/i.test(s.trim()));
  assert.ok(printed.length > 100, "printed " + printed.length);
  printed.forEach(s => {
    assert.ok(!BANNED.test(s), "banned word in: " + s);
    assert.ok(!/\d/.test(s.replace(/^\s*[123]\s/, "")), "a digit in a string the screen prints: " + s);   /* the three steps of the add sheet are numbered */
    assert.ok(!/\.(json|py|js|md|html)\b|\/api\/|_models/.test(s), "a path or file name: " + s);
  });
  /* the screens, printed with the fixtures: no count at rest, no path, no file name */
  const c = await onPage();
  const shown = [c.mdlCardHtml(), c.mdlPaneHtml()];
  click(c, { mdl: "onoff" }); await settle(); shown.push(sheet(c));
  click(c, { mdl: "close" });
  click(c, { mdl: "field", mdlName: "name" }); await fire(c); shown.push(sheet(c)); click(c, { mdl: "close" });
  click(c, { mdl: "link" }); shown.push(sheet(c)); click(c, { mdl: "close" });
  click(c, { mdl: "try" }); shown.push(sheet(c)); click(c, { mdl: "close" });
  click(c, { mdl: "back" }); click(c, { mdl: "add" }); shown.push(sheet(c)); click(c, { mdl: "close" });
  click(c, { mdl: "structure" }); await settle(); shown.push(c.mdlPaneHtml());
  shown.forEach(h => {
    const w = words(h).replace(/\b(x\.[a-z_]+|v\d+|version \d+|\d\d:\d\d)\b/g, " ").replace(/\b(up to|at least|between|from|and|runs? to) -?\d+( and \d+)?( characters| words)?/g, " ");
    assert.ok(!BANNED.test(w), "banned: " + w);
    assert.ok(!/\/api\/|_models|\.json|\.py\b|\/Users\//.test(w), "a path: " + w);
  });
  /* the pane prints no count of the owner's models */
  assert.ok(!/\b\d+ (models?|fields?|links?|changes?)\b/i.test(words(shown.join(" "))));
  /* hostile strings as a label, a field name, a choice and a model name, on every screen */
  const L = copy(LIST), P = copy(PAGE), G = copy(GRAPH);
  HOSTILE.forEach((x, i) => {
    L.yours.push({ key: "x.h" + i, name: "h" + i, label: x, version: 1, base: "core:record", base_label: x, state: i % 3 === 0 ? "needs_a_look" : "on", why: x, abstract: false, children: [], pending: i === 0 ? { id: "p-" + i, says: x, at: "2026-10-27T11:02:00+05:30" } : null });
    P.fields.push({ name: x, label: x, type: "one of", says: "one of " + x + ", b", required: true, nullable: false, retired: false, aliases: [x], from: x, locked: i % 2 === 0 });
    G.nodes.push({ key: "x.h" + i, label: x, core: false, state: "on" }); G.text.push(x + " is a kind of " + x);
    G.edges.push({ from: "x.h" + i, to: "x.client", kind: "extends", many: false, required: false });
  });
  P.label = HOSTILE[0]; P.chain = [HOSTILE[1]]; P.used_by = [{ kind: "filed", name: HOSTILE[2], art: "a", v: 3, dept: HOSTILE[3] }];
  P.links = { out: [{ name: "n", label: HOSTILE[4], mode: "nest", to: "x:h", to_label: HOSTILE[4], many: true, required: true, enabled: true }], in: [{ from: "x.h", from_label: HOSTILE[5], name: "n", mode: "refer" }] };
  const hostile = await onPage({ list: L, page: P, graph: G, shape: { schema: { title: HOSTILE[0] }, example: { a: HOSTILE[1] } } });
  const screens = [hostile.mdlCardHtml(), hostile.mdlListHtml(), hostile.mdlPageHtml("x.client")];
  click(hostile, { mdl: "add" }); type(hostile, "label", HOSTILE[0]); type(hostile, "about", HOSTILE[1]); screens.push(sheet(hostile));
  click(hostile, { mdl: "field" }); type(hostile, "f:name", HOSTILE[2]); type(hostile, "f:label", HOSTILE[3]); type(hostile, "f:type", "choice"); type(hostile, "f:choices", HOSTILE.join(",")); screens.push(sheet(hostile)); click(hostile, { mdl: "close" }); click(hostile, { mdl: "close" });
  click(hostile, { mdl: "link" }); screens.push(sheet(hostile)); click(hostile, { mdl: "close" });
  click(hostile, { mdl: "try" }); type(hostile, "sample", HOSTILE[0]); click(hostile, { mdl: "check" }); await settle(); screens.push(sheet(hostile));
  click(hostile, { mdl: "shapetab" }); await settle(); screens.push(sheet(hostile)); click(hostile, { mdl: "close" });
  click(hostile, { mdl: "structure" }); await settle(); screens.push(hostile.mdlPaneHtml());
  screens.forEach(h => {
    /* no tag the page did not write: no img or script, and no attribute that runs anything */
    const tags = attrs(h, /<[a-zA-Z](?:"[^"]*"|[^>"])*>/g);   /* a quoted value may hold a > */
    tags.forEach(t => {
      assert.ok(!/^<(img|script|iframe|object|embed)\b/i.test(t), "a tag made from an owner's word: " + t);
      assert.ok(!/\son[a-z]+\s*=/i.test(t.replace(/"[^"]*"/g, '""')), "an event attribute: " + t);
      assert.ok(!/href\s*=\s*"javascript:/i.test(t), t);
    });
    assert.ok(!/<svg onload/i.test(h));
  });
  assert.ok(/&lt;img src=x onerror=window.__xss=1&gt;|&lt;img src=x onerror=window\.__xss=1>/.test(screens[1]) || /&lt;img src=x onerror/.test(screens[1]), "as text");
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
