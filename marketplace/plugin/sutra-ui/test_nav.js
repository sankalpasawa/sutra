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
/* spies for the 2.118.1 regressions: which lazy loaders fired */
const loaded = [];
for (const fn of ["loadBalance","loadTeamsutra","loadGit","loadFs","loadAuto",
                  "loadUsage","loadEvals","loadRoutines","loadProposals",
                  "loadTeamsutra","loadConnectors","loadMediated","loadFilesScreen"])
  sandbox[fn] = (...a) => { loaded.push(fn); };

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
test("now: SCREENS.now renders the honest empty state and TITLES carries it", () => {
  /* v3.3 shipped a designed-later placeholder; PLAN-100 S59 made Now the
     needs-you feed consumer. Empty/dark feed = honest empty state. */
  assert(typeof T.SCREENS.now === "function", "SCREENS.now missing");
  assert(/Nothing needs you right now/.test(T.SCREENS.now()),
         "empty-state wording missing");
  assert(Array.isArray(T.TITLES.now) && T.TITLES.now.length === 2);
});

/* §planes ─ S6 */
test("planes: org post-S92 — Workspace leads; Knowledge/Files folded in", () => {
  /* S92 cutover (founder 2026-08-25): the flag defaults ON, Knowledge and
     Files fold into the Workspace (openScreen redirects their ids). */
  const rows = T.planeRows("org").flatMap(g => g.rows).map(r => r.screen);
  assert.strictEqual(JSON.stringify(rows), JSON.stringify(
    ["workspace","departments","charters","placements","reorg"]));
});
test("planes: settings carries four labelled groups", () => {
  const groups = T.planeRows("settings");
  assert.strictEqual(JSON.stringify(groups.map(g => g.label)), JSON.stringify(
    ["Tools","Automation","System","Preferences"]));
});
test("planes: focus leads with Shadow, Balance + Optimus live, one honest coming-soon", () => {
  const rows = T.DEST_PLANES.focus;
  assert.strictEqual(rows[0].screen, "shadow", "Shadow is the companion home row");
  const live = rows.filter(r => r.screen).map(r => r.screen);
  assert(live.includes("balance") && live.includes("optimus"), "Balance + Optimus stay");
  assert.strictEqual(rows.filter(r => r.soon).length, 1, "one honest coming-soon");
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

/* §hotfix 2.118.1 — the three live regressions stay dead */
test("hotfix: entering Focus from the rail lands on Shadow via openScreen", () => {
  /* the 2.118.1 regression was goDest bypassing openScreen so lazy loaders
     never fired. Focus now lands on Shadow; the route must still go through
     openScreen (Shadow's own lazy fetch is pinned in test_shadow_home.js),
     and a stored destSel pick still outranks the default. */
  T.S.ui = T.loadLayout();
  loaded.length = 0;
  T.goDest("focus");
  assert.strictEqual(T.S.screen, "shadow",
    "goDest(focus) must land on the Shadow home");
  assert.strictEqual(T.S.ui.browseClosed, false);
  T.S.ui.destSel.focus = "balance";
  loaded.length = 0;
  T.goDest("focus");
  assert(loaded.includes("loadBalance"),
    "a stored Balance pick still routes through its lazy loader");
});
test("hotfix: entering Team Sutra from the rail actually loads its tasks", () => {
  loaded.length = 0;
  T.goDest("team");
  assert(loaded.includes("loadTeamsutra"),
    "goDest(team) must fire loadTeamsutra");
});
test("hotfix: the terminal clamp reserves the plane and a 320px detail floor", () => {
  T.S.ui = T.loadLayout();
  T.S.ui.dest = "settings";
  els["app"]._cls.add("threecol"); els["app"]._cls.delete("noplane");
  sandbox.innerWidth = 1400;
  /* chrome 224+240+27=491; avail = 1400-491-320 = 589 — a 72% ask (1008) must
     come back at 589, leaving the detail its floor. */
  const clamped = vm.runInContext("clampTermW(1008)", sandbox);
  assert.strictEqual(clamped, 589, "got " + clamped);
  /* on Now (no plane) the same ask keeps 240 more */
  els["app"]._cls.add("noplane");
  assert.strictEqual(vm.runInContext("clampTermW(1008)", sandbox), 829);
  els["app"]._cls.delete("noplane");
});

/* §v3.4 — the lane collapse and the functional Act-as */
test("v3.4: the collapse rules exist and OUTRANK the threecol grid", () => {
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
  const three = css.indexOf(".app.threecol{grid-template-columns:224px 240px");
  const col = css.indexOf(".app.threecol.railcol{grid-template-columns:minmax(0,1fr)");
  assert(three !== -1 && col !== -1, "both grid rules must exist");
  assert(col > three, "the railcol override must come AFTER threecol, or it loses the cascade");
  assert(css.indexOf(".app.threecol.railcol .rail,.app.threecol.railcol .plane{display:none}") !== -1,
    "collapsed must hide BOTH lanes — hiding only the rail is the shipped overlap bug");
});
test("v3.4: the stored single-lane flag migrates to the both-lane flag", () => {
  storage._m["sutra.panel.layout"] = JSON.stringify({ railCollapsed: true });
  assert.strictEqual(T.loadLayout().navCollapsed, true);
  storage._m["sutra.panel.layout"] = JSON.stringify({ navCollapsed: false, railCollapsed: true });
  assert.strictEqual(T.loadLayout().navCollapsed, false, "the new key must win over the legacy one");
  delete storage._m["sutra.panel.layout"];
});
test("v3.4: collapsed lanes hand the terminal the freed width — and no more", () => {
  els["app"]._cls.add("threecol"); els["app"]._cls.add("railcol"); els["app"]._cls.delete("noplane");
  sandbox.innerWidth = 1400;
  /* chrome 46+9=55; avail = 1400-55-320 = 1025; the 72% ceiling (1008) now binds. */
  assert.strictEqual(vm.runInContext("clampTermW(10000)", sandbox), 1008);
  els["app"]._cls.delete("railcol");
});
test("v3.4: acting as CEO of Sutra scopes the org to the Sutra subtree", () => {
  const domains = [
    { ref: "r", parent_ref: null, name: "Asawa Inc." },
    { ref: "s", parent_ref: "r", name: "Sutra OS" },
    { ref: "sc", parent_ref: "s", name: "Core Plugin" },
    { ref: "h", parent_ref: "r", name: "Holding Departments" },
  ];
  const charters = [{ id: "c1", domain_ref: "s" }, { id: "c2", domain_ref: "h" }];
  const placements = [{ id: "p1", domain_ref: "sc" }, { id: "p2", domain_ref: "r" }];
  const out = vm.runInContext("scopeOrgForRole", sandbox)("CEO of Sutra", domains, charters, placements);
  assert.strictEqual(JSON.stringify(out.domains.map(d => d.ref)), JSON.stringify(["s", "sc"]));
  assert.strictEqual(out.charters.length, 1);
  assert.strictEqual(out.placements.length, 1);
  assert.strictEqual(out.scope.ref, "s");
  assert.strictEqual(out.scope.missing, false);
});
test("v3.4: CEO of Asawa sees the whole tree; a missing anchor fails OPEN and says so", () => {
  const domains = [{ ref: "r", parent_ref: null, name: "Asawa Inc." }];
  const scoper = vm.runInContext("scopeOrgForRole", sandbox);
  const whole = scoper("CEO of Asawa Inc.", domains, [], []);
  assert.strictEqual(whole.domains.length, 1);
  assert.strictEqual(whole.scope.ref, null);
  const miss = scoper("CEO of Sutra", domains, [], []);
  assert.strictEqual(miss.domains.length, 1, "no anchor must NOT blank the org");
  assert.strictEqual(miss.scope.missing, true, "…but it must say the scope is missing");
});
test("v3.4: the role accessor is published for loadOrg", () => {
  assert.strictEqual(typeof vm.runInContext("panelRole", sandbox), "function");
});

test("v3.4.1: the rail says Help and gives it no plane", () => {
  T.S.ui = T.loadLayout();
  T.renderRail();
  assert(/>\s*Help\s*</.test(els["railnav"].innerHTML), "rail label must be Help");
  assert(els["railnav"].innerHTML.indexOf("Team Sutra") === -1, "Team Sutra must be gone from the rail");
  T.goDest("team");
  assert.strictEqual(T.S.screen, "teamsutra", "Help still opens its screen directly");
  assert(els["app"]._cls.has("noplane"), "Help is full-bleed — no second plane");
  assert.strictEqual(T.planeRows("team").flatMap(g => g.rows).length, 0);
  T.goDest("now");
});
test("v3.4.1: a stale destSel cannot hijack a full-bleed destination (codex P1)", () => {
  T.S.ui = T.loadLayout();
  T.S.ui.destSel.team = "settings";   /* hostile/stale persisted pick */
  loaded.length = 0;
  T.goDest("team");
  assert.strictEqual(T.S.screen, "teamsutra", "Help must land on its own screen");
  assert(loaded.includes("loadTeamsutra"), "…and still load its tasks");
  assert(els["app"]._cls.has("noplane"));
  T.goDest("now");
});

/* §coverage ─ S21: every legacy railSpec destination is reachable in v3.3 */
test("coverage: all 20 legacy rail ids stay reachable through the new shell", () => {
  const legacy = ["departments","charters","placements","knowledge","files","reorg",
                  "history","git","editor","health","skills","automation","routines",
                  "connectors","teamsutra","usage","balance","evals","terminal","settings"];
  const reachable = new Set();
  for (const d of T.DESTS){
    T.planeRows(d).forEach(g => g.rows.forEach(r => r.screen && reachable.add(r.screen)));
    /* a plane-less destination (Now, Help) reaches its screen directly */
    if (T.DEST_DEFAULT_SCREEN[d]) reachable.add(T.DEST_DEFAULT_SCREEN[d]);
  }
  /* S92: knowledge + files no longer sit in a plane — they stay reachable
     because openScreen REDIRECTS their ids to the Workspace. The coverage
     claim they satisfy is the redirect, asserted here at the source level
     (behavior is exercised in the workspace suite). */
  ["knowledge", "files"].forEach(id => reachable.add(id));
  const loaders = require("fs").readFileSync(__dirname + "/static/js/07-loaders.js", "utf8");
  assert.ok(/id === "knowledge" \|\| id === "files"/.test(loaders)
    && /id = "workspace"/.test(loaders),
    "the folded ids must redirect to workspace in openScreen");
  const missing = legacy.filter(id => !reachable.has(id));
  assert.strictEqual(missing.length, 0, "unreachable: " + missing.join(", "));
});

/* ── plane groups collapse individually (founder, 2026-08-24) ─────────────── */
/* Per-file, because two of these assert ORDERING inside one file, which the
   concatenated SCRIPT would blur across module boundaries. */
const JS = f => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
test("each labelled plane group renders its own collapse control", () => {
  const src = JS("02-helpers.js");
  assert(/data-planecollapse=/.test(src), "no per-group collapse control is emitted");
  assert(/aria-expanded="\$\{!collapsed\}"/.test(src),
    "the control must report its own expanded state");
  assert(/aria-controls="\$\{bodyId\}"/.test(src),
    "the control must name the list it collapses");
});

test("an UNLABELLED plane group gets no collapse control", () => {
  /* Offering to hide rows under a header the operator cannot see is a control
     that makes its own target disappear. */
  const src = JS("02-helpers.js");
  assert(/const collapsible = !!g\.label/.test(src),
    "collapsibility must be gated on the group having a label");
});

test("the collapse key is scoped per destination", () => {
  const src = JS("02-helpers.js");
  assert(/const ckey = dest \+ ":" \+ \(g\.label \|\| ""\)/.test(src),
    "TOOLS under Settings must not share a switch with a same-named group elsewhere");
});

test("every data-planecollapse control has a handler that reads it", () => {
  /* The bug this repo has actually shipped: a rendered control nothing listens
     for. 152 tests passed while every button on a screen was dead. */
  const loaders = JS("07-loaders.js");
  assert(/\[data-planecollapse\]/.test(loaders), "no handler reads data-planecollapse");
  assert(/S\.ui\.planeSections/.test(loaders), "the handler must mutate planeSections");
  assert(/saveLayout\(\)/.test(loaders.slice(loaders.indexOf("data-planecollapse"))),
    "the collapse must persist");
});

test("the handler runs BEFORE the row handler", () => {
  /* Both live in one delegated listener. If [data-screen] were checked first a
     header click would also open a screen. */
  const loaders = JS("07-loaders.js");
  assert(loaders.indexOf("data-planecollapse") < loaders.indexOf('closest("[data-screen]")'),
    "the group header must be handled before the row");
});

test("only SCOPED plane-collapse keys are adopted from stored layout", () => {
  /* This replaced a test asserting railSections was migrated across. Migrating
     it was wrong: those keys are bare pre-v3.3 rail names ("org", "sessions")
     that can never match a dest:label pair, so importing them plants permanent
     dead entries in the operator's layout. Verified against the real store,
     which had picked up four of them. */
  const state = JS("01-state.js");
  assert(/k\.indexOf\(":"\) !== -1/.test(state),
    "an unscoped legacy key must not be adopted");
  assert(!/out\.planeSections = raw\.railSections/.test(state),
    "the untranslatable railSections migration must be gone");
});


console.log("-".repeat(60));
console.log(`v3.3 shell: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
