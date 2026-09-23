/* The Library's renderer: does the screen draw what the payload says, and
   nothing it decided for itself? (holding/plans/library-program/TEST-PLAN.md,
   renderer lane)

   Run: node test_library.js

   The panel's scripts are plain browser files, so this loads the three that
   matter into a vm with a small document stub, exactly as test_dept.js does,
   and calls the renderer with fixtures. No app, no network. */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const DIR = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(DIR, f), "utf8");

let FAIL = [], N = 0;
function check(name, cond, detail){
  N++;
  if (!cond) FAIL.push(name + (detail ? " -- " + detail : ""));
}

/* ── a document stub: enough for registration and the click listener ── */
const listeners = [];
const sandbox = {
  console,
  document: {
    addEventListener: (t, fn) => listeners.push([t, fn]),
    getElementById: () => null,
    querySelector: () => null,
    documentElement: { style: {}, classList: { add(){}, remove(){} } },
  },
  window: {},
  SCREENS: {}, TITLES: {},
  S: { ui: {} },
  esc: x => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
  render: () => {},
  fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
  module: { exports: {} },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(read("21-library.js"), sandbox, { filename: "21-library.js" });

/* top-level const in a vm script stays in the script's own scope, so the
   renderer's functions come from what it exports; SCREENS and TITLES are
   properties of the sandbox because the script assigns into them. */
const L = Object.assign({}, sandbox.module.exports,
                        { SCREENS: sandbox.SCREENS, TITLES: sandbox.TITLES });

/* ── 1. registration ───────────────────────────────────────────────────── */
check("seven shelves are named", L.LIB_SHELVES.length === 7, String(L.LIB_SHELVES.length));
for (const sh of L.LIB_SHELVES){
  check("screen registered: " + sh, typeof L.SCREENS["lib-" + sh] === "function");
  check("title registered: " + sh, Array.isArray(L.TITLES["lib-" + sh]));
  check("title reads Library: " + sh, L.TITLES["lib-" + sh][0] === "Library");
}
check("a click listener is mounted", listeners.length === 1 && listeners[0][0] === "click");
check("screen id maps to shelf", L.libShelfOf("lib-engines") === "engines");
check("shelf maps to screen id", L.libScreenOf("engines") === "lib-engines");
check("a foreign screen maps to nothing", L.libShelfOf("departments") === "");

/* ── 2. the head and its tabs ──────────────────────────────────────────── */
const HEAD = { id: "identity", name: "Identity", kind: "Function",
               line: "What a department is for.", count_line: "3 ready-made",
               tabs: ["About", "Templates"] };
let html = L.libHeadHtml(HEAD, "identity");
check("head draws the name", html.includes("Identity"));
check("head draws the kind as the app's tag", html.includes('class="dptag"'));
check("head draws the app's tab control", html.includes('class="tabs dptabs"'));
check("both tab names are drawn", html.includes(">About<") && html.includes(">Templates<"));
check("About is pressed first", /data-libtab="about"[^>]*aria-pressed="true"/.test(html));
check("the list tab is not pressed", /data-libtab="list"[^>]*aria-pressed="false"/.test(html));
check("the count line is drawn", html.includes("3 ready-made"));
check("no control is invented", !/class="lbtab(?!row|count)/.test(html));

L.LIB_STATE.tab["identity"] = "list";
html = L.libHeadHtml(HEAD, "identity");
check("switching the tab moves the pressed state",
      /data-libtab="list"[^>]*aria-pressed="true"/.test(html));
L.LIB_STATE.tab["identity"] = "about";

/* ── 3. the About pane ─────────────────────────────────────────────────── */
const ABOUT = {
  ways: [{ name: "From a ready-made one", does: "Pick one.", lands: "Lands as an ask." },
         { name: "In the chat", does: "Say what it is for.", lands: "Lands as an ask." }],
  settings: [{ name: "Starts on", decides: "Which one a new department runs on", now: "Default" }],
  parts: [{ name: "Floor", caption: "always", says: "What it must always do.",
            example: "Judges every effect against the rules." }],
  note: "A department writes its own child.",
};
html = L.libAboutHtml(ABOUT);
check("the ways are drawn", html.includes("From a ready-made one") && html.includes("In the chat"));
check("each way says what lands", (html.match(/lbthen/g) || []).length === 2);
check("the settings table is drawn", html.includes("Starts on") && html.includes("Default"));
check("the parts are drawn with their caption", html.includes("Floor") && html.includes("always"));
check("a part's example is quoted", html.includes("Judges every effect"));
check("the note is drawn", html.includes("writes its own child"));
check("an empty About draws nothing", L.libAboutHtml(null) === "");

/* ── 4. the list pane, its tags and its filter ─────────────────────────── */
const LIST = {
  tag_label: "Fits",
  tags: ["any department", "money", "product"],
  rows: [
    { id: "identity/default", name: "Default", sub: "identity/default",
      use: "Any department.", tags: ["any department", "base"], right: "5 always",
      state: "ready", action: "Use" },
    { id: "identity/money-movement", name: "Money movement", sub: "identity/money-movement",
      use: "A department that moves money.", tags: ["money", "from default"],
      right: "7 always", state: "in-use", action: "In Paisa" },
    { id: "identity/not-built", name: "Not built", sub: "", use: "Named, not built.",
      tags: ["product"], right: "to build", state: "to-build", action: "Use" },
  ],
  note: "A child may add a line. It may not drop one.",
};
html = L.libListHtml(LIST, "identity");
check("the filter label is drawn", html.includes("Fits"));
check("every tag becomes a chip", LIST.tags.every(t => html.includes(">" + t + "<")));
check("the all chip counts the rows", html.includes("All 3"));
check("a row per payload row", (html.match(/class="lbrow/g) || []).length === 3);
check("a row draws its own tags", html.includes(">money<") && html.includes(">base<"));
check("a row draws its right column", html.includes("5 always"));
check("the in-use action is the app's stamped button", html.includes("btn dpstamp"));
check("a to-build row is dimmed and dead",
      html.includes("lbrow tobuild") && html.includes("disabled"));
check("the note is drawn", html.includes("may not drop one"));

L.LIB_STATE.tag["identity"] = "money";
check("a tag narrows the rows", L.libRowsOf(LIST, "identity").length === 1);
html = L.libListHtml(LIST, "identity");
check("the picked chip is marked", /class="dptag on"[^>]*data-libtag="money"/.test(html));
check("only the matching row is drawn", (html.match(/class="lbrow/g) || []).length === 1);
L.LIB_STATE.tag["identity"] = "nothing-has-this";
check("a tag nothing carries says so",
      L.libListHtml(LIST, "identity").includes("No row carries that tag"));
L.LIB_STATE.tag["identity"] = "";
check("clearing the tag restores every row", L.libRowsOf(LIST, "identity").length === 3);

const EMPTY = { tag_label: "Fits", tags: [], rows: [] };
check("an empty shelf says so", L.libListHtml(EMPTY, "engines").includes("Nothing on this shelf yet"));
check("an empty shelf draws no row list", !L.libListHtml(EMPTY, "engines").includes("lbmade"));

/* ── 5. the opened row ─────────────────────────────────────────────────── */
L.LIB_STATE.open["identity"] = { id: "identity/money-movement", loading: false,
  parent: "identity/default", keeps: ["a", "b"], adds: ["every money effect is an ask"],
  where: ["Paisa"] };
html = L.libListHtml(LIST, "identity");
check("the open block is drawn", html.includes("lbopen"));
check("it says what the child adds", html.includes("every money effect is an ask"));
check("it counts what the child keeps", html.includes("The 2 it keeps"));
check("it says where it is in use", html.includes("Paisa"));
check("the open row is marked", html.includes("lbrow on"));
L.LIB_STATE.open["identity"] = null;

/* ── 6. the whole screen, and its states ───────────────────────────────── */
L.LIB_STATE.shelf["identity"] = { head: HEAD, about: ABOUT, list: LIST };
html = L.libScreenHtml("identity");
check("the screen draws the page", html.includes("lbpage"));
check("About is the open pane", html.includes("How one is made"));
check("the list is not drawn while About is open", !html.includes("lbmade"));
L.LIB_STATE.tab["identity"] = "list";
html = L.libScreenHtml("identity");
check("the list pane draws on the second tab", html.includes("lbmade"));
check("About is not drawn while the list is open", !html.includes("How one is made"));

L.LIB_STATE.err["engines"] = "the registry is unreadable";
html = L.libScreenHtml("engines");
check("a shelf that cannot read says so", html.includes("cannot read its record"));
check("and names the reason", html.includes("registry is unreadable"));
L.LIB_STATE.err["engines"] = "";

delete L.LIB_STATE.shelf["audit"];
L.LIB_STATE.busy["audit"] = true;
check("a shelf still reading says so", L.libScreenHtml("audit").includes("Reading the shelf"));

/* ── 7. escaping ───────────────────────────────────────────────────────── */
const NASTY = { tag_label: "Fits", tags: ['<img src=x>'], rows: [
  { id: "x", name: '<script>bad()</script>', sub: "", use: '"quoted"', tags: ['<b>'],
    right: "", state: "ready", action: "Use" }] };
html = L.libListHtml(NASTY, "identity");
check("a name is escaped", !html.includes("<script>bad"));
check("a tag is escaped", !html.includes("<img src=x>"));
check("a quote is escaped", html.includes("&quot;quoted&quot;"));

console.log(N + " checks, " + FAIL.length + " failed");
FAIL.forEach(f => console.log("  FAIL " + f));
process.exit(FAIL.length ? 1 : 0);
