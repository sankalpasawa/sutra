"use strict";
// ChartMarks (sutra_app/ui/static/js/chart_marks.js): the org chart as a graph (toGraph), the marks of the selected change (marks) and the
// change log (logHtml). docs/design/ui.md sections 6.3, 7 and 10; S2-models-01, S3-web-04.
// Run with: node --test tests/ui/js/chart_marks.test.js
//
// The log shows clock times in the viewer's own time zone, so this file pins the zone to UTC before any date is made (and tries other
// zones in one test). The markup is read by a small XML reader (balanced tags, quoted attributes, no raw "<", no stray "&").
process.env.TZ = "UTC";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const FILE = path.join(JS, "chart_marks.js");
const CODE = fs.readFileSync(FILE, "utf8");
const ChartMarks = require(FILE);
const GraphLayout = require(path.join(JS, "graph_layout.js"));
const GraphRender = require(path.join(JS, "graph_render.js"));
const {toGraph, marks, logHtml} = ChartMarks;

const DOT = " \u00b7 ";

/* ---------------------------------------------------------------- helpers */
const plain = value => JSON.parse(JSON.stringify(value));
function deepFreeze(value) {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

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
const classOf = node => (node.attrs.class || "").split(/\s+/).filter(Boolean);
const find = (node, pred) => { const out = []; walk(node, n => { if (n.tag !== "#root" && pred(n)) out.push(n); }); return out; };
const textOf = (node, skip = () => false) => node.content.map(c => (typeof c === "string" ? c : skip(c) ? "" : textOf(c, skip))).join("");
const logOf = html => {
  const doc = parse(html);
  assert.equal(doc.text, "", "nothing outside the log");
  assert.equal(doc.children.length, 1);
  return doc.children[0];
};
const rowsOf = html => find(logOf(html), n => classOf(n).includes("chgrow"));
// the words of a row without its reason
const wordsOf = row => textOf(row, c => classOf(c).includes("chgreason"));

const CHART = {version: 2, nodes: [
  {id: "root", kind: "root", name: "Root", purpose: "", parent_id: null, position: 0},
  {id: "web", kind: "department", name: "Web", purpose: "Websites and landing pages", parent_id: "root", position: 0},
  {id: "support", kind: "department", name: "Support", purpose: "Answers to customers", parent_id: "root", position: 1},
  {id: "quotes", kind: "division", name: "Quotes", purpose: "Prices for jobs", parent_id: "web", position: 0},
]};
const change = (seq, over = {}) => ({seq, id: "chg-" + String(seq).padStart(4, "0"), at: "2026-11-04T10:00:03Z", actor: "chat_agent", decision: "add", status: "applied",
  summary: "Added the Web team", reason: "No team makes websites", task_id: "req-17", task_title: "Coffee shop landing page", revision: seq,
  added: [], moved: [], archived: [], reused: [], ...over});

/* ---------------------------------------------------------------- loading */
test("loads with require and exposes the three functions of the design", () => {
  assert.deepEqual(Object.keys(ChartMarks).sort(), ["logHtml", "marks", "toGraph"]);
  for (const f of [toGraph, marks, logHtml]) assert.equal(typeof f, "function");
});

test("loads as a classic script with one global, ChartMarks, and needs no other script", () => {
  const sandbox = vm.createContext({});
  vm.runInContext(CODE, sandbox, {filename: "chart_marks.js"});
  assert.deepEqual(Object.keys(sandbox), ["ChartMarks"]);
  const changes = [change(1, {added: ["web"]})];
  assert.deepEqual(plain(sandbox.ChartMarks.toGraph(CHART)), plain(toGraph(CHART)));
  assert.deepEqual(plain(sandbox.ChartMarks.marks(changes)), plain(marks(changes)));
  assert.equal(sandbox.ChartMarks.logHtml(changes), logHtml(changes));
});

test("where module is null or has no exports the global is set instead; where it has exports they are filled", () => {
  for (const mod of [null, {}, {exports: null}, {exports: 0}, 5, "x"]) {
    const sandbox = vm.createContext({module: mod});
    vm.runInContext(CODE, sandbox);
    assert.equal(typeof sandbox.ChartMarks.marks, "function", JSON.stringify(mod));
  }
  const sandbox = vm.createContext({module: {exports: {}}});
  vm.runInContext(CODE, sandbox);
  assert.equal(typeof sandbox.module.exports.logHtml, "function");
  assert.equal("ChartMarks" in sandbox, false);
});

test("the sources of this package stay ASCII", () => {
  assert.equal(/[^\x00-\x7f]/.test(CODE), false);
});

/* ---------------------------------------------------------------- toGraph */
test("toGraph maps name to label, purpose to detail and parent_id to parent, in the shape GraphLayout takes", () => {
  const g = toGraph(CHART);
  assert.deepEqual(Object.keys(g), ["nodes", "links", "cross"]);
  assert.deepEqual(plain(g.nodes.map(n => [n.id, n.kind, n.label, n.detail, n.parent])), [
    ["root", "root", "Root", "", null], ["web", "department", "Web", "Websites and landing pages", "root"],
    ["quotes", "division", "Quotes", "Prices for jobs", "web"], ["support", "department", "Support", "Answers to customers", "root"]]);
  assert.deepEqual(plain(g.nodes[1]), {id: "web", kind: "department", label: "Web", status: "idle", detail: "Websites and landing pages", parent: "root", chat_session_id: null,
    org_node_id: "web", dept_id: "web", task_id: null, fn: null, step_ref: null, version: null, meta: {}});
  assert.deepEqual(plain(g.nodes[2]).dept_id, null, "only a department has a dept_id");
  assert.deepEqual(plain(g.nodes[0]).dept_id, null);
  assert.deepEqual(plain(g.links), [{from: "root", to: "web", kind: "contains"}, {from: "web", to: "quotes", kind: "contains"}, {from: "root", to: "support", kind: "contains"}]);
  assert.deepEqual(g.cross, []);
  assert.ok(g.nodes.every(n => n.status === "idle"), "the chart has no status: every node is idle");
});

test("siblings come in position order, whatever order the nodes were sent in; equal positions keep the order sent", () => {
  const chart = {nodes: [
    {id: "r", kind: "root", name: "R", parent_id: null, position: 0},
    {id: "c", kind: "department", name: "C", parent_id: "r", position: 2},
    {id: "a", kind: "department", name: "A", parent_id: "r", position: 0},
    {id: "b", kind: "department", name: "B", parent_id: "r", position: 1},
    {id: "a2", kind: "division", name: "A2", parent_id: "a", position: 1},
    {id: "a1", kind: "division", name: "A1", parent_id: "a", position: 0},
    {id: "t2", kind: "department", name: "T2", parent_id: "r", position: 5},
    {id: "t1", kind: "department", name: "T1", parent_id: "r", position: 5},
  ]};
  const g = toGraph(chart);
  assert.deepEqual(g.nodes.filter(n => n.parent === "r").map(n => n.id), ["a", "b", "c", "t2", "t1"]);
  assert.deepEqual(g.nodes.filter(n => n.parent === "a").map(n => n.id), ["a1", "a2"]);
  const L = GraphLayout.layout(g);
  assert.deepEqual(L.nodes.filter(n => n.parent === "r").sort((p, q) => p.x - q.x).map(n => n.id), ["a", "b", "c", "t2", "t1"], "and the picture follows it");
});

test("a missing, non-numeric or non-finite position counts as 0", () => {
  const chart = {nodes: [
    {id: "r", kind: "root", name: "R", parent_id: null},
    {id: "z", kind: "department", name: "Z", parent_id: "r", position: 1},
    {id: "n", kind: "department", name: "N", parent_id: "r", position: "0"},
    {id: "u", kind: "department", name: "U", parent_id: "r"},
    {id: "i", kind: "department", name: "I", parent_id: "r", position: Infinity},
    {id: "a", kind: "department", name: "A", parent_id: "r", position: NaN},
    {id: "neg", kind: "department", name: "Neg", parent_id: "r", position: -1},
  ]};
  assert.deepEqual(toGraph(chart).nodes.map(n => n.id), ["neg", "r", "n", "u", "i", "a", "z"]);
});

test("a number that is not finite is no text: NaN and Infinity give the id as label and no detail", () => {
  const g = toGraph({nodes: [{id: "a", kind: "department", name: NaN, purpose: Infinity, parent_id: null}, {id: "b", kind: "department", name: -Infinity, purpose: 0, parent_id: null}]});
  assert.deepEqual(g.nodes.map(n => [n.label, n.detail]), [["a", ""], ["b", "0"]]);
});

test("a name that is empty or only blanks gives the id as label; text fields are strings; ids are as sent", () => {
  const g = toGraph({nodes: [
    {id: "a", kind: "department", name: "", purpose: null, parent_id: null}, {id: "b", kind: "department", name: "   ", purpose: 4, parent_id: ""},
    {id: "c", kind: "department", name: 12, purpose: {}, parent_id: 5}, {id: "d", kind: "department", name: " Padded ", parent_id: undefined},
  ]});
  assert.deepEqual(g.nodes.map(n => n.label), ["a", "b", "12", " Padded "]);
  assert.deepEqual(g.nodes.map(n => n.detail), ["", "4", "", ""]);
  assert.deepEqual(g.nodes.map(n => n.parent), [null, null, null, null], "a parent_id that is not a non-empty string is no parent");
});

test("a link is made only for a parent that is in the chart and is not the node itself; the node keeps the parent it names for layout to repair", () => {
  const g = toGraph({nodes: [
    {id: "r", kind: "root", name: "R", parent_id: null, position: 0},
    {id: "a", kind: "department", name: "A", parent_id: "ghost", position: 1},
    {id: "b", kind: "department", name: "B", parent_id: "b", position: 2},
    {id: "c", kind: "department", name: "C", parent_id: "r", position: 3},
  ]});
  assert.deepEqual(plain(g.links), [{from: "r", to: "c", kind: "contains"}]);
  assert.equal(g.nodes[1].parent, "ghost");
  const L = GraphLayout.layout(g);
  assert.equal(L.warnings.length, 2, "layout says what it repaired");
  assert.deepEqual(L.nodes.map(n => n.depth), [0, 1, 0, 0]);
});

test("entries that are not objects are skipped; a node with no id is kept for layout to drop with a warning", () => {
  const g = toGraph({nodes: [null, 4, "x", [], {id: "r", kind: "root", name: "R", parent_id: null}, {kind: "department", name: "No id"}, {id: 5, kind: "root"}]});
  assert.deepEqual(g.nodes.map(n => n.id), ["r", "", "5"]);
  const L = GraphLayout.layout(g);
  assert.deepEqual(L.nodes.map(n => n.id), ["r", "5"]);
  assert.equal(L.warnings.length, 1);
  assert.match(L.warnings[0], /no id/);
});

test("a repeated id, or a loop of parents, is left for layout to repair with a warning", () => {
  const dup = GraphLayout.layout(toGraph({nodes: [{id: "r", kind: "root", name: "R", parent_id: null}, {id: "r", kind: "department", name: "Again", parent_id: null}]}));
  assert.deepEqual(dup.nodes.map(n => n.label), ["R"]);
  assert.equal(dup.warnings.length, 1);
  const loop = GraphLayout.layout(toGraph({nodes: [{id: "a", kind: "department", name: "A", parent_id: "b"}, {id: "b", kind: "department", name: "B", parent_id: "a"}]}));
  assert.equal(loop.nodes.length, 2);
  assert.equal(loop.warnings.length, 1);
});

test("toGraph throws a TypeError for a value that is not a chart, so a view can keep its last good picture", () => {
  for (const bad of [null, undefined, 5, "x", [], {}, {nodes: null}, {nodes: {}}, {nodes: "x"}, true]) {
    assert.throws(() => toGraph(bad), error => error instanceof TypeError && error.message === "ChartMarks.toGraph: the chart must be an object with a nodes array", JSON.stringify(bad));
  }
  assert.deepEqual(plain(toGraph({nodes: []})), {nodes: [], links: [], cross: []});
});

test("toGraph does not change the chart, hands back new objects, and the same chart gives the same graph", () => {
  const input = deepFreeze(JSON.parse(JSON.stringify(CHART)));
  const a = toGraph(input);
  assert.deepEqual(plain(toGraph(input)), plain(a));
  a.nodes[0].label = "changed";
  assert.equal(input.nodes[0].name, "Root");
  assert.notEqual(toGraph(input).nodes[0], toGraph(input).nodes[0]);
});

test("the chart's graph lays out without a warning and draws, with the department being viewed ringed", () => {
  const L = GraphLayout.layout(toGraph(CHART));
  assert.deepEqual(L.warnings, []);
  assert.deepEqual(L.nodes.map(n => [n.id, n.depth]), [["root", 0], ["web", 1], ["quotes", 2], ["support", 1]]);
  assert.deepEqual(L.edges, []);
  const html = GraphRender.svg(L, {uid: "chart", ring: "web", title: "Org chart"});
  const root = parse(html).children[0];
  assert.equal(find(root, n => classOf(n).includes("wnode")).length, 4);
  assert.deepEqual(find(root, n => classOf(n).includes("cur")).map(n => n.attrs["data-id"]), ["web"]);
  assert.deepEqual(find(root, n => classOf(n).includes("k-division")).map(n => n.attrs["data-id"]), ["quotes"]);
});

/* ---------------------------------------------------------------- marks */
const marked = (changes, seq) => plain(marks(changes, seq));

test("the newest change marks its added, moved and reused nodes, with a tag that names the task", () => {
  const changes = [change(1, {added: ["root"], task_title: ""}), change(2, {decision: "rearrange", added: ["support"], moved: ["web"], reused: ["root"], task_title: "Coffee shop landing page"})];
  assert.deepEqual(marked(changes), {
    support: {mark: "add", tag: "added by task: Coffee shop landing page"},
    web: {mark: "move", tag: "moved by task: Coffee shop landing page"},
    root: {mark: "reuse", tag: "reused by task: Coffee shop landing page"},
  });
  assert.deepEqual(Object.keys(marked(changes)), ["support", "web", "root"], "added first, then moved, then reused");
});

test("a change with no task title is named by its number", () => {
  const changes = [change(12, {added: ["web"], task_title: ""}), change(13, {moved: ["web"], task_title: "   "}), change(14, {reused: ["web"], task_title: null}), change(15, {added: ["web"], task_title: undefined})];
  assert.deepEqual(marked(changes, 12), {web: {mark: "add", tag: "added by change 12"}});
  assert.deepEqual(marked(changes, 13), {web: {mark: "move", tag: "moved by change 13"}});
  assert.deepEqual(marked(changes, 14), {web: {mark: "reuse", tag: "reused by change 14"}});
  assert.deepEqual(marked(changes, 15), {web: {mark: "add", tag: "added by change 15"}});
  assert.equal(marks([change(3, {added: ["web"], task_title: "  A\n\tB  "})]).web.tag, "added by task: A B", "a title is put on one line");
});

test("an older change can be selected, by number or by the digits of one; a number that no change has selects nothing", () => {
  const changes = [change(1, {added: ["root"]}), change(2, {added: ["web"]}), change(3, {moved: ["support"]})];
  assert.deepEqual(Object.keys(marked(changes)), ["support"], "the default is the newest");
  assert.deepEqual(Object.keys(marked(changes, 2)), ["web"]);
  assert.deepEqual(Object.keys(marked(changes, 1)), ["root"]);
  assert.deepEqual(Object.keys(marked(changes, "2")), ["web"]);
  assert.deepEqual(Object.keys(marked(changes, "003")), ["support"]);
  assert.deepEqual(marked(changes, 4), {});
  assert.deepEqual(marked(changes, 0), {});
  assert.deepEqual(marked(changes, "x"), {});
  assert.deepEqual(marked(changes, "2 "), {});
  assert.deepEqual(marked(changes, 2.5), {});
  assert.deepEqual(marked(changes, NaN), {});
  assert.deepEqual(marked(changes, {}), {});
  assert.deepEqual(marked(changes, -1), {});
  assert.deepEqual(Object.keys(marked(changes, null)), ["support"], "none asked: the newest");
  assert.deepEqual(Object.keys(marked(changes, undefined)), ["support"]);
});

test("the newest is the highest seq, whatever order the list is in", () => {
  const changes = [change(3, {added: ["c"]}), change(10, {added: ["ten"]}), change(2, {added: ["b"]}), change(9, {added: ["nine"]})];
  assert.deepEqual(Object.keys(marked(changes)), ["ten"]);
  assert.deepEqual(Object.keys(marked(changes.slice().reverse())), ["ten"]);
  assert.deepEqual(Object.keys(marked([change(2, {added: ["first"]}), change(2, {added: ["second"]})])), ["first"], "equal numbers: the first in the list");
});

test("a change that is waiting, rejected, stale or failed marks nothing, because its lists are only a plan", () => {
  for (const status of ["pending_approval", "rejected", "stale", "failed", "", undefined, null, "Applied", "bogus", 5]) {
    const changes = [change(1, {added: ["web"], moved: ["support"], reused: ["root"], status})];
    assert.deepEqual(marked(changes), {}, String(status));
  }
  assert.deepEqual(Object.keys(marked([change(1, {added: ["web"], status: "applied"})])), ["web"]);
  // the newest is a plan: the chart shows nothing, however good the one before it was
  assert.deepEqual(marked([change(1, {added: ["web"]}), change(2, {added: ["support"], status: "pending_approval"})]), {});
  assert.deepEqual(Object.keys(marked([change(1, {added: ["web"]}), change(2, {added: ["support"], status: "pending_approval"})], 1)), ["web"], "but it can be selected");
});

test("archived nodes are not in the chart and are never marked", () => {
  assert.deepEqual(marked([change(5, {decision: "rearrange", archived: ["old"], added: [], moved: ["web"]})]), {web: {mark: "move", tag: "moved by task: Coffee shop landing page"}});
  assert.deepEqual(marked([change(5, {archived: ["old"]})]), {});
});

test("missing or odd lists are tolerated; ids that are not names are skipped; a node in two lists takes the first", () => {
  assert.deepEqual(marked([{seq: 1, status: "applied"}]), {});
  assert.deepEqual(marked([{seq: 1, status: "applied", added: null, moved: "web", reused: {web: 1}}]), {});
  assert.deepEqual(Object.keys(marked([change(1, {added: ["a", "", null, 7, {}, [], "b", "a"], moved: [undefined, "c"]})])), ["a", "b", "c"]);
  assert.deepEqual(marked([change(1, {added: ["x"], moved: ["x"], reused: ["x"]})]).x.mark, "add", "added wins over moved and reused");
  assert.deepEqual(marked([change(1, {moved: ["x"], reused: ["x"]})]).x.mark, "move", "moved wins over reused");
  assert.deepEqual(Object.keys(marked([change(1, {added: ["__proto__", "constructor", "toString"]})])), ["__proto__", "constructor", "toString"], "an id is a key like any other");
  assert.equal(Object.getPrototypeOf(marks([change(1, {added: ["__proto__"]})])), Object.prototype, "and does not change what the result is");
  assert.equal(Object.prototype.hasOwnProperty.call(marks([change(1, {added: ["__proto__"]})]), "__proto__"), true);
});

test("changes that are not a list, entries that are not changes and changes with no seq are skipped", () => {
  for (const bad of [undefined, null, 5, "x", {}, [], [null, 4, "x", [], {}], [{added: ["web"], status: "applied"}], [{seq: "1", added: ["web"], status: "applied"}], [{seq: NaN, added: ["web"], status: "applied"}], [{seq: Infinity}]]) {
    assert.deepEqual(marked(bad), {}, JSON.stringify(bad));
  }
  assert.deepEqual(Object.keys(marked([null, {added: ["no"], status: "applied"}, change(4, {added: ["web"]})])), ["web"]);
});

test("marks hands back a new plain object each time and does not change the changes", () => {
  const changes = deepFreeze([change(1, {added: ["web"]})]);
  const a = marks(changes);
  assert.deepEqual(plain(marks(changes)), plain(a));
  a.web.tag = "changed";
  assert.equal(marks(changes).web.tag, "added by task: Coffee shop landing page");
  assert.notEqual(marks(changes), marks(changes));
});

test("the marks go straight into the picture: add dashed, move accented, reuse plain, with the tag spoken", () => {
  const changes = [change(2, {decision: "rearrange", added: ["quotes"], moved: ["support"], reused: ["web"]})];
  const L = GraphLayout.layout(toGraph(CHART));
  const root = parse(GraphRender.svg(L, {uid: "chart", marks: marks(changes)})).children[0];
  const byId = Object.fromEntries(find(root, n => classOf(n).includes("wnode")).map(n => [n.attrs["data-id"], n]));
  assert.ok(classOf(byId.quotes).includes("mk-add"));
  assert.ok(classOf(byId.support).includes("mk-move"));
  assert.ok(classOf(byId.web).includes("mk-reuse"));
  assert.equal(classOf(byId.root).some(c => c.startsWith("mk-")), false);
  assert.match(byId.quotes.attrs["aria-label"], /added by task: Coffee shop landing page\./);
});

/* ---------------------------------------------------------------- the log */
test("the log lists the changes newest first, each as a button row with its number, summary, time and task", () => {
  const changes = [change(1, {summary: "Started the chart", task_title: "", at: "2026-11-04T09:00:00Z"}), change(2), change(3, {decision: "rearrange", summary: "Moved Support", task_title: "Refunds", at: "2026-11-04T10:30:59Z"})];
  const root = logOf(logHtml(changes));
  assert.equal(root.tag, "div");
  assert.deepEqual(classOf(root), ["chglog"]);
  assert.equal(root.attrs.role, "group");
  assert.equal(root.attrs["aria-label"], "Changes to the org chart");
  assert.equal(root.text, "", "nothing but the rows is in it");
  assert.deepEqual(root.children.map(c => c.tag), ["div", "div", "div"]);
  const rows = rowsOf(logHtml(changes));
  assert.deepEqual(rows.map(r => r.attrs["data-change"]), ["3", "2", "1"]);
  rows.forEach(r => { assert.equal(r.tag, "div"); assert.equal(r.attrs.role, "button"); assert.equal(r.attrs.tabindex, "0"); });
  assert.equal(wordsOf(rows[0]), "Change 3" + DOT + "Moved Support" + DOT + "10:30" + DOT + "for 'Refunds'");
  assert.equal(wordsOf(rows[1]), "Change 2" + DOT + "Added the Web team" + DOT + "10:00" + DOT + "for 'Coffee shop landing page'", "the design's own row");
  assert.equal(wordsOf(rows[2]), "Change 1" + DOT + "Started the chart" + DOT + "09:00");
  assert.deepEqual(logOf(logHtml(changes.slice().reverse())), logOf(logHtml(changes)), "the list's order does not matter");
});

test("the time is an element with the instant and the full date; it is shown in the viewer's own time zone", () => {
  const html = logHtml([change(2)]);
  const time = find(logOf(html), n => n.tag === "time")[0];
  assert.deepEqual([time.attrs.datetime, time.attrs.title, textOf(time)], ["2026-11-04T10:00:03Z", "2026-11-04 10:00", "10:00"]);
  const before = process.env.TZ;
  try {
    process.env.TZ = "Asia/Kolkata";
    if (new Date("2026-11-04T10:00:03Z").getHours() === 15) {          // the zone can be changed at run time (it can on macOS and Linux)
      const t = find(logOf(logHtml([change(2)])), n => n.tag === "time")[0];
      assert.deepEqual([t.attrs.datetime, t.attrs.title, textOf(t)], ["2026-11-04T10:00:03Z", "2026-11-04 15:30", "15:30"]);
      process.env.TZ = "America/New_York";
      const u = find(logOf(logHtml([change(2, {at: "2026-11-04T01:05:00Z"})])), n => n.tag === "time")[0];
      assert.deepEqual([u.attrs.title, textOf(u)], ["2026-11-03 20:05", "20:05"], "and the date moves with the zone");
    }
  } finally {
    process.env.TZ = before;
  }
  const pad = find(logOf(logHtml([change(2, {at: "2026-01-02T03:04:05Z"})])), n => n.tag === "time")[0];
  assert.deepEqual([pad.attrs.title, textOf(pad)], ["2026-01-02 03:04", "03:04"], "hours, minutes, months and days have two digits");
});

test("a time that is no date is left out; a change with no summary or no task is shorter", () => {
  for (const at of [undefined, null, "", "yesterday", 5, "2026-13-45T99:99:99Z", {}]) {
    const row = rowsOf(logHtml([change(2, {at})]))[0];
    assert.equal(find(row, n => n.tag === "time").length, 0, String(at));
    assert.equal(wordsOf(row), "Change 2" + DOT + "Added the Web team" + DOT + "for 'Coffee shop landing page'");
  }
  assert.equal(wordsOf(rowsOf(logHtml([change(7, {summary: "", task_title: ""})]))[0]), "Change 7" + DOT + "10:00");
  assert.equal(wordsOf(rowsOf(logHtml([change(7, {summary: "  \n ", task_title: undefined, at: undefined})]))[0]), "Change 7");
});

test("a change that did not change the chart says so: 'waiting for your yes or no', or 'not applied'", () => {
  const word = status => {
    const row = rowsOf(logHtml([change(2, {status})]))[0];
    const spans = find(row, n => classOf(n).includes("chgstatus"));
    return spans.length === 0 ? null : textOf(spans[0]);
  };
  assert.equal(word("applied"), null);
  assert.equal(word("pending_approval"), "waiting for your yes or no");
  for (const status of ["rejected", "stale", "failed", "", undefined, null, "weird", 3]) assert.equal(word(status), "not applied", String(status));
  const row = rowsOf(logHtml([change(2, {status: "rejected"})]))[0];
  assert.equal(wordsOf(row), "Change 2" + DOT + "Added the Web team" + DOT + "10:00" + DOT + "for 'Coffee shop landing page'" + DOT + "not applied");
  assert.deepEqual(classOf(row), ["chgrow", "dec-add", "st-rejected", "sel"]);
});

test("the classes of a row: the decision, the status and .sel; an unknown decision has no class and an unknown status is st-unknown", () => {
  const c = (seq, decision, status) => change(seq, {decision, status});
  const rows = rowsOf(logHtml([c(1, "reuse", "applied"), c(2, "add", "pending_approval"), c(3, "rearrange", "stale"), c(4, "mystery", "failed"), c(5, "add", "odd"), c(6, undefined, undefined)]));
  assert.deepEqual(rows.map(r => r.attrs["data-change"]), ["6", "5", "4", "3", "2", "1"]);
  assert.deepEqual(rows.map(classOf), [
    ["chgrow", "st-unknown", "sel"],
    ["chgrow", "dec-add", "st-unknown"],
    ["chgrow", "st-failed"],
    ["chgrow", "dec-rearrange", "st-stale"],
    ["chgrow", "dec-add", "st-pending_approval"],
    ["chgrow", "dec-reuse", "st-applied"],
  ]);
});

test("the newest row is selected and shows its reason; selecting another moves both, and a number nobody has selects none", () => {
  const changes = [change(1, {reason: "first reason", summary: "One"}), change(2, {reason: "second reason", summary: "Two"}), change(3, {reason: "third reason", summary: "Three"})];
  const selection = html => rowsOf(html).filter(r => classOf(r).includes("sel")).map(r => r.attrs["data-change"]);
  const reasons = html => find(logOf(html), n => classOf(n).includes("chgreason")).map(textOf);
  assert.deepEqual(selection(logHtml(changes)), ["3"]);
  assert.deepEqual(reasons(logHtml(changes)), ["third reason"]);
  assert.deepEqual(rowsOf(logHtml(changes)).map(r => r.attrs["aria-pressed"]), ["true", "false", "false"]);
  for (const seq of [1, "1"]) {
    assert.deepEqual(selection(logHtml(changes, seq)), ["1"]);
    assert.deepEqual(reasons(logHtml(changes, seq)), ["first reason"]);
    assert.deepEqual(rowsOf(logHtml(changes, seq)).map(r => r.attrs["aria-pressed"]), ["false", "false", "true"]);
  }
  for (const seq of [9, 0, "x", 1.5, NaN, {}]) {
    assert.deepEqual(selection(logHtml(changes, seq)), [], String(seq));
    assert.deepEqual(reasons(logHtml(changes, seq)), []);
    assert.deepEqual(rowsOf(logHtml(changes, seq)).map(r => r.attrs["aria-pressed"]), ["false", "false", "false"]);
  }
  assert.deepEqual(selection(logHtml(changes, null)), ["3"]);
});

test("the reason is shown for the selected row only, in a block of its own, and not when it is empty", () => {
  const html = logHtml([change(1, {reason: "r1"}), change(2, {reason: "  \n "}), change(3, {reason: "r3"})], 1);
  const rows = rowsOf(html);
  assert.deepEqual(rows.map(r => find(r, n => classOf(n).includes("chgreason")).length), [0, 0, 1]);
  const reason = find(rows[2], n => classOf(n).includes("chgreason"))[0];
  assert.equal(reason.tag, "div");
  assert.equal(textOf(reason), "r1");
  for (const reason of ["", undefined, null, "   ", 5.5]) {
    const alone = rowsOf(logHtml([change(2, {reason})]))[0];
    assert.equal(classOf(alone).includes("sel"), true);
    assert.deepEqual(find(alone, n => classOf(n).includes("chgreason")).map(textOf), reason === 5.5 ? ["5.5"] : [], String(reason));
  }
  assert.equal(textOf(find(logOf(logHtml([change(2, {reason: "a\n\n b\t c"})])), n => classOf(n).includes("chgreason"))[0]), "a b c");
  assert.equal(find(logOf(logHtml([change(2, {reason: "x (planned by keywords)"})])), n => classOf(n).includes("chgreason")).map(textOf)[0], "x (planned by keywords)");
});

test("an empty log, or no usable change, says there is none yet", () => {
  for (const bad of [[], undefined, null, 5, "x", {}, [null, 4, "x"], [{summary: "no seq"}], [{seq: NaN}]]) {
    const html = logHtml(bad);
    assert.equal(html, '<div class="chglog" role="group" aria-label="Changes to the org chart"><p class="chgnone">No changes yet.</p></div>');
    assert.equal(logOf(html).text, "");
  }
});

test("a change with no seq is not listed; changes with the same seq are both listed, in order", () => {
  const rows = rowsOf(logHtml([{summary: "no seq"}, change(1, {summary: "kept"}), change(1, {summary: "twin"}), null]));
  assert.deepEqual(rows.map(r => wordsOf(r).split(DOT)[1]), ["kept", "twin"]);
  assert.deepEqual(rows.map(r => classOf(r).includes("sel")), [true, false], "only the first of two with one number is the selected one");
});

test("words from the wire are escaped in the log and the markup stays well formed", () => {
  const evil = `<script>alert("x")</script> & 'q' "d" </div><b onclick=1>`;
  const html = logHtml([change(1, {summary: evil, reason: evil, task_title: evil, at: `2026-11-04T10:00:03Z"><script>`, decision: evil, status: evil})], 1);
  assert.equal(html.includes("<script"), false);
  const root = logOf(html);
  const tags = new Set();
  const attributes = new Set();
  walk(root, n => { tags.add(n.tag); Object.keys(n.attrs).forEach(a => attributes.add(a)); });
  assert.deepEqual([...tags].sort(), ["div", "span"].sort());
  assert.equal([...attributes].some(a => a.startsWith("on")), false);
  const row = rowsOf(html)[0];
  assert.equal(wordsOf(row), "Change 1" + DOT + evil + DOT + "for '" + evil + "'" + DOT + "not applied", "the words themselves come back exactly, as text");
  assert.equal(textOf(find(root, n => classOf(n).includes("chgreason"))[0]), evil);
  assert.deepEqual(classOf(row), ["chgrow", "st-unknown", "sel"], "an unknown decision and status come in as no class at all");
  assert.equal(row.attrs["data-change"], "1");
});

test("an instant the date parser accepts with markup in a comment is escaped in the attribute", () => {
  const at = 'Nov 4 2026 10:00 UTC ("><b onclick=1>\' & x)';
  assert.equal(Number.isNaN(new Date(at).getTime()), false, "the parser takes this one");
  const html = logHtml([change(1, {at})]);
  const time = find(logOf(html), n => n.tag === "time")[0];
  assert.equal(time.attrs.datetime, at);
  assert.deepEqual([time.attrs.title, textOf(time)], ["2026-11-04 10:00", "10:00"]);
  assert.equal(find(logOf(html), n => n.tag === "b").length, 0);
});

test("a seq that is not a whole number is written as the number it is", () => {
  const html = logHtml([change(1.5), change(2)]);
  assert.deepEqual(rowsOf(html).map(r => r.attrs["data-change"]), ["2", "1.5"]);
  assert.equal(wordsOf(rowsOf(html)[1]).startsWith("Change 1.5"), true);
});

test("logHtml does not change what it is given and gives the same string twice", () => {
  const changes = deepFreeze([change(1, {added: ["web"]}), change(2, {status: "pending_approval"})]);
  const a = logHtml(changes, 1);
  assert.equal(logHtml(changes, 1), a);
  assert.equal(logHtml(JSON.parse(JSON.stringify(changes)), 1), a);
  assert.notEqual(logHtml(changes, 2), a);
});

test("a log of 2000 changes is built in a moment and is well formed", () => {
  const changes = Array.from({length: 2000}, (_, i) => change(i + 1, {summary: "Change " + i, reason: "why " + i}));
  const t = performance.now();
  const html = logHtml(changes, 1000);
  assert.ok(performance.now() - t < 500);
  const rows = rowsOf(html);
  assert.equal(rows.length, 2000);
  assert.equal(rows[0].attrs["data-change"], "2000");
  assert.equal(rows.filter(r => classOf(r).includes("sel"))[0].attrs["data-change"], "1000");
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

test("nothing toGraph, marks and logHtml are given can make them throw, but a value that is not a chart, and the log is always well formed", () => {
  const f = fuzzer(20261106);
  let marked = 0;
  let rows = 0;
  const changeOf = () => ({seq: f.pick([1, 2, 3, f.value()]), id: f.value(), at: f.pick(["2026-11-04T10:00:00Z", "Nov 4 2026 10:00 UTC (<b>)", f.value()]), decision: f.value(),
    status: f.pick(["applied", "applied", "applied", "pending_approval", "rejected", f.value()]), summary: f.value(), reason: f.value(), task_title: f.value(),
    added: f.pick([f.value(), [f.value(), "a"], ["a", "b"]]), moved: f.pick([f.value(), ["c"], ["__proto__"]]), reused: f.pick([f.value(), ["d", "a"]]), archived: f.value()});
  for (let round = 0; round < 400; round++) {
    const changes = Array.from({length: Math.floor(f.next() * 5)}, changeOf);
    const wanted = f.pick([undefined, undefined, 1, 2, 3, f.value()]);
    const made = marks(changes, wanted);
    assert.equal(Object.getPrototypeOf(made), Object.prototype);
    assert.ok(Object.values(made).every(m => ["add", "move", "reuse"].includes(m.mark) && typeof m.tag === "string"));
    marked += Object.keys(made).length;
    rows += rowsOf(logHtml(changes, wanted)).length;
    assert.equal(logOf(logHtml(changes, wanted)).text, "");
    logHtml(f.value(), f.value());
    marks(f.value(), f.value());
    const chart = {nodes: Array.from({length: Math.floor(f.next() * 10)}, () => ({id: f.pick(["a", "b", "c", f.value()]), kind: f.value(), name: f.value(), purpose: f.value(),
      parent_id: f.pick(["a", "b", "c", f.value()]), position: f.value()}))};
    const graph = toGraph(chart);
    GraphLayout.layout(graph);
    GraphRender.svg(GraphLayout.layout(graph), {marks: made, ring: f.value(), uid: f.value()});
    assert.throws(() => toGraph(f.pick([null, undefined, 3, "x", [], {}, {nodes: 3}])), TypeError);
  }
  assert.ok(marked > 200 && rows > 500, `the garbage was not empty: ${marked} marks, ${rows} rows`);
});
