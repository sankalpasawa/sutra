"use strict";
// The ported J2 page, rendered by its two harness copies (UI-2; docs/design/ui.md sections 5 and 10, S3-web-10).
// Run with: node --test tests/ui/js/page_render.test.js
//
// pages/j2_ui_render.js and pages/j2_graph_layout.js run the page's last inline script in a stub DOM and print JSON. With no
// department (the stub has no boot block and no location.pathname) the ported page must print what J2's own harness printed on
// J2's own page, except for the E13 wording: the goldens in tests/ui/fixtures/j2 were captured from J2 and get the E13 pairs
// applied (the pairs come from scripts/port_j2_ui.py, E13_WORDS). With a department only URLs may change.
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
const GOLDEN_KEYS = ["simple", "sprog", "workflows", "rail", "needs", "map", "agent"];
// What J2's harness prints, in J2's order (the command line and the JSON output do not change).
const J2_KEYS = ["simple", "sprog", "cards", "workflows", "charter", "docs", "artifacts", "map", "board", "story", "needs", "needcount",
  "branches", "pages", "given", "tree", "focusall", "rail", "prio", "priorities", "agent"];
const BOOT = {page: "dept", token: "t".repeat(24), dept: "web", dept_label: "Web", archived: false, note: "", version: "0.1.0"};
const RUN = "j2-20261104-100004-7f3a";
const MAX_BUFFER = 256 * 1024 * 1024;

const readJson = file => JSON.parse(fs.readFileSync(file, "utf8"));

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
  const done = spawnSync(process.execPath, [file, ...args], {encoding: "utf8", maxBuffer: MAX_BUFFER});
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
  new Function("require", "process", "console", "__dirname", fs.readFileSync(file, "utf8"))(
    load, {argv: ["node", file, ...args]}, print, path.dirname(file));
  return {out: JSON.parse(printed), context, elements, events, fetched, run: code => vm.runInContext(code, context)};
}

const dept = (extra = {}) => runHarness(RENDER, RENDER_ARGS, {boot: BOOT, ...extra, location: {pathname: "/d/web/", ...extra.location}});

let memo = null;
const rendered = () => (memo = memo || spawnHarness(RENDER, RENDER_ARGS));

// ----------------------------------------------------------------------------------------------------------------------
test("the E13 pairs come from the port script: four pairs, counts 1, 2, 1, 1", () => {
  assert.deepEqual(E13_WORDS.map(([from, to, count]) => [from.length > 0, to.length > 0, count]), [[true, true, 1], [true, true, 2], [true, true, 1], [true, true, 1]]);
  assert.ok(E13_WORDS.every(([from, to]) => /ranked|ranking/.test(from) && !/ranked|ranking/.test(to)));
});

test("the render harness copy runs on the ported page and prints J2's keys, quietly", () => {
  const done = rendered();
  assert.equal(done.status, 0);
  assert.equal(done.stderr, "");
  assert.deepEqual(Object.keys(done.out), J2_KEYS);
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "page-render-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const empty = path.join(dir, "empty-state.json");
  fs.writeFileSync(empty, JSON.stringify({...readJson(fixture("state.json")), chat: [], workflows: [], conflicts: []}));
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
  assert.ok(JSON.stringify(web).includes("href=\\\"/site/latest?dept=web#hero\\\""));
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
  // E19: the start page's output select first asks the engine for its own default (GET /api/engine/settings, with the department by hand)
  assert.deepEqual(dept().fetched, ["/api/engine/settings?dept=web", "/api/refs?dept=web", "/api/runs?dept=web", "/api/runlist?dept=web",
    "/api/state?since=0&dept=web"]);
  assert.deepEqual(dept({location: {search: `?run=${RUN}`}}).fetched,
    ["/api/engine/settings?dept=web", "/api/refs?dept=web", "/api/runs?dept=web", "/api/runlist?dept=web", `/api/state?since=0&run=${RUN}&dept=web`]);
});

test("without a department the page is J2's: SutraCtx is there and empty, nothing is wrapped, no dept= anywhere", () => {
  const plain = runHarness(RENDER, RENDER_ARGS);
  assert.equal(plain.run("typeof SutraCtx"), "object");
  assert.equal(plain.run("SutraCtx.dept"), "");
  assert.equal(plain.run("typeof fetch.sutraWrapped"), "undefined");
  assert.deepEqual(plain.fetched, ["/api/engine/settings", "/api/refs", "/api/runs", "/api/runlist", "/api/state?since=0"]);
  assert.ok(!JSON.stringify(plain.out).includes("dept="));
});

test("E5: the Simple view title is the department's name, else J2's words", () => {
  assert.equal(dept().elements.stitle.textContent, "Web");
  assert.equal(runHarness(RENDER, RENDER_ARGS).elements.stitle.textContent, "Your website team");
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
// opt in: the real J2 (SUTRA_J2_CHECKOUT=<J2 checkout>)
// ----------------------------------------------------------------------------------------------------------------------
const J2 = process.env.SUTRA_J2_CHECKOUT;
test("J2's own harness on J2's own page prints every key the ported page prints, except for the E13 wording", {skip: !J2 && "set SUTRA_J2_CHECKOUT=<J2 checkout>"}, () => {
  const theirs = spawnHarness(path.join(J2, "j2_ui_render.js"), [path.join(J2, "j2_ui.html"), ...RENDER_ARGS.slice(1)]);
  assert.equal(theirs.status, 0);
  assert.deepEqual(rendered().out, withE13(theirs.out));
  const layout = spawnHarness(path.join(J2, "j2_graph_layout.js"), [path.join(J2, "j2_ui.html"), fixture("maps.json")]);
  assert.deepEqual(spawnHarness(LAYOUT, [PAGE, fixture("maps.json")]).out, layout.out);
});

// ----------------------------------------------------------------------------------------------------------------------
// E14 to E18: Run settings (appearance cards and the run list over /api/runlist, patch P13)
// ----------------------------------------------------------------------------------------------------------------------
const ROW = (n, over = {}) => ({id: `j2-20261104-1000${String(n).padStart(2, "0")}-aaaa`, title: `Run ${n}`, status: "done", output: "website",
  when: `2026-11-04T10:00:${String(n % 60).padStart(2, "0")}`, brief: `brief ${n}`, ...over});
const shown = (page, runs, live = "") => {
  page.run(`RUNS.all = ${JSON.stringify(runs)}; RUNS.live = ${JSON.stringify(live)}; RUNS.f = "all"; RUNS.q = ""; RUNS.show = 20; renderRuns()`);
  return page.elements.runlist.innerHTML;
};

test("E14 to E18: the old controls are gone from the page and the new ones are in it", () => {
  const html = fs.readFileSync(PAGE, "utf8");
  for (const gone of ['id="outsel"', 'id="runsel"', 'id="to-simple"', "Back to simple view", "$(\"outsel\")", "$(\"runsel\")"]) assert.ok(!html.includes(gone), gone);
  for (const there of ['id="runlist"', 'id="runq"', 'data-rf="running"', 'data-themepick="system"', 'id="reset"', 'href="/ui/css/run-settings.css"']) assert.ok(html.includes(there), there);
  assert.ok(html.includes('class="outsel"'), "the Simple view's start page keeps its output select");
  assert.ok(html.includes("How the app looks, and which run you are looking at."));
});

test("Run settings lists the runs under date headings, marks the open one and shows 20 at a time", () => {
  const page = dept();
  const runs = Array.from({length: 25}, (_, i) => ROW(i + 1)).reverse();
  const html = shown(page, runs, runs[0].id);
  assert.equal((html.match(/class="runrow/g) || []).length, 20);
  assert.equal((html.match(/class="runrow cur"/g) || []).length, 1);
  assert.ok(html.includes(`aria-label="Run 25, ${runs[0].id}, done, open now"`) && html.includes("Show 5 more · 5 left"));
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
  const html = shown(page, [ROW(1, {title: "<img src=x onerror=1>", brief: '"quoted" & <b>', output: "prd"})]);
  assert.ok(!html.includes("<img src=x") && !html.includes("<b>") && html.includes("&lt;img src=x onerror=1&gt;"));
  assert.ok(html.includes('d="M6 3h8l4 4v14H6z"'));
});

test("Run settings opens a run by the URL's own parameters: the run set, the tab dropped, the live run by no run at all", () => {
  const page = dept({location: {search: "?view=detail&tab=runsettings"}});
  assert.equal(page.run('runHref("j2-20261104-100004-7f3a")'), "?view=detail&run=j2-20261104-100004-7f3a");
  assert.equal(page.run('runHref("")'), "?view=detail");
  assert.equal(runHarness(RENDER, RENDER_ARGS, {boot: BOOT, location: {pathname: "/d/web/", search: "?run=x"}}).run('runHref("")'), "");
});
