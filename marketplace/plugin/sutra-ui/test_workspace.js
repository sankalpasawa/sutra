#!/usr/bin/env node
/*
 * test_workspace.js -- unit + wiring tests for the Workspace screen
 * (static/js/13-workspace.js, PLAN-100 S76/S81).
 *
 * WHY THIS EXISTS
 * ---------------
 * The Workspace screen is a 14-state machine (STATE-MACHINE.md) gated by a
 * feature flag (FLAG.md) whose OFF position must be a ZERO-behaviour change.
 * Three failure classes the Python suite can never see:
 *
 *   - the flag gate living only in one code path, so a delegate or loader
 *     still acts with the flag off (the inertness contract broken silently);
 *   - a typed error kind rendering the wrong design state -- ERROR-MODEL.md
 *     maps engine_down/not_found/mismatch/registry_empty to states 13/14/12/08
 *     and the frontend must switch on KIND, never HTTP status;
 *   - a new URL builder sneaking in beside sbUrl/sbPageFromPath -- the audit's
 *     "no new URL builders anywhere" rule (ARCH.md S34).
 *
 * HOW
 * ---
 * Source-level assertions on the real bytes (the connectors-suite pattern),
 * plus a vm sandbox that evals 13-workspace.js ALONE with a minimal stub of
 * the globals it consumes -- and with sbPageFromPath/sbUrl extracted from the
 * REAL 02-helpers.js, so the validator under test is the shipped one, not a
 * copy that can drift.
 *
 * Run: node test_workspace.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = p => fs.readFileSync(path.join(__dirname, "static/js", p), "utf8");
const source = JS("13-workspace.js");
const helpers = JS("02-helpers.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static/panel.html"), "utf8");

let pass = 0, fail = 0, skip = 0;
function test(name, fn){
  try { fn(); console.log("ok   - " + name); pass++; }
  catch (e){ console.log("FAIL - " + name + "\n       " + (e && e.message || e)); fail++; }
}
function skipped(name, why){ console.log("skip - " + name + " (" + why + ")"); skip++; }
function assert(cond, msg){ if (!cond) throw new Error(msg); }

/* ══════════════════ 1. source-level wiring ══════════════════ */

if (/13-workspace\.js/.test(panelHtml)){
  test("13-workspace.js loads before 09-tail.js", () => {
    const tag = f => panelHtml.indexOf('<script src="/static/js/' + f);
    assert(tag("13-workspace.js") < tag("09-tail.js"),
      "load order would leave the screen undefined at boot (09-tail ends with boot())");
  });
} else {
  /* Integration (S72) adds the tag; before that the module must simply not be
     loaded -- which is its own kind of inertness. */
  skipped("13-workspace.js is loaded by panel.html", "panel.html not yet integrated -- S72");
}

test("no new URL builder; sbPageFromPath is the one validator (r5: sbUrl gone)", () => {
  assert(!/127\.0\.0\.1/.test(source),
    "a loopback literal in 13-workspace.js means a URL was built by hand");
  assert(!/new URL\(/.test(source), "no URL construction in the workspace module");
  assert(/sbPageFromPath\(/.test(source), "the shipped validator must be the one called");
  assert(!/sbUrl\(/.test(source), "sbUrl died with the sidecar — nothing may rebuild frame URLs");
  assert(!/function sbPageFromPath|function sbUrl/.test(source),
    "13-workspace.js must not redefine the validators -- reuse, not a copy");
});

test("no iframe surface at all (r5): the wsframe hook and its wiring are gone", () => {
  assert(!/<iframe/.test(source), "no iframe markup anywhere in the workspace module");
  assert(!/frame\.src/.test(source), "no frame src assignment survives the sidecar");
});

test("the click delegate is document-level and scoped to #scBody", () => {
  assert(/document\.addEventListener\(\s*["']click["']/.test(source),
    "no document-level click delegate -- per-render bindings die with #scBody");
  assert(/closest\(["']#scBody["']\)/.test(source),
    "delegate unscoped; a stray data-ws* attribute anywhere would trigger it");
  assert(!/getElementById\(["']scBody["']\)\.addEventListener/.test(source),
    "a listener bound to #scBody would not survive a re-render");
});

test("every delegated guard leads with the flag/screen predicate", () => {
  /* The inertness contract at the source level: each document/window listener
     body must consult wsActive()/wsFlagOn() before doing anything. */
  const starts = [];
  const re = /(?:document|window)\.addEventListener\(/g;
  let m; while ((m = re.exec(source))) starts.push(m.index);
  assert(starts.length >= 3, "expected click + keydown + focus listeners");
  for (const at of starts){
    const body = source.slice(at, at + 300);
    assert(/wsActive\(\)|wsFlagOn\(\)|wsKeydown/.test(body),
      "a listener without the flag guard acts with the flag off:\n" + body.slice(0, 120));
  }
  /* wsKeydown is registered by name; its body must carry the same guard. */
  assert(/function wsKeydown\(e\)\{\n  if \(!wsActive\(\)\) return;/.test(source),
    "wsKeydown must refuse before reading a single key");
});

/* ══════════════════ 2. vm sandbox over the real module ══════════════════ */

/* The REAL validators, extracted from 02-helpers.js so the bytes under test
   are the shipped ones. Both sbPageFromPath definitions are taken in file
   order -- the second wins at eval, exactly as in the browser. */
const validatorSrc = (helpers.match(/^function sbPageFromPath\([\s\S]*?^\}/gm) || []).join("\n");
assert(/sbPageFromPath/.test(validatorSrc),
  "could not extract the shipped validator from 02-helpers.js");

function makeNode(){
  return {
    tagName: "DIV", innerHTML: "", textContent: "", value: "", dataset: {},
    focus(){}, closest(){ return null; },
    querySelector(){ return null; }, querySelectorAll(){ return []; },
  };
}

function freshSandbox(){
  const sb = {
    console, Date, Math, JSON, Promise, Object, Array, String, Number, Boolean,
    RegExp, Error, Set, Map, encodeURIComponent, decodeURIComponent,
    /* fake timers: the 150ms debounce is driven by hand */
    _timers: [],
    setTimeout(fn, ms){ sb._timers.push({ fn, ms, dead:false }); return sb._timers.length; },
    clearTimeout(id){ const t = sb._timers[id-1]; if (t) t.dead = true; },
    fireTimers(){ const run = sb._timers.splice(0); run.forEach(t => { if (!t.dead) t.fn(); }); },
    /* the app globals the module consumes */
    API: "",
    S: { screen: "departments", ui: {} },
    SETTINGS: null,
    SCREENS: {}, TITLES: {},
    esc: s => String(s == null ? "" : s).replace(/[&<>"]/g,
      m => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[m])),
    renders: 0,
    render(){ sb.renders++; },
    fetchCalls: [],
    /* default: parks forever, the test_panel.js idiom -- no continuation may
       outlive an assertion. Tests that need a response override fetchImpl. */
    fetchImpl: () => new Promise(() => {}),
    fetch(url, opts){ sb.fetchCalls.push(url); return sb.fetchImpl(url, opts); },
    posts: [],
    apiGet: async p => { sb.fetchCalls.push(p); return sb.fetchImpl(p).then(r => r.json()); },
    apiPost: async (p, b) => { sb.posts.push({ path: p, body: b }); return {}; },
    loadFilesScreen(){ sb.sbStarts = (sb.sbStarts || 0) + 1; },
    loadFs(){ sb.fsLoads = (sb.fsLoads || 0) + 1; },
    handlers: {},
    document: {
      addEventListener(type, fn){ sb.handlers[type] = fn; },
      querySelector(){ return null; },
      getElementById(){ return makeNode(); },
      activeElement: null,
    },
  };
  sb.window = sb;
  sb.addEventListener = (type, fn) => { sb.handlers["window:" + type] = fn; };
  sb.globalThis = sb;
  vm.createContext(sb);
  const EPILOGUE = `
;globalThis.__W = { wsFlagOn, wsActive, wsEnsureRegistered, loadWorkspace,
  wsCurrentState, wsStateFromError, wsGroupResults, wsMarkSnippet,
  wsSearchInput, wsVisibleRows, wsActivateRow, wsKeydown, wsParseRoute,
  wsOpenDoc, wsSetLens, wsEdit, wsKeepMine, wireWorkspace, wsUnmountEditor,
  wsScreenHtml, WS_COPY, wsMatchWords, wsCount, wsTreeHtml, wsMdHtml,
  wsPaneHeadHtml, wsFileIt, wsFolderRows, wsFoldersHtml };
`;
  new vm.Script(validatorSrc + "\n" + source + EPILOGUE,
    { filename: "13-workspace.js#test" }).runInContext(sb);
  return sb;
}

/* a small filed tree + one unfiled doc */
const TREE = {
  departments: [{ ref: "D3", name: "Sutra OS", count: 2, charters: [
    { id: "C-9be2f1", title: "Engine Library", docs: [
      { path: "holding/research/viewer.md", title: "Obsidian-like file viewer", mtime: 1756022400, missing: false },
      { path: "holding/research/gone.md", title: "Ghost", mtime: 1756020000, missing: true },
    ]}]}],
  unfiled: [{ path: "holding/TODO.md", title: "TODO", mtime: 1756020000 }],
  doc_rows: 3, truncated: false, generated_at: 1756025000,
};
const EMPTY_TREE = { departments: [], unfiled: [], doc_rows: 0, truncated: false, generated_at: 0 };

/* ── flag-off inertness ─────────────────────────────────────────────────── */

test("flag off (explicit false): nothing registers, nothing fetches, nothing reacts", () => {
  /* S92 cutover inverted the default: absent means ON. The inert contract is
     unchanged, it just hangs off the EXPLICIT false now (FLAG.md rollback). */
  const sb = freshSandbox();
  sb.SETTINGS = { flags: { workspace: false } };
  const W = sb.__W;
  assert(W.wsFlagOn() === false, "explicit false must read as flag OFF");
  W.wsEnsureRegistered();
  assert(sb.SCREENS.workspace === undefined, "SCREENS.workspace registered with the flag off");
  assert(sb.TITLES.workspace === undefined, "TITLES.workspace registered with the flag off");
  W.loadWorkspace(true);
  assert(sb.fetchCalls.length === 0, "loadWorkspace fetched with the flag off");
  /* the delegates see events and must do nothing */
  const before = JSON.stringify(sb.S.ws.sel);
  sb.handlers.click({ target: { closest: () => ({ dataset: { wstype: "doc", wskey: "holding/TODO.md" } }) } });
  sb.handlers.keydown({ key: "ArrowDown", target: null, preventDefault(){} });
  sb.handlers["window:focus"]();
  assert(JSON.stringify(sb.S.ws.sel) === before && sb.fetchCalls.length === 0,
    "a delegate acted with the flag off");
  assert(sb.posts.length === 0, "telemetry pinged with the flag off");
});

test("S92 default-on: absent means ON; only explicit false turns it off", () => {
  /* Post-cutover the Workspace is the default surface, so the predicate
     FAILS OPEN: absent settings, absent flags, junk values all read ON.
     The server's sanitize only ships booleans, so the client never sees
     junk in practice; explicit false is the one recorded off-switch. */
  const sb = freshSandbox();
  assert(sb.__W.wsFlagOn() === true, "absent SETTINGS reads ON after cutover");
  sb.SETTINGS = { flags: {} };
  assert(sb.__W.wsFlagOn() === true, "absent flag key reads ON");
  sb.SETTINGS = { flags: { workspace: true } };
  assert(sb.__W.wsFlagOn() === true, "literal true reads ON");
  sb.SETTINGS = { flags: { workspace: false } };
  assert(sb.__W.wsFlagOn() === false, "explicit false is the off-switch");
});

test("flag on: registration adds BOTH the SCREENS and the TITLES row", () => {
  const sb = freshSandbox();
  sb.SETTINGS = { flags: { workspace: true } };
  sb.__W.wsEnsureRegistered();
  assert(typeof sb.SCREENS.workspace === "function", "SCREENS.workspace missing");
  assert(Array.isArray(sb.TITLES.workspace) && sb.TITLES.workspace[0] === "Workspace",
    "TITLES.workspace missing -- render() would TypeError, not blank-header");
});

/* ── the 14-state resolver ──────────────────────────────────────────────── */

function onSandbox(mut){
  const sb = freshSandbox();
  sb.SETTINGS = { flags: { workspace: true } };
  sb.S.screen = "workspace";
  sb.S.ws.loaded = true; sb.S.ws.tree = TREE;
  if (mut) mut(sb);
  return sb;
}

test("state resolver walks all 14 states", () => {
  const at = mut => onSandbox(mut).__W.wsCurrentState();
  assert(at(sb => { sb.S.ws.loaded = false; sb.S.ws.tree = null; sb.S.ws.loading = true; }) === "10", "loading -> 10");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; }) === "01", "filed doc -> 01");
  assert(at(sb => { sb.S.ws.sel = { type:"charter", id:"C-9be2f1" }; }) === "02", "charter -> 02");
  assert(at(sb => { sb.S.ws.results = { documents:[{}], records:[], counts:{documents:1, records:0} }; }) === "03", "results -> 03");
  assert(at(sb => {
    sb.S.ws.results = { documents:[], records:[{}], counts:{documents:0, records:1} };
    sb.S.ws.sel = { type:"charter", id:"C-9be2f1" }; sb.S.ws.matched = ["purpose"];
  }) === "04", "record selected -> 04");
  assert(at(sb => { sb.S.ws.lens = "folders"; }) === "05", "folders lens -> 05");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/TODO.md" }; }) === "06", "unfiled doc -> 06");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; sb.S.ws.editing = true; sb.S.ws.unsaved = true; }) === "07", "editing -> 07");
  assert(at(sb => { sb.S.ws.tree = EMPTY_TREE; }) === "08", "empty registry + no unfiled -> 08");
  assert(at(sb => { sb.S.ws.results = { documents:[], records:[], counts:{documents:0, records:0} }; }) === "09", "zero hits -> 09");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" };
    sb.S.ws.lastRead = { path:"holding/research/viewer.md", text:"b", editable:false }; }) === "11",
    "edit gate off (fs-read editable:false) -> 11 (r5: S.sb is gone)");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; sb.S.ws.editing = true; sb.S.ws.unsaved = true; sb.S.ws.changed = true; }) === "12", "external write -> 12");
  assert(at(sb => { sb.S.ws.treeError = { kind:"engine_down", message:"x" }; }) === "13", "engine_down -> 13");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; sb.S.ws.docGone = true; }) === "14", "doc gone -> 14");
});

test("error kinds map to states; unknown kind fails safe to F1", () => {
  const W = freshSandbox().__W;
  assert(W.wsStateFromError("engine_down") === "13", "engine_down -> 13");
  assert(W.wsStateFromError("not_found") === "14", "not_found -> 14");
  assert(W.wsStateFromError("mismatch") === "12", "mismatch -> 12");
  assert(W.wsStateFromError("registry_empty") === "08", "registry_empty -> 08");
  assert(W.wsStateFromError("someday_new_kind") === "13",
    "an unrecognized kind must render F1's copy (ERROR-MODEL fail-safe)");
});

/* ── grouping ───────────────────────────────────────────────────────────── */

test("search grouping: documents first, records second, total pre-cap", () => {
  const W = freshSandbox().__W;
  const g = W.wsGroupResults({
    documents: [{ path: "a.md", title: "A" }],
    records: [{ kind: "charter", ref: "C-1", title: "R" }],
    counts: { documents: 12, records: 4 }, truncated: true,
  });
  assert(g.docs.length === 1 && g.records.length === 1, "groups lost rows");
  assert(g.total === 16, "top-bar count must be the TOTAL pre-cap (SC7), got " + g.total);
  assert(g.truncated === true, "truncated flag dropped");
});

test("null filing renders as Unfiled in the result row", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.results = { documents: [{ path: "x.md", title: "X",
      filing: { department: null, charter: null },
      snippet: { text: "plain", ranges: [] } }],
      records: [], counts: { documents: 1, records: 0 } };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("Unfiled") !== -1, "a doc with null filing must read Unfiled");
});

/* ── snippet marking ────────────────────────────────────────────────────── */

test("snippet marks by code points and escapes everything", () => {
  const W = freshSandbox().__W;
  /* '𝒳' is one code point, two UTF-16 units: an index-based wrap would land
     the mark one unit late. Code points of "𝒳<a b>" are [𝒳 < a ␣ b >], so
     range [4,5) covers exactly 'b'. */
  const html = W.wsMarkSnippet("𝒳<a b>", [[4, 5]]);
  assert(html === "𝒳&lt;a <mark>b</mark>&gt;",
    "expected code-point-aware escape+mark, got: " + html);
});

test("no markup crosses from a hostile snippet", () => {
  const W = freshSandbox().__W;
  const html = W.wsMarkSnippet("<script>x</script>", [[0, 3]]);
  assert(html.indexOf("<script") === -1, "server text reached innerHTML unescaped");
  assert(/<mark>/.test(html), "the mark itself must still be authored");
});

/* ── search behaviour ───────────────────────────────────────────────────── */

test("search debounces to one fetch and pings once per episode", () => {
  const sb = onSandbox();
  const W = sb.__W;
  sb.fetchImpl = () => new Promise(() => {});
  W.wsSearchInput("o");
  W.wsSearchInput("ob");
  assert(sb.posts.filter(p => (p.body || {}).event === "search_used").length === 1,
    "search_used must fire once per episode, not per keystroke");
  sb.fireTimers();
  assert(sb.fetchCalls.filter(u => u.indexOf("/api/workspace/search") === 0).length === 1,
    "debounce must collapse two keystrokes into one fetch");
});

test("clearing the query closes search and resets the episode", () => {
  const sb = onSandbox();
  sb.S.ws.results = { documents: [], records: [], counts: {} };
  sb.S.ws.q = "x"; sb.S.ws.searchEpisode = true;
  sb.__W.wsSearchInput("");
  assert(sb.S.ws.results === null && sb.S.ws.q === "" && sb.S.ws.searchEpisode === false,
    "empty query must close search (SC9) and re-arm the episode counter");
});

/* ── validator reuse, functionally ──────────────────────────────────────── */

test("wsOpenDoc refuses what the shipped validator refuses", () => {
  const sb = onSandbox();
  for (const bad of ["../secret.md", "/etc/hosts", "a\\b.md", "notes.txt", "x:y.md"]){
    sb.__W.wsOpenDoc(bad, {});
    assert(sb.S.ws.sel === null, "wsOpenDoc accepted " + bad);
  }
  assert(sb.fetchCalls.length === 0, "a rejected path still cost a fetch");
});

test("deep-link parse: precedence fields, one decode, rejects per grammar", () => {
  const W = freshSandbox().__W;
  const p = W.wsParseRoute("workspace?doc=holding%2Fresearch%2Fviewer.md&charter=C-9be2f1&dept=D3&mystery=1");
  assert(p.doc === "holding/research/viewer.md", "doc must decode exactly once");
  assert(p.charter === "C-9be2f1" && p.dept === "D3", "co-present params must survive");
  assert(p.bad === null, "unknown params are ignored, never an error");
  assert(W.wsParseRoute("workspace?doc=../secret.md").bad, "traversal must be rejected");
  assert(W.wsParseRoute("workspace?doc=%2Fetc%2Fhosts").bad, "absolute must be rejected");
  assert(W.wsParseRoute("workspace?charter=Cx").bad, "charter shape must be C-<hex>");
  assert(W.wsParseRoute("elsewhere?doc=a.md").bad, "not a workspace route");
});

/* ── keyboard ───────────────────────────────────────────────────────────── */

test("visible rows mirror the collapsed tree exactly (codex finding 5)", () => {
  /* No selection: every dept row + Unfiled row, NOTHING expanded — the cursor
     must never land on a row the renderer did not draw. */
  const sb = onSandbox();
  assert(sb.__W.wsVisibleRows().map(r => r.type).join(",") === "dept,dept",
    "collapsed default must expose only dept rows");
  /* Selecting a filed doc expands its dept + charter + that charter's docs. */
  const sb2 = onSandbox(x => { x.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; });
  const shape = sb2.__W.wsVisibleRows().map(r => r.type).join(",");
  assert(shape === "dept,charter,doc,doc,dept",
    "active path traversal broken: " + shape);
  assert(sb2.__W.wsVisibleRows()[3].gone === true,
    "a missing doc stays LISTED (struck), never dropped");
  /* The renderer and the cursor use ONE predicate: what wsTreeHtml draws as
     buttons equals what wsVisibleRows returns, row for row. */
  const html = sb2.__W.wsTreeHtml();
  const drawn = (html.match(/data-wstype="(dept|charter|doc)"/g) || []).length;
  assert(drawn === sb2.__W.wsVisibleRows().length,
    "renderer drew " + drawn + " rows, cursor walks " + sb2.__W.wsVisibleRows().length);
});

test("a 15+ doc charter caps at 14 with an honest more-row (reviewer finding 4)", () => {
  const docs = [];
  for (let i = 0; i < 30; i++) docs.push({ path: "d/" + i + ".md", title: "Doc " + i, mtime: i });
  const sb = onSandbox(x => {
    x.S.ws.tree = { departments: [{ ref: "D9", name: "Big", count: 30, charters: [
      { id: "C-big", title: "Huge", docs } ] }], unfiled: [] };
    x.S.ws.sel = { type: "doc", path: "d/29.md" };   /* selected doc beyond the cap */
  });
  const html = sb.__W.wsTreeHtml();
  const drawnDocs = (html.match(/data-wstype="doc"/g) || []).length;
  assert(drawnDocs === 15, "cap draws 14 + the selected doc, got " + drawnDocs);
  assert(/ws-more/.test(html), "the more-row must exist");
  assert(/15 more/.test(html), "the more-row names the hidden count");
  sb.__W.wsActivateRow({ type: "more", key: "C-big" });
  assert(sb.S.ws.showAllDocs === "C-big", "activating the more-row lifts the cap");
});

test("Enter on a department toggles its expansion (founder 2026-08-25)", () => {
  /* Departments have no page; activate = expand/collapse. Collapsed is the
     DEFAULT for every dept outside the active selection path, so the first
     activation of an inactive dept must record open=true, the second false. */
  const sb = onSandbox();
  sb.__W.wsActivateRow({ type: "dept", key: "D3" });
  assert(sb.S.ws.openDeps && sb.S.ws.openDeps["D3"] === true,
    "first activation of a collapsed dept must expand it");
  sb.__W.wsActivateRow({ type: "dept", key: "D3" });
  assert(sb.S.ws.openDeps["D3"] === false,
    "second activation must collapse it again");
});

test("the tree collapses to counts by default; only the active path expands", () => {
  /* Mock 01: inactive departments render one row + count; the selected doc's
     department expands, and docs list only under the charter holding it. */
  const sb = onSandbox();
  const html = sb.__W.wsTreeHtml();
  const chaCount = (html.match(/ws-cha/g) || []).length;
  const sel = sb.S.ws.sel;
  if (sel){
    assert(chaCount > 0, "the active department must show its charters");
  }
  const depButtons = (html.match(/class="ws-dep/g) || []).length;
  assert(depButtons >= 1, "departments render as rows");
  assert(/ws-count/.test(html), "collapsed rows carry counts");
});

test("Esc clears search; a selected charter page survives (04 -> 02)", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.q = "x";
    sb2.S.ws.results = { documents: [], records: [], counts: {} };
    sb2.S.ws.sel = { type: "charter", id: "C-9be2f1" };
    sb2.S.ws.matched = ["purpose"];
  });
  sb.handlers.keydown({ key: "Escape", target: null, preventDefault(){} });
  assert(sb.S.ws.q === "" && sb.S.ws.results === null, "Esc must close search");
  assert(sb.S.ws.sel && sb.S.ws.sel.type === "charter",
    "Esc from a record view keeps the charter page (STATE-MACHINE 04 -> 02)");
});

test("arrows traverse; the cursor clamps at both ends", () => {
  const sb = onSandbox();
  const kd = key => sb.handlers.keydown({ key, target: null, preventDefault(){} });
  kd("ArrowDown");
  assert(sb.S.ws.cursor.i === 0, "first Down lands on row 0");
  for (let i = 0; i < 20; i++) kd("ArrowDown");
  assert(sb.S.ws.cursor.i === sb.__W.wsVisibleRows().length - 1, "cursor must clamp at the end");
  for (let i = 0; i < 40; i++) kd("ArrowUp");
  assert(sb.S.ws.cursor.i === 0, "cursor must clamp at the start");
});

/* ── error-state rendering (S81: every typed error renders its state) ───── */

test("state 13 renders survival copy, Try again, and the offline chip", () => {
  const sb = onSandbox(sb2 => { sb2.S.ws.treeError = { kind: "engine_down", message: "x" }; });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf(sb.__W.WS_COPY.engineDown) !== -1, "state-13 message missing");
  assert(html.indexOf(">Try again<") !== -1, "Try again action missing");
  /* r3: the chip cluster lives in the pane head now */
  assert(sb.__W.wsPaneHeadHtml().indexOf(">offline<") !== -1,
    "the offline chip MUST co-render with the message or cause is lost (COPY.md audit)");
});

test("state 08 renders the forward path", () => {
  const sb = onSandbox(sb2 => { sb2.S.ws.tree = EMPTY_TREE; });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf(sb.__W.WS_COPY.emptyMsg) !== -1, "empty message missing");
  assert(html.indexOf(">New document<") !== -1, "New document action missing");
});

test("state 09 names the full scope searched", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.q = "quarterly forecast";
    sb2.S.ws.results = { documents: [], records: [], counts: { documents: 0, records: 0 } };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("No document, charter or department contains that.") !== -1,
    "state-09 message must name all three levels");
});

test("state 12 renders the alert notice with both exits", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.editing = true; sb2.S.ws.unsaved = true; sb2.S.ws.changed = true;
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("Sutra changed this file while you had it open.") !== -1, "notice missing");
  assert(html.indexOf(">Reload<") !== -1 && html.indexOf(">Keep mine<") !== -1,
    "both exits must be offered -- neither copy is ever silently chosen");
  assert(html.indexOf("unsaved") !== -1, "the crumb must still say unsaved");
});

test("state 14 keeps the last read copy on screen and offers Save a copy", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.docGone = true;
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: true };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("This document is no longer there. Your last read copy is on screen.") !== -1,
    "state-14 message missing");
  assert(html.indexOf(">Save a copy<") !== -1, "Save a copy missing");
  /* The read view renders lastRead directly — a STRONGER guarantee than the
     old iframe (which cannot display a deleted file at all). The rendered
     body must be on screen; the editor frame must NOT mount in read state. */
  assert(html.indexOf("ws-read") !== -1 && html.indexOf("body") !== -1,
    "the rendered last-read copy must stay on screen");
  assert(html.indexOf("data-wsframe") === -1,
    "the editor iframe must not mount in the read state");
});

/* NOTE (default-edit, 2026-08-25): a plain explicit open now lands in EDIT —
   the read state below is reached via Done / restore / fromSearch / read-only
   / unfiled / gone, so this render pin stays valid. */
test("read state renders the panel view; edit state mounts the iframe (round 3)", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md",
      text: "# Title From Doc\n\nBody **bold** text\n\n- item", editable: true };
  });
  let html = sb.__W.wsScreenHtml();
  assert(html.indexOf("ws-doctitle") !== -1 && html.indexOf("Title From Doc") !== -1,
    "read state must show the serif doc title");
  assert(html.indexOf("<strong>bold</strong>") !== -1, "markdown must render");
  assert(html.indexOf("data-wsframe") === -1, "no iframe in read state");
  sb.S.ws.editing = true;
  html = sb.__W.wsScreenHtml();
  /* PLAN-25-EDITOR S11/S14: edit mode renders the NATIVE editor container;
     no iframe exists anywhere in the workspace surface anymore. */
  assert(html.indexOf("data-wseditor") !== -1, "edit state mounts the native editor div");
  assert(html.indexOf("<iframe") === -1, "no iframe in any workspace state");
});

test("the renderer never lets author bytes reach the DOM as markup", () => {
  const sb = onSandbox();
  const hostile = '# T\n\n<img src=x onerror=alert(1)> **b** <script>x</script>\n\n- <b>li</b>';
  const out = sb.__W.wsMdHtml(hostile);
  assert(out.indexOf("<img") === -1 && out.indexOf("<script") === -1
    && out.indexOf("<b>") === -1, "raw tags must be escaped: " + out.slice(0, 120));
  assert(out.indexOf("&lt;img") !== -1, "escaped form must survive");
  assert(out.indexOf("<strong>b</strong>") !== -1, "markdown still renders around it");
});

test("state 14 hides Save a copy when the edit gate is off", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.docGone = true;
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: false };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf(">Save a copy<") === -1,
    "Save a copy writes a file; it must be hidden when editing_allowed is false");
});

test("state 11 shows the read-only chip and NO edit affordance anywhere", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "b", editable: false };
  });
  /* r3: the chip cluster lives in the pane head now */
  const head = sb.__W.wsPaneHeadHtml();
  const html = sb.__W.wsScreenHtml();
  assert(head.indexOf(">read-only<") !== -1, "read-only chip missing from pane head");
  assert(head.indexOf('data-wsact="edit"') === -1 && html.indexOf('data-wsact="edit"') === -1,
    "Edit rendered in read-only mode");
  assert(html.indexOf(">New document here<") === -1 && html.indexOf(">File it<") === -1,
    "every write affordance must be absent in state 11");
});

test("state 06 renders the filing notice and the FILING rail says none", () => {
  const sb = onSandbox(sb2 => { sb2.S.ws.sel = { type: "doc", path: "holding/TODO.md" };
    sb2.S.ws.doc = { path: "holding/TODO.md", filing: { department: null, charter: null, placement_ref: null },
                     meta: { mtime: 1756020000 }, linked_from: [] }; });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("Not filed under a charter yet.") !== -1, "unfiled notice missing");
  assert(html.indexOf(">File it<") !== -1, "File it missing");
  assert(html.indexOf("FILING") !== -1 && html.indexOf(">none<") !== -1,
    "the FILING rail must say none, not hide");
});

test("state 10 renders skeletons with aria-busy, no strings", () => {
  const sb = onSandbox(sb2 => { sb2.S.ws.loaded = false; sb2.S.ws.tree = null; sb2.S.ws.loading = true; });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf('aria-busy="true"') !== -1, "loading panes must carry aria-busy (A11Y)");
  assert(html.indexOf("ws-skel") !== -1, "skeleton blocks missing");
});

test("hostile titles in the tree are escaped", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.tree = { departments: [{ ref: "D9", name: "<img src=x onerror=1>", count: 1,
      charters: [{ id: "C-1", title: "T", docs: [
        { path: "a.md", title: "<script>alert(1)</script>", mtime: 1, missing: false }]}]}],
      unfiled: [] };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf("<img") === -1 && html.indexOf("<script>alert") === -1,
    "a title reached innerHTML unescaped");
});

/* ── teardown ───────────────────────────────────────────────────────────── */

test("leaving the screen tears S.ws down to {lens, lastDocPath}", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.lens = "folders"; sb2.S.ws.lastDocPath = "holding/TODO.md";
    sb2.S.ws.results = { documents: [], records: [], counts: {} };
    sb2.S.ws.sel = { type: "doc", path: "holding/TODO.md" };
  });
  sb.S.screen = "departments";
  sb.__W.wireWorkspace(null);
  assert(sb.S.ws.tree === null && sb.S.ws.results === null && sb.S.ws.sel === null,
    "tree/results/selection must not survive screen exit (ARCH memory plan)");
  assert(sb.S.ws.lens === "folders" && sb.S.ws.lastDocPath === "holding/TODO.md",
    "lens and lastDocPath are the ONLY survivors");
});

/* ── async phase: stale search responses ────────────────────────────────── */

async function asyncChecks(){
  {
    /* editing mounts the native editor through the wire hook (PLAN-25 S10) */
    const calls = [];
    const sb = onSandbox(x => {
      x.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
      x.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: true, bytes: 4 };
      x.S.ws.editing = true;
      x.window.SutraEditor = { mount: (o) => { calls.push(o.path); return { destroy(){}, forceSave(){}, isDirty: () => false }; } };
    });
    const el = { querySelector: (q) => q === "[data-wseditor]" ? {} : null };
    sb.__W.wireWorkspace(el);
    await new Promise(r => setImmediate(r));
    if (calls.length === 1 && calls[0] === "holding/research/viewer.md" && sb.S.ws.edHandle){
      console.log("ok   - editing mounts the native editor through the wire hook (PLAN-25 S10)"); pass++;
    } else {
      console.log("FAIL - editing mounts the native editor through the wire hook\n       calls=" + JSON.stringify(calls)); fail++;
    }
  }

  {
    /* default-edit: an explicit doc open lands in edit state once the read
       copy arrives (founder 2026-08-25, dual consult) */
    const sb = onSandbox();
    sb.fetchImpl = (u) => Promise.resolve({ ok: true, json: async () =>
      String(u).indexOf("/api/fs/read") !== -1
        ? { text: "body", editable: true, bytes: 4 }
        : { meta: { mtime: 111 } } });
    await sb.__W.wsOpenDoc("holding/research/viewer.md", {});
    if (sb.S.ws.editing === true && sb.S.ws.unsaved === false
        && sb.__W.wsCurrentState() === "07"){
      console.log("ok   - default-edit: an explicit doc open lands in edit state (07), unsaved stays false"); pass++;
    } else {
      console.log("FAIL - default-edit: explicit open should land editing=true/unsaved=false/state 07, got editing="
        + sb.S.ws.editing + " unsaved=" + sb.S.ws.unsaved + " state=" + sb.__W.wsCurrentState()); fail++;
    }
  }

  {
    /* default-edit guards: restore, fromSearch, read-only, gone and unfiled
       all stay read-first */
    const mk = (impl) => { const sb = onSandbox(); sb.fetchImpl = impl || ((u) =>
      Promise.resolve({ ok: true, json: async () =>
        String(u).indexOf("/api/fs/read") !== -1
          ? { text: "body", editable: true, bytes: 4 }
          : { meta: { mtime: 111 } } })); return sb; };
    const bad = [];
    let sb = mk();
    await sb.__W.wsOpenDoc("holding/research/viewer.md", { restore: true });
    if (sb.S.ws.editing) bad.push("restore");
    sb = mk();
    await sb.__W.wsOpenDoc("holding/research/viewer.md", { fromSearch: true });
    if (sb.S.ws.editing) bad.push("fromSearch");
    sb = mk();
    sb.fetchImpl = (u) => Promise.resolve({ ok: true, json: async () =>
      String(u).indexOf("/api/fs/read") !== -1
        ? { text: "body", editable: false, bytes: 4 }
        : { meta: { mtime: 111 } } });
    await sb.__W.wsOpenDoc("holding/research/viewer.md", {});
    if (sb.S.ws.editing || sb.__W.wsCurrentState() !== "11") bad.push("read-only");
    sb = mk((u) => String(u).indexOf("/api/fs/read") !== -1
      ? Promise.resolve({ ok: true, json: async () => ({ error: { kind: "not_found" } }) })
      : Promise.resolve({ ok: false, json: async () => ({ error: { kind: "not_found", message: "gone" } }) }));
    await sb.__W.wsOpenDoc("holding/research/viewer.md", {});
    if (sb.S.ws.editing || !sb.S.ws.docGone) bad.push("gone");
    /* unfiled is NO LONGER a guard (r3: 87% of the corpus was unfiled) —
       its positive case is the dedicated r3 test below */
    if (!bad.length){
      console.log("ok   - default-edit guards: restore/fromSearch/read-only/gone stay read-first"); pass++;
    } else {
      console.log("FAIL - default-edit guards leaked into edit: " + bad.join(", ")); fail++;
    }
  }

  {
    /* default-edit: a stale mount resumer never pairs old text with a new
       path — the post-await openSeq/state re-check (dual consult) */
    const calls = [];
    const sb = onSandbox(x => {
      x.S.ws.sel = { type: "doc", path: "holding/research/a.md" };
      x.S.ws.lastRead = { path: "holding/research/a.md", text: "AAA", editable: true, bytes: 3 };
      x.S.ws.editing = true;
      x.S.ws.openSeq = 7;
      x.window.SutraEditor = { mount: (o) => { calls.push(o.path);
        return { destroy(){}, forceSave(){}, isDirty: () => false }; } };
    });
    const el = { querySelector: (q) => q === "[data-wseditor]" ? {} : null };
    sb.__W.wireWorkspace(el);
    /* a second open lands while the mount resumer sits behind the await */
    sb.S.ws.sel = { type: "doc", path: "holding/research/b.md" };
    sb.S.ws.openSeq = 8;
    await new Promise(r => setImmediate(r));
    if (calls.length === 0 && !sb.S.ws.edHandle){
      console.log("ok   - default-edit: a stale mount resumer aborts on the openSeq/state re-check"); pass++;
    } else {
      console.log("FAIL - default-edit: stale resumer mounted anyway: calls=" + JSON.stringify(calls)); fail++;
    }
  }

  {
    /* r3: unfiled docs default-edit too (87% of the corpus was unfiled), and
       the File-it banner rides ABOVE the editor in state 07 */
    const sb = onSandbox();
    sb.fetchImpl = (u) => Promise.resolve({ ok: true, json: async () =>
      String(u).indexOf("/api/fs/read") !== -1
        ? { text: "body", editable: true, bytes: 4 }
        : { meta: { mtime: 111 } } });
    sb.S.ws.tree = { departments: [], unfiled: [{ path: "holding/TODO.md", title: "TODO" }] };
    await sb.__W.wsOpenDoc("holding/TODO.md", {});
    const ok1 = sb.S.ws.editing === true && sb.S.ws.unsaved === false
      && sb.__W.wsCurrentState() === "07";
    const html = sb.__W.wsScreenHtml();
    const ok2 = html.indexOf('data-wsact="fileit"') !== -1 && html.indexOf("data-wseditor") !== -1;
    if (ok1 && ok2){
      console.log("ok   - unfiled docs default-edit too, File-it banner above the editor (r3)"); pass++;
    } else {
      console.log("FAIL - unfiled default-edit: editing=" + sb.S.ws.editing
        + " state=" + sb.__W.wsCurrentState() + " fileit=" + (html.indexOf('data-wsact="fileit"') !== -1)
        + " editor=" + (html.indexOf("data-wseditor") !== -1)); fail++;
    }
  }

  {
    /* r3 (deepseek hazard pin): File-it while editing dirty preserves the
       editor handle and the dirty state — filing classifies the PATH, it
       never touches doc bytes or identity */
    const sb = onSandbox();
    const handle = { destroy(){}, forceSave(){}, isDirty: () => true };
    sb.fetchImpl = () => Promise.resolve({ ok: true, json: async () =>
      ({ departments: [], unfiled: [] }) });
    sb.S.screen = "workspace";
    sb.S.ws.loaded = true;
    sb.S.ws.sel = { type: "doc", path: "holding/TODO.md" };
    sb.S.ws.docPath = "holding/TODO.md";
    sb.S.ws.editing = true; sb.S.ws.unsaved = true;
    sb.S.ws.edHandle = handle;
    await sb.__W.wsFileIt();
    if (sb.S.ws.edHandle === handle && sb.S.ws.unsaved === true
        && sb.S.ws.editing === true && sb.S.ws.busy === null){
      console.log("ok   - File-it while editing preserves the editor handle and dirty state (r3)"); pass++;
    } else {
      console.log("FAIL - File-it disturbed the editor: edHandle=" + (sb.S.ws.edHandle === handle)
        + " unsaved=" + sb.S.ws.unsaved + " editing=" + sb.S.ws.editing + " busy=" + sb.S.ws.busy); fail++;
    }
  }

  const sb = onSandbox();
  const W = sb.__W;
  const resolvers = [];
  sb.fetchImpl = () => new Promise(res => resolvers.push(res));
  W.wsSearchInput("obs"); sb.fireTimers();
  W.wsSearchInput("obsi"); sb.fireTimers();
  if (resolvers.length !== 2) throw new Error("expected two in-flight searches, got " + resolvers.length);
  /* the NEWER query answers first ... */
  resolvers[1]({ ok: true, json: async () => ({ query: "obsi",
    documents: [{ path: "new.md", title: "NEW" }], records: [],
    counts: { documents: 1, records: 0 } }) });
  await new Promise(r => setImmediate(r));
  /* ... then the STALE one arrives late and must be dropped */
  resolvers[0]({ ok: true, json: async () => ({ query: "obs",
    documents: [{ path: "old.md", title: "OLD" }], records: [],
    counts: { documents: 1, records: 0 } }) });
  await new Promise(r => setImmediate(r));
  if (!sb.S.ws.results || sb.S.ws.results.query !== "obsi")
    throw new Error("a stale search response overwrote the newest query's results");
  console.log("ok   - a superseded query's late response is dropped");
  pass++;
}

test("35. openScreen dispatches the workspace lazy load (regression: line dropped in a worktree restore)", () => {
  /* wireWorkspace() only binds handlers; the DATA arrives via openScreen's
     per-screen dispatch in 07-loaders.js. This line was silently lost once --
     the screen opened as an empty shell -- so the dispatch itself is pinned. */
  const src = fs.readFileSync(path.join(__dirname, "static/js/07-loaders.js"), "utf8");
  assert(/id === "workspace" && typeof loadWorkspace === "function"\) loadWorkspace\(false\)/.test(src),
    "openScreen must call loadWorkspace(false) for id workspace (guarded like wireWorkspace)");
});

test("search lives in the pane header: wsPaneHeadHtml carries the input, the screen body has no band (r3)", () => {
  const sb = onSandbox();
  const head = sb.__W.wsPaneHeadHtml();
  assert(head.indexOf("data-wssearch") !== -1, "pane head must carry the search input");
  assert(head.indexOf("ws-topright") !== -1, "pane head must carry the action cluster");
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf('class="ws-top"') === -1, "the .ws-top band must not render in the screen body");
  assert(html.indexOf("data-wssearch") === -1, "the search input must not render in the screen body");
});

test("search-in-header wiring pins (r3): 06-render injects the hook + preserves search focus", () => {
  const src = fs.readFileSync(path.join(__dirname, "static/js/06-render.js"), "utf8");
  assert(/S\.screen === "workspace" && typeof wsPaneHeadHtml === "function" \? wsPaneHeadHtml\(\) : ""/.test(src),
    ".ph must ask the workspace for its header contribution");
  assert(/"data-wssearch"/.test(src),
    "data-wssearch must be in the focused-input preserve whitelist (typing must survive background renders)");
});

test("click-to-edit (r4): the Edit button is gone from every surface", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.docPath = "holding/research/viewer.md";
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: true };
  });
  assert(sb.__W.wsPaneHeadHtml().indexOf('data-wsact="edit"') === -1,
    "the pane head must not render an Edit button");
  assert(sb.__W.wsScreenHtml().indexOf('data-wsact="edit"') === -1,
    "the screen body must not render an Edit button");
  assert(!/data-wsact="edit"/.test(source),
    "no Edit button markup anywhere in the module");
});

test("click-to-edit (r4): read-body click enters edit; selections and links do not", () => {
  const mk = (extra) => {
    const sb = onSandbox(sb2 => {
      sb2.S.screen = "workspace";
      sb2.S.ws.loaded = true;
      sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
      sb2.S.ws.docPath = "holding/research/viewer.md";
      sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: true };
      sb2.getSelection = () => ({ isCollapsed: extra.collapsed !== false });
    });
    const map = Object.assign({
      "#scBody": {}, "[data-wsread]": {},
    }, extra.map || {});
    sb.handlers.click({ target: { closest: q => map[q] || null, tagName: "DIV" } });
    return sb;
  };
  assert(mk({}).S.ws.editing === true, "a plain read-body click must enter edit");
  assert(mk({ collapsed: false }).S.ws.editing === false,
    "a drag-selection must NOT flip into edit (copying text stays safe)");
  assert(mk({ map: { "a,.ws-wikilink,button,input,textarea,select,summary,details": {} } }).S.ws.editing === false,
    "a link click keeps its own behaviour");
});

test("click-to-edit (r4): the keyboard path — 'e' enters edit, and read-only refuses", () => {
  const seed = sb2 => {
    sb2.S.screen = "workspace";
    sb2.S.ws.loaded = true;
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.docPath = "holding/research/viewer.md";
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: true };
  };
  const sb = onSandbox(seed);
  sb.handlers.keydown({ key: "e", target: { tagName: "DIV", closest: () => null }, preventDefault(){} });
  assert(sb.S.ws.editing === true, "'e' must enter edit from a read view");
  const ro = onSandbox(sb2 => { seed(sb2);
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "body", editable: false }; });
  ro.handlers.keydown({ key: "e", target: { tagName: "DIV", closest: () => null }, preventDefault(){} });
  assert(ro.S.ws.editing === false, "read-only mode must refuse the keyboard entry");
});

test("search (r9): clearing or escaping a live search brings the tree back", () => {
  /* the trap: the debounce is cancelled, so nothing downstream ever clears
     `searching` — the side pane renders "searching…" forever and the tree AND
     the lens buttons vanish. Two gestures in the r9 sweep caught this. */
  const mk = () => onSandbox(sb2 => {
    sb2.S.ws.tree = { departments: [{ ref:"D1", name:"Asawa Inc.", charters:[] }], unfiled: [] };
  });

  const a = mk();
  a.__W.wsSearchInput("sut");                 /* in flight (fetch parks) */
  assert(a.S.ws.searching === true, "typing must show the in-flight state");
  a.__W.wsSearchInput("");                    /* user clears the box */
  assert(a.S.ws.searching === false, "clearing the box must end the in-flight state");
  assert(a.__W.wsScreenHtml().indexOf("data-wslens") !== -1,
    "the lens buttons must come back with the tree");
  assert(a.__W.wsScreenHtml().indexOf("ws-dep") !== -1, "the tree must render again");

  const b = mk();
  b.__W.wsSearchInput("sut");
  assert(b.S.ws.searching === true, "precondition");
  b.handlers.keydown({ key: "Escape", target: { tagName: "DIV", closest: () => null },
                       preventDefault(){} });
  assert(b.S.ws.searching === false, "Escape must end the in-flight state too");
  assert(b.__W.wsScreenHtml().indexOf("ws-dep") !== -1, "the tree must render after Escape");
});

test("layout (r9): the workspace columns degrade, they never collapse", () => {
  const css = fs.readFileSync(path.join(__dirname, "static/workspace.css"), "utf8");
  /* the side pane and context rail MUST be shrinkable — with flex:none they
     out-sized the pane and the flexible document column measured ZERO, so the
     editor's content painted outside the pane and swallowed clicks */
  assert(!/\.ws-side\{width:286px;flex:none/.test(css),
    "the side pane must not be a fixed, unshrinkable column");
  assert(/\.ws-side\{flex:0 1 286px/.test(css), "side pane must shrink before the document");
  assert(/\.ws-ctx\{flex:0 1 232px/.test(css), "context rail must shrink too");
  assert(/\.ws-doccol\{[^}]*min-width:280px/.test(css),
    "the document column needs a floor so it can never reach zero width");
  assert(/@container \(max-width: 820px\)[\s\S]{0,80}\.ws-ctx\{display:none\}/.test(css),
    "the supplementary rail must yield first, on a container query");
  /* a table must not widen the editor's content layer past its column */
  assert(/\.sb-table-widget\{display:block;width:0;min-width:100%/.test(css),
    "the table widget must contribute zero intrinsic width");
  assert(/\.sb-table-widget table\{[^}]*table-layout:fixed/.test(css),
    "table-layout:fixed keeps the table inside its column");
});

test("folders lens (r7): nested model — counts, collapse, cap escape, md loader states", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.ws.lens = "folders";
    sb2.S.ws.fsMd = { files: [
      { path: "z-root.md" },
      { path: "a/one.md" }, { path: "a/two.md" },
      { path: "a/b/deep.md" },
      { path: "a/skip.txt" },
      { path: "empty/only.txt" },
      { path: ".tmp/scratch.md" },
      { path: "a/.cache/x.md" },
    ] };
  });
  let rows = sb.__W.wsFolderRows();
  /* collapsed: root doc + two top dirs (empty/ pruned — zero md) */
  assert(JSON.stringify(rows.map(r => r.type + ":" + r.key)) ===
    JSON.stringify(["fold:z-root.md", "folddir:a"]),
    "collapsed walk wrong: " + JSON.stringify(rows.map(r => r.type + ":" + r.key)));
  assert(rows[1].count === 3, "recursive md count must be 3, got " + rows[1].count);
  let html = sb.__W.wsFoldersHtml();
  assert(html.indexOf("z-root.md") !== -1 && html.indexOf('title="a"') !== -1,
    "renderer must draw the same rows");
  assert(html.indexOf("only.txt") === -1 && html.indexOf("empty") === -1,
    "zero-md dirs are pruned; non-md never renders");
  assert(html.indexOf(".tmp") === -1 && html.indexOf(".cache") === -1,
    "dot-dirs are tooling internals — never in the document lens");
  /* open a -> children appear; cursor model matches renderer */
  sb.S.ws.openFolds = { a: true };
  rows = sb.__W.wsFolderRows();
  assert(rows.some(r => r.type === "fold" && r.key === "a/one.md")
      && rows.some(r => r.type === "folddir" && r.key === "a/b"),
    "open dir must reveal children");
  const vis = sb.__W.wsVisibleRows();
  assert(JSON.stringify(vis.map(v => v.key)) === JSON.stringify(rows.map(r => r.key)),
    "wsVisibleRows must walk the SAME canonical model");
  /* loading + error states */
  const ld = onSandbox(sb2 => { sb2.S.ws.lens = "folders"; sb2.S.ws.fsMdLoading = true; });
  assert(ld.__W.wsFoldersHtml().indexOf("ws-skel") !== -1, "loading shows a skeleton");
  const er = onSandbox(sb2 => { sb2.S.ws.lens = "folders"; sb2.S.ws.fsMdError = "boom"; });
  const eh = er.__W.wsFoldersHtml();
  assert(eh.indexOf("did not load") !== -1 && eh.indexOf("foldretry") !== -1,
    "error state must name the failure and offer retry");
  /* the loader is md-only and workspace-owned */
  assert(/api\/fs\/tree\?md=1/.test(source), "wsLoadFolders must fetch md=1");
});

test("unmount flushes the editor BEFORE destroying it (r6: Done is gone)", () => {
  const calls = [];
  const sb = onSandbox(x => {
    x.S.ws.editing = true;
    x.S.ws.edHandle = { destroy: () => calls.push("destroyed"), forceSave: () => calls.push("flushed") };
  });
  sb.__W.wsUnmountEditor();
  assert(JSON.stringify(calls) === '["flushed","destroyed"]',
    "unmount must save FIRST, then destroy: " + JSON.stringify(calls));
  assert(sb.S.ws.edHandle === null, "handle cleared");
});

test("no Done button anywhere; the save chip replaces it (r6)", () => {
  assert(!/data-wsact="done"/.test(source), "the Done button must not exist in the module");
  const sb = onSandbox(sb2 => {
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
    sb2.S.ws.docPath = "holding/research/viewer.md";
    sb2.S.ws.lastRead = { path: "holding/research/viewer.md", text: "b", editable: true };
    sb2.S.ws.editing = true; sb2.S.ws.saveState = "saving";
  });
  assert(sb.__W.wsPaneHeadHtml().indexOf("saving") !== -1,
    "the pane head must show the saving chip while a save is in flight");
});

asyncChecks().catch(e => {
  console.log("FAIL - a superseded query's late response is dropped\n       " + e.message);
  fail++;
}).then(() => {
  console.log("\n" + "-".repeat(60));
  console.log("workspace screen: " + pass + " passed, " + fail + " failed"
    + (skip ? ", " + skip + " skipped" : ""));
  process.exit(fail ? 1 : 0);
});
