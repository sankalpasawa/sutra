"use strict";
// AttachBar (sutra_app/ui/static/js/attach_bar.js), D451 T8: the one chip controller the composer, the start box, the follow-up box, Attention's box and Create project share.
// Run with: node --test tests/ui/js/attach_bar.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const AB = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/attach_bar.js"));
const ID = "a".repeat(64);
const file = (name, size) => ({name, size: size === undefined ? 5 : size});
const tick = () => new Promise(r => setImmediate(r));

function rig(handlers, extra) {
  const calls = [];
  const api = {post: async (p, body) => { calls.push({p, body}); const h = handlers[p] || handlers["*"]; if (!h) throw Object.assign(new Error("no route"), {status: 404}); return h(body); }};
  let changes = 0;
  const bar = AB.create(Object.assign({api, url: "/up", readFile: async () => "aGVsbG8=", onChange: () => { changes += 1; }}, extra || {}));
  return {bar, calls, changes: () => changes};
}

test("a file is checked, read, uploaded to the one url and shown as a chip; refs() are the ready ones in order", async () => {
  const {bar, calls} = rig({"/up": b => ({id: b.name === "a.txt" ? ID : "b".repeat(64), kind: "text", size: 5})});
  await bar.addFiles([file("a.txt"), file("b.txt")]);
  assert.deepEqual(calls.map(c => c.body), [{name: "a.txt", content_b64: "aGVsbG8="}, {name: "b.txt", content_b64: "aGVsbG8="}]);
  assert.deepEqual(bar.refs(), [{id: ID, name: "a.txt"}, {id: "b".repeat(64), name: "b.txt"}]);
  assert.equal(bar.ready(), 2); assert.equal(bar.blocked(), "");
  assert.match(bar.html(), /class="ccfiles"/);
});

test("the url may be a function read at upload time (Attention: the picked project changes between files)", async () => {
  let target = "/api/teams/web/attachments";
  const {bar, calls} = rig({"*": () => ({id: ID, kind: "text", size: 5})}, {url: () => target});
  await bar.addFiles([file("a.txt")]);
  target = "/api/chats/cs_org/attachments";
  await bar.addFiles([file("b.txt")]);
  assert.deepEqual(calls.map(c => c.p), ["/api/teams/web/attachments", "/api/chats/cs_org/attachments"]);
});

test("a refused type is a failed chip that says why and stays; blocked() names it; Remove clears it", async () => {
  const {bar, calls} = rig({"/up": () => ({id: ID, kind: "text", size: 5})});
  await bar.addFiles([file("sheet.xlsx")]);
  assert.equal(bar.files()[0].status, "failed"); assert.match(bar.files()[0].error, /Excel and PowerPoint files cannot be attached/);
  assert.equal(calls.length, 0);                                                        // nothing was uploaded
  assert.equal(bar.blocked(), AB.REMOVE_FAILED); assert.deepEqual(bar.refs(), []);
  assert.match(bar.html(), /not attached: .*Excel and PowerPoint/);
  bar.removeFile(bar.files()[0].key);
  assert.equal(bar.files().length, 0); assert.equal(bar.blocked(), "");
});

test("a chip that is still uploading blocks with its own sentence, and a failed upload stays as a chip", async () => {
  let release;
  const {bar} = rig({"/up": () => new Promise(r => { release = () => r({id: ID, kind: "text", size: 5}); })});
  const job = bar.addFiles([file("slow.txt")]);
  await tick();
  assert.equal(bar.blocked(), AB.WAIT_UPLOAD); assert.match(bar.html(), /uploading/);
  release(); await job;
  assert.equal(bar.blocked(), "");
  const bad = rig({"/up": () => { throw new Error("The server is down."); }});
  await bad.bar.addFiles([file("a.txt")]);
  assert.equal(bad.bar.files()[0].status, "failed"); assert.match(bad.bar.files()[0].error, /The server is down/);
  assert.equal(bad.bar.blocked(), AB.REMOVE_FAILED);
});

test("an eleventh file is a failed chip with the limit in words (message by default, request when asked)", async () => {
  const {bar} = rig({"/up": () => ({id: ID, kind: "text", size: 5})});
  await bar.addFiles(Array.from({length: 11}, (_, i) => file("f" + i + ".txt")));
  assert.equal(bar.files().filter(f => f.status === "ready").length, 10);
  assert.equal(bar.files()[10].error, "Up to 10 files can go with one message.");
  const request = rig({"/up": () => ({id: ID, kind: "text", size: 5})}, {noun: "request", maxFiles: 1});
  await request.bar.addFiles([file("a.txt"), file("b.txt")]);
  assert.equal(request.bar.files()[1].error, "Up to 1 files can go with one request.");
});

test("a paste or a drop: take() is false for text and returns the upload for files; a pasted screenshot gets a name of its own", async () => {
  const {bar} = rig({"/up": () => ({id: ID, kind: "image", size: 5})});
  assert.equal(bar.take({files: [], items: []}), false); assert.equal(bar.take(null), false);
  await bar.take({files: [{name: "image.png", size: 3, type: "image/png"}]}, {pasted: true});
  await bar.take({files: [{name: "image.png", size: 3, type: "image/png"}]}, {pasted: true});
  assert.deepEqual(bar.files().map(f => f.name), ["pasted-image-1.png", "pasted-image-2.png"]);
  assert.equal(AB.hasFiles({types: ["Files"]}), true); assert.equal(AB.hasFiles({types: ["text/plain"]}), false);
});

test("a thumbnail is a blob: url the page made and is revoked when the chip goes", async () => {
  const made = [], revoked = [];
  const {bar} = rig({"/up": () => ({id: ID, kind: "image", size: 5})}, {objectUrl: {create: f => { made.push(f.name); return "blob:http://x/" + made.length; }, revoke: u => revoked.push(u)}});
  await bar.addFiles([file("shot.png")]);
  assert.match(bar.html(), /<img class="ccthumb" src="blob:http:\/\/x\/1"/);
  bar.clear();
  assert.deepEqual(revoked, ["blob:http://x/1"]); assert.equal(bar.files().length, 0);
});

test("with project: true a ready chip offers Add to project (and says In the project once it is); without it the chips are exactly what the composer draws", async () => {
  const {bar} = rig({"/up": () => ({id: ID, kind: "text", size: 5})});
  await bar.addFiles([file("a.txt")]);
  assert.doesNotMatch(bar.html(), /sf-project/);
  assert.match(bar.html({project: true}), /data-act="sf-project" data-key="f1" aria-label="Add a.txt to the project">Add to project</);
  bar.files()[0].inProject = true;
  assert.match(bar.html({project: true}), /In the project/); assert.doesNotMatch(bar.html({project: true}), /sf-project/);
  assert.equal(AB.chips([{key: "f1", name: "<b>.txt", status: "ready", size: 2048}]).includes("&lt;b&gt;.txt"), true);          // every word is escaped
});
