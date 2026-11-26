"use strict";
// DocFrame (sutra_app/ui/static/js/doc_frame.js), D455: the team page's half of the document reader's messages. The page's theme as the
// reader takes it, the only downloads it accepts, and the answers to "ready" and "mode".
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const DF = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/doc_frame.js"));
const docWith = theme => ({documentElement: {dataset: theme === undefined ? {} : {theme}}});

test("the theme is the page's data-theme, light unless it is dark", () => {
  assert.equal(DF.theme(docWith("dark")), "dark");
  assert.equal(DF.theme(docWith("light")), "light");
  assert.equal(DF.theme(docWith(undefined)), "light");
  assert.equal(DF.theme(docWith("purple")), "light");
  assert.equal(DF.theme(null), "light");
});

test("only the run's own Markdown and Word files, from /api/artifact, are downloaded", () => {
  const ok = "/api/artifact?dept=abcd&run=j2-1&name=agent_prd.md";
  assert.equal(DF.downloadHref(ok), ok);
  assert.equal(DF.downloadHref("/api/artifact?name=agent_prd.docx"), "/api/artifact?name=agent_prd.docx");
  for (const bad of ["https://example.com/x.md", "/api/artifact?name=../secret.md", "/api/artifact?name=run.json", "/view?name=a.md",
    "//evil/api/artifact?name=a.md", "/api/artifact?name=a.md#x", "javascript:alert(1)", "", null, 42]) {
    assert.equal(DF.downloadHref(bad), null, String(bad));
  }
});

test("ready gets the theme and the mode kept for that file; mode is kept per file", () => {
  const state = {modes: {}};
  assert.deepEqual(DF.handle(state, {sutraDoc: 1, type: "ready", name: "a.md"}, "dark"), [{sutraDoc: 1, type: "theme", theme: "dark"}]);
  assert.deepEqual(DF.handle(state, {sutraDoc: 1, type: "mode", mode: "source", name: "a.md"}, "dark"), []);
  assert.deepEqual(DF.handle(state, {sutraDoc: 1, type: "ready", name: "a.md"}, "light"),
    [{sutraDoc: 1, type: "theme", theme: "light"}, {sutraDoc: 1, type: "mode", mode: "source"}]);
  assert.deepEqual(DF.handle(state, {sutraDoc: 1, type: "ready", name: "b.md"}, "light"), [{sutraDoc: 1, type: "theme", theme: "light"}]);
  DF.handle(state, {sutraDoc: 1, type: "mode", mode: "evil", name: "a.md"}, "light");
  assert.equal(state.modes["a.md"], "source", "an unknown mode is ignored");
  assert.deepEqual(DF.handle(state, {type: "ready", name: "a.md"}, "light"), [], "not a reader message");
  assert.deepEqual(DF.handle(state, null, "light"), []);
});
