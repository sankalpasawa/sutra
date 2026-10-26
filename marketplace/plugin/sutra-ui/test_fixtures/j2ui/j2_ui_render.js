// Browser-free render of j2_ui.html for tests: node j2_ui_render.js <j2_ui.html> <state.json> [previews.json] [docs.json]
// Runs the page's script against a stub DOM and prints {simple, sprog, cards: {workflow id: html}} as JSON.
const fs = require("fs"), vm = require("vm");
const [html, statePath, previewPath, docsPath] = process.argv.slice(2);
const noop = () => noop;
const el = () => new Proxy({innerHTML: "", textContent: "", value: "", style: {}, dataset: {}, disabled: false, open: false,
  classList: {toggle: noop, add: noop, remove: noop, contains: () => false}, children: [], scrollHeight: 0},
  {get: (t, k) => k in t ? t[k] : k === "querySelectorAll" ? () => [] : noop, set: (t, k, v) => (t[k] = v, true)});
const els = {};
const ctx = vm.createContext({
  document: {getElementById: id => els[id] || (els[id] = el()), querySelector: () => el(), querySelectorAll: () => [],
             body: el(), addEventListener: noop, createElement: el},
  location: {search: "", href: ""}, localStorage: {getItem: () => null, setItem: noop}, CSS: {escape: x => x},
  fetch: () => Promise.reject(new Error("no network")), setTimeout: noop, setInterval: noop, requestAnimationFrame: noop,
  console, URLSearchParams, Date, JSON, Math, Set, Map, Promise});
const src = fs.readFileSync(html, "utf8"), scripts = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)];
vm.runInContext(scripts[scripts.length - 1][1], ctx);
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
state.allChat = state.chat;
const previews = previewPath ? JSON.parse(fs.readFileSync(previewPath, "utf8")) : {};
const docs = docsPath ? JSON.parse(fs.readFileSync(docsPath, "utf8")) : {docs: {}};
const out = vm.runInContext(`(s, p, d) => { if (typeof PREVIEWS !== "undefined") Object.assign(PREVIEWS, p);
  if (typeof CTX !== "undefined") CTX = s; if (typeof MAP !== "undefined") { Object.assign(MAP, d.map || {}); MAPPIN = d.mappin || ""; MAPFILT = d.mapfilt || ""; WFSTEP = d.wfstep || []; }
  if (typeof ARTS !== "undefined"){ Object.assign(ARTS, d.artifacts || {}); ARTOPEN = d.artopen || ""; Object.assign(ARTTEXT, d.arttext || {}); }
  if (typeof BOARD !== "undefined"){ BOARD.entries.length = 0; BOARD.entries.push(...(d.board || [])); }
  if (typeof DOCS !== "undefined"){ Object.assign(DOCS, d.docs); FOCUS = d.focus || {}; Object.assign(REFS, d.refs || {}); (d.open || []).forEach(k => FOLD.add(k)); CHFOCUS = d.chfocus || 0; OTAG = d.otag || ""; STAGE_AUDITS.length = 0; STAGE_AUDITS.push(...(d.stage_audits || [])); }
  renderSimple(s);
  return {simple: $("smsgs").innerHTML, sprog: $("sprog").innerHTML,
          cards: Object.fromEntries(s.workflows.map(w => [w.id, atomCards(s, w)])), workflows: typeof renderWorkflows === "function" ? renderWorkflows(s) : "", charter: typeof renderCharter === "function" ? renderCharter(s) : "", docs: typeof renderDocs === "function" ? renderDocs() : "", artifacts: typeof renderArtifacts === "function" ? renderArtifacts() : "", map: typeof renderMap === "function" ? renderMap(MAP) : "", board: typeof renderBoard === "function" ? renderBoard() : "", needs: typeof renderNeeds === "function" ? renderNeeds(s) : "", needcount: typeof needsYou === "function" ? needsYou(s).length : -1, branches: typeof MAPBRANCH !== "undefined" ? MAPBRANCH : [], pages: typeof MAPPAGES !== "undefined" ? MAPPAGES : [], given: typeof mapGiven === "function" ? mapGiven(MAP) : []}; }`, ctx)(state, previews, docs);
console.log(JSON.stringify(out));
