"use strict";
// The project page's theme (D383, D396): the owner's own choice (light or dark, stored by Home or a team page) wins; with none, or "system", the computer's light or dark setting decides and the page follows it
// while it is open; another tab's change of the choice is followed; a browser that cannot say gets dark. The script is read out of the page and run with fakes.
// Run with: node --test tests/ui/js/project_theme.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const HTML = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/pages/project.html"), "utf8");
const SCRIPT = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).find(code => code.includes("j2theme"));

function page(stored, osLight, {throws = false} = {}) {
  const document = {documentElement: {dataset: {}}};
  const state = {stored, osLight};
  const listeners = {media: [], storage: []};
  const localStorage = {getItem: key => { if (throws) throw new Error("blocked"); return key === "j2theme" ? state.stored : null; }};
  const matchMedia = query => ({matches: query.includes("light") ? state.osLight : !state.osLight, addEventListener: (type, fn) => listeners.media.push(fn)});
  const addEventListener = (type, fn) => listeners[type].push(fn);
  new Function("document", "localStorage", "matchMedia", "addEventListener", SCRIPT)(document, localStorage, matchMedia, addEventListener);
  return {theme: () => document.documentElement.dataset.theme, state, listeners};
}

test("the script is in the page", () => assert.ok(SCRIPT));

test("an owner's choice wins over the computer's setting", () => {
  assert.equal(page("light", false).theme(), "light");
  assert.equal(page("dark", true).theme(), "dark");
});

test("with no choice, or system, the page follows the computer's light or dark setting", () => {
  assert.equal(page(null, true).theme(), "light");
  assert.equal(page(null, false).theme(), "dark");
  assert.equal(page("system", true).theme(), "light");
  assert.equal(page("system", false).theme(), "dark");
  assert.equal(page("anything else", true).theme(), "light");
});

test("a change of the computer's setting while the page is open is followed, unless the owner chose", () => {
  const free = page(null, true);
  free.state.osLight = false;
  free.listeners.media.forEach(fn => fn());
  assert.equal(free.theme(), "dark");
  const chosen = page("light", true);
  chosen.state.osLight = false;
  chosen.listeners.media.forEach(fn => fn());
  assert.equal(chosen.theme(), "light");
});

test("a choice made in another tab is followed, and clearing it goes back to the computer's setting", () => {
  const p = page(null, true);
  p.state.stored = "dark";
  p.listeners.storage.forEach(fn => fn({key: "j2theme"}));
  assert.equal(p.theme(), "dark");
  p.state.stored = null;
  p.listeners.storage.forEach(fn => fn({key: "j2theme"}));
  assert.equal(p.theme(), "light");
  p.state.stored = "dark";
  p.listeners.storage.forEach(fn => fn({key: "something-else"}));
  assert.equal(p.theme(), "light", "another key is not a theme change");
});

test("a browser that blocks its storage follows the computer, and one that cannot say gets dark", () => {
  assert.equal(page(null, true, {throws: true}).theme(), "light");
  const document = {documentElement: {dataset: {}}};
  new Function("document", "localStorage", "matchMedia", "addEventListener", SCRIPT)(document, {getItem: () => { throw new Error("x"); }}, () => { throw new Error("no"); }, () => {});
  assert.equal(document.documentElement.dataset.theme, "dark");
});
