"use strict";
// What the Work page draws (DV-2): one list of tasks and projects with their state in words, tags as chips, filters, the edit form and "How did it go?"; every word from the wire is escaped; a link
// is drawn only for the two shapes the server makes; no machine name on the page.
// Run with: node --test tests/ui/js/work_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const View = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "work_view.js"));
const TASK = "tsk_0123456789ab";
const PROJECT = "prj_0123456789ab";
const task = (over = {}) => Object.assign({kind: "task", id: TASK, title: "Menu for my cafe", status: "done", status_word: "Done", team: "Web", created_at: "2026-11-20T10:00:00Z", tags: ["cafe"], link: "/d/web/"}, over);
const project = (over = {}) => Object.assign({kind: "project", id: PROJECT, title: "Cafe site", status: "failed", status_word: "Could not finish", team: "", created_at: "2026-11-20T10:00:00Z", tags: [], link: "/p/" + PROJECT}, over);

test("a task and a project are listed with their words, their link, their tags and what can be done", () => {
  const html = View.listHtml([task(), project()], {});
  assert.match(html, /<li class="witem" data-kind="task" data-id="tsk_0123456789ab"><div class="wtop"><span class="wkind">Task<\/span><a href="\/d\/web\/">Menu for my cafe<\/a><span class="pstate">Done<\/span>/);
  assert.match(html, /<span class="wtag" data-tag="cafe">cafe<\/span>/);
  assert.match(html, /data-act="tags-edit" data-id="tsk_0123456789ab">Change tags</);
  assert.match(html, /data-kind="project"[\s\S]*<a href="\/p\/prj_0123456789ab">Cafe site<\/a>[\s\S]*data-act="tags-edit" data-id="prj_0123456789ab">Add tags</);
  assert.equal((html.match(/data-act="how"/g) || []).length, 1, "only a project can be asked how it went");
  assert.match(html, />How did it go\?</);
});

test("an empty list says so, and says something else when a filter is on", () => {
  assert.match(View.listHtml([], {}), /Nothing yet\./);
  assert.match(View.listHtml([], {filtered: true}), /Nothing matches\./);
});

test("a link is drawn only for the two shapes the server makes and everything from the wire is escaped", () => {
  const evil = "<img src=x onerror=1>";
  const html = View.listHtml([task({title: evil, team: evil, tags: [evil], link: "javascript:alert(1)", status_word: evil}), task({id: "tsk_aaaaaaaaaaaa", link: "https://evil.example/"}), task({id: "tsk_bbbbbbbbbbbb", link: "/d/web/../../x"})], {});
  assert.equal(html.includes("<img"), false);
  assert.equal(html.includes("javascript:"), false);
  assert.equal(html.includes("evil.example"), false);
  assert.equal((html.match(/<a href=/g) || []).length, 0);
});

test("the edit form carries the item and the tags as text, and the split is by commas", () => {
  const html = View.listHtml([task({tags: ["cafe", "weekly"]})], {editing: TASK});
  assert.match(html, /<form class="wedit" data-act="tags-save" data-kind="task" data-id="tsk_0123456789ab">/);
  assert.match(html, /name="tags" value="cafe, weekly"/);
  assert.equal(html.includes('data-act="tags-edit"'), false, "the buttons give way to the form");
  assert.deepEqual(View.tagsFromText(" cafe, ,weekly ,, "), ["cafe", "weekly"]);
  assert.equal(View.tagsToText(["a", "b"]), "a, b");
});

test("the filters offer the tags in use with their count and only the states that exist", () => {
  const html = View.filtersHtml([{tag: "cafe", count: 2}, {tag: "weekly", count: 1}], {tag: "cafe", q: "menu", status: "done"}, ["done", "running", "weird"]);
  assert.match(html, /value="menu"/);
  assert.match(html, /<button type="button" class="wtag" data-act="filter-tag" data-tag="cafe" aria-pressed="true">cafe \(2\)<\/button>/);
  assert.match(html, /aria-pressed="false">weekly \(1\)/);
  assert.match(html, /<option value="done" selected>Done<\/option>/);
  assert.match(html, /<option value="running">Working<\/option>/);
  assert.equal(html.includes("weird"), false);
  assert.equal(View.filtersHtml([], {}, []).includes('class="wtags"'), false);
});

test("how did it go: the lines, the steps, working and a problem are drawn in plain words", () => {
  const html = View.summaryHtml({project_id: PROJECT, lines: ["It stopped.", "It used 3 credits and about $0.60, in about 4 minutes."], steps: [{name: "Write the menu", state: "done", state_word: "Done", calls: 3, usd: 0.6, tries: 2}, {name: "Price the dishes", state: "cancelled", state_word: "Cancelled", calls: 0, usd: null, tries: 1}, {name: "Check it", state: "planned", state_word: "Waiting its turn", calls: 0, usd: null, tries: 1}]});
  assert.match(html, /<p>It stopped\.<\/p><p>It used 3 credits/);
  assert.match(html, /<b>Write the menu<\/b> Done, 3 credits, about \$0\.60, 2 tries/);
  assert.match(html, /<b>Price the dishes<\/b> Cancelled<\/li>/);
  assert.match(html, /<b>Check it<\/b> Waiting its turn<\/li>/);                               // a step that has not started has its words too
  assert.match(View.summaryHtml("loading"), /Working it out/);
  assert.match(View.summaryHtml({error: "There is nothing to say about that project."}), /role="alert"><p>There is nothing/);
  assert.equal(View.summaryHtml(undefined), "");
  assert.equal(View.summaryHtml({lines: ["<b>x</b>"]}).includes("<b>x"), false);
});

test("the page uses no machine words", () => {
  const html = View.filtersHtml([{tag: "cafe", count: 1}], {}, ["done"]) + View.listHtml([task(), project()], {}) + View.summaryHtml({lines: ["It finished."], steps: []});
  const words = html.replace(/<[^>]*>/g, " ");
  assert.equal(/\b(node|nodes|lease|tier|grant|ledger|ceiling|api)\b/i.test(words), false, words);
});

test("the search box holds at most 200 characters", () => {
  assert.match(View.filtersHtml([], {}, []), /id="w-q" maxlength="200"/);
});
