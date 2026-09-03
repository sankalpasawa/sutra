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
  S: { cwd: {}, sutraId: {}, sessions: [] },
  SETTINGS: { workdir: "/home/op/work" },
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
new vm.Script([
  grab(helpers, "providerUsage"),
  grab(state, "sessCwd"),
  grab(state, "sessSutraId"),
  grab(state, "claudeWsUrl"),
].join("\n") + "\n;globalThis.__T={sessSutraId,claudeWsUrl,providerUsage};",
  { filename: "01-state.js#extract" }).runInContext(sandbox);
const T = sandbox.__T;

test("the client never sends a provider on the socket url", () => {
  // Provider is the server's own resolution now; a param from here could only
  // ever disagree with it.
  sandbox.S.cwd = { s1: "/home/op/x" }; sandbox.S.sutraId = { s1: "abc" };
  assert(!T.claudeWsUrl("s1").includes("provider="),
         "provider is chosen in Settings; the client must not send one");
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
  assert(/usable\.length < 2/.test(SW) && /return ""/.test(SW),
         "naming the only possible answer is noise on every turn");
});

test("nothing renders before anything has spawned", () => {
  assert(/if \(!running\) return ""/.test(SW),
         "with no provider frame there is no honest answer to give");
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

test("no per-session provider state remains", () => {
  ["provider:{}", "providerError:null"].forEach(f =>
    assert(!helpers.replace(/\s/g, "").includes(f.replace(/\s/g, "")),
           "S still carries " + f + " with no control to set it"));
  assert(!/function setSessProvider\(/.test(state),
         "the per-session setter must be gone, not merely unreferenced");
});

test("changing the Settings provider drops the open chat sockets", () => {
  // Otherwise the next prompt rides an existing socket to the OLD provider
  // while the UI claims the new one.
  const i = loaders.indexOf('apiPost("/api/providers/active"');
  assert(i > 0, "the Settings provider handler is gone");
  const body = loaders.slice(i, i + 2000);
  assert(body.includes("CLAUDE_SOCKETS.delete"), "sockets are not dropped");
  assert(body.includes("ws.close"), "sockets are not closed");
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

/* ── 6. the Assistant row (founder 2026-09-03) ─────────────────────────────── */

test("the nested row is called AI Assistant, not Settings", () => {
  // "Settings" inside the Settings destination repeated its parent and said
  // nothing about what was behind it.
  assert(helpers.includes('n:"AI Assistant"'), "railSpec does not label the row AI Assistant");
  assert(chat.includes('settings:["AI Assistant"'), "TITLES does not say AI Assistant");
  // The provider is ONE of this screen's three folds (provider, permission
  // mode, workdir), which is why it is not named for the provider alone.
  assert(!/n:"AI [Pp]rovider"/.test(helpers), "named for one of its three folds");
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

test("a provider that cannot run still says WHY", () => {
  // providers.py exists so the panel never says "unavailable" without saying
  // why. Plain language must not cost that: the status line leads, the exact
  // server reason stays underneath.
  assert(/Not installed on this Mac/.test(chat), "no plain status for not-installed");
  assert(/not signed in yet/.test(chat), "no plain status for installed-but-unconfigured");
  assert(/p\.reason\?/.test(chat.replace(/\s/g, "")),
         "the server's exact reason was dropped along with the jargon");
});

test("a refused saved choice is explained, not labelled", () => {
  assert(/could not be used/.test(chat), "the ignored-override notice is gone");
  assert(!/An override was NOT honoured/.test(chat), "still says 'override not honoured'");
});

test("Usage renders inside the AI Assistant screen, not as its own row", () => {
  // How much of an assistant you have used is a fact about the assistant you
  // just picked; a separate destination made you cross the app to answer a
  // question this screen had raised.
  assert(chat.includes("SCREENS.usage()"),
         "the AI Assistant screen does not render the usage section");
  const plane = state.slice(state.indexOf('settings: [{group:"Tools"'));
  const body = plane.slice(0, plane.indexOf("\n};"));
  assert(!/screen:"usage"/.test(body), "usage still has a nav row");
});

test("the usage figure moved onto the row you can actually click", () => {
  const i = helpers.indexOf('{id:"settings",n:"AI Assistant"');
  assert(i > 0, "the AI Assistant entry is gone");
  assert(/providerUsage\(\)/.test(helpers.slice(i, i + 260)),
         "the AI Assistant row carries no usage count");
  const j = helpers.indexOf('{id:"usage"');
  assert(!/providerUsage\(\)/.test(helpers.slice(j, j + 160)),
         "the row-less usage entry still computes a badge nobody sees");
});

test("opening the AI Assistant screen fetches usage", () => {
  // Otherwise the section sits on "Reading usage..." until something else
  // happens to load it.
  // Match the screen-open dispatcher specifically -- loadUsage is also called
  // from the composer popover and the sign-in flow, and indexOf found those.
  assert(/id === "usage" \|\| id === "settings"/.test(loaders),
         "the AI Assistant screen does not trigger a usage load on open");
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

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
