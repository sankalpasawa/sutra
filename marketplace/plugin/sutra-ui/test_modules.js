#!/usr/bin/env node
/* test_modules.js -- Org > Apps v1.2 (apps live within Departments):
   registration + labels, the shared Directory rail with app rows (the REAL
   dirRail sliced out of 03-org.js), the department view, the header-only app
   view with Edit in chat, the seeds (routing pin first), New app via chat and
   its provider gate, the narrow crumb, the done hook, the query key, and the
   open paths. Same discipline as test_shadow_home.js: run the REAL module
   under vm with a minimal stub context, assert on the real functions.
   Run: node test_modules.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const src = fs.readFileSync(path.join(__dirname, "static", "js", "18-modules.js"), "utf8");
const state = fs.readFileSync(path.join(__dirname, "static", "js", "01-state.js"), "utf8");
const helpers = fs.readFileSync(path.join(__dirname, "static", "js", "02-helpers.js"), "utf8");
const orgSrc = fs.readFileSync(path.join(__dirname, "static", "js", "03-org.js"), "utf8");

const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
assert(orgSrc.indexOf(RB) !== -1 && orgSrc.indexOf(RE) !== -1, "03-org.js must carry the rail-helpers markers");
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
    CHARTERS: [{ id: "C-1", domain_ref: "r2", title: "Sutra Desktop", purpose: "the Mac app" }],
    SETTINGS: opts.SETTINGS === undefined ? { provider: "claude" } : opts.SETTINGS,
    st: (d) => d.status || "active",
    S: Object.assign({ ui: { dest: "org", railOpen: "org" }, showRetired: false, sessions: [], modNarrow: false }, opts.S || {}),
    apiGet: (p) => { calls.apiGet.push(p); return new Promise(() => {}); },
    apiPost: (p, b) => { calls.apiPost.push([p, b]); return new Promise(() => {}); },
    openScreen: (id) => { calls.openScreen.push(id); ctx.S.screen = id; ctx.S.ui.dest = id === "shadow" ? "focus" : id === "git" ? "settings" : "org"; },
    destInline: (d) => d === "focus" || d === "org",
    newSession: (cwd, department) => { const s = { id: "s-9", title: "New session", cwd, department }; calls.newSession.push([cwd, department]); ctx.S.sessions.unshift(s); return s; },
    submitTurn: (t, sid, o) => { calls.submitTurn.push([t, sid, o]); },
    goDest: (d) => { calls.goDest.push(d); },
    render: () => { calls.render++; },
    scheduleRender: () => { calls.render++; },
    document: { addEventListener(){}, querySelector(){ return null; }, getElementById(){ return null; },
                documentElement: { getAttribute(){ return "dark"; } } },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const USER_PAGE = { id: "m<1", name: "Pipeline board", tagline: "deals by stage", kind: "page", status: "ready", schema: 2, department: dep(DESK),
                    origin: { created_by: "disk", at: "2026-09-08T10:00:00Z" }, surface: { entry: "index.html" }, guard: {}, has_page: true, reserved: false, warning: null };
const USER_CHAT = { id: "friday", name: "Friday review", tagline: "", kind: "chat", status: "draft", schema: 2, department: dep(DESK),
                    origin: { created_by: "shadow", at: "2026-09-08T10:00:00Z" }, surface: { instructions: "go" }, guard: {}, has_page: false, reserved: false, warning: null };
const WEB_CHAT  = { id: "site-check", name: "Site copy check", tagline: "claims with no source", kind: "chat", status: "draft", schema: 2, department: dep(WEB),
                    origin: { created_by: "app", at: "2026-09-08T10:00:00Z" }, surface: { instructions: "read" }, guard: {}, has_page: false, reserved: false, warning: null };
const SCRATCH   = { id: "scratch", name: "scratch", tagline: "", kind: "page", status: "draft", schema: 1, department: null,
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
const DESK_VIEW = api({ department: { ref: "r2", path: "D2.D1", name: "Desktop app", description: "the Sutra Mac app" },
                        groups: { here: [USER_CHAT, USER_PAGE] }, modules: SYS.concat([USER_CHAT, USER_PAGE, WEB_CHAT, SCRATCH]),
                        counts_by_ref: { r0: 3, r1: 3, r2: 2, r3: 1 }, unassigned_count: 1 });
const loaded = (a, extra) => Object.assign({}, a, { modKey: "?subtree=1" }, extra || {});

/* 1. load order + cache-bust */
test("panel.html loads 18-modules.js after 17-agents.js and before 09-tail.js, versioned", () => {
  const tags = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(\?[^"]*)?"/g)].map(m => [m[1], m[2] || ""]);
  const i18 = tags.findIndex(t => t[0] === "18-modules.js");
  const i17 = tags.findIndex(t => t[0] === "17-agents.js");
  const i09 = tags.findIndex(t => t[0] === "09-tail.js");
  assert(i18 > i17 && i18 < i09, "order: 17 < 18 < 09-tail");
  assert(/__ASSETVER__/.test(tags[i18][1]), "18-modules.js must carry ?v=__ASSETVER__");
});

/* 2. registration + the user-facing word (D-M22) */
test("SCREENS.modules + TITLES.modules registered; the word is App everywhere a person reads", () => {
  const T = fresh();
  assert.strictEqual(typeof T.SCREENS.modules, "function");
  assert.strictEqual(T.TITLES.modules[0], "Apps");
  assert(/screen:"modules",\s*label:"Apps",\s*flag:"modules"/.test(state), "01-state.js row label is Apps");
  const strings = src.replace(/\/\*[^]*?\*\//g, "").match(/(["'`])(?:(?!\1)[^\\]|\\.)*\1/g) || [];
  /* code inside ${...} is not text a person reads; strip it before the check */
  const leaks = strings.map(q => q.replace(/\$\{[^}]*\}/g, ""))
    .filter(q => /\bmodules?\b/i.test(q) && !/module\.json|\.sutra-ui\/modules|api\/modules|"modules"|modules\?|modules\/|SCREENS\.modules|TITLES\.modules|\/api\/modules/.test(q));
  assert.deepStrictEqual(leaks, [], "user-facing string still says module: " + leaks.join(" | "));
});

/* 3. plumbing: submitTurn carries the pin, the done frame calls modOnSessionDone */
test("plumbing: submitTurn(text, sid, opts) forwards to runTask; runTurn posts pin; claudeChannel done calls modOnSessionDone", () => {
  assert(/async function submitTurn\(text, sessionId, opts\)/.test(helpers));
  assert(/runTask\(text, sessionId, opts\)/.test(helpers));
  assert(/async function runTurn\(text, ts, opts\)/.test(state) && /body\.pin = \{ department_ref/.test(state));
  assert(/runTurn\(text, undefined, opts\)/.test(state), "runTask forwards opts");
  assert(/modOnSessionDone\(sess\)/.test(state), "the done handler hands the session to the Apps hook");
});

/* 4. first paint = the root query */
test("first paint: one read of the root subtree query; no second read while in flight", () => {
  const T = fresh();
  const out = T.SCREENS.modules();
  assert(/Reading your apps/.test(out));
  assert.deepStrictEqual(T.calls.apiGet, ["/api/modules?subtree=1"]);
  T.SCREENS.modules();
  assert.strictEqual(T.calls.apiGet.length, 1);
});

/* 5. root view: facets, the rail with app rows nested under departments, groups */
test("root view: facets bar, dirRail with app rows under their department + subtree counts, retired hidden, System + Unassigned", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  const out = T.SCREENS.modules();
  const facets = out.slice(out.indexOf('class="facets"'), out.indexOf('class="dpage'));
  assert(/data-modfacet="modules" aria-pressed="true">Apps</.test(facets), "Modules facet reads Apps and is pressed");
  assert(/data-modnew>\+ New app</.test(facets));
  assert(!/data-view=/.test(out) && !/data-ref=/.test(out) && !/id="dirQ"/.test(out), "never the Departments handlers' attributes");
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/<span class="chip">D0<\/span>[^]*?data-moddept="r0"/.test(nav), "root first");
  assert(/data-moddept="r1"[^]*?Experience[^]*?<span class="navcount">3<\/span>/.test(nav), "subtree count");
  const desk = nav.slice(nav.indexOf('data-moddept="r2"'), nav.indexOf('data-moddept="r3"'));
  assert(/data-modapp="friday"/.test(desk) && /data-modapp="m&lt;1"/.test(desk), "app rows nest under Desktop app (D-M16)");
  assert(/<span class="pill mod-kind">chat<\/span>/.test(desk));
  assert(!/Old/.test(nav), "retired departments never appear");
  assert(/data-moddept="unassigned"[^]*?Unassigned[^]*?<span class="navcount">1<\/span>[^]*?data-modapp="scratch"/.test(nav), "Unassigned last with its apps");
  assert(/data-modq/.test(nav));
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/<h1>Asawa Inc\.<\/h1>/.test(main) && /0 here · 3 below · 3 system/.test(main));
  assert(main.indexOf("In sub-departments") < main.indexOf("System") && main.indexOf("System") < main.indexOf("Unassigned"));
  assert(/<span class="mod-dep">D2\.1 Desktop app<\/span>/.test(main));
  assert(/data-modsub/.test(main) && /Edit in chat/.test(main), "toggle + hint mention Edit in chat");
});

/* 6. department view */
test("department view: Apps rows, count line without system, no edit button on a department", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2" }) });
  const out = T.SCREENS.modules();
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/<span class="chip big">D2\.1<\/span>/.test(main) && /<h1>Desktop app<\/h1>/.test(main));
  assert(/2 here/.test(main) && !/system/.test(main));
  assert(/>Apps</.test(main) && /data-modapp="friday"/.test(main));
  assert(!/data-modedit/.test(main), "no Edit in chat on the department view");
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/data-moddept="r2" aria-current="true"/.test(nav));
  assert(/<details class="navgrp" open>[^]*?data-moddept="r1"/.test(nav), "ancestors open");
});

/* 7. app view: header only, then the app (D-M17) */
test("app view: chip · crumb · name · tagline · kind · Edit in chat · status, then the app; no action row; sandboxed iframe", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2", modSel: "m<1" }) });
  const out = T.SCREENS.modules();
  const main = out.slice(out.indexOf("<main"), out.indexOf("</main>"));
  assert(/<p class="crumb">Desktop app › page<\/p>/.test(main) && /<h1>Pipeline board<\/h1>/.test(main));
  assert(/data-modedit[^>]*>[^]*?Edit in chat<\/button>/.test(main), "one Edit in chat button");
  assert(/<span class="count">ready<\/span>/.test(main));
  assert(!/Move|Archive|Open full width/.test(main), "no action row (founder 2026-09-11)");
  assert(/<iframe class="mod-frame" src="\/api\/modules\/m&lt;1\/page\?theme=dark&amp;v=0" [^>]*sandbox="allow-scripts">/.test(main));
  assert(!/allow-same-origin/.test(out));
  const nav = out.slice(out.indexOf("<nav"), out.indexOf("</nav>"));
  assert(/data-modapp="m&lt;1" aria-current="true"/.test(nav), "the open app is current in the rail");
});

/* 8. chat app body: read-only instructions + open in chat */
test("chat app: instructions read-only, an open-in-chat link, no inline editing", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2", modSel: "friday" }) });
  const out = T.SCREENS.modules();
  assert(/<pre class="mod-ro">go<\/pre>/.test(out) && /data-modopen/.test(out));
  assert(!/<textarea/.test(out), "inline instruction editing is gone (codex r1 P5)");
});

/* 9. Edit in chat: seeded session with the routing pin first, cwd = the folder, session.app set, pin forwarded */
test("Edit in chat: newSession(folder, dept), first line is the ROUTING PIN, session.app set, submitTurn carries the pin", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2", modSel: "m<1" }) });
  const sess = T.modEdit(T.modSelected(T.S));
  assert(sess, "a session was opened");
  assert.deepStrictEqual(T.calls.goDest, ["chats"]);
  assert.deepStrictEqual(T.calls.newSession, [["/tmp/mods/m<1", "r2"]]);
  assert.strictEqual(sess.title, "Edit · Pipeline board");
  /* objects born inside the vm have another Object prototype: compare by value */
  assert.strictEqual(JSON.stringify(sess.app), JSON.stringify({ id: "m<1", mode: "edit", department_ref: "r2" }));
  const [seed, sid, opts] = T.calls.submitTurn[0];
  assert.strictEqual(sid, "s-9");
  assert(seed.split("\n")[0].startsWith("ROUTING PIN — file this session under D2.1 Desktop app (r2). Do not re-classify."), "pin is line 1");
  assert(/You are editing the app "Pipeline board" \(page\) in department D2\.1 Desktop app\./.test(seed));
  assert(/Department charter: Sutra Desktop — the Mac app/.test(seed));
  assert(/move this app to another department or archive it/.test(seed));
  assert.strictEqual(JSON.stringify(opts), JSON.stringify({ pin: { department_ref: "r2" } }));
});

/* 10. + New app: seeded chat that asks what kind; provider gate */
test("+ New app: chat at the apps root seeded with the pin + the three questions; no provider -> recovery note, no session", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2" }) });
  const sess = T.modNew();
  assert(sess);
  assert.deepStrictEqual(T.calls.newSession, [["/tmp/mods", "r2"]]);
  assert.strictEqual(sess.title, "New app · Desktop app");
  const seed = T.calls.submitTurn[0][0];
  assert(seed.startsWith("ROUTING PIN"));
  assert(/Create a new app in department D2\.1 Desktop app\./.test(seed) && /\(1\) what kind/.test(seed) && /department:\{ref:"r2"\}/.test(seed));
  assert.strictEqual(JSON.stringify(sess.app), JSON.stringify({ id: null, mode: "new", department_ref: "r2" }));
  const T2 = fresh({ SETTINGS: { provider: "" }, S: loaded(ROOT_VIEW) });
  assert.strictEqual(T2.modNew(), null);
  assert.strictEqual(T2.calls.newSession.length, 0);
  assert(/Connect a chat provider in Settings/.test(T2.SCREENS.modules()));
});

/* 11. done hook: touch then forced read */
test("modOnSessionDone: POST /touch for an edit session, then loadModules(true)", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2" }) });
  T.apiPost = (p, b) => { T.calls.apiPost.push([p, b]); return Promise.resolve({ changed: true }); };
  /* the forced read must RESOLVE here, or the hook's promise never settles and
     the suite would exit with no verdict (a silent pass) */
  T.apiGet = (p) => { T.calls.apiGet.push(p); return Promise.resolve(DESK_VIEW.modules); };
  return T.modOnSessionDone({ id: "s-9", app: { id: "m<1", mode: "edit", department_ref: "r2" } }).then(() => {
    assert.strictEqual(JSON.stringify(T.calls.apiPost), JSON.stringify([["/api/modules/m%3C1/touch", { mode: "edit", session_id: "s-9" }]]));
    assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=1&department=r2", "forced read after touch");
  });
});

/* 12. narrow pane: crumb replaces the tree when an app is open (D-M20) */
test("narrow pane with an app open: no rail, a crumb back to the department", () => {
  const T = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2", modSel: "m<1", modNarrow: true }) });
  const out = T.SCREENS.modules();
  assert(!/<nav/.test(out), "tree yields");
  assert(/class="mod-back" data-modback>‹ Desktop app · 2 apps<\/a>/.test(out));
  assert(/data-modedit/.test(out));
  const T2 = fresh({ S: loaded(DESK_VIEW, { modDept: "r2", modKey: "?subtree=1&department=r2", modNarrow: true }) });
  assert(/<nav/.test(T2.SCREENS.modules()), "department view keeps the tree (stacked by the container query)");
});

/* 13. never blank */
test("never blank: empty department hint, empty registry = Unassigned only, building row renders, error card without a fallback list", () => {
  const empty = api({ department: { ref: "r3", path: "D2.D2", name: "Website", description: "" }, groups: {} });
  assert(/Nothing here yet\. New app puts it in Website\./.test(fresh({ S: loaded(empty, { modDept: "r3", modKey: "?subtree=1&department=r3" }) }).SCREENS.modules()));
  const T = fresh({ DOMAINS: [], S: loaded(api({ root: null, department: null, groups: { system: SYS, unassigned: [USER_CHAT] } })) });
  const out = T.SCREENS.modules();
  assert(/data-moddept="unassigned"/.test(out) && !/data-moddept="r0"/.test(out) && />System</.test(out) && !/puts it in/.test(out));
  const building = { id: "half", name: "half", kind: "chat", status: "draft", building: true, warning: "building… — this app's manifest is not readable yet", department: null, surface: {}, reserved: false };
  const T3 = fresh({ S: loaded(api({ groups: { system: SYS, unassigned: [building] } }), { modSel: "half" }) });
  assert(/building…/.test(T3.SCREENS.modules()));
  const T4 = fresh({ S: { modules: { modules: [], groups: null, error: "boom" }, modKey: "?subtree=1", sessions: [] } });
  const e = T4.SCREENS.modules();
  assert(/Apps unavailable/.test(e) && /boom/.test(e) && !/sys-/.test(e));
});

/* 14. open paths */
test("open paths: chat app opens a pinned session with its instructions; link opens the screen and the accordion follows; page has nothing to open", () => {
  const T = fresh({ S: loaded(DESK_VIEW) });
  assert.strictEqual(T.modOpen(USER_CHAT), true);
  assert.deepStrictEqual(T.calls.newSession, [["", "r2"]]);
  const [seed, , opts] = T.calls.submitTurn[0];
  assert(seed.startsWith("ROUTING PIN") && /\ngo$/.test(seed));
  assert.strictEqual(JSON.stringify(opts), JSON.stringify({ pin: { department_ref: "r2" } }));
  const shadow = { id: "shadow", name: "Shadow", kind: "link", status: "ready", surface: { screen: "shadow" }, reserved: false, department: dep(DESK) };
  assert.strictEqual(T.modOpen(shadow), true);
  assert.deepStrictEqual(T.calls.openScreen, ["shadow"]);
  assert.strictEqual(T.S.ui.railOpen, "focus");
  assert.strictEqual(T.modOpen(USER_PAGE), false);
  assert.strictEqual(T.modOpen({ id: "t", kind: "link", surface: { screen: "terminal" }, reserved: false }), false);
});

/* 15. facets route into the Departments family */
test("facets: Live/Draft/Directory set S.view and open Departments; Apps opens the Apps screen", () => {
  const T = fresh({ S: loaded(ROOT_VIEW) });
  T.modFacet("dir");
  assert.strictEqual(T.S.view, "dir");
  T.modFacet("modules");
  assert.deepStrictEqual(T.calls.openScreen, ["departments", "modules"]);
  assert.strictEqual(T.S.ui.railOpen, "org");
});

/* 16. selection = server-side query, keyed */
test("selecting a department reloads with department=<ref>; root drops the param; subtree in the key; opening an app selects it", () => {
  const T = fresh({ S: loaded(ROOT_VIEW, { modSel: "scratch" }) });
  T.modSelectDept("r1");
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=1&department=r1");
  assert.strictEqual(T.S.modSel, null);
  T.modSelectDept(null);
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=1");
  T.S.modSubtree = false; T.modSelectDept("unassigned");
  assert.strictEqual(T.calls.apiGet[T.calls.apiGet.length - 1], "/api/modules?subtree=0&department=unassigned");
  T.modOpenApp("scratch");
  assert.strictEqual(T.S.modSel, "scratch");
});

/* 17. Directory parity: the extracted helper still renders the Directory rail shape */
test("dirRail: Directory options give #dir- anchors, kid counts on groups, .dsub leaves; extra() nests rows; domainsDirectory uses it", () => {
  const T = fresh();
  const d = T.dirData();
  const tops = d.kids.get(d.root.ref) || [];
  const rail = T.dirRail({ tops, kids: d.kids, q: "",
    link: (x, inner, cls) => `<a${cls ? ` class="${cls}"` : ""} href="#dir-${x.ref}">${inner}</a>`,
    count: (x, ch, all) => ch.length ? all.length : null });
  assert(/<a href="#dir-r1">Experience<\/a><span class="navcount">2<\/span>/.test(rail));
  assert(/<a class="dsub" href="#dir-r2"><span class="chip">D2\.1<\/span>Desktop app<\/a>/.test(rail));
  assert(!/Old/.test(rail));
  const withExtra = T.dirRail({ tops, kids: d.kids, q: "", link: (x, inner) => `<a href="#">${inner}</a>`, extra: x => x.ref === "r4" ? '<a class="dsub modleaf">app</a>' : "" });
  assert(/<details class="navgrp"[^>]*>[^]*?Analytics[^]*?<a class="dsub modleaf">app<\/a>/.test(withExtra), "a leaf with extra content becomes a group holding it");
  const body = orgSrc.slice(orgSrc.indexOf("function domainsDirectory"), orgSrc.indexOf("SCREENS.departments"));
  assert(/dirRail\(/.test(body) && !/const navEntry/.test(body));
});

Promise.all(pending).then(() => {
  console.log(`\n${ran - failed}/${ran} passed`);
  process.exit(failed ? 1 : 0);
});
