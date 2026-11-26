"use strict";
// StartFiles (sutra_app/ui/static/js/start_files.js), D451 T9: files where work starts. The start box and the follow-up box of a team's page, Attention's box.
// Run with: node --test tests/ui/js/start_files.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const SF = require(path.join(JS, "start_files.js"));
const ID = "a".repeat(64);
const file = (name, size) => ({name, size: size === undefined ? 5 : size});
const tick = () => new Promise(r => setImmediate(r));

// a small stand-in for the page: elements with delegated listeners and the few members the module uses
function el() {
  const on = {};
  const input = {value: "x", files: [], classList: {contains: c => c === "sfinput"}, click() { this.clicked = (this.clicked || 0) + 1; }};
  return {innerHTML: "", on, input, addEventListener: (k, f) => { (on[k] = on[k] || []).push(f); }, querySelector: s => (s === ".sfinput" ? input : null),
          fire(k, e) { (on[k] || []).forEach(f => f(e)); }};
}
const button = data => ({closest() { return this; }, dataset: data});
function rig(handlers, extra) {
  const calls = [];
  const api = {post: async (p, body) => { calls.push({p, body}); const h = handlers[p] || handlers["*"]; if (!h) throw Object.assign(new Error("no route"), {status: 404}); return h(body); }};
  const attach = el(), chips = el(), host = el();
  const w = SF.mount(Object.assign({el: attach, chips, host, api, url: () => "/api/teams/web/attachments", project: () => "web", readFile: async () => "aGVsbG8="}, extra || {}));
  return {w, attach, chips, host, calls};
}

test("the paperclip is a real button with a label, beside a hidden file input; the chips row says its news with role=status", async () => {
  const {w, attach, chips} = rig({"*": () => ({id: ID, kind: "text", size: 5})});
  assert.match(attach.innerHTML, /<button type="button" class="sfattach" data-act="sf-attach" aria-label="Attach files"/);
  assert.match(attach.innerHTML, /<input type="file" class="sfinput" multiple hidden/);
  assert.equal(chips.innerHTML, "");                                                    // nothing held, nothing drawn
  await w.addFiles([file("a.txt")]);
  assert.match(chips.innerHTML, /^<div class="sfchips" role="status"><ul class="ccfiles"/);
  assert.match(chips.innerHTML, /a\.txt/);
});

test("a click on the paperclip opens the chooser; the chosen files are uploaded to the url and the input is emptied", async () => {
  const {w, attach, calls} = rig({"*": () => ({id: ID, kind: "text", size: 5})});
  attach.fire("click", {target: button({act: "sf-attach"})});
  assert.equal(attach.input.clicked, 1);
  attach.input.files = [file("a.txt"), file("b.csv")];
  attach.fire("change", {target: attach.input});
  await tick(); await tick();
  assert.equal(attach.input.value, "");
  assert.deepEqual(calls.map(c => c.p), ["/api/teams/web/attachments", "/api/teams/web/attachments"]);
  assert.deepEqual(w.refs(), [{id: ID, name: "a.txt"}, {id: ID, name: "b.csv"}]);
});

test("a drop and a paste on the box add files; a text paste is left alone; a failed chip stays with its reason and holds the send", async () => {
  const {w, host, chips} = rig({"*": () => ({id: ID, kind: "text", size: 5})});
  let prevented = 0;
  host.fire("dragover", {dataTransfer: {types: ["Files"]}, preventDefault() { prevented += 1; }});
  assert.equal(prevented, 1);
  host.fire("drop", {dataTransfer: {types: ["Files"], files: [file("sheet.xlsx")]}, preventDefault() { prevented += 1; }});
  assert.equal(w.bar.files()[0].status, "failed");
  assert.match(chips.innerHTML, /sheet\.xlsx.*not attached: .*Excel and PowerPoint files cannot be attached/);
  assert.equal(w.blocked(), "Remove the file that was not attached, or it will not be read.");
  host.fire("paste", {clipboardData: {files: [], items: []}, preventDefault() { prevented += 100; }});
  assert.equal(prevented, 2);                                                           // the text paste was not taken
  chips.fire("click", {target: button({act: "composer-remove", key: w.bar.files()[0].key})});
  assert.equal(w.bar.files().length, 0); assert.equal(w.blocked(), "");
  host.fire("paste", {clipboardData: {files: [{name: "image.png", size: 2, type: "image/png"}]}, preventDefault() { prevented += 1; }});
  await tick(); await tick();
  assert.equal(w.bar.files()[0].name, "pasted-image-1.png");
});

test("Add to project keeps a ready file with the project (promote) and says so; with no project there is no such button", async () => {
  const {w, chips, calls} = rig({"*": () => ({id: ID, kind: "text", size: 5})});
  await w.addFiles([file("brief.md")]);
  assert.match(chips.innerHTML, /data-act="sf-project"/);
  chips.fire("click", {target: button({act: "sf-project", key: "f1"})});
  await tick();
  assert.deepEqual(calls.at(-1), {p: "/api/teams/web/files/promote", body: {attachment_id: ID, name: "brief.md"}});
  assert.match(chips.innerHTML, /In the project/);
  const none = rig({"*": () => ({id: ID, kind: "text", size: 5})}, {project: () => ""});
  await none.w.addFiles([file("brief.md")]);
  assert.doesNotMatch(none.chips.innerHTML, /sf-project/);
});

test("the team page: a held send never reaches the page; a ready one carries its files once; the answer clears them or says why and puts the words back", async () => {
  const {w, chips} = rig({"*": () => ({id: ID, kind: "text", size: 5})});
  const form = el(), box = {value: "make the page"};
  SF.guard(form, w, box);
  await w.addFiles([file("spec.txt")]);
  let stopped = 0;
  form.fire("submit", {preventDefault() {}, stopImmediatePropagation() { stopped += 1; }});
  assert.equal(stopped, 0);                                                             // ready: the page's own handler runs
  assert.deepEqual(SF.fields(), {files: [{id: ID, name: "spec.txt"}]});
  assert.deepEqual(SF.fields(), {});                                                    // once: another sendText (a card answer) carries nothing
  box.value = "";                                                                       // the page cleared the box before it sent
  await SF.answered({ok: false, status: 404, json: async () => ({error: {code: "not_found", message: "that attachment was not found"}})});
  assert.match(chips.innerHTML, /One of the files is no longer stored\. Remove it and attach it again\./);
  assert.equal(box.value, "make the page");                                             // the words are back
  assert.equal(w.refs().length, 1);                                                     // and the chips stay
  form.fire("submit", {preventDefault() {}, stopImmediatePropagation() {}});
  SF.fields();
  await SF.answered({ok: true, status: 200});
  assert.equal(w.bar.files().length, 0);
});

test("a chip that is still uploading or failed stops the submit before the page sees it, with the sentence under the box", async () => {
  let release;
  const {w, chips} = rig({"*": () => new Promise(r => { release = () => r({id: ID, kind: "text", size: 5}); })});
  const form = el(), box = {value: "go"};
  SF.guard(form, w, box);
  const job = w.addFiles([file("slow.txt")]);
  await tick();
  let prevented = 0, stopped = 0;
  form.fire("submit", {preventDefault() { prevented += 1; }, stopImmediatePropagation() { stopped += 1; }});
  assert.equal(prevented, 1); assert.equal(stopped, 1);
  assert.match(chips.innerHTML, /Wait for the files to finish uploading\./);
  assert.deepEqual(SF.fields(), {});                                                    // nothing was taken for a send that did not happen
  release(); await job;
});

test("a send with no files changes nothing at all: no files key, no chips, no note", async () => {
  const {w, chips} = rig({});
  const form = el();
  SF.guard(form, w, {value: "plain words"});
  form.fire("submit", {preventDefault() {}, stopImmediatePropagation() {}});
  assert.deepEqual(SF.fields(), {});
  await SF.answered({ok: false, status: 409});                                          // not ours: it takes nothing and says nothing
  assert.equal(chips.innerHTML, "");
});

test("refusal words: a missing file, a busy team and the server's own sentence", () => {
  assert.match(SF.refusal({status: 404}, null), /no longer stored/);
  assert.match(SF.refusal({status: 409}, {ok: false}), /The team is working/);
  assert.equal(SF.refusal({status: 422}, {error: {message: "Files cannot go with an answer to a team's question yet."}}), "Files cannot go with an answer to a team's question yet.");
  assert.equal(SF.refusal({status: 400}, {error: "files must be a list of {id, name}, at most 10"}), "files must be a list of {id, name}, at most 10");
});

test("page(): mounts on the start box and the follow-up box when they are there, once, with the project's own upload url", async () => {
  const mk = id => Object.assign(el(), {id, value: ""});
  const parts = {lform: mk("lform"), lbox: mk("lbox"), lattach: mk("lattach"), lfiles: mk("lfiles"), sform: mk("sform"), sbox: mk("sbox"), sattach: mk("sattach"), sfiles: mk("sfiles")};
  const doc = {getElementById: id => parts[id] || null};
  const calls = [];
  globalThis.SutraCtx = {dept: "web", api: {post: async (p, b) => { calls.push(p); return {id: ID, kind: "text", size: 5}; }}};
  globalThis.FileReader = class { readAsDataURL() { this.result = "data:text/plain;base64,aGVsbG8="; setImmediate(() => this.onload()); } };          // the page's own reader
  SF._live.widgets = {};
  assert.equal(SF.page(doc), true);
  assert.match(parts.lattach.innerHTML, /sf-attach/); assert.match(parts.sattach.innerHTML, /sf-attach/);
  assert.equal(Object.keys(SF._live.widgets).length, 2);
  SF.page(doc);
  assert.equal(parts.lform.on.submit.length, 1);                                        // mounting again adds nothing
  await SF._live.widgets.lform.addFiles([file("a.txt")]);
  assert.deepEqual(calls, ["/api/teams/web/attachments"]);
  assert.equal(SF.page({getElementById: () => null}), true);                            // another page: nothing to mount, nothing breaks
  delete globalThis.SutraCtx; delete globalThis.FileReader;
});
