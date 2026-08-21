#!/usr/bin/env node
/*
 * test_connectors_ui.js -- wiring tests for the Connectors screen.
 *
 * WHY THIS EXISTS
 * ---------------
 * 2.112.3 shipped a Connectors screen that rendered perfectly and where no
 * button did anything. The handlers had been added inside the `.rail` click
 * listener, which only ever sees clicks inside `.rail`; every control on the
 * screen lives in `#scBody`. Rendering and event handling are separate paths
 * and only one of them was wrong, so the screen LOOKED right in a screenshot.
 *
 * test_panel.js could not catch it: it extracts the inline <script> from
 * panel.html, and this screen lives in static/js/12-connectors.js. 152 tests
 * passed while every button was dead.
 *
 * The load-bearing test here is the last one: every data-conn* attribute the
 * markup emits must have a handler that reads it. That generalises past this
 * one bug to "a control was rendered and nothing listens for it".
 *
 * Run: node test_connectors_ui.js
 */
const fs = require("fs");
const path = require("path");

const JS = p => fs.readFileSync(path.join(__dirname, "static/js", p), "utf8");
const loaders = JS("07-loaders.js");
const screen = JS("12-connectors.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static/panel.html"), "utf8");

let pass = 0, fail = 0;
function test(name, fn){
  try { fn(); console.log("ok   - " + name); pass++; }
  catch (e){ console.log("FAIL - " + name + "\n       " + e.message); fail++; }
}
function assert(cond, msg){ if (!cond) throw new Error(msg); }

/* Slice out the body of the `.rail` click listener so we can assert on it. */
function railListenerBody(src){
  const start = src.indexOf('document.querySelector(".rail").addEventListener("click"');
  assert(start !== -1, "rail click listener not found");
  const next = src.indexOf('document.addEventListener("click"', start);
  return src.slice(start, next === -1 ? src.length : next);
}

test("the screen is loaded by panel.html", () => {
  assert(/12-connectors\.js/.test(panelHtml), "12-connectors.js is not in panel.html");
});

test("12-connectors.js loads before 09-tail.js", () => {
  /* Match the SCRIPT TAGS, not the prose: panel.html explains this very
     ordering in a comment above them, and a plain indexOf finds the comment. */
  const tag = f => panelHtml.indexOf('<script src="/static/js/' + f);
  assert(tag("12-connectors.js") !== -1, "no script tag for 12-connectors.js");
  assert(tag("12-connectors.js") < tag("09-tail.js"),
    "load order would leave the screen undefined at boot (09-tail ends with boot())");
});

test("no connector handler sits in the rail listener", () => {
  /* The exact 2.112.3 bug. The rail listener cannot see #scBody clicks. */
  const body = railListenerBody(loaders);
  assert(!/data-conn/.test(body),
    "a connector handler is inside the .rail listener, where it can never fire");
});

test("the screen registers its own document-level click delegate", () => {
  assert(/document\.addEventListener\(\s*["']click["']/.test(screen),
    "12-connectors.js registers no click listener");
});

test("the delegate scopes itself to #scBody", () => {
  assert(/closest\(["']#scBody["']\)/.test(screen),
    "delegate is unscoped; a stray data-conn attribute anywhere would trigger it");
});

test("the delegate is not attached to a re-rendered element", () => {
  /* #scBody is rebuilt by render() every pass, so a listener bound to it would
     be discarded with the element. */
  assert(!/getElementById\(["']scBody["']\)\.addEventListener/.test(screen),
    "listener bound to #scBody would not survive a re-render");
});

test("every data-conn* control the markup emits has a handler", () => {
  /* The general form of the bug: a button rendered with nothing listening. */
  const emitted = new Set();
  for (const m of screen.matchAll(/\sdata-(conn[a-z]*)(?=[\s=>])/g)) emitted.add(m[1]);
  assert(emitted.size >= 5, "expected several data-conn* controls, found " + emitted.size);

  const handled = new Set();
  for (const m of screen.matchAll(/closest\(["']\[data-(conn[a-z]*)\]["']\)/g)) handled.add(m[1]);

  const orphans = [...emitted].filter(a => !handled.has(a));
  assert(orphans.length === 0,
    "controls rendered with no handler: " + orphans.map(o => "data-" + o).join(", "));
});

test("every handler corresponds to a control that exists", () => {
  const emitted = new Set();
  for (const m of screen.matchAll(/\sdata-(conn[a-z]*)(?=[\s=>])/g)) emitted.add(m[1]);
  const handled = new Set();
  for (const m of screen.matchAll(/closest\(["']\[data-(conn[a-z]*)\]["']\)/g)) handled.add(m[1]);
  const dead = [...handled].filter(a => !emitted.has(a));
  assert(dead.length === 0, "handlers for controls nothing renders: " + dead.join(", "));
});

test("the lazy loader fires when the screen opens", () => {
  assert(/S\.screen\s*===\s*["']connectors["']\)\s*loadConnectors/.test(loaders),
    "opening the screen does not trigger loadConnectors");
});

test("the rail has a connectors entry", () => {
  const helpers = JS("02-helpers.js");
  assert(/id:\s*["']connectors["']/.test(helpers), "no rail entry for connectors");
});

console.log("\n" + "-".repeat(60));
console.log(`connectors UI wiring: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
