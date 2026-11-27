"use strict";
// E34: the page's two text cleaners, `plain` (question cards) and `mapClean` (the Map), drop an agent @tag only at the start of a
// word, so an email address keeps its domain. Both are taken from the ported page itself. Run with: node --test tests/ui/js/tag_strip.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PAGE = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/pages/j2_ui.html"), "utf8");
// the text from `from` to the end of the line `lines` lines after it, as the page has it
const slice = (from, lines) => {
  let end = PAGE.indexOf(from);
  assert.ok(end >= 0, `${from} is in the page`);
  const start = end;
  for (let i = 0; i <= lines; i++) end = PAGE.indexOf("\n", end + 1);
  return PAGE.slice(start, end);
};
const ctx = vm.createContext({});
const PLAIN_TO = PAGE.slice(PAGE.indexOf("const AGENT = "), PAGE.indexOf("const plain = ")).split("\n").length;      // AGENT, END, TECH, PLAIN, plain (two lines)
vm.runInContext(slice("const AGENT = ", PLAIN_TO) + "\n" + slice("const mapClean = ", 0) + "\nthis.cleaners = {plain, mapClean};", ctx);
const {plain, mapClean} = ctx.cleaners;

for (const [name, clean] of [["plain", plain], ["mapClean", mapClean]]) {
  test(`${name}: an agent @tag at the start of a word is dropped`, () => {
    assert.equal(clean("@Requester hi"), name === "plain" ? "Hi" : "hi");      // plain capitalises a sentence start
    assert.equal(clean("@Adaptation: done"), name === "plain" ? "Done" : "done");
  });
  test(`${name}: an email address stays whole`, () => {
    assert.equal(clean("mail ana.lee@example.ai"), name === "plain" ? "Mail ana.lee@example.ai" : "mail ana.lee@example.ai");
    assert.equal(clean("@Requester mail a1@b-c.io"), name === "plain" ? "Mail a1@b-c.io" : "mail a1@b-c.io");
  });
}
