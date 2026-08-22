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

console.log("\n" + "-".repeat(60));
console.log(`update banner: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
