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
  grab(state, "sessCwd"),
  grab(state, "sessSutraId"),
  grab(state, "claudeWsUrl"),
].join("\n") + "\n;globalThis.__T={sessSutraId,claudeWsUrl};",
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
  const i = loaders.indexOf('apiPost("/api/providers/active"');
  const body = loaders.slice(i, i + 2000);
  assert(/streamingFor\(/.test(body) && /sideStreamingFor\(/.test(body),
         "closing a streaming pane would discard a reply being written");
});

test("the confirmation says when the change takes effect", () => {
  const i = loaders.indexOf('apiPost("/api/providers/active"');
  const body = loaders.slice(i, i + 2000);
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
  assert(/new chats start on/.test(chat));
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

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
