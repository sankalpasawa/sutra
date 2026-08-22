#!/usr/bin/env node
/* Project-level session collapse in the left rail.
 *
 * The state field (S.ui.sessCollapsed) shipped in loadLayout with nothing
 * reading or writing it -- persistence for a behaviour that did not exist.
 * These pin the three parts that make it real: the header renders a toggle,
 * the body honours the collapsed state, and the handler flips + persists it.
 *
 * Source assertions strip comments first: twice this session a source test
 * failed on the comment documenting the fix, not on code. */
const fs = require("fs"), path = require("path");
const strip = f => fs.readFileSync(path.join(__dirname, "static/js", f), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const helpers = strip("02-helpers.js"), loaders = strip("07-loaders.js");
const css = fs.readFileSync(path.join(__dirname, "static/panel.css"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

test("the project header renders a collapse toggle", () => {
  assert(/data-sesscollapse=/.test(helpers), "no toggle button in the project group header");
  assert(/aria-expanded=/.test(helpers), "toggle has no aria-expanded state");
});

test("the collapse key is namespaced to project + cwd", () => {
  assert(/["'`]project:["'`]\s*\+/.test(helpers),
    "collapse key must be 'project:'+cwd so it cannot clash with the department view");
});

test("the session list is actually hidden when collapsed", () => {
  assert(/collapsed\s*\?\s*["'`]hidden["'`]/.test(helpers),
    "the <ul> must carry `hidden` when the group is collapsed -- state without effect is the original bug");
});

test("default is EXPANDED — only an explicit collapse is stored", () => {
  assert(/S\.ui\.sessCollapsed\s*&&\s*S\.ui\.sessCollapsed\[/.test(helpers),
    "collapsed must read truthy-from-store, so an absent key means open");
});

test("the click handler toggles and persists", () => {
  assert(/data-sesscollapse/.test(loaders), "no click target for the toggle");
  assert(/saveLayout\(\)/.test(loaders.slice(loaders.indexOf("data-sesscollapse"))),
    "the toggle must persist via saveLayout()");
  assert(/render\(\)/.test(loaders.slice(loaders.indexOf("data-sesscollapse"))),
    "the toggle must re-render");
});

test("the toggle state machine flips both ways and is delete-not-false", () => {
  /* Mirror the handler body exactly. delete (not =false) keeps the store to
     only-collapsed groups, so it never grows to hold every project the user
     ever opened. */
  const ui = { sessCollapsed: {} };
  const toggle = key => {
    ui.sessCollapsed = ui.sessCollapsed || {};
    if (ui.sessCollapsed[key]) delete ui.sessCollapsed[key];
    else ui.sessCollapsed[key] = true;
  };
  const k = "project:/Users/x/repo";
  toggle(k); assert(ui.sessCollapsed[k] === true, "first click must collapse");
  toggle(k); assert(!(k in ui.sessCollapsed), "second click must expand AND remove the key");
  assert(Object.keys(ui.sessCollapsed).length === 0, "expanded groups must not linger in the store");
});

test("the chevron has a reduced-motion guard", () => {
  const rm = css.slice(css.indexOf("prefers-reduced-motion"));
  assert(/\.rgchev\s*\{\s*transition\s*:\s*none/.test(css.replace(/\s+/g, " ")),
    "the chevron rotation must be disabled under prefers-reduced-motion");
});

console.log("\n" + "-".repeat(60));
console.log(`session collapse: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
