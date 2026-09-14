#!/usr/bin/env node
/*
 * test_update_banner.js -- the update banner's dismissal contract.
 *
 * WHY THIS EXISTS
 * ---------------
 * "Not now" used to set S.updDeferred and re-render into a branch with NO
 * buttons. The countdown became a permanent, unclosable notice: an operator
 * who explicitly postponed an update was answered with a banner that stayed on
 * screen until the app quit. That is a nag, not a defer.
 *
 * test_panel.js cannot cover this -- it extracts the inline <script> from
 * panel.html, and the banner lives in static/js/06-render.js.
 *
 * These are source-level assertions. Cruder than driving a DOM, but they fail
 * on the next change that reintroduces an undismissable state, which is the
 * property worth protecting.
 *
 * Run: node test_update_banner.js
 */
const fs = require("fs");
const path = require("path");
const render = fs.readFileSync(path.join(__dirname, "static/js/06-render.js"), "utf8");
const state = fs.readFileSync(path.join(__dirname, "static/js/02-helpers.js"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

test("updDismissed exists in state", () => {
  assert(/updDismissed\s*:/.test(state), "S.updDismissed is not declared");
});

test("dismissal is keyed to a version, not a boolean", () => {
  /* A boolean would silence the NEXT release too. */
  assert(/S\.updDismissed\s*=\s*\(S\.updStaged/.test(render),
    "Not now must record which version was dismissed, not just that one was");
  assert(!/S\.updDismissed\s*=\s*true/.test(render),
    "a boolean dismissal would also silence a genuinely newer build");
});

test("the show gate consults the dismissal", () => {
  assert(/const\s+show\s*=[^;]*!dismissed/.test(render),
    "the banner's show gate ignores the dismissal, so Not now cannot hide it");
});

test("Not now dismisses as well as defers", () => {
  const handler = render.slice(render.indexOf('data-upd2'));
  assert(/S\.updDeferred\s*=\s*true/.test(handler), "defer flag not set");
  assert(/S\.updDismissed\s*=/.test(handler), "Not now does not dismiss the banner");
});

test("an error is never silenced by a dismissal", () => {
  const gate = render.slice(render.indexOf("const dismissed"), render.indexOf("const show"));
  assert(/!S\.updApplyError/.test(gate),
    "a failed install would be hidden by an earlier Not now");
});

test("an in-flight install is never silenced", () => {
  const gate = render.slice(render.indexOf("const dismissed"), render.indexOf("const show"));
  assert(/!==\s*["']installing["']/.test(gate),
    "an armed install would be hidden by an earlier Not now");
});

test("no banner branch renders without a way out", () => {
  /* Every branch must either offer an action or be transient. The deferred
     branch is allowed to have no buttons ONLY because it is now unreachable
     while dismissed -- and this asserts the gate that makes that true. */
  assert(/dismissed\s*=\s*!!\(u && u\.version && S\.updDismissed === u\.version/.test(render),
    "the dismissal gate is not keyed on the staged version");
});

/* Behavioural, not textual: run the real applyUpdateNow against a stub shell.
   The banner once said "Sutra 2.271.4 could not be applied. the update state
   is in use by another process" -- a busy lock presented as a failed install. */
function loadApply(answers) {
  const vm = require("vm");
  const start = render.indexOf("const UPD_BUSY_RETRY_S");
  const fnAt = render.indexOf("async function applyUpdateNow");
  const src = render.slice(start, render.indexOf("\n}\n", fnAt) + 2);
  const timers = [];
  const ctx = {
    S: { updFiring: false, updApplyError: null },
    renders: 0,
    window: { sutra: { applyUpdate: async () => answers.shift() } },
    stopUpdCountdown: () => {},
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); },
  };
  ctx.renderUpdateBanner = () => { ctx.renders++; };
  vm.createContext(ctx);
  vm.runInContext(src + "\nthis.applyUpdateNow = applyUpdateNow;", ctx);
  return { ctx, timers };
}

const pending = [];
const asyncTest = (n, f) => pending.push(f().then(
  () => { console.log("ok   - " + n); pass++; },
  (e) => { console.log("FAIL - " + n + "\n       " + e.message); fail++; }));

const BUSY = { ok: false, busy: true,
  error: "the update state is in use by another process (a stage or install is in progress)" };

asyncTest("a busy refusal retries quietly instead of showing 'could not be applied'", async () => {
  const { ctx, timers } = loadApply([BUSY, { ok: true }]);
  await ctx.applyUpdateNow();
  assert(ctx.S.updApplyError === null, "busy was reported as a failure: " + ctx.S.updApplyError);
  assert(ctx.S.updFiring === true, "banner left the restarting state, so the countdown could double-fire");
  assert(timers.length === 1 && timers[0].ms >= 1000, "no delayed retry was scheduled");
  await timers[0].fn();
  assert(ctx.S.updApplyError === null && timers.length === 1, "success after a busy retry misbehaved");
});

asyncTest("a lock that never frees still surfaces, after a bounded number of retries", async () => {
  const answers = Array.from({ length: 20 }, () => BUSY);
  const { ctx, timers } = loadApply(answers);
  await ctx.applyUpdateNow();
  for (let i = 0; i < 10 && ctx.S.updApplyError === null; i++) {
    assert(timers.length === i + 1, "retry " + i + " not scheduled");
    await timers[i].fn();
  }
  assert(ctx.S.updApplyError && /in use by another process/.test(ctx.S.updApplyError),
         "a permanently busy lock was retried forever and never shown");
  assert(timers.length <= 5, "too many quiet retries: " + timers.length);
  assert(ctx.S.updFiring === false, "the error state must allow Try again");
});

asyncTest("a genuine failure is shown immediately, not retried", async () => {
  const { ctx, timers } = loadApply([{ ok: false, error: "checksum mismatch" }]);
  await ctx.applyUpdateNow();
  assert(ctx.S.updApplyError === "checksum mismatch", "genuine failure hidden");
  assert(timers.length === 0, "a genuine failure was retried");
});

Promise.all(pending).then(() => {
console.log("\n" + "-".repeat(60));
console.log(`update banner: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
});
