#!/usr/bin/env node
/*
 * test_chat_ai_provider.js -- the ⋮ menu's "Chat AI Provider" row.
 *
 * WHAT IS BEING PINNED
 * The row is a CONTROL over one chat and a MIRROR of that chat's own provider,
 * and both halves have to hold at once:
 *
 *   mirror   it has no state of its own. Its selection is paneProvider(), the
 *            same expression the Model, Permissions, Turn options and Usage
 *            rows read, so "using Codex, ..." typed in the composer changes
 *            what this row says without anything telling this row about it.
 *   control  selecting a provider calls switchChatProvider -- the SAME
 *            function the composer's detector calls. There is no second
 *            switching mechanism, so there is nothing that can answer
 *            differently from the natural-language path.
 *
 * And two things it must never do: offer a provider that cannot run, or touch
 * the global Primary Provider in Settings.
 *
 * The row is built inside a template literal, so it cannot be extracted on its
 * own -- these tests run the real paneMenuHtml over real state. The click
 * handler is extracted from wire() by source and executed, because a handler
 * that never fires is invisible to a logic test.
 *
 * Run: node test_chat_ai_provider.js
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
const loaders = J("07-loaders.js");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
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
/* One statement, from a needle to the `;` that ends it at depth zero. Used for
   the wire() handler, which is a statement inside a 900-line function and
   therefore not reachable by grab(). */
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

/* ── the box: real render + real switch, one shared state ─────────────────── */

/* THE TABLE THE SERVER PUBLISHES. `runnable` is its verdict -- installed AND
   configured AND this build has an adapter -- and DeepSeek is catalogued here
   but not ready, which is the whole point of it being in the fixture. */
const TABLE = [
  { id: "claude", name: "Claude Code", runnable: true },
  { id: "codex", name: "OpenAI Codex", runnable: true },
  { id: "deepseek", name: "DeepSeek", runnable: false, reason: "nobody is signed in" },
];

function makeBox(opts) {
  const o = opts || {};
  const box = {
    /* Chat A on Codex (the server said so), Chat B on the global default. */
    S: { paneMenu: "A", chatProvider: {}, chatProviderNote: {}, repo: {}, prs: {},
         optsOpen: {}, sessTab: {}, model: {}, ui: { paneCollapsed: {} },
         sessions: o.sessions || [
           { id: "A", title: "Chat A", channel: { id: "codex", source: "chat-history" } },
           { id: "B", title: "Chat B", channel: { id: "claude", source: "settings" } },
         ] },
    /* THE GLOBAL PRIMARY PROVIDER. Every test below re-reads this at the end:
       a chat-level switch that moves it is the one failure that cannot be
       undone from inside a chat. */
    SETTINGS: { provider: "claude", model_by_provider: {} },
    SEED: { provider: "claude",
            provider_aliases: { "codex": "codex", "claude": "claude",
                                "deepseek": "deepseek" } },
    PROVIDERS: o.providers || TABLE,
    MODELS_BY_PROVIDER: {},
    closed: [],
    esc: (x) => String(x == null ? "" : x).replace(/[&<>"]/g, c =>
           ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
    /* stubs for the menu rows that are not under test */
    cwdLabel: () => "work", sessCwd: () => "",
    permSelect: () => '<select data-perm="x"></select>',
    providerUsage: () => null, usageKindOf: () => "none",
    turnOptsFor: () => new Set(),
    streamingFor: () => !!o.streaming, sideStreamingFor: () => false,
    render: () => { box.renders = (box.renders || 0) + 1; },
    /* A switch MUST NOT reach the network from here. Any fetch is a failure. */
    fetch: () => { throw new Error("the chat-level switch called fetch()"); },
    console,
  };
  box.closeClaudeChannel = (sid, opt) => { box.closed.push([sid, !!(opt && opt.force)]); };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessProviderRequest"),
    grab(chat, "providerLabel"),
    grab(render, "paneProvider"),
    grab(render, "paneDeclProvider"),
    grab(render, "paneMenuHtml"),
    grab(helpers, "switchChatProvider"),
    /* the natural-language path, whole, so convergence is tested and not assumed */
    "var PROVIDER_INTENT_PREFIX = " + /PROVIDER_INTENT_PREFIX = ([^\n]+)/.exec(helpers)[1],
    "var PROVIDER_INTENT_QUESTION = " + /PROVIDER_INTENT_QUESTION =\s*([^\n]+)/.exec(helpers)[1],
    "var PROVIDER_INTENT_NEGATION = " + /PROVIDER_INTENT_NEGATION =\s*([^\n]+)/.exec(helpers)[1],
    grab(helpers, "stripProviderNoise"),
    grab(helpers, "providerIntentFrames"),
    grab(helpers, "providerIntentOpensWithDirective"),
    grab(helpers, "detectProviderIntent"),
    grab(helpers, "applyProviderRequest"),
    /* the real wire() handler, executed against a fake select */
    /* wire() runs on every render; at load there is no select mounted yet,
       which is exactly what the live panel does before a menu is opened. */
    "var panes = { querySelectorAll: () => globalThis.__sel ? [globalThis.__sel] : [] };",
    grabStatement(loaders, 'panes.querySelectorAll("[data-chatprov]")'),
  ].join("\n"), { filename: "chatprov#extract" }).runInContext(box);
  return box;
}

/* Pick the chat's provider through the ROW, the way an operator does: mount the
   real select, fire the handler wire() attached to it. */
function selectProvider(box, sid, value) {
  box.__sel = { dataset: { chatprov: sid }, value: value, onchange: null };
  /* re-running the statement is what wire() does on every render */
  vm.runInContext("(" + "function(){ " +
    grabStatement(loaders, 'panes.querySelectorAll("[data-chatprov]")') + " })()", box);
  assert(typeof box.__sel.onchange === "function",
         "wire() attached no handler to the Chat AI Provider select");
  box.__sel.onchange();
}

/* The row's <option> list and which one is selected, from the real markup. */
function row(box, sid) {
  const s = box.S.sessions.find(x => x.id === sid);
  const prev = box.S.paneMenu;
  box.S.paneMenu = sid;
  const html = box.paneMenuHtml(s);
  box.S.paneMenu = prev;
  const m = /<span class="mk">Chat AI Provider<\/span>[\s\S]*?<\/select>/.exec(html);
  if (!m) return { present: false, html: html, options: [], selected: null };
  const block = m[0];
  const options = [...block.matchAll(/<option value="([^"]*)"([^>]*)>([^<]*)</g)]
    .map(o => ({ id: o[1], disabled: /\bdisabled\b/.test(o[2]),
                 selected: /\bselected\b/.test(o[2]), label: o[3] }));
  return { present: true, html: html, block: block, options: options,
           selected: (options.find(o => o.selected) || {}).id || null };
}

/* ── 1. the row mirrors the chat's active provider ────────────────────────── */

test("the row is labelled exactly \"Chat AI Provider\"", () => {
  const box = makeBox();
  const html = box.paneMenuHtml(box.S.sessions[0]);
  assert(/<span class="mk">Chat AI Provider<\/span>/.test(html),
         "the label is not the agreed one -- it is what the operator looks for");
  /* NOT the global control's name. "Primary Provider" is Settings' label for a
     different thing, and reusing it here is how a chat-level switch gets read
     as a global one. */
  assert(!/Primary Provider/.test(html), "the row borrows Settings' label");
});

test("it shows the provider THIS CHAT is on, not the global default", () => {
  const box = makeBox();
  eq(row(box, "A").selected, "codex", "Chat A is on codex; Settings says claude —");
  eq(row(box, "B").selected, "claude", "Chat B");
});

test("it reads the same expression every other provider-dependent row reads", () => {
  /* paneProvider IS the chat-local provider state (server frame, rail hint, or
     an armed switch). No second store: a row with its own copy is a row that
     can disagree with the chat it describes. */
  const box = makeBox();
  const s = box.S.sessions[0];
  eq(row(box, "A").selected, box.paneProvider(s),
     "the row's selection diverged from paneProvider —");
});

/* ── 2. natural language and the row are the same fact ───────────────────── */

test("\"Using Codex, what is 17 × 6?\" moves the row to Codex", () => {
  /* Chat B starts on Claude. The composer's detector runs; nothing tells the
     row anything, and the row has changed. */
  const box = makeBox();
  eq(row(box, "B").selected, "claude", "precondition");
  const held = box.applyProviderRequest(box.S.sessions[1], "Using Codex, what is 17 × 6?");
  eq(held, false, "a valid switch must not hold the message");
  eq(box.S.chatProvider.B, "codex", "the switch was not armed");
  eq(row(box, "B").selected, "codex",
     "the row still shows the provider the chat is LEAVING —");
});

test("\"Use Claude for this. What is 20 + 22?\" moves it back", () => {
  const box = makeBox();
  box.applyProviderRequest(box.S.sessions[1], "Using Codex, what is 17 × 6?");
  eq(row(box, "B").selected, "codex", "precondition");
  box.applyProviderRequest(box.S.sessions[1], "Use Claude for this. What is 20 + 22?");
  eq(box.S.chatProvider.B, "claude", "the second switch was not armed");
  eq(row(box, "B").selected, "claude", "the row did not follow the chat back");
});

/* ── 3. only ready-to-use providers are offered ──────────────────────────── */

test("a provider that cannot run is not in the list", () => {
  const box = makeBox();
  const r = row(box, "A");
  const ids = r.options.map(o => o.id);
  assert(ids.indexOf("claude") !== -1 && ids.indexOf("codex") !== -1,
         "the two ready providers are not both offered: " + ids.join(","));
  assert(ids.indexOf("deepseek") === -1,
         "DeepSeek is not ready to use and must not be offered: " + ids.join(","));
});

test("readiness is the server's `runnable`, not a list kept here", () => {
  /* Same table, one sign-in changed. Nothing else moves, and the option
     appears -- which is only true if the row reads the table. */
  const box = makeBox({ providers: TABLE.map(p =>
    p.id === "deepseek" ? { id: "deepseek", name: "DeepSeek", runnable: true } : p) });
  assert(row(box, "A").options.map(o => o.id).indexOf("deepseek") !== -1,
         "a newly ready provider did not appear, so the list is not the table's");
});

test("an unready provider cannot be switched to even if asked for directly", () => {
  const box = makeBox();
  selectProvider(box, "A", "deepseek");
  eq(box.S.chatProvider.A, undefined, "an unrunnable provider was armed");
  eq(box.closed.length, 0, "the socket was dropped for a provider that cannot start");
  assert(/not ready to use/.test(box.S.chatProviderNote.A || ""),
         "the refusal said nothing: " + box.S.chatProviderNote.A);
});

test("the row never renders from an UNFETCHED table", () => {
  /* GET /api/providers returns every catalogued provider whatever its
     readiness, so empty means NOT FETCHED -- and a row built from it would
     offer nothing at all while implying the chat has no provider. */
  const box = makeBox({ providers: [] });
  eq(row(box, "A").present, false, "a row was drawn during the boot window");
});

test("the provider a chat is RUNNING is never dropped from its own row", () => {
  /* Signed out after the socket resolved it. A select whose value is absent
     from its options displays the FIRST one, i.e. names a provider this chat
     is not on -- so it is listed, disabled. */
  const box = makeBox({ providers: [
    { id: "claude", name: "Claude Code", runnable: true },
    { id: "codex", name: "OpenAI Codex", runnable: false, reason: "signed out" }] });
  const r = row(box, "A");
  eq(r.selected, "codex", "the row stopped naming the provider actually running");
  const cur = r.options.find(o => o.id === "codex");
  assert(cur && cur.disabled, "the running-but-unready provider is selectable");
});

/* ── 4. selecting one switches THIS chat, through the existing path ──────── */

test("selecting another ready provider switches the chat", () => {
  const box = makeBox();
  selectProvider(box, "A", "claude");
  eq(box.S.chatProvider.A, "claude", "the switch was not armed for the url builder");
  eq(box.closed.length, 1, "the socket bound to the old provider was not dropped");
  eq(box.closed[0][0], "A", "the wrong chat's socket was dropped");
  eq(box.closed[0][1], true, "the drop was not forced, so an idle socket survives");
  eq(row(box, "A").selected, "claude", "the row did not follow the switch");
});

test("it is the SAME machinery the composer's request uses", () => {
  /* Byte-level, because this is the constraint: the handler calls
     switchChatProvider, and so does applyProviderRequest. One function. */
  const handler = grabStatement(loaders, 'panes.querySelectorAll("[data-chatprov]")');
  assert(/switchChatProvider\(/.test(handler),
         "the menu built its own switch instead of calling the shared one");
  assert(!/S\.chatProvider\[/.test(handler),
         "the handler arms the request itself -- that is a second switch path");
  assert(!/closeClaudeChannel\(/.test(handler),
         "the handler drops the socket itself -- that is a second switch path");
  const apply = grab(helpers, "applyProviderRequest");
  assert(/switchChatProvider\(/.test(apply),
         "the natural-language path no longer shares the switch");
});

test("both ways of asking land on the same state", () => {
  const a = makeBox(), b = makeBox();
  a.applyProviderRequest(a.S.sessions[1], "Using Codex, implement this");
  selectProvider(b, "B", "codex");
  eq(a.S.chatProvider.B, b.S.chatProvider.B, "the two paths armed different state");
  eq(row(a, "B").selected, row(b, "B").selected, "the two paths report differently");
  eq(a.closed.length, b.closed.length, "one path dropped the socket and the other did not");
});

/* ── 5. selecting the provider already running is a no-op ────────────────── */

test("choosing the current provider does nothing at all", () => {
  const box = makeBox();
  const before = JSON.stringify(box.S.sessions[0]);
  selectProvider(box, "A", "codex");
  eq(box.closed.length, 0, "the socket was dropped to arrive where the chat already is");
  eq(box.S.chatProvider.A, undefined, "a pointless switch was armed");
  eq(box.S.chatProviderNote.A, undefined, "a no-op produced a note");
  eq(JSON.stringify(box.S.sessions[0]), before, "the chat was mutated");
});

test("the no-op is decided in one place, not per caller", () => {
  const fn = grab(helpers, "switchChatProvider");
  assert(/target === paneProvider\(s\)/.test(fn),
         "the already-there short-circuit is not in the shared switch");
});

/* ── 6. the global Primary Provider is untouched ─────────────────────────── */

test("switching a chat does not change the global Primary Provider", () => {
  const box = makeBox();
  selectProvider(box, "A", "claude");
  eq(box.SETTINGS.provider, "claude", "Settings moved");
  const box2 = makeBox();
  selectProvider(box2, "B", "codex");
  eq(box2.SETTINGS.provider, "claude",
     "Settings followed a chat-level switch -- every other chat moved with it");
  eq(box2.SEED.provider, "claude", "the page's default provider was rewritten");
});

test("nothing on the chat-level path can reach the global endpoint", () => {
  const src = grab(helpers, "switchChatProvider")
            + grabStatement(loaders, 'panes.querySelectorAll("[data-chatprov]")');
  assert(!/providers\/active/.test(src), "it posts to the global provider endpoint");
  assert(!/api\/settings/.test(src), "it writes settings");
  assert(!/SETTINGS\s*=/.test(src), "it reassigns SETTINGS");
  /* fetch() throws in the box, so this is also proved behaviourally above. */
});

/* ── 7. other chats are unaffected ──────────────────────────────────────── */

test("switching one chat leaves the others where they were", () => {
  const box = makeBox();
  selectProvider(box, "A", "claude");
  eq(row(box, "B").selected, "claude", "Chat B moved");
  eq(box.S.chatProvider.B, undefined, "Chat B was armed for a switch it never asked for");
  eq(box.closed.filter(c => c[0] !== "A").length, 0, "another chat's socket was dropped");
});

test("a new chat still starts on the global default", () => {
  const box = makeBox();
  selectProvider(box, "A", "claude");
  box.S.sessions.push({ id: "N", title: "New session" });   /* no channel, no source */
  eq(box.paneProvider(box.S.sessions.find(s => s.id === "N")), "claude",
     "a brand-new chat inherited another chat's provider");
});

/* ── 8. refresh / reconnect ──────────────────────────────────────────────── */

test("after a refresh the row still shows the chat's provider, not Settings'", () => {
  /* A reload empties S.chatProvider -- it is memory-only and one-shot. The
     chat's durable answer is server-side (provider_history), and it reaches the
     browser two ways: the rail's row (`source`) before the socket exists, and
     the ws provider frame (`source: "chat-history"`) after. Both must beat the
     global default, or a chat moved to Codex comes back on Claude. */
  const reopened = makeBox({ sessions: [
    { id: "A", title: "Chat A", source: "codex" },                 /* rail only */
    { id: "B", title: "Chat B", source: "claude" },
  ] });
  eq(reopened.S.chatProvider.A, undefined, "the one-shot survived a reload");
  eq(row(reopened, "A").selected, "codex",
     "a refreshed Codex chat fell back to the Settings default —");

  const framed = makeBox({ sessions: [
    { id: "A", title: "Chat A", channel: { id: "codex", source: "chat-history" } },
    { id: "B", title: "Chat B", channel: { id: "claude", source: "settings" } },
  ] });
  eq(row(framed, "A").selected, "codex", "the reconnect frame was ignored");
});

test("an armed switch is spent, so a reconnect cannot re-send it", () => {
  /* Pinned in 01-state (claudeChannel deletes the request as it builds the
     url). Restated from this side because the row now READS that request: a
     one-shot that outlived its socket would keep the row -- and every
     provider-dependent row beside it -- describing a switch already made, and
     would silently override a later one. */
  assert(/delete S\.chatProvider\[s\.id\]/.test(state),
         "the one-shot is never spent");
});

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
