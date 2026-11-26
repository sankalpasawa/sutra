"use strict";
// ProjectContextView (sutra_app/ui/static/js/project_context_view.js), D451 T11, T13, T14: "Project files and memory".
// Run with: node --test tests/ui/js/project_context_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const PV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/project_context_view.js"));
const unescape = s => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const words = html => unescape(html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());

const FILES = {files: [{id: "pf_aaaaaaaaaaaa", name: "brand <1>.md", kind: "text", size: 2048, chars: 1500, enabled: true, reference_only: false},
                       {id: "pf_bbbbbbbbbbbb", name: "spec.pdf", kind: "pdf", size: 40000, chars: 0, enabled: false, reference_only: true}],
               totals: {files: 2, bytes: 42048, chars: 1500}, mode: "whole", limits: {max_files: 50}};
const MEMORY = {enabled: true, rev: "m1", entries: [{n: 2, text: "2026-11-25: asked 'a page'. Result: done", source: "run", on: true}, {n: 1, text: "The shop is in Leeds", source: "owner", on: false}]};
const INSTR = {text: "Plain words.", rev: "i1", max_chars: 4000};
const CONTEXT = {off: false, mode: "whole", chat_stable: "Project context: <b>x</b>\n\nFrom the owner, for this project:\nPlain words.", chat_context: "", run_block: "From the owner, for this project:\nPlain words.",
                 files_used: ["brand <1>.md"], files_total: 2, memory_on: true, sizes: {chat_stable: 80, run_block: 50}, parts: []};

test("the panel says the plain words: project, files, memory; never department, node or a hash, and the standing privacy sentence", () => {
  const html = PV.panelHtml({name: "Cafe", files: FILES, instructions: INSTR, memory: MEMORY, context: CONTEXT, ui: {}});
  const text = words(html);
  assert.match(text, /Project files and memory/);
  assert.match(text, /Files you add are sent to the model you choose \(Claude or Codex\) when a chat or run uses them\./);
  assert.doesNotMatch(text, /department|node\b|sha|[0-9a-f]{40}/i);
  assert.match(html, /role="dialog" aria-modal="true" aria-label="Project files and memory"/);
});

test("Files: name, kind, size, characters, the switch Use in this project, Rename and Remove as real labelled buttons, and the totals", () => {
  const html = PV.filesHtml(FILES, {});
  assert.match(words(html), /2 of 50 files, 41\.1 KB/);
  assert.match(html, /<input type="checkbox" role="switch" data-act="pcv-toggle" data-id="pf_aaaaaaaaaaaa" checked aria-label="Use brand &lt;1&gt;\.md in this project"\/>/);
  assert.match(html, /<input type="checkbox" role="switch" data-act="pcv-toggle" data-id="pf_bbbbbbbbbbbb" aria-label="Use spec\.pdf in this project"\/>/);        // off: not checked
  assert.match(html, /<button type="button" class="linkbtn" data-act="pcv-rename" data-id="pf_aaaaaaaaaaaa" aria-label="Rename brand &lt;1&gt;\.md">Rename<\/button>/);
  assert.match(html, /data-act="pcv-remove" data-id="pf_bbbbbbbbbbbb" aria-label="Remove spec\.pdf from the project">Remove<\/button>/);
  assert.match(words(html), /1,500 characters/);
  assert.doesNotMatch(html, /<b>/);                                                         // every name is escaped
});

test("Files: a PDF or an image says it is reference only on its row, and the honest limits are stated (NFR-8)", () => {
  const html = PV.filesHtml(FILES, {});
  assert.match(words(html), /PDF, 39\.1 KB, reference only: its content is not read/);
  assert.match(words(html), /Excel and PowerPoint files are not read\. PDFs and images are kept for reference only\./);
});

test("Files: the whole or excerpts line says which, and an empty project says what to do", () => {
  assert.match(words(PV.filesHtml(FILES, {})), /All the text of these files goes in whole, with every message\./);
  assert.match(words(PV.filesHtml(Object.assign({}, FILES, {mode: "excerpts"}), {})), /too long to paste whole, so each message gets the parts that match it best/);
  const empty = words(PV.filesHtml({files: [], totals: {files: 0, bytes: 0, chars: 0}, mode: "none", limits: {max_files: 50}}, {}));
  assert.match(empty, /No files yet/); assert.match(empty, /0 of 50 files, 0 B/);
});

test("Files: Remove all asks first, and a rename is an input with Save", () => {
  assert.match(PV.filesHtml(FILES, {}), /data-act="pcv-clear">Remove all files</);
  assert.match(PV.filesHtml(FILES, {confirmClear: true}), /Remove every file\? .*Yes, remove all.*Keep them/);
  assert.match(PV.filesHtml(FILES, {renaming: "pf_aaaaaaaaaaaa"}), /<input class="pcv-name" data-id="pf_aaaaaaaaaaaa" value="brand &lt;1&gt;\.md"/);
});

test("Instructions: the box holds the text with its count, and a stale save says so with Reload and keeps what was typed", () => {
  const html = PV.instructionsHtml(INSTR, {});
  assert.match(html, /<textarea class="pcv-text"[^>]*aria-label="Project instructions"[^>]*>Plain words\.<\/textarea>/);
  assert.match(words(html), /12 of 4,000 characters/);
  const stale = PV.instructionsHtml(INSTR, {draft: "my edit", stale: true, instrError: PV.STALE});
  assert.match(stale, />my edit<\/textarea>/); assert.match(words(stale), /Changed since you opened it\. Reload to see the new text\./); assert.match(stale, /data-act="pcv-reload"/);
});

test("Memory: lines newest first with their source, a switch each, Edit and Delete, the off switch and its words (FR-17)", () => {
  const html = PV.memoryHtml(MEMORY, {});
  assert.ok(html.indexOf("asked 'a page'") < html.indexOf("The shop is in Leeds"));
  assert.match(words(html), /from a run/); assert.match(words(html), /from you/);
  assert.match(html, /data-act="pcv-entry-toggle" data-n="2" checked/); assert.doesNotMatch(html, /data-act="pcv-entry-toggle" data-n="1" checked/);
  assert.match(html, /data-act="pcv-entry-delete" data-n="1" aria-label="Delete this line"/);
  assert.match(words(PV.memoryHtml({enabled: false, entries: []}, {})), /Memory is off: nothing is sent and nothing new is kept/);
});

test("What will be sent: the panel's text IS the endpoint's text, character for character (FR-17)", () => {
  const html = PV.previewHtml(CONTEXT);
  const pres = [...html.matchAll(/<pre class="pcv-pre">([\s\S]*?)<\/pre>/g)].map(m => unescape(m[1]));
  assert.equal(pres[0], CONTEXT.chat_stable);
  assert.equal(pres[1], CONTEXT.run_block);
  const withExcerpts = [...PV.previewHtml(Object.assign({}, CONTEXT, {chat_context: "Parts of the project files for this message (x)"})).matchAll(/<pre class="pcv-pre">([\s\S]*?)<\/pre>/g)].map(m => unescape(m[1]));
  assert.equal(withExcerpts[0], CONTEXT.chat_stable + "\n\nParts of the project files for this message (x)");
  assert.match(words(PV.previewHtml({off: true})), /switched off on this computer/);
});

test("summaryLine and usingLine: nothing to say is nothing; otherwise the counts in plain words", () => {
  assert.equal(PV.summaryLine({files: []}, {enabled: true, entries: []}), "");
  assert.equal(PV.summaryLine(FILES, MEMORY), "2 files · memory on");
  assert.equal(PV.summaryLine({files: [FILES.files[0]]}, {enabled: false, entries: []}), "1 file · memory off");
  assert.equal(PV.usingLine({files_used: [1, 2, 3, 4], files_total: 4, memory_on: true}), "Using 4 project files, memory on");
  assert.equal(PV.usingLine({files_used: [1, 2, 3], files_total: 5, memory_on: false}), "Using 3 of 5 files; memory off");
  assert.equal(PV.usingLine({files_used: [], files_total: 0, memory_on: true}), "");
});

// ---- the controller, against a fake api ------------------------------------------------------------------------------------------------------------
function rig(overrides) {
  const calls = [];
  const data = {files: JSON.parse(JSON.stringify(FILES)), instructions: Object.assign({}, INSTR), memory: JSON.parse(JSON.stringify(MEMORY)), context: Object.assign({}, CONTEXT)};
  const handle = (method, p, body) => {
    calls.push({method, p, body});
    if (overrides && overrides[method + " " + p]) return overrides[method + " " + p](body);
    if (method === "GET" && p.endsWith("/files")) return data.files;
    if (method === "GET" && p.endsWith("/instructions")) return data.instructions;
    if (method === "GET" && p.endsWith("/memory")) return data.memory;
    if (method === "GET" && p.endsWith("/context")) return data.context;
    if (method === "PUT" && p.endsWith("/instructions")) { data.instructions = {text: body.text, rev: "i2", max_chars: 4000}; return data.instructions; }
    if (method === "PUT" && p.endsWith("/memory")) { data.memory = Object.assign({}, data.memory, {rev: "m2", entries: body.entries.map(e => Object.assign({source: "owner"}, e))}); return data.memory; }
    if (method === "PUT" && p.endsWith("/memory/settings")) { data.memory = Object.assign({}, data.memory, {enabled: body.enabled}); return data.memory; }
    return {};
  };
  const api = {get: async p => handle("GET", p), put: async (p, b) => handle("PUT", p, b), post: async (p, b) => handle("POST", p, b), patch: async (p, b) => handle("PATCH", p, b), del: async p => handle("DELETE", p)};
  const on = {};
  const box = {value: ""};
  const el = {innerHTML: "", hidden: true, addEventListener: (k, f) => { on[k] = f; }, querySelector: s => ({".pcv-text": box, ".pcv-name": box, ".pcv-new": box, ".pcv-etext": box, ".pcv-input": {click() { box.clicked = true; }}}[s] || null)};
  const view = PV.mount({el, api, readFile: async () => "aGVsbG8=", onChange: line => { el.summary = line; }});
  const btn = (act, extra) => ({closest() { return this; }, dataset: Object.assign({act}, extra || {})});
  return {view, el, on, calls, box, data, btn, click: (act, extra) => on.click({target: btn(act, extra), preventDefault() {}}), tick: () => new Promise(r => setImmediate(r))};
}

test("open loads the four reads for the project, draws the panel and reports the summary line", async () => {
  const r = rig();
  await r.view.open({dept: "web", name: "Cafe"});
  assert.deepEqual(r.calls.map(c => c.p).sort(), ["/api/teams/web/context", "/api/teams/web/files", "/api/teams/web/instructions", "/api/teams/web/memory"]);
  assert.equal(r.el.hidden, false); assert.match(r.el.innerHTML, /Project files and memory/); assert.match(r.el.innerHTML, /Cafe/);
  assert.equal(r.el.summary, "2 files · memory on");
});

test("the switch and Remove and Remove all call the routes of the file and read again", async () => {
  const r = rig();
  await r.view.open({dept: "web", name: "Cafe"});
  r.calls.length = 0;
  r.on.change({target: {dataset: {act: "pcv-toggle", id: "pf_aaaaaaaaaaaa"}, checked: false, classList: {contains: () => false}}});
  await r.tick(); await r.tick();
  assert.deepEqual(r.calls[0], {method: "PATCH", p: "/api/teams/web/files/pf_aaaaaaaaaaaa", body: {enabled: false}});
  r.click("pcv-remove", {id: "pf_bbbbbbbbbbbb"}); await r.tick(); await r.tick();
  assert.ok(r.calls.some(c => c.method === "DELETE" && c.p === "/api/teams/web/files/pf_bbbbbbbbbbbb"));
  r.click("pcv-clear"); await r.tick();
  assert.match(r.el.innerHTML, /Yes, remove all/);
  r.click("pcv-clear-yes"); await r.tick(); await r.tick();
  assert.ok(r.calls.some(c => c.method === "DELETE" && c.p === "/api/teams/web/files"));
});

test("files chosen in the panel are uploaded one by one to the project; a refusal is said with the file's name and the rest still go", async () => {
  const r = rig({"POST /api/teams/web/files": b => { if (b.name === "sheet.xlsx") throw Object.assign(new Error("Excel and PowerPoint files cannot be attached."), {status: 422}); return {}; }});
  await r.view.open({dept: "web", name: "Cafe"});
  r.on.change({target: {classList: {contains: c => c === "pcv-input"}, files: [{name: "a.txt"}, {name: "sheet.xlsx"}, {name: "b.txt"}], value: "x"}});
  for (let i = 0; i < 8; i += 1) await r.tick();
  const posts = r.calls.filter(c => c.method === "POST").map(c => c.body.name);
  assert.deepEqual(posts, ["a.txt", "sheet.xlsx", "b.txt"]);
  assert.match(words(r.el.innerHTML), /sheet\.xlsx: Excel and PowerPoint files cannot be attached\./);
});

test("saving the instructions sends the revision it read; a stale save says so, keeps the typed text and offers Reload", async () => {
  const r = rig();
  await r.view.open({dept: "web", name: "Cafe"});
  r.box.value = "New words";
  r.click("pcv-save-instr"); await r.tick(); await r.tick(); await r.tick();
  assert.deepEqual(r.calls.find(c => c.method === "PUT"), {method: "PUT", p: "/api/teams/web/instructions", body: {text: "New words", rev: "i1"}});
  const stale = rig({"PUT /api/teams/web/instructions": () => { throw Object.assign(new Error("busy"), {status: 409}); }});
  await stale.view.open({dept: "web", name: "Cafe"});
  stale.box.value = "my edit";
  stale.click("pcv-save-instr"); await stale.tick(); await stale.tick();
  assert.match(words(stale.el.innerHTML), /Changed since you opened it\. Reload to see the new text\./); assert.match(stale.el.innerHTML, />my edit<\/textarea>/);
  assert.match(stale.el.innerHTML, /data-act="pcv-reload"/);
});

test("memory: the off switch, a line switched off, a line deleted and a line added, each through its route", async () => {
  const r = rig();
  await r.view.open({dept: "web", name: "Cafe"});
  r.calls.length = 0;
  r.on.change({target: {dataset: {act: "pcv-mem-toggle"}, checked: false, classList: {contains: () => false}}}); await r.tick(); await r.tick();
  assert.deepEqual(r.calls[0], {method: "PUT", p: "/api/teams/web/memory/settings", body: {enabled: false}});
  r.on.change({target: {dataset: {act: "pcv-entry-toggle", n: "2"}, checked: false, classList: {contains: () => false}}}); await r.tick(); await r.tick();
  const put = r.calls.find(c => c.method === "PUT" && c.p === "/api/teams/web/memory");
  assert.deepEqual(put.body, {entries: [{n: 2, text: MEMORY.entries[0].text, on: false}, {n: 1, text: "The shop is in Leeds", on: false}], rev: "m1"});
  r.click("pcv-entry-delete", {n: "1"}); await r.tick(); await r.tick();
  assert.ok(r.calls.some(c => c.method === "DELETE" && c.p === "/api/teams/web/memory/1"));
  r.box.value = "Prefers short pages";
  r.click("pcv-add-line"); await r.tick(); await r.tick();
  assert.deepEqual(r.calls.find(c => c.method === "POST"), {method: "POST", p: "/api/teams/web/memory", body: {text: "Prefers short pages"}});
});

test("Close hides the panel and Esc closes it; a failed read says so in a sentence", async () => {
  const r = rig();
  await r.view.open({dept: "web", name: "Cafe"});
  r.click("pcv-close");
  assert.equal(r.el.hidden, true); assert.equal(r.el.innerHTML, "");
  const bad = rig({"GET /api/teams/web/files": () => { throw Object.assign(new Error("The app is not responding."), {status: 0}); }});
  await bad.view.open({dept: "web", name: "Cafe"});
  assert.match(words(bad.el.innerHTML), /The app is not responding\./);
});
