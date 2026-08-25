#!/usr/bin/env node
/*
 * test_update_attach.js -- the attach-mode update surface's contracts.
 *
 * Source-level assertions (the test_update_banner.js pattern): they fail on
 * the change that lets an old-DMG + new-plugin combination lie, drops the
 * feature detection, re-gates updating on backend ownership, or lets the
 * quit path hang on an unbounded verb.
 *
 * Run: node test_update_attach.js
 */
const fs = require("fs");
const path = require("path");
const rd = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");
const chat = rd("static/js/05-chat.js");
const rend = rd("static/js/06-render.js");
const load = rd("static/js/07-loaders.js");
const main = rd("electron/main.js");
const pre = rd("electron/preload.js");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

test("preload exposes updateState and the staged push", () => {
  assert(pre.includes('updateState: () => ipcRenderer.invoke("sutra:update-state")'), "no updateState verb");
  assert(pre.includes('"sutra:update-staged"'), "no staged push channel");
});

test("every renderer call is feature-detected", () => {
  const sites = (chat + rend).split('window.sutra.updateState()').length - 1;
  const guards = (chat + rend).split('typeof window.sutra.updateState === "function"').length - 1;
  assert(sites >= 2, "expected updateState call sites, found " + sites);
  assert(guards >= 2, "call sites are not guarded by typeof checks (" + guards + ")");
});

test("shell state failure renders as incapable, never optimistic", () => {
  assert(/catch \(e\) \{ S\.shellUpd = null; \}/.test(chat), "checkUpdates does not null shellUpd on failure");
});

test("the banner reads the SHELL in attach mode, backend otherwise", () => {
  const i = rend.indexOf("async function pollStagedUpdate");
  const body = rend.slice(i, rend.indexOf("\n}", i));
  assert(body.indexOf("updateState") < body.indexOf('apiGet("/api/updates/staged")'),
         "shell branch does not precede the HTTP fallback");
  assert(body.includes("s.attach"), "shell answer not keyed on attach");
});

test("clicks route shell verbs to shell handlers", () => {
  assert(load.includes('what === "shell-stage"') && load.includes('what === "shell-apply"'),
         "shell click routes missing");
  assert(chat.includes("async function shellStage") && chat.includes("async function shellApply"),
         "shell handlers missing");
});

test("main.js gates updating on capability, not backend ownership", () => {
  assert(main.includes("function updateCapable()"), "no updateCapable()");
  assert(main.includes('RUNTIME.kind === "bundled"'), "bundled detection missing");
  ["async function checkForUpdate", "async function resolvePendingUpdate"].forEach(fn => {
    const i = main.indexOf(fn);
    const head = main.slice(i, i + 300);
    assert(head.includes("updateCapable()"), fn + " still gated on desktopControl");
  });
});

test("the sidecar spawn recipe holds its invariants", () => {
  const i = main.indexOf("function updateCli");
  const body = main.slice(i, main.indexOf("\n}", i + 500));
  assert(body.includes('"-m", "updates_cli"'), "not spawned as -m updates_cli");
  assert(body.includes("cwd: RUNTIME.appDir"), "cwd is not the payload dir");
  assert(body.includes("PYTHONDONTWRITEBYTECODE"), "read-only bundle would take .pyc writes");
  assert(body.includes("...process.env"), "env replaced instead of inherited+overlaid");
});

test("the quit path is bounded on BOTH verbs", () => {
  const i = main.indexOf("async function applyOnQuit");
  const body = main.slice(i, main.indexOf("\n}", i));
  assert(/updateOp\("staged", null, 3000\)/.test(body), "staged read unbounded");
  assert(/armUpdate\(false, 8000\)/.test(body), "quit-path arm unbounded");
});

test("attach boot path resolves pending updates before the window", () => {
  const i = main.indexOf("if (await isSutra())");
  const body = main.slice(i, i + 700);
  assert(body.indexOf("resolvePendingUpdate()") < body.indexOf("createWindow()"),
         "attach boot does not resolve before createWindow");
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
