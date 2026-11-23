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
  assert.deepEqual(m.projects.map(p => p.href), DEPTS.map(d => `/d/${d.id}/`));          // no ?view=: a project opens in its studio
});

test("a finished project is Done once its team is idle again (last_status), a crashed one Something broke, a fresh one Not started yet", () => {
  const m = ProjectRail.model([{id: "a", node_status: "idle", last_status: "done"}, {id: "b", node_status: "idle", last_status: "done_with_open_items"},
    {id: "c", node_status: "idle", last_status: "crashed"}, {id: "d", node_status: "idle", last_status: null}, {id: "e", node_status: "idle", last_status: "stopped"}], []);
  assert.deepEqual(m.projects.map(p => p.state), ["done", "done", "problem", "idle", "idle"]);
});

test("the Attention count is every open question, approval and problem; questions are counted per project", () => {
  const needs = [{message_id: 1, dept_id: "bakery"}, {message_id: 2, dept_id: "bakery"}, {message_id: 3, dept_id: "web"}, {message_id: 4, kind: "approval"}];
  const m = ProjectRail.model(DEPTS, needs);
  assert.equal(m.count, 4);
  const heads = [{kind: "problem", task_id: "tsk_1"}, {kind: "problem", task_id: "tsk_2"}, {kind: "finished", task_id: "tsk_3"}];
  assert.equal(ProjectRail.model(DEPTS, needs, heads, {tsk_2: true}).count, 5);        // plus a problem not marked Got it, as Attention counts
  assert.deepEqual(m.needs.map(n => [n.name, n.count]), [["Bakery site", 2], ["Align Physio", 1], ["Your organisation", 1]]);
  assert.equal(m.projects.find(p => p.id === "web").state, "needs");          // a question beats "being made"
});

test("the markup: Attention with its count, Agent Org, My sections with +, the open project marked once, words escaped", () => {
  const html = ProjectRail.html(ProjectRail.model([...DEPTS, {id: "x", name: "<b>bold</b>", node_status: "idle"}], [{dept_id: "bakery"}]), "brew", {});
  assert.match(html, /id="pr-att" href="\/">.*Attention<\/span><b class="pr-count" aria-label="1 thing needs you">1<\/b>/);
  assert.match(html, /id="pr-org" href="\/\?pane=org">/);
  assert.match(html, /<h2 class="pr-head" id="pr-sec-h">My sections<\/h2><button type="button" class="pr-add" id="pr-addsec" data-pr="add"/);
  assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
  assert.match(html, /class="pr-item pr-on" href="\/d\/brew\/" aria-current="page" title="Done">/);
  assert.ok(html.includes("&lt;b&gt;bold&lt;/b&gt;") && !html.includes("<b>bold"));
  assert.ok(!html.includes("pr-needs-h"));                                       // what needs the owner is on Attention, not in the column
  assert.ok(ProjectRail.html(ProjectRail.model([], []), "", {}).includes("Your projects show here."));
  assert.match(ProjectRail.html(ProjectRail.model([], []), "", {here: "org"}), /class="pr-nav pr-on" id="pr-org" href="\/\?pane=org" aria-current="page"/);
  assert.match(ProjectRail.html(ProjectRail.model([], []), "", {here: "attention"}), /class="pr-nav pr-on" id="pr-att"/);
});

test("sections: each with its projects in order, a folded one shows none, the rest under All projects, and the boxes to name one", () => {
  const doc = {version: 1, sections: [{id: "sec_aaaa", name: "Clients", teams: ["brew", "bakery"], collapsed: false},
    {id: "sec_bbbb", name: "Old", teams: ["code"], collapsed: true}, {id: "sec_cccc", name: "Empty", teams: [], collapsed: false}]};
  const html = ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc});
  const names = part => (part.match(/class="pr-name">([^<]+)</g) || []).map(x => x.slice(16, -1));
  assert.deepEqual(names(html.slice(html.indexOf('data-sec="sec_aaaa"'), html.indexOf('data-sec="sec_bbbb"'))), ["Bakery site", "Brew Lab"]);    // the sidebar's order
  assert.match(html, /<div class="pr-sec pr-shut" data-sec="sec_bbbb">/);
  assert.ok(!names(html.slice(html.indexOf('data-sec="sec_bbbb"'), html.indexOf('data-sec="sec_cccc"'))).includes("CodeSprint"));
  assert.match(html, /Empty\. Use &middot;&middot;&middot; on a project to move it here\./);
  assert.deepEqual(names(html.slice(html.indexOf("pr-all"))), ["Align Physio", "New one"]);
  assert.match(html, /data-pr="secmenu" data-sec="sec_aaaa" aria-haspopup="menu" aria-label="Rename or delete Clients"/);
  assert.match(html, /data-pr="projmenu" data-team="web" aria-haspopup="menu" aria-label="More for Align Physio"/);
  assert.match(ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc, adding: true}), /<form class="pr-namebox" data-pr-form="add"><input class="pr-input"/);
  assert.match(ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc, renaming: "sec_aaaa"}), /data-pr-form="rename"><input [^>]*value="Clients">/);
  assert.match(ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc, allShut: true}), /<div class="pr-sec pr-all pr-shut">/);
  assert.match(ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc, error: "No <way>"}), /<p class="pr-err" role="alert">No &lt;way&gt;<\/p>/);
});

test("bad rows are skipped: no id, an id that is not one, not an object", () => {
  const m = ProjectRail.model([null, {name: "no id"}, {id: "../x"}, "web", {id: "ok", name: ""}], [null, {dept_id: "../x"}]);
  assert.deepEqual(m.projects.map(p => [p.id, p.name]), [["ok", "ok"]]);
  assert.deepEqual(m.needs.map(n => n.name), ["Your organisation"]);           // a need with no usable project is an org-level one
});

test("the one view button of a project reads Agent view in the studio and Simple view in the agent view", () => {
  assert.equal(DeptExt.helpers.viewLabel(true), "Agent view");
  assert.equal(DeptExt.helpers.viewLabel(false), "Simple view");
  assert.equal(DeptExt.helpers.switchMenuHtml, undefined);
});

// ---- named projects, task 7: Rename and Delete in a project's menu (D426) ----------------------------------------------------------

const SECS = [{id: "sec_aaaa", name: "Clients", teams: ["web"], collapsed: false}];

test("a project's menu has Rename, Delete, then Move to section", () => {
  const html = ProjectRail.projectMenuHtml({id: "web", name: "Align Physio", state: "idle"}, SECS);
  const acts = (html.match(/data-pr="[a-z]+"/g) || []).map(x => x.slice(9, -1));
  assert.deepEqual(acts.slice(0, 2), ["teamrename", "teamdelete"]);
  assert.ok(html.indexOf("Move to section") > html.indexOf("teamdelete"));
  assert.match(html, /data-pr="move" data-team="web" data-sec="sec_aaaa"/);
  assert.doesNotMatch(html, /data-pr="teamdelete"[^>]* disabled/);
});

test("Delete of a working project is disabled and says why", () => {
  const html = ProjectRail.projectMenuHtml({id: "web", name: "Align Physio", state: "making"}, SECS);
  assert.match(html, /data-pr="teamdelete"[^>]* disabled/);
  assert.match(html, /Working\. Stop it first\./);
});

test("a project being renamed shows a name box of 80 characters in its row; a section keeps 40", () => {
  const html = ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc: {version: 1, sections: []}, renamingTeam: "web"});
  assert.match(html, /<form class="pr-namebox" data-pr-form="teamrename"><input class="pr-input" type="text" maxlength="80"[^>]*value="Align Physio">/);
  const sec = ProjectRail.html(ProjectRail.model(DEPTS, []), "", {doc: {version: 1, sections: SECS}, renaming: "sec_aaaa"});
  assert.match(sec, /data-pr-form="rename"><input class="pr-input" type="text" maxlength="40"/);
});

test("the delete question names the project and says its files stay", () => {
  assert.equal(ProjectRail.deleteQuestion("Align Physio"), "Delete Align Physio? It leaves the sidebar. Its runs and files stay on disk.");
});
