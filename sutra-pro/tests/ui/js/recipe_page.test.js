"use strict";
// The Recipes page's client (DV-3): it reads the list, opens a recipe, saves a new one or a change, goes back to an old version, puts one away, copies a starter, reads a file into a draft and starts a recipe
// with ONE client id for the form so a double press sends once; what the server refuses is shown in its own words.
// Run with: node --test tests/ui/js/recipe_page.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const RecipePage = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "recipe_page.js"));
const RID = "rcp_0123456789ab";
const BODY = {overview: "Write the menu.", procedure: ["Ask", "Write in $1 words"], specifications: [], advice: [], forbidden: ["Never invent"], needs: [{label: "Words"}]};

function world(over = {}) {
  const calls = [];
  const answers = Object.assign({list: [{id: RID, title: "Menu", kind: "own", status: "active", version: 1, overview: "x"}, {id: "starter-explain-this-folder", title: "Explain", kind: "starter", status: "active", version: 1, overview: "y"}],
    one: {id: RID, title: "Menu", kind: "own", status: "active", version: 1, current_version: 1, body: BODY, versions: [{version: 1, note: "first", sha256: "a"}]}}, over);
  const fail = (method, url) => { const f = answers.fail && answers.fail(method, url); if (f) throw f; };
  const api = {
    get: async (url, query) => { calls.push(["get", url, query]); fail("get", url); if (url === "/api/recipes") return answers.list; const id = decodeURIComponent(url.split("/")[3]); return id.startsWith("starter-") ? Object.assign({}, answers.one, {id, kind: "starter", title: "Explain"}) : answers.one; },
    post: async (url, body) => { calls.push(["post", url, body]); fail("post", url); return url.endsWith("/start") ? {duplicate: !!answers.dup, message_id: 1} : url.endsWith("/import") ? answers.imported : {id: RID, version: 2}; },
    put: async (url, body) => { calls.push(["put", url, body]); fail("put", url); return {id: RID, version: 2}; },
  };
  const nodes = {};
  const doc = {getElementById: id => (nodes[id] = nodes[id] || {id, innerHTML: ""})};
  let n = 0;
  const page = RecipePage.create({doc, api, newId: () => "form-id-" + (++n)});
  return {page, calls, nodes, answers};
}
const button = (act, dataset = {}) => ({dataset: Object.assign({act}, dataset), closest() { return this; }});
const form = (act, fields, dataset = {}) => ({dataset: Object.assign({act}, dataset), elements: Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, {value: v}])), closest() { return this; }});
const settle = () => new Promise(r => setImmediate(r));
const submit = async (w, f) => { w.page.onSubmit({target: f, preventDefault() {}}); await settle(); await settle(); };

test("start reads the list and draws it", async () => {
  const w = world();
  assert.equal(await w.page.start(), true);
  assert.match(w.nodes["r-list"].innerHTML, /<b>Menu<\/b>[\s\S]*<h2>Starters<\/h2>/);
  assert.deepEqual(w.calls[0], ["get", "/api/recipes", undefined]);
  await w.page.act("toggle-archived", {});
  assert.deepEqual(w.calls.at(-1), ["get", "/api/recipes", {archived: 1}]);
});

test("opening a recipe draws it, and an id of another shape asks nothing", async () => {
  const w = world();
  await w.page.start();
  assert.equal(await w.page.open(RID), true);
  assert.match(w.nodes["r-detail"].innerHTML, /<h2>Menu<\/h2>/);
  const before = w.calls.length;
  assert.equal(await w.page.open("../x"), false);
  assert.equal(w.calls.length, before);
});

test("a new recipe is saved with the lines split and the blanks as needs, then opened", async () => {
  const w = world();
  await w.page.start();
  await w.page.act("new", {});
  assert.match(w.nodes["r-detail"].innerHTML, /<h2>New recipe<\/h2>/);
  await submit(w, form("save", {title: " Menu ", overview: "For the cafe", procedure: "Ask\n\nWrite in $1 words", specifications: "", advice: "", forbidden: "Never invent", needs: "Words", note: ""}, {id: ""}));
  const post = w.calls.find(c => c[0] === "post" && c[1] === "/api/recipes");
  assert.deepEqual(post[2], {title: "Menu", body: {overview: "For the cafe", needs: [{label: "Words"}], procedure: ["Ask", "Write in $1 words"], specifications: [], advice: [], forbidden: ["Never invent"]}, note: ""});
  assert.equal(w.calls.at(-1)[1], "/api/recipes/" + RID);
});

test("a change goes to the recipe's own route and a refusal keeps what was typed with the server's sentence", async () => {
  const w = world();
  await w.page.start();
  await w.page.open(RID);
  await w.page.act("edit", {});
  await submit(w, form("save", {title: "Menu", overview: "", procedure: "", specifications: "", advice: "", forbidden: "", needs: "", note: "x"}, {id: RID}));
  assert.equal(w.calls.find(c => c[0] === "put")[1], "/api/recipes/" + RID);
  w.answers.fail = (m, url) => (m === "put" ? Object.assign(new Error("A recipe needs at least one step in its procedure"), {status: 422}) : null);
  assert.equal(await w.page.save(form("save", {title: "Menu", overview: "", procedure: "", specifications: "", advice: "", forbidden: "", needs: "", note: ""}, {id: RID})), false);
  assert.match(w.nodes["r-detail"].innerHTML, /role="alert">A recipe needs at least one step/);
  assert.match(w.nodes["r-detail"].innerHTML, /name="title" maxlength="80" value="Menu"/);
});

test("starting asks for the blanks, sends them with one client id and says it was sent; the same press again says it was already sent", async () => {
  const w = world();
  await w.page.start();
  await w.page.open(RID);
  await w.page.act("start-open", {id: RID});
  const id = w.page.state().clientId;
  assert.match(w.nodes["r-detail"].innerHTML, /name="blank0"/);
  await submit(w, form("start", {blank0: " twenty "}, {id: RID}));
  const post = w.calls.find(c => c[1].endsWith("/start"));
  assert.deepEqual(post, ["post", "/api/recipes/" + RID + "/start", {blanks: ["twenty"], client_id: id}]);
  assert.match(w.nodes["r-detail"].innerHTML, /Sent to Sutra\. Look at the chat on Home/);
  await w.page.act("start-open", {id: RID});
  assert.notEqual(w.page.state().clientId, id, "a new form is a new send");
  w.answers.dup = true;
  await submit(w, form("start", {blank0: "x"}, {id: RID}));
  assert.match(w.nodes["r-detail"].innerHTML, /That was already sent\./);
});

test("a start the server refuses shows its sentence and the form stays", async () => {
  const w = world({fail: (m, url) => (url.endsWith("/start") ? Object.assign(new Error("“Words”: That line looks like it holds a key, a token or a password, and those are never kept."), {status: 422}) : null)});
  await w.page.start();
  await w.page.open(RID);
  await w.page.act("start-open", {id: RID});
  assert.equal(await submit(w, form("start", {blank0: "secret"}, {id: RID})), undefined);
  await new Promise(r => setImmediate(r));
  assert.match(w.nodes["r-detail"].innerHTML, /role="alert">“Words”: That line looks like it holds a key/);
  assert.match(w.nodes["r-detail"].innerHTML, /name="blank0"/);
});

test("copy, put away and go back each use their own route", async () => {
  const w = world();
  await w.page.start();
  await w.page.open("starter-explain-this-folder");
  await w.page.act("copy", {});
  assert.deepEqual(w.calls.find(c => c[1].endsWith("/copy")), ["post", "/api/recipes/starter-explain-this-folder/copy", {}]);
  await w.page.open(RID);
  await w.page.act("revert", {version: "1"});
  assert.deepEqual(w.calls.find(c => c[1].endsWith("/revert")), ["post", "/api/recipes/" + RID + "/revert", {version: 1}]);
  await w.page.open(RID);
  await w.page.act("archive", {archived: "1"});
  assert.deepEqual(w.calls.find(c => c[1].endsWith("/archive")), ["post", "/api/recipes/" + RID + "/archive", {archived: true}]);
  assert.equal(w.page.state().open, null);
});

test("a recipe file is read into a draft form that is not saved, and a refusal is shown", async () => {
  const w = world({imported: {title: "Menu", body: BODY, draft: true}});
  await w.page.start();
  await w.page.act("import-open", {});
  assert.match(w.nodes["r-detail"].innerHTML, /Read a recipe file/);
  await submit(w, form("import", {markdown: "# Menu\n## Procedure\n- a"}));
  assert.match(w.nodes["r-detail"].innerHTML, /This is a draft\. Read it, change what you like, then save it/);
  assert.equal(w.calls.filter(c => c[1] === "/api/recipes" && c[0] === "post").length, 0, "reading a file saved nothing");
  const bad = world({fail: (m, url) => (url.endsWith("/import") ? Object.assign(new Error("A recipe file starts with a title line (# Title) and has a Procedure part"), {status: 422}) : null)});
  await bad.page.start();
  await bad.page.act("import-open", {});
  await submit(bad, form("import", {markdown: "nothing"}));
  await new Promise(r => setImmediate(r));
  assert.match(bad.nodes["r-detail"].innerHTML, /role="alert">A recipe file starts with a title line/);
});

test("a list that cannot be read says so in plain words", async () => {
  const w = world({fail: () => Object.assign(new Error("x"), {status: 0})});
  assert.equal(await w.page.start(), false);
  assert.match(w.nodes["r-list"].innerHTML, /Sutra could not be reached/);
});
