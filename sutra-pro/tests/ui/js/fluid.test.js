"use strict";
// Fluid (sutra_app/ui/static/js/fluid.js): the parts that keep the page fluid (gap package fluid). Frame batching, signatures, the keyed list edit a
// chat transcript is drawn with, and the append-only split of a streamed reply. Run with: node --test tests/ui/js/fluid.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Fluid = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/fluid.js"));
const ChatMarkdown = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_markdown.js"));
const {createFrames, signature, changed, diffList, patchList, splitStream, streamParts} = Fluid;

// a frame source a test fires by hand
function manualFrames() {
  let next = 1;
  const queue = new Map();
  const f = createFrames({raf: cb => { const id = next++; queue.set(id, cb); return id; }, caf: id => queue.delete(id)});
  return {f, queued: () => queue.size, fire() { const all = Array.from(queue.values()); queue.clear(); all.forEach(cb => cb(0)); }};
}

/* ---------------------------------------------------------------- 1. frames */
test("1a. many schedules of one key are one run, with the last function, on the next frame", () => {
  const m = manualFrames();
  const seen = [];
  m.f.schedule("paint", () => seen.push("a"));
  m.f.schedule("paint", () => seen.push("b"));
  m.f.schedule("paint", () => seen.push("c"));
  assert.deepEqual(seen, [], "nothing runs before the frame");
  assert.equal(m.queued(), 1, "one frame is asked for, however many jobs");
  m.fire();
  assert.deepEqual(seen, ["c"]);
  assert.equal(m.f.pending(), 0);
});

test("1b. different keys all run, once each, in the order they were first scheduled", () => {
  const m = manualFrames();
  const seen = [];
  m.f.schedule("a", () => seen.push("a1"));
  m.f.schedule("b", () => seen.push("b1"));
  m.f.schedule("a", () => seen.push("a2"));
  m.fire();
  assert.deepEqual(seen, ["a2", "b1"]);
});

test("1c. a job scheduled while the frame runs waits for the next frame", () => {
  const m = manualFrames();
  const seen = [];
  m.f.schedule("a", () => { seen.push("a"); m.f.schedule("a", () => seen.push("again")); });
  m.fire();
  assert.deepEqual(seen, ["a"]);
  assert.equal(m.queued(), 1);
  m.fire();
  assert.deepEqual(seen, ["a", "again"]);
});

test("1d. cancel drops a job, flush runs the jobs now and the frame that was asked for is cancelled", () => {
  const m = manualFrames();
  const seen = [];
  m.f.schedule("a", () => seen.push("a"));
  m.f.schedule("b", () => seen.push("b"));
  m.f.cancel("a");
  m.f.flush();
  assert.deepEqual(seen, ["b"]);
  assert.equal(m.queued(), 0, "no stale frame is left behind");
  m.f.schedule("c", () => seen.push("c"));
  m.f.cancel("c");
  assert.equal(m.queued(), 0, "cancelling the last job cancels the frame");
});

test("1e. without any frame source a job runs at once (node, a stub DOM)", () => {
  const f = createFrames({raf: () => null});
  let n = 0;
  f.schedule("a", () => { n += 1; });
  assert.equal(n, 1);
  assert.equal(f.pending(), 0);
});

test("1f. a job that throws is reported and does not stop the others of its frame", () => {
  const m = manualFrames();
  const seen = [];
  const log = console.error;
  console.error = () => seen.push("logged");
  try {
    m.f.schedule("bad", () => { throw new Error("boom"); });
    m.f.schedule("good", () => seen.push("ran"));
    m.fire();
  } finally {
    console.error = log;
  }
  assert.deepEqual(seen, ["logged", "ran"]);
});

/* ---------------------------------------------------------------- 2. signatures */
test("2. a signature is equal for equal data and `changed` says so once, then keeps the new one", () => {
  assert.equal(signature({a: [1, 2]}), signature({a: [1, 2]}));
  assert.notEqual(signature({a: [1, 2]}), signature({a: [1, 3]}));
  assert.equal(signature(undefined), "");
  const loop = {};
  loop.me = loop;
  assert.equal(signature(loop), "", "a circular value has no signature");
  const holder = {};
  assert.equal(changed(holder, "k", {n: 1}), true, "the first look is a change");
  assert.equal(changed(holder, "k", {n: 1}), false, "the same data is not");
  assert.equal(changed(holder, "k", {n: 2}), true);
  assert.equal(changed(holder, "k", loop), true);
  assert.equal(changed(holder, "k", loop), true, "what cannot be fingerprinted is always a change");
});

/* ---------------------------------------------------------------- 3. the keyed list */
const item = (key, html) => ({key, html: html === undefined ? "<p>" + key + "</p>" : html});

test("3a. a list that grows at the end is only inserts", () => {
  const e = diffList([item("1"), item("2")], [item("1"), item("2"), item("3"), item("4")]);
  assert.deepEqual(e.replace, []);
  assert.equal(e.removeCount, 0);
  assert.deepEqual(e.insert.map(i => i.key), ["3", "4"]);
});

test("3b. a kept item whose html changed is replaced in place, at the front and at the back", () => {
  const e = diffList([item("1"), item("2"), item("3")], [item("1", "<p>new</p>"), item("2"), item("3", "<p>new</p>")]);
  assert.deepEqual(e.replace.map(r => r.index), [0, 2]);
  assert.equal(e.removeCount, 0);
  assert.equal(e.insert.length, 0);
});

test("3c. a stretch that went and one that came are a remove and an insert, the ends stay", () => {
  const e = diffList([item("1"), item("2"), item("3"), item("4")], [item("1"), item("9"), item("4")]);
  assert.equal(e.removeFrom, 1);
  assert.equal(e.removeCount, 2);
  assert.deepEqual(e.insert.map(i => i.key), ["9"]);
});

test("3d. the same list is not touched", () => {
  const list = [item("1"), item("2")];
  assert.equal(diffList(list, list.map(i => Object.assign({}, i))).touched, false);
  assert.equal(diffList([], []).touched, false);
});

// a container and a node factory that count what is done to the DOM
function fakeDom() {
  const log = [];
  const made = [];
  const container = {
    children: [], firstChild: null,
    replaceChild(n, old) { log.push("replace"); this.children[this.children.indexOf(old)] = n; },
    removeChild(n) { log.push("remove"); this.children.splice(this.children.indexOf(n), 1); },
    insertBefore(n, ref) { log.push("insert"); this.children.splice(this.children.indexOf(ref), 0, n); },
    appendChild(n) { log.push("append"); this.children.push(n); this.firstChild = this.children[0]; },
    set textContent(v) { log.push("clear"); this.children = []; this.firstChild = null; },
  };
  const make = html => { const n = {html, classList: {names: [], add(c) { this.names.push(c); }}}; made.push(n); return n; };
  return {container, make, log, made, htmls: () => container.children.map(n => n.html)};
}

test("3e. patchList draws a list, then adds only the new lines and leaves every node that did not change", () => {
  const d = fakeDom();
  let r = patchList(d.container, [item("1"), item("2")], {make: d.make, enter: "in"});
  assert.deepEqual(r, {changed: true, rebuilt: true, added: 2});
  assert.deepEqual(d.htmls(), ["<p>1</p>", "<p>2</p>"]);
  assert.deepEqual(d.made.map(n => n.classList.names), [[], []], "the first drawing does not animate its lines");
  const before = d.container.children.slice();
  d.log.length = 0;
  r = patchList(d.container, [item("1"), item("2"), item("3")], {make: d.make, enter: "in"});
  assert.deepEqual(r, {changed: true, rebuilt: false, added: 1});
  assert.deepEqual(d.log, ["append"], "one node was added and nothing else was touched");
  assert.equal(d.container.children[0], before[0]);
  assert.equal(d.container.children[1], before[1]);
  assert.deepEqual(d.container.children[2].classList.names, ["in"], "a new line enters");
});

test("3e2. a history loaded at once does not enter line by line: only an arrival does", () => {
  const d = fakeDom();
  patchList(d.container, [item("empty")], {make: d.make, enter: "in"});                    // "No messages yet" was on the page
  const many = Array.from({length: 30}, (_, i) => item("m" + i));
  patchList(d.container, many, {make: d.make, enter: "in"});
  assert.equal(d.container.children.length, 30);
  assert.deepEqual(d.container.children.filter(n => n.classList.names.includes("in")).length, 0, "thirty lines at once are a page, not thirty arrivals");
  patchList(d.container, many.concat([item("m30"), item("m31")]), {make: d.make, enter: "in"});
  assert.deepEqual(d.container.children.slice(30).map(n => n.classList.names), [["in"], ["in"]], "two new lines are arrivals");
  patchList(d.container, many.concat([item("m30"), item("m31")]).concat(Array.from({length: 4}, (_, i) => item("n" + i))), {make: d.make, enter: "in", enterMax: 3});
  assert.equal(d.container.children.slice(32).filter(n => n.classList.names.includes("in")).length, 0, "enterMax is the limit");
});

test("3f. the same items touch nothing", () => {
  const d = fakeDom();
  patchList(d.container, [item("1"), item("2")], {make: d.make});
  d.log.length = 0;
  assert.deepEqual(patchList(d.container, [item("1"), item("2")], {make: d.make}), {changed: false, rebuilt: false, added: 0});
  assert.deepEqual(d.log, []);
});

test("3g. a changed line is replaced alone; a line that went is removed; a line in the middle is inserted before the one after it", () => {
  const d = fakeDom();
  patchList(d.container, [item("1"), item("2"), item("3")], {make: d.make});
  const [n1, , n3] = d.container.children;
  d.log.length = 0;
  patchList(d.container, [item("1"), item("2", "<p>two!</p>"), item("3")], {make: d.make});
  assert.deepEqual(d.log, ["replace"]);
  assert.equal(d.container.children[0], n1);
  assert.equal(d.container.children[2], n3);
  d.log.length = 0;
  patchList(d.container, [item("1"), item("2", "<p>two!</p>")], {make: d.make});
  assert.deepEqual(d.log, ["remove"]);
  d.log.length = 0;
  patchList(d.container, [item("1"), item("1b"), item("2", "<p>two!</p>")], {make: d.make});
  assert.deepEqual(d.log, ["insert"]);
  assert.deepEqual(d.htmls(), ["<p>1</p>", "<p>1b</p>", "<p>two!</p>"]);
});

test("3h. a container somebody else wrote into is drawn again from nothing", () => {
  const d = fakeDom();
  patchList(d.container, [item("1"), item("2")], {make: d.make});
  d.container.children = [{html: "<p class=\"empty\">Loading</p>"}];          // innerHTML written by another part of the page
  d.log.length = 0;
  const r = patchList(d.container, [item("1"), item("2")], {make: d.make});
  assert.equal(r.rebuilt, true);
  assert.deepEqual(d.log.slice(0, 1), ["clear"]);
  assert.deepEqual(d.htmls(), ["<p>1</p>", "<p>2</p>"]);
});

test("3i. an empty list clears the container; an item with no html is left out", () => {
  const d = fakeDom();
  patchList(d.container, [item("1"), item("2", "")], {make: d.make});
  assert.deepEqual(d.htmls(), ["<p>1</p>"]);
  patchList(d.container, [], {make: d.make});
  assert.deepEqual(d.htmls(), []);
});

test("3j. an html that makes no element becomes a hidden placeholder, so the list and the DOM stay in step", () => {
  const d = fakeDom();
  const doc = {createElement: () => ({classList: {add() {}}})};
  d.container.ownerDocument = doc;
  patchList(d.container, [item("1"), item("2")], {make: html => (html.includes("2") ? null : d.make(html))});
  assert.equal(d.container.children.length, 2);
  assert.equal(d.container.children[1].hidden, true);
  d.log.length = 0;
  assert.equal(patchList(d.container, [item("1"), item("2")], {make: () => null}).changed, false);
});

/* ---------------------------------------------------------------- 4. a streamed reply */
test("4a. a block is done when the next one has begun, and the tail is what is still being written", () => {
  const s = splitStream("First paragraph.\n\nSecond");
  assert.deepEqual(s.blocks, []);                 // the second block's first line is short and unfinished: the first one may still be joined
  assert.equal(s.tail, "First paragraph.\n\nSecond");
  const long = splitStream("First paragraph.\n\nSecond paragraph is being writ");
  assert.deepEqual(long.blocks, ["First paragraph.\n\n"], "a first line of 14 characters cannot turn into a list marker any more");
  const t = splitStream("First paragraph.\n\nSecond paragraph is being written now\n");
  assert.deepEqual(t.blocks, ["First paragraph.\n\n"]);
  assert.equal(t.tail, "Second paragraph is being written now\n");
  assert.equal(t.blocks.join("") + t.tail, "First paragraph.\n\nSecond paragraph is being written now\n");
  assert.equal(t.settled, "First paragraph.\n\n".length);
});

test("4b. the blocks and the tail always add up to the text", () => {
  const texts = ["", "x", "a\n\nb\n\nc\n\nd", "# H\n\ntext here is long enough\n\n- a\n- b\n\n- c\n\nafter the list is long\n\n", "\n\n\nlead blank\n\nnext one is long line\n\nlast one is also a long line\n"];
  texts.forEach(t => {
    const s = splitStream(t);
    assert.equal(s.blocks.join("") + s.tail, t, JSON.stringify(t));
    assert.equal(s.settled, s.blocks.join("").length);
  });
});

test("4c. a list with blank lines between its items, a quote and a table are never cut apart", () => {
  const list = splitStream("Intro line that is long enough.\n\n- one\n\n- two\n\n  more of two\n\n- three\n\nOutro line that is long enough.\n\nAnd one more line to be the tail");
  assert.deepEqual(list.blocks, ["Intro line that is long enough.\n\n", "- one\n\n- two\n\n  more of two\n\n- three\n\n", "Outro line that is long enough.\n\n"]);
  const quote = splitStream("> a quote\n\n> goes on\n\nnext paragraph is long enough\n\ntail goes here, long enough");
  assert.equal(quote.blocks[0], "> a quote\n\n> goes on\n\n");
  const numbered = splitStream("1. one\n\n2. two\n\nnext paragraph is long enough\n\ntail goes here, long enough");
  assert.equal(numbered.blocks[0], "1. one\n\n2. two\n\n");
});

test("4d. the blank lines of a fenced code block do not end it, and an open fence is all tail", () => {
  const closed = splitStream("```js\nconst a = 1;\n\nconst b = 2;\n```\n\nafter the code, long enough\n\nand the tail is here now");
  assert.deepEqual(closed.blocks, ["```js\nconst a = 1;\n\nconst b = 2;\n```\n\n", "after the code, long enough\n\n"]);
  const open = splitStream("Intro line that is long enough.\n\n```js\nconst a = 1;\n\nconst b = 2;");
  assert.deepEqual(open.blocks, ["Intro line that is long enough.\n\n"], "the intro is done; the open fence, blank line and all, is the tail");
  assert.equal(open.tail, "```js\nconst a = 1;\n\nconst b = 2;");
  const open2 = splitStream("```js\nconst a = 1;\n\nconst b = 2;\n\nmore code");
  assert.deepEqual(open2.blocks, [], "an open fence is never split, whatever follows its blank lines");
  const tildes = splitStream("~~~\na\n\n~~~~\nb\n\n~~~~\n\nnext paragraph is long enough\n\ntail goes here, long enough");
  assert.ok(tildes.blocks[0].startsWith("~~~\na\n\n~~~~\nb"), "a fence of three is not closed by a longer one inside: only a run at least as long closes it");
});

test("4e. a first line that is only begun (a bare marker) does not settle the block before it", () => {
  assert.deepEqual(splitStream("- item one\n\n-").blocks, []);
  assert.deepEqual(splitStream("- item one\n\n- item two\n").blocks, [], "and when it turns out to be a list item the two stay one list");
});

test("4f. streamParts adds only the blocks that settled since the last drawing and starts again when the head was cut", () => {
  const a = streamParts("", "First paragraph.\n\nSecond paragraph is being written now\n");
  assert.deepEqual(a.add, ["First paragraph.\n\n"]);
  assert.equal(a.reset, false);
  assert.equal(a.settledText, "First paragraph.\n\n");
  const b = streamParts(a.settledText, "First paragraph.\n\nSecond paragraph is being written now\n\nThird paragraph is being written now");
  assert.deepEqual(b.add, ["Second paragraph is being written now\n\n"], "only the new block");
  assert.equal(b.tail, "Third paragraph is being written now");
  assert.equal(b.settledText, "First paragraph.\n\nSecond paragraph is being written now\n\n");
  const same = streamParts(b.settledText, "First paragraph.\n\nSecond paragraph is being written now\n\nThird paragraph is being written now, more");
  assert.deepEqual(same.add, []);
  assert.equal(same.reset, false);
  const cut = streamParts(b.settledText, "ond paragraph is being written now\n\nThird paragraph is being written now\n\nA fourth one, long enough\n\nand the tail here, long enough");
  assert.equal(cut.reset, true, "the text no longer starts with what was drawn");
  assert.equal(cut.settledText + cut.tail, "ond paragraph is being written now\n\nThird paragraph is being written now\n\nA fourth one, long enough\n\nand the tail here, long enough");
});

test("4g. the settled blocks rendered one by one read as the whole reply rendered at once", () => {
  const reply = "Here is the plan, in short.\n\n## Steps\n\n1. Do the first thing\n2. Do the second thing\n\n- also a note\n- and another\n\n```js\nconst a = 1;\n\nconst b = 2;\n```\n\nA closing paragraph with **bold** and `code`.\n";
  const whole = ChatMarkdown.render(reply);
  const s = splitStream(reply + "\nTail line, long enough to be the tail.");
  const strip = html => html.replace(/^<div class="cmd">/, "").replace(/<\/div>$/, "");
  const parts = s.blocks.map(b => strip(ChatMarkdown.render(b))).join("");
  // the settled blocks (all of the reply but its last paragraph's tail) read exactly as the start of the whole
  assert.ok(strip(whole).startsWith(parts), "block by block is the same markup as all at once");
  assert.ok(s.blocks.length >= 4);
});

test("4h. a list that begins in the middle of a group, a list item continued by a one-space or a tab indent: never cut apart", () => {
  const inGroup = splitStream("Steps:\n1. one\n\n   detail of one\n\n2. two\n\nAfter the list, long enough\n\nand the tail here, long enough");
  assert.deepEqual(inGroup.blocks, ["Steps:\n1. one\n\n   detail of one\n\n2. two\n\n", "After the list, long enough\n\n"], "the intro's list goes on after a blank line");
  const loose = splitStream("Options:\n- first\n\n- second\n\nAfter the list, long enough\n\nand the tail here, long enough");
  assert.equal(loose.blocks[0], "Options:\n- first\n\n- second\n\n");
  const tab = splitStream("- item\n\n\tcontinued with a tab\n\n- next\n\nAfter the list, long enough\n\nand the tail here, long enough");
  assert.equal(tab.blocks[0], "- item\n\n\tcontinued with a tab\n\n- next\n\n");
  const space = splitStream("- item\n\n continued with one space\n\nAfter the list, long enough\n\nand the tail here, long enough");
  assert.equal(space.blocks[0], "- item\n\n continued with one space\n\n");
  const apart = splitStream("A paragraph, long enough.\n\n- a list after it\n\nAnother paragraph, long enough.\n\n- a second list\n\nand the tail here, long enough");
  assert.equal(apart.blocks.length, 4, "a paragraph between two lists still ends the first one");
});

test("4i. drawn chunk by chunk (settled blocks kept, tail drawn again), a reply reads as the same text drawn at once, at every chunk", () => {
  const strip = html => (html.startsWith('<div class="cmd">') && html.endsWith("</div>") ? html.slice('<div class="cmd">'.length, html.length - "</div>".length) : html);
  const texts = [
    "Steps:\n1. one\n\n   detail of one\n\n2. two\n\nDone, and this paragraph is long enough.\n",
    "Options:\n- first\n\n- second\n\n- third\n\nThat is all of it, long enough.\n\nBye bye bye bye.",
    "+ plus item\nShort\n\n1.\n=====\n2. second\n\n2. second\n",
    "- item\n\n\ttabbed\n\n- next item\n\n> a quote\n\n> goes on\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```js\nlet a;\n\nlet b;\n```\n\nThe end, long enough.",
  ];
  texts.forEach(text => {
    [1, 3, 7].forEach(step => {
      let settled = "";
      let drawn = "";                                    // the html of the settled blocks, as the row keeps it
      for (let n = step; n <= text.length + step; n += step) {
        const now = text.slice(0, Math.min(n, text.length));
        const plan = streamParts(settled, now);
        if (plan.reset) drawn = "";
        plan.add.forEach(b => { drawn += strip(ChatMarkdown.render(b, {streaming: false})); });
        settled = plan.settledText;
        assert.equal(drawn + strip(ChatMarkdown.render(plan.tail, {streaming: true})), strip(ChatMarkdown.render(now, {streaming: true})), JSON.stringify(now));
      }
    });
  });
});
