#!/usr/bin/env node
/*
 * test_composer_tools.js -- the message box's two controls, and the timeline's
 * tool cards.
 *
 * TWO THINGS ARE PINNED HERE.
 *
 *   THE COMPOSER. The model row used to be three clicks down the pane menu and
 *   said nothing about thinking level or fast mode, and the permission control
 *   offered raw native mode ids (`bypassPermissions`) as though they were
 *   English. Now one chip beside the box says what will answer -- "Claude ·
 *   Opus 5 · High" -- and one chip under it says what that thing may do, in
 *   the four plain words of the shared access contract.
 *
 *   THE TIMELINE. Every tool call rendered as one flat line, so a subagent, a
 *   shell command and a file edit were the same picture. There is now a card
 *   per kind, and the SAME classifier runs over stored history, so a chat from
 *   three months ago gets the new cards with nothing migrated on disk.
 *
 * Everything below runs the SHIPPED bytes: each function is extracted from its
 * module by brace matching, never re-typed here. The server-side keys the
 * controls read (model_catalog_by_provider, access_options, access_by_provider)
 * are supplied as FIXTURES, and a section at the end proves the controls still
 * render when they are absent -- which is their state until that lands.
 *
 * Run: node test_composer_tools.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const state = J("01-state.js");
const helpers = J("02-helpers.js");
const chat = J("05-chat.js");
const render = J("06-render.js");
const needs = J("14-needs-you.js");

let pass = 0, fail = 0;
const queue = [];
const test = (n, f) => queue.push([n, f]);
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(a === b, (m || "") + " expected " + JSON.stringify(b)
                               + " got " + JSON.stringify(a));
const deq = (a, b, m) => eq(JSON.stringify(a), JSON.stringify(b), m);

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
function grabConst(src, name) {
  const m = new RegExp("^(?:const|let|var) " + name.replace(/[$]/g, "\\$")
                       + "\\s*=[\\s\\S]*?;$", "m").exec(src);
  assert(m, "could not find const " + name);
  return m[0];
}

/* ── the fixtures ──────────────────────────────────────────────────────────
   The provider table is the server's own verdict on what can run: `pi` is a
   stand-in for a catalogued-but-NOT-runnable provider, which is why it must
   never become a tab. */
const TABLE = [
  { id: "claude", name: "Claude", runnable: true, usage_kind: "window-percent" },
  { id: "codex", name: "Codex", runnable: true, usage_kind: "tokens" },
  { id: "deepseek", name: "DeepSeek", runnable: true, usage_kind: "balance" },
  { id: "pi", name: "Pi CLI", runnable: false, reason: "no adapter in this build" },
];
/* SPEC B, shaped as the server will send it. Claude's efforts differ per model
   here on purpose: the thinking row must be the SELECTED model's, not a union. */
const CATALOG = {
  claude: {
    models: [
      { id: "", name: "Account default", note: "whatever the CLI is set to" },
      { id: "best", name: "Fable 5.1", tag: "newest",
        efforts: ["low", "medium", "high", "xhigh", "max"] },
      { id: "opus", name: "Opus 5", efforts: ["low", "medium", "high", "xhigh", "max"] },
      { id: "sonnet", name: "Sonnet 5", efforts: ["low", "medium", "high"] },
      { id: "haiku", name: "Haiku 4.5", efforts: ["low", "medium"] },
    ],
    more: [
      { id: "claude-opus-4-8", name: "Opus 4.8", efforts: ["low", "medium", "high"] },
      { id: "opus[1m]", name: "Opus (1M context)", efforts: ["low", "medium", "high"] },
    ],
    fast: false, default: "opus",
  },
  codex: {
    models: [
      { id: "", name: "CLI default" },
      { id: "gpt-5.6-terra", name: "GPT-5.6-Terra",
        efforts: ["low", "medium", "high", "xhigh", "max", "ultra"] },
      { id: "gpt-5.6-luna", name: "GPT-5.6-Luna", efforts: ["low", "medium", "high"] },
    ],
    more: [], fast: true, default: "gpt-5.6-terra",
  },
  deepseek: { models: [{ id: "deepseek-v4", name: "DeepSeek V4" }],
              more: [], fast: false, default: "deepseek-v4" },
};
const FLAT = {
  claude: [{ id: "", name: "CLI default" }, { id: "opus", name: "Opus" }],
  codex: [{ id: "", name: "CLI default" }],
  deepseek: [{ id: "deepseek-v4", name: "DeepSeek V4" }],
};
const SIX = [
  { id: "plan" }, { id: "acceptEdits", writes_files: true },
  { id: "bypassPermissions", writes_files: true }, { id: "auto" },
  { id: "manual", note: "approve every tool call by hand" },
  { id: "dontAsk", note: "used by routines" },
].map(m => Object.assign({ writes_files: false }, m));
const PMODES = {
  claude: ["plan", "acceptEdits", "bypassPermissions", "auto", "manual", "dontAsk"],
  codex: ["plan", "acceptEdits", "bypassPermissions"],
  deepseek: ["plan", "acceptEdits", "bypassPermissions"],
};
/* SPEC A, as the server will send it. */
const ACCESS_OPTS = [
  { id: "read", label: "Read only", desc: "Looks and plans. Changes nothing.", warn: false },
  { id: "edits", label: "Accept edits", desc: "Edits files in this folder. Asks for anything else.", warn: false },
  { id: "auto", label: "Approve for me", desc: "Same limit, but the tool approves routine requests itself.", warn: false },
  { id: "full", label: "Full access", desc: "Anything on this Mac, without asking.", warn: true },
];
const ACCESS_MAP = {
  claude: { read: "plan", edits: "acceptEdits", auto: "auto", full: "bypassPermissions" },
  codex: { read: "plan", edits: "acceptEdits", full: "bypassPermissions" },
  deepseek: { read: "plan", edits: "acceptEdits", full: "bypassPermissions" },
};
const TOPTS = {
  claude: ["effort", "max_budget_usd", "allowed_tools", "disallowed_tools", "append_system_prompt"],
  codex: ["reasoning_effort", "reasoning_summary", "verbosity"],
  deepseek: [],
};
const SESSIONS = () => [
  { id: "A", title: "Chat A", channel: { id: "claude", source: "settings" } },
  { id: "C", title: "Chat C", channel: { id: "codex", source: "chat-history" } },
  { id: "D", title: "Chat D", channel: { id: "deepseek", source: "chat-history" } },
];

function box(over) {
  const b = {
    S: { sessions: SESSIONS(), model: {}, turnOpts: {}, optsOpen: {}, perm: {},
         mdlMenu: null, accMenu: null, mdlTab: {}, mdlMore: {}, accAdv: {},
         toolOpen: {}, cwd: {}, sutraId: {}, chatProvider: {}, chatProviderNote: {},
         permConfirm: null, permError: null },
    SETTINGS: { provider: "claude", model_by_provider: { claude: "opus" },
                permission_mode: "plan", permission_mode_effective: "plan" },
    SEED: { provider: "claude" },
    PROVIDERS: TABLE,
    PERM_MODES: SIX,
    PERM_MODES_BY_PROVIDER: PMODES,
    MODELS_BY_PROVIDER: FLAT,
    MODEL_CATALOG_BY_PROVIDER: CATALOG,
    ACCESS_OPTIONS: ACCESS_OPTS,
    ACCESS_BY_PROVIDER: ACCESS_MAP,
    TURN_OPTIONS_BY_PROVIDER: TOPTS,
    location: { protocol: "http:", host: "127.0.0.1:7000" },
    posted: [],
    rendered: 0,
    console,
  };
  b.render = () => { b.rendered++; };
  b.apiPost = async (url, body) => { b.posted.push({ url, body });
                                     return { settings: b.SETTINGS }; };
  b.setPermMode = (mode) => { b.S.permConfirm = { mode }; };
  b.switchChatProvider = (s, target) => { b.switched = [s && s.id, target];
                                          b.S.chatProvider[s.id] = target; return "switched"; };
  b.closeClaudeChannel = () => {};
  b.streamingFor = () => false;
  b.sideStreamingFor = () => false;
  Object.assign(b, over || {});
  b.globalThis = b;
  vm.createContext(b);
  vm.runInContext([
    grabConst(helpers, "esc"),
    grab(needs, "escAttr"),
    grab(state, "fmtDur"),
    grab(state, "sessCwd"),
    grab(state, "sessSutraId"),
    grab(state, "sessProviderRequest"),
    grab(state, "claudeWsUrl"),
    grab(chat, "providerLabel"),
    /* 02-helpers: the catalogue, access and tool vocabulary */
    grab(helpers, "_catalogGlobal"), grab(helpers, "_accessOptionsGlobal"),
    grab(helpers, "_accessByProviderGlobal"), grab(helpers, "_settingsGlobal"),
    grab(helpers, "_modelsGlobal"), grab(helpers, "_permModesByProviderGlobal"),
    grab(helpers, "modelCatalogFor"), grab(helpers, "modelEntries"),
    grab(helpers, "modelEntryFor"), grab(helpers, "modelNameFor"),
    grab(helpers, "modelEffortsFor"), grab(helpers, "effortKeyFor"),
    grab(helpers, "effortLabel"),
    grabConst(helpers, "ACCESS_FALLBACK"), grabConst(helpers, "ACCESS_NATIVE_FALLBACK"),
    grab(helpers, "accessMapFor"), grab(helpers, "accessOptionsFor"),
    grab(helpers, "accessForMode"), grab(helpers, "sessPerm"),
    grab(helpers, "sessPermEffective"),
    grabConst(helpers, "TOOL_KIND_BY_NAME"), grabConst(helpers, "TOOL_KINDS"),
    grabConst(helpers, "TOOL_KIND_LABEL"),
    grab(helpers, "toolKindOf"), grab(helpers, "toolKindFor"),
    /* 06-render: the controls and the cards */
    grabConst(render, "TOPT_ALL"), grab(render, "turnOptsFor"),
    grab(render, "paneProvider"), grab(render, "paneDeclProvider"),
    grab(render, "paneModelValid"), grab(render, "composerModelFor"),
    grab(render, "composerModelLabel"), grab(render, "paneMenuHtml"),
    grab(render, "_pickBtn"), grab(render, "composerModelMenuHtml"),
    grab(render, "composerAccessLabel"), grab(render, "paneAccessRowHtml"),
    grab(render, "composerAccessMenuHtml"),
    grab(render, "_tcBase"), grab(render, "_tcDiff"), grab(render, "toolCardParts"),
    grab(render, "toolCardHtml"), grabConst(render, "TOOLCARD_WINDOW"),
    grab(render, "toolCallsHtml"), grab(render, "toolTimelineHtml"),
    grab(render, "pickComposerModel"), grab(render, "rememberModelForProvider"),
    grab(render, "setComposerEffort"), grab(render, "setSessAccess"),
    grab(render, "composerControlClick"), grab(render, "composerControlChange"),
  ].join("\n"), b, { filename: "composer#extract" });
  return b;
}

const sess = (b, id) => b.S.sessions.find(x => x.id === id);
/* every data-<attr> value in one blob of html */
const attrs = (h, name) =>
  [...h.matchAll(new RegExp('data-' + name + '="([^"]*)"', "g"))].map(m => m[1]);
const textOf = (h) => h.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

/* ══════════════════ 1. the model chip ══════════════════════════════════════ */

test("1a. the closed chip says who answers, which model, at what level", () => {
  const b = box();
  b.S.turnOpts.A = { effort: "high" };
  const h = b.composerModelLabel(sess(b, "A"), "claude");
  assert(h === "Claude · Opus 5 · High",
         "the Model row must read 'Claude · Opus 5 · High': " + h);
});

test("1b. no thinking level chosen -> the chip says so by omission, not by guessing", () => {
  const b = box();
  const h = b.composerModelLabel(sess(b, "A"), "claude");
  assert(h.includes("Claude · Opus 5"), h);
  assert(!/High|Low|Medium/.test(h), "a level nobody chose was printed: " + textOf(h));
});

test("1c. Fast mode shows on the chip once it is on", () => {
  const b = box();
  b.S.turnOpts.C = { service_tier: "fast" };
  const h = b.composerModelLabel(sess(b, "C"), b.paneProvider(sess(b, "C")));
  assert(/Fast/.test(h), "the chip hides a switch that changes what runs: " + textOf(h));
});

test("1d. the chip asks THIS chat's provider, never the global default", () => {
  /* Settings says claude in every fixture here, so any Claude answer on the
     Codex pane is the defect and not a coincidence. */
  const b = box();
  const h = b.composerModelLabel(sess(b, "C"), b.paneProvider(sess(b, "C")));
  assert(/Codex/.test(h) && !/Claude/.test(h), textOf(h));
});

/* ══════════════════ 2. the model menu ══════════════════════════════════════ */

function menu(b, sid) { b.S.mdlMenu = sid; return b.composerModelMenuHtml(sess(b, sid)); }

test("2a. provider tabs offer only what can actually run", () => {
  const b = box();
  const h = menu(b, "A");
  deq(attrs(h, "mdltab"), ["A:claude", "A:codex", "A:deepseek"],
      "a provider that cannot start was offered, or one that can was dropped —");
  assert(!/Pi CLI/.test(h), "a catalogued-but-unrunnable provider became a tab: " + h);
});

test("2b. the chat's own provider is the tab that opens selected", () => {
  const b = box();
  const h = menu(b, "C");
  const on = /<button class="mdltab on"[^>]*data-mdltab="C:([a-z]+)"/.exec(h);
  assert(on, "no tab is marked current: " + h);
  eq(on[1], "codex");
});

test("2c. the main list is that provider's models, More is a separate disclosure", () => {
  const b = box();
  const h = menu(b, "A");
  deq(attrs(h, "mdlpick"),
      ["A:claude:", "A:claude:best", "A:claude:opus", "A:claude:sonnet", "A:claude:haiku"],
      "the main list is not the catalogue's `models` —");
  assert(/data-mdlmore="A"/.test(h), "no More models control: " + h);
  assert(!h.includes("claude-opus-4-8"),
         "the More list is drawn before it is asked for: " + h);
});

test("2d. More models is ADDITIVE -- opening it keeps the main list", () => {
  const b = box();
  b.S.mdlMore.A = true;
  const h = menu(b, "A");
  const ids = attrs(h, "mdlpick");
  assert(ids.includes("A:claude:opus"), "the main list vanished: " + ids.join(","));
  assert(ids.includes("A:claude:claude-opus-4-8") && ids.includes("A:claude:opus[1m]"),
         "the older ids and aliases are missing: " + ids.join(","));
});

test("2e. a provider with no More list gets no More control", () => {
  const b = box();
  const h = menu(b, "C");
  assert(!/data-mdlmore/.test(h), "an empty disclosure was drawn: " + h);
});

test("2f. thinking levels are the SELECTED model's, not a union", () => {
  const b = box();
  b.S.model.A = "sonnet";
  deq(attrs(menu(b, "A"), "mdleff"),
      ["A:", "A:low", "A:medium", "A:high"],
      "Sonnet was offered a level it does not declare —");
  b.S.model.A = "haiku";
  deq(attrs(menu(b, "A"), "mdleff"), ["A:", "A:low", "A:medium"]);
});

test("2g. the chosen level is the one marked on, and it is the turn option", () => {
  const b = box();
  b.S.turnOpts.A = { effort: "xhigh" };
  const h = menu(b, "A");
  const on = /<button class="effbtn on"[^>]*data-mdleff="A:([a-z]*)"/.exec(h);
  assert(on, "no level marked current: " + h);
  eq(on[1], "xhigh");
});

test("2h. a provider that declares no levels gets no level row at all", () => {
  const b = box();
  const h = menu(b, "D");
  assert(!/data-mdleff/.test(h), "a row was drawn for a provider with nothing to put in it: " + h);
});

test("2i. Fast mode appears only where the catalogue says the provider has one", () => {
  const b = box();
  assert(/data-mdlfast="C"/.test(menu(b, "C")), "Codex declares fast:true and got no switch");
  assert(!/data-mdlfast/.test(menu(b, "A")),
         "Claude declares fast:false and was given a switch that does nothing");
  assert(!/data-mdlfast/.test(menu(b, "D")));
});

test("2j. the surviving turn options are reachable, and not on the bar", () => {
  const b = box();
  const h = menu(b, "A");
  assert(/data-mdlopts="A"/.test(h), "no way through to budget / allow only / never: " + h);
  assert(/budget, allow only, never, extra instructions/.test(h), textOf(h));
  /* DeepSeek honours none of them, so it must not be offered the door either. */
  assert(!/data-mdlopts/.test(menu(b, "D")), "an empty options box was offered: " + menu(b, "D"));
});

test("2k. a model marked unselectable is listed and refused, never hidden", () => {
  const b = box({});
  b.MODEL_CATALOG_BY_PROVIDER = Object.assign({}, CATALOG, { claude: Object.assign({},
    CATALOG.claude, { models: CATALOG.claude.models.concat(
      [{ id: "vision", name: "Vision", selectable: false,
         unavailable_reason: "this panel has no image channel" }]) }) });
  const h = menu(b, "A");
  assert(h.includes("Vision"), "it was hidden rather than explained: " + h);
  assert(/<button class="mdlopt" type="button" disabled/.test(h),
         "an unrunnable model was left pickable: " + h);
  assert(h.includes("no image channel"), "no reason given: " + h);
});

/* ══════════════════ 3. picking, and remembering per provider ═══════════════ */

test("3a. picking a model writes it back as model_by_provider", () => {
  const b = box();
  b.pickComposerModel("A", "claude", "sonnet");
  eq(b.S.model.A, "sonnet", "the per-pane override did not move —");
  eq(b.posted.length, 1, "nothing was persisted: " + JSON.stringify(b.posted));
  eq(b.posted[0].url, "/api/settings");
  deq(b.posted[0].body.model_by_provider, { claude: "sonnet" });
});

test("3b. the memory is PER PROVIDER -- one does not overwrite the other", () => {
  const b = box();
  b.SETTINGS.model_by_provider = { claude: "opus" };
  b.pickComposerModel("C", "codex", "gpt-5.6-luna");
  deq(b.posted[0].body.model_by_provider, { claude: "opus", codex: "gpt-5.6-luna" },
      "writing one provider's model erased another's —");
});

test("3c. switching provider and back restores the model", () => {
  /* The per-pane override is not per provider (the pane menu's old picker
     wrote it), so after a switch it can hold an id the new provider never had.
     A stale override must be ignored, or the chip reports a model that cannot
     be sent. */
  const b = box();
  b.SETTINGS.model_by_provider = { claude: "sonnet", codex: "gpt-5.6-luna" };
  b.S.model.A = "sonnet";
  eq(b.composerModelFor(sess(b, "A"), "claude"), "sonnet");
  /* the same pane, now looking at codex: the Claude id is not codex's */
  eq(b.composerModelFor(sess(b, "A"), "codex"), "gpt-5.6-luna",
     "a stale Claude override survived onto a Codex pane —");
  /* and back */
  eq(b.composerModelFor(sess(b, "A"), "claude"), "sonnet");
});

test("3d. picking under another provider's tab performs the existing switch", () => {
  const b = box();
  b.pickComposerModel("A", "codex", "gpt-5.6-terra");
  deq(b.switched, ["A", "codex"], "it did not go through switchChatProvider —");
  eq(b.S.model.A, "gpt-5.6-terra");
});

test("3e. a refused switch leaves the model alone", () => {
  const b = box({});
  b.switchChatProvider = () => "unready";
  b.S.model.A = "opus";
  b.pickComposerModel("A", "codex", "gpt-5.6-terra");
  eq(b.S.model.A, "opus",
     "the chat stayed on Claude holding a Codex model id —");
  eq(b.posted.length, 0, "a refused switch still wrote a setting");
});

test("3f. the thinking level is the turn option, not a second store", () => {
  const b = box();
  b.setComposerEffort("A", "max");
  deq(b.S.turnOpts.A, { effort: "max" },
      "Claude's level must land on `effort`, which is what the server reads —");
  b.setComposerEffort("C", "ultra");
  deq(b.S.turnOpts.C, { reasoning_effort: "ultra" },
      "Codex's level must land on `reasoning_effort` —");
  b.setComposerEffort("A", "");
  deq(b.S.turnOpts.A, {}, "choosing Default must remove the override, not store ''");
});

/* ══════════════════ 4. access, a row in the ⋯ menu ═════════════════════════
   Under the message box as a chip until 2026-09-21 (founder: "remove the full
   access thing ... put that into the three dots"). */

function accMenu(b, sid) { b.S.accMenu = sid; return b.composerAccessMenuHtml(sess(b, sid)); }

test("4a. the Access row says the access in plain words, and opens the same list", () => {
  const b = box();
  const h = b.paneAccessRowHtml(sess(b, "A"));
  assert(/class="mrow accrowm/.test(h), h);
  assert(/data-accmenu="A"/.test(h), "the row does not open the access list: " + h);
  assert(h.includes("Read only"), "it printed a native mode id at the operator: " + textOf(h));
  assert(!/accchip/.test(h), "the chip is back");
});

test("4b. all four options on Claude, in the shared order", () => {
  const b = box();
  deq(attrs(accMenu(b, "A"), "accpick"),
      ["A:plan", "A:acceptEdits", "A:auto", "A:bypassPermissions"]);
  const h = accMenu(b, "A");
  ["Read only", "Accept edits", "Approve for me", "Full access"]
    .forEach(w => assert(h.includes(w), "missing option: " + w));
});

test("4c. what the provider cannot do is not offered", () => {
  const b = box();
  const h = accMenu(b, "C");
  deq(attrs(h, "accpick"), ["C:plan", "C:acceptEdits", "C:bypassPermissions"],
      "Codex has no 'Approve for me' and must not be shown one —");
  assert(!h.includes("Approve for me"), h);
});

test("4d. the values that travel are still the native mode ids", () => {
  /* The plain names live only in the UI. Nothing stored or sent changes, which
     is the whole reason existing installs keep working. */
  const b = box();
  attrs(accMenu(b, "A"), "accpick").forEach(v => {
    const mode = v.split(":")[1];
    assert(PMODES.claude.includes(mode), "a UI-only id reached the wire: " + mode);
  });
});

test("4e. Full access is marked as the one that warns", () => {
  const b = box();
  const h = accMenu(b, "A");
  assert(/class="accopt warn"[^>]*data-accpick="A:bypassPermissions"/.test(h),
         "the one dangerous option looks like the other three: " + h);
});

test("4f. a legacy stored mode survives, under Advanced", () => {
  const b = box();
  const h = accMenu(b, "A");
  assert(/data-accadv="A"/.test(h), "no Advanced disclosure: " + h);
  assert(h.includes("2 older modes"), textOf(h));
  b.S.accAdv.A = true;
  const open = accMenu(b, "A");
  const ids = attrs(open, "accpick");
  assert(ids.includes("A:manual") && ids.includes("A:dontAsk"),
         "a mode someone already chose disappeared: " + ids.join(","));
});

test("4g. a chat already ON a legacy mode shows it, and opens Advanced for it", () => {
  const b = box();
  b.SETTINGS.permission_mode = b.SETTINGS.permission_mode_effective = "dontAsk";
  const chip = b.paneAccessRowHtml(sess(b, "A"));
  assert(chip.includes("dontAsk"),
         "the stored mode was silently relabelled as one of the four: " + textOf(chip));
  const h = accMenu(b, "A");
  assert(/<button class="accopt on"[^>]*data-accpick="A:dontAsk"/.test(h),
         "the mode in force is not the one marked current: " + h);
});

test("4h. choosing a safe access is remembered for THIS chat only", () => {
  const b = box();
  b.setSessAccess("A", "plan");
  eq(b.S.perm.A, "plan");
  eq(b.S.perm.C, undefined, "one chat's choice leaked onto another");
  eq(b.posted.length, 0, "a per-chat access rewrote the global setting");
});

test("4i. an unsafe access still goes through the existing consent flow", () => {
  const b = box();
  b.setSessAccess("A", "bypassPermissions");
  deq(b.S.permConfirm, { mode: "bypassPermissions" },
      "a write-capable mode was applied without the confirmation —");
  eq(b.S.perm.A, undefined,
     "it was armed for the socket before consent was given —");
});

test("4j. consent already granted is not re-asked", () => {
  const b = box();
  b.SETTINGS.unsafe_modes_allowed = true;
  b.setSessAccess("A", "acceptEdits");
  eq(b.S.permConfirm, null, "already-granted consent was re-prompted");
  eq(b.S.perm.A, "acceptEdits");
});

test("4k. the chosen access rides the socket as ?perm=, and only when chosen", () => {
  const b = box();
  eq(b.claudeWsUrl("A"), "ws://127.0.0.1:7000/ws/chat",
     "a chat that chose nothing must send nothing —");
  b.S.perm.A = "acceptEdits";
  const u = b.claudeWsUrl("A");
  assert(u.includes("perm=acceptEdits"), "the choice never reached the url: " + u);
  assert(!b.claudeWsUrl("C").includes("perm="),
         "one chat's access leaked onto another chat's socket");
});

/* SECTION 5 LIVED HERE and is gone (2026-09-14). It covered permSelect(), the
   pane menu's permission <select>, which has been deleted: the access control is
   the composer chip above (section 4), and the model picker took its place in the
   menu. Nothing it proved is lost -- the plain names over native ids, and the
   legacy modes under Advanced, are 4d, 4f and 4g. */

/* ══════════════════ 6. tool cards, one per kind ════════════════════════════ */

/* One live run, as 01-state stores it off a `tool` frame. */
const run = (o) => Object.assign({ id: "t1", name: "tool", running: false, ok: true,
                                   startedAt: 1000, endedAt: 2000 }, o);
const card = (b, o) => b.toolCallsHtml([run(o)], { live: true });

test("6a. subagent -- its own steps and its result", () => {
  const b = box();
  const h = card(b, { name: "Task", kind: "subagent", title: "Find the dead routes",
                      meta: { agent: "explore", steps: 3,
                              steps_list: [{ name: "Grep", summary: "12 hits" }, { name: "Read" }] },
                      output: "three routes are unreferenced" });
  assert(/data-toolkind="subagent"/.test(h), h);
  assert(h.includes("Subagent · explore"), textOf(h));
  assert(h.includes("Find the dead routes"), textOf(h));
  assert(h.includes("3 steps"), textOf(h));
  assert(/<ol class="tcsteps">/.test(h) && h.includes("12 hits"),
         "the nested steps are not drawn: " + h);
  b.S.toolOpen.t1 = true;
  assert(b.toolCallsHtml([run({ name: "Task", kind: "subagent",
    output: "three routes are unreferenced" })], { live: true })
    .includes("three routes are unreferenced"), "the result is unreachable");
});

test("6b. command -- the command and its exit code, plus the terminal control", () => {
  const b = box();
  const h = card(b, { name: "Bash", command: "npm test", meta: { exit_code: 0 },
                      output: "ok" });
  assert(/data-toolkind="command"/.test(h), h);
  assert(h.includes("npm test"), textOf(h));
  assert(h.includes("exit 0"), textOf(h));
  assert(/data-toolterm="t1"/.test(h), "the terminal re-open control was lost: " + h);
});

test("6c. file edit -- the file and a +/- summary", () => {
  const b = box();
  const h = card(b, { name: "Edit", meta: { path: "/w/src/app.py",
                                            lines_added: 3, lines_removed: 1 } });
  assert(/data-toolkind="file_edit"/.test(h), h);
  assert(h.includes("app.py"), textOf(h));
  assert(h.includes("+3 −1"), "no diff summary: " + textOf(h));
});

test("6d. file edit with nothing counted says the path, never +0 -0", () => {
  const b = box();
  const h = card(b, { name: "Write", meta: { path: "/w/notes.md" } });
  assert(!/\+0/.test(h), "a count nobody measured was printed: " + textOf(h));
  assert(h.includes("notes.md"), textOf(h));
});

test("6e. file read", () => {
  const b = box();
  const h = card(b, { name: "Read", meta: { path: "/w/README.md", lines: 240 } });
  assert(/data-toolkind="file_read"/.test(h), h);
  assert(h.includes("README.md") && h.includes("240 lines"), textOf(h));
});

test("6f. search -- the pattern and the match count", () => {
  const b = box();
  const h = card(b, { name: "Grep", meta: { pattern: "TODO", matches: 12 } });
  assert(/data-toolkind="search"/.test(h), h);
  assert(h.includes("TODO") && h.includes("12 matches"), textOf(h));
  assert(/data-toolkind="search"/.test(card(b, { name: "Glob", input: "**/*.py" })),
         "Glob is a search too");
});

test("6g. web search and web fetch are different cards", () => {
  const b = box();
  const s = card(b, { name: "WebSearch", meta: { query: "acp spec", results: 8 } });
  assert(/data-toolkind="web_search"/.test(s), s);
  assert(s.includes("acp spec") && s.includes("8 results"), textOf(s));
  const f = card(b, { name: "WebFetch", meta: { url: "https://example.com/x", status: 200 } });
  assert(/data-toolkind="web_fetch"/.test(f), f);
  assert(f.includes("example.com"), textOf(f));
});

test("6h. plan", () => {
  const b = box();
  const h = card(b, { name: "ExitPlanMode", detail: "4 steps" });
  assert(/data-toolkind="plan"/.test(h), h);
  assert(h.includes("Plan put up for approval") && h.includes("4 steps"), textOf(h));
});

test("6i. todo -- the list, with its states", () => {
  const b = box();
  const h = card(b, { name: "TodoWrite", meta: { done: 1, total: 3, todos: [
    { content: "read the adapter", status: "completed" },
    { content: "write the card", status: "in_progress" },
    { content: "test it", status: "pending" }] } });
  assert(/data-toolkind="todo"/.test(h), h);
  assert(h.includes("1 of 3 done"), textOf(h));
  assert(/<li class="completed">read the adapter/.test(h), h);
  assert(/<li class="in_progress">write the card/.test(h), h);
});

test("6j. notebook", () => {
  const b = box();
  const h = card(b, { name: "NotebookEdit", meta: { path: "/w/explore.ipynb" } });
  assert(/data-toolkind="notebook"/.test(h), h);
  assert(h.includes("explore.ipynb"), textOf(h));
});

test("6k. an MCP tool names the SERVER being trusted", () => {
  const b = box();
  const h = card(b, { name: "mcp__linear__create_issue", input: "title=Fix the router" });
  assert(/data-toolkind="mcp"/.test(h), h);
  assert(h.includes("MCP · linear"), textOf(h));
  assert(h.includes("create_issue"), textOf(h));
});

test("6l. compaction", () => {
  const b = box();
  const h = card(b, { name: "compaction", meta: { tokens_saved: 48000 } });
  assert(/data-toolkind="compaction"/.test(h), h);
  assert(h.includes("Earlier conversation compacted"), textOf(h));
  assert(h.includes("48000 tokens dropped"), textOf(h));
});

test("6m. FALLBACK: an unknown tool renders at least as well as it did before", () => {
  const b = box();
  const h = card(b, { name: "SomeNewTool", input: "--flag value", output: "done" });
  assert(/data-toolkind="other"/.test(h), h);
  /* The two things a flat row always carried: the name pill and the input. */
  assert(/<span class="tc-name pill p-acc">SomeNewTool<\/span>/.test(h),
         "the tool's own name was lost: " + h);
  assert(/<code class="tc-in">--flag value<\/code>/.test(h),
         "the input line was lost: " + h);
  assert(/data-toolout/.test(h), "the output expander was lost: " + h);
});

test("6n. a kind the SERVER invents is not trusted into a card that drops fields", () => {
  const b = box();
  const h = card(b, { name: "Bash", kind: "quantum_tunnel", command: "ls" });
  /* It falls back to the name-based classifier rather than rendering nothing. */
  assert(/data-toolkind="command"/.test(h), "an unrecognised kind broke the card: " + h);
});

test("6o. a call with NO name and NO kind still renders", () => {
  const b = box();
  const h = b.toolCallsHtml([{}], { live: true });
  assert(/class="toolcall tcard/.test(h), "a tool call disappeared from the screen: " + h);
});

/* ══════════════════ 7. the timeline's existing behaviour ═══════════════════ */

test("7a. the running dot, the verdict and the elapsed time survive", () => {
  const b = box();
  const h = b.toolCallsHtml([run({ running: true, ok: null, endedAt: null,
                                   name: "Bash", command: "sleep 5" })], { live: true });
  assert(/class="toolcall tcard k-command run"/.test(h), "no running state: " + h);
  assert(/<span class="tcdot"/.test(h), "no dot: " + h);
  assert(h.includes("running"), textOf(h));
});

test("7b. the output expander keeps its key, so an open output stays open", () => {
  const b = box();
  const shut = b.toolCallsHtml([run({ output: "hello" })], { live: true });
  assert(/aria-expanded="false"/.test(shut) && !shut.includes("<pre"), shut);
  b.S.toolOpen.t1 = true;
  const open = b.toolCallsHtml([run({ output: "hello" })], { live: true });
  assert(/<pre class="tc-outbody">hello<\/pre>/.test(open), open);
});

test("7c. a failed tool is red and says error", () => {
  const b = box();
  const h = b.toolCallsHtml([run({ ok: false, output: "boom" })], { live: true });
  assert(/tcard k-other bad/.test(h), h);
  assert(/p-block/.test(h), "the name pill did not go red: " + h);
  b.S.toolOpen.t1 = true;
  assert(/tc-outbody err/.test(b.toolCallsHtml([run({ ok: false, output: "boom" })],
    { live: true })), "the failure text is not styled as one");
});

test("7d. a long fan-out is capped and says how many are not drawn", () => {
  const b = box();
  const many = [];
  for (let i = 0; i < 20; i++) many.push(run({ id: "t" + i, name: "Read" }));
  const h = b.toolCallsHtml(many, { live: true });
  eq((h.match(/class="toolcall tcard/g) || []).length, 13, "cap + the summary line");
  assert(h.includes("8 earlier tool calls"), textOf(h));
});

test("7e. toolTimelineHtml is the one call the timeline needs", () => {
  const b = box();
  const h = b.toolTimelineHtml({ toolRuns: [run({ name: "Bash", command: "ls" })] });
  assert(/data-toolkind="command"/.test(h), h);
  eq(b.toolTimelineHtml({ toolRuns: [] }), "", "an empty turn must render nothing");
  eq(b.toolTimelineHtml({}), "");
});

/* ══════════════════ 8. STORED history gets the same cards ══════════════════ */

/* What transcriptTurns() folds out of a three-month-old chat: a name, its
   input, its output. No kind, no meta -- the classifier has only the name. */
const stored = (name, input, output) => ({ name, input, output });

test("8a. an old chat's tool_use blocks classify by name, with no migration", () => {
  const b = box();
  const h = b.toolCallsHtml([
    stored("Bash", "npm test", "ok"),
    stored("Read", "/w/app.py", "...."),
    stored("Task", "explore the router", "found it"),
    stored("mcp__github__list_prs", "", "[]"),
    stored("WhatIsThis", "x", ""),
  ]);
  deq(attrs(h, "toolkind"), ["command", "file_read", "subagent", "mcp", "other"],
      "stored history did not get the new cards —");
});

test("8b. the stored expander key is unchanged, so old toggles keep working", () => {
  const b = box();
  const h = b.toolCallsHtml([stored("Bash", "ls", "a\nb")]);
  assert(/data-toolout="c:Bash:0"/.test(h),
         "the replayed transcript's toolOpen key moved: " + h);
});

test("8c. a stored turn has no lifecycle, and none is invented", () => {
  const b = box();
  const h = b.toolCallsHtml([stored("Bash", "ls", "out")]);
  assert(!/class="tcv"/.test(h), "a replayed call claimed a duration it never had: " + h);
  assert(!/data-toolterm/.test(h),
         "a terminal control was offered for a command the server never sent: " + h);
  assert(/tcard k-command ok/.test(h), h);
});

test("8d. a stored error is still an error", () => {
  const b = box();
  const h = b.toolCallsHtml([{ name: "Bash", input: "false", output: "exit 1", is_error: true }]);
  assert(/tcard k-command bad/.test(h), h);
});

/* ══════════════════ 9. none of the new keys has landed yet ═════════════════ */

test("9a. no catalogue, no access list -> the controls still render", () => {
  const b = box({ MODEL_CATALOG_BY_PROVIDER: {}, ACCESS_OPTIONS: [], ACCESS_BY_PROVIDER: {} });
  const label = b.composerModelLabel(sess(b, "A"), "claude");
  assert(label, "the Model row lost its label on an older backend");
  /* It falls back to the FLAT models_by_provider the panel has always had. */
  assert(label.includes("Claude · Opus"), label);
  const h = menu(b, "A");
  deq(attrs(h, "mdlpick"), ["A:claude:", "A:claude:opus"],
      "the flat list was not used as the fallback —");
  assert(!/data-mdlmore/.test(h) && !/data-mdlfast/.test(h) && !/data-mdleff/.test(h),
         "a control was drawn for data that does not exist: " + h);
});

test("9b. no access list -> the four fall back to the provider's native modes", () => {
  const b = box({ ACCESS_OPTIONS: [], ACCESS_BY_PROVIDER: {} });
  deq(attrs(accMenu(b, "A"), "accpick"),
      ["A:plan", "A:acceptEdits", "A:auto", "A:bypassPermissions"]);
  deq(attrs(accMenu(b, "C"), "accpick"),
      ["C:plan", "C:acceptEdits", "C:bypassPermissions"],
      "the fallback ignored what Codex declares it can enforce —");
});

test("9c. nothing fetched at all -> access is permissive, never empty", () => {
  /* An empty PERM_MODES_BY_PROVIDER means NOT FETCHED, and a pane with no way
     to say "read only" is the wrong direction to be wrong in. */
  const b = box({ ACCESS_OPTIONS: [], ACCESS_BY_PROVIDER: {}, PERM_MODES_BY_PROVIDER: {} });
  const ids = attrs(accMenu(b, "D"), "accpick");
  assert(ids.length === 4, "the access picker went blank on a slow fetch: " + ids.join(","));
});

test("9d. the access list can also arrive as a plain array of ids", () => {
  /* Both shapes are read, because the key is new and guessing one would make
     the control go blank on the other. */
  const b = box({ ACCESS_BY_PROVIDER: { claude: ["read", "full"] } });
  deq(attrs(accMenu(b, "A"), "accpick"), ["A:plan", "A:bypassPermissions"]);
});

test("9e. the keys can arrive nested on SETTINGS instead of as globals", () => {
  const b = box({ MODEL_CATALOG_BY_PROVIDER: {}, ACCESS_BY_PROVIDER: {} });
  b.SETTINGS.model_catalog_by_provider = CATALOG;
  b.SETTINGS.access_by_provider = ACCESS_MAP;
  assert(b.composerModelLabel(sess(b, "A"), "claude").includes("Opus 5"),
         "the catalogue was ignored where the server actually put it");
  deq(attrs(accMenu(b, "C"), "accpick"), ["C:plan", "C:acceptEdits", "C:bypassPermissions"]);
});

/* ══════════════════ 10. the delegated handlers ═════════════════════════════
   Both chips are wired from ONE document listener installed on the first
   render, not re-bound per node: #panes is rebuilt wholesale on every paint,
   and a handler attached to a node that no longer exists is the classic way a
   control silently stops working mid-stream. So the handler is what is tested,
   fired against a node that answers closest() the way the DOM would. */
function ev(sel, data, extra) {
  const node = Object.assign({ dataset: data || {} }, extra || {});
  node.closest = (q) => (q === sel ? node : null);
  return { target: node };
}

test("10a. the model chip toggles its own menu and shuts the other one", () => {
  const b = box();
  b.S.accMenu = "A";
  b.composerControlClick(ev("[data-mdlmenu]", { mdlmenu: "A" }));
  eq(b.S.mdlMenu, "A"); eq(b.S.accMenu, null, "two popovers were open at once");
  b.composerControlClick(ev("[data-mdlmenu]", { mdlmenu: "A" }));
  eq(b.S.mdlMenu, null, "a second click did not close it");
});

test("10b. opening the menu starts on the chat's own provider tab", () => {
  const b = box();
  b.composerControlClick(ev("[data-mdlmenu]", { mdlmenu: "C" }));
  eq(b.S.mdlTab.C, "codex");
});

test("10c. a provider tab only BROWSES -- nothing switches until a model is picked", () => {
  const b = box();
  b.composerControlClick(ev("[data-mdltab]", { mdltab: "A:codex" }));
  eq(b.S.mdlTab.A, "codex");
  eq(b.switched, undefined, "looking at a provider moved the chat to it");
});

test("10d. an empty model id survives the round trip through the data attribute", () => {
  /* "A:claude:" is the account default, and a naive split would read it as no
     model at all and leave the previous one in place. */
  const b = box();
  b.S.model.A = "sonnet";
  b.composerControlClick(ev("[data-mdlpick]", { mdlpick: "A:claude:" }));
  eq(b.S.model.A, "", "the account default could not be chosen");
});

test("10e. a model id containing a colon still parses", () => {
  const b = box();
  b.composerControlClick(ev("[data-mdlpick]", { mdlpick: "A:claude:us.anthropic:v1" }));
  eq(b.S.model.A, "us.anthropic:v1");
});

test("10f. the Fast switch writes service_tier, and removes it when off", () => {
  const b = box();
  b.composerControlChange(ev("[data-mdlfast]", { mdlfast: "C" }, { checked: true }));
  deq(b.S.turnOpts.C, { service_tier: "fast" });
  b.composerControlChange(ev("[data-mdlfast]", { mdlfast: "C" }, { checked: false }));
  deq(b.S.turnOpts.C, {}, "an off switch must leave nothing behind, not `false`");
});

test("10g. More opens the turn-options box and closes the menu", () => {
  const b = box();
  b.S.mdlMenu = "A";
  b.composerControlClick(ev("[data-mdlopts]", { mdlopts: "A" }));
  eq(b.S.optsOpen.A, true); eq(b.S.mdlMenu, null);
});

test("10h. a click outside an open popover shuts it", () => {
  const b = box();
  b.S.mdlMenu = "A";
  b.composerControlClick(ev("[data-nothing]", {}));
  eq(b.S.mdlMenu, null, "the popover stayed open over the transcript");
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); console.log("ok   - " + n); pass++; }
    catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; }
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
