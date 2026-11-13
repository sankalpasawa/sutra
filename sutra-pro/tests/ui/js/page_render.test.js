"use strict";
// The ported J2 page, rendered by its two harness copies (UI-2; docs/design/ui.md sections 5 and 10, S3-web-10; sync 4: docs/design/j2-sync-4.md 4.8).
// Run with: node --test tests/ui/js/page_render.test.js
//
// pages/j2_ui_render.js and pages/j2_graph_layout.js run the page's last inline script in a stub DOM and print JSON. With no
// department (the stub has no boot block and no location.pathname) the ported page must print what J2's own harness printed on
// J2's own page, except for the E13 wording: the goldens in tests/ui/fixtures/j2 were captured from J2 (an extraction of prototypes/j2
// at the pinned commit, scripts/capture_j2_fixtures.py) and get the E13 pairs applied (the pairs come from scripts/port_j2_ui.py,
// E13_WORDS). With a department only URLs may change.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const {execFileSync, spawnSync} = require("node:child_process");

const ROOT = path.resolve(__dirname, "../../..");
const UI = path.join(ROOT, "sutra_app/ui");
const PAGE = path.join(UI, "pages/j2_ui.html");
const RENDER = path.join(UI, "pages/j2_ui_render.js");
const LAYOUT = path.join(UI, "pages/j2_graph_layout.js");
const FIXTURES = path.join(ROOT, "tests/ui/fixtures/j2");
const fixture = name => path.join(FIXTURES, name);
const RENDER_ARGS = [PAGE, fixture("state.json"), fixture("previews.json"), fixture("render-docs.json")];
// What the captures hold as goldens (docs/design/j2-sync-4.md 4.8): the seven of the first capture, the Simple view's, the rail's, the
// Adaptation Map's, the chat panel's, then the Studio view's. The layout harness has its own golden.
const GOLDEN_KEYS = ["simple", "sprog", "workflows", "rail", "needs", "map", "agent", "finish", "journey", "journeyhtml", "sframe", "needids",
  "railst", "planmap", "msgfns", "feed", "teamwork", "plan", "team", "status", "views", "files", "parts", "tabs", "inline"];
// What J2's harness prints, in J2's order (the command line and the JSON output do not change).
const J2_KEYS = ["simple", "sprog", "finish", "journey", "journeyhtml", "sframe", "teamwork", "plan", "team", "status", "views", "files", "parts",
  "tabs", "inline", "needids", "cards", "workflows", "charter", "docs", "artifacts", "map", "board", "story", "needs", "needcount", "branches",
  "pages", "given", "tree", "focusall", "rail", "railst", "prio", "priorities", "planmap", "msgfns", "feed", "agent"];
const BOOT = {page: "dept", token: "t".repeat(24), dept: "web", dept_label: "Web", archived: false, note: "", version: "0.1.0"};
const RUN = "j2-20261104-100004-7f3a";
const MAX_BUFFER = 256 * 1024 * 1024;

const readJson = file => JSON.parse(fs.readFileSync(file, "utf8"));
const MANIFEST = readJson(fixture("MANIFEST.json"));

// ----------------------------------------------------------------------------------------------------------------------
// the clock: the captures ran node on a frozen clock (J2's page may put Date.now() into an address), so every harness here does too
// ----------------------------------------------------------------------------------------------------------------------
const CLOCK_MS = MANIFEST.clock * 1000;
const CLOCK_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "page-render-clock-"));
const CLOCK_FILE = path.join(CLOCK_DIR, "frozen_clock.js");
fs.writeFileSync(CLOCK_FILE, `Date.now = () => ${CLOCK_MS};\n`);
process.on("exit", () => fs.rmSync(CLOCK_DIR, {recursive: true, force: true}));

// ----------------------------------------------------------------------------------------------------------------------
// the E13 pairs, from the port script (python, through the project's own runner)
// ----------------------------------------------------------------------------------------------------------------------
const E13_WORDS = JSON.parse(execFileSync(path.join(ROOT, "scripts", "py"), [path.join(ROOT, "scripts", "port_j2_ui.py"), "--e13-json"],
  {encoding: "utf8", cwd: ROOT}));
// Every pair applied to the text of a value: the goldens are J2's, the page says "priced" and "pricing" instead of "ranked".
const withE13 = value => JSON.parse(E13_WORDS.reduce((text, [from, to]) => text.split(from).join(to), JSON.stringify(value)));

// ----------------------------------------------------------------------------------------------------------------------
// a harness as a child process (what a developer runs), and in this process (to change what the stub page sees)
// ----------------------------------------------------------------------------------------------------------------------
function spawnHarness(file, args) {
  const done = spawnSync(process.execPath, ["--require", CLOCK_FILE, file, ...args], {encoding: "utf8", maxBuffer: MAX_BUFFER});
  return {status: done.status, stderr: done.stderr, out: done.status === 0 ? JSON.parse(done.stdout) : null};
}

// Runs a harness file in this process exactly as `node <file> <args>` would, with a hook on vm.createContext: the stub page
// gets what `opts` asks for, and the context and the elements it asked for stay available afterwards.
//   opts.boot      an object: the text of the #sutra-boot block (the server writes it; the stub has none)
//   opts.location  properties added to the stub's location (pathname, search)
//   opts.events    true: the stub document can dispatch, and CustomEvent exists (J2's stub has neither)
// The stub's fetch records its URLs (and rejects, as J2's does). Elements are kept by id in `elements`.
function runHarness(file, args, opts = {}) {
  const elements = {}, events = [], fetched = [];
  let context = null, printed = "";
  const patchedVm = Object.assign({}, vm, {
    createContext(sandbox) {
      const lookup = sandbox.document.getElementById, query = sandbox.document.querySelector;
      sandbox.document.getElementById = id => (id === "sutra-boot" && opts.boot ? {textContent: JSON.stringify(opts.boot)} : (elements[id] = lookup(id)));
      sandbox.document.querySelector = selector => Object.assign(query(selector), {closest: () => null});   // railReveal(): no rail section
      Object.assign(sandbox.location, opts.location);
      if (opts.events) {
        sandbox.CustomEvent = class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };
        sandbox.document.dispatchEvent = event => { events.push(event); return true; };
      }
      sandbox.fetch = url => { fetched.push(String(url)); return Promise.reject(new Error("no network")); };
      context = vm.createContext(sandbox);
      return context;
    },
  });
  const load = name => (name === "vm" ? patchedVm : require(name));
  const print = {log: text => { printed += text; }};
  const realNow = Date.now;
  Date.now = () => CLOCK_MS;
  try {
    new Function("require", "process", "console", "__dirname", fs.readFileSync(file, "utf8"))(
      load, {argv: ["node", file, ...args]}, print, path.dirname(file));
  } finally {
    Date.now = realNow;
  }
  return {out: JSON.parse(printed), context, elements, events, fetched, run: code => vm.runInContext(code, context)};
}

const dept = (extra = {}) => runHarness(RENDER, RENDER_ARGS, {boot: BOOT, ...extra, location: {pathname: "/d/web/", ...extra.location}});
const plain = (extra = {}) => runHarness(RENDER, RENDER_ARGS, extra);
const html = () => fs.readFileSync(PAGE, "utf8");

// a harness input changed for one test (a state or the render-docs file), written to a folder the test removes
function variant(t, name, value) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "page-render-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const file = path.join(dir, name);
  fs.writeFileSync(file, JSON.stringify(value));
  return file;
}

let memo = null;
const rendered = () => (memo = memo || spawnHarness(RENDER, RENDER_ARGS));

// ----------------------------------------------------------------------------------------------------------------------
test("the E13 pairs come from the port script: four pairs, each said in the page as often as the script counts, the old words nowhere", () => {
  assert.equal(E13_WORDS.length, 4);
  assert.ok(E13_WORDS.every(([from, to, count]) => from.length > 0 && to.length > 0 && Number.isInteger(count) && count >= 1));
  assert.ok(E13_WORDS.every(([from, to]) => /ranked|ranking/.test(from) && !/ranked|ranking/.test(to)));
  for (const [from, to, count] of E13_WORDS) {
    assert.equal(html().split(to).length - 1, count, to);
    assert.equal(html().split(from).length - 1, 0, from);
  }
});

test("the render harness copy runs on the ported page and prints J2's keys, quietly", () => {
  const done = rendered();
  assert.equal(done.status, 0);
  assert.equal(done.stderr, "");
  assert.deepEqual(Object.keys(done.out), J2_KEYS);
});

test("the manifest of the captures lists the goldens compared here, the pinned commit and the clock the harnesses run on", () => {
  assert.deepEqual(MANIFEST.harness.goldens, [...GOLDEN_KEYS, "layout"].map(key => `golden-${key}.json`));
  assert.match(MANIFEST.j2_commit, /^[0-9a-f]{40}$/);
  assert.ok(Number.isInteger(MANIFEST.clock) && MANIFEST.clock > 0);
  assert.ok(GOLDEN_KEYS.every(key => J2_KEYS.includes(key)));
});

for (const key of GOLDEN_KEYS) {
  test(`parity: "${key}" equals J2's golden once the E13 pairs are applied to it`, () => {
    assert.deepEqual(rendered().out[key], withE13(readJson(fixture(`golden-${key}.json`))));
  });
}

test("parity: the layout harness copy prints J2's golden layout for the map fixture", () => {
  const done = spawnHarness(LAYOUT, [PAGE, fixture("maps.json")]);
  assert.equal(done.status, 0);
  assert.equal(done.stderr, "");
  assert.deepEqual(done.out, readJson(fixture("golden-layout.json")));
  assert.ok(done.out.length > 0 && done.out.every(entry => entry.rest || entry.team || entry.wf));
});

test("E13: with Priority's records the funded list says registration order; the old word is gone from every output", () => {
  const text = JSON.stringify(rendered().out);
  assert.ok(rendered().out.priorities.includes("<h4>Funded, in registration order; Coordination sets the run order</h4>"));
  assert.ok(!/in the order it ranked them|ranking records|ranked the work/.test(text));
});

test("E13: with no records the Priorities tab, its status and the rail say pricing, not ranking", t => {
  const empty = variant(t, "empty-state.json", {...readJson(fixture("state.json")), chat: [], workflows: [], conflicts: []});
  const {out} = runHarness(RENDER, [PAGE, empty, fixture("previews.json"), fixture("render-docs.json")]);
  assert.equal(out.priorities, `<p class="empty">No pricing records in this run: Priority's decisions and the priced workflows were not recorded.</p>`);
  assert.equal(out.prio.has, false);
  assert.equal(out.prio.status, "no pricing records");
  assert.equal(JSON.stringify(out.rail).match(/no pricing records/g).length, 2);
  assert.ok(!/ranking/.test(JSON.stringify(out)));
});

// ----------------------------------------------------------------------------------------------------------------------
// with a department: the page learns it from SutraCtx (E4, E5, E10) and the fetch wrapper, and nothing else changes
// ----------------------------------------------------------------------------------------------------------------------
const strip = value => JSON.stringify(value).split("&dept=web").join("").split("?dept=web").join("");

test("with a department only URLs gain dept=: removing it gives the output of the page without one", () => {
  const alone = rendered().out, web = dept().out;
  assert.deepEqual(Object.keys(web), J2_KEYS);
  for (const key of J2_KEYS) assert.equal(strip(web[key]), JSON.stringify(alone[key]), key);
  const urls = JSON.stringify(web).match(/[?&]dept=web/g) || [];
  assert.ok(urls.length > 0, "a URL in the markup carries the department");
  assert.notEqual(JSON.stringify(web), JSON.stringify(alone));
  assert.equal(alone.sframe, "/site/v5?x=1");
  assert.equal(web.sframe, "/site/v5?x=1&dept=web", "the preview's address is made by the page's own script with runQ(): E4 adds the team");
});

test("with a department and a run the URLs carry the run first and the department last", () => {
  const withRun = path => runHarness(RENDER, RENDER_ARGS, path);
  const alone = withRun({location: {search: `?run=${RUN}`}});
  const web = withRun({boot: BOOT, location: {pathname: "/d/web/", search: `?run=${RUN}`}});
  for (const key of J2_KEYS) assert.equal(strip(web.out[key]), JSON.stringify(alone.out[key]), key);
  assert.ok(JSON.stringify(web.out).includes(`/site/latest?run=${RUN}&dept=web#hero`));
  assert.ok(!JSON.stringify(web.out).includes("dept=web&"));
});

test("the page's own first calls reach J2's routes with the department once, with and without a run", () => {
  // the start page's output select is a Sutra module (output_pick.js): the page's own script no longer asks /api/engine/settings
  assert.deepEqual(dept().fetched, ["/api/refs?dept=web", "/api/runs?dept=web", "/api/runlist?dept=web", "/api/timing?dept=web",
    "/api/state?since=0&dept=web", "/api/artifacts?x=1&dept=web"]);
  // a saved run also asks for its change requests (the build journey's stops) before the artifacts
  assert.deepEqual(dept({location: {search: `?run=${RUN}`}}).fetched,
    ["/api/refs?dept=web", "/api/runs?dept=web", "/api/runlist?dept=web", `/api/timing?run=${RUN}&dept=web`, `/api/state?since=0&run=${RUN}&dept=web`,
      `/api/changes?x=1&run=${RUN}&dept=web`, `/api/artifacts?x=1&run=${RUN}&dept=web`]);
});

test("without a department the page is J2's: SutraCtx is there and empty, nothing is wrapped, no dept= anywhere", () => {
  const alone = plain();
  assert.equal(alone.run("typeof SutraCtx"), "object");
  assert.equal(alone.run("SutraCtx.dept"), "");
  assert.equal(alone.run("typeof fetch.sutraWrapped"), "undefined");
  assert.deepEqual(alone.fetched, ["/api/refs", "/api/runs", "/api/runlist", "/api/timing", "/api/state?since=0", "/api/artifacts?x=1"]);
  assert.ok(!JSON.stringify(alone.out).includes("dept="));
});

test("E5: the Simple view opens with the strip, All teams and the team's chip (dept_ext.js fills the chip); the studio's own #shome is another element", () => {
  // the class is not `shome`: the studio has an element with that id (its Start over), so the strip is `steamstrip` (the style is sutra-panel.css's)
  assert.ok(html().includes('<div id="sview">\n  <div class="steamstrip"><a href="/" id="to-home-s">← All teams</a><b id="deptchip-s"></b></div>\n  <section class="sland" id="sland"'));
  assert.equal(html().split('id="to-home-s"').length - 1, 1);
});

test("E7: the rail starts with the strip (All teams, the team's chip, the Workflow graph and Org chart tabs), outside the panel J2 fills", () => {
  const start = html().indexOf('<nav class="rail tabs" id="rail"'), rail = html().slice(start, html().indexOf("</nav>", start));
  const strip = rail.slice(0, rail.indexOf('class="rsep"'));
  assert.ok(strip.includes('<div class="railhome">') && strip.includes('href="/" id="to-home"') && strip.includes('<b class="rdept" id="deptchip"></b>'));
  assert.deepEqual([...strip.matchAll(/data-tab="(\w+)"/g)].map(m => m[1]), ["graph", "orgchart"]);
  assert.ok(!/data-tab="(graph|orgchart)"/.test(rail.slice(rail.indexOf('id="railsub"'))), "J2's flyout model never lists the two tabs, so nothing is shown twice");
});

test("E2: the preview frames are sandboxed without allow-same-origin, and only the Detailed view's frame takes its address from data-src", () => {
  const frames = Object.fromEntries([...html().matchAll(/<iframe id="(\w+)"([^>]*)>/g)].map(m => [m[1], m[2]]));
  assert.deepEqual(Object.keys(frames).sort(), ["frame", "sframe", "sframe2"]);
  for (const [id, attributes] of Object.entries(frames)) {
    assert.ok(attributes.includes('sandbox="allow-scripts allow-forms allow-popups"'), id);
    assert.ok(!attributes.includes("allow-same-origin"), id);
    assert.equal(attributes.includes('data-src="/site/latest"'), id === "frame", id);
  }
});

// ----------------------------------------------------------------------------------------------------------------------
// E20 to E22: the shared library's paths, the function chat's hydration, the Run settings line
// ----------------------------------------------------------------------------------------------------------------------
test("E20: links to the shared library and to a run's Library tab are the team's paths with a team and J2's own without one", () => {
  const web = dept(), alone = plain();
  assert.equal(alone.run('libHref("prd", "Document", "generic", 1)'), "/library?open=prd/document/generic/v1");
  assert.equal(web.run('libHref("prd", "Document", "generic", 1)'), "/d/web/library?open=prd/document/generic/v1");
  assert.equal(alone.run('runHref("j2-x")'), "/?run=j2-x&view=detail&tab=library");
  assert.equal(web.run('runHref("j2-x")'), "/d/web/?run=j2-x&view=detail&tab=library");
  assert.equal(alone.run("CAT.on"), false);
  assert.equal(web.run("CAT.on"), false);
  assert.equal(dept({location: {pathname: "/d/web/library"}}).run("CAT.on"), true);
  assert.equal(dept({location: {pathname: "/d/web/library/"}}).run("CAT.on"), true, "a trailing slash is the same page");
  assert.equal(dept({location: {pathname: "/d/other/library"}}).run("CAT.on"), false, "another team's library is not this page");
  assert.equal(plain({location: {pathname: "/library"}}).run("CAT.on"), true, "J2's own page, as the stub has it");
});

test("E21: loadFeed hands the question list to FunctionChat before it paints the feed, and paints all the same when the module fails or is absent", async () => {
  const page = dept();
  page.run('globalThis.window = globalThis; globalThis.calls = []; globalThis.order = []; CHATFN = "adaptation"; paintFeed = () => order.push("paint");'
    + 'globalThis.FunctionChat = {hydrate: async (...args) => { calls.push(args); order.push("hydrate"); return true; }};');
  const order = () => [...page.run("order")];      // the page's array is of its own realm: copy it to compare
  await page.run("loadFeed(true)");
  assert.deepEqual(order(), ["hydrate", "paint"]);
  assert.equal(page.run('calls.length === 1 && calls[0][0] === QA && calls[0][1] === "adaptation" && calls[0][2] === ""'), true);
  assert.ok(page.fetched.includes("/api/activity?who=adaptation&dept=web"));
  page.run('order.length = 0; globalThis.FunctionChat = {hydrate: async () => { throw new Error("module failed"); }};');
  await page.run("loadFeed(true)");
  assert.deepEqual(order(), ["paint"]);
  page.run("order.length = 0; delete globalThis.FunctionChat;");
  await page.run("loadFeed(true)");
  assert.deepEqual(order(), ["paint"]);
});

test("E22: Run settings is described as the appearance and the saved runs; the pane has no 'what to build'", () => {
  assert.equal(plain().run("TABSUB.runsettings"), "appearance and saved runs");
  assert.ok(!/appearance, what to build/.test(html()));
});

// ----------------------------------------------------------------------------------------------------------------------
// the Simple view's cards: the finish card of a finished run, the feed's thinking
// ----------------------------------------------------------------------------------------------------------------------
test("E4: the finish card of a finished run links to the preview with the run first and the department last", t => {
  const done = variant(t, "done-state.json", {...readJson(fixture("state.json")), outcome: "Done", paused: null, status: "done"});
  const finish = opts => runHarness(RENDER, [PAGE, done, fixture("previews.json"), fixture("render-docs.json")], opts).out.finish;
  const alone = finish({}), web = finish({boot: BOOT, location: {pathname: "/d/web/"}});
  const run = finish({boot: BOOT, location: {pathname: "/d/web/", search: `?run=${RUN}`}});
  for (const card of [alone, web, run]) {
    assert.ok(card.includes("Copy share link") && card.includes("Open full view") && card.includes(`download="${readJson(fixture("state.json")).page}.html"`));
  }
  assert.ok(alone.includes('href="/site/latest"') && web.includes('href="/site/latest?dept=web"'));
  assert.ok(run.includes(`href="/site/latest?run=${RUN}&dept=web"`));
  assert.equal(rendered().out.finish, "", "the captured run still waits for an answer: no finish card");
});

test("the feed lists a function's calls, plans and judgements only while its thinking is shown (the harness's think input)", t => {
  const thinking = variant(t, "render-docs-think.json", {...readJson(fixture("render-docs.json")), think: true});
  const on = runHarness(RENDER, [PAGE, fixture("state.json"), fixture("previews.json"), thinking]).out.feed;
  const off = rendered().out.feed;
  assert.ok(!off.includes("fev f-call") && !off.includes("fev f-plan"));
  assert.ok(on.includes("fev f-call") && on.includes("fev f-plan") && on.includes("fev f-judge") && on.length > off.length);
});

// ----------------------------------------------------------------------------------------------------------------------
// E6: the two new panes
// ----------------------------------------------------------------------------------------------------------------------
test("showTab(\"graph\") reveals #pane-graph, hides the others and fires sutra:tab", () => {
  const page = dept({events: true});
  assert.deepEqual(page.events.map(e => e.detail.name), ["map"], "J2's own showTab(\"map\") at parse time");
  page.run('showTab("graph")');
  assert.equal(page.elements["pane-graph"].hidden, false);
  for (const pane of ["pane-orgchart", "pane-map", "pane-goal", "pane-preview", "pane-runsettings"]) assert.equal(page.elements[pane].hidden, true, pane);
  assert.deepEqual(page.events.map(e => [e.type, e.detail.name]), [["sutra:tab", "map"], ["sutra:tab", "graph"]]);
  assert.equal(page.run("SutraCtx.currentTab"), "graph");
});

test("showTab(\"orgchart\") reveals #pane-orgchart and showTab(\"map\") hides both new panes again", () => {
  const page = dept({events: true});
  page.run('showTab("orgchart")');
  assert.deepEqual([page.elements["pane-orgchart"].hidden, page.elements["pane-graph"].hidden, page.elements["pane-map"].hidden], [false, true, true]);
  page.run('showTab("map")');
  assert.deepEqual([page.elements["pane-orgchart"].hidden, page.elements["pane-graph"].hidden, page.elements["pane-map"].hidden], [true, true, false]);
  assert.equal(page.run("SutraCtx.currentTab"), "map");
});

test("a ?tab= deep link is shown at parse time and leaves the tab in SutraCtx.currentTab for dept_ext.js", () => {
  const page = dept({events: true, location: {search: "?tab=orgchart"}});
  assert.equal(page.elements["pane-orgchart"].hidden, false);
  assert.equal(page.elements["pane-map"].hidden, true);
  assert.equal(page.run("SutraCtx.currentTab"), "orgchart");
  assert.deepEqual(page.events.map(e => e.detail.name), ["map", "orgchart"], "the events had no listener yet, which is why currentTab exists");
});

test("showTab works in J2's stub, which has no dispatchEvent and no CustomEvent", () => {
  const page = runHarness(RENDER, RENDER_ARGS, {location: {}});
  page.run('showTab("graph")');
  assert.equal(page.elements["pane-graph"].hidden, false);
  assert.equal(page.run("SutraCtx.currentTab"), "graph");
});

// ----------------------------------------------------------------------------------------------------------------------
// opt in: J2's own harness on J2's own page (SUTRA_J2_CHECKOUT=<an extraction of prototypes/j2 at the pinned commit>)
// ----------------------------------------------------------------------------------------------------------------------
const J2 = process.env.SUTRA_J2_CHECKOUT;
test("J2's own harness on J2's own page prints every key the ported page prints, except for the E13 wording", {skip: !J2 && "set SUTRA_J2_CHECKOUT=<an extraction of prototypes/j2 at the pinned commit>"}, () => {
  const theirs = spawnHarness(path.join(J2, "j2_ui_render.js"), [path.join(J2, "j2_ui.html"), ...RENDER_ARGS.slice(1)]);
  assert.equal(theirs.status, 0);
  assert.deepEqual(Object.keys(theirs.out), J2_KEYS);
  assert.deepEqual(rendered().out, withE13(theirs.out));
  const layout = spawnHarness(path.join(J2, "j2_graph_layout.js"), [path.join(J2, "j2_ui.html"), fixture("maps.json")]);
  assert.deepEqual(spawnHarness(LAYOUT, [PAGE, fixture("maps.json")]).out, layout.out);
});

// ----------------------------------------------------------------------------------------------------------------------
// Run settings: J2's own (appearance cards and the run list over /api/runlist); the copies the earlier port added are gone
// ----------------------------------------------------------------------------------------------------------------------
const ROW = (n, over = {}) => ({id: `j2-20261104-1000${String(n).padStart(2, "0")}-aaaa`, title: `Run ${n}`, status: "done", output: "website",
  when: `2026-11-04T10:00:${String(n % 60).padStart(2, "0")}`, brief: `brief ${n}`, ...over});
const shown = (page, runs, live = "") => {
  page.run(`RUNS.all = ${JSON.stringify(runs)}; RUNS.live = ${JSON.stringify(live)}; RUNS.f = "all"; RUNS.q = ""; RUNS.show = 20; renderRuns()`);
  return page.elements.runlist.innerHTML;
};

test("Run settings is J2's own: its list, filters, search and reset are in the page and the start page's output select is a module's placeholder", () => {
  for (const gone of ['id="outsel"', 'id="runsel"', 'id="to-simple"', "Back to simple view", "run-settings.css"]) assert.ok(!html().includes(gone), gone);
  for (const there of ['id="runlist"', 'id="runq"', 'data-rf="running"', 'data-themepick="system"', 'id="reset"', 'id="soutpick"',
    'href="/ui/css/j2.css"', 'href="/ui/css/sutra-graph.css"', 'href="/ui/css/sutra-panel.css"']) assert.ok(html().includes(there), there);
  assert.ok(html().includes("How the app looks, and which run you are looking at."));
});

test("Run settings lists the runs under date headings, marks the open one and shows 20 at a time", () => {
  const page = dept();
  const runs = Array.from({length: 25}, (_, i) => ROW(i + 1)).reverse();
  const list = shown(page, runs, runs[0].id);
  assert.equal((list.match(/class="runrow/g) || []).length, 20);
  assert.equal((list.match(/class="runrow cur"/g) || []).length, 1);
  assert.ok(list.includes(`aria-label="Run 25, ${runs[0].id}, done, open now"`) && list.includes("Show 5 more · 5 left"));
  assert.equal(page.elements.runcount.textContent, "25 runs");
  page.run("RUNS.show += 20; renderRuns()");
  assert.equal((page.elements.runlist.innerHTML.match(/class="runrow/g) || []).length, 25);
  assert.ok(!page.elements.runlist.innerHTML.includes("runmore"));
});

test("Run settings filters by status and searches title, brief and run id; nothing matching says so", () => {
  const page = dept();
  const runs = [ROW(3, {status: "running", title: "Brew Lab"}), ROW(2, {status: "done", brief: "a florist in Jaipur"}), ROW(1, {status: "stopped"})];
  shown(page, runs);
  page.run('RUNS.f = "stopped"; renderRuns()');
  assert.deepEqual([...page.elements.runlist.innerHTML.matchAll(/data-openrun="([^"]+)"/g)].map(m => m[1]), [runs[2].id]);
  assert.equal(page.elements.runcount.textContent, "1 of 3 runs");
  page.run('RUNS.f = "all"; RUNS.q = "JAIPUR"; renderRuns()');
  assert.deepEqual([...page.elements.runlist.innerHTML.matchAll(/data-openrun="([^"]+)"/g)].map(m => m[1]), [runs[1].id]);
  page.run(`RUNS.q = ${JSON.stringify(runs[0].id.slice(4, 14))}; renderRuns()`);
  assert.equal((page.elements.runlist.innerHTML.match(/class="runrow/g) || []).length, 3);
  page.run('RUNS.q = "zzz"; renderRuns()');
  assert.equal(page.elements.runlist.innerHTML, '<div class="runnone">No runs match.</div>');
});

test("Run settings escapes what a run says and uses the document icon for a PRD", () => {
  const page = dept();
  const list = shown(page, [ROW(1, {title: "<img src=x onerror=1>", brief: '"quoted" & <b>', output: "prd"})]);
  assert.ok(!list.includes("<img src=x") && !list.includes("<b>") && list.includes("&lt;img src=x onerror=1&gt;"));
  assert.ok(list.includes('d="M6 3h8l4 4v14H6z"'));
});

test("Run settings opens a run by J2's own link: the run set and the view kept, the live run by no run at all", () => {
  const page = dept({location: {search: "?view=detail&tab=runsettings"}});
  assert.equal(page.run('viewHref("j2-20261104-100004-7f3a")'), "?run=j2-20261104-100004-7f3a&view=detail");
  assert.equal(page.run('viewHref("")'), "?view=detail");
  assert.equal(runHarness(RENDER, RENDER_ARGS, {boot: BOOT, location: {pathname: "/d/web/", search: "?run=x"}}).run('viewHref("")'), "?view=detail");
});
