// Driver for test_functions_view.py (PRD M1.7, round 2 gap 1; round 3): renders a real department's function panes, each
// on its three tabs (its page, Chat and Settings), its Map, All five, its own chat and the list from the reads the server
// really gave, and prints what a person sees on each, as one JSON object.
//
// The reads come in as a JSON file: {"name": the department's name, "reads": {tail: body}, "dept": {tail: body}}, where a
// tail is what follows /api/native/<ref>/ ("map", "functions", "functions/identity", "steps/Identity", "board",
// "chat", "chat?fn=identity", "engine/Identity", ...) or, under "dept", what follows /api/dept/<ref>/ (the registry's
// reads the older cards drew from: "identity", "adaptation", "priority", "functions", "engines", ...). The panel's own
// scripts (03-org.js's rail helpers, 19-org2.js, 20-dept.js, 22-website.js, 23-screens.js, 24-functions.js) run in a vm
// with the same small stand-ins test_website.js uses, and each pane is painted until its reads have landed. The printed
// text is the visible text at rest (tags dropped) and, apart, the hovers (title and aria-label), so the Python side can
// scan both. Usage: node pane_words.js <reads.json>
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.resolve(__dirname, "..", "..", "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
const orgSrc = read("03-org.js");
const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const reads = input.reads || {}, dept = input.dept || {};

const TREE = [
  { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1, node_kind: "root" },
  { ref: "r1", path: "D1", name: "The organisation", parent_ref: "r0", status: "active", ts_minted_ms: 2, node_kind: "organisation" },
  { ref: "r2", path: "D1.D1", name: "Root", parent_ref: "r1", status: "active", ts_minted_ms: 3, node_kind: "department" },
  { ref: "r3", path: "D1.D1.D1", name: input.name || "The department", parent_ref: "r2", status: "active", ts_minted_ms: 4, node_kind: "department" }];
const WEB = TREE[3];
const sleep = () => new Promise(r => setTimeout(r, 0));
const copy = x => JSON.parse(JSON.stringify(x));

const ctx = {
  console, Date, Number, String, Array, Set, Map, JSON, Math, encodeURIComponent, Promise, setTimeout, clearTimeout, isNaN,
  setInterval: () => 1, clearInterval: () => {},
  apiGet: (p) => {
    if (p === "/api/native/depts") return Promise.resolve({ depts: [{ ref: "r3", name: WEB.name, stopped: false, kind: (reads.map || {}).kind }] });
    /* the department is r3 on this tree; the reads name it by its own ref (the map's ref), and both are this one */
    const m = /^\/api\/native\/(?:r3|[\w-]+)\/(.+)$/.exec(p);
    if (m){
      const tail = decodeURIComponent(m[1]);
      if (Object.prototype.hasOwnProperty.call(reads, tail)) return Promise.resolve(copy(reads[tail]));
      if (/^engine\//.test(tail)) return Promise.resolve({ runs: [] });
    }
    /* the registry's reads, as the server gave them, so a card drawn from them shows what they say */
    const r = /^\/api\/dept\/[\w-]+\/(.+)$/.exec(p);
    if (r){
      const tail = decodeURIComponent(r[1]);
      return Promise.resolve(Object.prototype.hasOwnProperty.call(dept, tail) ? copy(dept[tail]) : {});
    }
    return new Promise(() => {});
  },
  apiPost: () => Promise.resolve({}),
  window: {},
  esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
  SCREENS: { departments: () => "" }, TITLES: { departments: ["Departments", ""] },
  DOMAINS: TREE, CHARTERS: [], PLACEMENTS: [], INDEX: [], META: {},
  SETTINGS: { flags: { org2: true } },
  ICON: { know: "<path d='k'/>", dept: "<path d='d'/>", edit: "<path d='e'/>", plc: "<path d='p'/>" },
  st: (d) => d.status || "active",
  S: { screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } },
  render: () => {}, loadOrg: () => Promise.resolve(), simulate: () => ({ pending: true }),
  sbPageFromPath: () => null, mdHtml: (t) => "<p>" + t + "</p>",
  decideProposal: () => Promise.resolve({}), loadProposals: () => {},
  document: {
    listeners: {}, activeElement: null, body: { appendChild(){} },
    addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector(){ return null; }, querySelectorAll(){ return []; }, getElementById(){ return null; },
    createElement(){ return { id: "", innerHTML: "" }; },
  },
};
vm.createContext(ctx);
vm.runInContext(orgSrc.slice(orgSrc.indexOf(RB), orgSrc.indexOf(RE)), ctx);
["19-org2.js", "20-dept.js", "22-website.js", "23-screens.js", "24-functions.js"].forEach(f => vm.runInContext(read(f), ctx));

function click(ds){
  const el = { dataset: ds, closest(sel){
    const keys = Object.keys(ds).map(k => "[data-" + k.toLowerCase() + "]");
    if (sel === ".dp" || sel === ".wb") return el;
    return sel.split(",").some(s => keys.indexOf(s.trim()) >= 0) ? el : null;
  } };
  (ctx.document.listeners.click || []).forEach(fn => fn({ target: el, preventDefault(){}, stopPropagation(){} }));
}
async function paint(){
  for (let k = 0; k < 4; k++){ ctx.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 8; i++) await sleep(); }
  return ctx.dpViewerHtml(WEB, {}, null, null);
}
/* a rule's tag is a badge whose word is the owner's own for a rule (go, ask, refuse, always: PRD S5), printed as
   [tag:word] so the Python side scans every other word and finds the badge beside its rule */
const rest = h => h.replace(/<title>[\s\S]*?<\/title>/g, " ").replace(/ (?:title|aria-label)="[^"]*"/g, "")
  .replace(/<span class="dptag (go|ask|refuse|always)">\1<\/span>/g, " [tag:$1] ")
  .replace(/<[^>]+>/g, " ").replace(/&#39;/g, "'").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/\s+/g, " ").trim();
const hover = h => (h.match(/ (?:title|aria-label)="[^"]*"|<title>[\s\S]*?<\/title>/g) || []).join(" ")
  .replace(/<\/?title>/g, " ").replace(/&#39;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();

(async () => {
  vm.runInContext("wbS().v2 = true; dpS().sel = 'r3'; dpS().tab['r3'] = 'now';", ctx);
  for (let k = 0; k < 3; k++){ ctx.wbList(WEB); ctx.wbViewer(WEB); for (let i = 0; i < 6; i++) await sleep(); }
  const out = {};
  click({ wbtab: "map" }); out.map = await paint();
  click({ wbtab: "five" }); out.five = await paint();
  /* each function's pane on its three tabs: its page, its Chat (read from the record) and its Settings */
  for (const fn of ["identity", "adaptation", "priority", "coordination", "audit"]){
    click({ dptab: fn }); out[fn] = await paint();
    click({ dppane: "chat" }); out[fn + ":chat"] = await paint();
    click({ dppane: "settings" }); out[fn + ":settings"] = await paint();
    click({ dppane: fn });
  }
  /* the owner's own chat with the department */
  click({ wbtab: "chat" }); out.chat = await paint();
  out.list = ctx.dpListHtml(WEB, {}, null, null);
  const shown = {};
  Object.keys(out).forEach(k => { shown[k] = { rest: rest(out[k]), hover: hover(out[k]) }; });
  process.stdout.write(JSON.stringify(shown));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
