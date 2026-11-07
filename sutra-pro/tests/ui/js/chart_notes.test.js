"use strict";
// ChartNotes (sutra_app/ui/static/js/chart_notes.js): the Chart notes panel of the Org chart pane (gap package chart-insight): names not ids, one
// "Nothing flagged" line when there is nothing, a button for each name, the sentence to say, every word of the wire escaped, well formed markup.
// Run with: node --test tests/ui/js/chart_notes.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChartNotes = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chart_notes.js"));
const {html, sentenceHtml, addressOf, INFO} = ChartNotes;

// A reader that proves the markup is well formed: every tag closes in order, no stray &, no raw < or > in text.
function wellFormed(markup) {
  const stack = [];
  const TOKEN = /<(\/?)([A-Za-z][\w-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|[^<]+/y;
  let pos = 0;
  while (pos < markup.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(markup);
    assert.ok(m && m.index === pos, `not well formed at ${pos}: ${markup.slice(pos, pos + 60)}`);
    pos = TOKEN.lastIndex;
    if (m[2] === undefined) {
      assert.equal(/&(?!(?:amp|lt|gt|quot|#39|ldquo|rdquo);)/.test(m[0]), false, "a stray & in " + m[0].slice(0, 60));
    } else if (m[1] === "/") {
      assert.equal(stack.pop(), m[2]);
    } else if (m[4] !== "/") {
      stack.push(m[2]);
    }
  }
  assert.deepEqual(stack, []);
}

const OVERLAP = {kind: "overlap", nodes: [{id: "menu-page", label: "Menu page"}, {id: "pages", label: "Pages"}],
  words: "Menu page and Pages look alike (45% of their words)", say: "merge Pages into Menu page"};
const NO_PURPOSE = {kind: "no_purpose", nodes: [{id: "reviews", label: "Reviews"}], words: "Reviews has no purpose written", say: "change the purpose of Reviews to ..."};
const QUIET = {kind: "quiet", nodes: [{id: "florist-site", label: "Florist site"}], words: "Florist site has had nothing for 90 days", say: ""};

test("a note says its words in names, with a button on each name that opens its card", () => {
  const out = sentenceHtml(OVERLAP);
  assert.equal(out, '<button type="button" class="linkbtn ocnodebtn" data-note-node="menu-page">Menu page</button> and ' +
    '<button type="button" class="linkbtn ocnodebtn" data-note-node="pages">Pages</button> look alike (45% of their words)');
  assert.doesNotMatch(out, /\bchg-|org_|\bkind\b/);
});

test("the panel lists the notes, the sentence to say, and that they change nothing", () => {
  const out = html({notes: [OVERLAP, NO_PURPOSE, QUIET], total: 3});
  wellFormed(out);
  assert.match(out, /^<h4>Chart notes<\/h4><ul class="ocnotelist">/);
  assert.equal((out.match(/<li class="ocnote /g) || []).length, 3);
  assert.match(out, /<li class="ocnote k-overlap">.*<span class="ocsay">Say: &ldquo;merge Pages into Menu page&rdquo;<\/span><\/li>/);
  assert.match(out, /Say: &ldquo;change the purpose of Reviews to \.\.\.&rdquo;/);
  assert.equal((out.match(/class="ocsay"/g) || []).length, 2, "a quiet team is information only: no sentence");
  assert.ok(out.endsWith('<p class="ocinfo">' + INFO + "</p>"));
});

test("with nothing flagged the panel says so in one line, as the old Health panel did", () => {
  const out = html({notes: [], total: 0});
  assert.equal(out, '<h4>Chart notes</h4><p class="ocnone">Nothing flagged</p>');
  wellFormed(out);
});

test("notes that were cut are counted, and an answer that is not one draws nothing", () => {
  assert.match(html({notes: [OVERLAP], total: 5}), /<p class="ocmore">4 more notes are not shown\.<\/p>/);
  assert.match(html({notes: [OVERLAP], total: 2}), /1 more note is not shown\./);
  [null, undefined, "x", 3, [], {}, {notes: "x"}].forEach(v => assert.equal(html(v), ""));
});

test("a label that is not in the words stays plain text, and an id that is not an id never becomes a button", () => {
  const odd = {kind: "overlap", nodes: [{id: "a", label: "Gone"}, {id: "bad id", label: "Pages"}], words: "Menu and Pages look alike", say: ""};
  assert.equal(sentenceHtml(odd), "Menu and Pages look alike");
  assert.equal(sentenceHtml({words: "Only words"}), "Only words");
  assert.equal(sentenceHtml(null), "");
});

test("every word of the wire is escaped", () => {
  const bad = `<script>alert("x")</script> & 'q'`;
  const note = {kind: bad, nodes: [{id: "x1", label: bad}], words: "The purpose of " + bad + " only repeats its name", say: bad};
  const out = html({notes: [note], total: 1});
  assert.equal(out.includes("<script"), false);
  wellFormed(out);
  assert.match(out, /k-other/);
  const hostile = {kind: "quiet", nodes: [{id: '"><img src=x onerror=1>', label: "Web"}], words: "Web has had nothing", say: ""};
  assert.equal(html({notes: [hostile], total: 1}).includes("<img"), false);
});

test("addressOf names the team and the divisions down to a deep node, and nothing for a team", () => {
  const nodes = [{id: "root", label: "Root", parent: null, kind: "root"}, {id: "bakery", label: "Bakery site", parent: "root", kind: "department"},
    {id: "menu", label: "Menu", parent: "bakery", kind: "division"}, {id: "cakes", label: "Cakes", parent: "menu", kind: "division"}];
  assert.equal(addressOf(nodes, "cakes"), "Bakery site > Menu > Cakes");
  assert.equal(addressOf(nodes, "menu"), "Bakery site > Menu");
  assert.equal(addressOf(nodes, "bakery"), "");
  assert.equal(addressOf(nodes, "root"), "");
  assert.equal(addressOf(nodes, "nope"), "");
  assert.equal(addressOf(null, "x"), "");
  const loop = [{id: "a", label: "A", parent: "b", kind: "division"}, {id: "b", label: "B", parent: "a", kind: "division"}];
  assert.equal(addressOf(loop, "a"), "B > A");                                  // a loop of parents ends, it never hangs
});
