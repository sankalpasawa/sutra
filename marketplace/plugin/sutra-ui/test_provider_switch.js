#!/usr/bin/env node
/*
 * test_provider_switch.js -- provider selection lives in Settings ONLY
 * (GAME-PLAN-provider-switch piece 7, revised by founder direction 2026-09-03).
 *
 * THE RULE THIS PINS
 * A provider is chosen in Settings and nowhere else. The row in the composer is
 * a read-only INDICATOR: with two runnable providers, "which one am I talking
 * to?" stops being obvious, and a chat that will not say is worse than one that
 * cannot be changed there. With fewer than two, it renders nothing at all --
 * naming the only possible answer is noise on every turn.
 *
 * AND THE MECHANISM BEHIND IT
 * The new provider applies to whatever you do NEXT. That is only true if
 * changing Settings drops the open chat sockets: a socket is bound to its
 * provider at spawn (binary and protocol both fixed there), so a message sent
 * down an existing one would reach the OLD provider while the UI claimed
 * otherwise. A pane mid-reply is spared, because closing it would discard a
 * reply the operator is waiting on.
 *
 * Two kinds of assertion, as before: behavioural on real extracted bytes for
 * the URL builder, source-level for placement and wiring -- a control rendered
 * into no pane, or a handler that never fires, is invisible to a logic test.
 *
 * Run: node test_provider_switch.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const state = J("01-state.js");
const helpers = J("02-helpers.js");
const chat = J("05-chat.js");
const screens = J("04-screens.js");
const render = J("06-render.js");
const loaders = J("07-loaders.js");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(a === b, (m || "") + " expected " + JSON.stringify(b)
                               + " got " + JSON.stringify(a));

/* ── 1. behavioural: the socket URL, on real bytes ───────────────────────── */

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

const sandbox = {
  location: { protocol: "http:", host: "127.0.0.1:7000" },
  S: { cwd: {}, sutraId: {}, sessions: [], chatProvider: {}, chatProviderNote: {} },
  SETTINGS: { workdir: "/home/op/work" },
  /* providerUsage resolves the provider's DECLARED usage kind before reading
     any state -- the `else` it replaced handed every non-DeepSeek provider
     Claude's percentage. That declaration ships on the /api/providers row, so
     the sandbox has to carry one the way the live panel does. */
  PROVIDERS: [{ id: "claude", name: "Claude Code", usage_kind: "window-percent" },
              { id: "deepseek", name: "DeepSeek", usage_kind: "balance" },
              { id: "codex", name: "OpenAI Codex", usage_kind: "none" }],
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
new vm.Script([
  grab(helpers, "usageKindOf"),
  grab(helpers, "providerUsage"),
  grab(state, "sessCwd"),
  grab(state, "sessSutraId"),
  grab(state, "sessProviderRequest"),
  grab(state, "claudeWsUrl"),
].join("\n") + "\n;globalThis.__T={sessSutraId,claudeWsUrl,providerUsage,usageKindOf,"
              + "sessProviderRequest};",
  { filename: "01-state.js#extract" }).runInContext(sandbox);
const T = sandbox.__T;

test("an ordinary turn still sends no provider on the socket url", () => {
  // THE DEFAULT IS UNCHANGED and this is the case that must stay that way.
  // With no pending request the server answers from the chat's own
  // provider_history, or from Settings -- and a provider sent on every connect
  // would put the client's stale idea of the chat ahead of the record.
  sandbox.S.cwd = { s1: "/home/op/x" }; sandbox.S.sutraId = { s1: "abc" };
  sandbox.S.chatProvider = {};
  assert(!T.claudeWsUrl("s1").includes("provider="),
         "a turn that asked for nothing must not name a provider");
});

test("a detected in-chat request DOES send the provider", () => {
  // This is the whole switch mechanism: the socket is bound to its provider at
  // spawn, so the request rides the URL of the socket that replaces it.
  sandbox.S.cwd = {}; sandbox.S.sutraId = { s1: "abc" };
  sandbox.S.chatProvider = { s1: "codex" };
  const u = T.claudeWsUrl("s1");
  assert(u.includes("provider=codex"), "the request never reached the url: " + u);
  assert(u.includes("sutra=abc"),
         "without the chat id the server cannot carry the conversation over");
  sandbox.S.chatProvider = {};
});

test("the request is per chat, never global", () => {
  sandbox.S.cwd = {}; sandbox.S.sutraId = { s1: "abc", s2: "def" };
  sandbox.S.chatProvider = { s1: "codex" };
  assert(T.claudeWsUrl("s1").includes("provider=codex"));
  assert(!T.claudeWsUrl("s2").includes("provider="),
         "one chat's request leaked onto another chat's socket");
  sandbox.S.chatProvider = {};
});

test("the chat id still rides the url, so history can be carried", () => {
  sandbox.S.cwd = {}; sandbox.S.sutraId = { s1: "abc123" };
  assert(T.claudeWsUrl("s1").includes("sutra=abc123"));
});

test("the pre-existing cwd param is untouched", () => {
  sandbox.S.cwd = { s1: "/home/op/other" }; sandbox.S.sutraId = {};
  const u = T.claudeWsUrl("s1");
  assert(u.includes("cwd="), "cwd must still be carried");
  eq((u.match(/\?/g) || []).length, 1, "exactly one '?' ");
});

test("a pane that never switched sends no chat id", () => {
  sandbox.S.cwd = {}; sandbox.S.sutraId = {};
  const prev = sandbox.SETTINGS;
  sandbox.SETTINGS = { workdir: "" };
  try { eq(T.claudeWsUrl("s1"), "ws://127.0.0.1:7000/ws/chat"); }
  finally { sandbox.SETTINGS = prev; }
});

/* The Settings provider-change handler, extracted by brace-matching rather than
   by a fixed-width window. Windows kept silently falling out of range every
   time a comment was added inside the handler -- three tests broke that way in
   one sitting, none of them because the code was wrong. */
function provHandlerSrc() {
  const i = loaders.indexOf('apiPost("/api/providers/active"');
  assert(i >= 0, "the Settings provider handler is gone");
  /* Bounded by the NEXT handler, not by brace matching: the first brace after
     apiPost is the { id: ... } argument object, which closes immediately and
     would end the slice on line one. Not bounded by a fixed width either --
     three tests fell out of range in one sitting when a comment was added
     inside the handler, none of them because the code was wrong. */
  const j = loaders.indexOf('querySelectorAll("[data-pmode-set]")', i);
  assert(j > i, "the permission-mode handler no longer follows this one -- "
                + "provHandlerSrc needs a new boundary");
  return loaders.slice(i, j);
}

/* ── 2. the composer row is an indicator, not a control ──────────────────── */

function switcherSrc() {
  const i = chat.indexOf("function providerSwitcherHtml(");
  assert(i >= 0, "providerSwitcherHtml is gone");
  let j = chat.indexOf("{", i), depth = 0;
  for (let k = j; k < chat.length; k++) {
    if (chat[k] === "{") depth++;
    else if (chat[k] === "}") { depth--; if (depth === 0) return chat.slice(i, k + 1); }
  }
  throw new Error("unbalanced braces");
}
const SW = switcherSrc();

test("the composer row has no buttons", () => {
  assert(!/<button/.test(SW), "a button implies a choice this row does not offer");
});

test("the composer row has no click targets or handlers", () => {
  ["data-provset", "data-provclear", "onclick", "aria-pressed"].forEach(bit =>
    assert(!SW.includes(bit), "read-only row still carries " + bit));
  assert(!loaders.includes("data-provset"), "a dead handler is still wired");
  assert(!loaders.includes("data-provclear"), "a dead handler is still wired");
});

test("nothing renders when fewer than two providers can run", () => {
  // Still guarded on the same condition; the return is now `noteRow`, which
  // is "" whenever there is nothing to report. Behaviour is asserted in
  // section 6 ("one runnable provider and nothing to report..."); this keeps
  // the GUARD itself from being deleted by accident.
  assert(/usable\.length < 2/.test(SW),
         "naming the only possible answer is noise on every turn");
  assert(/return noteRow/.test(SW),
         "the guard must still return the empty-unless-refused row");
});

test("nothing renders before anything has spawned", () => {
  // Still true for the ORDINARY case -- with no provider frame there is no
  // honest answer to give about what is running.
  assert(/if \(!running\) return noteRow/.test(SW),
         "the unspawned pane no longer takes its own branch -- and it must "
         + "return noteRow, because a REFUSED provider request still has to "
         + "speak there: 'use Gemini' in a brand-new chat is exactly that "
         + "case, and silence reads as a broken detector");
  // noteRow is built BEFORE both quiet-row guards, or either one swallows it.
  assert(SW.indexOf("const noteRow") < SW.indexOf("usable.length < 2"),
         "the refusal is built after a guard that can return without it");
});

test("it reports what the SERVER resolved, not a local preference", () => {
  assert(SW.includes("channel"), "the running provider comes from the provider frame");
  assert(!SW.includes("sessProvider"), "there is no per-session preference any more");
});

test("a Settings change under a live socket is stated, not hidden", () => {
  assert(SW.includes("provpend") && /next message uses/.test(SW),
         "a pane whose socket predates a Settings change must say both facts");
});

test("the read-only row is styled as a label, not a button", () => {
  assert(css.includes(".provnow"), "no style for the indicator");
  // Match the RULE, not the word: the comment above it names both classes to
  // record that they were removed, and a bare substring check reads that as
  // the styles still being present.
  assert(!/\.provopt\s*[{,]/.test(css), "button styles outlived the buttons");
  assert(!/\.provclear\s*[{,]/.test(css), "reset-button style outlived the button");
});

/* ── 3. selection lives in Settings, and drops the sockets ───────────────── */

test("no per-session provider PREFERENCE remains", () => {
  // The dead state is still dead. `S.chatProvider` is not a revival of it: a
  // preference is read on every connect and would outrank the record, whereas
  // that map is a ONE-SHOT request cleared by the socket that spends it (see
  // claudeChannel). The durable answer lives in provider_history, server-side.
  ["provider:{}", "providerError:null"].forEach(f =>
    assert(!helpers.replace(/\s/g, "").includes(f.replace(/\s/g, "")),
           "S still carries " + f + " with no control to set it"));
  assert(!/function setSessProvider\(/.test(state),
         "the per-session setter must be gone, not merely unreferenced");
  assert(/delete S\.chatProvider\[s\.id\]/.test(state),
         "the request must be spent when the socket carrying it is created, "
         + "or it would re-send on every reconnect and override a later switch");
});

test("changing the Settings provider drops the open chat sockets", () => {
  // Otherwise the next prompt rides an existing socket to the OLD provider
  // while the UI claims the new one.
  // provHandlerSrc(), not a fixed 2000-char window: the window fell out of
  // range the moment a comment was added inside the handler, which is the
  // exact fragility the extractor below this file's own comment was written
  // for.
  const body = provHandlerSrc();
  assert(body.includes("CLAUDE_SOCKETS.delete"), "sockets are not dropped");
  assert(body.includes("ws.close"), "sockets are not closed");
});

test("...but it does NOT drop a chat that chose its own provider", () => {
  // Settings = Claude, Chat A = Codex. Changing the global default to DeepSeek
  // must move new chats and leave Chat A alone -- that is the whole point of a
  // chat-local switch, and dropping A's socket would hand it to the new
  // default on its next message.
  const body = provHandlerSrc();
  assert(/providerIsChatLocal\(/.test(body),
         "the handler cannot tell a chat-local pane from a governed one");
  assert(/local\+\+|local \+= 1/.test(body),
         "a spared chat is not counted, so the receipt cannot mention it");
});

test("chat-local is read off the SERVER's provider frame", () => {
  // Not from S.chatProvider (one-shot, already spent) and not from SETTINGS.
  // `source` is how ws_chat actually resolved the provider, and it is the only
  // thing that knows about provider_history.
  const i = render.indexOf("function providerIsChatLocal(");
  assert(i > 0, "providerIsChatLocal is gone");
  const body = render.slice(i, i + 600);
  assert(/channel/.test(body) && /source/.test(body),
         "it must read the provider frame's source field");
  assert(/"chat"/.test(body) && /"chat-history"/.test(body),
         "both chat-scoped sources must count: an explicit ?provider= and the "
         + "chat's own recorded segment");
});

test("a pane mid-reply is spared", () => {
  const body = provHandlerSrc();
  assert(/streamingFor\(/.test(body) && /sideStreamingFor\(/.test(body),
         "closing a streaming pane would discard a reply being written");
});

test("the confirmation says when the change takes effect", () => {
  const body = provHandlerSrc();
  assert(/next message use/.test(body),
         "'active provider is now X' overstated it -- nothing moves until you send");
});

test("the switch ARMS the toast -- it does not fire in Settings", () => {
  // S.setOk is this screen's receipt. The fact worth having ("which provider
  // is this chat about to use") is worth having when a chat is opened.
  const body = provHandlerSrc();
  assert(/S\.provToast = true/.test(body), "the success path arms nothing");
  assert(!/showNudge\(/.test(body),
         "Settings is the screen the operator leaves -- the toast is the chat's");
  assert(!/S\.toast\s*=/.test(body), "a second notification system");
  assert(!/pushTurn|S\.turns|sideTurns/.test(body),
         "a Settings change is not a turn -- it must never enter chat history");
});

test("a REFUSED switch arms nothing", () => {
  // A 400 (provider not runnable) must not leave a toast waiting to announce a
  // switch that never happened.
  const i = loaders.indexOf('apiPost("/api/providers/active"');
  const c = loaders.indexOf(".catch(", i);
  const j = loaders.indexOf('querySelectorAll("[data-pmode-set]")', i);
  assert(c > i && j > c, "the handler's catch is gone");
  assert(!/provToast/.test(loaders.slice(c, j)), "the failure path arms the toast");
});

/* ── 3b. behavioural: pushPane spends the flag, on real bytes ─────────────
   The flag is only worth anything if the ONE place both chat-open paths share
   actually spends it, so this runs the real pushPane rather than reading it. */

function panePad(){
  const box = {
    S: { openPanes: [], provToast: null },
    SETTINGS: { provider: "codex" },
    PROVIDERS: [{ id: "codex", name: "OpenAI Codex" },
                { id: "claude", name: "Claude Code" }],
    MAX_PANES: 6, nudges: [], console,
  };
  box.showNudge = (text, ms) => { const el = { className: "nudge" };
                                  box.nudges.push({ text, ms, el }); return el; };
  vm.createContext(box);
  new vm.Script([grab(chat, "providerLabel"),
                 grab(helpers, "pushPane")].join("\n")).runInContext(box);
  return box;
}

test("opening a chat spends the flag and names the provider from SETTINGS", () => {
  const box = panePad();
  box.S.provToast = true;
  box.pushPane("s-1");
  eq(box.nudges.length, 1, "no toast on the first chat opened after a switch");
  eq(box.nudges[0].text, "This chat will use OpenAI Codex.");
  eq(box.nudges[0].ms, 5000, "the toast must clear itself after 5s");
  eq(box.S.provToast, null, "the flag was not spent");
  eq(box.S.openPanes.length, 1, "the pane must still open");
  /* The reference is a readable 18px card, not the 12px chip the shadow
     nudges are. A VARIANT class, so those callers cannot inherit it. */
  assert(/\bprovtoast\b/.test(box.nudges[0].el.className),
         "the toast does not wear the provider variant");
  assert(/\.nudge\.provtoast\s*\{/.test(css), "no style for the variant");
  assert(/\.nudge\{[^}]*font-size:12px/.test(css),
         ".nudge itself was restyled -- the shadow chips moved with it");
});

test("it fires ONCE per switch, not on every chat opened afterwards", () => {
  const box = panePad();
  box.S.provToast = true;
  box.pushPane("s-1"); box.pushPane("s-2"); box.pushPane("s-1");
  eq(box.nudges.length, 1, "one switch, one toast");
});

test("with no switch pending, opening a chat is silent", () => {
  const box = panePad();
  box.pushPane("s-1");
  eq(box.nudges.length, 0, "opening a chat is not a provider announcement");
});

test("the name comes from SETTINGS at spend time, not from the switch", () => {
  // Two switches before the next chat open collapse to one toast, naming the
  // provider that actually won.
  const box = panePad();
  box.S.provToast = true;
  box.SETTINGS.provider = "claude";
  box.pushPane("s-1");
  eq(box.nudges[0].text, "This chat will use Claude Code.");
});

test("existing showNudge callers keep the lifetime they were written against", () => {
  const nudge = fs.readFileSync(
    path.join(__dirname, "static", "js", "14-needs-you.js"), "utf8");
  assert(/function showNudge\(text, ms\)/.test(nudge), "the duration is not a parameter");
  assert(/ms \|\| 6000/.test(nudge), "the 6000 default is gone");
  ["15-shadow-overlay.js", "16-shadow-home.js"].forEach(f => {
    const src = fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
    (src.match(/showNudge\([^)]*\)/g) || []).forEach(call =>
      assert(!/,\s*\d/.test(call), f + " now passes a duration: " + call));
  });
});

/* ── 4. the surfaces that survived ───────────────────────────────────────── */

test("the rail still badges which provider wrote each transcript", () => {
  assert(helpers.includes('class="provtag'), "rowMeta has no provider tag");
  assert(helpers.includes("s.source"), "rowMeta never reads the source field");
});

test("Settings still calls it the DEFAULT provider", () => {
  assert(chat.includes('"Default provider"'));
  assert(/Which AI answers your messages/.test(chat),
         "the fold must say what it does in plain words");
});

test("the dead override notice is gone", () => {
  assert(!/function providerOverridesHtml\(/.test(chat),
         "with no per-chat control there are no overrides to disclose");
});

test("the switch marker survives -- a carry-over must still be visible", () => {
  assert(render.includes("switchMarkerHtml(s.id)"), "the marker is not rendered");
  assert(/NOT carried over/.test(chat), "a refusal must still be stated");
});

test("the carry-over failure has exactly one home", () => {
  // An ASSIGNMENT, not a mention: the comment where it used to live names the
  // field deliberately, to record why there is only one home now.
  assert(!/S\.providerError\s*=/.test(state),
         "two copies of the same failure is how one goes stale");
  assert(state.includes("S.switchNote"), "the marker's source is gone");
});

/* ── 5. usage follows the selected provider ─────────────────────────────────
   Reported 2026-09-03 with a screenshot: the Usage SCREEN showed "USD 1.81"
   while the rail badge said 26 and the footer said "26% of the usage window".
   Three surfaces derived Claude's window percentage directly, so they went on
   describing a plan the panel was no longer using. */

test("claude selected -> the window percentage", () => {
  sandbox.SETTINGS = { provider: "claude" };
  sandbox.S.usage = { available: true, limits: [{ active: true, percent: 26.4 }] };
  const r = T.providerUsage();
  eq(r.short, 26); eq(r.long, "26% of the usage window"); eq(r.row, "26% used");
});

test("deepseek selected -> a balance, never a percentage", () => {
  sandbox.SETTINGS = { provider: "deepseek" };
  sandbox.S.deepseekUsage = { available: true,
    balances: [{ currency: "USD", total_balance: "1.81" }] };
  const r = T.providerUsage();
  eq(r.short, "$1.81"); eq(r.long, "USD 1.81 balance"); eq(r.row, "$1.81 balance");
  assert(!String(r.long).includes("%"), "a percentage leaked into the deepseek reading");
});

test("stale claude usage is ignored when deepseek is selected", () => {
  // THE REPORTED BUG: falling through to S.usage left three 26% readings behind.
  sandbox.SETTINGS = { provider: "deepseek" };
  sandbox.S.usage = { available: true, limits: [{ active: true, percent: 26.4 }] };
  sandbox.S.deepseekUsage = null;
  assert(T.providerUsage() === null, "fell back to Claude's percentage");
});

test("nothing fetched yet -> null, so no surface asserts a number", () => {
  sandbox.SETTINGS = { provider: "claude" };
  sandbox.S.usage = null; sandbox.S.deepseekUsage = null;
  assert(T.providerUsage() === null, "asserted a figure nobody fetched");
});

test("a provider with no usage concept gets null, not Claude's percentage", () => {
  /* THE SAME BUG ONE PROVIDER LATER. The reported failure was DeepSeek falling
     through to S.usage; the shape that caused it -- `if (deepseek) ... else
     Claude` -- left every future provider in the else. Codex reports neither a
     window nor a balance, and the day it becomes selectable it must show
     nothing rather than Anthropic's number. */
  sandbox.SETTINGS = { provider: "codex" };
  sandbox.S.usage = { available: true, limits: [{ active: true, percent: 26.4 }] };
  sandbox.S.deepseekUsage = { available: true,
    balances: [{ currency: "USD", total_balance: "1.81" }] };
  assert(T.providerUsage() === null, "borrowed another provider's figure");
});

test("an unread provider table withholds rather than guesses", () => {
  /* Deliberate: with no table there is no way to tell which kind of fact
     applies, and asserting one anyway is the whole failure. */
  const prev = sandbox.PROVIDERS;
  sandbox.PROVIDERS = [];
  sandbox.SETTINGS = { provider: "claude" };
  sandbox.S.usage = { available: true, limits: [{ active: true, percent: 26.4 }] };
  try { assert(T.providerUsage() === null, "asserted a figure with no provider table"); }
  finally { sandbox.PROVIDERS = prev; }
});

test("the caller may name a provider, so a pane can differ from the app", () => {
  /* SETTINGS.provider is global; a pane's provider is its own. Without the
     argument a DeepSeek pane left open across a switch to Claude would quote
     Claude's percentage for a session DeepSeek is still answering. */
  sandbox.SETTINGS = { provider: "claude" };
  sandbox.S.usage = { available: true, limits: [{ active: true, percent: 26.4 }] };
  sandbox.S.deepseekUsage = { available: true,
    balances: [{ currency: "USD", total_balance: "1.81" }] };
  eq(T.providerUsage("deepseek").row, "$1.81 balance");
  eq(T.providerUsage("claude").row, "26% used");
});

test("all three surfaces read the one helper", () => {
  // A correct helper that two of three callers ignore is the bug unfixed.
  assert(/c:\(\(providerUsage\(\)/.test(helpers), "the rail badge does not use it");
  assert(loaders.includes("providerUsage()"), "the footer telemetry does not use it");
  assert(render.includes("providerUsage()"), "the pane menu row does not use it");
});

test("the percentage is derived in exactly one place", () => {
  // providerUsage itself must derive it -- that is its job. What must NOT
  // happen is a second copy in a rendering surface, which is how the three
  // readings drifted apart in the first place.
  const pat = /limits\|\|\[\]\)\.find\(r=>r\.active\)/g;
  const n = (helpers.replace(/\s/g, "").match(pat) || []).length;
  eq(n, 1, "the derivation should live only inside providerUsage;");
  [["footer", loaders], ["pane menu", render]].forEach(([who, src]) => {
    assert(!pat.test(src.replace(/\s/g, "")),
           who + " still derives Claude's window percentage directly");
  });
});

/* ── 6. the Provider row (founder 2026-09-03; renamed 2026-09-07) ─────────── */

test("the nested row is called AI Provider, not Settings", () => {
  // "Settings" inside the Settings destination repeated its parent and said
  // nothing about what was behind it.
  assert(helpers.includes('n:"AI Provider"'), "railSpec does not label the row AI Provider");
  assert(chat.includes('settings:["AI Provider"'), "TITLES does not say AI Provider");
  // This assertion used to run the other way -- it FORBADE "AI Provider", on
  // the reasoning that the provider is one of the screen's three folds
  // (provider, permission mode, workdir). Founder direction 2026-09-07
  // overrode that: provider is the word every other surface already uses.
  // What is checked now is that the old label is gone from BOTH files. The
  // label lives in two of them, so a half-landed rename would show an
  // operator two names for one screen.
  // Assembled from parts so a future blanket rename cannot rewrite the string
  // this guard exists to forbid -- which is exactly what happened on the
  // 2026-09-07 pass, leaving the assert banning the new name.
  const OLD_LABEL = "AI " + "Assistant";
  assert(!helpers.includes(OLD_LABEL) && !chat.includes(OLD_LABEL),
         `the old ${OLD_LABEL} label survives in railSpec or TITLES`);
});

test("the Preferences group is gone and the row lives under System", () => {
  const plane = state.slice(state.indexOf('settings: [{group:"Tools"'));
  const body = plane.slice(0, plane.indexOf("\n};"));
  assert(!/group:"Preferences"/.test(body), "a one-row group is a header that earns nothing");
  const sys = body.slice(body.indexOf('group:"System"'));
  const rows = [...sys.matchAll(/screen:"([a-z]+)"/g)].map(m => m[1]);
  assert(rows.includes("settings"), "the assistant row is not under System");
  // eq() is strict ===, which is always false for arrays -- compare serialised.
  eq(rows.join(","), "health,evals,history,settings", "System rows;");
});

test("the top-level destination is still called Settings", () => {
  // Only the nested row was renamed; the rail button keeps its name.
  assert(/settings:"Settings"/.test(helpers), "DEST_LABEL was renamed by mistake");
});

test("the screen id did not change", () => {
  // Links, openScreen and every stale selection validate against this id.
  assert(helpers.includes('id:"settings"'), "the screen id moved with the label");
});

/* ── 7. plain language in the two operator-facing folds (founder 2026-09-03) ── */

function foldSrc(a, b) {
  const i = chat.indexOf(a); const j = chat.indexOf(b, i);
  assert(i >= 0 && j > i, "could not isolate " + a);
  return chat.slice(i, j);
}

test("the provider fold carries no implementation jargon", () => {
  const src = foldSrc('fold("set.prov"', 'fold("set.mode"');
  ["binary", "on PATH", "config directory", "adapter", "stream-json",
   "Resolved via", "catalog default"].forEach(j =>
    assert(!src.includes(j), "operator-facing copy still says " + JSON.stringify(j)));
});

test("the project-folder fold carries no implementation jargon", () => {
  const src = foldSrc('fold("set.workdir"', "Some saved settings could not be used");
  ["working directory", "read oracle", "In force", "cwd",
   "SUTRA_UI_WORKDIR_ROOT"].forEach(j =>
    assert(!src.includes(j), "operator-facing copy still says " + JSON.stringify(j)));
  assert(src.includes('"Project folder"'), "the fold is still called Workdir");
});

test("a provider that cannot run says WHY, in a user's words", () => {
  // providers.py exists so the panel never says "unavailable" without saying
  // why. Every not-runnable case still gets a status here -- what changed
  // (founder 2026-09-07, "only show minimum a user might want to see") is that
  // the status is ALL this list shows.
  assert(/Not installed on this Mac/.test(chat), "no plain status for not-installed");
  assert(/not signed in yet/.test(chat), "no plain status for installed-but-unconfigured");
  assert(/can’t chat with it yet/.test(chat), "no plain status for installed-but-no-adapter");
  assert(/Ready to use/.test(chat), "no plain status for runnable");
});

test("the provider list does NOT render the server's diagnostic sentence", () => {
  // What this removes, measured: up to ~400 characters per row naming binary
  // paths, ~/.codex/auth.json, PATH, an npm package, the ACP and stream-json
  // protocols, a codex-cli version pin, and the keychain service and account a
  // key would live at. True, and not what this list is asked.
  const row = chat.slice(chat.indexOf("const provRow ="),
                         chat.indexOf("const running ="));
  assert(!/p\.reason/.test(row),
         "provRow renders p.reason again -- the row is back to explaining Sutra "
         + "to whoever opened Settings");
  const fold = chat.slice(chat.indexOf('fold("set.prov"'), chat.indexOf('fold("set.mode"'));
  assert(!/i\.reason/.test(fold),
         "the fallback banner pastes the same sentence back in under a different "
         + "heading");
  assert(!/SUTRA_UI_|not on PATH|auth\.json|stream-json/.test(fold),
         "an internals name leaked back into the Default provider fold");
});

test("the diagnostic sentence still HAS a home", () => {
  // This was a change of audience, not a deletion. Someone who wants the exact
  // reason goes to Health; if that stops rendering it too, the detail is gone
  // from the product and this test is the only thing that would notice.
  assert(/p\.reason/.test(screens),
         "nothing renders the provider reason any more -- Health lost it too");
  assert(/Why nothing here runs/.test(screens),
         "the Health block that carries it is gone");
});

test("the one status that would be a lie is told from a FLAG, not prose", () => {
  // "Not installed on this Mac" is wrong for the person who has Claude Desktop
  // and believes they installed Claude (providers.py's own field incident). The
  // UI must decide the wording; the backend only says whether it is that case.
  assert(/desktop_only/.test(chat), "the Claude Desktop case is not handled in the row");
  assert(/needs Claude Code/.test(chat),
         "the row does not name the actual fix for a Claude Desktop user");
  const py = fs.readFileSync(path.join(__dirname, "providers.py"), "utf8");
  assert(/"desktop_only":/.test(py), "providers.py does not send the flag");
});

test("a refused saved choice is explained, not labelled", () => {
  assert(/could not be used/.test(chat), "the ignored-override notice is gone");
  assert(!/An override was NOT honoured/.test(chat), "still says 'override not honoured'");
});

test("Usage renders inside the AI Provider screen, not as its own row", () => {
  // How much of an assistant you have used is a fact about the assistant you
  // just picked; a separate destination made you cross the app to answer a
  // question this screen had raised.
  assert(chat.includes("SCREENS.usage()"),
         "the AI Provider screen does not render the usage section");
  const plane = state.slice(state.indexOf('settings: [{group:"Tools"'));
  const body = plane.slice(0, plane.indexOf("\n};"));
  assert(!/screen:"usage"/.test(body), "usage still has a nav row");
});

test("the usage figure moved onto the row you can actually click", () => {
  const i = helpers.indexOf('{id:"settings",n:"AI Provider"');
  assert(i > 0, "the AI Provider entry is gone");
  assert(/providerUsage\(\)/.test(helpers.slice(i, i + 260)),
         "the AI Provider row carries no usage count");
  const j = helpers.indexOf('{id:"usage"');
  assert(!/providerUsage\(\)/.test(helpers.slice(j, j + 160)),
         "the row-less usage entry still computes a badge nobody sees");
});

test("opening the AI Provider screen fetches usage", () => {
  // Otherwise the section sits on "Reading usage..." until something else
  // happens to load it.
  // Match the screen-open dispatcher specifically -- loadUsage is also called
  // from the composer popover and the sign-in flow, and indexOf found those.
  assert(/id === "usage" \|\| id === "settings"/.test(loaders),
         "the AI Provider screen does not trigger a usage load on open");
});

/* ── 8. two defects from a screenshot, 2026-09-03 ──────────────────────────── */

test("switching provider refetches usage for the provider you switched TO", () => {
  // Usage renders as a section of this very screen and the two providers keep
  // their figures in different state. Without a refetch the section sat on
  // "Reading usage..." indefinitely -- the screen-open trigger cannot help,
  // because you never left the screen.
  const body = provHandlerSrc();
  assert(/loadUsage\(true\)/.test(body),
         "the provider change never refetches usage");
});

test("the refetch forces, because the cached state belongs to the other provider", () => {
  const body = provHandlerSrc();
  assert(!/loadUsage\(\s*\)/.test(body),
         "loadUsage() without force early-returns on state left by the "
         + "provider you just switched away from");
});

test("the status line and the detail line are separate blocks", () => {
  // .oi is a plain block and both are spans, so without display:block they
  // flow inline and their margin-top does nothing -- producing
  // "Not installed on this Mac binary 'gemini' not on PATH...".
  const od = css.slice(css.indexOf(".opt .od{"), css.indexOf(".opt .od{") + 90);
  const why = css.slice(css.indexOf(".opt .why{"), css.indexOf(".opt .why{") + 90);
  assert(/display:block/.test(od), ".opt .od is not a block -- it will run inline");
  assert(/display:block/.test(why), ".opt .why is not a block -- it will run inline");
});

test("the detail line reads as supporting detail, not a second error", () => {
  // The plain status already says what is wrong; the detail carries the fix.
  const why = css.slice(css.indexOf(".opt .why{"), css.indexOf(".opt .why{") + 120);
  assert(!/color:var\(--block\)/.test(why),
         "the detail line still shouts in the error colour beneath a status "
         + "line that already stated the problem");
});

/* ── entering a key installs the CLI ─────────────────────────────────────────
   The founder-reported state (screenshot 2026-09-07): a validated key saved on
   a Mac with no `deepseek` binary. The panel confirmed a success under a row
   that correctly read "Not installed on this Mac", and there was no control
   anywhere on the screen that could fix it. These guard the two halves of the
   remedy -- the automatic chain, and the button for a key saved long ago. */

test("a saved key with no CLI installs the CLI, without a second click", () => {
  assert(/SAVED_NO_CLI/.test(loaders),
         "the save handler no longer reads the backend's no-CLI code, so the "
         + "install never fires and entering a key leaves a dead row again");
  const chain = loaders.slice(loaders.indexOf('verb === "save" && r.code'),
                              loaders.indexOf('verb === "save" && r.code') + 220);
  assert(/deepseekInstallCli\(\)/.test(chain),
         "SAVED_NO_CLI is read and nothing is done about it");
});

test("the install holds the busy flag, so two cannot run into one prefix", () => {
  const fn = loaders.slice(loaders.indexOf("async function deepseekInstallCli"),
                           loaders.indexOf('scBody.querySelectorAll("[data-deepseek]")'));
  assert(/S\.deepseekBusy = "install"/.test(fn), "the install does not mark itself busy");
  assert(/S\.deepseekBusy = null/.test(fn), "the busy flag is never cleared -- the "
         + "field and both buttons would stay disabled after an install");
});

test("a key saved before this feature still gets a way to install the CLI", () => {
  assert(/data-deepseek="install"/.test(chat),
         "the signed-in block offers no install control, so a Mac with a saved "
         + "key and no CLI has nothing to press");
  assert(/dsRow\.installed/.test(chat),
         "the install block is not conditioned on the row's own installed flag "
         + "-- it will render over a machine that already has the CLI");
});

/* ONE RULE, BOTH PLACES. This assertion used to cover only the block, and the
   FALLBACK message leaked exactly what the block was scrubbed of: it ended
   "or run  npm install -g @sluisr/deepseek-cli  in a terminal" (founder,
   2026-09-07). Two failures in one sentence -- an internals leak, and a
   recommendation of the GLOBAL install deepseek_install.py refuses because a
   root-owned prefix answers EACCES. Both strings are checked here now, because
   a rule enforced in one of two places is how the second one drifts. */
const INTERNALS = ["npm", "node_modules", "PATH", "sluisr", "--prefix", "-g"];

test("the install copy names no internals", () => {
  const block = chat.slice(chat.indexOf("const cliBlock ="),
                           chat.indexOf("const cliBlock =") + 1200);
  INTERNALS.forEach(j =>
    assert(!block.includes(j),
           "the install block says " + JSON.stringify(j) + " -- the backend owns "
           + "that judgment and answers with it only when the install is refused"));
});

test("the stale-bundle message is one sentence and names no internals", () => {
  // The only thing a person with an old app can do is update it. Anything else
  // in this box is either unusable or a trap.
  const guard = loaders.slice(loaders.indexOf("if (bridge && !bridge.deepseekCliInstall)"),
                              loaders.indexOf('S.deepseekBusy = "install"'));
  const msg = (guard.match(/S\.deepseekMsg = ([\s\S]*?);/) || [])[1] || "";
  assert(msg, "the stale-bundle guard no longer sets a message");
  INTERNALS.forEach(j =>
    assert(!msg.includes(j),
           "the stale-bundle message says " + JSON.stringify(j)
           + " -- the same leak the install block is held to"));
  assert(/update the sutra app/i.test(msg), "it no longer names the actual fix");
  assert((msg.match(/\./g) || []).length === 1,
         "more than one sentence -- there is exactly one thing to do");
});

/* ── 6. a chat may run on its own provider while Settings stays put ───────── */

/* Settings = Claude, Chat A = Codex (server said source:"chat-history"),
   Chat B = Claude, Chat C has never spawned. */
const CHAT_LOCAL_SESSIONS = [
  { id: "A", channel: { id: "codex", source: "chat-history" } },
  { id: "B", channel: { id: "claude", source: "settings" } },
  { id: "C" },
  { id: "D", source: "codex" },     /* reopened from the rail, no socket yet */
];

const UI = (() => {
  const box = {
    /* chatProvider is the ARMED-BUT-NOT-YET-SPAWNED switch paneProvider now
       consults first (see 06-render). Empty here: these four sessions are all
       past that window, so the answer must come from what the server said. */
    S: { sessions: CHAT_LOCAL_SESSIONS, chatProviderNote: {}, chatProvider: {} },
    SETTINGS: { provider: "claude" },
    PROVIDERS: [{ id: "claude", name: "Claude Code", runnable: true },
                { id: "codex", name: "OpenAI Codex", runnable: true },
                { id: "deepseek", name: "DeepSeek", runnable: true }],
    esc: (x) => String(x == null ? "" : x).replace(/[&<>"]/g, c =>
           ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessProviderRequest"),
    grab(render, "paneProvider"),
    grab(render, "providerIsChatLocal"),
    grab(chat, "providerLabel"),
    grab(chat, "providerSwitcherHtml"),
  ].join("\n") + "\n;globalThis.__U={paneProvider,providerIsChatLocal,providerSwitcherHtml};",
    { filename: "ui#extract" }).runInContext(box);
  return { box, fns: box.__U };
})();

test("paneProvider answers the CHAT's provider, not the global default", () => {
  eq(UI.fns.paneProvider(CHAT_LOCAL_SESSIONS[0]), "codex",
     "Chat A is on codex; Settings says claude");
  eq(UI.fns.paneProvider(CHAT_LOCAL_SESSIONS[1]), "claude", "Chat B");
});

test("an unspawned pane falls back to the global default", () => {
  eq(UI.fns.paneProvider(CHAT_LOCAL_SESSIONS[2]), "claude",
     "nothing is known about C yet, so Settings is the honest answer");
});

test("a chat reopened from the rail uses its transcript's provider", () => {
  // The window before the first message. Without this a Codex chat reopened
  // from the rail paints Claude's model list, Claude's permission set and
  // Claude's usage kind -- for precisely as long as the operator is looking at
  // the menu before asking anything.
  eq(UI.fns.paneProvider(CHAT_LOCAL_SESSIONS[3]), "codex");
});

/* THE REFRESH, END TO END, on the shape /api/sessions really returns.

   The four fixtures above set `source` by hand, and that is exactly how this
   bug survived: nothing in the client was assigning it. adoptRealSessions
   REBUILDS every on-disk row into a new object, and its literal copied id,
   title, project, cwd, branch, mtime, size and claude_session -- but not
   `source`. So paneProvider's transcript-provider branch could never fire, and
   a Codex chat reopened after a refresh reported the GLOBAL Settings default
   until its next turn's provider frame arrived.

   Measured against the live endpoint 2026-09-09: row source="codex",
   id="01a085fc-...", sutra_id="5bafdfaa..." -- and paneProvider answered
   "claude". This drives the REAL rebuild rather than a fixture, which is the
   only thing that could have caught it. */
const REFRESH = (() => {
  const box = {
    S: { sessions: [], openPanes: [], cwd: {}, sutraId: {},
         chatProvider: {}, chatProviderNote: {} },
    SETTINGS: { provider: "claude" },       /* Settings still says Claude */
    /* the preservation branches are not under test: a refreshed page has no
       in-flight turn and no loaded pane to keep */
    sessionBusy: () => false,
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "adoptRealSessions"),
    grab(state, "sessProviderRequest"),
    grab(render, "paneProvider"),
  ].join("\n") + "\n;globalThis.__R={adoptRealSessions,paneProvider};",
    { filename: "refresh#extract" }).runInContext(box);
  return { box: box, fns: box.__R };
})();

/* One page of /api/sessions, verbatim in shape: a Codex-only chat (the new-chat
   case -- its only transcript lives in codex's tree) and a Claude one. */
const REFRESH_ROWS = [
  { id: "01a085fc-3c41-7f20-bc80-b37a69f02e47", source: "codex",
    title: "what's 4=5", cwd: "/w/sutra-ui", branch: "main",
    mtime: 1789000000, size: 1234,
    sutra_id: "5bafdfaa415246398d0b08e6b1fb38c3" },
  { id: "07c7e7e1-9cea-404a-a0a7-9263805b8608", source: "claude",
    title: "something else", cwd: "/w/sutra-ui", branch: "main",
    mtime: 1788999000, size: 999, sutra_id: null },
];

test("a refreshed row KEEPS the provider that wrote it", () => {
  REFRESH.fns.adoptRealSessions(REFRESH_ROWS);
  const codex = REFRESH.box.S.sessions.find(s => s.id === REFRESH_ROWS[0].id);
  assert(codex, "the codex row was not adopted at all");
  eq(codex.source, "codex",
     "adoptRealSessions dropped the row's source, so paneProvider has nothing "
     + "to read —");
});

test("...so paneProvider reports Codex, not the Settings default", () => {
  // THE REGRESSION. Settings says claude and this chat is on codex; before the
  // fix the reopened pane answered "claude" -- the composer row, the Model,
  // Permissions, Turn options and Usage rows and the Chat AI Provider row all
  // named a provider the chat was not on.
  REFRESH.fns.adoptRealSessions(REFRESH_ROWS);
  const codex = REFRESH.box.S.sessions.find(s => s.id === REFRESH_ROWS[0].id);
  const claude = REFRESH.box.S.sessions.find(s => s.id === REFRESH_ROWS[1].id);
  eq(REFRESH.fns.paneProvider(codex), "codex",
     "a refreshed Codex chat fell back to the global default —");
  eq(REFRESH.fns.paneProvider(claude), "claude", "the Claude row");
  eq(REFRESH.box.SETTINGS.provider, "claude",
     "the rebuild wrote the global default");
});

test("the hint stays BELOW the server's frame", () => {
  /* `source` says what this ROW is; the chat's durable provider is its
     provider_history segment, which only the ws frame reports. A chat whose
     rail row is its Claude transcript but whose live socket resolved Codex
     must answer Codex. */
  REFRESH.fns.adoptRealSessions(REFRESH_ROWS);
  const claude = REFRESH.box.S.sessions.find(s => s.id === REFRESH_ROWS[1].id);
  claude.channel = { id: "codex", source: "chat-history" };
  eq(REFRESH.fns.paneProvider(claude), "codex",
     "the transcript hint outranked the frame the server actually sent —");
});

test("providerIsChatLocal separates governed chats from pinned ones", () => {
  assert(UI.fns.providerIsChatLocal("A") === true, "A chose codex itself");
  assert(UI.fns.providerIsChatLocal("B") === false, "B is on the global default");
  assert(UI.fns.providerIsChatLocal("C") === false,
         "nothing has told us C is pinned, and guessing would strand it");
});

test("the composer row names the chat's provider and says it is chat-local", () => {
  const html = UI.fns.providerSwitcherHtml("A");
  assert(/OpenAI Codex/.test(html), "the row does not name codex: " + html);
  assert(/this chat only/.test(html), "nothing marks it as chat-local: " + html);
  assert(/provlocal/.test(html), "the chip is not styled as divergent");
});

test("a chat-local pane is NOT told the global default will take over", () => {
  // The defect this replaces: `dflt !== running` rendered "next message uses
  // Claude Code" over a chat pinned to Codex -- a promise the Settings handler
  // no longer keeps, because it now spares that socket.
  const html = UI.fns.providerSwitcherHtml("A");
  assert(!/next message uses/.test(html),
         "a false promise survives on a chat-local pane: " + html);
});

test("a governed pane still states a pending Settings change", () => {
  // Unchanged behaviour for the chats the global default really does govern.
  UI.box.SETTINGS = { provider: "deepseek" };
  try {
    const html = UI.fns.providerSwitcherHtml("B");
    assert(/next message uses/.test(html) && /DeepSeek/.test(html),
           "a pane whose socket predates a Settings change must say both: " + html);
  } finally { UI.box.SETTINGS = { provider: "claude" }; }
});

test("a refused provider request speaks even on a pane that never spawned", () => {
  UI.box.S.chatProviderNote = { C: "Gemini CLI is not ready to use — no chat adapter yet." };
  try {
    const html = UI.fns.providerSwitcherHtml("C");
    assert(/Gemini CLI is not ready/.test(html),
           "the refusal was swallowed on an unspawned pane: " + JSON.stringify(html));
    assert(/provnote/.test(html), "no style hook for the note");
  } finally { UI.box.S.chatProviderNote = {}; }
});

test("a refusal speaks even when only ONE provider can run", () => {
  // The likeliest place to type "use Codex" and be refused is a machine that
  // cannot run Codex -- and that is exactly the machine whose row returns
  // early because a one-item provider list is noise. The note must outrank
  // that rule, or an explicit instruction is answered by nothing at all.
  const prev = UI.box.PROVIDERS;
  UI.box.PROVIDERS = [{ id: "claude", name: "Claude Code", runnable: true }];
  UI.box.S.chatProviderNote = { B: "OpenAI Codex is not ready to use — nobody is signed in." };
  try {
    const html = UI.fns.providerSwitcherHtml("B");
    assert(/not ready to use/.test(html),
           "the refusal was swallowed by the one-provider guard: "
           + JSON.stringify(html));
  } finally { UI.box.PROVIDERS = prev; UI.box.S.chatProviderNote = {}; }
});

test("one runnable provider and nothing to report still renders nothing", () => {
  const prev = UI.box.PROVIDERS;
  UI.box.PROVIDERS = [{ id: "claude", name: "Claude Code", runnable: true }];
  try {
    eq(UI.fns.providerSwitcherHtml("B"), "",
       "naming the only possible answer is noise on every turn");
  } finally { UI.box.PROVIDERS = prev; }
});

test("with nothing to report an unspawned pane still renders nothing", () => {
  eq(UI.fns.providerSwitcherHtml("C"), "",
     "naming a provider no socket has resolved would be a guess");
});

/* ── 7. the switch never touches the global default ──────────────────────── */

function applySrc() {
  const i = helpers.indexOf("function applyProviderRequest(");
  assert(i >= 0, "applyProviderRequest is gone");
  let j = helpers.indexOf("{", i), depth = 0;
  for (let k = j; k < helpers.length; k++) {
    if (helpers[k] === "{") depth++;
    else if (helpers[k] === "}") { depth--; if (depth === 0) return helpers.slice(i, k + 1); }
  }
  throw new Error("unbalanced braces");
}
const APPLY = applySrc();
/* THE SWITCH ITSELF MOVED OUT of applyProviderRequest and into
   switchChatProvider, which the ⋮ menu's Chat AI Provider row calls too -- one
   function, so the two ways of asking for a switch cannot answer differently.
   The pins below describe the in-chat PATH, which is now both functions. */
function switchFnSrc() {
  const i = helpers.indexOf("function switchChatProvider(");
  assert(i >= 0, "switchChatProvider is gone -- the shared switch must exist");
  let j = helpers.indexOf("{", i), depth = 0;
  for (let k = j; k < helpers.length; k++) {
    if (helpers[k] === "{") depth++;
    else if (helpers[k] === "}") { depth--; if (depth === 0) return helpers.slice(i, k + 1); }
  }
  throw new Error("unbalanced braces");
}
const SWITCH_FN = switchFnSrc();
const IN_CHAT_PATH = APPLY + "\n" + SWITCH_FN;

test("an in-chat switch never writes the global provider", () => {
  // THE LOCKED CONSTRAINT. Settings.provider governs new chats and chats that
  // never asked; an in-chat request is explicitly not a vote about it.
  assert(!/providers\/active/.test(IN_CHAT_PATH),
         "the in-chat path posts to the global provider endpoint");
  assert(!/api\/settings/.test(IN_CHAT_PATH), "the in-chat path writes settings");
  assert(!/SETTINGS\s*=/.test(IN_CHAT_PATH), "the in-chat path reassigns SETTINGS");
});

test("a request for the provider already running does nothing at all", () => {
  // No socket drop, no replay, no marker: the server would answer NOT_NEEDED
  // and the reconnect would cost a cold start to arrive where it already is.
  assert(/target === paneProvider\(s\)/.test(IN_CHAT_PATH),
         "the same-provider case is not short-circuited");
});

test("readiness is the server's answer, never a local one", () => {
  assert(/p\.runnable/.test(APPLY) || /runnable/.test(APPLY),
         "the runnable list must come from the provider table");
  assert(/want\.ready/.test(APPLY), "the detector's readiness verdict is ignored");
});

test("the boot window never claims a provider is unready", () => {
  /* PROVIDERS is [] until GET /api/providers resolves, and GET /api/providers
     returns EVERY catalogued provider whatever its readiness -- so empty means
     NOT FETCHED, never "nothing is ready". Read as a readiness answer it
     printed "OpenAI Codex is not ready to use" over a Codex that was fine.
     The guard must DEFER (hold the message, assert nothing) rather than
     invent a verdict in either direction. */
  assert(/const loaded = \(PROVIDERS \|\| \[\]\)\.length > 0/.test(APPLY),
         "not-loaded is not distinguished from nothing-is-ready");
  const notLoaded = APPLY.indexOf("if (!loaded)");
  const notReady = APPLY.indexOf("if (!want.ready)");
  assert(notLoaded > 0 && notReady > 0, "one of the two branches is gone");
  assert(notLoaded < notReady,
         "the readiness verdict is reached before the table is known to exist");
  const body = APPLY.slice(notLoaded, notReady);
  assert(/return true/.test(body), "the message is sent anyway -- it must defer");
  assert(!/not ready/i.test(body),
         "the boot window still asserts a readiness verdict it cannot have");
});

test("a pane mid-reply is spared, as the Settings handler spares it", () => {
  assert(/streamingFor\(/.test(IN_CHAT_PATH) && /sideStreamingFor\(/.test(IN_CHAT_PATH),
         "switching now would discard the reply being written");
});

test("the switch is the reconnect -- no per-turn routing was introduced", () => {
  assert(/closeClaudeChannel\(/.test(IN_CHAT_PATH),
         "the socket is bound to its provider at spawn, so the switch must "
         + "drop it");
  assert(/S\.chatProvider\[s\.id\] =/.test(IN_CHAT_PATH),
         "the request never reaches the url builder");
});

/* BEHAVIOURAL, on the real bytes: applyProviderRequest executed with the exact
   state the boot window presents. The source-level test above pins the shape of
   the guard; this one pins what an operator actually sees. */
function runApply(providers, text) {
  const box = {
    S: { chatProviderNote: {}, chatProvider: {}, sessions: [] },
    PROVIDERS: providers,
    SEED: { provider_aliases: { "codex": "codex", "claude": "claude" } },
    paneProvider: () => "claude",
    providerLabel: (id) => ({ codex: "OpenAI Codex", claude: "Claude Code" }[id] || id),
    streamingFor: () => false,
    sideStreamingFor: () => false,
    closed: 0,
    console,
  };
  box.closeClaudeChannel = () => { box.closed++; };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grabVarLike(helpers, "PROVIDER_INTENT_PREFIX"),
    grabVarLike(helpers, "PROVIDER_INTENT_QUESTION"),
    grabVarLike(helpers, "PROVIDER_INTENT_NEGATION"),
    grab(helpers, "stripProviderNoise"),
    grab(helpers, "providerIntentFrames"),
    grab(helpers, "providerIntentOpensWithDirective"),
    grab(helpers, "detectProviderIntent"),
    grab(helpers, "switchChatProvider"),
    grab(helpers, "applyProviderRequest"),
  ].join("\n") + "\n;globalThis.__A=applyProviderRequest;",
    { filename: "apply#extract" }).runInContext(box);
  const held = box.__A({ id: "A" }, text);
  return { held, note: box.S.chatProviderNote.A, want: box.S.chatProvider.A,
           closed: box.closed };
}

/* The full table GET /api/providers returns -- every catalogued provider,
   whatever its readiness. This is why an EMPTY list can only mean not-fetched. */
const TABLE_READY = [{ id: "claude", name: "Claude Code", runnable: true },
                     { id: "codex", name: "OpenAI Codex", runnable: true }];
const TABLE_CODEX_OUT = [{ id: "claude", name: "Claude Code", runnable: true },
                         { id: "codex", name: "OpenAI Codex", runnable: false,
                           reason: "nobody is signed in" }];

test("BOOT WINDOW: 'use Codex' before the table loads defers, and says nothing false", () => {
  const r = runApply([], "use Codex");
  assert(r.held === true, "the message was sent on a verdict we cannot have");
  assert(!/not ready/i.test(r.note || ""),
         "still claims Codex is unready during the boot window: " + r.note);
  assert(/still checking/i.test(r.note || ""), "no honest note: " + r.note);
  assert(r.want === undefined, "a switch was proposed without a provider table");
  assert(r.closed === 0, "the socket was dropped on an unvalidated switch");
});

test("LOADED + ready: unchanged -- the switch happens", () => {
  const r = runApply(TABLE_READY, "use Codex");
  assert(r.held === false, "a valid switch must not defer");
  assert(r.want === "codex", "the request was not recorded: " + r.want);
  assert(r.closed === 1, "the socket was not dropped, so nothing reconnects");
  assert(r.note === undefined, "a successful switch needs no note: " + r.note);
});

test("LOADED + genuinely unready: unchanged -- refused, with the real reason", () => {
  const r = runApply(TABLE_CODEX_OUT, "use Codex");
  assert(r.held === false, "a refusal must not hold the message");
  assert(/not ready to use/.test(r.note || ""), "the refusal lost its wording: " + r.note);
  assert(/nobody is signed in/.test(r.note || ""),
         "the provider table's own reason is no longer shown: " + r.note);
  assert(r.want === undefined, "an unready provider was proposed");
  assert(r.closed === 0, "the socket was dropped for a switch that cannot happen");
});

test("BOOT WINDOW: a non-request is still not a request", () => {
  // The guard must not turn every message into a deferral just because the
  // table is missing -- only ones that actually named a provider.
  const r = runApply([], "implement the parser");
  assert(r.held === false, "an ordinary message was held during boot");
  assert(r.note === undefined, "an ordinary message got a provider note");
});

test("BOOT WINDOW: ambiguity still answers without the table", () => {
  const r = runApply([], "use Codex, then switch to Claude");
  assert(r.held === false, "ambiguity needs no provider table, so it must not defer");
  assert(/say which one/.test(r.note || ""), "lost the ambiguity note: " + r.note);
});

test("side chats do not switch the chat's provider", () => {
  // askSide deliberately bypasses submitTurn (it files no placement), and that
  // is also what keeps an exploratory branch from moving the whole chat.
  const i = helpers.indexOf("function askSide(");
  const body = helpers.slice(i, helpers.indexOf("\n}", i));
  assert(!/applyProviderRequest/.test(body),
         "a side chat must not move the chat's provider");
  assert(/askClaude\(s, turn, true\)/.test(body), "askSide changed shape");
});

/* ── 8. end to end, on the real bytes: the founder's own sequence ────────── */

/* detectProviderIntent -> S.chatProvider -> claudeWsUrl, composed. The unit
   tests above prove each piece; this proves the JOIN, which is where a feature
   assembled from three files actually breaks. Nothing is mocked but the
   globals the two functions read. */
const E2E = (() => {
  const box = {
    location: { protocol: "http:", host: "127.0.0.1:7000" },
    S: { cwd: {}, sutraId: { A: "aaaa", B: "bbbb" }, chatProvider: {} },
    SETTINGS: { workdir: "" },
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grabVarLike(helpers, "PROVIDER_INTENT_PREFIX"),
    grabVarLike(helpers, "PROVIDER_INTENT_QUESTION"),
    grabVarLike(helpers, "PROVIDER_INTENT_NEGATION"),
    grab(helpers, "stripProviderNoise"),
    grab(helpers, "providerIntentFrames"),
    grab(helpers, "providerIntentOpensWithDirective"),
    grab(helpers, "detectProviderIntent"),
    grab(state, "sessCwd"),
    grab(state, "sessSutraId"),
    grab(state, "sessProviderRequest"),
    grab(state, "claudeWsUrl"),
  ].join("\n") + "\n;globalThis.__E={detectProviderIntent,claudeWsUrl};",
    { filename: "e2e#extract" }).runInContext(box);
  return box;
})();

function grabVarLike(src, name) {
  const start = src.indexOf("var " + name + " =");
  assert(start >= 0, "could not find var " + name);
  const end = src.indexOf(";\n", start);
  return src.slice(start, end + 1);
}

const ALIASES_E2E = { "claude": "claude", "claude code": "claude",
                      "codex": "codex", "openai codex": "codex",
                      "gemini": "gemini", "deepseek": "deepseek" };
const READY = ["claude", "codex", "deepseek"];

/* One turn, as submitTurn would run it: detect, then (if it switched) let the
   next socket carry the request. Returns the URL that socket would open. */
function turn(chatId, text) {
  const want = E2E.__E.detectProviderIntent(text, ALIASES_E2E, READY);
  if (want && want.ready) E2E.S.chatProvider[chatId] = want.target;
  const url = E2E.__E.claudeWsUrl(chatId);
  delete E2E.S.chatProvider[chatId];   /* claudeChannel spends it on creation */
  return url;
}

test("E2E: 'Using Codex, implement this' opens Chat A on codex, with its id", () => {
  const u = turn("A", "Using Codex, implement this");
  assert(u.includes("provider=codex"), "the chat did not switch: " + u);
  assert(u.includes("sutra=aaaa"),
         "without the chat id the server cannot replay the conversation: " + u);
});

test("E2E: the NEXT turn in Chat A names no provider", () => {
  // Sticky is the SERVER's job from here: provider_history holds codex, and
  // ws_chat resolves a socket with no ?provider= from it. Re-sending it would
  // put the client's idea of the chat ahead of the record.
  const u = turn("A", "and now add the tests");
  assert(!u.includes("provider="), "the request was re-sent: " + u);
  assert(u.includes("sutra=aaaa"));
});

test("E2E: Chat B is untouched by Chat A's switch", () => {
  const u = turn("B", "carry on");
  assert(!u.includes("provider="), "Chat A's switch leaked onto Chat B: " + u);
});

test("E2E: 'Use Claude for this' switches Chat A back", () => {
  const u = turn("A", "Use Claude for this");
  assert(u.includes("provider=claude"), "the chat did not switch back: " + u);
});

test("E2E: a bare mention in Chat A changes nothing", () => {
  const u = turn("A", "Codex would probably do this differently");
  assert(!u.includes("provider="), "a mention moved the chat: " + u);
});

test("E2E: a provider that is not ready never reaches the url", () => {
  const u = turn("A", "use Gemini");
  assert(!u.includes("provider="),
         "an unrunnable provider was proposed to the server: " + u);
});

/* ── 9. the REAL first-turn ordering, on a brand-new chat ─────────────────
   Section 8 above composes detect -> S.chatProvider -> claudeWsUrl by hand.
   That helper asserted the pieces agree; it could not have caught the bug the
   founder hit, because it never ran submitTurn and therefore never asked
   whether the request SURVIVES to the socket the real client opens.

   This drives the actual chain -- submitTurn -> applyProviderRequest ->
   askClaude -> claudeChannel -> claudeWsUrl -> new WebSocket(...) -- with a
   stub WebSocket that records the URL it was constructed with. That URL is the
   only thing the server ever sees, so it is the only honest assertion about
   whether a switch happened.

   THE BUG IT PINS: "Using Codex, what is 17 x 6?" is an INSTRUCTION whose
   payload is a question. detectProviderIntent rejected any message ending in
   "?" before it looked at a single frame, so nothing switched, the socket
   opened with no provider, the server fell back to Claude, and Claude answered
   102 while the pane truthfully badged itself Claude. Nothing downstream was
   wrong -- nothing had asked it to switch. */
async function firstTurn(text, opts) {
  const urls = [];
  const box = {
    location: { protocol: "http:", host: "127.0.0.1:7000" },
    S: { cwd: {}, sutraId: {}, sessions: [], chatProvider: {}, chatProviderNote: {},
         model: {}, turnOpts: {}, sideTurns: {} },
    SETTINGS: { provider: "claude", workdir: "" },
    SEED: { provider_aliases: { "codex": "codex", "claude": "claude" } },
    PROVIDERS: (opts && opts.providers) || [
      { id: "claude", name: "Claude Code", runnable: true },
      { id: "codex", name: "OpenAI Codex", runnable: true }],
    CLAUDE_SOCKETS: new Map(),
    console,
    /* the pieces submitTurn leans on that are not under test */
    render: () => {}, scheduleRender: () => {}, renderNow: () => {},
    groundingPrefix: () => "",
    providerLabel: (id) => id,
    paneProvider: (s) => (s && s.channel && s.channel.id) || box.SETTINGS.provider,
    streamingFor: () => false, sideStreamingFor: () => false,
    resumableId: () => null,
    sessCwd: () => "",
    WebSocket: function (url) { urls.push(url); this.readyState = 0;
                               this.send = () => {}; this.close = () => {}; },
  };
  box.WebSocket.CONNECTING = 0; box.WebSocket.OPEN = 1;
  /* runTask does a /api/classify round trip that has nothing to do with
     provider routing; the SESSION it returns is what matters here. */
  box.runTask = async (t, sid) => {
    let s = box.S.sessions.find(x => x.id === sid);
    if (!s) { s = { id: sid || "s1", turns: [], local: true }; box.S.sessions.push(s); }
    const result = { text: t, response: "", tools: [] };
    s.turns.push(result);
    return { session: s, result };
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grabVarLike(helpers, "PROVIDER_INTENT_PREFIX"),
    grabVarLike(helpers, "PROVIDER_INTENT_QUESTION"),
    grabVarLike(helpers, "PROVIDER_INTENT_NEGATION"),
    grab(helpers, "stripProviderNoise"),
    grab(helpers, "providerIntentFrames"),
    grab(helpers, "providerIntentOpensWithDirective"),
    grab(helpers, "detectProviderIntent"),
    grab(helpers, "switchChatProvider"),
    grab(helpers, "applyProviderRequest"),
    grab(helpers, "turnUid"),
    grab(helpers, "askClaude"),
    grab(helpers, "submitTurn"),
    grab(state, "chanKey"),
    grab(state, "sessSutraId"),
    grab(state, "sessProviderRequest"),
    grab(state, "claudeWsUrl"),
    grab(state, "claudeChannel"),
    grab(state, "closeClaudeChannel"),
    grab(state, "failChannel"),
    "let _UID = 0;",
  ].join("\n") + "\n;globalThis.__F=submitTurn;",
    { filename: "firstturn#extract" }).runInContext(box);
  await box.__F(text, "s1");
  return { urls, note: box.S.chatProviderNote.s1, box };
}

test("REAL PATH: a brand-new chat opens its socket on codex", async () => {
  // The founder's exact message. Before the fix this opened a socket with no
  // provider at all, so the server resolved Claude and answered it.
  const { urls } = await firstTurn("Using Codex, what is 17 × 6?");
  assert(urls.length === 1, "expected exactly one socket, got " + urls.length);
  assert(/[?&]provider=codex(&|$)/.test(urls[0]),
         "the socket opened WITHOUT provider=codex: " + urls[0]);
});

test("REAL PATH: the request survives to socket construction, not just to state", async () => {
  // claudeChannel deletes S.chatProvider the moment it builds the socket, and
  // applyProviderRequest force-closes the channel just before askClaude
  // reopens it. The ordering has to leave the request readable in between.
  const { urls, box } = await firstTurn("Using Codex, implement this");
  assert(/provider=codex/.test(urls[0]), "the request never reached the url");
  assert(box.S.chatProvider.s1 === undefined,
         "the one-shot was not spent, so it would re-send on every reconnect");
});

test("REAL PATH: an ordinary first turn opens with no provider", async () => {
  const { urls } = await firstTurn("what is 17 × 6?");
  assert(urls.length === 1, "expected one socket");
  assert(!/provider=/.test(urls[0]),
         "a message that asked for nothing named a provider: " + urls[0]);
});

test("REAL PATH: naming the provider already in use opens no second socket", async () => {
  const { urls } = await firstTurn("Using Claude, what is 17 × 6?");
  assert(urls.length === 1, "a redundant switch cold-started an extra socket");
  assert(!/provider=/.test(urls[0]), "a no-op switch still named a provider");
});

test("REAL PATH: the boot window sends nothing at all", async () => {
  // PROVIDERS empty = not fetched. The turn is held, so no socket is opened
  // and no verdict about Codex is asserted.
  const { urls, note } = await firstTurn("Using Codex, what is 17 × 6?",
                                         { providers: [] });
  assert(urls.length === 0, "a socket opened before readiness was known");
  assert(/still checking/i.test(note || ""), "no honest note: " + note);
  assert(!/not ready/i.test(note || ""), "asserted a verdict it cannot have");
});

/* ── 10. the rail re-supplies the chat id after a refresh ─────────────────
   S.sutraId is memory-only, so a reload empties it. Without it claudeWsUrl
   sends no ?sutra=, ws_chat's chat-local step returns on the empty parameter,
   and a chat switched to Codex reconnects on the GLOBAL default -- then the
   seed recovery finds it too late and replays Codex -> Claude. Measured live:
   "OpenAI Codex -> Claude Code, turns 1-2 carried over". */

test("adoptRealSessions stores the chat id every row now carries", () => {
  const body = grab(state, "adoptRealSessions");
  assert(/S\.sutraId\[r\.id\] = r\.sutra_id/.test(body),
         "the rail never stores the chat id, so ?sutra= stays absent");
  assert(/r && r\.id && r\.sutra_id/.test(body),
         "a null sutra_id must not overwrite an id a live socket already "
         + "learned from its own chat frame");
  assert(body.indexOf("S.sutraId[r.id]") < body.indexOf("const real ="),
         "the mapping must be written for EVERY row, before the map -- the "
         + "three branches there return in-flight, on-screen and fresh "
         + "sessions, and it is true of all of them");
});

test("the stored id is what claudeWsUrl then sends", () => {
  const box = {
    location: { protocol: "http:", host: "127.0.0.1:7000" },
    S: { cwd: {}, sutraId: {}, chatProvider: {} },
    SETTINGS: { workdir: "" },
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grab(state, "sessCwd"),
    grab(state, "sessSutraId"),
    grab(state, "sessProviderRequest"),
    grab(state, "claudeWsUrl"),
  ].join("\n") + "\n;globalThis.__W=claudeWsUrl;",
    { filename: "wsurl#extract" }).runInContext(box);

  const SID = "01a08572-164d-75d0";
  const CHAT = "aaaabbbbccccddddeeeeffff00001111";
  box.S.sutraId[SID] = CHAT;              // exactly what adoptRealSessions writes
  const u = box.__W(SID);
  assert(u.indexOf("sutra=" + CHAT) !== -1,
         "the recovered chat id never reaches the socket: " + u);
  assert(u.indexOf("provider=") === -1,
         "a reconnect must not name a provider; the server resolves it from "
         + "the chat's own record: " + u);
});

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
