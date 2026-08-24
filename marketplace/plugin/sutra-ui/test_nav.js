#!/usr/bin/env node
/*
 * test_nav.js -- the v3.3 shell: six destinations, the second plane, the
 * identity footer, and the accent colour (PLAN-25 S3-S19).
 *
 * Same discipline as test_panel.js: extract the module list panel.html loads,
 * concatenate in source order, run under vm with a minimal DOM stub, assert on
 * the REAL functions. No doubles of the logic under test.
 *
 * Run: node test_nav.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const PANEL = path.join(__dirname, "static", "panel.html");
const html = fs.readFileSync(PANEL, "utf8");
const srcs = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(?:\?[^"]*)?"/g)].map(m => m[1]);
assert(srcs.length >= 5, "panel.html must list its js modules");
const SCRIPT = srcs.map(f =>
  fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8")).join("\n;\n");

/* ── minimal DOM/browser stub ─────────────────────────────────────────────── */
function makeNode(tag){
  const node = {
    tagName: tag, children: [], dataset: {}, style: { setProperty(){}, removeProperty(){} },
    _attrs: {}, _cls: new Set(), innerHTML: "", textContent: "", hidden: false, value: "",
    classList: {
      add: (...c) => c.forEach(x => node._cls.add(x)),
      remove: (...c) => c.forEach(x => node._cls.delete(x)),
      toggle: (c, on) => { (on === undefined ? !node._cls.has(c) : on) ? node._cls.add(c) : node._cls.delete(c); },
      contains: c => node._cls.has(c),
    },
    setAttribute: (k, v) => { node._attrs[k] = String(v); },
    getAttribute: k => (k in node._attrs ? node._attrs[k] : null),
    removeAttribute: k => { delete node._attrs[k]; },
    addEventListener() {}, removeEventListener() {},
    appendChild(c){ node.children.push(c); return c; },
    querySelector: () => null, querySelectorAll: () => [],
    closest: () => null, contains: () => false, focus() {},
  };
  return node;
}
const els = {};                       /* id -> node, so assertions can inspect */
const doc = {
  documentElement: makeNode("html"),
  getElementById: id => (els[id] ||= makeNode("div")),
  querySelector: () => makeNode("div"),
  querySelectorAll: () => [],
  createElement: t => makeNode(t),
  addEventListener() {}, body: makeNode("body"),
};
const storage = { _m: {}, getItem(k){ return k in this._m ? this._m[k] : null; },
  setItem(k, v){ this._m[k] = String(v); }, removeItem(k){ delete this._m[k]; } };
const sandbox = {
  document: doc, localStorage: storage, console,
  fetch: () => new Promise(() => {}),          /* never settles, like test_panel */
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  WebSocket: function(){ return { addEventListener() {}, send() {}, close() {} }; },
  location: { search: "", protocol: "http:", host: "x" },
  navigator: { platform: "MacIntel" }, history: { replaceState() {} },
  setInterval: () => 0, setTimeout: () => 0, clearInterval() {}, clearTimeout() {},
  requestAnimationFrame: fn => fn(), innerWidth: 1400,
  navOrg: makeNode("div"), navChange: makeNode("div"), navRuntime: makeNode("div"),
  themeBtn: makeNode("button"),
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(SCRIPT, sandbox, { filename: "panel-modules.js" });
/* render() repaints the whole shell; these are unit tests of the model, so a
   no-op keeps goDest() honest without dragging the full paint pipeline in.
   (Top-level function declarations are globals, so this override is real.) */
sandbox.render = () => {};
/* const/let at a vm script's top level live in the context's lexical scope,
   not on the sandbox object — capture them from INSIDE the context. */
const T = vm.runInContext(`({ DESTS, DEST_PLANES, DEST_DEFAULT_SCREEN, S, SCREENS, TITLES,
  loadLayout, planeRows, goDest, renderRail, paintTelemetry, applyAccent, onAccFor,
  buildAccentRow, ACCENTS, document })`, sandbox);

/* ── harness ──────────────────────────────────────────────────────────────── */
let passed = 0, failed = 0;
function test(name, fn){
  try { fn(); passed++; console.log("ok   - " + name); }
  catch (e) { failed++; console.log("FAIL - " + name + "\n       " + e.message); }
}

/* §model ─ S3 */
test("model: exactly six destinations, in the founder's order", () => {
  assert.strictEqual(JSON.stringify(T.DESTS), JSON.stringify(["now","focus","chats","org","team","settings"]));
});
test("model: a stored Code tab migrates to Chats", () => {
  storage._m["sutra.panel.layout"] = JSON.stringify({ railTab: "code" });
  assert.strictEqual(T.loadLayout().dest, "chats");
  delete storage._m["sutra.panel.layout"];
});
test("model: a hostile destSel is filtered to known destinations", () => {
  storage._m["sutra.panel.layout"] =
    JSON.stringify({ destSel: { org: "charters", bogus: "x", team: 42 } });
  const out = T.loadLayout();
  assert.strictEqual(JSON.stringify(out.destSel), JSON.stringify({ org: "charters" }));
  delete storage._m["sutra.panel.layout"];
});

/* §now ─ S4 */
test("now: SCREENS.now renders an honest placeholder and TITLES carries it", () => {
  assert(typeof T.SCREENS.now === "function", "SCREENS.now missing");
  assert(/placeholder/i.test(T.SCREENS.now()), "placeholder wording missing");
  assert(Array.isArray(T.TITLES.now) && T.TITLES.now.length === 2);
});

/* §planes ─ S6 */
test("planes: org lists its six screens, Files included, railSpec-decorated", () => {
  const rows = T.planeRows("org").flatMap(g => g.rows).map(r => r.screen);
  assert.strictEqual(JSON.stringify(rows), JSON.stringify(
    ["departments","charters","placements","knowledge","files","reorg"]));
});
test("planes: settings carries four labelled groups", () => {
  const groups = T.planeRows("settings");
  assert.strictEqual(JSON.stringify(groups.map(g => g.label)), JSON.stringify(
    ["Tools","Automation","System","Preferences"]));
});
test("planes: focus offers Balance live and two honest comings-soon", () => {
  const rows = T.planeRows("focus").flatMap(g => g.rows);
  assert.strictEqual(rows.length, 3);
  assert.strictEqual(rows.filter(r => r.disabled).length, 2);
  assert.strictEqual(rows[0].screen, "balance");
});

/* §rail ─ S7 */
test("rail: renderRail paints six data-dest buttons", () => {
  T.S.ui = T.loadLayout();
  T.renderRail();
  const out = els["railnav"].innerHTML;
  assert.strictEqual((out.match(/data-dest="/g) || []).length, 6);
});

/* §chats ─ S8: the Code tab's controls survive, verbatim, exactly once */
test("chats: newSession, sgroup filters, sessSort and #sessions moved intact", () => {
  for (const needle of ['id="newSession"', 'id="sessSort"', 'id="sessions"'])
    assert.strictEqual(html.split(needle).length - 1, 1, needle + " must occur exactly once");
  assert.strictEqual((html.match(/data-sgroup="/g) || []).length, 3);
  const plane = html.slice(html.indexOf('id="plane"'));
  assert(plane.indexOf('id="sessions"') !== -1, "#sessions must live inside the plane");
});
test("chats: the old tab chrome is gone", () => {
  for (const dead of ["rtabs", "data-railtab", "tabHome", "tabCode"])
    assert.strictEqual(html.indexOf(dead), -1, dead + " should be deleted");
});

/* §switching ─ S9 */
test("switching: chats yields the browse pane; org restores the remembered pick", () => {
  T.S.ui = T.loadLayout();
  T.S.ui.destSel.org = "charters";
  T.goDest("chats");
  assert.strictEqual(T.S.ui.dest, "chats");
  assert.strictEqual(T.S.ui.browseClosed, true);
  T.goDest("org");
  assert.strictEqual(T.S.screen, "charters");
  assert.strictEqual(T.S.ui.browseClosed, false);
  T.goDest("bogus");
  assert.strictEqual(T.S.ui.dest, "org", "an unknown destination must be refused");
});

/* §footer + §menu ─ S11-S13 */
test("footer: the identity block states a role and offers exactly the two jobs", () => {
  assert(html.indexOf('id="idRole"') !== -1 && html.indexOf('id="idStat"') !== -1);
  assert(html.indexOf('id="roleList"') !== -1);
  const menu = html.slice(html.indexOf('id="idMenu"'), html.indexOf('id="idBtn"'));
  assert(menu.indexOf('id="themeBtn"') !== -1, "theme switch must live in the menu");
  for (const dead of ["Sign out", "Account settings", ">Account<"])
    assert.strictEqual(html.indexOf(dead), -1, dead + " must not exist");
});
test("roles: the pick persists and survives a reload", () => {
  storage._m["sutra.panel.role"] = "CEO of Sutra";
  assert.strictEqual(storage.getItem("sutra.panel.role"), "CEO of Sutra");
  delete storage._m["sutra.panel.role"];
});

/* §telemetry ─ S14 */
test("telemetry: renders the utilization when known, an em-dash when not", () => {
  T.S.usage = null; T.paintTelemetry();
  assert.strictEqual(els["idStat"].textContent, "—");
  T.S.usage = { available: true, limits: [{ active: true, percent: 63.4 }] };
  T.paintTelemetry();
  assert.strictEqual(els["idStat"].textContent, "63% of the usage window");
  T.S.usage = null;
});

/* §accent ─ S15-S19 */
test("accent: applyAccent sets the vars, persists, and reset clears", () => {
  const r = T.document.documentElement;
  const seen = {};
  r.style.setProperty = (k, v) => { seen[k] = v; };
  r.style.removeProperty = k => { delete seen[k]; };
  assert.strictEqual(T.applyAccent("#4A6B8B"), true);
  assert.strictEqual(seen["--acc"], "#4A6B8B");
  assert(seen["--on-acc"], "--on-acc must be set");
  assert.strictEqual(storage.getItem("sutra.panel.accent"), "#4A6B8B");
  assert.strictEqual(T.applyAccent(null), true);
  assert.strictEqual(storage.getItem("sutra.panel.accent"), null);
  assert(!("--acc" in seen), "reset must remove the override");
});
test("accent: the contrast floor rejects an unusable colour outright", () => {
  /* #777777 sits in the dead band: 4.18:1 against the dark ink, 4.49:1
     against white — neither text colour clears 4.5, so the swatch must be
     refused outright rather than shipped dimmer. */
  assert.strictEqual(T.onAccFor("#777777"), null, "the dead-band grey clears no floor");
  assert.strictEqual(T.applyAccent("#777777"), false);
  assert.strictEqual(T.onAccFor("#2D5A3E"), "#ffffff");
  assert.strictEqual(T.onAccFor("#C9A227") === null, false);
});
test("accent: every offered swatch clears the floor; the row offers reset + 6", () => {
  assert.strictEqual(T.ACCENTS.length, 6);
  assert.strictEqual(T.ACCENTS.filter(h => T.onAccFor(h)).length, T.ACCENTS.length,
    "a shipped swatch below the floor would be dropped silently — fix the palette instead");
  T.buildAccentRow();
  const row = els["accentRow"].innerHTML;
  assert.strictEqual((row.match(/data-accent="/g) || []).length, 7, "reset + 6 swatches");
});
test("accent: the per-theme tint derivation lives in the stylesheet", () => {
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
  assert((css.match(/data-accent[^\n]*color-mix/g) || []).length >= 2,
    "both themes must derive --acc-bg from the one hex");
});

/* §coverage ─ S21: every legacy railSpec destination is reachable in v3.3 */
test("coverage: all 20 legacy rail ids stay reachable through the new shell", () => {
  const legacy = ["departments","charters","placements","knowledge","files","reorg",
                  "history","git","editor","health","skills","automation","routines",
                  "connectors","teamsutra","usage","balance","evals","terminal","settings"];
  const reachable = new Set();
  for (const d of T.DESTS)
    T.planeRows(d).forEach(g => g.rows.forEach(r => r.screen && reachable.add(r.screen)));
  const missing = legacy.filter(id => !reachable.has(id));
  assert.strictEqual(missing.length, 0, "unreachable: " + missing.join(", "));
});

console.log("-".repeat(60));
console.log(`v3.3 shell: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
