#!/usr/bin/env node
/* test_modules.js -- Org > Modules (2.247.0): registration, the two-column
   screen, the never-blank states, and the three open paths.
   Same discipline as test_shadow_home.js: run the REAL module under vm with a
   minimal stub context, assert on the real functions.
   Run: node test_modules.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const src = fs.readFileSync(path.join(__dirname, "static", "js", "18-modules.js"), "utf8");
const state = fs.readFileSync(path.join(__dirname, "static", "js", "01-state.js"), "utf8");

let failed = 0, ran = 0;
function test(name, fn){
  ran++;
  try { fn(); console.log("ok   " + name); }
  catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.message)); }
}

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], openScreen: [], newSession: [], submitTurn: [], goDest: [], render: 0 };
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { shadow: () => "", balance: () => "", teamsutra: () => "", settings: () => "", git: () => "" },
    TITLES: { settings: ["AI Provider", ""], git: ["Git", ""], teamsutra: ["Help", ""] },
    DEST_PLANES: { settings: [{ group: "Tools", rows: [{ screen: "terminal" }, { screen: "git" }] },
                              { group: "System", rows: [{ screen: "settings" }] }] },
    S: Object.assign({ ui: { dest: "org", railOpen: "org" } }, opts.S || {}),
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
  vm.runInContext(src, ctx);
  return ctx;
}

const USER_PAGE = { id: "m<1", name: "Pipeline board", tagline: "deals by stage", kind: "page", status: "ready",
                    origin: { created_by: "disk", at: "2026-09-08T10:00:00Z" }, surface: { entry: "index.html" }, guard: {}, has_page: true, reserved: false, warning: null };
const USER_CHAT = { id: "friday", name: "Friday review", tagline: "", kind: "chat", status: "draft",
                    origin: { created_by: "shadow", at: "2026-09-08T10:00:00Z" }, surface: { instructions: "go" }, guard: {}, has_page: false, reserved: false, warning: null };
const SYS = [
  { id: "sys-balance", name: "Balance", tagline: "", kind: "link", status: "ready", origin: { created_by: "system" }, surface: { screen: "balance" }, guard: {}, reserved: false, warning: null },
  { id: "sys-help", name: "Help", tagline: "", kind: "link", status: "ready", origin: { created_by: "system" }, surface: { screen: "teamsutra" }, guard: {}, reserved: false, warning: null },
  { id: "sys-settings", name: "Settings", tagline: "", kind: "link", status: "ready", origin: { created_by: "system" }, surface: { screen: "settings", sections: "client" }, guard: {}, reserved: false, warning: null },
];
const loaded = (mods, extra) => Object.assign({ modules: { modules: mods, count_user: 0, archived: 0, home: "/tmp/mods", error: null } }, extra || {});

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

/* 4. first paint */
test("first paint: reads once, renders a placeholder longer than the surfaces floor", () => {
  const T = fresh();
  const out = T.SCREENS.modules();
  assert(/Reading your modules/.test(out));
  assert(out.length > 40);
  assert.deepStrictEqual(T.calls.apiGet, ["/api/modules"]);
  T.SCREENS.modules();
  assert.strictEqual(T.calls.apiGet.length, 1, "no second read while the first is in flight");
});

/* 5. populated */
test("populated: Yours before System, kind pill on user rows only, sandboxed page iframe, escaped id", () => {
  const T = fresh({ S: loaded([...SYS, USER_PAGE], { modSel: "m<1" }) });
  const out = T.SCREENS.modules();
  assert(out.indexOf("Yours") < out.indexOf("System"));
  assert(/data-mod="m&lt;1"/.test(out), "row id escaped");
  assert(/<span class="pill mod-kind">page<\/span>/.test(out));
  const sysRow = out.slice(out.indexOf('data-mod="sys-balance"'), out.indexOf('data-mod="sys-help"'));
  assert(!/mod-kind/.test(sysRow), "system rows carry no kind pill");
  assert(/<iframe class="mod-frame" src="\/api\/modules\/m&lt;1\/page\?theme=dark&amp;v=0" [^>]*sandbox="allow-scripts">/.test(out), "iframe must be sandboxed with allow-scripts ONLY");
  assert(!/allow-same-origin/.test(out));
});

/* 6. settings sections derived from the plane */
test("sys-settings detail derives its sections from DEST_PLANES.settings", () => {
  const T = fresh({ S: loaded(SYS, { modSel: "sys-settings" }) });
  const out = T.SCREENS.modules();
  assert(/data-screen="git"/.test(out) && /data-screen="settings"/.test(out) && /data-screen="terminal"/.test(out));
  assert(/>AI Provider</.test(out), "label comes from TITLES");
  assert(/>Terminal</.test(out), "terminal has no TITLES row; label map covers it");
});

/* 7. empty Yours = empty state + System still renders */
test("empty Yours: empty-state card, System group still listed, never blank", () => {
  const T = fresh({ S: loaded(SYS) });
  const out = T.SCREENS.modules();
  assert(/Nothing you have built yet/.test(out));
  assert(/data-mod="sys-balance"/.test(out));
  assert(out.length > 40);
});

/* 8. unavailable: no fallback registry */
test("API error: 'Modules unavailable' and NO client-side system list", () => {
  const T = fresh({ S: { modules: { modules: [], error: "boom" } } });
  const out = T.SCREENS.modules();
  assert(/Modules unavailable/.test(out) && /boom/.test(out));
  assert(!/sys-/.test(out), "a fallback list would be a second registry");
  assert(out.length > 40);
});

/* 9. chat open */
test("chat open: goDest(chats), newSession, title set, instructions become the first turn", () => {
  const T = fresh({ S: loaded([USER_CHAT]) });
  assert.strictEqual(T.modOpen(USER_CHAT), true);
  assert.deepStrictEqual(T.calls.goDest, ["chats"]);
  assert.deepStrictEqual(T.calls.newSession, [""]);
  assert.deepStrictEqual(T.calls.submitTurn, [["go", "s-9"]]);
});

/* 10. link open follows the accordion */
test("link open: openScreen(target) then railOpen follows the owning inline destination", () => {
  const T = fresh({ S: loaded(SYS) });
  const shadow = { id: "shadow", name: "Shadow", kind: "link", status: "ready", surface: { screen: "shadow" }, reserved: false };
  assert.strictEqual(T.modOpen(shadow), true);
  assert.deepStrictEqual(T.calls.openScreen, ["shadow"]);
  assert.strictEqual(T.S.ui.railOpen, "focus");
  const term = { id: "t", name: "T", kind: "link", status: "ready", surface: { screen: "terminal" }, reserved: false };
  assert.strictEqual(T.modOpen(term), false, "terminal is a pane toggle, never a link target");
  const T2 = fresh({ S: loaded([term], { modSel: "t" }) });
  assert(/cannot be opened/.test(T2.SCREENS.modules()));
});

/* 11. reserved rows render but never open */
test("reserved sys- folder: listed under Yours with the warning, Open refused", () => {
  const fake = { id: "sys-fake", name: "sys-fake", kind: "chat", status: "draft", surface: {}, reserved: true, warning: "reserved id, not loaded" };
  const T = fresh({ S: loaded([...SYS, fake], { modSel: "sys-fake" }) });
  const out = T.SCREENS.modules();
  assert(/reserved id/.test(out));
  assert.strictEqual(T.modOpen(fake), false);
});

console.log(`\n${ran - failed}/${ran} passed`);
process.exit(failed ? 1 : 0);
