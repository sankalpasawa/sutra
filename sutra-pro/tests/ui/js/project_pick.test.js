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

test("a project heading names it as a button that opens the projects", () => {
  const html = ProjectPick.heading(P, "pulse", {attention: true});
  assert.match(html, /^What should we make in <button type="button" class="pp-name" aria-haspopup="menu" aria-expanded="false">Pulse<\/button>\?$/);
  assert.equal(text(html), "What should we make in Pulse?");
});

test("Let Sutra choose reads What should we make?", () => {
  const html = ProjectPick.heading(P, "", {attention: true});
  assert.match(html, /^What should we make\? <button type="button" class="pp-name pp-let" aria-haspopup="menu" aria-expanded="false">Let Sutra choose<\/button>$/);
});

test("the menu lists every project, then Let Sutra choose on Attention only, then New project", () => {
  const items = html => (html.match(/data-pp="[^"]*"/g) || []).map(x => x.slice(9, -1));
  assert.deepEqual(items(ProjectPick.menuHtml(P, "pulse", {attention: true})), ["pulse", "web", "", "+new"]);
  assert.deepEqual(items(ProjectPick.menuHtml(P, "pulse", {attention: false})), ["pulse", "web", "+new"]);
  assert.match(ProjectPick.menuHtml(P, "pulse", {}), /role="menuitemradio" aria-checked="true" data-pp="pulse">Pulse</);
  assert.match(ProjectPick.menuHtml(P, "pulse", {}), /data-pp="\+new">\+ New project&hellip;</);
});

test("a deleted or unknown last pick reads as Let Sutra choose", () => {
  assert.equal(ProjectPick.pickOf(P, "gone"), "");
  assert.equal(ProjectPick.pickOf(P, "web"), "web");
  assert.equal(ProjectPick.pickOf(null, "web"), "");
  assert.equal(text(ProjectPick.heading(P, "gone", {attention: true})), "What should we make? Let Sutra choose");
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
