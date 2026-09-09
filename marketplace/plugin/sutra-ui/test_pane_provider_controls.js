#!/usr/bin/env node
/*
 * test_pane_provider_controls.js -- the ⋮ pane's provider-dependent controls
 * resolve their ACTIONS from the active chat provider, not from Settings.
 *
 * TWO INDEPENDENT DEFECTS ARE PINNED HERE, and they are not variants of one:
 *
 *   USAGE   asked the WRONG provider. usagePopHtml() and loadUsage() both read
 *           SETTINGS.provider, so a Codex chat's Usage panel fetched
 *           ANTHROPIC's account and usage and rendered them under "Plan usage".
 *           Broken in the live session too -- never a refresh regression.
 *
 *   MODEL   asked the RIGHT provider and had no data. MODELS_BY_PROVIDER is
 *           written once by loadRuntime() in boot(), and codex's entry there
 *           comes from an in-process cache warmed only by the AI Provider
 *           screen's probe -- so on any load where Settings was never opened
 *           the dropdown held `[CLI default]` alone and codexEffortsFor()
 *           returned [].
 *
 * Both are tested on the SHIPPED bytes: the real loadUsage executed against a
 * recording apiGet, the real usagePopHtml, and the real wire() handler
 * extracted from its 900-line function and fired against a fake select --
 * a handler that never runs is invisible to a logic test.
 *
 * Run: node test_pane_provider_controls.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const state = J("01-state.js");
const helpers = J("02-helpers.js");
const screens = J("04-screens.js");
const chat = J("05-chat.js");
const render = J("06-render.js");
const loaders = J("07-loaders.js");
const boot = J("08-boot.js");

let pass = 0, fail = 0;
const queue = [];
const test = (n, f) => queue.push([n, f]);
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(a === b, (m || "") + " expected " + JSON.stringify(b)
                               + " got " + JSON.stringify(a));

function grab(src, name) {
  const start = src.indexOf("function " + name + "(");
  assert(start >= 0, "could not find function " + name);
  let i = src.indexOf("{", start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("unbalanced braces reading " + name);
}
/* async function <name>( -- loadUsage is one */
function grabAsync(src, name) {
  const start = src.indexOf("async function " + name + "(");
  assert(start >= 0, "could not find async function " + name);
  let i = src.indexOf("{", start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("unbalanced braces reading " + name);
}
/* One statement, from a needle to the `;` that closes it at depth zero. The
   wire() handlers are statements inside a huge function, so grab() cannot see
   them and a copy in the test would prove nothing about what ships. */
function grabStatement(src, needle) {
  const start = src.indexOf(needle);
  assert(start >= 0, "could not find statement starting " + needle);
  let round = 0, curly = 0;
  for (let j = start; j < src.length; j++) {
    const c = src[j];
    if (c === "(") round++; else if (c === ")") round--;
    else if (c === "{") curly++; else if (c === "}") curly--;
    else if (c === ";" && round === 0 && curly === 0) return src.slice(start, j + 1);
  }
  throw new Error("no statement end found for " + needle);
}
function grabConst(src, name) {
  const m = new RegExp("^(?:const|let|var) " + name + "\\s*=[\\s\\S]*?;$", "m").exec(src);
  assert(m, "could not find const " + name);
  return m[0];
}

/* The provider table the server publishes. usage_kind is its declaration:
   claude reports a rate-limit window, codex reports per-turn tokens and a plan,
   deepseek a balance, and each has its own endpoint and its own renderer. */
const TABLE = [
  { id: "claude", name: "Claude Code", runnable: true, usage_kind: "window-percent" },
  { id: "codex", name: "OpenAI Codex", runnable: true, usage_kind: "tokens" },
  { id: "deepseek", name: "DeepSeek", runnable: true, usage_kind: "balance" },
];

/* Chat A on Codex (server said so), Chat B on Claude, Chat D on DeepSeek. */
const SESSIONS = () => [
  { id: "A", title: "Chat A", channel: { id: "codex", source: "chat-history" } },
  { id: "B", title: "Chat B", channel: { id: "claude", source: "settings" } },
  { id: "D", title: "Chat D", channel: { id: "deepseek", source: "chat-history" } },
];

/* ── 1. the Usage panel: branch + fetch, on the shipped bytes ────────────── */

function usageBox(models) {
  const box = {
    S: { usagePop: null, sessions: SESSIONS(), usage: null, account: null,
         codexPlan: null, deepseekUsage: null, model: {}, paneMenu: null },
    /* THE GLOBAL DEFAULT IS CLAUDE in every case below, so any Claude answer
       on a Codex pane is the defect and not a coincidence. */
    SETTINGS: { provider: "claude", model_by_provider: {} },
    PROVIDERS: TABLE,
    MODELS_BY_PROVIDER: models || {},
    got: [],
    esc: (x) => String(x == null ? "" : x).replace(/[&<>"]/g, c =>
           ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
    usageRowsHtml: () => "<!--CLAUDE-WINDOW-ROWS-->",
    codexPlanBodyHtml: () => "<!--CODEX-PLAN-ROWS-->",
    deepseekBalanceRowsHtml: () => "<!--DEEPSEEK-BALANCE-ROWS-->",
    deepseekTokensHtml: () => "",
    render: () => {},
    console,
  };
  box.apiGet = async (url) => { box.got.push(url); return { available: true, url: url }; };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessProviderRequest"),
    grab(chat, "providerLabel"),
    grab(render, "paneProvider"),
    grab(helpers, "usageKindOf"),
    grab(helpers, "usagePopProvider"),
    grab(screens, "usagePopHtml"),
    grabAsync(boot, "loadUsage"),
    /* the ⋮ Usage row, verbatim: it is what sets S.usagePop and then fetches */
    grab(loaders, "paneMenuAction"),
  ].join("\n") + "\n;globalThis.__U={usagePopProvider,usagePopHtml,loadUsage,paneMenuAction};",
    { filename: "usage#extract" }).runInContext(box);
  return box;
}

/* Which branch did the popover render? Named by the provider it belongs to. */
function popKind(html) {
  if (/CODEX-PLAN-ROWS|Codex plan usage/.test(html)) return "codex";
  if (/DEEPSEEK-BALANCE-ROWS|DeepSeek usage/.test(html)) return "deepseek";
  if (/CLAUDE-WINDOW-ROWS|Plan usage/.test(html)) return "claude";
  if (/publishes no usage figure/.test(html)) return "none";
  return "?";
}

test("Codex chat → the Usage row fetches CODEX, never Anthropic", async () => {
  const box = usageBox();
  /* the real ⋮ row: sets S.usagePop, then calls loadUsage with the provider */
  box.__U.paneMenuAction("A", "usage");
  await new Promise(r => setImmediate(r));
  eq(box.S.usagePop, "A", "the popover did not open on this pane");
  assert(box.got.some(u => /\/api\/providers\/codex\/plan/.test(u)),
         "codex's own endpoint was never called: " + JSON.stringify(box.got));
  assert(!box.got.some(u => /\/api\/usage|\/api\/account/.test(u)),
         "it read ANTHROPIC's account/usage on a Codex chat: " + JSON.stringify(box.got));
});

test("Codex chat → the Usage panel renders CODEX's plan", async () => {
  const box = usageBox();
  box.S.usagePop = "A";
  eq(box.__U.usagePopProvider(), "codex", "the panel resolved the wrong provider —");
  eq(popKind(box.__U.usagePopHtml()), "codex",
     "the popover drew another provider's panel on a Codex chat —");
});

test("Claude chat → Usage is unchanged: the window, from Anthropic", async () => {
  const box = usageBox();
  box.__U.paneMenuAction("B", "usage");
  await new Promise(r => setImmediate(r));
  eq(box.__U.usagePopProvider(), "claude");
  eq(popKind(box.__U.usagePopHtml()), "claude", "Claude's own panel changed");
  assert(box.got.some(u => /\/api\/account/.test(u)) &&
         box.got.some(u => /\/api\/usage/.test(u)),
         "Claude's two reads were dropped: " + JSON.stringify(box.got));
  assert(!box.got.some(u => /codex|deepseek/.test(u)),
         "a Claude chat reached another provider: " + JSON.stringify(box.got));
});

test("DeepSeek chat → its balance, its endpoint (non-Codex, unchanged)", async () => {
  const box = usageBox();
  box.__U.paneMenuAction("D", "usage");
  await new Promise(r => setImmediate(r));
  eq(box.__U.usagePopProvider(), "deepseek");
  eq(popKind(box.__U.usagePopHtml()), "deepseek");
  assert(box.got.some(u => /\/api\/deepseek\/usage/.test(u)),
         "the balance read was dropped: " + JSON.stringify(box.got));
  assert(!box.got.some(u => /\/api\/usage|\/api\/account/.test(u)),
         "it also read Anthropic's: " + JSON.stringify(box.got));
});

test("no pane → Settings still governs, and that is the only fallback", async () => {
  /* The Usage and Settings SCREENS describe the app, not a chat: they call
     loadUsage with no provider, and must keep the global default. */
  const box = usageBox();
  box.S.usagePop = null;
  eq(box.__U.usagePopProvider(), "claude", "the fallback is not the global default");
  await box.__U.loadUsage(true);            /* exactly how openScreen calls it */
  assert(box.got.some(u => /\/api\/usage/.test(u)),
         "the screen's own read was lost: " + JSON.stringify(box.got));
  /* And with the global default set to Codex, the screen follows THAT. */
  const box2 = usageBox();
  box2.SETTINGS.provider = "codex";
  await box2.__U.loadUsage(true);
  assert(box2.got.some(u => /codex\/plan/.test(u)),
         "the screen ignored the global provider: " + JSON.stringify(box2.got));
});

test("the panel and the fetch cannot disagree", async () => {
  /* One expression feeds both, which is the constraint: a popover that draws
     Codex while the request reads Anthropic is the original bug. */
  const src = grab(screens, "usagePopHtml") + grabAsync(boot, "loadUsage");
  assert(!/usageKindOf\(\(SETTINGS \|\| \{\}\)\.provider\)/.test(src),
         "a SETTINGS.provider read survives in the pane usage path");
  assert(/usagePopProvider\(\)/.test(grab(screens, "usagePopHtml")),
         "the popover no longer asks which pane it belongs to");
  const i = loaders.indexOf('case "usage":');
  assert(i >= 0, "the ⋮ Usage row is gone");
  const rowCall = loaders.slice(i, loaders.indexOf("break;", i));
  assert(/usagePopProvider\(\)/.test(rowCall),
         "the ⋮ Usage row does not pass the pane's provider: " + rowCall);
});

/* ── 2. Codex model data, warmed by the existing path ────────────────────── */

const MENU_HANDLER = grabStatement(loaders, 'panes.querySelectorAll("[data-panemenu]")');

function menuBox() {
  const box = {
    S: { paneMenu: null, sessions: SESSIONS() },
    SETTINGS: { provider: "claude" },
    PROVIDERS: TABLE,
    probes: 0,
    render: () => {},
    document: { querySelector: () => null },
    console,
  };
  box.loadCodexAuth = () => { box.probes++; };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessProviderRequest"),
    grab(render, "paneProvider"),
    "var panes = { querySelectorAll: () => globalThis.__btn ? [globalThis.__btn] : [] };",
    MENU_HANDLER,
  ].join("\n"), { filename: "menu#extract" }).runInContext(box);
  return box;
}
function openMenu(box, sid) {
  box.__btn = { dataset: { panemenu: sid }, focus: () => {} };
  vm.runInContext("(function(){ " + MENU_HANDLER + " })()", box);
  assert(typeof box.__btn.onclick === "function", "wire() attached no ⋮ handler");
  box.__btn.onclick();
}

test("opening the ⋮ on a Codex chat asks the existing Codex loader", async () => {
  const box = menuBox();
  openMenu(box, "A");
  eq(box.S.paneMenu, "A", "the menu did not open");
  eq(box.probes, 1, "the Codex model/auth path was never triggered —");
});

test("...and it is the EXISTING path, not a new one", async () => {
  /* CODE ONLY. The handler's comment names the state it does NOT touch (that
     is what the comment is for), so a naive grep over the whole statement
     would fail on the explanation rather than on the behaviour. */
  const code = MENU_HANDLER.replace(/\/\*[\s\S]*?\*\//g, " ")
                           .replace(/\/\/[^\n]*/g, " ");
  assert(/loadCodexAuth\(\)/.test(code),
         "the handler does not call the existing loader");
  assert(!/apiGet|fetch\(|models_by_provider|MODELS_BY_PROVIDER/.test(code),
         "the handler fetches or parses models itself -- that is a second path");
  assert(!/loadCodexAuth\(true\)/.test(code),
         "forced: loadCodexAuth's own guards are what keep this to one probe");
});

test("a Claude chat opens no Codex probe", async () => {
  const box = menuBox();
  openMenu(box, "B");
  eq(box.S.paneMenu, "B");
  eq(box.probes, 0, "a Claude pane spawned `codex login status`");
});

test("CLOSING a Codex menu probes nothing", async () => {
  const box = menuBox();
  openMenu(box, "A");                       /* open  */
  openMenu(box, "A");                       /* close */
  eq(box.S.paneMenu, null, "the menu did not close");
  eq(box.probes, 1, "closing the menu fired a second probe");
});

/* ── 3. what the warm answer puts on screen ─────────────────────────────── */

/* The two states of MODELS_BY_PROVIDER measured against the live server on
   2026-09-09: COLD is what GET /api/settings publishes when codex discovery
   has never run (the catalogue entry alone); WARM is the same call after
   GET /providers/codex/auth ran refresh_if_stale. Claude's list is identical
   in both, which is what makes the codex-only difference provable. */
const CLAUDE_MODELS = [{ id: "", name: "CLI default" }, { id: "opus", name: "Opus" },
                        { id: "sonnet", name: "Sonnet" }];
const COLD = { claude: CLAUDE_MODELS, codex: [{ id: "", name: "CLI default" }] };
const WARM = { claude: CLAUDE_MODELS, codex: [
  { id: "", name: "CLI default" },
  { id: "gpt-5.6-terra", name: "GPT-5.6-Terra", default: true,
    efforts: ["low", "medium", "high", "xhigh", "max", "ultra"] },
  { id: "gpt-5.6-luna", name: "GPT-5.6-Luna",
    efforts: ["low", "medium", "high", "xhigh", "max"] },
  { id: "gpt-5.5", name: "GPT-5.5", efforts: ["low", "medium", "high", "xhigh"] },
] };

function paneBox(models) {
  const box = {
    S: { paneMenu: "A", sessions: SESSIONS(), chatProvider: {}, chatProviderNote: {},
         repo: {}, prs: {}, optsOpen: {}, sessTab: {}, model: {}, turnOpts: {},
         ui: { paneCollapsed: {} }, usagePop: null, usage: null, codexPlan: null },
    SETTINGS: { provider: "claude", model_by_provider: {} },
    SEED: { provider: "claude" },
    PROVIDERS: TABLE,
    MODELS_BY_PROVIDER: models,
    TURN_OPTIONS_BY_PROVIDER: { claude: ["effort", "max_budget_usd"],
                                codex: ["reasoning_summary", "verbosity", "reasoning_effort"] },
    PERM_MODES_BY_PROVIDER: { claude: ["plan", "acceptEdits"], codex: ["plan", "acceptEdits"] },
    esc: (x) => String(x == null ? "" : x).replace(/[&<>"]/g, c =>
           ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
    cwdLabel: () => "sutra-ui", sessCwd: () => "/w",
    permSelect: () => '<select data-perm="x"></select>',
    providerUsage: () => null, usageKindOf: () => "tokens",
    turnOptsFor: () => new Set(["reasoning_effort"]),
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessProviderRequest"),
    grab(chat, "providerLabel"),
    grab(render, "paneProvider"),
    grab(render, "paneDeclProvider"),
    grab(render, "codexEffortsFor"),
    grab(render, "paneMenuHtml"),
    grab(loaders, "codexApplyState"),
  ].join("\n") + "\n;globalThis.__P={paneMenuHtml,codexEffortsFor,codexApplyState};",
    { filename: "pane#extract" }).runInContext(box);
  return box;
}
function modelOptions(box, sid) {
  const s = box.S.sessions.find(x => x.id === sid);
  /* paneMenuHtml draws nothing for a pane whose menu is shut, so the pane
     being asked about is the one opened. */
  const prev = box.S.paneMenu;
  box.S.paneMenu = sid;
  const html = box.__P.paneMenuHtml(s);
  box.S.paneMenu = prev;
  const m = /<span class="mk">Model<\/span>[\s\S]*?<\/select>/.exec(html);
  return m ? [...m[0].matchAll(/<option value="([^"]*)"/g)].map(o => o[1]) : null;
}

test("COLD: the Codex Model dropdown has nothing but the CLI default", async () => {
  const box = paneBox(COLD);
  eq(JSON.stringify(modelOptions(box, "A")), JSON.stringify([""]),
     "the cold state this fix exists for is not reproduced —");
  eq(JSON.stringify(box.__P.codexEffortsFor("codex", "")), "[]",
     "cold efforts");
});

test("the loader's answer populates the Model dropdown and the efforts", async () => {
  /* codexApplyState is what loadCodexAuth feeds with the auth response. This
     is the whole point of routing through the existing path: one answer fills
     the picker AND the per-model effort sets. */
  const box = paneBox(COLD);
  const applied = box.__P.codexApplyState({ state: "chatgpt", models_by_provider: WARM });
  assert(applied, "codexApplyState reported nothing applied");
  eq(JSON.stringify(modelOptions(box, "A")),
     JSON.stringify(["", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"]),
     "the Model dropdown is still empty after the load —");
  eq(JSON.stringify(box.__P.codexEffortsFor("codex", "")),
     JSON.stringify(["low", "medium", "high", "xhigh", "max", "ultra"]),
     "Reasoning effort has no options after the load —");
  eq(JSON.stringify(box.__P.codexEffortsFor("codex", "gpt-5.5")),
     JSON.stringify(["low", "medium", "high", "xhigh"]),
     "the effort set is not the SELECTED model's");
});

test("non-Codex panes are untouched by any of it", async () => {
  const box = paneBox(COLD);
  const before = JSON.stringify(modelOptions(box, "B"));
  box.__P.codexApplyState({ state: "chatgpt", models_by_provider: WARM });
  eq(JSON.stringify(modelOptions(box, "B")), before, "the Claude pane's picker moved");
  eq(JSON.stringify(modelOptions(box, "B")),
     JSON.stringify(["", "opus", "sonnet"]), "Claude's own list");
  eq(box.SETTINGS.provider, "claude", "the global default was rewritten");
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); console.log("ok   - " + n); pass++; }
    catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; }
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
