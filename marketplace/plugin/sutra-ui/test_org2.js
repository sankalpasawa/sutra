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
  const calls = { apiGet: [], apiPost: [], render: 0, openScreen: [] };
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Promise, encodeURIComponent, setTimeout, clearTimeout,
    apiPost: opts.apiPost || ((p, body) => { calls.apiPost.push({ p, body }); return Promise.resolve({}); }),
    window: opts.window || {},
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
test("flag off (flags.org2: false): nothing registers, the loader is inert", () => {
  const c = fresh({ SETTINGS: { flags: { org2: false } } });
  assert.strictEqual(c.org2FlagOn(), false);
  c.o2EnsureRegistered();
  assert.strictEqual(c.SCREENS.org2, undefined);
  assert.strictEqual(c.TITLES.org2, undefined);
  c.loadOrg2(false);
  assert.strictEqual(c.S.o2, undefined, "the loader must not touch state with the flag off");
});
test("flag absent means ON (plan step 98, 2.278.0): only an explicit false hides the screen", () => {
  assert.strictEqual(fresh({ SETTINGS: null }).org2FlagOn(), true, "no settings yet");
  assert.strictEqual(fresh({ SETTINGS: { flags: {} } }).org2FlagOn(), true, "no flag");
  assert.strictEqual(fresh({ SETTINGS: { flags: { org2: "no" } } }).org2FlagOn(), true, "a non-false value does not hide it");
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
  assert.strictEqual((html.match(/data-o2act="editcharter"/g) || []).length, 1, "one action: Write the charter");
});
test("edit charter: the sheet is prefilled, refuses no change, files org.charter by succession", async () => {
  const c = fresh(); c.loadProposals = () => {};
  c.o2Select("r4"); c.o2S().dept.r4 = DEPT_EXP;
  c.o2OpenSheet("charter");
  const sh = c.o2S().sheet;
  assert.strictEqual(sh.name, "Experience Charter"); assert.strictEqual(sh.charterId, "C-1");
  assert.ok(/^Own the operator/.test(sh.purpose));
  const d = c.o2Data();
  let html = c.o2SheetHtml(d.byRef.get("r4"), d);
  assert.ok(/<h1>Edit charter<\/h1>/.test(html) && /data-o2spurpose/.test(html) && /value="Experience Charter"/.test(html));
  await c.o2SendRequest();
  assert.strictEqual(c.calls.apiPost.length, 0); assert.strictEqual(sh.error, "Nothing changed");
  sh.purpose = "Own the operator's experience of Sutra Desktop, end to end.";
  await c.o2SendRequest();
  /* PIN MOVED (slice G, DS-1): the request now carries the charter's own two
     extra records. Empty here because this charter has neither -- absent would
     mean "the sheet said nothing", and the writer would keep the prior value. */
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0].body)),
    { kind: "org.charter", args: { ref: "r4", charter_id: "C-1", title: "Experience Charter", purpose: "Own the operator's experience of Sutra Desktop, end to end.", done_when: [], rules: [] } });
  /* no charter yet: the sheet writes one, title defaulted from the name, no charter_id */
  const c2 = fresh(); c2.loadProposals = () => {};
  c2.o2Select("r4"); c2.o2S().dept.r4 = Object.assign({}, DEPT_EXP, { charter: null });
  c2.o2OpenSheet("charter");
  assert.ok(/<h1>Write the charter<\/h1>/.test(c2.o2SheetHtml(c2.o2Data().byRef.get("r4"), c2.o2Data())));
  await c2.o2SendRequest();
  assert.strictEqual(c2.o2S().sheet.error, "A purpose is needed");
  c2.o2S().sheet.purpose = "  Everything the operator sees.  ";
  await c2.o2SendRequest();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c2.calls.apiPost[0].body)),
    { kind: "org.charter", args: { ref: "r4", charter_id: null, title: "Experience Charter", purpose: "Everything the operator sees.", done_when: [], rules: [] } });
});
/* ── DS-1: the sheet's two new fields ─────────────────────────────────────── */
test("S-G/DS-1: the charter sheet carries Done when and tagged rules, and files them", async () => {
  const c = fresh(); c.loadProposals = () => {};
  c.o2Select("r4");
  c.o2S().dept.r4 = Object.assign({}, DEPT_EXP, {
    charter: Object.assign({}, DEPT_EXP.charter, {
      done_when: ["every screen reads its own record"],
      rules: [{ tag: "refuse", line: "Never a third AI in one task" }] }) });
  c.o2OpenSheet("charter");
  const sh = c.o2S().sheet;
  assert.strictEqual(sh.done, "every screen reads its own record", "prefilled, one line per row");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(sh.rules)), [{ tag: "refuse", line: "Never a third AI in one task" }]);
  const d = c.o2Data();
  const html = c.o2SheetHtml(d.byRef.get("r4"), d);
  assert.ok(/data-o2sdone/.test(html), "the sheet has a Done when field");
  assert.ok(/data-o2srtag="0"/.test(html) && /data-o2srline="0"/.test(html), "one row per rule");
  assert.ok(/<option value="refuse" selected>/.test(html), "the row's tag is the one on the record");
  for (const t of ["go", "ask", "refuse", "always"]) assert.ok(html.indexOf(`<option value="${t}"`) !== -1, t + " is offered");
  assert.ok(/data-o2act="addrule"/.test(html), "a rule is added, never typed as a tag");
  /* nothing changed: the same title, purpose, done lines and rules */
  await c.o2SendRequest();
  assert.strictEqual(c.calls.apiPost.length, 0); assert.strictEqual(sh.error, "Nothing changed");
  /* one more rule, a blank row dropped, and the whole set rides the request */
  c.o2AddRule(); c.o2AddRule();
  c.o2S().sheet.rules[1].tag = "ask"; c.o2S().sheet.rules[1].line = "  Ask before a push  ";
  c.o2S().sheet.done = "every screen reads its own record\n\n  the words are the D78 words  ";
  await c.o2SendRequest();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0].body.args.done_when)),
    ["every screen reads its own record", "the words are the D78 words"]);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0].body.args.rules)),
    [{ tag: "refuse", line: "Never a third AI in one task" }, { tag: "ask", line: "Ask before a push" }],
    "the empty third row is not a rule");
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
  const c = fresh(); c.o2S().appOk.board = true;
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
test("rail: one Org destination, labelled Org; no org2 label or icon of its own (2.287.2)", () => {
  const labels = helpersSrc.match(/const DEST_LABEL[\s\S]*?\};/)[0];
  assert.ok(/org:\s*"Org"/.test(labels), "DEST_LABEL.org");
  assert.ok(!/Old Org/.test(labels), "no Old Org label");
  assert.ok(!/org2:/.test(labels), "no DEST_LABEL.org2");
});
test("rail model: org2 is not a destination; it is the Org accordion's first row, Org structure, opt-out by flag", () => {
  const m = stateSrc.match(/const DESTS = \[([^\]]*)\]/);
  assert.ok(m, "DESTS found");
  const dests = m[1].split(",").map(s => s.trim().replace(/"/g, ""));
  assert.strictEqual(dests.indexOf("org2"), -1, "org2 left DESTS");
  assert.ok(/org:\s*\[[\s\S]*?\{screen:"org2",\s*label:"Org structure",\s*flag:"org2"\}/.test(stateSrc), "first row of DEST_PLANES.org");
  assert.ok(!/org2:\s*"org2"/.test(stateSrc), "no DEST_DEFAULT_SCREEN.org2");
});
test("rail: renderRail registers the screen before painting; goDest lands Org on org2 when registered", () => {
  const body = helpersSrc.slice(helpersSrc.indexOf("function renderRail"), helpersSrc.indexOf("function renderRail") + 1600);
  assert.ok(/o2EnsureRegistered/.test(body));
  const go = helpersSrc.slice(helpersSrc.indexOf("function goDest"), helpersSrc.indexOf("function goDest") + 2200);
  assert.ok(/d === "org"\)\{[\s\S]{0,200}o2EnsureRegistered[\s\S]{0,120}fallback = "org2"/.test(go), "Org lands on Org structure");
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
/* ── slice B: alone on the row, the editor, filter, search, requests, page, health ── */
const renderSrc = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");
const apiSrc = fs.readFileSync(path.join(__dirname, "org_api.py"), "utf8");
const propSrc = fs.readFileSync(path.join(__dirname, "proposals.py"), "utf8");
test("the screen opens alone: soloScreen names org2 and the pane takes the row", () => {
  const solo = renderSrc.slice(renderSrc.indexOf("const soloScreen"), renderSrc.indexOf("const soloScreen") + 200);
  assert.ok(/S\.screen === "org2"/.test(solo), "soloScreen");
  assert.ok(/classList\.toggle\("o2wide"/.test(renderSrc), "the o2wide class");
  assert.ok(/\.pane\.browse\.o2wide\{flex:1 1 100%/.test(css), "panel.css gives it the row");
  assert.ok(/wireOrg2/.test(loadersSrc), "wire() calls the per-paint hook");
});
test("an editable document emits the editor container; a conflict offers Reload only", () => {
  const c = fresh();
  let html = c.o2DocHtml({ path: "a.md", title: "A", text: "# A", editable: true, bytes: 3, conflict: false, saveState: null });
  assert.ok(/data-o2editor/.test(html) && !/ws-mdbody/.test(html));
  html = c.o2DocHtml({ path: "a.md", title: "A", text: "# A", editable: true, bytes: 3, conflict: true, saveState: "failed" });
  assert.ok(/Changed in another session/.test(html) && /data-o2act="reload"/.test(html));
  assert.strictEqual((html.match(/data-o2act="reload"/g) || []).length, 1, "one action");
  html = c.o2DocHtml({ path: "a.md", title: "A", text: "# A", editable: false });
  assert.ok(/ws-mdbody/.test(html), "read-only renders the text");
});
test("wireOrg2 mounts the Workspace editor once, re-attaches the live view, tears down off-screen", async () => {
  const mounts = [], destroyed = [], appended = [];
  const handle = { view: { dom: { isConnected: false } }, forceSave(){}, destroy(){ destroyed.push(1); } };
  const el = { isConnected: true, appendChild(x){ appended.push(x); } };
  const win = { SutraEditor: { mount(o){ mounts.push(o); return handle; } } };
  const c = fresh({ window: win });
  c.wsLoadEditorScript = () => Promise.resolve();
  c.o2S().sel = "r4"; c.o2S().view = "doc";
  c.o2S().doc = { path: "a.md", title: "A", text: "# A", editable: true, bytes: 3, conflict: false, saveState: null };
  const scBody = { querySelector: () => el };
  c.wireOrg2(scBody); await sleep(); await sleep();
  assert.strictEqual(mounts.length, 1, "mounted once");
  assert.strictEqual(mounts[0].path, "a.md");
  assert.strictEqual(mounts[0].readOnly, false);
  c.wireOrg2(scBody);
  assert.strictEqual(mounts.length, 1, "no second mount while the handle lives");
  assert.strictEqual(appended.length, 1, "the live view is moved back into the new container");
  c.S.screen = "chats"; c.wireOrg2(scBody);
  assert.strictEqual(destroyed.length, 1, "leaving the screen destroys the editor");
  assert.strictEqual(c.o2S().edHandle, null);
});
test("saving goes through /api/fs/write with the bytes read; a 409 marks the conflict", async () => {
  const posts = [];
  let fail = false;
  const c = fresh({ apiPost: (p, body) => { posts.push({ p, body }); if (fail){ const e = new Error("changed"); e.status = 409; return Promise.reject(e); } return Promise.resolve({ bytes: 9 }); },
                    window: { SutraEditor: { mount(o){ c._opts = o; return { view: {}, forceSave(){}, destroy(){} }; } } } });
  c.wsLoadEditorScript = () => Promise.resolve();
  c.o2S().sel = "r4"; c.o2S().view = "doc";
  const doc = { path: "a.md", title: "A", text: "# A", editable: true, bytes: 3, conflict: false, saveState: null };
  c.o2S().doc = doc;
  await c.o2MountEditor({ isConnected: true });
  await c._opts.save("# A!");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(posts[0])), { p: "/api/fs/write", body: { path: "a.md", text: "# A!", base_bytes: 3 } });
  assert.strictEqual(doc.bytes, 9);
  fail = true;
  let threw = false;
  try { await c._opts.save("# A!!"); } catch (e) { threw = true; }
  assert.ok(threw && doc.conflict === true, "409 -> conflict, and the editor learns the save failed");
});
test("the funnel: chips, one server call, matching subtrees stay and the rest dim", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ refs: ["r2"], n: 1 }); } });
  c.o2S().filter.open = true;
  let html = c.o2SearchHtml();
  for (const l of ["Organisations", "Departments", "Machine", "Active", "No charter", "One-line charter"]) assert.ok(html.indexOf(">" + l + "<") !== -1, l);
  c.o2S().filter.kind.push("organisation");
  await c.o2ApplyFilter();
  assert.ok(c.calls.apiGet.some(p => p === "/api/org2/filter?kind=organisation&state="));
  html = c.o2TreeHtml();
  assert.ok(/class="o2row o2k-machine dim"/.test(html), "Desktop dims");
  assert.ok(/class="o2row o2k-dept dim"[^>]*data-o2ref="r3"/.test(html), "a department outside the answer dims");
  assert.ok(!/class="o2row o2k-org dim"/.test(html), "the matching organisation stays");
  assert.ok(/aria-pressed="true"/.test(c.o2SearchHtml()), "the funnel lights up");
  c.o2S().filter.kind = []; await c.o2ApplyFilter();
  assert.strictEqual(c.o2S().filter.refs, null, "cleared without a call");
});
test("search: server hits join the name match", async () => {
  const c = fresh({ apiGet: (p) => { c.calls.apiGet.push(p); return Promise.resolve({ refs: ["r6"], n: 1 }); } });
  c.o2S().q = "lending";
  await c.o2SearchServer();
  assert.ok(c.calls.apiGet.indexOf("/api/org2/search?q=lending") !== -1);
  const html = c.o2TreeHtml();
  assert.ok(/data-o2ref="r6"/.test(html) && !/class="o2row o2k-dept dim"[^>]*data-o2ref="r6"/.test(html), "the hit stays");
  assert.ok(/class="o2row o2k-machine dim"/.test(html));
});
test("the pencil menu: Rename, Move, New sub-department above the three views; the root and the machine lose what they cannot do", () => {
  const c = fresh(); const d = c.o2Data(); c.o2S().dept.r4 = DEPT_EXP;
  let html = c.o2MenuHtml(d.byRef.get("r4"), d);
  const order = ["Edit charter…", "Rename…", "Move…", "New sub-department…", "Changes", "Approvals", "Health"].map(l => html.indexOf(">" + l + "<"));
  assert.ok(order.every(i => i !== -1) && order.every((v, i, a) => i === 0 || v > a[i - 1]), order.join(","));
  html = c.o2MenuHtml(d.byRef.get("r0"), d);
  assert.ok(html.indexOf("Rename") === -1 && html.indexOf("Move") === -1 && html.indexOf("New sub-department") !== -1);
  assert.ok(html.indexOf("Write the charter…") !== -1, "no charter read yet: the item offers to write one");
  html = c.o2MenuHtml(d.byRef.get("r1"), d);
  assert.ok(html.indexOf("Rename") !== -1 && html.indexOf("Move…") === -1);
});
test("rename: the sheet files org.rename, then Approvals opens with one line", async () => {
  const c = fresh({ apiPost: (p, body) => { c.calls.apiPost.push({ p, body }); return Promise.resolve({ summary: "Rename Experience to Experience Design" }); } });
  c.loadProposals = () => {};
  c.o2Select("r4"); c.o2OpenSheet("rename");
  let html = c.o2SheetHtml(c.o2Data().byRef.get("r4"), c.o2Data());
  assert.ok(/<h1>Rename<\/h1>/.test(html) && /value="Experience"/.test(html) && /data-o2act="request"/.test(html));
  await c.o2SendRequest();
  assert.strictEqual(c.calls.apiPost.length, 0, "the current name is not a request");
  assert.ok(/current name/.test(c.o2S().sheet.error));
  c.o2S().sheet.name = "Experience Design";
  await c.o2SendRequest();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0])), { p: "/api/org2/request", body: { kind: "org.rename", args: { ref: "r4", name: "Experience Design" } } });
  assert.strictEqual(c.o2S().sheet, null);
  assert.strictEqual(c.o2S().panel, "approvals");
  assert.ok(/Waiting for approval · Rename Experience to Experience Design/.test(c.o2S().flash));
  assert.ok(/Waiting for approval/.test(c.SCREENS.org2 ? c.o2ScreenHtml() : c.o2ScreenHtml()));
});
test("move: targets exclude the subtree and the current parent; the preview shows only what the move adds", () => {
  const OLD = { code: "ORG-020", sev: "warn", subject: "Sutra Charter is homed to retired Sutra" };
  const NEW = { code: "ORG-004", sev: "warn", subject: "Experience is deeper than four" };
  const c = fresh({ simulate: (ops) => { if (ops.length) c._ops = ops; return { pending: false, error: null, findings: ops.length ? [OLD, NEW, NEW, OLD] : [OLD] }; } });
  c.o2Select("r4"); c.o2OpenSheet("move");
  const d = c.o2Data();
  const refs = c.o2MoveTargets(d.byRef.get("r4"), d).map(t => t.ref);
  for (const r of ["r4", "r5", "r3"]) assert.ok(refs.indexOf(r) === -1, r + " is out");
  for (const r of ["r0", "r1", "r2", "r6"]) assert.ok(refs.indexOf(r) !== -1, r + " is in");
  c.o2S().sheet.target = "r6";
  const html = c.o2SheetHtml(d.byRef.get("r4"), d);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c._ops)), [{ op: "move", ref: "r4", target: "r6" }]);
  assert.ok(/Experience is deeper than four/.test(html) && !/Apply/.test(html));
  assert.ok(html.indexOf("homed to retired") === -1, "a finding true before the move is not the move's");
  assert.strictEqual((html.match(/deeper than four/g) || []).length, 1, "duplicates collapse");
  const c2 = fresh({ simulate: (ops) => ({ pending: false, error: null, findings: [OLD] }) });
  c2.o2Select("r4"); c2.o2OpenSheet("move"); c2.o2S().sheet.target = "r6";
  assert.ok(/Nothing in the way/.test(c2.o2SheetHtml(c2.o2Data().byRef.get("r4"), c2.o2Data())));
});
test("new sub-department: the sheet files org.create under the selected department", async () => {
  const c = fresh(); c.loadProposals = () => {};
  c.o2Select("r4"); c.o2OpenSheet("create");
  c.o2S().sheet.name = "  Design  ";
  await c.o2SendRequest();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0].body)), { kind: "org.create", args: { parent: "r4", name: "Design" } });
});
test("a filed .html opens in the sandboxed frame from /api/org2/page", () => {
  const c = fresh(); c.o2S().sel = "r4";
  c.o2OpenPage("holding/website/org.html", "Org page");
  const html = c.o2PageHtml(c.o2S().page);
  assert.ok(/<iframe class="o2frame" src="\/api\/org2\/page\?path=holding%2Fwebsite%2Forg\.html&amp;theme=dark" [^>]*sandbox="allow-scripts"/.test(html));
  c.o2OpenPage("notes.txt");
  assert.strictEqual(c.o2S().page.path, "holding/website/org.html", "only an html path opens as a page");
});
test("health: the server's charter findings, as names that open the department", () => {
  const c = fresh({ simulate: () => ({ pending: false, error: null, findings: [] }) });
  const d = c.o2Data();
  let html = c.o2HealthHtml(d.byRef.get("r4"), d);
  assert.ok(c.calls.apiGet.indexOf("/api/org2/health/r4") !== -1, "asked once");
  assert.ok(/Checking/.test(html));
  c.o2S().health.r4 = { data: { unowned: [{ ref: "r5", name: "Org" }], one_line: [{ ref: "r4", name: "Experience", title: "Experience Charter" }], overlaps: [{ a: "Org", b: "Org design", similarity: 0.6 }] }, error: null };
  html = c.o2HealthHtml(d.byRef.get("r4"), d);
  assert.ok(/No charter: <button[^>]*data-o2ref="r5"[^>]*>Org<\/button>/.test(html));
  assert.ok(/One line: /.test(html) && /Org and Org design overlap/.test(html));
  c.o2S().health.r4 = { data: { unowned: [], one_line: [], overlaps: [] }, error: null };
  assert.ok(/Every department under Experience has a charter/.test(c.o2HealthHtml(d.byRef.get("r4"), d)));
  c.o2S().health.r4 = { data: null, error: "boom" };
  assert.ok(/data-o2act="healthretry"/.test(c.o2HealthHtml(d.byRef.get("r4"), d)));
});
test("the request kinds are proposal kinds and the applier routes them to org2_apply", () => {
  for (const k of ["org.rename", "org.move", "org.create"]) assert.ok(propSrc.indexOf('"' + k + '"') !== -1, k);
  const ap = apiSrc.slice(apiSrc.indexOf("def _apply_proposal"), apiSrc.indexOf("def _apply_proposal") + 1600);
  assert.ok(/org2_apply\.apply_request/.test(ap));
  assert.ok(!/import org2_apply|from org2_apply/.test(fs.readFileSync(path.join(__dirname, "org2_api.py"), "utf8")), "the read module never imports the applier");
});
/* ── slice C: stored node kind, keyboard, Recent, unsaved chip, app probe ── */
test("the tree is the whole registry from the D76 root, not the role's scoped slice", () => {
  const c = fresh({ DOMAINS: [CO, HOLD, EXP, ORG, SOS] });     /* what scopeOrgForRole leaves in DOMAINS */
  assert.strictEqual(c.o2Data().root.ref, "r2", "without ORG_ALL the scoped slice is all there is");
  c.ORG_ALL = { domains: TREE.concat([{ ref: "s1", path: "D9", name: "Stray", parent_ref: null, status: "active", ts_minted_ms: 99 }]), charters: [], placements: [] };
  const d = c.o2Data();
  assert.strictEqual(d.root.ref, "r0", "the rooted tree wins over a childless stray root");
  assert.deepStrictEqual(JSON.parse(JSON.stringify((d.kids.get("r0") || []).map(x => x.name))), ["Desktop", "Asawa Inc."], "root children in path order, retired hidden");
  assert.ok(!d.byRef.has("r9"), "retired rows never enter the tree");
  const html = c.o2TreeHtml();
  assert.ok(html.indexOf(">Sutra<") !== -1 && html.indexOf(">Desktop<") !== -1, "the home shows the root and its level");
});
test("node kind: the engine's stored field wins over the interim rule", () => {
  const rows = TREE.map(x => Object.assign({}, x));
  rows[1].node_kind = "organisation";          /* Desktop renamed and re-kinded by the engine */
  rows[2].node_kind = "machine";
  const c = fresh({ DOMAINS: rows }); const d = c.o2Data();
  assert.strictEqual(c.o2Kind(d.byRef.get("r1"), d), "org");
  assert.strictEqual(c.o2Kind(d.byRef.get("r2"), d), "machine");
  assert.strictEqual(c.o2Kind(d.byRef.get("r3"), d), "dept", "no field: the interim rule");
  assert.strictEqual(c.o2Kind(Object.assign({}, ROOT, { node_kind: "planet" }), d), "root", "an unknown value falls back");
});
test("keyboard: arrows walk the visible rows, right expands then descends, left collapses then climbs", () => {
  const c = fresh(); const d = c.o2Data(); const ex = c.o2Expanded();   /* home open: r0 > r1 r2 r9? (retired hidden) */
  let vis = c.o2VisibleRefs(d, ex);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(vis)), ["r0", "r1", "r2"]);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("ArrowDown", "r0", vis, d, ex))), { focus: "r1" });
  assert.strictEqual(c.o2TreeKey("ArrowUp", "r0", vis, d, ex), null);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("End", "r0", vis, d, ex))), { focus: "r2" });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("ArrowRight", "r2", vis, d, ex))), { toggle: "r2", open: true });
  ex.add("r2"); vis = c.o2VisibleRefs(d, ex);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("ArrowRight", "r2", vis, d, ex))), { focus: "r3" }, "open: descend");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("ArrowLeft", "r2", vis, d, ex))), { toggle: "r2", open: false });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("ArrowLeft", "r3", vis, d, ex))), { focus: "r2" }, "leaf-like: climb");
  assert.strictEqual(c.o2TreeKey("ArrowRight", "r1", vis, d, ex), null, "a leaf has nowhere to go");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.o2TreeKey("Enter", "r3", vis, d, ex))), { select: "r3" });
  assert.strictEqual(c.o2TreeKey("x", "r3", vis, d, ex), null);
});
test("focus asked for by the keyboard is restored after the paint", () => {
  const focused = [];
  const c = fresh(); c.o2S().focusRef = "r2";
  const row = { focus(){ focused.push("r2"); } };
  c.wireOrg2({ querySelector: (sel) => (/data-o2ref="r2"/.test(sel) ? row : null) });
  assert.deepStrictEqual(focused, ["r2"]);
  assert.strictEqual(c.o2S().focusRef, null, "used once");
});
test("Recent: the last things opened in a department, newest first, one row each, capped", async () => {
  const c = fresh({ apiGet: () => Promise.resolve({ text: "x", editable: false, bytes: 1 }) });
  c.o2S().sel = "r4"; c.o2S().dept.r4 = DEPT_EXP; c.o2S().apps.r4 = [];
  await c.o2OpenDoc("a.md", "A"); await c.o2OpenDoc("b.md", "B"); await c.o2OpenDoc("a.md", "A");
  c.o2OpenPage("p.html", "P"); c.o2OpenApp({ id: "board", name: "Board", kind: "chat" });
  const rec = c.o2S().recent.r4;
  assert.deepStrictEqual(JSON.parse(JSON.stringify(rec.map(r => r.title))), ["Board", "P", "A", "B"], "cap of four, newest first, A once");
  const d = c.o2Data();
  const html = c.o2ListHtml(d.byRef.get("r4"), d, DEPT_EXP, null);
  const order = ["Charter", "Recent", "Departments"].map(l => html.indexOf(">" + l + "<"));
  assert.ok(order.every(i => i !== -1) && order[0] < order[1] && order[1] < order[2], "Recent sits between Charter and Departments");
  const recent = html.slice(html.indexOf(">Recent<"), html.indexOf(">Departments<"));
  assert.ok(/data-o2app="board"/.test(recent) && /data-o2filed="p\.html"/.test(recent) && /data-o2doc="a\.md"/.test(recent));
  assert.ok(!/a\.md</.test(recent), "names, not paths");
  const c2 = fresh(); assert.ok(c2.o2ListHtml(c2.o2Data().byRef.get("r4"), c2.o2Data(), DEPT_EXP, null).indexOf(">Recent<") === -1, "nothing opened: no group");
});
test("unsaved chip: hidden at rest, shown by onDirty without a paint, cleared on save", async () => {
  const c = fresh({ window: { SutraEditor: { mount(o){ c._opts = o; return { view: {}, forceSave(){}, destroy(){} }; } } } });
  c.wsLoadEditorScript = () => Promise.resolve();
  const chip = { hidden: true };
  c.document.querySelector = (sel) => (/data-o2dirty/.test(sel) ? chip : null);
  c.o2S().sel = "r4"; c.o2S().view = "doc";
  const doc = { path: "a.md", title: "A", text: "# A", editable: true, bytes: 3, conflict: false, saveState: null, dirty: false };
  c.o2S().doc = doc;
  let html = c.o2DocHtml(doc);
  assert.ok(/data-o2dirty hidden>unsaved</.test(html), "hidden at rest");
  await c.o2MountEditor({ isConnected: true });
  const renders = c.calls.render;
  c._opts.onDirty(true);
  assert.strictEqual(chip.hidden, false); assert.strictEqual(c.calls.render, renders, "no paint per keystroke");
  assert.ok(/data-o2dirty>unsaved</.test(c.o2DocHtml(doc)), "a later paint keeps it");
  c._opts.onSaveState("saved");
  assert.strictEqual(chip.hidden, true); assert.strictEqual(doc.dirty, false);
});
test("an app page is asked for first: a 200 gets the frame, anything else says so with Retry", async () => {
  const seen = [];
  let ok = false;
  const c = fresh(); c.fetch = (url, opts) => { seen.push({ url, h: opts && opts.headers }); return Promise.resolve({ ok }); };
  c.panelToken = () => "tok"; c.API = "";
  const m = { id: "board", name: "Board", kind: "page", has_page: true };
  c.o2S().sel = "r4";
  c.o2OpenApp(m);
  assert.ok(/aria-busy="true"/.test(c.o2AppHtml(m)), "asking");
  await sleep();
  assert.strictEqual(seen[0].url, "/api/modules/board/page"); assert.strictEqual(seen[0].h["X-Sutra-Panel"], "tok");
  let html = c.o2AppHtml(m);
  assert.ok(/Nothing to show yet/.test(html) && /data-o2act="appretry"/.test(html) && !/<iframe/.test(html));
  ok = true; delete c.o2S().appOk.board; await c.o2ProbeApp(m);
  assert.ok(/<iframe class="o2frame"/.test(c.o2AppHtml(m)));
  assert.strictEqual(seen.length, 2, "one probe per open, not per paint");
});
test("stale registry: a department read at another history length shows one line; Refresh reloads and clears it", async () => {
  let lines = 7, loads = 0;
  const c = fresh({ META: { domain_index_lines: 7 },
                    apiGet: (p) => Promise.resolve(Object.assign({}, DEPT_EXP, { index_lines: lines })),
                    loadOrg: () => { loads++; return Promise.resolve(); } });
  c.o2EnsureRegistered();
  await c.loadOrg2(false);
  c.o2Select("r4"); await sleep();
  assert.ok(!c.o2S().stale && !/The registry changed/.test(c.SCREENS.org2()), "same length: quiet");
  lines = 9;
  c.o2Select("r5"); await sleep();
  assert.strictEqual(c.o2S().stale, true);
  const html = c.SCREENS.org2();
  assert.ok(/The registry changed/.test(html) && /data-o2act="retry"/.test(html));
  assert.strictEqual((html.match(/The registry changed/g) || []).length, 1, "one line");
  c.META.domain_index_lines = 9;
  await c.loadOrg2(true);
  assert.strictEqual(loads, 2);
  assert.strictEqual(c.o2S().stale, false);
  assert.deepStrictEqual(Object.keys(c.o2S().dept).length, 0, "a refresh drops the cached reads");
});
test("panel.css carries a scoped .o2 block with tokens only", () => {
  const start = css.indexOf("/* ── Org (org2");
  assert.ok(start !== -1, "block present");
  const block = css.slice(start);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(block.replace(/var\(--[a-z-]+\)/g, "")), "no literal colours in the .o2 block");
  assert.ok(/data-o2q/.test(fs.readFileSync(path.join(JS, "06-render.js"), "utf8")), "the search input keeps focus across a re-render");
});

/* ── the Library, top right (2.299.0, founder) ───────────────────────────── */

test("the Library button sits in the strip's action row, carrying the word", () => {
  const c = fresh();
  const html = c.o2LibBtnHtml();
  assert.ok(/data-o2act="lib"/.test(html), "it is an action of this screen");
  assert.ok(/aria-pressed="false"/.test(html), "off by default");
  assert.ok(/<span>Library<\/span>/.test(html),
    "the WORD rides with the mark: alone in that corner it reads as a tool for the selected department");
  assert.ok(/<svg/.test(html), "and the mark is there too");
});

test("pressed, the button reads as pressed and offers the way back", () => {
  const c = fresh();
  c.o2S().lib = true;
  const html = c.o2LibBtnHtml();
  assert.ok(/aria-pressed="true"/.test(html));
  assert.ok(/class="o2libbtn on"/.test(html));
  assert.ok(/Back to the departments/.test(html), "the title says how to return");
});

test("the panel's second mode lists the seven shelves, then the Archive", () => {
  const c = fresh();
  const html = c.o2LibPanelHtml();
  for (const label of ["Identity", "Adaptation", "Priority", "Coordination", "Audit",
                       "Engines", "Work atom"])
    assert.ok(new RegExp(">" + label + "<").test(html), label + " is a row");
  assert.ok(/o2libgrp">Functions</.test(html) && /o2libgrp">Parts</.test(html),
    "the shelves keep their two groups");
  /* 2026-09-25 (founder): "in the library itself we can just have Archive for
     those particular sections" -- the rows that left the Org menu, plus Reorg
     plans. This file loads without 02-helpers.js, so no flag hides a row. */
  assert.ok(/o2libgrp">Archive</.test(html), "a third group, Archive");
  const arch = html.split('o2libgrp">Archive<')[1];
  assert.deepStrictEqual([...arch.matchAll(/data-screen="([^"]+)"/g)].map(m => m[1]),
    ["workspace", "departments", "charters", "placements", "modules", "reorg"],
    "each opens its old screen by its own id");
  assert.ok(/>Apps</.test(arch) && />Reorg plans</.test(arch), "the words the menu used");
  assert.strictEqual((html.match(/class="o2librow"|class="o2librow /g) || []).length, 13);
});

test("the Archive honours Workspace's and Apps' on/off settings", () => {
  const c = fresh();
  /* the rail's own test, as 02-helpers.js defines it: workspace is opt-in,
     every other flag opt-out */
  c.destRowHidden = e => e.flag === "workspace" ? !c.wsOn : !!(e.flag && c.SETTINGS.flags[e.flag] === false);
  c.wsOn = false;
  c.SETTINGS.flags.modules = false;
  let arch = c.o2LibPanelHtml().split('o2libgrp">Archive<')[1];
  assert.ok(!/data-screen="workspace"/.test(arch), "Workspace off: no row");
  assert.ok(!/data-screen="modules"/.test(arch), "Apps off: no row");
  assert.ok(/data-screen="departments"/.test(arch), "unflagged rows stay");
  c.wsOn = true;
  c.SETTINGS.flags.modules = true;
  arch = c.o2LibPanelHtml().split('o2libgrp">Archive<')[1];
  assert.ok(/data-screen="workspace"/.test(arch) && /data-screen="modules"/.test(arch), "both on: both rows");
});

test("a shelf row opens the screen the rail already opens, never a second one", () => {
  const c = fresh();
  const html = c.o2LibPanelHtml();
  for (const screen of ["lib-identity", "lib-engines", "lib-work-atom"])
    assert.ok(html.indexOf('data-screen="' + screen + '"') !== -1,
      screen + " is opened by its own id");
  assert.strictEqual(html.indexOf("data-o2ref"), -1,
    "a shelf is not a domain: it never carries a tree ref");
});

test("the open shelf is marked in the panel", () => {
  const c = fresh();
  c.S.screen = "lib-engines";
  const html = c.o2LibPanelHtml();
  assert.ok(/data-screen="lib-engines"[^>]*aria-selected="true"/.test(html));
  assert.ok(/data-screen="lib-identity"[^>]*aria-selected="false"/.test(html));
});

test("the toggle changes nothing about the tree, so pressing twice returns", () => {
  const c = fresh();
  const before = c.o2TreeHtml();
  c.o2S().lib = true;
  c.o2S().lib = false;
  assert.strictEqual(c.o2TreeHtml(), before, "byte for byte, the same tree");
});

test("panel.css carries the button and the panel, in tokens only", () => {
  const start = css.indexOf("THE LIBRARY, TOP RIGHT");
  assert.ok(start !== -1, "the block is there");
  const block = css.slice(start);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(block.replace(/var\(--[a-z-]+\)/g, "")),
    "no literal colours");
  assert.ok(/\.o2libbtn\.on\{/.test(block), "a pressed state");
  assert.ok(/\.o2librow\[aria-selected="true"\]/.test(block), "a selected row");
});

Promise.all(pending).then(() => {
  console.log(`\n${ran - failed}/${ran} passed`);
  process.exit(failed ? 1 : 0);
});
