"use strict";
// The project page's theme before the first paint (D383): the owner's own choice (light or dark) wins; with none, or "system", the computer's light or dark setting decides; a browser that
// cannot say gets dark. The script is read out of the page and run with fakes.
// Run with: node --test tests/ui/js/project_theme.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const HTML = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/pages/project.html"), "utf8");
const SCRIPT = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).find(code => code.includes("j2theme"));

function themeFor(stored, osLight, {throws = false} = {}) {
  const document = {documentElement: {dataset: {}}};
  const localStorage = {getItem: key => { if (throws) throw new Error("blocked"); return key === "j2theme" ? stored : null; }};
  const matchMedia = query => ({matches: query.includes("light") ? osLight : !osLight});
  new Function("document", "localStorage", "matchMedia", SCRIPT)(document, localStorage, matchMedia);
  return document.documentElement.dataset.theme;
}

test("the script is in the page", () => assert.ok(SCRIPT));

test("an owner's choice wins over the computer's setting", () => {
  assert.equal(themeFor("light", false), "light");
  assert.equal(themeFor("dark", true), "dark");
});

test("with no choice, or system, the page follows the computer's light or dark setting", () => {
  assert.equal(themeFor(null, true), "light");
  assert.equal(themeFor(null, false), "dark");
  assert.equal(themeFor("system", true), "light");
  assert.equal(themeFor("system", false), "dark");
  assert.equal(themeFor("anything else", true), "light");
});

test("a browser that blocks its storage gets dark", () => assert.equal(themeFor(null, true, {throws: true}), "dark"));
