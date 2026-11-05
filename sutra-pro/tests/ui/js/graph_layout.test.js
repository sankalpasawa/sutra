"use strict";
// GraphLayout (sutra_app/ui/static/js/graph_layout.js): validate (GraphView to tree and cross links), layout (a layered tree on a page,
// tree links, cross links, ports, loops) and diff. docs/design/ui.md sections 6.1, 7 and 10; S3-web-13.
// Run with: node --test tests/ui/js/graph_layout.test.js
//
// The module is a classic browser script that also does module.exports; most tests use require, one group runs the text in a vm context
// as a browser loads it. Nothing here touches a clock except the timing check, and nothing is random (the random trees use a seeded generator).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.resolve(__dirname, "../../../sutra_app/ui/static/js/graph_layout.js");
const CODE = fs.readFileSync(FILE, "utf8");
const GraphLayout = require(FILE);
const {validate, layout, diff, forest} = GraphLayout;

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
const rawNode = (id, kind = "step", extra = {}) => ({id, kind, label: id, status: "idle", detail: "", meta: {}, ...extra});
const edge = (src, dst, kind = "contains", label = "") => ({src, dst, kind, label});
const view = (nodes, edges = []) => ({version: 1, chart_version: 1, nodes, edges});

// The department of the design's examples: web, its five function nodes (in the server's order), a step.
function department(id, status = "idle") {
  const nodes = [rawNode(id, "department", {label: id, status})];
  const edges = [];
  FUNCTIONS.forEach(fn => {
    nodes.push(rawNode(id + "." + fn, "function", {label: fn[0].toUpperCase() + fn.slice(1), fn, dept_id: id}));
    edges.push(edge(id, id + "." + fn, "has_function"));
  });
  nodes.push(rawNode("s-" + id, "step", {label: "Coffee shop landing page", step_ref: "task", dept_id: id}));
  edges.push(edge(id, "s-" + id, "has_step"));
  return {nodes, edges};
}
function sampleView() {
  const web = department("web", "waiting_on_you");
  const support = department("support", "running");
  return view(
    [rawNode("root", "root", {label: "Root", status: "running"}), ...web.nodes, ...support.nodes],
    [edge("root", "web"), edge("root", "support"), ...web.edges, ...support.edges,
      edge("web.identity", "web.adaptation", "handoff"), edge("web.audit", "web.identity", "handoff"),
      edge("web.identity", "web.coordination", "speaks_to", "3"), edge("web.audit", "web.priority", "depends_on", "revises"),
      edge("web.identity", "s-web", "step")],
  );
}
// A graph in validate's shape with only the fields layout needs: ids, kinds, parents, cross links.
const lnode = (id, parent = null, kind = "step", extra = {}) => ({id, kind, label: id, status: "idle", parent, ...extra});
const clink = (from, to, kind = "handoff", label = "") => ({from, to, kind, label});

function byId(list) { return new Map(list.map(n => [n.id, n])); }
const cx = n => n.x + n.w / 2;
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function bezier(d) {
  const m = /^M(-?[\d.]+),(-?[\d.]+) C(-?[\d.]+),(-?[\d.]+) (-?[\d.]+),(-?[\d.]+) (-?[\d.]+),(-?[\d.]+)$/.exec(d);
  assert.ok(m, `not a cubic path: ${d}`);
  const n = m.slice(1).map(Number);
  const at = t => ({x: (1 - t) ** 3 * n[0] + 3 * (1 - t) ** 2 * t * n[2] + 3 * (1 - t) * t * t * n[4] + t ** 3 * n[6],
    y: (1 - t) ** 3 * n[1] + 3 * (1 - t) ** 2 * t * n[3] + 3 * (1 - t) * t * t * n[5] + t ** 3 * n[7]});
  return {p: {x: n[0], y: n[1]}, c1: {x: n[2], y: n[3]}, c2: {x: n[4], y: n[5]}, q: {x: n[6], y: n[7]}, at};
}
// a small seeded generator (mulberry32), so the "random" trees are the same every run
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function randomGraph(seed, count) {
  const next = rng(seed);
  const kinds = ["department", "division", "function", "step", "root"];
  const nodes = [lnode("n0", null, "root")];
  for (let i = 1; i < count; i++) {
    const parent = next() < 0.08 ? null : "n" + Math.floor(next() * i);
    nodes.push(lnode("n" + i, parent, kinds[Math.floor(next() * kinds.length)]));
  }
  const cross = [];
  for (let i = 0; i < count; i++) {
    const a = "n" + Math.floor(next() * count);
    const b = "n" + Math.floor(next() * count);
    if (a !== b) cross.push(clink(a, b, ["handoff", "depends_on", "speaks_to", "step"][Math.floor(next() * 4)]));
  }
  return {nodes, cross};
}

/* ---------------------------------------------------------------- loading */
test("loads with require and exposes the vocabulary, frozen", () => {
  assert.deepEqual(Object.keys(GraphLayout).sort(), ["CROSS_KINDS", "DEFAULTS", "KINDS", "SIZES", "STATUSES", "TREE_KINDS", "diff", "forest", "layout", "validate"]);
  assert.deepEqual([...GraphLayout.STATUSES], NINE);
  assert.deepEqual([...GraphLayout.KINDS], ["root", "department", "division", "function", "step"]);
  assert.deepEqual([...GraphLayout.TREE_KINDS], ["contains", "has_function", "has_step"]);
  assert.deepEqual([...GraphLayout.CROSS_KINDS], ["handoff", "depends_on", "speaks_to", "step"]);
  assert.deepEqual(plain(GraphLayout.SIZES), {root: {w: 96, h: 34}, department: {w: 168, h: 54}, division: {w: 150, h: 46}, function: {w: 168, h: 50}, step: {w: 140, h: 40}});
  assert.deepEqual(plain(GraphLayout.DEFAULTS), {pad: 40, slot: 178, rowGap: 78, maxRise: 60});
  for (const frozen of [GraphLayout.STATUSES, GraphLayout.KINDS, GraphLayout.TREE_KINDS, GraphLayout.CROSS_KINDS, GraphLayout.SIZES, GraphLayout.SIZES.root, GraphLayout.DEFAULTS]) {
    assert.ok(Object.isFrozen(frozen));
  }
  assert.throws(() => { GraphLayout.DEFAULTS.pad = 1; }, TypeError);
});

test("loads as a classic script: one global, GraphLayout, and nothing else", () => {
  const sandbox = vm.createContext({});
  vm.runInContext(CODE, sandbox, {filename: "graph_layout.js"});
  assert.deepEqual(Object.keys(sandbox), ["GraphLayout"]);
  const result = sandbox.GraphLayout.validate(sampleView());
  assert.deepEqual(plain(result), plain(validate(sampleView())));
  assert.deepEqual(plain(sandbox.GraphLayout.layout(result.graph)), plain(layout(validate(sampleView()).graph)));
});

test("where module is null or has no exports the global is set instead; where it has exports they are filled", () => {
  for (const mod of [null, {}, {exports: null}, {exports: 0}, 5, "x"]) {
    const sandbox = vm.createContext({module: mod});
    vm.runInContext(CODE, sandbox);
    assert.equal(typeof sandbox.GraphLayout.validate, "function", JSON.stringify(mod));
  }
  const sandbox = vm.createContext({module: {exports: {}}});
  vm.runInContext(CODE, sandbox);
  assert.equal(typeof sandbox.module.exports.layout, "function");
  assert.equal("GraphLayout" in sandbox, false);
});

test("the sources of this package stay ASCII", () => {
  assert.equal(/[^\x00-\x7f]/.test(CODE), false);
});

/* ---------------------------------------------------------------- validate */
test("validate builds each parent from the incoming contains, has_function or has_step edge", () => {
  const {graph, warnings} = validate(sampleView());
  assert.deepEqual(warnings, []);
  const parents = Object.fromEntries(graph.nodes.map(n => [n.id, n.parent]));
  assert.equal(parents.root, null);
  assert.equal(parents.web, "root");
  assert.equal(parents.support, "root");
  FUNCTIONS.forEach(fn => assert.equal(parents["web." + fn], "web"));
  assert.equal(parents["s-web"], "web");
  assert.equal(parents["support.audit"], "support");
  const kindOf = Object.fromEntries(graph.links.map(l => [l.to, l.kind]));
  assert.equal(kindOf.web, "contains");
  assert.equal(kindOf["web.identity"], "has_function");
  assert.equal(kindOf["s-web"], "has_step");
  assert.equal(graph.links.length, graph.nodes.length - 1);
  assert.ok(graph.links.every(l => parents[l.to] === l.from));
});

test("validate keeps handoff, depends_on, speaks_to, step and any other kind as cross links, in order, with their labels", () => {
  const v = sampleView();
  v.edges.push(edge("web.priority", "web.audit", "mentions", "x"));
  const {graph, warnings} = validate(v);
  assert.deepEqual(warnings, []);
  assert.deepEqual(plain(graph.cross), [
    {from: "web.identity", to: "web.adaptation", kind: "handoff", label: ""},
    {from: "web.audit", to: "web.identity", kind: "handoff", label: ""},
    {from: "web.identity", to: "web.coordination", kind: "speaks_to", label: "3"},
    {from: "web.audit", to: "web.priority", kind: "depends_on", label: "revises"},
    {from: "web.identity", to: "s-web", kind: "step", label: ""},
    {from: "web.priority", to: "web.audit", kind: "mentions", label: "x"},
  ]);
  // none of them made a parent
  assert.equal(graph.nodes.find(n => n.id === "web.adaptation").parent, "web");
});

test("a node with no incoming structural edge is a root, and the array order is the sibling order", () => {
  const {graph} = validate(view([rawNode("a", "department"), rawNode("b", "department"), rawNode("c", "step")], [edge("a", "c", "has_step")]));
  assert.deepEqual(graph.nodes.map(n => [n.id, n.parent]), [["a", null], ["b", null], ["c", "a"]]);
  const sample = validate(sampleView()).graph;
  const kids = sample.nodes.filter(n => n.parent === "web").map(n => n.id);
  assert.deepEqual(kids, ["web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit", "s-web"]);
});

test("validate normalises a node: label falls back to the id, text fields are strings, ids are string or null", () => {
  const {graph, warnings} = validate(view([
    {id: "a", kind: "step", status: "idle", label: "  ", detail: null, version: "7", meta: null, chat_session_id: "", org_node_id: 5, dept_id: "web", task_id: undefined, fn: null, step_ref: "task"},
    {id: "b", kind: "department", status: "filed", label: 12, detail: 3.5, version: 9, meta: {run_id: "r"}, chat_session_id: "cs_1", org_node_id: "b", dept_id: null, task_id: "tsk_1", fn: "x", step_ref: null},
  ]));
  assert.deepEqual(warnings, []);
  assert.deepEqual(plain(graph.nodes[0]), {id: "a", kind: "step", label: "a", status: "idle", detail: "", parent: null, chat_session_id: null, org_node_id: null,
    dept_id: "web", task_id: null, fn: null, step_ref: "task", version: null, meta: {}});
  assert.deepEqual(plain(graph.nodes[1]), {id: "b", kind: "department", label: "12", status: "filed", detail: "3.5", parent: null, chat_session_id: "cs_1", org_node_id: "b",
    dept_id: null, task_id: "tsk_1", fn: "x", step_ref: null, version: 9, meta: {run_id: "r"}});
  const blank = validate(view([{id: "z"}])).graph.nodes[0];
  assert.equal(blank.label, "z");
  assert.equal(blank.status, "idle");
  assert.equal(blank.kind, "step");
});

test("the label is kept as sent when it has any text (not trimmed)", () => {
  assert.equal(validate(view([rawNode("a", "step", {label: " Coffee "})])).graph.nodes[0].label, " Coffee ");
});

test("each of J2's nine status words and the five kinds is accepted without a warning", () => {
  NINE.forEach(status => {
    const {graph, warnings} = validate(view([rawNode("a", "step", {status})]));
    assert.deepEqual(warnings, [], status);
    assert.equal(graph.nodes[0].status, status);
  });
  ["root", "department", "division", "function", "step"].forEach(kind => {
    const {graph, warnings} = validate(view([rawNode("a", kind)]));
    assert.deepEqual(warnings, [], kind);
    assert.equal(graph.nodes[0].kind, kind);
  });
});

test("an unknown status is drawn as idle and an unknown kind as a step, each with a warning that names the node", () => {
  for (const status of ["busy", "", undefined, null, 4, "Running", "__proto__"]) {
    const {graph, warnings} = validate(view([rawNode("a", "step", {status})]));
    assert.equal(graph.nodes[0].status, "idle");
    assert.equal(warnings.length, 1, String(status));
    assert.match(warnings[0], /"a"/);
    assert.match(warnings[0], /drawn as idle/);
  }
  for (const kind of ["person", "", undefined, null, 4, "Step", "constructor"]) {
    const {graph, warnings} = validate(view([{...rawNode("a"), kind}]));
    assert.equal(graph.nodes[0].kind, "step");
    assert.equal(warnings.length, 1, String(kind));
    assert.match(warnings[0], /drawn as a step/);
  }
});

test("archived nodes are not drawn, nor the links to them, and no warning is made; their children become roots", () => {
  const {graph, warnings} = validate(view(
    [rawNode("a", "department"), rawNode("old", "division", {status: "archived"}), rawNode("kid", "step"), rawNode("b", "step")],
    [edge("a", "old"), edge("old", "kid", "has_step"), edge("a", "b", "has_step"), edge("old", "b", "handoff"), edge("b", "old", "speaks_to", "2")],
  ));
  assert.deepEqual(warnings, []);
  assert.deepEqual(graph.nodes.map(n => [n.id, n.parent]), [["a", null], ["kid", null], ["b", "a"]]);
  assert.deepEqual(graph.cross, []);
  assert.deepEqual(graph.links.map(l => [l.from, l.to]), [["a", "b"]]);
});

test("a node without a usable id, or a repeated id, is dropped with a warning; the first of a repeated id stays", () => {
  const {graph, warnings} = validate(view([
    rawNode("a", "department", {label: "first"}), rawNode("a", "department", {label: "second"}), {kind: "step"}, null, "text", {id: 4}, {id: ""}, rawNode("b"),
  ]));
  assert.deepEqual(graph.nodes.map(n => [n.id, n.label]), [["a", "first"], ["b", "b"]]);
  assert.equal(warnings.length, 6);
  assert.ok(warnings.some(w => /appears twice/.test(w) && /"a"/.test(w)));
  assert.equal(warnings.filter(w => /has no id/.test(w)).length, 5);
  assert.ok(warnings.some(w => /^node 3 has no id/.test(w)));
});

test("an edge without a source or a target, to a node that is not there, or from a node to itself is dropped with a warning", () => {
  const nodes = [rawNode("a", "department"), rawNode("b", "step")];
  const cases = [
    [{dst: "b", kind: "handoff"}, /no source or no target/], [{src: "a", kind: "handoff"}, /no source or no target/], [null, /no source or no target/],
    [{src: "", dst: "b", kind: "handoff"}, /no source or no target/], [{src: 3, dst: "b", kind: "handoff"}, /no source or no target/],
    [edge("a", "ghost", "handoff"), /not in the graph/], [edge("ghost", "a", "has_step"), /not in the graph/],
    [edge("a", "a", "handoff"), /to itself/], [edge("b", "b", "has_step"), /to itself/],
  ];
  cases.forEach(([bad, pattern]) => {
    const {graph, warnings} = validate(view(nodes, [bad, edge("a", "b", "has_step")]));
    assert.equal(warnings.length, 1, JSON.stringify(bad));
    assert.match(warnings[0], pattern);
    assert.deepEqual(graph.nodes.map(n => n.parent), [null, "a"]);
    assert.deepEqual(graph.cross, []);
  });
});

test("a second parent is refused (the first stays) and a repeated cross link is dropped, each with a warning", () => {
  const nodes = [rawNode("a", "department"), rawNode("b", "department"), rawNode("c", "step")];
  const second = validate(view(nodes, [edge("a", "c", "has_step"), edge("b", "c", "has_step")]));
  assert.equal(second.graph.nodes[2].parent, "a");
  assert.equal(second.warnings.length, 1);
  assert.match(second.warnings[0], /second parent/);
  assert.match(second.warnings[0], /"a" stays/);
  assert.deepEqual(second.graph.links.map(l => [l.from, l.to]), [["a", "c"]]);
  const mixed = validate(view(nodes, [edge("a", "c", "has_step"), edge("b", "c", "contains")]));
  assert.equal(mixed.graph.nodes[2].parent, "a");
  assert.equal(mixed.graph.links[0].kind, "has_step");

  const twice = validate(view(nodes, [edge("a", "b", "handoff", "x"), edge("a", "b", "handoff", "y"), edge("a", "b", "depends_on"), edge("b", "a", "handoff")]));
  assert.deepEqual(twice.graph.cross.map(c => [c.from, c.to, c.kind, c.label]), [["a", "b", "handoff", "x"], ["a", "b", "depends_on", ""], ["b", "a", "handoff", ""]]);
  assert.equal(twice.warnings.length, 1);
  assert.match(twice.warnings[0], /appears twice/);
});

test("links are told apart by kind, source and target as a whole, however their words run together", () => {
  // "step" + "a" + "bc" and "step" + "ab" + "c" are the same letters in a row, and so are "x" + "yy" + "z" and "xy" + "y" + "z"
  const nodes = [rawNode("a"), rawNode("bc"), rawNode("ab"), rawNode("c"), rawNode("yy"), rawNode("z"), rawNode("y")];
  const edges = [edge("a", "bc", "step"), edge("ab", "c", "step"), edge("a", "bc", "ste"), edge("yy", "z", "x"), edge("y", "z", "xy")];
  const {graph, warnings} = validate(view(nodes, edges));
  assert.deepEqual(warnings, []);
  assert.deepEqual(graph.cross.map(c => [c.kind, c.from, c.to]), [["step", "a", "bc"], ["step", "ab", "c"], ["ste", "a", "bc"], ["x", "yy", "z"], ["xy", "y", "z"]]);
  const L = layout({nodes: nodes.map(n => lnode(n.id)), cross: graph.cross});
  assert.deepEqual(L.warnings, []);
  assert.equal(L.edges.length, 5);
  assert.deepEqual(L.edges.map(e => e.loop), [false, false, false, false, false]);
  // and a reverse twin is found by the same key
  const twins = layout({nodes: ["a", "bc", "ab", "c"].map(id => lnode(id)), cross: [clink("a", "bc", "step"), clink("bc", "a", "step"), clink("ab", "c", "step"), clink("c", "ab", "mystery")]});
  assert.deepEqual(twins.edges.map(e => e.loop), [true, true, false, false]);
});

test("an edge without a kind is a plain link (step) with a warning; a kind that is not a string counts as no kind", () => {
  const nodes = [rawNode("a"), rawNode("b")];
  for (const kind of [undefined, "", null, 7, {}]) {
    const {graph, warnings} = validate(view(nodes, [{src: "a", dst: "b", kind, label: "l"}]));
    assert.deepEqual(plain(graph.cross), [{from: "a", to: "b", kind: "step", label: "l"}], String(kind));
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /no kind/);
  }
});

test("a label that is not a string is an empty label", () => {
  const {graph} = validate(view([rawNode("a"), rawNode("b")], [{src: "a", dst: "b", kind: "handoff", label: 5}]));
  assert.equal(graph.cross[0].label, "5");
  assert.equal(validate(view([rawNode("a"), rawNode("b")], [{src: "a", dst: "b", kind: "handoff", label: {}}])).graph.cross[0].label, "");
});

test("a loop of parents is cut at its lowest id, which is drawn as a root, with one warning", () => {
  const nodes = [rawNode("c", "department"), rawNode("a", "department"), rawNode("b", "department"), rawNode("tail", "step")];
  const {graph, warnings} = validate(view(nodes, [edge("a", "b"), edge("b", "c"), edge("c", "a"), edge("c", "tail", "has_step")]));
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /each other's parents/);
  assert.match(warnings[0], /"a" is drawn as a root/);
  const parents = Object.fromEntries(graph.nodes.map(n => [n.id, n.parent]));
  assert.deepEqual(parents, {c: "b", a: null, b: "a", tail: "c"});
  assert.deepEqual(graph.links.map(l => l.to).sort(), ["b", "c", "tail"]);
  // and the picture can be made from it
  assert.deepEqual(layout(graph).warnings, []);
});

test("a loop is cut among its own members, not at a node that only hangs from it", () => {
  // the walk up from "0t" (a child of a) goes a, b, c and back to a: the ring is a, b, c, and "0t" is lower than all of them
  const f = forest([lnode("0t", "a"), lnode("a", "b"), lnode("b", "c"), lnode("c", "a")]);
  assert.deepEqual(f.warnings, ['nodes "a", "b", "c" are each other\'s parents; "a" is drawn as a root']);
  assert.deepEqual(f.order, ["a", "0t", "c", "b"], "every node is reached: a is the root, 0t and c hang from it, b from c");
  assert.deepEqual(f.nodes.map(n => [n.id, n.parent]), [["0t", "a"], ["a", null], ["b", "c"], ["c", "a"]]);
  const v = validate(view([rawNode("0t"), rawNode("a"), rawNode("b"), rawNode("c")], [edge("a", "0t", "has_step"), edge("b", "a"), edge("c", "b"), edge("a", "c")]));
  assert.deepEqual(v.warnings, ['nodes "a", "b", "c" are each other\'s parents; "a" is drawn as a root']);
  assert.equal(layout(v.graph).nodes.length, 4);
});

test("nothing validate is given can make it throw, but a value that is not a graph", () => {
  for (const bad of [null, undefined, 5, "text", true, [], {}, {nodes: null}, {nodes: {}}, {nodes: "x"}]) {
    assert.throws(() => validate(bad), TypeError, JSON.stringify(bad));
  }
  for (const edges of ["x", {}, 4, true]) {
    assert.throws(() => validate({nodes: [], edges}), /edges must be an array/);
  }
  assert.deepEqual(plain(validate({nodes: []})), {graph: {nodes: [], links: [], cross: []}, warnings: []});
  assert.deepEqual(plain(validate({nodes: [], edges: null})), {graph: {nodes: [], links: [], cross: []}, warnings: []});
  assert.equal(validate(view([rawNode("a")], [undefined, 4, "x", [], {}])).warnings.length, 5);
});

test("validate does not change what it is given, and hands back new objects", () => {
  const input = deepFreeze(sampleView());
  const first = validate(input);
  assert.deepEqual(plain(validate(input)), plain(first));
  first.graph.nodes[0].label = "changed";
  first.graph.cross.push({});
  assert.equal(input.nodes[0].label, "Root");
  assert.notEqual(first.graph.nodes[1], input.nodes[1]);
  assert.equal(plain(validate(sampleView())).graph.nodes[0].label, "Root");
});

test("warnings are plain sentences with the ids quoted", () => {
  const {warnings} = validate(view([rawNode("a", "step", {status: "x"})], [edge("a", "zz", "handoff")]));
  assert.ok(warnings.every(w => typeof w === "string" && w.length > 10));
  assert.ok(warnings.some(w => w.includes('"zz"')));
});

/* ---------------------------------------------------------------- the words of the warnings */
test("the warnings of validate say exactly what was repaired, one sentence each", () => {
  const say = (nodes, edges) => validate(view(nodes, edges)).warnings;
  assert.deepEqual(say([{kind: "step"}, rawNode("b"), rawNode("b")]), ["node 1 has no id and is not drawn", 'node "b" appears twice; the later one is not drawn']);
  assert.deepEqual(say([rawNode("a", "step", {status: "busy"})]), ['node "a" has status "busy"; it is drawn as idle']);
  assert.deepEqual(say([rawNode("a", "step", {status: 7})]), ['node "a" has status "7"; it is drawn as idle']);
  assert.deepEqual(say([rawNode("a", "step", {status: {}})]), ['node "a" has status ""; it is drawn as idle']);
  assert.deepEqual(say([{...rawNode("a"), kind: "person"}]), ['node "a" has kind "person"; it is drawn as a step']);
  assert.deepEqual(say([{...rawNode("a"), kind: undefined}]), ['node "a" has kind ""; it is drawn as a step']);
  const two = [rawNode("a"), rawNode("b")];
  assert.deepEqual(say(two, [{src: "a"}, {dst: "b"}]), ["link 1 has no source or no target and is not drawn", "link 2 has no source or no target and is not drawn"]);
  assert.deepEqual(say(two, [{src: "a", dst: "b", label: "l"}]), ['link "a" -> "b" has no kind; it is drawn as a plain link']);
  assert.deepEqual(say(two, [edge("a", "ghost", "handoff")]), ['link "a" -> "ghost" (handoff) names a node that is not in the graph and is not drawn']);
  assert.deepEqual(say(two, [edge("ghost", "b", "has_step")]), ['link "ghost" -> "b" (has_step) names a node that is not in the graph and is not drawn']);
  assert.deepEqual(say(two, [edge("a", "a", "speaks_to")]), ['link "a" -> "a" (speaks_to) joins a node to itself and is not drawn']);
  assert.deepEqual(say([rawNode("a"), rawNode("b"), rawNode("c")], [edge("a", "c", "has_step"), edge("b", "c", "contains")]),
    ['link "b" -> "c" (contains) gives "c" a second parent; "a" stays']);
  assert.deepEqual(say(two, [edge("a", "b", "step"), edge("a", "b", "step", "again")]), ['link "a" -> "b" (step) appears twice; the later one is not drawn']);
  assert.deepEqual(say([rawNode("b"), rawNode("a"), rawNode("c")], [edge("a", "b"), edge("b", "c"), edge("c", "a")]),
    ['nodes "b", "a", "c" are each other\'s parents; "a" is drawn as a root'], "the loop is listed from the first node of the list that is in it, parent after parent");
});

test("the warnings of forest and layout say exactly what was repaired", () => {
  assert.deepEqual(forest([lnode("a", "ghost")]).warnings, ['node "a" names parent "ghost", which is not drawn; it is drawn as a root']);
  assert.deepEqual(forest([lnode("a", "a")]).warnings, ['node "a" is its own parent; it is drawn as a root']);
  assert.deepEqual(forest([lnode("d", "c"), lnode("c", "d")]).warnings, ['nodes "d", "c" are each other\'s parents; "c" is drawn as a root']);
  assert.deepEqual(forest([{parent: null}, lnode("a"), lnode("a")]).warnings, ["node 1 has no id and is not drawn", 'node "a" appears twice; the later one is not drawn']);
  const warnings = layout({nodes: [lnode("a"), lnode("b")], cross: [clink("a", "ghost", "handoff"), clink("a", "a", "step"), clink("a", "b", "speaks_to"), clink("a", "b", "speaks_to")]}).warnings;
  assert.deepEqual(warnings, ['link "a" -> "ghost" (handoff) names a node that is not drawn and is skipped', 'link "a" -> "a" (step) joins a node to itself and is skipped',
    'link "a" -> "b" (speaks_to) appears twice; the later one is skipped']);
});

test("a cross link with a missing end says so in layout, naming the end that is there", () => {
  const nodes = [lnode("a"), lnode("b")];
  assert.deepEqual(layout({nodes, cross: [{to: "b", kind: "handoff"}]}).warnings, ['link "" -> "b" (handoff) names a node that is not drawn and is skipped']);
  assert.deepEqual(layout({nodes, cross: [{from: "a", kind: "step"}]}).warnings, ['link "a" -> "" (step) names a node that is not drawn and is skipped']);
  assert.deepEqual(layout({nodes, cross: [{from: 5, to: "b"}]}).warnings, ['link "" -> "b" (step) names a node that is not drawn and is skipped']);
  assert.deepEqual(layout({nodes, cross: [null]}).warnings, ['link "" -> "" (step) names a node that is not drawn and is skipped']);
});

test("the errors validate throws say what was wrong", () => {
  assert.throws(() => validate(null), error => error instanceof TypeError && error.message === "GraphLayout.validate: the graph must be an object with a nodes array");
  assert.throws(() => validate({nodes: "x"}), error => error instanceof TypeError && error.message === "GraphLayout.validate: the graph must be an object with a nodes array");
  assert.throws(() => validate({nodes: [], edges: 3}), error => error instanceof TypeError && error.message === "GraphLayout.validate: edges must be an array");
});

/* ---------------------------------------------------------------- forest */
test("forest gives roots, children, depth-first order and depth", () => {
  const f = forest([lnode("r"), lnode("a", "r"), lnode("b", "r"), lnode("a1", "a"), lnode("a2", "a"), lnode("s")]);
  assert.deepEqual(f.roots, ["r", "s"]);
  assert.deepEqual(f.order, ["r", "a", "a1", "a2", "b", "s"]);
  assert.deepEqual([...f.depth], [["r", 0], ["a", 1], ["a1", 2], ["a2", 2], ["b", 1], ["s", 0]]);
  assert.deepEqual([...f.children].map(([id, kids]) => [id, kids]), [["r", ["a", "b"]], ["a", ["a1", "a2"]], ["b", []], ["a1", []], ["a2", []], ["s", []]]
    .sort((x, y) => ["r", "a", "b", "a1", "a2", "s"].indexOf(x[0]) - ["r", "a", "b", "a1", "a2", "s"].indexOf(y[0])));
  assert.deepEqual(f.warnings, []);
  assert.deepEqual(f.nodes.map(n => n.id), ["r", "a", "b", "a1", "a2", "s"]);
});

test("forest repairs a missing, own or looping parent and a repeated id, and never throws", () => {
  const f = forest([lnode("a", "ghost"), lnode("b", "b"), lnode("c", "d"), lnode("d", "c"), lnode("a", "d"), {parent: "a"}, null]);
  assert.deepEqual(f.roots, ["a", "b", "c"]);
  assert.deepEqual(f.order, ["a", "b", "c", "d"]);
  assert.equal(f.warnings.length, 6);
  assert.ok(f.warnings.some(w => /names parent "ghost", which is not drawn/.test(w)));
  assert.ok(f.warnings.some(w => /"b" is its own parent/.test(w)));
  assert.ok(f.warnings.some(w => /"c", "d" are each other's parents; "c" is drawn as a root/.test(w)));
  assert.deepEqual(forest(undefined).order, []);
  assert.deepEqual(forest("x").order, []);
  assert.deepEqual(forest(null).roots, []);
});

test("forest takes a very deep chain and a very wide level without overflowing the stack", () => {
  const deep = [lnode("n0")];
  for (let i = 1; i < 60000; i++) deep.push(lnode("n" + i, "n" + (i - 1)));
  const f = forest(deep);
  assert.equal(f.order.length, 60000);
  assert.equal(f.depth.get("n59999"), 59999);
  const wide = [lnode("r")];
  for (let i = 0; i < 20000; i++) wide.push(lnode("w" + i, "r"));
  assert.equal(forest(wide).children.get("r").length, 20000);
  // a long loop is found and cut as well
  const ring = [];
  for (let i = 0; i < 30000; i++) ring.push(lnode("r" + String(i).padStart(6, "0"), "r" + String((i + 1) % 30000).padStart(6, "0")));
  const cut = forest(ring);
  assert.deepEqual(cut.roots, ["r000000"]);
  assert.equal(cut.warnings.length, 1);
});

test("forest copies its nodes and puts the parent that stands on them", () => {
  const input = [lnode("a", "zz"), lnode("b", "a")];
  const f = forest(input);
  assert.equal(f.nodes[0].parent, null);
  assert.equal(input[0].parent, "zz");
  assert.notEqual(f.nodes[1], input[1]);
});

/* ---------------------------------------------------------------- layout: the tree on a page */
test("the smallest tree, to the pixel: a root over two leaves", () => {
  const g = {nodes: [lnode("root", null, "root"), lnode("a", "root", "department"), lnode("b", "root", "department")], cross: []};
  const L = layout(g);
  assert.deepEqual(L.warnings, []);
  const n = byId(L.nodes);
  // a department is 168 x 54 and a root 96 x 34; slots are 178 wide, rows (54 + 78) apart, the leftmost box starts at x = 40
  assert.deepEqual(plain([n.get("a"), n.get("b"), n.get("root")].map(({id, x, y, w, h, depth}) => ({id, x, y, w, h, depth}))), [
    {id: "a", x: 40, y: 172, w: 168, h: 54, depth: 1},
    {id: "b", x: 218, y: 172, w: 168, h: 54, depth: 1},
    {id: "root", x: 165, y: 40, w: 96, h: 34, depth: 0},
  ]);
  assert.equal(L.width, 426);
  assert.equal(L.height, 266);
  assert.deepEqual(plain(L.links.map(l => ({from: l.from, to: l.to, d: l.d, x1: l.x1, y1: l.y1, x2: l.x2, y2: l.y2}))), [
    {from: "root", to: "a", d: "M213,74 C213,123 124,123 124,172", x1: 213, y1: 74, x2: 124, y2: 172},
    {from: "root", to: "b", d: "M213,74 C213,123 302,123 302,172", x1: 213, y1: 74, x2: 302, y2: 172},
  ]);
  assert.deepEqual(L.edges, []);
});

test("layout answers the shape of the design: nodes with id, kind, x, y, w, h and depth in depth-first order, links, edges, size, warnings", () => {
  const L = layout(validate(sampleView()).graph);
  assert.deepEqual(Object.keys(L), ["nodes", "links", "edges", "width", "height", "warnings"]);
  assert.deepEqual(L.nodes.map(n => n.id), ["root", "web", "web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit", "s-web",
    "support", "support.identity", "support.adaptation", "support.priority", "support.coordination", "support.audit", "s-support"]);
  L.nodes.forEach(n => {
    ["id", "kind", "x", "y", "w", "h", "depth"].forEach(key => assert.ok(key in n, key));
    assert.equal(typeof n.label, "string");
    assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y));
  });
  assert.deepEqual(L.nodes.map(n => n.depth), [0, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2]);
  const sizes = {root: [96, 34], department: [168, 54], function: [168, 50], step: [140, 40]};
  L.nodes.forEach(n => assert.deepEqual([n.w, n.h], sizes[n.kind], n.id));
  assert.equal(L.links.length, L.nodes.length - 1);
  assert.equal(L.edges.length, 5);
});

test("a parent is centred over its first and last child, in any tree", () => {
  for (const kids of [1, 2, 3, 4, 7]) {
    const nodes = [lnode("p", null, "department")];
    for (let i = 0; i < kids; i++) nodes.push(lnode("k" + i, "p"));
    const n = byId(layout({nodes, cross: []}).nodes);
    assert.ok(Math.abs(cx(n.get("p")) - (cx(n.get("k0")) + cx(n.get("k" + (kids - 1)))) / 2) < 1e-9, `${kids} children`);
  }
  for (let seed = 1; seed <= 40; seed++) {
    const g = randomGraph(seed, 60);
    const L = layout({nodes: g.nodes, cross: []});
    const n = byId(L.nodes);
    const kids = new Map();
    L.nodes.forEach(x => { if (x.parent !== null) kids.set(x.parent, (kids.get(x.parent) || []).concat(x.id)); });
    kids.forEach((list, parent) => {
      // x is rounded to a tenth of a pixel, so the middles agree to a tenth
      assert.ok(Math.abs(cx(n.get(parent)) - (cx(n.get(list[0])) + cx(n.get(list[list.length - 1]))) / 2) <= 0.1, `seed ${seed} ${parent}`);
    });
  }
});

test("a leaf takes one slot (178 px) and the slots follow the depth-first order, so siblings keep the order they were sent in", () => {
  const nodes = [lnode("p", null, "department")];
  FUNCTIONS.forEach(fn => nodes.push(lnode("p." + fn, "p", "function")));
  const L = layout({nodes, cross: []});
  const kids = L.nodes.filter(n => n.parent === "p");
  assert.deepEqual(kids.map(n => n.id), FUNCTIONS.map(fn => "p." + fn));
  kids.forEach((n, i) => {
    assert.equal(n.y, L.nodes[0].y + 132, "one row down: 54 + 78");
    if (i > 0) assert.equal(cx(n) - cx(kids[i - 1]), 178);
  });
  assert.equal(cx(L.nodes[0]), cx(kids[2]), "the department sits over the middle function");
});

test("function nodes of the sample stay in the order of the server and are never reordered by layout", () => {
  const L = layout(validate(sampleView()).graph);
  const row = L.nodes.filter(n => n.parent === "web").sort((a, b) => a.x - b.x).map(n => n.id);
  assert.deepEqual(row, ["web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit", "s-web"]);
});

test("trees side by side are one empty slot apart, and a lone root sits at the left edge", () => {
  const L = layout({nodes: [lnode("a", null, "department"), lnode("a1", "a"), lnode("b", null, "department"), lnode("b1", "b"), lnode("c", null, "step")], cross: []});
  const n = byId(L.nodes);
  assert.equal(cx(n.get("b1")) - cx(n.get("a1")), 2 * 178);
  assert.equal(cx(n.get("c")) - cx(n.get("b1")), 2 * 178);
  assert.equal(cx(n.get("a")), cx(n.get("a1")));
  const lone = layout({nodes: [lnode("r", null, "root")], cross: []});
  assert.deepEqual([lone.nodes[0].x, lone.nodes[0].y, lone.width, lone.height], [40, 40, 176, 114]);
});

test("rows are (tallest box + row gap) apart, whatever the kinds in a row", () => {
  // the tallest box of the whole graph is a department (54), so every row is 132 apart, even a row of steps (40)
  const L = layout({nodes: [lnode("d", null, "department"), lnode("s", "d", "step"), lnode("t", "s", "step"), lnode("u", "t", "step")], cross: []});
  assert.deepEqual(L.nodes.map(n => n.y), [40, 172, 304, 436]);
  const flat = layout({nodes: [lnode("r", null, "root"), lnode("s", "r", "step")], cross: []});
  assert.deepEqual(flat.nodes.map(n => n.y), [40, 40 + 40 + 78]);
});

test("the picture starts at the pad on the left and the top and ends a pad after the last box", () => {
  for (let seed = 1; seed <= 30; seed++) {
    const g = randomGraph(seed, 50);
    const L = layout(g);
    assert.equal(Math.min(...L.nodes.map(n => n.x)), 40, `seed ${seed}`);
    assert.equal(Math.min(...L.nodes.map(n => n.y)), 40);
    assert.equal(L.width, Math.max(...L.nodes.map(n => n.x + n.w)) + 40);
    assert.equal(L.height, Math.max(...L.nodes.map(n => n.y + n.h)) + 40);
  }
});

test("no two boxes overlap, in the sample and in 200 random trees of mixed kinds", () => {
  const check = (L, label) => {
    for (let i = 0; i < L.nodes.length; i++) {
      for (let j = i + 1; j < L.nodes.length; j++) assert.equal(overlap(L.nodes[i], L.nodes[j]), false, `${label}: ${L.nodes[i].id} and ${L.nodes[j].id}`);
    }
  };
  check(layout(validate(sampleView()).graph), "sample");
  for (let seed = 1; seed <= 200; seed++) check(layout(randomGraph(seed, 40)), "seed " + seed);
});

test("an empty graph is two pads square", () => {
  for (const empty of [{nodes: [], cross: []}, {}, null, undefined, "x", {nodes: "x"}]) {
    const L = layout(empty);
    assert.deepEqual(plain(L), {nodes: [], links: [], edges: [], width: 80, height: 80, warnings: []});
  }
  assert.deepEqual([layout({}, {pad: 10}).width, layout({}, {pad: 10}).height], [20, 20]);
});

test("the options replace pad, slot, row gap, rise and sizes; a value that is not a usable number is ignored", () => {
  const g = {nodes: [lnode("r", null, "root"), lnode("a", "r", "step"), lnode("b", "r", "step")], cross: []};
  const base = layout(g);
  const custom = layout(g, {pad: 10, slot: 200, rowGap: 20, sizes: {step: {w: 100, h: 30}, root: {w: 60}}});
  const n = byId(custom.nodes);
  assert.deepEqual([n.get("a").x, n.get("a").y, n.get("a").w, n.get("a").h], [10, 10 + 34 + 20, 100, 30], "the tallest box is still the root (34)");
  assert.equal(n.get("b").x - n.get("a").x, 200);
  assert.deepEqual([n.get("r").w, n.get("r").h], [60, 34], "a size that gives only a width keeps the other side");
  assert.notDeepEqual(plain(custom), plain(base));
  const junk = [{pad: -1}, {pad: NaN}, {pad: "8"}, {slot: 0}, {slot: -5}, {slot: Infinity}, {rowGap: -1}, {rowGap: null}, {maxRise: -3}, {sizes: "x"}, {sizes: {step: {w: 0, h: -4}}}, {sizes: {step: null}}, "text", 5, null, undefined, []];
  junk.forEach(opts => assert.deepEqual(plain(layout(g, opts)), plain(base), JSON.stringify(opts)));
  assert.equal(layout(g, {pad: 0}).nodes.find(x => x.id === "a").x, 0, "a pad of 0 is a usable number");
  assert.equal(layout(g, {pad: 0.5}).nodes.find(x => x.id === "a").x, 0.5, "and so is a pad of half a pixel");
  const tight = byId(layout(g, {slot: 1}).nodes);
  assert.equal(tight.get("b").x - tight.get("a").x, 1, "a slot of 1 px is usable (the boxes then overlap, which is the caller's choice)");
  assert.equal(byId(layout(g, {slot: 0.5}).nodes).get("b").x - byId(layout(g, {slot: 0.5}).nodes).get("a").x, 0.5, "and so is half a pixel");
  const tiny = byId(layout(g, {sizes: {step: {w: 1, h: 0.5}}}).nodes).get("a");
  assert.deepEqual([tiny.w, tiny.h], [1, 0.5], "a box 1 wide and half a pixel high is usable");
  assert.equal(layout(g, {rowGap: 0}).nodes.find(x => x.id === "a").y, 40 + 40, "a gap of 0 is a usable number (the tallest box is a step, 40)");
});

test("a picture of boxes smaller than a pixel is as small as they are", () => {
  const L = layout({nodes: [lnode("a")], cross: []}, {pad: 0, sizes: {step: {w: 0.5, h: 0.2}}});
  assert.deepEqual([L.width, L.height, L.nodes[0].x, L.nodes[0].y], [0.5, 0.2, 0, 0]);
  const two = layout({nodes: [lnode("a"), lnode("b", "a")], cross: []}, {pad: 0, rowGap: 0, sizes: {step: {w: 0.5, h: 0.2}}});
  assert.deepEqual(two.nodes.map(n => n.y), [0, 0.2], "a row is the tallest box (0.2) plus the gap (0)");
  assert.deepEqual([two.width, two.height], [0.5, 0.4]);
});

test("a node whose kind has no size takes a step's size", () => {
  const L = layout({nodes: [lnode("a", null, "banana"), lnode("b", null, "constructor")], cross: []});
  assert.deepEqual(L.nodes.map(n => [n.w, n.h]), [[140, 40], [140, 40]]);
});

test("layout repairs a hand-made graph the way validate does and says so", () => {
  const L = layout({nodes: [lnode("a", "ghost"), lnode("b", "b"), lnode("c", "d"), lnode("d", "c"), lnode("a", null)], cross: []});
  assert.equal(L.nodes.length, 4);
  assert.equal(L.warnings.length, 4);
  assert.ok(L.nodes.every(n => n.depth >= 0));
});

test("layout keeps every field of a node and does not change the graph it is given", () => {
  const graph = deepFreeze(validate(sampleView()).graph);
  const L = layout(graph);
  const web = L.nodes.find(n => n.id === "web");
  assert.equal(web.label, "web");
  assert.equal(web.status, "waiting_on_you");
  assert.equal(web.parent, "root");
  assert.deepEqual(plain(layout(graph)), plain(L));
  assert.notEqual(web, graph.nodes.find(n => n.id === "web"));
});

test("the same input gives byte-identical output, twice and from a copy", () => {
  const graph = validate(sampleView()).graph;
  const a = JSON.stringify(layout(graph));
  assert.equal(JSON.stringify(layout(graph)), a);
  assert.equal(JSON.stringify(layout(JSON.parse(JSON.stringify(graph)))), a);
  assert.equal(JSON.stringify(layout(validate(sampleView()).graph)), a);
  for (let seed = 1; seed <= 10; seed++) {
    const g = randomGraph(seed, 80);
    assert.equal(JSON.stringify(layout(g)), JSON.stringify(layout(JSON.parse(JSON.stringify(g)))));
  }
});

test("500 nodes lay out in under 200 ms, and a very large graph and a very deep chain still lay out", () => {
  const g = randomGraph(7, 500);
  const best = Math.min(...[0, 1, 2].map(() => { const t = performance.now(); layout(g); return performance.now() - t; }));
  assert.ok(best < 200, `took ${best} ms`);
  assert.equal(layout(randomGraph(8, 4000)).nodes.length, 4000);
  const chain = [lnode("n0", null, "department")];
  for (let i = 1; i < 8000; i++) chain.push(lnode("n" + i, "n" + (i - 1), "step"));
  const L = layout({nodes: chain, cross: [clink("n0", "n7999")]});
  assert.equal(L.nodes[7999].depth, 7999);
  assert.equal(L.edges.length, 1);
});

/* ---------------------------------------------------------------- layout: tree links */
test("a tree link is an S-curve from the middle of the bottom of the parent to the middle of the top of the child", () => {
  const L = layout(validate(sampleView()).graph);
  const n = byId(L.nodes);
  L.links.forEach(l => {
    const from = n.get(l.from);
    const to = n.get(l.to);
    assert.equal(l.x1, cx(from));
    assert.equal(l.y1, from.y + from.h);
    assert.equal(l.x2, cx(to));
    assert.equal(l.y2, to.y);
    const mid = (l.y1 + l.y2) / 2;
    assert.equal(l.d, `M${l.x1},${l.y1} C${l.x1},${mid} ${l.x2},${mid} ${l.x2},${l.y2}`);
  });
  assert.deepEqual(L.links.map(l => l.to), L.nodes.filter(x => x.parent !== null).map(x => x.id), "one link per child, in node order");
});

/* ---------------------------------------------------------------- layout: cross links */
function crossLayout(cross, kinds = {}) {
  // a: row 0; b, c, d, e: row 1 (left to right); f: row 2 under b; g: row 2 under e
  const nodes = [lnode("a", null, kinds.a || "department"), lnode("b", "a"), lnode("c", "a"), lnode("d", "a"), lnode("e", "a", "step"), lnode("f", "b"), lnode("g", "e")];
  return layout({nodes, cross});
}

test("a cross link between two rows is an S-curve between the facing borders: down from a bottom to a top, up from a top to a bottom", () => {
  const L = crossLayout([clink("b", "f"), clink("g", "c")]);
  const n = byId(L.nodes);
  const [down, up] = L.edges;
  assert.equal(down.y1, n.get("b").y + n.get("b").h);
  assert.equal(down.y2, n.get("f").y);
  assert.equal(up.y1, n.get("g").y);
  assert.equal(up.y2, n.get("c").y + n.get("c").h);
  [down, up].forEach(e => {
    const b = bezier(e.d);
    assert.deepEqual([b.p.x, b.p.y, b.q.x, b.q.y], [e.x1, e.y1, e.x2, e.y2]);
    const mid = (e.y1 + e.y2) / 2;
    assert.deepEqual([b.c1.x, b.c1.y, b.c2.x, b.c2.y], [e.x1, mid, e.x2, mid]);
    assert.equal(e.lx, (e.x1 + e.x2) / 2);
    assert.equal(e.ly, mid);
  });
  // it never meets the box at the middle, where the tree links are
  [[down, "b", "f"], [up, "g", "c"]].forEach(([e, from, to]) => {
    assert.notEqual(e.x1, cx(n.get(from)));
    assert.notEqual(e.x2, cx(n.get(to)));
  });
});

test("a cross link between two boxes of one row is an arc that rises min(60, 0.3 x the distance) above both tops", () => {
  const L = crossLayout([clink("b", "c"), clink("b", "e")]);
  const n = byId(L.nodes);
  const [near, far] = L.edges;
  [near, far].forEach(e => {
    assert.equal(e.y1, n.get("b").y);
    assert.equal(e.y2, n.get("b").y);
    const b = bezier(e.d);
    const rise = Math.min(60, 0.3 * Math.abs(e.x2 - e.x1));
    assert.ok(Math.abs(b.at(0.5).y - (e.y1 - rise)) < 0.2, `the top of the arc is ${rise} above the tops`);
    assert.ok(Math.abs(e.ly - (e.y1 - rise)) < 1e-9);
    assert.equal(e.lx, (e.x1 + e.x2) / 2);
    assert.ok(b.c1.y < e.y1 && b.c2.y < e.y2);
    assert.equal(b.c1.x, e.x1);
    assert.equal(b.c2.x, e.x2);
  });
  assert.ok(Math.abs(far.ly - (far.y1 - 60)) < 1e-9, "a long arc stops rising at 60");
  assert.ok(near.ly > far.ly && Math.abs(near.ly - (near.y1 - 0.3 * Math.abs(near.x2 - near.x1))) < 1e-9, "a short one rises by 0.3 of its length");
});

test("an arc never rises above y = 2, however far apart its ends are", () => {
  const L = layout({nodes: [lnode("a", null, "step"), lnode("b", null, "step")], cross: [clink("a", "b")]});
  const e = L.edges[0];
  assert.equal(e.y1, 40);
  assert.ok(Math.abs(bezier(e.d).at(0.5).y - 2) < 0.2);
  assert.ok(Math.abs(e.ly - 2) < 1e-9);
  const close = layout({nodes: [lnode("a", null, "step"), lnode("b", null, "step")], cross: [clink("a", "b")]}, {slot: 20, pad: 40});
  assert.ok(Math.abs(close.edges[0].ly - (40 - 0.3 * Math.abs(close.edges[0].x2 - close.edges[0].x1))) < 1e-9);
  const zero = layout({nodes: [lnode("a", null, "step"), lnode("b", null, "step")], cross: [clink("a", "b")]}, {pad: 2});
  assert.equal(zero.edges[0].d.startsWith("M"), true);
  assert.ok(zero.edges[0].ly <= 2);
  const none = layout({nodes: [lnode("a", null, "step"), lnode("b", null, "step")], cross: [clink("a", "b")]}, {pad: 0, slot: 300});
  assert.equal(none.edges[0].ly, 0, "no room above the top row: no rise");
  assert.ok(none.edges[0].d.includes(" 0 C") === false);
});

test("the options maxRise and slot change how high an arc rises", () => {
  const g = {nodes: [lnode("a", null, "department"), lnode("b", "a"), lnode("c", "a")], cross: [clink("b", "c")]};
  assert.ok(Math.abs(layout(g, {maxRise: 10}).edges[0].ly - (172 - 10)) < 1e-9);
  assert.ok(Math.abs(layout(g, {maxRise: 100}).edges[0].ly - (172 - 0.3 * Math.abs(layout(g, {maxRise: 100}).edges[0].x2 - layout(g, {maxRise: 100}).edges[0].x1))) < 1e-9);
  assert.equal(layout(g, {maxRise: 0}).edges[0].ly, 172, "a rise of 0 is a usable number: a flat link");
});

test("edges carry id, ends, kind, label and the path; the id is kind:from>to as the library names an edge", () => {
  const L = crossLayout([clink("b", "c", "speaks_to", "3"), clink("c", "b", "depends_on", "revises"), clink("b", "f", "mystery", "")]);
  assert.deepEqual(L.edges.map(e => [e.id, e.from, e.to, e.kind, e.label]), [
    ["speaks_to:b>c", "b", "c", "speaks_to", "3"], ["depends_on:c>b", "c", "b", "depends_on", "revises"], ["mystery:b>f", "b", "f", "mystery", ""]]);
  L.edges.forEach(e => {
    ["x1", "y1", "x2", "y2", "lx", "ly"].forEach(k => assert.equal(typeof e[k], "number", k));
    assert.match(e.d, /^M[\d.,]+ C[\d.,]+ [\d.,]+ [\d.,]+$/);
  });
});

test("loop is true for a link with a reverse twin of the same kind, and only then", () => {
  const L = crossLayout([clink("b", "c", "handoff"), clink("c", "b", "handoff"), clink("b", "d", "handoff"), clink("d", "b", "speaks_to", "1"), clink("c", "d", "depends_on"),
    clink("d", "e", "step"), clink("e", "c", "step"), clink("c", "e", "step"), clink("b", "e", "handoff"), clink("f", "g", "handoff"), clink("g", "f", "handoff")]);
  const loops = Object.fromEntries(L.edges.map(e => [e.id, e.loop]));
  assert.deepEqual(loops, {
    "handoff:b>c": true, "handoff:c>b": true,           // a pair of the same kind
    "handoff:b>d": false, "speaks_to:d>b": false,       // the same two boxes, another kind each
    "depends_on:c>d": false, "step:d>e": false,         // one way only
    "step:e>c": true, "step:c>e": true,                 // a pair of the same kind
    "handoff:b>e": false,
    "handoff:f>g": true, "handoff:g>f": true,           // a pair across rows
  });
  assert.ok(L.edges.every(e => typeof e.loop === "boolean"));
});

test("a three-step ring is not a loop: a loop is a pair", () => {
  const L = crossLayout([clink("b", "c"), clink("c", "d"), clink("d", "b")]);
  assert.deepEqual(L.edges.map(e => e.loop), [false, false, false]);
});

test("a cross link that cannot be drawn is skipped with a warning and the others stand", () => {
  const L = crossLayout([clink("b", "ghost"), clink("ghost", "b"), clink("b", "b"), clink("b", "c", "handoff"), clink("b", "c", "handoff"), clink("b", "c", "speaks_to"), null, 4, {to: "c"}, {from: "b"}, clink("c", "b")]);
  assert.deepEqual(L.edges.map(e => e.id), ["handoff:b>c", "speaks_to:b>c", "handoff:c>b"]);
  assert.equal(L.warnings.length, 8);
  assert.equal(L.warnings.filter(w => /not drawn and is skipped/.test(w)).length, 6);
  assert.ok(L.warnings.some(w => /joins a node to itself/.test(w)));
  assert.ok(L.warnings.some(w => /appears twice/.test(w)));
  assert.equal(L.edges[0].loop, true, "the repeated link does not count twice, the twin still makes a loop");
});

test("a link with no kind is drawn as a step link; cross is optional", () => {
  const L = crossLayout([{from: "b", to: "c"}, {from: "b", to: "d", kind: ""}, {from: "b", to: "e", kind: 4}]);
  assert.deepEqual(L.edges.map(e => e.kind), ["step", "step", "step"]);
  assert.deepEqual(L.edges.map(e => e.label), ["", "", ""]);
  const none = layout({nodes: [lnode("a")], cross: "x"});
  assert.deepEqual(none.edges, []);
  assert.deepEqual(layout({nodes: [lnode("a")]}).edges, []);
});

test("the ends of cross links on one side of one box are apart, off the middle and inside the box, whoever is at the other end", () => {
  for (let seed = 1; seed <= 60; seed++) {
    const g = randomGraph(seed, 40);
    const L = layout(g);
    const n = byId(L.nodes);
    const ends = new Map();
    L.edges.forEach(e => {
      [[e.from, e.x1, e.y1], [e.to, e.x2, e.y2]].forEach(([id, x, y]) => {
        const box = n.get(id);
        const side = y === box.y ? "top" : y === box.y + box.h ? "bottom" : null;
        assert.ok(side, `${seed} ${e.id} meets ${id} on a top or a bottom edge`);
        const key = id + "|" + side;
        if (!ends.has(key)) ends.set(key, []);
        ends.get(key).push(x);
        assert.notEqual(x, cx(box), "the middle is for the tree links");
        assert.ok(x > box.x && x < box.x + box.w);
        assert.ok(Math.abs(x - cx(box)) <= box.w / 2 - 10 + 1e-9, "at least 10 px from a corner");
      });
    });
    ends.forEach((xs, key) => {
      assert.equal(new Set(xs).size, xs.length, `${seed} ${key}: two ends at one point`);
      const sorted = xs.slice().sort((a, b) => a - b);
      const gaps = sorted.slice(1).map((x, i) => x - sorted[i]);
      assert.ok(gaps.every(gap => gap >= 0.1), `${seed} ${key} ends are apart`);
    });
  }
});

test("a link to the right leaves to the right of the middle and one to the left to the left; the nearest is nearest the middle", () => {
  const L = crossLayout([clink("c", "b"), clink("c", "d"), clink("c", "e")]);
  const n = byId(L.nodes);
  const mid = cx(n.get("c"));
  const [toB, toD, toE] = L.edges;
  assert.ok(toB.x1 < mid, "b is on the left");
  assert.ok(toD.x1 > mid && toE.x1 > mid, "d and e are on the right");
  // arcs: the longest is innermost (so that arcs from one box nest instead of crossing)
  assert.ok(toE.x1 < toD.x1, "the arc to e (the farther) starts nearer the middle than the arc to d");
  const S = crossLayout([clink("a", "f"), clink("a", "g"), clink("a", "c")]);
  const sn = byId(S.nodes);
  const bottoms = S.edges.filter(e => e.y1 === sn.get("a").y + sn.get("a").h);
  assert.equal(bottoms.length, 3, "three links go down from a: to f, g and c");
  const [toF, toG, toC] = bottoms;
  const mid2 = cx(sn.get("a"));
  assert.ok(toF.x1 < mid2 && toC.x1 < mid2 && toG.x1 > mid2, "f (under b) and c are left of a's middle; g (under e) is right of it");
  assert.ok(mid2 - toC.x1 < mid2 - toF.x1, "of the two on the left the nearer end (c) is nearer the middle");
});

test("with several links on a side the spacing is 12 px, or less when the box is small, and the nearest other end comes first", () => {
  const nodes = [lnode("a", null, "department")];
  for (let i = 0; i < 6; i++) nodes.push(lnode("k" + i, "a"));
  const g = {nodes: nodes.concat([lnode("t", "k0", "step")]), cross: []};
  // three links from the bottom of k0 to a row below? t is the only deeper box: use several links from a (row 0) to the row-2 box t
  const down = layout({nodes: g.nodes, cross: [clink("a", "t", "handoff"), clink("a", "t", "depends_on"), clink("a", "t", "speaks_to", "1")]});
  const a = down.nodes.find(n => n.id === "a");
  const xs = down.edges.map(e => e.x1);
  // all three target a box left of a's middle (k0 is the leftmost leaf), so they leave left of the middle, 12 px apart
  assert.ok(xs.every(x => x < cx(a)));
  assert.deepEqual(xs.map(x => Math.round((cx(a) - x) * 10) / 10).sort((p, q) => p - q), [12, 24, 36]);
  // a small box: the room (w/2 - 10) is shared out
  const small = layout({nodes: g.nodes, cross: [clink("a", "t", "handoff"), clink("a", "t", "depends_on"), clink("a", "t", "speaks_to", "1")]}, {sizes: {department: {w: 60, h: 54}}});
  const sa = small.nodes.find(n => n.id === "a");
  const offs = small.edges.map(e => Math.round((cx(sa) - e.x1) * 10) / 10).sort((p, q) => p - q);
  assert.deepEqual(offs, [6.7, 13.3, 20], "20 / 3 = 6.67, shown to a tenth");
  // a box with no room keeps all ends in the middle rather than outside it
  const tiny = layout({nodes: g.nodes, cross: [clink("a", "t", "handoff"), clink("a", "t", "depends_on")]}, {sizes: {department: {w: 10, h: 54}}});
  const ta = tiny.nodes.find(n => n.id === "a");
  assert.deepEqual(tiny.edges.map(e => e.x1), [cx(ta), cx(ta)]);
});

test("two links between the same two boxes run side by side and do not cross", () => {
  const L = crossLayout([clink("b", "f", "handoff"), clink("b", "f", "depends_on"), clink("c", "e", "handoff"), clink("c", "e", "speaks_to", "2")]);
  const [h, d] = L.edges;
  assert.notEqual(h.x1, d.x1);
  assert.notEqual(h.x2, d.x2);
  assert.ok((h.x1 - d.x1) * (h.x2 - d.x2) > 0, "the order of the ends is the same at both boxes, so the curves do not cross");
  const [x, y] = L.edges.slice(2);
  assert.ok((x.x1 - y.x1) * (x.x2 - y.x2) < 0, "two arcs between one pair nest: the order of their ends is reversed");
  const outer = Math.abs(x.x2 - x.x1) > Math.abs(y.x2 - y.x1) ? x : y;
  const inner = outer === x ? y : x;
  const o = bezier(outer.d);
  const i = bezier(inner.d);
  assert.ok(Math.abs(o.q.x - o.p.x) > Math.abs(i.q.x - i.p.x));
  const dense = Array.from({length: 4001}, (_, k) => o.at(k / 4000));
  for (let t = 0.05; t < 1; t += 0.05) {
    const p = i.at(t);
    // the outer arc, at the same x, is higher (a smaller y)
    const q = dense.reduce((best, c) => (Math.abs(c.x - p.x) < Math.abs(best.x - p.x) ? c : best));
    assert.ok(q.y <= p.y + 0.5, `the inner arc stays under the outer one at t=${t.toFixed(2)}`);
  }
});

// every ordering of a list
const permutations = list => (list.length <= 1 ? [list] : list.flatMap((item, i) => permutations(list.slice(0, i).concat(list.slice(i + 1))).map(rest => [item].concat(rest))));

test("a link to a box right above or below leaves to the right of the middle: the middle is for the tree link", () => {
  const L = crossLayout([clink("b", "f"), clink("f", "b")]);
  const n = byId(L.nodes);
  assert.equal(cx(n.get("b")), cx(n.get("f")), "f is right under b");
  const [down, up] = L.edges;
  assert.ok(down.x1 > cx(n.get("b")) && down.x2 > cx(n.get("f")), "b to f: right of the middle at both ends");
  assert.ok(up.x1 > cx(n.get("f")) && up.x2 > cx(n.get("b")), "f to b too");
});

test("the order of the ends on a box comes from where the other ends are, not from the order the links came in", () => {
  // a is the parent of b, c, d, e (left to right): b and e are far, c and d near; a's middle is between c and d
  const links = ["b", "c", "d", "e"].map(to => clink("a", to));
  permutations(links).forEach(order => {
    const L = crossLayout(order);
    const n = byId(L.nodes);
    const at = Object.fromEntries(L.edges.map(e => [e.to, e.x1]));
    const mid = cx(n.get("a"));
    // S-curves leave the bottom of a: on each side the nearest other end is nearest the middle
    assert.ok(at.c < mid && at.b < at.c, order.map(l => l.to).join() + ": left side, c nearer than b");
    assert.ok(at.d > mid && at.e > at.d, order.map(l => l.to).join() + ": right side, d nearer than e");
  });
  // arcs from k2 along a row of five: on each side the farthest arc is innermost, whatever the order
  const row = [lnode("a", null, "department")];
  for (let i = 0; i < 5; i++) row.push(lnode("k" + i, "a", "step"));
  permutations([clink("k2", "k0"), clink("k2", "k1"), clink("k2", "k3"), clink("k2", "k4")]).forEach(order => {
    const L = layout({nodes: row, cross: order});
    const mid = cx(byId(L.nodes).get("k2"));
    const at = Object.fromEntries(L.edges.map(e => [e.to, e.x1]));
    assert.ok(at.k0 < mid && at.k1 < mid && at.k0 > at.k1, order.map(l => l.to).join() + ": left side, k0 (farther) is innermost");
    assert.ok(at.k3 > mid && at.k4 > mid && at.k4 < at.k3, order.map(l => l.to).join() + ": right side, k4 (farther) is innermost");
  });
});

test("two links between one pair of boxes never cross, whichever way round the boxes are and whichever link came first", () => {
  const pairs = [["e", "f"], ["f", "e"], ["c", "g"], ["g", "c"], ["b", "f"], ["f", "b"], ["a", "g"], ["g", "a"]];
  pairs.forEach(([from, to]) => {
    [false, true].forEach(swap => {
      const two = [clink(from, to, "handoff"), clink(from, to, "depends_on")];
      const [first, second] = layout({nodes: crossLayout([]).nodes, cross: swap ? two.slice().reverse() : two}).edges;
      assert.ok((first.x1 - second.x1) * (first.x2 - second.x2) > 0, `${from}>${to}${swap ? " reversed" : ""}: the order of the ends is the same at both boxes`);
      assert.ok(first.x1 < second.x1 && first.x2 < second.x2, `${from}>${to}${swap ? " reversed" : ""}: the link that came first is the left one at both ends`);
    });
  });
  const arcs = [["b", "e"], ["e", "b"], ["c", "d"], ["d", "c"], ["b", "c"], ["c", "b"]];
  arcs.forEach(([from, to]) => {
    [false, true].forEach(swap => {
      const two = [clink(from, to, "handoff"), clink(from, to, "depends_on")];
      const [first, second] = layout({nodes: crossLayout([]).nodes, cross: swap ? two.slice().reverse() : two}).edges;
      assert.ok((first.x1 - second.x1) * (first.x2 - second.x2) < 0, `${from}>${to}${swap ? " reversed" : ""}: arcs nest, so the order is reversed at the two ends`);
      assert.ok(Math.abs(first.x2 - first.x1) > Math.abs(second.x2 - second.x1), `${from}>${to}${swap ? " reversed" : ""}: the arc that came first is the outer one`);
    });
  });
});

test("the ends on the top of a box and the ends on its bottom are two separate rows of ports", () => {
  const L = crossLayout([clink("b", "c"), clink("b", "f")]);        // an arc to the right along the top, an S-curve straight down from the bottom
  const b = byId(L.nodes).get("b");
  const [arc, down] = L.edges;
  assert.equal(arc.y1, b.y);
  assert.equal(down.y1, b.y + b.h);
  assert.equal(arc.x1 - cx(b), 12, "the first port on the top");
  assert.equal(down.x1 - cx(b), 12, "and the first port on the bottom, not the second");
  // two arcs on the top of b (c is one slot to its right, d two) and two S-curves on its bottom (f is right under it)
  const both = crossLayout([clink("b", "c"), clink("d", "b"), clink("b", "f"), clink("f", "b")]);
  const middle = cx(byId(both.nodes).get("b"));
  const top = [];
  const bottom = [];
  both.edges.forEach(e => {
    [[e.from, e.x1, e.y1], [e.to, e.x2, e.y2]].filter(([id]) => id === "b").forEach(([, x, y]) => (y === b.y ? top : bottom).push(x - middle));
  });
  assert.deepEqual(top.sort((p, q) => p - q), [12, 24], "the arcs take the first two places on the top");
  assert.deepEqual(bottom.sort((p, q) => p - q), [12, 24], "the S-curves take the first two on the bottom");
});

test("arcs from one box nest: the longer arc starts nearer the middle, on either side", () => {
  const nodes = [lnode("a", null, "department")];
  for (let i = 0; i < 5; i++) nodes.push(lnode("k" + i, "a", "step"));
  const L = layout({nodes, cross: [clink("k2", "k3"), clink("k2", "k4"), clink("k2", "k1"), clink("k2", "k0")]});
  const n = byId(L.nodes);
  const mid = cx(n.get("k2"));
  const byTo = Object.fromEntries(L.edges.map(e => [e.to, e]));
  assert.ok(byTo.k4.x1 < byTo.k3.x1 && byTo.k3.x1 > mid && byTo.k4.x1 > mid);
  assert.ok(byTo.k0.x1 > byTo.k1.x1 && byTo.k1.x1 < mid && byTo.k0.x1 < mid);
});

test("a box with links on both the top (arcs, up links) and the bottom keeps them apart", () => {
  const L = crossLayout([clink("b", "f"), clink("c", "b"), clink("b", "d"), clink("f", "b"), clink("g", "b")]);
  const n = byId(L.nodes);
  const b = n.get("b");
  const mine = [];
  L.edges.forEach(e => {
    if (e.from === "b") mine.push([e.x1, e.y1 === b.y ? "top" : "bottom"]);
    if (e.to === "b") mine.push([e.x2, e.y2 === b.y ? "top" : "bottom"]);
  });
  assert.equal(mine.length, 5);
  for (const side of ["top", "bottom"]) {
    const xs = mine.filter(m => m[1] === side).map(m => m[0]);
    assert.equal(new Set(xs).size, xs.length, side);
  }
});

test("layout of a validated sample gives every cross link a path between its two boxes", () => {
  const L = layout(validate(sampleView()).graph);
  assert.deepEqual(L.warnings, []);
  assert.deepEqual(L.edges.map(e => e.id), ["handoff:web.identity>web.adaptation", "handoff:web.audit>web.identity", "speaks_to:web.identity>web.coordination",
    "depends_on:web.audit>web.priority", "step:web.identity>s-web"]);
  const n = byId(L.nodes);
  L.edges.forEach(e => {
    const from = n.get(e.from);
    const to = n.get(e.to);
    assert.ok(e.x1 >= from.x && e.x1 <= from.x + from.w);
    assert.ok(e.x2 >= to.x && e.x2 <= to.x + to.w);
  });
  assert.ok(L.edges.every(e => e.loop === false));
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

test("nothing validate, layout and diff are given can make them throw, but a value that is not a graph, and the picture is always whole", () => {
  const f = fuzzer(20261104);
  const nodeOf = i => ({id: f.next() < 0.9 ? "n" + (i % 12) : f.value(), kind: f.pick(["root", "department", "division", "function", "step", f.value()]), label: f.value(),
    status: f.pick(["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made", "archived", f.value()]), detail: f.value(), meta: f.value(),
    fn: f.value(), step_ref: f.value(), version: f.value(), parent: f.value()});
  const end = () => (f.next() < 0.9 ? "n" + Math.floor(f.next() * 12) : f.value());
  let boxes = 0;
  let paths = 0;
  let warned = 0;
  for (let round = 0; round < 400; round++) {
    const graphView = {nodes: Array.from({length: Math.floor(f.next() * 14)}, (_, i) => nodeOf(i)),
      edges: Array.from({length: Math.floor(f.next() * 20)}, () => ({src: end(), dst: end(), kind: f.pick(["contains", "has_function", "has_step", "handoff", "depends_on", "speaks_to", "step", f.value()]), label: f.value()}))};
    const {graph, warnings} = validate(graphView);
    assert.ok(warnings.every(w => typeof w === "string"));
    warned += warnings.length;
    const L = layout(graph, f.value());
    boxes += L.nodes.length;
    paths += L.edges.length;
    assert.ok(L.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y) && n.w > 0 && n.h > 0), "every box has a place");
    assert.ok(L.edges.every(e => /^M[-\d.,]+ C[-\d.,]+ [-\d.,]+ [-\d.,]+$/.test(e.d)), "every path is well formed");
    assert.equal(L.nodes.length, new Set(L.nodes.map(n => n.id)).size);
    for (let i = 0; i < L.nodes.length; i++) for (let j = i + 1; j < L.nodes.length; j++) assert.equal(overlap(L.nodes[i], L.nodes[j]), false);
    layout({nodes: f.value(), cross: f.value()}, f.value());
    diff(f.value(), graph);
    diff(graph, f.value());
    forest(f.value());
  }
  assert.ok(boxes > 1500 && paths > 400 && warned > 1000, `the garbage was not empty: ${boxes} boxes, ${paths} links, ${warned} warnings`);
});

/* ---------------------------------------------------------------- diff */
test("diff says which nodes were added, removed or changed their status, in the order of the lists", () => {
  const a = validate(view([rawNode("r", "root"), rawNode("x"), rawNode("y"), rawNode("z")])).graph;
  const b = validate(view([rawNode("r", "root", {status: "running"}), rawNode("n1"), rawNode("y", "step", {status: "fault"}), rawNode("z"), rawNode("n2")])).graph;
  assert.deepEqual(plain(diff(a, b)), {added: ["n1", "n2"], removed: ["x"], status: [{id: "r", from: "idle", to: "running"}, {id: "y", from: "idle", to: "fault"}]});
  assert.deepEqual(plain(diff(b, a)), {added: ["x"], removed: ["n1", "n2"], status: [{id: "r", from: "running", to: "idle"}, {id: "y", from: "fault", to: "idle"}]});
  assert.deepEqual(plain(diff(a, a)), {added: [], removed: [], status: []});
});

test("diff with no earlier picture adds every node; with no later one removes every node", () => {
  const g = validate(sampleView()).graph;
  for (const none of [undefined, null, {}, {nodes: "x"}, 5, "x", []]) {
    assert.deepEqual(diff(none, g).added, g.nodes.map(n => n.id));
    assert.deepEqual(diff(none, g).removed, []);
    assert.deepEqual(diff(g, none).removed, g.nodes.map(n => n.id));
    assert.deepEqual(diff(g, none).added, []);
  }
  assert.deepEqual(plain(diff(undefined, undefined)), {added: [], removed: [], status: []});
});

test("diff reads layouts as well as graphs, ignores nodes that have no id and keeps the first of a repeated id", () => {
  const g1 = validate(sampleView()).graph;
  const l1 = layout(g1);
  const v2 = sampleView();
  v2.nodes.find(n => n.id === "web.audit").status = "fault";
  const g2 = validate(v2).graph;
  const expected = {added: [], removed: [], status: [{id: "web.audit", from: "idle", to: "fault"}]};
  assert.deepEqual(plain(diff(g1, g2)), expected);
  assert.deepEqual(plain(diff(l1, layout(g2))), expected);
  assert.deepEqual(plain(diff(l1, g2)), expected);
  const odd = diff({nodes: [{id: "a", status: "idle"}, {id: "a", status: "fault"}, {status: "x"}, null, 4, {id: 3}]}, {nodes: [{id: "a", status: "idle"}, {id: "a", status: "running"}]});
  assert.deepEqual(plain(odd), {added: [], removed: [], status: []});
});

test("diff counts only a change of status, not of any other field", () => {
  const a = {nodes: [{id: "a", status: "idle", label: "x", detail: "1"}]};
  const b = {nodes: [{id: "a", status: "idle", label: "y", detail: "2"}]};
  assert.deepEqual(plain(diff(a, b)), {added: [], removed: [], status: []});
});
