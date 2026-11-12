"use strict";
// ProjectRail (sutra_app/ui/static/js/project_rail.js): the project sidebar of Home and of every team page. Here the pure parts (what each project
// reads as, the Needs you group, the markup); the column on the real pages is proved by tests/ui/test_home_front.py.
// Run with: node --test tests/ui/js/project_rail.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ProjectRail = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/project_rail.js"));
const DeptExt = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/dept_ext.js"));

const DEPTS = [
  {id: "web", name: "Align Physio", node_status: "running", live_task_id: "tsk_1"},
  {id: "bakery", name: "Bakery site", node_status: "waiting_on_you"},
  {id: "brew", name: "Brew Lab", node_status: "filed"},
  {id: "code", name: "CodeSprint", node_status: "fault"},
  {id: "new", name: "New one", node_status: "not_made"},
];

test("each project reads in plain words: being made, needs your answer, done, something broke, not started yet", () => {
  const m = ProjectRail.model(DEPTS, []);
  assert.deepEqual(m.projects.map(p => [p.id, p.state, p.words]), [
    ["web", "making", "Being made"], ["bakery", "needs", "Needs your answer"], ["brew", "done", "Done"],
    ["code", "problem", "Something broke"], ["new", "idle", "Not started yet"]]);
  assert.deepEqual(m.projects.map(p => p.href), DEPTS.map(d => `/d/${d.id}/?view=simple`));
});

test("Needs you: one row per project with an open question and its count; an approval of no project goes to the org chart", () => {
  const needs = [{message_id: 1, dept_id: "bakery"}, {message_id: 2, dept_id: "bakery"}, {message_id: 3, dept_id: "web"}, {message_id: 4, kind: "approval"}];
  const m = ProjectRail.model(DEPTS, needs);
  assert.deepEqual(m.needs.map(n => [n.name, n.count, n.href]), [
    ["Bakery site", 2, "/d/bakery/?view=simple"], ["Align Physio", 1, "/d/web/?view=simple"], ["Your organisation", 1, "/?pane=chart"]]);
  assert.equal(m.projects.find(p => p.id === "web").state, "needs");          // a question beats "being made"
});

test("the markup: the open project is marked, words are escaped, the groups have headings, and an empty list says where projects go", () => {
  const html = ProjectRail.html(ProjectRail.model([...DEPTS, {id: "x", name: "<b>bold</b>", node_status: "idle"}], [{dept_id: "bakery"}]), "brew");
  assert.match(html, /<h2 class="pr-head" id="pr-needs-h">Needs you<\/h2>/);
  assert.match(html, /<h2 class="pr-head" id="pr-proj-h">Projects<\/h2>/);
  assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
  assert.match(html, /class="pr-item pr-on" href="\/d\/brew\/\?view=simple" aria-current="page" title="Done">/);
  assert.ok(html.includes("&lt;b&gt;bold&lt;/b&gt;") && !html.includes("<b>bold"));
  assert.ok(!ProjectRail.html(ProjectRail.model([], []), "").includes("Needs you"));
  assert.ok(ProjectRail.html(ProjectRail.model([], []), "").includes("Your projects show here."));
});

test("bad rows are skipped: no id, an id that is not one, not an object", () => {
  const m = ProjectRail.model([null, {name: "no id"}, {id: "../x"}, "web", {id: "ok", name: ""}], [null, {dept_id: "../x"}]);
  assert.deepEqual(m.projects.map(p => [p.id, p.name]), [["ok", "ok"]]);
  assert.deepEqual(m.needs.map(n => n.name), ["Your organisation"]);           // a need with no usable project is an org-level one
});

test("the view switch of a project: Simple lists only the three views; Manager adds the Detailed view and the org map; Debug adds the raw AI chat and the log", () => {
  const menu = DeptExt.helpers.switchMenuHtml;
  const links = html => (html.match(/class="pv-link"[^>]*>([^<]+)</g) || []).map(s => s.slice(s.lastIndexOf(">") + 1, -1));
  assert.deepEqual(links(menu("simple")), []);
  assert.deepEqual(links(menu("manager")), ["Detailed view", "Team chats", "Org chart", "Workflow graph"]);
  assert.deepEqual(links(menu("debug")), ["Detailed view", "Team chats", "Org chart", "Workflow graph", "Raw AI chat", "Usage and log"]);
  assert.match(menu("manager"), /data-level="manager" aria-checked="true"/);
  assert.equal((menu("simple").match(/role="menuitemradio"/g) || []).length, 3);
});
