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
/* PROVIDERS and SETTINGS need getter/setter pairs, not plain properties: a
   top-level `let` in a classic script lives in the SCRIPT scope, not on the
   global object, so `T.PROVIDERS = x` would set a field on this literal and
   leave the binding the code actually reads untouched. Same reason test_panel.js
   gives for SETTINGS. */
const T = vm.runInContext(`({ DESTS, DEST_PLANES, DEST_DEFAULT_SCREEN, S, SCREENS, TITLES,
  loadLayout, planeRows, goDest, renderRail, paintTelemetry, applyAccent, onAccFor,
  buildAccentRow, ACCENTS, document,
  get PROVIDERS(){ return PROVIDERS; }, set PROVIDERS(v){ PROVIDERS = v; },
  get SETTINGS(){ return SETTINGS; }, set SETTINGS(v){ SETTINGS = v; } })`, sandbox);
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
test("model: exactly seven destinations, in the founder's order", () => {
  /* 2.239.0: Agents joined the rail after Chats -- the SEO Writer is the first
     agent that works in front of you (design/GAME-PLAN-agents.md). */
  /* Seven again since 2026-09-04: Routines went back under Settings ->
     Automation, the home it held before the 2026-09-02 promotion. */
  assert.strictEqual(JSON.stringify(T.DESTS),
    JSON.stringify(["now","focus","chats","agents","org","team","settings"]));
});
test("model: routines is a Settings -> Automation row, not a destination", () => {
  /* One home, not two: it must be a row on the Settings plane AND absent from
     the rail model entirely -- DESTS, the plane spec and the landing map. */
  assert.strictEqual(T.DESTS.indexOf("routines"), -1, "routines is not a destination");
  assert.strictEqual(T.DEST_PLANES.routines, undefined, "no routines plane spec");
  assert.strictEqual(T.DEST_DEFAULT_SCREEN.routines, undefined, "no routines landing screen");
  const auto = T.planeRows("settings").find(g => g.label === "Automation");
  assert(auto, "Settings must carry an Automation group");
  const rows = auto.rows.map(r => r.screen);
  assert.strictEqual(JSON.stringify(rows),
    JSON.stringify(["skills","automation","routines","connectors"]));
  /* the name is unchanged -- the row still reads "Routines" */
  assert.strictEqual(auto.rows[rows.indexOf("routines")].label, "Routines");
});
test("model: a stored Routines destination migrates to Settings, on that row", () => {
  storage._m["sutra.panel.layout"] =
    JSON.stringify({ dest: "routines", destSel: { settings: "health" } });
  const out = T.loadLayout();
  assert.strictEqual(out.dest, "settings");
  assert.strictEqual(out.destSel.settings, "routines", "the migrated pick wins");
  delete storage._m["sutra.panel.layout"];
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
  /* 2.247.0: Modules sits after Placements (design D-M7) -- the products the
     operator builds, before the one row that changes the org itself. */
  assert.strictEqual(JSON.stringify(rows), JSON.stringify(
    ["workspace","departments","charters","placements","modules","reorg"]));
});
test("planes: settings carries three labelled groups", () => {
  /* Was four. "Preferences" held exactly one row -- the AI Provider screen --
     and a group wrapping a single row is a header that earns nothing. The row
     moved into System (founder 2026-09-03), which is where the rest of the
     machine-state screens already live. The assertion stays EXACT rather than
     loosening to a subset: this plane is a fixed, ordered list. */
  const groups = T.planeRows("settings");
  assert.strictEqual(JSON.stringify(groups.map(g => g.label)), JSON.stringify(
    ["Tools","Automation","System"]));
  const system = groups.find(g => g.label === "System").rows.map(r => r.screen);
  /* Usage lost its row on 2026-09-03 -- it renders as a section inside the AI
     Assistant screen, since how much of an assistant you have used is a fact
     about the assistant you just picked. The SCREEN is still registered. */
  assert.strictEqual(JSON.stringify(system), JSON.stringify(
    ["health","evals","history","settings"]),
    "the AI Provider row must be the last System row, and Usage must not be one");
  assert.ok(T.SCREENS && typeof T.SCREENS.usage === "function",
    "the usage screen must stay registered so openScreen('usage') still resolves");
});
test("planes: focus leads with Shadow, Balance + Optimus live, one honest coming-soon", () => {
  const rows = T.DEST_PLANES.focus;
  assert.strictEqual(rows[0].screen, "shadow", "Shadow is the companion home row");
  const live = rows.filter(r => r.screen).map(r => r.screen);
  assert(live.includes("balance") && live.includes("optimus"), "Balance + Optimus stay");
  assert.strictEqual(rows.filter(r => r.soon).length, 1, "one honest coming-soon");
});

/* §rail ─ S7 */
test("rail: renderRail paints seven data-dest buttons", () => {
  T.S.ui = T.loadLayout();
  T.renderRail();
  const out = els["railnav"].innerHTML;
  assert.strictEqual((out.match(/data-dest="/g) || []).length, 7);
});

/* §chats ─ S8: the Code tab's controls survive, verbatim, exactly once */
test("chats: newSession and #sessions intact; three groupings, no sort", () => {
  for (const needle of ['id="newSession"', 'id="sessions"'])
    assert.strictEqual(html.split(needle).length - 1, 1, needle + " must occur exactly once");
  /* Recent + Dept + Routines. Project grouping and the sort control it fed were
     deleted on 2026-09-02 (founder); Routines was added on 2026-09-13, because
     routine runs are real transcripts and were 1,009 of 1,208 rows in the rail
     -- indistinguishable from hand-started chats until they had their own
     section. The COUNT is pinned so a fourth cannot appear unnoticed. */
  assert.strictEqual((html.match(/data-sgroup="/g) || []).length, 3);
  for (const g of ["recent", "dept", "routines"])
    assert(html.indexOf('data-sgroup="' + g + '"') !== -1, g + " grouping must exist");
  assert(html.indexOf('data-sgroup="project"') === -1, "Project grouping must be gone");
  assert(html.indexOf('id="sessSort"') === -1, "the sort control must be gone");
  const helpers = fs.readFileSync(
    path.join(__dirname, "static", "js", "02-helpers.js"), "utf8");
  assert(helpers.indexOf('S.sgroup === "project"') === -1,
    "the project grouping branch must be deleted, not orphaned");
  const plane = html.slice(html.indexOf('id="plane"'));
  assert(plane.indexOf('id="sessions"') !== -1, "#sessions must live inside the plane");
});
/* The partition invariant (founder, 2026-09-02): "all chats are there in the
   department". Dept must PARTITION S.sessions, not filter it -- a chat with no
   resolved department lands in the catch-all rather than vanishing. */
test("dept: every chat is rendered, filed or not", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  /* The three ways a chat can carry no department, plus one that carries one.
     The AXIS changed on 2026-09-08 -- a department comes from the chat's
     working directory (every Claude project is a department, project_import.py)
     rather than from its turns' placements -- so these fixtures describe
     directories, not turns. The INVARIANT this test exists for is unchanged
     and is what the assertions below still check: every chat renders, the
     catch-all is labelled and counted, and each chat gets a stated reason
     rather than one flattened shrug. */
  T.S.sessions = [
    { id:"s-nocwd",   title:"no folder recorded",   real:true, loadState:"unread",
      cwd:"", turns:[], updated_ms:1 },
    { id:"s-scratch", title:"ran in a scratchpad",  real:true, loadState:"ok",
      cwd:"/private/tmp/claude-501/x/scratchpad", turns:[], updated_ms:2 },
    { id:"s-elsewhere", title:"folder never imported", real:false, loadState:"ok",
      cwd:"/Users/x/somewhere-else", turns:[], updated_ms:3 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  for (const s of T.S.sessions)
    assert(out.indexOf('data-sid="' + s.id + '"') !== -1,
           s.id + " was dropped from the department view");
  /* Label and count live in separate spans since the group became collapsible
     (2026-09-08); both must still be there -- a catch-all that does not say how
     many chats it holds is the thing this test exists to prevent. */
  assert(/<span class="rgn">No department yet<\/span>/.test(out),
         "the catch-all must be labelled");
  assert(/No department yet<\/span>\s*<span class="rgc">3<\/span>/.test(out),
         "the catch-all must be counted");
  for (const why of ["no folder recorded", "scratch folder, not imported",
                     "folder is not an imported project"])
    assert(out.indexOf(why) !== -1, "missing reason: " + why);
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
});
test("dept: chats group under the department that owns their folder", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  /* `department` is resolved server-side from the chat's cwd
     (app.py _with_departments). Two chats in one department must produce ONE
     heading holding both -- a department that can only hold a single chat is
     the thing this feature exists to stop. */
  const sutra = { ref:"dref-s", name:"Sutra", cwd:"/d/sutra" };
  T.S.sessions = [
    { id:"s-a", title:"first",  real:true, loadState:"ok", turns:[],
      cwd:"/d/sutra", department:sutra, updated_ms:2 },
    { id:"s-b", title:"second", real:true, loadState:"ok", turns:[],
      cwd:"/d/sutra/deep", department:sutra, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert((out.match(/class="rgrp rgrph/g) || []).length === 1,
         "two chats in one department must share one heading");
  assert(/Sutra<\/span>\s*<span class="rgc">2<\/span>/.test(out),
         "the heading must count the chats it holds");
  for (const id of ["s-a", "s-b"])
    assert(out.indexOf('data-sid="' + id + '"') !== -1, id + " was dropped");
  assert(out.indexOf("No department yet") === -1,
         "a filed chat must not also appear in the catch-all");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
});
test("dept: the + starts a chat in that department's own folder", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  T.S.sessions = [
    { id:"s-a", title:"first", real:true, loadState:"ok", turns:[], cwd:"/d/sutra",
      department:{ ref:"dref-s", name:"Sutra", cwd:"/d/sutra" }, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  /* The cwd on the button is what newSession receives, and it is the
     DEPARTMENT's directory rather than the clicked chat's -- otherwise a new
     chat started from a heading would inherit a subdirectory and could resolve
     to a different (deeper) department than the one it was started from. */
  assert(/data-act="dept-new"/.test(out), "the department heading needs a +");
  assert(/data-cwd="\/d\/sutra"/.test(out), "the + must carry the department's own cwd");
  assert(/data-ref="dref-s"/.test(out), "the + must carry the department ref");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
});
test("dept: a department with no folder gets no + rather than a broken one", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  /* A department minted by some other path carries no cwd. Rendering a + for
     it would open a chat in whatever the default workdir is and file it
     somewhere else entirely -- a button that lies about what it does. */
  T.S.sessions = [
    { id:"s-a", title:"first", real:true, loadState:"ok", turns:[], cwd:"/d/x",
      department:{ ref:"dref-n", name:"No Folder" }, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("No Folder") !== -1, "the department must still render");
  assert(out.indexOf('data-act="dept-new"') === -1,
         "a department with no cwd must not offer a +");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
});
test("dept: a group collapses, hiding its chats but not its count", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  const sutra = { ref:"dref-s", name:"Sutra", cwd:"/d/sutra" };
  T.S.sessions = [
    { id:"s-a", title:"first",  real:true, loadState:"ok", turns:[],
      cwd:"/d/sutra", department:sutra, updated_ms:2 },
    { id:"s-b", title:"second", real:true, loadState:"ok", turns:[],
      cwd:"/d/sutra", department:sutra, updated_ms:1 },
  ];
  T.renderRail();
  let out = T.document.getElementById("sessions").innerHTML;
  assert(/data-deptcollapse="dept:dref-s"/.test(out), "the heading must be a toggle");
  assert(/aria-expanded="true"/.test(out), "a group defaults to expanded");
  assert(!/<ul class="rlist"[^>]*hidden/.test(out), "an expanded group must not be hidden");

  T.S.ui.sessCollapsed = { "dept:dref-s": true };
  T.renderRail();
  out = T.document.getElementById("sessions").innerHTML;
  assert(/rgrp rgrph collapsed/.test(out), "a collapsed group needs the class the chevron keys off");
  assert(/aria-expanded="false"/.test(out), "collapsed must be announced");
  assert(/<ul class="rlist"[^>]*hidden/.test(out), "a collapsed group must hide its chats");
  /* The count stays readable while collapsed: a folded group that also hides
     how much it holds gives no reason to unfold it. */
  assert(/<span class="rgc">2<\/span>/.test(out), "the count must survive collapsing");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup; T.S.ui = T.loadLayout();
});
test("dept: collapse is keyed by ref, so a rename keeps the group folded", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  T.S.ui.sessCollapsed = { "dept:dref-s": true };
  T.S.sessions = [
    { id:"s-a", title:"first", real:true, loadState:"ok", turns:[], cwd:"/d/sutra",
      department:{ ref:"dref-s", name:"Renamed In The Registry", cwd:"/d/sutra" },
      updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(/rgrp rgrph collapsed/.test(out),
         "a department renamed in the registry must stay collapsed");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup; T.S.ui = T.loadLayout();
});
test("dept: the catch-all collapses too, and keeps its per-chat reasons", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  T.S.sessions = [
    { id:"s-x", title:"unplaced", real:true, loadState:"ok", turns:[],
      cwd:"/private/tmp/scratch", updated_ms:1 },
  ];
  T.renderRail();
  let out = T.document.getElementById("sessions").innerHTML;
  assert(/data-deptcollapse="dept:__none__"/.test(out), "the catch-all must collapse too");
  assert(out.indexOf("scratch folder, not imported") !== -1,
         "the per-chat reason must survive the shared group renderer");

  T.S.ui.sessCollapsed = { "dept:__none__": true };
  T.renderRail();
  out = T.document.getElementById("sessions").innerHTML;
  assert(/<ul class="rlist"[^>]*hidden/.test(out), "the collapsed catch-all must hide its chats");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup; T.S.ui = T.loadLayout();
});
/* DOMAINS is a module-level `let`, not part of T's export list, so it is read
   and written through the sandbox the same way scopeOrgForRole is. */
const getDomains = () => vm.runInContext("DOMAINS", sandbox);
const setDomains = list =>
  vm.runInContext("DOMAINS = " + JSON.stringify(list), sandbox);

test("dept: every imported department is listed, not only ones with a loaded chat", () => {
  /* The defect: the list was built from S.sessions -- ONE PAGE of 100 -- so a
     department whose newest chat is older than that page vanished entirely.
     8 of 24 showed, against a Claude project list that shows every project. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([
    { ref:"r",  parent_ref:null, name:"Co" },
    { ref:"d1", parent_ref:"r", name:"Loaded",   cwd:"/d/one", sessions:5 },
    { ref:"d2", parent_ref:"r", name:"Unloaded", cwd:"/d/two", sessions:3 },
    { ref:"d3", parent_ref:"r", name:"Empty",    cwd:"/d/three", sessions:0 },
    { ref:"d4", parent_ref:"r", name:"HandMade" },   /* no cwd: not a chat container */
  ]);
  T.S.sessions = [
    { id:"s-a", title:"a", real:true, loadState:"ok", turns:[], cwd:"/d/one",
      department:{ ref:"d1", name:"Loaded", cwd:"/d/one" }, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  for (const n of ["Loaded", "Unloaded", "Empty"])
    assert(out.indexOf(n) !== -1, n + " must be listed");
  assert(out.indexOf("HandMade") === -1,
         "a department with no cwd is not a chat container and must stay out");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains); T.S.ui = T.loadLayout();
});
test("dept: the heading shows the department's real size, not the loaded page", () => {
  /* It read "90" for a project holding 941. A count wrong by 10x is worse
     than no count. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([{ ref:"r", parent_ref:null, name:"Co" },
              { ref:"d1", parent_ref:"r", name:"Big", cwd:"/d/big", sessions:941 }]);
  T.S.sessions = [
    { id:"s-a", title:"a", real:true, loadState:"ok", turns:[], cwd:"/d/big",
      department:{ ref:"d1", name:"Big", cwd:"/d/big" }, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(/<span class="rgc">941<\/span>/.test(out),
    "the heading must state the department's true size");
  assert(!/<span class="rgc">1<\/span>/.test(out),
    "it must not report the number of chats on this page");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains); T.S.ui = T.loadLayout();
});
test("dept: an enumerated department with nothing on this page says which", () => {
  /* Two different situations, two different sentences -- a heading over a void
     makes the operator guess whether the department is empty or just paged out. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([{ ref:"r", parent_ref:null, name:"Co" },
              { ref:"d1", parent_ref:"r", name:"Older", cwd:"/d/a", sessions:7 },
              { ref:"d2", parent_ref:"r", name:"Fresh", cwd:"/d/b", sessions:0 }]);
  T.S.sessions = [];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("7 sessions here, none started in Sutra yet") !== -1,
    "a department with sessions but no Sutra chat must say which");
  assert(out.indexOf("nothing here yet") !== -1,
    "a genuinely empty department must say THAT instead");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains); T.S.ui = T.loadLayout();
});
test("dept: an unloaded org tree degrades to the loaded-page grouping", () => {
  /* The guard. With DOMAINS empty the enumeration adds nothing and the view
     behaves exactly as it did before -- it must not empty itself at boot. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([]);
  T.S.sessions = [
    { id:"s-a", title:"a", real:true, loadState:"ok", turns:[], cwd:"/d/one",
      department:{ ref:"d1", name:"Loaded", cwd:"/d/one" }, updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("Loaded") !== -1, "the loaded chat's department must still group");
  assert(out.indexOf('data-sid="s-a"') !== -1, "and its chat must still render");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains); T.S.ui = T.loadLayout();
});
test("dept: the empty-state reason depends on which chats are shown", () => {
  /* Saying the wrong reason is worse than saying none. Scoped, an empty
     department means the work happened outside Sutra; showing everything, that
     sentence is false and the only honest reason is that those sessions are
     older than the loaded page. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  const prevSettings = T.SETTINGS;
  T.S.sgroup = "dept";
  setDomains([{ ref:"r", parent_ref:null, name:"Co" },
              { ref:"d1", parent_ref:"r", name:"Older", cwd:"/d/a", sessions:7 }]);
  T.S.sessions = [];

  T.SETTINGS = { chat_scope: "sutra" };
  T.renderRail();
  let out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("none started in Sutra yet") !== -1,
    "scoped: must say the work happened elsewhere");

  T.SETTINGS = { chat_scope: "all" };
  T.renderRail();
  out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("none started in Sutra yet") === -1,
    "showing everything: that reason is false and must not appear");
  assert(out.indexOf("older than the loaded list") !== -1,
    "incomplete list: the honest reason is the bound");
  assert(!/scroll to load/i.test(out),
    "must not promise scrolling loads more -- this client has no offset paging");

  /* The list IS complete, so the sessions are recorded with no transcript to
     show -- five real projects on the founder's Mac are exactly this, and
     calling them "older than the loaded list" was a lie about pagination. */
  T.S.sessionsComplete = true;
  T.renderRail();
  out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("no transcript on this Mac") !== -1,
    "complete list: an empty department has no transcript, not a paging problem");
  assert(out.indexOf("older than the loaded list") === -1,
    "complete list: the bound is not the reason and must not be given as one");
  T.S.sessionsComplete = false;

  T.SETTINGS = prevSettings;
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains); T.S.ui = T.loadLayout();
});

test("routines: chats group by the routine that produced them", () => {
  T.S.ui = T.loadLayout();
  const prev = T.S.sessions, pg = T.S.sgroup;
  T.S.sgroup = "routines";
  T.S.sessions = [
    { id:"r1", title:"run a", real:true, loadState:"ok", turns:[], updated_ms:3,
      routine:{ routine:"si-feedback-sync", outcome:"ok" } },
    { id:"r2", title:"run b", real:true, loadState:"ok", turns:[], updated_ms:2,
      routine:{ routine:"si-feedback-sync", outcome:"failed" } },
    { id:"h1", title:"my own chat", real:true, loadState:"ok", turns:[], updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf("si-feedback-sync") !== -1, "the routine must head its own group");
  for (const id of ["r1","r2"])
    assert(out.indexOf('data-sid="'+id+'"') !== -1, id + " must render under its routine");
  /* A filter, not a partition (founder, 2026-09-13): a chat no routine produced
     does not appear in this view at all -- it lives in Recent and Dept. */
  assert(out.indexOf("Not from a routine") === -1, "there is no catch-all group here");
  assert(out.indexOf('data-sid="h1"') === -1, "a hand-started chat must not render here");
  T.S.sessions = prev; T.S.sgroup = pg; T.S.ui = T.loadLayout();
});
test("routines: a routine that never succeeded says so", () => {
  /* daily-leetcode-cp has 38 runs and 0 successes on the founder's machine and
     nothing in the app said so. A routine that has never worked must not look
     like one that merely fails sometimes. */
  T.S.ui = T.loadLayout();
  const prev = T.S.sessions, pg = T.S.sgroup;
  T.S.sgroup = "routines";
  T.S.sessions = [
    { id:"a", title:"x", real:true, loadState:"ok", turns:[], updated_ms:2,
      routine:{ routine:"always-broken", outcome:"failed" } },
    { id:"b", title:"y", real:true, loadState:"ok", turns:[], updated_ms:1,
      routine:{ routine:"mostly-fine", outcome:"ok" } },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(/never succeeded/.test(out), "a routine with zero successes must say so");
  assert(/rgfail all/.test(out), "and must be marked distinctly, not just counted");
  const fine = out.slice(out.indexOf("mostly-fine"));
  assert(!/never succeeded/.test(fine), "a working routine must not be labelled broken");
  T.S.sessions = prev; T.S.sgroup = pg; T.S.ui = T.loadLayout();
});
test("routines: with no runs recorded, it says that rather than rendering blank", () => {
  T.S.ui = T.loadLayout();
  const prev = T.S.sessions, pg = T.S.sgroup;
  T.S.sgroup = "routines";
  T.S.sessions = [];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(/No routine has recorded a run yet/.test(out), "an empty state must explain itself");
  T.S.sessions = prev; T.S.sgroup = pg; T.S.ui = T.loadLayout();
});

test("dept: collapse keys for departments that no longer exist are pruned", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([{ ref:"dref-live", name:"Live", parent_ref:null }]);
  T.S.ui.sessCollapsed = { "dept:dref-live":true, "dept:dref-gone":true,
                           "dept:__none__":true };
  T.S.sessions = [
    { id:"s-a", title:"a", real:true, loadState:"ok", turns:[], cwd:"/d/live",
      department:{ ref:"dref-live", name:"Live", cwd:"/d/live" }, updated_ms:1 },
  ];
  T.renderRail();
  assert(T.S.ui.sessCollapsed["dept:dref-live"] === true, "a live key must survive");
  assert(!("dept:dref-gone" in T.S.ui.sessCollapsed), "an orphaned key must be pruned");
  assert(T.S.ui.sessCollapsed["dept:__none__"] === true,
         "the catch-all names an absence, not a ref, and must never be pruned");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains);
  T.S.ui = T.loadLayout();
});
test("dept: an unloaded org tree prunes nothing", () => {
  /* With DOMAINS empty every key looks orphaned. Pruning then would discard
     the operator's real layout on any boot where the org fetch has not landed
     yet -- the failure would be silent and total. */
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup, prevDomains = getDomains();
  T.S.sgroup = "dept";
  setDomains([]);
  T.S.ui.sessCollapsed = { "dept:dref-a":true, "dept:dref-b":true };
  T.S.sessions = [
    { id:"s-a", title:"a", real:true, loadState:"ok", turns:[], cwd:"/d/x",
      department:{ ref:"dref-a", name:"A", cwd:"/d/x" }, updated_ms:1 },
  ];
  T.renderRail();
  assert(Object.keys(T.S.ui.sessCollapsed).length === 2,
         "nothing may be pruned while the tree is unknown");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
  setDomains(prevDomains);
  T.S.ui = T.loadLayout();
});
test("dept: a group whose ref left the registry does not swallow its chats", () => {
  T.S.ui = T.loadLayout();
  const prevSessions = T.S.sessions, prevGroup = T.S.sgroup;
  T.S.sgroup = "dept";
  /* byRef("dref-gone") returns nothing: the group cannot render, so the chat
     must fall through to the catch-all rather than disappear between the two */
  T.S.sessions = [
    { id:"s-orphan", title:"filed under a deleted domain", real:true, loadState:"ok",
      turns:[{ domain:{ ref:"dref-gone", name:"Gone" }, mode:"match" }], updated_ms:1 },
  ];
  T.renderRail();
  const out = T.document.getElementById("sessions").innerHTML;
  assert(out.indexOf('data-sid="s-orphan"') !== -1,
         "a chat whose department left the registry must still render");
  T.S.sessions = prevSessions; T.S.sgroup = prevGroup;
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
  /* The footer asks providerUsage(), which since 2026-09-07 resolves WHICH KIND
     of usage fact the selected provider reports before reading any state --
     otherwise the line quoted Anthropic's percentage whatever was selected. So
     the fixture has to name a provider and a kind, the way the live panel does
     from GET /api/providers. */
  const prevP = T.PROVIDERS, prevS = T.SETTINGS;
  T.PROVIDERS = [{ id: "claude", name: "Claude Code", usage_kind: "window-percent" }];
  T.SETTINGS = Object.assign({}, T.SETTINGS, { provider: "claude" });
  try {
    T.S.usage = null; T.paintTelemetry();
    assert.strictEqual(els["idStat"].textContent, "—");
    T.S.usage = { available: true, limits: [{ active: true, percent: 63.4 }] };
    T.paintTelemetry();
    assert.strictEqual(els["idStat"].textContent, "63% of the usage window");
  } finally { T.S.usage = null; T.PROVIDERS = prevP; T.SETTINGS = prevS; }
});

test("telemetry: withholds rather than guesses when the provider table is unread", () => {
  /* DELIBERATE, not a gap. With no provider table there is no way to know
     whether this assistant reports a window, a balance, or nothing -- and the
     failure this whole change fixes was a surface asserting a number it had no
     basis for. An em-dash is the honest output; the figure appears when the
     table arrives. */
  const prevP = T.PROVIDERS;
  T.PROVIDERS = [];
  T.S.usage = { available: true, limits: [{ active: true, percent: 63.4 }] };
  try {
    T.paintTelemetry();
    assert.strictEqual(els["idStat"].textContent, "—");
  } finally { T.S.usage = null; T.PROVIDERS = prevP; }
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
  /* The rail track is var(--railw,224px) since 2.259.0, when the sidebar became draggable
     (owner: "click on the centre and slide left to collapse it like I have it in VS Code").
     224px stays the DEFAULT inside the var, so a browser with nothing stored, or one that
     refuses localStorage, lays out exactly as it did before. */
  const three = css.indexOf(".app.threecol{grid-template-columns:var(--railw,224px) 240px");
  /* The collapsed grid leads with the PLANE's 240px now, not minmax(0,1fr): collapsing hides
     the nav and keeps the Chats list (2026-09-10). See the assertions further down. */
  const col = css.indexOf(".app.threecol.railcol{grid-template-columns:240px minmax(0,1fr)");
  assert(three !== -1 && col !== -1, "both grid rules must exist");
  assert(col > three, "the railcol override must come AFTER threecol, or it loses the cascade");
  /* THIS ASSERTION WAS REVERSED ON 2026-09-10, DELIBERATELY. It used to demand that collapsing
     hide BOTH lanes, because hiding only the rail once caused an overlap: the 4-track grid was
     left intact, so the plane slid into the rail's track and the detail crammed into the
     plane's. The owner then asked for the opposite -- "I only want the Sutra thing to get
     collapsed, not the chat one" -- so the blunt rule had to go.

     The overlap is now prevented properly, by dropping a TRACK rather than hiding a lane, and
     that is what the next three assertions check. Do not restore the old rule: it would take
     the Chats list with it again. */
  assert(css.indexOf(".app.threecol.railcol .rail{display:none}") !== -1,
    "collapsed hides the Sutra nav");
  assert(css.indexOf(".app.threecol.railcol .plane{display:none}") === -1,
    "collapsed must NOT hide the plane — that is the Chats list the owner keeps");
  /* The anti-overlap invariant: one lane hidden, one track fewer. Four tracks with three lanes
     is exactly the state that caused the original bug. */
  const railcolGrid = /\.app\.threecol\.railcol\{grid-template-columns:([^;}]+)/.exec(css);
  assert(railcolGrid, "the collapsed threecol grid must be declared");
  const railcolTracks = railcolGrid[1].trim().split(/\s+(?![^(]*\))/).length;
  assert(railcolTracks === 3,
    "collapsed threecol must declare exactly 3 tracks (plane|detail|term), saw " + railcolTracks +
    " — a 4-track grid with the rail hidden IS the overlap bug");
  assert(/\.app\.threecol\.railcol\.noplane\{grid-template-columns:minmax\(0,1fr\) var\(--termw/.test(css),
    "a plane-less destination collapses to 2 tracks, or it keeps an empty 240px gutter");
  /* Every rail track carries the same fallback. One that hardcoded 224px would ignore a drag
     on that layout only, which is the kind of bug you find by resizing on a settings screen. */
  const tracks = css.match(/grid-template-columns:[^;}]*224px[^;}]*/g) || [];
  tracks.forEach(t => assert(t.indexOf("var(--railw,224px)") !== -1,
    "a rail track still hardcodes 224px and would not answer the drag: " + t));
  assert(tracks.length >= 3, "expected the three rail-bearing grids, saw " + tracks.length);
});

test("2.259.0: the sidebar drag edge exists, and collapsed it is still reachable", () => {
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
  const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
  assert(/id="railDrag"/.test(html), "the drag edge is in the markup");
  assert(/role="separator"/.test(html) && /tabindex="0"/.test(html),
    "it is a separator and it is reachable by keyboard, not mouse-only");
  assert(css.indexOf(".raildrag{position:absolute") !== -1, "it is out of flow, claiming no grid track");
  assert(css.indexOf(".app{display:grid;position:relative;") !== -1,
    ".app must be the positioning context, or the edge resolves against the page");

  /* THE ONE THAT MATTERS, and it is STRUCTURAL, not a style. Collapsed, `.app.railcol .rail`
     is display:none. A child of a display:none parent is not rendered whatever position it
     carries -- position:fixed does not rescue it -- so an edge written inside <nav class="rail">
     disappears at exactly the moment you need it to drag the sidebar back. Caught by driving
     the real gesture in a browser on 2026-09-10; the DOM order is the fix. */
  const nav = html.indexOf("</nav>");
  const edge = html.indexOf('id="railDrag"');
  assert(nav !== -1 && edge !== -1, "both the rail and the edge must be in the markup");
  assert(edge > nav,
    "the drag edge must be a SIBLING of .rail, after </nav> — inside it, display:none takes it too");
  assert(css.indexOf(".app.railcol .raildrag{left:0") !== -1,
    "collapsed, the edge pins to the window's left edge so there is still something to grab");
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
  /* Usage lost its nav row on 2026-09-03 and is reached by being RENDERED
     INSIDE the AI Provider screen -- a stronger form of reachable than a row,
     since you arrive at it while answering the question that raised it. Same
     shape of claim as knowledge/files above, so it is asserted the same way:
     at the source level, that SCREENS.settings actually calls SCREENS.usage. */
  assert(/SCREENS\.usage\(\)/.test(String(T.SCREENS.settings)),
         "usage has no nav row AND is not rendered inside the AI Provider "
         + "screen -- it would be orphaned");
  reachable.add("usage");
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

test("identity: no company name is hardcoded in the role list", () => {
  /* The regression. ROLES was the literal pair "CEO of Asawa Inc." / "CEO of
     Sutra" -- the founder's own companies -- so every operator who installed
     Sutra was offered someone else's identity to act under. */
  const src = JS("07-loaders.js");
  const roleBlock = src.slice(src.indexOf('const KEY = "sutra.panel.role"'),
                              src.indexOf("globalThis.panelRole"));
  assert(roleBlock.length > 200, "the identity block must be findable");
  assert(!/name:\s*"CEO of (Asawa|Sutra)/.test(roleBlock),
    "a company name is hardcoded in the role list");
  assert(/"CEO of "\s*\+\s*org/.test(roleBlock),
    "the role must be composed from the registry root, not declared");
});
test("identity: the role reads the company off the registry root", () => {
  const prevDomains = getDomains();
  setDomains([{ ref:"r", parent_ref:null, name:"Acme Ltd" },
              { ref:"c", parent_ref:"r", name:"Child" }]);
  assert.strictEqual(vm.runInContext("panelRole()", sandbox), "CEO of Acme Ltd");
  /* Renaming the root renames the role -- one source of truth, not two. */
  setDomains([{ ref:"r", parent_ref:null, name:"Renamed Co" }]);
  assert.strictEqual(vm.runInContext("panelRole()", sandbox), "CEO of Renamed Co");
  setDomains(prevDomains);
});
test("identity: before the org loads the footer says so rather than inventing one", () => {
  /* paintRole runs at boot, BEFORE loadOrg. Showing a guessed company there
     would be a fact the operator never entered. */
  const prevDomains = getDomains();
  setDomains([]);
  const role = vm.runInContext("panelRole()", sandbox);
  assert(!/CEO of/.test(role), "no company may be claimed before the tree loads");
  assert(role.trim().length, "but the label must not be blank either");
  setDomains(prevDomains);
});
test("identity: a stored role naming a company that is gone is not shown", () => {
  /* How an operator upgrading from the hardcoded pair stops seeing
     "CEO of Asawa Inc." -- no migration step, the stale value simply loses. */
  const prevDomains = getDomains();
  setDomains([{ ref:"r", parent_ref:null, name:"Acme Ltd" }]);
  storage._m["sutra.panel.role"] = "CEO of Asawa Inc.";
  assert.strictEqual(vm.runInContext("panelRole()", sandbox), "CEO of Acme Ltd");
  delete storage._m["sutra.panel.role"];
  setDomains(prevDomains);
});
test("identity: the superseded role is cleared from storage, not just ignored", () => {
  /* Ignoring it leaves the old company's name sitting in the operator's
     storage forever -- the same dead-key problem the collapse map has. */
  const prevDomains = getDomains();
  setDomains([{ ref:"r", parent_ref:null, name:"Acme Ltd" }]);
  storage._m["sutra.panel.role"] = "CEO of Asawa Inc.";
  vm.runInContext("paintPanelRole()", sandbox);
  assert.strictEqual(storage.getItem("sutra.panel.role"), "CEO of Acme Ltd",
    "a superseded role must be rewritten, not left in place");
  delete storage._m["sutra.panel.role"];
  setDomains(prevDomains);
});
test("identity: a boot-time paint with no tree must not erase a stored role", () => {
  /* Before loadOrg every role looks stale. Rewriting then would destroy a
     legitimate choice on every cold start. */
  const prevDomains = getDomains();
  setDomains([]);
  storage._m["sutra.panel.role"] = "CEO of Acme Ltd";
  vm.runInContext("paintPanelRole()", sandbox);
  assert.strictEqual(storage.getItem("sutra.panel.role"), "CEO of Acme Ltd",
    "an unloaded tree must not rewrite stored state");
  delete storage._m["sutra.panel.role"];
  setDomains(prevDomains);
});
test("identity: loadOrg repaints the role once the company exists", () => {
  /* Without this the operator stares at the unset label for a whole session
     while the Org screen two panes away shows the company perfectly well. */
  const src = JS("07-loaders.js");
  const body = src.slice(src.indexOf("async function loadOrg()"),
                         src.indexOf("async function loadRuntime()"));
  assert(/paintPanelRole\(\)/.test(body),
    "loadOrg must repaint the identity footer when the tree lands");
});

test("only dept: collapse keys are adopted, stale project: ones are dropped", () => {
  /* sessCollapsed was retired on 2026-09-02 holding "project:<cwd>" keys and
     revived on 2026-09-08 holding "dept:<ref>". An old stored layout must not
     resurrect groups that no longer exist, so adoption is prefix-filtered --
     asserted against the source, the same way the plane-collapse key filter
     above is (localStorage is not shimmed in this harness). */
  const state = JS("01-state.js");
  assert(/k\.indexOf\("dept:"\) === 0/.test(state),
    "sessCollapsed must adopt only dept:-prefixed keys");
  assert(/sessCollapsed:\{\}/.test(state),
    "sessCollapsed must have a default so a first run has no undefined map");
});

test("sessions: the rail tops up to a bounded page in either scope", () => {
  /* A bound, not "all": the cost scales with the disk, and the operator this
     scope protects has 20,255 transcripts. */
  const src = JS("09-tail.js");
  assert(/SESSION_PAGE\s*=\s*100/.test(src), "first paint stays the small page");
  assert(/SESSION_PAGE_ALL\s*=\s*2000/.test(src), "the top-up is capped, not unbounded");
  const body = src.slice(src.indexOf("async function loadSessions()"),
                         src.indexOf("function refetchOrg"));
  /* Not gated on scope: routine runs count as Sutra's own chats, and a
     100-row first page hid every weekly routine behind one busy daily one. */
  assert(!/chat_scope === "all"/.test(body), "the top-up must run in both scopes");
  assert(/catch\s*\(/.test(body), "a failed top-up must leave the first page standing");
});


/* §2.226.0 — Focus + Org fold their plane into a rail accordion
   (founder 2026-08-25, design canvas 68c685b1; codex consult P1/P2 folds). */
test("inline: Focus and Org open with NO second plane; Settings still has one", () => {
  T.S.ui = T.loadLayout();
  T.goDest("focus"); T.renderRail();
  assert(els["app"]._cls.has("noplane"), "Focus must be planeless");
  assert.strictEqual(els["planeBody"].innerHTML, "", "hidden plane holds no rows");
  T.goDest("org"); T.renderRail();
  assert(els["app"]._cls.has("noplane"), "Org must be planeless");
  T.goDest("settings"); T.renderRail();
  assert(!els["app"]._cls.has("noplane"), "Settings keeps its plane");
  assert(els["planeBody"].innerHTML.indexOf('data-screen="terminal"') !== -1, "…and its rows");
  T.goDest("now");
});
test("inline: the terminal clamp treats Focus/Org as no-plane (codex P1)", () => {
  T.S.ui = T.loadLayout();
  els["app"]._cls.add("threecol");
  sandbox.innerWidth = 1400;
  T.goDest("org"); T.renderRail();
  assert.strictEqual(vm.runInContext("clampTermW(1008)", sandbox), 829, "org: 240px handed back");
  T.goDest("settings"); T.renderRail();
  assert.strictEqual(vm.runInContext("clampTermW(1008)", sandbox), 589, "settings: plane reserved");
  T.goDest("now");
});
test("inline: entering Org renders its rows inside the rail with the plane's markup", () => {
  T.S.ui = T.loadLayout();
  T.goDest("org");
  T.renderRail();
  const out = els["railnav"].innerHTML;
  assert.strictEqual((out.match(/data-dest="/g) || []).length, 7, "still seven destinations");
  assert(/data-dest="org"[^>]*data-open="true"/.test(out), "Org parent reads open");
  assert(/data-dest="org"[^>]*aria-expanded="true"/.test(out), "aria-expanded on the parent");
  assert(/aria-controls="acc-org"/.test(out) && /id="acc-org"/.test(out), "aria-controls wires the list");
  assert(/data-dest="org"[^>]*aria-current="false"/.test(out), "open parent yields the highlight");
  assert(/data-screen="departments"[^>]*aria-current="true"/.test(out), "the landed child carries it");
  assert(/data-screen="charters"/.test(out) && /data-screen="reorg"/.test(out), "rows come from DEST_PLANES");
  assert(/data-dest="focus"[^>]*data-open="false"/.test(out), "only one accordion open");
  assert(!/id="acc-focus"/.test(out), "closed accordion renders no list");
  T.goDest("now");
});
test("inline: Focus rows keep the soon marker; child rows never carry data-dest", () => {
  T.S.ui = T.loadLayout();
  T.goDest("focus");
  T.renderRail();
  const sub = (els["railnav"].innerHTML.split('id="acc-focus"')[1] || "").split("</ul>")[0];
  assert(sub.length > 0, "focus accordion rendered");
  assert(/class="dis">soon</.test(sub), "Daily brief keeps its honest soon");
  assert(!/data-dest=/.test(sub), "child rows are screen rows only (codex P1)");
  T.goDest("now");
});
test("inline: collapsed accordion hands the highlight back to the parent", () => {
  T.S.ui = T.loadLayout();
  T.goDest("focus");
  T.S.ui.railOpen = null;          /* what the rail click toggle does */
  T.renderRail();
  const out = els["railnav"].innerHTML;
  assert(/data-dest="focus"[^>]*aria-current="true"/.test(out), "parent current when folded");
  assert(!/id="acc-focus"/.test(out));
  assert.strictEqual(T.S.screen, "shadow", "the screen stayed open");
  T.goDest("now");
});
test("inline: a remembered pick still routes; leaving closes the accordion (codex P2)", () => {
  T.S.ui = T.loadLayout();
  T.S.ui.destSel.org = "charters";
  T.goDest("org");
  assert.strictEqual(T.S.screen, "charters", "destSel still outranks the default");
  assert.strictEqual(T.S.ui.railOpen, "org");
  T.goDest("settings");
  assert.strictEqual(T.S.ui.railOpen, null, "no stale open section");
  T.goDest("now");
});
test("inline: stored railOpen is adopted only for the current inline dest", () => {
  sandbox.localStorage.setItem("sutra.panel.layout", JSON.stringify({ dest:"settings", railOpen:"org" }));
  assert.strictEqual(T.loadLayout().railOpen, null, "stale slot dropped");
  sandbox.localStorage.setItem("sutra.panel.layout", JSON.stringify({ dest:"org", railOpen:"org" }));
  assert.strictEqual(T.loadLayout().railOpen, "org", "matching slot kept");
  sandbox.localStorage.removeItem("sutra.panel.layout");
});

console.log("-".repeat(60));
console.log(`v3.3 shell: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
