"use strict";
// ChatMarkdown (sutra_app/ui/static/js/chat_markdown.js): a model's direct reply drawn as formatted text, escaped first, with no link and no
// HTML (package GAP-markdown; docs/design/ui.md section 4.3). Also the two places that use it: ChatView.transcript (a direct reply only) and
// ChatPill's streaming row. Re-expresses the intent of the old app's mdHtml tests (test_panel.js, test_md_decision_callout.py, test_j2ui_xss.py)
// without the link and the DECISION-callout branches, which are not ported.
// Run with: node --test tests/ui/js/chat_markdown.test.js
//
// Every output is parsed by the small XML reader below, so "well formed" is proved and the tests ask for elements instead of matching text.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const FILE = path.join(JS, "chat_markdown.js");
const ChatMarkdown = require(FILE);
const ChatView = require(path.join(JS, "chat_view.js"));
const ChatPill = require(path.join(JS, "chat_pill.js"));
const {render, hold, fenceAt} = ChatMarkdown;

/* ---------------------------------------------------------------- a small XML reader (as in chat_view.test.js) */
const ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"};
function decode(value, where) {
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(value), false, `a stray & in ${where}: ${value.slice(0, 80)}`);
  return value.replace(/&(?:amp|lt|gt|quot|#39);/g, m => ENTITY[m]);
}
function parse(markup) {
  const top = {tag: "#root", attrs: {}, children: [], content: []};
  const stack = [top];
  const TOKEN = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>|[^<]+/y;
  let pos = 0;
  while (pos < markup.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(markup);
    assert.ok(m && m.index === pos, `not well formed at ${pos}: ${markup.slice(pos, pos + 80)}`);
    pos = TOKEN.lastIndex;
    const here = stack[stack.length - 1];
    if (m[2] === undefined) {
      assert.equal(m[0].startsWith("<"), false, `a malformed tag: ${m[0].slice(0, 80)}`);
      here.content.push(decode(m[0], "text"));
      continue;
    }
    if (m[1] === "/") {
      assert.equal(here.tag, m[2], `</${m[2]}> closes <${here.tag}>`);
      stack.pop();
      continue;
    }
    const attrs = {};
    for (const a of m[3].matchAll(/([\w:.-]+)="([^"<]*)"/g)) {
      assert.equal(a[1] in attrs, false, `attribute ${a[1]} twice on <${m[2]}>`);
      attrs[a[1]] = decode(a[2], "attribute " + a[1]);
    }
    const node = {tag: m[2], attrs, children: [], content: [], parent: here};
    here.children.push(node);
    here.content.push(node);
    if (m[4] !== "/") stack.push(node);
  }
  assert.equal(stack.length, 1, "unclosed tags: " + stack.slice(1).map(n => n.tag).join(" "));
  return top;
}
const all = (node, out = []) => { node.children.forEach(c => { out.push(c); all(c, out); }); return out; };
const byTag = (node, tag) => all(node).filter(n => n.tag === tag);
const byClass = (node, name) => all(node).filter(n => (n.attrs.class || "").split(/\s+/).includes(name));
const textOf = node => node.content.map(c => (typeof c === "string" ? c : (c.tag === "br" ? "\n" : textOf(c)))).join("");
const dom = html => parse(html);
const md = (value, opts) => dom(render(value, opts));

// What render may write, and nothing else.
const TAGS = new Set(["div", "p", "br", "strong", "em", "del", "code", "pre", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "hr", "table",
  "thead", "tbody", "tr", "th", "td"]);
const CLASSES = new Set(["cmd", "cmd-p", "cmd-h", "cmd-l", "cmd-pre", "cmd-q", "cmd-hr", "cmd-tw", "cmd-t", "cmd-ac", "cmd-ar"]);
function onlyAuthored(html, where) {
  const doc = parse(html);
  all(doc).forEach(n => {
    assert.ok(TAGS.has(n.tag), `<${n.tag}> from ${where}`);
    Object.entries(n.attrs).forEach(([k, v]) => {
      if (k === "class") assert.ok(CLASSES.has(v), `class="${v}" from ${where}`);
      else assert.ok(k === "start" && n.tag === "ol" && /^\d+$/.test(v), `${k}="${v}" on <${n.tag}> from ${where}`);
    });
  });
  return doc;
}

/* ================================================================ escape first, no link, no html */
const HOSTILE = [
  "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", '"><svg onload=1>', "<<script>script>alert(1)<</script>/script>",
  "<sc<!---->ript>alert(1)</script>", "<!-- hidden --> shown", "<![CDATA[x]]>", "&lt;script&gt;", "\u0000<a>\u0007", "`<b>`", "**<i>**",
  "```html\n<script>x()</script>\n```", "| <b>x</b> | y |\n|---|---|\n| <img src=x> | z |", "> <script>q</script>", "- <a href=\"x\">a</a>",
  "# <h1>head</h1>", "[click](javascript:alert(1))", "[x](data:text/html,<script>alert(1)</script>)", "![i](https://img.example/x.png)",
  '<a href="https://evil.example">here</a>', "see https://example.com/a_b_c?x=1&y=2", "javascript:alert(1)", "*<em>*", "~~<del>~~", "\\<script>",
  "1. <x>\n   <y>", "<style>body{display:none}</style>", "<iframe src=//e.example>", "\" onclick=\"x", "' onmouseover='x", "<p class=\"cmd\">",
];

test("escape first: no markup from the text ever becomes an element or an attribute, and it is shown as text", () => {
  HOSTILE.forEach(input => {
    const html = render(input);
    onlyAuthored(html, JSON.stringify(input));
    assert.equal(/<(?:script|img|svg|a|iframe|style|i|b|h1)\b/i.test(html), false, input);
    assert.equal(/<[^>]*\son\w+=/i.test(html), false, input);
  });
  const shown = textOf(md("<script>alert(1)</script> & 'q' \"r\""));
  assert.equal(shown, "<script>alert(1)</script> & 'q' \"r\"");
  assert.equal(textOf(md("<!-- hidden --> shown")), "<!-- hidden --> shown");           // nothing is hidden from the owner
});

test("no link and no image: a markdown link, an image and a bare address stay plain text", () => {
  const input = "[label](https://u.example/p) ![alt](https://img.example/x.png) https://example.com <https://a.example>";
  const doc = onlyAuthored(render(input), "links");
  assert.equal(byTag(doc, "a").length + byTag(doc, "img").length, 0);
  assert.equal(textOf(doc), input);
  assert.equal(render(input).includes("href"), false);
  assert.equal(render(input).includes("src="), false);
});

test("control characters are dropped and any value is taken: numbers are digits, everything else is empty", () => {
  assert.equal(textOf(md("a\u0000b\u0008c\u001fd\u007fe\tf")), "abcde\tf");
  assert.equal(render(null), "");
  assert.equal(render(undefined), "");
  assert.equal(render({}), "");
  assert.equal(render([1]), "");
  assert.equal(render(""), "");
  assert.equal(render("   \n\n  "), "");
  assert.equal(textOf(md(42)), "42");
});

test("a fuzz of markdown marks always gives well formed markup made of the authored tags only", () => {
  const ALPHABET = ["*", "**", "_", "__", "~~", "`", "``", "```", "|", "-", "#", "> ", ">", " ", "  ", "\n", "\n\n", "a", "b", "1.", "2)", ":",
    "<", "&", "\\", "[", "](", ")", "---", "\t", "x|y", "|---|"];
  let seed = 7;
  const rand = n => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
  for (let k = 0; k < 3000; k += 1) {
    let s = "";
    const len = 1 + rand(40);
    for (let j = 0; j < len; j += 1) s += ALPHABET[rand(ALPHABET.length)];
    onlyAuthored(render(s), JSON.stringify(s));
    onlyAuthored(render(s, {streaming: true}), "streaming " + JSON.stringify(s));
  }
});

/* ================================================================ paragraphs and inline marks */
test("paragraphs: a blank line separates them, a single line break is a <br/>, and the whole reply sits in div.cmd", () => {
  const doc = md("One line\nnext line\n\nSecond paragraph");
  const root = doc.children[0];
  assert.equal(root.tag, "div");
  assert.equal(root.attrs.class, "cmd");
  const ps = byTag(doc, "p");
  assert.deepEqual(ps.map(textOf), ["One line\nnext line", "Second paragraph"]);
  assert.equal(render("x").includes("\n"), false);                                    // no raw line break outside <pre> (the bubble is pre-wrap)
});

test("inline marks: **bold**, __bold__, *italic*, _italic_, ~~struck~~ and `code`", () => {
  const doc = md("**b1** __b2__ *i1* _i2_ ~~s~~ `c`");
  assert.deepEqual(byTag(doc, "strong").map(textOf), ["b1", "b2"]);
  assert.deepEqual(byTag(doc, "em").map(textOf), ["i1", "i2"]);
  assert.deepEqual(byTag(doc, "del").map(textOf), ["s"]);
  assert.deepEqual(byTag(doc, "code").map(textOf), ["c"]);
});

test("a mark never reaches into code, and a mark around code or around another mark nests properly", () => {
  const code = md("`**not bold**` and `a*b*c`");
  assert.equal(byTag(code, "strong").length + byTag(code, "em").length, 0);
  assert.deepEqual(byTag(code, "code").map(textOf), ["**not bold**", "a*b*c"]);
  const around = md("**`file.py`** then **a *b* c** then *see **this** part*");
  const strongs = byTag(around, "strong");
  assert.equal(strongs[0].children[0].tag, "code");
  assert.equal(textOf(strongs[1]), "a b c");
  assert.equal(strongs[1].children[0].tag, "em");
  const outer = byTag(around, "em").find(e => e.children.some(c => c.tag === "strong"));
  assert.equal(textOf(outer), "see this part");
});

test("arithmetic, snake_case, a lone star and spaced stars stay as written", () => {
  ["2*3*4 = 24", "snake_case_name and __init__.py's file_name_here", "a * b * c", "**open only", "a ` b", "****", "_ _"].forEach(input => {
    const doc = md(input);
    assert.equal(byTag(doc, "em").length, 0, input);
    if (!input.includes("__init__")) assert.equal(byTag(doc, "strong").length, 0, input);
  });
  assert.equal(textOf(md("2*3*4 = 24")), "2*3*4 = 24");
});

test("code spans: a longer run holds a backtick, one space each side is trimmed, an unpartnered run stays", () => {
  assert.deepEqual(byTag(md("``a ` b``"), "code").map(textOf), ["a ` b"]);
  assert.deepEqual(byTag(md("`` `x` ``"), "code").map(textOf), ["`x`"]);
  assert.equal(byTag(md("use ``` inline"), "code").length, 0);
  assert.equal(textOf(md("use ``` inline")), "use ``` inline");
  assert.deepEqual(byTag(md("`<b>&</b>`"), "code").map(textOf), ["<b>&</b>"]);
});

test("a backslash keeps a mark as a mark", () => {
  const doc = md("\\*not italic\\* and \\_x\\_ and \\`y\\` and a\\\\b");
  assert.equal(byTag(doc, "em").length + byTag(doc, "code").length, 0);
  assert.equal(textOf(doc), "*not italic* and _x_ and `y` and a\\b");
  assert.equal(textOf(md("C:\\path\\file")), "C:\\path\\file");                       // a backslash before a letter is kept
});

test("a reply that starts with @name keeps it: it is not an agent's address", () => {
  assert.equal(textOf(md("@dataclass makes the class")), "@dataclass makes the class");
});

/* ================================================================ fenced code */
test("a fenced block is a code box: escaped, white space kept, info string dropped, never inside a <p>", () => {
  const doc = md("Before\n```js\nif (a < b && c) {\n\treturn \"x\";\n}\n\n\n```\nAfter");
  const pre = byTag(doc, "pre");
  assert.equal(pre.length, 1);
  assert.equal(pre[0].attrs.class, "cmd-pre");
  assert.equal(pre[0].children[0].tag, "code");
  assert.equal(textOf(pre[0]), "if (a < b && c) {\n\treturn \"x\";\n}");
  assert.deepEqual(byTag(doc, "p").map(textOf), ["Before", "After"]);
  all(doc).forEach(n => { if (n.tag === "pre" || n.tag === "ul" || n.tag === "table") assert.notEqual(n.parent.tag, "p"); });
});

test("~~~ fences, and a longer fence holds a shorter one (a fenced block about fences)", () => {
  assert.equal(textOf(byTag(md("~~~\n# not a heading\n- not a list\n~~~"), "pre")[0]), "# not a heading\n- not a list");
  const nested = md("````md\n```js\ncode\n```\n````\nafter");
  assert.equal(byTag(nested, "pre").length, 1);
  assert.equal(textOf(byTag(nested, "pre")[0]), "```js\ncode\n```");
  assert.deepEqual(byTag(nested, "p").map(textOf), ["after"]);
  assert.equal(byTag(md("```\na\n~~~\nb\n```"), "pre").length, 1);                     // a ~~~ line does not close a ``` fence
});

test("an unclosed fence runs to the end, so a streamed fence is code from its first line and equals the closed block", () => {
  const closed = render("Here:\n```py\nx = 1\ny = 2\n```");
  ["Here:\n```py\nx = 1\ny = 2", "Here:\n```py\nx = 1\ny = 2\n", "Here:\n```py\nx = 1\ny = 2\n```"].forEach(partialText => {
    assert.equal(render(partialText, {streaming: true}), closed, JSON.stringify(partialText));
  });
  const early = md("Intro paragraph\n```py\nx = 1", {streaming: true});
  assert.deepEqual(byTag(early, "p").map(textOf), ["Intro paragraph"]);                // the fence does not swallow the paragraph before it
  assert.equal(textOf(byTag(early, "pre")[0]), "x = 1");
});

test("an indented fence (in a list item) is code with the indent removed, and the list goes on with its number", () => {
  const doc = md("1. Install:\n   ```bash\n   npm i\n     --save\n   ```\n2. Run it");
  assert.equal(textOf(byTag(doc, "pre")[0]), "npm i\n  --save");
  const lists = byTag(doc, "ol");
  assert.equal(lists.length, 2);
  assert.equal(lists[1].attrs.start, "2");
});

/* ================================================================ headings, rules, quotes */
test("headings # to ###### are h3 to h6 inside a bubble; a closing run of # goes; #tag and seven # are not headings", () => {
  const doc = md("# One\n## Two ##\n### Three\n#### Four\n##### Five\n###### Six");
  assert.deepEqual(all(doc).filter(n => /^h\d$/.test(n.tag)).map(n => [n.tag, textOf(n)]),
    [["h3", "One"], ["h4", "Two"], ["h5", "Three"], ["h6", "Four"], ["h6", "Five"], ["h6", "Six"]]);
  ["#tag", "####### seven", "#", "#   "].forEach(input => assert.equal(all(md(input)).some(n => /^h\d$/.test(n.tag)), false, input));
  assert.equal(textOf(byTag(md("# C# is a language"), "h3")[0]), "C# is a language");
});

test("---, *** and ___ are rules, and - - - is a rule, not a list", () => {
  ["---", "***", "___", "- - -", " * * * "].forEach(input => {
    const doc = md("a\n\n" + input + "\n\nb");
    assert.equal(byTag(doc, "hr").length, 1, input);
    assert.equal(byTag(doc, "li").length, 0, input);
  });
  assert.equal(render("---").includes("<hr class=\"cmd-hr\"/>"), true);
});

test("quotes: > lines are one quote, may hold blocks, nest, and stop nesting at four", () => {
  const doc = md("> first\n> second\n>\n> - item\n\nafter");
  const q = byTag(doc, "blockquote");
  assert.equal(q.length, 1);
  assert.equal(textOf(byTag(q[0], "p")[0]), "first\nsecond");
  assert.equal(byTag(q[0], "li").length, 1);
  assert.equal(textOf(byTag(doc, "p").pop()), "after");
  const deep = md("> ".repeat(20) + "deep");
  assert.equal(byTag(deep, "blockquote").length, 4);
  assert.match(textOf(deep), /deep$/);
});

/* ================================================================ lists */
test("lists: - * + bullets, numbers with . or ), nested by indent of two or four spaces", () => {
  const doc = md("- a\n- b\n  - b1\n  - b2\n    1. deep\n- c\n\n1) one\n2) two");
  const uls = byTag(doc, "ul");
  assert.deepEqual(uls[0].children.map(li => li.content.filter(c => typeof c === "string").join("")), ["a", "b", "c"]);
  assert.equal(uls[1].parent.tag, "li");
  assert.equal(byTag(uls[1], "ol").length, 1);
  assert.equal(textOf(byTag(uls[1], "ol")[0]), "deep");
  const ols = byTag(doc, "ol");
  assert.equal(ols.length, 2);
  assert.equal(ols[1].parent.tag, "div");                                              // "1) one" after the bullets is a list of its own
  assert.deepEqual(byTag(md("* x\n+ y\n- z"), "li").map(textOf), ["x", "y", "z"]);
  assert.equal(byTag(md("    - four\n        - eight"), "ul").length, 2);
});

test("an ordered list keeps its first number, and blank lines between items keep one list and its numbering", () => {
  const doc = md("3. three\n\n4. four\n\n\n5. five");
  const ol = byTag(doc, "ol");
  assert.equal(ol.length, 1);
  assert.equal(ol[0].attrs.start, "3");
  assert.equal(byTag(ol[0], "li").length, 3);
  assert.equal("start" in byTag(md("1. a\n2. b"), "ol")[0].attrs, false);
});

test("a line indented under an item is that item's words; a plain line after the list is a paragraph", () => {
  const doc = md("1. **Step one**\n   what it does\n\n   and more\n2. Step two\nNot in the list");
  const items = byTag(doc, "li");
  assert.deepEqual(items.map(textOf), ["Step one\nwhat it does\n\nand more", "Step two"]);
  assert.deepEqual(byTag(doc, "p").map(textOf), ["Not in the list"]);
  assert.deepEqual(byTag(md("Steps:\n1. a\n2. b"), "p").map(textOf), ["Steps:"]);      // a list may follow a line without a blank line
});

test("a bullet after numbers at the same level is a new list, and lists nest at most six deep", () => {
  const doc = md("1. a\n- b");
  assert.equal(byTag(doc, "ol").length, 1);
  assert.equal(byTag(doc, "ul").length, 1);
  const ladder = Array.from({length: 30}, (_, k) => " ".repeat(2 * k) + "- level " + k).join("\n");
  const deep = md(ladder);
  const lists = byTag(deep, "ul");
  assert.equal(lists.filter(l => byTag(l, "ul").length === 0).length, 1);            // one innermost list: the ladder was not cut into pieces
  assert.equal(byTag(deep, "li").length, 30);                                         // every item is still there
  const nesting = l => (l ? (l.tag === "ul" ? 1 : 0) + nesting(l.parent) : 0);
  assert.equal(Math.max(...lists.map(nesting)), ChatMarkdown.MAX_LIST_DEPTH);
});

/* ================================================================ tables */
test("a table: a header row and a separator; cells carry inline marks; : aligns a column; it scrolls in its own wrapper", () => {
  const doc = md("Compare:\n| Name | Speed | Note |\n|:-----|------:|:----:|\n| **A** | 10 | `x` |\n| B | 2 | y |\n\nafter");
  const wrap = byClass(doc, "cmd-tw");
  assert.equal(wrap.length, 1);
  assert.equal(wrap[0].children[0].tag, "table");
  assert.deepEqual(byTag(doc, "th").map(textOf), ["Name", "Speed", "Note"]);
  assert.deepEqual(byTag(doc, "th").map(th => th.attrs.class), [undefined, "cmd-ar", "cmd-ac"]);
  assert.deepEqual(byTag(doc, "tr").slice(1).map(tr => byTag(tr, "td").map(textOf)), [["A", "10", "x"], ["B", "2", "y"]]);
  assert.equal(byTag(byTag(doc, "td")[0], "strong").length, 1);
  assert.deepEqual(byTag(doc, "p").map(textOf), ["Compare:", "after"]);
});

test("table rows are never padded, extra cells are dropped, and \\| is a pipe inside a cell", () => {
  const doc = md("| a | b |\n|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 |\n| x \\| y | z |");
  const rows = byTag(doc, "tbody")[0].children.map(tr => tr.children.map(textOf));
  assert.deepEqual(rows, [["1"], ["1", "2"], ["x | y", "z"]]);
  assert.equal(byTag(md("| a |\n|---|"), "tbody").length, 0);                            // a header with no body yet
});

test("no table without its separator, with a separator of another width, or with more than 50 columns", () => {
  assert.equal(byTag(md("| a | b |\n| c | d |"), "table").length, 0);
  assert.equal(byTag(md("| a | b |\n|---|"), "table").length, 0);
  assert.equal(byTag(md("| a | b |\n|---|-x-|"), "table").length, 0);
  const wide = "|" + "c|".repeat(51) + "\n|" + "-|".repeat(51);
  assert.equal(byTag(md(wide), "table").length, 0);
  const fifty = "|" + "c|".repeat(50) + "\n|" + "-|".repeat(50);
  assert.equal(byTag(md(fifty), "th").length, 50);
  assert.equal(byTag(md("a | b and | c"), "table").length, 0);                         // pipes in prose
});

/* ================================================================ streaming: hold and fenceAt */
test("hold: an unfinished table row and a header still waiting for its separator are held, so the table does not jump", () => {
  assert.equal(hold("Intro\n| a | b |"), "Intro\n");
  assert.equal(hold("Intro\n| a | b |\n"), "Intro\n");
  assert.equal(hold("Intro\n| a | b |\n|---|-"), "Intro\n");
  assert.equal(hold("| a | b |\n|---|---|\n"), "| a | b |\n|---|---|\n");
  assert.equal(hold("| a | b |\n|---|---|\n| 1 | 2"), "| a | b |\n|---|---|\n");
  assert.equal(hold("| a | b |\n|---|---|\n| 1 | 2 |\n"), "| a | b |\n|---|---|\n| 1 | 2 |\n");
  assert.equal(hold("| only a row"), "");
  const shown = md("Intro\n| a | b |\n|---|-", {streaming: true});
  assert.equal(byTag(shown, "table").length, 0);
  assert.equal(textOf(shown), "Intro");
  assert.equal(byTag(md("Intro\n| a | b |\n|---|---|", {streaming: true}), "table").length, 0);     // the separator may still grow a column
  const settled = md("Intro\n| a | b |\n|---|---|\n", {streaming: true});
  assert.equal(byTag(settled, "table").length, 1);
});

test("hold leaves everything else alone: prose with one pipe, a finished line, and any line inside a fence", () => {
  ["Use a | b here", "Some words\nmore", "done\n", "```\nls | grep x | wc", "```sh\nls | grep x |\n", ""].forEach(input => assert.equal(hold(input), input, input));
  assert.equal(render("Intro\n| a | b |", {streaming: false}).includes("| a | b |"), true);   // the stored reply shows everything
});

test("fenceAt names the fence left open at the end of a text", () => {
  assert.equal(fenceAt("x\n```js\ny"), "```");
  assert.equal(fenceAt("```\ny\n```"), "");
  assert.equal(fenceAt("~~~~\n~~~\n"), "~~~~");
  assert.equal(fenceAt("````\n```\n````"), "");
  assert.equal(fenceAt("use ```x``` inline"), "");
  assert.equal(fenceAt(null), "");
});

/* ================================================================ bounded on hostile input */
test("100 KB of backticks, pipes, stars, quotes and indents each renders well formed in well under a second", () => {
  const K = 100000;
  const shapes = {
    backticks: "`".repeat(K), "backtick pairs": "` ".repeat(K / 2), "fence lines": "```\n".repeat(K / 4), pipes: "|".repeat(K),
    "pipe table": "| a ".repeat(K / 8) + "|\n" + "|---".repeat(K / 8) + "|\n" + "| 1 ".repeat(K / 8),
    "a table of 5 000 rows": "| a | b |\n|---|---|\n" + "| x | y |\n".repeat(5000), stars: "*".repeat(K), "star words": "*a ".repeat(K / 3),
    "spaced stars": "* ".repeat(K / 2) + "x", underscores: "_".repeat(K), tildes: "~~".repeat(K / 2), escapes: "\\*".repeat(K / 2),
    brackets: "[](".repeat(K / 3), quotes: "> ".repeat(K / 2) + "x", "quote lines": "> x\n".repeat(K / 4), dashes: "-".repeat(K) + "x",
    "deep indent": " ".repeat(K) + "- x", "heading of spaces": "# a" + " ".repeat(K) + "b #", "list ladder": Array.from({length: 2000}, (_, k) => " ".repeat(k) + "- x").join("\n"),
    "mixed marks": "**_~~`|".repeat(K / 7), "lt and amp": "<&".repeat(K / 2), "long word": "w".repeat(K), newlines: "\n".repeat(K),
    "html comments": "<!--".repeat(K / 4), "numbered": "1. x\n".repeat(K / 5),
  };
  for (const [name, input] of Object.entries(shapes)) {
    const started = process.hrtime.bigint();
    const html = render(input, {streaming: name.length % 2 === 0});
    const ms = Number(process.hrtime.bigint() - started) / 1e6;
    assert.ok(ms < 1000, `${name}: ${ms.toFixed(0)} ms`);
    assert.ok(html.length < 30 * input.length + 100, `${name}: ${html.length} characters of html from ${input.length}`);
    parse(html);
  }
});

/* ================================================================ where it is used: the transcript and the streaming row */
const direct = (over = {}) => ({id: 7, session_id: "cs_x", role: "agent", who: "sutra", kind: "text", text: "Plan:\n1. one\n2. two\n```sh\nls\n```",
  card: null, pause: null, answered_by: null, task_id: null, state: "ok", at: "2026-11-07T10:00:00Z", turn: 6, ...over});
const session = {id: "cs_x", node_id: "web", kind: "department", title: "Web", writable: true, status: "active", connector: "claude", note: ""};

test("in a transcript only a model's direct reply (an agent text with turn set) is drawn as markdown", () => {
  globalThis.ChatMarkdown = ChatMarkdown;
  try {
    const doc = dom(ChatView.transcript(session, [direct(), direct({id: 8, turn: undefined}), direct({id: 9, role: "user", who: "user", turn: undefined}),
      direct({id: 10, kind: "error", text: "**Stopped** `x`"}), direct({id: 11, kind: "note", text: "1. a"}), direct({id: 12, who: "identity", turn: null})]));
    const bubbles = doc.children;
    assert.deepEqual(bubbles.map(b => b.attrs["data-id"]), ["7", "8", "9", "10", "11", "12"]);
    const reply = bubbles[0];
    assert.equal(byClass(reply, "cmd").length, 1);
    assert.equal(byTag(reply, "ol").length, 1);
    assert.equal(textOf(byTag(reply, "pre")[0]), "ls");
    assert.equal(textOf(byTag(reply, "small")[0]), "Sutra");
    bubbles.slice(1).forEach(b => {
      assert.equal(byClass(b, "cmd").length, 0, b.attrs["data-id"]);
      assert.equal(byTag(b, "pre").length + byTag(b, "ol").length, 0, b.attrs["data-id"]);
    });
    assert.equal(byTag(bubbles[3], "b").length, 1);                                     // the error line keeps safeText's three marks
  } finally {
    delete globalThis.ChatMarkdown;
  }
});

test("a direct reply keeps a leading @name, and without chat_markdown.js on the page it falls back to safeText", () => {
  globalThis.ChatMarkdown = ChatMarkdown;
  try {
    assert.match(textOf(dom(ChatView.transcript(session, [direct({text: "@dataclass works"})]))), /@dataclass works$/);
  } finally {
    delete globalThis.ChatMarkdown;
  }
  const plain = dom(ChatView.transcript(session, [direct()]));
  assert.equal(byClass(plain, "cmd").length, 0);
  assert.equal(textOf(plain.children[0]).endsWith("Plan:\n1. one\n2. two\n```sh\nls\n```"), true);
});

test("the hostile corpus through a direct reply stays escaped in the transcript", () => {
  globalThis.ChatMarkdown = ChatMarkdown;
  try {
    HOSTILE.forEach(input => {
      const html = ChatView.transcript(session, [direct({text: input})]);
      parse(html);
      assert.equal(/<(?:script|img|svg|a|iframe|style)\b/i.test(html), false, input);
    });
  } finally {
    delete globalThis.ChatMarkdown;
  }
});

test("the streaming row draws the reply so far as markdown: an open fence is code, a half row is held, the text is escaped", () => {
  const row = (t, who) => dom(ChatPill.indicator({active: true, text: t}, who || "claude"));
  const code = row("Run:\n```sh\nnpm i <pkg>");
  assert.equal(textOf(byTag(code, "small")[0]), "Claude is writing\u2026");
  assert.equal(textOf(byTag(code, "pre")[0]), "npm i <pkg>");
  assert.deepEqual(byTag(code, "p").map(textOf), ["Run:"]);
  const table = row("Compare:\n| a | b |\n|--");
  assert.equal(byTag(table, "table").length, 0);
  assert.equal(textOf(byClass(table, "cstream-text")[0]), "Compare:");
  const held = row("| a | b");
  assert.equal(byClass(held, "cstream-text").length, 0);                               // nothing to show yet: only who is writing
  assert.equal(ChatPill.indicator({active: true, text: "<script>x</script>"}, "").includes("<script>"), false);
});

test("a long stream cut to its last characters starts at a line and keeps an open fence open", () => {
  let s = ChatPill.idle();
  s = ChatPill.partial(s, {delta: "Intro\n```js\n"});
  for (let k = 0; k < 400; k += 1) s = ChatPill.partial(s, {delta: "const line" + k + " = " + k + ";\n"});
  assert.ok(s.text.length <= 4000 + 4, String(s.text.length));
  assert.ok(s.text.startsWith("```\n"), s.text.slice(0, 20));
  assert.equal(byTag(dom(ChatPill.indicator(s, "claude")), "p").length, 0);             // all of it is still code
  s = ChatPill.partial(s, {delta: "```\nAfter the code\n"});
  assert.equal(byTag(dom(ChatPill.indicator(s, "claude")), "p").length, 1);             // the fence closed: the prose after it is prose
  for (let k = 0; k < 600; k += 1) s = ChatPill.partial(s, {delta: "words " + k + "\n"});
  assert.equal(s.text.startsWith("```"), false);
  assert.match(s.text, /^words \d+\n/);
  assert.equal(ChatPill.partial(ChatPill.idle(), {delta: "x".repeat(9000)}).text.length, 4000);
});

/* ================================================================ how the file loads */
test("the script loads as a classic script with one global and no other name, and as a module", () => {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FILE, "utf8"), sandbox);
  assert.deepEqual(Object.keys(sandbox), ["globalThis", "ChatMarkdown"]);
  assert.equal(sandbox.ChatMarkdown.render("**x**"), '<div class="cmd"><p class="cmd-p"><strong>x</strong></p></div>');
  assert.deepEqual(Object.keys(ChatMarkdown).sort(), Object.keys(sandbox.ChatMarkdown).sort());
});

test("the source is plain ASCII and makes no route, no URL and no DOM call", () => {
  const source = fs.readFileSync(FILE, "utf8");
  assert.equal(/[^\x00-\x7f]/.test(source), false);
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.equal(/document|window|innerHTML|fetch|XMLHttpRequest|https?:|\/api\//.test(code), false);
});
