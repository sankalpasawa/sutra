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

test("no new URL builder: iframe URLs come only from sbUrl/sbPageFromPath", () => {
  assert(!/127\.0\.0\.1/.test(source),
    "a loopback literal in 13-workspace.js means a URL was built by hand");
  assert(!/new URL\(/.test(source), "no URL construction outside sbUrl");
  assert(/sbUrl\(/.test(source) && /sbPageFromPath\(/.test(source),
    "the shipped validators must be the ones called");
  assert(!/function sbPageFromPath|function sbUrl/.test(source),
    "13-workspace.js must not redefine the validators -- reuse, not a copy");
});

test("the iframe carries no src in markup -- property assignment only", () => {
  assert(/data-wsframe/.test(source), "the frame hook attribute is missing");
  assert(!/<iframe[^>]*src=/.test(source),
    "an iframe src in markup is one escaping bug from executable");
  assert(/frame\.src = url/.test(source), "the property-assignment path is missing");
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
const validatorSrc = (helpers.match(/^function (?:sbPageFromPath|sbUrl)\([\s\S]*?^\}/gm) || []).join("\n");
assert(/sbPageFromPath/.test(validatorSrc) && /sbUrl/.test(validatorSrc),
  "could not extract the shipped validators from 02-helpers.js");

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
  wsOpenDoc, wsSetLens, wsEdit, wsDone, wsKeepMine, wireWorkspace,
  wsScreenHtml, WS_COPY, wsMatchWords, wsCount };
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

test("flag off: nothing registers, nothing fetches, nothing reacts", () => {
  const sb = freshSandbox();
  const W = sb.__W;
  assert(W.wsFlagOn() === false, "absent SETTINGS must read as flag OFF");
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

test("flags.workspace must be literal true -- truthy strings stay OFF", () => {
  const sb = freshSandbox();
  sb.SETTINGS = { flags: { workspace: "yes" } };
  assert(sb.__W.wsFlagOn() === false, "a truthy non-boolean must not turn the flag on");
  sb.SETTINGS = { flags: { workspace: true } };
  assert(sb.__W.wsFlagOn() === true, "literal true must turn the flag on");
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
  assert(at(sb => { sb.S.sb = { running: true, readonly: true }; }) === "11", "edit gate off -> 11");
  assert(at(sb => { sb.S.ws.sel = { type:"doc", path:"holding/research/viewer.md" }; sb.S.ws.editing = true; sb.S.ws.unsaved = true; sb.S.ws.changed = true; }) === "12", "external write -> 12");
  assert(at(sb => { sb.S.ws.treeError = { kind:"engine_down", message:"x" }; }) === "13", "engine_down -> 13");
  assert(at(sb => { sb.S.sb = { running: false }; }) === "13", "sidecar dead -> 13");
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

test("visible rows walk the flat visual order: dept, charter, doc, Unfiled", () => {
  const sb = onSandbox();
  const rows = sb.__W.wsVisibleRows();
  const shape = rows.map(r => r.type).join(",");
  assert(shape === "dept,charter,doc,doc,dept,doc",
    "flat traversal order broken: " + shape);
  assert(rows[3].gone === true, "a missing doc stays LISTED (struck), never dropped");
});

test("Enter on a department moves the cursor to its first charter", () => {
  const sb = onSandbox();
  sb.__W.wsActivateRow({ type: "dept", key: "D3" });
  assert(sb.S.ws.cursor && sb.S.ws.cursor.i === 1,
    "departments have no page -- Enter must land on the first charter");
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
  assert(html.indexOf(">offline<") !== -1,
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
  assert(html.indexOf("data-wsframe") !== -1,
    "the frame (the last read copy) must stay on screen");
});

test("state 14 hides Save a copy when the edit gate is off", () => {
  const sb = onSandbox(sb2 => {
    sb2.S.sb = { running: true, readonly: true };
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
    sb2.S.sb = { running: true, readonly: true };
    sb2.S.ws.sel = { type: "doc", path: "holding/research/viewer.md" };
  });
  const html = sb.__W.wsScreenHtml();
  assert(html.indexOf(">read-only<") !== -1, "read-only chip missing");
  assert(html.indexOf('data-wsact="edit"') === -1, "Edit rendered in read-only mode");
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

asyncChecks().catch(e => {
  console.log("FAIL - a superseded query's late response is dropped\n       " + e.message);
  fail++;
}).then(() => {
  console.log("\n" + "-".repeat(60));
  console.log("workspace screen: " + pass + " passed, " + fail + " failed"
    + (skip ? ", " + skip + " skipped" : ""));
  process.exit(fail ? 1 : 0);
});
