#!/usr/bin/env node
/* test_org2.js -- the new Org screen (19-org2.js, BUILD-PLAN.md phases 0-5):
   registration behind flags.org2, the names-only tree, the strip, the list
   column groups, the charter view with its facet rows, the chart, the states,
   and the rail model changes (Old Org relabel, the org2 destination). Same
   discipline as test_modules.js: run the REAL module under vm with a stub
   context and assert on the real functions.
   Run: node test_org2.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const src = fs.readFileSync(path.join(JS, "19-org2.js"), "utf8");
const orgSrc = fs.readFileSync(path.join(JS, "03-org.js"), "utf8");
const stateSrc = fs.readFileSync(path.join(JS, "01-state.js"), "utf8");
const helpersSrc = fs.readFileSync(path.join(JS, "02-helpers.js"), "utf8");
const loadersSrc = fs.readFileSync(path.join(JS, "07-loaders.js"), "utf8");
const tailSrc = fs.readFileSync(path.join(JS, "09-tail.js"), "utf8");
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
    if (r && typeof r.then === "function") pending.push(r.then(() => console.log("ok   " + name), e => { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e && e.message)); }));
    else console.log("ok   " + name);
  } catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e && e.message)); }
}

const ROOT = { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1 };
const DESK = { ref: "r1", path: "D1", name: "Desktop", parent_ref: "r0", status: "active", ts_minted_ms: 2, cwd: "/Users/x" };
const CO   = { ref: "r2", path: "D2", name: "Asawa Inc.", parent_ref: "r0", status: "active", ts_minted_ms: 3 };
const HOLD = { ref: "r3", path: "D2.D1", name: "Holding Departments", parent_ref: "r2", status: "active", ts_minted_ms: 4 };
const EXP  = { ref: "r4", path: "D2.D1.D1", name: "Experience", parent_ref: "r3", status: "active", ts_minted_ms: 5 };
const ORG  = { ref: "r5", path: "D2.D1.D1.D1", name: "Org", parent_ref: "r4", status: "active", ts_minted_ms: 6 };
const SOS  = { ref: "r6", path: "D2.D2", name: "Sutra OS", parent_ref: "r2", status: "active", ts_minted_ms: 7 };
const OLD  = { ref: "r9", path: "D3", name: "Old", parent_ref: "r0", status: "retired", ts_minted_ms: 8 };
const TREE = [ROOT, DESK, CO, HOLD, EXP, ORG, SOS, OLD];

const DEPT_EXP = {
  ref: "r4", name: "Experience", kind: "department", status: "active",
  parent: { ref: "r3", name: "Holding Departments" },
  address: ["Sutra", "Asawa Inc.", "Holding Departments", "Experience"],
  children: [{ ref: "r5", name: "Org" }],
  charter: { id: "C-1", title: "Experience Charter", purpose: "Own the operator's experience of Sutra Desktop: screens, journeys and the words on them.", status: "active", kind: "standing", scope_in: [] },
  charters: [{ id: "C-2", title: "Org design program", status: "active", kind: "project" }],
  filed: [{ id: "holding/departments/experience/org/HLD.md", kind: "task", label: "HLD", charter_id: "C-1", ts_ms: 10 },
          { id: "a chat about the org screen", kind: "task", label: "a chat about the org screen", charter_id: "C-2", ts_ms: 9 }],
  filed_n: 2,
  docs: [{ path: "holding/departments/experience/org/HLD.md", title: "Org HLD", mtime: 5 }],
  successors: [], ts_minted_ms: 1789000000000, retired_at_ms: null, retire_reason_code: null,
};

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], render: 0, openScreen: [] };
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Promise, encodeURIComponent,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { departments: () => "", charters: () => "", placements: () => "", reorg: () => "", history: () => "", health: () => "" },
    TITLES: { departments: ["Departments", ""] },
    DOMAINS: opts.DOMAINS === undefined ? TREE : opts.DOMAINS,
    CHARTERS: [], PLACEMENTS: [], INDEX: opts.INDEX || [], META: opts.META || {},
    SETTINGS: opts.SETTINGS === undefined ? { flags: { org2: true } } : opts.SETTINGS,
    ICON: { know: "<path d='k'/>", dept: "<path d='d'/>", edit: "<path d='e'/>", plc: "<path d='p'/>" },
    st: (d) => d.status || "active",
    S: Object.assign({ screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } }, opts.S || {}),
    apiGet: opts.apiGet || ((p) => { calls.apiGet.push(p); return new Promise(() => {}); }),
    render: () => { calls.render++; },
    loadOrg: opts.loadOrg || (() => Promise.resolve()),
    simulate: opts.simulate || (() => ({ pending: true })),
    sbPageFromPath: (p) => (/\.md$/.test(p) ? p : null),
    mdHtml: (t) => "<p>" + t + "</p>",
    document: { addEventListener(){}, querySelector(){ return null; }, getElementById(){ return null; } },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}
const sleep = () => new Promise(r => setTimeout(r, 0));

/* ── registration and the flag ── */
test("flag off: nothing registers, the loader is inert", () => {
  const c = fresh({ SETTINGS: { flags: {} } });
  assert.strictEqual(c.org2FlagOn(), false);
  c.o2EnsureRegistered();
  assert.strictEqual(c.SCREENS.org2, undefined);
  assert.strictEqual(c.TITLES.org2, undefined);
  c.loadOrg2(false);
  assert.strictEqual(c.S.o2, undefined, "the loader must not touch state with the flag off");
});
test("flag absent means off (opt-in until plan step 98)", () => {
  const c = fresh({ SETTINGS: null });
  assert.strictEqual(c.org2FlagOn(), false);
});
test("flag on: SCREENS.org2 and TITLES.org2 register together", () => {
  const c = fresh();
  c.o2EnsureRegistered();
  assert.strictEqual(typeof c.SCREENS.org2, "function");
  assert.strictEqual(JSON.stringify(c.TITLES.org2), JSON.stringify(["Org", ""]));
});
test("the six Old Org screen ids are untouched by this module", () => {
  const c = fresh(); c.o2EnsureRegistered();
  for (const id of ["departments", "charters", "placements", "reorg", "history", "health"]) assert.ok(c.SCREENS[id], id);
  assert.ok(!/SCREENS\.(departments|charters|placements|reorg|history|health)\s*=/.test(src), "19-org2.js never reassigns an old screen");
});

/* ── tree ── */
test("tree: names only, no chips, no counts, no paths", () => {
  const c = fresh(); c.o2S().sel = "r4";
  const html = c.o2TreeHtml();
  for (const n of ["Sutra", "Asawa Inc.", "Desktop"]) assert.ok(html.indexOf(n) !== -1, n);
  assert.ok(!/class="chip"/.test(html) && !/navcount/.test(html), "no chip, no count");
  assert.ok(!/D2\.D1/.test(html), "no D-path in the tree");
  assert.ok(html.indexOf("Old") === -1, "retired departments are not in the tree");
});
test("tree: the home opens one level; the selected node and its ancestors open", () => {
  const c = fresh();
  let html = c.o2TreeHtml();
  assert.ok(html.indexOf("Holding Departments") === -1, "two levels down stays closed at rest");
  c.o2Select("r5");
  html = c.o2TreeHtml();
  assert.ok(html.indexOf("Holding Departments") !== -1 && html.indexOf(">Org<") !== -1);
  assert.ok(/data-o2ref="r5"[^>]*aria-selected="true"/.test(html) || /aria-selected="true"[^>]*data-o2ref="r5"/.test(html) || /o2row[^>]*data-o2ref="r5"[^>]*aria-selected="true"/.test(html));
});
test("tree: node kinds -- root and organisation in serif, the machine muted", () => {
  const c = fresh();
  const d = c.o2Data();
  assert.strictEqual(c.o2Kind(ROOT, d), "root");
  assert.strictEqual(c.o2Kind(DESK, d), "machine");
  assert.strictEqual(c.o2Kind(CO, d), "org");
  assert.strictEqual(c.o2Kind(HOLD, d), "dept");
});
test("tree: the hover title carries the address chain", () => {
  const c = fresh(); c.o2Select("r5");
  assert.ok(/title="Sutra › Asawa Inc\. › Holding Departments › Experience › Org"/.test(c.o2TreeHtml()));
});
test("search: non-matching subtrees dim, ancestors of a match stay", () => {
  const c = fresh(); c.o2S().q = "org";
  const html = c.o2TreeHtml();
  assert.ok(/data-o2ref="r5"(?![^>]*dim)/.test(html) || /class="o2row o2k-dept" data-o2ref="r5"/.test(html));
  assert.ok(/class="o2row o2k-machine dim"/.test(html), "Desktop dims under the search");
  assert.ok(!/class="o2row o2k-org dim"/.test(html), "Asawa Inc. is an ancestor of a match and stays");
});

/* ── strip, list, viewer ── */
test("selecting a department fetches its read once and paints the strip", () => {
  const c = fresh();
  c.o2Select("r4"); c.o2Select("r4");
  assert.deepStrictEqual(c.calls.apiGet.filter(p => p.indexOf("/api/org2/department/") === 0), ["/api/org2/department/r4"]);
  const d = c.o2Data();
  const strip = c.o2StripHtml(d.byRef.get("r4"), d, null);
  assert.ok(/<h2>Experience<\/h2>/.test(strip) && /Holding Departments/.test(strip));
  assert.ok(/aria-label="Chart"/.test(strip) && /aria-label="Edit"/.test(strip), "two icons: Chart and the pencil");
});
test("list column: Charter, Departments, Filed work, Other charters, Documents, in that order, names only", () => {
  const c = fresh(); c.o2S().sel = "r4"; c.o2S().dept.r4 = DEPT_EXP; c.o2S().apps.r4 = [];
  const d = c.o2Data();
  const html = c.o2ListHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  const order = ["Charter", "Departments", "Filed work", "Other charters", "Documents"].map(l => html.indexOf(">" + l + "<"));
  assert.ok(order.every(i => i !== -1) && order.every((v, i, a) => i === 0 || v > a[i - 1]), "group order " + order.join(","));
  assert.ok(html.indexOf("Experience Charter") !== -1 && html.indexOf(">HLD<") !== -1 && html.indexOf("Org HLD") !== -1);
  assert.ok(!/experience\/org\/HLD\.md</.test(html), "no path shows as a name");
});
test("list column: more… appears past four names and expands", () => {
  const dept = Object.assign({}, DEPT_EXP, { filed: [1, 2, 3, 4, 5, 6].map(i => ({ id: "f" + i, label: "Filed " + i, charter_id: "C-1", ts_ms: i })) });
  const c = fresh(); c.o2S().sel = "r4"; c.o2S().apps.r4 = [];
  const d = c.o2Data();
  let html = c.o2ListHtml(d.byRef.get("r4"), d, dept, null);
  assert.ok(html.indexOf("Filed 4") !== -1 && html.indexOf("Filed 5") === -1 && /data-o2more="filed"/.test(html));
  c.o2S().more.filed = true;
  html = c.o2ListHtml(d.byRef.get("r4"), d, dept, null);
  assert.ok(html.indexOf("Filed 6") !== -1);
});
test("charter view: the charter first, then the facet rows", () => {
  const c = fresh(); c.o2S().sel = "r4"; c.o2S().dept.r4 = DEPT_EXP;
  const d = c.o2Data();
  const html = c.o2ViewerHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  assert.ok(/charter · standing · active/.test(html));
  assert.ok(html.indexOf("<h1>Experience Charter</h1>") !== -1);
  const rows = ["Address", "Lifecycle", "Relations", "Filed under this charter", "Governance", "Org scope", "Tier reach", "Build layer"].map(l => html.indexOf("<b>" + l + "</b>"));
  assert.ok(rows.every(i => i !== -1) && rows.every((v, i, a) => i === 0 || v > a[i - 1]), "facet order " + rows.join(","));
  assert.ok(html.indexOf("Sutra › Asawa Inc. › Holding Departments › Experience") !== -1, "the address is names");
  assert.ok(html.indexOf("sub-departments: Org") !== -1);
  const filedRow = html.slice(html.indexOf("<b>Filed under this charter</b>"), html.indexOf("<b>Governance</b>"));
  assert.ok(filedRow.indexOf("HLD") !== -1 && filedRow.indexOf("HLD.md") === -1, "filed under this charter lists labels, not paths");
  assert.ok(filedRow.indexOf("a chat about the org screen") === -1, "work filed under another charter stays out of this row");
  assert.strictEqual((html.match(/not sourced yet/g) || []).length, 4, "governance references + three unsourced facets");
  assert.ok(!/one line/.test(html));
});
test("charter view: a one-line charter is marked", () => {
  const dept = Object.assign({}, DEPT_EXP, { charter: Object.assign({}, DEPT_EXP.charter, { purpose: "Asawa org: Experience." }) });
  const c = fresh(); const d = c.o2Data();
  assert.ok(/one line/.test(c.o2ViewerHtml(d.byRef.get("r4"), d, dept, null)));
});
test("no charter: one quiet line, the facets still show", () => {
  const dept = Object.assign({}, DEPT_EXP, { charter: null, filed: [] });
  const c = fresh(); const d = c.o2Data();
  const html = c.o2ViewerHtml(d.byRef.get("r4"), d, dept, null);
  assert.ok(html.indexOf("No charter yet") !== -1 && html.indexOf("<b>Address</b>") !== -1);
  assert.ok(html.indexOf("Filed under this charter") === -1);
});
test("the department read failing: one line and one action, never blank", () => {
  const c = fresh(); const d = c.o2Data();
  const html = c.o2ViewerHtml(d.byRef.get("r4"), d, null, "boom");
  assert.ok(/Sutra did not answer/.test(html) && /Try again/.test(html));
});

/* ── chart, documents, apps ── */
test("chart: this department, its children, up to four grandchildren then an ellipsis", () => {
  const kids = [];
  for (let i = 1; i <= 6; i++) kids.push({ ref: "g" + i, path: "D2.D2.D" + i, name: "Grand " + i, parent_ref: "r6", status: "active", ts_minted_ms: 20 + i });
  const c = fresh({ DOMAINS: TREE.concat(kids) }); c.o2S().view = "chart";
  const d = c.o2Data();
  const html = c.o2ChartHtml(d.byRef.get("r2"), d);
  assert.ok(/o2tile on"[^>]*>Asawa Inc\./.test(html));
  assert.ok(html.indexOf("Holding Departments") !== -1 && html.indexOf("Sutra OS") !== -1);
  assert.ok(html.indexOf("Grand 4") !== -1 && html.indexOf("Grand 5") === -1 && /aria-label="More under Sutra OS"/.test(html));
  assert.ok(!/D2\.D2/.test(html), "no paths on tiles");
});
test("chart of a leaf: one tile and a quiet line", () => {
  const c = fresh(); const d = c.o2Data();
  const html = c.o2ChartHtml(d.byRef.get("r5"), d);
  assert.ok(/Nothing below Org/.test(html));
});
test("a document opens in place through the validator and /api/fs/read", async () => {
  let resolveRead;
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return new Promise(r => { resolveRead = r; }); } });
  c.o2S().sel = "r4";
  c.o2OpenDoc("holding/departments/experience/org/HLD.md", "Org HLD");
  assert.strictEqual(c.calls.apiGet[0], "/api/fs/read?path=holding%2Fdepartments%2Fexperience%2Forg%2FHLD.md");
  let html = c.o2DocHtml(c.o2S().doc);
  assert.ok(/aria-busy="true"/.test(html), "skeleton while reading");
  resolveRead({ text: "# Hello", editable: false, bytes: 7 }); await sleep();
  html = c.o2DocHtml(c.o2S().doc);
  assert.ok(html.indexOf("<p># Hello</p>") !== -1 && html.indexOf("Org HLD") !== -1);
  c.o2OpenDoc("not-a-document.txt");
  assert.strictEqual(c.calls.apiGet.length, 1, "a path the validator refuses is never read");
});
test("a missing document: one line and one action", () => {
  const c = fresh();
  const html = c.o2DocHtml({ path: "gone.md", title: "Gone", text: null, error: "404" });
  assert.ok(/Not on disk anymore/.test(html) && /Show in Changes/.test(html));
});
test("an app opens in the sandboxed page frame; a page without a body says so", () => {
  const c = fresh();
  const html = c.o2AppHtml({ id: "board", name: "Pipeline board", kind: "page", has_page: true });
  assert.ok(/<iframe class="o2frame" src="\/api\/modules\/board\/page\?theme=dark" [^>]*sandbox="allow-scripts"/.test(html));
  assert.ok(/Nothing to show yet/.test(c.o2AppHtml({ id: "x", name: "X", kind: "page", has_page: false })));
});

/* ── states ── */
test("offline: the last names stay dimmed and one line offers Retry", async () => {
  const c = fresh({ loadOrg: () => Promise.reject(new Error("ECONNREFUSED")) });
  c.o2EnsureRegistered();
  await c.loadOrg2(false);
  const html = c.SCREENS.org2();
  assert.ok(/Sutra is not reachable/.test(html) && /data-o2act="retry"/.test(html));
  assert.ok(/class="o2 off"/.test(html) && html.indexOf("Asawa Inc.") !== -1);
});
test("first run: no departments, one quiet line", () => {
  const c = fresh({ DOMAINS: [] }); c.o2EnsureRegistered();
  c.o2S().loaded = true;
  const html = c.SCREENS.org2();
  assert.ok(/No departments yet/.test(html));
});
test("loading: skeleton names, never a blank pane", () => {
  const c = fresh({ DOMAINS: [] }); c.o2EnsureRegistered();
  c.o2S().loading = true;
  assert.ok(/aria-busy="true"/.test(c.SCREENS.org2()));
});
test("the pencil menu holds Changes, Approvals, Health; Escape closes it", () => {
  const c = fresh(); c.o2S().menu = true;
  const html = c.o2MenuHtml();
  for (const item of ["Changes", "Approvals", "Health"]) assert.ok(html.indexOf(">" + item + "<") !== -1, item);
  assert.ok(!/Details/.test(html));
});
test("changes panel: events of the subtree only, names not refs, empty says so", () => {
  const INDEXES = [
    { ref: "r5", event: "domain_minted", name: "Org", ts_ms: 1789000000000 },
    { ref: "r6", event: "domain_minted", name: "Sutra OS", ts_ms: 1789000001000 },
  ];
  const c = fresh({ INDEX: INDEXES }); const d = c.o2Data();
  let html = c.o2ChangesHtml(d.byRef.get("r4"), d);
  assert.ok(html.indexOf("Org created") !== -1 && html.indexOf("Sutra OS") === -1 && html.indexOf("r5") === -1);
  html = c.o2ChangesHtml(d.byRef.get("r1"), d);
  assert.ok(/No changes yet/.test(html));
});
test("health panel: checking while the simulation is pending; nothing flagged reads as all clear", () => {
  const c = fresh(); const d = c.o2Data();
  assert.ok(/Checking/.test(c.o2HealthHtml(d.byRef.get("r4"), d)));
  const c2 = fresh({ simulate: () => ({ pending: false, error: null, findings: [{ code: "ORG-001", sev: "warn", subject: "Sutra OS overlaps Native" }] }) });
  const d2 = c2.o2Data();
  assert.ok(/Nothing flagged for Experience/.test(c2.o2HealthHtml(d2.byRef.get("r4"), d2)));
  assert.ok(/Sutra OS overlaps Native/.test(c2.o2HealthHtml(d2.byRef.get("r6"), d2)));
});
test("approvals panel: nothing waiting, decided rows with a pill", () => {
  const c = fresh({ S: { props: [{ id: "p1", kind: "routine.create", summary: "weekly review", status: "approved" }] } });
  const html = c.o2ApprovalsHtml();
  assert.ok(/Nothing waiting/.test(html) && /weekly review/.test(html) && /p-ok">approved/.test(html));
});

/* ── rail model and wiring pins (source reads, like test_nav's pins) ── */
test("rail: the old destination reads Old Org and the new one reads Org", () => {
  assert.ok(/org:\s*"Old Org"/.test(helpersSrc), "DEST_LABEL.org");
  assert.ok(/org2:\s*"Org"/.test(helpersSrc), "DEST_LABEL.org2");
  assert.ok(/org2:\s*"dept"/.test(helpersSrc), "DEST_ICON.org2");
});
test("rail model: org2 sits before org in DESTS, is full-bleed, lands on its own screen", () => {
  const m = stateSrc.match(/const DESTS = \[([^\]]*)\]/);
  assert.ok(m, "DESTS found");
  const dests = m[1].split(",").map(s => s.trim().replace(/"/g, ""));
  assert.ok(dests.indexOf("org2") !== -1 && dests.indexOf("org2") < dests.indexOf("org"));
  assert.ok(/org2:\s*\[\]/.test(stateSrc), "DEST_PLANES.org2 is empty (full-bleed)");
  assert.ok(/org2:\s*"org2"/.test(stateSrc), "DEST_DEFAULT_SCREEN.org2");
});
test("rail: renderRail hides org2 while the flag is off and registers the screen first", () => {
  const body = helpersSrc.slice(helpersSrc.indexOf("function renderRail"), helpersSrc.indexOf("function renderRail") + 1600);
  assert.ok(/o2EnsureRegistered/.test(body) && /org2FlagOn/.test(body));
});
test("open path: openScreen redirects org2 to Old Org while the flag is off and hooks the loader", () => {
  const body = loadersSrc.slice(loadersSrc.indexOf("function openScreen"), loadersSrc.indexOf("function openScreen") + 4000);
  assert.ok(/id === "org2"\)\{[\s\S]{0,400}org2FlagOn[\s\S]{0,120}id = "departments"/.test(body), "redirect");
  assert.ok(/loadOrg2/.test(body), "loader hook");
  const redirectAt = body.indexOf('id === "org2"'), checkAt = body.indexOf("if (!id || !SCREENS[id]) return;");
  assert.ok(redirectAt !== -1 && checkAt !== -1 && redirectAt < checkAt, "the redirect runs before the SCREENS check");
});
test("boot restore falls back when the destination's default screen is not registered", () => {
  assert.ok(/SCREENS\[DEST_DEFAULT_SCREEN\[S\.ui\.dest\]\]/.test(tailSrc) || /dflt && SCREENS\[dflt\]/.test(tailSrc));
});
test("panel.html loads 19-org2.js before 09-tail.js", () => {
  const a = panelHtml.indexOf('<script src="/static/js/19-org2.js'), b = panelHtml.indexOf('<script src="/static/js/09-tail.js');
  assert.ok(a !== -1 && b !== -1 && a < b, "the module tag precedes the boot tag");
});
test("panel.css carries a scoped .o2 block with tokens only", () => {
  const start = css.indexOf("/* ── Org (org2");
  assert.ok(start !== -1, "block present");
  const block = css.slice(start);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(block.replace(/var\(--[a-z-]+\)/g, "")), "no literal colours in the .o2 block");
  assert.ok(/data-o2q/.test(fs.readFileSync(path.join(JS, "06-render.js"), "utf8")), "the search input keeps focus across a re-render");
});

Promise.all(pending).then(() => {
  console.log(`\n${ran - failed}/${ran} passed`);
  process.exit(failed ? 1 : 0);
});
