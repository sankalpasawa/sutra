"use strict";
// SectionsStore (sutra_app/ui/static/js/sections_store.js): the owner's sidebar sections over GET/PUT /api/sections, and the pure helpers the sidebar
// uses to change and draw them. Run with: node --test tests/ui/js/sections_store.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const S = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/sections_store.js"));

const DOC = {version: 1, sections: [
  {id: "sec_aaaaaa", name: "Clients", teams: ["web-development", "prd"], collapsed: false},
  {id: "sec_bbbbbb", name: "Internal", teams: ["ops"], collapsed: true},
]};
const frozen = () => JSON.parse(JSON.stringify(DOC));

function fakeApi(answers) {
  const calls = [];
  return {
    calls,
    get: async p => { calls.push(["GET", p]); if (answers.get instanceof Error) throw answers.get; return answers.get; },
    put: async (p, body) => { calls.push(["PUT", p, body]); if (answers.put instanceof Error) throw answers.put; return answers.put === undefined ? body : answers.put; },
  };
}

test("load reads /api/sections and any failure or odd answer is the empty default", async () => {
  const api = fakeApi({get: frozen()});
  assert.deepEqual(await S.load(api), DOC);
  assert.deepEqual(api.calls, [["GET", "/api/sections"]]);
  assert.deepEqual(await S.load(fakeApi({get: new Error("network")})), {version: 1, sections: []});
  assert.deepEqual(await S.load(fakeApi({get: {nope: 1}})), {version: 1, sections: []});
});

test("save puts the whole document and says what the server kept, or why it refused", async () => {
  const api = fakeApi({});
  const done = await S.save(frozen(), api);
  assert.equal(done.ok, true);
  assert.deepEqual(done.data, DOC);
  assert.deepEqual(api.calls[0].slice(0, 2), ["PUT", "/api/sections"]);
  const refused = await S.save(frozen(), fakeApi({put: Object.assign(new Error("The sections were refused"), {status: 422})}));
  assert.deepEqual(refused, {ok: false, data: null, error: "The sections were refused"});
});

test("assign moves a team into one section only, or out of all of them, and never changes its input", () => {
  const doc = frozen();
  const moved = S.assign(doc, "ops", "sec_aaaaaa");
  assert.deepEqual(moved.sections.map(s => s.teams), [["web-development", "prd", "ops"], []]);
  assert.deepEqual(doc, DOC);
  const out = S.assign(moved, "prd", null);
  assert.deepEqual(out.sections.map(s => s.teams), [["web-development", "ops"], []]);
  assert.deepEqual(S.assign(doc, "prd", "sec_nothere"), DOC);
  assert.deepEqual(S.assign(doc, "brand-new", "sec_bbbbbb").sections[1].teams, ["ops", "brand-new"]);
});

test("add makes a section with a fresh id and a clean name; a bad name or a full list changes nothing", () => {
  const doc = frozen();
  const added = S.add(doc, "  Side\u0007 projects \n");
  assert.equal(added.sections.length, 3);
  const made = added.sections[2];
  assert.match(made.id, /^sec_[a-z0-9]{6}$/);
  assert.ok(!["sec_aaaaaa", "sec_bbbbbb"].includes(made.id));
  assert.deepEqual([made.name, made.teams, made.collapsed], ["Side projects", [], false]);
  assert.deepEqual(S.add(doc, "   "), DOC);
  assert.deepEqual(S.add(doc, "x".repeat(41)), DOC);
  let full = {version: 1, sections: []};
  for (let i = 0; i < S.MAX_SECTIONS; i++) full = S.add(full, "S" + i);
  assert.equal(full.sections.length, 30);
  assert.equal(S.add(full, "one more").sections.length, 30);
  assert.equal(new Set(full.sections.map(s => s.id)).size, 30);
});

test("rename follows the same name rules; remove sends the teams back to All projects", () => {
  const doc = frozen();
  assert.equal(S.rename(doc, "sec_aaaaaa", " Customers ").sections[0].name, "Customers");
  assert.deepEqual(S.rename(doc, "sec_aaaaaa", ""), DOC);
  assert.deepEqual(S.rename(doc, "sec_nothere", "X"), DOC);
  const gone = S.remove(doc, "sec_aaaaaa");
  assert.deepEqual(gone.sections.map(s => s.id), ["sec_bbbbbb"]);
  assert.deepEqual(S.group(gone, ["web-development", "ops"]).at(-1).teams, ["web-development"]);
  assert.deepEqual(doc, DOC);
});

test("group lists each section with its shown teams in sidebar order, then the unsectioned rest", () => {
  const teams = [{id: "prd", name: "PRD"}, {id: "ops", name: "Ops"}, {id: "design", name: "Design"}, {id: "web-development", name: "Web"}];
  const groups = S.group(frozen(), teams);
  assert.equal(groups.length, 3);
  assert.deepEqual(groups.map(g => g.section && g.section.id), ["sec_aaaaaa", "sec_bbbbbb", null]);
  assert.deepEqual(groups[0].teams.map(t => t.name), ["PRD", "Web"]);       // the sidebar's order, the sidebar's objects
  assert.deepEqual(groups[1].teams.map(t => t.id), ["ops"]);
  assert.deepEqual(groups[2].teams.map(t => t.id), ["design"]);
  assert.deepEqual(S.group(null, ["a1", "b2"]), [{section: null, teams: ["a1", "b2"]}]);
  const twice = {version: 1, sections: [{id: "sec_aaaaaa", name: "A", teams: ["ab"]}, {id: "sec_bbbbbb", name: "B", teams: ["ab"]}]};
  assert.deepEqual(S.group(twice, ["ab"]).map(g => g.teams), [["ab"], [], []]);           // a team is drawn once, in its first section
});

test("the helper is a classic script with one global and calls the one route literally", () => {
  const fs = require("node:fs");
  const text = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/js/sections_store.js"), "utf8");
  assert.match(text, /root\.SectionsStore = SectionsStore/);
  assert.match(text, /"\/api\/sections"/);
  assert.doesNotMatch(text, /localStorage/);
});
