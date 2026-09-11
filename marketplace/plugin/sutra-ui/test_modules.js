#!/usr/bin/env node
/* test_modules.js -- Org > Modules v1.1 (modules live within Departments):
   registration, the facets bar, the shared Directory rail (the REAL dirRail
   sliced out of 03-org.js), the here / below / system / unassigned groups,
   the inline detail with its Move picker, the never-blank states and the
   three open paths. Same discipline as test_shadow_home.js: run the REAL
   module under vm with a minimal stub context, assert on the real functions.
   Run: node test_modules.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const src = fs.readFileSync(path.join(__dirname, "static", "js", "18-modules.js"), "utf8");
const state = fs.readFileSync(path.join(__dirname, "static", "js", "01-state.js"), "utf8");
const orgSrc = fs.readFileSync(path.join(__dirname, "static", "js", "03-org.js"), "utf8");

/* The rail helpers (dirData / dirChip / dirMatches / dirRail) are sliced out of
   03-org.js between two marker comments, so the test runs the SAME code the
   Directory view runs -- not a copy. 03-org.js cannot be loaded whole under vm:
   its top-level `const SCREENS = {}` is a lexical global (codex P13). */
const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
assert(orgSrc.indexOf(RB) !== -1 && orgSrc.indexOf(RE) !== -1, "03-org.js must carry the rail-helpers markers");
const railSrc = orgSrc.slice(orgSrc.indexOf(RB), orgSrc.indexOf(RE));

let failed = 0, ran = 0;
function test(name, fn){
  ran++;
  try { fn(); console.log("ok   " + name); }
  catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e && e.message)); }
}

const ROOT = { ref: "r0", path: "D0", name: "Asawa Inc.", parent_ref: null, status: "active", description: "the holding company", ts_minted_ms: 1 };
const EXP  = { ref: "r1", path: "D2", name: "Experience", parent_ref: "r0", status: "active", ts_minted_ms: 2 };
const DESK = { ref: "r2", path: "D2.D1", name: "Desktop app", parent_ref: "r1", status: "active", description: "the Sutra Mac app", ts_minted_ms: 3 };
const WEB  = { ref: "r3", path: "D2.D2", name: "Website", parent_ref: "r1", status: "active", ts_minted_ms: 4 };
const ANA  = { ref: "r4", path: "D3", name: "Analytics", parent_ref: "r0", status: "active", ts_minted_ms: 5 };
const OLD  = { ref: "r9", path: "D4", name: "Old", parent_ref: "r0", status: "retired", ts_minted_ms: 6 };
const TREE = [ROOT, EXP, DESK, WEB, ANA, OLD];
const dep = d => ({ ref: d.ref, path: d.path, name: d.name, moved: false });

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], openScreen: [], newSession: [], submitTurn: [], goDest: [], render: 0 };
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { shadow: () => "", balance: () => "", teamsutra: () => "", settings: () => "", git: () => "", departments: () => "" },
    TITLES: { settings: ["AI Provider", ""], git: ["Git", ""], teamsutra: ["Help", ""] },
    DEST_PLANES: { settings: [{ group: "Tools", rows: [{ screen: "terminal" }, { screen: "git" }] },
                              { group: "System", rows: [{ screen: "settings" }] }] },
    DOMAINS: opts.DOMAINS === undefined ? TREE : opts.DOMAINS,
    CHARTERS: [],
    st: (d) => d.status || "active",
    S: Object.assign({ ui: { dest: "org", railOpen: "org" }, showRetired: false }, opts.S || {}),
    apiGet: (p) => { calls.apiGet.push(p); return new Promise(() => {}); },
    apiPost: (p, b) => { calls.apiPost.push([p, b]); return new Promise(() => {}); },
    openScreen: (id) => { calls.openScreen.push(id); ctx.S.screen = id; ctx.S.ui.dest = id === "shadow" ? "focus" : id === "git" ? "settings" : "org"; },
    destInline: (d) => d === "focus" || d === "org",
    newSession: (cwd) => { const s = { id: "s-9", title: "New session", cwd }; calls.newSession.push(cwd); return s; },
    submitTurn: (t, sid) => { calls.submitTurn.push([t, sid]); },
    goDest: (d) => { calls.goDest.push(d); },
    render: () => { calls.render++; },
    scheduleRender: () => { calls.render++; },
    document: { addEventListener(){}, querySelector(){ return null; },
                documentElement: { getAttribute(){ return "dark"; } } },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const USER_PAGE = { id: "m<1", name: "Pipeline board", tagline: "deals by stage", kind: "page", status: "ready", department: dep(DESK),
                    origin: { created_by: "disk", at: "2026-09-08T10:00:00Z" }, surface: { entry: "index.html" }, guard: {}, has_page: true, reserved: false, warning: null };
const USER_CHAT = { id: "friday", name: "Friday review", tagline: "", kind: "chat", status: "draft", department: dep(DESK),
                    origin: { created_by: "shadow", at: "2026-09-08T10:00:00Z" }, surface: { instructions: "go" }, guard: {}, has_page: false, reserved: false, warning: null };
const WEB_CHAT  = { id: "site-check", name: "Site copy check", tagline: "claims with no source", kind: "chat", status: "draft", department: dep(WEB),
                    origin: { created_by: "app", at: "2026-09-08T10:00:00Z" }, surface: { instructions: "read" }, guard: {}, has_page: false, reserved: false, warning: null };
const SCRATCH   = { id: "scratch", name: "scratch", tagline: "", kind: "page", status: "draft", department: null,
                    origin: { created_by: "disk", at: null }, surface: {}, guard: {}, has_page: false, reserved: false, warning: null };
const SYS = [
  { id: "sys-balance", name: "Balance", tagline: "", kind: "link", status: "ready", department: dep(ROOT), origin: { created_by: "system" }, surface: { screen: "balance" }, guard: {}, reserved: false, warning: null },
  { id: "sys-help", name: "Help", tagline: "", kind: "link", status: "ready", department: dep(ROOT), origin: { created_by: "system" }, surface: { screen: "teamsutra" }, guard: {}, reserved: false, warning: null },
  { id: "sys-settings", name: "Settings", tagline: "", kind: "link", status: "ready", department: dep(ROOT), origin: { created_by: "system" }, surface: { screen: "settings", sections: "client" }, guard: {}, reserved: false, warning: null },
];
const ROOT_ECHO = { ref: "r0", path: "D0", name: "Asawa Inc.", description: "the holding company" };
function api(o){
  o = o || {};
  const groups = Object.assign({ here: [], below: [], system: [], unassigned: [] }, o.groups || {});
  const user = [].concat(groups.here, ...groups.below.map(g => g.modules), groups.unassigned);
  return { modules: { modules: (o.modules || SYS.concat(user)), groups,
                      counts_by_ref: o.counts_by_ref || {}, unassigned_count: o.unassigned_count || groups.unassigned.length,
                      root: o.root === undefined ? ROOT_ECHO : o.root,
                      department: o.department === undefined ? ROOT_ECHO : o.department,
                      count_user: user.length, archived: 0, home: "/tmp/mods", error: null } };
}
const ROOT_VIEW = api({ groups: { below: [{ department: dep(DESK), modules: [USER_CHAT, USER_PAGE] }, { department: dep(WEB), modules: [WEB_CHAT] }],
                                  system: SYS, unassigned: [SCRATCH] },
                        counts_by_ref: { r0: 3, r1: 3, r2: 2, r3: 1 } });
const loaded = (a, extra) => Object.assign({}, a, { modKey: "?subtree=1" }, extra || {});

/* 1. load order + cache-bust */
test("panel.html loads 18-modules.js after 17-agents.js and before 09-tail.js, versioned", () => {
  const tags = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(\?[^"]*)?"/g)].map(m => [m[1], m[2] || ""]);
  const i18 = tags.findIndex(t => t[0] === "18-modules.js");
  const i17 = tags.findIndex(t => t[0] === "17-agents.js");
  const i09 = tags.findIndex(t => t[0] === "09-tail.js");
  assert(i18 > i17 && i18 < i09, "order: 17 < 18 < 09-tail");
  assert(/__ASSETVER__/.test(tags[i18][1]), "18-modules.js must carry ?v=__ASSETVER__");
  assert(tags.every(t => /__ASSETVER__/.test(t[1])), "every panel module is versioned (14/15/16 were not)");
});

/* 2. registration */
test("SCREENS.modules + TITLES.modules registered (a missing TITLES row aborts render)", () => {
  const T = fresh();
  assert.strictEqual(typeof T.SCREENS.modules, "function");
  assert.strictEqual(T.TITLES.modules[0], "Modules");
});

/* 3. the Org row */
test("01-state.js: DEST_PLANES.org carries the modules row with an explicit label and flag", () => {
  assert(/screen:"modules",\s*label:"Modules",\s*flag:"modules"/.test(state), "row missing or unlabelled");
});

/* 4. first paint = the root query */
test("first paint: one read of the root subtree query, placeholder longer than the surfaces floor", () => {
  const T = fresh();
  const out = T.SCREENS.modules();
  assert(/Reading your modules/.test(out));
  assert(out.length > 40);
  assert.deepStrictEqual(T.calls.apiGet, ["/api/modules?subtree=1"]);
  T.SCREENS.modules();
  assert.strictEqual(T.calls.apiGet.length, 1, "no second read while the same query is in flight");
});

/* 5. root view: facets, the shared rail with counts, grouped below, System + Unassigned */
test("root view: facets bar, dirRail with subtree counts (retired hidden), below grouped by department, System + Unassigned", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  const out = T.SCREENS.modules();
  const facets = out.slice(out.indexOf('class="facets"'), out.indexOf('class="dpage'));
  assert(/data-modfacet="live"/.test(facets) && /data-modfacet="draft"/.test(facets) && /data-modfacet="dir"/.test(facets));
  assert(/data-modfacet="modules" aria-pressed="true"/.test(facets), "Modules facet pressed");
  assert(/data-modnew/.test(facets), "+ New module sits on the facets bar");
  assert(!/data-view=/.test(out) && !/data-ref=/.test(out) && !/id="dirQ"/.test(out), "never the Departments handlers' attributes (07-loaders collision)");
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/<span class="chip">D0<\/span>[^]*?data-moddept="r0"/.test(nav), "root node first, D0 chip");
  assert(/data-moddept="r1"[^]*?Experience[^]*?<span class="navcount">3<\/span>/.test(nav), "Experience carries its subtree total");
  assert(/<span class="chip">D2\.1<\/span>Desktop app<span class="navcount">2<\/span>/.test(nav), "leaf chip uses the published spelling (dirChip) + count");
  assert(!/Old/.test(nav), "retired departments never appear in the rail");
  assert(/data-moddept="unassigned"[^]*?Unassigned[^]*?<span class="navcount">1<\/span>/.test(nav), "Unassigned node last, with its count");
  assert(/data-modq/.test(nav), "rail search is the Modules screen's own field");
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/<h1>Asawa Inc\.<\/h1>/.test(main));
  assert(/0 here · 3 below · 3 system/.test(main), "header count line");
  assert(main.indexOf("In sub-departments") < main.indexOf("System") && main.indexOf("System") < main.indexOf("Unassigned"), "group order below, System, Unassigned");
  assert(/data-mod="m&lt;1"/.test(main), "row id escaped");
  assert(/<span class="mod-dep">D2\.1 Desktop app<\/span>/.test(main), "below rows name their department");
  assert(/data-mod="sys-balance"/.test(main) && /data-mod="scratch"/.test(main));
  assert(/data-modsub/.test(main), "the subtree toggle is offered");
});

/* 6. a department selected: Here, the inline detail, the Department line, no System */
test("department view: Here rows, inline detail under the selected row with Department + Move, sandboxed iframe, no System group", () => {
  const view = api({ department: { ref: "r2", path: "D2.D1", name: "Desktop app", description: "the Sutra Mac app" },
                     groups: { here: [USER_CHAT, USER_PAGE] }, counts_by_ref: { r0: 3, r1: 3, r2: 2, r3: 1 }, unassigned_count: 1 });
  const T = fresh({ S: loaded(view, { modDept: "r2", modSel: "m<1", modKey: "?subtree=1&department=r2" }) });
  const out = T.SCREENS.modules();
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/<span class="chip big">D2\.1<\/span>/.test(main) && /<h1>Desktop app<\/h1>/.test(main));
  assert(/2 here/.test(main) && !/system/.test(main), "count line: here only; System is root-only");
  assert(/>Here</.test(main));
  const rowAt = main.indexOf('data-mod="m&lt;1"'), detailAt = main.indexOf('class="mod-detail"');
  assert(rowAt !== -1 && detailAt > rowAt, "detail renders inline under the selected row");
  assert(/aria-selected="true"[^>]*>|data-mod="m&lt;1" aria-selected="true"/.test(main));
  assert(/<b>Department<\/b><span>Desktop app[^]*?data-modmove/.test(main), "Department line with Move");
  assert(/<iframe class="mod-frame" src="\/api\/modules\/m&lt;1\/page\?theme=dark&amp;v=0" [^>]*sandbox="allow-scripts">/.test(main), "iframe sandboxed with allow-scripts ONLY");
  assert(!/allow-same-origin/.test(out));
  assert(!/data-mod="sys-balance"/.test(main), "System rows only at the root");
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/data-moddept="r2" aria-current="true"/.test(nav), "selected department marked in the rail");
  assert(/<details class="navgrp" open>[^]*?data-moddept="r1"/.test(nav), "ancestors of the selection are open");
});

/* 7. empty department never blank */
test("empty department: 'Nothing here yet' names the department; sub-department group still offered", () => {
  const view = api({ department: { ref: "r3", path: "D2.D2", name: "Website", description: "" }, groups: {} });
  const T = fresh({ S: loaded(view, { modDept: "r3", modKey: "?subtree=1&department=r3" }) });
  const out = T.SCREENS.modules();
  assert(/Nothing here yet\. New module puts it in Website\./.test(out));
  assert(out.length > 40);
});

/* 8. empty registry (fleet first open, D-M14) */
test("empty registry: Unassigned pseudo-node alone on the left, System + Unassigned on the right, nothing minted", () => {
  const view = api({ root: null, department: null, groups: { system: SYS, unassigned: [USER_CHAT] } });
  const T = fresh({ DOMAINS: [], S: loaded(view) });
  const out = T.SCREENS.modules();
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/data-moddept="unassigned"/.test(nav) && !/data-moddept="r0"/.test(nav));
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/>System</.test(main) && /data-mod="sys-balance"/.test(main));
  assert(/>Unassigned</.test(main) && /data-mod="friday"/.test(main));
  assert(!/puts it in/.test(main));
  assert(out.length > 40);
});

/* 9. unavailable: no fallback registry */
test("API error: 'Modules unavailable' and NO client-side system list", () => {
  const T = fresh({ S: { modules: { modules: [], groups: null, error: "boom" }, modKey: "?subtree=1" } });
  const out = T.SCREENS.modules();
  assert(/Modules unavailable/.test(out) && /boom/.test(out));
  assert(!/sys-/.test(out), "a fallback list would be a second registry");
  assert(out.length > 40);
});

/* 10. chat open */
test("chat open: goDest(chats), newSession, title set, instructions become the first turn", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  assert.strictEqual(T.modOpen(USER_CHAT), true);
  assert.deepStrictEqual(T.calls.goDest, ["chats"]);
  assert.deepStrictEqual(T.calls.newSession, [""]);
  assert.deepStrictEqual(T.calls.submitTurn, [["go", "s-9"]]);
});

/* 11. link open follows the accordion */
test("link open: openScreen(target) then railOpen follows the owning inline destination", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  const shadow = { id: "shadow", name: "Shadow", kind: "link", status: "ready", surface: { screen: "shadow" }, reserved: false };
  assert.strictEqual(T.modOpen(shadow), true);
  assert.deepStrictEqual(T.calls.openScreen, ["shadow"]);
  assert.strictEqual(T.S.ui.railOpen, "focus");
  const term = { id: "t", name: "T", kind: "link", status: "ready", surface: { screen: "terminal" }, reserved: false, department: null };
  assert.strictEqual(T.modOpen(term), false, "terminal is a pane toggle, never a link target");
  const T2 = fresh({ S: loaded(api({ groups: { unassigned: [term] } }), { modSel: "t" }) });
  assert(/cannot be opened/.test(T2.SCREENS.modules()));
});

/* 12. reserved rows render but never open */
test("reserved sys- folder: listed under Unassigned with the warning, Open refused", () => {
  const fake = { id: "sys-fake", name: "sys-fake", kind: "chat", status: "draft", surface: {}, reserved: true, warning: "reserved id, not loaded", department: null };
  const T = fresh({ S: loaded(api({ groups: { system: SYS, unassigned: [fake] } }), { modSel: "sys-fake" }) });
  const out = T.SCREENS.modules();
  assert(/reserved id/.test(out));
  assert.strictEqual(T.modOpen(fake), false);
});

/* 13. Move picker: the same tree, live only, current marked, assign posts */
test("Move picker: live departments in tree order, current marked, Move posts action=assign", () => {
  const view = api({ department: { ref: "r2", path: "D2.D1", name: "Desktop app", description: "" }, groups: { here: [USER_CHAT] } });
  const T = fresh({ S: loaded(view, { modDept: "r2", modKey: "?subtree=1&department=r2", modSel: "friday", modMove: "friday", modPick: "r4" }) });
  const out = T.SCREENS.modules();
  const picker = out.slice(out.indexOf('class="mod-picker"'), out.indexOf("</div>", out.lastIndexOf("data-modmovego")));
  const refs = [...picker.matchAll(/data-modpick="([^"]+)"/g)].map(m => m[1]);
  assert.deepStrictEqual(refs, ["r0", "r1", "r2", "r3", "r4"], "tree order, retired excluded");
  assert(/data-modpick="r2"[^>]*class="[^"]*\bnow\b/.test(picker) || /class="[^"]*\bnow\b[^"]*"[^>]*data-modpick="r2"/.test(picker), "current department marked");
  assert(/class="[^"]*\bpick\b[^"]*"[^>]*data-modpick="r4"|data-modpick="r4"[^>]*class="[^"]*\bpick\b/.test(picker), "picked department marked");
  assert(/data-modmovego(?![^>]*disabled)/.test(picker), "Move enabled once a different department is picked");
  T.modAssign("friday", "r4");
  assert.deepStrictEqual(T.calls.apiPost, [["/api/modules/friday", { action: "assign", department_ref: "r4" }]]);
  assert.strictEqual(T.S.modMove, null);
});

/* 14. facets route into the Departments family */
test("facets: Live/Draft/Directory set S.view and open Departments; Modules opens the Modules screen", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  T.modFacet("dir");
  assert.strictEqual(T.S.view, "dir");
  assert.deepStrictEqual(T.calls.openScreen, ["departments"]);
  T.modFacet("modules");
  assert.deepStrictEqual(T.calls.openScreen, ["departments", "modules"]);
  assert.strictEqual(T.S.ui.railOpen, "org", "the accordion follows the inline destination");
});

/* 15. new module form: department select, live only, defaults to the selected department */
test("New module form: department select lists live departments only and defaults to the rail selection", () => {
  const view = api({ department: { ref: "r2", path: "D2.D1", name: "Desktop app", description: "" }, groups: {} });
  const T = fresh({ S: loaded(view, { modDept: "r2", modKey: "?subtree=1&department=r2", modNew: true }) });
  const out = T.SCREENS.modules();
  const sel = out.slice(out.indexOf('data-modf="department"'), out.indexOf("</select>"));
  assert(/<option value="r2" selected>/.test(sel), "defaults to the selected department");
  assert(!/value="r9"/.test(sel), "retired never offered");
  assert(!/value="unassigned"/.test(sel), "unassigned is not a target (codex P18)");
  const T2 = fresh({ DOMAINS: [], S: loaded(api({ root: null, department: null }), { modNew: true }) });
  assert(!/data-modf="department"/.test(T2.SCREENS.modules()), "no picker on an empty registry");
});

/* 16. selecting a department is a server-side query, keyed */
test("selecting a department reloads with department=<ref>; root drops the param; subtree toggle is in the key", () => {
  const T = fresh({ S: loaded(ROOT_VIEW, { modSel: "scratch" }) });
  T.modSelectDept("r1");
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=1&department=r1");
  assert.strictEqual(T.S.modSel, null, "selection does not survive a department change");
  T.modSelectDept(null);
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=1");
  T.S.modSubtree = false; T.modSelectDept("unassigned");
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=0&department=unassigned");
});

/* 17. Directory parity: the extracted helper still renders the Directory rail shape */
test("dirRail: Directory options give #dir- anchors, kid counts on groups, .dsub leaves; domainsDirectory uses it", () => {
  const T = fresh();
  const d = T.dirData();
  const tops = d.kids.get(d.root.ref) || [];
  const rail = T.dirRail({ tops, kids: d.kids, q: "",
    link: (x, inner, cls) => `<a${cls ? ` class="${cls}"` : ""} href="#dir-${x.ref}">${inner}</a>`,
    count: (x, ch, all) => ch.length ? all.length : null });
  assert(/<a href="#dir-r1">Experience<\/a><span class="navcount">2<\/span>/.test(rail), "group: anchor + all-kids count");
  assert(/<a class="dsub" href="#dir-r2"><span class="chip">D2\.1<\/span>Desktop app<\/a>/.test(rail), "leaf: .dsub with chip, no count");
  assert(!/Old/.test(rail), "dirData hides retired unless S.showRetired");
  const body = orgSrc.slice(orgSrc.indexOf("function domainsDirectory"), orgSrc.indexOf("SCREENS.departments"));
  assert(/dirRail\(/.test(body), "domainsDirectory renders its rail through dirRail");
  assert(!/const navEntry/.test(body), "the old inline navEntry is gone");
});

console.log(`\n${ran - failed}/${ran} passed`);
process.exit(failed ? 1 : 0);
