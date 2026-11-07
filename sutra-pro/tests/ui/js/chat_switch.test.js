"use strict";
// ChatSwitch (sutra_app/ui/static/js/chat_switch.js): the strip of chats in Home's chat column (gap package dept-chats). The org chat first, then each
// team followed by its divisions; the active one selected and named; questions that wait counted on their team's tab; every word escaped.
// Run with: node --test tests/ui/js/chat_switch.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatSwitch = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_switch.js"));
const {entries, bar, heading, nextIndex, entryOf} = ChatSwitch;

const DEPTS = [{id: "print", name: "Print", session_id: "cs_aaaaaaaaaaaa"}, {id: "web", name: "Web", session_id: "cs_bbbbbbbbbbbb"}];
const GRAPH = {nodes: [
  {id: "root", kind: "root", chat_session_id: "cs_org"},
  {id: "web", kind: "department", chat_session_id: "cs_bbbbbbbbbbbb"},
  // the shape GET /api/graph really sends (GraphNodeOut): a division names its team in `dept_id`; there is no `department_id` or `parent_id`
  {id: "blog", kind: "division", label: "Blog", org_node_id: "blog", dept_id: "web", chat_session_id: "cs_cccccccccccc"},
  {id: "web.identity", kind: "function", chat_session_id: "cs_dddddddddddd", dept_id: "web"},
]};

test("the org chat comes first, then each team followed by its divisions, in the order the server listed them", () => {
  const list = entries(DEPTS, GRAPH, []);
  assert.deepEqual(list.map(e => [e.id, e.kind, e.label]), [["cs_org", "org", "Sutra"], ["cs_aaaaaaaaaaaa", "department", "Print"], ["cs_bbbbbbbbbbbb", "department", "Web"], ["cs_cccccccccccc", "division", "Blog"]]);
  assert.equal(list[3].parent, "Web");
  assert.equal(list[0].node, "root");
});

test("a division is listed under the team its `dept_id` names, and under no other", () => {
  const graph = {nodes: [
    {id: "menu", kind: "division", label: "Menu", dept_id: "print", chat_session_id: "cs_111111111111"},
    {id: "blog", kind: "division", label: "Blog", dept_id: "web", chat_session_id: "cs_cccccccccccc"},
    {id: "orphan", kind: "division", label: "Orphan", dept_id: "gone", chat_session_id: "cs_222222222222"},
  ]};
  const list = entries(DEPTS, graph, []);
  assert.deepEqual(list.map(e => [e.node, e.kind, e.parent]), [["root", "org", ""], ["print", "department", ""], ["menu", "division", "Print"], ["web", "department", ""], ["blog", "division", "Web"]]);
  assert.match(bar(list, "cs_cccccccccccc"), /data-session="cs_cccccccccccc" data-node="blog" data-kind="division" aria-selected="true"/);
  assert.equal(heading(list, "cs_cccccccccccc"), "Chat with Blog");
});

test("functions and steps are not chats the owner switches to", () => {
  assert.equal(entries(DEPTS, GRAPH, []).some(e => e.id === "cs_dddddddddddd"), false);
});

test("a row without a usable id or chat is dropped, and a chat is listed once", () => {
  const list = entries([{id: "a b", name: "Bad", session_id: "cs_eeeeeeeeeeee"}, {id: "x", name: "NoChat"}, {id: "p", name: "P", session_id: "cs_ffffffffffff"}, {id: "q", name: "Q", session_id: "cs_ffffffffffff"}, null, "x"], null, null);
  assert.deepEqual(list.map(e => e.id), ["cs_org", "cs_ffffffffffff"]);
  assert.deepEqual(entries(null, undefined, undefined).map(e => e.id), ["cs_org"]);
  assert.deepEqual(entries("nope", {nodes: "nope"}, 3).map(e => e.id), ["cs_org"]);
});

test("a team's questions that wait are counted on its tab; approvals are not a team's", () => {
  const needs = [{session_id: "cs_bbbbbbbbbbbb", kind: "question"}, {session_id: "cs_bbbbbbbbbbbb", kind: "question"}, {session_id: "cs_org", kind: "approval"}, {session_id: "cs_aaaaaaaaaaaa", kind: "approval"}];
  const list = entries(DEPTS, GRAPH, needs);
  assert.deepEqual(list.map(e => e.waiting), [0, 0, 2, 0]);
  const html = bar(list, "cs_org");
  assert.match(html, /<span class="csbadge" aria-label="2 questions wait">2<\/span>/);
  assert.match(bar(entries(DEPTS, GRAPH, [needs[0]]), "cs_org"), /aria-label="1 question waits">1</);
});

test("the strip is a tablist of buttons; the active tab is selected and the only one in the tab order", () => {
  const html = bar(entries(DEPTS, GRAPH, []), "cs_bbbbbbbbbbbb");
  const tabs = [...html.matchAll(/<button [^>]*>/g)].map(m => m[0]);
  assert.equal(tabs.length, 4);
  tabs.forEach(t => assert.match(t, /^<button type="button" role="tab" class="cstab[ a-z]*" id="cstab-cs_[a-z]+" data-act="switch-chat" data-session="/));
  assert.equal(tabs.filter(t => /aria-selected="true"/.test(t)).length, 1);
  assert.match(tabs[2], /data-session="cs_bbbbbbbbbbbb" data-node="web" data-kind="department" aria-selected="true" tabindex="0"/);
  tabs.filter(t => !/aria-selected="true"/.test(t)).forEach(t => assert.match(t, /aria-selected="false" tabindex="-1"/));
  assert.match(tabs[3], /title="A division of Web"/);
});

test("an unknown active chat falls back to the org chat, which is the only one that was ever not a team", () => {
  assert.match(bar(entries(DEPTS, GRAPH, []), "cs_nope"), /data-session="cs_org" data-node="root" data-kind="org" aria-selected="true"/);
  assert.match(bar(entries(DEPTS, GRAPH, []), ""), /data-session="cs_org"[^>]*aria-selected="true"/);
});

test("with no team there is nothing to switch and no strip", () => {
  assert.equal(bar(entries([], {nodes: []}, []), "cs_org"), "");
  assert.equal(bar([], "cs_org"), "");
  assert.equal(bar(null, "cs_org"), "");
});

test("names are escaped and cut to a length that fits a tab", () => {
  const html = bar(entries([{id: "x", name: '<img src=x onerror=alert(1)>', session_id: "cs_999999999999"}, {id: "y", name: "A".repeat(80), session_id: "cs_888888888888"}], null, []), "cs_org");
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, />A{39}…</);
});

test("the heading names the chat on show", () => {
  const list = entries(DEPTS, GRAPH, []);
  assert.equal(heading(list, "cs_org"), "Chat with Sutra");
  assert.equal(heading(list, "cs_bbbbbbbbbbbb"), "Chat with Web");
  assert.equal(heading(list, "blog"), "Chat with Blog");                          // a node id finds its chat too
  assert.equal(heading(list, "cs_unknown"), "Chat with Sutra");
  assert.equal(heading([], ""), "Chat with Sutra");
});

test("entryOf finds a chat by its session or its node", () => {
  const list = entries(DEPTS, GRAPH, []);
  assert.equal(entryOf(list, "web").id, "cs_bbbbbbbbbbbb");
  assert.equal(entryOf(list, "cs_aaaaaaaaaaaa").node, "print");
  assert.equal(entryOf(list, "nothing"), null);
  assert.equal(entryOf(null, "web"), null);
});

test("the arrow keys wrap, Home and End go to the ends, any other key is not ours", () => {
  assert.equal(nextIndex("ArrowRight", 4, 3), 0);
  assert.equal(nextIndex("ArrowRight", 4, 0), 1);
  assert.equal(nextIndex("ArrowLeft", 4, 0), 3);
  assert.equal(nextIndex("ArrowLeft", 4, 2), 1);
  assert.equal(nextIndex("Home", 4, 2), 0);
  assert.equal(nextIndex("End", 4, 0), 3);
  assert.equal(nextIndex("Enter", 4, 0), -1);
  assert.equal(nextIndex("ArrowRight", 0, 0), -1);
  assert.equal(nextIndex("ArrowRight", 4, -1), 0);
  assert.equal(nextIndex("ArrowRight", "x", 0), -1);
});
