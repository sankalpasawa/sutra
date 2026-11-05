"use strict";
// GraphRender (sutra_app/ui/static/js/graph_render.js): the status look and words of J2, the function chip with its atom counts, the SVG
// string of a layout, the outline list and the header counts. docs/design/ui.md sections 3.3, 6.1, 7 and 10; S2-models-03, S3-web-13, S4-fnodes-10.
// Run with: node --test tests/ui/js/graph_render.test.js
//
// The markup is parsed by a small XML reader below (balanced tags, quoted attributes, no raw "<", no stray "&"), so "well formed" is
// proved and the tests can ask for elements instead of matching text.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const RENDER_FILE = path.join(JS, "graph_render.js");
const LAYOUT_FILE = path.join(JS, "graph_layout.js");
const RENDER_CODE = fs.readFileSync(RENDER_FILE, "utf8");
const LAYOUT_CODE = fs.readFileSync(LAYOUT_FILE, "utf8");
const GraphLayout = require(LAYOUT_FILE);
const GraphRender = require(RENDER_FILE);
const {svg, outline, summary, statusLook, statusWord, chipText, kindWord, edgeLook, textWidth, fit, PERSONA} = GraphRender;

const DOT = " \u00b7 ";
const ELLIPSIS = "\u2026";
const FUNCTIONS = ["identity", "adaptation", "priority", "coordination", "audit"];
const NINE = ["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"];

/* ---------------------------------------------------------------- helpers */
const plain = value => JSON.parse(JSON.stringify(value));
function deepFreeze(value) {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

// ---- a small XML reader
const ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"};
function decode(text, where) {
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(text), false, `a stray & in ${where}: ${text.slice(0, 80)}`);
  return text.replace(/&(?:amp|lt|gt|quot|#39);/g, m => ENTITY[m]);
}
function parse(markup) {
  const root = {tag: "#root", attrs: {}, children: [], text: "", content: []};
  const stack = [root];
  const TOKEN = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>|[^<]+/y;
  let pos = 0;
  while (pos < markup.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(markup);
    assert.ok(m && m.index === pos, `not well formed at ${pos}: ${markup.slice(pos, pos + 80)}`);
    pos = TOKEN.lastIndex;
    const top = stack[stack.length - 1];
    if (m[2] === undefined) {
      assert.equal(m[0].startsWith("<"), false, `a malformed tag: ${m[0].slice(0, 80)}`);
      const piece = decode(m[0], "text");
      top.text += piece;
      top.content.push(piece);
      continue;
    }
    if (m[1] === "/") {
      assert.equal(top.tag, m[2], `</${m[2]}> closes <${top.tag}>`);
      stack.pop();
      continue;
    }
    const attrs = {};
    for (const a of m[3].matchAll(/([\w:.-]+)="([^"<]*)"/g)) {
      assert.equal(a[1] in attrs, false, `attribute ${a[1]} twice on <${m[2]}>`);
      attrs[a[1]] = decode(a[2], "attribute " + a[1]);
    }
    const node = {tag: m[2], attrs, children: [], text: "", content: []};
    top.children.push(node);
    top.content.push(node);
    if (m[4] !== "/") stack.push(node);
  }
  assert.equal(stack.length, 1, "unclosed tags: " + stack.slice(1).map(n => n.tag).join(" "));
  return root;
}
const walk = (node, fn) => { fn(node); node.children.forEach(c => walk(c, fn)); };
function select(node, selector) {          // tag.class.class[attr][attr=value], one compound, no combinators
  const m = /^([a-zA-Z]*)((?:\.[\w-]+)*)((?:\[[\w:.-]+(?:=[^\]]*)?\])*)$/.exec(selector);
  assert.ok(m, "selector " + selector);
  const classes = m[2].split(".").filter(Boolean);
  const attrs = [...m[3].matchAll(/\[([\w:.-]+)(?:=([^\]]*))?\]/g)].map(a => [a[1], a[2]]);
  const out = [];
  walk(node, n => {
    if (n.tag === "#root") return;
    if (m[1] !== "" && n.tag !== m[1]) return;
    const have = (n.attrs.class || "").split(/\s+/);
    if (!classes.every(c => have.includes(c))) return;
    if (!attrs.every(([k, v]) => (v === undefined ? k in n.attrs : n.attrs[k] === v))) return;
    out.push(n);
  });
  return out;
}
const one = (node, selector) => { const found = select(node, selector); assert.equal(found.length, 1, `${selector}: ${found.length} found`); return found[0]; };
const textOf = (node, skip = () => false) => node.content.map(c => (typeof c === "string" ? c : skip(c) ? "" : textOf(c, skip))).join("");
const kidsOf = (node, tag) => node.children.filter(c => c.tag === tag);
const classOf = node => (node.attrs.class || "").split(/\s+/).filter(Boolean);
// the elements that hold no words of their own: whatever text is found directly in them is stray
const HOLLOW = new Set(["svg", "defs", "g", "marker", "linearGradient", "stop", "path", "rect", "circle", "ul", "li", "button"]);
function assertNoStrayText(node) {
  walk(node, n => { if (HOLLOW.has(n.tag)) assert.equal(n.text, "", `stray text in <${n.tag}>: ${n.text.slice(0, 40)}`); });
}
// the one element a view hands back, with nothing before or after it and no stray text inside it
function whole(html) {
  const doc = parse(html);
  assert.equal(doc.text, "", "nothing outside the element");
  assert.equal(doc.children.length, 1, "one element");
  assertNoStrayText(doc.children[0]);
  return doc.children[0];
}
const drawing = (L, v) => whole(svg(L, v));
const listing = html => whole(html);

// ---- fixtures: the department of the design's examples
const FN_LABEL = {identity: "Identity", adaptation: "Adaptation", priority: "Priority", coordination: "Coordination", audit: "Audit"};
const STATS = {calls: 12, seconds: 41.0, tokens_in: 7000, tokens_out: 2120, atoms_open: 1, atoms_closed: 5, atoms_failed: 1, atoms_total: 8};
const rawNode = (id, kind = "step", extra = {}) => ({id, kind, label: id, status: "idle", detail: "", meta: {}, ...extra});
const edge = (src, dst, kind = "contains", label = "") => ({src, dst, kind, label});
function department(id, status = "idle") {
  const nodes = [rawNode(id, "department", {label: id[0].toUpperCase() + id.slice(1), status, detail: status === "waiting_on_you" ? "Identity asks about the menu" : ""})];
  const edges = [];
  FUNCTIONS.forEach((fn, i) => {
    nodes.push(rawNode(id + "." + fn, "function", {label: FN_LABEL[fn], fn, dept_id: id, status: i === 0 ? status : "idle",
      meta: {stats: {...STATS}, wait_on: i === 0 && status === "waiting_on_you" ? "you" : null}}));
    edges.push(edge(id, id + "." + fn, "has_function"));
  });
  nodes.push(rawNode("s-" + id, "step", {label: "Coffee shop landing page", step_ref: "task", dept_id: id, status: "running"}));
  edges.push(edge(id, "s-" + id, "has_step"));
  return {nodes, edges};
}
function sampleView() {
  const web = department("web", "waiting_on_you");
  const support = department("support", "running");
  return {version: 42, chart_version: 2,
    nodes: [rawNode("root", "root", {label: "Root", status: "running"}), ...web.nodes, ...support.nodes],
    edges: [edge("root", "web"), edge("root", "support"), ...web.edges, ...support.edges,
      edge("web.identity", "web.adaptation", "handoff"), edge("web.adaptation", "web.identity", "handoff"),
      edge("web.audit", "web.identity", "handoff"),
      edge("web.identity", "web.coordination", "speaks_to", "3"), edge("web.coordination", "web.identity", "speaks_to", "2"),
      edge("web.audit", "web.priority", "depends_on", "revises"), edge("web.priority", "web.adaptation", "depends_on", "reads"),
      edge("web.identity", "s-web", "step"), edge("web.audit", "s-web", "mentions", "x")]};
}
const sampleGraph = () => GraphLayout.validate(sampleView()).graph;
const sampleLayout = () => GraphLayout.layout(sampleGraph());
const fnNode = (over = {}) => ({id: "web.identity", kind: "function", fn: "identity", label: "Identity", status: "idle", meta: {stats: {...STATS}, wait_on: null}, ...over});

// a layout made by hand, for the cases that GraphLayout would never produce
const hand = (nodes, links = [], edges = [], extra = {}) => ({nodes, links, edges, width: 400, height: 300, warnings: [], ...extra});
const box = (id, kind = "step", extra = {}) => ({id, kind, label: id, status: "idle", detail: "", meta: {}, x: 10, y: 20, w: 140, h: 40, depth: 0, parent: null, ...extra});

/* ---------------------------------------------------------------- loading */
test("loads with require and exposes the interface of the design", () => {
  assert.deepEqual(Object.keys(GraphRender).sort(), ["PERSONA", "chipText", "edgeLook", "fit", "kindWord", "outline", "statusLook", "statusWord", "summary", "svg", "textWidth"]);
  assert.deepEqual(plain(PERSONA), {identity: "Client Lead", adaptation: "Strategist", priority: "Prioritiser", coordination: "Scheduler", audit: "Quality Reviewer"});
  assert.ok(Object.isFrozen(PERSONA));
  assert.throws(() => { PERSONA.identity = "x"; }, TypeError);
});

test("loads as a classic script with one global, GraphRender, and finds GraphLayout whichever file was loaded first", () => {
  for (const order of [[LAYOUT_CODE, RENDER_CODE], [RENDER_CODE, LAYOUT_CODE]]) {
    const sandbox = vm.createContext({});
    order.forEach(code => vm.runInContext(code, sandbox));
    assert.deepEqual(Object.keys(sandbox).sort(), ["GraphLayout", "GraphRender"]);
    const g = sandbox.GraphLayout.validate(sampleView()).graph;
    assert.equal(sandbox.GraphRender.svg(sandbox.GraphLayout.layout(g), {uid: "v"}), svg(sampleLayout(), {uid: "v"}));
    assert.equal(sandbox.GraphRender.outline(g), outline(sampleGraph()));
    assert.deepEqual(plain(sandbox.GraphRender.summary(g)), plain(summary(sampleGraph())));
  }
});

test("outline and summary say plainly that graph_layout.js was not loaded; svg needs nothing", () => {
  const sandbox = vm.createContext({});
  vm.runInContext(RENDER_CODE, sandbox);
  assert.deepEqual(Object.keys(sandbox), ["GraphRender"]);
  const message = "GraphRender needs GraphLayout: load graph_layout.js before calling outline or summary";
  for (const call of [() => sandbox.GraphRender.outline({nodes: []}), () => sandbox.GraphRender.summary({nodes: []})]) {
    assert.throws(call, error => error.name === "Error" && error.message === message);       // (the error is from the sandbox's realm: no instanceof)
  }
  assert.equal(typeof sandbox.GraphRender.svg(hand([])), "string");
  assert.equal(sandbox.GraphRender.chipText({kind: "step", label: "a"}).line1, "a");
});

test("where module is null or has no exports the global is set instead; where it has exports they are filled", () => {
  for (const mod of [null, {}, {exports: null}, {exports: 0}, 5, "x"]) {
    const sandbox = vm.createContext({module: mod});
    vm.runInContext(RENDER_CODE, sandbox);
    assert.equal(typeof sandbox.GraphRender.svg, "function", JSON.stringify(mod));
  }
  const sandbox = vm.createContext({module: {exports: {}}});
  vm.runInContext(RENDER_CODE, sandbox);
  assert.equal(typeof sandbox.module.exports.svg, "function");
  assert.equal("GraphRender" in sandbox, false);
});

test("outline and summary find graph_layout.js through require when the page has not loaded it, and through nothing else", () => {
  const asked = [];
  const sandbox = vm.createContext({require: name => { asked.push(name); return GraphLayout; }});
  vm.runInContext(RENDER_CODE, sandbox);
  assert.equal(sandbox.GraphRender.summary(sampleGraph()).waiting, 1);
  assert.equal(sandbox.GraphRender.outline(sampleGraph()), outline(sampleGraph()));
  assert.deepEqual(asked, ["./graph_layout.js", "./graph_layout.js"]);
  const none = vm.createContext({require: () => undefined});
  vm.runInContext(RENDER_CODE, none);
  assert.throws(() => none.GraphRender.outline({nodes: []}), /^Error: GraphRender needs GraphLayout: load graph_layout.js before calling outline or summary$/);
  const global = vm.createContext({require: () => { throw new Error("must not be asked"); }});
  vm.runInContext(LAYOUT_CODE, global);
  vm.runInContext(RENDER_CODE, global);
  assert.equal(global.GraphRender.summary(sampleGraph()).waiting, 1, "a loaded GraphLayout is used before require");
});

test("the sources of this package stay ASCII", () => {
  assert.equal(/[^\x00-\x7f]/.test(RENDER_CODE), false);
});

/* ---------------------------------------------------------------- status look */
test("each of J2's nine status words has the look of mapLook and mapBadge", () => {
  const PANEL = "var(--panel)";
  const TINT = "color-mix(in srgb, var(--ok) 14%, var(--panel))";
  const expected = {
    idle: ["var(--line)", 1.5, PANEL, "", "", false],
    running: ["var(--muted)", 1.5, PANEL, "", "", true],
    waiting: ["var(--validator)", 4, PANEL, "", "?", false],
    waiting_on_you: ["var(--validator)", 4, PANEL, "", "?", false],
    fault: ["var(--bad)", 4, PANEL, "", "!", false],
    filed: ["var(--ok)", 1.5, TINT, "", "", false],
    done_unchecked: ["var(--validator)", 4, PANEL, "2 3", "", false],
    left_open: ["var(--muted)", 1.5, PANEL, "6 4", "", false],
    not_made: ["var(--line)", 1.5, "none", "", "", false],
  };
  assert.deepEqual(Object.keys(expected), NINE);
  NINE.forEach(word => {
    const look = statusLook(word);
    const [stroke, width, fill, dash, badge, ring] = expected[word];
    assert.deepEqual(plain(look), {status: word, stroke, width, fill, dash, badge, badgeFill: badge === "!" ? "var(--bad)" : "var(--validator)", ring, warning: ""}, word);
  });
});

test("an unknown status word (or none, or one that is a property of every object) is drawn as idle, with a warning that names it", () => {
  for (const word of ["busy", "", undefined, null, 4, {}, [], "Idle", "__proto__", "constructor", "toString", "hasOwnProperty", "archived"]) {
    const look = statusLook(word);
    assert.equal(look.status, "idle", String(word));
    assert.equal(look.stroke, "var(--line)");
    assert.match(look.warning, /^unknown status .*, drawn as idle$/);
  }
  assert.equal(statusLook("busy").warning, 'unknown status "busy", drawn as idle');
  assert.equal(statusLook(undefined).warning, 'unknown status "", drawn as idle');
  assert.equal(statusLook(42).warning, 'unknown status "42", drawn as idle');
  assert.equal(statusLook("idle").warning, "");
});

test("statusLook hands out a fresh object each time", () => {
  const a = statusLook("fault");
  a.stroke = "x";
  assert.equal(statusLook("fault").stroke, "var(--bad)");
});

/* ---------------------------------------------------------------- status words and kind words */
test("the words of a function node are J2's mapState, and of every other node J2's MAPS", () => {
  const fnWords = {filed: "filed and checked", done_unchecked: "done \u00b7 checks did not pass", running: "running now", left_open: "left open",
    waiting_on_you: "waiting on you", not_made: "not made", fault: "blocked", idle: "idle"};
  const otherWords = {filed: "filed", done_unchecked: "done \u00b7 checks did not pass", running: "running now", left_open: "left open", waiting: "waiting",
    waiting_on_you: "waiting on you", fault: "fault", not_made: "not made", idle: ""};
  Object.entries(fnWords).forEach(([status, word]) => assert.equal(statusWord(status, "function"), word, status));
  Object.entries(otherWords).forEach(([status, word]) => {
    for (const kind of ["department", "division", "step", "root", "person", undefined]) assert.equal(statusWord(status, kind), word, status + " " + kind);
  });
  assert.equal(statusWord("waiting", "function"), "waiting on someone");
  NINE.forEach(status => assert.equal(typeof statusWord(status, "function"), "string"));
});

test("a function node that is waiting names who it waits for: you, a persona, or whatever the server named", () => {
  assert.equal(statusWord("waiting", "function", "you"), "waiting on you");
  FUNCTIONS.forEach(fn => assert.equal(statusWord("waiting", "function", fn), "waiting on " + PERSONA[fn]));
  assert.equal(statusWord("waiting", "function", "W-3"), "waiting on W-3");
  assert.equal(statusWord("waiting", "function", "team:Web\nDeveloper"), "waiting on team:Web Developer");
  for (const none of [null, undefined, "", "  ", {}, [], true]) assert.equal(statusWord("waiting", "function", none), "waiting on someone");
  assert.equal(statusWord("waiting", "function", 5), "waiting on 5");
  assert.equal(statusWord("running", "function", "audit"), "running now", "wait_on only matters while waiting");
  assert.equal(statusWord("waiting", "step", "audit"), "waiting", "and only for a function");
  assert.equal(statusWord("waiting", "function", "__proto__"), "waiting on __proto__");
  assert.equal(statusWord("waiting", "function", "constructor"), "waiting on constructor");
});

test("an unknown status has the idle word, for a function and for any other node", () => {
  for (const word of ["busy", undefined, null, "__proto__", "constructor", 3]) {
    assert.equal(statusWord(word, "function"), "idle");
    assert.equal(statusWord(word, "step"), "");
  }
});

test("kindWord names each kind and takes an unknown one for a step", () => {
  assert.deepEqual(["root", "department", "division", "function", "step"].map(kindWord), ["root", "team", "division", "function", "step"]);
  for (const kind of ["person", "", undefined, null, 5, "__proto__", "constructor", "toString", {}]) assert.equal(kindWord(kind), "step");
});

/* ---------------------------------------------------------------- the chip */
test("the chip of the design's example: persona, '<Function> . 1 open . 5 closed', and the tooltip with calls, seconds, tokens and failed", () => {
  const chip = chipText(fnNode({status: "waiting_on_you", meta: {stats: STATS, wait_on: "you"}}));
  assert.deepEqual(plain(chip), {line1: "Client Lead", line2: "Identity" + DOT + "1 open" + DOT + "5 closed", tip: "12 calls" + DOT + "41 s" + DOT + "9,120 tokens" + DOT + "1 failed"});
});

test("the second line is just the function name when the node has no atoms; the tooltip leaves 'failed' out when none failed", () => {
  const none = chipText(fnNode({meta: {stats: {...STATS, atoms_total: 0, atoms_open: 3, atoms_closed: 4, atoms_failed: 2}}}));
  assert.equal(none.line2, "Identity");
  assert.ok(none.tip.endsWith(" failed"), "failed still counts when atoms_total is 0 (the numbers are as sent)");
  const clean = chipText(fnNode({meta: {stats: {...STATS, atoms_failed: 0}}}));
  assert.equal(clean.tip, "12 calls" + DOT + "41 s" + DOT + "9,120 tokens");
  assert.equal(clean.line2, "Identity" + DOT + "1 open" + DOT + "5 closed");
  const two = chipText(fnNode({meta: {stats: {...STATS, atoms_failed: 2}}}));
  assert.ok(two.tip.endsWith(DOT + "2 failed"));
  assert.ok(chipText(fnNode({meta: {stats: {...STATS, atoms_failed: -1}}})).tip.indexOf("failed") < 0);
});

test("a missing, negative, fractional or non-numeric number in the stats counts as 0 (fractions are cut)", () => {
  [{meta: {}}, {meta: {stats: null}}, {meta: {stats: []}}, {meta: {stats: "x"}}, {meta: null}, {meta: undefined}].forEach(extra => {
    const chip = chipText(fnNode(extra));
    assert.equal(chip.line2, "Identity");
    assert.equal(chip.tip, "0 calls" + DOT + "0 s" + DOT + "0 tokens");
    assert.equal(chip.line1, "Client Lead");
  });
  const odd = chipText(fnNode({meta: {stats: {calls: "5", seconds: NaN, tokens_in: -4, tokens_out: Infinity, atoms_total: 2.9, atoms_open: 1.9, atoms_closed: "2", atoms_failed: null}}}));
  assert.equal(odd.line2, "Identity" + DOT + "1 open" + DOT + "0 closed");
  assert.equal(odd.tip, "0 calls" + DOT + "0 s" + DOT + "0 tokens");
});

test("a node with one atom shows its counts", () => {
  assert.equal(chipText(fnNode({meta: {stats: {atoms_total: 1, atoms_open: 1, atoms_closed: 0}}})).line2, "Identity" + DOT + "1 open" + DOT + "0 closed");
  assert.equal(chipText(fnNode({meta: {stats: {atoms_total: 0.9, atoms_open: 1, atoms_closed: 0}}})).line2, "Identity", "less than one atom is none");
});

test("calls and tokens are singular for exactly one, numbers are grouped by thousands, tokens are in plus out", () => {
  const t = stats => chipText(fnNode({meta: {stats: {atoms_total: 1, ...stats}}})).tip;
  assert.equal(t({calls: 1, tokens_in: 1, tokens_out: 0}), "1 call" + DOT + "0 s" + DOT + "1 token");
  assert.equal(t({calls: 0, tokens_in: 0, tokens_out: 1}), "0 calls" + DOT + "0 s" + DOT + "1 token");
  assert.equal(t({calls: 2, tokens_in: 1, tokens_out: 1}), "2 calls" + DOT + "0 s" + DOT + "2 tokens");
  assert.equal(t({calls: 1234567, tokens_in: 999999, tokens_out: 1}), "1,234,567 calls" + DOT + "0 s" + DOT + "1,000,000 tokens");
  assert.equal(t({calls: 999, tokens_in: 100, tokens_out: 900}), "999 calls" + DOT + "0 s" + DOT + "1,000 tokens");
  assert.equal(t({calls: 12, tokens_in: 7000, tokens_out: 2120}), "12 calls" + DOT + "0 s" + DOT + "9,120 tokens");
});

test("seconds: whole seconds from ten up (grouped), a tenth below ten, nothing for none", () => {
  const s = seconds => chipText(fnNode({meta: {stats: {seconds, atoms_total: 1}}})).tip.split(DOT)[1];
  assert.deepEqual([0, -3, undefined, "7", NaN].map(s), ["0 s", "0 s", "0 s", "0 s", "0 s"]);
  assert.deepEqual([0.04, 0.4, 3.46, 9.94, 9.96, 10, 10.4, 10.6, 41, 41.4, 41.6, 1234.5, 100000].map(s),
    ["0 s", "0.4 s", "3.5 s", "9.9 s", "10 s", "10 s", "10 s", "11 s", "41 s", "41 s", "42 s", "1,235 s", "100,000 s"]);
  assert.equal(s(-0.4), "0 s");
  assert.equal(s(0), "0 s");
});

test("each function has its persona; the function is known from fn, else from the label, else from the end of the id", () => {
  FUNCTIONS.forEach(fn => {
    assert.equal(chipText(fnNode({fn, label: FN_LABEL[fn], id: "web." + fn})).line1, PERSONA[fn]);
    assert.equal(chipText(fnNode({fn: null, label: FN_LABEL[fn].toUpperCase(), id: "x"})).line1, PERSONA[fn], "label, any case");
    assert.equal(chipText(fnNode({fn: undefined, label: "", id: "dept.a.b." + fn})).line1, PERSONA[fn], "id tail");
    assert.equal(chipText(fnNode({fn: "unknown", label: FN_LABEL[fn], id: "x"})).line1, PERSONA[fn], "a fn that is no function is skipped");
  });
  // when the three disagree the wire's fn wins, then the label, then the end of the id
  assert.equal(chipText(fnNode({fn: "audit", label: "Identity", id: "web.priority"})).line1, "Quality Reviewer");
  assert.equal(chipText(fnNode({fn: undefined, label: "Identity", id: "web.priority"})).line1, "Client Lead");
  assert.equal(chipText(fnNode({fn: "nobody", label: "nobody", id: "web.priority"})).line1, "Prioritiser");
  const unknown = chipText(fnNode({fn: "builder", label: "Builder", id: "web.builder"}));
  assert.equal(unknown.line1, "Builder", "a function with no persona shows its label");
  assert.equal(unknown.line2, "Builder" + DOT + "1 open" + DOT + "5 closed");
  assert.equal(chipText(fnNode({fn: "constructor", label: "Constructor", id: "toString"})).line1, "Constructor", "no property of Object is a persona");
});

test("the line 2 of a function names the function as the wire's label does", () => {
  assert.equal(chipText(fnNode({label: "Coordination", fn: "coordination"})).line2, "Coordination" + DOT + "1 open" + DOT + "5 closed");
  assert.equal(chipText(fnNode({label: "", fn: "audit", id: "web.audit"})).line2, "web.audit" + DOT + "1 open" + DOT + "5 closed", "no label: the id");
});

test("a department or division shows its label and detail, a step its detail or its step_ref, the root only its label", () => {
  assert.deepEqual(plain(chipText({kind: "department", label: "Web", detail: "Identity asks about the menu"})),
    {line1: "Web", line2: "Identity asks about the menu", tip: "Web" + DOT + "Identity asks about the menu"});
  assert.deepEqual(plain(chipText({kind: "division", label: "Quotes", detail: ""})), {line1: "Quotes", line2: "", tip: "Quotes"});
  assert.deepEqual(plain(chipText({kind: "step", label: "Coffee", detail: "waiting for the menu", step_ref: "task"})), {line1: "Coffee", line2: "waiting for the menu", tip: "Coffee" + DOT + "waiting for the menu"});
  assert.deepEqual(plain(chipText({kind: "step", label: "Coffee", detail: "", step_ref: "W-3"})), {line1: "Coffee", line2: "W-3", tip: "Coffee" + DOT + "W-3"});
  assert.deepEqual(plain(chipText({kind: "department", label: "Web", detail: "", step_ref: "W-3"})), {line1: "Web", line2: "", tip: "Web"}, "only a step shows its step_ref");
  assert.deepEqual(plain(chipText({kind: "root", label: "Root", detail: "something"})), {line1: "Root", line2: "", tip: "Root"});
});

test("words from the wire are put on one line: control characters and runs of white space become one space; no label gives the id", () => {
  assert.equal(chipText({kind: "step", label: "a\n\n b\t\tc\u0000d", detail: "x\u2028y"}).line1, "a b c d");
  assert.equal(chipText({kind: "step", label: "", id: "s-1"}).line1, "s-1");
  assert.equal(chipText({kind: "step", label: "   ", id: "s-1"}).line1, "s-1");
  assert.equal(chipText({kind: "step", label: 12}).line1, "12");
  assert.equal(chipText({kind: "step", label: {}, id: 7}).line1, "7");
  assert.equal(chipText({kind: "step", label: {}, id: {}}).line1, "");
  assert.deepEqual(plain(chipText({kind: "step", label: "a", detail: "b\r\nc"})), {line1: "a", line2: "b c", tip: "a" + DOT + "b c"});
});

test("chipText takes anything: no node, a node with no kind, a node that is not an object", () => {
  for (const bad of [undefined, null, 5, "x", [], {}]) {
    const chip = chipText(bad);
    assert.deepEqual(Object.keys(chip), ["line1", "line2", "tip"]);
    assert.equal(typeof chip.tip, "string");
  }
  assert.equal(chipText({id: "a"}).line1, "a");
});

/* ---------------------------------------------------------------- text width */
test("textWidth is the sum of Arial's advances: spot checks", () => {
  assert.equal(textWidth("", 13), 0);
  assert.equal(textWidth("i", 1000), 222);
  assert.equal(textWidth("W", 1000), 944);
  assert.equal(textWidth(" ", 1000), 278);
  assert.equal(textWidth("0123456789", 1000), 5560);
  assert.equal(textWidth("~", 1000), 584);
  assert.equal(textWidth("@", 1000), 1015);
  assert.equal(textWidth("\u00b7", 1000), 333, "the middle dot");
  assert.equal(textWidth(ELLIPSIS, 1000), 1000);
  assert.equal(textWidth("\u00e9", 1000), 556, "any other Latin letter counts as an n");
  assert.equal(textWidth("\u4e2d", 1000), 1000, "a wide character is one em");
  assert.equal(textWidth("\ud83d\ude00", 1000), 1000, "a pair of surrogates is one character");
  assert.equal(textWidth("\u0001", 1000), 556);
  assert.equal(textWidth("\u007f", 1000), 556);
  assert.equal(textWidth("ab", 10), (556 + 556) * 10 / 1000);
  assert.equal(textWidth("Client Lead", 13), 5058 * 13 / 1000);
  assert.equal(textWidth("Coordination" + DOT + "1 open" + DOT + "5 closed", 11), 14229 * 11 / 1000);
});

test("the table of widths is Arial's, every one of the 95 printable ASCII characters", () => {
  const AFM = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584];
  assert.equal(AFM.length, 95);
  AFM.forEach((width, i) => assert.equal(textWidth(String.fromCharCode(32 + i), 1000), width, JSON.stringify(String.fromCharCode(32 + i))));
});

test("outside ASCII a character is an n wide, and one em wide from U+2E80 on", () => {
  assert.equal(textWidth("\u2e7f", 1000), 556);
  assert.equal(textWidth("\u2e80", 1000), 1000);
  assert.equal(textWidth("\u2e81", 1000), 1000);
  assert.equal(textWidth("\u00b6", 1000), 556, "the character next to the middle dot");
  assert.equal(textWidth("\u00b8", 1000), 556);
  assert.equal(textWidth("\u2025", 1000), 556, "and next to the ellipsis");
  assert.equal(textWidth("\u2027", 1000), 556);
  assert.equal(textWidth("\u001f", 1000), 556, "a control character just below the space");
});

test("textWidth takes a number as its digits and anything else as no text; a size that is no number is no size", () => {
  assert.equal(textWidth(12, 1000), 1112);
  assert.equal(textWidth(1.5, 1000), 556 + 278 + 556);
  for (const bad of [undefined, null, {}, [], NaN, Infinity, true]) assert.equal(textWidth(bad, 13), 0, String(bad));
  for (const size of [undefined, null, "13", NaN, Infinity, {}]) assert.equal(textWidth("abc", size), 0, String(size));
  assert.equal(textWidth("abc", 0), 0);
  assert.equal(textWidth("abc", -10), -(556 + 556 + 500) * 10 / 1000, "a negative size is taken as given");
  const words = fit(5, 100, 13);
  assert.equal(words, "5");
  assert.equal(fit({}, 100, 13), "");
  assert.equal(fit(undefined, 100, 13), "");
  assert.equal(fit("abc", NaN, 13), ELLIPSIS, "no usable width: no room");
  assert.equal(fit("i", NaN, 4), ELLIPSIS, "none at all, however small the font");
  assert.equal(fit("abc", "100", 13), ELLIPSIS);
  assert.equal(fit("abc", 100, NaN), "abc", "no size: no width");
});

test("fit keeps a prefix that fits to the pixel (a prefix and the ellipsis may fill the room exactly) and no more", () => {
  // at 1000 px a bar is 260 wide and the ellipsis 1000: "|" and the ellipsis take 1260, "||" and the ellipsis 1520
  const bars = "|".repeat(20);
  assert.equal(fit(bars, 1260 + 8, 1000), "|" + ELLIPSIS);
  assert.equal(fit(bars, 1260 + 8 - 1, 1000), ELLIPSIS);
  assert.equal(fit(bars, 1520 + 8, 1000), "||" + ELLIPSIS);
  assert.equal(fit(bars, 1520 + 8 - 1, 1000), "|" + ELLIPSIS);
  assert.equal(fit("|||||", 1300 + 8, 1000), "|||||", "the whole text, exactly the room");
  assert.equal(fit("|||||", 1300 + 8 - 1, 1000), "|" + ELLIPSIS, "and a pixel less: cut");
  // a box that has no room takes no text, however small the font
  assert.equal(fit("i", 8, 4), ELLIPSIS);
  assert.equal(fit("", 0, 13), "");
  assert.equal(fit("", -30, 13), "");
});

test("every printable ASCII character has an advance, the table is Helvetica's: a few widths from all over it", () => {
  const widths = {};
  for (let c = 32; c <= 126; c++) widths[String.fromCharCode(c)] = textWidth(String.fromCharCode(c), 1000);
  assert.equal(Object.keys(widths).length, 95);
  assert.deepEqual([widths[" "], widths["!"], widths['"'], widths["%"], widths["&"], widths["'"], widths["/"], widths["9"], widths["?"], widths["A"], widths["I"], widths["M"], widths["O"], widths["P"],
    widths["Z"], widths["["], widths["^"], widths["_"], widths["`"], widths["a"], widths["f"], widths["i"], widths["m"], widths["o"], widths["p"], widths["w"], widths["z"], widths["{"], widths["|"], widths["}"]],
  [278, 278, 355, 889, 667, 191, 278, 556, 556, 667, 278, 833, 778, 667, 611, 278, 469, 556, 333, 556, 278, 222, 833, 556, 556, 722, 500, 334, 260, 334]);
  assert.ok(Object.values(widths).every(w => w >= 191 && w <= 1015));
});

test("fit keeps text that fits, and otherwise the longest start that leaves room for an ellipsis", () => {
  const text = "Coffee shop landing page";
  assert.equal(fit("", 140, 13), "");
  assert.equal(fit("Quotes", 140, 13), "Quotes");
  const cut = fit(text, 140, 13);
  assert.ok(cut.endsWith(ELLIPSIS) && cut.length < text.length);
  assert.ok(textWidth(cut, 13) <= 140 - 8, "the cut text fits");
  assert.ok(textWidth(cut.slice(0, -1) + text[cut.length - 1] + ELLIPSIS, 13) > 140 - 8, "and one more letter would not");
  assert.equal(cut, "Coffee shop landing" + ELLIPSIS);
  assert.equal(fit(text, 140, 13), fit(text, 140, 13));
  // "ab cd" is 24.5 px wide at 10 px; in 24 px "ab " still fits with an ellipsis (13.9 + 10) and "ab c" does not (18.9 + 10): the space goes
  assert.equal(fit("ab cd", 24 + 8, 10), "ab" + ELLIPSIS, "a space before the cut is dropped");
});

test("fit keeps text that fits exactly, leaves 4 px at each side, and gives just an ellipsis when nothing else fits", () => {
  const w = textWidth("Quotes", 13);
  assert.equal(fit("Quotes", w + 8, 13), "Quotes", "exactly the room");
  assert.equal(fit("Quotes", w + 8 - 0.01, 13), "Quot" + ELLIPSIS, "a hair less: the ellipsis (13 px) takes the place of the last two letters");
  assert.equal(fit("Quotes", 8, 13), ELLIPSIS);
  assert.equal(fit("Quotes", 0, 13), ELLIPSIS);
  assert.equal(fit("Quotes", -50, 13), ELLIPSIS);
  const smile = "\ud83d\ude00";
  const three = smile.repeat(3);
  assert.equal(fit(three, 8 + 3 * 13, 13), three, "three one-em characters fit exactly");
  assert.equal(fit(three, 8 + 3 * 13 - 1, 13), smile + ELLIPSIS, "a character outside the BMP is kept or dropped whole, never cut in two");
  assert.equal(fit(three, 8 + 2 * 13 + 13 - 1, 13), smile + ELLIPSIS);
  for (let width = 0; width < 200; width += 7) {
    const out = fit("Coordination" + DOT + "12 open" + DOT + "120 closed", width, 11);
    assert.ok(out === ELLIPSIS || textWidth(out, 11) <= width - 8, `width ${width}: ${out}`);
    assert.ok(out.endsWith(ELLIPSIS) || out === "Coordination" + DOT + "12 open" + DOT + "120 closed");
  }
});

test("the standard chip of a function fits its box, so no ellipsis is made for it; a long one is cut", () => {
  FUNCTIONS.forEach(fn => {
    const line2 = chipText(fnNode({fn, label: FN_LABEL[fn]})).line2;
    assert.equal(fit(line2, 168, 11), line2, line2);
  });
  const big = "Coordination" + DOT + "12 open" + DOT + "120 closed";
  assert.notEqual(fit(big, 168, 11), big);
  assert.equal(fit("Quality Reviewer", 168, 13), "Quality Reviewer");
});

/* ---------------------------------------------------------------- svg: the picture */
test("the picture is an svg with the size of the layout, one box per node and one path per link, in the layers of section 3.3", () => {
  const L = sampleLayout();
  const root = drawing(L, {uid: "t"});
  assert.equal(root.tag, "svg");
  assert.equal(root.attrs.xmlns, "http://www.w3.org/2000/svg");
  assert.deepEqual(classOf(root), ["wgsvg"]);
  assert.deepEqual([root.attrs["data-w"], root.attrs["data-h"], root.attrs.width, root.attrs.height], [String(L.width), String(L.height), String(L.width), String(L.height)]);
  assert.equal(root.attrs.role, "group");
  assert.equal(root.attrs["aria-label"], "Graph");
  assert.equal("viewBox" in root.attrs, false);
  assert.deepEqual(root.children.map(c => c.tag), ["defs", "g"]);
  const view = root.children[1];
  assert.deepEqual(classOf(view), ["wview"]);
  assert.deepEqual(view.children.map(c => classOf(c)[0]), ["wedges", "wnodes"]);
  const [edges, nodes] = view.children;
  assert.equal(edges.children.filter(c => c.tag === "path").length, L.links.length + L.edges.length);
  assert.equal(nodes.children.length, L.nodes.length);
  nodes.children.forEach((g, i) => {
    assert.equal(g.tag, "g");
    assert.equal(g.attrs["data-id"], L.nodes[i].id, "in the order of the layout (depth first), so the tab order is depth first");
    assert.equal(g.attrs.tabindex, "0");
    assert.equal(g.attrs.role, "button");
  });
  assert.equal(new Set(nodes.children.map(g => g.attrs["data-id"])).size, L.nodes.length);
});

test("a node is a g.wnode.k-<kind>.st-<status> with a rect.shape, the two lines of text and a title", () => {
  const L = sampleLayout();
  const root = drawing(L, {uid: "t"});
  const web = one(root, "g.wnode[data-id=web]");
  assert.deepEqual(classOf(web), ["wnode", "k-department", "st-waiting_on_you"]);
  assert.deepEqual(web.children.map(c => c.tag + "." + classOf(c).join(".")), ["title.", "rect.shape", "text.tlab", "text.tsub", "circle.wbadge", "text.wbadget"]);
  const node = L.nodes.find(n => n.id === "web");
  const shape = one(web, "rect.shape");
  assert.deepEqual([shape.attrs.x, shape.attrs.y, shape.attrs.width, shape.attrs.height, shape.attrs.rx], [String(node.x), String(node.y), "168", "54", "8"]);
  assert.equal(textOf(one(web, "text.tlab")), "Web");
  assert.deepEqual([one(web, "text.tlab").attrs["font-size"], one(web, "text.tsub").attrs["font-size"]], ["13", "11"]);
  assert.deepEqual([one(web, "text.tlab").attrs.fill, one(web, "text.tsub").attrs.fill], ["var(--ink)", "var(--muted)"]);
  assert.equal(textOf(one(web, "text.tsub")), "Identity asks about the menu");
  const identity = one(root, "g.wnode[data-id=web.identity]");
  assert.deepEqual(classOf(identity), ["wnode", "k-function", "st-waiting_on_you"]);
  assert.equal(textOf(one(identity, "text.tlab")), "Client Lead");
  assert.equal(textOf(one(identity, "text.tsub")), "Identity" + DOT + "1 open" + DOT + "5 closed");
  assert.equal(textOf(one(identity, "title")), "12 calls" + DOT + "41 s" + DOT + "9,120 tokens" + DOT + "1 failed");
  const step = one(root, "g.wnode[data-id=s-web]");
  assert.deepEqual(classOf(step), ["wnode", "k-step", "st-running"]);
  assert.equal(textOf(one(step, "text.tsub")), "task");
  assert.equal(select(one(root, "g.wnode[data-id=root]"), "text.tsub").length, 0, "no second line: no sub text");
  assert.equal(select(root, "g.wnode").length, L.nodes.length);
});

test("the text of a node with one line sits lower than that of a node with two", () => {
  const root = drawing(hand([box("a", "step", {x: 0, y: 0, w: 100, h: 40}), box("b", "step", {x: 0, y: 0, w: 100, h: 40, detail: "d"})]), {uid: "t"});
  assert.equal(one(one(root, "g.wnode[data-id=a]"), "text.tlab").attrs.y, "24.5");
  assert.equal(one(one(root, "g.wnode[data-id=b]"), "text.tlab").attrs.y, "17");
  assert.equal(one(one(root, "g.wnode[data-id=b]"), "text.tsub").attrs.y, "33");
  assert.equal(one(one(root, "g.wnode[data-id=b]"), "text.tsub").attrs.x, "50");
  assert.equal(one(one(root, "g.wnode[data-id=b]"), "text.tsub").attrs["text-anchor"], "middle");
  assert.equal(one(one(root, "g.wnode[data-id=a]"), "text.tlab").attrs.x, "50");
  assert.equal(one(one(root, "g.wnode[data-id=a]"), "text.tlab").attrs["text-anchor"], "middle");
});

test("each status word gives its box the stroke, width, fill and dashes of its look, the badge, and the double ring for running", () => {
  NINE.forEach(status => {
    const root = drawing(hand([box("a", "step", {status})]), {uid: "t"});
    const g = one(root, "g.wnode");
    const look = statusLook(status);
    assert.ok(classOf(g).includes("st-" + status));
    const shape = one(g, "rect.shape");
    assert.equal(shape.attrs.stroke, look.stroke, status);
    assert.equal(shape.attrs["stroke-width"], String(look.width));
    assert.equal(shape.attrs.fill, look.fill);
    assert.equal(shape.attrs["stroke-dasharray"], look.dash === "" ? undefined : look.dash);
    assert.equal(select(g, "rect.wring").length, look.ring ? 1 : 0, status);
    assert.equal(select(g, "circle.wbadge").length, look.badge === "" ? 0 : 1, status);
    if (look.badge !== "") {
      assert.equal(textOf(one(g, "text.wbadget")), look.badge);
      assert.equal(one(g, "circle.wbadge").attrs.fill, look.badgeFill);
      assert.equal(one(g, "circle.wbadge").attrs.cx, "148", "at the top right corner (x + w - 2)");
      assert.equal(one(g, "circle.wbadge").attrs.cy, "22");
    }
  });
  const ring = one(drawing(hand([box("a", "step", {status: "running"})]), {uid: "t"}), "rect.wring");
  assert.deepEqual([ring.attrs.x, ring.attrs.y, ring.attrs.width, ring.attrs.height, ring.attrs.rx, ring.attrs.fill], ["6", "16", "148", "48", "12", "none"]);
});

test("an unknown status is drawn as idle and an unknown kind as a step", () => {
  const root = drawing(hand([box("a", "person", {status: "busy"}), box("b", "constructor", {status: "__proto__"}), box("c", undefined, {status: undefined})]), {uid: "t"});
  select(root, "g.wnode").forEach(g => assert.deepEqual(classOf(g), ["wnode", "k-step", "st-idle"]));
});

test("a division wears the five-dot team glyph, and only a division", () => {
  const root = drawing(hand([box("d", "division", {w: 150, h: 46}), box("e", "department", {w: 168, h: 54})]), {uid: "t"});
  const dots = select(one(root, "g.wnode[data-id=d]"), "circle.wdot");
  assert.deepEqual(dots.map(c => c.attrs.cx), ["69", "77", "85", "93", "101"], "five dots, 8 px apart, round the middle (x 10 + 75)");
  assert.ok(dots.every(c => c.attrs.cy === "25" && c.attrs.r === "2"));
  assert.equal(select(one(root, "g.wnode[data-id=e]"), "circle.wdot").length, 0);
});

test("a node that has no coordinates or size is drawn at 0,0 with a step's size", () => {
  const root = drawing(hand([{id: "a", kind: "step", label: "a", status: "idle"}]), {uid: "t"});
  const shape = one(root, "rect.shape");
  assert.deepEqual([shape.attrs.x, shape.attrs.y, shape.attrs.width, shape.attrs.height], ["0", "0", "140", "40"]);
  const bad = drawing(hand([{id: "a", kind: "step", label: "a", x: "3", y: NaN, w: -1 / 0, h: null}]), {uid: "t"});
  assert.deepEqual([one(bad, "rect.shape").attrs.x, one(bad, "rect.shape").attrs.y, one(bad, "rect.shape").attrs.width], ["0", "0", "140"]);
});

test("the tooltip, and the label spoken to a screen reader, follow the design: 'Identity, Client Lead, waiting on you. Open chat.'", () => {
  const root = drawing(sampleLayout(), {uid: "t"});
  assert.equal(one(root, "g.wnode[data-id=web.identity]").attrs["aria-label"], "Identity, Client Lead, waiting on you. Open chat.");
  assert.equal(one(root, "g.wnode[data-id=web.adaptation]").attrs["aria-label"], "Adaptation, Strategist, idle. Open chat.");
  assert.equal(one(root, "g.wnode[data-id=web]").attrs["aria-label"], "Web, team, waiting on you. Open chat.");
  assert.equal(one(root, "g.wnode[data-id=s-web]").attrs["aria-label"], "Coffee shop landing page, step, running now. Open chat.");
  assert.equal(one(root, "g.wnode[data-id=root]").attrs["aria-label"], "Root, running now. Go to the org chat.", "the word 'root' is not said twice");
  const idle = drawing(hand([box("x", "step", {label: "Quotes"}), box("y", "division", {label: "Division"})]), {uid: "t"});
  assert.equal(one(idle, "g.wnode[data-id=x]").attrs["aria-label"], "Quotes, step. Open chat.", "idle has no word of its own on a step");
  assert.equal(one(idle, "g.wnode[data-id=y]").attrs["aria-label"], "Division. Open chat.");
  const waiting = drawing(hand([box("w", "function", {fn: "audit", label: "Audit", status: "waiting", meta: {wait_on: "priority"}})]), {uid: "t"});
  assert.equal(one(waiting, "g.wnode").attrs["aria-label"], "Audit, Quality Reviewer, waiting on Prioritiser. Open chat.");
});

test("view.action and view.title replace the end of the label and the name of the picture", () => {
  const root = drawing(sampleLayout(), {uid: "t", title: "Org chart", action: "Select."});
  assert.equal(root.attrs["aria-label"], "Org chart");
  assert.equal(one(root, "g.wnode[data-id=web]").attrs["aria-label"], "Web, team, waiting on you. Select.");
  assert.equal(one(root, "g.wnode[data-id=root]").attrs["aria-label"], "Root, running now. Select.");
  for (const bad of [undefined, null, "", "  ", 5, {}]) {
    const r = drawing(sampleLayout(), {uid: "t", title: bad, action: bad});
    assert.equal(r.attrs["aria-label"], typeof bad === "number" ? "5" : "Graph");
    assert.match(one(r, "g.wnode[data-id=web]").attrs["aria-label"], typeof bad === "number" ? /\. 5$/ : /\. Open chat\.$/);
  }
});

test("a selected node has .sel and aria-current; a node under the pointer is .hot, its neighbours .near, the rest .dim, and so are the links", () => {
  const L = sampleLayout();
  const plainRoot = drawing(L, {uid: "t"});
  assert.deepEqual(classOf(plainRoot), ["wgsvg"]);
  assert.equal(select(plainRoot, "g.wnode.sel").length, 0);
  assert.equal(select(plainRoot, "g.wnode[aria-current]").length, 0);
  assert.equal(select(plainRoot, "g.wnode.dim").length + select(plainRoot, "path.dim").length + select(plainRoot, "path.hot").length, 0);
  const root = drawing(L, {uid: "t", selected: "web.priority", hot: "web.identity"});
  assert.deepEqual(classOf(root), ["wgsvg", "ehot"]);
  const sel = one(root, "g.wnode.sel");
  assert.equal(sel.attrs["data-id"], "web.priority");
  assert.equal(sel.attrs["aria-current"], "true");
  const state = Object.fromEntries(select(root, "g.wnode").map(g => [g.attrs["data-id"], ["hot", "near", "dim"].filter(c => classOf(g).includes(c))]));
  assert.deepEqual(state["web.identity"], ["hot"]);
  const neighbours = ["web", "web.adaptation", "web.coordination", "s-web", "web.audit"];
  neighbours.forEach(id => assert.deepEqual(state[id], ["near"], id));
  Object.keys(state).filter(id => id !== "web.identity" && !neighbours.includes(id)).forEach(id => assert.deepEqual(state[id], ["dim"], id));
  select(root, "path.wedge").forEach(p => {
    const touches = p.attrs["data-from"] === "web.identity" || p.attrs["data-to"] === "web.identity";
    assert.deepEqual(["hot", "dim"].filter(c => classOf(p).includes(c)), [touches ? "hot" : "dim"], p.attrs["data-from"] + ">" + p.attrs["data-to"]);
  });
  assert.ok(select(root, "path.wedge.hot").length >= 6);
  const bogus = drawing(L, {uid: "t", hot: "nobody"});
  assert.deepEqual(classOf(bogus), ["wgsvg"]);
  assert.equal(select(bogus, "g.wnode.dim").length, 0);
  for (const bad of [5, null, {}, [], "", "__proto__"]) assert.deepEqual(classOf(drawing(L, {uid: "t", hot: bad})), ["wgsvg"]);
});

test("unread nodes get a dot and fresh nodes .wnew, from an array, a Set or an object; the viewed team gets a ring", () => {
  const L = sampleLayout();
  const forms = [["web.audit", "s-web"], new Set(["web.audit", "s-web"]), {"web.audit": true, "s-web": 1, "web.priority": 0, "web.identity": false}];
  forms.forEach(unread => {
    const root = drawing(L, {uid: "t", unread, fresh: unread});
    assert.deepEqual(select(root, "circle.wunread").map(c => c.attrs.fill), ["var(--accent)", "var(--accent)"]);
    assert.deepEqual(select(root, "g.wnode.wnew").map(g => g.attrs["data-id"]), ["s-web", "web.audit"].sort((a, b) => L.nodes.findIndex(n => n.id === a) - L.nodes.findIndex(n => n.id === b)));
    const dot = one(one(root, "g.wnode[data-id=web.audit]"), "circle.wunread");
    const node = L.nodes.find(n => n.id === "web.audit");
    assert.deepEqual([dot.attrs.cx, dot.attrs.cy, dot.attrs.r], [String(node.x + 8), String(node.y + 8), "4"]);
  });
  for (const none of [undefined, null, [], new Set(), {}, "web", 5]) {
    const root = drawing(L, {uid: "t", unread: none, fresh: none});
    assert.equal(select(root, "circle.wunread").length + select(root, "g.wnode.wnew").length, 0, String(none));
  }
  const ringed = drawing(L, {uid: "t", ring: "web"});
  assert.deepEqual(select(ringed, "g.wnode.cur").map(g => g.attrs["data-id"]), ["web"]);
  const ring = one(ringed, "rect.wcur");
  const web = L.nodes.find(n => n.id === "web");
  assert.deepEqual([ring.attrs.x, ring.attrs.y, ring.attrs.width, ring.attrs.height, ring.attrs.stroke], [String(web.x - 6), String(web.y - 6), String(web.w + 12), String(web.h + 12), "var(--accent)"]);
  assert.equal(select(drawing(L, {uid: "t"}), "rect.wcur").length, 0);
});

test("chart marks: add is dashed and tinted in the accent colour, move is a 2.4 px accent outline, reuse is plain; the tag goes in the tooltip and the label", () => {
  const L = hand([box("a", "department", {x: 40, y: 40, w: 168, h: 54}), box("b", "department", {status: "filed"}), box("c", "department", {status: "fault"}), box("d", "department", {status: "filed"})]);
  const marks = {a: {mark: "add", tag: "added by task: Coffee"}, b: {mark: "move", tag: "moved by change 4"}, c: {mark: "reuse", tag: "reused by change 5"}, d: {mark: "nonsense", tag: "x"}};
  const root = drawing(L, {uid: "t", marks});
  const a = one(root, "g.wnode[data-id=a]");
  assert.ok(classOf(a).includes("mk-add"));
  assert.equal(one(a, "rect.shape").attrs.stroke, "var(--accent)");
  assert.equal(one(a, "rect.shape").attrs["stroke-dasharray"], "5 3");
  assert.equal(one(a, "rect.shape").attrs.fill, "color-mix(in srgb, var(--accent) 12%, var(--panel))");
  assert.equal(one(a, "rect.shape").attrs["stroke-width"], "1.8");
  assert.equal(textOf(one(a, "text.wtag")), "added");
  assert.deepEqual([one(a, "text.wtag").attrs.x, one(a, "text.wtag").attrs.y], ["42", "35"]);
  assert.equal(textOf(one(a, "title")).split("\n").pop(), "added by task: Coffee");
  assert.match(a.attrs["aria-label"], /^a, team\. added by task: Coffee\. Open chat\.$/);
  const b = one(root, "g.wnode[data-id=b]");
  assert.ok(classOf(b).includes("mk-move"));
  assert.equal(one(b, "rect.shape").attrs.stroke, "var(--accent)");
  assert.equal(one(b, "rect.shape").attrs["stroke-width"], "2.4");
  assert.equal("stroke-dasharray" in one(b, "rect.shape").attrs, false);
  assert.equal(one(b, "rect.shape").attrs.fill, statusLook("filed").fill, "a move keeps the fill of the status");
  assert.equal(textOf(one(b, "text.wtag")), "moved");
  const c = one(root, "g.wnode[data-id=c]");
  assert.ok(classOf(c).includes("mk-reuse"));
  assert.equal(one(c, "rect.shape").attrs.stroke, "var(--bad)", "a reused node keeps its own look");
  assert.equal(select(c, "text.wtag").length, 0);
  assert.equal(textOf(one(c, "title")), "c\nreused by change 5", "the tooltip is the chip's words, then the tag on a line of its own");
  const d = one(root, "g.wnode[data-id=d]");
  assert.equal(classOf(d).some(k => k.startsWith("mk-")), false, "a mark that is none of the three is ignored");
  assert.equal(one(d, "rect.shape").attrs.stroke, "var(--ok)");
});

test("the ring of a running node is never dashed, even when a mark makes the box itself dashed", () => {
  const root = drawing(hand([box("a", "department", {status: "running"})]), {uid: "t", marks: {a: {mark: "add", tag: "x"}}});
  const g = one(root, "g.wnode");
  assert.equal(one(g, "rect.shape").attrs["stroke-dasharray"], "5 3");
  assert.equal("stroke-dasharray" in one(g, "rect.wring").attrs, false);
  assert.equal(one(g, "rect.wring").attrs.stroke, "var(--accent)", "but it takes the colour of the mark");
  const lefty = drawing(hand([box("a", "step", {status: "left_open"})]), {uid: "t"});
  assert.equal("stroke-dasharray" in one(lefty, "rect.shape").attrs, true);
  assert.equal(select(lefty, "rect.wring").length, 0);
});

test("the badge is a circle at the top right corner with its mark in bold, centred", () => {
  const g = one(drawing(hand([box("a", "step", {status: "fault"})]), {uid: "t"}), "g.wnode");
  const mark = one(g, "text.wbadget");
  assert.deepEqual([mark.attrs.x, mark.attrs.y, mark.attrs["text-anchor"], mark.attrs["font-size"], mark.attrs["font-weight"], mark.attrs.fill], ["148", "26", "middle", "12", "700", "var(--on)"]);
  assert.deepEqual([one(g, "circle.wbadge").attrs.cx, one(g, "circle.wbadge").attrs.cy, one(g, "circle.wbadge").attrs.r], ["148", "22", "8"]);
});

test("a mark with no tag says nothing more in the label than an unmarked node", () => {
  const untagged = drawing(hand([box("a", "department")]), {uid: "t", marks: {a: {mark: "add"}}});
  assert.equal(one(untagged, "g.wnode").attrs["aria-label"], "a, team. Open chat.");
  const blank = drawing(hand([box("a", "department")]), {uid: "t", marks: {a: {mark: "move", tag: " \n "}}});
  assert.equal(one(blank, "g.wnode").attrs["aria-label"], "a, team. Open chat.");
});

test("marks that are not an object, or not a mark, are ignored; an id such as __proto__ is a name like any other", () => {
  const L = hand([box("a"), box("__proto__")]);
  const marked = marks => select(drawing(L, {uid: "t", marks}), "g.wnode").filter(g => classOf(g).some(c => c.startsWith("mk-"))).map(g => g.attrs["data-id"]);
  for (const marks of [undefined, null, 5, "x", [], {}, {a: null}, {a: 5}, {a: "add"}, {a: {}}, {a: {mark: 3}}, {a: {mark: "Add"}}, {b: {mark: "add", tag: "x"}}]) {
    assert.deepEqual(marked(marks), [], JSON.stringify(marks));
  }
  assert.deepEqual(marked(Object.fromEntries([["__proto__", {mark: "move", tag: "moved"}]])), ["__proto__"]);
  assert.deepEqual(marked({a: {mark: "add"}}), ["a"], "a mark with no tag is a mark with an empty tag");
  assert.equal(textOf(one(one(drawing(L, {uid: "t", marks: {a: {mark: "add"}}}), "g.wnode[data-id=a]"), "title")), "a", "and the tooltip has no empty line");
  assert.deepEqual(marked({toString: {mark: "add", tag: "x"}, constructor: {mark: "add", tag: "x"}}), [], "properties every object has are not marks");
});

test("a label that does not fit its box is cut with an ellipsis and the whole text is in the tooltip", () => {
  const root = drawing(hand([box("a", "step", {label: "Coffee shop landing page for the cafe", detail: "waiting for the owner to say which menu to use"}), box("b", "step", {label: "Quotes", detail: "short"})]), {uid: "t"});
  const a = one(root, "g.wnode[data-id=a]");
  const shown1 = textOf(one(a, "text.tlab"));
  const shown2 = textOf(one(a, "text.tsub"));
  assert.ok(shown1.endsWith(ELLIPSIS) && shown2.endsWith(ELLIPSIS));
  assert.ok(textWidth(shown1, 13) <= 132 && textWidth(shown2, 11) <= 132);
  assert.equal(textOf(one(a, "title")), "Coffee shop landing page for the cafe" + DOT + "waiting for the owner to say which menu to use");
  const b = one(root, "g.wnode[data-id=b]");
  assert.equal(textOf(one(b, "text.tlab")), "Quotes");
  assert.equal(textOf(one(b, "title")), "Quotes" + DOT + "short");
  // a function chip keeps its stats tooltip and adds the full words only when it cut them
  const big = drawing(hand([box("f", "function", {fn: "coordination", label: "Coordination", w: 168, h: 50, meta: {stats: {atoms_total: 140, atoms_open: 12, atoms_closed: 120, calls: 3}}}),
    box("g", "function", {fn: "audit", label: "Audit", w: 168, h: 50, meta: {stats: {atoms_total: 2, atoms_open: 1, atoms_closed: 1, calls: 3}}})]), {uid: "t"});
  const f = one(big, "g.wnode[data-id=f]");
  assert.ok(textOf(one(f, "text.tsub")).endsWith(ELLIPSIS));
  assert.equal(textOf(one(f, "title")), "3 calls" + DOT + "0 s" + DOT + "0 tokens\nScheduler" + DOT + "Coordination" + DOT + "12 open" + DOT + "120 closed");
  assert.equal(textOf(one(one(big, "g.wnode[data-id=g]"), "title")), "3 calls" + DOT + "0 s" + DOT + "0 tokens");
});

/* ---------------------------------------------------------------- svg: the links */
test("every link is a path.wedge with data-edge, data-from, data-to, the layout's d, a gradient stroke and an arrowhead", () => {
  const L = sampleLayout();
  const root = drawing(L, {uid: "t"});
  const paths = select(root, "path.wedge");
  assert.equal(paths.length, L.links.length + L.edges.length);
  const ids = new Set(select(root, "linearGradient").map(g => g.attrs.id));
  paths.slice(0, L.links.length).forEach((p, i) => {
    assert.deepEqual(classOf(p), ["wedge", "e-org"]);
    assert.equal(p.attrs["data-edge"], "org");
    assert.equal(p.attrs["data-tone"], "org");
    assert.equal(p.attrs["data-from"], L.links[i].from);
    assert.equal(p.attrs["data-to"], L.links[i].to);
    assert.equal(p.attrs.d, L.links[i].d);
    assert.equal(p.attrs.fill, "none");
    assert.equal(p.attrs.stroke, `url(#eg-t-${i + 1})`);
    assert.equal(p.attrs["marker-end"], "url(#ea-org-t)");
    assert.ok(ids.has(`eg-t-${i + 1}`));
    assert.equal(p.children.length, 0, "a tree link has no title");
    assert.deepEqual(Object.keys(p.attrs), ["class", "data-edge", "data-tone", "data-from", "data-to", "d", "fill", "stroke", "marker-end"], "and no dots");
  });
  paths.slice(L.links.length).forEach((p, i) => {
    const e = L.edges[i];
    assert.equal(p.attrs["data-from"], e.from);
    assert.equal(p.attrs["data-to"], e.to);
    assert.equal(p.attrs.d, e.d);
    assert.equal(p.attrs.stroke, `url(#eg-t-${L.links.length + i + 1})`);
    assert.equal(p.children[0].tag, "title");
    assert.ok(/^e-(handoff|depends_on|speaks_to|step)$/.test(classOf(p)[1]), classOf(p).join(" "));
  });
  assert.equal(ids.size, paths.length, "one gradient for each");
  paths.forEach(p => assert.match(p.attrs.d, /^M[\d.,]+ C[\d.,]+ [\d.,]+ [\d.,]+$/, "every path is one cubic, well formed"));
  assert.ok(select(root, "path.wedge").every(p => ["org", "handoff", "depends_on", "speaks_to", "step"].includes(p.attrs["data-edge"])));
});

test("each kind of cross link has its own colour family: handoff amber (makes), depends_on blue (reads) and terracotta (fix) when it revises, speaks_to blue and dotted, step and unknown blue", () => {
  const e = (kind, label = "") => ({id: "e", from: "a", to: "b", kind, label, d: "M0,0 C0,10 10,10 10,20", x1: 0, y1: 0, x2: 10, y2: 20, lx: 5, ly: 10, loop: false});
  // [the link, the kind it is drawn as, its tone, dotted, the data-kind the stylesheet may use (the kind as sent, when it is not one of ours)]
  const cases = [
    [e("handoff"), "handoff", "makes", false, undefined],
    [e("depends_on"), "depends_on", "reads", false, undefined],
    [e("depends_on", "revises"), "depends_on", "fix", false, undefined],
    [e("depends_on", " Revises "), "depends_on", "fix", false, undefined],
    [e("depends_on", "reads"), "depends_on", "reads", false, undefined],
    [e("depends_on", "revising"), "depends_on", "reads", false, undefined],
    [e("speaks_to", "3"), "speaks_to", "reads", true, undefined],
    [e("step"), "step", "reads", false, undefined],
    [e("mentions"), "step", "reads", false, "mentions"],
    [e("revises", "revises"), "step", "reads", false, "revises"],
    [e("handoff", "revises"), "handoff", "makes", false, undefined],
    [e(undefined), "step", "reads", false, undefined],
    [e(""), "step", "reads", false, undefined],
    [e(5), "step", "reads", false, "5"],
  ];
  cases.forEach(([edgeIn, kind, tone, dotted, original]) => {
    const p = one(drawing(hand([box("a"), box("b")], [], [edgeIn]), {uid: "t"}), "path.wedge");
    const name = JSON.stringify(edgeIn.kind) + " " + JSON.stringify(edgeIn.label);
    assert.deepEqual(classOf(p), ["wedge", "e-" + kind], name);
    assert.equal(p.attrs["data-edge"], kind, name);
    assert.equal(p.attrs["data-tone"], tone, name);
    assert.equal(p.attrs["marker-end"], "url(#ea-" + tone + "-t)", name);
    assert.equal(p.attrs.style, dotted ? "stroke-dasharray:1.5 4 !important" : undefined, name);
    assert.equal(p.attrs["data-kind"], original, name);
  });
  assert.deepEqual(plain(edgeLook("handoff")), {kind: "handoff", tone: "makes", verb: "hands to", dotted: false});
  assert.deepEqual(plain(edgeLook("depends_on", "revises")), {kind: "depends_on", tone: "fix", verb: "revises", dotted: false});
  assert.deepEqual(plain(edgeLook("depends_on", "reads")), {kind: "depends_on", tone: "reads", verb: "reads", dotted: false});
  assert.deepEqual(plain(edgeLook("speaks_to", "2")), {kind: "speaks_to", tone: "reads", verb: "speaks to", dotted: true});
  assert.deepEqual(plain(edgeLook("step")), {kind: "step", tone: "reads", verb: "leads to", dotted: false});
  for (const odd of ["contains", "", "__proto__", "constructor", "toString", undefined, null, 7]) {
    assert.deepEqual(plain(edgeLook(odd, "revises")), {kind: "step", tone: "reads", verb: "leads to", dotted: false}, String(odd));
  }
});

test("the colour of each tone is a J2 token: reads, makes and fix, and --e-org (falling back to --edge) for the tree", () => {
  const root = drawing(hand([box("a"), box("b")], [{from: "a", to: "b", d: "M0,0 C0,1 1,1 1,2", x1: 0, y1: 0, x2: 1, y2: 2}], [
    {from: "a", to: "b", kind: "handoff", d: "M0,0 C0,1 1,1 1,2", x1: 0, y1: 0, x2: 1, y2: 2}, {from: "a", to: "b", kind: "depends_on", d: "M0,0 C0,1 1,1 1,2", x1: 0, y1: 0, x2: 1, y2: 2},
    {from: "a", to: "b", kind: "depends_on", label: "revises", d: "M0,0 C0,1 1,1 1,2", x1: 0, y1: 0, x2: 1, y2: 2}]), {uid: "t"});
  const colour = {org: "var(--e-org, var(--edge))", makes: "var(--e-makes)", reads: "var(--e-reads)", fix: "var(--e-fix)"};
  const markers = select(root, "marker");
  assert.deepEqual(markers.map(m => m.attrs.id), ["ea-org-t", "ea-reads-t", "ea-makes-t", "ea-fix-t"], "in a fixed order, only the tones in use");
  markers.forEach(m => {
    const tone = m.attrs.id.split("-")[1];
    assert.deepEqual([m.attrs.viewBox, m.attrs.refX, m.attrs.refY, m.attrs.markerWidth, m.attrs.markerHeight, m.attrs.markerUnits, m.attrs.orient], ["0 0 8 8", "7.2", "4", "6", "6", "userSpaceOnUse", "auto"]);
    const head = one(m, "path");
    assert.deepEqual(classOf(head), ["earr", "e-" + tone]);
    assert.equal(head.attrs.d, "M1.4 1.4 L7.2 4 L1.4 6.6 Q2.4 4 1.4 1.4 Z");
    assert.deepEqual([head.attrs.fill, head.attrs.stroke], [colour[tone], colour[tone]]);
  });
  const grads = select(root, "linearGradient");
  assert.equal(grads.length, 4);
  grads.forEach((g, i) => {
    const tone = ["org", "makes", "reads", "fix"][i];
    assert.deepEqual([g.attrs.gradientUnits, g.attrs.x1, g.attrs.y1, g.attrs.x2, g.attrs.y2], ["userSpaceOnUse", "0", "0", "1", "2"]);
    assert.deepEqual(g.children.map(s => [s.tag, s.attrs.offset, s.attrs.style]), [["stop", "0", `stop-color:${colour[tone]};stop-opacity:.82`], ["stop", "1", `stop-color:${colour[tone]}`]]);
  });
  assert.equal(select(drawing(hand([box("a")]), {uid: "t"}), "marker").length, 0, "no links, no markers");
  assert.equal(select(drawing(hand([box("a"), box("b")], [{from: "a", to: "b", d: "M0,0"}]), {uid: "t"}), "marker").length, 1);
});

test("a loop is dashed (class loop) and only when the layout says so; a dotted link that is a loop loses its dots to the dashes", () => {
  const d = "M0,0 C0,10 10,10 10,20";
  const e = (kind, loop) => ({from: "a", to: "b", kind, label: kind === "speaks_to" ? "2" : "", d, x1: 0, y1: 0, x2: 10, y2: 20, loop});
  const root = drawing(hand([box("a"), box("b")], [], [e("handoff", true), e("handoff", false), e("speaks_to", true), e("speaks_to", false), e("depends_on", "true"), e("step", 1), e("step", undefined)]), {uid: "t"});
  const flags = select(root, "path.wedge").map(p => [classOf(p).includes("loop"), p.attrs.style !== undefined]);
  assert.deepEqual(flags, [[true, false], [false, false], [true, false], [false, true], [false, false], [false, false], [false, false]]);
  const L = GraphLayout.layout({nodes: [{id: "a", parent: null, kind: "step"}, {id: "b", parent: null, kind: "step"}], cross: [
    {from: "a", to: "b", kind: "handoff"}, {from: "b", to: "a", kind: "handoff"}, {from: "a", to: "b", kind: "speaks_to", label: "1"}]});
  assert.deepEqual(select(drawing(L, {uid: "t"}), "path.wedge").map(p => classOf(p).includes("loop")), [true, true, false]);
});

test("the count on a speaks_to link is its label, drawn at the middle of the link and said in the title; other labels are not drawn", () => {
  const L = sampleLayout();
  const root = drawing(L, {uid: "t"});
  const labels = select(root, "text.wedgelab");
  assert.deepEqual(labels.map(t => [t.attrs["data-from"], t.attrs["data-to"], textOf(t)]), [["web.identity", "web.coordination", "3"], ["web.coordination", "web.identity", "2"]]);
  const first = L.edges.find(e => e.kind === "speaks_to");
  assert.deepEqual([labels[0].attrs.x, labels[0].attrs.y, labels[0].attrs["text-anchor"], labels[0].attrs["font-size"]], [String(first.lx), String(Math.round((first.ly - 4) * 10) / 10), "middle", "11"]);
  assert.deepEqual(classOf(labels[0]), ["wedgelab", "e-speaks_to"]);
  const titleOf = id => textOf(one(select(root, "path.wedge").find(p => `${p.attrs["data-from"]}>${p.attrs["data-to"]}` === id && p.children.length) || {children: []}, "title"));
  assert.equal(titleOf("web.identity>web.coordination"), "Identity speaks to Coordination (3 messages)");
  assert.equal(titleOf("web.coordination>web.identity"), "Coordination speaks to Identity (2 messages)");
  assert.equal(titleOf("web.identity>web.adaptation"), "Identity hands to Adaptation");
  assert.equal(titleOf("web.audit>web.priority"), "Audit revises Priority");
  assert.equal(titleOf("web.priority>web.adaptation"), "Priority reads Adaptation");
  assert.equal(titleOf("web.identity>s-web"), "Identity leads to Coffee shop landing page");
  assert.equal(titleOf("web.audit>s-web"), "Audit leads to Coffee shop landing page", "an unknown kind reads as a plain link");
  const one1 = drawing(hand([box("a", "step", {label: "A"}), box("b", "step", {label: "B"})], [], [{from: "a", to: "b", kind: "speaks_to", label: "1", d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}]), {uid: "t"});
  assert.equal(textOf(one(one(one1, "path.wedge"), "title")), "A speaks to B (1 message)");
  const words = drawing(hand([box("a", "step", {label: "A"}), box("b", "step", {label: "B"})], [], [{from: "a", to: "b", kind: "speaks_to", label: "many", d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}]), {uid: "t"});
  assert.equal(textOf(one(one(words, "path.wedge"), "title")), "A speaks to B (many)");
  assert.equal(textOf(one(words, "text.wedgelab")), "many");
  const none = drawing(hand([box("a", "step", {label: "A"}), box("b", "step", {label: "B"})], [], [{from: "a", to: "b", kind: "speaks_to", label: "", d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}, {from: "a", to: "b", kind: "handoff", label: "5", d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}]), {uid: "t"});
  assert.equal(select(none, "text.wedgelab").length, 0);
  assert.deepEqual(select(none, "path.wedge").map(p => textOf(one(p, "title"))), ["A speaks to B", "A hands to B"]);
  const nopos = drawing(hand([box("a"), box("b")], [], [{from: "a", to: "b", kind: "speaks_to", label: "4", d: "M0,0 C0,1 1,1 1,2"}]), {uid: "t"});
  assert.equal(select(nopos, "text.wedgelab").length, 0, "no position, no label");
  const nopath = drawing(hand([box("a"), box("b")], [], [{from: "a", to: "b", kind: "speaks_to", label: "4", lx: 1, ly: 2}]), {uid: "t"});
  assert.equal(select(nopath, "text.wedgelab").length + select(nopath, "path").length, 0, "no path, no label either");
  assert.equal(textOf(one(one(drawing(hand([box("a"), box("b")], [], [{from: "a", to: "b", kind: "speaks_to", label: "0", d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}]), {uid: "t"}), "path.wedge"), "title")), "a speaks to b (0 messages)");
});

test("a link with no path is not drawn, and a link with no gradient ends is drawn with a plain stroke", () => {
  const root = drawing(hand([box("a"), box("b")], [{from: "a", to: "b"}, {from: "a", to: "b", d: ""}, {from: "a", to: "b", d: "  "}, {from: "a", to: "b", d: 5}], [
    {from: "a", to: "b", kind: "handoff"}, {from: "a", to: "b", kind: "handoff", d: "M0,0 C0,1 1,1 1,2"}]), {uid: "t"});
  const paths = select(root, "path.wedge");
  assert.equal(paths.length, 1);
  assert.equal(paths[0].attrs.stroke, "var(--e-makes)");
  assert.equal(select(root, "linearGradient").length, 0);
  assert.equal(paths[0].attrs["marker-end"], "url(#ea-makes-t)");
  assert.equal(select(root, "marker").length, 1, "an undrawn link makes no marker");
  const partial = select(drawing(hand([box("a"), box("b")], [{from: "a", to: "b", d: "M0,0 C0,1 1,1 1,2", x1: 1, y1: 2, x2: 3}]), {uid: "t"}), "path.wedge")[0];
  assert.equal(partial.attrs.stroke, "var(--e-org, var(--edge))", "all four ends or none");
});

test("the d of a link is written as the layout gave it, after the same clean-up as any other word", () => {
  const root = drawing(hand([box("a"), box("b")], [{from: "a", to: "b", d: "M1,2\n C3,4 5,6 7,8"}]), {uid: "t"});
  assert.equal(select(root, "path.wedge")[0].attrs.d, "M1,2 C3,4 5,6 7,8");
});

/* ---------------------------------------------------------------- svg: ids, safety, robustness */
test("every url(#id) in the picture names an element that is there, and every id is used once", () => {
  const root = drawing(sampleLayout(), {uid: "t"});
  const ids = [];
  const refs = [];
  walk(root, n => {
    if (n.attrs.id) ids.push(n.attrs.id);
    Object.values(n.attrs).forEach(v => { for (const m of v.matchAll(/url\(#([^)]+)\)/g)) refs.push(m[1]); });
  });
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(refs.length > 0 && refs.every(r => ids.includes(r)), refs.filter(r => !ids.includes(r)).join());
  assert.ok(ids.every(id => /^(ea-(org|reads|makes|fix)-t|eg-t-\d+)$/.test(id)), ids.join());
});

test("view.uid keeps the ids of two pictures on one page apart; without it the ids come from the drawing, so different drawings differ", () => {
  const L = sampleLayout();
  const idsOf = html => [...html.matchAll(/ id="([^"]+)"/g)].map(m => m[1]);
  const a = idsOf(svg(L, {uid: "graph"}));
  const b = idsOf(svg(L, {uid: "chart"}));
  assert.ok(a.length > 5 && a.every(id => !b.includes(id)));
  assert.ok(a.every(id => id.includes("graph")));
  const small = GraphLayout.layout(GraphLayout.validate({nodes: [rawNode("root", "root"), rawNode("a", "department")], edges: [edge("root", "a")]}).graph);
  const x = idsOf(svg(L, {}));
  const y = idsOf(svg(small, {}));
  assert.ok(x.every(id => /^(ea|eg)-(org|reads|makes|fix|)-?d[0-9a-f]{8}(-\d+)?$/.test(id)), x.slice(0, 3).join());
  assert.ok(y.length > 0 && y.every(id => !x.includes(id)), "two different drawings never share an id");
  assert.deepEqual(idsOf(svg(L, {})), x, "the same drawing gives the same ids");
  assert.deepEqual(idsOf(svg(L, {hot: "web", selected: "web", unread: ["web"]})), x, "and so does the same drawing in another state");
  const moved = JSON.parse(JSON.stringify(L));
  moved.nodes[0].x += 1;
  assert.notDeepEqual(idsOf(svg(moved, {})), x, "a box that moves changes the fingerprint");
  const bent = JSON.parse(JSON.stringify(L));
  bent.edges[0].d = bent.edges[0].d.replace("M", "M ");
  assert.notDeepEqual(idsOf(svg(bent, {})), x, "and so does a path");
  const rekind = JSON.parse(JSON.stringify(L));
  rekind.edges[0].kind = "mentions";
  assert.notDeepEqual(idsOf(svg(rekind, {})), x, "and so does a kind");
});

test("the default id is the fingerprint of the drawing, d and eight hex digits, pinned for two drawings", () => {
  const first = svg(hand([box("a"), box("b")], [{from: "a", to: "b", d: "M0,0 C0,1 1,1 1,2"}]), {});
  assert.match(first, /<marker id="ea-org-d6897be71"/);
  // a drawing whose number starts with zeros keeps them: eight digits whatever the number
  const zero = svg(hand([box("a")], [{from: "a", to: "a", d: "M0,0"}], [], {width: 1}), {});
  assert.match(zero, /<marker id="ea-org-d066fe929"/);
  const zeros = svg(hand([box("a")], [{from: "a", to: "a", d: "M0,0"}], [], {width: 198}), {});
  assert.match(zeros, /<marker id="ea-org-d00a61ea0"/);
  // a coordinate that is no number counts as 0: the drawing is the same, and another number is another drawing
  const idsOfBox = extra => [...svg(hand([box("a", "step", extra), box("b")], [{from: "a", to: "b", d: "M0,0"}]), {}).matchAll(/ id="([^"]+)"/g)].map(m => m[1]);
  assert.deepEqual(idsOfBox({x: undefined}), idsOfBox({x: 0}));
  assert.deepEqual(idsOfBox({y: "5", w: NaN, h: Infinity}), idsOfBox({y: 0, w: 0, h: 0}));
  assert.notDeepEqual(idsOfBox({x: 1}), idsOfBox({x: 0}));
});

test("a uid that is not letters, digits, - and _ (or is empty, or too long) is not used", () => {
  const L = hand([box("a"), box("b")], [{from: "a", to: "b", d: "M0,0 C0,1 1,1 1,2"}]);
  for (const bad of ["a b", 'a"b', "a<b", "", "x".repeat(41), "a.b", "a/b", 7, null, {}, "a\nb", "\u00e9"]) {
    assert.match(svg(L, {uid: bad}), /id="ea-org-d[0-9a-f]{8}"/, JSON.stringify(bad));
  }
  assert.match(svg(L, {uid: "Ab_9-z"}), /id="ea-org-Ab_9-z"/);
  assert.match(svg(L, {uid: "x".repeat(40)}), /id="ea-org-x{40}"/);
  assert.match(svg(L, {uid: "-"}), /id="ea-org--"/);
});

test("words from the wire are escaped everywhere: labels, details, ids, kinds, tags, titles, edge ends", () => {
  const evil = `<script>alert("x")</script> & 'q' "d" </g><g onclick=1>`;
  const L = hand([box(evil, "step", {label: evil, detail: evil, x: 0, y: 0, w: 400, h: 40}), box("b\"><x y=\"", "step", {label: "ok"}), box("c", "department", {label: evil, fn: evil, meta: {wait_on: evil}})],
    [{from: evil, to: 'b"><x y="', d: "M0,0 C0,1 1,1 1,2"}],
    [{from: evil, to: "c", kind: evil, label: evil, d: "M0,0 C0,1 1,1 1,2", x1: 0, y1: 0, x2: 1, y2: 2, lx: 1, ly: 1}, {from: "c", to: evil, kind: "speaks_to", label: evil, d: "M0,0 C0,1 1,1 1,2", lx: 1, ly: 1}]);
  const html = svg(L, {uid: "t", title: evil, action: evil, marks: {[evil]: {mark: "add", tag: evil}}, selected: evil, ring: evil, unread: [evil], fresh: [evil], hot: evil});
  assert.equal(html.includes("<script"), false);
  const root = parse(html).children[0];             // the markup is well formed, and what is in it is only what the module wrote
  const tags = new Set();
  const attributes = new Set();
  walk(root, n => { tags.add(n.tag); Object.keys(n.attrs).forEach(a => attributes.add(a)); });
  assert.deepEqual([...tags].sort(), ["circle", "defs", "g", "linearGradient", "marker", "path", "rect", "stop", "svg", "text", "title"]);
  assert.equal([...attributes].some(a => a.startsWith("on")), false, "no attribute came from the words");
  const g = select(root, "g.wnode")[0];
  assert.equal(g.attrs["data-id"], evil);
  assert.equal(textOf(one(g, "text.tlab")).includes("<script>"), true, "the words themselves are kept (as text)");
  assert.equal(root.attrs["aria-label"], evil.replace(/\s+/g, " "));
  select(root, "path.wedge").forEach(p => assert.ok(p.attrs["data-from"] === evil || p.attrs["data-from"] === "c"));
  assert.equal(select(root, "g.wnode").length, 3);
  assert.equal(classOf(select(root, "g.wnode")[1]).every(c => /^[\w-]+$/.test(c)), true, "class names come only from fixed words");
});

test("a node id with markup in it does not break the outline or the list of classes", () => {
  const html = outline({nodes: [{id: '"><b>', kind: "step", label: "<i>x</i>", status: "idle", parent: null}]});
  assert.equal(html.includes("<b>"), false);
  assert.equal(html.includes("<i>"), false);
  parse(html);
});

test("the same layout and view give the same string twice, and nothing the caller passed is changed", () => {
  const L = deepFreeze(sampleLayout());
  const view = deepFreeze({uid: "t", selected: "web", hot: "web.identity", marks: {web: {mark: "add", tag: "x"}}, unread: ["s-web"], fresh: ["web.audit"], ring: "support"});
  const a = svg(L, view);
  assert.equal(svg(L, view), a);
  assert.equal(svg(JSON.parse(JSON.stringify(L)), JSON.parse(JSON.stringify(view))), a);
  parse(a);
});

test("svg takes anything: no layout, a layout with no lists, entries that are not objects", () => {
  for (const bad of [undefined, null, 5, "x", [], {}, {nodes: "x", links: 5, edges: null}, {nodes: [null, 4, "x", []], links: [null], edges: [null, 3]}]) {
    const root = drawing(bad, {uid: "t"});
    assert.equal(root.tag, "svg");
    assert.equal(select(root, "g.wnode").length, 0);
    assert.equal(select(root, "path").length, 0);
  }
  const empty = drawing(undefined, undefined);
  assert.deepEqual([empty.attrs["data-w"], empty.attrs["data-h"]], ["0", "0"]);
  const sized = drawing({width: 12.34, height: "x"}, {});
  assert.deepEqual([sized.attrs["data-w"], sized.attrs["data-h"]], ["12.3", "0"]);
  assert.equal(select(drawing(hand([box("a")]), 7), "g.wnode").length, 1);
  assert.equal(select(drawing(hand([box("a")]), null), "g.wnode").length, 1);
});

test("a graph of 500 nodes draws in a moment and the markup is well formed", () => {
  const nodes = [{id: "n0", parent: null, kind: "root"}];
  for (let i = 1; i < 500; i++) nodes.push({id: "n" + i, parent: "n" + Math.floor((i - 1) / 4), kind: i % 5 === 0 ? "function" : "step"});
  const L = GraphLayout.layout({nodes, cross: [{from: "n10", to: "n20", kind: "handoff"}]});
  const t = performance.now();
  const html = svg(L, {uid: "big"});
  assert.ok(performance.now() - t < 500);
  assert.equal(select(parse(html).children[0], "g.wnode").length, 500);
});

/* ---------------------------------------------------------------- outline */
test("the outline is the same graph as a nested list, with the same click targets", () => {
  const graph = sampleGraph();
  const root = listing(outline(graph, {}));
  assert.equal(root.tag, "ul");
  assert.deepEqual(classOf(root), ["wtree"]);
  assert.equal(root.attrs.role, "tree");
  const buttons = select(root, "button.wobtn");
  assert.deepEqual(buttons.map(b => b.attrs["data-id"]), graph.nodes.map(n => n.id), "depth-first, like the tree");
  buttons.forEach(b => assert.equal(b.attrs.type, "button"));
  // the nesting is the tree's: each li holds its button, and its children in a ul[role=group] when it has any
  const parentOf = {};
  const levelOf = {};
  (function visit(ul, parent, level) {
    kidsOf(ul, "li").forEach(li => {
      const own = kidsOf(li, "button");
      assert.equal(own.length, 1);
      const id = own[0].attrs["data-id"];
      parentOf[id] = parent;
      levelOf[id] = level;
      assert.equal(li.attrs.role, "treeitem");
      assert.equal(li.attrs["aria-level"], String(level));
      const groups = kidsOf(li, "ul");
      assert.equal(li.attrs["aria-expanded"], groups.length ? "true" : undefined);
      assert.deepEqual(li.children.map(c => c.tag), groups.length ? ["button", "ul"] : ["button"]);
      groups.forEach(group => { assert.equal(group.attrs.role, "group"); visit(group, id, level + 1); });
    });
  })(root, null, 1);
  graph.nodes.forEach(n => assert.equal(parentOf[n.id], n.parent, n.id));
  assert.equal(levelOf.root, 1);
  assert.equal(levelOf.web, 2);
  assert.equal(levelOf["web.identity"], 3);
  assert.equal(Object.keys(levelOf).length, graph.nodes.length);
});

test("an outline item carries the kind and status classes, the words of the chip and the status word, for the screen reader as well", () => {
  const root = listing(outline(sampleGraph(), {}));
  const li = select(root, "li").find(x => kidsOf(x, "button")[0].attrs["data-id"] === "web.identity");
  assert.deepEqual(classOf(li), ["woitem", "k-function", "st-waiting_on_you"]);
  const button = kidsOf(li, "button")[0];
  assert.deepEqual(button.children.map(c => [c.tag, classOf(c)[0], textOf(c)]), [["span", "wolab", "Client Lead"], ["span", "wosub", "Identity" + DOT + "1 open" + DOT + "5 closed"], ["span", "wost", "waiting on you"]]);
  assert.equal(button.attrs["aria-label"], "Client Lead, Identity" + DOT + "1 open" + DOT + "5 closed, waiting on you");
  const plainItem = select(root, "li").find(x => kidsOf(x, "button")[0].attrs["data-id"] === "web.adaptation");
  assert.equal(kidsOf(plainItem, "button")[0].children.length, 3, "an idle function says 'idle'");
  const rootItem = select(root, "li")[0];
  assert.deepEqual(kidsOf(rootItem, "button")[0].children.map(c => classOf(c)[0]), ["wolab", "wost"], "the root has no second line");
  const step = select(root, "li").find(x => kidsOf(x, "button")[0].attrs["data-id"] === "s-web");
  assert.deepEqual(kidsOf(kidsOf(step, "button")[0], "span").map(textOf), ["Coffee shop landing page", "task", "running now"]);
  const idleStep = listing(outline({nodes: [{id: "a", kind: "step", label: "A", status: "idle", parent: null}]}));
  assert.deepEqual(select(idleStep, "span").map(classOf).map(c => c[0]), ["wolab"], "an idle step has only its label");
  assert.equal(select(idleStep, "button")[0].attrs["aria-label"], "A");
});

test("a function that is waiting in the outline names who it waits for, or someone when it has no meta", () => {
  const root = listing(outline({nodes: [
    {id: "a", kind: "function", fn: "audit", label: "Audit", status: "waiting", parent: null},
    {id: "b", kind: "function", fn: "audit", label: "Audit", status: "waiting", parent: null, meta: {wait_on: "priority"}},
    {id: "c", kind: "function", fn: "audit", label: "Audit", status: "waiting", parent: null, meta: null},
    {id: "d", kind: "function", fn: "audit", label: "Audit", status: "waiting_on_you", parent: null, meta: {wait_on: "you"}},
  ]}));
  assert.deepEqual(select(root, "span.wost").map(textOf), ["waiting on someone", "waiting on Prioritiser", "waiting on someone", "waiting on you"]);
});

test("the selected item has .sel and aria-current, a fresh one .wnew, an unread one a dot", () => {
  const graph = sampleGraph();
  const root = listing(outline(graph, {selected: "web.audit", fresh: ["s-web"], unread: new Set(["support"])}));
  const item = id => select(root, "li").find(x => kidsOf(x, "button")[0].attrs["data-id"] === id);
  assert.ok(classOf(item("web.audit")).includes("sel"));
  assert.equal(kidsOf(item("web.audit"), "button")[0].attrs["aria-current"], "true");
  assert.equal(select(root, "li.sel").length, 1);
  assert.equal(select(root, "button[aria-current]").length, 1);
  assert.ok(classOf(item("s-web")).includes("wnew"));
  assert.equal(select(root, "li.wnew").length, 1);
  const dots = select(root, "span.wounread");
  assert.equal(dots.length, 1);
  assert.equal(dots[0].attrs.title, "Unread messages");
  assert.ok(kidsOf(item("support"), "button")[0].children.includes(dots[0]));
  const none = listing(outline(graph, {}));
  assert.equal(select(none, "li.sel").length + select(none, "li.wnew").length + select(none, "span.wounread").length, 0);
});

test("the outline repairs the tree the way layout does, and draws an unknown status as idle and an unknown kind as a step", () => {
  const html = outline({nodes: [
    {id: "a", kind: "person", label: "A", status: "busy", parent: "ghost"}, {id: "b", kind: "step", label: "B", status: "idle", parent: "b"},
    {id: "c", kind: "step", label: "C", parent: "d"}, {id: "d", kind: "step", label: "D", parent: "c"}, {id: "a", kind: "step"}, null]});
  const root = listing(html);
  assert.deepEqual(select(root, "button").map(b => b.attrs["data-id"]), ["a", "b", "c", "d"]);
  assert.deepEqual(classOf(select(root, "li")[0]), ["woitem", "k-step", "st-idle"]);
  assert.equal(select(root, "li").length, 4);
});

test("an empty or broken graph gives an empty list; a very deep graph does not overflow the stack", () => {
  for (const bad of [undefined, null, {}, {nodes: null}, {nodes: []}, 5, "x"]) assert.equal(outline(bad), '<ul class="wtree" role="tree"></ul>');
  const deep = [];
  for (let i = 0; i < 30000; i++) deep.push({id: "n" + i, kind: "step", label: "n" + i, status: "idle", parent: i === 0 ? null : "n" + (i - 1)});
  const html = outline({nodes: deep});
  assert.equal(html.split("<li ").length - 1, 30000);
  assert.equal(html.split("</li>").length - 1, 30000);
  assert.equal(html.split("<ul").length, 30001);
  assert.equal(html.split("</ul>").length, 30001);
});

test("the outline lists many roots side by side, and many children in order", () => {
  const root = listing(outline({nodes: [{id: "a", parent: null}, {id: "b", parent: null}, {id: "a1", parent: "a"}, {id: "a2", parent: "a"}, {id: "b1", parent: "b"}]}));
  assert.deepEqual(kidsOf(root, "li").map(li => kidsOf(li, "button")[0].attrs["data-id"]), ["a", "b"]);
  assert.deepEqual(kidsOf(kidsOf(kidsOf(root, "li")[0], "ul")[0], "li").map(li => kidsOf(li, "button")[0].attrs["data-id"]), ["a1", "a2"]);
});

/* ---------------------------------------------------------------- summary */
test("the header counts: teams, divisions, function nodes and steps, then how many are waiting on you; the root is not counted", () => {
  const s = summary(sampleGraph());
  assert.deepEqual(plain(s), {line: "2 teams" + DOT + "10 function nodes" + DOT + "2 steps" + DOT + "1 waiting on you", parts: ["2 teams", "10 function nodes", "2 steps", "1 waiting on you"], waiting: 1});
  const v = sampleView();
  v.nodes = v.nodes.filter(n => n.kind !== "step");
  v.edges = v.edges.filter(e => !/^s-/.test(e.dst) && !/^s-/.test(e.src));
  assert.equal(summary(GraphLayout.validate(v).graph).line, "2 teams" + DOT + "10 function nodes" + DOT + "1 waiting on you", "the design's own example");
});

test("a team and its Identity that wait on the same question count once; a separate node that waits counts again", () => {
  const nodes = [
    {id: "root", kind: "root", status: "waiting_on_you", parent: null},
    {id: "web", kind: "department", status: "waiting_on_you", parent: "root"}, {id: "web.identity", kind: "function", status: "waiting_on_you", parent: "web"},
    {id: "web.audit", kind: "function", status: "waiting_on_you", parent: "web"},
    {id: "sup", kind: "department", status: "idle", parent: "root"}, {id: "sup.identity", kind: "function", status: "waiting_on_you", parent: "sup"},
    {id: "sup.audit", kind: "function", status: "waiting", parent: "sup"}, {id: "sup.s", kind: "step", status: "waiting_on_you", parent: "sup"},
    {id: "lone", kind: "step", status: "waiting_on_you", parent: null},
  ];
  assert.equal(summary({nodes}).waiting, 2, "the root asks and covers everything under it; the lone step is a second one");
  assert.equal(summary({nodes: nodes.slice(1)}).waiting, 4, "without the root: web (it covers its Identity and Audit), sup.identity, sup.s, lone");
  assert.equal(summary({nodes: nodes.slice(1)}).line.endsWith("4 waiting on you"), true);
  assert.equal(summary({nodes: nodes.slice(4)}).waiting, 3, "sup is not asking: its Identity and its step are two, and the lone step");
  assert.equal(summary({nodes: [{id: "a", kind: "step", status: "waiting", parent: null}]}).waiting, 0, "waiting on a function is not waiting on you");
});

test("counts are singular for one, plural otherwise, and an unknown kind counts as a step", () => {
  const one1 = summary({nodes: [{id: "r", kind: "root", parent: null}, {id: "d", kind: "department", parent: "r"}, {id: "v", kind: "division", parent: "d"}, {id: "f", kind: "function", parent: "d"}, {id: "s", kind: "step", parent: "d"}]});
  assert.deepEqual(one1.parts, ["1 team", "1 division", "1 function node", "1 step"]);
  const many = summary({nodes: [{id: "d1", kind: "department"}, {id: "d2", kind: "department"}, {id: "v1", kind: "division"}, {id: "v2", kind: "division"}, {id: "p", kind: "person"}, {id: "q", kind: undefined}, {id: "z", kind: "constructor"}]});
  assert.deepEqual(many.parts, ["2 teams", "2 divisions", "3 steps"]);
  assert.equal(many.line, "2 teams" + DOT + "2 divisions" + DOT + "3 steps");
  assert.deepEqual(plain(summary({nodes: []})), {line: "", parts: [], waiting: 0});
  for (const bad of [undefined, null, 5, "x", {}, {nodes: "x"}]) assert.deepEqual(plain(summary(bad)), {line: "", parts: [], waiting: 0});
  assert.deepEqual(summary({nodes: [{id: "r", kind: "root"}]}).parts, [], "a lone root has nothing to count");
  assert.equal(summary({nodes: Array.from({length: 1500}, (_, i) => ({id: "d" + i, kind: "department"}))}).parts[0], "1,500 teams");
});

test("the counts go with the repaired tree: a repeated id counts once", () => {
  assert.equal(summary({nodes: [{id: "d", kind: "department"}, {id: "d", kind: "department"}, {id: "e", kind: "department", parent: "e"}]}).parts[0], "2 teams");
  assert.equal(summary({nodes: [{id: "a", status: "waiting_on_you", parent: "b", kind: "step"}, {id: "b", status: "waiting_on_you", parent: "a", kind: "step"}]}).waiting, 1);
});


/* ---------------------------------------------------------------- garbage in, no exception out */
// A seeded generator of hostile values: markup, prototype names, numbers that are not finite, nested lists and objects, and one cyclic object.
function fuzzer(seed) {
  let state = seed >>> 0;
  const next = () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const pick = list => list[Math.floor(next() * list.length)];
  const STR = ["", "a", "b", "web", "web.identity", "<script>", "\"'&", "__proto__", "constructor", "toString", "root", "department", "function", "step", "idle", "running",
    "waiting_on_you", "fault", "archived", "handoff", "depends_on", "speaks_to", "contains", "has_function", "has_step", "revises", "you", "audit", "3", "x".repeat(300),
    "\u0000\n\t", "\ud83d\ude00", "applied", "pending_approval", "2026-11-04T10:00:00Z"];
  const cyclic = () => { const o = {}; o.self = o; o.list = [o]; return o; };
  const value = (depth = 0) => {
    const r = next();
    if (r < 0.25) return pick(STR);
    if (r < 0.35) return pick([0, 1, -1, 1.5, NaN, Infinity, -Infinity, 1e21, 2 ** 31]);
    if (r < 0.42) return pick([null, undefined, true, false]);
    if (r < 0.44) return cyclic();
    if (depth > 3) return pick(STR);
    if (r < 0.62) return Array.from({length: Math.floor(next() * 4)}, () => value(depth + 1));
    const o = {};
    for (let i = 0, n = Math.floor(next() * 5); i < n; i++) {
      o[pick(["id", "kind", "label", "status", "detail", "meta", "stats", "fn", "x", "y", "w", "h", "d", "from", "to", "parent", "src", "dst", "wait_on", "atoms_total",
        "name", "seq", "added", "summary", "position", "parent_id", "tag", "mark", "kind", "label", "at", "reason", "task_title", "decision"])] = value(depth + 1);
    }
    return o;
  };
  return {next, pick, value, STR};
}

test("nothing the renderer is given can make it throw, and what it writes is always well formed with no stray text", () => {
  const f = fuzzer(20261105);
  const nodeOf = i => ({id: f.next() < 0.9 ? "n" + (i % 12) : f.value(), kind: f.pick(["root", "department", "division", "function", "step", f.value()]), label: f.value(),
    status: f.pick(["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made", f.value()]), detail: f.value(),
    meta: f.next() < 0.5 ? {stats: f.value(), wait_on: f.value()} : f.value(), fn: f.value(), step_ref: f.value(), parent: f.next() < 0.7 ? "n" + Math.floor(f.next() * 12) : f.value()});
  const end = () => (f.next() < 0.9 ? "n" + Math.floor(f.next() * 12) : f.value());
  let boxes = 0;
  let paths = 0;
  for (let round = 0; round < 300; round++) {
    const graph = {nodes: Array.from({length: Math.floor(f.next() * 14)}, (_, i) => nodeOf(i)),
      cross: Array.from({length: Math.floor(f.next() * 14)}, () => ({from: end(), to: end(), kind: f.pick(["handoff", "depends_on", "speaks_to", "step", f.value()]), label: f.value()}))};
    const L = GraphLayout.layout(graph);
    const options = {selected: f.value(), hot: f.pick(f.STR), marks: f.value(), unread: f.value(), fresh: f.value(), ring: f.value(), uid: f.value(), title: f.value(), action: f.value()};
    const picture = drawing(L, options);
    boxes += select(picture, "g.wnode").length;
    paths += select(picture, "path.wedge").length;
    drawing(f.value(), options);
    drawing(hand(Array.from({length: 4}, () => f.value()), Array.from({length: 3}, () => f.value()), Array.from({length: 3}, () => f.value())), options);
    listing(outline(graph, options));
    listing(outline(f.value(), f.value()));
    summary(graph);
    summary(f.value());
    ["statusLook", "statusWord", "kindWord", "chipText", "edgeLook", "textWidth", "fit"].forEach(name => GraphRender[name](f.value(), f.value(), f.value()));
    const chip = chipText(nodeOf(round));
    assert.ok(["line1", "line2", "tip"].every(k => typeof chip[k] === "string"));
  }
  assert.ok(boxes > 1000 && paths > 600, `the garbage was not empty: ${boxes} boxes, ${paths} links`);
});

/* ---------------------------------------------------------------- the three modules together */
test("a graph goes from the wire to a picture: validate, layout, svg, with every node and link on it", () => {
  const {graph, warnings} = GraphLayout.validate(sampleView());
  assert.deepEqual(warnings, []);
  const L = GraphLayout.layout(graph);
  const root = drawing(L, {uid: "all"});
  assert.equal(select(root, "g.wnode").length, 15);
  assert.equal(select(root, "path.wedge").length, 14 + 9);
  assert.equal(select(root, "g.wnode.st-waiting_on_you").length, 2);
  assert.equal(select(root, "circle.wbadge").length, 2);
  assert.equal(select(root, "g.wnode.k-function").length, 10);
  assert.equal(select(root, "text.wedgelab").length, 2);
  assert.equal(select(root, "path.wedge.loop").length, 4, "the handoff pair and the speaks_to pair");
});
