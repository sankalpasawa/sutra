"use strict";
// The Work page's client (DV-2): it reads the list and the tags, asks again for a tag, a state or the words typed (after a short pause, newest answer wins), saves tags through the right route,
// says the server's own sentence when a tag is refused, and asks a project how it went.
// Run with: node --test tests/ui/js/work_page.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const WorkPage = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "work_page.js"));
const TASK = "tsk_0123456789ab";
const PROJECT = "prj_0123456789ab";
const item = (over = {}) => Object.assign({kind: "task", id: TASK, title: "Menu", status: "done", status_word: "Done", team: "Web", created_at: "2026-11-20T10:00:00Z", tags: [], link: "/d/web/"}, over);

function world(over = {}) {
  const gets = [];
  const puts = [];
  const answers = Object.assign({items: [item(), item({kind: "project", id: PROJECT, link: "/p/" + PROJECT, status: "failed"})], tags: [{tag: "cafe", count: 1}], summary: {project_id: PROJECT, lines: ["It stopped."], steps: []}}, over);
  const api = {
    get: async (url, query) => {
      gets.push([url, query]);
      if (answers.fail && answers.fail(url)) throw answers.fail(url);
      if (url === "/api/work") return typeof answers.items === "function" ? answers.items(query) : answers.items;
      if (url === "/api/work/tags") return answers.tags;
      if (url.endsWith("/summary")) return answers.summary;
      throw new Error("unexpected " + url);
    },
    put: async (url, body) => {
      puts.push([url, body]);
      if (answers.failPut) throw answers.failPut;
      return {tags: body.tags};
    },
  };
  const nodes = {};
  const doc = {activeElement: null, getElementById: id => (nodes[id] = nodes[id] || {id, innerHTML: "", contains: () => false})};
  const timers = [];
  const page = WorkPage.create({doc, api, setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearTimeout: n => { if (timers[n - 1]) timers[n - 1].fn = null; }});
  return {page, gets, puts, nodes, timers, answers, doc};
}
const button = dataset => ({dataset, closest() { return this; }});
const click = (w, b) => w.page.onClick({target: b});

test("start reads the list and the tags and draws them", async () => {
  const w = world();
  assert.equal(await w.page.start(), true);
  assert.match(w.nodes["w-list"].innerHTML, /Menu/);
  assert.match(w.nodes["w-filters"].innerHTML, /cafe \(1\)/);
  assert.deepEqual(w.gets[0], ["/api/work", {limit: 201}]);
});

test("a tag, a state and the words typed each ask again, the words after a pause and only the last", async () => {
  const w = world();
  await w.page.start();
  await click(w, button({act: "filter-tag", tag: "cafe"}));
  assert.deepEqual(w.gets.filter(g => g[0] === "/api/work").pop()[1], {limit: 201, tag: "cafe"});
  await click(w, button({act: "filter-tag", tag: "cafe"}));                                      // the same tag again clears it
  assert.deepEqual(w.gets.filter(g => g[0] === "/api/work").pop()[1], {limit: 201});
  await w.page.onChange({target: {id: "w-status", value: "done"}});
  assert.equal(w.gets.filter(g => g[0] === "/api/work").pop()[1].status, "done");
  const before = w.gets.length;
  w.page.onInput({target: {id: "w-q", value: "m"}});
  w.page.onInput({target: {id: "w-q", value: "menu"}});
  assert.equal(w.timers.filter(t => t.fn).length, 1);
  assert.equal(w.timers.at(-1).ms, WorkPage.SEARCH_MS);
  assert.equal(w.gets.length, before);
  await w.timers.at(-1).fn();
  assert.equal(w.gets.filter(g => g[0] === "/api/work").pop()[1].q, "menu");
});

test("a slower answer to an older question never replaces the newer one", async () => {
  const waiting = [];
  const w = world({items: query => new Promise(resolve => waiting.push(() => resolve([item({title: query.q || "everything"})])))});
  const first = w.page.start();
  const second = w.page.setFilter({q: "menu"});
  waiting[1]();                                                                                  // the newer answer comes first
  await second;
  waiting[0]();
  await first;
  assert.deepEqual(w.page.state().items.map(i => i.title), ["menu"]);
});

test("saving tags goes to the item's own route with the words split, then the list is read again", async () => {
  const w = world();
  await w.page.start();
  await click(w, button({act: "tags-edit", id: TASK}));
  assert.match(w.nodes["w-list"].innerHTML, /data-act="tags-save"/);
  const form = {dataset: {act: "tags-save", kind: "task", id: TASK}, elements: {tags: {value: " cafe , weekly,, "}}, closest() { return this; }};
  let stopped = false;
  await w.page.onSubmit({target: form, preventDefault() { stopped = true; }});
  assert.equal(stopped, true);
  assert.deepEqual(w.puts, [["/api/work/task/" + TASK + "/tags", {tags: ["cafe", "weekly"]}]]);
  assert.equal(w.page.state().editing, "");
  assert.equal(w.gets.filter(g => g[0] === "/api/work").length, 2);
  await w.page.saveTags("chat", TASK, []);
  await w.page.saveTags("task", "../x", []);
  assert.equal(w.puts.length, 1, "a kind or an id of another shape sends nothing");
});

test("a refused tag shows the server's own sentence and keeps the form open", async () => {
  const refusal = Object.assign(new Error("A tag is 1 to 30 letters, digits, spaces, dashes or underscores: “bad/tag” is not"), {status: 422});
  const w = world({failPut: refusal});
  await w.page.start();
  await click(w, button({act: "tags-edit", id: TASK}));
  assert.equal(await w.page.saveTags("task", TASK, ["bad/tag"]), false);
  assert.match(w.nodes["w-list"].innerHTML, /role="alert">A tag is 1 to 30 letters/);
  assert.equal(w.page.state().editing, TASK);
  w.answers.failPut = Object.assign(new Error("x"), {status: 0});
  await w.page.saveTags("task", TASK, ["x"]);
  assert.match(w.nodes["w-list"].innerHTML, /Sutra could not be reached/);
});

test("how did it go asks the project and draws the lines, and a project that is gone says so", async () => {
  const w = world();
  await w.page.start();
  assert.equal(await w.page.how(PROJECT), true);
  assert.equal(w.gets.at(-1)[0], "/api/projects/" + PROJECT + "/summary");
  assert.match(w.nodes["w-list"].innerHTML, /<p>It stopped\.<\/p>/);
  assert.equal(await w.page.how(TASK), false, "a task has no summary");
  w.answers.fail = url => (url.endsWith("/summary") ? Object.assign(new Error("not found"), {status: 404}) : null);
  await w.page.how(PROJECT);
  assert.match(w.nodes["w-list"].innerHTML, /There is nothing to say about that project\./);
});

test("a list that cannot be read says so in plain words and keeps asking possible", async () => {
  const w = world({fail: url => (url === "/api/work" ? Object.assign(new Error("x"), {status: 0}) : null)});
  assert.equal(await w.page.start(), false);
  assert.match(w.nodes["w-list"].innerHTML, /Sutra could not be reached/);
  w.answers.fail = null;
  assert.equal(await w.page.refresh(), true);
  assert.equal(w.page.state().error, "");
});

test("the page shows the newest 200 and says so when there are more, and Show more asks for another 200", async () => {          // review 11
  const many = n => Array.from({length: n}, (_, i) => item({id: "tsk_" + String(i).padStart(12, "0"), title: "Task " + i}));
  const w = world({items: q => many(Math.min(q.limit, 450))});
  await w.page.start();
  assert.equal(w.page.state().items.length, 200);
  assert.equal(w.page.state().more, true);
  assert.match(w.nodes["w-list"].innerHTML, /Showing the newest 200\. <button type="button" data-act="show-more">Show more<\/button>/);
  assert.deepEqual(w.gets[0][1], {limit: 201});                                                    // one more than shown: that is how it knows
  await click(w, button({act: "show-more"}));
  await new Promise(r => setImmediate(r));
  assert.equal(w.gets.filter(g => g[0] === "/api/work").pop()[1].limit, 401);
  assert.equal(w.page.state().items.length, 400);
  await w.page.setFilter({q: "x"});
  assert.equal(w.page.state().limit, WorkPage.PAGE, "a new question starts again from the newest 200");
  const few = world({items: many(5)});
  await few.page.start();
  assert.equal(few.page.state().more, false);
  assert.equal(few.nodes["w-list"].innerHTML.includes("Show more"), false);
});

test("what is typed in the search box is cut at 200 characters", () => {
  const w = world();
  w.page.typed("x".repeat(500));
  assert.equal(w.page.state().filter.q.length, 200);
});

test("the caret stays where it was when the list is drawn again while the owner types", async () => {                          // review 12
  const w = world();
  await w.page.start();
  const box = {id: "w-q", selectionStart: 2, selectionEnd: 4, focused: 0, range: null, focus() { this.focused += 1; }, setSelectionRange(a, b) { this.range = [a, b]; }};
  w.doc.activeElement = box;
  w.nodes["w-filters"].contains = x => x === box;
  w.nodes["w-q"] = box;
  await w.page.setFilter({tag: "cafe"});                                                                     // the filters are drawn again with a tag pressed
  assert.equal(box.focused, 1);
  assert.deepEqual(box.range, [2, 4]);
});
