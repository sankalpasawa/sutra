"use strict";
// Fluid.paintText (sutra_app/ui/static/js/fluid.js): one text block of the live chat drawn by appending (STR-10): settled blocks are never written again, only the tail is,
// an open code fence is ONE <pre> that grows, a table or a list that is not finished does not break the block, and highlighting happens once, on settle.
// Run with: node --test tests/ui/js/fluid_text.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const Fluid = require(path.join(JS, "fluid.js"));
const MD = require(path.join(JS, "chat_markdown.js"));
const {createDocument} = require("./helpers/fake_dom.js");

const render = (t, o) => MD.render(t, o);
function rig() {
  const doc = createDocument();
  const el = doc.createElement("div");
  const lit = [];
  const paint = (text, streaming) => Fluid.paintText(el, text, {render, streaming, highlight: pre => lit.push(pre)});
  return {doc, el, lit, paint, cmd: () => el.querySelector(".cmd")};
}
const kids = r => r.cmd().children;

test("an empty text draws nothing; the first text makes one .cmd wrapper", () => {
  const r = rig();
  assert.equal(r.paint("", true), false);
  assert.equal(r.el.children.length, 0);
  assert.equal(r.paint("Hello", true), true);
  assert.equal(r.el.querySelectorAll(".cmd").length, 1);
  assert.equal(r.cmd().textContent, "Hello");
});

test("settled blocks keep their nodes while the tail grows; a new block adds, nothing earlier is touched", () => {
  const r = rig();
  r.paint("First paragraph.\n\nSecond paragraph is", true);          // the second group is long enough that it can no longer turn into a list marker: the first has settled
  const first = kids(r)[0];
  assert.equal(first.textContent, "First paragraph.");
  r.paint("First paragraph.\n\nSecond paragraph grows", true);
  assert.equal(kids(r)[0], first);
  assert.equal(kids(r)[1].textContent, "Second paragraph grows");
  const second = kids(r)[1];
  r.paint("First paragraph.\n\nSecond paragraph grows.\n\nThird", true);
  assert.equal(kids(r)[0], first);
  assert.equal(kids(r).length, 3);
  assert.notEqual(kids(r)[1], undefined);
  assert.equal(kids(r)[1].textContent, "Second paragraph grows.");
  assert.equal(second.parentNode === null || second.parentNode === r.cmd(), true);
});

test("the same text drawn again changes nothing (no node is created)", () => {
  const r = rig();
  r.paint("A\n\nB", true);
  const made = r.doc.created;
  assert.equal(r.paint("A\n\nB", true), false);
  assert.equal(r.doc.created, made);
});

test("an open code fence is one <pre> that grows: the node is never recreated while it streams", () => {
  const r = rig();
  r.paint("Here is code:\n\n```js\nlet a = 1;", true);
  const pre = r.cmd().querySelector("pre");
  assert.ok(pre);
  const made = r.doc.created;
  r.paint("Here is code:\n\n```js\nlet a = 1;\nlet b = 2;\n\nlet c = 3;", true);       // a blank line inside the fence does not end it
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.equal(pre.textContent, "let a = 1;\nlet b = 2;\n\nlet c = 3;");
  assert.ok(r.doc.created - made <= 1, "only the text node of the code may be new");
  assert.equal(r.cmd().querySelectorAll("pre").length, 1);
  assert.deepEqual(r.lit, [], "no highlighting while it streams");
});

test("text before an open fence in the same group is drawn once and the fence still streams in one node", () => {
  const r = rig();
  r.paint("Intro line\n```\nx", true);
  const pre = r.cmd().querySelector("pre");
  r.paint("Intro line\n```\nx\ny\nz", true);
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.equal(pre.textContent, "x\ny\nz");
  assert.equal(r.cmd().children[0].textContent, "Intro line");
});

test("a fence that closes and settles keeps the node that streamed and is highlighted once", () => {
  const r = rig();
  r.paint("```js\nlet a = 1;\n  indented", true);
  const pre = r.cmd().querySelector("pre");
  r.paint("```js\nlet a = 1;\n  indented\n```", true);                                  // closed, not yet a settled block (it is the tail)
  assert.equal(r.cmd().querySelector("pre"), pre);
  r.paint("```js\nlet a = 1;\n  indented\n```\n\nAfter the code.", true);               // the next block begins: the fence settles
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.equal(r.cmd().querySelectorAll("pre").length, 1);
  assert.deepEqual(r.lit, [pre]);
  r.paint("```js\nlet a = 1;\n  indented\n```\n\nAfter the code. More.", true);
  assert.deepEqual(r.lit, [pre], "highlighted once");
});

test("the end of the turn settles the tail as a block; a fence that was streaming is kept and highlighted", () => {
  const r = rig();
  r.paint("Done:\n\n```\ncode here\n```", true);
  const pre = r.cmd().querySelector("pre");
  r.paint("Done:\n\n```\ncode here\n```", false);
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.deepEqual(r.lit, [pre]);
  assert.equal(r.paint("Done:\n\n```\ncode here\n```", false), false);
});

test("settling a text that has no fence redraws only its tail", () => {
  const r = rig();
  r.paint("One.\n\nTwo is quite a bit longer", true);
  const one = kids(r)[0];
  r.paint("One.\n\nTwo is quite a bit longer", false);
  assert.equal(kids(r)[0], one);
  assert.equal(r.cmd().textContent, "One.Two is quite a bit longer");
});

test("an unfinished table row is held until it is whole; the table redraws as the tail only", () => {
  const r = rig();
  r.paint("Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3", true);
  const before = kids(r)[0];
  assert.equal(before.textContent, "Before.");
  const table1 = r.cmd().querySelector("table");
  assert.ok(table1);
  assert.equal(r.cmd().querySelectorAll("tr").length, 2);                              // the header and the finished row; the half row waits
  r.paint("Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n", true);
  assert.equal(kids(r)[0], before);
  assert.equal(r.cmd().querySelectorAll("tr").length, 3);
});

test("a list that grows keeps one list, not a new one per item", () => {
  const r = rig();
  r.paint("Steps:\n\n- one\n- two", true);
  r.paint("Steps:\n\n- one\n- two\n- three", true);
  assert.equal(r.cmd().querySelectorAll("ul").length, 1);
  assert.equal(r.cmd().querySelectorAll("li").length, 3);
});

test("an unclosed bold or code span in the tail is shown as the text, then formed when it closes", () => {
  const r = rig();
  r.paint("This is **bold", true);
  assert.equal(r.cmd().textContent, "This is **bold");
  r.paint("This is **bold** now", true);
  assert.equal(r.cmd().querySelectorAll("strong").length, 1);
});

test("a reset (the text no longer starts with what was drawn) starts the block again", () => {
  const r = rig();
  r.paint("Old block.\n\nOld tail", true);
  r.paint("New text entirely", true);
  assert.equal(r.cmd().textContent, "New text entirely");
});

test("a 200 KB reply in 4,000 pieces: one tail redraw per piece at most, and no settled block is ever redrawn", () => {
  const r = rig();
  const para = "Paragraph of words that keeps going on and on for a while. ";
  let text = "";
  let redraws = 0;
  const nodes = new Map();
  for (let i = 0; i < 4000; i += 1) {
    text += i % 80 === 79 ? "\n\n" : para.slice(0, 50);
    const before = r.doc.elements;
    r.paint(text, true);
    if (r.doc.elements - before > 6) redraws += 1;                                      // a piece creates a few elements (the tail), never a block's worth
    kids(r).slice(0, -1).forEach((n, k) => { if (!nodes.has(k)) nodes.set(k, n); else assert.equal(nodes.get(k), n, "settled block " + k + " was recreated"); });
  }
  assert.ok(text.length > 150000);
  assert.equal(redraws, 0);
  assert.ok(kids(r).length > 40);
});

test("a closed fence followed by the start of the next paragraph keeps its <pre> (the next group is not complete yet, so the fence is still in the tail)", () => {
  const r = rig();
  r.paint("```js\nlet a = 1;\n```\n\nNext", true);
  const pre = r.cmd().querySelector("pre");
  r.paint("```js\nlet a = 1;\n```\n\nNext para", true);
  assert.equal(r.cmd().querySelector("pre"), pre);
  r.paint("```js\nlet a = 1;\n```\n\nNext paragraph with more words.", true);
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.equal(r.cmd().textContent.endsWith("Next paragraph with more words."), true);
  r.paint("```js\nlet a = 1;\n```\n\nNext paragraph with more words.\n\nAnd another one here.", true);
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.deepEqual(r.lit, [pre]);
});

test("two fences in one tail are two nodes that both survive, and a text between them is drawn between them", () => {
  const r = rig();
  r.paint("```a\none\n```\nbetween\n```b\ntwo", true);
  const pres = r.cmd().querySelectorAll("pre");
  assert.equal(pres.length, 2);
  r.paint("```a\none\n```\nbetween\n```b\ntwo\nmore", true);
  const again = r.cmd().querySelectorAll("pre");
  assert.equal(again[0], pres[0]);
  assert.equal(again[1], pres[1]);
  assert.equal(again[1].textContent, "two\nmore");
  assert.deepEqual(r.cmd().children.map(n => n.tagName), ["PRE", "P", "PRE"]);
});

test("a text segment that changes between two fences is drawn again in its own place", () => {
  const r = rig();
  r.paint("```a\none\n```\nbetwe\n```b\ntwo", true);
  r.paint("```a\none\n```\nbetween us\n```b\ntwo", true);
  assert.deepEqual(r.cmd().children.map(n => n.tagName), ["PRE", "P", "PRE"]);
  assert.equal(r.cmd().children[1].textContent, "between us");
});

// A reply cut into pieces at random places (the server's coalescer cuts wherever the timer falls): whatever the cut, the code fence is one node from its first appearance to the end,
// no matter whether the opener, the code, the closing line or the next paragraph arrives in one piece or in ten.
test("fuzz: 300 random cuts of a reply with a table, a list and a fence never recreate the fence", () => {
  const LONGER = "## Plan\n\nHere is the plan for the site, in short paragraphs that read well.\n\n- Home page with the menu\n- Opening hours and the map\n- A pre-order form for pickup\n\n" +
    "| Page | Owner | Status |\n|---|---|---|\n| Home | Ana | done |\n| Menu | Ben | draft |\n| Contact | Cy | todo |\n\n" +
    "```python\ndef price(item):\n    # the menu price in rupees\n    return item.base * 1.18\n```\n\n" +
    Array.from({length: 12}, (_, i) => "Paragraph " + (i + 1) + ": the menu lists coffee, tea and pastries, each with a short description and a price in rupees.").join("\n\n") + "\n\nThat is all.";
  const rnd = seed => { let x = seed; return () => { x = (x * 1664525 + 1013904223) % 4294967296; return x / 4294967296; }; };
  for (let seed = 1; seed <= 300; seed += 1) {
    const next = rnd(seed);
    const r = rig();
    let pre = null;
    let i = 0;
    while (i < LONGER.length) {
      i = Math.min(LONGER.length, i + 1 + Math.floor(next() * 60));
      r.paint(LONGER.slice(0, i), true);
      const p = r.cmd().querySelector("pre");
      if (p && !pre) pre = p;
      if (pre) assert.equal(p, pre, "seed " + seed + ": the fence was recreated at " + i);
    }
    r.paint(LONGER, false);
    assert.equal(r.cmd().querySelector("pre"), pre, "seed " + seed + ": the fence was recreated at settle");
    assert.equal(r.cmd().querySelectorAll("pre").length, 1);
    assert.equal(r.lit.length, 1, "seed " + seed + ": highlighted once");
    assert.equal(pre.textContent, "def price(item):\n    # the menu price in rupees\n    return item.base * 1.18");
  }
});

test("an open code fence ends at its last code line: the newline after it is not a line, so the <pre> is the height it keeps when the closing fence arrives", () => {
  const r = rig();
  r.paint("Code:\n\n```python\nx = 1\ny = 2\n", true);
  const pre = r.cmd().querySelector("pre");
  assert.equal(pre.textContent, "x = 1\ny = 2");
  r.paint("Code:\n\n```python\nx = 1\ny = 2\nz = 3", true);
  assert.equal(pre.textContent, "x = 1\ny = 2\nz = 3");
  r.paint("Code:\n\n```python\nx = 1\ny = 2\nz = 3\n``", true);                 // the closing fence being typed
  assert.equal(pre.textContent, "x = 1\ny = 2\nz = 3");
  r.paint("Code:\n\n```python\nx = 1\ny = 2\nz = 3\n```\n\nDone.", true);
  assert.equal(r.cmd().querySelector("pre"), pre);
  assert.equal(pre.textContent, "x = 1\ny = 2\nz = 3");
  r.paint("Code:\n\n```python\nx = 1\n\n", true);                                // a blank last code line is kept as the closed form keeps it
  assert.equal(r.cmd().querySelector("pre").textContent, "x = 1\n");
});
