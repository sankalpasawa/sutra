"use strict";
// Run with: node --test tests/ui/js/project_pick.test.js
// The start heading names where a prompt goes (named projects, task 8, R1.8 and R1.9): "What should we make in <Project>?", the name a
// dropdown of projects. On Attention it also offers "Let Sutra choose" (plain "What should we make?"); both offer "+ New project…".
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const ProjectPick = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/project_pick.js"));

const P = [{id: "pulse", name: "Pulse"}, {id: "web", name: "Web <shop>"}];
const text = html => html.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();

test("a project heading names it as an underlined name that opens the projects (no box)", () => {
  const html = ProjectPick.heading(P, "pulse", {attention: true});
  assert.match(html, /^What should we make in <button type="button" class="pp-name" aria-haspopup="menu" aria-expanded="false">Pulse<\/button>\?$/);
  assert.equal(text(html), "What should we make in Pulse?");
});

test("there is no Let Sutra choose: an unknown or empty pick is the first project", () => {
  assert.equal(ProjectPick.pickOf(P, ""), "pulse");
  assert.equal(ProjectPick.pickOf(P, "gone"), "pulse");
  assert.equal(ProjectPick.pickOf(P, "web"), "web");
  assert.equal(text(ProjectPick.heading(P, "gone", {attention: true})), "What should we make in Pulse?");
  assert.doesNotMatch(ProjectPick.heading(P, "", {attention: true}) + ProjectPick.menuHtml(P, "", {attention: true}), /Let Sutra choose/);
});

test("with no project at all the heading is plain words and has no button", () => {
  assert.equal(ProjectPick.heading([], "", {attention: true}), "What should we make?");
  assert.equal(ProjectPick.pickOf(null, "web"), "");
});

test("the menu lists every project, then New project, on Attention and on a team page alike", () => {
  const items = html => (html.match(/data-pp="[^"]*"/g) || []).map(x => x.slice(9, -1));
  assert.deepEqual(items(ProjectPick.menuHtml(P, "pulse", {attention: true})), ["pulse", "web", "+new"]);
  assert.deepEqual(items(ProjectPick.menuHtml(P, "pulse", {attention: false})), ["pulse", "web", "+new"]);
  assert.match(ProjectPick.menuHtml(P, "pulse", {}), /role="menuitemradio" aria-checked="true" data-pp="pulse">Pulse</);
  assert.match(ProjectPick.menuHtml(P, "pulse", {}), /data-pp="\+new">\+ New project&hellip;</);
});

test("names are escaped", () => {
  assert.match(ProjectPick.heading(P, "web", {}), />Web &lt;shop&gt;</);
  assert.match(ProjectPick.menuHtml(P, "", {}), />Web &lt;shop&gt;</);
});

test("a busy or deleted project's refusal reads in plain words", () => {
  assert.equal(ProjectPick.refusal(409, "Pulse"), "Pulse is working. Wait for it or stop it.");
  assert.equal(ProjectPick.refusal(403, "Pulse"), "This project was deleted.");
  assert.equal(ProjectPick.refusal(500, "Pulse"), "");
});

test("the module is a classic script with one global", () => {
  const src = require("node:fs").readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/js/project_pick.js"), "utf8");
  assert.match(src, /root\.ProjectPick = ProjectPick/);
});
